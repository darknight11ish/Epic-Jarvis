//! "Look at this" and "Watch with me" on this PC (the owner's decision of
//! 2026-09-28; docs/SCREEN-DESIGN.md; backend/jarvis_screen.py is the
//! session, jarvis_screen_win.py takes the picture; JARVIS-API sections 62
//! and 93).
//!
//! WHAT THIS DOES
//! * **Look at this** (the hotkey; hotkeys.rs `capture_screen`, renamed):
//!   ONE look at the window in front. It is taken BEFORE the Jarvis bar
//!   comes up - once the bar is in front, Jarvis's own window is what would
//!   be seen, and that is a pause - by asking this PC (`POST /api/screen
//!   {"do":"look","want":"picture"}`), which checks for a password box, the
//!   Never look at list and capture protection, takes the picture in memory,
//!   reads its words and throws the picture away. Since the owner's decision
//!   of 2026-10-07 it ALSO hands back the CLEANED picture - the one
//!   `jarvis_picture.clean` painted every key, password and Never-look window
//!   out of - and that lands in the question box as an attachment with a
//!   thumbnail, before the owner types their question (main.js's
//!   `attachCapture`; `.dsh-scratch/SCREEN-ATTACH-DESIGN.md`). A picture the
//!   PC could not verify is not handed back at all, and `capture-failed`
//!   carries the plain reason (`capture_why` below). This app still never
//!   TAKES a picture: it receives the cleaner's own PNG, keeps it in the page,
//!   and neither decodes it, reads it, saves it nor logs it.
//!   Then the bar opens, and a question asked within two minutes is marked
//!   `screen: "look"` (main.js), so the PC adds the words to THAT question as
//!   outside text.
//! * **Watch with me** (the bar's button, the tray's row, a hotkey that is
//!   off until the owner picks a key, or "watch with me" said or typed): a
//!   session with a sign on screen the whole time (`watch-badge.html`, an
//!   always-on-top badge that is hidden from screen captures). No card to
//!   start - the owner's own act - but held on a stale link (rule 4) and
//!   while App lock would ask. While it is on, a fresh look is taken when the
//!   owner STARTS a question: the bar opened by its hotkey, or "Hey Jarvis"
//!   heard. It is used by that one question. It asks for no picture: "Watch
//!   with me" answers questions about the screen, it does not attach one.
//! * **Stop** (the badge, the bar, the tray, "stop watching", Stop
//!   everything): never held, never a card.
//! * The session's state comes to every window as `screen-status`, from the
//!   PC's own `screen_watch` event (stream.rs) - fixed words and numbers
//!   only, never a program, a site, a title or a word from the screen.
//!
//! WHAT THIS REFUSES: to look at anything but the PC this app runs on. The
//! PC's routes refuse a request from another machine, and this app refuses
//! when it is pointed at another machine's Jarvis (`voice::is_loopback_base`),
//! so a look can never be a look at a screen the owner is not sitting at.
//!
//! NOTHING HERE READS THE SCREEN. The one picture that crosses is the PC's
//! cleaner's own output, and only when the PC says it is a PNG and it decodes
//! inside a size cap (`capture_payload`); anything else is refused.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::time::Duration;

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use tauri::{AppHandle, Manager, PhysicalPosition};

use crate::commands;

/// Label of the badge window.
pub const BADGE_LABEL: &str = "watch-badge";
/// Payload: `{ "status": <GET /api/screen or a screen_watch event>, "stale":
/// bool, "say"? }` - to every window. Fixed words and numbers only.
pub const SCREEN_STATUS: &str = "screen-status";
/// Payload to the Jarvis bar after a look: `{ "ok": bool, "note"?, "said"? }`.
/// The note names the program the owner asked about (it is on the owner's own
/// screen, and stays there); never a word from the screen. `{ "closed": true }`
/// when the bar closed: nothing about the last look stays on it.
pub const SCREEN_LOOK: &str = "screen-look";
/// The badge's size, in logical pixels, at 100% text.
const BADGE_W: f64 = 400.0;
const BADGE_H: f64 = 88.0;
/// How long the badge stays up after a session ended, saying why.
const BADGE_ENDED_FOR: Duration = Duration::from_secs(15);
const READ_TIMEOUT: Duration = Duration::from_secs(5);
/// A look answers in a fraction of a second (the words are read after); this
/// only stops a stuck PC from holding the bar back for long.
const LOOK_TIMEOUT: Duration = Duration::from_secs(4);
/// A look that also asks for the picture. The PC cannot answer that one in a
/// fraction of a second: it reads the screen's words AND paints the secrets out
/// of the picture before answering (`jarvis_screen_attach.look_with_picture`),
/// and Windows' text reader alone can take a second or two on a busy screen.
/// The PC's own wait for its reader is 35 s (`jarvis_screen.READ_WAIT_S`); this
/// is the app's shorter patience, so a hung PC still gives the bar back.
/// NOT MEASURED on the owner's PC - see CHANGELOG.md.
const ATTACH_TIMEOUT: Duration = Duration::from_secs(20);
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);

/// The most bytes of cleaned picture this app will take from the PC. The PC
/// already caps its own capture (the cap its own text reader sets; a PNG past
/// it is written half size, and past that it hands nothing on), so this is the
/// second lock: a wrong or damaged answer must not put a hundred megabytes
/// through IPC.
const MAX_ATTACH_BYTES: usize = 8 * 1024 * 1024;
/// The signature every PNG starts with. The PC's own cleaner writes PNGs
/// (`jarvis_picture.encode_png`), so a payload that is not one is not its
/// output and is refused.
const PNG_SIG: &[u8] = b"\x89PNG\r\n\x1a\n";

/// The verbs `screen_watch` takes. "look" and "ask" are this file's own
/// (the hotkey, a question starting); the bar never sends them.
pub(crate) const WATCH_ACTIONS: &[&str] = &["start", "stop", "extend", "drop"];
/// The verbs `screen_never` takes.
pub(crate) const NEVER_ACTIONS: &[&str] = &["list", "add", "remove"];
/// The verbs `screen_picture` takes: read the setting, turn picture mode on
/// (ONE approval card on the PC - nothing changes until it is approved) or
/// off (at once).
pub(crate) const PICTURE_ACTIONS: &[&str] = &["read", "on", "off"];
/// How a session may say it was started (for the audit trail only).
pub(crate) const STARTS: &[&str] = &["button", "tray", "hotkey", "voice"];

/// A session is on on this PC, as far as this app knows (the tray's row).
static ON_HERE: AtomicBool = AtomicBool::new(false);

pub(crate) const MISSING: &str = "This PC's Jarvis is missing this feature. In PowerShell on \
     the PC, in the Jarvis folder, run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis.";
pub(crate) const PICTURE_MISSING: &str = "This PC's Jarvis is missing this feature. In PowerShell \
     on the PC, in the Jarvis folder, run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis.";
const STALE_HELD: &str = "Reconnecting to Jarvis. Looking at the screen waits until the \
     connection is back - try again in a moment.";
pub(crate) const APP_LOCK_HELD: &str = "Jarvis is locked (App lock). Open the Jarvis bar and \
     unlock it with Windows Hello, then ask Jarvis to look.";
pub(crate) const NOT_THIS_PC: &str = "Jarvis only looks at the screen of the PC it runs on, and \
     this app is set to a Jarvis on another machine. Change the address in Settings, Connection, \
     if this PC is the one to look at.";
/// The Jarvis bar's line when a look could not be taken and the PC gave no
/// reason of its own.
const NO_LOOK: &str = "Jarvis could not look at your screen just now.";
/// The plain words when a look WAS taken but nothing could be attached and the
/// PC gave no reason of its own.
const NO_PICTURE: &str = "Jarvis looked at your screen, but could not attach a picture of it. \
     Your question can still be asked without one.";

/// How often this app tells the PC "I am still here" while a session is on
/// (the heartbeat). The PC ends a session after about 45 seconds of silence,
/// so a closed or crashed app cannot leave Jarvis watching with nobody to
/// see the sign. 12 s leaves three beats inside that window.
pub(crate) const HEARTBEAT_EVERY: Duration = Duration::from_secs(12);
/// The PC's silence limit, in seconds (the backend's number, not ours).
#[cfg(test)]
const HEARTBEAT_PC_LIMIT_SECS: u64 = 45;
/// Which heartbeat loop is the current one; a newer session bumps it, so an
/// older loop notices and stops instead of doubling the beats.
static BEAT_GEN: AtomicU64 = AtomicU64::new(0);

/// The body of the heartbeat. The verb is `heartbeat` on `POST /api/screen`,
/// no other fields.
pub(crate) fn heartbeat_body() -> serde_json::Value {
    serde_json::json!({ "do": "heartbeat" })
}

/// What one loop turn does.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Beat {
    Send,
    Stop,
}

/// Pure decision for one turn of the heartbeat loop: beat only while this is
/// still the newest loop and a session is on.
pub(crate) fn beat_action(my_gen: u64, current_gen: u64, on: bool) -> Beat {
    if on && my_gen == current_gen {
        Beat::Send
    } else {
        Beat::Stop
    }
}

/// Starts the heartbeat for a session that just began. One loop per session:
/// the generation counter retires any older one. A PC that does not know the
/// verb (older backend) just answers an error, which is ignored - the beat
/// is best effort and never shows the owner a message.
fn start_heartbeat(app: &AppHandle) {
    let my_gen = BEAT_GEN.fetch_add(1, Ordering::SeqCst) + 1;
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(HEARTBEAT_EVERY).await;
            if beat_action(my_gen, BEAT_GEN.load(Ordering::SeqCst), on_here()) == Beat::Stop {
                return;
            }
            if let Ok(out) = post(&app, "/api/screen", heartbeat_body(), WRITE_TIMEOUT).await {
                // The PC's answer carries the session's state: if it says
                // the session ended, the sign follows.
                if out.get("on").is_some() {
                    on_status(&app, &out);
                }
            }
        }
    });
}

/// Is a watch session on on this PC (the tray asks).
pub fn on_here() -> bool {
    ON_HERE.load(Ordering::SeqCst)
}

/// The body of a look. `whole`: the whole screen the window is on, instead
/// of only the window in front.
pub(crate) fn look_body(whole: bool) -> serde_json::Value {
    serde_json::json!({ "do": "look", "whole": whole })
}

/// The one field that asks the PC to hand back the look's CLEANED picture as
/// well (the owner's decision of 2026-10-07;
/// `.dsh-scratch/SCREEN-ATTACH-DESIGN.md`; `backend/jarvis_screen_attach.py`).
/// It rides on the LOOK, on jarvis_screen.py's own route: a second route would
/// be a second thing to keep in step with the session rules.
pub(crate) const WANT_PICTURE: &str = "picture";

/// The body of a look that also asks for the picture - the one the Look at
/// this key sends, so the owner's one action both looks and attaches.
/// "Watch with me" sends `look_body` instead: it answers questions about the
/// screen, it does not attach one.
pub(crate) fn attach_body(whole: bool) -> serde_json::Value {
    let mut body = look_body(whole);
    body["want"] = serde_json::json!(WANT_PICTURE);
    body
}

/// The `screen-captured` payload (commands.rs `CapturePayload`'s shape, which
/// main.js's `attachCapture` reads) taken from the PC's answer to an
/// `attach_body` look, or None when there is no usable picture - then
/// [`capture_why`] says why.
///
/// WHAT IS ACCEPTED, AND WHY SO LITTLE. Only a picture the PC itself says is
/// `image/png` - the cleaner's own output (`jarvis_picture.encode_png`) - which
/// really decodes as base64, starts with a PNG's signature, and is inside
/// `MAX_ATTACH_BYTES`. A JPEG, some other `image/*`, or a body that is not the
/// PC's cleaned PNG is refused: this app must never be the place a raw screen
/// picture arrives, and `look-rules.mjs` holds it to that. The decoded length
/// is what the thumbnail shows, so what the owner reads is what is really
/// there. Nothing here is written to a file, a log or an event payload other
/// than the one the page draws.
pub(crate) fn capture_payload(
    out: &serde_json::Value,
    elapsed_ms: u64,
) -> Option<serde_json::Value> {
    let pic = out.get("picture")?;
    if pic.get("mime").and_then(|v| v.as_str()) != Some("image/png") {
        return None;
    }
    let data = pic.get("data").and_then(|v| v.as_str()).unwrap_or("");
    if data.is_empty() {
        return None;
    }
    let raw = BASE64.decode(data).ok()?;
    if raw.len() < PNG_SIG.len() || raw.len() > MAX_ATTACH_BYTES || !raw.starts_with(PNG_SIG) {
        return None;
    }
    let width = pic.get("width").and_then(|v| v.as_u64()).unwrap_or(0);
    let height = pic.get("height").and_then(|v| v.as_u64()).unwrap_or(0);
    if width == 0 || height == 0 {
        return None;
    }
    Some(serde_json::json!({
        "dataUri": format!("data:image/png;base64,{data}"),
        "width": width,
        "height": height,
        "bytes": raw.len(),
        "elapsedMs": elapsed_ms,
    }))
}

/// Why there is no picture to attach, in plain words: the PC's own reason when
/// it gave one (`picture_why` for a picture it would not verify; `said` for a
/// look it refused at a password box), this app's own `PICTURE_MISSING`
/// sentence when the look worked and the PC said nothing about a picture at all
/// (a backend whose `jarvis_screen_attach.py` is not installed), and
/// `NO_PICTURE` otherwise. Never a word from the screen.
pub(crate) fn capture_why(out: &serde_json::Value) -> String {
    for key in ["picture_why", "said"] {
        if let Some(text) = out
            .get(key)
            .and_then(|v| v.as_str())
            .map(str::trim)
            .filter(|s| !s.is_empty())
        {
            return text.to_string();
        }
    }
    if out.get("ok").and_then(|v| v.as_bool()) == Some(true) {
        return PICTURE_MISSING.to_string();
    }
    NO_PICTURE.to_string()
}

/// The body of one `screen_watch` verb, or why it is not one.
pub(crate) fn watch_body(
    action: &str,
    minutes: Option<u32>,
    by: Option<&str>,
) -> Result<serde_json::Value, String> {
    if !WATCH_ACTIONS.contains(&action) {
        return Err(format!("Watch with me cannot {action:?}"));
    }
    let mut body = serde_json::json!({ "do": action });
    match action {
        "start" => {
            // The PC ends a Watch started from this app after about 45 seconds
            // without a heartbeat (jarvis_screen.py), so it must say who started it.
            body["from"] = serde_json::json!("desktop");
            if let Some(m) = minutes {
                if !(1..=120).contains(&m) {
                    return Err("Say 1 to 120 minutes.".to_string());
                }
                body["minutes"] = serde_json::json!(m);
            }
            if let Some(by) = by.filter(|b| STARTS.contains(b)) {
                body["by"] = serde_json::json!(by);
            }
        }
        "extend" => {
            let m = minutes.unwrap_or(20);
            if !(1..=120).contains(&m) {
                return Err("Say 1 to 120 more minutes.".to_string());
            }
            body["minutes"] = serde_json::json!(m);
        }
        _ => {}
    }
    Ok(body)
}

/// The body of one "Never look at" change: a kind ("program" or "site") and
/// the name, both plain words. Nothing else goes in.
pub(crate) fn never_body(
    action: &str,
    kind: Option<&str>,
    value: Option<&str>,
) -> Result<serde_json::Value, String> {
    if !NEVER_ACTIONS.contains(&action) {
        return Err(format!("The Never look at list cannot {action:?}"));
    }
    if action == "list" {
        return Ok(serde_json::json!({}));
    }
    let kind = kind.unwrap_or("");
    if kind != "program" && kind != "site" {
        return Err("Say whether it is a program or a website.".to_string());
    }
    let value = value.unwrap_or("").trim();
    if value.is_empty() || value.len() > 200 {
        return Err(
            "Type the name of a program (like MyBank.exe) or a website (like \
                    mybank.com)."
                .to_string(),
        );
    }
    Ok(serde_json::json!({ "do": action, "kind": kind, "value": value }))
}

/// The body of one picture-mode verb, or why it is not one. Only a switch
/// position goes in - nothing else.
pub(crate) fn picture_body(action: &str) -> Result<serde_json::Value, String> {
    if !PICTURE_ACTIONS.contains(&action) {
        return Err(format!("Picture mode cannot {action:?}"));
    }
    Ok(match action {
        "on" => serde_json::json!({ "enabled": true }),
        "off" => serde_json::json!({ "enabled": false }),
        _ => serde_json::json!({}),
    })
}

/// The PC's answer, as a value or the reason in words.
pub(crate) fn answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    let parsed = serde_json::from_str::<serde_json::Value>(body).ok();
    if (200..300).contains(&status) {
        return parsed
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if status == 404 || status == 501 {
        return Err(MISSING.to_string());
    }
    // A refusal with its own plain words (a look at a password box is 200
    // with ok: false; a 403, 400, 503 carry an `error` sentence).
    if let Some(error) = parsed
        .as_ref()
        .and_then(|v| v.get("error"))
        .and_then(|e| e.as_str())
    {
        return Err(error.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// What the Jarvis bar says about one look: the note when it looked, else the
/// PC's own sentence about why not. Never a word from the screen.
pub(crate) fn look_line(out: &serde_json::Value) -> String {
    let said = |key: &str| {
        out.get(key)
            .and_then(|v| v.as_str())
            .map(str::trim)
            .filter(|s| !s.is_empty())
    };
    if out.get("ok").and_then(|v| v.as_bool()) == Some(true) {
        return said("note").unwrap_or("Looked at your screen.").to_string();
    }
    said("said").unwrap_or(NO_LOOK).to_string()
}

pub(crate) async fn get(app: &AppHandle, path: &str) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    answer(status, &text)
}

pub(crate) async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    timeout: Duration,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(timeout))?
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    answer(status, &text)
}

pub(crate) fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

/// Looking is held on a stale link and while App lock would ask; `None` when
/// it may go ahead. (Stopping is never held.)
fn held(app: &AppHandle) -> Option<&'static str> {
    if stale(app) {
        return Some(STALE_HELD);
    }
    if crate::lock::app_locked(app) {
        return Some(APP_LOCK_HELD);
    }
    None
}

/// What every window hears about the session. `status` is the PC's, fixed
/// words and numbers.
fn payload(app: &AppHandle, status: &serde_json::Value) -> serde_json::Value {
    serde_json::json!({ "status": status, "stale": stale(app) })
}

fn is_on(status: &serde_json::Value) -> bool {
    status.get("on").and_then(|v| v.as_bool()) == Some(true)
}

/// The PC told us the session's state (a read, an answer or the
/// `screen_watch` event): the sign, the tray and every window follow.
pub(crate) fn on_status(app: &AppHandle, status: &serde_json::Value) {
    if !status.is_object() {
        return;
    }
    let on = is_on(status);
    let was = ON_HERE.swap(on, Ordering::SeqCst);
    note_held(status);
    crate::emit_all(app, SCREEN_STATUS, payload(app, status));
    if on {
        if let Err(why) = show_badge(app) {
            eprintln!("[look] the badge did not open: {why}");
        }
        if !was {
            start_heartbeat(app);
        }
    } else if was {
        // Ended: the badge stays a few seconds, saying why.
        let app = app.clone();
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep(BADGE_ENDED_FOR).await;
            if !on_here() {
                hide_badge(&app);
            }
        });
    }
    if on != was {
        crate::tray::watch_changed(app);
    }
}

/// The `screen_watch` event's data: the same fixed keys as the status.
pub(crate) fn on_event(app: &AppHandle, data: &serde_json::Value) {
    on_status(app, data);
}

/// Reads the session once at start-up, so a session that was running when
/// this app (re)started gets its sign again.
pub fn adopt(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(Duration::from_secs(4)).await;
        if let Ok(status) = get(&app, "/api/screen").await {
            if is_on(&status) {
                on_status(&app, &status);
            }
        }
    });
}

/// The session, read now (the bar, the badge and Settings on opening).
#[tauri::command]
pub async fn screen_status(app: AppHandle) -> Result<serde_json::Value, String> {
    let status = get(&app, "/api/screen").await?;
    Ok(payload(&app, &status))
}

/// One verb on the Watch with me session: "start" (no card; held on a stale
/// link and under App lock), "extend" (held on a stale link), "stop" and
/// "drop" (the bar closed; never held). `by`: how a start began.
#[tauri::command]
pub async fn screen_watch(
    app: AppHandle,
    action: String,
    minutes: Option<u32>,
    by: Option<String>,
) -> Result<serde_json::Value, String> {
    run_watch(&app, &action, minutes, by.as_deref()).await
}

pub(crate) async fn run_watch(
    app: &AppHandle,
    action: &str,
    minutes: Option<u32>,
    by: Option<&str>,
) -> Result<serde_json::Value, String> {
    let body = watch_body(action, minutes, by)?;
    match action {
        "start" => {
            if !crate::voice::is_loopback_base(&commands::jarvis_base(app)) {
                return Err(NOT_THIS_PC.to_string());
            }
            if let Some(why) = held(app) {
                return Err(why.to_string());
            }
        }
        "extend" if stale(app) => {
            return Err(STALE_HELD.to_string());
        }
        _ => {}
    }
    let out = post(app, "/api/screen", body, WRITE_TIMEOUT).await?;
    on_status(app, &out);
    Ok(payload(app, &out))
}

/// The Never look at list, for Settings: "list" reads it, "add" is instant
/// (stricter), "remove" raises ONE approval card on this PC (it loosens what
/// Jarvis may see) and answers "pending" - the card is decided in the bar.
#[tauri::command]
pub async fn screen_never(
    app: AppHandle,
    action: String,
    kind: Option<String>,
    value: Option<String>,
) -> Result<serde_json::Value, String> {
    let body = never_body(&action, kind.as_deref(), value.as_deref())?;
    if action == "list" {
        return get(&app, "/api/screen/never-look").await;
    }
    if action == "remove" && stale(&app) {
        return Err(STALE_HELD.to_string());
    }
    post(&app, "/api/screen/never-look", body, WRITE_TIMEOUT).await
}

/// Picture mode's switch, for Settings (backend/jarvis_screen_picture.py; the
/// owner's decision of 2026-09-29): "read" gets the setting - on or off,
/// whether it would work now, the measured seconds per look (never a guess)
/// and the one PowerShell line that installs and measures the model; "on" asks
/// for it to be turned on, which raises ONE approval card on this PC and
/// changes nothing until a person says yes (held on a stale link); "off" is
/// at once and never held. The picture itself never passes through this app.
#[tauri::command]
pub async fn screen_picture(app: AppHandle, action: String) -> Result<serde_json::Value, String> {
    let body = picture_body(&action)?;
    if action == "on" && stale(&app) {
        return Err(STALE_HELD.to_string());
    }
    let out = if action == "read" {
        get(&app, "/api/screen/picture").await
    } else {
        post(&app, "/api/screen/picture", body, WRITE_TIMEOUT).await
    };
    // A PC with the screen routes but not this one answers 404: say which.
    out.map_err(|why| {
        if why == MISSING {
            PICTURE_MISSING.to_string()
        } else {
            why
        }
    })
}

/// The Look at this key: look now, THEN bring up the bar. A refusal is the
/// PC's own plain sentence, in the bar and as a notification (the bar may be
/// hidden or locked).
pub fn look_from_hotkey(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        look_then_bar(&app).await;
    });
}

async fn look_then_bar(app: &AppHandle) {
    if !crate::voice::is_loopback_base(&commands::jarvis_base(app)) {
        commands::notify(app, "Jarvis", NOT_THIS_PC);
        return;
    }
    if let Some(why) = held(app) {
        commands::notify(app, "Jarvis", why);
        return;
    }
    let started = std::time::Instant::now();
    let out = match post(app, "/api/screen", attach_body(false), ATTACH_TIMEOUT).await {
        Ok(out) => out,
        Err(why) => {
            commands::notify_guarded(app, "Jarvis", &why, None);
            return;
        }
    };
    let line = look_line(&out);
    let ok = out.get("ok").and_then(|v| v.as_bool()) == Some(true);
    on_status(app, &out);
    // The bar comes up only now: a window of Jarvis's own in front is what a
    // look would have seen.
    if let Err(err) = crate::windows::show_quickbar(app) {
        eprintln!("[look] unable to show the Jarvis bar: {err}");
    }
    crate::emit_quickbar(
        app,
        SCREEN_LOOK,
        serde_json::json!({ "ok": ok, "note": if ok { line.clone() } else { String::new() },
                            "said": if ok { String::new() } else { line } }),
    );
    // The CLEANED picture, when the PC could make one: it becomes the
    // attachment on the question box, with its thumbnail, before the owner
    // types anything (main.js's `attachCapture`). The PC has already painted
    // every password, key and Never-look window SOLID BLACK, and a picture it
    // could not verify is not handed back at all - so a refusal here is a plain
    // sentence in the strip, never a picture. Nothing is decoded, read, saved
    // or logged on this side: `capture_payload` checks it and the page draws
    // it. Sent AFTER `screen-look`: a successful look's own handler clears the
    // strip's notice, and that must not wipe this refusal with it.
    match capture_payload(&out, started.elapsed().as_millis() as u64) {
        Some(capture) => crate::emit_quickbar(app, crate::events::SCREEN_CAPTURED, capture),
        None => crate::emit_quickbar(app, crate::events::CAPTURE_FAILED, capture_why(&out)),
    }
    crate::emit_quickbar(app, crate::events::FOCUS_INPUT, ());
}

/// "Watch with me": a question is about to start (the Jarvis bar's hotkey,
/// or "Hey Jarvis" heard) - take ONE fresh look, now, before the bar or the
/// answer is in front. Does nothing unless a session is on. Waits (a little)
/// for the PC's answer; never fails a question - no look is just no look.
pub(crate) async fn ask(app: &AppHandle) {
    if !on_here() || held(app).is_some() {
        return;
    }
    match post(
        app,
        "/api/screen",
        serde_json::json!({ "do": "ask" }),
        LOOK_TIMEOUT,
    )
    .await
    {
        Ok(out) => {
            on_status(app, &out);
            if out.get("looked").and_then(|v| v.as_bool()) == Some(true) {
                crate::emit_quickbar(
                    app,
                    SCREEN_LOOK,
                    serde_json::json!({ "ok": true, "note": look_line(&out), "said": "" }),
                );
            } else if out.get("ok").and_then(|v| v.as_bool()) == Some(false) {
                crate::emit_quickbar(
                    app,
                    SCREEN_LOOK,
                    serde_json::json!({ "ok": false, "note": "", "said": look_line(&out) }),
                );
            }
        }
        Err(why) => eprintln!("[look] no look for this question: {why}"),
    }
}

/// [`ask`] from a thread that is not async (the voice listener's).
pub(crate) fn ask_blocking(app: &AppHandle) {
    if !on_here() {
        return;
    }
    tauri::async_runtime::block_on(ask(app));
}

/// The Jarvis bar's hotkey with a session on: the look first, then the bar.
/// Without a session (or with the bar already showing) it is the plain
/// toggle.
pub fn toggle_bar_with_look(app: &AppHandle) -> Result<bool, String> {
    let visible = app
        .get_webview_window(crate::QUICKBAR_LABEL)
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false);
    if visible || !on_here() {
        return crate::windows::toggle_quickbar(app);
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        ask(&app).await;
        match crate::windows::toggle_quickbar(&app) {
            Ok(true) => crate::emit_quickbar(&app, crate::events::FOCUS_INPUT, ()),
            Ok(false) => {}
            Err(err) => eprintln!("[look] quickbar toggle failed: {err}"),
        }
    });
    Ok(false)
}

/// The Jarvis bar closed: a look held for follow-ups is thrown away now.
/// Fire and forget; nothing is held on a stale link for this - it only
/// makes Jarvis keep less.
pub fn bar_closed(app: &AppHandle) {
    // The bar's own note about the last look goes with it, held or not.
    crate::emit_quickbar(app, SCREEN_LOOK, serde_json::json!({ "closed": true }));
    if !LOOK_HELD.load(Ordering::SeqCst) {
        return;
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let _ = post(
            &app,
            "/api/screen",
            serde_json::json!({ "do": "drop" }),
            WRITE_TIMEOUT,
        )
        .await;
    });
}

/// Is a look held on the PC for follow-ups? Kept from the last status, so
/// closing the bar costs no request when there is nothing to drop.
static LOOK_HELD: AtomicBool = AtomicBool::new(false);

/// The tray's row, the hotkey (off until picked) and voice: start or end
/// Watch with me. A refusal is a notification - the bar may be hidden.
pub fn toggle(app: &AppHandle, by: &'static str) {
    let by = if STARTS.contains(&by) { by } else { "button" };
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let result = if on_here() {
            run_watch(&app, "stop", None, None).await
        } else {
            run_watch(&app, "start", None, Some(by)).await
        };
        if let Err(why) = result {
            commands::notify_guarded(&app, "Watch with me", &why, None);
        }
    });
}

pub fn toggle_from_tray(app: &AppHandle) {
    toggle(app, "tray");
}

// ---------------------------------------------------------------------------
// The badge: "Jarvis is watching - 24 min left - Stop", always on top
// ---------------------------------------------------------------------------

/// Opens the badge at the top of the main screen. It shows only what the
/// sign says (fixed words and minutes) and its buttons, so it is not behind
/// App lock, like the Live badge and the floating face: the owner must always
/// be able to see that Jarvis is watching, and stop it. It is hidden from
/// screen captures (`set_content_protected`), so it never shows up in
/// Jarvis's own pictures of the screen - whether Windows honours that for
/// every capture method is checked on the owner's PC, not here.
pub fn show_badge(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(BADGE_LABEL) {
        return window
            .show()
            .map_err(|e| format!("unable to show the watch badge: {e}"));
    }
    let window = tauri::WebviewWindowBuilder::new(
        app,
        BADGE_LABEL,
        tauri::WebviewUrl::App("watch-badge.html".into()),
    )
    .title("Jarvis is watching")
    .inner_size(BADGE_W, BADGE_H)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .decorations(false)
    .transparent(true)
    .always_on_top(true)
    .skip_taskbar(true)
    .shadow(false)
    .content_protected(true)
    // It never takes the keyboard from what the owner is doing; its buttons
    // are clicked with the mouse.
    .focused(false)
    .visible(false)
    .build()
    .map_err(|e| format!("unable to open the watch badge: {e}"))?;
    if let Ok(Some(monitor)) = window.current_monitor() {
        let size = monitor.size();
        let scale = monitor.scale_factor();
        let at = monitor.position();
        let width = (BADGE_W * scale) as i32;
        // Below the Live badge's spot, so both can be up at once.
        let x = at.x + (size.width as i32 - width) / 2;
        let y = at.y + (110.0 * scale) as i32;
        let _ = window.set_position(PhysicalPosition::new(x, y));
    }
    window
        .show()
        .map_err(|e| format!("unable to show the watch badge: {e}"))
}

pub fn hide_badge(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(BADGE_LABEL) {
        let _ = window.hide();
    }
}

/// Keeps `LOOK_HELD` in step with a status (called with every one).
pub(crate) fn note_held(status: &serde_json::Value) {
    LOOK_HELD.store(
        status.get("look_held").and_then(|v| v.as_bool()) == Some(true),
        Ordering::SeqCst,
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_heartbeat_is_one_fixed_word_inside_the_pcs_silence_limit() {
        assert_eq!(heartbeat_body(), json!({ "do": "heartbeat" }));
        // Between 10 and 15 seconds, and at least three beats fit in the
        // PC's 45 seconds of allowed silence.
        assert!((10..=15).contains(&HEARTBEAT_EVERY.as_secs()));
        assert!(HEARTBEAT_EVERY.as_secs() * 3 <= HEARTBEAT_PC_LIMIT_SECS);
        // Not a verb a page can send.
        assert!(!WATCH_ACTIONS.contains(&"heartbeat"));
    }

    #[test]
    fn the_heartbeat_stops_when_the_session_ends_or_a_newer_loop_starts() {
        assert_eq!(beat_action(3, 3, true), Beat::Send);
        assert_eq!(beat_action(3, 3, false), Beat::Stop);
        assert_eq!(beat_action(3, 4, true), Beat::Stop);
    }

    #[test]
    fn a_look_body_says_only_what_to_look_at() {
        assert_eq!(look_body(false), json!({ "do": "look", "whole": false }));
        assert_eq!(look_body(true), json!({ "do": "look", "whole": true }));
        // The key's own look asks for the picture too, and nothing else.
        assert_eq!(
            attach_body(false),
            json!({ "do": "look", "whole": false, "want": "picture" })
        );
        assert_eq!(
            attach_body(true),
            json!({ "do": "look", "whole": true, "want": "picture" })
        );
        assert_eq!(WANT_PICTURE, "picture");
    }

    /// A 1x1 PNG this repository's cleaner could have written (`clean` returns
    /// the original bytes when nothing had to be painted, so any real PNG will
    /// do here). Made up, decoded nowhere.
    const PNG_1PX: &[u8] = &[
        0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, b'I', b'H', b'D',
        b'R', 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00,
    ];

    fn picture_answer(data: &str, mime: &str) -> serde_json::Value {
        json!({ "ok": true, "note": "Looked at: Chrome window \u{b7} words only",
                "picture": { "data": data, "mime": mime, "width": 1920, "height": 1080,
                             "bytes": 4096 } })
    }

    #[test]
    fn only_the_pcs_own_cleaned_png_becomes_an_attachment() {
        let data = BASE64.encode(PNG_1PX);
        let got = capture_payload(&picture_answer(&data, "image/png"), 37).expect("a PNG is taken");
        assert_eq!(got["dataUri"], format!("data:image/png;base64,{data}"));
        assert_eq!(got["width"], 1920);
        assert_eq!(got["height"], 1080);
        // The size shown is the REAL decoded length, not the PC's own claim.
        assert_eq!(got["bytes"], PNG_1PX.len());
        assert_eq!(got["elapsedMs"], 37);

        // Anything that is not the cleaner's PNG is refused, however well shaped.
        for (data, mime) in [
            (BASE64.encode(b"not a png at all"), "image/png"),
            (BASE64.encode(b"\xff\xd8\xff\xe0jpegish"), "image/png"),
            (BASE64.encode(PNG_1PX), "image/jpeg"),
            (BASE64.encode(PNG_1PX), ""),
            ("!!!not base64!!!".to_string(), "image/png"),
            (String::new(), "image/png"),
        ] {
            assert!(
                capture_payload(&picture_answer(&data, mime), 1).is_none(),
                "{mime} {data:.16}"
            );
        }
        // No picture at all, and a picture with no size: nothing to attach.
        assert!(capture_payload(&json!({ "ok": true }), 1).is_none());
        let mut no_size = picture_answer(&BASE64.encode(PNG_1PX), "image/png");
        no_size["picture"]["width"] = json!(0);
        assert!(capture_payload(&no_size, 1).is_none());
        // The size cap: one byte past it is refused rather than sent on.
        let mut big = vec![0u8; MAX_ATTACH_BYTES + 1];
        big[..PNG_SIG.len()].copy_from_slice(PNG_SIG);
        let over = picture_answer(&BASE64.encode(&big), "image/png");
        assert!(capture_payload(&over, 1).is_none());
        // No payload ever carries a path, a file name or a log line.
        let text = capture_payload(&picture_answer(&BASE64.encode(PNG_1PX), "image/png"), 1)
            .unwrap()
            .to_string();
        assert!(!text.contains("http") && !text.contains(".png\""), "{text}");
    }

    #[test]
    fn a_refused_picture_says_why_in_the_pcs_own_words() {
        assert_eq!(
            capture_why(&json!({ "ok": true, "picture_why": "The picture could not be checked." })),
            "The picture could not be checked."
        );
        // A look refused at a password box: the PC's own sentence, which is
        // also what `screen-look` shows.
        assert_eq!(
            capture_why(&json!({ "ok": false, "said": "There's a password box in front." })),
            "There's a password box in front."
        );
        // A look that worked and said nothing about a picture: the PC's Jarvis
        // does not know the field yet.
        assert_eq!(capture_why(&json!({ "ok": true })), PICTURE_MISSING);
        assert_eq!(capture_why(&json!({})), NO_PICTURE);
        // Never a `part` (the screen's words), even if a wrong PC sent one.
        let leaked = capture_why(&json!({ "ok": false, "part": "Snorvelquist balance owed" }));
        assert!(!leaked.contains("Snorvelquist"), "{leaked}");
    }

    #[test]
    fn watch_verbs_are_checked_and_carry_only_fixed_words() {
        assert_eq!(
            watch_body("stop", None, None).unwrap(),
            json!({ "do": "stop" })
        );
        assert_eq!(
            watch_body("drop", Some(5), Some("tray")).unwrap(),
            json!({ "do": "drop" })
        );
        assert_eq!(
            watch_body("start", None, None).unwrap(),
            json!({ "do": "start", "from": "desktop" })
        );
        assert_eq!(
            watch_body("start", Some(20), Some("hotkey")).unwrap(),
            json!({ "do": "start", "from": "desktop", "minutes": 20, "by": "hotkey" })
        );
        // A `by` that is not one of the fixed words is left out, never sent.
        assert_eq!(
            watch_body("start", None, Some("please do")).unwrap(),
            json!({ "do": "start", "from": "desktop" })
        );
        assert_eq!(
            watch_body("extend", None, None).unwrap(),
            json!({ "do": "extend", "minutes": 20 })
        );
        assert!(watch_body("start", Some(0), None).is_err());
        assert!(watch_body("start", Some(121), None).is_err());
        assert!(watch_body("extend", Some(500), None).is_err());
        // "look" and "ask" are this file's own; the bar cannot send them.
        assert!(watch_body("look", None, None).is_err());
        assert!(watch_body("ask", None, None).is_err());
        assert!(watch_body("", None, None).is_err());
    }

    #[test]
    fn never_look_changes_are_checked() {
        assert_eq!(never_body("list", None, None).unwrap(), json!({}));
        assert_eq!(
            never_body("add", Some("site"), Some(" mybank.com ")).unwrap(),
            json!({ "do": "add", "kind": "site", "value": "mybank.com" })
        );
        assert_eq!(
            never_body("remove", Some("program"), Some("MyBank.exe")).unwrap(),
            json!({ "do": "remove", "kind": "program", "value": "MyBank.exe" })
        );
        assert!(never_body("add", Some("folder"), Some("x")).is_err());
        assert!(never_body("add", None, Some("x")).is_err());
        assert!(never_body("add", Some("site"), Some("   ")).is_err());
        assert!(never_body("add", Some("site"), Some(&"x".repeat(201))).is_err());
        assert!(never_body("wipe", Some("site"), Some("x")).is_err());
    }

    #[test]
    fn picture_mode_verbs_carry_only_a_switch_position() {
        assert_eq!(picture_body("read").unwrap(), json!({}));
        assert_eq!(picture_body("on").unwrap(), json!({ "enabled": true }));
        assert_eq!(picture_body("off").unwrap(), json!({ "enabled": false }));
        for bad in ["", "toggle", "enable", "on ", "ON", "measure", "download"] {
            assert!(picture_body(bad).is_err(), "{bad:?}");
        }
        for verb in PICTURE_ACTIONS {
            assert!(picture_body(verb).is_ok(), "{verb}");
        }
    }

    #[test]
    fn the_pcs_answers_become_a_value_or_plain_words() {
        assert_eq!(
            answer(200, r#"{"ok":true}"#).unwrap(),
            json!({ "ok": true })
        );
        assert!(answer(200, "not json").is_err());
        assert_eq!(answer(404, "").unwrap_err(), MISSING);
        assert_eq!(
            answer(
                403,
                r#"{"error":"Jarvis can only look at the screen of the PC it runs on."}"#
            )
            .unwrap_err(),
            "Jarvis can only look at the screen of the PC it runs on."
        );
        // Never the raw body when the PC gave no sentence.
        let raw = answer(500, "Traceback (most recent call last)").unwrap_err();
        assert!(!raw.contains("Traceback"), "{raw}");
    }

    #[test]
    fn a_look_line_is_the_note_or_the_reason_and_never_a_screens_words() {
        assert_eq!(
            look_line(&json!({ "ok": true, "note": "Looked at: Chrome window \u{b7} words only" })),
            "Looked at: Chrome window \u{b7} words only"
        );
        assert_eq!(look_line(&json!({ "ok": true })), "Looked at your screen.");
        assert_eq!(
            look_line(
                &json!({ "ok": false, "said": "There's a password box in front, so I'm not looking." })
            ),
            "There's a password box in front, so I'm not looking."
        );
        assert_eq!(look_line(&json!({ "ok": false })), NO_LOOK);
        // A `part` (the words) is never read, even if a wrong backend sent one.
        let leaked = look_line(&json!({ "ok": false, "part": "Snorvelquist balance owed" }));
        assert!(!leaked.contains("Snorvelquist"));
    }

    #[test]
    fn only_a_session_that_is_on_counts() {
        assert!(is_on(&json!({ "on": true })));
        assert!(!is_on(&json!({ "on": false })));
        assert!(!is_on(&json!({ "state": "watching" })));
        assert!(!is_on(&json!(null)));
    }

    #[test]
    fn a_held_look_is_remembered_from_the_status() {
        note_held(&json!({ "look_held": true }));
        assert!(LOOK_HELD.load(Ordering::SeqCst));
        note_held(&json!({ "look_held": false }));
        assert!(!LOOK_HELD.load(Ordering::SeqCst));
        note_held(&json!({}));
        assert!(!LOOK_HELD.load(Ordering::SeqCst));
    }

    #[test]
    fn the_words_are_plain() {
        for words in [
            MISSING,
            PICTURE_MISSING,
            STALE_HELD,
            APP_LOCK_HELD,
            NOT_THIS_PC,
            NO_LOOK,
            NO_PICTURE,
        ] {
            assert!(!words.contains("::") && !words.contains('{'), "{words}");
        }
    }
}
