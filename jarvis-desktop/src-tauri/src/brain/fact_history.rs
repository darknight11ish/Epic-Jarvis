//! "History of this fact" - every earlier (and later) version of one fact,
//! for the Brain's Memory tab (the owner's choice of 2026-09-28;
//! JARVIS-API.md section 71, `GET /api/memory/fact-history?id=`).
//!
//! Today a replaced fact only said "replaced by #N". The PC now answers with
//! the whole chain of wordings, oldest first, and the page marks the words
//! that changed from one version to the next (fact-history.js).
//!
//! It is memory, so it is hidden like every memory list: while "Windows
//! Hello for memory lists and chat history" (lock.rs) holds the lists back,
//! the answer comes back with every version taken out (how many there were
//! is kept), here in Rust, so a page script cannot read round it. And an
//! ERASED version never carries words from the PC in the first place
//! (`jarvis_memory.fact_history_view`); [`fact_history_answer`] checks that
//! again, so a PC that ever sent the "[erased]" marker or old words beside
//! `erased_at` would still show none.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network. Desktop only: the phone
//! keeps no list of every fact (ARCHITECTURE.md section 8).

use tauri::AppHandle;

use super::READ_TIMEOUT;
use crate::commands;

/// What the page says for a PC whose backend cannot list a fact's versions
/// yet (no `brain-reads.patch`).
pub(crate) const FACT_HISTORY_MISSING: &str =
    "Your PC's Jarvis cannot show a fact's history yet - run apply-patches.ps1 on the PC to \
     update it.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The query for one fact, or why not: one whole number above 0.
pub(crate) fn fact_history_query(id: i64) -> Result<String, String> {
    if id <= 0 {
        return Err("That is not a fact id.".to_string());
    }
    Ok(format!("id={id}"))
}

/// [`brain_fact_history`]'s reading of the answer.
///
/// * 2xx with a `versions` list - passed on, with the words of any version
///   that has `erased_at` blanked again (belt and braces, above).
/// * 404 with the PC's own "no such fact" - an error in its words.
/// * 404 without it, or 501 - `{"available": false, "why":
///   FACT_HISTORY_MISSING}`: an older backend, said plainly.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn fact_history_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let mut v = serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("versions").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string())?;
        if let Some(serde_json::Value::Array(items)) = v.get_mut("versions") {
            for item in items.iter_mut() {
                let erased = item.get("erased_at").is_some_and(|e| !e.is_null());
                if erased {
                    if let Some(obj) = item.as_object_mut() {
                        obj.insert("text".into(), serde_json::json!(""));
                    }
                }
            }
        }
        return Ok(v);
    }
    if status == 404 && body.contains("no such fact") {
        return Err("That fact is not in Jarvis's memory any more. Refresh the list.".to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": FACT_HISTORY_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// The answer with every version taken out, for while the memory lists are
/// hidden (lock.rs). How many there were stays: it says nothing about the
/// owner.
pub(crate) fn redact_fact_history(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = answer.as_object_mut() {
        if let Some(serde_json::Value::Array(items)) = obj.get_mut("versions") {
            let count = items.len();
            items.clear();
            obj.insert("hidden".into(), serde_json::json!(true));
            obj.insert("hidden_count".into(), serde_json::json!(count));
        }
    }
    answer
}

/// Every version of one fact, oldest first. A read.
#[tauri::command]
pub async fn brain_fact_history(app: AppHandle, id: i64) -> Result<serde_json::Value, String> {
    let query = fact_history_query(id)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/memory/fact-history?{query}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = fact_history_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_fact_history(answer)
    } else {
        answer
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_one_real_id_is_sent() {
        assert_eq!(fact_history_query(12).unwrap(), "id=12");
        assert!(fact_history_query(0).is_err());
        assert!(fact_history_query(-4).is_err());
    }

    #[test]
    fn the_versions_or_why_not() {
        let body = r#"{"id": 3, "versions": [
            {"id": 2, "text": "Owner lives in York", "erased_at": null, "this": false},
            {"id": 3, "text": "Owner lives in Leeds", "erased_at": null, "this": true}],
            "count": 2, "more": false}"#;
        let got = fact_history_answer(200, body).unwrap();
        assert_eq!(got["versions"][1]["text"], "Owner lives in Leeds");
        assert!(fact_history_answer(200, r#"{"id": 3}"#).is_err());
        let gone = fact_history_answer(
            404,
            r#"{"error": "no such fact - it may never have been saved"}"#,
        )
        .unwrap_err();
        assert!(gone.contains("not in Jarvis's memory"), "{gone}");
        for status in [404, 501] {
            let old = fact_history_answer(status, r#"{"error": "no such route"}"#).unwrap();
            assert_eq!(old["available"], false);
            assert_eq!(old["why"], FACT_HISTORY_MISSING);
        }
    }

    #[test]
    fn an_erased_version_never_shows_words_even_if_a_pc_sent_some() {
        let body = r#"{"id": 3, "versions": [
            {"id": 2, "text": "Owner's PIN is 4821", "erased_at": 1790000000.0},
            {"id": 3, "text": "[erased]", "erased_at": 1790000100.0},
            {"id": 4, "text": "Owner uses the bank app", "erased_at": null}]}"#;
        let got = fact_history_answer(200, body).unwrap();
        let text = got.to_string();
        assert!(!text.contains("4821"), "{text}");
        assert!(!text.contains("[erased]"), "{text}");
        assert_eq!(got["versions"][2]["text"], "Owner uses the bank app");
    }

    #[test]
    fn hidden_keeps_the_count_and_no_words() {
        let answer = serde_json::json!({"id": 3, "versions": [
            {"id": 2, "text": "Owner lives in York"}, {"id": 3, "text": "Owner lives in Leeds"}]});
        let hidden = redact_fact_history(answer);
        assert_eq!(hidden["versions"], serde_json::json!([]));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert!(!hidden.to_string().contains("Leeds"));
    }
}
