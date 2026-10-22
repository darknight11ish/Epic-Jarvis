//! Chat history's switch and retention, for Settings (2026-10-22, task-79's
//! owner requirement + voiceprint-wiring's #734 typed `chat_history` and
//! `chat_keep_days`). Backend `jarvis_chat_log.py`, route `/api/history/settings`
//! added by `backend/chat-history.patch`, JARVIS-API section 18.
//!
//! WHY THIS EXISTS. The typed path for both settings shipped first (#734);
//! the only UI was the Brain's History tab, so Settings showed no control and
//! the typed path looked covered while the owner requirement "findable and
//! adjustable in Settings too" was not met for these two. This command is the
//! Settings window's own, narrow path.
//!
//! TWO SETTINGS, EACH ONE FIELD PER REQUEST - the route's own contract. The
//! body is one of `{"enabled": bool}` or `{"keep_days": 0|30|90|365}`, never
//! both, and `keep_days` is checked here against the same four values the
//! route accepts. There is no delete path in this command at all: deleting a
//! conversation stays in the Brain's History, one id per request, and this
//! command cannot reach it.
//!
//! READ = THE PC'S STATUS, NEVER A CONVERSATION. There is no
//! `GET /api/history/settings` route; the status fields ride on
//! `GET /api/history?limit=1`. This command asks for that one page and returns
//! ONLY `enabled`, `keep_days`, `recording` and `why_not` - the conversation
//! list is dropped IN RUST, so a single chat word never crosses the loopback
//! wire into the Settings page. (The PC-side process still reads the page the
//! route serves; the page does not.)
//!
//! ON IS ONE CARD, AND SO IS A RETENTION CHANGE. `enabled: true` raises the
//! EXISTING `history_enable` card (tier ask) and the route answers 202
//! "waiting" straight away - the page says so and re-reads the status until it
//! is decided. A `keep_days` change DELETES conversations older than the
//! chosen age at once, so it is held on a stale link too (rule 4) - the same
//! rule the Brain's own History switch follows. OFF is immediate and never
//! held. All writes get the short budget: none of them blocks on a person.

use std::time::Duration;

use tauri::AppHandle;

use crate::look;

/// The verbs `history_settings` takes.
pub(crate) const ACTIONS: &[&str; 4] = &["read", "on", "off", "keep"];

/// The retention choices the route accepts, in days; 0 means "keep until I
/// delete them". Kept here as the one list this command will send.
pub(crate) const KEEP_DAYS: [u32; 4] = [0, 30, 90, 365];

const PATH: &str = "/api/history/settings";
/// The one page the status fields ride on; `limit=1` because nothing from the
/// page is returned - it is read only for `enabled`/`keep_days`/`recording`.
const STATUS_PATH: &str = "/api/history?limit=1";

/// A PC whose backend predates chat history (the same words the Brain uses).
pub(crate) const MISSING: &str = "This PC's Jarvis does not keep chat history yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// ON asks for a card, and a retention change deletes older conversations at
/// once: both are held while the link is stale (rule 4). OFF is never held.
const STALE_HELD: &str = "The connection to Jarvis is catching up, so changing this is held \
     until it does - try again in a moment. Turning chat history off works at once.";

/// One write with no waiting on a person: ON answers 202 at once, OFF and a
/// retention change are immediate. Ten seconds is plenty.
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);

/// The body of one verb - ONE field, exactly as the route documents.
pub(crate) fn body(action: &str, keep_days: Option<u32>) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!("The chat history setting cannot {action:?}"));
    }
    match action {
        "on" => Ok(serde_json::json!({ "enabled": true })),
        "off" => Ok(serde_json::json!({ "enabled": false })),
        "keep" => match keep_days {
            Some(days) if KEEP_DAYS.contains(&days) => Ok(serde_json::json!({ "keep_days": days })),
            Some(days) => Err(format!(
                "{days} is not one of the retention choices (0, 30, 90 or 365 days)"
            )),
            None => Err("choosing how long chats are kept needs the number of days".to_string()),
        },
        _ => Ok(serde_json::json!({})),
    }
}

/// Is this change held because the link is stale?
pub(crate) fn held(action: &str, stale: bool) -> bool {
    stale && (action == "on" || action == "keep")
}

/// The status fields and nothing else from `GET /api/history`'s answer.
///
/// The conversation list is dropped here, in Rust: the page that calls this
/// command never sees a chat word, a title or an id. Anything unreadable is
/// an error (the page then says the PC answered in an unreadable way) rather
/// than a guess.
pub(crate) fn status_only(v: &serde_json::Value) -> Result<serde_json::Value, String> {
    let enabled = v
        .get("enabled")
        .and_then(|b| b.as_bool())
        .ok_or_else(|| "the chat history answer did not say whether it is on".to_string())?;
    let keep = v.get("keep_days").and_then(|n| n.as_u64()).unwrap_or(0) as u32;
    let keep_days = if KEEP_DAYS.contains(&keep) { keep } else { 0 };
    let recording = v
        .get("recording")
        .and_then(|b| b.as_bool())
        .unwrap_or(false);
    let why_not = v
        .get("why_not")
        .and_then(|s| s.as_str())
        .unwrap_or("")
        .to_string();
    Ok(serde_json::json!({
        "enabled": enabled,
        "keep_days": keep_days,
        "recording": recording,
        "why_not": why_not,
    }))
}

/// What a switch/retention answer means for the page: the PC's own words plus
/// the values it repaints from - still no conversation. `look::post` has
/// already turned every non-2xx into its refusal sentence, so this only reads
/// the successful shape (200 applied, 202 waiting for the card).
pub(crate) fn answer(v: &serde_json::Value) -> serde_json::Value {
    let mut out = serde_json::Map::new();
    out.insert("ok".into(), serde_json::json!(true));
    for key in ["waiting", "paused"] {
        if let Some(b) = v.get(key).and_then(|b| b.as_bool()) {
            out.insert(key.into(), serde_json::json!(b));
        }
    }
    for key in ["enabled", "recording"] {
        if let Some(b) = v.get(key).and_then(|b| b.as_bool()) {
            out.insert(key.into(), serde_json::json!(b));
        }
    }
    for key in ["keep_days", "deleted"] {
        if let Some(n) = v.get(key).and_then(|n| n.as_u64()) {
            out.insert(key.into(), serde_json::json!(n));
        }
    }
    if let Some(m) = v.get("message").and_then(|m| m.as_str()) {
        out.insert("message".into(), serde_json::json!(m));
    }
    serde_json::Value::Object(out)
}

/// The chat history switch and retention choice, for Settings.
#[tauri::command]
pub async fn history_settings(
    app: AppHandle,
    action: String,
    keep_days: Option<u32>,
) -> Result<serde_json::Value, String> {
    let body = body(&action, keep_days)?;
    if held(&action, look::stale(&app)) {
        return Err(STALE_HELD.to_string());
    }
    if action == "read" {
        let page = look::get(&app, STATUS_PATH).await.map_err(|why| {
            if why == look::MISSING {
                MISSING.to_string()
            } else {
                why
            }
        })?;
        return status_only(&page);
    }
    let said = look::post(&app, PATH, body, WRITE_TIMEOUT)
        .await
        .map_err(|why| {
            if why == look::MISSING {
                MISSING.to_string()
            } else {
                why
            }
        })?;
    Ok(answer(&said))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn each_change_sends_exactly_one_field() {
        assert_eq!(body("read", None).unwrap(), json!({}));
        assert_eq!(body("on", None).unwrap(), json!({ "enabled": true }));
        assert_eq!(body("off", None).unwrap(), json!({ "enabled": false }));
        assert_eq!(body("keep", Some(30)).unwrap(), json!({ "keep_days": 30 }));
        for days in KEEP_DAYS {
            assert_eq!(
                body("keep", Some(days)).unwrap(),
                json!({ "keep_days": days })
            );
        }
    }

    #[test]
    fn only_the_four_retention_choices_and_no_mixing() {
        for bad in [1u32, 7, 29, 31, 364, 366, 1000] {
            assert!(body("keep", Some(bad)).is_err(), "{bad} was accepted");
        }
        assert!(
            body("keep", None).is_err(),
            "a keep_days change with no number"
        );
        // One field per request: the retention body never carries `enabled`.
        let keep = body("keep", Some(90)).unwrap();
        assert!(keep.get("enabled").is_none());
        let on = body("on", None).unwrap();
        assert!(on.get("keep_days").is_none());
    }

    #[test]
    fn only_the_two_loosening_changes_are_held_by_a_stale_link() {
        assert!(held("on", true));
        assert!(
            held("keep", true),
            "a retention change deletes older chats at once"
        );
        assert!(!held("off", true), "OFF must never be held");
        assert!(!held("read", true));
        assert!(!held("on", false));
    }

    #[test]
    fn on_answers_waiting_at_once_so_no_write_blocks_on_a_person() {
        // The route raises the card and returns 202 "waiting" immediately, so
        // every write gets the short budget; the page re-reads the status
        // until the card is decided.
        assert!(WRITE_TIMEOUT <= Duration::from_secs(15));
    }

    #[test]
    fn the_read_drops_every_conversation_and_keeps_only_the_status() {
        let page = json!({
            "enabled": true, "keep_days": 30, "recording": true, "why_not": "",
            "conversations": [
                {"id": "c1", "title": "private chat title", "messages": ["a word"]},
            ],
        });
        let out = status_only(&page).unwrap();
        assert_eq!(
            out,
            json!({"enabled": true, "keep_days": 30,
                               "recording": true, "why_not": ""})
        );
        let text = out.to_string();
        assert!(!text.contains("private chat title"));
        assert!(!text.contains("conversations"));
        assert!(!text.contains("a word"));
    }

    #[test]
    fn an_unreadable_status_is_an_error_not_a_guess() {
        assert!(status_only(&json!({"keep_days": 30})).is_err());
        // A keep value the route would not accept reads as the default, never
        // as a value this app then shows as real.
        let out = status_only(&json!({"enabled": false, "keep_days": 7})).unwrap();
        assert_eq!(out["keep_days"], json!(0));
    }

    #[test]
    fn no_delete_or_conversation_verb_exists_here() {
        for verb in ["delete", "delete-all", "clear", "open", "search", ""] {
            assert!(body(verb, None).is_err(), "{verb} was accepted");
        }
        assert_eq!(ACTIONS.len(), 4);
    }
}
