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
//! * **App lock** - off by default. On: opening the Jarvis bar, the Brain,
//!   Settings or the HUD needs Windows Hello, and so does coming back to one
//!   of them after being away longer than "Lock again after" (straight away,
//!   1, 5 or 15 minutes; 1 minute by default). One of them left open on
//!   screen is hidden once that time is up ([`spawn_watch`]). The widget
//!   stays on the desktop, but while the lock is on its approval card shows
//!   only the notice's title, and its Approve opens the Jarvis bar - behind
//!   the lock - instead of approving (`commands::answer_approval`,
//!   `open_approval_in_quickbar`; apps security audit M3, the owner's
//!   decision 2026-09-25). Deny still works from the widget, as on the phone.
//! * **Windows Hello for approvals** - "Risky only" (the default, and the
//!   phone's rule: [`is_risky`]) or "Every approval". There is no third
//!   value below "Risky only", so the type itself cannot express "never".
//!   Since the approval gap's step 1 (docs/APPROVAL-GAP-DESIGN.md) an
//!   up-to-date backend asks Windows Hello itself for a risky approval from
//!   this PC, and this app then leaves those to it ([`check_approval`]), so
//!   the owner is asked once. A PC with no Windows Hello refuses a risky
//!   approval whatever the settings say ([`NO_HELLO_NO_RISKY`]).
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

    let read = app
        .store(SETTINGS_STORE)
        .map(|store| store.get(STORE_KEY))
        .map_err(|e| e.to_string());
    let last = *LAST_KNOWN.lock().unwrap_or_else(|p| p.into_inner());
    let (security, fell_back) = resolve_read(read.as_ref().map_err(|_| ()), last);
    if fell_back {
        // Plainly, once: the settings file could not be opened, so the last
        // state this run read is being kept - a lock does not quietly read
        // as OFF because a file was locked by another program for a moment.
        if !WARNED_UNREADABLE.swap(true, Ordering::SeqCst) {
            let why = read.err().unwrap_or_default();
            crate::crash_notes::record(
                "lock",
                "settings-unreadable",
                &format!(
                    "the settings file could not be opened ({why}), so App lock kept its last known state"
                ),
            );
        }
    } else {
        WARNED_UNREADABLE.store(false, Ordering::SeqCst);
        *LAST_KNOWN.lock().unwrap_or_else(|p| p.into_inner()) = Some(security);
    }
    security
}

/// What this run last read successfully. See [`current`].
static LAST_KNOWN: Mutex<Option<Security>> = Mutex::new(None);
/// So the "could not be read" note is written once per outage, not per call.
static WARNED_UNREADABLE: AtomicBool = AtomicBool::new(false);

/// The decision inside [`current`], pure so it can be tested: a store that
/// could not be read keeps the last known state (defaults only if nothing was
/// ever read); a store that read fine is trusted, a missing key meaning the
/// defaults. Returns the settings and whether it fell back.
fn resolve_read(
    read: Result<&Option<serde_json::Value>, ()>,
    last: Option<Security>,
) -> (Security, bool) {
    match read {
        Ok(Some(value)) => (parse_stored(value.clone()), false),
        Ok(None) => (Security::default(), false),
        Err(()) => (last.unwrap_or_default(), true),
    }
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
///
/// The HUD joined on 2026-09-25 (apps security audit M3): it shows the
/// memory galaxy, what was recalled for each answer, and the conversation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Covered {
    Quickbar,
    Brain,
    Settings,
    Hud,
}

impl Covered {
    /// Every covered window, for the checks that look at all of them.
    const ALL: [Covered; 4] = [
        Covered::Quickbar,
        Covered::Brain,
        Covered::Settings,
        Covered::Hud,
    ];

    fn from_label(label: &str) -> Option<Self> {
        match label {
            crate::QUICKBAR_LABEL => Some(Self::Quickbar),
            crate::windows::BRAIN_LABEL => Some(Self::Brain),
            crate::windows::SETTINGS_LABEL => Some(Self::Settings),
            crate::HUD_LABEL => Some(Self::Hud),
            _ => None,
        }
    }

    fn label(self) -> &'static str {
        match self {
            Self::Quickbar => crate::QUICKBAR_LABEL,
            Self::Brain => crate::windows::BRAIN_LABEL,
            Self::Settings => crate::windows::SETTINGS_LABEL,
            Self::Hud => crate::HUD_LABEL,
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

/// True when the Jarvis bar, the Brain, Settings or the HUD has the keyboard
/// focus. Asked of Windows through Tauri each time, not remembered.
fn covered_focused(app: &AppHandle) -> bool {
    Covered::ALL
        .iter()
        .filter_map(|c| app.get_webview_window(c.label()))
        .any(|w| w.is_focused().unwrap_or(false))
}

// ---------------------------------------------------------------------------
// Blocking screenshots while the app is locked (the owner's decision, 2026-10-11)
// ---------------------------------------------------------------------------
//
// The desktop half of the phone's `FLAG_SECURE`
// (`jarvis-client/.../data/Security.kt` `blockScreenCapture`), which the owner
// decided for the phone on 2026-09-25 and left undecided here. He said yes on
// 2026-10-11, so this is a decided feature - not a new switch: it follows App
// lock and "Windows Hello for memory lists and chat history", exactly as the
// phone's rule follows App lock and its own hide-lists setting.
//
// Being honest about what this is worth, because it is easy to overstate:
//
// * It DOES keep Jarvis's own windows out of a screen capture made through
//   Windows' own capture APIs (`PrintScreen`, Snipping Tool, the Game Bar, a
//   screen recorder, a screen share) on Windows 10 2004 and newer. Before that
//   build `WDA_EXCLUDEFROMCAPTURE` degrade to `WDA_MONITOR`, where the window
//   still shows - as a black rectangle - rather than leaving the picture. See
//   Microsoft's own page for `SetWindowDisplayAffinity`.
// * It does NOT stop a camera pointed at the screen. Microsoft says so in the
//   same paragraph: "unlike a security feature ... there is no guarantee".
// * It does NOT remove the window from a capture of the WHOLE desktop. On
//   Windows 11 the taskbar's own screenshot tool and most capture programs take
//   the screen as one picture; the exclusion generally still applies to that
//   picture, but the guarantee Microsoft gives is about the window's own
//   content, not about what sits around it. The doc line in
//   `docs/ARCHITECTURE.md` says this plainly rather than implying a wall.
// * It is not what makes the lock safe. The lock itself - hiding a window that
//   was left open, asking Windows Hello before showing one again - is what
//   protects the content. This only closes the cheapest way to copy it.
//
// Not Tauri's `set_content_protected`, which would be the obvious call, and
// `devices.rs` already records why in full: on Windows tao applies it by
// RECREATING the window, which closed Settings the moment a pairing succeeded
// (the owner's report, 2026-10-07). `SetWindowDisplayAffinity` is called
// directly instead - it changes an attribute of a window this app already
// owns, and rebuilds nothing, so the lock can never close a window under the
// owner.

/// The windows a capture is blocked on while the app is locked.
///
/// Every window this app can put Jarvis's words in, by Tauri's own label. The
/// four App lock covers (`Covered`) hide themselves once the owner has been
/// away, so this list buys nothing for them in that state - but a window is
/// still on screen between the moment the owner leaves and the moment the
/// watch notices (up to [`WATCH_EVERY`]), and on a second monitor a Brain left
/// open can be photographed... captured, rather than read. Cheap to include,
/// and wrong to leave out. The rest are the windows that stay visible while
/// locked, which is the gap this feature closes.
///
/// `onboarding` is here for the same reason as the rest: it draws Jarvis's
/// words, and a one-time window is not a licence to leak them.
///
/// The two badges (`live-badge`, `watch-badge`) are NOT here. They are the
/// small status marks for a Live session and "Watch with me", drawn over
/// whatever else is on screen; their words ("Jarvis is watching") are the whole
/// point of them, and blocking them would hide the notice that Jarvis is
/// listening or looking - the opposite of what this project wants.
pub const SNAPSHOT_LABELS: [&str; 9] = [
    crate::QUICKBAR_LABEL,
    crate::HUD_LABEL,
    crate::windows::WIDGET_LABEL,
    crate::windows::FLOATING_LABEL,
    crate::windows::BRAIN_LABEL,
    crate::windows::SETTINGS_LABEL,
    crate::windows::FACES_LABEL,
    crate::windows::FEATURES_LABEL,
    crate::windows::ONBOARDING_LABEL,
];

/// True when a screen capture of Jarvis's windows must not show their content.
///
/// The decision, pure, so its cases are testable without a window: App lock on
/// and the lock would ask for Windows Hello now, or the Brain's private lists
/// hidden and that show has ended. The settings decide whether the block is
/// allowed at all; the state decides whether it is on. Unlocked, the owner is
/// looking at those windows, so there is nothing to keep from a capture they
/// asked for themselves.
///
/// Deliberately not `current(app).app_lock` alone, which is the phone's shape:
/// the phone must set `FLAG_SECURE` from the setting because Android gives it
/// no "the owner has gone" moment it could react to. Here there is one, and
/// `app_locked` is already it - the same test that ends a Live session and
/// tells talk-to-type to stop listening. One notion of "locked", not a second.
pub fn capture_blocked(app: &AppHandle) -> bool {
    let owner_here = !app_locked(app);
    if owner_here {
        // The owner is looking at their own screen. Nothing to keep from them.
        return false;
    }
    current(app).blocks_capture(owner_here) || private_hidden(app)
}

/// Hides `window` from screen capture (`excluded`), or puts it back.
///
/// The one Win32 call, shared with `devices.rs`, which needs the same thing
/// while a pairing code is on screen. The window must belong to this process
/// and be top level - both true of every window Tauri gives us here.
///
/// A refusal is logged once and otherwise ignored: the owner decided the lock
/// is worth having, and an older Windows that cannot exclude a window must not
/// turn that into a crash or a window that will not open. It is a cheap guard
/// against the easiest copy, not a wall (docs/ARCHITECTURE.md section 3).
pub fn set_affinity(window: &WebviewWindow, excluded: bool) {
    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            SetWindowDisplayAffinity, WDA_EXCLUDEFROMCAPTURE, WDA_NONE,
        };
        let Ok(handle) = window.hwnd() else {
            eprintln!(
                "[jarvis] could not read {}'s handle for the capture block",
                window.label()
            );
            return;
        };
        // SAFETY: `handle` is this app's own window handle, read back from
        // Tauri. SetWindowDisplayAffinity only sets an attribute on it - unlike
        // Tauri's set_content_protected, it cannot rebuild the window.
        let ok = unsafe {
            SetWindowDisplayAffinity(
                handle.0 as _,
                if excluded {
                    WDA_EXCLUDEFROMCAPTURE
                } else {
                    WDA_NONE
                },
            )
        };
        if ok == 0 {
            let err = std::io::Error::last_os_error();
            crate::crash_notes::record(
                "lock",
                "capture-block-refused",
                &format!(
                    "Windows refused to keep {} out of screen capture ({err}), so it can be captured while the app is locked",
                    window.label()
                ),
            );
        }
    }
    #[cfg(not(windows))]
    {
        // No equivalent on the platforms this app is not shipped for.
        let _ = (window, excluded);
    }
}

/// What the last [`sweep`] did: the state it was asked for, and the windows it
/// is sure it reached. `None` until the first one.
///
/// [`sweep`] runs from the watch every five seconds for the whole life of the
/// app, so it asks Windows only when the answer has changed or when a window is
/// one it has never set (one built since the last look). Two small values,
/// rather than a call into `user32` per window per tick.
static SWEPT: Mutex<Option<(bool, HashSet<&'static str>)>> = Mutex::new(None);

/// Which windows still need [`set_affinity`] asked of them, returning them and
/// updating `reached` to say that they have now been done.
///
/// `reached` is the set `sweep` remembers between its ticks, so this is what
/// decides both halves of the feature: a window never set is set; every window
/// is set again when the answer has CHANGED - which is the "off" half, and the
/// one that would leave a screen uncapturable for good if it were missing. Pure
/// apart from the set it is handed, so both are testable without a window and
/// without an app.
fn to_set(
    excluded: bool,
    last: Option<bool>,
    reached: &mut HashSet<&'static str>,
    present: &[&'static str],
) -> Vec<&'static str> {
    let changed = last != Some(excluded);
    let mut set = Vec::new();
    // A window that is not there now may be built later, so it is forgotten:
    // when it appears, it is one we have never set.
    for label in SNAPSHOT_LABELS {
        if !present.contains(&label) {
            reached.remove(label);
        }
    }
    for label in present {
        if changed || !reached.contains(label) {
            reached.insert(label);
            set.push(*label);
        }
    }
    set
}

/// Puts every window in [`SNAPSHOT_LABELS`] into the state [`capture_blocked`]
/// asks for, right now.
///
/// Called when the lock turns on (the watch, [`spawn_watch`]), when it turns
/// off (the owner passing Windows Hello, [`start_unlock`]), when the security
/// settings change, and once as a window is created - a window built while the
/// lock is on must not sit unprotected until the next tick.
pub fn sweep(app: &AppHandle) {
    let excluded = capture_blocked(app);
    let mut swept = SWEPT.lock().unwrap_or_else(|p| p.into_inner());
    let last = swept.as_ref().map(|(last, _)| *last);
    let mut reached = swept.take().map(|(_, reached)| reached).unwrap_or_default();
    let present: Vec<&'static str> = SNAPSHOT_LABELS
        .into_iter()
        .filter(|label| app.get_webview_window(label).is_some())
        .collect();
    let set = to_set(excluded, last, &mut reached, &present);
    for label in set {
        if let Some(window) = app.get_webview_window(label) {
            set_affinity(&window, excluded);
        }
    }
    *swept = Some((excluded, reached));
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

/// What `decide_approval` does next, once [`check_approval`] has passed.
pub struct ApprovalSend {
    /// The backend may show its own Windows Hello prompt for this one
    /// (owner-check.patch), so the Approve may wait `wait` for its answer and
    /// the backend's prompt should be let to the front.
    pub backend_may_ask: bool,
    /// How long the Approve request may take.
    pub wait: Duration,
}

/// Holds an approval until Windows Hello says it is the owner, when the
/// settings say this one needs it. Called by `decide_approval` after its own
/// checks and before the request is built. Deny never comes here.
///
/// Since the approval gap's step 1 (docs/APPROVAL-GAP-DESIGN.md) the backend
/// asks Windows Hello itself for a risky approval made on this PC, when its
/// `/api/version` says `capabilities.owner_check: "backend"`. Then this app
/// does not ask as well - the owner is asked once, by the backend, whose
/// prompt names the card the same way - unless "Every approval" wants a
/// card the backend will not ask about ([`approval_needs_local_check`]).
/// Only when this app talks to the backend on this PC (loopback): the
/// backend asks only for approvals that come from this PC, so a desktop
/// pointed anywhere else keeps asking itself. An older backend: as before.
pub async fn check_approval(
    app: &AppHandle,
    window: &WebviewWindow,
    id: &str,
    short: Duration,
) -> Result<ApprovalSend, String> {
    let security = current(app);
    let item = app
        .state::<crate::stream::StreamState>()
        .pending()
        .into_iter()
        .find(|row| crate::stream::approval_id(row).as_deref() == Some(id));
    let backend_checks = crate::commands::backend_owner_check(app).await;
    let backend_asks = backend_checks && crate::commands::base_is_this_pc(app);
    if approval_needs_local_check(security.approvals, item.as_ref(), backend_asks) {
        let outcome = ask(app, &Asker::window(window), approval_message(item.as_ref())).await;
        approval_verdict(outcome, &security)?;
    }
    // A backend with the check asks for a risky card whenever the request
    // reaches it from this PC - also through this PC's own Tailscale
    // address, where this app asked as well - so the wait grows whenever it
    // might ask, not only when this app left the asking to it.
    let backend_may_ask = backend_checks && item.as_ref().is_none_or(is_risky);
    Ok(ApprovalSend {
        backend_may_ask,
        wait: approval_wait(short, backend_may_ask, item.as_ref()),
    })
}

/// Lets the backend's Windows Hello prompt come to the front, just before an
/// Approve it may ask about is sent. Windows gives the right to take the
/// front only to the program the owner is using - this one, since they just
/// pressed Approve - and this passes it on for the next window that asks. It
/// lasts until the owner next clicks or types; it lets a window come
/// forward, nothing more.
pub fn let_backend_prompt_forward() {
    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{AllowSetForegroundWindow, ASFW_ANY};
        // SAFETY: a plain Win32 call with a constant argument; it reads and
        // writes nothing of ours.
        unsafe {
            AllowSetForegroundWindow(ASFW_ANY);
        }
    }
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

/// Talk-to-type (talk_type.rs): true while App lock is on and the owner has
/// been away longer than "Lock again after" - the same test [`may_open`]
/// makes, but it starts no prompt (a prompt would take the keyboard focus
/// from the program the owner wants to type into) and does not count as the
/// owner being here. Talk-to-type then does not listen or type.
pub fn locked_now(app: &AppHandle) -> bool {
    let security = current(app);
    if !security.app_lock {
        return false;
    }
    let state = app.state::<LockState>();
    !state.fresh(app, &security, Instant::now())
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
                // The owner is back and has just proved it, so the windows stop
                // being hidden from capture. `touch` above is what
                // `capture_blocked` reads, so this is the unlock half.
                sweep(&app);
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
        Covered::Hud => crate::windows::show_hud_unlocked(app),
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

/// True when App lock is on and would ask Windows Hello before showing a
/// Jarvis window now - the owner has been away longer than "Lock again
/// after" and no Jarvis window has focus. Jarvis Live on this PC ends then,
/// and cannot start (live.rs): someone else at the PC must not be able to
/// talk to Jarvis through a session the owner left running. Asks nothing.
pub fn app_locked(app: &AppHandle) -> bool {
    let security = current(app);
    if !security.app_lock {
        return false;
    }
    let state = app.state::<LockState>();
    state.inside_prompts.load(Ordering::SeqCst) == 0 && !state.fresh(app, &security, Instant::now())
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
/// Jarvis bar, the Brain, Settings and the HUD are hidden (App lock on), and a Show
/// on the Brain's memory lists ends (private answers on). Opening one again
/// asks Windows Hello, as ever.
pub fn spawn_watch(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(WATCH_EVERY).await;
            let security = current(&app);
            // Before the two `continue`s below, not after. This is the one
            // place that runs whether the lock is on or off, so it is where
            // the capture block turns on as the owner leaves and off as they
            // come back - including the case where App lock has just been
            // switched off in Settings while this loop was asleep. It writes
            // to the windows only when the answer has changed, so the usual
            // tick does no more than a boolean per window.
            sweep(&app);
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
                for which in Covered::ALL {
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
    // A tag-suggestion card already on screen loses its chat title now.
    crate::stream::rebroadcast_pending(app);
    if let Err(err) = app.emit_to(
        crate::windows::BRAIN_LABEL,
        crate::events::PRIVATE_HIDDEN,
        (),
    ) {
        eprintln!("[jarvis] unable to tell the Brain to hide its lists: {err}");
    }
    // The Jarvis bar hides its thread of earlier answers the same moment
    // (the second chat audit, 2026-09-28).
    if let Err(err) = app.emit_to(crate::QUICKBAR_LABEL, crate::events::PRIVATE_HIDDEN, ()) {
        eprintln!("[jarvis] unable to tell the Jarvis bar to hide its thread: {err}");
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
    // ...which also means turning App lock on does not blank the screen out of
    // every capture while the owner is still sitting in front of it. This
    // settles the block either way: on if the settings now call for it and the
    // owner has gone, off if they have just turned the last of them off.
    sweep(&app);
    crate::emit_all(&app, crate::events::SECURITY_CHANGED, settings);
    Ok(settings)
}

#[cfg(test)]
mod read_tests {
    use super::*;
    use serde_json::json;

    fn locked() -> Security {
        Security {
            app_lock: true,
            ..Security::default()
        }
    }

    #[test]
    fn an_unreadable_store_keeps_the_last_known_lock() {
        let (s, fell_back) = resolve_read(Err(()), Some(locked()));
        assert!(s.app_lock && fell_back);
    }

    #[test]
    fn an_unreadable_store_with_nothing_known_is_the_defaults() {
        let (s, fell_back) = resolve_read(Err(()), None);
        assert_eq!(s, Security::default());
        assert!(fell_back);
    }

    #[test]
    fn a_readable_store_is_trusted() {
        let v = Some(json!({ "appLock": false }));
        let (s, fell_back) = resolve_read(Ok(&v), Some(locked()));
        assert!(!s.app_lock && !fell_back);
        let (s, _) = resolve_read(Ok(&None), Some(locked()));
        assert_eq!(s, Security::default());
    }
}

/// Blocking a capture while the app is locked (2026-10-11).
///
/// The app's own `capture_blocked` asks the live settings and the live lock
/// state, so what these check is the rule underneath it - the same shape as
/// `read_tests` above, which tests `resolve_read` rather than the store.
#[cfg(test)]
mod capture_tests {
    use super::*;

    /// A stand-in for the app's two settings, so a case reads as the situation
    /// it describes. The real `capture_blocked` is checked against these by
    /// `the_live_rule_is_the_one_these_cases_check` below.
    fn block(app_lock: bool, hide_lists: bool, after_the_lock_would_ask: bool) -> bool {
        Security {
            app_lock,
            private_answers: hide_lists,
            ..Security::default()
        }
        .blocks_capture(!after_the_lock_would_ask)
    }

    #[test]
    fn nothing_is_blocked_with_both_settings_off() {
        // CONTROL. Without this one, a build that blocked every capture for
        // its whole life would pass every case below.
        assert!(!block(false, false, false));
        assert!(!block(false, false, true));
    }

    #[test]
    fn the_lock_blocks_once_it_would_ask_for_windows_hello() {
        // The feature: the owner has walked away, so a capture must not show
        // Jarvis's windows.
        assert!(block(true, false, true));
    }

    #[test]
    fn the_lock_leaves_capture_alone_while_the_owner_is_there() {
        // The other half of the same rule, and the one that would be left
        // broken by a build that only ever turned the block ON: an owner
        // sitting in front of their own screen can still take a picture of it.
        assert!(!block(true, false, false));
    }

    #[test]
    fn hidden_memory_lists_block_capture_the_same_way_the_phone_does() {
        // The phone's rule is `appLock || privateLists`
        // (`Security.kt` `blockScreenCapture`); this is the desktop's half of
        // it. "Hide memory lists and chat history" is off by default, and with
        // it on the Brain comes back with the entries taken out until Show
        // passes Windows Hello - a capture in that window is the leak.
        assert!(block(false, true, true));
        assert!(block(true, true, true));
        // Show just passed, or the owner is here: the lists are on screen
        // because they asked for them, so there is nothing to keep back.
        assert!(!block(false, true, false));
    }

    #[test]
    fn the_live_rule_is_the_one_these_cases_check() {
        // The cases above are only worth anything if the shipped rule takes
        // the same three inputs. Pinned as source, because this crate has no
        // headless way to build a Tauri app and call the real one.
        let src = include_str!("lock.rs");
        let rule = &src[src.find("pub fn capture_blocked").expect("the rule")..];
        let rule = &rule[..rule.find("\n}\n").expect("its end")];
        assert!(
            rule.contains("app_locked(app)") && rule.contains("private_hidden(app)"),
            "capture_blocked no longer asks the two things these cases are about:\n{rule}"
        );
    }

    /// Two windows on screen, and nothing set yet.
    fn two() -> (HashSet<&'static str>, Vec<&'static str>) {
        (
            HashSet::new(),
            vec![crate::QUICKBAR_LABEL, crate::windows::FLOATING_LABEL],
        )
    }

    #[test]
    fn the_first_sweep_sets_every_window_it_can_see() {
        let (mut reached, present) = two();
        let set = to_set(true, None, &mut reached, &present);
        assert_eq!(set, present, "a window was left unset on the first sweep");
        assert_eq!(reached.len(), 2, "the sweep forgot what it had just set");
    }

    #[test]
    fn a_tick_that_changes_nothing_asks_nothing() {
        // The watch runs every five seconds for the whole life of the app.
        let (mut reached, present) = two();
        to_set(true, None, &mut reached, &present);
        assert!(
            to_set(true, Some(true), &mut reached, &present).is_empty(),
            "a locked-down PC is re-set every five seconds for nothing"
        );
    }

    #[test]
    fn the_answer_changing_sets_every_window_again() {
        // BOTH halves of the feature. The second is the one that matters most:
        // if turning the lock off did not re-set these, the screen would stay
        // uncapturable after the owner came back - a block left ON, which is
        // exactly the failure this test exists to catch.
        let (mut reached, present) = two();
        let on = to_set(true, None, &mut reached, &present);
        assert_eq!(on.len(), 2, "the lock did not set the windows");
        let off = to_set(false, Some(true), &mut reached, &present);
        assert_eq!(off, present, "the unlock did not clear the block");
    }

    #[test]
    fn a_window_built_later_is_set_as_soon_as_it_appears() {
        // The floating face can be switched on while the app is already locked.
        let (mut reached, present) = two();
        to_set(true, None, &mut reached, &present);
        // It is not on screen, so it is forgotten rather than counted as done.
        let fewer = vec![crate::QUICKBAR_LABEL];
        assert!(to_set(true, Some(true), &mut reached, &fewer).is_empty());
        assert!(!reached.contains(crate::windows::FLOATING_LABEL));
        // It appears. Nothing has changed about the lock, but it is new.
        let set = to_set(true, Some(true), &mut reached, &present);
        assert_eq!(
            set,
            vec![crate::windows::FLOATING_LABEL],
            "a window built while locked waited for the next change to be set"
        );
    }

    #[test]
    fn the_windows_are_the_ones_jarvis_puts_its_words_in() {
        // A list, so a window added later is a deliberate choice rather than a
        // silent hole. Every label must be one this app really has.
        for label in SNAPSHOT_LABELS {
            assert!(
                [
                    crate::QUICKBAR_LABEL,
                    crate::HUD_LABEL,
                    crate::windows::WIDGET_LABEL,
                    crate::windows::FLOATING_LABEL,
                    crate::windows::BRAIN_LABEL,
                    crate::windows::SETTINGS_LABEL,
                    crate::windows::FACES_LABEL,
                    crate::windows::FEATURES_LABEL,
                    crate::windows::ONBOARDING_LABEL,
                ]
                .contains(&label),
                "{label} is not a window this app builds"
            );
        }
        // The two badges are deliberately absent: their whole job is to say
        // Jarvis is listening or looking, and a capture that misses them would
        // hide the notice rather than the secret.
        assert!(
            !SNAPSHOT_LABELS.contains(&crate::live::BADGE_LABEL)
                && !SNAPSHOT_LABELS.contains(&crate::look::BADGE_LABEL),
            "a badge that says Jarvis is watching must stay in a capture"
        );
    }
}

// ---------------------------------------------------------------------------
// The real thing, on the real Windows
// ---------------------------------------------------------------------------
//
// Everything above decides; this measures. `cargo test` runs on Windows in CI
// (ci.yml's `rust` job), so this is checked there too, and skips - loudly, as
// a pass with a printed reason - rather than failing a machine with no
// desktop, which is not this feature being wrong.
#[cfg(all(test, windows))]
mod capture_probe {
    use super::*;
    use image::RgbaImage;
    // `writeln!` on the process's own stderr handle, in `skipped_by_env` below.
    use std::io::Write;
    use windows_sys::Win32::Foundation::HWND;
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DestroyWindow, GetWindowDisplayAffinity, GetWindowRect, IsWindowVisible,
        SetWindowDisplayAffinity, ShowWindow, SW_SHOWNOACTIVATE, WDA_EXCLUDEFROMCAPTURE, WDA_NONE,
        WS_EX_TOOLWINDOW, WS_POPUP, WS_VISIBLE,
    };

    /// One window, one screen. Taken for real: the exclusion is a property of
    /// the desktop, not of this process, so two of these at once would be
    /// measuring each other's windows.
    static ONE_AT_A_TIME: Mutex<()> = Mutex::new(());

    /// This probe's own window class - not a stock one, so that giving it a red
    /// background brush cannot repaint anything else on the owner's desktop.
    const CLASS: &[u16] = &[
        b'J' as u16,
        b'a' as u16,
        b'r' as u16,
        b'v' as u16,
        b'i' as u16,
        b's' as u16,
        b'C' as u16,
        b'a' as u16,
        b'p' as u16,
        b't' as u16,
        b'u' as u16,
        b'r' as u16,
        b'e' as u16,
        b'P' as u16,
        b'r' as u16,
        b'o' as u16,
        b'b' as u16,
        b'e' as u16,
        0,
    ];
    /// `COLORREF`, which is 0x00BBGGRR - so this is a pure red.
    const RED: u32 = 0x0000_00FF;
    const SIZE: i32 = 240;

    fn wide(text: &str) -> Vec<u16> {
        text.encode_utf16().chain(std::iter::once(0)).collect()
    }

    /// A visible top-level window of our own class, 240 by 240, filled red, with
    /// its top-left corner at `(x, y)`. `None` when Windows will not give us a
    /// window at all - no interactive desktop, a session with no window station.
    unsafe fn red_window(x: i32, y: i32) -> Option<HWND> {
        use windows_sys::Win32::Graphics::Gdi::CreateSolidBrush;
        use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            DefWindowProcW, RegisterClassW, WNDCLASSW,
        };

        let module = GetModuleHandleW(std::ptr::null());
        // A red brush as the class background: `DefWindowProcW` erases with it,
        // so the window is red with no paint code of ours. Freed when the
        // process exits - one brush, for one test.
        let class = WNDCLASSW {
            style: 0,
            lpfnWndProc: Some(DefWindowProcW),
            cbClsExtra: 0,
            cbWndExtra: 0,
            hInstance: module,
            hIcon: std::ptr::null_mut(),
            hCursor: std::ptr::null_mut(),
            hbrBackground: CreateSolidBrush(RED),
            lpszMenuName: std::ptr::null(),
            lpszClassName: CLASS.as_ptr(),
        };
        // 0 means the class already exists, which is fine: the test binary runs
        // this once, and a second registration of the same name is not an error
        // we care about.
        RegisterClassW(&class);

        let title = wide("Jarvis capture probe");
        let hwnd = CreateWindowExW(
            WS_EX_TOOLWINDOW,
            CLASS.as_ptr(),
            title.as_ptr(),
            WS_POPUP | WS_VISIBLE,
            x,
            y,
            SIZE,
            SIZE,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            module,
            std::ptr::null(),
        );
        if hwnd.is_null() {
            return None;
        }
        ShowWindow(hwnd, SW_SHOWNOACTIVATE);
        Some(hwnd)
    }

    fn affinity(hwnd: HWND) -> Option<u32> {
        let mut value = WDA_NONE;
        // SAFETY: a plain Win32 read of an attribute of a window we own.
        let ok = unsafe { GetWindowDisplayAffinity(hwnd, &mut value) };
        (ok != 0).then_some(value)
    }

    fn set(hwnd: HWND, value: u32) -> bool {
        // SAFETY: an attribute write on a window this test created.
        unsafe { SetWindowDisplayAffinity(hwnd, value) != 0 }
    }

    /// Red pixels anywhere in `frame`.
    fn red_in(frame: &RgbaImage) -> u32 {
        frame
            .pixels()
            .filter(|p| p[0] > 180 && p[1] < 90 && p[2] < 90)
            .count() as u32
    }

    /// The documented way out of the probe below, for anyone working at this
    /// PC: `JARVIS_SKIP_WINDOW_TESTS=1` in the environment and the probe never
    /// runs.
    ///
    /// Why a helper and not `#[ignore]`: `#[ignore]` inverts the default, so
    /// every ordinary run would lose the probe; it cannot be driven by an
    /// environment variable; and it prints `ignored`, which this project does
    /// not accept in place of "did not run". The guard keeps the default the
    /// right way round - the probe runs - and the opt-out is explicit.
    ///
    /// The line is written through the process's own `stderr` handle rather
    /// than with `eprintln!`, and that is measured, not assumed: **libtest
    /// captures `eprintln!` exactly as it captures `println!`**, so this line
    /// was invisible in a plain `cargo test` run until it was written this way
    /// (checked at this PC's terminal, 1.99.0). `--nocapture` is the usual way
    /// to see a captured line, and the whole point is the run where someone
    /// has NOT passed it and still needs to know the probe did not run.
    ///
    /// This is the project's rule, not a nicety: **BLOCKED and NOT-TESTABLE
    /// are never counted as passes**, so a skipped test says so out loud.
    fn skipped_by_env(what: &str) -> bool {
        let skip = std::env::var("JARVIS_SKIP_WINDOW_TESTS").is_ok_and(|v| v == "1");
        if skip {
            // The handle, not the macro: see this function's doc above.
            let mut err = std::io::stderr();
            let _ = writeln!(
                err,
                "SKIPPED  {what} - this test opens a window or reads the screen, and \
                 JARVIS_SKIP_WINDOW_TESTS=1 is set. It did NOT run, and it did NOT pass. Unset \
                 that variable to run it."
            );
            let _ = err.flush();
        }
        skip
    }

    /// The opt-out itself must be the documented one, the guard at the top of
    /// the probe must still be there, and this must still be the ONLY test that
    /// needs the opt-out - every other source file in the crate is included
    /// below, so a second desktop-needing test fails to compile until it is
    /// added to that list on purpose. A gate that quietly stopped working would
    /// put the red window back on the owner's screen, so a rename here is
    /// caught rather than discovered. Reads the source, so it needs no desktop
    /// and never opens one.
    #[test]
    fn the_window_probe_is_the_only_test_the_opt_out_guards() {
        let src = include_str!("lock.rs");
        assert!(
            src.contains(r#"std::env::var("JARVIS_SKIP_WINDOW_TESTS")"#),
            "the opt-out is no longer JARVIS_SKIP_WINDOW_TESTS"
        );
        let probe = &src[src
            .find("fn the_exclusion_is_real_and_reversible_on_this_pc")
            .expect("the probe")..];
        let body = &probe[..probe.find("\n    }\n").expect("its end")];
        assert!(
            body.contains("skipped_by_env("),
            "the probe no longer asks to be skipped, so it will open a red window on \
             every run:\n{body}"
        );

        // Every other file of the crate, which is what makes the name above
        // true rather than merely confident. Built by hand rather than by a
        // directory walk so the list is visible and a new file is a deliberate
        // edit: the failure mode this guards - a second test that opens a
        // window - arrives as a new file or a new test in one of these.
        const ELSEWHERE: &[&str] = &[
            include_str!("account_addresses.rs"),
            include_str!("account_secrets.rs"),
            include_str!("aec.rs"),
            include_str!("animal.rs"),
            include_str!("appearance.rs"),
            include_str!("asks_first.rs"),
            include_str!("attention.rs"),
            include_str!("attention/state.rs"),
            include_str!("autostart.rs"),
            include_str!("backup.rs"),
            include_str!("brain.rs"),
            include_str!("brain/auto_learn.rs"),
            include_str!("brain/briefing.rs"),
            include_str!("brain/chatbot.rs"),
            include_str!("brain/conversation_facts.rs"),
            include_str!("brain/decks.rs"),
            include_str!("brain/fact_history.rs"),
            include_str!("brain/focus.rs"),
            include_str!("brain/forget_range.rs"),
            include_str!("brain/form_review.rs"),
            include_str!("brain/goals.rs"),
            include_str!("brain/history.rs"),
            include_str!("brain/history_import.rs"),
            include_str!("brain/inbox_tidy.rs"),
            include_str!("brain/photo_reminder.rs"),
            include_str!("brain/pictures.rs"),
            include_str!("brain/profile.rs"),
            include_str!("brain/progress.rs"),
            include_str!("brain/projects.rs"),
            include_str!("brain/quiz.rs"),
            include_str!("brain/quiz_cloud.rs"),
            include_str!("brain/retirement.rs"),
            include_str!("brain/routes.rs"),
            include_str!("brain/schedule.rs"),
            include_str!("brain/shared.rs"),
            include_str!("brain/sources.rs"),
            include_str!("brain/support.rs"),
            include_str!("brain/topics.rs"),
            include_str!("brain/used.rs"),
            include_str!("brain/widgets.rs"),
            include_str!("brain/youtube.rs"),
            include_str!("browser_engine.rs"),
            include_str!("chatbot_money.rs"),
            include_str!("clipboard_privacy.rs"),
            include_str!("commands.rs"),
            include_str!("crash_notes.rs"),
            include_str!("devices.rs"),
            include_str!("email_sending.rs"),
            include_str!("folders.rs"),
            include_str!("handoff.rs"),
            include_str!("hardware.rs"),
            include_str!("hotkeys.rs"),
            include_str!("hud_proxy.rs"),
            include_str!("lib.rs"),
            include_str!("limits.rs"),
            include_str!("live.rs"),
            include_str!("lock/rules.rs"),
            include_str!("logfile.rs"),
            include_str!("look.rs"),
            include_str!("main.rs"),
            include_str!("notifications.rs"),
            include_str!("open_app.rs"),
            include_str!("plain_errors.rs"),
            include_str!("proctree.rs"),
            include_str!("prompt_coach.rs"),
            include_str!("pyfind.rs"),
            include_str!("reach.rs"),
            include_str!("screen_work.rs"),
            include_str!("sidecar.rs"),
            include_str!("sky.rs"),
            include_str!("spec.rs"),
            include_str!("spec_drift.rs"),
            include_str!("spending.rs"),
            include_str!("sse.rs"),
            include_str!("stream.rs"),
            include_str!("system_theme.rs"),
            include_str!("talk_type.rs"),
            include_str!("talk_type/paste_tx.rs"),
            include_str!("talk_type/paste_windows.rs"),
            include_str!("talk_type/rules.rs"),
            include_str!("token_store.rs"),
            include_str!("tool_updates.rs"),
            include_str!("tray.rs"),
            include_str!("tutorials.rs"),
            include_str!("update.rs"),
            include_str!("vision.rs"),
            include_str!("voice.rs"),
            include_str!("voice_flow.rs"),
            include_str!("voice_training.rs"),
            include_str!("web_search.rs"),
            include_str!("window_memory.rs"),
            include_str!("windows.rs"),
            include_str!("winrt_toast.rs"),
        ];
        for (i, other) in ELSEWHERE.iter().enumerate() {
            assert!(
                !other.contains("skipped_by_env"),
                "file {i} of the list above calls `skipped_by_env`, so this test's name is \
                 now wrong: add it here on purpose"
            );
        }
    }

    #[test]
    fn the_exclusion_is_real_and_reversible_on_this_pc() {
        if skipped_by_env("the_exclusion_is_real_and_reversible_on_this_pc") {
            return;
        }
        let _one = ONE_AT_A_TIME.lock().unwrap_or_else(|p| p.into_inner());

        // The primary display, and the capture of a small region of it around
        // the probe window. A region rather than the whole display: it says
        // exactly which pixels were looked at, and it is quick.
        let Ok(monitors) = xcap::Monitor::all() else {
            println!("SKIP  the exclusion is real: no displays were reported");
            return;
        };
        let Some(monitor) = monitors
            .iter()
            .find(|m| m.is_primary().unwrap_or(false))
            .or_else(|| monitors.first())
        else {
            println!("SKIP  the exclusion is real: no display to put a window on");
            return;
        };
        let (mx, my) = match (monitor.x(), monitor.y()) {
            (Ok(x), Ok(y)) => (x, y),
            _ => {
                println!("SKIP  the exclusion is real: the display gave no position");
                return;
            }
        };
        let (mw, mh) = (monitor.width().unwrap_or(0), monitor.height().unwrap_or(0));

        // Just inside the top-left corner of that display: clear of the centre,
        // and clear of the taskbar.
        let (wx, wy) = (mx + 40, my + 40);
        // SAFETY: creating our own window is the point of the probe.
        let Some(hwnd) = (unsafe { red_window(wx, wy) }) else {
            println!("SKIP  the exclusion is real: no desktop to put a window on");
            return;
        };
        // The window's own screen coordinates, as Windows now sees them - not
        // as they were asked for, so a desktop that moved it says so.
        // SAFETY: reads of our own window's state.
        let mut rect = windows_sys::Win32::Foundation::RECT {
            left: wx,
            top: wy,
            right: wx + SIZE,
            bottom: wy + SIZE,
        };
        // SAFETY: a plain Win32 read into a local.
        let placed = unsafe { GetWindowRect(hwnd, &mut rect) } != 0;
        let visible = unsafe { IsWindowVisible(hwnd) } != 0;

        // A 40 px inset of that window, in the display's own coordinates: the
        // part of the picture this probe looks at. Inset, so a border or a
        // shadow is never what is being judged.
        let region = (
            (rect.left - mx + 40).max(0) as u32,
            (rect.top - my + 40).max(0) as u32,
            160,
            160,
        );

        /// One capture of the probe's region, or a printed reason this machine
        /// cannot make it.
        fn grab(
            monitor: &xcap::Monitor,
            region: (u32, u32, u32, u32),
            why: &str,
        ) -> Option<RgbaImage> {
            let frame = match monitor.capture_region(region.0, region.1, region.2, region.3) {
                Ok(frame) => frame,
                Err(_) => {
                    println!("SKIP  the exclusion is real: {why}");
                    return None;
                }
            };
            let (w, h) = (frame.width(), frame.height());
            match RgbaImage::from_raw(w, h, frame.into_raw()) {
                Some(image) => Some(image),
                None => {
                    println!("SKIP  the exclusion is real: a capture had an unexpected size");
                    None
                }
            }
        }

        // Every pixel of a frame, since the frame IS the region now.
        // A moment for the desktop to draw the window first: one this process
        // has just asked for is not necessarily composited on the next line,
        // and every reading below is of what is on screen.
        std::thread::sleep(std::time::Duration::from_millis(700));

        // 1. NOT excluded: the capture must see the window. This is the
        //    CONTROL - without it, "nothing red" below would also pass on a
        //    machine where the capture was simply broken.
        let Some(before) = grab(monitor, region, "this machine will not capture the screen") else {
            // SAFETY: our own window.
            unsafe { DestroyWindow(hwnd) };
            return;
        };
        let before = red_in(&before);

        // 2. Excluded, through the same call the shipped code makes.
        let applied = set(hwnd, WDA_EXCLUDEFROMCAPTURE);
        let read_back = affinity(hwnd);
        let Some(while_out) = grab(monitor, region, "the second capture failed") else {
            // SAFETY: our own window.
            unsafe { DestroyWindow(hwnd) };
            return;
        };
        let after = red_in(&while_out);

        // 3. Cleared again: the same thing the unlock path does.
        let cleared = set(hwnd, WDA_NONE);
        let restored = affinity(hwnd);
        let back = grab(monitor, region, "the third capture failed").map(|frame| red_in(&frame));

        // SAFETY: our own window.
        unsafe { DestroyWindow(hwnd) };

        println!(
            "the exclusion on this PC: red before={before}, red while excluded={after}, \
             red after clearing={back:?} (display {mw}x{mh} at {mx},{my}); \
             window placed={placed} visible={visible} at {:?}; set={applied} read back \
             {read_back:?}; clear={cleared} read back {restored:?}",
            (rect.left, rect.top)
        );

        assert!(
            applied,
            "Windows refused WDA_EXCLUDEFROMCAPTURE on our own window"
        );
        assert_eq!(
            read_back,
            Some(WDA_EXCLUDEFROMCAPTURE),
            "the attribute did not stick"
        );
        assert_eq!(restored, Some(WDA_NONE), "the attribute would not clear");

        // The attribute is set and read back correctly. What is left is
        // whether the pixels really go - and that needs a desktop that puts the
        // window on screen in the first place.
        if before == 0 {
            // A skip, said plainly, never as a quiet pass. A session with no
            // interactive desktop (a service, a CI runner, a session whose
            // windows are never composited onto the captured screen) captures
            // the screen happily and never shows a window on it, ours or
            // anyone's. Measured on this project's own machine, 2026-10-11:
            // 293 colours in a screen capture, and a plainly visible window
            // absent from it.
            println!(
                "SKIP  the exclusion is real: this session captures the screen but never \
                 shows a window on it, so the pixels cannot be judged here"
            );
            return;
        }
        assert_eq!(
            after, 0,
            "the window's pixels are STILL in a screen capture while excluded"
        );
        assert!(
            matches!(back, Some(n) if n > 0),
            "the window stayed out of the capture after the exclusion was cleared"
        );
    }
}
