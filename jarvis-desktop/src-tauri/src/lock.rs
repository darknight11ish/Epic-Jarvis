//! Windows Hello: the app lock, the check before an approval, and "Show" for
//! the Brain's private lists.
//!
//! The desktop half of the phone's fingerprint check
//! (`jarvis-client/.../ui/approval/BiometricGate.kt`). Windows Hello is
//! whatever this PC has - a Windows PIN, a fingerprint reader or a face
//! camera - asked through `UserConsentVerifier`, the same system prompt
//! Windows itself uses. It is **not** a second authorisation layer: the
//! pairing token is still what authorises every request. It only decides
//! whether the person at the keyboard gets to send one.
//!
//! ## The four settings (Settings, "Security")
//!
//! * **App lock** - off by default. On: opening the Jarvis bar, the Brain or
//!   Settings needs Windows Hello, and so does coming back to one of them
//!   after being away longer than "Lock again after" (straight away, 1, 5
//!   or 15 minutes; 1 minute by default). One of them left open on screen
//!   is hidden once that time is up ([`spawn_watch`]).
//! * **Windows Hello for approvals** - "Risky only" (the default, and the
//!   phone's rule: [`is_risky`]) or "Every approval". There is no third
//!   value below "Risky only", so the type itself cannot express "never".
//! * **Windows Hello for memory lists and chat history** - off by default. On: the Brain's
//!   memory lists come back from [`crate::brain::brain_read`] with the
//!   entries taken out ([`redact_private`]) until Show passes Windows Hello,
//!   and so do its chat history list (`brain/history.rs`, which also will
//!   not open a conversation until then) and its "Saved automatically" list
//!   (`brain/auto_learn.rs`).
//!
//! The rules themselves - which approvals are risky, what counts as
//! loosening, what Windows' answers mean - are in `lock/rules.rs`, with no
//! Tauri in them, so their tests run anywhere.
//!
//! ## Where each decision is made
//!
//! Here, in Rust, before anything is sent - never in a page script. A page
//! can call `decide_approval` directly, skipping every button, and the check
//! still runs, because it is inside the command. The settings live in the
//! app's settings store, which no window can write: no capability grants the
//! store plugin, so the only way to change them is
//! [`set_security_settings`], which asks Windows Hello before anything is
//! loosened. Tightening is instant, and Deny is never held up by anything
//! here: refusing costs a retry, approving the wrong thing is what this is
//! for.

use std::collections::HashSet;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter, Manager, WebviewWindow, WindowEvent};

use crate::commands::SETTINGS_STORE;

mod rules;
pub use rules::*;
use rules::{approval_message, LOOSEN_MESSAGE, REVEAL_MESSAGE, UNLOCK_MESSAGE};

/// Where the four settings live in the settings store.
pub const STORE_KEY: &str = "security";

/// The settings as stored. Read every time rather than cached: the store
/// keeps its own copy in memory, and one source cannot disagree with itself.
pub fn current(app: &AppHandle) -> Security {
    use tauri_plugin_store::StoreExt;

    app.store(SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(STORE_KEY))
        .map(parse_stored)
        .unwrap_or_default()
}

fn save(app: &AppHandle, security: &Security) -> Result<(), String> {
    use tauri_plugin_store::StoreExt;

    let store = app
        .store(SETTINGS_STORE)
        .map_err(|e| format!("the settings file could not be opened: {e}"))?;
    let value = serde_json::to_value(security)
        .map_err(|e| format!("the security settings could not be written: {e}"))?;
    store.set(STORE_KEY, value);
    store
        .save()
        .map_err(|e| format!("the security settings could not be saved: {e}"))
}

/// The windows the app lock covers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Covered {
    Quickbar,
    Brain,
    Settings,
}

impl Covered {
    fn from_label(label: &str) -> Option<Self> {
        match label {
            crate::QUICKBAR_LABEL => Some(Self::Quickbar),
            crate::windows::BRAIN_LABEL => Some(Self::Brain),
            crate::windows::SETTINGS_LABEL => Some(Self::Settings),
            _ => None,
        }
    }

    fn label(self) -> &'static str {
        match self {
            Self::Quickbar => crate::QUICKBAR_LABEL,
            Self::Brain => crate::windows::BRAIN_LABEL,
            Self::Settings => crate::windows::SETTINGS_LABEL,
        }
    }
}

/// Managed state. Nothing here is saved: a restart starts locked.
#[derive(Default)]
pub struct LockState {
    /// The last moment the owner was known to be using a covered window, or
    /// passed Windows Hello.
    last_seen: Mutex<Option<Instant>>,
    /// Covered windows that got focus while unlocked. Used for one thing
    /// only: whether a window's focus LOSS marks the moment the owner left.
    /// A window that got focus while locked is hidden at once and never
    /// enters this, so hiding it starts no "away" clock. Whether the owner is
    /// here now is asked of the windows themselves ([`covered_focused`]), so
    /// an entry left behind by a missed event cannot hold the lock open.
    present: Mutex<HashSet<&'static str>>,
    /// Show was pressed on the Brain and passed Windows Hello.
    revealed: AtomicBool,
    /// Prompts open that were asked for from inside a covered window. The
    /// prompt takes the focus and hands it back when it closes, and that
    /// hand-back can arrive before the answer does; a window getting its
    /// focus back from its own prompt is the owner coming back, not a
    /// stranger arriving. A prompt asked from anywhere else (the widget)
    /// does not count, or cancelling one would open whatever sat behind it.
    inside_prompts: AtomicUsize,
    /// One Windows Hello prompt at a time.
    prompt: tokio::sync::Mutex<()>,
    /// One settings change at a time, so a change cannot be decided against
    /// a value another change is replacing.
    writing: tokio::sync::Mutex<()>,
}

impl LockState {
    fn touch(&self, now: Instant) {
        *self
            .last_seen
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(now);
    }

    fn last_seen(&self) -> Option<Instant> {
        *self
            .last_seen
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    fn present(&self) -> std::sync::MutexGuard<'_, HashSet<&'static str>> {
        self.present
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// The owner is here: they were seen within "Lock again after", or a
    /// covered window has focus right now.
    fn fresh(&self, app: &AppHandle, security: &Security, now: Instant) -> bool {
        within(self.last_seen(), security.relock(), now) || covered_focused(app)
    }
}

/// True when the Jarvis bar, the Brain or Settings has the keyboard focus.
/// Asked of Windows through Tauri each time, not remembered.
fn covered_focused(app: &AppHandle) -> bool {
    [Covered::Quickbar, Covered::Brain, Covered::Settings]
        .iter()
        .filter_map(|c| app.get_webview_window(c.label()))
        .any(|w| w.is_focused().unwrap_or(false))
}

// ---------------------------------------------------------------------------
// Asking Windows Hello
// ---------------------------------------------------------------------------

/// Who asked: the window whose page pressed the button, or nothing (a hotkey,
/// the tray). The window is what the prompt is shown over.
struct Asker {
    label: Option<String>,
    hwnd: isize,
}

impl Asker {
    fn window(window: &WebviewWindow) -> Self {
        Self {
            label: Some(window.label().to_string()),
            hwnd: hwnd_of(window),
        }
    }
}

#[cfg(windows)]
fn hwnd_of(window: &WebviewWindow) -> isize {
    window.hwnd().map(|h| h.0 as isize).unwrap_or(0)
}

#[cfg(not(windows))]
fn hwnd_of(_window: &WebviewWindow) -> isize {
    0
}

/// The window the unlock prompt is shown over, when a hotkey or the tray
/// asked to open something: the window being opened when it exists, else the
/// Jarvis bar (created at startup, so it always does). Both are this app's
/// own - the prompt belongs to this process, which is the one the hotkey or
/// the tray click just gave the right to come to the front.
fn owner_for(app: &AppHandle, which: Covered) -> isize {
    app.get_webview_window(which.label())
        .or_else(|| app.get_webview_window(crate::QUICKBAR_LABEL))
        .map_or(0, |w| hwnd_of(&w))
}

/// Shows one prompt, waiting for any other to finish first, and notes that
/// the owner was here when it confirms - or when it was asked from inside a
/// covered window, where they were already.
async fn ask(app: &AppHandle, asker: &Asker, message: String) -> Outcome {
    let state = app.state::<LockState>();
    let inside = asker
        .label
        .as_deref()
        .and_then(Covered::from_label)
        .is_some();
    let outcome = {
        let _one = state.prompt.lock().await;
        if inside {
            state.inside_prompts.fetch_add(1, Ordering::SeqCst);
        }
        run_check(asker.hwnd, message).await
    };
    if outcome == Outcome::Confirmed || inside {
        state.touch(Instant::now());
    }
    if inside {
        state.inside_prompts.fetch_sub(1, Ordering::SeqCst);
    }
    outcome
}

/// Runs the blocking check on a thread of its own, which it initialises for
/// COM itself rather than trusting a runtime worker's state.
async fn run_check(hwnd: isize, message: String) -> Outcome {
    let (tx, rx) = tokio::sync::oneshot::channel();
    std::thread::spawn(move || {
        let _ = tx.send(hello::verify(hwnd, &message));
    });
    rx.await.unwrap_or(Outcome::Failed)
}

/// What Settings shows about this PC's Windows Hello.
async fn hello_state() -> &'static str {
    let (tx, rx) = tokio::sync::oneshot::channel();
    std::thread::spawn(move || {
        let _ = tx.send(hello::availability());
    });
    match rx.await.unwrap_or(None) {
        None => "not-windows",
        Some(0) => "ready",
        Some(1 | 2) => "not-set-up",
        Some(3) => "blocked",
        Some(_) => "busy",
    }
}

#[cfg(windows)]
mod hello {
    use super::rules::{after_prompt, before_prompt, Attempt, RETRY_DELAY};
    use super::Outcome;
    use ::windows::core::{factory, HSTRING};
    use ::windows::Security::Credentials::UI::{
        UserConsentVerificationResult, UserConsentVerifier,
    };
    use ::windows::Win32::Foundation::HWND;
    use ::windows::Win32::System::Com::{CoInitializeEx, CoUninitialize, COINIT_MULTITHREADED};
    use ::windows::Win32::System::WinRT::IUserConsentVerifierInterop;
    use windows_future::IAsyncOperation;

    /// `UserConsentVerifierAvailability`, by value. `None` only when even
    /// asking failed.
    pub fn availability() -> Option<i32> {
        with_mta(|| {
            UserConsentVerifier::CheckAvailabilityAsync()
                .and_then(|op| op.get())
                .map(|a| a.0)
                .ok()
                // Asking failed: report "busy" (temporary), never "ready".
                .or(Some(4))
        })
    }

    /// At most two tries, and only for temporary failures: a person
    /// dismissing the prompt is an answer and is never asked again.
    pub fn verify(hwnd: isize, message: &str) -> Outcome {
        with_mta(|| {
            for attempt in 0..2 {
                if attempt > 0 {
                    std::thread::sleep(RETRY_DELAY);
                }
                let before =
                    match UserConsentVerifier::CheckAvailabilityAsync().and_then(|op| op.get()) {
                        Ok(a) => before_prompt(a.0),
                        Err(_) => Some(Attempt::Transient),
                    };
                let result = before.unwrap_or_else(|| prompt_once(hwnd, message));
                if let Attempt::Done(outcome) = result {
                    return outcome;
                }
                crate::logfile::log(&format!(
                    "[jarvis] Windows Hello was not available just now (attempt {})",
                    attempt + 1
                ));
            }
            Outcome::Failed
        })
    }

    fn prompt_once(hwnd: isize, message: &str) -> Attempt {
        let message = HSTRING::from(message);
        // The desktop-app form first: the prompt is owned by a real window,
        // so it comes up in front of it rather than behind. If Windows
        // refuses that form, the plain one - the prompt may then open behind
        // other windows, which is still better than no way to answer.
        let over_window =
            || -> ::windows::core::Result<IAsyncOperation<UserConsentVerificationResult>> {
                let interop = factory::<UserConsentVerifier, IUserConsentVerifierInterop>()?;
                // SAFETY: `hwnd` is one of this app's own window handles, read
                // from Tauri a moment ago; the call only reads it, and a window
                // that has since closed is reported as an error, not undefined
                // behaviour.
                unsafe { interop.RequestVerificationForWindowAsync(HWND(hwnd as *mut _), &message) }
            };
        let asked = || -> ::windows::core::Result<i32> {
            let op = match (hwnd != 0).then(over_window) {
                Some(Ok(op)) => op,
                Some(Err(err)) => {
                    crate::logfile::log(&format!(
                        "[jarvis] Windows Hello over a window was refused ({err}); asking without one"
                    ));
                    UserConsentVerifier::RequestVerificationAsync(&message)?
                }
                None => UserConsentVerifier::RequestVerificationAsync(&message)?,
            };
            Ok(op.get()?.0)
        };
        match asked() {
            Ok(code) => after_prompt(code),
            Err(err) => {
                crate::logfile::log(&format!("[jarvis] Windows Hello prompt failed: {err}"));
                Attempt::Transient
            }
        }
    }

    fn with_mta<T>(work: impl FnOnce() -> T) -> T {
        // SAFETY: this thread was spawned for this one check, so nothing else
        // on it has chosen an apartment; it is released below if it was set.
        let init = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) };
        let out = work();
        if init.is_ok() {
            // SAFETY: balances the successful CoInitializeEx above.
            unsafe { CoUninitialize() };
        }
        out
    }
}

/// Not Windows: this app is built for Windows only, and nothing here pretends
/// otherwise. There is no Windows Hello, so the check is "unavailable".
#[cfg(not(windows))]
mod hello {
    use super::Outcome;

    pub fn availability() -> Option<i32> {
        None
    }

    pub fn verify(_hwnd: isize, _message: &str) -> Outcome {
        Outcome::Unavailable
    }
}

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

/// Holds an approval until Windows Hello says it is the owner, when the
/// settings say this one needs it. Called by `decide_approval` after its own
/// checks and before the request is built. Deny never comes here.
pub async fn check_approval(
    app: &AppHandle,
    window: &WebviewWindow,
    id: &str,
) -> Result<(), String> {
    let security = current(app);
    let item = app
        .state::<crate::stream::StreamState>()
        .pending()
        .into_iter()
        .find(|row| crate::stream::approval_id(row).as_deref() == Some(id));
    if !approval_needs_check(security.approvals, item.as_ref()) {
        return Ok(());
    }
    let outcome = ask(app, &Asker::window(window), approval_message(item.as_ref())).await;
    approval_verdict(outcome, &security)
}

// ---------------------------------------------------------------------------
// The app lock
// ---------------------------------------------------------------------------

/// True when `which` may be shown now. Otherwise a Windows Hello check is
/// started (unless one is open) that shows it once the owner confirms, and
/// the caller must not show it.
pub fn may_open(app: &AppHandle, which: Covered) -> bool {
    let security = current(app);
    if !security.app_lock {
        return true;
    }
    let state = app.state::<LockState>();
    let now = Instant::now();
    if state.fresh(app, &security, now) {
        state.touch(now);
        return true;
    }
    start_unlock(app, which);
    false
}

fn start_unlock(app: &AppHandle, which: Covered) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let state = app.state::<LockState>();
        // A second Alt+Space while the prompt is up does not stack a second
        // prompt behind it.
        let Ok(one) = state.prompt.try_lock() else {
            return;
        };
        let outcome = run_check(owner_for(&app, which), UNLOCK_MESSAGE.to_string()).await;
        drop(one);
        match strict_verdict(outcome) {
            Ok(()) => {
                state.touch(Instant::now());
                open_now(&app, which);
            }
            // Dismissed: the owner's own answer, nothing to say.
            Err(_) if outcome == Outcome::Cancelled => {}
            Err(why) => crate::commands::notify(&app, "Jarvis is locked", &format!("{why}.")),
        }
    });
}

fn open_now(app: &AppHandle, which: Covered) {
    let shown = match which {
        Covered::Quickbar => crate::windows::show_quickbar_unlocked(app).map(|()| {
            crate::emit_quickbar(app, crate::events::FOCUS_INPUT, ());
        }),
        Covered::Brain => crate::windows::show_brain_unlocked(app),
        Covered::Settings => crate::windows::show_settings_unlocked(app),
    };
    if let Err(err) = shown {
        eprintln!(
            "[jarvis] unlocked, but {} would not open: {err}",
            which.label()
        );
    }
}

/// Every window's focus changes, from the app-wide handler in lib.rs.
///
/// A covered window that gains focus after the owner has been away longer
/// than "Lock again after" is hidden at once and asks Windows Hello - the
/// Brain left open behind a browser is not a way around the lock. The same
/// moment ends a Show on the Brain's private lists.
pub fn on_window_event(window: &tauri::Window, event: &WindowEvent) {
    let Some(which) = Covered::from_label(window.label()) else {
        return;
    };
    let app = window.app_handle();
    let state = app.state::<LockState>();
    match event {
        WindowEvent::Focused(true) => {
            let security = current(app);
            let now = Instant::now();
            // Not `fresh`: that asks which window has focus, and the answer
            // here is this one - the window being judged.
            let back_from_own_prompt = state.inside_prompts.load(Ordering::SeqCst) > 0;
            if !back_from_own_prompt && !within(state.last_seen(), security.relock(), now) {
                if state.revealed.swap(false, Ordering::SeqCst) {
                    emit_private_hidden(app);
                }
                if security.app_lock {
                    let _ = window.hide();
                    start_unlock(app, which);
                    return;
                }
            }
            state.present().insert(which.label());
            state.touch(now);
        }
        WindowEvent::Focused(false) => {
            // Only a window that was in use while unlocked marks the moment
            // the owner left. One hidden by the lock above never entered
            // `present`, so its focus loss starts no "away" clock.
            if state.present().remove(which.label()) {
                state.touch(Instant::now());
            }
        }
        WindowEvent::Destroyed => {
            state.present().remove(which.label());
            if which == Covered::Brain {
                state.revealed.store(false, Ordering::SeqCst);
            }
        }
        _ => {}
    }
}

/// How often [`spawn_watch`] looks. "Lock again after" is honoured to within
/// this much.
const WATCH_EVERY: Duration = Duration::from_secs(5);

/// Locks what was left on screen. Started once, from `setup`.
///
/// The focus check in [`on_window_event`] catches someone clicking a Jarvis
/// window after the owner left - but a Brain or Settings window left open and
/// visible on a second screen can be READ without being clicked. So every few
/// seconds: when the owner has been away longer than "Lock again after", the
/// Jarvis bar, the Brain and Settings are hidden (App lock on), and a Show
/// on the Brain's memory lists ends (private answers on). Opening one again
/// asks Windows Hello, as ever.
pub fn spawn_watch(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(WATCH_EVERY).await;
            let security = current(&app);
            if !security.app_lock && !security.private_answers {
                continue;
            }
            let state = app.state::<LockState>();
            if state.inside_prompts.load(Ordering::SeqCst) > 0
                || state.fresh(&app, &security, Instant::now())
            {
                continue;
            }
            if state.revealed.swap(false, Ordering::SeqCst) {
                emit_private_hidden(&app);
            }
            if security.app_lock {
                for which in [Covered::Quickbar, Covered::Brain, Covered::Settings] {
                    if let Some(window) = app.get_webview_window(which.label()) {
                        if window.is_visible().unwrap_or(false) {
                            let _ = window.hide();
                        }
                    }
                }
            }
        }
    });
}

fn emit_private_hidden(app: &AppHandle) {
    if let Err(err) = app.emit_to(
        crate::windows::BRAIN_LABEL,
        crate::events::PRIVATE_HIDDEN,
        (),
    ) {
        eprintln!("[jarvis] unable to tell the Brain to hide its lists: {err}");
    }
}

// ---------------------------------------------------------------------------
// Private answers
// ---------------------------------------------------------------------------

/// True while the Brain's private lists must come back without their entries.
pub fn private_hidden(app: &AppHandle) -> bool {
    let security = current(app);
    if !security.private_answers {
        return false;
    }
    let state = app.state::<LockState>();
    if !state.revealed.load(Ordering::SeqCst) {
        return true;
    }
    if state.fresh(app, &security, Instant::now()) {
        return false;
    }
    state.revealed.store(false, Ordering::SeqCst);
    true
}

/// For the commands that hand the facts out in another shape (the "as of"
/// view, the export): refused while the lists are hidden.
pub fn require_private_shown(app: &AppHandle) -> Result<(), String> {
    if private_hidden(app) {
        Err(PRIVATE_STILL_HIDDEN.to_string())
    } else {
        Ok(())
    }
}

/// The Brain's Show button. Only the Brain holds this command.
#[tauri::command]
pub async fn reveal_private_answers(app: AppHandle, window: WebviewWindow) -> Result<bool, String> {
    if !current(&app).private_answers {
        return Ok(true);
    }
    let outcome = ask(&app, &Asker::window(&window), REVEAL_MESSAGE.to_string()).await;
    strict_verdict(outcome)?;
    app.state::<LockState>()
        .revealed
        .store(true, Ordering::SeqCst);
    Ok(true)
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

/// The four settings, and whether this PC has Windows Hello to back them.
#[tauri::command]
pub async fn get_security_settings(app: AppHandle) -> serde_json::Value {
    serde_json::json!({
        "settings": current(&app),
        "hello": hello_state().await,
    })
}

/// Changes the settings. Loosening anything asks Windows Hello first;
/// tightening is instant, but a lock cannot be turned on when this PC has no
/// Windows Hello to unlock it with. Returns what is now stored.
#[tauri::command]
pub async fn set_security_settings(
    app: AppHandle,
    window: WebviewWindow,
    settings: Security,
) -> Result<Security, String> {
    settings.validate()?;
    let state = app.state::<LockState>();
    let _one = state.writing.lock().await;
    let old = current(&app);
    if settings == old {
        return Ok(old);
    }
    if adds_lock(&old, &settings) && !matches!(hello_state().await, "ready" | "busy") {
        return Err(TURN_ON_NEEDS_HELLO.to_string());
    }
    if change_needs_hello(&old, &settings) {
        let outcome = ask(&app, &Asker::window(&window), LOOSEN_MESSAGE.to_string()).await;
        strict_verdict(outcome)?;
    }
    save(&app, &settings)?;
    if old.private_answers != settings.private_answers {
        state.revealed.store(false, Ordering::SeqCst);
    }
    // Turning the lock on from Settings: the owner is here, so the window
    // they are in does not lock under them the moment they click away.
    state.touch(Instant::now());
    crate::emit_all(&app, crate::events::SECURITY_CHANGED, settings);
    Ok(settings)
}
