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
//!   {"do":"look"}`), which checks for a password box, the Never look at
//!   list and capture protection, takes the picture in memory, reads its
//!   words and throws the picture away. This app never sees the picture or
//!   the words: it gets a note ("Looked at: Chrome window - words only") or
//!   the plain reason there was no look. Then the bar opens, and a question
//!   asked within two minutes is marked `screen: "look"` (main.js), so the PC
//!   adds the words to THAT question as outside text.
//! * **Watch with me** (the bar's button, the tray's row, a hotkey that is
//!   off until the owner picks a key, or "watch with me" said or typed): a
//!   session with a sign on screen the whole time (`watch-badge.html`, an
//!   always-on-top badge that is hidden from screen captures). No card to
//!   start - the owner's own act - but held on a stale link (rule 4) and
//!   while App lock would ask. While it is on, a fresh look is taken when the
//!   owner STARTS a question: the bar opened by its hotkey, or "Hey Jarvis"
//!   heard. It is used by that one question.
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
//! NOTHING HERE READS THE SCREEN.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

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
const BADGE_H: f64 = 64.0;
/// How long the badge stays up after a session ended, saying why.
const BADGE_ENDED_FOR: Duration = Duration::from_secs(15);
const READ_TIMEOUT: Duration = Duration::from_secs(5);
/// A look answers in a fraction of a second (the words are read after); this
/// only stops a stuck PC from holding the bar back for long.
const LOOK_TIMEOUT: Duration = Duration::from_secs(4);
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);

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

pub(crate) const MISSING: &str = "This PC's Jarvis does not have \"Look at this\" and \"Watch \
     with me\" yet. Run scripts\\apply-patches.ps1 on the PC to add them.";
pub(crate) const PICTURE_MISSING: &str = "This PC's Jarvis does not have picture mode yet. Run \
     scripts\\apply-patches.ps1 on the PC to add it.";
const STALE_HELD: &str = "The connection to Jarvis is catching up, so looking at the screen is \
     held until it does - try again in a moment.";
pub(crate) const APP_LOCK_HELD: &str = "Jarvis is locked (App lock). Open the Jarvis bar and \
     unlock it with Windows Hello, then ask Jarvis to look.";
pub(crate) const NOT_THIS_PC: &str = "Jarvis only looks at the screen of the PC it runs on, and \
     this app is set to a Jarvis on another machine. Change the address in Settings, Connection, \
     if this PC is the one to look at.";
/// The Jarvis bar's line when a look could not be taken and the PC gave no
/// reason of its own.
const NO_LOOK: &str = "Jarvis could not look at your screen just now.";

/// Is a watch session on on this PC (the tray asks).
pub fn on_here() -> bool {
    ON_HERE.load(Ordering::SeqCst)
}

/// The body of a look. `whole`: the whole screen the window is on, instead
/// of only the window in front.
pub(crate) fn look_body(whole: bool) -> serde_json::Value {
    serde_json::json!({ "do": "look", "whole": whole })
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

async fn get(app: &AppHandle, path: &str) -> Result<serde_json::Value, String> {
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

async fn post(
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

fn stale(app: &AppHandle) -> bool {
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
        "extend" => {
            if stale(app) {
                return Err(STALE_HELD.to_string());
            }
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
    let out = match post(app, "/api/screen", look_body(false), LOOK_TIMEOUT).await {
        Ok(out) => out,
        Err(why) => {
            commands::notify(app, "Jarvis", &why);
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
            commands::notify(&app, "Watch with me", &why);
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
    fn a_look_body_says_only_what_to_look_at() {
        assert_eq!(look_body(false), json!({ "do": "look", "whole": false }));
        assert_eq!(look_body(true), json!({ "do": "look", "whole": true }));
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
            json!({ "do": "start" })
        );
        assert_eq!(
            watch_body("start", Some(20), Some("hotkey")).unwrap(),
            json!({ "do": "start", "minutes": 20, "by": "hotkey" })
        );
        // A `by` that is not one of the fixed words is left out, never sent.
        assert_eq!(
            watch_body("start", None, Some("please do")).unwrap(),
            json!({ "do": "start" })
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
        ] {
            assert!(!words.contains("::") && !words.contains('{'), "{words}");
        }
    }
}
