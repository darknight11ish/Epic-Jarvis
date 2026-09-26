//! Jarvis Desktop — application orchestrator.
//!
//! `main.rs` is a two-line shim over [`run`]. This module owns everything that
//! defines the running application:
//!
//! * plugin registration — global shortcut, clipboard manager, notifications;
//! * the global hotkeys (`Alt+Space`, `Win+Shift+J`, `Alt+Shift+S`,
//!   `Alt+Shift+N`, `Alt+Shift+W`, and "Stop everything" on `Alt+Shift+X`;
//!   all rebindable, [`hotkeys`]);
//! * the notification-area tray icon ([`tray::create_tray`]);
//! * window vibrancy and focus-loss auto-hide ([`windows::setup_windows`]).
//!
//! The two windows are declared in `tauri.conf.json`:
//!
//! | label      | role                                                        |
//! |------------|-------------------------------------------------------------|
//! | `quickbar` | 750×80 frameless transparent spotlight bar, always on top    |
//! | `hud`      | 1280×820 frameless HUD pointed at the local Jarvis server    |

pub mod aec;
pub mod appearance;
pub mod asks_first;
pub mod attention;
pub mod autostart;
pub mod brain;
pub mod commands;
pub mod email_sending;
pub mod hardware;
pub mod hotkeys;
pub mod hud_proxy;
pub mod lock;
pub mod logfile;
pub mod plain_errors;
pub mod proctree;
pub mod reach;
pub mod sidecar;
pub mod spec;
pub mod spec_drift;
pub mod sse;
pub mod stream;
pub mod system_theme;
pub mod token_store;
pub mod tray;
pub mod update;
pub mod vision;
pub mod voice;
pub mod voice_flow;
pub mod voice_training;
pub mod web_search;
pub mod windows;
#[cfg(windows)]
pub mod winrt_toast;

use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::Notify;

/// Label of the spotlight quickbar window.
pub const QUICKBAR_LABEL: &str = "quickbar";
/// Label of the full HUD window.
pub const HUD_LABEL: &str = "hud";
/// Label of the always-on-desktop widget.
pub const WIDGET_LABEL: &str = windows::WIDGET_LABEL;

/// How often the widget's telemetry is sampled and broadcast. Three seconds is
/// slow enough that the `nvidia-smi` spawn costs nothing in practice, and fast
/// enough that a thermal spike is visible while it still matters.
const TELEMETRY_INTERVAL: std::time::Duration = std::time::Duration::from_secs(3);

/// Default Jarvis orchestrator base. One value, defined in [`commands`], so a
/// port change cannot be half-applied — and configuration overrides it at
/// runtime via [`commands::jarvis_base`]. `JARVIS_HUD_PORT` defaults to 4719
/// in `jarvis_hud.py`; nothing here assumes any other number.
pub const JARVIS_SERVER_URL: &str = commands::DEFAULT_BASE;
/// Local Ollama daemon.
pub const OLLAMA_URL: &str = "http://127.0.0.1:11434";
/// Local LiteLLM proxy.
pub const LITELLM_URL: &str = "http://127.0.0.1:4000";

/// Event names shared with the frontend. Keeping them in one place stops the
/// Rust and JavaScript sides from drifting apart.
pub mod events {
    /// Payload: none. The quickbar should select and focus its input.
    pub const FOCUS_INPUT: &str = "focus-input";
    /// Payload: `String` — clipboard text to pre-load into the quickbar.
    pub const CLIPBOARD_INJECT: &str = "clipboard-inject";
    /// Payload: [`crate::commands::CapturePayload`] — a JPEG data URI.
    pub const SCREEN_CAPTURED: &str = "screen-captured";
    /// Payload: `String` — a human readable failure message.
    pub const CAPTURE_FAILED: &str = "capture-failed";
    /// Payload: [`crate::commands::HealthReport`].
    pub const HEALTH_REPORT: &str = "health-report";
    /// Payload: `bool` — whether the quickbar is pinned open.
    pub const PIN_CHANGED: &str = "pin-changed";
    /// Payload: `&str` — the note target to pre-arm, `"logseq"` or `"joplin"`.
    pub const QUICK_NOTE_SUMMON: &str = "quick-note-summon";
    /// Payload: [`crate::commands::DesktopTelemetry`].
    pub const DESKTOP_TELEMETRY: &str = "desktop-telemetry";
    /// Payload: `{ id, approved }`.
    pub const APPROVAL_RESOLVED: &str = "approval-resolved";
    /// Payload: `String` — the theme id. Sent to every window so four
    /// surfaces on screen together never disagree about which palette is in
    /// force.
    pub const THEME_CHANGED: &str = "theme-changed";
    /// Payload: the id of the card to show, or null for the first one
    /// waiting ("Open the card", `open_approval_in_quickbar`). Show the
    /// approval gate. The queue lives in the quickbar, which is the surface
    /// that renders the risk line and the `raised` block.
    pub const SHOW_APPROVAL: &str = "show-approval";
    /// Payload: none. Open the daily brief. Sent by the tray's waiting row and
    /// by the widget — the panel itself lives in the quickbar, because the HUD
    /// window is the backend's own page and not ours to add sections to.
    pub const SHOW_DIGEST: &str = "show-digest";
    /// Payload: [`crate::update::Status`] — the result of an update check.
    /// Carries no action: nothing that receives this may install anything.
    pub const UPDATE_STATUS: &str = "update-status";
    /// Payload: [`crate::update::DownloadProgress`] — bytes downloaded so far
    /// while an install already pressed is in flight. Informational only,
    /// same as `UPDATE_STATUS`: nothing here starts or resumes anything.
    pub const UPDATE_PROGRESS: &str = "update-progress";
    /// Payload: none. The appearance document (which face, which state
    /// bindings) changed — the tray already repaints on this via
    /// `on_appearance_changed`; sent to every window too so a display-mode
    /// Faces surface (the Widget's live face) can re-fetch and switch face
    /// or colours without waiting for its own next reload.
    pub const APPEARANCE_CHANGED: &str = "appearance-changed";
    /// Payload: [`crate::spec_drift::DriftReport`] — the result of the
    /// one startup comparison between this build's bundled
    /// `jarvis-visual-spec.json` and the server's own copy. Carries no
    /// action, same as `UPDATE_STATUS`: nothing here edits either spec.
    pub const VISUAL_SPEC_DRIFT: &str = "visual-spec-drift";
    /// Payload: [`crate::voice::HeardReply`] - one utterance automatic
    /// listening cut and sent on its own, with no command call waiting on
    /// it the way `stop_voice_capture` returns push-to-talk's result
    /// directly. Sent only for a genuinely finished utterance; a failed
    /// send (server unreachable, no engine) is logged, not emitted here.
    pub const VOICE_HEARD: &str = "voice-heard";
    /// Payload: none. Automatic listening's VAD just crossed from silence
    /// into speech - the frontend's barge-in hook: if a spoken reply is
    /// still playing, this is the moment to stop it, before the finished
    /// utterance (`VOICE_HEARD`, above) is anywhere close to ready.
    pub const VOICE_SPEECH_STARTED: &str = "voice-speech-started";
    /// Payload: none. Sent to the quickbar only, by
    /// [`crate::voice::summon_push_to_talk`] (the HUD's mic button): put
    /// focus on the mic and say how to talk. Starts no recording.
    pub const VOICE_SUMMON: &str = "voice-summon";
    /// Payload: [`crate::voice::ListenInfo`]. "Hey Jarvis" listening changed
    /// how it hears while still on: the echo-cancelled microphone stopped
    /// and it carries on through the ordinary one (`note` says so).
    pub const VOICE_LISTENING: &str = "voice-listening";
    /// Payload: [`crate::voice_flow::BargeOnset`]. "Hey Jarvis" listening
    /// heard half a second of speech in one utterance: if a reply is
    /// playing, the Jarvis bar may pause it and ask for the utterance to be
    /// checked (`judge_barge_in`). See voice_flow.rs.
    pub const VOICE_BARGE_ONSET: &str = "voice-barge-onset";
    /// Payload: [`crate::voice_flow::BargeVerdict`]. The PC's answer for an
    /// utterance the Jarvis bar asked about: stop the reply, or carry on.
    pub const VOICE_BARGE_VERDICT: &str = "voice-barge-verdict";
    /// Payload: [`crate::lock::Security`] - the Security settings changed
    /// (Settings' Windows Hello section). The Brain re-reads its memory
    /// lists, which may now be hidden or shown.
    pub const SECURITY_CHANGED: &str = "security-changed";
    /// Payload: none. Sent to the Brain only: the owner was away longer than
    /// "Lock again after", so a Show on the private lists has ended and they
    /// are read again, hidden.
    pub const PRIVATE_HIDDEN: &str = "private-hidden";
    /// Payload: `{ uri }` - a `data:audio/wav` URI. Sent to the quickbar
    /// only, by [`crate::brain::focus::play_callout`]: one focus-session
    /// line ("YouTube can wait."), fetched as SOUND from this PC's backend,
    /// to play. The words never reach any window.
    pub const FOCUS_CALLOUT: &str = "focus-callout";

    // ---- the fanned-out event stream -----------------------------------
    //
    // Rust holds one `GET /api/events` open and re-emits every frame on these
    // three names. No surface opens a stream of its own, and none of them
    // polls: one stream, one source of truth, three consumers.

    /// Payload: `{ kind, id, data }` — one frame off the server's event bus,
    /// verbatim. `kind` is `hello`, `approval`, `finding`, `power`, `persona`,
    /// `model`, `voice`, `activity`, `attention` or `job`. (JARVIS-API §3 lists
    /// only the first seven; `activity`, `attention` and `job` are all
    /// published by the backend and documented elsewhere in §4.)
    pub const JARVIS_EVENT: &str = "jarvis-event";
    /// Payload: [`crate::stream::LinkState`] — whether the stream is up, what
    /// Jarvis is doing, and how many approvals are waiting.
    pub const JARVIS_LINK: &str = "jarvis-link";
    /// Payload: `{ count, items }` — the approval queue, re-read once by the
    /// backend after the doorbell rang, not once per window.
    pub const APPROVALS_CHANGED: &str = "approvals-changed";
    /// Payload: none. `hello.stale` said the resume point fell off the back of
    /// the server's 512-event ring: everything on screen is suspect and must be
    /// re-read rather than patched up.
    pub const JARVIS_RESYNC: &str = "jarvis-resync";
    /// Payload: none. "Stop everything" (the hotkey): every window that
    /// speaks stops its speech now, before the backend is even asked. See
    /// [`crate::commands::stop_everything_now`].
    pub const STOP_EVERYTHING: &str = "stop-everything";
}

/// Cancellation handle for the one chat stream the spotlight may have running.
///
/// [`Notify::notify_one`] leaves a permit behind when nobody is waiting yet, so
/// a cancel that lands between `begin` and the `select!` still wins the race —
/// which a bare `notify_waiters` would lose.
#[derive(Default)]
pub struct ChatState {
    cancel: Mutex<Option<Arc<Notify>>>,
}

impl ChatState {
    /// Starts a stream, cancelling whatever was already running. The returned
    /// handle is what the new stream selects against.
    pub fn begin(&self) -> Arc<Notify> {
        let token = Arc::new(Notify::new());
        let mut slot = self
            .cancel
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(previous) = slot.replace(token.clone()) {
            previous.notify_one();
        }
        token
    }

    /// Cancels the stream in flight, if any.
    pub fn cancel(&self) {
        if let Some(token) = self
            .cancel
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .take()
        {
            token.notify_one();
        }
    }

    /// Clears the slot, but only if it still holds this stream's handle — a
    /// newer stream must not have its cancellation forgotten.
    pub fn finish(&self, token: &Arc<Notify>) {
        let mut slot = self
            .cancel
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if slot
            .as_ref()
            .is_some_and(|current| Arc::ptr_eq(current, token))
        {
            *slot = None;
        }
    }
}

/// Emits an event to the quickbar window only.
pub fn emit_quickbar<S: serde::Serialize + Clone>(app: &AppHandle, event: &str, payload: S) {
    if let Err(err) = app.emit_to(QUICKBAR_LABEL, event, payload) {
        eprintln!("[jarvis] unable to emit `{event}` to the quickbar: {err}");
    }
}

/// Emits an event to every window.
///
/// Which windows HEAR it is decided by their capabilities, not here: in
/// Tauri 2.11 a page's global `listen()` registers with the target `Any`,
/// and `match_any_or_filter` (tauri `event/listener.rs`) lets an `Any`
/// listener through every filter - so even `emit_to` one window reaches a
/// global listener in any other. The Faces and first-run windows, which
/// must not hear the approval queue, hold no `core:event:allow-listen`
/// (bug audit 2026-09-26, #6; `tests/security.mjs`).
pub fn emit_all<S: serde::Serialize + Clone>(app: &AppHandle, event: &str, payload: S) {
    if let Err(err) = app.emit(event, payload) {
        eprintln!("[jarvis] unable to broadcast `{event}`: {err}");
    }
}

/// Pushes a value into the HUD page by evaluating a call to its feed.
///
/// Why a feed and not a Tauri event: this comment used to say `listen` and
/// `invoke` are both refused inside the HUD, because `jarvis_hud.html`'s own
/// Content-Security-Policy does not list `http://ipc.localhost`. That was
/// wrong (apps security audit M2): when that fetch is refused, Tauri's
/// `ipc-protocol.js` falls back to `window.ipc.postMessage`, which no CSP
/// governs, so IPC works from the HUD - it is how the mic button's
/// `summon_push_to_talk` and the page's reads (`hud_proxy.rs`) reach Rust.
/// What limits the HUD is its capability file, `capabilities/hud.json`.
/// The feed stays because it was here first and delivers the shell's one
/// event stream to the page's `EventSource` shim without a second listener.
///
/// `serde_json` is what makes it safe: the payload is a JSON literal, escaped
/// by the serialiser, spliced into a call to a function the initialisation
/// script defined. Nothing here is concatenated by hand.
pub fn push_to_hud<S: serde::Serialize>(app: &AppHandle, channel: &str, payload: &S) {
    let Some(hud) = app.get_webview_window(HUD_LABEL) else {
        return;
    };
    let (Ok(channel), Ok(payload)) = (
        serde_json::to_string(channel),
        serde_json::to_string(payload),
    ) else {
        return;
    };
    let script =
        format!("if (window.__jarvisFeed) {{ window.__jarvisFeed({channel}, {payload}); }}");
    if let Err(err) = hud.eval(&script) {
        eprintln!("[jarvis] unable to push `{channel}` to the HUD: {err}");
    }
}

/// Gives the HUD page the current base, if it holds a different one - and
/// never a token.
///
/// The page used to be given the pairing token here and in the bootstrap,
/// so any script running in it could call the whole API (apps security
/// audit M2). Now its requests go through `hud_proxy.rs`, which adds the
/// token in Rust, and the page is configured with an EMPTY token, on every
/// page load and every link change, so a token some earlier version or a
/// browser session left in the page is wiped too. The base is still set:
/// the page builds its URLs from it, and the bootstrap's `fetch` shim reads
/// the path back out of them.
pub fn configure_hud(app: &AppHandle) {
    let Some(hud) = app.get_webview_window(HUD_LABEL) else {
        return;
    };
    let base = commands::jarvis_base(app);
    let Ok(base) = serde_json::to_string(&base) else {
        return;
    };
    // `typeof` guards the reference rather than `window.JARVIS`, because a
    // top-level `const` is a global *lexical* binding and never a property of
    // `window`.
    let script = format!(
        "if (typeof JARVIS !== 'undefined' && JARVIS && typeof JARVIS.set === 'function' \
         && (JARVIS.base !== {base} || JARVIS.token !== '')) {{ \
         if (typeof JARVIS.forget === 'function') JARVIS.forget(); \
         JARVIS.set({base}, '', false); }}"
    );
    if let Err(err) = hud.eval(&script) {
        eprintln!("[jarvis] unable to configure the HUD page: {err}");
    }
}

// ---------------------------------------------------------------------------
// Global hotkeys
// ---------------------------------------------------------------------------

// The accelerators live in `hotkeys.rs` now, as data rather than as five
// struct fields: they are configurable, so the set has to be iterable and
// each one has to carry its own label and default for the Settings window to
// render. `Hotkeys::new()` was here, and it hard-coded them.

/// Reads the clipboard and hands its text to the quickbar.
#[cfg(desktop)]
fn ingest_clipboard(app: &AppHandle) {
    use tauri_plugin_clipboard_manager::ClipboardExt;

    match app.clipboard().read_text() {
        Ok(text) if !text.trim().is_empty() => {
            // Guard against someone copying a whole file into the bar.
            const MAX_CHARS: usize = 8_000;
            let payload: String = if text.chars().count() > MAX_CHARS {
                text.chars().take(MAX_CHARS).collect::<String>() + "\n…[truncated]"
            } else {
                text
            };
            if let Err(err) = windows::show_quickbar(app) {
                eprintln!("[jarvis] unable to show the quickbar: {err}");
            }
            emit_quickbar(app, events::CLIPBOARD_INJECT, payload);
        }
        Ok(_) => {
            commands::notify(app, "Jarvis", "The clipboard holds no text to ingest.");
        }
        Err(err) => {
            commands::notify(app, "Jarvis", &format!("Clipboard unavailable: {err}"));
        }
    }
}

/// Captures the primary display off the UI thread and streams the result to the
/// quickbar. Encoding a 4K frame to JPEG takes tens of milliseconds — long
/// enough that doing it inline would visibly stall the hotkey.
#[cfg(desktop)]
fn capture_desktop(app: &AppHandle) {
    let handle = app.clone();
    std::thread::spawn(move || match commands::capture_primary_display() {
        Ok(payload) => {
            if let Err(err) = windows::show_quickbar(&handle) {
                eprintln!("[jarvis] unable to show the quickbar: {err}");
            }
            emit_quickbar(&handle, events::SCREEN_CAPTURED, payload);
        }
        Err(err) => {
            eprintln!("[jarvis] desktop capture failed: {err}");
            emit_quickbar(&handle, events::CAPTURE_FAILED, err.clone());
            commands::notify(&handle, "Jarvis", &format!("Capture failed: {err}"));
        }
    });
}

/// The route lane last seen on a stream, mirrored into the widget's pill.
#[derive(Default)]
pub struct RouteState {
    pub lane: Mutex<Option<String>>,
}

/// Samples the machine every [`TELEMETRY_INTERVAL`] and pushes the result to the
/// widget, then flushes any geometry the user changed by dragging.
///
/// Sampling is skipped while the widget is hidden: nobody is reading the
/// numbers, and the GPU probe is a process spawn.
fn spawn_telemetry_loop(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let mut system = sysinfo::System::new_all();

        loop {
            tokio::time::sleep(TELEMETRY_INTERVAL).await;

            // A drag is persisted even while the widget is collapsed or hidden.
            // `flush` writes a file, so it goes to the blocking pool too.
            {
                let handle = app.clone();
                if let Err(err) = tokio::task::spawn_blocking(move || {
                    handle.state::<windows::WidgetState>().flush(&handle);
                })
                .await
                {
                    eprintln!("[jarvis] widget preference flush failed: {err}");
                }
            }

            if !windows::widget_is_visible(&app) {
                continue;
            }

            let lane = app
                .state::<RouteState>()
                .lane
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .clone();

            // `sample_telemetry` spawns `nvidia-smi` and blocks on it, which on
            // a busy GPU is routinely hundreds of milliseconds and sometimes
            // seconds. Doing that on a tokio worker every three seconds steals
            // capacity from the SSE loop and every async command, so it goes to
            // the blocking pool. `System` moves in and back out again because
            // it is not `Sync`.
            let sampled = tokio::task::spawn_blocking(move || {
                let value = commands::sample_telemetry(&mut system, lane);
                (system, value)
            })
            .await;
            let sample = match sampled {
                Ok((returned, sample)) => {
                    system = returned;
                    sample
                }
                Err(err) => {
                    // The blocking task panicked or was cancelled; `system`
                    // went with it, so start a fresh one for the next tick.
                    eprintln!("[jarvis] telemetry sampling failed: {err}");
                    system = sysinfo::System::new_all();
                    continue;
                }
            };
            if let Err(err) = app.emit_to(WIDGET_LABEL, events::DESKTOP_TELEMETRY, sample) {
                eprintln!("[jarvis] unable to push telemetry: {err}");
            }
        }
    });
}

/// Default note target for the quick-capture hotkey.
///
/// Logseq is the dev/agent journal and the one a keystroke-speed capture almost
/// always means; the Joplin vault is reached by typing `#joplin` instead.
pub const DEFAULT_NOTE_TARGET: &str = "logseq";

/// Summons the bar pre-armed for a note. The frontend fills in the prefix.
#[cfg(desktop)]
fn summon_quick_note(app: &AppHandle) {
    if let Err(err) = windows::show_quickbar(app) {
        eprintln!("[jarvis] unable to show the quickbar: {err}");
        return;
    }
    emit_quickbar(app, events::QUICK_NOTE_SUMMON, DEFAULT_NOTE_TARGET);
}

/// The bootstrap injected into the HUD webview before any of its own scripts.
/// See the file itself for what it does and why it has to run this early.
const HUD_BOOTSTRAP: &str = include_str!("hud_bootstrap.js");

/// Creates the HUD window with its initialisation script.
///
/// Everything here mirrors what `tauri.conf.json` used to declare for the `hud`
/// label; the window moved into Rust only so it could carry the script, and the
/// capability file still addresses it by the same label.
/// Whether THIS process was started by a Deny click on a Windows toast.
///
/// Read from this process's own argv, the same string
/// `winrt_toast::deny_id_from_argv` looks for. Used only to decide whether a
/// window belongs on screen; the decision itself is sent by
/// `winrt_toast::decide_denied_at_startup`, which reads the same argv again
/// rather than sharing state with this - two cheap reads of a fixed string
/// are simpler than threading a flag through `setup`.
#[cfg(windows)]
fn launched_by_deny() -> bool {
    let argv: Vec<String> = std::env::args().collect();
    // A Snooze on a timer's or reminder's toast (2026-09-25) is the same kind
    // of launch: it answers from the toast and puts no window up.
    winrt_toast::deny_id_from_argv(&argv).is_some()
        || winrt_toast::snooze_id_from_argv(&argv).is_some()
}

/// Always false off Windows: no toast, no Deny action, no such launch.
#[cfg(not(windows))]
fn launched_by_deny() -> bool {
    false
}

fn build_hud_window(app: &AppHandle) -> Result<(), String> {
    // A window with this label already exists. `setup` runs once, so in normal
    // operation this cannot happen — but Tauri creates every window declared in
    // `tauri.conf.json` *before* `setup` runs, so re-adding a `hud` entry there
    // would silently win this race and the bootstrap below would never inject:
    // no API base, no token, no EventSource shim, and the page left to open its
    // own stream with the token in the URL.
    //
    // That is exactly what used to happen, because a stale generated copy of
    // the config declared one. The config now lives in one tracked place, and
    // this says so out loud rather than returning quietly if it ever recurs.
    if app.get_webview_window(HUD_LABEL).is_some() {
        let message = format!(
            "a window labelled `{HUD_LABEL}` already exists, so the HUD bootstrap \
             was not injected. Remove the `{HUD_LABEL}` entry from tauri.conf.json \
             — this window is built in Rust because it needs an initialisation script."
        );
        eprintln!("[jarvis] {message}");
        commands::notify(app, "Jarvis — HUD misconfigured", &message);
        return Err(message);
    }

    let base = commands::jarvis_base(app);
    // `serde_json` is what makes this safe: the base is a value a user typed
    // into a settings field, and it is spliced into JavaScript. Serialising
    // it as a JSON string literal is exactly the escaping that needs, quotes
    // and backslashes included. No token: the page does not get one (apps
    // security audit M2; hud_proxy.rs makes its requests).
    let script = HUD_BOOTSTRAP.replace(
        "__JARVIS_BASE__",
        &serde_json::to_string(&base).unwrap_or_else(|_| "\"\"".into()),
    );

    // Started by hand, the HUD is what you came for, so it opens focused.
    // Started by Windows at login it must not: a 1280x820 window taking focus
    // while the desktop is still painting is the single most obnoxious thing a
    // startup program can do, and it would arrive over whatever the person
    // actually opened. Hidden, not skipped - it is fully built and warm, and
    // the tray's "Show the HUD window" or the hotkey brings it up instantly.
    let at_login = autostart::launched_at_login();
    // A Deny clicked on a toast while Jarvis was closed is the OTHER launch
    // that must not put a window on screen. `docs/ARCHITECTURE.md` rule 2 is
    // "Deny may be a notification action. Approve may not... Approving means
    // opening the app" - so a Deny that opens the app has paid Approve's
    // price. Answering it at startup (winrt_toast::decide_denied_at_startup)
    // fixed the half where nothing happened at all; without this line the
    // other half stood, and the doc over there said otherwise.
    //
    // Hidden, exactly as for a login start: fully built and warm, reachable
    // from the tray or the hotkey the moment the owner does want it.
    let hidden = at_login || launched_by_deny();
    // App lock on: a restart starts locked (lock.rs), and the HUD is covered
    // (apps security audit M3), so it is built hidden and shown through the
    // lock below - Windows Hello first. Not at login or on a Deny launch,
    // where it stays hidden anyway.
    let lock_first = !hidden && lock::current(app).app_lock;

    tauri::WebviewWindowBuilder::new(
        app,
        HUD_LABEL,
        tauri::WebviewUrl::App("jarvis_hud.html".into()),
    )
    .title("Jarvis")
    .inner_size(1280.0, 820.0)
    .min_inner_size(960.0, 640.0)
    .center()
    .decorations(true)
    .transparent(false)
    .always_on_top(false)
    .skip_taskbar(false)
    .resizable(true)
    .visible(!hidden && !lock_first)
    .focused(!hidden && !lock_first)
    .shadow(true)
    .theme(Some(tauri::Theme::Dark))
    .initialization_script(&script)
    .build()
    .map_err(|e| format!("{e}"))?;

    if lock_first {
        if let Err(err) = windows::show_hud(app) {
            eprintln!("[jarvis] the HUD could not be shown through the lock: {err}");
        }
    }

    logfile::log(&format!(
        "[jarvis] HUD window created for {base}{}",
        if lock_first {
            " (hidden until Windows Hello: App lock is on)"
        } else if at_login {
            " (hidden: started at login)"
        } else if hidden {
            " (hidden: launched by a notification Deny, which must not open the app)"
        } else {
            ""
        }
    ));
    Ok(())
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

/// Builds and runs the Tauri application. Blocks until the process exits.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default();

    // Build order step 3. Registered before anything else so a second launch
    // is intercepted as early as possible: it raises the running window rather
    // than standing up a second app against the same backend and the same
    // SQLite approval queue.
    #[cfg(desktop)]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // A Deny click's own relaunch, not an ordinary second launch -
            // see winrt_toast.rs's own doc for why this is the argv shape a
            // toast action produces. Answered and left alone: raising the
            // window here would turn a notification-only Deny into exactly
            // the "opening the app" cost docs/ARCHITECTURE.md's rule 2
            // reserves for Approve.
            #[cfg(windows)]
            if let Some(id) = winrt_toast::deny_id_from_argv(&_argv) {
                logfile::log(&format!(
                    "[jarvis] Deny reached from a notification relaunch: {id}"
                ));
                winrt_toast::decide_denied_detached(app, id);
                return;
            }
            // A Snooze on a toast for a timer, alarm or reminder that went
            // off (brain/schedule.rs toast_fired): the same shape - answered
            // from the toast, no window.
            #[cfg(windows)]
            if let Some(id) = winrt_toast::snooze_id_from_argv(&_argv) {
                logfile::log(&format!(
                    "[jarvis] Snooze reached from a notification relaunch: {id}"
                ));
                winrt_toast::snooze_detached(app, id);
                return;
            }
            logfile::log("[jarvis] second launch folded into the running instance");
            // Through the app lock, like every other way to the HUD (apps
            // security audit M3): with it on, Windows Hello is asked first.
            if let Err(err) = windows::show_hud(app) {
                eprintln!("[jarvis] second launch: HUD unavailable: {err}");
            }
        }));
    }

    builder = builder
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        // Registering this is not optional and its absence was invisible:
        // `UpdaterExt::updater_builder` resolves `state::<UpdaterState>()`,
        // which PANICS when the type was never managed. The empty `pubkey` in
        // tauri.conf.json masks it today, because `update.rs::configured()`
        // short-circuits every path before it can be reached — so the first
        // thing that would have happened after pasting in a real signing key
        // is an abort with `panic = "abort"` and no stderr to print it to.
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(ChatState::default())
        .manage(stream::StreamState::default())
        .manage(sidecar::SupervisorState::default())
        .manage(tray::TrayHandles::default())
        .manage(tray::Painted::default())
        .manage(tray::TrayFlashGovernor::default())
        .manage(windows::WidgetState::default())
        .manage(RouteState::default())
        // Registered here with every other managed type, not inside setup: the
        // shortcut handler reads it and would panic on an unregistered state
        // if a fallible call above it ever returned early.
        .manage(hotkeys::HotkeyState::default())
        .manage(update::UpdateState::default())
        .manage(appearance::AppearanceState::default())
        .manage(system_theme::AppliedTheme::default())
        .manage(voice::VoiceCaptureState::default())
        .manage(voice::AutoListenState::default())
        // Settings' voice recordings, held in memory until sent (voice_training.rs).
        .manage(voice_training::SampleState::default())
        // Windows Hello: when the owner was last here, and whether the
        // Brain's private lists are shown (lock.rs).
        .manage(lock::LockState::default())
        // The HUD's own chat stream, apart from the Jarvis bar's (hud_proxy.rs).
        .manage(hud_proxy::HudChatState::default())
        // Every window's focus changes reach the app lock: a Jarvis bar,
        // Brain or Settings window focused again after the owner was away is
        // hidden and asks Windows Hello (lock.rs `on_window_event`).
        .on_window_event(lock::on_window_event)
        .invoke_handler(tauri::generate_handler![
            // Eight commands used to be registered here with no caller in any
            // window: capture_screen, is_quickbar_pinned, notify_user,
            // quit_app, read_clipboard, show_quickbar, toggle_hud and
            // toggle_widget. The tray and the hotkeys call the `windows::`
            // functions directly, not these wrappers. Registered IPC is
            // reachable from every page — `quit_app` in particular let any
            // script terminate the app — so unused surface is cost without
            // benefit. The command bodies remain in commands.rs for the paths
            // that will want them; they are simply not exposed until then.
            commands::stream_chat,
            commands::temporary_chat_available,
            commands::cancel_chat,
            commands::decide_approval,
            // The HUD page's requests, made in Rust so the page holds no
            // token (apps security audit M2; hud_proxy.rs).
            hud_proxy::hud_get,
            hud_proxy::hud_chat,
            hud_proxy::hud_chat_cancel,
            // App lock and the widget (apps security audit M3).
            commands::get_app_lock,
            commands::open_approval_in_quickbar,
            // The five `jarvis-link.js` has invoked since before they
            // existed. Without these lines every task-control button and the
            // approval note failed at the Tauri boundary, which reads to the
            // user as the button doing nothing.
            commands::pause_task,
            commands::resume_task,
            commands::stop_task,
            commands::inject_task_note,
            commands::amend_approval,
            commands::set_route_lane,
            stream::get_link_state,
            stream::get_pending_approvals,
            stream::refresh_link,
            attention::get_digest,
            brain::brain_read,
            brain::brain_revert_undo,
            brain::brain_cancel_job,
            brain::brain_cancel_hold,
            brain::brain_watch_add,
            brain::brain_watch_remove,
            brain::brain_watch_seen,
            brain::brain_remove_skill,
            brain::brain_memory_decide,
            brain::brain_memory_forget,
            brain::brain_memory_erase,
            brain::brain_memory_edit,
            brain::brain_memory_learning,
            brain::brain_memory_sleep_time,
            brain::brain_memory_keep_both,
            brain::brain_memory_export,
            brain::brain_memory_as_of,
            brain::auto_learn::brain_memory_learning_status,
            brain::auto_learn::brain_memory_auto_list,
            brain::auto_learn::brain_memory_learning_auto,
            brain::auto_learn::brain_memory_learning_sensitive,
            brain::auto_learn::brain_memory_saved_unseen,
            brain::profile::brain_memory_profile,
            brain::profile::brain_memory_pin,
            brain::schedule::brain_schedule,
            brain::schedule::brain_schedule_act,
            brain::schedule::brain_schedule_add_todo,
            brain::schedule::brain_schedule_add_standby,
            brain::schedule::brain_schedule_clear_list,
            brain::focus::focus_status,
            brain::focus::focus_start,
            brain::focus::focus_act,
            brain::briefing::brain_briefing,
            brain::briefing::brain_briefing_now,
            brain::briefing::get_briefing_setup,
            brain::briefing::set_briefing,
            brain::briefing::stop_briefing,
            brain::briefing::set_briefing_senders,
            brain::used::memory_used,
            brain::history::brain_history_list,
            brain::history::brain_history_open,
            brain::history::brain_history_delete,
            brain::history::brain_history_settings,
            brain::brain_model,
            attention::mark_digest_seen,
            attention::set_attention_muted,
            sidecar::supervisor_status,
            sidecar::set_supervision,
            sidecar::start_backend,
            sidecar::stop_backend,
            commands::get_theme,
            commands::set_theme,
            commands::get_theme_prefs,
            commands::set_theme_follow_system,
            commands::open_faces,
            commands::mark_answer,
            commands::finish_onboarding,
            commands::get_api_settings,
            commands::set_api_settings,
            commands::reveal_pairing_token,
            commands::get_second_card,
            commands::set_second_card,
            commands::get_backend_capabilities,
            commands::get_big_model,
            commands::set_big_model,
            hardware::get_hardware,
            hardware::apply_hardware,
            hardware::hardware_step,
            hardware::measure_hardware,
            web_search::get_web_search,
            web_search::set_web_search,
            web_search::test_web_search,
            web_search::save_search_key,
            web_search::forget_search_key,
            reach::get_reach,
            asks_first::get_asks_first,
            asks_first::set_asks_first,
            asks_first::set_lights_without_card,
            email_sending::get_email_sending,
            plain_errors::get_manner,
            plain_errors::set_manner,
            plain_errors::open_fix_place,
            appearance::get_appearance,
            appearance::set_appearance,
            appearance::appearance_snapshot,
            appearance::appearance_colours,
            update::update_status,
            update::check_for_update,
            update::set_update_check_on_start,
            update::install_update,
            update::restart_app,
            hotkeys::get_hotkeys,
            hotkeys::set_hotkeys,
            hotkeys::reset_hotkeys,
            commands::hide_widget,
            commands::resize_desktop_widget,
            commands::set_widget_always_on_top,
            commands::save_widget_position,
            commands::get_widget_prefs,
            commands::prefill_quickbar,
            commands::capture_note,
            commands::capture_note_status,
            commands::note_targets,
            commands::wiki_status,
            commands::wiki_ingest,
            commands::wiki_ingest_status,
            commands::wiki_open_folder,
            commands::get_deep,
            commands::ask_deep,
            commands::check_server_health,
            commands::hide_quickbar,
            commands::resize_quickbar,
            commands::set_quickbar_pinned,
            commands::write_clipboard,
            commands::open_external_url,
            commands::get_log_info,
            commands::open_log_folder,
            commands::get_autostart,
            commands::set_autostart,
            voice::start_voice_capture,
            voice::stop_voice_capture,
            voice::cancel_voice_capture,
            voice::start_automatic_listening,
            voice::stop_automatic_listening,
            voice::speak_reply,
            // Interrupting by talking and "One moment." (voice_flow.rs).
            voice_flow::judge_barge_in,
            voice_flow::get_voice_flow,
            voice_flow::get_voice_moment,
            voice::summon_push_to_talk,
            voice::get_voice_status,
            voice::set_wake_word,
            // Settings -> Voice: training on this PC, the voice-check settings,
            // the guided test and custom voices (voice_training.rs).
            voice_training::start_voice_sample,
            voice_training::voice_sample_level,
            voice_training::stop_voice_sample,
            voice_training::cancel_voice_sample,
            voice_training::discard_voice_samples,
            voice_training::send_voice_training,
            voice_training::cancel_voice_training,
            voice_training::measure_voice,
            voice_training::set_voice_setting,
            voice_training::check_voice_with_someone_else,
            voice_training::propose_voice_threshold,
            voice_training::get_custom_voices,
            voice_training::create_custom_voice,
            voice_training::set_active_voice,
            voice_training::delete_custom_voice,
            voice_training::set_better_voice,
            voice_training::set_voice_speed,
            vision::local_model_vision,
            // Windows Hello (lock.rs): Settings reads and changes the four
            // Security settings; the Brain's Show button.
            lock::get_security_settings,
            lock::set_security_settings,
            lock::reveal_private_answers,
        ]);

    // The global-shortcut plugin owns a single handler for every accelerator we
    // register, so the three hotkeys are dispatched by comparing the shortcut
    // that fired against the ones resolved at startup.
    #[cfg(desktop)]
    {
        use tauri_plugin_global_shortcut::ShortcutState;

        builder = builder.plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    // Key-up would otherwise fire every action twice.
                    if event.state() != ShortcutState::Pressed {
                        return;
                    }

                    // Resolved against the LIVE bindings. This used to compare
                    // the fired shortcut against five values captured at
                    // startup, which is correct exactly until someone rebinds
                    // one: after that the old combination still ran the action
                    // and the new one did nothing.
                    let Some(action) = hotkeys::action_for(app, shortcut) else {
                        return;
                    };

                    match action {
                        "toggle_quickbar" => match windows::toggle_quickbar(app) {
                            Ok(visible) => {
                                if visible {
                                    // `toggle_quickbar` has already centred and
                                    // focused the window; tell the WebView to
                                    // put the caret in the input.
                                    emit_quickbar(app, events::FOCUS_INPUT, ());
                                }
                            }
                            Err(err) => eprintln!("[jarvis] quickbar toggle failed: {err}"),
                        },
                        "ingest_clipboard" => ingest_clipboard(app),
                        "capture_screen" => capture_desktop(app),
                        "quick_note" => summon_quick_note(app),
                        "toggle_widget" => {
                            if let Err(err) = windows::toggle_widget(app) {
                                eprintln!("[jarvis] widget toggle failed: {err}");
                            }
                        }
                        // Never held: not by a stale link, not by App lock,
                        // not by a waiting card. Stopping only makes Jarvis
                        // do less (backend/jarvis_stop_all.py).
                        "stop_everything" => commands::stop_everything_now(app),
                        other => eprintln!("[jarvis] no handler for hotkey action `{other}`"),
                    }
                })
                .build(),
        );
    }

    // DESKTOP-BUILD §3.1 step 4, belt to the braces in `hud_bootstrap.js`.
    //
    // The real configuration happens in the initialisation script the HUD
    // window is built with, which runs before the page's own scripts and
    // catches the assignment to `window.JARVIS` as it happens. This is the
    // fallback for a page that somehow defined JARVIS without that assignment
    // being interceptable: late — the first fetches have already gone out with
    // the wrong base — but better than a page that never works at all.
    //
    // `typeof` guards the reference rather than `window.JARVIS`, because a
    // top-level `const` is a global *lexical* binding and never a property of
    // `window`. Against a page without the `window.JARVIS =` assignment, the
    // obvious spelling throws TypeError inside an injected script, where the
    // error is close to invisible.
    builder = builder.on_page_load(|webview, payload| {
        if payload.event() != tauri::webview::PageLoadEvent::Finished {
            return;
        }
        if webview.label() != HUD_LABEL {
            return;
        }
        let app = webview.app_handle();
        // Re-sends the base and token whenever the page's differ - not only
        // when it has no base, which it always has. See `configure_hud`.
        configure_hud(app);

        // A HUD that loads (or reloads) mid-session has heard nothing yet: the
        // stream only speaks on change, and it may have connected minutes ago.
        // Push the current state once, now, so the page is not a frame behind.
        let link = app.state::<stream::StreamState>().link();
        push_to_hud(app, "link", &link);

        // Same reason, for the face its reactor wears. The page waits a
        // moment for this before loading any face, so the owner's choice is
        // the first one drawn rather than a swap after the default.
        let appearance = app.state::<appearance::AppearanceState>().snapshot();
        push_to_hud(app, "appearance", &appearance);
    });

    let app = builder
        .setup(|app| {
            let handle = app.handle().clone();

            // FIRST, before anything that might fail. Until this runs, every
            // `logfile::log` is a no-op and a release build has no console, so
            // anything that goes wrong below would be lost exactly the way the
            // backend's startup errors used to be.
            match logfile::init(&handle) {
                Some(dir) => logfile::log(&format!(
                    "\n===== Jarvis Desktop {} starting ===== (logs in {})",
                    env!("CARGO_PKG_VERSION"),
                    dir.display()
                )),
                None => eprintln!(
                    "[jarvis] no log directory could be created; this session is not recorded"
                ),
            }
            if autostart::launched_at_login() {
                logfile::log("[jarvis] started by Windows at login");
            }

            // Before anything reads the token (the HUD bootstrap, the backend
            // it may start): a token an older version kept in the settings
            // file as plain text moves into Windows Credential Manager, once.
            // Any failure leaves it where it was - see token_store.rs.
            commands::migrate_plain_token(&handle);

            // Claims this process's AUMID before the first approval toast can
            // possibly fire - see winrt_toast.rs's own doc for why an
            // actionable Deny button depends on it matching the installer's
            // own shortcut.
            #[cfg(windows)]
            winrt_toast::set_explicit_aumid();

            // The HUD is built here rather than declared in `tauri.conf.json`
            // because a config-declared window cannot carry an initialisation
            // script, and this one needs two things to run before the page's
            // own scripts do: the API base and token (the page reads them when
            // it defines `JARVIS`, which is before its first fetch) and the
            // EventSource shim that keeps the desktop down to one subscription.
            // `on_page_load` is too late for either.
            if let Err(err) = build_hud_window(&handle) {
                logfile::log(&format!(
                    "[jarvis] the HUD window could not be created: {err}"
                ));
            }

            // Vibrancy (Acrylic on the quickbar, Mica on the HUD) plus the
            // focus-loss auto-hide listener for the spotlight bar.
            if let Err(err) = windows::setup_windows(&handle) {
                logfile::log(&format!("[jarvis] window setup reported: {err}"));
            }

            // Desktop widget: put it back where the user left it, then start
            // the telemetry broadcast that keeps its panel live.
            let widget_prefs = windows::load_widget_prefs(&handle);
            handle
                .state::<windows::WidgetState>()
                .update(|prefs| *prefs = widget_prefs.clone());
            if let Err(err) = windows::setup_widget(&handle, &widget_prefs) {
                eprintln!("[jarvis] widget setup reported: {err}");
            }
            spawn_telemetry_loop(handle.clone());

            // Notification-area icon and context menu. Built before the
            // stream starts so the first link change has something to paint.
            if let Err(err) = tray::create_tray(&handle) {
                eprintln!("[jarvis] tray icon unavailable: {err}");
            }

            // Build order step 4. Off unless switched on, and even then it
            // attaches to a backend that is already listening rather than
            // starting a second one against the same SQLite approval queue.
            {
                let supervisor = handle.clone();
                tauri::async_runtime::spawn(async move {
                    match sidecar::ensure_backend(&supervisor).await {
                        Ok(outcome) => {
                            println!("[jarvis] {outcome}");
                            sidecar::watch_startup(supervisor);
                        }
                        Err(err) => {
                            eprintln!("[jarvis] backend supervision: {err}");
                            commands::notify(&supervisor, "Jarvis — backend", &err);
                        }
                    }
                });
            }

            // The one event-stream connection. Everything downstream of it —
            // the tray colour, the approval queue in all three windows, the
            // online pill — is fed from here and nowhere else.
            stream::spawn(handle.clone());

            // Windows Hello's app lock: hides the Jarvis bar, the Brain and
            // Settings once the owner has been away longer than "Lock again
            // after" (lock.rs). Does nothing while the lock is off.
            lock::spawn_watch(handle.clone());

            // A Deny clicked on a toast while Jarvis was CLOSED. The
            // single-instance callback above only fires when a process is
            // already running, so this launch is the only place a cold-start
            // Deny can be seen at all - without it the app simply opened and
            // answered nothing. Right after `stream::spawn` because the
            // decision cannot go out until the stream is live; it waits for
            // that itself. See winrt_toast.rs.
            #[cfg(windows)]
            winrt_toast::decide_denied_at_startup(&handle);
            // And a Snooze clicked while Jarvis was closed - the same wait.
            #[cfg(windows)]
            winrt_toast::snooze_at_startup(&handle);

            // One outbound GET, if the owner left it on, and nothing is
            // installed by it. Spawned and forgotten: a slow endpoint must not
            // hold up the window, the tray or the event stream.
            update::spawn_startup_check(&handle);

            // Same shape, a different question: does this build's bundled
            // look spec still agree with the server's copy? Answers nothing
            // by itself - see spec_drift.rs's own doc for why this exists
            // and what it does and does not do.
            spec_drift::spawn_startup_check(&handle);

            // The owner's face, before the tray's first paint. Local read only:
            // a network fetch here would hold the icon behind a socket timeout.
            appearance::adopt_at_startup(&handle);

            // "Match Windows light or dark mode". Reads Windows' own setting
            // every couple of seconds and holds a switch while Jarvis is busy
            // or an approval is waiting - see system_theme.rs for why this
            // is not `prefers-color-scheme` in the pages.
            system_theme::start(&handle);

            // Bind the accelerators. A failure here is not fatal: another
            // application may already own a combination, and Jarvis still works
            // from the tray in that case.
            #[cfg(desktop)]
            {
                let bound = hotkeys::apply(&handle);
                let refused: Vec<String> = bound
                    .iter()
                    .filter(|b| !b.registered)
                    .map(|b| format!("{} ({})", b.accelerator, b.label))
                    .collect();

                // A refused hotkey used to be reported by `eprintln!` alone, and
                // release builds set `windows_subsystem = "windows"` — there is
                // no stderr for it to reach. Alt+Space is claimed by PowerToys
                // Run and, on recent Windows 11 builds, by the Copilot app, so
                // on such a machine Jarvis Desktop launched, bound nothing, and
                // was indistinguishable from a failed install: the tray tooltip,
                // the card footer and the startup banner all say "Alt+Space to
                // summon", and none of them would have worked.
                //
                // The toast names the combinations rather than saying something
                // went wrong, and now also names where to change them — which
                // it could not before, because there was nowhere.
                if !refused.is_empty() {
                    let list = refused.join(", ");
                    let body = format!(
                        "{list} could not be registered — another application owns \
                         {}. Change them in Settings, or use the tray icon, which \
                         reaches everything.",
                        if refused.len() == 1 { "it" } else { "them" }
                    );
                    commands::notify(&handle, "Jarvis Desktop: hotkeys in use", &body);
                }
            }

            println!(
                "[jarvis] Jarvis Desktop {} online — Alt+Space to summon",
                handle.package_info().version
            );

            // The first-run walkthrough. Last, deliberately: everything above
            // this line is what makes Jarvis actually work, and a walkthrough
            // that opened before the tray icon or the event stream existed
            // would be explaining surfaces that were not there yet.
            if !commands::onboarding_seen(&handle) {
                if let Err(err) = windows::show_onboarding(&handle) {
                    logfile::log(&format!(
                        "[jarvis] the first-run walkthrough could not be opened: {err}"
                    ));
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the Jarvis Desktop application");

    app.run(|app, event| match event {
        // Both windows are hidden rather than destroyed, so the process
        // normally stays alive on its own. The guard covers the case where the
        // HUD is closed outright: Jarvis keeps living in the tray. An explicit
        // `AppHandle::exit(code)` carries `Some(code)` and is let through.
        tauri::RunEvent::ExitRequested { code, api, .. } => {
            if code.is_none() {
                api.prevent_exit();
                return;
            }
            // This exit is really happening. DESKTOP-BUILD §5: ask the backend
            // to stop — which is what unloads the model from the GPU — wait,
            // and kill the process tree if it is still there. Blocking here is
            // deliberate; the alternative is exiting with a model still
            // resident and no window left to say so.
            // The last event id seen, forced: without it a restart of this
            // app alone replays the last few seconds of events, and an alarm
            // that already rang rings again (bug audit 2026-09-26, #4).
            stream::save_resume_now(app);
            sidecar::stop_on_exit(app);
        }

        // A last line of defence for the paths that reach `Exit` without an
        // `ExitRequested` we saw. Stopping twice is a no-op: the owned child is
        // taken out of the state by whichever call gets there first.
        tauri::RunEvent::Exit => {
            stream::save_resume_now(app);
            sidecar::stop_on_exit(app);
        }

        _ => {}
    });
}
