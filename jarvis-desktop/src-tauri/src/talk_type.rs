//! Talk-to-type on the PC: hold a key, speak, and Jarvis types what you said
//! into the program in front.
//!
//! The owner's decision (2026-09-27): "Talk-to-type on the PC: one approval
//! card to switch it on, then no card each time. Hold a key, speak, and
//! Jarvis types what was said into the program in front - speech-to-text on
//! the PC only, as always. Switching it off is immediate. Not on the phone
//! (a client must not do speech-to-text)." docs/JARVIS-API.md section 72.
//!
//! ## The switch lives on the PC, like every voice setting
//!
//! `gate.talk_to_type` in `GET /api/voice/status`, changed through
//! `POST /api/voice/enroll {"mode": "talk_to_type", "value": "on"|"off"}`
//! (Settings, Voice; `voice_training::set_voice_setting`): ON raises ONE
//! approval card (`change_own_config`), OFF is at once. Nothing here can turn
//! it on. The PC also refuses a `source=talk_to_type` clip by itself while
//! it is off (jarvis_speech.hear), before the clip is read at all.
//!
//! ## One press, start to finish
//!
//! 1. The key goes down (`Alt+Shift+T` unless the owner changed it). The
//!    window in front is remembered. Before the microphone opens: the event
//!    stream must be live (rule 4), App lock must not be locked, Jarvis must
//!    be on THIS PC (the audio never leaves it), nothing else may hold the
//!    microphone, and the PC must say the switch is on.
//! 2. The microphone records into memory. The tray icon (and the floating
//!    face, when it is shown) says "listening". Let go after a HOLD and it
//!    stops; a quick TAP keeps it listening until the key is pressed again.
//!    Two minutes at most, then it stops by itself.
//! 3. The clip goes to the Jarvis server on this PC over loopback, as
//!    `source=talk_to_type`. The server does what it does for every clip:
//!    is there speech, is it the owner's voice - and only then the words.
//!    It cleans out "um" and "uh", keeps nothing (no chat history), and the
//!    words come back here once.
//! 4. Checked again: still live, still unlocked, not stopped. Then, on a
//!    thread of its own: every modifier key let go, the SAME window still in
//!    front, and the box with the focus not a password box
//!    (paste_windows.rs). Then pasted - the clipboard way Handy does it -
//!    and the owner's clipboard put back.
//!
//! Any refusal is one notification in plain words. The words spoken are
//! never in a notification, a log line or a file.
//!
//! "Stop everything" ends all of it at once: the microphone closes, the clip
//! is dropped, and nothing is typed.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter, Manager};

#[cfg(windows)]
mod paste_tx;
#[cfg(windows)]
mod paste_windows;
mod rules;

pub(crate) use rules::TRAY_LISTENING;
use rules::*;

/// The hotkey action's id (hotkeys.rs `ACTIONS`).
pub const ACTION_ID: &str = "talk_to_type";
/// Sent to the floating face: `true` while talk-to-type is listening.
pub const LISTENING_EVENT: &str = "talk-type-listening";

/// Listening right now - read by the tray to show "listening".
static LISTENING: AtomicBool = AtomicBool::new(false);

/// True while talk-to-type holds the microphone.
pub fn listening() -> bool {
    LISTENING.load(Ordering::SeqCst)
}

struct Capture {
    stop_tx: mpsc::Sender<()>,
    samples: Arc<Mutex<Vec<i16>>>,
    spec: hound::WavSpec,
    join: JoinHandle<()>,
}

#[derive(Default)]
enum Phase {
    #[default]
    Idle,
    /// The key went down; the checks and the microphone are on their way.
    Starting {
        gen: u64,
        pressed_at: Instant,
        released_at: Option<Instant>,
        target: isize,
    },
    Recording {
        gen: u64,
        capture: Capture,
        pressed_at: Instant,
        /// A tap: keep listening until the key is pressed again.
        latched: bool,
        target: isize,
    },
    /// Sent to the PC, then typed. The microphone is already closed.
    Finishing { gen: u64 },
}

impl Phase {
    fn gen(&self) -> Option<u64> {
        match self {
            Phase::Idle => None,
            Phase::Starting { gen, .. }
            | Phase::Recording { gen, .. }
            | Phase::Finishing { gen } => Some(*gen),
        }
    }
}

/// Managed state (lib.rs).
#[derive(Default)]
pub struct TalkTypeState {
    phase: Mutex<Phase>,
    /// Bumped by every new press and by Stop everything: a step that finds
    /// it changed stops, and types nothing.
    generation: AtomicU64,
    /// When the PC last said the switch is on.
    on_seen: Mutex<Option<Instant>>,
}

impl TalkTypeState {
    fn phase(&self) -> MutexGuard<'_, Phase> {
        self.phase.lock().unwrap_or_else(|p| p.into_inner())
    }

    /// Talk-to-type holds, or is about to hold, the microphone. Read by the
    /// talk button, "hey Jarvis" listening and Settings' recorder, which
    /// must not open a second capture on the same device.
    pub(crate) fn mic_busy(&self) -> bool {
        matches!(
            *self.phase(),
            Phase::Starting { .. } | Phase::Recording { .. }
        )
    }

    fn current(&self, gen: u64) -> bool {
        self.generation.load(Ordering::SeqCst) == gen
    }
}

/// Settings turned the switch off: ask the PC again next time.
pub fn forget_switch(app: &AppHandle) {
    *app.state::<TalkTypeState>()
        .on_seen
        .lock()
        .unwrap_or_else(|p| p.into_inner()) = None;
}

fn set_listening(app: &AppHandle, on: bool) {
    if LISTENING.swap(on, Ordering::SeqCst) == on {
        return;
    }
    crate::tray::refresh(app);
    let _ = app.emit_to(crate::windows::FLOATING_LABEL, LISTENING_EVENT, on);
}

fn tell(app: &AppHandle, why: &str) {
    crate::commands::notify(app, TITLE, why);
}

/// Back to idle, if `gen` is still the session in charge.
fn end_if(app: &AppHandle, gen: u64) {
    let state = app.state::<TalkTypeState>();
    let mut phase = state.phase();
    if phase.gen() == Some(gen) {
        *phase = Phase::Idle;
        drop(phase);
        set_listening(app, false);
    }
}

// ---------------------------------------------------------------------------
// The hotkey
// ---------------------------------------------------------------------------

/// The talk-to-type key went down (`pressed`) or up. From lib.rs's
/// shortcut handler - the only action there that reads key-up as well.
pub fn on_hotkey(app: &AppHandle, pressed: bool) {
    if pressed {
        on_press(app);
    } else {
        on_release(app);
    }
}

fn on_press(app: &AppHandle) {
    let state = app.state::<TalkTypeState>();
    let now = Instant::now();
    let mut phase = state.phase();
    match &*phase {
        Phase::Idle => {
            let gen = state.generation.fetch_add(1, Ordering::SeqCst) + 1;
            *phase = Phase::Starting {
                gen,
                pressed_at: now,
                released_at: None,
                target: foreground(),
            };
            drop(phase);
            let app = app.clone();
            tauri::async_runtime::spawn(async move { start(app, gen).await });
        }
        Phase::Recording { latched: true, .. } => {
            let taken = std::mem::take(&mut *phase);
            if let Phase::Recording {
                gen,
                capture,
                target,
                ..
            } = taken
            {
                *phase = Phase::Finishing { gen };
                drop(phase);
                spawn_finish(app, gen, capture, target);
            }
        }
        // Already starting, held down, or typing: a second press waits.
        _ => {}
    }
}

fn on_release(app: &AppHandle) {
    let state = app.state::<TalkTypeState>();
    let now = Instant::now();
    let mut phase = state.phase();
    match &mut *phase {
        Phase::Starting { released_at, .. } => {
            *released_at = Some(now);
            return;
        }
        Phase::Recording {
            latched,
            pressed_at,
            ..
        } if !*latched => {
            if is_tap(now.duration_since(*pressed_at)) {
                // A tap: carry on listening until the next press.
                *latched = true;
                return;
            }
        }
        // Idle, typing, or a tap already listening: key-up means nothing.
        _ => return,
    }
    // A hold, let go: stop listening and type.
    if let Phase::Recording {
        gen,
        capture,
        target,
        ..
    } = std::mem::take(&mut *phase)
    {
        *phase = Phase::Finishing { gen };
        drop(phase);
        spawn_finish(app, gen, capture, target);
    }
}

/// "Stop everything" (commands.rs `stop_everything_now`): the microphone
/// closes, the clip is dropped, and nothing that is still on its way is
/// typed. Never held by anything.
pub fn stop(app: &AppHandle) {
    let state = app.state::<TalkTypeState>();
    state.generation.fetch_add(1, Ordering::SeqCst);
    let old = std::mem::take(&mut *state.phase());
    if let Phase::Recording { capture, .. } = old {
        // Not joined: this must not wait on the microphone closing.
        let _ = capture.stop_tx.send(());
    }
    set_listening(app, false);
}

// ---------------------------------------------------------------------------
// Starting: the checks, then the microphone
// ---------------------------------------------------------------------------

/// Rule 4, App lock, and "this PC only" - asked before listening and again
/// before typing.
fn may_act(app: &AppHandle) -> Result<(), &'static str> {
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(STALE);
    }
    if crate::lock::locked_now(app) {
        return Err(LOCKED);
    }
    if !crate::voice::is_loopback_base(&crate::commands::jarvis_base(app)) {
        return Err(NOT_THIS_PC);
    }
    Ok(())
}

fn mic_free(app: &AppHandle) -> Result<(), &'static str> {
    // Live first: its listener is the same one "hey Jarvis" uses, so the
    // check below would blame "hey Jarvis" - and a paused Live has no
    // listener open at all, yet will want the microphone back. (Jarvis Live
    // owns the microphone while it is on, also while closed for a pause,
    // exactly as for the talk button - voice.rs start_voice_capture.)
    if crate::voice::LIVE_MODE.load(Ordering::SeqCst) {
        return Err(MIC_LIVE);
    }
    if app.state::<crate::voice::AutoListenState>().busy() {
        return Err(MIC_WAKE);
    }
    if app.state::<crate::voice::VoiceCaptureState>().busy() {
        return Err(MIC_TALK);
    }
    if app
        .state::<crate::voice_training::SampleState>()
        .recording()
    {
        return Err(crate::voice_training::MIC_IN_SETTINGS);
    }
    Ok(())
}

/// Is the switch on? Asked of the PC, unless it said "on" a moment ago.
async fn switch_on(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<TalkTypeState>();
    let recent = state
        .on_seen
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .is_some_and(|at| at.elapsed() < SWITCH_TRUSTED_FOR);
    if recent {
        return Ok(());
    }
    let status = crate::voice::get_voice_status(app.clone())
        .await
        .map_err(|e| format!("{} Nothing was typed.", sentence(&e)))?;
    match switch_from_status(&status) {
        Switch::On => {
            *state.on_seen.lock().unwrap_or_else(|p| p.into_inner()) = Some(Instant::now());
            Ok(())
        }
        Switch::Off => Err(OFF.to_string()),
        Switch::NotOnThisPc => Err(NOT_ON_THIS_PC.to_string()),
    }
}

async fn start(app: AppHandle, gen: u64) {
    let checked = match may_act(&app).and_then(|()| mic_free(&app)) {
        Err(why) => Err(why.to_string()),
        Ok(()) => switch_on(&app).await,
    };
    if let Err(why) = checked {
        end_if(&app, gen);
        if app.state::<TalkTypeState>().current(gen) {
            tell(&app, &why);
        }
        return;
    }
    // Stopped (Stop everything) while the PC was asked: the microphone is
    // not opened at all.
    if !app.state::<TalkTypeState>().current(gen) {
        return;
    }
    // Asked again right before opening: the round trip above was an await.
    if let Err(why) = mic_free(&app) {
        end_if(&app, gen);
        tell(&app, why);
        return;
    }

    // Before the microphone opens: an animal's "Try it" playing in Settings
    // stops now, as it does for the talk button (voice.rs), so it is not
    // typed into the owner's words.
    crate::emit_all(&app, crate::events::VOICE_CAPTURE_STARTED, ());

    let opener = app.clone();
    let opened = tauri::async_runtime::spawn_blocking(move || open_microphone(opener, gen))
        .await
        .unwrap_or_else(|e| Err(format!("the microphone could not be opened: {e}")));
    let capture = match opened {
        Ok(capture) => capture,
        Err(why) => {
            end_if(&app, gen);
            tell(&app, &format!("{} Nothing was typed.", sentence(&why)));
            return;
        }
    };

    let state = app.state::<TalkTypeState>();
    let mut phase = state.phase();
    let (pressed_at, released_at, target) = match &*phase {
        Phase::Starting {
            gen: g,
            pressed_at,
            released_at,
            target,
        } if *g == gen => (*pressed_at, *released_at, *target),
        _ => {
            // Stopped while the microphone was opening: close it, keep nothing.
            drop(phase);
            let _ = capture.stop_tx.send(());
            return;
        }
    };
    match released_at {
        // Let go after a long hold while the microphone was still opening:
        // it heard nothing worth sending. Close it and say why.
        Some(at) if !is_tap(at.duration_since(pressed_at)) => {
            *phase = Phase::Idle;
            drop(phase);
            let _ = capture.stop_tx.send(());
            tell(&app, MIC_SLOW);
        }
        released => {
            *phase = Phase::Recording {
                gen,
                capture,
                pressed_at,
                latched: released.is_some(),
                target,
            };
            drop(phase);
            set_listening(&app, true);
        }
    }
}

/// Opens the default microphone into memory. Blocking (it waits for the
/// device), so it runs on a blocking thread.
fn open_microphone(app: AppHandle, gen: u64) -> Result<Capture, String> {
    let samples: Arc<Mutex<Vec<i16>>> = Arc::new(Mutex::new(Vec::new()));
    let (ready_tx, ready_rx) = mpsc::channel();
    let (stop_tx, stop_rx) = mpsc::channel();
    let join = crate::voice::spawn_capture_thread(
        Arc::clone(&samples),
        ready_tx,
        stop_rx,
        move |_samples, _spec, stop_rx| {
            let began = Instant::now();
            loop {
                match stop_rx.recv_timeout(Duration::from_millis(200)) {
                    Ok(()) | Err(mpsc::RecvTimeoutError::Disconnected) => return,
                    Err(mpsc::RecvTimeoutError::Timeout) => {}
                }
                if began.elapsed() >= MAX_LISTEN {
                    // Two minutes: stop listening and type what was said.
                    limit_reached(&app, gen);
                    return;
                }
            }
        },
    );
    match crate::voice::wait_for_ready(ready_rx, stop_tx.clone()) {
        Ok(spec) => Ok(Capture {
            stop_tx,
            samples,
            spec,
            join,
        }),
        Err(why) => {
            let _ = join.join();
            Err(why)
        }
    }
}

/// The two minutes are up (from the capture thread itself).
fn limit_reached(app: &AppHandle, gen: u64) {
    let state = app.state::<TalkTypeState>();
    let mut phase = state.phase();
    if !matches!(&*phase, Phase::Recording { gen: g, .. } if *g == gen) {
        return;
    }
    if let Phase::Recording {
        capture, target, ..
    } = std::mem::take(&mut *phase)
    {
        *phase = Phase::Finishing { gen };
        drop(phase);
        spawn_finish(app, gen, capture, target);
    }
}

// ---------------------------------------------------------------------------
// Finishing: the words, then the typing
// ---------------------------------------------------------------------------

fn spawn_finish(app: &AppHandle, gen: u64, capture: Capture, target: isize) {
    set_listening(app, false);
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let outcome = finish(&app, gen, capture, target).await;
        let still_ours = app.state::<TalkTypeState>().current(gen);
        end_if(&app, gen);
        if let Err(why) = outcome {
            // A stopped session says nothing: Stop everything tells the
            // owner what it stopped.
            if still_ours {
                tell(&app, &why);
            }
        }
    });
}

async fn finish(app: &AppHandle, gen: u64, capture: Capture, target: isize) -> Result<(), String> {
    let Capture {
        stop_tx,
        samples,
        spec,
        join,
    } = capture;
    let _ = stop_tx.send(());
    let _ = tauri::async_runtime::spawn_blocking(move || join.join()).await;
    let samples = Arc::try_unwrap(samples)
        .map(|m| m.into_inner().unwrap_or_else(|p| p.into_inner()))
        .unwrap_or_else(|arc| arc.lock().map(|g| g.clone()).unwrap_or_default());

    let state = app.state::<TalkTypeState>();
    if !state.current(gen) {
        return Ok(());
    }
    if samples.is_empty() {
        return Err(NOTHING_HEARD.to_string());
    }
    if crate::voice::clip_length(spec, &samples) > MAX_LISTEN + Duration::from_secs(1) {
        return Err(TOO_LONG.to_string());
    }
    may_act(app).map_err(str::to_string)?;

    // Loopback only (may_act), and read once: the address checked is the
    // address sent to.
    let base = crate::commands::jarvis_base(app);
    let reply =
        crate::voice::post_utterance(app, &base, spec, &samples, "talk_to_type", None).await?;
    drop(samples);
    let words = words_to_type(&reply)?;

    if !state.current(gen) {
        return Ok(());
    }
    may_act(app).map_err(str::to_string)?;

    let checker = app.clone();
    let wanted = move || checker.state::<TalkTypeState>().current(gen);
    tauri::async_runtime::spawn_blocking(move || type_into(target, &words, &wanted))
        .await
        .map_err(|e| format!("Typing stopped unexpectedly ({e}). Nothing was typed."))?
}

// ---------------------------------------------------------------------------
// Typing (Windows)
// ---------------------------------------------------------------------------

#[cfg(windows)]
fn foreground() -> isize {
    paste_windows::foreground_root()
}

#[cfg(not(windows))]
fn foreground() -> isize {
    0
}

/// Every check before the paste, then the paste. Blocking.
#[cfg(windows)]
fn type_into(target: isize, text: &str, wanted: &dyn Fn() -> bool) -> Result<(), String> {
    use paste_tx::Settled;

    if target == 0 {
        return Err(NO_TARGET.to_string());
    }
    if !paste_windows::wait_keys_up(KEYS_UP_WAIT) {
        return Err(KEYS_HELD.to_string());
    }
    if !wanted() {
        return Ok(());
    }
    if paste_windows::foreground_root() != target {
        return Err(MOVED.to_string());
    }
    // Refused when either check says password. When UI Automation cannot
    // answer at all (a program that does not support it, or hangs), the
    // plain Windows check has already run and found nothing - that is the
    // one gap, and docs/JARVIS-API.md section 72 says so.
    if paste_windows::focused_is_password() == Some(true) {
        return Err(PASSWORD.to_string());
    }
    if !wanted() {
        return Ok(());
    }
    match paste_windows::paste(text).map_err(|e| format!("{} Nothing was typed.", sentence(&e)))? {
        Settled::Read => Ok(()),
        Settled::NotRead => Err(NOT_TAKEN.to_string()),
        Settled::KeysRefused => Err(KEYS_REFUSED.to_string()),
    }
}

#[cfg(not(windows))]
fn type_into(_target: isize, _text: &str, _wanted: &dyn Fn() -> bool) -> Result<(), String> {
    Err(NEEDS_WINDOWS.to_string())
}
