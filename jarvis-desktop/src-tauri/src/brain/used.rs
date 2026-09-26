//! "Used in this answer" and "Jarvis remembered N things" - the words of a
//! few facts, fetched by id (the owner's decision, 2026-09-25; JARVIS-API.md
//! section 6, `/api/memory/used`).
//!
//! The chat reply's `X-Jarvis-Route` and the `memory_saved` event carry fact
//! ids only, never a fact's words. When the owner opens "Used 2 memories"
//! under an answer (the quickbar) or "Jarvis remembered 2 things" (the
//! Brain), [`memory_used`] asks the PC for those facts' words:
//! `GET /api/memory/used?ids=12,15`. A read, one small list the owner is
//! looking at.
//!
//! While "Windows Hello for memory lists and chat history" (lock.rs) hides
//! the memory lists, the answer comes back with every fact's words taken out
//! (how many there were is kept), here in Rust, so a page script cannot read
//! round it - the same rule as every other memory list.
//!
//! Forget and "Erase the words" beside each fact are the Brain's own
//! one-fact commands (`brain_memory_forget`, `brain_memory_erase`): held on
//! a stale link, one id per call, asked about first by the page.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::READ_TIMEOUT;
use crate::commands;

/// The most ids one read asks for - the PC's own limit
/// (`jarvis_memory.USED_MAX`).
pub(crate) const USED_MAX: usize = 100;

/// What the page says for a PC whose backend cannot list the facts yet.
/// The phone says the same (`MemoryUsed.MISSING`).
pub(crate) const USED_MISSING: &str =
    "Your PC's Jarvis cannot show which facts these were yet - run apply-patches.ps1 on the PC \
     to update it.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The query string for these ids - `ids=12,15` - or an error when there
/// are none, too many, or one that is not a whole number above 0. Nothing is
/// sent for a list the PC would refuse.
pub(crate) fn used_query(ids: &[i64]) -> Result<String, String> {
    if ids.is_empty() {
        return Err("No facts to show.".to_string());
    }
    if ids.len() > USED_MAX {
        return Err(format!("At most {USED_MAX} facts at a time."));
    }
    if ids.iter().any(|id| *id <= 0) {
        return Err("That is not a fact id.".to_string());
    }
    let list: Vec<String> = ids.iter().map(|id| id.to_string()).collect();
    Ok(format!("ids={}", list.join(",")))
}

/// [`memory_used`]'s reading of the answer.
///
/// * 2xx with a `facts` list - passed on as it is.
/// * 404 or 501 - `{"available": false, "why": USED_MISSING}`: an older
///   backend, which the page says plainly rather than as an error.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn used_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("facts").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": USED_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// The answer with every fact's words taken out, for while the memory lists
/// are hidden (lock.rs). How many there were stays: it says nothing about
/// the owner.
pub(crate) fn redact_used(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = answer.as_object_mut() {
        if let Some(serde_json::Value::Array(items)) = obj.get_mut("facts") {
            let count = items.len();
            items.clear();
            obj.insert("hidden".into(), serde_json::json!(true));
            obj.insert("hidden_count".into(), serde_json::json!(count));
        }
    }
    answer
}

/// The words of these facts (at most [`USED_MAX`]), in the order asked, with
/// whether each is still in use, pinned or erased. A read.
#[tauri::command]
pub async fn memory_used(app: AppHandle, ids: Vec<i64>) -> Result<serde_json::Value, String> {
    let query = used_query(&ids)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/memory/used?{query}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = used_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_used(answer)
    } else {
        answer
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_list_the_pc_would_take_is_sent() {
        assert_eq!(used_query(&[12, 15]).unwrap(), "ids=12,15");
        assert!(used_query(&[]).is_err());
        assert!(used_query(&[3, 0]).is_err());
        assert!(used_query(&[-1]).is_err());
        let many: Vec<i64> = (1..=101).collect();
        assert!(used_query(&many).is_err());
        let enough: Vec<i64> = (1..=100).collect();
        assert!(used_query(&enough).is_ok());
    }

    #[test]
    fn the_facts_are_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"facts": [{"id": 3, "text": "Owner is vegetarian", "current": true,
            "pinned": true, "erased_at": null}], "missing": [9]}"#;
        let got = used_answer(200, body).unwrap();
        assert_eq!(got["facts"][0]["id"], 3);
        assert_eq!(got["missing"][0], 9);
        for old in [404, 501] {
            let a = used_answer(old, r#"{"error": "x"}"#).unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], USED_MISSING);
        }
        assert!(used_answer(200, r#"{"ok": true}"#).is_err());
        assert!(used_answer(200, "not json").is_err());
        assert!(used_answer(401, r#"{"error": "bad or missing X-Jarvis-Token"}"#).is_err());
    }

    #[test]
    fn hidden_lists_keep_the_count_but_no_fact() {
        let answer = serde_json::json!({
            "facts": [{"id": 1, "text": "Sees Dr Patel on Tuesdays"}, {"id": 2, "text": "x"}],
            "missing": []
        });
        let hidden = redact_used(answer);
        assert_eq!(hidden["facts"], serde_json::json!([]));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert!(!hidden.to_string().contains("Patel"));
    }
}
