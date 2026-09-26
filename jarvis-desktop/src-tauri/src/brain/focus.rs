//! Focus sessions (the owner's decision of 2026-09-25; backend/focus.patch,
//! `jarvis_focus.py`; JARVIS-API.md section 31).
//!
//! A timer plus Quiet: on this PC, Jarvis watches which app or site is in
//! front, names a drift out loud, keeps only counts, and ends with a report
//! card. Three commands, and one thing that is not a command:
//!
//! * [`focus_status`] - `GET /api/focus`: the countdown, booleans, counts and
//!   the last report card. A read (Brain and widget). Never what was in
//!   front: the PC does not send it.
//! * [`focus_start`] - `POST /api/focus/start {"minutes", "on"}`. No approval
//!   card (jarvis_focus.py says why). Held on a stale link: it makes Jarvis
//!   watch. Brain only.
//! * [`focus_act`] - `POST /api/focus/act {"do", "minutes"?}`: ONE thing to
//!   the running session - pause, resume, extend, stop, or lock (the widget's
//!   "Lock on": Jarvis's own window is in front when it is pressed, so the
//!   PC waits for the owner to land somewhere and locks on there). Resume,
//!   extend and lock are held on a stale link; pause and stop are not - they
//!   only make Jarvis do less. Brain and widget.
//! * [`play_callout`] - stream.rs calls it when a `focus` event says a line
//!   is waiting (`{"state": "callout", "seq"}` - a number, never words). It
//!   fetches the line as SOUND from `GET /api/focus/callout?seq=` and hands
//!   it to the Jarvis bar to play. Only when the backend is on this PC
//!   (loopback): the PC refuses anyone else anyway, and the words never
//!   travel - the line names what was in front, so it stays on the PC.
//!
//! STOP-EVERYTHING HOOK: the "stop everything" hotkey was built at the same
//! time as this. The Jarvis bar's `stopSpeaking` silences a playing line;
//! to pause the session too, the hotkey can call [`focus_act`]'s body with
//! `"pause"` (or the backend's `jarvis_focus.ENGINE.stop_everything()`).

use std::time::Duration;

use base64::Engine as _;
use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no focus sessions. The phone says the same
/// (`Focus.MISSING`).
pub(crate) const FOCUS_MISSING: &str =
    "Your PC's Jarvis does not have focus sessions yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// Everything the desktop may ask of a running session. Never "all".
pub(crate) const ACTIONS: &[&str] = &["pause", "resume", "extend", "stop", "lock"];

/// Held on a stale link: they make Jarvis watch, or watch for longer.
pub(crate) const HELD_WHEN_STALE: &[&str] = &["resume", "extend", "lock"];

/// How long the fetch of one spoken line may take (the PC makes the sound).
const CALLOUT_TIMEOUT: Duration = Duration::from_secs(20);

/// How many times "Stop everything" has been pressed since the app started.
/// A callout notes it before asking the PC for the sound, and drops the
/// sound if a stop happened while it was being made (bug audit 2026-09-26,
/// #1): the PC takes the line first and synthesises it after, so a stop in
/// between found nothing playing yet, and the line played a second later.
static STOPS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

/// Called by `commands::stop_everything_now` before anything else.
pub fn note_stop_everything() {
    STOPS.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
}

fn stops_so_far() -> u64 {
    STOPS.load(std::sync::atomic::Ordering::SeqCst)
}

/// Whether a callout started when `before` stops had been counted may
/// still play now.
fn still_wanted(before: u64, now: u64) -> bool {
    before == now
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// [`focus_status`]'s reading of the answer.
pub(crate) fn status_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("on").is_some_and(|o| o.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": FOCUS_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`focus_start`]'s and [`focus_act`]'s reading: the PC's own sentence,
/// whether it changed or refused (409 "No focus session is running.").
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Err(FOCUS_MISSING.to_string());
    }
    if status == 400 || status == 409 {
        if let Some(error) = parsed(body)
            .as_ref()
            .and_then(|v| v.get("error"))
            .and_then(|e| e.as_str())
        {
            return Err(error.to_string());
        }
    }
    Err(commands::backend_refusal(status, body))
}

/// The body for a start: minutes 1 to 240, and the owner's "on what" (at
/// most 60 characters, spaces tidied).
pub(crate) fn start_body(minutes: u32, on: &str) -> Result<serde_json::Value, String> {
    if !(1..=240).contains(&minutes) {
        return Err("A focus session is 1 to 240 minutes long.".to_string());
    }
    let words: String = on
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .chars()
        .take(60)
        .collect();
    Ok(serde_json::json!({ "minutes": minutes, "on": words }))
}

/// The body for ONE action. Anything not in [`ACTIONS`] is refused here.
pub(crate) fn act_body(action: &str, minutes: Option<u32>) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!(
            "{action:?} is not something a focus session can do"
        ));
    }
    Ok(match (action, minutes) {
        ("extend", Some(m)) if (1..=240).contains(&m) => {
            serde_json::json!({ "do": "extend", "minutes": m })
        }
        ("extend", _) => serde_json::json!({ "do": "extend", "minutes": 10 }),
        _ => serde_json::json!({ "do": action }),
    })
}

/// The callout's number out of a `focus` event, when it is one.
pub(crate) fn callout_seq(data: &serde_json::Value) -> Option<u64> {
    if data.get("state").and_then(|s| s.as_str()) != Some("callout") {
        return None;
    }
    data.get("seq").and_then(|s| s.as_u64())
}

/// The focus session. A read.
#[tauri::command]
pub async fn focus_status(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/focus"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = status_answer(status, &body)?;
    // What the session is "on" is the owner's own words, like a reminder's:
    // hidden with the private lists (continuity audit 2026-09-26, #10).
    Ok(if crate::lock::private_hidden(&app) {
        hide_intent(answer)
    } else {
        answer
    })
}

/// The status with its `intent` taken out and `intent_hidden` set, when
/// there was one to hide.
pub(crate) fn hide_intent(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = answer.as_object_mut() {
        let had = obj
            .get("intent")
            .and_then(|v| v.as_str())
            .is_some_and(|s| !s.trim().is_empty());
        if had {
            obj.insert("intent".into(), serde_json::json!(""));
            obj.insert("intent_hidden".into(), serde_json::json!(true));
        }
    }
    answer
}

/// Start a session. Held on a stale link.
#[tauri::command]
pub async fn focus_start(
    app: AppHandle,
    minutes: u32,
    on: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = start_body(minutes, &on)?;
    post(&app, "/api/focus/start", body).await
}

/// ONE thing to the running session. Resume, extend and lock are held on a
/// stale link; pause and stop are let through.
#[tauri::command]
pub async fn focus_act(
    app: AppHandle,
    action: String,
    minutes: Option<u32>,
) -> Result<serde_json::Value, String> {
    if HELD_WHEN_STALE.contains(&action.as_str()) {
        require_link_live(&app)?;
    }
    let body = act_body(&action, minutes)?;
    post(&app, "/api/focus/act", body).await
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    change_answer(status, &text)
}

/// A `focus` event said a line is waiting: fetch it as sound from THIS PC
/// and give it to the Jarvis bar to play. Nothing when the backend is not
/// on this PC, when the line is gone (fetched, or waited too long), or when
/// there is no voice - the widget's countdown still tints on a drift.
pub async fn play_callout(app: AppHandle, base: String, data: serde_json::Value) {
    let Some(seq) = callout_seq(&data) else {
        return;
    };
    let stops_before = stops_so_far();
    if !crate::voice::is_loopback_base(&base) {
        return;
    }
    let Ok(headers) = commands::jarvis_headers(&app) else {
        return;
    };
    let Ok(client) = commands::jarvis_client(Some(CALLOUT_TIMEOUT)) else {
        return;
    };
    let Ok(response) = client
        .get(format!("{base}/api/focus/callout"))
        .query(&[("seq", seq.to_string())])
        .headers(headers)
        .send()
        .await
    else {
        return;
    };
    if !response.status().is_success() {
        return;
    }
    let Ok(bytes) = response.bytes().await else {
        return;
    };
    if bytes.len() < 44 || &bytes[..4] != b"RIFF" {
        return;
    }
    if !still_wanted(stops_before, stops_so_far()) {
        return;
    }
    let uri = format!(
        "data:audio/wav;base64,{}",
        base64::engine::general_purpose::STANDARD.encode(&bytes)
    );
    crate::emit_quickbar(
        &app,
        crate::events::FOCUS_CALLOUT,
        serde_json::json!({ "uri": uri }),
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn what_a_session_is_on_is_hidden_with_the_private_lists() {
        let out = hide_intent(serde_json::json!({"on": true, "intent": "the tax return"}));
        assert_eq!(out["intent"], "");
        assert_eq!(out["intent_hidden"], true);
        let none = hide_intent(serde_json::json!({"on": true, "intent": ""}));
        assert!(none.get("intent_hidden").is_none());
    }

    #[test]
    fn a_stop_while_the_sound_was_being_made_drops_it() {
        assert!(still_wanted(3, 3));
        assert!(!still_wanted(3, 4));
        let before = stops_so_far();
        note_stop_everything();
        assert!(!still_wanted(before, stops_so_far()));
    }

    #[test]
    fn the_status_is_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"available": true, "on": true, "left_s": 1500, "drifts": 1}"#;
        assert_eq!(status_answer(200, body).unwrap()["left_s"], 1500);
        for old in [404, 501] {
            let a = status_answer(old, "{}").unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], FOCUS_MISSING);
        }
        assert!(status_answer(200, r#"{"ok": true}"#).is_err());
        assert!(status_answer(200, "not json").is_err());
    }

    #[test]
    fn a_refusal_is_the_pcs_own_sentence() {
        let e = change_answer(
            409,
            r#"{"ok": false, "error": "No focus session is running."}"#,
        );
        assert_eq!(e.unwrap_err(), "No focus session is running.");
        assert_eq!(change_answer(404, "").unwrap_err(), FOCUS_MISSING);
        assert_eq!(
            change_answer(200, r#"{"ok": true, "said": "Paused."}"#).unwrap()["said"],
            "Paused."
        );
    }

    #[test]
    fn bodies_are_only_what_a_session_can_do() {
        assert_eq!(
            start_body(30, "  the   essay ").unwrap(),
            serde_json::json!({"minutes": 30, "on": "the essay"})
        );
        assert!(start_body(0, "").is_err());
        assert!(start_body(241, "").is_err());
        assert_eq!(
            act_body("pause", None).unwrap(),
            serde_json::json!({"do": "pause"})
        );
        assert_eq!(act_body("extend", None).unwrap()["minutes"], 10);
        assert_eq!(act_body("extend", Some(5)).unwrap()["minutes"], 5);
        assert!(act_body("approve", None).is_err());
        assert!(act_body("stop_all", None).is_err());
        for held in HELD_WHEN_STALE {
            assert!(ACTIONS.contains(held));
        }
        assert!(!HELD_WHEN_STALE.contains(&"pause"));
        assert!(!HELD_WHEN_STALE.contains(&"stop"));
    }

    #[test]
    fn only_a_callout_event_asks_for_a_line() {
        assert_eq!(
            callout_seq(&serde_json::json!({"state": "callout", "seq": 7})),
            Some(7)
        );
        assert_eq!(callout_seq(&serde_json::json!({"state": "changed"})), None);
        assert_eq!(callout_seq(&serde_json::json!({"state": "callout"})), None);
    }
}
