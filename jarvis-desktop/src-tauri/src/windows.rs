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
use std::time::Duration;

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
    // shipping Windows 11 — window-vibrancy 0.6 takes the DWM path,
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
                // The bar closed: a look held for follow-ups is thrown away.
                crate::look::bar_closed(&handle);
            }
        }
        WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            if let Some(quickbar) = handle.get_webview_window(QUICKBAR_LABEL) {
                let _ = quickbar.hide();
                crate::look::bar_closed(&handle);
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

    // Collapse back to the input row and recentre - but only when summoning
    // it from hidden: a stale tall window would otherwise flash the previous
    // answer for a frame before the frontend resets it. Skipped when it is
    // already on screen: "open a chat" (2026-09-27) calls this to bring an
    // ALREADY-OPEN bar forward mid-stream, and collapsing it here raced the
    // page's own height tracking (main.js only grows the window during a
    // stream, never shrinks it, so the answer stayed visibly clipped until
    // the next height change) and undid a drag the owner had just made (bug
    // audit 2026-09-27, desktop-rust "possible, not verified" #1).
    if !window.is_visible().unwrap_or(false) {
        let _ = window.set_size(LogicalSize::new(QUICKBAR_WIDTH, QUICKBAR_BASE_HEIGHT));
        center_quickbar(&window)?;
    }

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

/// Jarvis Live: puts the quickbar on screen, if it is hidden, WITHOUT taking
/// the keyboard from the program in front - a Live answer arrives in it
/// (the Live review of 2026-09-28, #10: answers streamed into a hidden bar).
/// Never while App lock would ask (Live has ended then anyway), and never
/// moves a bar already on screen. Whether Windows keeps the focus where it
/// was when a window is shown is Windows' call: `show` without `set_focus`
/// is the gentlest this API offers - checked on the owner's PC, not here.
pub(crate) fn show_quickbar_quietly(app: &AppHandle) -> Result<(), String> {
    if crate::lock::app_locked(app) {
        return Ok(());
    }
    let window = app
        .get_webview_window(QUICKBAR_LABEL)
        .ok_or_else(|| format!("window `{QUICKBAR_LABEL}` was not found"))?;
    if window.is_visible().unwrap_or(false) {
        return Ok(());
    }
    let _ = window.set_size(LogicalSize::new(QUICKBAR_WIDTH, QUICKBAR_BASE_HEIGHT));
    center_quickbar(&window)?;
    window
        .show()
        .map_err(|e| format!("unable to show the quickbar: {e}"))?;
    window
        .set_always_on_top(true)
        .map_err(|e| format!("unable to raise the quickbar: {e}"))
}

/// Hides the quickbar and drops any pin, so the next summon starts clean.
pub fn hide_quickbar(app: &AppHandle) -> Result<(), String> {
    QUICKBAR_PINNED.store(false, Ordering::Relaxed);

    let window = app
        .get_webview_window(QUICKBAR_LABEL)
        .ok_or_else(|| format!("window `{QUICKBAR_LABEL}` was not found"))?;

    let hidden = window
        .hide()
        .map_err(|e| format!("unable to hide the quickbar: {e}"));
    // The bar closed: a look held for follow-ups is thrown away (look.rs).
    crate::look::bar_closed(app);
    hidden
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

    let window = tauri::WebviewWindowBuilder::new(
        app,
        SETTINGS_LABEL,
        tauri::WebviewUrl::App("settings.html".into()),
    )
    .title("Jarvis Desktop — Settings")
    .inner_size(680.0, 760.0)
    .min_inner_size(520.0, 480.0)
    .center()
    .resizable(true)
    // Hidden until it is back where the owner left it (window_memory.rs),
    // so it does not flash up centred first and then jump.
    .visible(false)
    .theme(Some(tauri::Theme::Dark))
    // No capture guard is set here. The settings window's guard is toggled by
    // devices.rs (`guard_capture`): on while a pairing code is on screen, off
    // when the session ends or the panel closes (PAIRING-DESIGN 7.1).
    //
    // It is deliberately NOT Tauri's content-protection builder setting, here
    // or later: on Windows that reaches `SetWindowDisplayAffinity`, which tao
    // applies by RECREATING the window - so toggling it closed Settings the
    // moment pairing succeeded (the owner, 2026-10-07). devices.rs calls the
    // Win32 function directly instead. See its comment for the whole story.
    .build()
    .map_err(|e| format!("unable to open settings: {e}"))?;
    crate::window_memory::restore(&window, true);
    window
        .show()
        .map_err(|e| format!("unable to open settings: {e}"))?;
    let _ = window.set_focus();
    Ok(())
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

/// The Brain places a tray item or the Jarvis bar may open it at. The page
/// is told the name alone (`#history` on a new window, the
/// [`BRAIN_PLACE_EVENT`] event on an open one), never anything else.
pub(crate) const BRAIN_PLACES: [&str; 1] = ["history"];

/// The event an open Brain hears a place by.
pub(crate) const BRAIN_PLACE_EVENT: &str = "brain-place";

/// The place asked for, kept until the Brain is really shown - App lock may
/// ask Windows Hello first (lock.rs), and the window is built only then.
static PENDING_PLACE: std::sync::Mutex<Option<&'static str>> = std::sync::Mutex::new(None);

/// Opens the Brain at one of [`BRAIN_PLACES`] - "Chat history…" in the tray
/// and "Earlier chats" in the Jarvis bar (the chat audit, 2026-09-28).
/// Navigation only; App lock still applies, as for [`show_brain`].
pub fn show_brain_at(app: &AppHandle, place: &str) -> Result<(), String> {
    let place = BRAIN_PLACES
        .iter()
        .copied()
        .find(|p| *p == place)
        .ok_or_else(|| "That is not a place in the Brain.".to_string())?;
    if let Ok(mut pending) = PENDING_PLACE.lock() {
        *pending = Some(place);
    }
    show_brain(app)
}

fn take_pending_place() -> Option<&'static str> {
    PENDING_PLACE.lock().ok().and_then(|mut p| p.take())
}

/// [`show_brain`] without the app lock. Only lock.rs calls this.
pub(crate) fn show_brain_unlocked(app: &AppHandle) -> Result<(), String> {
    let place = take_pending_place();
    if let Some(window) = app.get_webview_window(BRAIN_LABEL) {
        window
            .show()
            .map_err(|e| format!("unable to show the Brain: {e}"))?;
        let _ = window.unminimize();
        if let Some(place) = place {
            let _ = tauri::Emitter::emit_to(app, BRAIN_LABEL, BRAIN_PLACE_EVENT, place);
        }
        return window
            .set_focus()
            .map_err(|e| format!("unable to focus the Brain: {e}"));
    }

    let page = match place {
        Some(p) => format!("brain.html#{p}"),
        None => "brain.html".to_string(),
    };
    let window =
        tauri::WebviewWindowBuilder::new(app, BRAIN_LABEL, tauri::WebviewUrl::App(page.into()))
            .title("Jarvis — Brain")
            .inner_size(1180.0, 820.0)
            .min_inner_size(880.0, 600.0)
            .center()
            .resizable(true)
            // Hidden until it is back where the owner left it (window_memory.rs),
            // so it does not flash up centred first and then jump.
            .visible(false)
            .theme(Some(tauri::Theme::Dark))
            .build()
            .map_err(|e| format!("unable to open the Brain: {e}"))?;
    crate::window_memory::restore(&window, true);
    window
        .show()
        .map_err(|e| format!("unable to open the Brain: {e}"))?;
    let _ = window.set_focus();
    Ok(())
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

    let window = tauri::WebviewWindowBuilder::new(
        app,
        FACES_LABEL,
        tauri::WebviewUrl::App("faces.html".into()),
    )
    .title("Jarvis — Faces")
    .inner_size(1280.0, 900.0)
    .min_inner_size(900.0, 620.0)
    .center()
    .resizable(true)
    // Hidden until it is back where the owner left it (window_memory.rs),
    // so it does not flash up centred first and then jump.
    .visible(false)
    .theme(Some(tauri::Theme::Dark))
    .build()
    .map_err(|e| format!("unable to open Faces: {e}"))?;
    crate::window_memory::restore(&window, true);
    window
        .show()
        .map_err(|e| format!("unable to open Faces: {e}"))?;
    let _ = window.set_focus();
    Ok(())
}

/// Label of "Everything Jarvis can do".
pub const FEATURES_LABEL: &str = "features";

/// Opens "Everything Jarvis can do" (`features.html`): the whole feature set,
/// in plain words, in nine groups, each row extending to what it does, how to
/// reach it, whether it asks first, and one real limit - the owner's request of
/// 2026-10-08, designed in docs/FEATURES-LIST-DESIGN.md.
///
/// Built on demand, like Faces: most sessions never open it. It reads one
/// bundled JSON file (`src/features.json`, held byte-identical to the phone's
/// copy by tools/check_feature_list.py) and draws it. It calls no command of its
/// own, listens to no event and reaches no network, so
/// `capabilities/features.json` grants it the core window calls and the theme,
/// and nothing else. Its size is not remembered: `window_memory.rs` tracks the
/// four windows that place themselves, and this one centres like the
/// walkthrough, so a stray entry in that store cannot move a window that has no
/// business being there.
pub fn show_features(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(FEATURES_LABEL) {
        window
            .show()
            .map_err(|e| format!("unable to show the feature list: {e}"))?;
        let _ = window.unminimize();
        return window
            .set_focus()
            .map_err(|e| format!("unable to focus the feature list: {e}"));
    }

    tauri::WebviewWindowBuilder::new(
        app,
        FEATURES_LABEL,
        tauri::WebviewUrl::App("features.html".into()),
    )
    .title("Jarvis — Everything Jarvis can do")
    .inner_size(760.0, 900.0)
    .min_inner_size(420.0, 480.0)
    .resizable(true)
    .center()
    .theme(Some(tauri::Theme::Dark))
    .build()
    .map(|_| ())
    .map_err(|e| format!("unable to open the feature list: {e}"))
}

/// Label of the first-run walkthrough.
pub const ONBOARDING_LABEL: &str = "onboarding";
/// Opens the first-run walkthrough: plain-language screens covering what
/// Jarvis is and that it runs on this PC, the tray icon, an approval, memory,
/// how to talk to it and where the settings live - the things DESKTOP-BUILD's
/// own support notes and the 2026-10-05 UI audit said a new owner asks about
/// first (`docs/UI-AUDIT-2026-10-05.md` section 5 and its "what I would
/// change" row 3).
///
/// Called at most once per install, from the end of `setup()` in `lib.rs`,
/// gated on `commands::onboarding_seen`. Fixed size and not resizable: five
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
    // Behind the app lock, like the Jarvis bar, the Brain and Settings (apps
    // security audit M3). `Ok` while Windows Hello is asked: lock.rs shows
    // the HUD once the owner confirms.
    if !crate::lock::may_open(app, crate::lock::Covered::Hud) {
        return Ok(());
    }
    show_hud_unlocked(app)
}

/// [`show_hud`] without the app lock. Only lock.rs calls this, after Windows
/// Hello confirmed it is the owner.
pub(crate) fn show_hud_unlocked(app: &AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window(HUD_LABEL)
        .ok_or_else(|| format!("window `{HUD_LABEL}` was not found"))?;
    window
        .show()
        .map_err(|e| format!("unable to show the HUD: {e}"))?;
    // Maximised last time but built hidden: maximised now that it is on
    // screen, never before (window_memory.rs).
    crate::window_memory::finish_showing(&window);
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
        // Through the app lock (apps security audit M3). While Windows Hello
        // is asked the HUD is not shown yet, so this reports it hidden.
        if !crate::lock::may_open(app, crate::lock::Covered::Hud) {
            return Ok(false);
        }
        show_hud_unlocked(app)?;
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

// ---------------------------------------------------------------------------
// Floating face ("picture-in-picture" mode)
// ---------------------------------------------------------------------------

/// Label of the minimalist floating face window.
pub const FLOATING_LABEL: &str = "floating";

/// Fixed size, both directions — the round face never letterboxes inside a
/// rectangular window.
///
/// The Widget's own embedded face is 120 CSS px (widget.css `#face-frame`),
/// but it sits inside a 320px card whose header and status row already say
/// what Jarvis is doing; here the face is the ONLY thing on screen, so it
/// gets more room — 200 is inside the 160–220 range this feature was scoped
/// to (CLAUDE.md), big enough that the face's own expressions read at a
/// glance from across a desk, small enough that it does not cover whatever
/// the owner is doing behind it.
const FLOATING_SIZE: f64 = 200.0;

/// Geometry and on/off state, persisted between runs — the same shape as
/// [`WidgetPrefs`] and the same reason: four scalars, written from Rust, so
/// a plugin would add a dependency and a capability grant to buy nothing.
///
/// Unlike `WidgetPrefs`, every field's derived default (`None`, `false`) is
/// already the one this needs — off, no saved position — so `Default` is
/// derived rather than written out by hand.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct FloatingPrefs {
    pub x: Option<f64>,
    pub y: Option<f64>,
    /// Off by default (this app's house style for anything new). Settings,
    /// the tray and its hotkey all flip this; a restart reopens the window
    /// only if the owner had turned it on and never turned it off.
    pub enabled: bool,
    /// "Click through to what is behind", off by default (2026-10-10, the
    /// integration evaluation): every click on this window goes to whatever
    /// is behind it EXCEPT where the face's own picture is drawn, so the
    /// animal can still be grabbed and moved. Cosmetic, so it applies at
    /// once and asks for no approval card.
    pub click_through: bool,
}

/// In-memory copy of [`FloatingPrefs`], flushed to disk by the telemetry
/// tick — see [`WidgetState`], which this mirrors exactly.
#[derive(Default)]
pub struct FloatingState {
    prefs: Mutex<FloatingPrefs>,
    dirty: AtomicBool,
    /// Where the floating face's own page last said its picture is drawn
    /// (see [`note_floating_hit_mask`]). `None` until it has said once, and
    /// `None` again if it ever says it cannot — both keep every click on the
    /// window, which is the safe way round.
    hit_mask: Mutex<Option<Vec<bool>>>,
}

impl FloatingState {
    pub fn snapshot(&self) -> FloatingPrefs {
        self.prefs
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    pub fn update(&self, edit: impl FnOnce(&mut FloatingPrefs)) {
        let mut prefs = self
            .prefs
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        edit(&mut prefs);
        self.dirty.store(true, Ordering::Relaxed);
    }

    pub fn flush(&self, app: &AppHandle) {
        if !self.dirty.swap(false, Ordering::Relaxed) {
            return;
        }
        let prefs = self.snapshot();
        if let Err(err) = write_floating_prefs(app, &prefs) {
            eprintln!("[jarvis] unable to persist floating face prefs: {err}");
        }
    }

    /// The face's own picture, as last measured, or `None` when there is not
    /// one to go on.
    fn hit_mask(&self) -> Option<Vec<bool>> {
        self.hit_mask
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    fn set_hit_mask(&self, cells: Option<Vec<bool>>) {
        *self
            .hit_mask
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = cells;
    }
}

fn floating_prefs_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("unable to resolve the app config dir: {e}"))?;
    Ok(dir.join("floating.json"))
}

fn write_floating_prefs(app: &AppHandle, prefs: &FloatingPrefs) -> Result<(), String> {
    let path = floating_prefs_path(app)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("unable to create {}: {e}", parent.display()))?;
    }
    let json = serde_json::to_string_pretty(prefs)
        .map_err(|e| format!("unable to serialize floating face prefs: {e}"))?;
    std::fs::write(&path, json).map_err(|e| format!("unable to write {}: {e}", path.display()))
}

/// Loads persisted prefs, falling back to defaults (off, no position) for a
/// missing or corrupt file — a bad `floating.json` must never stop the app
/// from starting.
pub fn load_floating_prefs(app: &AppHandle) -> FloatingPrefs {
    floating_prefs_path(app)
        .ok()
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|raw| serde_json::from_str::<FloatingPrefs>(&raw).ok())
        .unwrap_or_default()
}

/// Opens the floating face — the picture-in-picture-style mode: just
/// Jarvis's animated face, voice-only, no title bar, no resize handles, no
/// text box — or brings it forward if it is already open. Built on demand,
/// like Faces, Settings and the Brain: most sessions never turn this on, so
/// a hidden webview living for the run of the app would be pure cost.
///
/// NOT behind the app lock (contrast [`show_quickbar`], [`show_brain`],
/// [`show_settings`], [`show_hud`]): it shows nothing the tray icon does
/// not already show to anyone at the keyboard — which of the states in
/// `jarvis-visual-spec.json` Jarvis is in — never a word of text, a memory
/// or a chat. lock.rs's own reasoning for leaving the widget uncovered
/// ("the widget stays on the desktop... Deny still works from the widget")
/// applies here even more directly: this window carries strictly less
/// information than the widget's status row.
///
/// The URL is `floating.html` — a small new page, not `faces.html` itself.
/// It embeds the SAME `faces.html?mode=display&feed=parent` frame the
/// Widget's tray already runs, driven by postMessage exactly the way
/// `widget.js`'s `postFace` drives it (`floating.js` mirrors that
/// function). `faces.html` is deliberately NOT loaded as this window's own
/// page: its own capability (`capabilities/faces.json`) holds no event or
/// approval-queue permission at all — "it is the largest body of
/// third-party-shaped drawing code in the app" — and loading it directly
/// here would mean either leaving this window's face frozen (no
/// permission to read live state) or handing that permission to the one
/// file this app keeps free of it. `floating.html` holds the read-only
/// permission instead (`capabilities/floating.json`) and hands the frame
/// only a state id and the appearance document, never the queue itself.
pub fn show_floating(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(FLOATING_LABEL) {
        return window
            .show()
            .map_err(|e| format!("unable to show the floating face: {e}"));
    }

    // Built hidden and centred first, then repositioned if a saved spot is
    // still on screen, then shown — the same order `setup_widget` uses, so
    // there is never a visible flash-then-jump on a mixed-DPI desktop.
    let window = tauri::WebviewWindowBuilder::new(
        app,
        FLOATING_LABEL,
        tauri::WebviewUrl::App("floating.html".into()),
    )
    .title("Jarvis")
    .inner_size(FLOATING_SIZE, FLOATING_SIZE)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .decorations(false)
    .transparent(true)
    .always_on_top(true)
    .skip_taskbar(true)
    .shadow(false)
    // Voice-only, no controls: this window must never take the keyboard,
    // the way the widget only ever does on an explicit show (see
    // `toggle_widget`'s own comment) — here it never does, because there is
    // nothing in it to type into or click a button on.
    .focused(false)
    .visible(false)
    .center()
    .theme(Some(tauri::Theme::Dark))
    .build()
    .map_err(|e| format!("unable to open the floating face: {e}"))?;

    let prefs = load_floating_prefs(app);
    if let (Some(x), Some(y)) = (prefs.x, prefs.y) {
        if position_is_visible(&window, x, y) {
            let _ = window.set_position(PhysicalPosition::new(x, y));
        }
    }

    attach_floating_listeners(app, &window);

    // Clicks pass through this window except over the animal, if the owner
    // has asked for that (windows.rs's own note above explains the hit test).
    // Started here rather than in `setup` so the watcher exists exactly while
    // the window does; it does nothing at all until the setting is on.
    start_floating_hit_watch(app);

    window
        .show()
        .map_err(|e| format!("unable to show the floating face: {e}"))
}

/// Tracks dragging (persisted by the telemetry tick, same as the widget) and
/// turns a close request into a hide — there is no titlebar and so no close
/// button, but a future script calling `window.close()` must still leave
/// the process exactly as every other window in this app does.
fn attach_floating_listeners(app: &AppHandle, window: &WebviewWindow) {
    let handle = app.clone();
    window.on_window_event(move |event| match event {
        WindowEvent::Moved(position) => {
            handle.state::<FloatingState>().update(|prefs| {
                prefs.x = Some(position.x as f64);
                prefs.y = Some(position.y as f64);
            });
        }
        WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            if let Some(floating) = handle.get_webview_window(FLOATING_LABEL) {
                let _ = floating.hide();
            }
            handle
                .state::<FloatingState>()
                .update(|prefs| prefs.enabled = false);
            // So Settings' own checkbox repaints (bug audit 2026-09-27,
            // finding #5) - this path turns the face off without going
            // through `set_floating` or `toggle_floating` at all.
            crate::emit_all(&handle, crate::events::FLOATING_CHANGED, false);
        }
        _ => {}
    });
}

/// Hides the floating face.
pub fn hide_floating(app: &AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window(FLOATING_LABEL)
        .ok_or_else(|| format!("window `{FLOATING_LABEL}` was not found"))?;
    window
        .hide()
        .map_err(|e| format!("unable to hide the floating face: {e}"))
}

/// Toggles the floating face and persists the new on/off state. Returns its
/// new visibility.
pub fn toggle_floating(app: &AppHandle) -> Result<bool, String> {
    let visible = floating_is_open(app);
    if visible {
        hide_floating(app)?;
    } else {
        show_floating(app)?;
    }
    app.state::<FloatingState>()
        .update(|prefs| prefs.enabled = !visible);
    // So Settings' own checkbox repaints (bug audit 2026-09-27, finding #5).
    crate::emit_all(app, crate::events::FLOATING_CHANGED, !visible);
    Ok(!visible)
}

/// True when the floating face is on screen.
pub fn floating_is_open(app: &AppHandle) -> bool {
    app.get_webview_window(FLOATING_LABEL)
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false)
}

// ---------------------------------------------------------------------------
// Click-through ("pass my clicks on, except over the animal")
// ---------------------------------------------------------------------------

// WHICH TAURI CALL, AND WHY.
//
// Tauri 2.11.6 offers one thing that makes a whole window transparent to the
// pointer and nothing finer: `WebviewWindow::set_ignore_cursor_events(bool)`
// (its own `window/mod.rs:2224`, and the same method on `WebviewWindow`,
// `webview/webview_window.rs:2132`). On Windows it puts `WS_EX_TRANSPARENT`
// on the window, so the click goes to whatever is behind - all of it or none
// of it. There is no per-pixel form of it in this version, and no
// `hit_test`-shaped method beside it.
//
// So the finer question - "is the pointer on the animal?" - is answered HERE,
// by watching the pointer and flipping that one switch. The pointer's screen
// position comes from `WebviewWindow::cursor_position()`
// (`webview/webview_window.rs:1906`), which is a plain "where is the mouse
// now" query: it keeps answering while this window is ignoring the cursor,
// which is the whole reason it can be used to decide when to stop ignoring
// it. `inner_position()` and `inner_size()` give the window's own rectangle
// in the same physical pixels, so the pointer can be turned into a fraction
// of the window with no DPI arithmetic of our own.
//
// WHERE THE ANIMAL IS comes from the face's own page, not from geometry
// guessed at here: `floating.js` has the picture in front of it, so it
// samples its own drawing into a [`FLOATING_HIT_GRID`]-square grid of
// "something is drawn in this cell" and hands it over through the one command
// `commands::note_floating_hit_mask` (a command, not an event:
// `core:event:allow-emit` is forbidden to every window, apps security audit
// M1). Guessing instead - a circle round the middle - would be wrong for a
// real animal: measured with the real shader on 2026-10-10, every one of the
// five faces reaches the very edge of its square in some pose (the panda's
// tail, the monkey's vine, the owl's branch), so any circle small enough to
// let clicks past the animal would also have cut a limb off.

/// Cells a side in the grid the floating face measures its own picture on.
///
/// 32 is a compromise, not a measurement: at 200 px a side each cell is
/// about 6 px, fine enough that the outline of an animal reads and coarse
/// enough that the whole grid is 1,024 characters on the wire. The page
/// dilates the grid by one cell before sending it (see `floating.js`), so an
/// edge that falls between two cells still counts as the animal.
pub const FLOATING_HIT_GRID: usize = 32;

/// How often the pointer is looked at while click-through is on. 16 ms is
/// about a 60 Hz display's frame: a click that lands on the animal is one
/// frame from being treated as one.
const FLOATING_HIT_POLL: Duration = Duration::from_millis(16);

/// How often it is looked at the rest of the time. Nothing needs doing then
/// (the window takes every click), but the switch can be turned on from
/// Settings at any moment and must take effect at once - so this is short
/// enough to feel immediate and long enough not to spin a core for a
/// window the owner may never turn the setting on for.
const FLOATING_HIT_IDLE: Duration = Duration::from_millis(40);

/// Starts the pointer watcher for the floating face, once per run.
///
/// Called from [`show_floating`], so it exists exactly while the window does.
/// The thread ends by itself the moment the window is gone.
fn start_floating_hit_watch(app: &AppHandle) {
    static STARTED: AtomicBool = AtomicBool::new(false);
    if STARTED.swap(true, Ordering::SeqCst) {
        return;
    }
    let handle = app.clone();
    std::thread::spawn(move || {
        // What this thread last told the window. Kept so a pointer resting
        // still does not call into the window sixty times a second, and so a
        // failing call is logged once rather than on every tick.
        let mut applied: Option<bool> = None;
        let mut complained = false;
        loop {
            let Some(window) = handle.get_webview_window(FLOATING_LABEL) else {
                // Closed for good: nothing left to watch, and never a second
                // watcher (STARTED is one-way), so simply stop.
                return;
            };
            let visible = window.is_visible().unwrap_or(false);
            let click_through = visible && handle.state::<FloatingState>().snapshot().click_through;
            // TRUE means "ignore the cursor", i.e. clicks pass through.
            let ignore = if click_through {
                // `None` - the face has not said where it is drawn, or the
                // pointer or the window's own rectangle could not be read -
                // leaves the window taking every click. The house rule for
                // this feature is that the animal must never become
                // unclickable, so every doubt goes that way.
                pointer_over_face(&window, &handle)
                    .map(|over| !over)
                    .unwrap_or(false)
            } else {
                false
            };
            if applied != Some(ignore) {
                match window.set_ignore_cursor_events(ignore) {
                    Ok(()) => {
                        applied = Some(ignore);
                        complained = false;
                    }
                    Err(err) => {
                        if !complained {
                            eprintln!(
                                "[jarvis] the floating face could not change its click-through: {err}"
                            );
                            complained = true;
                        }
                    }
                }
            }
            std::thread::sleep(if click_through {
                FLOATING_HIT_POLL
            } else {
                FLOATING_HIT_IDLE
            });
        }
    });
}

/// Whether the pointer is over the face's own drawing, or `None` when that
/// cannot be decided (no grid yet, a pointer or a window rectangle that
/// could not be read) - which the caller treats as "let the window have the
/// click", never as "pass it on".
fn pointer_over_face(window: &WebviewWindow, app: &AppHandle) -> Option<bool> {
    let mask = app.state::<FloatingState>().hit_mask()?;
    if mask.len() != FLOATING_HIT_GRID * FLOATING_HIT_GRID {
        return None;
    }
    let cursor = window.cursor_position().ok()?;
    let origin = window.inner_position().ok()?;
    let size = window.inner_size().ok()?;
    if size.width == 0 || size.height == 0 {
        return None;
    }
    let fx = (cursor.x - origin.x as f64) / size.width as f64;
    let fy = (cursor.y - origin.y as f64) / size.height as f64;
    if !(0.0..1.0).contains(&fx) || !(0.0..1.0).contains(&fy) {
        // Off the window's own rectangle: nothing to hit. This is decided
        // from the pointer's real position rather than from the window
        // receiving a move event, which it never does while it is ignoring
        // the cursor - so there is no way for the pointer to be "stuck" on
        // the animal and leave the window swallowing clicks beside it.
        return Some(false);
    }
    let gx = ((fx * FLOATING_HIT_GRID as f64) as usize).min(FLOATING_HIT_GRID - 1);
    let gy = ((fy * FLOATING_HIT_GRID as f64) as usize).min(FLOATING_HIT_GRID - 1);
    Some(mask[gy * FLOATING_HIT_GRID + gx])
}

/// The floating face's own page reporting where its picture is drawn.
///
/// `grid` is one character per cell, left to right and top to bottom, `1` for
/// a cell the face is drawn in. Anything else - a grid of the wrong length, or
/// the empty string the page sends when it cannot measure itself - clears the
/// grid, and a window with no grid takes every click (see
/// [`start_floating_hit_watch`]).
pub fn note_floating_hit_mask(app: &AppHandle, grid: &str) {
    app.state::<FloatingState>()
        .set_hit_mask(parse_hit_mask(grid));
}

/// The command's own argument, read into cells - or `None` for anything that
/// is not exactly one grid.
fn parse_hit_mask(grid: &str) -> Option<Vec<bool>> {
    (grid.len() == FLOATING_HIT_GRID * FLOATING_HIT_GRID)
        .then(|| grid.bytes().map(|b| b == b'1').collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A grid of `n` cells, all background except the ones named (row, col).
    fn grid_with(drawn: &[(usize, usize)]) -> String {
        let mut cells = vec!['0'; FLOATING_HIT_GRID * FLOATING_HIT_GRID];
        for (row, col) in drawn {
            cells[row * FLOATING_HIT_GRID + col] = '1';
        }
        cells.into_iter().collect()
    }

    /// The page's grid is the only thing that says where the animal is, so a
    /// grid that is not exactly one is refused rather than half-believed: a
    /// grid of the wrong length would be read as a different geometry, and
    /// the empty string the page sends when it cannot measure itself must
    /// leave the window taking every click.
    #[test]
    fn only_exactly_one_grid_is_a_grid() {
        let full = FLOATING_HIT_GRID * FLOATING_HIT_GRID;
        assert!(parse_hit_mask(&grid_with(&[])).is_some());
        for bad in [
            String::new(),
            "1".repeat(full - 1),
            "0".repeat(full + 1),
            "1".repeat(FLOATING_HIT_GRID),
            "not a grid at all".repeat(100),
        ] {
            assert!(
                parse_hit_mask(&bad).is_none(),
                "accepted a grid of {} cells",
                bad.len()
            );
        }
    }

    /// `1` is the animal and every other character is not, and a cell is
    /// found by row and column the way the page wrote it: left to right,
    /// top to bottom.
    #[test]
    fn a_grid_reads_left_to_right_top_to_bottom() {
        let cells = parse_hit_mask(&grid_with(&[
            (0, 0),
            (3, 5),
            (FLOATING_HIT_GRID - 1, FLOATING_HIT_GRID - 1),
        ]))
        .expect("a full grid");
        assert_eq!(cells.len(), FLOATING_HIT_GRID * FLOATING_HIT_GRID);
        assert!(cells[0]);
        assert!(cells[3 * FLOATING_HIT_GRID + 5]);
        assert!(cells[FLOATING_HIT_GRID * FLOATING_HIT_GRID - 1]);
        assert_eq!(cells.iter().filter(|on| **on).count(), 3);
        assert!(!cells[FLOATING_HIT_GRID - 1]);
    }

    /// The house rule this feature is built around: a face that has not said
    /// where it is drawn is never "click through" - the window keeps taking
    /// every click, so the animal can never become unclickable.
    #[test]
    fn there_is_no_mask_until_the_page_sends_one() {
        let state = FloatingState::default();
        assert!(state.hit_mask().is_none());
        state.set_hit_mask(Some(vec![true; 4]));
        assert_eq!(state.hit_mask().map(|m| m.len()), Some(4));
        state.set_hit_mask(None);
        assert!(state.hit_mask().is_none());
    }

    /// Off by default, like every cosmetic switch in this app, and a
    /// `floating.json` written before this setting existed reads as off
    /// rather than failing to load.
    #[test]
    fn click_through_is_off_by_default_and_an_old_file_still_loads() {
        assert!(!FloatingPrefs::default().click_through);
        let old: FloatingPrefs =
            serde_json::from_str(r#"{"x":10.0,"y":20.0,"enabled":true}"#).expect("an old file");
        assert!(old.enabled);
        assert!(!old.click_through);
        let round = serde_json::to_string(&FloatingPrefs {
            click_through: true,
            ..Default::default()
        })
        .expect("serialisable");
        assert!(round.contains("\"clickThrough\":true"), "{round}");
    }
}
