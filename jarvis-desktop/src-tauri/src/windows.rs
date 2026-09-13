//! Window effects and behaviour.
//!
//! Two responsibilities live here:
//!
//! 1. **Vibrancy** — Windows 11 Acrylic behind the frameless quickbar and Mica
//!    behind the HUD, applied through `window-vibrancy`.
//! 2. **Spotlight behaviour** — showing, centring, resizing and auto-hiding the
//!    quickbar, including the focus-loss listener that dismisses the bar when
//!    the user clicks away (unless it has been pinned open).

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, LogicalPosition, LogicalSize, Manager, WebviewWindow, WindowEvent};

use crate::{events, HUD_LABEL, QUICKBAR_LABEL};

/// Label of the always-on-desktop widget.
pub const WIDGET_LABEL: &str = "widget";

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

/// Fixed logical width of the desktop widget.
const WIDGET_WIDTH: f64 = 320.0;
/// Height of the collapsed mini-pill.
const WIDGET_COLLAPSED_HEIGHT: f64 = 44.0;
/// Height of the expanded card when the frontend does not measure itself.
const WIDGET_EXPANDED_HEIGHT: f64 = 220.0;
/// Ceiling, matching `maxHeight` in `tauri.conf.json`.
///
/// 240 fits the telemetry panel and the capture row, but an approval card adds
/// roughly another 110px, and clipping the Approve button would be a
/// correctness bug, not a cosmetic one — so the ceiling is set where the
/// tallest legitimate layout ends rather than where the common one does.
const WIDGET_MAX_HEIGHT: f64 = 320.0;

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

/// Acrylic behind the spotlight bar.
///
/// Acrylic rather than Mica is deliberate, on three grounds:
///
/// * Fluent guidance puts Mica on long-lived base layers of app windows and
///   Acrylic on transient, light-dismiss surfaces — a command palette is the
///   canonical Acrylic case, and this bar is exactly that.
/// * Mica tints from the *desktop wallpaper*; it does not blur what sits behind
///   the window. On a 750×80 pane floating over other applications that throws
///   away the floating-glass effect the design is built on.
/// * Mica needs Windows 11 22000+. On Windows 10 it fails outright, and a
///   transparent window with no backdrop is worse than a blurred one.
///
/// The DWM stutter sometimes blamed on Acrylic comes from resizing the window
/// at token rate, not from the material; the frontend throttles resizes to
/// ~7 Hz (`RESIZE_INTERVAL_MS` in `main.js`), which is the actual fix. To trade
/// the blur for a wallpaper tint anyway, swap this call for the `apply_mica`
/// used by [`apply_hud_effects`].
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

/// Acrylic behind the desktop widget, a shade darker and denser than the
/// quickbar's: the widget sits on the desktop for hours rather than seconds, so
/// it reads better as a solid pane of smoked glass than as a floating one.
#[cfg(target_os = "windows")]
pub fn apply_widget_effects(window: &WebviewWindow) -> Result<(), String> {
    use window_vibrancy::apply_acrylic;

    apply_acrylic(window, Some((8, 12, 16, 210)))
        .map_err(|e| format!("Acrylic unavailable on the widget: {e}"))
}

#[cfg(not(target_os = "windows"))]
pub fn apply_widget_effects(_window: &WebviewWindow) -> Result<(), String> {
    Ok(())
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

// ---------------------------------------------------------------------------
// Desktop widget
// ---------------------------------------------------------------------------

/// Widget geometry and mode, persisted between runs.
///
/// A small JSON file rather than a store plugin: the widget needs four scalars,
/// and everything here is written from Rust, so a plugin would add a dependency
/// and a capability grant to buy nothing.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct WidgetPrefs {
    pub x: Option<f64>,
    pub y: Option<f64>,
    pub expanded: bool,
    /// `true` floats above everything; `false` lets active windows cover it.
    pub always_on_top: bool,
    pub visible: bool,
}

impl Default for WidgetPrefs {
    fn default() -> Self {
        Self {
            x: None,
            y: None,
            expanded: false,
            always_on_top: true,
            visible: true,
        }
    }
}

/// In-memory copy of [`WidgetPrefs`], flushed to disk by the telemetry tick.
///
/// Dragging emits a `Moved` event per mouse move; writing the file on each one
/// would hammer the disk for a value only the next launch reads.
#[derive(Default)]
pub struct WidgetState {
    prefs: Mutex<WidgetPrefs>,
    dirty: AtomicBool,
}

impl WidgetState {
    pub fn snapshot(&self) -> WidgetPrefs {
        self.prefs
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    /// Applies `edit` to the stored prefs and marks them for the next flush.
    pub fn update(&self, edit: impl FnOnce(&mut WidgetPrefs)) {
        let mut prefs = self
            .prefs
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        edit(&mut prefs);
        self.dirty.store(true, Ordering::Relaxed);
    }

    /// Writes the prefs out if anything changed since the last flush.
    pub fn flush(&self, app: &AppHandle) {
        if !self.dirty.swap(false, Ordering::Relaxed) {
            return;
        }
        let prefs = self.snapshot();
        if let Err(err) = write_widget_prefs(app, &prefs) {
            eprintln!("[jarvis] unable to persist widget prefs: {err}");
        }
    }
}

fn widget_prefs_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("unable to resolve the app config dir: {e}"))?;
    Ok(dir.join("widget.json"))
}

fn write_widget_prefs(app: &AppHandle, prefs: &WidgetPrefs) -> Result<(), String> {
    let path = widget_prefs_path(app)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("unable to create {}: {e}", parent.display()))?;
    }
    let json = serde_json::to_string_pretty(prefs)
        .map_err(|e| format!("unable to serialize widget prefs: {e}"))?;
    std::fs::write(&path, json).map_err(|e| format!("unable to write {}: {e}", path.display()))
}

/// Loads persisted prefs, falling back to defaults for a missing or corrupt
/// file — a bad `widget.json` must never stop the app from starting.
pub fn load_widget_prefs(app: &AppHandle) -> WidgetPrefs {
    widget_prefs_path(app)
        .ok()
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|raw| serde_json::from_str::<WidgetPrefs>(&raw).ok())
        .unwrap_or_default()
}

/// True when the point lies inside some monitor's bounds.
///
/// Guards against restoring the widget onto a monitor that has since been
/// unplugged, which would park it somewhere the user cannot reach.
fn position_is_visible(window: &WebviewWindow, x: f64, y: f64) -> bool {
    let Ok(monitors) = window.available_monitors() else {
        return false;
    };
    monitors.iter().any(|monitor| {
        let scale = monitor.scale_factor();
        let origin = monitor.position().to_logical::<f64>(scale);
        let size = monitor.size().to_logical::<f64>(scale);
        // Require the widget's top-left corner plus a margin to land on-screen,
        // so it can never be restored with only a sliver visible.
        x >= origin.x - 8.0
            && y >= origin.y - 8.0
            && x + 48.0 <= origin.x + size.width
            && y + 24.0 <= origin.y + size.height
    })
}

/// Restores geometry and mode, and wires the listener that tracks dragging.
pub fn setup_widget(app: &AppHandle, prefs: &WidgetPrefs) -> Result<(), String> {
    let window = app
        .get_webview_window(WIDGET_LABEL)
        .ok_or_else(|| format!("window `{WIDGET_LABEL}` was not found"))?;

    apply_widget_effects(&window)?;

    if let (Some(x), Some(y)) = (prefs.x, prefs.y) {
        if position_is_visible(&window, x, y) {
            let _ = window.set_position(LogicalPosition::new(x, y));
        } else {
            eprintln!("[jarvis] saved widget position is off-screen; using the default corner");
        }
    }

    let height = if prefs.expanded {
        WIDGET_EXPANDED_HEIGHT
    } else {
        WIDGET_COLLAPSED_HEIGHT
    };
    let _ = window.set_size(LogicalSize::new(WIDGET_WIDTH, height));
    let _ = window.set_always_on_top(prefs.always_on_top);
    if prefs.visible {
        let _ = window.show();
    } else {
        let _ = window.hide();
    }

    // Track drags in memory; the telemetry tick flushes them to disk.
    let handle = app.clone();
    window.on_window_event(move |event| match event {
        WindowEvent::Moved(position) => {
            let scale = handle
                .get_webview_window(WIDGET_LABEL)
                .and_then(|w| w.scale_factor().ok())
                .unwrap_or(1.0);
            let logical = position.to_logical::<f64>(scale);
            handle.state::<WidgetState>().update(|prefs| {
                prefs.x = Some(logical.x);
                prefs.y = Some(logical.y);
            });
        }
        WindowEvent::CloseRequested { api, .. } => {
            // The widget is a desktop fixture: closing it hides it, and the
            // choice is remembered.
            api.prevent_close();
            if let Some(widget) = handle.get_webview_window(WIDGET_LABEL) {
                let _ = widget.hide();
            }
            handle
                .state::<WidgetState>()
                .update(|prefs| prefs.visible = false);
        }
        _ => {}
    });

    Ok(())
}

/// Grows or collapses the widget.
///
/// `height` lets the frontend pass its own measured content height; without it
/// the two canonical heights are used. Always clamped to the window's declared
/// bounds so a bad measurement cannot produce a 4000px pill.
pub fn resize_widget(app: &AppHandle, expanded: bool, height: Option<f64>) -> Result<(), String> {
    let window = app
        .get_webview_window(WIDGET_LABEL)
        .ok_or_else(|| format!("window `{WIDGET_LABEL}` was not found"))?;

    let target = match height {
        Some(value) if value.is_finite() => value,
        _ if expanded => WIDGET_EXPANDED_HEIGHT,
        _ => WIDGET_COLLAPSED_HEIGHT,
    }
    .clamp(WIDGET_COLLAPSED_HEIGHT, WIDGET_MAX_HEIGHT);

    app.state::<WidgetState>()
        .update(|prefs| prefs.expanded = expanded);

    window
        .set_size(LogicalSize::new(WIDGET_WIDTH, target))
        .map_err(|e| format!("unable to resize the widget: {e}"))
}

/// Switches between floating above everything and sitting behind active windows.
///
/// `false` is the "pin to desktop" mode: the widget stops being topmost, so any
/// focused application covers it. It is not re-parented to the desktop's
/// `WorkerW` — that needs raw Win32 and breaks Acrylic on several builds — so it
/// still surfaces when clicked or Alt+Tabbed past.
pub fn set_widget_always_on_top(app: &AppHandle, always_on_top: bool) -> Result<(), String> {
    let window = app
        .get_webview_window(WIDGET_LABEL)
        .ok_or_else(|| format!("window `{WIDGET_LABEL}` was not found"))?;

    window
        .set_always_on_top(always_on_top)
        .map_err(|e| format!("unable to change the widget's stacking: {e}"))?;
    app.state::<WidgetState>()
        .update(|prefs| prefs.always_on_top = always_on_top);
    Ok(())
}

/// Shows or hides the widget. Returns its new visibility.
pub fn toggle_widget(app: &AppHandle) -> Result<bool, String> {
    let window = app
        .get_webview_window(WIDGET_LABEL)
        .ok_or_else(|| format!("window `{WIDGET_LABEL}` was not found"))?;

    let visible = window
        .is_visible()
        .map_err(|e| format!("unable to query widget visibility: {e}"))?;

    if visible {
        window
            .hide()
            .map_err(|e| format!("unable to hide the widget: {e}"))?;
    } else {
        window
            .show()
            .map_err(|e| format!("unable to show the widget: {e}"))?;
    }

    app.state::<WidgetState>()
        .update(|prefs| prefs.visible = !visible);
    Ok(!visible)
}

/// True when the widget is on screen — the telemetry loop uses this to stay
/// quiet while nobody can see the numbers.
pub fn widget_is_visible(app: &AppHandle) -> bool {
    app.get_webview_window(WIDGET_LABEL)
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false)
}
