//! Windows remember their size and place (owner's choice, 2026-09-28;
//! docs/RESEARCH-AUDIT-2026-09-28.md idea 16).
//!
//! Brain, Settings, Faces and the HUD open where the owner last left them, at
//! the size they left them, and maximised if they were. Built on
//! `tauri-plugin-window-state` 2.4.1 - the newest release that builds on this
//! crate's Rust 1.89 (2.5.0 needs 1.90).
//!
//! Three things the plugin does NOT get to decide here, each for a reason:
//!
//! * **Whether a window is visible.** The plugin's default restores that too,
//!   and a HUD that was open at the last quit would be put straight back on
//!   screen - before Windows Hello, with App lock on (lib.rs
//!   `build_hud_window`). [`REMEMBERED`] is size, position and maximised
//!   only, and a test below fails if `VISIBLE` ever joins it.
//! * **Maximising a hidden window.** On Windows, maximising is
//!   `ShowWindow(SW_MAXIMIZE)` (tao's `window_state.rs`), which SHOWS the
//!   window as well. So a window built hidden - the HUD at login, on a Deny
//!   launch, or waiting for Windows Hello - gets its size and place now and
//!   is maximised only once it is really shown ([`finish_showing`]).
//! * **Which windows.** Only [`TRACKED`]. The widget and the floating face
//!   keep their own positions (windows.rs), the Jarvis bar centres itself on
//!   every show, and the first-run welcome is a fixed little window. A window
//!   added later is left alone until someone adds it here on purpose.
//!
//! Off-screen: a saved place is used only when the window's title bar would
//! be reachable on a monitor that is plugged in now ([`title_bar_reachable`]).
//! Otherwise the window is centred on the screen it opened on, and shrunk
//! first if it no longer fits.

use std::collections::HashSet;
use std::sync::Mutex;

use tauri::{AppHandle, Manager, PhysicalSize, Runtime, WebviewWindow};
use tauri_plugin_window_state::{AppHandleExt, StateFlags, WindowExt};

use crate::windows::{BRAIN_LABEL, FACES_LABEL, SETTINGS_LABEL};
use crate::HUD_LABEL;

/// What is remembered: size, position and maximised. Never `VISIBLE` (App
/// lock), never `DECORATIONS` or `FULLSCREEN` (the app sets those itself).
pub const REMEMBERED: StateFlags = StateFlags::SIZE
    .union(StateFlags::POSITION)
    .union(StateFlags::MAXIMIZED);

/// The windows whose size and place are remembered.
pub const TRACKED: [&str; 4] = [HUD_LABEL, SETTINGS_LABEL, BRAIN_LABEL, FACES_LABEL];

/// Where the sizes are kept, in the app's config folder. The plugin's own
/// default name, spelled out so a later plugin default cannot move it.
const FILENAME: &str = ".window-state.json";

/// How much of a title bar must be on a monitor for the window to be
/// grabbable, in physical pixels: enough to put the mouse on and drag.
const GRAB_WIDTH: i32 = 120;
const GRAB_HEIGHT: i32 = 24;
/// Windows 10 and 11 draw an invisible resize border of about 7-8 physical
/// pixels round a normal window, which the outer position includes: a
/// window snapped to the left half of the screen reports x = -7. The grab
/// strip starts below it so a snapped window never reads as off-screen.
const BORDER: i32 = 8;

/// Windows that were maximised last time but are hidden now, so their
/// maximise waits until they are shown (see the module doc).
#[derive(Default)]
pub struct PendingMaximize(Mutex<HashSet<String>>);

/// The plugin, restricted as the module doc says. Every tracked window is
/// restored by hand ([`restore`]) rather than by the plugin as it is built,
/// so the plugin never maximises (and so shows) a window that is meant to be
/// hidden.
pub fn plugin<R: Runtime>() -> tauri::plugin::TauriPlugin<R> {
    let mut builder = tauri_plugin_window_state::Builder::new()
        .with_state_flags(REMEMBERED)
        .with_filename(FILENAME)
        .with_filter(is_tracked);
    for label in TRACKED {
        builder = builder.skip_initial_state(label);
    }
    builder.build()
}

/// Whether a window's size and place are remembered.
pub fn is_tracked(label: &str) -> bool {
    TRACKED.contains(&label)
}

/// Puts a freshly built window back where the owner left it.
///
/// `shown` says whether the caller is about to show it (or already has). A
/// window that stays hidden gets its size and place now and its maximise
/// later, from [`finish_showing`]. Never shows a window. Never fails: a
/// window that cannot be restored simply opens where it was built.
pub fn restore(window: &WebviewWindow, shown: bool) {
    if !is_tracked(window.label()) {
        return;
    }
    let flags = if shown {
        REMEMBERED
    } else {
        REMEMBERED.difference(StateFlags::MAXIMIZED)
    };
    if let Err(err) = window.restore_state(flags) {
        crate::logfile::log(&format!(
            "[jarvis] could not restore the size and place of `{}`: {err}",
            window.label()
        ));
        return;
    }
    keep_on_screen(window);
    if !shown && was_maximised(window) {
        if let Some(pending) = window.try_state::<PendingMaximize>() {
            if let Ok(mut set) = pending.0.lock() {
                set.insert(window.label().to_string());
            }
        }
    }
}

/// Called right after a tracked window is shown: a maximise that had to
/// wait while it was hidden happens now. Once only.
pub fn finish_showing(window: &WebviewWindow) {
    let Some(pending) = window.try_state::<PendingMaximize>() else {
        return;
    };
    let waiting = pending
        .0
        .lock()
        .map(|mut set| set.remove(window.label()))
        .unwrap_or(false);
    if waiting {
        let _ = window.maximize();
    }
}

/// Saves every tracked window's size and place now. Called just before the
/// HUD is destroyed on Quit: the plugin's own save runs at exit, by which
/// time the HUD is gone, and a HUD maximised during the session would be
/// forgotten.
///
/// A window still waiting to be maximised (hidden all session) is saved
/// without the maximised flag, so the maximise it never got to show is not
/// overwritten with "not maximised".
pub fn save_now<R: Runtime>(app: &AppHandle<R>) {
    let waiting = app
        .try_state::<PendingMaximize>()
        .and_then(|p| p.0.lock().ok().map(|set| !set.is_empty()))
        .unwrap_or(false);
    let flags = if waiting {
        REMEMBERED.difference(StateFlags::MAXIMIZED)
    } else {
        REMEMBERED
    };
    if let Err(err) = app.save_window_state(flags) {
        crate::logfile::log(&format!(
            "[jarvis] could not save the windows' sizes and places: {err}"
        ));
    }
}

/// Whether the saved state says this window was maximised. Read from the
/// file, because the window itself was deliberately not maximised yet.
fn was_maximised(window: &WebviewWindow) -> bool {
    let Ok(dir) = window.app_handle().path().app_config_dir() else {
        return false;
    };
    std::fs::read_to_string(dir.join(FILENAME))
        .ok()
        .and_then(|text| saved_maximised(&text, window.label()))
        .unwrap_or(false)
}

/// The `maximized` field saved for one window, from the plugin's file.
pub fn saved_maximised(file: &str, label: &str) -> Option<bool> {
    let value: serde_json::Value = serde_json::from_str(file).ok()?;
    value.get(label)?.get("maximized")?.as_bool()
}

/// A rectangle in physical pixels, the one coordinate space Windows has for
/// the whole desktop (see windows.rs `position_is_visible`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

/// Whether enough of the window's title bar - [`GRAB_HEIGHT`] pixels of it,
/// starting [`BORDER`] pixels down - is on one monitor to grab and drag it. The plugin itself only
/// asks that one CORNER touches a monitor, which lets a window come back with
/// its title bar above the top of the screen or almost all of it off to the
/// side, and no way to move it.
pub fn title_bar_reachable(window: Rect, monitors: &[Rect]) -> bool {
    let bar_top = window.y + BORDER.min(window.height.max(0));
    let bar_bottom = (bar_top + GRAB_HEIGHT).min(window.y + window.height.max(1));
    let need = GRAB_WIDTH.min(window.width.max(1));
    monitors.iter().any(|m| {
        let across = (window.x + window.width).min(m.x + m.width) - window.x.max(m.x);
        let down = bar_bottom.min(m.y + m.height) - bar_top.max(m.y);
        // The whole grab strip vertically, and enough of it across.
        across >= need && down >= bar_bottom - bar_top
    })
}

/// A size that fits on `monitor`: unchanged when it already fits, otherwise
/// shrunk to nine tenths of the monitor in the direction that overflows.
pub fn fitted(size: (i32, i32), monitor: Rect) -> (i32, i32) {
    let (w, h) = size;
    let fit_w = if w > monitor.width {
        monitor.width * 9 / 10
    } else {
        w
    };
    let fit_h = if h > monitor.height {
        monitor.height * 9 / 10
    } else {
        h
    };
    (fit_w, fit_h)
}

/// Centres (and if needed shrinks) a window whose title bar is not
/// reachable on any monitor that is plugged in now.
fn keep_on_screen(window: &WebviewWindow) {
    // Maximised windows are placed by Windows itself.
    if window.is_maximized().unwrap_or(false) {
        return;
    }
    let (Ok(pos), Ok(size), Ok(monitors)) = (
        window.outer_position(),
        window.outer_size(),
        window.available_monitors(),
    ) else {
        return;
    };
    let rects: Vec<Rect> = monitors.iter().map(monitor_rect).collect();
    if rects.is_empty() {
        return;
    }
    let here = Rect {
        x: pos.x,
        y: pos.y,
        width: size.width as i32,
        height: size.height as i32,
    };
    if title_bar_reachable(here, &rects) {
        return;
    }
    // The screen it opened on, else the main one.
    let target = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten())
        .map(|m| monitor_rect(&m))
        .unwrap_or(rects[0]);
    if let Ok(inner) = window.inner_size() {
        let (w, h) = fitted((inner.width as i32, inner.height as i32), target);
        if (w, h) != (inner.width as i32, inner.height as i32) && w > 0 && h > 0 {
            let _ = window.set_size(PhysicalSize::new(w as u32, h as u32));
        }
    }
    let _ = window.center();
    crate::logfile::log(&format!(
        "[jarvis] `{}` was saved somewhere no screen shows now, so it opens centred",
        window.label()
    ));
}

fn monitor_rect(m: &tauri::Monitor) -> Rect {
    Rect {
        x: m.position().x,
        y: m.position().y,
        width: m.size().width as i32,
        height: m.size().height as i32,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SCREEN: Rect = Rect {
        x: 0,
        y: 0,
        width: 1920,
        height: 1080,
    };
    const RIGHT: Rect = Rect {
        x: 1920,
        y: 0,
        width: 2560,
        height: 1440,
    };

    fn win(x: i32, y: i32) -> Rect {
        Rect {
            x,
            y,
            width: 1180,
            height: 820,
        }
    }

    #[test]
    fn visibility_is_never_remembered() {
        // App lock: a restored VISIBLE would show the HUD before Windows Hello.
        assert!(!REMEMBERED.contains(StateFlags::VISIBLE));
        assert!(!REMEMBERED.intersects(StateFlags::VISIBLE));
    }

    #[test]
    fn only_size_place_and_maximised_are_remembered() {
        assert!(REMEMBERED.contains(StateFlags::SIZE));
        assert!(REMEMBERED.contains(StateFlags::POSITION));
        assert!(REMEMBERED.contains(StateFlags::MAXIMIZED));
        assert!(!REMEMBERED.intersects(StateFlags::DECORATIONS | StateFlags::FULLSCREEN));
        assert_eq!(
            REMEMBERED.bits(),
            (StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED).bits()
        );
    }

    #[test]
    fn the_small_self_placing_windows_are_left_alone() {
        for label in [
            crate::WIDGET_LABEL,
            crate::windows::FLOATING_LABEL,
            crate::QUICKBAR_LABEL,
            crate::windows::ONBOARDING_LABEL,
            "some-window-added-later",
        ] {
            assert!(!is_tracked(label), "{label} places itself");
        }
        for label in ["hud", "settings", "brain", "faces"] {
            assert!(is_tracked(label), "{label} is remembered");
        }
    }

    #[test]
    fn a_window_fully_on_a_screen_is_reachable() {
        assert!(title_bar_reachable(win(100, 100), &[SCREEN]));
        assert!(title_bar_reachable(win(2000, 50), &[SCREEN, RIGHT]));
    }

    #[test]
    fn a_window_on_an_unplugged_screen_is_not() {
        // Saved on the right-hand monitor, which is gone now.
        assert!(!title_bar_reachable(win(2000, 50), &[SCREEN]));
    }

    #[test]
    fn a_title_bar_above_the_top_of_the_screen_is_not() {
        // One corner still touches the screen - enough for the plugin, not
        // enough to grab the window.
        assert!(!title_bar_reachable(win(100, -400), &[SCREEN]));
        assert!(!title_bar_reachable(win(100, -40), &[SCREEN]));
    }

    #[test]
    fn a_snapped_window_with_its_invisible_border_off_screen_is_reachable() {
        // Windows reports a window snapped to the left half at x = -7, and
        // one dragged hard to the top edge a few pixels above zero.
        assert!(title_bar_reachable(win(-7, 0), &[SCREEN]));
        assert!(title_bar_reachable(win(100, -8), &[SCREEN]));
    }

    #[test]
    fn a_sliver_at_the_edge_is_not() {
        // Only 40 px of the window left on screen.
        assert!(!title_bar_reachable(win(1880, 100), &[SCREEN]));
        // 200 px is enough to grab.
        assert!(title_bar_reachable(win(1720, 100), &[SCREEN]));
    }

    #[test]
    fn a_title_bar_across_two_screens_counts_on_either() {
        assert!(title_bar_reachable(win(1500, 100), &[SCREEN, RIGHT]));
    }

    #[test]
    fn a_screen_to_the_left_has_negative_coordinates() {
        let left = Rect {
            x: -1920,
            y: 0,
            width: 1920,
            height: 1080,
        };
        assert!(title_bar_reachable(win(-1500, 200), &[left, SCREEN]));
        assert!(!title_bar_reachable(win(-1500, 200), &[SCREEN]));
    }

    #[test]
    fn fitted_shrinks_only_what_overflows() {
        assert_eq!(fitted((1180, 820), SCREEN), (1180, 820));
        assert_eq!(fitted((2400, 820), SCREEN), (1728, 820));
        assert_eq!(fitted((2400, 1300), SCREEN), (1728, 972));
    }

    #[test]
    fn the_saved_maximised_flag_is_read_per_window() {
        let file = r#"{"hud":{"width":1280,"height":820,"x":10,"y":10,"prev_x":0,"prev_y":0,
            "maximized":true,"visible":true,"decorated":true,"fullscreen":false},
            "brain":{"maximized":false}}"#;
        assert_eq!(saved_maximised(file, "hud"), Some(true));
        assert_eq!(saved_maximised(file, "brain"), Some(false));
        assert_eq!(saved_maximised(file, "settings"), None);
        assert_eq!(saved_maximised("not json", "hud"), None);
    }
}
