//! The picture of a filled-in web form, for the "Jarvis wants to submit this
//! form" card (docs/FORM-REVIEW-DESIGN.md, 2026-09-30).
//!
//! Jarvis fills a form in a visible browser, stops before the last click and
//! takes ONE picture of the page. The card for that click
//! (`browser_form_submit`) carries the picture's id in `detail.picture`; the
//! Jarvis bar asks for the picture with [`form_review_picture`] while that
//! card is showing.
//!
//! One command, for the Jarvis bar only (`permissions/surfaces.toml`,
//! `form-review`):
//!
//! * [`form_review_picture`] - `GET /api/form-review/picture?id=<id>`. A read,
//!   never held on a stale link (seeing the picture decides nothing). While
//!   App lock has locked Jarvis it asks the PC for nothing and answers
//!   `{"ok": false, "locked": true}`: the picture shows only inside the
//!   unlocked app. A picture the PC no longer holds (404) answers
//!   `{"ok": false}`.
//!
//! The picture is the owner's own screen, shown as it is (nothing blacked out:
//! the owner needs to read the name and number), and it only ever goes to this
//! window. It is never logged here - not the id, not the picture - and nothing
//! in this file writes it anywhere.
//!
//! The answer-reading function is a plain function of (status, body), so its
//! tests run without an app or a network.

use tauri::AppHandle;

use super::READ_TIMEOUT;
use crate::commands;

pub(crate) const PICTURE_PATH: &str = "/api/form-review/picture";

/// A picture base64-encoded can be a couple of MiB; anything far beyond the
/// backend's own 1.5 MiB cap is not one the PC sent.
const MAX_JPEG_CHARS: usize = 4 * 1024 * 1024;

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read.";

/// An id the backend could have made: short, plain letters, digits, `-`, `_`.
/// Anything else is never put in a URL.
pub(crate) fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 64
        && id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

fn is_base64(text: &str) -> bool {
    !text.is_empty()
        && text
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'+' | b'/' | b'='))
}

/// The reading: the PC's `{"ok": true, "jpeg", "width", "height"}` on a 2xx
/// (checked to be what it says); `{"ok": false}` for a picture that is gone
/// (404); the PC's own sentence for any other refusal. The errors never carry
/// the body of a 2xx, and never the id.
pub(crate) fn picture_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let v = serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string())?;
        let jpeg = v.get("jpeg").and_then(|j| j.as_str()).unwrap_or("");
        if v.get("ok").and_then(|o| o.as_bool()) != Some(true)
            || jpeg.len() > MAX_JPEG_CHARS
            || !is_base64(jpeg)
        {
            return Err(UNREADABLE.to_string());
        }
        return Ok(v);
    }
    if status == 404 {
        return Ok(serde_json::json!({ "ok": false }));
    }
    // Not `backend_refusal(status, body)`: it may quote the body, and this
    // route's bodies are never worth quoting.
    Err(format!("Jarvis could not give the picture (HTTP {status})."))
}

fn locked(app: &AppHandle) -> bool {
    crate::lock::app_locked(app)
}

/// The picture for one waiting "submit this form" card. A read.
#[tauri::command]
pub async fn form_review_picture(
    app: AppHandle,
    id: String,
) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err("That is not a picture Jarvis could have made.".to_string());
    }
    if locked(&app) {
        return Ok(serde_json::json!({ "ok": false, "locked": true }));
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{PICTURE_PATH}"))
        .query(&[("id", id.as_str())])
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    let answer = picture_answer(status, &text);
    // Re-check: the lock may have closed while the picture was in flight.
    if locked(&app) {
        return Ok(serde_json::json!({ "ok": false, "locked": true }));
    }
    answer
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_plain_ids_go_in_a_url() {
        assert!(valid_id("fr_0123abcDEF-9"));
        for bad in ["", "a b", "a/b", "a?b", "a&id=b", "../x", "é", &"a".repeat(65)] {
            assert!(!valid_id(bad), "{bad:?}");
        }
    }

    #[test]
    fn a_real_answer_is_passed_on_and_a_gone_one_is_ok_false() {
        let body = r#"{"ok": true, "jpeg": "/9j/4AAQSkZJRg==", "width": 10, "height": 5}"#;
        let got = picture_answer(200, body).unwrap();
        assert_eq!(got["width"], 10);
        assert_eq!(got["jpeg"], "/9j/4AAQSkZJRg==");
        assert_eq!(
            picture_answer(404, r#"{"ok": false}"#).unwrap(),
            serde_json::json!({ "ok": false })
        );
        assert_eq!(picture_answer(404, "").unwrap()["ok"], false);
    }

    #[test]
    fn an_answer_that_is_not_a_picture_is_refused_without_quoting_it() {
        for body in [
            "{nope",
            "[]",
            r#"{"ok": false, "jpeg": "AAAA"}"#,
            r#"{"ok": true}"#,
            r#"{"ok": true, "jpeg": "<script>"}"#,
        ] {
            let e = picture_answer(200, body).unwrap_err();
            assert_eq!(e, UNREADABLE, "{body}");
        }
        let e = picture_answer(500, r#"{"error": "SECRET-BODY"}"#).unwrap_err();
        assert!(!e.contains("SECRET-BODY"));
        assert!(e.contains("500"));
    }
}
