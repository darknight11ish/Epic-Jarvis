//! The IPC surface exposed to the WebView2 frontend.
//!
//! Every `#[tauri::command]` here is reachable from JavaScript through
//! `invoke("<fn name>", { ...args })`. Commands stay thin: they validate input,
//! delegate to [`crate::windows`] or to a plain helper, and return serializable
//! structs. Failures come back as `Result::Err(String)` and surface in the
//! frontend as a rejected promise.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use serde::Serialize;
use tauri::{ipc::Channel, AppHandle, Manager, State};

use crate::{windows, ChatState, HUD_LABEL, LITELLM_URL, OLLAMA_URL};

/// JPEG quality for desktop captures. 82 keeps text legible while staying well
/// under the size at which a base64 data URI becomes painful over IPC.
const JPEG_QUALITY: u8 = 82;
/// Captures wider than this are downscaled before encoding. A raw 4K frame
/// base64-encodes to several megabytes, which is far more than a vision model
/// needs and slow to hand across the IPC bridge.
const MAX_CAPTURE_WIDTH: u32 = 1920;
/// Per-service timeout for [`check_server_health`].
const HEALTH_TIMEOUT: Duration = Duration::from_millis(1_500);
/// Connect timeout for the chat stream. There is deliberately no *total*
/// timeout: a long answer is a long-lived response body, and `Client::timeout`
/// would guillotine it mid-sentence.
const CHAT_CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
/// Value of the `X-Jarvis-Client` header. The server accepts a request whose
/// `Origin` is absent or unrecognised only when this marks it first-party.
const JARVIS_CLIENT: &str = "hud";
/// Approval decisions are a single small round trip, so they do get a total
/// timeout — unlike the chat stream.
const APPROVAL_TIMEOUT: Duration = Duration::from_secs(10);
/// A widget quick-capture is not streamed, but the model still has to answer,
/// so it gets a longer leash than an approval.
const CAPTURE_TIMEOUT: Duration = Duration::from_secs(45);

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

/// Where the desktop shell keeps the API base URL and the pairing token.
///
/// A store file rather than the page's `localStorage`, per DESKTOP-BUILD §3.1:
/// the port can change without a rebuild, and reading it from Rust means the
/// token reaches the webview only as the `JARVIS.set()` call at page load.
/// Largest chat line accepted before the stream is treated as broken.
const MAX_CHAT_LINE_BYTES: usize = 4 * 1024 * 1024;

pub const SETTINGS_STORE: &str = "jarvis-desktop.json";

/// Default API base. `JARVIS_HUD_PORT` defaults to 4719 in `jarvis_hud.py`;
/// this is the matching default, and the store overrides it.
pub const DEFAULT_BASE: &str = "http://127.0.0.1:4719";

/// The API base URL: the store first, then `JARVIS_HUD_BASE`, then the default.
///
/// Read rather than baked in, because the port is configuration — the last
/// resync turned on a wrong one having been hardcoded.
pub fn jarvis_base(app: &AppHandle) -> String {
    use tauri_plugin_store::StoreExt;

    app.store(SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get("base"))
        .and_then(|v| v.as_str().map(str::to_string))
        .or_else(|| std::env::var("JARVIS_HUD_BASE").ok())
        .map(|b| b.trim().trim_end_matches('/').to_string())
        .filter(|b| !b.is_empty())
        .unwrap_or_else(|| DEFAULT_BASE.to_string())
}

/// The pairing token: the store first, then the environment.
pub fn jarvis_token_for(app: &AppHandle) -> Option<String> {
    use tauri_plugin_store::StoreExt;

    app.store(SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get("token"))
        .and_then(|v| v.as_str().map(str::to_string))
        .or_else(|| jarvis_token().cloned())
        .or_else(|| token_from_config_dir(app))
        .map(|t| t.trim().to_string())
        .filter(|t| !t.is_empty())
}

/// The token the backend writes for itself on first run.
///
/// Third and last, deliberately: something typed into Settings wins, then the
/// environment, then this. It exists so the two halves agree without the owner
/// configuring anything — the server now always has a token, and a desktop
/// that did not know where to find it would be locked out of its own backend
/// by a secret generated on its behalf.
///
/// `OPENJARVIS_CONFIG_DIR` is honoured because the backend honours it. Reading
/// a different directory from the one the server wrote to is the whole failure
/// this is meant to avoid.
fn token_from_config_dir(app: &AppHandle) -> Option<String> {
    let dir = match std::env::var_os("OPENJARVIS_CONFIG_DIR") {
        Some(explicit) => std::path::PathBuf::from(explicit),
        // `app.path().home_dir()` rather than the `dirs` crate: Tauri already
        // resolves this and windows.rs already uses the same API for
        // widget.json. A new top-level crate for one lookup is a new thing to
        // audit and pin, which is the argument build.rs makes about
        // futures-util.
        None => app.path().home_dir().ok()?.join(".openjarvis"),
    };
    std::fs::read_to_string(dir.join("token"))
        .ok()
        .map(|t| t.trim().to_string())
        .filter(|t| !t.is_empty())
}

/// Every theme `theme.css` defines. Validated here rather than trusted from
/// the window, so a page cannot persist a value that resolves to no palette
/// and leaves every surface on the fallback colours.
pub const THEMES: &[&str] = &["deep-space", "ember", "paper", "high-contrast"];

/// The chosen theme, or the default when nothing has been chosen or the stored
/// value is one this build no longer ships.
#[tauri::command]
pub fn get_theme(app: AppHandle) -> String {
    use tauri_plugin_store::StoreExt;

    app.store(SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get("theme"))
        .and_then(|v| v.as_str().map(str::to_string))
        .filter(|t| THEMES.contains(&t.as_str()))
        .unwrap_or_else(|| THEMES[0].to_string())
}

/// Persists the theme and tells every open window at once.
///
/// The fan-out is the point. Four surfaces can be on screen together, and a
/// theme that changed in the window you clicked while the widget stayed cyan
/// would look like a bug rather than a setting.
#[tauri::command]
pub fn set_theme(app: AppHandle, theme: String) -> Result<String, String> {
    use tauri_plugin_store::StoreExt;

    let theme = theme.trim().to_string();
    if !THEMES.contains(&theme.as_str()) {
        return Err(format!(
            "`{theme}` is not a theme this build ships ({})",
            THEMES.join(", ")
        ));
    }
    let store = app
        .store(SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    store.set("theme", serde_json::Value::String(theme.clone()));
    store
        .save()
        .map_err(|e| format!("could not save the theme: {e}"))?;

    crate::emit_all(&app, crate::events::THEME_CHANGED, theme.clone());
    Ok(theme)
}

/// True once the owner has closed the first-run walkthrough.
///
/// Not a command: `windows.rs` decides whether to build the onboarding window
/// at all from this, before anything on screen could ask for it. The
/// walkthrough itself never checks its own flag — it only exists to close
/// itself, which is [`mark_onboarding_seen`] below.
pub fn onboarding_seen(app: &AppHandle) -> bool {
    use tauri_plugin_store::StoreExt;

    app.store(SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get("onboarding_seen"))
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
}

/// Persists that the walkthrough has been seen, so it never opens again, and
/// closes it — one command rather than two, since the page has no reason to
/// do either without the other.
#[tauri::command]
pub fn finish_onboarding(app: AppHandle) -> Result<(), String> {
    use tauri_plugin_store::StoreExt;

    let store = app
        .store(SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    store.set("onboarding_seen", serde_json::Value::Bool(true));
    store
        .save()
        .map_err(|e| format!("could not save onboarding state: {e}"))?;

    let window = app
        .get_webview_window(windows::ONBOARDING_LABEL)
        .ok_or_else(|| "the walkthrough window was not found".to_string())?;
    window
        .close()
        .map_err(|e| format!("unable to close the walkthrough: {e}"))
}

/// Reports the base and whether a token is configured — never the token
/// itself, so a log or a screenshot of this cannot leak it.
#[tauri::command]
pub fn get_api_settings(app: AppHandle) -> serde_json::Value {
    serde_json::json!({
        "base": jarvis_base(&app),
        "hasToken": jarvis_token_for(&app).is_some(),
        "bindAddress": supervised_bind_address(&app).unwrap_or_default(),
        "store": SETTINGS_STORE,
    })
}

/// The address a supervised backend should bind on, beyond loopback — empty
/// (the default) means "let the backend pick its own default", which is
/// loopback-only. Read by `sidecar::start()` when it launches the child.
///
/// Not the same setting as `base`: `base` is where THIS client's own windows
/// look for Jarvis (almost always loopback); this is where the backend
/// ALSO listens, so a phone on the same tailnet can reach it too. Two
/// different questions, so two different settings — conflating them would
/// mean a Tailscale address here also becoming the origin the desktop's own
/// webviews try to fetch, when they should keep talking to loopback.
pub fn supervised_bind_address(app: &AppHandle) -> Option<String> {
    use tauri_plugin_store::StoreExt;

    app.store(SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get("bind_address"))
        .and_then(|v| v.as_str().map(str::to_string))
        .map(|b| b.trim().to_string())
        .filter(|b| !b.is_empty())
}

/// Checks a bind address before it is persisted.
///
/// This is not `validate_base`: a bind address is a bare host (an IP, a
/// Tailscale `100.x` address, a hostname) with no scheme, path or port — the
/// backend derives the port itself from `JARVIS_HUD_PORT`. Empty is always
/// accepted; it means "clear this and let the backend bind loopback only",
/// the safe default.
///
/// `0.0.0.0` is refused outright rather than merely discouraged.
/// `docs/INSTALL.md` is explicit that this setting exists to reach a
/// specific tailnet address, never the whole network: "Bind to the specific
/// Tailscale address, not 0.0.0.0. Then the port is not reachable from the
/// café Wi-Fi at all." Typing the wildcard here would quietly turn a
/// same-tailnet feature into a same-network one — every device on whatever
/// Wi-Fi the machine is on, not just the owner's own tailnet — which is
/// exactly the "no public tunnel" line this project does not cross.
fn validate_bind_address(addr: &str) -> Result<(), String> {
    if addr.is_empty() {
        return Ok(()); // clearing it falls back to loopback-only
    }
    if addr == "0.0.0.0" || addr == "::" {
        return Err(
            "refusing to bind every network interface (0.0.0.0) — set the \
             machine's own Tailscale address instead, so this is reachable \
             from the tailnet and nowhere else"
                .to_string(),
        );
    }
    if addr.contains('/') || addr.contains('?') || addr.contains('#') || addr.contains('@') {
        return Err(
            "the bind address must be a bare host — no path, query, fragment \
                     or credentials"
                .to_string(),
        );
    }
    if addr.contains(':') {
        return Err(
            "the bind address must not include a port — the backend already \
             knows its port from JARVIS_HUD_PORT"
                .to_string(),
        );
    }
    if addr.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err("the bind address contains whitespace or control characters".to_string());
    }
    Ok(())
}

/// Persists the base URL, the token and the supervised bind address —
/// each optional, so a caller can change one without resending the others.
#[tauri::command]
pub fn set_api_settings(
    app: AppHandle,
    base: Option<String>,
    token: Option<String>,
    bind_address: Option<String>,
) -> Result<(), String> {
    use tauri_plugin_store::StoreExt;

    let store = app
        .store(SETTINGS_STORE)
        .map_err(|e| format!("unable to open the settings store: {e}"))?;
    if let Some(base) = base {
        let base = base.trim().trim_end_matches('/').to_string();
        validate_base(&base)?;
        store.set("base", serde_json::Value::String(base));
    }
    if let Some(token) = token {
        store.set("token", serde_json::Value::String(token.trim().to_string()));
    }
    if let Some(bind_address) = bind_address {
        let bind_address = bind_address.trim().to_string();
        validate_bind_address(&bind_address)?;
        store.set("bind_address", serde_json::Value::String(bind_address));
    }
    store
        .save()
        .map_err(|e| format!("unable to write the settings store: {e}"))
}

/// Checks a base URL before it is persisted.
///
/// This matters more than it looks. Every Rust-side request is built as
/// `format!("{base}/api/…")` and carries `X-Jarvis-Token` — and those requests
/// are made by reqwest, not the webview, so the CSP's `connect-src` does not
/// apply to them and `.no_proxy()` means nothing on the network sees them
/// either. A base pointing anywhere at all would therefore send the token, the
/// conversation and a full-desktop screenshot to that host, and keep doing it
/// after a restart.
///
/// It deliberately does NOT require loopback. The server supports binding off
/// the loopback interface — that is what `HUD_TOKEN` exists for, and what a
/// phone on a tailnet needs — so an allowlist of `127.0.0.1` would break a
/// supported deployment. What it enforces is shape: a bare origin, nothing
/// else, so the value cannot smuggle a path, a query, credentials or
/// whitespace into every URL the client builds.
fn validate_base(base: &str) -> Result<(), String> {
    if base.is_empty() {
        return Ok(()); // clearing it falls back to the default
    }
    let rest = base
        .strip_prefix("http://")
        .or_else(|| base.strip_prefix("https://"))
        .ok_or_else(|| "the base URL must start with http:// or https://".to_string())?;
    if rest.is_empty() {
        return Err("the base URL has no host".to_string());
    }
    if rest.contains('/') || rest.contains('?') || rest.contains('#') {
        return Err("the base URL must be an origin only — no path, query or fragment".to_string());
    }
    if rest.contains('@') {
        return Err("the base URL must not carry credentials".to_string());
    }
    if rest.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err("the base URL contains whitespace or control characters".to_string());
    }
    Ok(())
}

/// Shared secret for `X-Jarvis-Token`, read once from the environment.
///
/// `JARVIS_TOKEN` wins; `HUD_TOKEN` is accepted as the name the server itself
/// uses. Reading it here keeps it out of the pages the shell controls — the
/// quickbar, the widget, settings and the Brain never see it.
///
/// It is NOT true that the token never enters WebView2 memory, and this
/// comment used to claim that. `hud_bootstrap.js` substitutes the real value
/// into the HUD window's initialisation script, so any script in that
/// vendored page can read `window.JARVIS.token`. That is a deliberate
/// trade — the page needs a token to talk to the backend at all, and the
/// alternative was a second copy persisted in its localStorage — but it is
/// an exposure, and describing it as impossible is how the next person
/// builds something on a guarantee that is not there.
fn jarvis_token() -> Option<&'static String> {
    static TOKEN: OnceLock<Option<String>> = OnceLock::new();
    TOKEN
        .get_or_init(|| {
            ["JARVIS_TOKEN", "HUD_TOKEN"]
                .iter()
                .find_map(|name| std::env::var(name).ok())
                .map(|t| t.trim().to_string())
                .filter(|t| !t.is_empty())
        })
        .as_ref()
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

/// Where the pointer is, in the virtual-screen coordinate space.
///
/// `None` on any platform that is not Windows, and on any failure - callers
/// fall back to the primary display, which is what they did before.
fn cursor_point() -> Option<(i32, i32)> {
    #[cfg(windows)]
    {
        use windows_sys::Win32::Foundation::POINT;
        use windows_sys::Win32::UI::WindowsAndMessaging::GetCursorPos;
        let mut p = POINT { x: 0, y: 0 };
        // SAFETY: `p` is a valid, writable POINT for the duration of the call,
        // which is the function's only requirement.
        if unsafe { GetCursorPos(&mut p) } != 0 {
            return Some((p.x, p.y));
        }
        None
    }
    #[cfg(not(windows))]
    {
        None
    }
}

/// Grabs the display under the pointer, encodes it as JPEG and returns a
/// base64 data URI.
///
/// Split out of the command so the `Alt+Shift+S` hotkey can run it on a worker
/// thread without going through the IPC layer.
pub fn capture_primary_display() -> Result<CapturePayload, String> {
    use image::{codecs::jpeg::JpegEncoder, ExtendedColorType, ImageEncoder};
    use xcap::Monitor;

    let started = Instant::now();

    let monitors = Monitor::all().map_err(|e| format!("unable to enumerate displays: {e}"))?;
    if monitors.is_empty() {
        return Err("no display was reported by the compositor".to_string());
    }
    // The monitor under the pointer, not the primary one. "Capture my screen"
    // means the screen being looked at, and on a two-monitor desk the hotkey
    // was firing while the owner worked on the secondary and handing back a
    // picture of the other one - with no indication it had done so.
    //
    // Falls back to primary, then to the first display: `is_primary` is
    // fallible in xcap, and a display that will not answer that question is
    // not a reason to capture nothing.
    let monitor = cursor_point()
        .and_then(|(x, y)| Monitor::from_point(x, y).ok())
        .or_else(|| {
            monitors
                .iter()
                .find(|m| m.is_primary().unwrap_or(false))
                .cloned()
        })
        .unwrap_or_else(|| monitors[0].clone());
    let monitor = &monitor;

    let frame = monitor
        .capture_image()
        .map_err(|e| format!("desktop capture failed: {e}"))?;

    let (raw_width, raw_height) = (frame.width(), frame.height());
    if raw_width == 0 || raw_height == 0 {
        return Err("the compositor returned an empty frame".to_string());
    }

    // Rebuilt from raw bytes so this stays independent of which `image` version
    // the capture crate links against.
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
    headers: Option<reqwest::header::HeaderMap>,
) -> ServiceStatus {
    let started = Instant::now();

    // Ollama and the LiteLLM proxy are unauthenticated; Jarvis is not. Probing
    // it bare meant `_origin_ok` fell through to its `X-Jarvis-Client` check —
    // reqwest sends no Origin — and answered 403 every time, so the core dot
    // read "unhealthy" against a perfectly healthy server.
    let request = match headers {
        Some(headers) => client.get(&url).headers(headers),
        None => client.get(&url),
    };

    match request.send().await {
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
pub async fn check_server_health(app: AppHandle) -> Result<HealthReport, String> {
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
            format!("{}/api/status", jarvis_base(&app)),
            jarvis_headers(&app).ok(),
        ),
        probe(
            &client,
            "ollama",
            "Ollama",
            format!("{OLLAMA_URL}/api/tags"),
            None,
        ),
        probe(
            &client,
            "litellm",
            "LiteLLM",
            format!("{LITELLM_URL}/health"),
            None,
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
// Chat streaming
// ---------------------------------------------------------------------------

/// Shared `reqwest` client settings for talking to the Jarvis server.
///
/// There is deliberately no *total* timeout: a chat response is a long-lived
/// body, and `Client::timeout` covers the read as well as the connect, so it
/// would guillotine a long answer mid-sentence.
fn jarvis_client(total_timeout: Option<Duration>) -> Result<reqwest::Client, String> {
    let mut builder = reqwest::Client::builder()
        .connect_timeout(CHAT_CONNECT_TIMEOUT)
        // A loopback service; a proxy would only get in the way.
        .no_proxy();
    if let Some(timeout) = total_timeout {
        builder = builder.timeout(timeout);
    }
    builder
        .build()
        .map_err(|e| format!("unable to build the HTTP client: {e}"))
}

/// `X-Jarvis-Client` and, when configured, `X-Jarvis-Token`.
pub fn jarvis_headers(app: &AppHandle) -> Result<reqwest::header::HeaderMap, String> {
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "X-Jarvis-Client",
        reqwest::header::HeaderValue::from_static(JARVIS_CLIENT),
    );
    if let Some(token) = jarvis_token_for(app) {
        let value = reqwest::header::HeaderValue::from_str(&token).map_err(|_| {
            "JARVIS_TOKEN/HUD_TOKEN contains characters that cannot go in a header".to_string()
        })?;
        headers.insert("X-Jarvis-Token", value);
    }
    Ok(headers)
}

/// Opens a chat stream against the Jarvis server and forwards each line of the
/// response body to the frontend over `on_event`.
///
/// The request is made from Rust rather than from the WebView on purpose:
///
/// * no CORS and no preflight `OPTIONS` — a native client should not negotiate
///   with a browser sandbox to reach its own loopback service;
/// * the token stays in the backend instead of sitting in JavaScript memory
///   where a script injected into the HUD could read it;
/// * cancelling drops the response future, which drops the connection, which
///   stops the workstation generating tokens nobody is waiting for.
///
/// The future resolves when the body ends, and rejects with the failure text if
/// the request could not be completed — so the frontend learns the terminal
/// state from the promise and never has to infer it from silence.
///
/// Two fields this used to send are gone, because the server never read either.
///
/// `images: [dataUri]` was a sibling of `messages`. `jarvis_hud.py`'s
/// `_build_payload` forwards only `model / messages / stream / temperature /
/// max_tokens` upstream, and `images` appears nowhere in the server at all — so
/// the screenshot was encoded, sent, and dropped. Worse, `has_image` *is* read,
/// and routes the turn to a vision lane: the capture went to a vision model
/// that received no image and answered about nothing. The image now rides
/// inside the user message's content, which is the part the server forwards
/// verbatim, in the OpenAI shape the upstream `/v1/chat/completions` expects.
///
/// `note_target` was invented outright — zero hits in the server. The system
/// message the frontend already sends is the only mechanism that ever worked.
#[tauri::command]
pub async fn stream_chat(
    app: AppHandle,
    messages: Vec<serde_json::Value>,
    has_image: bool,
    auto: bool,
    on_event: Channel<String>,
) -> Result<(), String> {
    let cancel = app.state::<ChatState>().begin();
    let base = jarvis_base(&app);
    let headers = jarvis_headers(&app)?;

    let payload = serde_json::json!({
        "messages": messages,
        "has_image": has_image,
        "stream": true,
        "auto": auto,
    });

    // `notified()` consumes a permit left by `notify_one`, so a cancel that
    // lands before this future is polled still wins the race.
    let outcome = tokio::select! {
        result = pump_chat(base, headers, payload, &on_event) => result,
        _ = cancel.notified() => Ok(()),
    };

    app.state::<ChatState>().finish(&cancel);
    outcome
}

/// Cancels the stream in flight, if there is one.
///
/// Dropping the `pump_chat` future closes the HTTP connection, so the server
/// sees the client disappear immediately rather than after the model finishes.
#[tauri::command]
pub fn cancel_chat(state: State<'_, ChatState>) {
    state.cancel();
}

/// Drives one request to completion, forwarding whole lines as they arrive.
async fn pump_chat(
    base: String,
    headers: reqwest::header::HeaderMap,
    payload: serde_json::Value,
    on_event: &Channel<String>,
) -> Result<(), String> {
    let mut response = jarvis_client(None)?
        .post(format!("{base}/api/chat"))
        .headers(headers)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {base}. Is it running?")
            } else {
                format!("chat request failed: {e}")
            }
        })?;

    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        // This used to treat 409 as an approval gate. It is not: the server
        // returns 409 only from /api/approve and /api/deny, meaning "already
        // decided, expired, or unknown id". /api/chat never sends one, so the
        // special case was inventing a protocol. Gates arrive inside the
        // stream as `tier: "ask"` instead.
        let body = body.trim();
        return Err(if body.is_empty() {
            format!("the server answered HTTP {}", status.as_u16())
        } else {
            format!("the server answered HTTP {}: {body}", status.as_u16())
        });
    }

    // Lines are cut from raw bytes so a multi-byte character split across two
    // network chunks is never decoded half-way.
    let mut buffer: Vec<u8> = Vec::with_capacity(8 * 1024);

    while let Some(bytes) = response
        .chunk()
        .await
        .map_err(|e| format!("the stream broke: {e}"))?
    {
        buffer.extend_from_slice(&bytes);
        // Bounded for the same reason the event stream's is: a body with no
        // newline would grow this until the process dies.
        if buffer.len() > MAX_CHAT_LINE_BYTES {
            return Err(format!(
                "the chat stream sent {} bytes with no line break; treating it as broken",
                buffer.len()
            ));
        }
        while let Some(newline) = buffer.iter().position(|b| *b == b'\n') {
            let line: Vec<u8> = buffer.drain(..=newline).collect();
            let text = String::from_utf8_lossy(&line[..line.len() - 1])
                .trim_end_matches('\r')
                .to_string();
            // Blank lines are only SSE frame separators; dropping them here
            // saves an IPC hop per frame.
            if text.trim().is_empty() {
                continue;
            }
            on_event
                .send(text)
                .map_err(|e| format!("unable to deliver a chunk: {e}"))?;
        }
    }

    // Whatever is left without a trailing newline is still a line.
    let tail = String::from_utf8_lossy(&buffer).trim().to_string();
    if !tail.is_empty() {
        let _ = on_event.send(tail);
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Approval gates
// ---------------------------------------------------------------------------

/// Answers a pending autonomy approval.
///
/// `approved` picks the endpoint: `/api/approve` or `/api/deny`. Both carry
/// `{"id": …, "by": "desktop_spotlight"}` so the server can attribute the
/// decision to the machine the human was actually sitting at.
#[tauri::command]
pub async fn decide_approval(
    app: AppHandle,
    id: String,
    approved: bool,
) -> Result<serde_json::Value, String> {
    let id = id.trim();
    if id.is_empty() {
        return Err("that approval has no id to answer".to_string());
    }

    // Rule 4 - "block acting when the event stream is stale" - was enforced
    // in the webview and nowhere else: `syncApprovalButtons` in main.js,
    // the same guard in widget.js, and `jarvis-link.js`. This command is the
    // thing that actually sends the decision, and it posted unconditionally.
    // A disabled button is a courtesy, not a gate: any window holding the
    // `approvals` capability reaches this directly, and a page that has not
    // re-read its link state reaches it by accident.
    //
    // Stale means the queue could not be confirmed live, and answering a
    // queue you cannot confirm is how one action gets decided twice. The
    // server's 409 catches the second decision, but that is a backstop for a
    // race, not a licence to send a decision we already know is unfounded.
    //
    // Found by the jarvis-client branch, which had the same shape on its own
    // side: its `decisionBlocker` was consulted by `decide()` and by nothing
    // else, so `revert` went out ungated. See docs/CROSS-CLIENT-CONTRACT.md.
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(
            "the event stream is stale, so the approval queue cannot be confirmed live - \
             nothing can be answered until it reconnects"
                .to_string(),
        );
    }

    let endpoint = if approved { "approve" } else { "deny" };
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .post(format!("{}/api/{endpoint}", jarvis_base(&app)))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "id": id, "by": "desktop_spotlight" }))
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(&app))
            } else {
                format!("unable to {endpoint} `{id}`: {e}")
            }
        })?;

    let status = response.status();
    let body = response.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(format!(
            "the server answered HTTP {} to /{endpoint}: {}",
            status.as_u16(),
            body.trim()
        ));
    }

    // Every window that showed the gate needs to know it is answered — the
    // widget and the quickbar can both be displaying the same one.
    crate::emit_all(
        &app,
        crate::events::APPROVAL_RESOLVED,
        serde_json::json!({ "id": id, "approved": approved }),
    );

    Ok(serde_json::from_str(&body)
        .unwrap_or_else(|_| serde_json::json!({ "ok": true, "endpoint": endpoint, "raw": body })))
}

/// Records the route lane the quickbar last saw, so the widget's pill can show
/// it without running a stream of its own.
#[tauri::command]
pub fn set_route_lane(app: AppHandle, lane: String) {
    let state = app.state::<crate::RouteState>();
    let mut slot = state
        .lane
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    *slot = Some(lane);
}

// ---------------------------------------------------------------------------
// Desktop telemetry
// ---------------------------------------------------------------------------

/// One sample of machine state, pushed to the widget on a timer.
#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopTelemetry {
    pub cpu_percent: f32,
    pub ram_used_mb: u64,
    pub ram_total_mb: u64,
    pub gpu_temp_c: Option<u32>,
    pub gpu_util_percent: Option<u32>,
    pub vram_used_mb: Option<u64>,
    pub vram_total_mb: Option<u64>,
    /// `"local"` or `"cloud"`, mirroring the quickbar's route badge.
    pub route_lane: Option<String>,
    pub sampled_at: u128,
}

/// What `nvidia-smi` reports, with each field absent when the driver omits it.
#[derive(Debug, Clone, Copy, Default)]
struct GpuSample {
    temp_c: Option<u32>,
    util_percent: Option<u32>,
    vram_used_mb: Option<u64>,
    vram_total_mb: Option<u64>,
}

/// Set to false the first time `nvidia-smi` is missing, so a machine without an
/// NVIDIA GPU does not pay for a failed process spawn every few seconds.
static GPU_PROBE_ENABLED: AtomicBool = AtomicBool::new(true);

/// Reads temperature, utilisation and VRAM from `nvidia-smi`.
///
/// A process spawn rather than a crate: NVML bindings would add a dependency
/// and a runtime DLL requirement to read four numbers that the driver already
/// prints. `CREATE_NO_WINDOW` matters — without it a console window flashes on
/// every sample, which on a 3-second timer is unusable.
fn sample_gpu() -> Option<GpuSample> {
    if !GPU_PROBE_ENABLED.load(Ordering::Relaxed) {
        return None;
    }

    let mut command = std::process::Command::new("nvidia-smi");
    command.args([
        "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    // `Command::output()` blocks until the child exits, with no deadline. A
    // wedged NVIDIA driver — a reload, a lost GPU, an ECC fault — makes
    // `nvidia-smi` hang, and this runs inside the single telemetry task: the
    // `.await` in `lib.rs` would never resolve, freezing the widget's numbers
    // and the widget-position flush for the rest of the session, with one
    // blocking-pool thread parked forever and nothing printed anywhere.
    let Some(output) = run_with_deadline(command, GPU_PROBE_TIMEOUT) else {
        // Timed out and was killed. Do NOT latch: a driver that is busy now is
        // usually fine on the next tick.
        return None;
    };
    let output = match output {
        Ok(output) if output.status.success() => output,
        // The binary is not here. That is permanent, so stop asking.
        Err(_) => {
            GPU_PROBE_ENABLED.store(false, Ordering::Relaxed);
            return None;
        }
        // It ran and failed. `nvidia-smi` exits non-zero transiently — a
        // driver reload, `GPU is lost`, an ECC state, a query timed out on a
        // saturated card — and latching on one of those killed GPU telemetry
        // for the rest of the session.
        Ok(_) => return None,
    };

    let text = String::from_utf8_lossy(&output.stdout);
    let row = text.lines().next()?;
    let mut fields = row.split(',').map(|f| f.trim());

    Some(GpuSample {
        temp_c: fields.next().and_then(|v| v.parse().ok()),
        util_percent: fields.next().and_then(|v| v.parse().ok()),
        vram_used_mb: fields.next().and_then(|v| v.parse().ok()),
        vram_total_mb: fields.next().and_then(|v| v.parse().ok()),
    })
}

/// How long `nvidia-smi` gets before it is treated as not answering.
///
/// It normally replies in well under 100 ms. Two seconds is generous for a
/// loaded card and short enough that the telemetry tick is never held up.
const GPU_PROBE_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(2);

/// Runs a command with a deadline, killing it if it overruns.
///
/// `std::process` has no timeout and `wait_timeout` is not in std, so this
/// polls `try_wait`. Crude, and correct: the alternative is a probe that can
/// hang a background task for the life of the process.
///
/// `None` means it did not finish in time and has been killed. `Some(Err)`
/// means it could not be started at all — a different and permanent thing,
/// which is why the caller tells them apart.
fn run_with_deadline(
    mut command: std::process::Command,
    limit: std::time::Duration,
) -> Option<std::io::Result<std::process::Output>> {
    use std::io::Read;
    use std::process::Stdio;

    command.stdout(Stdio::piped()).stderr(Stdio::null());
    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(err) => return Some(Err(err)),
    };
    let deadline = std::time::Instant::now() + limit;
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                let mut stdout = Vec::new();
                if let Some(mut pipe) = child.stdout.take() {
                    let _ = pipe.read_to_end(&mut stdout);
                }
                return Some(Ok(std::process::Output {
                    status,
                    stdout,
                    stderr: Vec::new(),
                }));
            }
            Ok(None) => {
                if std::time::Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    eprintln!("[jarvis] a GPU probe overran {limit:?} and was killed");
                    return None;
                }
                std::thread::sleep(std::time::Duration::from_millis(25));
            }
            Err(err) => return Some(Err(err)),
        }
    }
}

/// Samples CPU, RAM and (when present) the GPU.
///
/// The [`System`] handle is reused across calls because `sysinfo` derives CPU
/// percentages from the delta between two refreshes; a fresh one every tick
/// would report zero forever.
pub fn sample_telemetry(
    system: &mut sysinfo::System,
    route_lane: Option<String>,
) -> DesktopTelemetry {
    system.refresh_cpu_usage();
    system.refresh_memory();

    let gpu = sample_gpu().unwrap_or_default();

    DesktopTelemetry {
        cpu_percent: system.global_cpu_usage(),
        ram_used_mb: system.used_memory() / (1024 * 1024),
        ram_total_mb: system.total_memory() / (1024 * 1024),
        gpu_temp_c: gpu.temp_c,
        gpu_util_percent: gpu.util_percent,
        vram_used_mb: gpu.vram_used_mb,
        vram_total_mb: gpu.vram_total_mb,
        route_lane,
        sampled_at: now_ms(),
    }
}

// ---------------------------------------------------------------------------
// Desktop widget
// ---------------------------------------------------------------------------

/// Hides the widget. The keyboard's way out of it.
///
/// The widget is `skipTaskbar` and `focus: false`, so once `toggle_widget` has
/// focused it there is no shell affordance to leave — no title bar, no taskbar
/// button, no Alt+Tab entry. Escape in the page calls this. It hides its own
/// window and nothing else, which is why it is granted to the widget and to no
/// one else.
#[tauri::command]
pub fn hide_widget(app: AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window(windows::WIDGET_LABEL)
        .ok_or_else(|| "the widget window was not found".to_string())?;
    window
        .hide()
        .map_err(|e| format!("unable to hide the widget: {e}"))
}

/// Expands or collapses the widget. `height` carries the frontend's measured
/// content height when it has one.
#[tauri::command]
pub fn resize_desktop_widget(
    app: AppHandle,
    expanded: bool,
    height: Option<f64>,
) -> Result<(), String> {
    windows::resize_widget(&app, expanded, height)
}

/// Floats the widget above everything (`true`) or lets active windows cover it.
#[tauri::command]
pub fn set_widget_always_on_top(app: AppHandle, always_on_top: bool) -> Result<(), String> {
    windows::set_widget_always_on_top(&app, always_on_top)
}

/// Shows or hides the widget. Returns its new visibility.
#[tauri::command]
pub fn toggle_widget(app: AppHandle) -> Result<bool, String> {
    windows::toggle_widget(&app)
}

/// Persists the widget's geometry immediately instead of waiting for the next
/// flush — used when the frontend knows the user has finished dragging.
#[tauri::command]
pub fn save_widget_position(app: AppHandle, x: Option<f64>, y: Option<f64>) -> Result<(), String> {
    let state = app.state::<windows::WidgetState>();
    if let (Some(x), Some(y)) = (x, y) {
        state.update(|prefs| {
            prefs.x = Some(x);
            prefs.y = Some(y);
        });
    }
    state.flush(&app);
    Ok(())
}

/// The widget's persisted geometry and mode, so it can paint its toggles
/// correctly on first load.
#[tauri::command]
pub fn get_widget_prefs(app: AppHandle) -> windows::WidgetPrefs {
    app.state::<windows::WidgetState>().snapshot()
}

/// Summons the quickbar with a note prefix already armed.
///
/// The widget cannot emit Tauri events itself without a broader capability
/// grant, so it asks the backend to do it — which also keeps one code path for
/// "arm a note", shared with the `Alt+Shift+N` hotkey.
#[tauri::command]
pub fn prefill_quickbar(app: AppHandle, target: String) -> Result<(), String> {
    let target = match target.trim().to_ascii_lowercase().as_str() {
        "joplin" | "vault" => "joplin",
        _ => "logseq",
    };
    windows::show_quickbar(&app)?;
    crate::emit_quickbar(&app, crate::events::QUICK_NOTE_SUMMON, target);
    Ok(())
}

/// Files a note without opening the quickbar.
///
/// The widget's capture field is a one-shot: it posts the turn with
/// `stream: false` and returns whatever the server replies, so the widget can
/// flash a confirmation without standing up a stream it would only close.
#[tauri::command]
pub async fn capture_note(app: AppHandle, target: String, text: String) -> Result<String, String> {
    let text = text.trim();
    if text.is_empty() {
        return Err("nothing to capture".to_string());
    }
    let target = match target.trim().to_ascii_lowercase().as_str() {
        "joplin" | "vault" => "joplin",
        _ => "logseq",
    };
    let instruction = if target == "joplin" {
        "Route this turn to the Joplin personal vault via create_joplin_note."
    } else {
        "Route this turn to the Logseq daily journal via append_logseq_journal. \
         Capture it verbatim unless asked to summarise."
    };

    let payload = serde_json::json!({
        "messages": [
            { "role": "system", "content": instruction },
            { "role": "user", "content": text },
        ],
        "has_image": false,
        "stream": false,
        // No `note_target`: the server has never read one. The system message
        // above is what actually routes the capture.
        "auto": true,
    });

    let response = jarvis_client(Some(CAPTURE_TIMEOUT))?
        .post(format!("{}/api/chat", jarvis_base(&app)))
        .headers(jarvis_headers(&app)?)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(&app))
            } else {
                format!("capture failed: {e}")
            }
        })?;

    let status = response.status();
    let body = response.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(format!(
            "the server answered HTTP {} to the capture: {}",
            status.as_u16(),
            body.trim()
        ));
    }
    // HTTP 200 means the CHAT completed. It does not mean a note was written:
    // this route asks a model to call `append_logseq_journal`, and a model can
    // decline, lack the tool, or answer in prose. `/api/chat` returns no
    // tool-execution receipt, so nothing here can honestly say "filed".
    //
    // What can be returned is the model's own account of what it did, which is
    // the closest thing to evidence the API offers. The widget shows it instead
    // of asserting a result.
    Ok(assistant_reply(&body))
}

/// Pulls the assistant's text out of whatever shape `/api/chat` answered with.
///
/// Non-streaming OpenAI puts it at `choices[0].message.content`; the streaming
/// shape uses `delta`; some proxies flatten it to a bare `content` or
/// `response`. Anything unrecognised comes back empty rather than as a slice of
/// raw JSON — a caller that shows this to a person needs a sentence or nothing.
fn assistant_reply(body: &str) -> String {
    let Ok(json) = serde_json::from_str::<serde_json::Value>(body) else {
        return String::new();
    };
    let choice = json.get("choices").and_then(|c| c.get(0));
    let text = choice
        .and_then(|c| c.get("message"))
        .and_then(|m| m.get("content"))
        .or_else(|| {
            choice
                .and_then(|c| c.get("delta"))
                .and_then(|d| d.get("content"))
        })
        .or_else(|| choice.and_then(|c| c.get("text")))
        .or_else(|| json.get("content"))
        .or_else(|| json.get("response"))
        .and_then(|v| v.as_str())
        .unwrap_or_default();
    text.trim().to_string()
}

#[cfg(test)]
mod capture_tests {
    use super::{assistant_reply, validate_bind_address, validate_external_url};

    #[test]
    fn reads_the_non_streaming_openai_shape() {
        let body = r#"{"choices":[{"message":{"role":"assistant","content":" Added to today's journal. "}}]}"#;
        assert_eq!(assistant_reply(body), "Added to today's journal.");
    }

    #[test]
    fn reads_the_streaming_and_flattened_shapes() {
        assert_eq!(
            assistant_reply(r#"{"choices":[{"delta":{"content":"ok"}}]}"#),
            "ok"
        );
        assert_eq!(assistant_reply(r#"{"response":"filed"}"#), "filed");
    }

    #[test]
    fn an_unrecognised_shape_yields_nothing_rather_than_raw_json() {
        // The caller puts this in front of a person. A slice of JSON in a
        // 320px flash is worse than no sentence at all.
        assert_eq!(assistant_reply(r#"{"weird":{"nested":1}}"#), "");
        assert_eq!(assistant_reply("not json at all"), "");
    }

    /// The trick this exists for: the visible text, the apparent host and the
    /// real destination can be three different things.
    #[test]
    fn a_url_with_userinfo_is_refused() {
        assert!(validate_external_url("https://github.com@evil.example/").is_err());
        assert!(validate_external_url("http://user:pass@evil.example").is_err());
        // Backslash folds to `/` in a real URL parser, so a `@`-only check
        // could be stepped around with it.
        assert!(validate_external_url("https://example.com\\@evil.example").is_err());
    }

    /// CONTROL: the ordinary case still opens, or this is just a deny-all.
    #[test]
    fn a_plain_url_still_opens() {
        assert!(validate_external_url("https://github.com/anthropics").is_ok());
        assert!(validate_external_url("http://127.0.0.1:4719/api/status").is_ok());
        // A `@` after the host is a legitimate path character.
        assert!(validate_external_url("https://example.com/users/@someone").is_ok());
    }

    /// Empty clears the setting back to loopback-only — always allowed.
    #[test]
    fn an_empty_bind_address_is_accepted() {
        assert!(validate_bind_address("").is_ok());
    }

    /// The one input this exists to stop: the wildcard would turn a
    /// same-tailnet feature into a same-network one.
    #[test]
    fn the_wildcard_addresses_are_refused() {
        assert!(validate_bind_address("0.0.0.0").is_err());
        assert!(validate_bind_address("::").is_err());
    }

    #[test]
    fn a_real_tailscale_address_is_accepted() {
        assert!(validate_bind_address("100.64.12.3").is_ok());
    }

    #[test]
    fn a_path_query_fragment_or_credential_is_refused() {
        assert!(validate_bind_address("100.64.12.3/api").is_err());
        assert!(validate_bind_address("100.64.12.3?x=1").is_err());
        assert!(validate_bind_address("100.64.12.3#frag").is_err());
        assert!(validate_bind_address("user@100.64.12.3").is_err());
    }

    /// The port is the backend's own job via `JARVIS_HUD_PORT`, not this field's.
    #[test]
    fn a_port_is_refused() {
        assert!(validate_bind_address("100.64.12.3:4719").is_err());
    }

    #[test]
    fn whitespace_or_control_characters_are_refused() {
        assert!(validate_bind_address("100.64.12.3 ").is_err());
        assert!(validate_bind_address("100.64.12.3\n").is_err());
    }
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

/// Rejects anything that is not a plain, well-formed http(s) URL.
///
/// Links in the answer card are authored by a language model, so this is
/// untrusted input on its way to a process spawn.
fn validate_external_url(url: &str) -> Result<(), String> {
    if url.len() > 2_048 {
        return Err("refusing to open an implausibly long URL".to_string());
    }
    if !(url.starts_with("http://") || url.starts_with("https://")) {
        return Err("only http and https URLs can be opened".to_string());
    }
    // Whitespace and control characters are how an argument becomes two.
    if url.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err(
            "refusing to open a URL containing whitespace or control characters".to_string(),
        );
    }
    let host = url
        .split_once("//")
        .map(|(_, rest)| rest.split(['/', '?', '#']).next().unwrap_or(""))
        .unwrap_or("");
    if host.is_empty() {
        return Err("that URL has no host".to_string());
    }
    // `https://github.com@evil.example/` has a host of `evil.example`; the
    // part before the `@` is userinfo and is ignored by every resolver. A
    // model that writes `[github.com](https://github.com@evil.example/)`
    // produces a link whose visible text, whose apparent host, and whose
    // actual destination are three different things — and this hands the
    // result to the real browser.
    //
    // `validate_base` forty lines up already refuses `@` for exactly this
    // reason. The two checks guard the same class of trick and disagreed.
    if host.contains('@') {
        return Err("refusing to open a URL that carries credentials before the host".to_string());
    }
    // Backslash is folded to `/` by the URL parser for http(s), so
    // `https://example.com\@evil.example` would slip past a `@`-only check on
    // what this function believes is the host.
    if url.contains('\\') {
        return Err("refusing to open a URL containing a backslash".to_string());
    }
    Ok(())
}

/// Opens an external link in the user's default browser.
///
/// Deliberately *not* `cmd /C start "" <url>`: `cmd.exe` re-parses its command
/// line, and Rust's argument escaping targets the C runtime convention, not
/// cmd's metacharacters. A model that emits `https://example.com/?a=1&calc`
/// would get `&calc` treated as a second command. `rundll32` hands the URL to
/// the protocol handler through `CreateProcess` with no shell in the path, and
/// [`validate_external_url`] rejects anything unusual before we get that far.
#[tauri::command]
pub fn open_external_url(url: String) -> Result<(), String> {
    let url = url.trim();
    validate_external_url(url)?;

    #[cfg(target_os = "windows")]
    return open_with_shell(url);

    #[cfg(target_os = "macos")]
    return spawn_opener("open", url);

    #[cfg(all(unix, not(target_os = "macos")))]
    return spawn_opener("xdg-open", url);
}

/// Hands a URL to the shell with `ShellExecuteExW`.
///
/// This used to be `rundll32.exe url.dll,FileProtocolHandler`. That works, but
/// it is the wrong tool three times over:
///
/// * `rundll32` with `url.dll,FileProtocolHandler` is a catalogued LOLBin —
///   an execute primitive that Defender ASR, Defender for Endpoint and most
///   third-party EDR alert on. On a managed machine a policy can block it
///   outright, and the user sees a link that silently does nothing.
/// * It is fire-and-forget. `spawn()` discards the exit code, so a refused
///   protocol or a missing handler is invisible.
/// * It starts a whole process to do what one call does.
///
/// `ShellExecuteExW` returns a real error, spawns nothing extra, and is not on
/// anyone's watchlist. `validate_external_url` has already established that the
/// string is an `http`/`https` URL with no whitespace or control characters.
#[cfg(target_os = "windows")]
fn open_with_shell(url: &str) -> Result<(), String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::UI::Shell::{
        ShellExecuteExW, SEE_MASK_FLAG_NO_UI, SEE_MASK_NOASYNC, SHELLEXECUTEINFOW,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

    /// A NUL-terminated UTF-16 string, kept alive for the duration of the call.
    fn wide(value: &str) -> Vec<u16> {
        std::ffi::OsStr::new(value)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    let verb = wide("open");
    let target = wide(url);

    // SAFETY: the struct is zeroed, `cbSize` is set to its own size as the API
    // requires, and both pointers reference buffers that outlive the call.
    // SEE_MASK_NOASYNC is required because this function returns — and may drop
    // those buffers — before the shell would otherwise finish with them.
    let mut info: SHELLEXECUTEINFOW = unsafe { std::mem::zeroed() };
    info.cbSize = std::mem::size_of::<SHELLEXECUTEINFOW>() as u32;
    info.fMask = SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI;
    info.lpVerb = verb.as_ptr();
    info.lpFile = target.as_ptr();
    info.nShow = SW_SHOWNORMAL;

    let ok = unsafe { ShellExecuteExW(&mut info) };
    if ok == 0 {
        let err = std::io::Error::last_os_error();
        return Err(format!(
            "Windows refused to open {url}: {err}. A policy may be blocking it, \
             or no application is registered for that protocol."
        ));
    }
    Ok(())
}

/// The non-Windows path, kept for developer machines. The product is Windows.
#[cfg(not(target_os = "windows"))]
fn spawn_opener(program: &str, url: &str) -> Result<(), String> {
    std::process::Command::new(program)
        .arg(url)
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("unable to open {url}: {e}"))
}

/// Where the logs are, whether they exist, and how big they have got.
///
/// A read, so Settings can show the path as selectable text even when opening
/// the folder fails — on a locked-down machine the Explorer call can be
/// refused, and a path the owner can copy is the difference between sending a
/// log and giving up.
#[tauri::command]
pub fn get_log_info() -> serde_json::Value {
    let dir = match crate::logfile::dir() {
        Some(d) => d,
        None => {
            return serde_json::json!({
                "available": false,
                "note": "no log directory could be created, so nothing is being \
                         recorded. Start the backend in a terminal to see why it \
                         fails.",
            })
        }
    };
    let describe = |name: &str| {
        let path = dir.join(name);
        match std::fs::metadata(&path) {
            Ok(m) => serde_json::json!({ "path": path.display().to_string(), "bytes": m.len() }),
            // Not an error: backend.log does not exist until the app has
            // started the backend at least once, which is the normal state on
            // a machine where the owner runs it themselves.
            Err(_) => serde_json::json!({ "path": path.display().to_string(), "bytes": 0 }),
        }
    };
    serde_json::json!({
        "available": true,
        "dir": dir.display().to_string(),
        "app": describe("jarvis-desktop.log"),
        "backend": describe("backend.log"),
        "note": "plain text, and not redacted. Read it before you send it anywhere.",
    })
}

/// Opens the log folder in Explorer.
///
/// A folder, never a file: opening `backend.log` would hand it to whatever is
/// registered for `.log`, and this function has no say in what that is.
/// Explorer with a directory path is a fixed, known target.
#[tauri::command]
pub fn open_log_folder() -> Result<(), String> {
    let dir = crate::logfile::dir()
        .ok_or_else(|| "there is no log directory on this machine".to_string())?;
    if !dir.is_dir() {
        return Err(format!("{} is not there any more", dir.display()));
    }

    // `#[cfg]` on the `let`, not on a block: an attribute on a trailing block
    // EXPRESSION is still unstable, and this function is the shape that
    // tempts you into writing one.
    #[cfg(target_os = "windows")]
    let program = "explorer.exe";
    #[cfg(target_os = "macos")]
    let program = "open";
    #[cfg(all(unix, not(target_os = "macos")))]
    let program = "xdg-open";

    // `explorer.exe <dir>` rather than ShellExecuteExW: the path comes from
    // Tauri's own resolver, not from a page, so there is no URL to validate,
    // and Explorer is the only handler a directory ever has. Its exit code is
    // famously non-zero on success, so it is never checked - `spawn` failing
    // is the only signal here that means anything.
    std::process::Command::new(program)
        .arg(dir.as_os_str())
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("could not open {}: {e}", dir.display()))
}

/// Does Jarvis start when Windows does?
///
/// Read from the registry every time rather than from the settings store. The
/// store would record what we asked for; this reports what is actually there,
/// and the two part company the moment the owner turns it off in Task
/// Manager's Startup tab - which is where most people turn these off.
#[tauri::command]
pub fn get_autostart() -> serde_json::Value {
    serde_json::json!({
        "enabled": crate::autostart::is_enabled(),
        "supported": cfg!(windows),
        "launchedAtLogin": crate::autostart::launched_at_login(),
        "note": "Jarvis will be running after a restart. It does not promise to \
                 be first: the Alt+Space hotkey is still claimed on a \
                 first-come basis and other startup programs are racing for it.",
    })
}

/// Turns the Windows startup entry on or off, and reports what it is after.
///
/// The returned value is read back from the registry rather than echoed from
/// the argument, so a write that silently did nothing shows as off in the UI
/// instead of as the success it was not.
#[tauri::command]
pub fn set_autostart(enabled: bool) -> Result<serde_json::Value, String> {
    let now = crate::autostart::set(enabled)?;
    crate::logfile::log(&format!(
        "[jarvis] start with Windows: asked for {enabled}, registry now reads {now}"
    ));
    Ok(serde_json::json!({ "enabled": now, "supported": cfg!(windows) }))
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
