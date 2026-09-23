//! "Match Windows light or dark mode" - the desktop's "Follow the system".
//!
//! ## Why this reads the registry instead of asking the page
//!
//! The obvious way is `matchMedia('(prefers-color-scheme: dark)')` in each
//! window. It does not work here: every window is built with
//! `.theme(Some(tauri::Theme::Dark))`, and tauri-runtime-wry hands the
//! window's theme to WebView2 as its preferred colour scheme
//! (`with_theme(match window.theme() ...)` then `SetPreferredColorScheme`).
//! A forced Dark window therefore reports `prefers-color-scheme: dark` to its
//! page whatever Windows is set to, and tao does not raise `ThemeChanged` for
//! a window whose theme is forced. So the answer comes from where Windows
//! keeps it: `AppsUseLightTheme` under
//! `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`
//! (1 = light, 0 = dark), the same value tao reads for its own dark mode.
//!
//! ## Held until Jarvis is resting
//!
//! Like the phone (MainActivity's "Follow the system defers rather than
//! fires"): a switch Windows makes on its own is not applied while an
//! approval is waiting or Jarvis is busy, because a ground that changes
//! mid-approval is the "is it telling me something?" ambiguity the approval
//! card exists to avoid. It lands the next time Jarvis is idle. A theme the
//! owner picks by hand applies at once - they are the one changing it.

use std::sync::Mutex;
use std::time::Duration;

use tauri::{AppHandle, Manager};

/// How often Windows' mode is re-read. A registry read is microseconds; this
/// is about how soon a change shows up, not about cost.
const POLL: Duration = Duration::from_secs(2);

/// The theme id last broadcast to every window.
#[derive(Default)]
pub struct AppliedTheme(Mutex<Option<String>>);

impl AppliedTheme {
    fn get(&self) -> Option<String> {
        self.0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    fn set(&self, theme: &str) {
        *self
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(theme.to_string());
    }
}

/// What the windows are wearing, or `fallback` before anything was applied.
///
/// A window opened while a switch is being held has to match the windows
/// already open, not jump ahead to the theme that is waiting.
pub fn applied_or(app: &AppHandle, fallback: String) -> String {
    app.try_state::<AppliedTheme>()
        .and_then(|state| state.get())
        .unwrap_or(fallback)
}

/// Records and broadcasts a theme to every window now.
pub fn apply_now(app: &AppHandle, theme: &str) {
    if let Some(state) = app.try_state::<AppliedTheme>() {
        state.set(theme);
    }
    crate::emit_all(app, crate::events::THEME_CHANGED, theme.to_string());
}

/// Whether a switch may land now: nothing waiting on a decision, and Jarvis
/// not in the middle of anything. The phone's `resting` is idle, standby or
/// banked - all three are `activity == "idle"` with no approval waiting.
pub fn resting(approvals: usize, activity: &str) -> bool {
    approvals == 0 && activity == "idle"
}

/// Starts the watcher. Called once from `setup`.
pub fn start(app: &AppHandle) {
    let initial = crate::commands::theme_prefs(app).effective;
    if let Some(state) = app.try_state::<AppliedTheme>() {
        state.set(&initial);
    }
    let app = app.clone();
    std::thread::Builder::new()
        .name("jarvis-system-theme".into())
        .spawn(move || loop {
            std::thread::sleep(POLL);
            let prefs = crate::commands::theme_prefs(&app);
            if !prefs.follow_system {
                continue;
            }
            let applied = applied_or(&app, prefs.theme.clone());
            if prefs.effective == applied {
                continue;
            }
            let link = app.state::<crate::stream::StreamState>().link();
            if !resting(link.approvals, &link.activity) {
                // Held, not dropped: the next pass tries again.
                continue;
            }
            apply_now(&app, &prefs.effective);
        })
        .map(|_| ())
        .unwrap_or_else(|err| eprintln!("[jarvis] could not watch the Windows theme: {err}"));
}

/// Windows' app mode: `Some(true)` light, `Some(false)` dark, `None` when it
/// cannot be read.
#[cfg(windows)]
pub fn apps_use_light_theme() -> Option<bool> {
    use windows_sys::Win32::Foundation::ERROR_SUCCESS;
    use windows_sys::Win32::System::Registry::{RegGetValueW, HKEY_CURRENT_USER, RRF_RT_REG_DWORD};

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }
    let key = wide(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
    let value = wide("AppsUseLightTheme");
    let mut data: u32 = 0;
    let mut size: u32 = std::mem::size_of::<u32>() as u32;
    // SAFETY: both strings are NUL-terminated UTF-16 that outlive the call,
    // `data` is a u32 and `size` says so, and RRF_RT_REG_DWORD makes the call
    // fail rather than write anything that is not a four-byte DWORD.
    let rc = unsafe {
        RegGetValueW(
            HKEY_CURRENT_USER,
            key.as_ptr(),
            value.as_ptr(),
            RRF_RT_REG_DWORD,
            std::ptr::null_mut(),
            (&mut data as *mut u32).cast(),
            &mut size,
        )
    };
    if rc == ERROR_SUCCESS {
        Some(data != 0)
    } else {
        None
    }
}

/// Not Windows: there is no light/dark setting this app knows how to read,
/// so following it keeps the theme picked by hand.
#[cfg(not(windows))]
pub fn apps_use_light_theme() -> Option<bool> {
    None
}

#[cfg(test)]
mod tests {
    use super::resting;

    /// A switch is held while anything is waiting on the owner or Jarvis is
    /// busy, and lands when it is idle.
    #[test]
    fn a_switch_waits_for_jarvis_to_rest() {
        assert!(resting(0, "idle"));
        assert!(!resting(1, "idle"));
        assert!(!resting(0, "speaking"));
        assert!(!resting(0, "thinking"));
    }
}
