//! "Where this came from", and the quote check - feasibility I42/I132
//! (`docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md` detail 1;
//! `docs/JARVIS-API.md` section 55).
//!
//! Only saved MEMORY facts were ever listed under an answer ("Used in this
//! answer", [`super::used`]). A note, a wiki page, a web result or a file
//! the model read was not listed anywhere at all. When the owner opens
//! "Where this came from" under an answer, [`chat_sources`] asks the PC for
//! that answer's own reading-tool receipts, by the same `turn_id`
//! "Used in this answer" and the right/wrong mark already use:
//! `GET /api/chat/sources?turn_id=<id>`. A read - this fetches nothing new,
//! it only reads back what a tool already fetched during that turn.
//!
//! While "Windows Hello for memory lists and chat history" (lock.rs) hides
//! the memory lists, the answer comes back with every source's own
//! reference (a note's title, a web link, a file's path) taken out - how
//! many there were stays - here in Rust, so a page script cannot read round
//! it. The same rule as [`super::used::redact_used`], because note and file
//! titles are just as private as a saved fact's words.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::READ_TIMEOUT;
use crate::commands;

/// What the page says for a PC whose backend cannot show this yet.
pub(crate) const SOURCES_MISSING: &str =
    "Your PC's Jarvis cannot show where this answer came from yet - run apply-patches.ps1 on the \
     PC to update it.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The query string for one turn - `turn_id=<id>` - or an error when the id
/// is not the shape the PC would ever hand out (the same 32-character
/// lowercase hex id every `turn_id` is - [`commands::valid_turn_id`], also
/// used for the right/wrong mark). Nothing is sent for one it would refuse
/// outright.
pub(crate) fn sources_query(turn_id: &str) -> Result<String, String> {
    if !commands::valid_turn_id(turn_id) {
        return Err("That is not an answer id.".to_string());
    }
    Ok(format!("turn_id={turn_id}"))
}

/// [`chat_sources`]'s reading of the answer.
///
/// * 2xx with a `sources` list - passed on as it is.
/// * 404 or 501 - `{"available": false, "why": SOURCES_MISSING}`: an older
///   backend, said plainly rather than as an error.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn sources_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("sources").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": SOURCES_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// The answer with every source's own reference (a note's title, a wiki
/// page's path, a web link, a file's path) taken out, for while the memory
/// lists are hidden (lock.rs). How many there were stays; the quoted
/// phrases jarvis flagged as unread ARE kept - they are jarvis's own
/// answer's words, already on screen, not a saved fact or a note title.
pub(crate) fn redact_sources(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = answer.as_object_mut() {
        if let Some(serde_json::Value::Array(items)) = obj.get_mut("sources") {
            let count = items.len();
            items.clear();
            obj.insert("hidden".into(), serde_json::json!(true));
            obj.insert("hidden_count".into(), serde_json::json!(count));
        }
    }
    answer
}

/// This answer's own reading-tool receipts and its quote check. A read.
#[tauri::command]
pub async fn chat_sources(app: AppHandle, turn_id: String) -> Result<serde_json::Value, String> {
    let query = sources_query(&turn_id)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/chat/sources?{query}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = sources_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_sources(answer)
    } else {
        answer
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_real_turn_id_is_sent() {
        let good = "0123456789abcdef0123456789abcdef";
        assert_eq!(sources_query(good).unwrap(), format!("turn_id={good}"));
        assert!(sources_query("not-hex").is_err());
        assert!(sources_query("0123456789ABCDEF0123456789abcdef").is_err());
        assert!(sources_query("").is_err());
        assert!(sources_query(&good[..31]).is_err());
    }

    #[test]
    fn the_sources_are_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"sources": [{"kind": "note", "ref": "Ideas.md", "title": "Ideas"}],
            "unverified_quotes": ["a made-up line"]}"#;
        let got = sources_answer(200, body).unwrap();
        assert_eq!(got["sources"][0]["kind"], "note");
        assert_eq!(got["unverified_quotes"][0], "a made-up line");
        for old in [404, 501] {
            let a = sources_answer(old, r#"{"error": "x"}"#).unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], SOURCES_MISSING);
        }
        assert!(sources_answer(200, r#"{"ok": true}"#).is_err());
        assert!(sources_answer(200, "not json").is_err());
        assert!(sources_answer(401, r#"{"error": "bad or missing X-Jarvis-Token"}"#).is_err());
    }

    #[test]
    fn hidden_lists_keep_the_count_but_no_reference() {
        let answer = serde_json::json!({
            "sources": [{"kind": "note", "ref": "Health/Notes.md", "title": "Notes"},
                        {"kind": "web", "url": "https://example.com/x"}],
            "unverified_quotes": []
        });
        let hidden = redact_sources(answer);
        assert_eq!(hidden["sources"], serde_json::json!([]));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert!(!hidden.to_string().contains("Health"));
    }
}
