//! "Grade this better" cloud quiz grading (the owner's decision of 2026-09-30;
//! `docs/STUDY-FROM-TEXT-DESIGN.md` section 15; JARVIS-API.md section 113;
//! backend `jarvis_quiz_cloud.py`).
//!
//! One button on the existing quiz screen: sends ONE text quiz to a cloud AI
//! service to be marked more carefully than the local model can. The PC raises
//! ONE approval card (gate action `quiz_cloud_grade`, tier `ask`, a risky approval,
//! decided in the ordinary approval screens) listing exactly what would leave
//! this PC. Only after a yes does the request go to the cloud service.
//!
//! Four commands, one per route:
//! * [`brain_quiz_cloud_info`] - `GET /api/quiz-cloud`: whether the PC has the
//!   feature, whether a service is ready, and the newest request.
//! * [`brain_quiz_cloud_start`] - `POST /api/quiz-cloud/grade {"quiz_id"}`. Held
//!   on a stale link (rule 4).
//! * [`brain_quiz_cloud_get`] - `GET /api/quiz-cloud/<id>`: polled while waiting.
//! * [`brain_quiz_cloud_cancel`] - `POST /api/quiz-cloud/<id>/cancel {}`. Never
//!   held on a stale link.
//!
//! While "Windows Hello for memory lists and chat history" hides private lists,
//! the quiz's words and comments are taken out of every answer here in Rust.

use tauri::AppHandle;

use super::quiz::{redact_mark, redact_quiz, valid_id};
use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no cloud quiz grading yet.
pub(crate) const QUIZ_CLOUD_MISSING: &str =
    "Your PC's Jarvis does not have cloud quiz grading yet - run apply-patches.ps1 on the PC.";

/// The backend answered, but not in a shape this app can read.
const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The PC's own words for a request it no longer has.
pub(crate) const NO_SUCH_REQUEST: &str =
    "That grading request is not open any more. Start a new one.";

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

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

/// The reading of start, get and cancel.
pub(crate) fn quiz_cloud_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
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
        return Err(QUIZ_CLOUD_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The reading of `GET /api/quiz-cloud`.
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

/// One request with private words taken out.
pub(crate) fn redact_request(request: &mut serde_json::Value) {
    let Some(obj) = request.as_object_mut() else {
        return;
    };
    if let Some(q) = obj.get_mut("quiz") {
        if q.is_object() {
            redact_quiz(q);
        }
    }
    if let Some(serde_json::Value::Array(marks)) = obj.get_mut("marks") {
        for m in marks.iter_mut() {
            if m.is_object() {
                redact_mark(m);
            }
        }
    }
    obj.insert("hidden".into(), serde_json::json!(true));
}

/// Applies [`redact_request`] to an answer carrying one.
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

/// Checks the PC's cloud quiz grading availability and status.
#[tauri::command]
pub async fn brain_quiz_cloud_info(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/quiz-cloud"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = info_answer(status, &body)?;
    Ok(hide_if_private(&app, answer))
}

/// Requests cloud grading for an open quiz. Held on a stale link.
#[tauri::command]
pub async fn brain_quiz_cloud_start(
    app: AppHandle,
    quiz_id: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let base = commands::jarvis_base(&app);
    let body = serde_json::json!({ "quiz_id": quiz_id.trim() });
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/quiz-cloud/grade"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    let answer = quiz_cloud_answer(status, &text)?;
    Ok(hide_if_private(&app, answer))
}

/// Reads one grading request. A read; never held on a stale link.
#[tauri::command]
pub async fn brain_quiz_cloud_get(
    app: AppHandle,
    id: String,
) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err(NO_SUCH_REQUEST.to_string());
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/quiz-cloud/{id}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = quiz_cloud_answer(status, &body)?;
    Ok(hide_if_private(&app, answer))
}

/// Withdraws a waiting grading request card. Not held on a stale link.
#[tauri::command]
pub async fn brain_quiz_cloud_cancel(
    app: AppHandle,
    id: String,
) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err(NO_SUCH_REQUEST.to_string());
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/quiz-cloud/{id}/cancel"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&serde_json::json!({}))
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = quiz_cloud_answer(status, &body)?;
    Ok(hide_if_private(&app, answer))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> serde_json::Value {
        serde_json::from_str(include_str!("../../../tests/fixtures/quiz-cloud-cases.json")).unwrap()
    }

    #[test]
    fn every_sample_of_the_contract_is_read_as_the_fixture_says() {
        let f = fixture();
        for (name, s) in f["samples"].as_object().unwrap() {
            let status = s["status"].as_u64().unwrap() as u16;
            let body = s["body"].to_string();
            if name.starts_with("info_") {
                let a = info_answer(status, &body).unwrap();
                assert_eq!(a["available"], s["expect"]["available"], "{name}");
                assert_eq!(a["ready"], s["expect"]["ready"], "{name}");
                continue;
            }
            let a = quiz_cloud_answer(status, &body);
            let expect = &s["expect"];
            let a = a.unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(a["ok"], expect["ok"], "{name}");
            if expect["ok"] == false {
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
            let a = quiz_cloud_answer(status, &body).unwrap();
            assert_eq!(a["ok"], false, "{code}");
            assert_eq!(a["message"], r["message"], "{code}");
        }
        for old in [404, 501] {
            for body in ["", "Not Found", "{}"] {
                assert_eq!(quiz_cloud_answer(old, body).unwrap_err(), QUIZ_CLOUD_MISSING);
            }
        }
    }
}
