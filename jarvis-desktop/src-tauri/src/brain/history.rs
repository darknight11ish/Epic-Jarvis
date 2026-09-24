//! Chat history on the PC - the Brain's History tab (JARVIS-API.md section
//! 18, "Chat history").
//!
//! The PC keeps each conversation, encrypted, when "Keep chat history on
//! this PC" is on (the default). This window lists them, opens one
//! read-only, deletes ONE at a time, and changes the two settings. Four
//! commands, each its own power, like the rest of brain.rs:
//!
//! * [`brain_history_list`] - `GET /api/history`, a page at a time.
//! * [`brain_history_open`] - `GET /api/history/conversation?id=`.
//! * [`brain_history_delete`] - `POST /api/history/delete`, one id. There is
//!   no "delete all" here or on the server: irreversible bulk actions stay
//!   off the API.
//! * [`brain_history_settings`] - `POST /api/history/settings`, ONE field
//!   per request. Turning history ON only raises an approval card (tier
//!   `ask`), and is held while the event stream is stale (rule 4), exactly
//!   like the learning switch ([`super::brain_memory_learning`]). OFF is
//!   never held: it only narrows what Jarvis does.
//!
//! "Windows Hello for private answers" (lock.rs) covers this list too: while
//! the Brain's private lists are hidden, the list comes back with its
//! conversations taken out (how many there were is kept), and a transcript
//! is not opened at all. Here, in Rust, so a page script cannot read round
//! it.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// What a backend without chat history (without `chat-history.patch`) is
/// told to do about it. The page shows this sentence as it is.
pub(crate) const HISTORY_UPDATE: &str = "This PC's Jarvis does not keep chat history yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// The only "Delete conversations older than" choices the PC takes: never
/// (0, the default), 30 days, 90 days, a year.
pub(crate) const KEEP_DAYS: [u32; 4] = [0, 30, 90, 365];

/// What a transcript open is refused with while the private lists are
/// hidden.
pub(crate) const HISTORY_STILL_HIDDEN: &str = "Your chat history is hidden. Press Show on \
     the Brain's History tab and confirm it is you with Windows Hello first.";

/// A page of the list: 30 unless asked, never more than the server's 100.
const DEFAULT_LIMIT: u32 = 30;
const MAX_LIMIT: u32 = 100;

/// `GET /api/history`'s path for one page. `before` is the `updated` of the
/// oldest conversation already shown; it is written as the plain number the
/// page was given (Rust never writes an `f64` in exponent form), so paging
/// neither repeats nor skips one.
pub(crate) fn list_path(limit: Option<u32>, before: Option<f64>) -> Result<String, String> {
    let limit = limit.unwrap_or(DEFAULT_LIMIT).clamp(1, MAX_LIMIT);
    let mut path = format!("/api/history?limit={limit}");
    if let Some(b) = before {
        if !b.is_finite() || b <= 0.0 {
            return Err(format!("{b} is not a moment in time"));
        }
        path.push_str(&format!("&before={b}"));
    }
    Ok(path)
}

/// The id, checked before it goes into a URL or a body: 8-64 characters of
/// `[A-Za-z0-9_-]`, what the PC makes and accepts. Nothing else can reach
/// the query string.
fn checked_id(id: &str) -> Result<&str, String> {
    if commands::valid_conversation_id(id) {
        Ok(id)
    } else {
        Err("That is not a conversation this PC keeps.".to_string())
    }
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// [`brain_history_list`]'s reading of the answer.
///
/// * 2xx with `enabled` and a `conversations` list - passed on as it is.
/// * 404 - `{"available": false, "why": HISTORY_UPDATE}`: an older backend,
///   which the page says plainly rather than as an error.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn list_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| {
                v.get("enabled").is_some_and(|e| e.is_boolean())
                    && v.get("conversations").is_some_and(|c| c.is_array())
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Ok(serde_json::json!({ "available": false, "why": HISTORY_UPDATE }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_history_open`]'s reading: the transcript, or why not. A 404 is
/// "no such conversation" - it was deleted (here, on the phone, or by the
/// keep setting) after the list was read.
pub(crate) fn conversation_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("turns").is_some_and(|t| t.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Err(
            "That conversation is no longer kept on this PC. It was deleted, \
                    or it was older than the keep setting."
                .to_string(),
        );
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_history_delete`]'s reading. A 404 means it is already gone -
/// which is what was asked for - so it is `{"ok": true, "gone": true}`, and
/// the page says it was already deleted rather than that deleting failed.
pub(crate) fn delete_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return Ok(parsed(body).unwrap_or_else(|| serde_json::json!({ "ok": true })));
    }
    if status == 404 {
        return Ok(serde_json::json!({ "ok": true, "gone": true }));
    }
    Err(commands::backend_refusal(status, body))
}

/// The body for `POST /api/history/settings`: exactly ONE of the two, as
/// the server takes them (anything else is a 400 there). `keep_days` only
/// from [`KEEP_DAYS`].
pub(crate) fn settings_body(
    enabled: Option<bool>,
    keep_days: Option<u32>,
) -> Result<serde_json::Value, String> {
    match (enabled, keep_days) {
        (Some(on), None) => Ok(serde_json::json!({ "enabled": on })),
        (None, Some(days)) if KEEP_DAYS.contains(&days) => {
            Ok(serde_json::json!({ "keep_days": days }))
        }
        (None, Some(days)) => Err(format!(
            "{days} days is not a choice; pick never, 30 days, 90 days or 1 year."
        )),
        _ => Err("Change one chat history setting at a time.".to_string()),
    }
}

/// [`brain_history_settings`]'s reading. 200 (off, keep days) and 202
/// (`{"waiting": true}` - a card was raised, history is NOT on yet) are both
/// answers to show as they are; a 503 (the tier is not `ask`) and anything
/// else is the backend's own sentence.
pub(crate) fn settings_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Err(HISTORY_UPDATE.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The list with its conversations taken out, for while the private lists
/// are hidden (lock.rs). The switch, the keep setting and `why_not` stay:
/// they say nothing about what was said.
pub(crate) fn redact_list(mut list: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = list.as_object_mut() {
        if let Some(serde_json::Value::Array(items)) = obj.get_mut("conversations") {
            let count = items.len();
            items.clear();
            obj.insert("hidden".into(), serde_json::json!(true));
            obj.insert("hidden_count".into(), serde_json::json!(count));
        }
    }
    list
}

// ---------------------------------------------------------------------------
// The commands
// ---------------------------------------------------------------------------

async fn get(app: &AppHandle, path: &str) -> Result<(u16, String), String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    Ok((status, response.text().await.unwrap_or_default()))
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<(u16, String), String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    Ok((status, response.text().await.unwrap_or_default()))
}

/// One page of conversations, newest first. `before`: the `updated` of the
/// oldest one already shown, for "Load older". Reads only.
#[tauri::command]
pub async fn brain_history_list(
    app: AppHandle,
    before: Option<f64>,
    limit: Option<u32>,
) -> Result<serde_json::Value, String> {
    let path = list_path(limit, before)?;
    let (status, body) = get(&app, &path).await?;
    let answer = list_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_list(answer)
    } else {
        answer
    })
}

/// One conversation's transcript, read-only. Refused while the private
/// lists are hidden.
#[tauri::command]
pub async fn brain_history_open(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    let id = checked_id(&id)?;
    if crate::lock::private_hidden(&app) {
        return Err(HISTORY_STILL_HIDDEN.to_string());
    }
    let (status, body) = get(&app, &format!("/api/history/conversation?id={id}")).await?;
    conversation_answer(status, &body)
}

/// Deletes ONE conversation. It cannot be undone, and the page asks first.
/// Held while the event stream is stale, like forgetting a fact
/// ([`super::brain_memory_forget`]): it acts on a list read from a link
/// that cannot be confirmed live.
#[tauri::command]
pub async fn brain_history_delete(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let id = checked_id(&id)?;
    let (status, body) = post(&app, "/api/history/delete", serde_json::json!({ "id": id })).await?;
    delete_answer(status, &body)
}

/// Changes ONE chat history setting: `enabled` (the switch) or `keep_days`.
///
/// Turning history ON raises an approval card and is held on a stale link;
/// OFF is immediate and never held. A `keep_days` shorter than before
/// deletes older conversations at once, and it was chosen from a setting
/// this window read, so every keep change is held on a stale link too (the
/// page greys the choice then, the same rule).
#[tauri::command]
pub async fn brain_history_settings(
    app: AppHandle,
    enabled: Option<bool>,
    keep_days: Option<u32>,
) -> Result<serde_json::Value, String> {
    let body = settings_body(enabled, keep_days)?;
    if enabled == Some(true) || keep_days.is_some() {
        require_link_live(&app)?;
    }
    let (status, text) = post(&app, "/api/history/settings", body).await?;
    settings_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_page_is_asked_for_within_the_servers_limits() {
        assert_eq!(list_path(None, None).unwrap(), "/api/history?limit=30");
        assert_eq!(list_path(Some(0), None).unwrap(), "/api/history?limit=1");
        assert_eq!(
            list_path(Some(500), None).unwrap(),
            "/api/history?limit=100"
        );
        assert_eq!(
            list_path(Some(30), Some(1_790_000_300.0)).unwrap(),
            "/api/history?limit=30&before=1790000300"
        );
        // A fractional `updated` goes back exactly as it came, never rounded
        // into the next second.
        assert_eq!(
            list_path(None, Some(1_790_000_300.25)).unwrap(),
            "/api/history?limit=30&before=1790000300.25"
        );
        for bad in [f64::NAN, f64::INFINITY, 0.0, -5.0] {
            assert!(list_path(None, Some(bad)).is_err(), "{bad}");
        }
    }

    #[test]
    fn only_a_well_formed_id_reaches_a_url() {
        assert!(checked_id("3f2c9a1e-7b4d-4c1a-9e2f-0a1b2c3d4e5f").is_ok());
        for bad in [
            "short",
            "a&limit=100000",
            "a b c d e f g",
            "../../etc/passwd",
        ] {
            assert!(checked_id(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn the_list_is_passed_on_and_an_older_backend_says_update() {
        let body = r#"{"enabled": true, "recording": true, "why_not": "", "waiting": false,
            "keep_days": 0, "encrypted": true, "conversations": [{"id": "abcdefgh"}]}"#;
        let got = list_answer(200, body).unwrap();
        assert_eq!(got["conversations"][0]["id"], "abcdefgh");
        let old = list_answer(404, "").unwrap();
        assert_eq!(old["available"], false);
        assert!(old["why"].as_str().unwrap().contains("apply-patches.ps1"));
        assert!(list_answer(200, r#"{"ok": true}"#).is_err());
        assert_eq!(
            list_answer(500, r#"{"error": "the history store is locked"}"#).unwrap_err(),
            "The history store is locked"
        );
    }

    #[test]
    fn a_transcript_or_why_not() {
        let got = conversation_answer(200, r#"{"id": "abcdefgh", "turns": []}"#).unwrap();
        assert_eq!(got["id"], "abcdefgh");
        assert!(conversation_answer(404, "")
            .unwrap_err()
            .contains("no longer kept"));
        assert!(conversation_answer(200, "{}").is_err());
    }

    #[test]
    fn deleting_one_already_gone_is_not_a_failure() {
        assert_eq!(delete_answer(200, r#"{"ok": true}"#).unwrap()["ok"], true);
        let gone = delete_answer(404, "").unwrap();
        assert_eq!(gone["gone"], true);
        assert!(delete_answer(500, "").is_err());
    }

    #[test]
    fn one_setting_per_request_and_only_the_four_keep_choices() {
        assert_eq!(
            settings_body(Some(false), None).unwrap(),
            serde_json::json!({ "enabled": false })
        );
        for days in KEEP_DAYS {
            assert_eq!(
                settings_body(None, Some(days)).unwrap(),
                serde_json::json!({ "keep_days": days })
            );
        }
        assert!(settings_body(None, Some(7)).is_err());
        assert!(settings_body(Some(true), Some(30)).is_err());
        assert!(settings_body(None, None).is_err());
    }

    #[test]
    fn on_waits_and_a_refusal_is_the_servers_own_sentence() {
        let waiting = settings_answer(202, r#"{"waiting": true, "enabled": false}"#).unwrap();
        assert_eq!(waiting["waiting"], true);
        assert_eq!(
            settings_answer(
                503,
                r#"{"error": "history_enable is not set to ask in jarvis-framework.toml"}"#
            )
            .unwrap_err(),
            "History_enable is not set to ask in jarvis-framework.toml"
        );
        assert_eq!(settings_answer(404, "").unwrap_err(), HISTORY_UPDATE);
    }

    #[test]
    fn hidden_lists_keep_the_count_and_the_settings_but_no_conversation() {
        let list = serde_json::json!({
            "enabled": true, "recording": true, "keep_days": 30,
            "conversations": [{"id": "abcdefgh", "title": "Dentist"}, {"id": "ijklmnop"}]
        });
        let hidden = redact_list(list);
        assert_eq!(hidden["conversations"], serde_json::json!([]));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert_eq!(hidden["keep_days"], 30);
        assert!(!hidden.to_string().contains("Dentist"));
    }
}
