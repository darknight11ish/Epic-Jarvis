//! Jarvis Desktop — application orchestrator.
//!
//! `main.rs` is a two-line shim over [`run`]. This module owns everything that
//! defines the running application:
//!
//! * plugin registration — global shortcut, clipboard manager, notifications;
//! * the four global hotkeys (`Alt+Space`, `Win+Shift+J`, `Alt+Shift+S`,
//!   `Alt+Shift+N`);
//! * the notification-area tray icon ([`tray::create_tray`]);
//! * window vibrancy and focus-loss auto-hide ([`windows::setup_windows`]).
//!
//! The two windows are declared in `tauri.conf.json`:
//!
//! | label      | role                                                        |
//! |------------|-------------------------------------------------------------|
//! | `quickbar` | 750×80 frameless transparent spotlight bar, always on top    |
//! | `hud`      | 1280×820 frameless HUD pointed at the local Jarvis server    |

pub mod commands;
pub mod tray;
pub mod windows;

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
    /// Payload: the normalised approval — `id`, `action`, `detail`.
    pub const APPROVAL_REQUESTED: &str = "approval-requested";
    /// Payload: `{ id, approved }`.
    pub const APPROVAL_RESOLVED: &str = "approval-resolved";
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
pub fn emit_all<S: serde::Serialize + Clone>(app: &AppHandle, event: &str, payload: S) {
    if let Err(err) = app.emit(event, payload) {
        eprintln!("[jarvis] unable to broadcast `{event}`: {err}");
    }
}

// ---------------------------------------------------------------------------
// Global hotkeys
// ---------------------------------------------------------------------------

/// The three accelerators Jarvis owns, resolved once at startup.
#[cfg(desktop)]
struct Hotkeys {
    /// `Alt+Space` — toggle the spotlight quickbar.
    toggle_quickbar: tauri_plugin_global_shortcut::Shortcut,
    /// `Win+Shift+J` — ingest the clipboard into the quickbar.
    ingest_clipboard: tauri_plugin_global_shortcut::Shortcut,
    /// `Alt+Shift+S` — capture the active desktop.
    ///
    /// Deliberately *not* `Win+Shift+S`: that combination is owned by the
    /// Windows Snipping Tool at the shell level, so `RegisterHotKey` returns
    /// ERROR_HOTKEY_ALREADY_REGISTERED (1409) and the user gets the Snipping
    /// Tool instead of the Jarvis vision pipeline.
    capture_screen: tauri_plugin_global_shortcut::Shortcut,
    /// `Alt+Shift+N` — summon the bar pre-armed for a Logseq journal note.
    quick_note: tauri_plugin_global_shortcut::Shortcut,
    /// `Alt+Shift+W` — show or hide the desktop widget.
    toggle_widget: tauri_plugin_global_shortcut::Shortcut,
}

#[cfg(desktop)]
impl Hotkeys {
    fn new() -> Self {
        use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut};
        Self {
            toggle_quickbar: Shortcut::new(Some(Modifiers::ALT), Code::Space),
            ingest_clipboard: Shortcut::new(Some(Modifiers::SUPER | Modifiers::SHIFT), Code::KeyJ),
            capture_screen: Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::KeyS),
            quick_note: Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::KeyN),
            toggle_widget: Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::KeyW),
        }
    }
}

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
            app.state::<windows::WidgetState>().flush(&app);

            if !windows::widget_is_visible(&app) {
                continue;
            }

            let lane = app
                .state::<RouteState>()
                .lane
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .clone();
            let sample = commands::sample_telemetry(&mut system, lane);
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
            println!("[jarvis] second launch folded into the running instance");
            if let Some(hud) = app.get_webview_window(HUD_LABEL) {
                let _ = hud.show();
                let _ = hud.unminimize();
                let _ = hud.set_focus();
            }
        }));
    }

    builder = builder
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .manage(ChatState::default())
        .manage(windows::WidgetState::default())
        .manage(RouteState::default())
        .invoke_handler(tauri::generate_handler![
            commands::stream_chat,
            commands::cancel_chat,
            commands::decide_approval,
            commands::announce_approval,
            commands::set_route_lane,
            commands::get_api_settings,
            commands::set_api_settings,
            commands::resize_desktop_widget,
            commands::set_widget_always_on_top,
            commands::toggle_widget,
            commands::save_widget_position,
            commands::get_widget_prefs,
            commands::prefill_quickbar,
            commands::capture_note,
            commands::capture_screen,
            commands::check_server_health,
            commands::hide_quickbar,
            commands::toggle_hud,
            commands::show_quickbar,
            commands::resize_quickbar,
            commands::set_quickbar_pinned,
            commands::is_quickbar_pinned,
            commands::write_clipboard,
            commands::read_clipboard,
            commands::notify_user,
            commands::open_external_url,
            commands::quit_app,
        ]);

    // The global-shortcut plugin owns a single handler for every accelerator we
    // register, so the three hotkeys are dispatched by comparing the shortcut
    // that fired against the ones resolved at startup.
    #[cfg(desktop)]
    {
        use tauri_plugin_global_shortcut::ShortcutState;

        let hotkeys = Hotkeys::new();
        let toggle = hotkeys.toggle_quickbar;
        let ingest = hotkeys.ingest_clipboard;
        let capture = hotkeys.capture_screen;
        let quick_note = hotkeys.quick_note;
        let widget = hotkeys.toggle_widget;

        builder = builder.plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    // Key-up would otherwise fire every action twice.
                    if event.state() != ShortcutState::Pressed {
                        return;
                    }

                    if shortcut == &toggle {
                        match windows::toggle_quickbar(app) {
                            Ok(visible) => {
                                if visible {
                                    // `toggle_quickbar` has already centred and
                                    // focused the window; tell the WebView to
                                    // put the caret in the input.
                                    emit_quickbar(app, events::FOCUS_INPUT, ());
                                }
                            }
                            Err(err) => eprintln!("[jarvis] quickbar toggle failed: {err}"),
                        }
                    } else if shortcut == &ingest {
                        ingest_clipboard(app);
                    } else if shortcut == &capture {
                        capture_desktop(app);
                    } else if shortcut == &quick_note {
                        summon_quick_note(app);
                    } else if shortcut == &widget {
                        if let Err(err) = windows::toggle_widget(app) {
                            eprintln!("[jarvis] widget toggle failed: {err}");
                        }
                    }
                })
                .build(),
        );
    }

    // DESKTOP-BUILD §3.1 step 4. The page reads its API base and token from
    // `JARVIS.set(base, token)`; the desktop shell is what calls it, sourcing
    // both from the settings store rather than the page's own localStorage.
    //
    // Injected on page load rather than as an initialisation script, because
    // `JARVIS` is defined by the page itself and does not exist yet when an
    // init script runs. `typeof` guards the reference: `JARVIS` is a top-level
    // `const`, which is a global *lexical* binding and never a property of
    // `window`, so `window.JARVIS` would be undefined here.
    builder = builder.on_page_load(|webview, payload| {
        if payload.event() != tauri::webview::PageLoadEvent::Finished {
            return;
        }
        if webview.label() != HUD_LABEL {
            return;
        }
        let app = webview.app_handle();
        let base = commands::jarvis_base(app);
        let token = commands::jarvis_token_for(app).unwrap_or_default();
        let script = format!(
            "if (typeof JARVIS !== 'undefined' && JARVIS && typeof JARVIS.set === 'function') \
             {{ JARVIS.set({}, {}); }}",
            serde_json::to_string(&base).unwrap_or_else(|_| "\"\"".into()),
            serde_json::to_string(&token).unwrap_or_else(|_| "\"\"".into()),
        );
        if let Err(err) = webview.eval(&script) {
            eprintln!("[jarvis] unable to configure the HUD page: {err}");
        } else {
            println!("[jarvis] HUD page configured for {base}");
        }
    });

    let app = builder
        .setup(|app| {
            let handle = app.handle().clone();

            // Vibrancy (Acrylic on the quickbar, Mica on the HUD) plus the
            // focus-loss auto-hide listener for the spotlight bar.
            if let Err(err) = windows::setup_windows(&handle) {
                eprintln!("[jarvis] window setup reported: {err}");
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

            // Notification-area icon and context menu.
            if let Err(err) = tray::create_tray(&handle) {
                eprintln!("[jarvis] tray icon unavailable: {err}");
            }

            // Bind the accelerators. A failure here is not fatal: another
            // application may already own a combination, and Jarvis still works
            // from the tray in that case.
            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::GlobalShortcutExt;

                let hotkeys = Hotkeys::new();
                for (label, shortcut) in [
                    ("Alt+Space", hotkeys.toggle_quickbar),
                    ("Win+Shift+J", hotkeys.ingest_clipboard),
                    ("Alt+Shift+S", hotkeys.capture_screen),
                    ("Alt+Shift+N", hotkeys.quick_note),
                    ("Alt+Shift+W", hotkeys.toggle_widget),
                ] {
                    match handle.global_shortcut().register(shortcut) {
                        Ok(()) => println!("[jarvis] hotkey {label} registered"),
                        Err(err) => eprintln!(
                            "[jarvis] hotkey {label} could not be registered ({err}); \
                             another application probably owns it"
                        ),
                    }
                }
            }

            println!(
                "[jarvis] Jarvis Desktop {} online — Alt+Space to summon",
                handle.package_info().version
            );

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the Jarvis Desktop application");

    app.run(|_app, event| {
        // Both windows are hidden rather than destroyed, so the process
        // normally stays alive on its own. The guard covers the case where the
        // HUD is closed outright: Jarvis keeps living in the tray. An explicit
        // `AppHandle::exit(code)` carries `Some(code)` and is let through.
        if let tauri::RunEvent::ExitRequested { code, api, .. } = event {
            if code.is_none() {
                api.prevent_exit();
            }
        }
    });
}
