//! The IPC surface exposed to the WebView2 frontend.
//!
//! Every `#[tauri::command]` here is reachable from JavaScript through
//! `invoke("<fn name>", { ...args })`. Commands stay thin: they validate input,
//! delegate to [`crate::windows`] or to a plain helper, and return serializable
//! structs. Failures come back as `Result::Err(String)` and surface in the
//! frontend as a rejected promise.

use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use serde::Serialize;
use tauri::AppHandle;

use crate::{windows, HUD_LABEL, JARVIS_SERVER_URL, LITELLM_URL, OLLAMA_URL};

/// JPEG quality for desktop captures. 82 keeps text legible while staying well
/// under the size at which a base64 data URI becomes painful over IPC.
const JPEG_QUALITY: u8 = 82;
/// Captures wider than this are downscaled before encoding. A raw 4K frame
/// base64-encodes to several megabytes, which is far more than a vision model
/// needs and slow to hand across the IPC bridge.
const MAX_CAPTURE_WIDTH: u32 = 1920;
/// Per-service timeout for [`check_server_health`].
const HEALTH_TIMEOUT: Duration = Duration::from_millis(1_500);

// ---------------------------------------------------------------------------
// Payload types
// ---------------------------------------------------------------------------

/// A desktop capture, ready to be dropped into an `<img src>` or posted to a
/// vision endpoint.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CapturePayload {
    /// `data:image/jpeg;base64,…`
    pub data_uri: String,
    /// Width of the encoded image, after any downscale.
    pub width: u32,
    /// Height of the encoded image, after any downscale.
    pub height: u32,
    /// Size of the JPEG payload in bytes, before base64 expansion.
    pub bytes: usize,
    /// Milliseconds spent grabbing and encoding the frame.
    pub elapsed_ms: u128,
    /// Milliseconds since the Unix epoch.
    pub captured_at: u128,
}

/// The result of probing one local service.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ServiceStatus {
    /// Stable identifier: `"jarvis"`, `"ollama"` or `"litellm"`.
    pub id: &'static str,
    /// Human readable name for the UI.
    pub name: &'static str,
    /// The exact URL that was probed.
    pub url: String,
    /// True when the service answered with a 2xx.
    pub online: bool,
    /// HTTP status code, when the connection succeeded at all.
    pub http_status: Option<u16>,
    /// Round-trip time in milliseconds.
    pub latency_ms: u128,
    /// One-line explanation suitable for a tooltip.
    pub detail: String,
    /// Parsed JSON body, when the service returned one and it was small enough
    /// to be worth forwarding (the Ollama model list, for instance).
    pub payload: Option<serde_json::Value>,
}

/// The structured report returned by [`check_server_health`].
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HealthReport {
    /// Milliseconds since the Unix epoch.
    pub checked_at: u128,
    /// True when every probed service answered.
    pub all_online: bool,
    pub online_count: usize,
    pub total_count: usize,
    /// One-line summary, also used as the tray notification body.
    pub summary: String,
    pub services: Vec<ServiceStatus>,
}

// ---------------------------------------------------------------------------
// Small helpers shared across the crate
// ---------------------------------------------------------------------------

/// Milliseconds since the Unix epoch.
fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or_default()
}

/// Raises a Windows toast, logging (but swallowing) any failure — a missing
/// notification permission must never break the calling flow.
pub fn notify(app: &AppHandle, title: &str, body: &str) {
    use tauri_plugin_notification::NotificationExt;

    if let Err(err) = app.notification().builder().title(title).body(body).show() {
        eprintln!("[jarvis] notification failed: {err}");
    }
}

// ---------------------------------------------------------------------------
// Desktop capture
// ---------------------------------------------------------------------------

/// Grabs the primary display, encodes it as JPEG and returns a base64 data URI.
///
/// Split out of the command so the `Win+Shift+S` hotkey can run it on a worker
/// thread without going through the IPC layer.
pub fn capture_primary_display() -> Result<CapturePayload, String> {
    use image::{codecs::jpeg::JpegEncoder, ExtendedColorType, ImageEncoder};
    use screenshots::Screen;

    let started = Instant::now();

    let screens = Screen::all().map_err(|e| format!("unable to enumerate displays: {e}"))?;
    if screens.is_empty() {
        return Err("no display was reported by the compositor".to_string());
    }
    // Prefer the display Windows marks primary; fall back to the first one so a
    // multi-monitor rig with an odd configuration still captures something.
    let screen = screens
        .iter()
        .find(|s| s.display_info.is_primary)
        .unwrap_or(&screens[0]);

    let frame = screen
        .capture()
        .map_err(|e| format!("desktop capture failed: {e}"))?;

    let (raw_width, raw_height) = (frame.width(), frame.height());
    if raw_width == 0 || raw_height == 0 {
        return Err("the compositor returned an empty frame".to_string());
    }

    // `screenshots` hands back RGBA. Rebuilding the buffer from raw bytes keeps
    // this code independent of which `image` version the capture crate links.
    let rgba = image::RgbaImage::from_raw(raw_width, raw_height, frame.into_raw())
        .ok_or_else(|| "captured frame had an unexpected buffer length".to_string())?;

    let mut rgb = image::DynamicImage::ImageRgba8(rgba).to_rgb8();

    if rgb.width() > MAX_CAPTURE_WIDTH {
        let height =
            ((MAX_CAPTURE_WIDTH as u64 * rgb.height() as u64) / rgb.width() as u64).max(1) as u32;
        rgb = image::imageops::resize(
            &rgb,
            MAX_CAPTURE_WIDTH,
            height,
            image::imageops::FilterType::Triangle,
        );
    }

    let (width, height) = (rgb.width(), rgb.height());
    let mut jpeg: Vec<u8> = Vec::with_capacity(512 * 1024);
    JpegEncoder::new_with_quality(&mut jpeg, JPEG_QUALITY)
        .write_image(rgb.as_raw(), width, height, ExtendedColorType::Rgb8)
        .map_err(|e| format!("JPEG encoding failed: {e}"))?;

    let bytes = jpeg.len();
    let data_uri = format!("data:image/jpeg;base64,{}", BASE64.encode(&jpeg));

    Ok(CapturePayload {
        data_uri,
        width,
        height,
        bytes,
        elapsed_ms: started.elapsed().as_millis(),
        captured_at: now_ms(),
    })
}

/// Grabs the primary display and returns it as a base64 JPEG data URI.
///
/// Runs on a blocking worker so the WebView2 message loop is never stalled by
/// the grab-and-encode round trip.
#[tauri::command]
pub async fn capture_screen() -> Result<CapturePayload, String> {
    tauri::async_runtime::spawn_blocking(capture_primary_display)
        .await
        .map_err(|e| format!("capture worker panicked: {e}"))?
}

// ---------------------------------------------------------------------------
// Health checks
// ---------------------------------------------------------------------------

/// Probes one endpoint and shapes the outcome into a [`ServiceStatus`].
async fn probe(
    client: &reqwest::Client,
    id: &'static str,
    name: &'static str,
    url: String,
) -> ServiceStatus {
    let started = Instant::now();

    match client.get(&url).send().await {
        Ok(response) => {
            let status = response.status();
            let latency_ms = started.elapsed().as_millis();
            // Bodies are only forwarded when they are small and JSON — the
            // Ollama tag list is genuinely useful in the UI, a stray HTML error
            // page is not.
            let payload = response.json::<serde_json::Value>().await.ok();

            ServiceStatus {
                id,
                name,
                url,
                online: status.is_success(),
                http_status: Some(status.as_u16()),
                latency_ms,
                detail: if status.is_success() {
                    match (id, &payload) {
                        ("ollama", Some(body)) => {
                            let models = body
                                .get("models")
                                .and_then(|m| m.as_array())
                                .map(|m| m.len())
                                .unwrap_or(0);
                            format!("online — {models} model(s) loaded, {latency_ms} ms")
                        }
                        _ => format!("online — HTTP {} in {latency_ms} ms", status.as_u16()),
                    }
                } else {
                    format!("reachable but unhealthy — HTTP {}", status.as_u16())
                },
                payload,
            }
        }
        Err(err) => {
            let detail = if err.is_timeout() {
                format!("no answer within {} ms", HEALTH_TIMEOUT.as_millis())
            } else if err.is_connect() {
                "offline — nothing is listening on this port".to_string()
            } else {
                format!("unreachable — {err}")
            };
            ServiceStatus {
                id,
                name,
                url,
                online: false,
                http_status: None,
                latency_ms: started.elapsed().as_millis(),
                detail,
                payload: None,
            }
        }
    }
}

/// Pings the local Jarvis orchestrator, Ollama and LiteLLM, and returns a
/// structured report. All three are probed concurrently, so the command costs
/// roughly one timeout in the worst case rather than three.
#[tauri::command]
pub async fn check_server_health() -> Result<HealthReport, String> {
    let client = reqwest::Client::builder()
        .timeout(HEALTH_TIMEOUT)
        .connect_timeout(HEALTH_TIMEOUT)
        // These are loopback services; a proxy would only get in the way.
        .no_proxy()
        .build()
        .map_err(|e| format!("unable to build the HTTP client: {e}"))?;

    let (jarvis, ollama, litellm) = tokio::join!(
        probe(
            &client,
            "jarvis",
            "Jarvis Core",
            format!("{JARVIS_SERVER_URL}/api/status"),
        ),
        probe(
            &client,
            "ollama",
            "Ollama",
            format!("{OLLAMA_URL}/api/tags"),
        ),
        probe(
            &client,
            "litellm",
            "LiteLLM",
            format!("{LITELLM_URL}/health"),
        ),
    );

    let services = vec![jarvis, ollama, litellm];
    let online_count = services.iter().filter(|s| s.online).count();
    let total_count = services.len();
    let offline: Vec<&str> = services
        .iter()
        .filter(|s| !s.online)
        .map(|s| s.name)
        .collect();

    Ok(HealthReport {
        checked_at: now_ms(),
        all_online: online_count == total_count,
        online_count,
        total_count,
        summary: if offline.is_empty() {
            format!("All {total_count} services online.")
        } else {
            format!(
                "{online_count}/{total_count} online — offline: {}",
                offline.join(", ")
            )
        },
        services,
    })
}

// ---------------------------------------------------------------------------
// Window control
// ---------------------------------------------------------------------------

/// Hides the spotlight window.
#[tauri::command]
pub fn hide_quickbar(app: AppHandle) -> Result<(), String> {
    windows::hide_quickbar(&app).map_err(|e| e.to_string())
}

/// Shows, centres and focuses the spotlight window.
#[tauri::command]
pub fn show_quickbar(app: AppHandle) -> Result<(), String> {
    windows::show_quickbar(&app).map_err(|e| e.to_string())
}

/// Toggles the HUD window. Returns its new visibility.
#[tauri::command]
pub fn toggle_hud(app: AppHandle) -> Result<bool, String> {
    windows::toggle_hud(&app).map_err(|e| e.to_string())
}

/// Grows or shrinks the quickbar so the streaming answer card fits underneath
/// the input. The frontend calls this whenever the card's height changes.
#[tauri::command]
pub fn resize_quickbar(app: AppHandle, height: f64) -> Result<(), String> {
    windows::resize_quickbar(&app, height).map_err(|e| e.to_string())
}

/// Pins the quickbar open so it survives losing focus — used while the user is
/// reading a long answer or dragging a selection out of the card.
#[tauri::command]
pub fn set_quickbar_pinned(app: AppHandle, pinned: bool) -> bool {
    windows::set_quickbar_pinned(&app, pinned)
}

/// Reports whether the quickbar is currently pinned open.
#[tauri::command]
pub fn is_quickbar_pinned() -> bool {
    windows::is_quickbar_pinned()
}

// ---------------------------------------------------------------------------
// Clipboard, notifications, lifecycle
// ---------------------------------------------------------------------------

/// Copies text to the Windows clipboard (the answer card's copy button).
#[tauri::command]
pub fn write_clipboard(app: AppHandle, text: String) -> Result<(), String> {
    use tauri_plugin_clipboard_manager::ClipboardExt;

    app.clipboard()
        .write_text(text)
        .map_err(|e| format!("unable to write to the clipboard: {e}"))
}

/// Reads text from the Windows clipboard.
#[tauri::command]
pub fn read_clipboard(app: AppHandle) -> Result<String, String> {
    use tauri_plugin_clipboard_manager::ClipboardExt;

    app.clipboard()
        .read_text()
        .map_err(|e| format!("unable to read the clipboard: {e}"))
}

/// Raises a Windows toast from the frontend.
#[tauri::command]
pub fn notify_user(app: AppHandle, title: Option<String>, body: String) {
    notify(&app, title.as_deref().unwrap_or("Jarvis"), &body);
}

/// Shuts the application down for real, releasing the global shortcuts first.
#[tauri::command]
pub fn quit_app(app: AppHandle) {
    #[cfg(desktop)]
    {
        use tauri_plugin_global_shortcut::GlobalShortcutExt;
        let _ = app.global_shortcut().unregister_all();
    }
    // Closing the HUD explicitly stops WebView2 from logging a teardown warning
    // when the process exits while a remote origin is still loaded.
    if let Some(hud) = tauri::Manager::get_webview_window(&app, HUD_LABEL) {
        let _ = hud.destroy();
    }
    app.exit(0);
}
