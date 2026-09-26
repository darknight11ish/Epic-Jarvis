//! "Always keep in mind" - the facts the owner pinned, which Jarvis reads with
//! every question, word for word (the owner's decision, 2026-09-24;
//! JARVIS-API.md section 6, `/api/memory/profile`).
//!
//! Two commands, each its own power, like the rest of brain.rs:
//!
//! * [`brain_memory_profile`] - `GET /api/memory/profile`: the pinned facts,
//!   and how many of the list's characters they use. A read. While
//!   "Windows Hello for memory lists and chat history" (lock.rs) hides the
//!   Brain's private lists it comes back with its facts taken out (how many
//!   there were is kept), here in Rust, so a page script cannot read round it.
//! * [`brain_memory_pin`] - `POST /api/memory/profile {"id", "pinned"}`: pin
//!   or unpin ONE fact. No approval card - it is the owner's own tap on a fact
//!   they can see, like Forget - but held while the event stream is stale
//!   (rule 4), both ways, like every memory write in this window. There is no
//!   list form: one fact per call.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// What the page says for a PC whose backend has no such list yet. The
/// phone says the same (`MemoryProfile.MISSING`).
pub(crate) const PROFILE_MISSING: &str =
    "Your PC's Jarvis does not have the \"Always keep in mind\" list yet.";

/// A pin refused because the PC cannot pin at all (no route, or an older
/// `jarvis_memory.py`). Nothing changed.
pub(crate) const PIN_TOO_OLD: &str = "Not changed: your PC's Jarvis cannot keep facts in mind \
     yet - run apply-patches.ps1 on the PC to update it.";

/// The fact was not there any more (a 404 that says so).
pub(crate) const NO_SUCH_FACT: &str = "Jarvis had no such fact any more.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// [`brain_memory_profile`]'s reading of the answer.
///
/// * 2xx with a `facts` list - passed on as it is.
/// * 404 or 501 - `{"available": false, "why": PROFILE_MISSING}`: an older
///   backend, which the page says plainly rather than as an error.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn profile_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("facts").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": PROFILE_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_memory_pin`]'s reading of the answer.
///
/// * 2xx - passed on (`{"ok", "id", "pinned", "changed", "chars", "limit"}`).
/// * 404 that says `no_such_fact` - [`NO_SUCH_FACT`]. A 404 without it is a
///   PC with no such route at all, which is [`PIN_TOO_OLD`], as is a 501:
///   nothing was pinned, and the page must not say it was.
/// * 409 - the backend's own sentence: "That would make the list too long -
///   unpin something first", and the other two refusals.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn pin_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        let reason =
            parsed(body).and_then(|v| v.get("reason").and_then(|r| r.as_str()).map(str::to_string));
        return Err(if reason.as_deref() == Some("no_such_fact") {
            NO_SUCH_FACT.to_string()
        } else {
            PIN_TOO_OLD.to_string()
        });
    }
    if status == 501 {
        return Err(PIN_TOO_OLD.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The list with its facts taken out, for while the private lists are
/// hidden (lock.rs). How many there were, and the characters used, stay:
/// they say nothing about the owner.
pub(crate) fn redact_profile(mut list: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = list.as_object_mut() {
        if let Some(serde_json::Value::Array(items)) = obj.get_mut("facts") {
            let count = items.len();
            items.clear();
            obj.insert("hidden".into(), serde_json::json!(true));
            obj.insert("hidden_count".into(), serde_json::json!(count));
        }
    }
    list
}

/// The body of one pin or unpin: one id, one answer, nothing else.
pub(crate) fn pin_body(id: i64, pinned: bool) -> serde_json::Value {
    serde_json::json!({ "id": id, "pinned": pinned })
}

/// The pinned facts, oldest pin first, with `chars` and `limit`. A read.
#[tauri::command]
pub async fn brain_memory_profile(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/memory/profile"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = profile_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_profile(answer)
    } else {
        answer
    })
}

/// Pins (`pinned: true`) or unpins ONE fact on "Always keep in mind". Held
/// on a stale link either way: it acts on a list the window drew from a read
/// that may be stale, like Forget.
#[tauri::command]
pub async fn brain_memory_pin(
    app: AppHandle,
    id: i64,
    pinned: bool,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/memory/profile"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&pin_body(id, pinned))
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    pin_answer(status, &body)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_list_is_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"facts": [{"id": 3, "text": "Owner is vegetarian", "added": 1790000000.5}],
            "chars": 19, "limit": 1200}"#;
        let got = profile_answer(200, body).unwrap();
        assert_eq!(got["facts"][0]["id"], 3);
        assert_eq!(got["chars"], 19);
        for old in [404, 501] {
            let a = profile_answer(old, r#"{"error": "x"}"#).unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], PROFILE_MISSING);
        }
        assert!(profile_answer(200, r#"{"ok": true}"#).is_err());
        assert!(profile_answer(200, "not json").is_err());
        assert_eq!(
            profile_answer(503, r#"{"error": "memory layer not importable"}"#).unwrap_err(),
            "Memory layer not importable"
        );
    }

    #[test]
    fn a_refused_pin_says_why_and_a_missing_route_is_never_a_success() {
        let ok = pin_answer(
            200,
            r#"{"ok": true, "id": 3, "pinned": true, "changed": true}"#,
        );
        assert_eq!(ok.unwrap()["pinned"], true);
        assert_eq!(
            pin_answer(
                409,
                r#"{"ok": false, "reason": "too_long",
                    "error": "That would make the list too long - unpin something first"}"#
            )
            .unwrap_err(),
            "That would make the list too long - unpin something first"
        );
        assert_eq!(
            pin_answer(404, r#"{"ok": false, "reason": "no_such_fact"}"#).unwrap_err(),
            NO_SUCH_FACT
        );
        for old in [(404, r#"{"error": "not found"}"#), (404, ""), (501, "{}")] {
            assert_eq!(pin_answer(old.0, old.1).unwrap_err(), PIN_TOO_OLD);
        }
        assert!(pin_answer(400, r#"{"error": "need an integer id"}"#).is_err());
    }

    #[test]
    fn one_fact_one_answer() {
        assert_eq!(
            pin_body(7, true),
            serde_json::json!({ "id": 7, "pinned": true })
        );
        assert_eq!(
            pin_body(7, false),
            serde_json::json!({ "id": 7, "pinned": false })
        );
    }

    #[test]
    fn hidden_lists_keep_the_count_but_no_fact() {
        let list = serde_json::json!({
            "facts": [{"id": 1, "text": "Sees Dr Patel on Tuesdays"}, {"id": 2, "text": "x"}],
            "chars": 26, "limit": 1200
        });
        let hidden = redact_profile(list);
        assert_eq!(hidden["facts"], serde_json::json!([]));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert_eq!(hidden["limit"], 1200);
        assert!(!hidden.to_string().contains("Patel"));
    }
}
