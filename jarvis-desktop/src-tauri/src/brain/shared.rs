//! "Between us" - facts the owner tagged as a shared joke or nickname (the
//! owner's decision, 2026-09-27; JARVIS-API.md section 44, `/api/memory/shared`).
//!
//! Two commands, each its own power, like `profile.rs`:
//!
//! * [`brain_memory_shared`] - `GET /api/memory/shared`: the tagged facts,
//!   newest first. A read. While "Windows Hello for memory lists and chat
//!   history" (lock.rs) hides the Brain's private lists it comes back with
//!   its facts taken out (how many there were is kept), here in Rust, so a
//!   page script cannot read round it.
//! * [`brain_memory_share`] - `POST /api/memory/shared {"id", "shared"}`: tag
//!   or untag ONE fact. No approval card - the owner's own tap on a fact
//!   they can see, like Pin - but held while the event stream is stale
//!   (rule 4), both ways, like every memory write in this window. There is
//!   no list form: one fact per call.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// What the page says for a PC whose backend has no such list yet. The
/// phone says the same (`MemoryShared.MISSING`).
pub(crate) const SHARED_MISSING: &str =
    "Your PC's Jarvis does not have the \"Between us\" list yet.";

/// A tag/untag refused because the PC cannot do it at all (no route, or an
/// older `jarvis_memory.py`). Nothing changed.
pub(crate) const SHARED_TOO_OLD: &str = "Not changed: your PC's Jarvis cannot tag \"Between us\" \
     facts yet - run apply-patches.ps1 on the PC to update it.";

/// The fact was not there any more (a 404 that says so).
pub(crate) const NO_SUCH_FACT: &str = "Jarvis had no such fact any more.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// [`brain_memory_shared`]'s reading of the answer.
///
/// * 2xx with a `facts` list - passed on as it is.
/// * 404 or 501 - `{"available": false, "why": SHARED_MISSING}`: an older
///   backend, which the page says plainly rather than as an error.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn shared_list_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("facts").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": SHARED_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_memory_share`]'s reading of the answer.
///
/// * 2xx - passed on (`{"ok", "id", "shared", "changed"}`).
/// * 404 that says `no_such_fact` - [`NO_SUCH_FACT`]. A 404 without it is a
///   PC with no such route at all, which is [`SHARED_TOO_OLD`], as is a
///   501: nothing was tagged, and the page must not say it was.
/// * 409 - the backend's own sentence ("not_current").
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn share_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        let reason =
            parsed(body).and_then(|v| v.get("reason").and_then(|r| r.as_str()).map(str::to_string));
        return Err(if reason.as_deref() == Some("no_such_fact") {
            NO_SUCH_FACT.to_string()
        } else {
            SHARED_TOO_OLD.to_string()
        });
    }
    if status == 501 {
        return Err(SHARED_TOO_OLD.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The list with its facts taken out, for while the private lists are
/// hidden (lock.rs). How many there were stays: it says nothing about the
/// owner.
pub(crate) fn redact_shared(mut list: serde_json::Value) -> serde_json::Value {
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

/// The body of one tag or untag: one id, one answer, nothing else.
pub(crate) fn share_body(id: i64, shared: bool) -> serde_json::Value {
    serde_json::json!({ "id": id, "shared": shared })
}

/// The tagged facts, newest first. A read.
#[tauri::command]
pub async fn brain_memory_shared(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/memory/shared"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = shared_list_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_shared(answer)
    } else {
        answer
    })
}

/// Tags (`shared: true`) or untags ONE fact "Between us". Held on a stale
/// link either way: it acts on a list the window drew from a read that may
/// be stale, like Forget.
#[tauri::command]
pub async fn brain_memory_share(
    app: AppHandle,
    id: i64,
    shared: bool,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/memory/shared"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&share_body(id, shared))
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    share_answer(status, &body)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_list_is_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"facts": [{"id": 3, "text": "We call the printer the beast"}]}"#;
        let got = shared_list_answer(200, body).unwrap();
        assert_eq!(got["facts"][0]["id"], 3);
        for old in [404, 501] {
            let a = shared_list_answer(old, r#"{"error": "x"}"#).unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], SHARED_MISSING);
        }
        assert!(shared_list_answer(200, r#"{"ok": true}"#).is_err());
        assert!(shared_list_answer(200, "not json").is_err());
        assert_eq!(
            shared_list_answer(503, r#"{"error": "memory layer not importable"}"#).unwrap_err(),
            "Memory layer not importable"
        );
    }

    #[test]
    fn a_refused_share_says_why_and_a_missing_route_is_never_a_success() {
        let ok = share_answer(
            200,
            r#"{"ok": true, "id": 3, "shared": true, "changed": true}"#,
        );
        assert_eq!(ok.unwrap()["shared"], true);
        assert_eq!(
            share_answer(
                409,
                r#"{"ok": false, "reason": "not_current",
                    "error": "That fact is no longer in use, so it cannot be a shared joke"}"#
            )
            .unwrap_err(),
            "That fact is no longer in use, so it cannot be a shared joke"
        );
        assert_eq!(
            share_answer(404, r#"{"ok": false, "reason": "no_such_fact"}"#).unwrap_err(),
            NO_SUCH_FACT
        );
        for old in [(404, r#"{"error": "not found"}"#), (404, ""), (501, "{}")] {
            assert_eq!(share_answer(old.0, old.1).unwrap_err(), SHARED_TOO_OLD);
        }
        assert!(share_answer(400, r#"{"error": "need an integer id"}"#).is_err());
    }

    #[test]
    fn one_fact_one_answer() {
        assert_eq!(
            share_body(7, true),
            serde_json::json!({ "id": 7, "shared": true })
        );
        assert_eq!(
            share_body(7, false),
            serde_json::json!({ "id": 7, "shared": false })
        );
    }

    #[test]
    fn hidden_lists_keep_the_count_but_no_fact() {
        let list = serde_json::json!({
            "facts": [{"id": 1, "text": "We call the router the goblin"}, {"id": 2, "text": "x"}]
        });
        let hidden = redact_shared(list);
        assert_eq!(hidden["facts"], serde_json::json!([]));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert!(!hidden.to_string().contains("goblin"));
    }
}
