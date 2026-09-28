//! "Facts this chat taught" - for History's Delete (the owner's choice of
//! 2026-09-28; JARVIS-API.md section 79,
//! `GET /api/memory/conversation-facts?conversation_id=`).
//!
//! Deleting a chat now offers to forget the facts Jarvis learned from it:
//! the page lists them with a tick box each (none ticked), asks "are you
//! sure?", deletes the chat, and forgets each ticked fact through the
//! ordinary `brain_memory_forget` - ONE fact per call, held on a stale link
//! like every Forget. This command only READS the list; nothing here
//! forgets, and there is no list form of Forget anywhere.
//!
//! It is memory, so it is hidden like every memory list: while "Windows
//! Hello for memory lists and chat history" (lock.rs) holds the lists back,
//! the facts are taken out here in Rust (how many there were is kept), so a
//! page script cannot read round it - the page then deletes the chat only,
//! and says the facts were kept.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::READ_TIMEOUT;
use crate::commands;

/// What the page is told by a PC whose backend cannot list a chat's facts
/// yet (no update since 2026-09-28): it deletes the chat as before.
pub(crate) const CONVERSATION_FACTS_MISSING: &str =
    "This PC's Jarvis cannot list the facts a chat taught yet - run apply-patches.ps1 on the \
     PC to update it.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The query for one conversation, or why not: the shape JARVIS-API.md
/// 18.1 gives a conversation id (8-64 letters, digits, `-` or `_`), so
/// nothing else is ever put in the address.
pub(crate) fn conversation_facts_query(conversation_id: &str) -> Result<String, String> {
    let ok = (8..=64).contains(&conversation_id.len())
        && conversation_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_');
    if !ok {
        return Err("That is not a conversation id.".to_string());
    }
    Ok(format!("conversation_id={conversation_id}"))
}

/// [`brain_conversation_facts`]'s reading of the answer.
///
/// * 2xx with a `facts` list - passed on.
/// * 404 or 501 - `{"available": false, "why": CONVERSATION_FACTS_MISSING}`:
///   an older backend, said plainly; the page deletes the chat as before.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn conversation_facts_answer(
    status: u16,
    body: &str,
) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("facts").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": CONVERSATION_FACTS_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// The answer with every fact taken out, for while the memory lists are
/// hidden (lock.rs). How many there were stays: the page says the facts
/// were kept, and that showing the lists lets the owner choose.
pub(crate) fn redact_conversation_facts(mut answer: serde_json::Value) -> serde_json::Value {
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

/// The facts still in use that one conversation taught, newest first. A read.
#[tauri::command]
pub async fn brain_conversation_facts(
    app: AppHandle,
    conversation_id: String,
) -> Result<serde_json::Value, String> {
    let query = conversation_facts_query(&conversation_id)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/memory/conversation-facts?{query}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = conversation_facts_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_conversation_facts(answer)
    } else {
        answer
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_real_conversation_id_is_sent() {
        assert_eq!(
            conversation_facts_query("conv-abc_123").unwrap(),
            "conversation_id=conv-abc_123"
        );
        for bad in [
            "",
            "short",
            "has space in it",
            "a&b=c-defgh",
            &"x".repeat(65),
        ] {
            assert!(conversation_facts_query(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn the_facts_or_why_not() {
        let body = r#"{"conversation_id": "conv-abc_123", "facts": [
            {"id": 7, "text": "Owner likes green tea", "created": 1790000000.0, "source": "auto"}],
            "count": 1, "more": false}"#;
        let got = conversation_facts_answer(200, body).unwrap();
        assert_eq!(got["facts"][0]["id"], 7);
        assert!(conversation_facts_answer(200, r#"{"count": 1}"#).is_err());
        for status in [404, 501] {
            let old = conversation_facts_answer(status, r#"{"error": "no such route"}"#).unwrap();
            assert_eq!(old["available"], false);
            assert_eq!(old["why"], CONVERSATION_FACTS_MISSING);
        }
    }

    #[test]
    fn hidden_lists_take_the_words_out() {
        let body = serde_json::json!({"conversation_id": "conv-abc_123", "facts": [
            {"id": 7, "text": "Owner likes green tea"}, {"id": 8, "text": "Owner has a cat"}],
            "count": 2});
        let got = redact_conversation_facts(body);
        assert_eq!(got["facts"].as_array().unwrap().len(), 0);
        assert_eq!(got["hidden"], true);
        assert_eq!(got["hidden_count"], 2);
        assert!(!got.to_string().contains("green tea"));
    }
}
