//! Jarvis Desktop — application orchestrator.
//!
//! `main.rs` is a two-line shim over [`run`]. This module owns everything that
//! defines the running application:
//!
//! * plugin registration — global shortcut, clipboard manager, notifications;
//! * the three global hotkeys (`Alt+Space`, `Win+Shift+J`, `Alt+Shift+S`);
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

use tauri::{AppHandle, Emitter};

/// Label of the spotlight quickbar window.
pub const QUICKBAR_LABEL: &str = "quickbar";
/// Label of the full HUD window.
pub const HUD_LABEL: &str = "hud";

/// Local Jarvis orchestrator (also the origin the HUD window loads).
pub const JARVIS_SERVER_URL: &str = "http://127.0.0.1:4719";
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
}

#[cfg(desktop)]
impl Hotkeys {
    fn new() -> Self {
        use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut};
        Self {
            toggle_quickbar: Shortcut::new(Some(Modifiers::ALT), Code::Space),
            ingest_clipboard: Shortcut::new(Some(Modifiers::SUPER | Modifiers::SHIFT), Code::KeyJ),
            capture_screen: Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::KeyS),
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

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

/// Builds and runs the Tauri application. Blocks until the process exits.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
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
                    }
                })
                .build(),
        );
    }

    let app = builder
        .setup(|app| {
            let handle = app.handle().clone();

            // Vibrancy (Acrylic on the quickbar, Mica on the HUD) plus the
            // focus-loss auto-hide listener for the spotlight bar.
            if let Err(err) = windows::setup_windows(&handle) {
                eprintln!("[jarvis] window setup reported: {err}");
            }

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
