//! Quiz me on a YouTube video (the owner's decision of 2026-09-30;
//! `docs/STUDY-FROM-TEXT-DESIGN.md` section 14; JARVIS-API.md section 112;
//! backend `jarvis_youtube.py`).
//!
//! The owner pastes a YouTube link on the Quiz page. The PC raises ONE approval
//! card for that link (a risky approval, decided in the ordinary approval
//! screens, never here) and only after a yes fetches the video's CAPTION TEXT,
//! writes questions with the local model and hands back an ordinary quiz marked
//! as outside text. Four commands, one per route:
//!
//! * [`brain_youtube_info`] - `GET /api/youtube`: whether the PC has the
//!   feature, and the newest request. A read; never starts anything.
//! * [`brain_youtube_start`] - `POST /api/youtube/quiz {"url", "count"}`. Held
//!   on a stale link (rule 4). The app checks nothing about the link beyond
//!   "not empty": the PC's own refusal is handed on as it came.
//! * [`brain_youtube_get`] - `GET /api/youtube/<id>`: polled about every two
//!   seconds while a request is open. A read; never held.
//! * [`brain_youtube_cancel`] - `POST /api/youtube/<id>/cancel {}`. Never held
//!   on a stale link: it only ever makes things safer.
//!
//! THIS APP KEEPS NOTHING: the link goes out once, in a request body. It is
//! never in a URL, a log, a saved draft, a notification or an error sentence
//! (a transport error names the PC's address, never the body). While "Windows
//! Hello for memory lists and chat history" (lock.rs) hides the private lists,
//! the request's `link` and the quiz's words are taken out of every answer
//! here, in Rust, so a page script cannot read round it. The state message and
//! the counts stay.
//!
//! The backend's own refusals (`{"ok": false, "error": <code>, "message":
//! ...}`) are handed on unchanged; this file never rewords them and never
//! invents a success. The answer-reading functions are plain functions of
//! (status, body) so their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::quiz::{redact_quiz, valid_id};
use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no YouTube quizzes yet. The phone says the same words.
pub(crate) const YOUTUBE_MISSING: &str =
    "Your PC's Jarvis does not have YouTube quizzes yet - run apply-patches.ps1 on the PC.";

/// The backend answered, but not in a shape this app can read.
const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The PC's own words for a request it no longer has (JARVIS-API 112.2).
pub(crate) const NO_SUCH_REQUEST: &str =
    "That YouTube request is not open any more. Start a new one.";

/// Nothing to send.
const NO_LINK: &str = "Paste a video link first.";

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A body the backend itself classified as a refusal: `{"ok": false,
/// "error": "<code>", ...}`. `None` for any other shape, which is how a
/// backend with no YouTube quizzes at all (a bare 404) is told apart from the
/// feature's own `not_found`.
fn backend_refusal_body(body: &str) -> Option<serde_json::Value> {
    let v = parsed(body)?;
    if v.get("ok").and_then(|o| o.as_bool()) != Some(false) {
        return None;
    }
    v.get("error")
        .and_then(|e| e.as_str())
        .filter(|s| !s.is_empty())?;
    Some(v)
}

/// The reading of start, get and cancel. A success carries a `request`
/// object; a refusal the backend classified comes back as `Ok` with `ok:
/// false` intact (the page shows its `message` word for word). A missing route
/// is [`YOUTUBE_MISSING`]. Anything else is a plain line with the status code,
/// never the body.
pub(crate) fn youtube_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) == Some(true))
            .filter(|v| v.get("request").is_some_and(|r| r.is_object()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if let Some(refusal) = backend_refusal_body(body) {
        return Ok(refusal);
    }
    if status == 404 || status == 501 {
        return Err(YOUTUBE_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The reading of `GET /api/youtube`. A PC without the feature answers 404 (or
/// 501, or 503): that is `{"ok": true, "available": false}`, not an error.
pub(crate) fn info_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) == Some(true))
            .filter(|v| v.get("available").is_some_and(|a| a.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if matches!(status, 404 | 501 | 503) {
        return Ok(serde_json::json!({ "ok": true, "available": false }));
    }
    Err(commands::backend_refusal(status, body))
}

/// One request with its private words taken out, for while the private lists
/// are hidden: the link, and the quiz's own words. The state, the PC's message,
/// the counts and the truncation flag say nothing about the owner's video.
pub(crate) fn redact_request(request: &mut serde_json::Value) {
    let Some(obj) = request.as_object_mut() else {
        return;
    };
    if obj.get("link").is_some_and(|l| l.is_string()) {
        obj.insert("link".into(), serde_json::Value::Null);
    }
    if let Some(q) = obj.get_mut("quiz") {
        if q.is_object() {
            redact_quiz(q);
        }
    }
    obj.insert("hidden".into(), serde_json::json!(true));
}

/// Applies [`redact_request`] to an answer that carries one (and to `latest`
/// on the info answer).
pub(crate) fn redact_answer(mut answer: serde_json::Value) -> serde_json::Value {
    if answer.get("ok").and_then(|o| o.as_bool()) != Some(true) {
        return answer;
    }
    if let Some(obj) = answer.as_object_mut() {
        for key in ["request", "latest"] {
            if let Some(r) = obj.get_mut(key) {
                redact_request(r);
            }
        }
        // The start answer repeats the request's message; it is the PC's own
        // state sentence and stays.
        obj.insert("hidden".into(), serde_json::json!(true));
    }
    answer
}

fn hide_if_private(app: &AppHandle, answer: serde_json::Value) -> serde_json::Value {
    if crate::lock::private_hidden(app) {
        redact_answer(answer)
    } else {
        answer
    }
}

/// The body of `POST /api/youtube/quiz`: only the link and, if chosen, the
/// question count. Nothing else is ever sent (no title, no language).
pub(crate) fn start_body(url: &str, count: Option<i64>) -> Result<serde_json::Value, String> {
    let url = url.trim();
    if url.is_empty() {
        return Err(NO_LINK.to_string());
    }
    let mut body = serde_json::json!({ "url": url });
    if let Some(count) = count {
        body["count"] = serde_json::json!(count);
    }
    Ok(body)
}

/// Asks the PC whether it has YouTube quizzes, and for the newest request (a
/// waiting one is picked up again after the app restarted). A read.
#[tauri::command]
pub async fn brain_youtube_info(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/youtube"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = info_answer(status, &body)?;
    Ok(hide_if_private(&app, answer))
}

/// Sends the pasted link to the PC, which raises ONE approval card. The link
/// is in the body only. Held on a stale link.
#[tauri::command]
pub async fn brain_youtube_start(
    app: AppHandle,
    url: String,
    count: Option<i64>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = start_body(&url, count)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/youtube/quiz"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    let answer = youtube_answer(status, &text)?;
    Ok(hide_if_private(&app, answer))
}

/// One open request, read again. A read; never held on a stale link.
#[tauri::command]
pub async fn brain_youtube_get(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err(NO_SUCH_REQUEST.to_string());
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/youtube/{id}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = youtube_answer(status, &body)?;
    Ok(hide_if_private(&app, answer))
}

/// Withdraws the card while it is still waiting. NOT held on a stale link.
#[tauri::command]
pub async fn brain_youtube_cancel(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err(NO_SUCH_REQUEST.to_string());
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/youtube/{id}/cancel"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&serde_json::json!({}))
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = youtube_answer(status, &body)?;
    Ok(hide_if_private(&app, answer))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> serde_json::Value {
        serde_json::from_str(include_str!("../../../tests/fixtures/youtube-cases.json")).unwrap()
    }

    #[test]
    fn the_start_body_is_the_link_and_the_count_and_nothing_else() {
        let b = start_body("  https://youtu.be/dQw4w9WgXcQ  ", Some(4)).unwrap();
        assert_eq!(
            b,
            serde_json::json!({"url": "https://youtu.be/dQw4w9WgXcQ", "count": 4})
        );
        let b = start_body("https://youtu.be/x", None).unwrap();
        assert_eq!(b, serde_json::json!({"url": "https://youtu.be/x"}));
        assert_eq!(start_body("   ", Some(3)).unwrap_err(), NO_LINK);
        assert_eq!(start_body("", None).unwrap_err(), NO_LINK);
    }

    #[test]
    fn every_sample_of_the_contract_is_read_as_the_fixture_says() {
        let f = fixture();
        for (name, s) in f["samples"].as_object().unwrap() {
            let status = s["status"].as_u64().unwrap() as u16;
            let body = s["body"].to_string();
            if name == "info" || name == "info_no_latest" {
                let a = info_answer(status, &body).unwrap();
                assert_eq!(a["available"], s["expect"]["available"], "{name}");
                continue;
            }
            let a = youtube_answer(status, &body);
            let expect = &s["expect"];
            if expect["unreadable"] == true {
                // Handed on: the page decides a ready request with no quiz is over.
                assert!(a.is_ok(), "{name}");
                continue;
            }
            let a = a.unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(a["ok"], expect["ok"], "{name}");
            if expect["ok"] == false {
                assert_eq!(a["message"], expect["shown"], "{name}");
                assert_eq!(a["error"], expect["code"], "{name}");
            }
        }
    }

    #[test]
    fn a_refusal_keeps_the_pcs_words_and_a_missing_feature_says_so() {
        let f = fixture();
        for (code, r) in f["refusals"].as_object().unwrap() {
            let body = serde_json::json!({"ok": false, "error": code, "message": r["message"]})
                .to_string();
            let status = r["status"].as_u64().unwrap() as u16;
            let a = youtube_answer(status, &body).unwrap();
            assert_eq!(a["ok"], false, "{code}");
            assert_eq!(a["message"], r["message"], "{code}");
        }
        for old in [404, 501] {
            for body in ["", "Not Found", "{}"] {
                assert_eq!(youtube_answer(old, body).unwrap_err(), YOUTUBE_MISSING);
            }
        }
        assert_eq!(YOUTUBE_MISSING, fixture()["words"]["missing"]);
        // An unexplained failure is a plain line with the code, never the body.
        let e = youtube_answer(500, "SECRET https://youtu.be/abc").unwrap_err();
        assert!(e.contains("500") && !e.contains("youtu"), "{e}");
    }

    #[test]
    fn a_bad_shape_is_never_a_success() {
        assert!(youtube_answer(200, r#"{"ok": true}"#).is_err());
        assert!(youtube_answer(200, r#"{"ok": true, "request": null}"#).is_err());
        assert!(youtube_answer(200, "not json").is_err());
        assert!(youtube_answer(200, r#"{"ok": false, "request": {}}"#).is_err());
        assert!(info_answer(200, r#"{"ok": true}"#).is_err());
        assert!(info_answer(200, r#"{"ok": true, "available": "yes"}"#).is_err());
    }

    #[test]
    fn a_pc_without_the_feature_answers_info_as_not_available() {
        for old in [404, 501, 503] {
            let a = info_answer(old, "").unwrap();
            assert_eq!(a, serde_json::json!({"ok": true, "available": false}));
        }
        assert!(info_answer(500, "").is_err());
    }

    #[test]
    fn a_request_id_is_checked_like_a_quiz_id() {
        assert!(valid_id("0123456789ab"));
        assert!(!valid_id("../x"));
        assert!(!valid_id("a/b"));
    }

    #[test]
    fn hidden_lists_lose_the_link_and_the_quiz_words_but_not_the_state() {
        let f = fixture();
        let ready =
            youtube_answer(200, &f["samples"]["ready_truncated"]["body"].to_string()).unwrap();
        let hidden = redact_answer(ready);
        let s = hidden.to_string();
        for word in [
            "youtube.com",
            "dQw4w9WgXcQ",
            "mainly about",
            "Why does the speaker",
        ] {
            assert!(!s.contains(word), "{word} leaked: {s}");
        }
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["request"]["state"], "ready");
        assert_eq!(hidden["request"]["truncated"], true);
        assert_eq!(hidden["request"]["minutes"], 42);
        assert_eq!(
            hidden["request"]["message"],
            f["samples"]["ready_truncated"]["expect"]["shown"]
        );
        assert_eq!(hidden["request"]["quiz"]["questions"][1]["n"], 2);
        assert_eq!(hidden["request"]["quiz"]["source"], "youtube");
        // The waiting request keeps its sentence; only the link goes.
        let waiting = youtube_answer(202, &f["samples"]["started"]["body"].to_string()).unwrap();
        let hidden = redact_answer(waiting);
        assert!(hidden["request"]["link"].is_null());
        assert_eq!(
            hidden["request"]["message"],
            "Waiting for your yes on the approval card."
        );
        // The newest request on the info answer is cleaned the same way.
        let info = info_answer(200, &f["samples"]["info"]["body"].to_string()).unwrap();
        let hidden = redact_answer(info);
        assert!(hidden["latest"]["link"].is_null());
        assert_eq!(hidden["latest"]["state"], "waiting");
        // A refusal has nothing to hide and is left as it is.
        let refusal = serde_json::json!({"ok": false, "error": "not_youtube", "message": "m"});
        assert_eq!(redact_answer(refusal.clone()), refusal);
    }

    #[test]
    fn nothing_here_logs() {
        let src = include_str!("youtube.rs")
            .split("#[cfg(test)]")
            .next()
            .unwrap();
        for bad in ["println!", "eprintln!", "tracing::", "log::", "dbg!"] {
            assert!(!src.contains(bad), "{bad}");
        }
    }
}
