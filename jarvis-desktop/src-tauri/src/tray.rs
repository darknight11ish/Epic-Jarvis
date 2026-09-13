//! The Windows notification-area (system tray) icon and its context menu.
//!
//! Menu layout:
//!
//! ```text
//! Toggle Spotlight
//! Toggle HUD Window
//! ─────────────────
//! Status Check
//! ─────────────────
//! Quit
//! ```

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager,
};

use crate::{commands, events, windows};

/// Identifier the tray icon is registered under, so it can be looked up later
/// with `AppHandle::tray_by_id`.
pub const TRAY_ID: &str = "jarvis-tray";

// Menu item ids. Kept as constants so the builder and the click handler cannot
// drift apart.
const ID_TOGGLE_SPOTLIGHT: &str = "toggle-spotlight";
const ID_TOGGLE_HUD: &str = "toggle-hud";
const ID_STATUS_CHECK: &str = "status-check";
const ID_QUIT: &str = "quit";

/// Builds the tray icon, its menu and the event handlers.
pub fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    let toggle_spotlight = MenuItem::with_id(
        app,
        ID_TOGGLE_SPOTLIGHT,
        "Toggle Spotlight",
        true,
        Some("Alt+Space"),
    )?;
    let toggle_hud =
        MenuItem::with_id(app, ID_TOGGLE_HUD, "Toggle HUD Window", true, None::<&str>)?;
    let status_check = MenuItem::with_id(app, ID_STATUS_CHECK, "Status Check", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, ID_QUIT, "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(
        app,
        &[
            &toggle_spotlight,
            &toggle_hud,
            &PredefinedMenuItem::separator(app)?,
            &status_check,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;

    let mut builder = TrayIconBuilder::with_id(TRAY_ID)
        .tooltip("Jarvis — Alt+Space")
        .menu(&menu)
        // Left click summons the spotlight; the menu belongs on right click.
        .show_menu_on_left_click(false)
        .on_menu_event(handle_menu_event)
        .on_tray_icon_event(handle_tray_icon_event);

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    Ok(())
}

/// Routes a context-menu click to the matching action.
fn handle_menu_event(app: &AppHandle, event: tauri::menu::MenuEvent) {
    match event.id().as_ref() {
        ID_TOGGLE_SPOTLIGHT => match windows::toggle_quickbar(app) {
            Ok(true) => crate::emit_quickbar(app, events::FOCUS_INPUT, ()),
            Ok(false) => {}
            Err(err) => eprintln!("[jarvis] tray: quickbar toggle failed: {err}"),
        },

        ID_TOGGLE_HUD => {
            if let Err(err) = windows::toggle_hud(app) {
                eprintln!("[jarvis] tray: HUD toggle failed: {err}");
                commands::notify(app, "Jarvis", &format!("HUD unavailable: {err}"));
            }
        }

        ID_STATUS_CHECK => run_status_check(app),

        ID_QUIT => {
            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::GlobalShortcutExt;
                let _ = app.global_shortcut().unregister_all();
            }
            if let Some(hud) = app.get_webview_window(crate::HUD_LABEL) {
                let _ = hud.destroy();
            }
            app.exit(0);
        }

        other => eprintln!("[jarvis] tray: unhandled menu id `{other}`"),
    }
}

/// Left click on the icon summons the spotlight, matching what users expect
/// from a launcher that lives in the notification area.
fn handle_tray_icon_event(tray: &tauri::tray::TrayIcon, event: TrayIconEvent) {
    if let TrayIconEvent::Click {
        button: MouseButton::Left,
        button_state: MouseButtonState::Up,
        ..
    } = event
    {
        let app = tray.app_handle();
        match windows::show_quickbar(app) {
            Ok(()) => crate::emit_quickbar(app, events::FOCUS_INPUT, ()),
            Err(err) => eprintln!("[jarvis] tray: unable to summon the quickbar: {err}"),
        }
    }
}

/// Probes the local services off the UI thread, then reports the result both as
/// a Windows toast and as an event the windows can render.
fn run_status_check(app: &AppHandle) {
    let handle = app.clone();

    tauri::async_runtime::spawn(async move {
        match commands::check_server_health(handle.clone()).await {
            Ok(report) => {
                commands::notify(&handle, "Jarvis — Status Check", &report.summary);
                crate::emit_all(&handle, events::HEALTH_REPORT, report);
            }
            Err(err) => {
                eprintln!("[jarvis] tray: status check failed: {err}");
                commands::notify(&handle, "Jarvis — Status Check", &format!("Failed: {err}"));
            }
        }
    });
}
