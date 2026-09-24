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
///
/// Was 1.5 s, and the owner's backend answers `/api/status` slower than that:
/// its traceback showed the 200 being written to a socket this probe had
/// already closed (WinError 10053), while the tray reported "offline: Jarvis
/// Core" against a server that was up. `/api/status` probes :8000 and :4000
/// itself, and on Windows a connect to a closed local port takes about two
/// seconds to fail. The probe is on-demand and never on a timer, so waiting
/// longer costs nothing but a slower answer when something really is down.
///
/// Nothing in THIS app probes :8000 (the old OpenJarvis agent, never run
/// here) - the desktop's "Core" light is Jarvis's own server, read from the
/// event stream. The :8000 probe is inside the backend's `/api/status`, whose
/// code is not in this repository, so it cannot be removed from here; until
/// it is, and while :4000 (LiteLLM, the future cloud lane) is probed the same
/// way, this timeout has to stay long enough to outwait both.
const HEALTH_TIMEOUT: Duration = Duration::from_secs(5);
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
/// Filing a note waits up to a second and a half on the server for the
/// approval gate (see jarvis_note_capture.capture), then answers.
const CAPTURE_TIMEOUT: Duration = Duration::from_secs(15);

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
    /// Only needed for something the owner may not use. LiteLLM is the cloud
    /// lane's proxy: with no cloud lane set up, nothing runs on :4000, and
    /// that is the normal state, not a fault. An optional service counts in
    /// the totals only when it answers - see [`summarise_health`].
    pub optional: bool,
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

/// Largest chat line accepted before the stream is treated as broken.
const MAX_CHAT_LINE_BYTES: usize = 4 * 1024 * 1024;

/// Where the desktop shell keeps the API base URL and the bind address.
///
/// A store file rather than the page's `localStorage`, per DESKTOP-BUILD §3.1:
/// the port can change without a rebuild, and reading it from Rust means the
/// token reaches the webview only as the `JARVIS.set()` call at page load.
/// The pairing token is NOT kept here - it is in Windows Credential Manager
/// (`token_store.rs`). An older version kept it here as plain text; that copy
/// is moved out at startup ([`migrate_plain_token`]) and is only ever read.
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
        .map(|b| b.trim().trim_end_matches('/').to_string())
        .filter(|b| !b.is_empty())
        .or_else(|| std::env::var("JARVIS_HUD_BASE").ok())
        .map(|b| b.trim().trim_end_matches('/').to_string())
        .filter(|b| !b.is_empty())
        .unwrap_or_else(|| DEFAULT_BASE.to_string())
}

/// Where the token in use came from. Reported to Settings by name - never
/// the token itself.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TokenSource {
    /// Typed into Settings, kept in Windows Credential Manager.
    CredentialManager,
    /// Typed into Settings by an older version, still in the settings file
    /// as plain text because Credential Manager refused the move. Read only;
    /// nothing here writes a token to that file any more.
    SettingsFile,
    /// `JARVIS_TOKEN` / `HUD_TOKEN` in the environment.
    Environment,
    /// The backend's own token, in Credential Manager (`BACKEND_TARGET`).
    BackendCredentialManager,
    /// The backend's own OLD plain-text `~/.openjarvis/token`, read only until
    /// the backend (with token-store.patch) moves it into Credential Manager.
    BackendFile,
}

impl TokenSource {
    pub fn as_str(self) -> &'static str {
        match self {
            TokenSource::CredentialManager => "credential-manager",
            TokenSource::SettingsFile => "settings-file",
            TokenSource::Environment => "environment",
            TokenSource::BackendCredentialManager => "backend-credential-manager",
            TokenSource::BackendFile => "backend-file",
        }
    }
}

/// Which token wins. Pure, so the order is tested without an app.
///
/// **An empty value means "not set" at every step, and falls through.** It
/// used to be read as "the token is the empty string": Settings' "Clear
/// token" saved `""`, this found it first and stopped, never reaching the
/// environment or the backend's own file - so every request went out with
/// no token and the backend answered 401 until the app was reconfigured.
///
/// The settings-file copy wins over Credential Manager because it only
/// exists when an older version left it there and Credential Manager refused
/// the move ([`migrate_plain_token`]) - so it is what was typed last.
///
/// The backend's own token comes last: from its old plain-text file, which a
/// backend without token-store.patch still writes, or else from Credential
/// Manager - the backend's own order ([`pick_backend_token`]). Both are only
/// read here.
pub(crate) fn pick_token(
    settings_file: Option<String>,
    credential_manager: Option<String>,
    environment: Option<String>,
    backend: impl FnOnce() -> Option<(String, TokenSource)>,
) -> Option<(String, TokenSource)> {
    let clean = |t: Option<String>| t.map(|t| t.trim().to_string()).filter(|t| !t.is_empty());
    clean(settings_file)
        .map(|t| (t, TokenSource::SettingsFile))
        .or_else(|| clean(credential_manager).map(|t| (t, TokenSource::CredentialManager)))
        .or_else(|| clean(environment).map(|t| (t, TokenSource::Environment)))
        .or_else(|| backend().and_then(|(t, source)| clean(Some(t)).map(|t| (t, source))))
}

/// The pairing token and where it came from: typed into Settings first
/// (see [`pick_token`] for the order), then the environment, then the token
/// the backend made for itself.
pub fn jarvis_token_with_source(app: &AppHandle) -> Option<(String, TokenSource)> {
    use tauri_plugin_store::StoreExt;

    let settings_file = app
        .store(SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get("token"))
        .and_then(|v| v.as_str().map(str::to_string));
    // A failure to read Credential Manager is not a reason to send no token:
    // fall through to the next source rather than stop.
    let credential_manager = crate::token_store::read().ok().flatten();
    pick_token(
        settings_file,
        credential_manager,
        jarvis_token().cloned(),
        || backend_token(app),
    )
}

/// The pairing token, wherever it came from.
pub fn jarvis_token_for(app: &AppHandle) -> Option<String> {
    jarvis_token_with_source(app).map(|(token, _)| token)
}

/// Moves a token an older version saved in `jarvis-desktop.json` (plain
/// text) into Windows Credential Manager, once, at startup - and deletes the
/// plain-text copy only after reading it back from Credential Manager and
/// finding it identical. Any failure leaves the settings file alone, so the
/// pairing is never lost; the reason is logged, the token never is.
pub fn migrate_plain_token(app: &AppHandle) {
    use crate::token_store::{plan_migration, read_fresh, write, Migration};
    use tauri_plugin_store::StoreExt;

    let Ok(store) = app.store(SETTINGS_STORE) else {
        return;
    };
    let Some(plain) = store
        .get("token")
        .and_then(|v| v.as_str().map(str::to_string))
    else {
        return;
    };
    match plan_migration(Some(&plain), write, read_fresh) {
        // An empty value is what the old "Clear token" saved. It holds no
        // secret and it is what locked the app out, so it simply goes.
        Migration::Nothing | Migration::RemovePlain => {
            let moved = !plain.trim().is_empty();
            store.delete("token");
            match store.save() {
                Ok(()) if moved => crate::logfile::log(
                    "[jarvis] moved the pairing token out of the settings file into Windows Credential Manager",
                ),
                Ok(()) => {}
                Err(e) => crate::logfile::log(&format!(
                    "[jarvis] the pairing token is in Credential Manager, but the settings file could not be rewritten without it: {e}"
                )),
            }
        }
        Migration::KeepPlain(why) => crate::logfile::log(&format!(
            "[jarvis] the pairing token stays in the settings file (plain text): {why}"
        )),
    }
}

/// The token the backend makes for itself on first run.
///
/// Last, deliberately: something typed into Settings wins, then the
/// environment, then this. It exists so the two halves agree without the owner
/// configuring anything — the server always has a token, and a desktop that
/// did not know where to find it would be locked out of its own backend by a
/// secret generated on its behalf.
///
/// The OLD plain-text file first, then Credential Manager - the order
/// `backend/jarvis_token_store.resolve` uses. The file only exists when a
/// backend without token-store.patch wrote it (the patched backend moves it
/// into Credential Manager and deletes it at its next start), so when both
/// exist the file is the newer token: an older backend is running and
/// wrote it after the move. Reading Credential Manager first sent that
/// backend a token it no longer used, and every request was refused.
fn backend_token(app: &AppHandle) -> Option<(String, TokenSource)> {
    pick_backend_token(token_from_config_dir(app), || {
        crate::token_store::read_backend().ok().flatten()
    })
}

/// [`backend_token`]'s order, pure so it is tested without an app: the old
/// file, else Credential Manager (read only when the file has nothing - a
/// failure there falls through to "no token", never stops). Empty is "not
/// set" at both steps.
pub(crate) fn pick_backend_token(
    file: Option<String>,
    credential_manager: impl FnOnce() -> Option<String>,
) -> Option<(String, TokenSource)> {
    let clean = |t: Option<String>| t.map(|t| t.trim().to_string()).filter(|t| !t.is_empty());
    clean(file)
        .map(|t| (t, TokenSource::BackendFile))
        .or_else(|| clean(credential_manager()).map(|t| (t, TokenSource::BackendCredentialManager)))
}

/// Whether a token from `source` is handed to a backend this app starts, as
/// `HUD_TOKEN`.
///
/// Only a token set DELIBERATELY: typed into Settings (Credential Manager,
/// or an older version's settings-file copy) or given in the environment.
/// Never the backend's own token read back: `HUD_TOKEN` overrides the
/// backend's own choice, so passing it back pinned the backend to whatever
/// this app happened to read - a stale copy included - instead of the one
/// the backend itself resolves (`jarvis_token_store.resolve`).
pub(crate) fn passes_as_hud_token(source: TokenSource) -> bool {
    match source {
        TokenSource::CredentialManager | TokenSource::SettingsFile | TokenSource::Environment => {
            true
        }
        TokenSource::BackendCredentialManager | TokenSource::BackendFile => false,
    }
}

/// The backend's OLD plain-text token file. Read, never written.
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
///
/// The same three the phone ships (`Themes.kt`'s `ALL`), under the same
/// names: `deep-space` is Reactor, `paper` is Daylight, `high-contrast` is
/// High Contrast. The ids stay as they were so no saved choice breaks.
/// Ember was the fourth and is gone, matching the phone - see
/// [`normalise_theme`] for where an owner who had it lands.
pub const THEMES: &[&str] = &["deep-space", "paper", "high-contrast"];

/// The light theme "Follow the system" uses when Windows is in light mode.
const LIGHT_THEME: &str = "paper";

/// A stored theme id as this build reads it.
///
/// Anything this build does not ship - `ember`, removed to match the phone, or
/// a hand-edited value - is Reactor, which is where the phone sends a removed
/// theme too (`Themes.byId`).
pub fn normalise_theme(stored: Option<&str>) -> &'static str {
    let wanted = stored.unwrap_or("").trim();
    THEMES
        .iter()
        .copied()
        .find(|t| *t == wanted)
        .unwrap_or(THEMES[0])
}

fn is_dark_theme(theme: &str) -> bool {
    theme != LIGHT_THEME
}

/// The owner's theme choices, as stored.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ThemePrefs {
    /// The theme picked by hand.
    pub theme: String,
    /// "Match Windows light or dark mode".
    pub follow_system: bool,
    /// The dark theme following returns to when Windows goes dark: the last
    /// dark theme picked, so an owner on High Contrast does not get Reactor
    /// at every dusk (the phone's `preferredDark`, audit custom-8).
    pub dark_theme: String,
    /// Windows' own app mode right now: `Some(true)` light, `Some(false)`
    /// dark, `None` when it cannot be read (not Windows, or the value is
    /// missing).
    pub system_light: Option<bool>,
    /// What every window should be wearing, given all of the above.
    pub effective: String,
}

/// Pure: which theme the windows wear.
///
/// Following the system with Windows in light mode is Daylight; in dark mode
/// it is the remembered dark theme. When Windows' mode cannot be read,
/// following falls back to the theme picked by hand rather than guessing.
pub fn effective_theme(
    theme: &str,
    follow_system: bool,
    dark_theme: &str,
    system_light: Option<bool>,
) -> String {
    match (follow_system, system_light) {
        (true, Some(true)) => LIGHT_THEME.to_string(),
        (true, Some(false)) => dark_theme.to_string(),
        _ => theme.to_string(),
    }
}

/// Reads the stored choices and Windows' mode, and works out the answer.
pub fn theme_prefs(app: &AppHandle) -> ThemePrefs {
    use tauri_plugin_store::StoreExt;

    let store = app.store(SETTINGS_STORE).ok();
    let text = |key: &str| -> Option<String> {
        store
            .as_ref()
            .and_then(|s| s.get(key))
            .and_then(|v| v.as_str().map(str::to_string))
    };
    let theme = normalise_theme(text("theme").as_deref()).to_string();
    let follow_system = store
        .as_ref()
        .and_then(|s| s.get("theme_follow_system"))
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let dark_theme = {
        let stored = normalise_theme(text("theme_dark").as_deref());
        if text("theme_dark").is_some() && is_dark_theme(stored) {
            stored.to_string()
        } else if is_dark_theme(&theme) {
            theme.clone()
        } else {
            THEMES[0].to_string()
        }
    };
    let system_light = crate::system_theme::apps_use_light_theme();
    let effective = effective_theme(&theme, follow_system, &dark_theme, system_light);
    ThemePrefs {
        theme,
        follow_system,
        dark_theme,
        system_light,
        effective,
    }
}

/// The theme every window should be wearing right now - the picked one, or
/// what "Match Windows" makes of it. A stored `ember` reads as Reactor.
#[tauri::command]
pub fn get_theme(app: AppHandle) -> String {
    crate::system_theme::applied_or(&app, theme_prefs(&app).effective)
}

/// The owner's theme choices, for the Settings picker. Read-only.
#[tauri::command]
pub fn get_theme_prefs(app: AppHandle) -> ThemePrefs {
    let mut prefs = theme_prefs(&app);
    prefs.effective = crate::system_theme::applied_or(&app, prefs.effective);
    prefs
}

/// Persists the theme and tells every open window at once.
///
/// The fan-out is the point. Four surfaces can be on screen together, and a
/// theme that changed in the window you clicked while the widget stayed cyan
/// would look like a bug rather than a setting.
///
/// A dark theme is also remembered as the one "Match Windows" returns to when
/// Windows goes dark.
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
    if is_dark_theme(&theme) {
        store.set("theme_dark", serde_json::Value::String(theme.clone()));
    }
    store
        .save()
        .map_err(|e| format!("could not save the theme: {e}"))?;

    // A choice made by hand applies now, even mid-approval: the owner is the
    // one changing it. Only a switch Windows makes on its own is held.
    let effective = theme_prefs(&app).effective;
    crate::system_theme::apply_now(&app, &effective);
    Ok(effective)
}

/// Turns "Match Windows light or dark mode" on or off.
#[tauri::command]
pub fn set_theme_follow_system(app: AppHandle, follow: bool) -> Result<ThemePrefs, String> {
    use tauri_plugin_store::StoreExt;

    let store = app
        .store(SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    store.set("theme_follow_system", serde_json::Value::Bool(follow));
    store
        .save()
        .map_err(|e| format!("could not save the setting: {e}"))?;
    let prefs = theme_prefs(&app);
    crate::system_theme::apply_now(&app, &prefs.effective);
    Ok(prefs)
}

/// Opens the Faces window from a page. Settings has an "Open Faces" button
/// because the face and the state colours - the part of the look shared
/// with the phone - were reachable only from the tray menu before.
#[tauri::command]
pub fn open_faces(app: AppHandle) -> Result<(), String> {
    crate::windows::show_faces(&app)
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
        // Where it came from, by name - "credential-manager",
        // "settings-file", "environment", "backend-credential-manager" or
        // "backend-file" - never the token.
        // Settings only offers "Clear" for the first two, the ones typed there.
        "tokenSource": jarvis_token_with_source(&app).map(|(_, source)| source.as_str()),
        "bindAddress": supervised_bind_address(&app).unwrap_or_default(),
        // A value an older build saved that this one refuses; the backend is
        // not started with it (sidecar.rs), and Settings says why.
        "bindAddressProblem": supervised_bind_address(&app)
            .and_then(|b| validate_bind_address(&b).err()),
        "store": SETTINGS_STORE,
    })
}

/// The token in use, for Settings' "Show the token for my phone" button -
/// the settings window only (`permissions/surfaces.toml`).
///
/// The phone has to be given the same token, and before this the only way to
/// see it was to find a file (and a token typed into Settings was in no file
/// at all). Returned to that one page on a click; never logged, never
/// written anywhere by this command.
#[tauri::command]
pub fn reveal_pairing_token(app: AppHandle) -> Result<String, String> {
    jarvis_token_for(&app).ok_or_else(|| {
        "there is no token yet - start Jarvis once and it makes one for itself".to_string()
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

/// Checks a bind address before it is persisted, and again before a
/// supervised backend is started with it (`sidecar.rs`).
///
/// This is not `validate_base`: a bind address is a bare host with no scheme,
/// path or port — the backend derives the port itself from `JARVIS_HUD_PORT`.
/// Empty is always accepted; it means "clear this and let the backend bind
/// loopback only", the safe default.
///
/// **What is accepted is a short list, not "anything but 0.0.0.0".** The
/// Settings note promises this "never opens Jarvis to the whole internet, or
/// even to your home Wi-Fi — only to your own devices on that private
/// network", and `docs/INSTALL.md` says the same: "Bind to the specific
/// Tailscale address, not 0.0.0.0. Then the port is not reachable from the
/// café Wi-Fi at all." Only three things keep that promise:
///
/// - an address in `100.64.0.0/10`, the range Tailscale and NordVPN Meshnet
///   hand out;
/// - a loopback address (`127.x`), which opens nothing;
/// - `localhost`, the same.
///
/// A home-network address (`192.168.x`) would reach every device on that
/// Wi-Fi, and a public one the internet, so both are refused.
///
/// **It used to refuse only the exact strings `0.0.0.0` and `::`.** The
/// operating system's address parser is far looser than that: `0`, `0x0`,
/// `0.0` and `000.000.000.000` all bind every interface (checked with a real
/// `socket.bind`), and `100.64.012.3` binds `100.64.10.3`, because a leading
/// zero means octal. So the check is now "parse it strictly as four plain
/// numbers, or it is refused" — and anything the OS would read as the
/// wildcard gets the wildcard's own explanation. The cases live in
/// `jarvis-desktop/tests/bind-address-cases.json`, which this file's tests,
/// the backend's `test_bind_wildcard.py` and `tests/tailscale.mjs` all read.
pub(crate) fn validate_bind_address(addr: &str) -> Result<(), String> {
    if addr.is_empty() {
        return Ok(()); // clearing it falls back to loopback-only
    }
    if binds_every_interface(addr) {
        return Err(
            "refusing to bind every network interface (0.0.0.0) — set this \
             computer's own Tailscale or NordVPN Meshnet address instead, so \
             Jarvis is reachable from your private network and nowhere else"
                .to_string(),
        );
    }
    if addr.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err("the bind address contains whitespace or control characters".to_string());
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
    if addr.eq_ignore_ascii_case("localhost") {
        return Ok(());
    }
    // Strict: exactly four decimal numbers, no leading zeros. Anything looser
    // is refused rather than guessed at, because the OS would guess
    // differently (see above).
    let ip: std::net::Ipv4Addr = addr.parse().map_err(|_| {
        format!(
            "\"{addr}\" is not an address this can use — type this computer's \
             own Tailscale or NordVPN Meshnet address as four plain numbers, \
             like 100.64.1.5 (the Tailscale or NordVPN app shows it)"
        )
    })?;
    if ip.is_loopback() {
        return Ok(());
    }
    let [a, b, _, _] = ip.octets();
    if a == 100 && (64..=127).contains(&b) {
        return Ok(());
    }
    Err(format!(
        "{addr} is not a Tailscale or NordVPN Meshnet address (those start \
         with 100.64 up to 100.127). Binding it could open Jarvis to your \
         home Wi-Fi or the internet, so it is refused"
    ))
}

/// True when the operating system would read `addr` as "every interface".
///
/// A strict parse catches `0.0.0.0`, `::` and the other IPv6 spellings. The
/// rest is `inet_aton`, the lenient parser `socket.bind` falls back to, which
/// reads `0`, `0x0`, `0.0` and `000.000.000.000` as `0.0.0.0` too.
fn binds_every_interface(addr: &str) -> bool {
    if let Ok(ip) = addr.parse::<std::net::IpAddr>() {
        return ip.is_unspecified();
    }
    inet_aton(addr) == Some(0)
}

/// The classic BSD `inet_aton` reading of a numeric host: one to four parts
/// separated by dots, each decimal, `0x` hex or leading-zero octal, the last
/// part filling whatever bytes are left. `None` when it is not numeric.
fn inet_aton(s: &str) -> Option<u32> {
    let parts: Vec<&str> = s.split('.').collect();
    if parts.is_empty() || parts.len() > 4 {
        return None;
    }
    let mut values = Vec::with_capacity(parts.len());
    for part in &parts {
        let (digits, radix) =
            if let Some(hex) = part.strip_prefix("0x").or_else(|| part.strip_prefix("0X")) {
                (hex, 16)
            } else if part.len() > 1 && part.starts_with('0') {
                (&part[1..], 8)
            } else {
                (*part, 10)
            };
        if digits.is_empty() {
            // "0x" alone is not a number; a lone "0" was handled as decimal.
            return None;
        }
        values.push(u64::from_str_radix(digits, radix).ok()?);
    }
    let (last, head) = values.split_last()?;
    if head.iter().any(|&v| v > 0xff) {
        return None;
    }
    let tail_bits = 8 * (4 - head.len() as u32);
    if tail_bits < 64 && *last >= (1u64 << tail_bits) {
        return None;
    }
    let mut out: u64 = 0;
    for (i, &v) in head.iter().enumerate() {
        out |= v << (24 - 8 * i as u32);
    }
    Some((out | *last) as u32)
}

/// Persists the base URL, the token and the supervised bind address —
/// each optional, so a caller can change one without resending the others.
///
/// The token goes to Windows Credential Manager (`token_store.rs`) and
/// nowhere else. If Credential Manager refuses it, it is NOT saved - an
/// error says so and why, and nothing else in the call is saved either.
/// It used to fall back to the settings file as plain text, which is exactly
/// what CLAUDE.md rule 3 forbids.
///
/// The settings file is saved (without any token) BEFORE Credential Manager
/// is written - see [`save_file_then_token`] for why that order.
///
/// An empty token means **clear what was typed here**: it is removed from
/// Credential Manager and from any old settings-file copy, and the app goes
/// back to the environment or the backend's own token. It is never saved as
/// `""` - that value used to be read as "the token is empty" and lock the app
/// out of its own backend.
///
/// Returns a note for Settings to show, or `None` when there is nothing to add.
#[tauri::command]
pub fn set_api_settings(
    app: AppHandle,
    base: Option<String>,
    token: Option<String>,
    bind_address: Option<String>,
) -> Result<Option<String>, String> {
    use crate::token_store::{self, StoreError};
    use tauri_plugin_store::StoreExt;

    let store = app
        .store(SETTINGS_STORE)
        .map_err(|e| format!("unable to open the settings store: {e}"))?;
    // Everything that can be refused is checked before anything is written,
    // so a refused bind address does not leave a half-saved token behind.
    let base = base.map(|b| b.trim().trim_end_matches('/').to_string());
    if let Some(base) = &base {
        validate_base(base)?;
    }
    let bind_address = bind_address.map(|b| b.trim().to_string());
    if let Some(bind_address) = &bind_address {
        validate_bind_address(bind_address)?;
    }

    let token = token.map(|t| t.trim().to_string());
    let base_before = jarvis_base(&app);

    // What the settings file held before this call, to put back if any step
    // below is refused - in memory, and on disk if it had been saved.
    let keys = ["token", "base", "bind_address"];
    let before: Vec<(&str, Option<serde_json::Value>)> =
        keys.iter().map(|&k| (k, store.get(k))).collect();
    let restore = || {
        for (key, value) in &before {
            match value {
                // Only ever what was already in the file before this call:
                // an older version's plain copy is put back as it was, never
                // the new token.
                Some(value) => store.set(*key, value.clone()),
                None => {
                    store.delete(*key);
                }
            }
        }
    };

    // The settings file FIRST - without any plain-text token - and
    // Credential Manager SECOND (CONN-7). It used to be the other way round:
    // the new token went into Credential Manager, the old plain copy was
    // deleted only in memory, and when the file then failed to save, the
    // next start's migration (`migrate_plain_token`) found the OLD plain
    // copy still on disk and moved it back over the new one.
    if token.is_some() {
        store.delete("token");
    }
    if let Some(base) = base {
        store.set("base", serde_json::Value::String(base));
    }
    if let Some(bind_address) = bind_address {
        store.set("bind_address", serde_json::Value::String(bind_address));
    }
    let credential_manager = || -> Result<(), String> {
        match token.as_deref() {
            None => Ok(()),
            Some("") => match token_store::delete() {
                Ok(()) | Err(StoreError::Unavailable) => Ok(()),
                // Still in Credential Manager means still in use: say so
                // rather than report a clear that did not happen.
                Err(e) => Err(format!(
                    "could not clear the token: {e}. Nothing in Settings was changed."
                )),
            },
            Some(token) => token_store::write(token).map_err(|e| {
                format!(
                    "The token was NOT saved, because {e}. Nothing in Settings was changed, \
                     and nothing was written to disk in plain text. Try again, or set the \
                     JARVIS_TOKEN environment variable instead."
                )
            }),
        }
    };
    save_file_then_token(
        || store.save().map_err(|e| e.to_string()),
        credential_manager,
        || {
            restore();
            // Best effort: when this fails too, the file is left without
            // the plain copy and with the new address - never with a token
            // Credential Manager does not also hold.
            let _ = store.save();
        },
        restore,
    )?;
    // "Hey Jarvis" listening sends room audio to the server address, and was
    // started against the old one. It stops, and says so; turning it on
    // again checks the new address from scratch (voice.rs
    // wake_audio_refusal - which also runs before every clip, so this is
    // the early, visible half of the same rule, not the only guard).
    let base_after = jarvis_base(&app);
    if base_after != base_before {
        crate::voice::stop_listening_because(
            &app,
            format!(
                "The Jarvis server address changed to {base_after}, so listening for \
                 \"hey Jarvis\" stopped. Turn it on again to listen with the new address."
            ),
        );
    }
    Ok(None)
}

/// The order [`set_api_settings`] writes in, pure so it is tested without an
/// app or Credential Manager (CONN-7):
///
/// 1. the settings file, already without any plain-text token - refused,
///    and the in-memory store is put back (`restore_memory`) and nothing
///    else is touched;
/// 2. then Credential Manager - refused, and the settings file is rolled
///    back to what it held before the call (`roll_back_file`), so a refused
///    token leaves nothing half-saved.
///
/// Never the other order: a new token in Credential Manager with the OLD
/// plain copy still on disk is what the next start's migration moved back
/// over it.
pub(crate) fn save_file_then_token(
    save_file: impl FnOnce() -> Result<(), String>,
    credential_manager: impl FnOnce() -> Result<(), String>,
    roll_back_file: impl FnOnce(),
    restore_memory: impl FnOnce(),
) -> Result<(), String> {
    if let Err(e) = save_file() {
        restore_memory();
        return Err(format!(
            "unable to write the settings store: {e}. Nothing was changed."
        ));
    }
    if let Err(e) = credential_manager() {
        roll_back_file();
        return Err(e);
    }
    Ok(())
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
                optional: false,
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
                optional: false,
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

    // The cloud lane's proxy. Not running is the normal state when no cloud
    // lane is set up - which is the default, and today's setup - so it no
    // longer turns every status check into "2/3 online - offline: LiteLLM".
    let mut litellm = litellm;
    litellm.optional = true;
    if !litellm.online {
        litellm.detail = format!(
            "not running — only needed if you set up a cloud model ({})",
            litellm.detail
        );
    }

    let services = vec![jarvis, ollama, litellm];
    let (online_count, total_count, summary) = summarise_health(&services);
    Ok(HealthReport {
        checked_at: now_ms(),
        all_online: online_count == total_count,
        online_count,
        total_count,
        summary,
        services,
    })
}

/// The counts and the one-line summary. An optional service (LiteLLM) is
/// counted only when it answers; when it does not, the summary says so in a
/// separate, calm sentence instead of listing it as offline.
pub(crate) fn summarise_health(services: &[ServiceStatus]) -> (usize, usize, String) {
    let counted: Vec<&ServiceStatus> = services
        .iter()
        .filter(|s| !s.optional || s.online)
        .collect();
    let online_count = counted.iter().filter(|s| s.online).count();
    let total_count = counted.len();
    let offline: Vec<&str> = counted
        .iter()
        .filter(|s| !s.online)
        .map(|s| s.name)
        .collect();
    let mut summary = if offline.is_empty() {
        format!("All {total_count} services online.")
    } else {
        format!(
            "{online_count}/{total_count} online — offline: {}",
            offline.join(", ")
        )
    };
    for s in services.iter().filter(|s| s.optional && !s.online) {
        summary.push_str(&format!(
            " {} is not running, which is fine unless you use a cloud model.",
            s.name
        ));
    }
    (online_count, total_count, summary)
}

// ---------------------------------------------------------------------------
// Chat streaming
// ---------------------------------------------------------------------------

/// Shared `reqwest` client settings for talking to the Jarvis server.
///
/// There is deliberately no *total* timeout: a chat response is a long-lived
/// body, and `Client::timeout` covers the read as well as the connect, so it
/// would guillotine a long answer mid-sentence.
pub(crate) fn jarvis_client(total_timeout: Option<Duration>) -> Result<reqwest::Client, String> {
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

/// Starts the one line on the chat channel that is not part of the answer: the
/// answer's `turn_id`. A unit-separator control character never appears in
/// a server's SSE line, so main.js can split this off before anything tries
/// to read it as text.
pub const TURN_LINE_PREFIX: &str = "\u{1f}jarvis-turn:";

/// The `turn_id` in an `X-Jarvis-Route` header value, if it holds a valid one:
/// exactly 32 lower-case hex characters, what `jarvis_feedback.record_turn`
/// makes. Anything else is ignored rather than passed on.
pub fn turn_id_from_route(header: &str) -> Option<String> {
    let route: serde_json::Value = serde_json::from_str(header).ok()?;
    let id = route.get("turn_id")?.as_str()?;
    valid_turn_id(id).then(|| id.to_string())
}

/// Starts the line on the chat channel that carries `X-Jarvis-Route`'s lane,
/// `where` ("local" / "cloud") and gate - never its reason text or memory ids.
/// main.js paints the Local/Cloud badge from it rather than guessing from the
/// model name each chunk carries, which says nothing about where it ran.
pub const ROUTE_LINE_PREFIX: &str = "\u{1f}jarvis-route:";

/// The small JSON object for [`ROUTE_LINE_PREFIX`], from an `X-Jarvis-Route`
/// header value: `lane`, `where`, `gate` and `second_card`, each only when it
/// is a string.
///
/// `second_card` (second-card.patch) is there only on a turn the second
/// graphics card answered, and says why: `"long_context"` or `"vision"`.
/// `where` is still `"local"` then (it is this PC) and `lane` names the model
/// really answering. main.js adds "on the second graphics card" to the model.
pub fn route_line_from_header(header: &str) -> Option<String> {
    let route: serde_json::Value = serde_json::from_str(header).ok()?;
    let mut out = serde_json::Map::new();
    for key in ["lane", "where", "gate", "second_card"] {
        if let Some(value) = route.get(key).and_then(|v| v.as_str()) {
            out.insert(
                key.to_string(),
                serde_json::Value::String(value.to_string()),
            );
        }
    }
    (!out.is_empty()).then(|| serde_json::Value::Object(out).to_string())
}

/// The sentence in a failed `/api/chat` body: `{"error": "..."}` (the
/// backend's own shape) or `{"error": {"message": "..."}}` (Ollama's and
/// OpenAI's). None when there is none to find.
pub fn error_text_from_body(body: &str) -> Option<String> {
    let value: serde_json::Value = serde_json::from_str(body).ok()?;
    let error = value.get("error")?;
    let text = error
        .as_str()
        .or_else(|| error.get("message").and_then(|m| m.as_str()))?
        .trim();
    (!text.is_empty()).then(|| text.to_string())
}

fn valid_turn_id(id: &str) -> bool {
    id.len() == 32
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// The owner's right/wrong mark on ONE answer (feedback.patch).
///
/// One id and one mark, never a list: the server refuses a list with a 400
/// too, because a "mark all" would move every counter at once. A mark never
/// changes memory; at most it raises one "stop using this fact?" card in the
/// ordinary review queue, which still needs its own decision.
///
/// A backend without the patch answers 404 (no such route) or 503 (the
/// module is missing); both come back as `{"available": false}` so the page
/// can hide the control quietly rather than show an error.
#[tauri::command]
pub async fn mark_answer(
    app: AppHandle,
    turn_id: String,
    mark: String,
) -> Result<serde_json::Value, String> {
    if !valid_turn_id(&turn_id) {
        return Err("that answer has no valid id to mark".to_string());
    }
    if !matches!(mark.as_str(), "right" | "wrong" | "none") {
        return Err(format!("`{mark}` is not a mark (right, wrong or none)"));
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .post(format!("{base}/api/feedback/mark"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "turn_id": turn_id, "mark": mark }))
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {base}")
            } else {
                format!("the mark could not be sent: {e}")
            }
        })?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    if matches!(status, 404 | 501 | 503) {
        return Ok(serde_json::json!({ "available": false, "status": status }));
    }
    if !(200..300).contains(&status) {
        return Err(format!(
            "the server answered HTTP {status}: {}",
            text.trim()
        ));
    }
    Ok(serde_json::from_str(&text).unwrap_or_else(|_| serde_json::json!({ "ok": true })))
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
        // The server's own sentence when it sent one (`{"error": "..."}`, or
        // `{"error": {"message": ...}}`), not the whole JSON body - which
        // used to put the route dictionary, reasons and ids and all, on the
        // card under "Jarvis could not answer".
        return Err(match error_text_from_body(body) {
            Some(said) => said,
            None if body.is_empty() => format!("the server answered HTTP {}", status.as_u16()),
            None => format!("the server answered HTTP {}: {body}", status.as_u16()),
        });
    }

    // Which lane answered and whether it is this PC, for the Local/Cloud
    // badge - see ROUTE_LINE_PREFIX. Only those fields (and `second_card`,
    // on a turn the second graphics card answered) go to the page.
    if let Some(route) = response
        .headers()
        .get("X-Jarvis-Route")
        .and_then(|v| v.to_str().ok())
        .and_then(route_line_from_header)
    {
        let _ = on_event.send(format!("{ROUTE_LINE_PREFIX}{route}"));
    }

    // The answer's id, for the right/wrong mark (feedback.patch: `turn_id` in
    // the JSON `X-Jarvis-Route` header). Sent to the page first, as one line
    // it can tell apart from the answer - see TURN_LINE_PREFIX. A backend
    // without the patch sends no id, and the page then shows no mark.
    if let Some(turn) = response
        .headers()
        .get("X-Jarvis-Route")
        .and_then(|v| v.to_str().ok())
        .and_then(turn_id_from_route)
    {
        let _ = on_event.send(format!("{TURN_LINE_PREFIX}{turn}"));
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
    option_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let id = id.trim();
    if id.is_empty() {
        return Err("that approval has no id to answer".to_string());
    }

    // Declared so it can be REFUSED, not so it can be forwarded.
    //
    // `jarvis-link.js` has always attached `option_id` when a proposal
    // carries several plans, and this signature did not take it - so Tauri
    // dropped the key silently and the call went through as a plain
    // whole-proposal approve. The webview's per-option buttons were disabled
    // to stop that, which is the fix this function's own comment below calls
    // insufficient: "a disabled button is a courtesy, not a gate: any window
    // holding the `approvals` capability reaches this directly".
    //
    // No backend route accepts a choice yet (docs/AUTONOMY-PROPOSALS.md §3b
    // proposes one; docs/JARVIS-API.md records that none is confirmed), so
    // the honest answer is to refuse rather than to approve something other
    // than what was asked for. Forwarding it would be inventing a server
    // contract; dropping it silently is what this is here to stop.
    if let Some(option) = option_id
        .as_deref()
        .map(str::trim)
        .filter(|o| !o.is_empty())
    {
        return Err(format!(
            "this Jarvis cannot approve one option out of several yet, so \
             nothing was sent - option {option:?} was not chosen. Deny works \
             normally; approving needs a server route that can carry the choice."
        ));
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

/// The shared half of the task controls and `amend_approval`: POST a small
/// JSON body, and turn anything that is not a 2xx into a sentence.
///
/// Deliberately NOT gated on a stale stream here, unlike [`decide_approval`]
/// ([`resume_task`] adds its own check, being the one that makes work go
/// again). A note is an annotation, and pause and stop are the safe
/// direction in the same sense Deny is — the
/// moment you most want to stop a running task is the moment the link is
/// misbehaving, and a Stop button that refuses to work because the link is
/// unhealthy is a Stop button that fails when it is needed. `jarvis-client`
/// reached the same conclusion on its own side, where `decisionBlocker`
/// gates `decide`/`revert` and deliberately does not gate amend.
async fn post_task_control(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {base}")
            } else {
                format!("unable to reach `{path}`: {e}")
            }
        })?;

    let status = response.status();
    let detail = response.text().await.unwrap_or_default();
    if status.is_success() {
        return Ok(serde_json::from_str(&detail).unwrap_or(serde_json::Value::Null));
    }
    // A 404 means this backend does not have `backend/task-control.patch`
    // applied, and saying so beats a bare status code.
    if status.as_u16() == 404 {
        return Err(format!(
            "this Jarvis backend has no `{path}` route - apply the backend \
             patches (task-control.patch) to turn it on"
        ));
    }
    Err(server_sentence(status.as_u16(), path, &detail))
}

/// The sentence a task-control route put in its `error` field, or the raw
/// body when it did not send one. Those routes answer a 409 with a plain
/// reason ("nothing is running or paused"), which reads better than JSON.
fn server_sentence(code: u16, path: &str, body: &str) -> String {
    let said = serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(str::to_string));
    match said {
        Some(reason) if !reason.trim().is_empty() => {
            let mut s = reason.trim().to_string();
            if let Some(first) = s.get(0..1) {
                let upper = first.to_uppercase();
                s.replace_range(0..1, &upper);
            }
            s
        }
        _ => format!("the server answered HTTP {code} to {path}: {}", body.trim()),
    }
}

/// Pause, resume, or stop whatever Jarvis is running right now, and add a
/// note to it — `docs/AUTONOMY-PROPOSALS.md` §3d, served by
/// `backend/task-control.patch`. Stop and Pause need no approval card.
/// Resume does not carry on by itself: the server raises one card listing
/// the steps that are left, and runs them only if that card is approved.
///
/// These four and [`amend_approval`] were invoked by `jarvis-link.js` long
/// before they existed here, so every one of those buttons failed at the
/// Tauri boundary with "command not found" rather than reaching the
/// backend at all. `jarvis-client` has called the same routes over plain
/// HTTP the whole time, so the desktop was the odd one out.
///
/// None of the four takes a task id, matching the phone and matching this
/// project's own rule that "the current turn" is singular.
#[tauri::command]
pub async fn pause_task(app: AppHandle) -> Result<serde_json::Value, String> {
    post_task_control(&app, "/api/task/pause", serde_json::json!({})).await
}

/// The one task control held to rule 4 - "block acting when the event
/// stream is stale" - because it is the one that makes something go again.
/// It only raises an approval card, but that card should be answered by
/// someone looking at a live queue. Checked here, not only in the webview,
/// for the reason [`decide_approval`] gives: any window holding the
/// capability reaches this command directly.
#[tauri::command]
pub async fn resume_task(app: AppHandle) -> Result<serde_json::Value, String> {
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err("the event stream is stale, so resuming is held until it \
                    reconnects - Stop still works"
            .to_string());
    }
    post_task_control(&app, "/api/task/resume", serde_json::json!({})).await
}

#[tauri::command]
pub async fn stop_task(app: AppHandle) -> Result<serde_json::Value, String> {
    post_task_control(&app, "/api/task/stop", serde_json::json!({})).await
}

#[tauri::command]
pub async fn inject_task_note(app: AppHandle, note: String) -> Result<serde_json::Value, String> {
    post_task_control(&app, "/api/task/note", serde_json::json!({ "note": note })).await
}

/// Asks the backend to switch power mode - `POST /api/power`
/// (`backend/power-mode.patch`). Returns the server's own sentence.
///
/// Going quieter always goes through; waking (`"active"`) is held while the
/// event stream is stale - rule 4, "block acting when the event stream is
/// stale" - since it is the direction that makes Jarvis do more. The server
/// still decides through its gate (`power_manage`).
pub async fn set_power_mode(app: &AppHandle, mode: &str) -> Result<String, String> {
    if mode == "active" && app.state::<crate::stream::StreamState>().link().stale {
        return Err(
            "the event stream is stale, so waking Jarvis is held until it \
                    reconnects - going quieter still works"
                .to_string(),
        );
    }
    let out = post_task_control(app, "/api/power", serde_json::json!({ "mode": mode })).await;
    match out {
        Ok(v) => Ok(v
            .get("message")
            .and_then(|m| m.as_str())
            .unwrap_or("The power mode request was sent.")
            .to_string()),
        Err(e) if e.contains("has no `/api/power` route") => Err(
            "this Jarvis backend cannot change power mode yet - apply the backend \
             patches (power-mode.patch) to turn it on"
                .to_string(),
        ),
        Err(e) => Err(e),
    }
}

/// Percent-encodes one path segment.
///
/// Hand-rolled rather than pulled from `url`, which is not a dependency of
/// this crate, and deliberately NOT `form_urlencoded`: that is the encoding
/// for a query string, where a space becomes `+`. Inside a path a `+` is a
/// literal plus, so an id containing a space would address a different
/// resource. Unreserved characters per RFC 3986 pass through; everything
/// else becomes %XX.
fn encode_path_segment(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    for byte in raw.as_bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => {
                out.push(*byte as char);
            }
            other => out.push_str(&format!("%{other:02X}")),
        }
    }
    out
}

/// A note attached to a pending proposal before it is decided — NOT a
/// decision, and it approves nothing.
///
/// The id is percent-encoded into the path, the same as the phone does:
/// an id carrying a `/` or a `?` would otherwise address a different route
/// entirely.
#[tauri::command]
pub async fn amend_approval(
    app: AppHandle,
    id: String,
    note: String,
) -> Result<serde_json::Value, String> {
    let encoded = encode_path_segment(&id);
    post_task_control(
        &app,
        &format!("/api/pending/{encoded}/amend"),
        serde_json::json!({ "note": note }),
    )
    .await
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
    let target = note_target(&target)?;
    windows::show_quickbar(&app)?;
    crate::emit_quickbar(&app, crate::events::QUICK_NOTE_SUMMON, target);
    Ok(())
}

/// The backend's name for a note target. An unknown one is refused rather
/// than filed somewhere the owner did not pick (it used to become Logseq).
pub(crate) fn note_target(target: &str) -> Result<&'static str, String> {
    match target.trim().to_ascii_lowercase().as_str() {
        "logseq" | "log" | "journal" => Ok("logseq"),
        "joplin" | "jop" => Ok("joplin"),
        // "vault" meant Joplin until 2026-09-24; it is Obsidian's word.
        "obsidian" | "obs" | "daily" | "vault" => Ok("obsidian"),
        other => Err(format!(
            "\"{other}\" is not a note app Jarvis knows - Logseq, Joplin or Obsidian"
        )),
    }
}

/// Which note apps this PC is set up for: `GET /api/notes/capture` with no
/// id (`backend/note-capture.patch`, `jarvis_note_capture.available_targets`).
/// The answer is `{"ok": true, "targets": ["logseq", ...]}` - names only,
/// never a path or a token. The windows show only those; `note-capture.js`
/// reads it, and says why when it cannot.
#[tauri::command]
pub async fn note_targets(app: AppHandle) -> Result<serde_json::Value, String> {
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .get(format!("{}/api/notes/capture", jarvis_base(&app)))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(&app))
            } else {
                format!("unable to reach `/api/notes/capture`: {e}")
            }
        })?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    note_targets_answer(status, &body)
}

/// [`note_targets`]'s reading of the server's answer, on its own so it can be
/// tested against what the backend really sends.
pub(crate) fn note_targets_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    let parsed = serde_json::from_str::<serde_json::Value>(body).ok();
    if (200..300).contains(&status) {
        if let Some(v) = parsed.filter(|v| v.get("targets").is_some_and(|t| t.is_array())) {
            return Ok(v);
        }
    }
    if status == 404 || (200..300).contains(&status) {
        // A backend from before this: a bare GET was "no note with that id".
        return Err(
            "this PC's Jarvis does not say which note apps are set up yet - \
                    copy the new backend files in (run apply-patches.ps1)"
                .to_string(),
        );
    }
    Err(server_sentence(status, "/api/notes/capture", body))
}

/// Files a note in Logseq, Joplin or Obsidian - the owner's own words, no model.
///
/// Posts to `/api/notes/capture` (`backend/note-capture.patch`). The backend
/// writes through `jarvis_gate` under the owner's own action names
/// (`append_logseq_journal`, `create_joplin_note`), so the tier in their
/// `jarvis-framework.toml` decides whether an approval card comes first.
///
/// This used to post a chat turn asking the model to call two tools that
/// existed nowhere, and could only report the model's own account of what it
/// did. Now the answer is the backend's: `state` is `"filed"` (and it read
/// the note back), `"waiting"` (a card is up - poll [`capture_note_status`]),
/// `"not_filed"` (said no, nobody answered, refused - with the reason) or
/// `"failed"`. The widget and the quickbar say exactly that.
#[tauri::command]
pub async fn capture_note(
    app: AppHandle,
    target: String,
    text: String,
) -> Result<serde_json::Value, String> {
    let text = text.trim();
    if text.is_empty() {
        return Err("nothing to capture".to_string());
    }
    let target = note_target(&target)?;
    let payload = serde_json::json!({ "target": target, "text": text });
    let response = jarvis_client(Some(CAPTURE_TIMEOUT))?
        .post(format!("{}/api/notes/capture", jarvis_base(&app)))
        .headers(jarvis_headers(&app)?)
        .json(&payload)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(&app))
            } else {
                format!("the note could not be sent: {e}")
            }
        })?;
    note_answer(response, "/api/notes/capture").await
}

/// How a note filed with [`capture_note`] ended. Never carries the note's text.
#[tauri::command]
pub async fn capture_note_status(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    let id = id.trim();
    if id.is_empty() {
        return Err("that note has no id to look up".to_string());
    }
    let path = format!("/api/notes/capture?id={}", encode_path_segment(id));
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .get(format!("{}{path}", jarvis_base(&app)))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(&app))
            } else {
                format!("unable to reach `/api/notes/capture`: {e}")
            }
        })?;
    note_answer(response, "/api/notes/capture").await
}

/// The capture routes answer 200 (finished) or 202 (waiting) with the job;
/// anything else becomes a sentence.
async fn note_answer(response: reqwest::Response, path: &str) -> Result<serde_json::Value, String> {
    let status = response.status();
    let body = response.text().await.unwrap_or_default();
    if status.is_success() {
        return serde_json::from_str(&body)
            .map_err(|_| "the server's answer about the note could not be read".to_string());
    }
    if status.as_u16() == 404 && !body.contains("\"state\"") {
        return Err(
            "this Jarvis backend cannot file notes yet - apply the backend \
                    patches (note-capture.patch) to turn it on. Nothing was filed."
                .to_string(),
        );
    }
    // A refusal the server explained ("no Logseq graph folder at ...", "no
    // Joplin token is set ...") carries a `message`; prefer it.
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(&body) {
        if let Some(m) = v.get("message").and_then(|m| m.as_str()) {
            return Err(m.to_string());
        }
    }
    Err(server_sentence(status.as_u16(), path, &body))
}

// ---------------------------------------------------------------------------
// The second graphics card (backend/second-card.patch, docs/SECOND-CARD.md)
// ---------------------------------------------------------------------------

/// The one route both second-card commands use, and `vision.rs` reads too.
pub(crate) const SECOND_CARD_PATH: &str = "/api/second-card";

/// What a backend without `jarvis_second_card.py` is told to do about it.
/// The page shows this sentence; it never sees a status code or a body.
pub(crate) const SECOND_CARD_UPDATE: &str =
    "This PC's Jarvis does not have the second graphics card part yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// A transport failure in plain words. Never the request, never a header:
/// the only thing named is the address the owner typed in Settings.
fn second_card_unreachable(err: &reqwest::Error, base: &str) -> String {
    if err.is_connect() {
        format!("Jarvis is not answering at {base}. Is it running?")
    } else if err.is_timeout() {
        "Jarvis took too long to answer. Try again in a moment.".to_string()
    } else {
        "The request to Jarvis did not finish. Try again in a moment.".to_string()
    }
}

/// The backend's own sentence (`{"error": "..."}`), first letter raised,
/// words unchanged - JARVIS-API.md section 12 says to show it word for word.
/// With no sentence, a plain line with the status code, never the body.
fn second_card_refusal(code: u16, body: &str) -> String {
    let said = serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(str::to_string));
    match said {
        Some(reason) if !reason.trim().is_empty() => {
            let mut s = reason.trim().to_string();
            if let Some(first) = s.get(0..1) {
                let upper = first.to_uppercase();
                s.replace_range(0..1, &upper);
            }
            s
        }
        _ => format!("Jarvis refused the request (HTTP {code})."),
    }
}

/// [`second_card_refusal`] under a name other routes can use: the backend's
/// own `error` sentence, first letter raised, or a plain line with the code.
/// Settings' Voice section and "This backend supports" use it.
pub(crate) fn backend_refusal(code: u16, body: &str) -> String {
    second_card_refusal(code, body)
}

/// [`second_card_unreachable`] under a name other routes can use.
pub(crate) fn backend_unreachable(err: &reqwest::Error, base: &str) -> String {
    second_card_unreachable(err, base)
}

/// Whether a 404/503 means "this backend has no second-card module": a 404
/// (no such route - an older backend), or the route's own 503
/// `{"available": false}` when `jarvis_second_card.py` is missing. A POST 503
/// with an `error` sentence and no `available: false` is a real refusal ("no
/// capable second card"), and is NOT this.
fn second_card_missing(code: u16, body: &str) -> bool {
    if code == 404 {
        return true;
    }
    code == 503
        && serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
            == Some(false)
}

/// [`get_second_card`]'s reading of the server's answer, on its own so it can
/// be tested against `tests/fixtures/second-card-cases.json` (the real
/// `status()` output).
///
/// * 200 with `detected` and `features` - `status()` itself, passed on as is.
/// * 404, or 503 `{"available": false}` - `{"available": false, "why":
///   "<update the backend>"}`, so the page says what to do rather than error.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn second_card_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let parsed = serde_json::from_str::<serde_json::Value>(body).ok();
        return parsed
            .filter(|v| {
                v.get("detected").is_some_and(|d| d.is_object())
                    && v.get("features").is_some_and(|f| f.is_array())
            })
            .ok_or_else(|| {
                "Jarvis answered, but not in a way this app can read. \
                 Update the backend by running apply-patches.ps1."
                    .to_string()
            });
    }
    if second_card_missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": SECOND_CARD_UPDATE }));
    }
    Err(second_card_refusal(status, body))
}

/// [`set_second_card`]'s reading of the server's answer. 200 is the backend's
/// `{"ok", "enabled", "pending", "message"}` as is: `pending: true` means an
/// approval card is up and NOTHING is on yet. Every refusal (409 a card
/// already waits, 400 the main switch or a needed feature is off, 503 no
/// capable card) is the backend's own sentence.
pub(crate) fn second_card_change_answer(
    status: u16,
    body: &str,
) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if second_card_missing(status, body) {
        return Err(SECOND_CARD_UPDATE.to_string());
    }
    Err(second_card_refusal(status, body))
}

/// A switch name the backend could know: `master` or a feature id, lower-case
/// letters and underscores only. The backend refuses an unknown one with its
/// own sentence; this only keeps anything else from being sent at all.
pub(crate) fn second_card_feature(feature: &str) -> Result<&str, String> {
    let f = feature.trim();
    if f.is_empty() || f.len() > 40 || !f.bytes().all(|b| b.is_ascii_lowercase() || b == b'_') {
        return Err("That is not one of the second graphics card's switches.".to_string());
    }
    Ok(f)
}

/// What the second graphics card could do on this PC, and which of its
/// switches are on: `GET /api/second-card` (`jarvis_second_card.status()`).
///
/// Settings window only (permissions/surfaces.toml, `settings-surface`). The
/// answer names the cards and their hardware ids (`GPU-...`) and carries the
/// one-line PowerShell `pin_command`; it never carries a token. The token goes
/// out in `X-Jarvis-Token` through [`jarvis_headers`], with `X-Jarvis-Client:
/// hud`, the same as every other call to Jarvis, and is never logged or put in
/// an error.
#[tauri::command]
pub async fn get_second_card(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .get(format!("{base}{SECOND_CARD_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| second_card_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    second_card_answer(status, &body)
}

/// One second-card switch on or off: `POST /api/second-card` with
/// `{"feature", "enabled"}`.
///
/// This approves nothing. ON only raises one approval card on the PC and the
/// phone (action `second_card_enable`, tier `ask`), and the answer says
/// `pending: true` until the owner decides it there. OFF is immediate, because
/// it only narrows what runs. There is no form that sends more than one
/// switch. Settings window only, like [`get_second_card`].
///
/// ON is held while the event stream is stale - rule 4, the same
/// one-direction hold as [`set_big_model`]: the card it raises should be
/// answered by someone looking at a live queue. OFF always goes through.
#[tauri::command]
pub async fn set_second_card(
    app: AppHandle,
    feature: String,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    let feature = second_card_feature(&feature)?;
    if enabled && app.state::<crate::stream::StreamState>().link().stale {
        return Err(
            "The connection to Jarvis is catching up, so nothing can be turned on until \
             it does. Turning things off still works."
                .to_string(),
        );
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(CAPTURE_TIMEOUT))?
        .post(format!("{base}{SECOND_CARD_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "feature": feature, "enabled": enabled }))
        .send()
        .await
        .map_err(|e| second_card_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    second_card_change_answer(status, &body)
}

// ---------------------------------------------------------------------------
// "This backend supports": the capabilities GET /api/version reports
// ---------------------------------------------------------------------------

/// Whether one `capabilities` entry means "present" - the phone's
/// `asCapabilityFlag` (ApiModels.kt), so both apps show the same list.
///
/// `true`, a non-empty object (a capability that carries detail, like
/// `power`), or a non-empty string other than "false". Anything else -
/// `false`, `{}`, a number, `null`, a list - is absent: a client that hides
/// what it could have shown is a smaller failure than one that shows what
/// is not there.
pub(crate) fn capability_present(value: &serde_json::Value) -> bool {
    match value {
        serde_json::Value::Bool(b) => *b,
        serde_json::Value::String(s) => !s.is_empty() && !s.eq_ignore_ascii_case("false"),
        serde_json::Value::Object(m) => !m.is_empty(),
        _ => false,
    }
}

/// [`get_backend_capabilities`]'s reading of `GET /api/version`: the
/// server's name, the API number and two sorted lists of capability NAMES -
/// what it has and what it reports not having. Only the names leave here;
/// what a capability carries (`power` carries the mode and quiet hours) is
/// not passed on, because the page shows names only.
pub(crate) fn capabilities_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if !(200..300).contains(&status) {
        if status == 404 {
            return Err(
                "Something answered at that address, but it is not a Jarvis server that \
                 reports what it supports."
                    .to_string(),
            );
        }
        return Err(backend_refusal(status, body));
    }
    let version = serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
        .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string())?;
    let mut on = Vec::new();
    let mut off = Vec::new();
    if let Some(caps) = version.get("capabilities").and_then(|c| c.as_object()) {
        for (name, value) in caps {
            if capability_present(value) {
                on.push(name.clone());
            } else {
                off.push(name.clone());
            }
        }
    }
    on.sort();
    off.sort();
    Ok(serde_json::json!({
        "server": version.get("server").and_then(|s| s.as_str()).unwrap_or(""),
        "api": version.get("api").and_then(|a| a.as_i64()),
        "on": on,
        "off": off,
    }))
}

/// What the Jarvis server says it supports: `GET /api/version`'s
/// `capabilities`, as two lists of names - the list the phone shows under
/// "This backend". Read only.
///
/// Settings window only (permissions/surfaces.toml, `settings-surface`). The
/// token goes out in `X-Jarvis-Token` through [`jarvis_headers`], with
/// `X-Jarvis-Client: hud`, like every other call to Jarvis, and is never
/// logged or put in an error.
#[tauri::command]
pub async fn get_backend_capabilities(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .get(format!("{base}/api/version"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    capabilities_answer(status, &body)
}

#[cfg(test)]
mod capabilities_tests {
    use super::{capabilities_answer, capability_present};
    use serde_json::json;

    #[test]
    fn present_means_what_it_means_on_the_phone() {
        for yes in [
            json!(true),
            json!({"mode": "active"}),
            json!("on"),
            json!("yes"),
        ] {
            assert!(capability_present(&yes), "{yes} should count");
        }
        for no in [
            json!(false),
            json!({}),
            json!(""),
            json!("false"),
            json!("FALSE"),
            json!(1),
            json!(null),
            json!([true]),
        ] {
            assert!(!capability_present(&no), "{no} should not count");
        }
    }

    #[test]
    fn names_only_sorted_in_two_lists() {
        let body = json!({
            "api": 1,
            "server": "jarvis_hud",
            "capabilities": {
                "voice": true,
                "approvals": true,
                "power": {"mode": "quiet", "why": "you set it", "quiet_hours": "22-7"},
                "appearance": false,
                "second_card": {},
                "models": "true"
            }
        })
        .to_string();
        let got = capabilities_answer(200, &body).expect("reads");
        assert_eq!(got["on"], json!(["approvals", "models", "power", "voice"]));
        assert_eq!(got["off"], json!(["appearance", "second_card"]));
        assert_eq!(got["server"], "jarvis_hud");
        assert_eq!(got["api"], 1);
        // What a capability carries does not leave: names only.
        assert!(!got.to_string().contains("quiet_hours"));
    }

    #[test]
    fn the_rebuilt_hello_reads_as_the_phone_would_read_it() {
        // backend/rebuilt/jarvis_events.hello()'s `capabilities`, run on
        // 2026-09-24 with none of the owner's own modules present (so most
        // are false); `power` and `voice` shortened, their shape kept.
        let body = json!({"api": 1, "server": "jarvis-hud", "capabilities": {
            "approvals": false, "memory": true, "models": false, "skills": false,
            "power": {"mode": "active", "why": "startup", "quiet_hours": false},
            "voice": {"enabled": true, "mode": "owner", "enrolled": false},
            "persona": false, "appearance": false, "connectors": {}
        }})
        .to_string();
        let got = capabilities_answer(200, &body).expect("reads");
        assert_eq!(got["on"], json!(["memory", "power", "voice"]));
        assert_eq!(
            got["off"],
            json!([
                "appearance",
                "approvals",
                "connectors",
                "models",
                "persona",
                "skills"
            ])
        );
    }

    #[test]
    fn an_old_or_odd_answer_is_a_sentence() {
        let bare = capabilities_answer(200, r#"{"api": 1}"#).expect("reads");
        assert_eq!(bare["on"], json!([]));
        assert_eq!(bare["off"], json!([]));
        assert!(capabilities_answer(200, "<html>").is_err());
        let gone = capabilities_answer(404, "").unwrap_err();
        assert!(gone.contains("not a Jarvis server"), "{gone}");
        let refused = capabilities_answer(401, r#"{"error": "token required"}"#).unwrap_err();
        assert_eq!(refused, "Token required");
    }
}

#[cfg(test)]
mod second_card_tests {
    use super::{
        second_card_answer, second_card_change_answer, second_card_feature, SECOND_CARD_UPDATE,
    };

    /// The real `status()` output, one per case, made by
    /// `tools/gen_second_card_cases.py` - never hand-written here.
    const CASES: &str = include_str!("../../tests/fixtures/second-card-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("second-card-cases.json is JSON")
    }

    #[test]
    fn every_real_status_is_passed_on_unchanged() {
        let doc = cases();
        let all = doc["cases"].as_object().expect("cases");
        assert!(all.len() >= 6, "fewer cases than the fixture promised");
        for (name, status) in all {
            let body = status.to_string();
            let got = second_card_answer(200, &body).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, status, "{name}");
        }
    }

    #[test]
    fn an_older_backend_is_told_to_update_not_shown_an_error() {
        // 404: no such route. 503 {"available": false}: the patch is in but
        // jarvis_second_card.py is missing (second-card.patch's own answer).
        for (code, body) in [
            (404, ""),
            (404, "<html>Not Found</html>"),
            (
                503,
                r#"{"available": false, "error": "ModuleNotFoundError: No module named 'jarvis_second_card'"}"#,
            ),
        ] {
            let got = second_card_answer(code, body).expect("not an error");
            assert_eq!(got["available"], false, "{code}");
            assert_eq!(got["why"], SECOND_CARD_UPDATE);
            assert!(!got.to_string().contains("ModuleNotFoundError"));
            assert_eq!(
                second_card_change_answer(code, body).unwrap_err(),
                SECOND_CARD_UPDATE
            );
        }
        assert!(SECOND_CARD_UPDATE.contains("apply-patches.ps1"));
    }

    #[test]
    fn a_refusal_is_the_backends_own_sentence_never_its_json() {
        // jarvis_second_card.request_change's real refusals.
        let busy = r#"{"error": "a card to turn on \"Pictures\" is already waiting - approve or deny that one"}"#;
        assert_eq!(
            second_card_change_answer(409, busy).unwrap_err(),
            "A card to turn on \"Pictures\" is already waiting - approve or deny that one"
        );
        let no_card = r#"{"error": "The second graphics card cannot be turned on: only one graphics card found (the NVIDIA GeForce RTX 2080 SUPER)."}"#;
        let said = second_card_change_answer(503, no_card).unwrap_err();
        assert!(said.starts_with("The second graphics card cannot be turned on"));
        assert_ne!(
            said, SECOND_CARD_UPDATE,
            "a real 503 refusal read as 'update'"
        );
        // No sentence: a plain line, and never the body.
        let odd = second_card_answer(500, "<html>boom</html>").unwrap_err();
        assert!(!odd.contains("<html>") && odd.contains("500"), "{odd}");
        // A 200 that is not status() is not passed on.
        assert!(second_card_answer(200, r#"{"ok": true}"#).is_err());
        assert!(second_card_answer(200, "not json").is_err());
    }

    #[test]
    fn on_is_pending_until_the_card_is_decided() {
        // request_change's real 200 answers.
        let up = r#"{"ok": true, "enabled": false, "pending": true, "message": "Approve the card on your PC or phone to turn it on. Nothing changes until you do."}"#;
        let got = second_card_change_answer(200, up).unwrap();
        assert_eq!(got["pending"], true);
        assert_eq!(got["enabled"], false);
        let off = r#"{"ok": true, "enabled": false, "pending": false, "message": "\"Pictures\" is off."}"#;
        assert_eq!(
            second_card_change_answer(200, off).unwrap()["pending"],
            false
        );
    }

    #[test]
    fn only_a_switch_name_is_sent() {
        let doc = cases();
        for f in doc["cases"]["capable_off"]["features"].as_array().unwrap() {
            let id = f["id"].as_str().unwrap();
            assert_eq!(second_card_feature(id), Ok(id));
        }
        assert_eq!(second_card_feature("master"), Ok("master"));
        let long = "a".repeat(41);
        for bad in ["", "Vision", "vision; rm", "../x", long.as_str()] {
            assert!(second_card_feature(bad).is_err(), "{bad:?} was accepted");
        }
    }
}

#[cfg(test)]
mod note_target_tests {
    use super::{note_target, note_targets_answer};

    /// The backend's real answers, written by `backend/test_obsidian_notes.py
    /// --write` from `jarvis_note_capture` itself.
    const FIXTURE: &str =
        include_str!("../../../jarvis-client/app/src/test/resources/contract/note-targets.json");

    fn case(name: &str) -> (u16, String) {
        let all: serde_json::Value = serde_json::from_str(FIXTURE).expect("fixture parses");
        let c = &all[name];
        (
            c["status"].as_u64().expect("status") as u16,
            c["body"].to_string(),
        )
    }

    #[test]
    fn the_real_answers_are_read() {
        let (status, body) = case("all");
        let v = note_targets_answer(status, &body).expect("a list");
        assert_eq!(
            v["targets"],
            serde_json::json!(["logseq", "joplin", "obsidian"])
        );
        let (status, body) = case("none");
        assert_eq!(
            note_targets_answer(status, &body).expect("a list")["targets"],
            serde_json::json!([])
        );
    }

    /// An older backend is said to be older - not read as "nothing set up".
    #[test]
    fn an_older_backend_says_so() {
        let (status, body) = case("older_backend");
        let err = note_targets_answer(status, &body).expect_err("not a list");
        assert!(err.contains("apply-patches"), "{err}");
    }

    #[test]
    fn targets_map_and_an_unknown_one_is_refused() {
        assert_eq!(note_target("OBS"), Ok("obsidian"));
        assert_eq!(note_target("vault"), Ok("obsidian"));
        assert_eq!(note_target("jop"), Ok("joplin"));
        assert_eq!(note_target(" log "), Ok("logseq"));
        assert!(note_target("evernote").is_err());
    }
}

// ---------------------------------------------------------------------------
// The wiki builder - backend/wiki.patch and backend/jarvis_wiki.py
// ---------------------------------------------------------------------------

/// The folder, inside the owner's Obsidian vault, that the wiki builder
/// writes to. The only folder [`wiki_open_folder`] will ever open.
const WIKI_FOLDER_NAME: &str = "Jarvis Wiki";

/// What the wiki builder can do now: `GET /api/wiki`. Whether it can run
/// (it needs the second graphics card's "wiki" lane) and why not, the
/// documents in `Jarvis Wiki/Sources` with their state, the last few log
/// lines, and how many pages there are. Never a page's text.
#[tauri::command]
pub async fn wiki_status(app: AppHandle) -> Result<serde_json::Value, String> {
    let (status, body) = wiki_get(&app, "/api/wiki").await?;
    wiki_answer(status, &body, "/api/wiki")
}

/// "Add to wiki" for one document in `Jarvis Wiki/Sources`:
/// `POST /api/wiki/ingest`. The backend's model reads it and then raises ONE
/// approval card (`wiki_update`); nothing is written before that card is
/// answered. The answer is the job (`state: "reading"`), or an explained
/// refusal (`state: "refused"` with `error`).
///
/// Held while the event stream is stale - rule 4 - for the reason
/// [`decide_approval`] gives: the card it raises should be answered by
/// someone looking at a live queue, and any window holding the capability
/// reaches this command directly, whatever its button shows.
#[tauri::command]
pub async fn wiki_ingest(app: AppHandle, source: String) -> Result<serde_json::Value, String> {
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(
            "the event stream is stale, so nothing can be added to the wiki \
                    until it reconnects"
                .to_string(),
        );
    }
    let source = source.trim();
    if source.is_empty() {
        return Err("say which document to add to the wiki".to_string());
    }
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .post(format!("{}/api/wiki/ingest", jarvis_base(&app)))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "source": source }))
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(&app))
            } else {
                format!("unable to reach `/api/wiki/ingest`: {e}")
            }
        })?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    wiki_answer(status, &body, "/api/wiki/ingest")
}

/// How one "Add to wiki" is going: `GET /api/wiki/ingest?id=`. `state` is
/// `reading`, `waiting` (the card is up), `writing`, `done`, `refused` or
/// `failed`, with the backend's own sentence in `message`.
#[tauri::command]
pub async fn wiki_ingest_status(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    let id = id.trim();
    if id.is_empty() {
        return Err("that wiki job has no id to look up".to_string());
    }
    let path = format!("/api/wiki/ingest?id={}", encode_path_segment(id));
    let (status, body) = wiki_get(&app, &path).await?;
    wiki_answer(status, &body, "/api/wiki/ingest")
}

/// Opens `Jarvis Wiki` in Explorer. The folder comes from the backend's own
/// answer, read here in Rust - never from the page - and is opened only when
/// the backend is on this PC (a loopback address), the path is absolute,
/// names a folder called exactly "Jarvis Wiki", and that folder is here.
/// A folder, never a file: the same reasoning as [`open_log_folder`].
#[tauri::command]
pub async fn wiki_open_folder(app: AppHandle) -> Result<(), String> {
    if !base_is_loopback(&jarvis_base(&app)) {
        return Err(
            "the wiki folder is on the PC Jarvis runs on, not this one - open it there".to_string(),
        );
    }
    let (status, body) = wiki_get(&app, "/api/wiki").await?;
    let answer = wiki_answer(status, &body, "/api/wiki")?;
    let dir = wiki_folder_to_open(&answer)?;

    #[cfg(target_os = "windows")]
    let program = "explorer.exe";
    #[cfg(target_os = "macos")]
    let program = "open";
    #[cfg(all(unix, not(target_os = "macos")))]
    let program = "xdg-open";

    std::process::Command::new(program)
        .arg(dir.as_os_str())
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("could not open {}: {e}", dir.display()))
}

async fn wiki_get(app: &AppHandle, path: &str) -> Result<(u16, String), String> {
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .get(format!("{}{path}", jarvis_base(app)))
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(app))
            } else {
                format!("unable to reach the wiki builder: {e}")
            }
        })?;
    let status = response.status().as_u16();
    Ok((status, response.text().await.unwrap_or_default()))
}

/// Reads one of the wiki routes' answers. A JSON object on success is the
/// answer; a refusal the backend explained (`"state": "refused"`, with its
/// sentence in `error`) is an answer too, for the page to show as it is.
/// Everything else becomes a sentence.
pub(crate) fn wiki_answer(
    status: u16,
    body: &str,
    path: &str,
) -> Result<serde_json::Value, String> {
    let parsed = serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object());
    if let Some(v) = parsed.as_ref() {
        if (200..300).contains(&status) || v.get("state").is_some() {
            return Ok(v.clone());
        }
    }
    if status == 404 && path == "/api/wiki/ingest" && parsed.is_some() {
        return Err(
            "Jarvis no longer knows this job - it may have restarted. Nothing \
                    is written without an approval card; look in the wiki folder to see."
                .to_string(),
        );
    }
    if status == 404 {
        return Err(
            "this PC's Jarvis has no wiki builder yet - copy the new backend \
                    files in (run apply-patches.ps1)"
                .to_string(),
        );
    }
    if (200..300).contains(&status) {
        return Err("the server's answer about the wiki could not be read".to_string());
    }
    Err(server_sentence(status, path, body))
}

/// The folder [`wiki_open_folder`] may open, from `GET /api/wiki`'s answer.
pub(crate) fn wiki_folder_to_open(
    answer: &serde_json::Value,
) -> Result<std::path::PathBuf, String> {
    let folder = answer
        .get("folder")
        .and_then(|f| f.as_str())
        .filter(|f| !f.trim().is_empty())
        .ok_or_else(|| {
            "the wiki folder is not set up yet - make a \"Jarvis Wiki\" folder in your vault"
                .to_string()
        })?;
    let dir = std::path::PathBuf::from(folder);
    if !dir.is_absolute() || dir.file_name() != Some(std::ffi::OsStr::new(WIKI_FOLDER_NAME)) {
        return Err(format!(
            "the backend named {folder}, which is not a \"{WIKI_FOLDER_NAME}\" folder, so it \
             is not opened"
        ));
    }
    if !dir.is_dir() {
        return Err(format!("{} is not a folder on this PC", dir.display()));
    }
    Ok(dir)
}

/// Is the Jarvis address this PC (127.x, ::1 or localhost)?
pub(crate) fn base_is_loopback(base: &str) -> bool {
    let Ok(url) = reqwest::Url::parse(base) else {
        return false;
    };
    match url.host_str() {
        Some(h) if h.eq_ignore_ascii_case("localhost") => true,
        Some(h) => h
            .trim_start_matches('[')
            .trim_end_matches(']')
            .parse::<std::net::IpAddr>()
            .map(|ip| ip.is_loopback())
            .unwrap_or(false),
        None => false,
    }
}

#[cfg(test)]
mod wiki_tests {
    use super::{base_is_loopback, wiki_answer, wiki_folder_to_open};

    /// The backend's real answers, written by `tools/gen_wiki_cases.py` from
    /// `jarvis_wiki` itself; `backend/test_wiki.py` fails when it is stale.
    const FIXTURE: &str = include_str!("../../tests/fixtures/wiki-cases.json");

    fn case(name: &str) -> (u16, String, String) {
        let all: serde_json::Value = serde_json::from_str(FIXTURE).expect("fixture parses");
        let c = &all["cases"][name];
        (
            c["status"].as_u64().expect("status") as u16,
            c["body"].to_string(),
            name.to_string(),
        )
    }

    #[test]
    fn the_real_answers_are_read() {
        let (status, body, _) = case("status_ready");
        let v = wiki_answer(status, &body, "/api/wiki").expect("an answer");
        assert_eq!(v["available"], serde_json::json!(true));
        assert!(v["sources"].as_array().is_some_and(|s| s.len() == 5));
        let (status, body, _) = case("ingest_started");
        assert_eq!(status, 202);
        let v = wiki_answer(status, &body, "/api/wiki/ingest").expect("a job");
        assert_eq!(v["state"], serde_json::json!("reading"));
    }

    /// A refusal the backend explained reaches the page as it is.
    #[test]
    fn an_explained_refusal_is_an_answer() {
        for name in [
            "ingest_in_wiki",
            "ingest_busy",
            "ingest_off",
            "ingest_too_big",
        ] {
            let (status, body, _) = case(name);
            let v = wiki_answer(status, &body, "/api/wiki/ingest").expect(name);
            assert_eq!(v["state"], serde_json::json!("refused"), "{name}");
            assert!(v["error"].as_str().is_some_and(|e| !e.is_empty()), "{name}");
        }
    }

    #[test]
    fn an_older_backend_and_a_lost_job_say_so() {
        let err = wiki_answer(404, "", "/api/wiki").expect_err("no route");
        assert!(err.contains("apply-patches"), "{err}");
        let (status, body, _) = case("job_unknown");
        let err = wiki_answer(status, &body, "/api/wiki/ingest").expect_err("lost");
        assert!(err.contains("no longer knows"), "{err}");
    }

    #[test]
    fn only_a_real_jarvis_wiki_folder_is_opened() {
        let dir = std::env::temp_dir().join(format!("jarvis-wiki-open-{}", std::process::id()));
        let wiki = dir.join("Jarvis Wiki");
        std::fs::create_dir_all(&wiki).expect("temp folder");
        let ok = wiki_folder_to_open(&serde_json::json!({ "folder": wiki.to_string_lossy() }));
        assert_eq!(ok.as_deref(), Ok(wiki.as_path()));
        let other = wiki_folder_to_open(&serde_json::json!({ "folder": dir.to_string_lossy() }));
        assert!(other.is_err());
        assert!(wiki_folder_to_open(&serde_json::json!({ "folder": "Jarvis Wiki" })).is_err());
        assert!(wiki_folder_to_open(&serde_json::json!({ "folder": null })).is_err());
        // The fixture's folder is a made-up path, not a folder on this PC.
        let (_, body, _) = case("status_ready");
        let v: serde_json::Value = serde_json::from_str(&body).expect("json");
        assert!(wiki_folder_to_open(&v).is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_folder_opens_only_for_a_backend_on_this_pc() {
        assert!(base_is_loopback("http://127.0.0.1:4719"));
        assert!(base_is_loopback("http://localhost:4719"));
        assert!(base_is_loopback("http://[::1]:4719"));
        assert!(!base_is_loopback("http://100.64.1.2:4719"));
        assert!(!base_is_loopback("http://desktop.tailnet.ts.net:4719"));
        assert!(!base_is_loopback("not a url"));
    }
}

// ---------------------------------------------------------------------------
// The big model, slow - backend/big-model.patch, backend/jarvis_big_model.py,
// docs/BIG-MODEL.md, JARVIS-API.md section 14
// ---------------------------------------------------------------------------

/// What was found and the three switches: `GET` and `POST`.
pub(crate) const BIG_MODEL_PATH: &str = "/api/big-model";
/// The deep questions and their answers, newest first.
pub(crate) const DEEP_PATH: &str = "/api/deep";
/// Queue one deep question.
pub(crate) const DEEP_ASK_PATH: &str = "/api/deep/ask";

/// The longest question the backend takes, in characters (Unicode code
/// points, as Python's `len` counts them): `jarvis_big_model.MAX_QUESTION_CHARS`,
/// which `GET /api/deep` reports as `limits.question_chars`. A test holds the
/// two together against the real fixture.
pub(crate) const DEEP_QUESTION_CHARS: usize = 4000;

/// The only switch names `POST /api/big-model` knows, in its own words:
/// the main switch, then one per background job.
pub(crate) const BIG_MODEL_SWITCHES: [&str; 3] = ["master", "wiki", "deep_questions"];

/// What a backend without `jarvis_big_model.py` (or without the patch at all)
/// is told to do about it. The page shows this sentence; it never sees a
/// status code or a body.
pub(crate) const BIG_MODEL_UPDATE: &str = "This PC's Jarvis does not have the big model part yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// [`get_big_model`]'s reading of the server's answer, on its own so it can
/// be tested against `tests/fixtures/big-model-cases.json` (the real
/// `status()` output).
///
/// * 200 with `detected` and `switches` - `status()` itself, passed on as is.
/// * 404, or 503 `{"available": false}` - `{"available": false, "why":
///   "<update the backend>"}`, so the page says what to do rather than error.
/// * anything else - the backend's own sentence, or a plain line.
///
/// The "module missing", refusal and unreachable readings are the second
/// card's ([`second_card_missing`], [`second_card_refusal`],
/// [`second_card_unreachable`]): the same backend shapes, the same words.
pub(crate) fn big_model_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| {
                v.get("detected").is_some_and(|d| d.is_object())
                    && v.get("switches").is_some_and(|s| s.is_array())
            })
            .ok_or_else(|| {
                "Jarvis answered, but not in a way this app can read. \
                 Update the backend by running apply-patches.ps1."
                    .to_string()
            });
    }
    if second_card_missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": BIG_MODEL_UPDATE }));
    }
    Err(second_card_refusal(status, body))
}

/// [`set_big_model`]'s reading of the server's answer. 200 is the backend's
/// `{"ok", "enabled", "pending", "message"}` as is: `pending: true` means an
/// approval card is up and NOTHING is on yet. Every refusal (409 a card
/// already waits, 400 the main switch is off, 503 not possible here) is the
/// backend's own sentence.
pub(crate) fn big_model_change_answer(
    status: u16,
    body: &str,
) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if second_card_missing(status, body) {
        return Err(BIG_MODEL_UPDATE.to_string());
    }
    Err(second_card_refusal(status, body))
}

/// One of [`BIG_MODEL_SWITCHES`], exactly, or a refusal. Nothing else is
/// ever sent.
pub(crate) fn big_model_switch(name: &str) -> Result<&'static str, String> {
    BIG_MODEL_SWITCHES
        .iter()
        .find(|s| **s == name)
        .copied()
        .ok_or_else(|| "That is not one of the big model's switches.".to_string())
}

/// [`get_deep`]'s reading of the server's answer: `deep_status()` (an object
/// with `available` and a `jobs` list) passed on as is; an older backend is
/// `{"available": false, "why": "<update the backend>"}`, with no `jobs`.
pub(crate) fn deep_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| {
                v.get("available").is_some_and(|a| a.is_boolean())
                    && v.get("jobs").is_some_and(|j| j.is_array())
            })
            .ok_or_else(|| {
                "Jarvis answered, but not in a way this app can read. \
                 Update the backend by running apply-patches.ps1."
                    .to_string()
            });
    }
    if second_card_missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": BIG_MODEL_UPDATE }));
    }
    Err(second_card_refusal(status, body))
}

/// [`ask_deep`]'s reading of the server's answer. The 202 job, and every
/// refusal the backend explained (`{"ok": false, "state": "refused",
/// "error"}` - empty, too long, three already waiting, not available), are
/// answers for the page to show as they are, like the wiki's. An older
/// backend is the update sentence; anything else a plain line.
pub(crate) fn deep_ask_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    let parsed = serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object());
    if let Some(v) = parsed.as_ref() {
        let refused = v.get("state").and_then(|s| s.as_str()) == Some("refused");
        if (200..300).contains(&status) || refused {
            return Ok(v.clone());
        }
    }
    if second_card_missing(status, body) {
        return Err(BIG_MODEL_UPDATE.to_string());
    }
    if (200..300).contains(&status) {
        return Err("Jarvis answered, but not in a way this app can read.".to_string());
    }
    Err(second_card_refusal(status, body))
}

/// The question as the backend will count it: trimmed, Windows line ends
/// made plain (`ask` does both), then at most [`DEEP_QUESTION_CHARS`]
/// characters. Refused here, with a sentence, rather than sent to be refused.
pub(crate) fn deep_question(text: &str) -> Result<String, String> {
    let q = text.trim().replace("\r\n", "\n");
    if q.is_empty() {
        return Err("Type a question first.".to_string());
    }
    let n = q.chars().count();
    if n > DEEP_QUESTION_CHARS {
        return Err(format!(
            "The question is {} characters long; at most {} can be asked. Shorten it and \
             ask again.",
            thousands(n),
            thousands(DEEP_QUESTION_CHARS)
        ));
    }
    Ok(q)
}

/// `4000` as `4,000`, the way the backend writes its own limit.
fn thousands(n: usize) -> String {
    let digits = n.to_string();
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(c);
    }
    out
}

/// What the big model could do on this PC, and which of its switches are on:
/// `GET /api/big-model` (`jarvis_big_model.status()`). Starts nothing.
///
/// Settings window only (permissions/surfaces.toml, `settings-surface`). The
/// answer names folders, drives, memory and disk; it never carries the key
/// colibri is started with (only where it is kept) and never a token. The
/// token goes out in `X-Jarvis-Token` through [`jarvis_headers`], with
/// `X-Jarvis-Client: hud`, the same as every other call to Jarvis, and is
/// never logged or put in an error.
#[tauri::command]
pub async fn get_big_model(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .get(format!("{base}{BIG_MODEL_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| second_card_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    big_model_answer(status, &body)
}

/// One big-model switch on or off: `POST /api/big-model` with
/// `{"switch", "enabled"}`, built here from the two typed arguments.
///
/// This approves nothing. ON only raises one approval card on the PC and the
/// phone (action `big_model_enable`, tier `ask`), and the answer says
/// `pending: true` until the owner decides it there. ON is held while the
/// event stream is stale - rule 4, the same one-direction hold as
/// [`resume_task`] and waking from a power mode: that card should be
/// answered by someone looking at a live queue. OFF always goes through,
/// because it only stops things. Settings window only, like
/// [`get_big_model`].
#[tauri::command]
pub async fn set_big_model(
    app: AppHandle,
    switch: String,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    let switch = big_model_switch(&switch)?;
    if enabled && app.state::<crate::stream::StreamState>().link().stale {
        return Err(
            "The connection to Jarvis is catching up, so nothing can be turned on until \
             it does. Turning things off still works."
                .to_string(),
        );
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(CAPTURE_TIMEOUT))?
        .post(format!("{base}{BIG_MODEL_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "switch": switch, "enabled": enabled }))
        .send()
        .await
        .map_err(|e| second_card_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    big_model_change_answer(status, &body)
}

/// The deep questions and their answers, newest first: `GET /api/deep`
/// (`jarvis_big_model.deep_status()`). Reads only; starts nothing.
///
/// The Brain window only (`brain-deep`). The answers are the owner's own
/// questions and answers, kept on the PC; the page renders them as text.
#[tauri::command]
pub async fn get_deep(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(APPROVAL_TIMEOUT))?
        .get(format!("{base}{DEEP_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| second_card_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    deep_answer(status, &body)
}

/// "Ask slowly": `POST /api/deep/ask` with `{"question"}`, built here from
/// the typed text after [`deep_question`] has trimmed and capped it.
///
/// There is no approval card per question (JARVIS-API.md section 14): the
/// switch was approved, and a question acts on nothing - no tools, no memory
/// writes, no web - and nothing leaves the PC. It is still held while the
/// event stream is stale, as that section asks (rule 4). The answer is the
/// queued job (`state: "queued"`) or the backend's explained refusal.
#[tauri::command]
pub async fn ask_deep(app: AppHandle, question: String) -> Result<serde_json::Value, String> {
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(
            "The connection to Jarvis is catching up, so nothing can be asked until it does."
                .to_string(),
        );
    }
    let question = deep_question(&question)?;
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(CAPTURE_TIMEOUT))?
        .post(format!("{base}{DEEP_ASK_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "question": question }))
        .send()
        .await
        .map_err(|e| second_card_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    deep_ask_answer(status, &body)
}

#[cfg(test)]
mod big_model_tests {
    use super::{
        big_model_answer, big_model_change_answer, big_model_switch, deep_answer, deep_ask_answer,
        deep_question, thousands, BIG_MODEL_SWITCHES, BIG_MODEL_UPDATE, DEEP_QUESTION_CHARS,
    };

    /// The backend's real answers, one per case, made by
    /// `tools/gen_big_model_cases.py` from `jarvis_big_model` itself - never
    /// hand-written here.
    const CASES: &str = include_str!("../../tests/fixtures/big-model-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("big-model-cases.json is JSON")
    }

    fn named(prefix: &str) -> Vec<(String, serde_json::Value)> {
        cases()["cases"]
            .as_object()
            .expect("cases")
            .iter()
            .filter(|(k, _)| k.starts_with(prefix))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect()
    }

    #[test]
    fn every_real_status_is_passed_on_unchanged() {
        let all = named("status_");
        assert!(all.len() >= 10, "fewer status cases than the fixture had");
        for (name, status) in all {
            let got = big_model_answer(200, &status.to_string())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(got, status, "{name}");
        }
    }

    #[test]
    fn every_real_deep_status_is_passed_on_unchanged() {
        let all = named("deep_");
        assert!(all.len() >= 6, "fewer deep cases than the fixture had");
        for (name, status) in all {
            let got =
                deep_answer(200, &status.to_string()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(got, status, "{name}");
        }
        // status() is not deep_status(), and the other way round.
        let off = cases()["cases"]["status_ready_off"].to_string();
        assert!(deep_answer(200, &off).is_err());
        let deep = cases()["cases"]["deep_done"].to_string();
        assert!(big_model_answer(200, &deep).is_err());
    }

    #[test]
    fn the_question_cap_is_the_backends() {
        for (name, status) in named("deep_") {
            assert_eq!(
                status["limits"]["question_chars"].as_u64(),
                Some(DEEP_QUESTION_CHARS as u64),
                "{name}"
            );
        }
        // The backend's own sentence for one too many names the same number.
        let over = cases()["cases"]["ask_too_long_400"]["body"]["error"]
            .as_str()
            .expect("error")
            .to_string();
        assert!(over.contains(&thousands(DEEP_QUESTION_CHARS)), "{over}");
        assert!(over.contains(&thousands(DEEP_QUESTION_CHARS + 1)), "{over}");
    }

    #[test]
    fn a_question_is_trimmed_and_capped_before_it_is_sent() {
        assert_eq!(
            deep_question("  Why is the sky blue?\r\n").as_deref(),
            Ok("Why is the sky blue?")
        );
        assert_eq!(deep_question("a\r\nb").as_deref(), Ok("a\nb"));
        assert!(deep_question("").is_err());
        assert!(deep_question(" \n\t ").is_err());
        let most = "é".repeat(DEEP_QUESTION_CHARS);
        assert_eq!(deep_question(&most).as_deref(), Ok(most.as_str()));
        let over = format!("{most}x");
        let said = deep_question(&over).unwrap_err();
        assert!(said.contains("4,001") && said.contains("4,000"), "{said}");
        // Counted in characters, as Python's len() counts them, not bytes.
        assert!(most.len() > DEEP_QUESTION_CHARS);
        assert_eq!(thousands(0), "0");
        assert_eq!(thousands(999), "999");
        assert_eq!(thousands(1000), "1,000");
        assert_eq!(thousands(1234567), "1,234,567");
    }

    #[test]
    fn only_the_three_switch_names_are_sent() {
        assert_eq!(BIG_MODEL_SWITCHES, ["master", "wiki", "deep_questions"]);
        for (name, status) in named("status_") {
            for sw in status["switches"].as_array().expect("switches") {
                let id = sw["id"].as_str().expect("id");
                assert_eq!(big_model_switch(id), Ok(id), "{name}");
            }
        }
        assert_eq!(big_model_switch("master"), Ok("master"));
        for bad in [
            "",
            "Master",
            "vision",
            "deep_questions ",
            "master; x",
            "../x",
        ] {
            assert!(big_model_switch(bad).is_err(), "{bad:?} was accepted");
        }
    }

    #[test]
    fn the_switch_answers_are_read() {
        let c = cases();
        let pending = &c["cases"]["post_master_on_pending"];
        let got = big_model_change_answer(
            pending["status"].as_u64().unwrap() as u16,
            &pending["body"].to_string(),
        )
        .unwrap();
        assert_eq!(got["pending"], true);
        assert_eq!(
            got["enabled"], false,
            "ON is not on until the card is approved"
        );
        let off = &c["cases"]["post_master_off"];
        let got = big_model_change_answer(200, &off["body"].to_string()).unwrap();
        assert_eq!(got["pending"], false);
        assert_eq!(got["message"], "The big model is off.");
        let again = &c["cases"]["post_master_on_again_409"];
        let said = big_model_change_answer(409, &again["body"].to_string()).unwrap_err();
        assert_eq!(
            said,
            "A card to turn on the big model is already waiting - approve or deny that one"
        );
    }

    #[test]
    fn an_ask_and_its_refusals_are_answers_the_page_shows() {
        let c = cases();
        let ok = &c["cases"]["ask_accepted"];
        assert_eq!(ok["status"], 202);
        let got = deep_ask_answer(202, &ok["body"].to_string()).unwrap();
        assert_eq!(got["state"], "queued");
        for name in ["ask_empty_400", "ask_refused_off", "ask_too_long_400"] {
            let case = &c["cases"][name];
            let code = case["status"].as_u64().unwrap() as u16;
            let got = deep_ask_answer(code, &case["body"].to_string())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(got["state"], "refused", "{name}");
            assert_eq!(got["error"], case["body"]["error"], "{name}");
        }
    }

    #[test]
    fn an_older_backend_is_told_to_update_not_shown_an_error() {
        let missing = r#"{"available": false, "error": "ModuleNotFoundError: No module named 'jarvis_big_model'"}"#;
        for (code, body) in [(404, ""), (404, "<html>Not Found</html>"), (503, missing)] {
            for got in [big_model_answer(code, body), deep_answer(code, body)] {
                let got = got.expect("not an error");
                assert_eq!(got["available"], false, "{code}");
                assert_eq!(got["why"], BIG_MODEL_UPDATE);
                assert!(!got.to_string().contains("ModuleNotFoundError"));
            }
            assert_eq!(
                big_model_change_answer(code, body).unwrap_err(),
                BIG_MODEL_UPDATE
            );
            assert_eq!(deep_ask_answer(code, body).unwrap_err(), BIG_MODEL_UPDATE);
        }
        assert!(BIG_MODEL_UPDATE.contains("apply-patches.ps1"));
        // A real 503 refusal is the backend's sentence, not "update".
        let off = &cases()["cases"]["ask_refused_off"]["body"];
        assert_eq!(
            deep_ask_answer(503, &off.to_string()).unwrap()["error"],
            "The big-model switch is off."
        );
        let no = r#"{"error": "The big model cannot be turned on: Python 3 was not found."}"#;
        let said = big_model_change_answer(503, no).unwrap_err();
        assert!(said.starts_with("The big model cannot be turned on"));
    }

    #[test]
    fn nothing_unreadable_is_passed_on_as_is() {
        for code in [200, 202] {
            assert!(big_model_answer(code, r#"{"ok": true}"#).is_err());
            assert!(deep_answer(code, r#"{"ok": true}"#).is_err());
            assert!(deep_ask_answer(code, "not json").is_err());
            assert!(big_model_change_answer(code, "[1]").is_err());
        }
        let odd = big_model_answer(500, "<html>boom</html>").unwrap_err();
        assert!(!odd.contains("<html>") && odd.contains("500"), "{odd}");
        let odd = deep_ask_answer(500, "<html>boom</html>").unwrap_err();
        assert!(!odd.contains("<html>") && odd.contains("500"), "{odd}");
    }
}

#[cfg(test)]
mod capture_tests {
    use super::{server_sentence, validate_bind_address, validate_external_url};

    /// The capture routes' refusal wording reaches the person, not raw JSON.
    #[test]
    fn a_task_route_error_is_read_out_of_its_json() {
        assert_eq!(
            server_sentence(
                409,
                "/api/task/stop",
                r#"{"ok":false,"error":"nothing is running or paused"}"#
            ),
            "Nothing is running or paused"
        );
        // CONTROL: no `error` field - the raw body is still shown.
        assert!(server_sentence(500, "/x", "boom").contains("HTTP 500"));
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

    /// The shared table: `jarvis-desktop/tests/bind-address-cases.json`.
    /// The backend's `test_bind_wildcard.py` binds a real socket to every
    /// `every_interface` entry to prove the OS really reads it as 0.0.0.0, so
    /// this list is checked against the operating system, not against itself.
    fn bind_cases(key: &str) -> Vec<String> {
        let table: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/bind-address-cases.json"))
                .expect("bind-address-cases.json is valid JSON");
        table[key]
            .as_array()
            .unwrap_or_else(|| panic!("bind-address-cases.json has no {key} list"))
            .iter()
            .map(|v| v.as_str().expect("every case is a string").to_string())
            .collect()
    }

    /// The one input this exists to stop, in every spelling the OS accepts:
    /// the wildcard would turn a same-tailnet feature into a same-network one.
    #[test]
    fn every_spelling_of_the_wildcard_is_refused_as_the_wildcard() {
        let cases = bind_cases("every_interface");
        assert!(
            cases.iter().any(|c| c == "0"),
            "the table lost the short forms"
        );
        for case in cases {
            let err = validate_bind_address(&case)
                .expect_err(&format!("{case:?} binds every interface and was accepted"));
            assert!(err.contains("every network interface"), "{case:?}: {err}");
        }
    }

    /// Non-canonical numbers, home-network and public addresses, and
    /// anything that is not a bare host.
    #[test]
    fn everything_else_the_table_refuses_is_refused() {
        for case in bind_cases("refused") {
            assert!(
                validate_bind_address(&case).is_err(),
                "{case:?} should have been refused"
            );
        }
    }

    /// CONTROL: the ordinary cases still save, or this is just a deny-all.
    #[test]
    fn the_tables_good_addresses_are_accepted() {
        for case in bind_cases("accepted") {
            let got = validate_bind_address(&case);
            assert!(got.is_ok(), "{case:?} should have been accepted: {got:?}");
        }
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

#[cfg(test)]
mod health_tests {
    use super::{summarise_health, ServiceStatus};

    fn svc(id: &'static str, name: &'static str, online: bool, optional: bool) -> ServiceStatus {
        ServiceStatus {
            id,
            name,
            url: String::new(),
            online,
            http_status: None,
            latency_ms: 0,
            detail: String::new(),
            payload: None,
            optional,
        }
    }

    /// The everyday state: no cloud lane, so nothing on :4000. That is not
    /// "2/3 online - offline: LiteLLM".
    #[test]
    fn litellm_not_running_is_not_an_outage() {
        let (online, total, summary) = summarise_health(&[
            svc("jarvis", "Jarvis Core", true, false),
            svc("ollama", "Ollama", true, false),
            svc("litellm", "LiteLLM", false, true),
        ]);
        assert_eq!((online, total), (2, 2));
        assert!(summary.starts_with("All 2 services online."), "{summary}");
        assert!(!summary.contains("offline"), "{summary}");
        assert!(summary.contains("LiteLLM is not running"), "{summary}");
    }

    /// When it does run, it counts like anything else.
    #[test]
    fn litellm_running_is_counted() {
        let (online, total, _) = summarise_health(&[
            svc("jarvis", "Jarvis Core", true, false),
            svc("ollama", "Ollama", true, false),
            svc("litellm", "LiteLLM", true, true),
        ]);
        assert_eq!((online, total), (3, 3));
    }

    /// CONTROL: a required service being down is still reported as down.
    #[test]
    fn ollama_down_is_still_an_outage() {
        let (online, total, summary) = summarise_health(&[
            svc("jarvis", "Jarvis Core", true, false),
            svc("ollama", "Ollama", false, false),
            svc("litellm", "LiteLLM", false, true),
        ]);
        assert_eq!((online, total), (1, 2));
        assert!(summary.contains("offline: Ollama"), "{summary}");
    }
}

#[cfg(test)]
mod token_tests {
    use super::{passes_as_hud_token, pick_backend_token, pick_token, TokenSource};

    fn s(v: &str) -> Option<String> {
        Some(v.to_string())
    }

    /// What `backend_token` hands back: the backend's own token and where
    /// it was found.
    fn file(v: &str) -> Option<(String, TokenSource)> {
        Some((v.to_string(), TokenSource::BackendFile))
    }
    fn backend_cm(v: &str) -> Option<(String, TokenSource)> {
        Some((v.to_string(), TokenSource::BackendCredentialManager))
    }

    /// The lockout: "Clear token" saved "", and "" was taken as the token.
    #[test]
    fn an_empty_saved_token_falls_through_to_the_backend_file() {
        let got = pick_token(s(""), None, None, || file("from-file"));
        assert_eq!(
            got,
            Some(("from-file".to_string(), TokenSource::BackendFile))
        );
        let got = pick_token(s("   "), s(""), None, || file("from-file"));
        assert_eq!(
            got,
            Some(("from-file".to_string(), TokenSource::BackendFile))
        );
    }

    #[test]
    fn an_empty_saved_token_falls_through_to_the_environment() {
        let got = pick_token(s(""), None, s("from-env"), || panic!("not reached"));
        assert_eq!(
            got,
            Some(("from-env".to_string(), TokenSource::Environment))
        );
    }

    #[test]
    fn a_typed_token_wins_and_credential_manager_is_where_it_normally_lives() {
        let got = pick_token(None, s("typed"), s("env"), || file("file"));
        assert_eq!(
            got,
            Some(("typed".to_string(), TokenSource::CredentialManager))
        );
    }

    /// The backend's own token is reported by where it was found, so
    /// Settings can say "kept in Credential Manager" or "still a plain file".
    #[test]
    fn the_backends_own_token_keeps_its_source() {
        let got = pick_token(None, None, None, || backend_cm("made-by-backend"));
        assert_eq!(
            got,
            Some((
                "made-by-backend".to_string(),
                TokenSource::BackendCredentialManager
            ))
        );
        assert_eq!(
            TokenSource::BackendCredentialManager.as_str(),
            "backend-credential-manager"
        );
    }

    /// The settings-file copy exists only when an older version left it and
    /// Credential Manager refused the move, so it is what was typed last.
    #[test]
    fn a_settings_file_copy_beats_an_older_credential_manager_one() {
        let got = pick_token(s("newer"), s("older"), None, || None);
        assert_eq!(got, Some(("newer".to_string(), TokenSource::SettingsFile)));
    }

    #[test]
    fn nothing_anywhere_is_none_not_an_empty_token() {
        assert_eq!(pick_token(s(""), s(""), s(""), || file("")), None);
        assert_eq!(pick_token(s(""), s(""), s(""), || backend_cm("  ")), None);
        assert_eq!(pick_token(None, None, None, || None), None);
    }

    #[test]
    fn values_are_trimmed() {
        let got = pick_token(None, None, None, || file("  tok\n"));
        assert_eq!(got.map(|(t, _)| t), s("tok"));
    }

    /// CONN-3: the backend's own order (jarvis_token_store.resolve) - the
    /// old file wins, because it exists only when an older backend wrote it
    /// after the move into Credential Manager.
    #[test]
    fn the_backends_old_file_beats_its_credential_manager_copy() {
        let got = pick_backend_token(s("from-file"), || s("from-cm"));
        assert_eq!(
            got,
            Some(("from-file".to_string(), TokenSource::BackendFile))
        );
    }

    #[test]
    fn with_no_old_file_the_backends_credential_manager_copy_is_used() {
        for none in [None, s(""), s("  \n")] {
            let got = pick_backend_token(none, || s(" from-cm "));
            assert_eq!(
                got,
                Some(("from-cm".to_string(), TokenSource::BackendCredentialManager))
            );
        }
        assert_eq!(pick_backend_token(None, || None), None);
        assert_eq!(pick_backend_token(s(""), || s("")), None);
    }

    #[test]
    fn credential_manager_is_not_even_read_when_the_old_file_has_a_token() {
        let got = pick_backend_token(s("from-file"), || panic!("not reached"));
        assert_eq!(got.map(|(t, _)| t), s("from-file"));
    }

    /// CONN-7: the order set_api_settings writes in. A model of the two
    /// places a typed token can be - the settings file on disk and
    /// Credential Manager - and of the next start's migration, which moves a
    /// plain copy it finds on disk into Credential Manager.
    mod write_order {
        use super::super::save_file_then_token;
        use std::cell::RefCell;

        #[derive(Clone, Debug, PartialEq)]
        struct World {
            /// The plain `token` key in the settings file ON DISK.
            file: Option<&'static str>,
            credential_manager: Option<&'static str>,
        }

        /// migrate_plain_token at the next start, as plan_migration does it.
        fn next_start(mut w: World) -> World {
            if let Some(plain) = w.file.take() {
                w.credential_manager = Some(plain);
            }
            w
        }

        /// set_api_settings(token = new) against `w`, with the file save and
        /// the Credential Manager write each allowed to fail.
        fn set_token(
            w: World,
            new: &'static str,
            save_ok: bool,
            cm_ok: bool,
        ) -> (World, Result<(), String>, Vec<&'static str>) {
            let disk = RefCell::new(w.file);
            let cm = RefCell::new(w.credential_manager);
            let calls = RefCell::new(Vec::new());
            let before = w.file;
            let result = save_file_then_token(
                || {
                    calls.borrow_mut().push("save file");
                    if save_ok {
                        *disk.borrow_mut() = None; // saved without the token
                        Ok(())
                    } else {
                        Err("disk full".to_string())
                    }
                },
                || {
                    calls.borrow_mut().push("credential manager");
                    if cm_ok {
                        *cm.borrow_mut() = Some(new);
                        Ok(())
                    } else {
                        Err("refused".to_string())
                    }
                },
                || {
                    calls.borrow_mut().push("roll back file");
                    *disk.borrow_mut() = before;
                },
                || calls.borrow_mut().push("restore memory"),
            );
            let world = World {
                file: disk.into_inner(),
                credential_manager: cm.into_inner(),
            };
            (world, result, calls.into_inner())
        }

        /// The bug: an old plain copy on disk, the new token saved to
        /// Credential Manager, then the file save fails - and the next
        /// start put the OLD token back. Now the file goes first, so a
        /// failed save leaves Credential Manager untouched.
        #[test]
        fn a_failed_file_save_never_lets_the_old_token_come_back() {
            let start = World {
                file: Some("old"),
                credential_manager: Some("old"),
            };
            let (w, result, calls) = set_token(start.clone(), "new", false, true);
            assert!(result.unwrap_err().contains("Nothing was changed"));
            assert_eq!(calls, ["save file", "restore memory"]);
            assert_eq!(w, start, "Credential Manager was written before the file");
            // Either way round, what the app reads after a restart is one
            // consistent token, never a new one overwritten by an old one.
            assert_eq!(next_start(w).credential_manager, Some("old"));
        }

        #[test]
        fn a_refused_token_rolls_the_file_back() {
            let start = World {
                file: Some("old"),
                credential_manager: None,
            };
            let (w, result, calls) = set_token(start.clone(), "new", true, false);
            assert!(result.unwrap_err().contains("refused"));
            assert_eq!(calls, ["save file", "credential manager", "roll back file"]);
            assert_eq!(w, start, "a refused token left a half-saved change behind");
        }

        #[test]
        fn a_saved_token_survives_the_next_start() {
            let start = World {
                file: Some("old"),
                credential_manager: Some("old"),
            };
            let (w, result, calls) = set_token(start, "new", true, true);
            assert!(result.is_ok());
            assert_eq!(calls, ["save file", "credential manager"]);
            assert_eq!(w.file, None, "the plain copy is still on disk");
            assert_eq!(next_start(w).credential_manager, Some("new"));
        }
    }

    /// CONN-3: only a token set on purpose is handed to a backend this app
    /// starts. The backend's own token, read back, never is.
    #[test]
    fn only_a_deliberately_set_token_is_passed_as_hud_token() {
        assert!(passes_as_hud_token(TokenSource::CredentialManager));
        assert!(passes_as_hud_token(TokenSource::SettingsFile));
        assert!(passes_as_hud_token(TokenSource::Environment));
        assert!(!passes_as_hud_token(TokenSource::BackendCredentialManager));
        assert!(!passes_as_hud_token(TokenSource::BackendFile));
    }
}

#[cfg(test)]
mod theme_tests {
    use super::{effective_theme, normalise_theme, THEMES};

    /// The phone dropped Ember and sends anyone who had it to Reactor; so
    /// does the desktop. An unknown or missing value lands there too.
    #[test]
    fn ember_and_unknown_themes_land_on_reactor() {
        assert!(!THEMES.contains(&"ember"));
        assert_eq!(normalise_theme(Some("ember")), "deep-space");
        assert_eq!(normalise_theme(Some("nonsense")), "deep-space");
        assert_eq!(normalise_theme(None), "deep-space");
        assert_eq!(normalise_theme(Some("paper")), "paper");
        assert_eq!(normalise_theme(Some("high-contrast")), "high-contrast");
    }

    /// Light Windows is Daylight, dark Windows is the remembered dark theme,
    /// and an unreadable Windows mode keeps the theme picked by hand.
    #[test]
    fn following_the_system_picks_daylight_or_the_dark_theme() {
        assert_eq!(
            effective_theme("high-contrast", true, "high-contrast", Some(true)),
            "paper"
        );
        assert_eq!(
            effective_theme("paper", true, "high-contrast", Some(false)),
            "high-contrast"
        );
        assert_eq!(
            effective_theme("high-contrast", true, "deep-space", None),
            "high-contrast"
        );
        assert_eq!(
            effective_theme("deep-space", false, "deep-space", Some(true)),
            "deep-space"
        );
    }
}

#[cfg(test)]
mod turn_tests {
    use super::turn_id_from_route;

    /// Only a real 32-character lower-case hex id gets through; a backend
    /// without feedback.patch sends none and the page shows no mark.
    #[test]
    fn a_turn_id_is_read_only_when_it_is_a_real_one() {
        let good = "0123456789abcdef0123456789abcdef";
        assert_eq!(
            turn_id_from_route(&format!(r#"{{"lane":"qwen3:8b","turn_id":"{good}"}}"#)).as_deref(),
            Some(good)
        );
        assert_eq!(turn_id_from_route(r#"{"lane":"qwen3:8b"}"#), None);
        assert_eq!(turn_id_from_route(r#"{"turn_id":"not-hex"}"#), None);
        assert_eq!(turn_id_from_route(r#"{"turn_id":["a","b"]}"#), None);
        assert_eq!(turn_id_from_route("not json"), None);
    }

    /// The fixture `backend/test_chat_stream_contract.py` writes by RUNNING
    /// the producer: X-Jarvis-Route built from the real router's decision
    /// plus the fields the patches add, and bodies from the real relay.
    const CASES: &str = include_str!("../../tests/fixtures/chat-stream-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("chat-stream-cases.json is JSON")
    }

    /// The route line carries lane, where and gate - and never the reason
    /// text or the memory ids. An older backend has no `where`; the page
    /// then reads the gate (only "escalate" is a cloud lane).
    #[test]
    fn the_route_line_is_built_from_the_real_header() {
        let doc = cases();
        let routes = doc["route_headers"].as_array().expect("route_headers");
        assert!(!routes.is_empty());
        for case in routes {
            let header = case["header"].as_str().unwrap();
            let expect = &case["expect"];
            let line = super::route_line_from_header(header).expect("a route line");
            let got: serde_json::Value = serde_json::from_str(&line).unwrap();
            assert_eq!(got["lane"], expect["lane"], "{}", case["name"]);
            let where_ = got["where"].as_str().unwrap_or_else(|| {
                if got["gate"] == "escalate" {
                    "cloud"
                } else {
                    "local"
                }
            });
            assert_eq!(
                where_,
                expect["where"].as_str().unwrap(),
                "{}",
                case["name"]
            );
            assert!(got.get("reason").is_none() && got.get("injected_ids").is_none());
            assert_eq!(
                turn_id_from_route(header).as_deref(),
                expect["turn_id"].as_str(),
                "{}",
                case["name"]
            );
        }
    }

    /// A turn the second graphics card answered. `chat-stream-cases.json` has
    /// no such header yet (its producer, test_chat_stream_contract.py, does
    /// not build one), so this starts from its REAL local header and makes
    /// exactly the two changes second-card.patch makes to `route_header`:
    /// `lane` becomes the model really answering and `second_card` the
    /// feature (`route_header["lane"] = _lane2.model`,
    /// `route_header["second_card"] = _lane2.feature`); `where` stays.
    #[test]
    fn the_route_line_carries_second_card_when_the_second_card_answered() {
        let doc = cases();
        let local = doc["route_headers"]
            .as_array()
            .unwrap()
            .iter()
            .find(|c| c["expect"]["where"] == "local")
            .expect("a local header");
        let mut header: serde_json::Value =
            serde_json::from_str(local["header"].as_str().unwrap()).unwrap();
        assert!(
            header.get("second_card").is_none(),
            "an ordinary turn has no second_card"
        );
        let plain = super::route_line_from_header(&header.to_string()).unwrap();
        assert!(!plain.contains("second_card"));
        for (model, feature) in [("qwen3:14b", "long_context"), ("qwen2.5vl:7b", "vision")] {
            header["lane"] = serde_json::json!(model);
            header["second_card"] = serde_json::json!(feature);
            let line = super::route_line_from_header(&header.to_string()).unwrap();
            let got: serde_json::Value = serde_json::from_str(&line).unwrap();
            assert_eq!(got["lane"], model);
            assert_eq!(got["where"], "local");
            assert_eq!(got["second_card"], feature);
            assert!(got.get("reason").is_none() && got.get("injected_ids").is_none());
        }
        // Not a string: not passed on.
        header["second_card"] = serde_json::json!(true);
        let line = super::route_line_from_header(&header.to_string()).unwrap();
        assert!(!line.contains("second_card"));
    }

    /// A failed /api/chat shows the server's sentence, not its JSON.
    #[test]
    fn a_failed_turn_shows_the_servers_sentence() {
        use super::error_text_from_body;
        assert_eq!(
            error_text_from_body(
                r#"{"error": "The local model is not running.", "route": {"lane": "x"}}"#
            )
            .as_deref(),
            Some("The local model is not running.")
        );
        assert_eq!(
            error_text_from_body(
                r#"{"error": {"message": "model not found", "type": "not_found_error"}}"#
            )
            .as_deref(),
            Some("model not found")
        );
        assert_eq!(error_text_from_body("<html>502</html>"), None);
        assert_eq!(error_text_from_body(r#"{"error": ""}"#), None);
    }
}
