//! Jarvis Live on this PC: a back-and-forth voice conversation the owner
//! starts and stops (the owner's decision and answers of 2026-09-28;
//! docs/LIVE-DESIGN.md; backend/jarvis_live.py is the session).
//!
//! WHAT THIS DOES
//! * **Start** (the Jarvis bar's Live button, or the tray's row): no card -
//!   Live is the owner's own act - but refused while the event stream is
//!   stale (rule 4) or App lock would ask Windows Hello, and refused by the
//!   PC itself until the owner's voice is trained (the voice check runs on
//!   every clip). Then `POST /api/voice/live {"do": "start", "device":
//!   "desktop"}`, the microphone in Live mode (voice.rs `open_for_live`:
//!   every sentence goes as `source=live`, checked for the owner's voice
//!   before any words exist - only ever to a server on THIS PC), the
//!   always-on-top "Jarvis Live" badge, and the watcher.
//! * **The watcher**, once a second while Live is on here, reads
//!   `GET /api/voice/live` and tells every window (`LIVE_STATUS`); the badge
//!   and the bar draw the sign from it (live-rules.js). It:
//!   - ends Live when App lock would ask again - or, when the owner chose
//!     "Only when Windows locks" (the voice setting `live_end`, a card;
//!     the PC's status says `end_on`), only when Windows is locked;
//!   - CLOSES the microphone - not just ignores it, so Windows' own
//!     microphone sign goes off too - while Live is muted, a card waits (or
//!     the queue cannot be read), the bar shows a card, the link is stale,
//!     it cannot tell whether Windows is locked, or the bar is speaking in
//!     "Interrupt by tap only"; it stays open, check-only, through a voice
//!     pause, so the owner's own voice carries on without a tap;
//!   - mutes Live while another program is using the microphone (a call),
//!     and unmutes it after - never undoing the owner's own Mute. When the
//!     microphone's use cannot be read, the sign says "Jarvis can't tell
//!     when you're on a call - use Mute";
//!   - when the PC says Live is not on here any more (the owner said
//!     "that's all", 90 quiet seconds, the time ran out, Stop everything,
//!     Standby, it moved to the phone), closes the microphone and the badge.
//! * **Stop** (the badge, the bar, the tray): never held, never a card.
//!
//! NOTHING HERE HEARS ANYTHING: the microphone is voice.rs's, the words are
//! the PC's, and what this reads is fixed words and numbers.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use tauri::{AppHandle, Manager, PhysicalPosition};

use crate::commands;
use crate::voice;

/// Label of the badge window.
pub const BADGE_LABEL: &str = "live-badge";
/// Payload: `{ "status": <GET /api/voice/live>, "stale", "lockUnknown",
/// "callUnknown", "say"? }` - to every window. Fixed words and numbers only.
pub const LIVE_STATUS: &str = "live-status";
/// Payload: `{ "heard": bool, "short": bool }` - the instant "Heard you -
/// thinking" (a Live sentence passed the voice check) or "Didn't catch that
/// - say a bit more" (probably the owner, too short). Never any words.
pub const LIVE_HEARD: &str = "live-heard";
/// The badge's size, in logical pixels, at 100% text (live-badge.js grows
/// it with the text size). Two rows: the review of 2026-09-28 found why
/// Live paused cut off in 12 of 14 states at one row of 52 px.
const BADGE_W: f64 = 420.0;
const BADGE_H: f64 = 84.0;
/// How long the badge stays up after Live ended, showing why (and Resume).
const BADGE_ENDED_FOR: Duration = Duration::from_secs(15);
/// How often the watcher looks.
const WATCH_EVERY: Duration = Duration::from_secs(1);
/// Reads that fail in a row before Live is taken as over here (10 s). The
/// microphone is closed from the first failure.
const WATCH_FAILURES: u32 = 10;
const READ_TIMEOUT: Duration = Duration::from_secs(5);
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);

/// The actions `live_act` takes. Stop is `live_stop`, Mute is `live_mute`.
/// "active": the owner typed or tapped in Live (the PC's quiet clock starts
/// again); "open" / "show_card": the badge opens the Jarvis bar (at the
/// card); "show": the bar comes on screen without the keyboard for a Live
/// answer. None of them approves, starts or widens anything.
pub(crate) const ACTIONS: &[&str] = &["extend", "resume", "active", "open", "show_card", "show"];
/// The actions that only put a window on screen here - nothing is sent.
const WINDOW_ACTIONS: &[&str] = &["open", "show_card", "show"];
/// How a start may say it was started (backend `APP_STARTS`).
pub(crate) const STARTS: &[&str] = &["button", "tray", "hotkey"];
/// The pauses that hold every clip AND close the microphone.
pub(crate) const CARD_PAUSES: &[&str] = &["card", "cards_unknown"];

static WATCHING: AtomicBool = AtomicBool::new(false);
/// Live is on on THIS PC, as far as this app knows (the tray's row).
static ON_HERE: AtomicBool = AtomicBool::new(false);
/// The PC paused Live for a card (or cannot read the queue).
static CARD_PAUSED: AtomicBool = AtomicBool::new(false);
/// The bar is showing an approval card: nothing is heard until it is gone.
static CARD_SHOWN: AtomicBool = AtomicBool::new(false);
/// The bar is speaking an answer under "Interrupt by tap only".
static ANSWERING_TAP_ONLY: AtomicBool = AtomicBool::new(false);
/// Whether Windows is locked could not be read: Live pauses.
static LOCK_UNKNOWN: AtomicBool = AtomicBool::new(false);
/// Whether another program is using the microphone could not be read.
static CALL_UNKNOWN: AtomicBool = AtomicBool::new(false);
/// The owner pressed Unmute while Live was muted for another program on the
/// microphone: that wins until Windows' record says the other program let
/// go (a program that closed badly can leave its record "in use" for good,
/// and the owner must not be muted forever by it).
static MIC_OVERRIDDEN: AtomicBool = AtomicBool::new(false);
/// The bar is playing an answer or a fixed line (live-rules / main.js
/// `syncLiveAnswer`). voice.rs drops a Live sentence that BEGAN while this
/// was true unless the PC said, over barge-in, that it was the owner - an
/// "mm-hm" over an answer is not a new question (the review's bug 9).
static SPEAKING: AtomicBool = AtomicBool::new(false);
/// The owner chose "Only when Windows locks" for Live on this PC (the PC's
/// status `end_on`, read by the watcher). False - App lock's rule - until
/// the PC says otherwise.
static END_ON_WINDOWS_LOCK: AtomicBool = AtomicBool::new(false);
/// A pause ended while talk-to-type held the microphone: Live stays on,
/// its microphone closed, and listens again once talk-to-type lets go -
/// it is not ended as if the owner had ended it (the 2026-09-28 audit, #1).
static TALK_TYPE_WAIT: AtomicBool = AtomicBool::new(false);

pub(crate) const LIVE_MISSING: &str = "This PC's Jarvis does not have Jarvis Live yet. Run \
     scripts\\apply-patches.ps1 on the PC to add it.";
const STALE_HELD: &str = "The connection to Jarvis is catching up, so Jarvis Live is held \
     until it does - try again in a moment.";
pub(crate) const APP_LOCK_HELD: &str = "Jarvis is locked (App lock). Open the Jarvis bar \
     and unlock it with Windows Hello, then start Jarvis Live.";
/// The talk button while Live has the microphone (live-rules.js
/// `SEEN.busy_mic`, the same words on the phone).
pub(crate) const BUSY_MIC: &str = "Jarvis Live is already listening - just talk";
/// Shown under the Live sign while talk-to-type holds the microphone.
pub(crate) const WAIT_TALK_TYPE: &str = "Talk-to-type is using the microphone. Jarvis Live \
     listens again when you let go of its key.";

/// What the watcher does with Live's microphone after a look.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum MicStep {
    /// Held (a card, Mute, a stale link...): the microphone closes.
    Close,
    /// Talk-to-type has the microphone: Live waits, closed, and stays on.
    WaitForTalkType,
    /// Nothing holds it: the microphone opens again.
    Open,
}

pub(crate) fn mic_step(held: bool, talk_type_busy: bool) -> MicStep {
    if held {
        MicStep::Close
    } else if talk_type_busy {
        MicStep::WaitForTalkType
    } else {
        MicStep::Open
    }
}

/// Whether Live is on here (the tray asks).
pub fn on_here() -> bool {
    ON_HERE.load(Ordering::SeqCst)
}

/// Whether the bar is playing an answer or a fixed line in Live (voice.rs).
pub(crate) fn answer_playing() -> bool {
    on_here() && SPEAKING.load(Ordering::SeqCst)
}

/// Does App lock end Live on this PC now? Not when the owner chose "Only
/// when Windows locks" (`end_on`, the PC's `live_end` setting).
pub(crate) fn app_lock_ends(status_end_on: Option<&str>) -> bool {
    status_end_on != Some("windows_lock")
}

/// voice.rs asks before sending a Live sentence: the PC paused Live for a
/// card, or the bar is showing one. A held sentence is dropped, never sent,
/// so a spoken "yes" cannot even reach the PC - cards are decided by tapping.
pub(crate) fn card_paused() -> bool {
    CARD_PAUSED.load(Ordering::SeqCst) || CARD_SHOWN.load(Ordering::SeqCst)
}

/// A Live sentence came back from the PC: the badge and the bar show at
/// once that it was heard (or was too short). Visual only - the "I heard
/// you" sound stays under its own switch.
pub(crate) fn heard_note(app: &AppHandle, heard: bool, short: bool) {
    if heard || short {
        crate::emit_all(
            app,
            LIVE_HEARD,
            serde_json::json!({ "heard": heard, "short": short && !heard }),
        );
    }
}

/// Is `status` a session on THIS PC?
pub(crate) fn on_desktop(status: &serde_json::Value) -> bool {
    status.get("on").and_then(|v| v.as_bool()) == Some(true)
        && status.get("device").and_then(|v| v.as_str()) == Some("desktop")
}

fn text<'a>(status: &'a serde_json::Value, key: &str) -> &'a str {
    status.get(key).and_then(|v| v.as_str()).unwrap_or("")
}

/// Is the PC holding Live for a card (or a queue it cannot read)?
pub(crate) fn card_pause(status: &serde_json::Value) -> bool {
    CARD_PAUSES.contains(&text(status, "paused"))
}

pub(crate) fn muted(status: &serde_json::Value) -> bool {
    status.get("muted").and_then(|v| v.as_bool()) == Some(true)
}

/// Must the microphone be CLOSED now? (live-rules.js `liveListen`'s `mic`.)
/// A voice pause ("other voices") keeps it open: those clips are checked for
/// the owner's voice only, so the owner carries on without a tap.
pub(crate) fn mic_held(
    status: &serde_json::Value,
    stale: bool,
    lock_unknown: bool,
    card_shown: bool,
    answering_tap_only: bool,
) -> bool {
    stale || lock_unknown || card_shown || answering_tap_only || muted(status) || card_pause(status)
}

/// What to tell the PC about another program on the microphone, if
/// anything: `Some(true)` mute, `Some(false)` unmute. Only ever undoes a
/// mute THIS rule made - never the owner's own Mute.
pub(crate) fn mic_mute_change(
    status: &serde_json::Value,
    others: Option<bool>,
    overridden: bool,
) -> Option<bool> {
    match others {
        Some(true) if !muted(status) && !overridden => Some(true),
        Some(false) if muted(status) && text(status, "muted_why") == "mic_in_use" => Some(false),
        _ => None,
    }
}

/// The body for one action. Only the fixed words go in.
pub(crate) fn act_body(
    action: &str,
    minutes: Option<u32>,
    conversation_id: Option<&str>,
) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!("Jarvis Live cannot {action:?}"));
    }
    let mut body = serde_json::json!({ "do": action });
    if action == "active" {
        body["device"] = serde_json::json!("desktop");
        // A session started by voice or from the tray has no chat of its
        // own yet: the bar names its chat here, once (the chat audit,
        // 2026-09-28), so "Move it here" on the phone carries it on.
        if let Some(cid) = conversation_id.filter(|c| commands::valid_conversation_id(c)) {
            body["conversation_id"] = serde_json::json!(cid);
        }
    }
    if action == "extend" {
        let m = minutes.unwrap_or(20);
        if !(1..=120).contains(&m) {
            return Err("Say 1 to 120 more minutes.".to_string());
        }
        body["minutes"] = serde_json::json!(m);
    }
    Ok(body)
}

/// The start body: how it was started is one of the fixed words, and the
/// chat the session's words go in (the bar's conversation id - a fresh one,
/// or the other device's for "Move it here"; the chat audit, 2026-09-28).
/// An id that is not one is left out, never sent.
pub(crate) fn start_body(by: Option<&str>, conversation_id: Option<&str>) -> serde_json::Value {
    let by = by.filter(|b| STARTS.contains(b)).unwrap_or("button");
    let mut body = serde_json::json!({ "do": "start", "device": "desktop", "by": by });
    if let Some(cid) = conversation_id.filter(|c| commands::valid_conversation_id(c)) {
        body["conversation_id"] = serde_json::json!(cid);
    }
    body
}

/// The PC's answer, as a value or the reason in words.
pub(crate) fn answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    let parsed = serde_json::from_str::<serde_json::Value>(body).ok();
    if (200..300).contains(&status) {
        return parsed
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if status == 404 || status == 501 {
        return Err(LIVE_MISSING.to_string());
    }
    if let Some(error) = parsed
        .as_ref()
        .and_then(|v| v.get("error"))
        .and_then(|e| e.as_str())
    {
        return Err(error.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

async fn read(app: &AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/voice/live"))
        .headers(commands::jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    answer(status, &text)
}

async fn post(app: &AppHandle, body: serde_json::Value) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/voice/live"))
        .headers(commands::jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    answer(status, &text)
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

fn payload(app: &AppHandle, status: &serde_json::Value, say: &str) -> serde_json::Value {
    let mut out = serde_json::json!({
        "status": status,
        "stale": stale(app),
        "lockUnknown": LOCK_UNKNOWN.load(Ordering::SeqCst),
        "callUnknown": CALL_UNKNOWN.load(Ordering::SeqCst),
    });
    if on_here() && TALK_TYPE_WAIT.load(Ordering::SeqCst) {
        out["micWait"] = serde_json::json!(WAIT_TALK_TYPE);
    }
    if !say.is_empty() {
        // A FIXED line for the bar to say ("I'm listening.") - never
        // anything heard.
        out["say"] = serde_json::json!(say);
    }
    out
}

fn tell(app: &AppHandle, status: &serde_json::Value, say: &str) {
    crate::emit_all(app, LIVE_STATUS, payload(app, status, say));
}

fn status_of(out: &serde_json::Value) -> serde_json::Value {
    out.get("status")
        .cloned()
        .unwrap_or(serde_json::Value::Null)
}

/// The session, read now (the bar and the badge on opening).
#[tauri::command]
pub async fn live_status(app: AppHandle) -> Result<serde_json::Value, String> {
    let status = read(&app).await?;
    Ok(payload(&app, &status, ""))
}

/// Starts Jarvis Live on this PC. No card; refused on a stale link and
/// while App lock would ask. `by`: "button" (the bar), "tray", "hotkey".
#[tauri::command]
pub async fn live_start(
    app: AppHandle,
    by: Option<String>,
    conversation_id: Option<String>,
) -> Result<serde_json::Value, String> {
    start(&app, by.as_deref(), conversation_id.as_deref()).await
}

pub(crate) async fn start(
    app: &AppHandle,
    by: Option<&str>,
    conversation_id: Option<&str>,
) -> Result<serde_json::Value, String> {
    if stale(app) {
        return Err(STALE_HELD.to_string());
    }
    if crate::lock::app_locked(app) {
        return Err(APP_LOCK_HELD.to_string());
    }
    if let Some(why) = voice::live_audio_refusal(&commands::jarvis_base(app)) {
        return Err(why);
    }
    let out = post(app, start_body(by, conversation_id)).await?;
    if let Err(why) = voice::open_for_live(app).await {
        // No microphone: the session the PC just started is ended again, so
        // no sign says "Live" over a microphone that is not open.
        let _ = post(
            app,
            serde_json::json!({ "do": "stop", "why": "owner", "device": "desktop" }),
        )
        .await;
        return Err(why);
    }
    CARD_PAUSED.store(false, Ordering::SeqCst);
    ON_HERE.store(true, Ordering::SeqCst);
    crate::tray::live_changed(app);
    if let Err(why) = show_badge(app) {
        eprintln!("[live] the badge did not open: {why}");
    }
    let status = status_of(&out);
    let say = out.get("say").and_then(|v| v.as_str()).unwrap_or("");
    tell(app, &status, say);
    spawn_watcher(app.clone());
    Ok(payload(app, &status, say))
}

/// "Hey Jarvis, let's talk" started Live on this PC (the PC's own session;
/// voice.rs saw `live: "started"`): the microphone moves into Live mode,
/// and the badge and the watcher start, as for the button. Under App lock,
/// or on a stale link, the PC's session is ended again at once.
pub(crate) fn adopt(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        if on_here() {
            return;
        }
        if crate::lock::app_locked(&app) {
            let _ = post(
                &app,
                serde_json::json!({ "do": "stop", "why": "app_lock", "device": "desktop" }),
            )
            .await;
            return;
        }
        if stale(&app) {
            let _ = post(
                &app,
                serde_json::json!({ "do": "stop", "why": "owner", "device": "desktop" }),
            )
            .await;
            return;
        }
        if let Err(why) = voice::open_for_live(&app).await {
            let _ = post(
                &app,
                serde_json::json!({ "do": "stop", "why": "owner", "device": "desktop" }),
            )
            .await;
            commands::notify(&app, "Jarvis Live", &why);
            return;
        }
        CARD_PAUSED.store(false, Ordering::SeqCst);
        ON_HERE.store(true, Ordering::SeqCst);
        crate::tray::live_changed(&app);
        if let Err(why) = show_badge(&app) {
            eprintln!("[live] the badge did not open: {why}");
        }
        // The bar already says the start line (from the heard reply).
        if let Ok(status) = read(&app).await {
            tell(&app, &status, "");
        }
        spawn_watcher(app.clone());
    });
}

/// Ends Jarvis Live. Never held, never a card.
#[tauri::command]
pub async fn live_stop(app: AppHandle) -> Result<serde_json::Value, String> {
    stop(&app, "owner").await
}

/// `why`: "owner", "app_lock" or "locked" (backend `APP_END_REASONS`).
pub(crate) async fn stop(app: &AppHandle, why: &str) -> Result<serde_json::Value, String> {
    // Here first: the microphone closes even if the PC cannot be reached.
    ended_here(app).await;
    let out = post(
        app,
        serde_json::json!({ "do": "stop", "why": why, "device": "desktop" }),
    )
    .await?;
    let status = status_of(&out);
    tell(app, &status, "");
    Ok(status)
}

/// "More time" and "Carry on". Held on a stale link.
#[tauri::command]
pub async fn live_act(
    app: AppHandle,
    action: String,
    minutes: Option<u32>,
    conversation_id: Option<String>,
) -> Result<serde_json::Value, String> {
    if WINDOW_ACTIONS.contains(&action.as_str()) {
        match action.as_str() {
            "show" => crate::windows::show_quickbar_quietly(&app)?,
            "show_card" => {
                crate::windows::show_quickbar(&app)?;
                crate::emit_quickbar(&app, crate::events::SHOW_APPROVAL, None::<String>);
            }
            _ => crate::windows::show_quickbar(&app)?,
        }
        return Ok(serde_json::Value::Null);
    }
    let body = act_body(&action, minutes, conversation_id.as_deref())?;
    // "More time" and "Carry on" are held on a stale link; "active" only
    // keeps open a session the owner started, and goes.
    if action != "active" && stale(&app) {
        return Err(STALE_HELD.to_string());
    }
    let out = post(&app, body).await?;
    let status = status_of(&out);
    tell(&app, &status, "");
    Ok(status)
}

/// Mute / Unmute. The microphone closes HERE first; the session and its
/// time carry on. Never held: muting makes Jarvis hear less, and unmuting
/// only listens again in a session the owner already started.
#[tauri::command]
pub async fn live_mute(app: AppHandle, muted: bool) -> Result<serde_json::Value, String> {
    if muted {
        voice::suspend_for_live(&app);
        MIC_OVERRIDDEN.store(false, Ordering::SeqCst);
    } else {
        // Unmute is the owner's word over "another program is using the
        // microphone" (see MIC_OVERRIDDEN).
        MIC_OVERRIDDEN.store(true, Ordering::SeqCst);
    }
    let out = post(
        &app,
        serde_json::json!({
            "do": if muted { "mute" } else { "unmute" },
            "why": "owner",
            "device": "desktop",
        }),
    )
    .await?;
    let status = status_of(&out);
    apply_hold(&app, &status);
    tell(&app, &status, "");
    Ok(status)
}

/// The bar holds the microphone closed while it shows an approval card
/// raised in this session (`what: "card"`) or speaks under "By button only"
/// or "Don't interrupt" (`what: "answer"`). Takes effect at once, not at the
/// next look. `what: "speaking"` holds nothing: it says an answer is
/// playing, so a sentence that began over it is dropped unless the PC said
/// it was the owner (voice.rs).
#[tauri::command]
pub async fn live_hold(app: AppHandle, what: String, on: bool) -> Result<(), String> {
    match what.as_str() {
        "card" => CARD_SHOWN.store(on, Ordering::SeqCst),
        "answer" => ANSWERING_TAP_ONLY.store(on, Ordering::SeqCst),
        "speaking" => {
            SPEAKING.store(on, Ordering::SeqCst);
            return Ok(());
        }
        other => return Err(format!("Jarvis Live cannot hold for {other:?}")),
    }
    if !on_here() {
        return Ok(());
    }
    if on {
        voice::suspend_for_live(&app);
        return Ok(());
    }
    // Let go: the next look decides with everything else it knows.
    match read(&app).await {
        Ok(status) => apply_hold(&app, &status),
        Err(why) => eprintln!("[live] could not read Live after a hold: {why}"),
    }
    Ok(())
}

/// The tray's row: start or end. A refusal is a notification - the bar may
/// be hidden (or locked).
pub fn toggle_from_tray(app: &AppHandle) {
    toggle(app, "tray");
}

/// Start or end Live from the tray's row (`by` "tray") or the Live hotkey
/// (`by` "hotkey", hotkeys.rs `toggle_live`, off until the owner picks a
/// key). Start is held on a stale link and while App lock would ask; End
/// never is. A refusal is a notification.
pub fn toggle(app: &AppHandle, by: &'static str) {
    let by = if STARTS.contains(&by) { by } else { "button" };
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let result = if on_here() {
            stop(&app, "owner").await
        } else {
            start(&app, Some(by), None).await
        };
        if let Err(why) = result {
            commands::notify(&app, "Jarvis Live", &why);
        }
    });
}

/// The listener stopped by itself (the microphone went, or the address
/// changed): Live ends too.
pub(crate) fn listener_stopped(app: &AppHandle) {
    if !on_here() {
        return;
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let _ = stop(&app, "owner").await;
    });
}

/// Everything on this PC's side of Live goes back to off. The badge stays a
/// few seconds, saying why it ended.
async fn ended_here(app: &AppHandle) {
    let was_on = ON_HERE.swap(false, Ordering::SeqCst);
    CARD_PAUSED.store(false, Ordering::SeqCst);
    CARD_SHOWN.store(false, Ordering::SeqCst);
    ANSWERING_TAP_ONLY.store(false, Ordering::SeqCst);
    SPEAKING.store(false, Ordering::SeqCst);
    LOCK_UNKNOWN.store(false, Ordering::SeqCst);
    TALK_TYPE_WAIT.store(false, Ordering::SeqCst);
    voice::close_for_live(app).await;
    crate::tray::live_changed(app);
    if was_on {
        let app = app.clone();
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep(BADGE_ENDED_FOR).await;
            if !on_here() {
                hide_badge(&app);
            }
        });
    }
}

/// Opens or closes the microphone for what the status says.
fn apply_hold(app: &AppHandle, status: &serde_json::Value) {
    if !on_here() {
        return;
    }
    let held = mic_held(
        status,
        stale(app),
        LOCK_UNKNOWN.load(Ordering::SeqCst),
        CARD_SHOWN.load(Ordering::SeqCst),
        ANSWERING_TAP_ONLY.load(Ordering::SeqCst),
    );
    let talk_type = app.state::<crate::talk_type::TalkTypeState>();
    match mic_step(held, talk_type.mic_busy()) {
        MicStep::Close => {
            TALK_TYPE_WAIT.store(false, Ordering::SeqCst);
            voice::suspend_for_live(app);
        }
        MicStep::WaitForTalkType => {
            // Talk-to-type refuses while Live is on, so this is only a race
            // (it started in the instant before Live did). Live waits with
            // its microphone closed; the watcher looks again every second.
            TALK_TYPE_WAIT.store(true, Ordering::SeqCst);
            voice::suspend_for_live(app);
        }
        MicStep::Open => {
            TALK_TYPE_WAIT.store(false, Ordering::SeqCst);
            if let Err(why) = voice::resume_for_live(app) {
                if talk_type.mic_busy() {
                    // Taken between the two looks: wait, as above.
                    TALK_TYPE_WAIT.store(true, Ordering::SeqCst);
                    return;
                }
                eprintln!("[live] the microphone would not open again: {why}");
                listener_stopped(app);
            }
        }
    }
}

fn spawn_watcher(app: AppHandle) {
    if WATCHING.swap(true, Ordering::SeqCst) {
        return;
    }
    tauri::async_runtime::spawn(async move {
        let mut failures = 0u32;
        loop {
            tokio::time::sleep(WATCH_EVERY).await;
            if !on_here() {
                break;
            }
            // App lock first: it needs no network. Someone else at the PC
            // must not talk to Jarvis through a session the owner left -
            // unless the owner chose "Only when Windows locks" (a card on
            // the PC; the last status read says so), when Windows' own lock
            // below ends it instead.
            let end_on = if END_ON_WINDOWS_LOCK.load(Ordering::SeqCst) {
                Some("windows_lock")
            } else {
                None
            };
            if crate::lock::app_locked(&app) && app_lock_ends(end_on) {
                let _ = stop(&app, "app_lock").await;
                break;
            }
            match windows_locked() {
                Some(true) => {
                    let _ = stop(&app, "locked").await;
                    break;
                }
                seen => LOCK_UNKNOWN.store(seen.is_none(), Ordering::SeqCst),
            }
            match read(&app).await {
                Ok(status) => {
                    failures = 0;
                    if !on_desktop(&status) {
                        ended_here(&app).await;
                        tell(&app, &status, "");
                        break;
                    }
                    CARD_PAUSED.store(card_pause(&status), Ordering::SeqCst);
                    END_ON_WINDOWS_LOCK.store(
                        !app_lock_ends(status.get("end_on").and_then(|v| v.as_str())),
                        Ordering::SeqCst,
                    );
                    let others = mic_in_use_by_others();
                    CALL_UNKNOWN.store(others.is_none(), Ordering::SeqCst);
                    if others == Some(false) {
                        MIC_OVERRIDDEN.store(false, Ordering::SeqCst);
                    }
                    let overridden = MIC_OVERRIDDEN.load(Ordering::SeqCst);
                    let status = match mic_mute_change(&status, others, overridden) {
                        Some(mute) => post(
                            &app,
                            serde_json::json!({
                                "do": if mute { "mute" } else { "unmute" },
                                "why": "mic_in_use",
                                "device": "desktop",
                            }),
                        )
                        .await
                        .map(|out| status_of(&out))
                        .unwrap_or(status),
                        None => status,
                    };
                    apply_hold(&app, &status);
                    tell(&app, &status, "");
                }
                Err(why) => {
                    // Cannot tell what the PC says: nothing is heard.
                    voice::suspend_for_live(&app);
                    failures += 1;
                    if failures >= WATCH_FAILURES {
                        eprintln!("[live] the PC stopped answering ({why}); Live ends here");
                        ended_here(&app).await;
                        break;
                    }
                }
            }
        }
        WATCHING.store(false, Ordering::SeqCst);
    });
}

// ---------------------------------------------------------------------------
// Windows: is the PC locked? Is another program using the microphone?
// ---------------------------------------------------------------------------

/// The input desktop's name: "Default" while someone is signed in and
/// working. On the lock screen this app is refused the input desktop
/// outright (access denied): locked. "Winlogon" is also the secure desktop a
/// User Account Control prompt shows, and "Screen-saver" is not a lock by
/// itself - both are "cannot tell", which pauses Live rather than ending it.
pub(crate) fn locked_from_desktop(name: Option<&str>, access_denied: bool) -> Option<bool> {
    match name {
        Some(n) if n.eq_ignore_ascii_case("default") => Some(false),
        Some(_) => None,
        None if access_denied => Some(true),
        None => None,
    }
}

/// `Some(true)` on the lock screen, `Some(false)` when not, `None` when it
/// cannot be told - and Live pauses then.
#[cfg(windows)]
fn windows_locked() -> Option<bool> {
    use windows_sys::Win32::Foundation::{GetLastError, ERROR_ACCESS_DENIED};
    use windows_sys::Win32::System::StationsAndDesktops::{
        CloseDesktop, GetUserObjectInformationW, OpenInputDesktop, DESKTOP_READOBJECTS, UOI_NAME,
    };

    // SAFETY: OpenInputDesktop takes no pointers; a null handle is checked
    // before use, and a real one is closed below.
    let desk = unsafe { OpenInputDesktop(0, 0, DESKTOP_READOBJECTS) };
    if desk.is_null() {
        // SAFETY: reads this thread's last error, nothing else.
        let denied = unsafe { GetLastError() } == ERROR_ACCESS_DENIED;
        return locked_from_desktop(None, denied);
    }
    let mut buf = [0u16; 64];
    let mut needed: u32 = 0;
    // SAFETY: `buf` is writable for its full size in bytes, which is what
    // nlength says; `needed` is a valid u32. The handle is live.
    let ok = unsafe {
        GetUserObjectInformationW(
            desk,
            UOI_NAME,
            buf.as_mut_ptr().cast(),
            std::mem::size_of_val(&buf) as u32,
            &mut needed,
        )
    };
    // SAFETY: the handle came from OpenInputDesktop and is closed once.
    unsafe { CloseDesktop(desk) };
    if ok == 0 {
        return None;
    }
    let end = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
    let name = String::from_utf16_lossy(&buf[..end]);
    locked_from_desktop(Some(&name), false)
}

#[cfg(not(windows))]
fn windows_locked() -> Option<bool> {
    None
}

/// Windows' own record of microphone use: under
/// `...\CapabilityAccessManager\ConsentStore\microphone`, one key per app
/// (programs under `NonPackaged`, their path with `#` for `\`), each with
/// `LastUsedTimeStart` and `LastUsedTimeStop`. A stop of 0 after a start
/// means that app has the microphone NOW. This app's own entry does not
/// count (it is Live's own listener).
pub(crate) fn others_using(entries: &[(String, u64, u64)], own: &str) -> bool {
    let own = own.replace('\\', "#").to_lowercase();
    entries
        .iter()
        .any(|(name, start, stop)| *start > 0 && *stop == 0 && name.to_lowercase() != own)
}

/// `Some(true)` while another program uses the microphone (a call, most
/// likely), `None` when Windows' record cannot be read.
#[cfg(windows)]
fn mic_in_use_by_others() -> Option<bool> {
    let own = std::env::current_exe().ok()?.to_string_lossy().into_owned();
    let root = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone";
    let mut entries = Vec::new();
    for key in reg::subkeys(root)? {
        if key.eq_ignore_ascii_case("NonPackaged") {
            let sub = format!(r"{root}\NonPackaged");
            for exe in reg::subkeys(&sub).unwrap_or_default() {
                let path = format!(r"{sub}\{exe}");
                entries.push((
                    exe,
                    reg::qword(&path, "LastUsedTimeStart"),
                    reg::qword(&path, "LastUsedTimeStop"),
                ));
            }
        } else {
            let path = format!(r"{root}\{key}");
            entries.push((
                key,
                reg::qword(&path, "LastUsedTimeStart"),
                reg::qword(&path, "LastUsedTimeStop"),
            ));
        }
    }
    Some(others_using(&entries, &own))
}

#[cfg(not(windows))]
fn mic_in_use_by_others() -> Option<bool> {
    None
}

#[cfg(windows)]
mod reg {
    use windows_sys::Win32::Foundation::ERROR_SUCCESS;
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegEnumKeyExW, RegGetValueW, RegOpenKeyExW, HKEY, HKEY_CURRENT_USER, KEY_READ,
        RRF_RT_REG_QWORD,
    };

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    /// The names of the keys under `path` (HKCU), or None if it cannot be
    /// opened.
    pub(super) fn subkeys(path: &str) -> Option<Vec<String>> {
        let path = wide(path);
        let mut key: HKEY = std::ptr::null_mut();
        // SAFETY: `path` is NUL-terminated UTF-16 that outlives the call;
        // `key` receives the handle, closed below.
        let rc = unsafe { RegOpenKeyExW(HKEY_CURRENT_USER, path.as_ptr(), 0, KEY_READ, &mut key) };
        if rc != ERROR_SUCCESS {
            return None;
        }
        let mut out = Vec::new();
        let mut index = 0u32;
        loop {
            let mut name = [0u16; 512];
            let mut len = name.len() as u32;
            // SAFETY: `name` holds `len` UTF-16 units; the other out
            // pointers are null, which the call allows.
            let rc = unsafe {
                RegEnumKeyExW(
                    key,
                    index,
                    name.as_mut_ptr(),
                    &mut len,
                    std::ptr::null(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                )
            };
            if rc != ERROR_SUCCESS {
                break;
            }
            out.push(String::from_utf16_lossy(&name[..len as usize]));
            index += 1;
            if index > 4096 {
                break;
            }
        }
        // SAFETY: opened above, closed once.
        unsafe { RegCloseKey(key) };
        Some(out)
    }

    /// A QWORD value, 0 when missing.
    pub(super) fn qword(path: &str, value: &str) -> u64 {
        let path = wide(path);
        let value = wide(value);
        let mut data: u64 = 0;
        let mut size = std::mem::size_of::<u64>() as u32;
        // SAFETY: both strings are NUL-terminated UTF-16 that outlive the
        // call; `data` is a u64 and `size` says so, and RRF_RT_REG_QWORD
        // makes the call fail rather than write anything else.
        let rc = unsafe {
            RegGetValueW(
                HKEY_CURRENT_USER,
                path.as_ptr(),
                value.as_ptr(),
                RRF_RT_REG_QWORD,
                std::ptr::null_mut(),
                (&mut data as *mut u64).cast(),
                &mut size,
            )
        };
        if rc == ERROR_SUCCESS {
            data
        } else {
            0
        }
    }
}

// ---------------------------------------------------------------------------
// The badge: "Jarvis Live · 24 min left", Mute and Stop, always on top
// ---------------------------------------------------------------------------

/// Opens the badge at the top of the main screen. It shows only what the
/// sign says (fixed words and minutes) and its buttons - never a word
/// anyone said - so it is not behind App lock, like the floating face: the
/// owner must always be able to see that Live is on, and end it.
pub fn show_badge(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(BADGE_LABEL) {
        return window
            .show()
            .map_err(|e| format!("unable to show the Live badge: {e}"));
    }
    let window = tauri::WebviewWindowBuilder::new(
        app,
        BADGE_LABEL,
        tauri::WebviewUrl::App("live-badge.html".into()),
    )
    .title("Jarvis Live")
    .inner_size(BADGE_W, BADGE_H)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .decorations(false)
    .transparent(true)
    .always_on_top(true)
    .skip_taskbar(true)
    .shadow(false)
    // It never takes the keyboard from what the owner is doing; its buttons
    // are clicked with the mouse.
    .focused(false)
    .visible(false)
    .build()
    .map_err(|e| format!("unable to open the Live badge: {e}"))?;
    if let Ok(Some(monitor)) = window.current_monitor() {
        let size = monitor.size();
        let scale = monitor.scale_factor();
        let at = monitor.position();
        let width = (BADGE_W * scale) as i32;
        let x = at.x + (size.width as i32 - width) / 2;
        let y = at.y + (12.0 * scale) as i32;
        let _ = window.set_position(PhysicalPosition::new(x, y));
    }
    window
        .show()
        .map_err(|e| format!("unable to show the Live badge: {e}"))
}

pub fn hide_badge(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(BADGE_LABEL) {
        let _ = window.hide();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn only_a_desktop_session_counts_here() {
        assert!(on_desktop(&json!({"on": true, "device": "desktop"})));
        assert!(!on_desktop(&json!({"on": true, "device": "phone"})));
        assert!(!on_desktop(&json!({"on": false, "device": "desktop"})));
        assert!(!on_desktop(&json!({})));
    }

    #[test]
    fn talk_to_type_on_the_microphone_makes_live_wait_not_end() {
        assert_eq!(mic_step(true, false), MicStep::Close);
        assert_eq!(mic_step(true, true), MicStep::Close);
        assert_eq!(mic_step(false, true), MicStep::WaitForTalkType);
        assert_eq!(mic_step(false, false), MicStep::Open);
        assert!(WAIT_TALK_TYPE.contains("Talk-to-type"));
        assert!(!WAIT_TALK_TYPE.contains("hey Jarvis"));
    }

    #[test]
    fn the_microphone_closes_for_everything_but_a_voice_pause() {
        let on = json!({"on": true, "device": "desktop"});
        assert!(!mic_held(&on, false, false, false, false));
        assert!(mic_held(&on, true, false, false, false), "stale link");
        assert!(mic_held(&on, false, true, false, false), "lock unknown");
        assert!(mic_held(&on, false, false, true, false), "a card on screen");
        assert!(mic_held(&on, false, false, false, true), "tap-only answer");
        assert!(mic_held(
            &json!({"muted": true}),
            false,
            false,
            false,
            false
        ));
        assert!(mic_held(
            &json!({"paused": "card"}),
            false,
            false,
            false,
            false
        ));
        assert!(mic_held(
            &json!({"paused": "cards_unknown"}),
            false,
            false,
            false,
            false
        ));
        // Check-only listening: the owner carries on without a tap.
        assert!(!mic_held(
            &json!({"paused": "other_voices"}),
            false,
            false,
            false,
            false
        ));
        assert!(!mic_held(
            &json!({"paused": "voice_trouble"}),
            false,
            false,
            false,
            false
        ));
    }

    #[test]
    fn a_call_never_undoes_the_owners_mute() {
        let open = json!({"muted": false});
        let owner = json!({"muted": true, "muted_why": "owner"});
        let call = json!({"muted": true, "muted_why": "mic_in_use"});
        assert_eq!(mic_mute_change(&open, Some(true), false), Some(true));
        assert_eq!(mic_mute_change(&open, Some(false), false), None);
        assert_eq!(mic_mute_change(&open, None, false), None);
        assert_eq!(mic_mute_change(&call, Some(false), false), Some(false));
        assert_eq!(mic_mute_change(&call, Some(true), false), None);
        assert_eq!(mic_mute_change(&owner, Some(false), false), None);
        assert_eq!(mic_mute_change(&owner, Some(true), false), None);
        assert_eq!(
            mic_mute_change(&call, None, false),
            None,
            "cannot tell: left as it is"
        );
        // The owner's Unmute wins over a record stuck on "in use".
        assert_eq!(mic_mute_change(&open, Some(true), true), None);
    }

    #[test]
    fn windows_own_record_of_the_microphone() {
        let own = r"C:\Program Files\Jarvis\jarvis-desktop.exe";
        let me = (
            r"C:#Program Files#Jarvis#jarvis-desktop.exe".to_string(),
            5,
            0,
        );
        let zoom = (
            r"C:#Users#me#AppData#Roaming#Zoom#bin#Zoom.exe".to_string(),
            7,
            0,
        );
        let old = (r"C:#Tools#recorder.exe".to_string(), 3, 4);
        let never = ("MicrosoftTeams_8wekyb3d8bbwe".to_string(), 0, 0);
        assert!(!others_using(
            &[me.clone(), old.clone(), never.clone()],
            own
        ));
        assert!(others_using(&[me, zoom, old], own));
        assert!(others_using(
            &[("MicrosoftTeams_8wekyb3d8bbwe".to_string(), 9, 0)],
            own
        ));
        assert!(!others_using(&[never], own));
    }

    #[test]
    fn the_lock_screen_and_cannot_tell() {
        assert_eq!(locked_from_desktop(Some("Default"), false), Some(false));
        assert_eq!(
            locked_from_desktop(Some("Winlogon"), false),
            None,
            "a UAC prompt pauses"
        );
        assert_eq!(locked_from_desktop(None, true), Some(true));
        assert_eq!(locked_from_desktop(None, false), None);
        assert_eq!(locked_from_desktop(Some("Something"), false), None);
    }

    #[test]
    fn app_lock_ends_live_unless_the_owner_chose_windows_lock() {
        assert!(app_lock_ends(None), "the default: App lock's rule");
        assert!(app_lock_ends(Some("app_lock")));
        assert!(
            app_lock_ends(Some("nonsense")),
            "anything else: the stricter"
        );
        assert!(!app_lock_ends(Some("windows_lock")));
    }

    #[test]
    fn only_fixed_actions_go_out() {
        assert_eq!(
            act_body("active", None, None).unwrap(),
            json!({"do": "active", "device": "desktop"})
        );
        assert!(ACTIONS.contains(&"show_card") && WINDOW_ACTIONS.contains(&"open"));
        assert_eq!(
            act_body("extend", None, None).unwrap(),
            json!({"do": "extend", "minutes": 20})
        );
        assert_eq!(
            act_body("resume", None, None).unwrap(),
            json!({"do": "resume"})
        );
        assert!(
            act_body("start", None, None).is_err(),
            "start is live_start's"
        );
        assert!(act_body("approve", None, None).is_err());
        assert!(act_body("extend", Some(0), None).is_err());
        assert!(act_body("extend", Some(500), None).is_err());
        assert_eq!(start_body(Some("tray"), None)["by"], "tray");
        // The chat the session goes in (the chat audit, 2026-09-28): a
        // conversation id is passed on; anything else never reaches the PC.
        assert_eq!(
            start_body(None, Some("conv-live-0001"))["conversation_id"],
            "conv-live-0001"
        );
        assert!(start_body(None, Some("bad id!"))
            .get("conversation_id")
            .is_none());
        assert_eq!(
            act_body("active", None, Some("conv-voice-0002")).unwrap()["conversation_id"],
            "conv-voice-0002"
        );
        assert!(act_body("resume", None, Some("conv-voice-0002"))
            .unwrap()
            .get("conversation_id")
            .is_none());
        assert_eq!(
            start_body(Some("voice"), None)["by"],
            "button",
            "voice is the PC's to say"
        );
        assert_eq!(start_body(None, None)["by"], "button");
    }

    #[test]
    fn an_older_pc_says_how_to_get_it() {
        assert_eq!(answer(404, ""), Err(LIVE_MISSING.to_string()));
        assert_eq!(
            answer(409, r#"{"error": "needs voice", "needs": "voice"}"#),
            Err("needs voice".to_string())
        );
        assert!(answer(200, r#"{"ok": true}"#).is_ok());
    }

    #[test]
    fn live_audio_goes_only_to_this_pc() {
        assert!(voice::live_audio_refusal("http://127.0.0.1:7777").is_none());
        assert!(voice::live_audio_refusal("http://100.64.1.2:7777").is_some());
    }

    #[test]
    fn a_sentence_over_an_answer_goes_only_when_it_was_the_owner() {
        assert!(
            voice::live_over_answer_sent(true, false, false),
            "not over an answer"
        );
        assert!(
            !voice::live_over_answer_sent(true, true, false),
            "an mm-hm over an answer"
        );
        assert!(
            voice::live_over_answer_sent(true, true, true),
            "the owner cut in"
        );
        assert!(voice::live_over_answer_sent(false, true, false), "not Live");
    }

    #[test]
    fn a_card_or_a_stale_link_holds_the_sentence() {
        assert!(!voice::live_held(false, false));
        assert!(voice::live_held(true, false));
        assert!(voice::live_held(false, true));
    }
}
