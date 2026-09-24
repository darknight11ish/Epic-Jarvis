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
use tauri::{AppHandle, LogicalSize, Manager, PhysicalPosition, WebviewWindow, WindowEvent};

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
///
/// Raised from 320 when the `raised` block landed: a gate that carries one
/// gains a chip and a quote, and the old budget was measured before that
/// existed. The quote is line-clamped in `widget.css` for the same reason —
/// the string is attacker-authored and arbitrarily long, so the ceiling alone
/// is not a guarantee.
const WIDGET_MAX_HEIGHT: f64 = 400.0;

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
        // The HUD is the only window built with `decorations(true)`, so it is
        // the only one with a real X button - and it was the only one with no
        // CloseRequested handler. Clicking that X DESTROYED it, and
        // `build_hud_window` is called once, from `setup`. After that:
        // `show_hud` and `toggle_hud` both fail with "window `hud` was not
        // found", the tray's "Show the HUD window" only raises a toast, and a
        // second launch of the app does nothing visible at all, because
        // single-instance folds it into this process and the callback focuses
        // a window that no longer exists. Release builds have no console, so
        // none of that is reported anywhere.
        //
        // Hide, like the quickbar and the widget. The window survives, every
        // route back to it keeps working, and closing still does what the
        // owner meant.
        let handle = app.clone();
        hud.on_window_event(move |event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                if let Some(hud) = handle.get_webview_window(HUD_LABEL) {
                    let _ = hud.hide();
                }
            }
        });
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

    // The tint argument is honoured only on Windows 10 v1809..=22H1 and
    // Windows 11 builds below 22523. Above that — which is every currently
    // shipping Windows 11 — window-vibrancy 0.5.3 takes the DWM path,
    // `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW)`,
    // and never passes `color` at all. It is kept because it still applies on
    // Windows 10, and it is documented here because a colour that silently does
    // nothing on the main target is worth knowing about.
    //
    // Text contrast does NOT depend on it. `--surface` in style.css is
    // rgba(8,9,12,0.86), which composites to rgb(43,43,46) against a pure white
    // desktop with no DWM tint whatsoever — 10.7:1 against the body colour,
    // comfortably AAA. The tint was belt to the CSS braces, not the other way
    // round.
    //
    // Note also that this returns `Ok(())` on the DWM path without checking the
    // HRESULT, so a failure here is not reportable. Do not read a success as
    // proof the effect applied.
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

    // Physical throughout, for the reason `position_is_visible` below already
    // spells out: Windows has exactly one coordinate space for the virtual
    // screen and it is physical. This used to divide `monitor.position()` -
    // which is physical, in that single space - by *that monitor's* scale,
    // inventing a per-monitor logical space that does not exist, and then hand
    // the result to `set_position(Logical)`, which multiplies by the scale of
    // whichever monitor the window is on *now*. On a 150% primary beside a
    // 100% secondary those two disagree and the bar lands off-centre or off
    // the monitor entirely.
    let scale = monitor.scale_factor();
    let size = monitor.size(); // physical
    let origin = monitor.position(); // physical, virtual-screen space

    let width_px = QUICKBAR_WIDTH * scale;
    let x = origin.x as f64 + (size.width as f64 - width_px) / 2.0;
    let y = origin.y as f64 + size.height as f64 * QUICKBAR_VERTICAL_ANCHOR;

    window
        .set_position(PhysicalPosition::new(x, y))
        .map_err(|e| format!("unable to position the quickbar: {e}"))
}

/// Shows, centres and focuses the quickbar - or, while the app lock is on
/// and the owner has been away, asks Windows Hello first and shows it once
/// they confirm (lock.rs). `Ok` either way: every caller's next step (focus
/// the input, hand over the clipboard) lands in the bar, which the owner sees
/// when they have unlocked it.
pub fn show_quickbar(app: &AppHandle) -> Result<(), String> {
    if !crate::lock::may_open(app, crate::lock::Covered::Quickbar) {
        return Ok(());
    }
    show_quickbar_unlocked(app)
}

/// [`show_quickbar`] without the app lock. Only lock.rs calls this, after
/// Windows Hello confirmed it is the owner.
pub(crate) fn show_quickbar_unlocked(app: &AppHandle) -> Result<(), String> {
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

/// Label of the settings window, created on demand.
pub const SETTINGS_LABEL: &str = "settings";

/// Opens the settings window, or brings it forward if it is already open.
///
/// Built on demand rather than declared in `tauri.conf.json` because it is a
/// window most sessions never open, and a hidden one costs a WebView2 process
/// for as long as the app runs.
///
/// While the app lock is on and the owner has been away, Windows Hello is
/// asked first and the window opens once they confirm (lock.rs).
pub fn show_settings(app: &AppHandle) -> Result<(), String> {
    if !crate::lock::may_open(app, crate::lock::Covered::Settings) {
        return Ok(());
    }
    show_settings_unlocked(app)
}

/// [`show_settings`] without the app lock. Only lock.rs calls this.
pub(crate) fn show_settings_unlocked(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(SETTINGS_LABEL) {
        window
            .show()
            .map_err(|e| format!("unable to show settings: {e}"))?;
        let _ = window.unminimize();
        return window
            .set_focus()
            .map_err(|e| format!("unable to focus settings: {e}"));
    }

    tauri::WebviewWindowBuilder::new(
        app,
        SETTINGS_LABEL,
        tauri::WebviewUrl::App("settings.html".into()),
    )
    .title("Jarvis Desktop — Settings")
    .inner_size(680.0, 760.0)
    .min_inner_size(520.0, 480.0)
    .center()
    .resizable(true)
    .focused(true)
    .theme(Some(tauri::Theme::Dark))
    .build()
    .map(|_| ())
    .map_err(|e| format!("unable to open settings: {e}"))
}

pub const BRAIN_LABEL: &str = "brain";

/// Opens the Brain — the memory graph, the live trace and every faculty the
/// backend exposes.
///
/// Built on demand for the same reason as settings: most sessions never open
/// it, and a hidden window costs a WebView2 process for as long as the app
/// runs. This one costs more than most — the graph canvas holds every node the
/// memory store knows about — so it is emphatically not declared in
/// `tauri.conf.json`.
///
/// Larger minimum than settings because the galaxy is the point: a force-
/// directed graph in a 520px column is a hairball, and shrinking it below this
/// makes the window look broken rather than cramped.
///
/// While the app lock is on and the owner has been away, Windows Hello is
/// asked first and the window opens once they confirm (lock.rs).
pub fn show_brain(app: &AppHandle) -> Result<(), String> {
    if !crate::lock::may_open(app, crate::lock::Covered::Brain) {
        return Ok(());
    }
    show_brain_unlocked(app)
}

/// [`show_brain`] without the app lock. Only lock.rs calls this.
pub(crate) fn show_brain_unlocked(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(BRAIN_LABEL) {
        window
            .show()
            .map_err(|e| format!("unable to show the Brain: {e}"))?;
        let _ = window.unminimize();
        return window
            .set_focus()
            .map_err(|e| format!("unable to focus the Brain: {e}"));
    }

    tauri::WebviewWindowBuilder::new(
        app,
        BRAIN_LABEL,
        tauri::WebviewUrl::App("brain.html".into()),
    )
    .title("Jarvis — Brain")
    .inner_size(1180.0, 820.0)
    .min_inner_size(880.0, 600.0)
    .center()
    .resizable(true)
    .focused(true)
    .theme(Some(tauri::Theme::Dark))
    .build()
    .map(|_| ())
    .map_err(|e| format!("unable to open the Brain: {e}"))
}

/// Label of the faces window.
pub const FACES_LABEL: &str = "faces";

/// Opens Faces — every face the spec defines, drawn live, and the bindings
/// that decide which one Jarvis wears in each state.
///
/// Built on demand, and the heaviest window in the app by a distance: twenty
/// procedural canvases animating at once, several of them integrating a
/// physics step per frame. Declaring it in `tauri.conf.json` would pay that
/// cost in every session, including the overwhelming majority that never open
/// it.
///
/// The minimum is wide rather than tall on purpose. The grid is five across
/// and the editor above it is one row of twelve pattern chips; below about
/// 900px the chips wrap to three lines and the controls stop reading as one
/// bar.
pub fn show_faces(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(FACES_LABEL) {
        window
            .show()
            .map_err(|e| format!("unable to show Faces: {e}"))?;
        let _ = window.unminimize();
        return window
            .set_focus()
            .map_err(|e| format!("unable to focus Faces: {e}"));
    }

    tauri::WebviewWindowBuilder::new(
        app,
        FACES_LABEL,
        tauri::WebviewUrl::App("faces.html".into()),
    )
    .title("Jarvis — Faces")
    .inner_size(1280.0, 900.0)
    .min_inner_size(900.0, 620.0)
    .center()
    .resizable(true)
    .focused(true)
    .theme(Some(tauri::Theme::Dark))
    .build()
    .map(|_| ())
    .map_err(|e| format!("unable to open Faces: {e}"))
}

/// Label of the first-run walkthrough.
pub const ONBOARDING_LABEL: &str = "onboarding";

/// Opens the first-run walkthrough: three plain-language screens covering the
/// tray icon, an approval, and memory — the three things DESKTOP-BUILD's own
/// support notes said a new owner asks about first.
///
/// Called at most once per install, from the end of `setup()` in `lib.rs`,
/// gated on `commands::onboarding_seen`. Fixed size and not resizable: three
/// short screens of plain text do not need a resize handle, and giving it one
/// invites a half-width window that wraps mid-sentence.
pub fn show_onboarding(app: &AppHandle) -> Result<(), String> {
    if app.get_webview_window(ONBOARDING_LABEL).is_some() {
        return Ok(()); // already open — a second setup pass must not open two
    }

    tauri::WebviewWindowBuilder::new(
        app,
        ONBOARDING_LABEL,
        tauri::WebviewUrl::App("onboarding.html".into()),
    )
    .title("Jarvis — Welcome")
    .inner_size(480.0, 560.0)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .center()
    .focused(true)
    .theme(Some(tauri::Theme::Dark))
    .build()
    .map(|_| ())
    .map_err(|e| format!("unable to open the walkthrough: {e}"))
}

/// Shows the HUD and brings it forward, whatever state it was in.
///
/// Separate from [`toggle_hud`] because the tray's "Show HUD Window" and its
/// approvals row both mean *show it* — a toggle there would hide the window for
/// anyone who clicked while it was already open behind something else.
pub fn show_hud(app: &AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window(HUD_LABEL)
        .ok_or_else(|| format!("window `{HUD_LABEL}` was not found"))?;
    window
        .show()
        .map_err(|e| format!("unable to show the HUD: {e}"))?;
    // A window that was minimised stays minimised on `show`.
    let _ = window.unminimize();
    window
        .set_focus()
        .map_err(|e| format!("unable to focus the HUD: {e}"))
}

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
        // Physical, on both sides. This used to divide each monitor's physical
        // origin by that monitor's OWN scale factor and compare the results —
        // but Windows has exactly one coordinate space for the virtual screen
        // and it is physical. Dividing per-monitor invents a set of "logical"
        // spaces that overlap or leave gaps on a mixed-DPI desktop, so the
        // guard both rejected positions that were fine and accepted ones that
        // were off-screen.
        let origin = monitor.position();
        let size = monitor.size();
        let (mx, my) = (origin.x as f64, origin.y as f64);
        let (mw, mh) = (size.width as f64, size.height as f64);
        let scale = monitor.scale_factor();
        // The margins are in logical pixels because that is how the widget is
        // sized; scale them to compare against physical bounds.
        x >= mx - 8.0 * scale
            && y >= my - 8.0 * scale
            && x + 48.0 * scale <= mx + mw
            && y + 24.0 * scale <= my + mh
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
            // Physical, matching what `Moved` reported and what was stored.
            // Restoring through `LogicalPosition` multiplied by whichever
            // monitor the window happened to start on, so a widget parked at
            // physical x=2500 on a 100% secondary display reappeared at x=3750
            // when the app started on a 150% primary.
            let _ = window.set_position(PhysicalPosition::new(x, y));
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
            // Stored as physical, which is what this event reports and what the
            // virtual screen is measured in. Converting to "logical" here using
            // the window's current scale factor and converting back on restore
            // using whatever scale factor applied then was a round trip through
            // two different numbers.
            handle.state::<WidgetState>().update(|prefs| {
                prefs.x = Some(position.x as f64);
                prefs.y = Some(position.y as f64);
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
        // The widget is configured `focus: false` and `skipTaskbar: true`, so
        // it is not in the Alt+Tab order and nothing ever gave it the keyboard.
        // Every control in it — pin, expand, the two note buttons, Approve and
        // Deny — was mouse-only, including a gate. Focusing it on show makes
        // Alt+Shift+W the way in, and Escape inside the page is the way out.
        //
        // Only on SHOW. Focus-stealing is the reason `focus: false` is there in
        // the first place: a widget that grabbed the caret every time it
        // repainted would be unusable.
        let _ = window.set_focus();
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
