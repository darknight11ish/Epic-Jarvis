//! Window effects and behaviour.
//!
//! Two responsibilities live here:
//!
//! 1. **Vibrancy** — Windows 11 Acrylic behind the frameless quickbar and Mica
//!    behind the HUD, applied through `window-vibrancy`.
//! 2. **Spotlight behaviour** — showing, centring, resizing and auto-hiding the
//!    quickbar, including the focus-loss listener that dismisses the bar when
//!    the user clicks away (unless it has been pinned open).

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{AppHandle, LogicalPosition, LogicalSize, Manager, WebviewWindow, WindowEvent};

use crate::{events, HUD_LABEL, QUICKBAR_LABEL};

/// When set, losing focus does not dismiss the quickbar. The frontend raises it
/// while an answer is streaming or while the user is interacting with the card.
static QUICKBAR_PINNED: AtomicBool = AtomicBool::new(false);

/// Collapsed height of the quickbar — just the input row.
const QUICKBAR_BASE_HEIGHT: f64 = 80.0;
/// Tallest the quickbar is allowed to grow once the answer card is open.
const QUICKBAR_MAX_HEIGHT: f64 = 720.0;
/// Fixed logical width, matching `tauri.conf.json`.
const QUICKBAR_WIDTH: f64 = 750.0;
/// Vertical placement of the bar as a fraction of the work area. Sitting a
/// little above the true centre is the classic spotlight position and keeps the
/// expanding answer card from running off the bottom of the screen.
const QUICKBAR_VERTICAL_ANCHOR: f64 = 0.24;

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

/// Applies window effects and attaches behaviour listeners to both windows.
///
/// Errors are collected rather than propagated one at a time: a machine that
/// refuses Acrylic (an older Windows 10 build, a remote session, a policy that
/// disables transparency) should still get a fully working application.
pub fn setup_windows(app: &AppHandle) -> Result<(), String> {
    let mut problems: Vec<String> = Vec::new();

    if let Some(quickbar) = app.get_webview_window(QUICKBAR_LABEL) {
        if let Err(err) = apply_quickbar_effects(&quickbar) {
            problems.push(err);
        }
        attach_quickbar_listeners(app, &quickbar);
        // The bar is created hidden; park it at the spotlight position now so
        // the very first Alt+Space paints in the right place.
        if let Err(err) = center_quickbar(&quickbar) {
            problems.push(err);
        }
    } else {
        problems.push(format!("window `{QUICKBAR_LABEL}` was not found"));
    }

    if let Some(hud) = app.get_webview_window(HUD_LABEL) {
        if let Err(err) = apply_hud_effects(&hud) {
            problems.push(err);
        }
    } else {
        problems.push(format!("window `{HUD_LABEL}` was not found"));
    }

    if problems.is_empty() {
        Ok(())
    } else {
        Err(problems.join("; "))
    }
}

// ---------------------------------------------------------------------------
// Vibrancy
// ---------------------------------------------------------------------------

/// Acrylic behind the spotlight bar: it blurs whatever is underneath, which is
/// what sells the floating-glass look on a 750×80 frameless window.
#[cfg(target_os = "windows")]
pub fn apply_quickbar_effects(window: &WebviewWindow) -> Result<(), String> {
    use window_vibrancy::apply_acrylic;

    // A near-black tint at ~78% keeps text readable over a bright desktop while
    // still letting the blur through on an AMOLED-dark theme.
    apply_acrylic(window, Some((10, 10, 14, 200)))
        .map_err(|e| format!("Acrylic unavailable on the quickbar: {e}"))
}

/// Mica behind the HUD: cheaper than Acrylic for a large, mostly static window
/// and the material Windows 11 expects for app backdrops.
#[cfg(target_os = "windows")]
pub fn apply_hud_effects(window: &WebviewWindow) -> Result<(), String> {
    use window_vibrancy::{apply_acrylic, apply_mica};

    // Mica needs Windows 11 (build 22000+). On Windows 10 it fails, so fall
    // back to Acrylic rather than leaving the HUD fully transparent.
    match apply_mica(window, Some(true)) {
        Ok(()) => Ok(()),
        Err(mica_err) => apply_acrylic(window, Some((10, 10, 14, 190))).map_err(|acrylic_err| {
            format!("Mica ({mica_err}) and Acrylic ({acrylic_err}) both unavailable on the HUD")
        }),
    }
}

#[cfg(not(target_os = "windows"))]
pub fn apply_quickbar_effects(_window: &WebviewWindow) -> Result<(), String> {
    Ok(())
}

#[cfg(not(target_os = "windows"))]
pub fn apply_hud_effects(_window: &WebviewWindow) -> Result<(), String> {
    Ok(())
}

// ---------------------------------------------------------------------------
// Listeners
// ---------------------------------------------------------------------------

/// Wires the spotlight's dismissal behaviour:
///
/// * losing focus hides the bar, unless it is pinned;
/// * a close request hides it instead of destroying it, so the next Alt+Space
///   is instant and the process keeps living in the tray.
fn attach_quickbar_listeners(app: &AppHandle, window: &WebviewWindow) {
    let handle = app.clone();

    window.on_window_event(move |event| match event {
        WindowEvent::Focused(false) => {
            if QUICKBAR_PINNED.load(Ordering::Relaxed) {
                return;
            }
            if let Some(quickbar) = handle.get_webview_window(QUICKBAR_LABEL) {
                let _ = quickbar.hide();
            }
        }
        WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            if let Some(quickbar) = handle.get_webview_window(QUICKBAR_LABEL) {
                let _ = quickbar.hide();
            }
        }
        _ => {}
    });
}

// ---------------------------------------------------------------------------
// Quickbar control
// ---------------------------------------------------------------------------

/// Places the quickbar horizontally centred on the monitor that currently hosts
/// it, at the spotlight anchor height.
pub fn center_quickbar(window: &WebviewWindow) -> Result<(), String> {
    let monitor = window
        .current_monitor()
        .map_err(|e| format!("unable to query the current monitor: {e}"))?
        .or(window
            .primary_monitor()
            .map_err(|e| format!("unable to query the primary monitor: {e}"))?);

    let Some(monitor) = monitor else {
        // No monitor information (headless or a very unusual session): fall
        // back to Tauri's own centring.
        return window
            .center()
            .map_err(|e| format!("unable to centre the quickbar: {e}"));
    };

    let scale = monitor.scale_factor();
    let size = monitor.size().to_logical::<f64>(scale);
    let origin = monitor.position().to_logical::<f64>(scale);

    let x = origin.x + (size.width - QUICKBAR_WIDTH) / 2.0;
    let y = origin.y + size.height * QUICKBAR_VERTICAL_ANCHOR;

    window
        .set_position(LogicalPosition::new(x, y))
        .map_err(|e| format!("unable to position the quickbar: {e}"))
}

/// Shows, centres and focuses the quickbar.
pub fn show_quickbar(app: &AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window(QUICKBAR_LABEL)
        .ok_or_else(|| format!("window `{QUICKBAR_LABEL}` was not found"))?;

    // Collapse back to the input row: a stale tall window would flash the
    // previous answer for a frame before the frontend resets it.
    let _ = window.set_size(LogicalSize::new(QUICKBAR_WIDTH, QUICKBAR_BASE_HEIGHT));
    center_quickbar(&window)?;

    window
        .show()
        .map_err(|e| format!("unable to show the quickbar: {e}"))?;
    window
        .set_always_on_top(true)
        .map_err(|e| format!("unable to raise the quickbar: {e}"))?;
    window
        .set_focus()
        .map_err(|e| format!("unable to focus the quickbar: {e}"))?;

    Ok(())
}

/// Hides the quickbar and drops any pin, so the next summon starts clean.
pub fn hide_quickbar(app: &AppHandle) -> Result<(), String> {
    QUICKBAR_PINNED.store(false, Ordering::Relaxed);

    let window = app
        .get_webview_window(QUICKBAR_LABEL)
        .ok_or_else(|| format!("window `{QUICKBAR_LABEL}` was not found"))?;

    window
        .hide()
        .map_err(|e| format!("unable to hide the quickbar: {e}"))
}

/// Toggles the quickbar. Returns its new visibility.
pub fn toggle_quickbar(app: &AppHandle) -> Result<bool, String> {
    let window = app
        .get_webview_window(QUICKBAR_LABEL)
        .ok_or_else(|| format!("window `{QUICKBAR_LABEL}` was not found"))?;

    let visible = window
        .is_visible()
        .map_err(|e| format!("unable to query quickbar visibility: {e}"))?;

    if visible {
        hide_quickbar(app)?;
        Ok(false)
    } else {
        show_quickbar(app)?;
        Ok(true)
    }
}

/// Resizes the quickbar to fit its answer card, clamped to sane bounds.
pub fn resize_quickbar(app: &AppHandle, height: f64) -> Result<(), String> {
    let window = app
        .get_webview_window(QUICKBAR_LABEL)
        .ok_or_else(|| format!("window `{QUICKBAR_LABEL}` was not found"))?;

    let height = if height.is_finite() {
        height.clamp(QUICKBAR_BASE_HEIGHT, QUICKBAR_MAX_HEIGHT)
    } else {
        QUICKBAR_BASE_HEIGHT
    };

    window
        .set_size(LogicalSize::new(QUICKBAR_WIDTH, height))
        .map_err(|e| format!("unable to resize the quickbar: {e}"))
}

/// Sets the persistent flag that keeps the bar open through focus loss.
pub fn set_quickbar_pinned(app: &AppHandle, pinned: bool) -> bool {
    QUICKBAR_PINNED.store(pinned, Ordering::Relaxed);
    crate::emit_quickbar(app, events::PIN_CHANGED, pinned);
    pinned
}

/// Reads the persistent flag.
pub fn is_quickbar_pinned() -> bool {
    QUICKBAR_PINNED.load(Ordering::Relaxed)
}

// ---------------------------------------------------------------------------
// HUD control
// ---------------------------------------------------------------------------

/// Toggles the HUD window, returning its new visibility.
pub fn toggle_hud(app: &AppHandle) -> Result<bool, String> {
    let window = app
        .get_webview_window(HUD_LABEL)
        .ok_or_else(|| format!("window `{HUD_LABEL}` was not found"))?;

    let visible = window
        .is_visible()
        .map_err(|e| format!("unable to query HUD visibility: {e}"))?;

    if visible {
        window
            .hide()
            .map_err(|e| format!("unable to hide the HUD: {e}"))?;
        Ok(false)
    } else {
        window
            .show()
            .map_err(|e| format!("unable to show the HUD: {e}"))?;
        // A window that was minimised stays minimised on `show`.
        let _ = window.unminimize();
        window
            .set_focus()
            .map_err(|e| format!("unable to focus the HUD: {e}"))?;
        Ok(true)
    }
}
