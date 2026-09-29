//! "Inbox tidy by voice" - the Undo strip (the owner's decision of
//! 2026-09-28; backend `jarvis_inbox_tidy.py`, inbox-tidy.patch;
//! JARVIS-API.md section 92).
//!
//! The owner says "archive the newsletters from last week". Jarvis finds the
//! emails on this PC and raises ONE approval card that lists every email it
//! will touch (an ordinary card, approved in the Jarvis bar - never by voice,
//! never from the widget's one line: see `email_sending::is_email`). Approved,
//! the PC does it and keeps a record for 10 minutes; the strip under the
//! Jarvis bar's input offers Undo.
//!
//! Two commands, for the Jarvis bar (`permissions/surfaces.toml`,
//! `inbox-tidy`):
//!
//! * [`inbox_tidy_read`] - `GET /api/email/tidy`: whether a tidy is open to
//!   Undo, as counts and the PC's own words (never a sender or a subject).
//!   A read, never held. While App lock has locked Jarvis, or "Windows
//!   Hello for memory lists and chat history" hides the private lists, the
//!   PC's words are taken out here (the strip says only that the inbox was
//!   tidied) and `hidden` is true.
//! * [`inbox_tidy_undo`] - `POST /api/email/tidy/undo`: one tap, no card. It
//!   puts back exactly what the last tidy changed. It acts on the owner's
//!   mailbox, so it is held while the event stream is stale (rule 4), and
//!   while the words are hidden the owner must unlock first.
//!
//! The answer-reading functions are plain functions of (status, body), so
//! their tests run against the real answers (`tests/fixtures/
//! inbox-tidy-cases.json`, made by tools/gen_inbox_tidy_cases.py).

use tauri::{AppHandle, Manager};

use super::{READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

pub(crate) const STATUS_PATH: &str = "/api/email/tidy";
pub(crate) const UNDO_PATH: &str = "/api/email/tidy/undo";

/// A PC without `jarvis_inbox_tidy.py` / `inbox-tidy.patch`. The phone and
/// inbox-tidy.js say the same - all from the contract's `words.missing`.
pub(crate) const INBOX_TIDY_MISSING: &str =
    "Your PC's Jarvis cannot tidy your inbox yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

/// Undo, while the words are hidden: the owner unlocks Jarvis first.
pub(crate) const LOCKED: &str = "Unlock Jarvis to undo this.";

/// The strip's only line while the words are hidden.
pub(crate) const HIDDEN: &str = "Your inbox was tidied. You can undo it for a few minutes.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A 404 that jarvis_inbox_tidy itself sent carries `"ok": false`; a PC
/// without the routes at all does not.
fn own_404(body: &str) -> bool {
    parsed(body).and_then(|v| v.get("ok").and_then(|o| o.as_bool())) == Some(false)
}

/// [`inbox_tidy_read`]'s reading: the PC's own body on a 2xx;
/// `{"available": false, "why": INBOX_TIDY_MISSING}` from a PC without the
/// routes; the PC's own sentence otherwise.
pub(crate) fn read_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if (status == 404 && !own_404(body)) || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": INBOX_TIDY_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`inbox_tidy_undo`]'s reading: the PC's own body on a 2xx (`message` says
/// how many came back) with the status as `http`; the PC's own sentence
/// otherwise (409: nothing to undo; 503: the mail server could not be
/// reached, and it can be tried again).
pub(crate) fn undo_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let mut v = parsed(body).ok_or_else(|| UNREADABLE.to_string())?;
        if let Some(o) = v.as_object_mut() {
            o.insert("http".into(), serde_json::json!(status));
        }
        return Ok(v);
    }
    if (status == 404 && !own_404(body)) || status == 501 {
        return Err(INBOX_TIDY_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The status with the PC's words taken out, for while the words are hidden
/// or Jarvis is locked: only that a tidy is open, and for how long. The
/// count, the action and the sentence go; `hidden` says why.
pub(crate) fn redact(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = answer.as_object_mut() {
        obj.insert("hidden".into(), serde_json::json!(true));
        if let Some(undo) = obj.get_mut("undo").and_then(|u| u.as_object_mut()) {
            undo.insert("said".into(), serde_json::json!(HIDDEN));
            undo.insert("count".into(), serde_json::json!(0));
            undo.insert("action".into(), serde_json::json!(""));
            undo.insert("action_name".into(), serde_json::json!(""));
            undo.insert("more".into(), serde_json::json!(0));
        }
        obj.remove("last");
    }
    answer
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

fn words_hidden(app: &AppHandle) -> bool {
    crate::lock::private_hidden(app) || crate::lock::app_locked(app)
}

/// The status: is a tidy open to Undo. A read.
#[tauri::command]
pub async fn inbox_tidy_read(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{STATUS_PATH}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    let answer = read_answer(status, &text)?;
    Ok(if words_hidden(&app) {
        redact(answer)
    } else {
        answer
    })
}

/// Undo the newest tidy - one tap, no card. Held on a stale link, and while
/// the words are hidden (see the module note).
#[tauri::command]
pub async fn inbox_tidy_undo(app: AppHandle) -> Result<serde_json::Value, String> {
    if words_hidden(&app) {
        return Err(LOCKED.to_string());
    }
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{UNDO_PATH}"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&serde_json::json!({}))
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    undo_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The real answers, made by `tools/gen_inbox_tidy_cases.py`.
    const CASES: &str = include_str!("../../../tests/fixtures/inbox-tidy-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("inbox-tidy-cases.json is JSON")
    }

    #[test]
    fn every_real_status_is_passed_on_unchanged() {
        let doc = cases();
        let all = doc["cases"].as_object().expect("cases");
        assert!(all.len() >= 8);
        for (name, case) in all {
            let (Some(status), Some(body)) = (case["status"].as_u64(), case.get("body")) else {
                continue;
            };
            if name.starts_with("status_") {
                assert_eq!(
                    &read_answer(status as u16, &body.to_string()).unwrap(),
                    body,
                    "{name}"
                );
            }
        }
    }

    #[test]
    fn every_real_undo_answer_reads_the_way_the_strip_expects() {
        let doc = cases();
        let done = &doc["cases"]["undo_done"];
        let got = undo_answer(
            done["status"].as_u64().unwrap() as u16,
            &done["body"].to_string(),
        )
        .unwrap();
        assert_eq!(got["http"], 200);
        assert_eq!(got["message"], done["body"]["message"]);
        for name in ["undo_nothing", "undo_unreachable"] {
            let case = &doc["cases"][name];
            let said = case["body"]["error"].as_str().unwrap();
            let e = undo_answer(
                case["status"].as_u64().unwrap() as u16,
                &case["body"].to_string(),
            )
            .expect_err(name);
            assert!(e.starts_with(&said[..1].to_uppercase()), "{name}: {e}");
        }
    }

    #[test]
    fn a_pc_without_it_says_so() {
        let doc = cases();
        let missing = doc["missing"]["body"].to_string();
        let got = read_answer(404, &missing).unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], INBOX_TIDY_MISSING);
        assert_eq!(doc["words"]["missing"], INBOX_TIDY_MISSING);
        assert_eq!(undo_answer(404, "").unwrap_err(), INBOX_TIDY_MISSING);
        assert_eq!(undo_answer(501, "").unwrap_err(), INBOX_TIDY_MISSING);
        // The PC's own "no such route" is a refusal, not "missing".
        assert!(undo_answer(404, r#"{"ok": false, "error": "no such route"}"#).is_err());
        assert_ne!(
            undo_answer(404, r#"{"ok": false, "error": "no such route"}"#).unwrap_err(),
            INBOX_TIDY_MISSING
        );
        assert!(read_answer(200, "{nope").is_err());
    }

    #[test]
    fn the_words_here_are_the_contracts() {
        let doc = cases();
        assert_eq!(doc["words"]["hidden"], HIDDEN);
        assert_eq!(doc["words"]["locked"], LOCKED);
        assert_eq!(doc["words"]["stale"], STALE);
        assert_eq!(doc["routes"]["status"], STATUS_PATH);
        assert_eq!(doc["routes"]["undo"], UNDO_PATH);
    }

    #[test]
    fn hidden_words_keep_only_that_a_tidy_is_open_and_for_how_long() {
        let doc = cases();
        let open = doc["cases"]["status_undo_two"]["body"].clone();
        let hidden = redact(open.clone());
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["undo"]["said"], HIDDEN);
        assert_eq!(hidden["undo"]["count"], 0);
        assert_eq!(hidden["undo"]["action"], "");
        assert_eq!(hidden["undo"]["more"], 0);
        assert_eq!(hidden["undo"]["minutes_left"], open["undo"]["minutes_left"]);
        assert!(hidden.get("last").is_none());
        let s = hidden.to_string();
        assert!(!s.contains("Archived") && !s.contains("Marked"));
        // Nothing open: nothing invented.
        let idle = redact(doc["cases"]["status_idle"]["body"].clone());
        assert!(idle["undo"].is_null());
    }
}
