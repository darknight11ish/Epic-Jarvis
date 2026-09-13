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

use crate::{windows, ChatState, HUD_LABEL, JARVIS_SERVER_URL, LITELLM_URL, OLLAMA_URL};

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

/// Shared secret for `X-Jarvis-Token`, read once from the environment.
///
/// `JARVIS_TOKEN` wins; `HUD_TOKEN` is accepted as the name the server itself
/// uses. Keeping it in the backend means the token never enters WebView2
/// memory, where any script running in the HUD could reach it.
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

/// Grabs the primary display, encodes it as JPEG and returns a base64 data URI.
///
/// Split out of the command so the `Alt+Shift+S` hotkey can run it on a worker
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
fn jarvis_headers() -> Result<reqwest::header::HeaderMap, String> {
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "X-Jarvis-Client",
        reqwest::header::HeaderValue::from_static(JARVIS_CLIENT),
    );
    if let Some(token) = jarvis_token() {
        let value = reqwest::header::HeaderValue::from_str(token).map_err(|_| {
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
#[tauri::command]
pub async fn stream_chat(
    app: AppHandle,
    messages: Vec<serde_json::Value>,
    has_image: bool,
    images: Vec<String>,
    auto: bool,
    note_target: Option<String>,
    on_event: Channel<String>,
) -> Result<(), String> {
    let cancel = app.state::<ChatState>().begin();

    let mut payload = serde_json::json!({
        "messages": messages,
        "has_image": has_image,
        "images": images,
        "stream": true,
        "auto": auto,
    });
    // Additive: only present when a #log / #joplin prefix pre-routed the turn,
    // so a server that does not know the field simply ignores it.
    if let Some(target) = note_target.as_deref().filter(|t| !t.is_empty()) {
        payload["note_target"] = serde_json::Value::String(target.to_string());
    }

    // `notified()` consumes a permit left by `notify_one`, so a cancel that
    // lands before this future is polled still wins the race.
    let outcome = tokio::select! {
        result = pump_chat(payload, &on_event) => result,
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
async fn pump_chat(payload: serde_json::Value, on_event: &Channel<String>) -> Result<(), String> {
    let mut response = jarvis_client(None)?
        .post(format!("{JARVIS_SERVER_URL}/api/chat"))
        .headers(jarvis_headers()?)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {JARVIS_SERVER_URL}. Is it running?")
            } else {
                format!("chat request failed: {e}")
            }
        })?;

    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        // 409 is the approval gate, not a failure: the body describes what the
        // agent wants to do. Forward it so the frontend renders the card
        // through its normal parsing path.
        if status == reqwest::StatusCode::CONFLICT {
            let _ = on_event.send(body);
            return Ok(());
        }
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

    let endpoint = if approved { "approve" } else { "deny" };
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .post(format!("{JARVIS_SERVER_URL}/api/{endpoint}"))
        .headers(jarvis_headers()?)
        .json(&serde_json::json!({ "id": id, "by": "desktop_spotlight" }))
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {JARVIS_SERVER_URL}")
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

/// Broadcasts a pending approval to every window.
///
/// The quickbar spots gates in its own stream; the widget has no stream of its
/// own, so the discovery is relayed through the backend rather than window to
/// window. Emitting from Rust also means no window needs the capability to emit
/// events itself.
#[tauri::command]
pub fn announce_approval(app: AppHandle, approval: serde_json::Value) {
    crate::emit_all(&app, crate::events::APPROVAL_REQUESTED, approval);
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

    let output = match command.output() {
        Ok(output) if output.status.success() => output,
        _ => {
            GPU_PROBE_ENABLED.store(false, Ordering::Relaxed);
            return None;
        }
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
pub async fn capture_note(target: String, text: String) -> Result<String, String> {
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
        "images": [],
        "stream": false,
        "auto": true,
        "note_target": target,
    });

    let response = jarvis_client(Some(CAPTURE_TIMEOUT))?
        .post(format!("{JARVIS_SERVER_URL}/api/chat"))
        .headers(jarvis_headers()?)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {JARVIS_SERVER_URL}")
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
    Ok(body)
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
    let mut command = {
        let mut c = std::process::Command::new("rundll32.exe");
        c.arg("url.dll,FileProtocolHandler").arg(url);
        c
    };
    #[cfg(target_os = "macos")]
    let mut command = {
        let mut c = std::process::Command::new("open");
        c.arg(url);
        c
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = {
        let mut c = std::process::Command::new("xdg-open");
        c.arg(url);
        c
    };

    command
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("unable to open {url}: {e}"))
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
