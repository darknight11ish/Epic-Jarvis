//! Goals - a plan the owner edits, one card per acting step (the owner's
//! "build it now", 2026-09-27; JARVIS-API.md section 59; backend
//! jarvis_goals.py).
//!
//! Five commands, each its own power, like the rest of brain.rs:
//!
//! * [`brain_goals`] - `GET /api/goals`: the list, plus the PC's own limits
//!   (steps per plan, open goals, text lengths). A read. While "Windows
//!   Hello for memory lists and chat history" (lock.rs) hides the Brain's
//!   private lists, a goal's and a step's own words are taken out here, in
//!   Rust, so a page script cannot read round it - the same treatment
//!   [`super::schedule::redact_list`] already gives reminders and to-dos.
//!   Status and step count stay: they say nothing about the owner, and a
//!   stopped goal should still look stopped.
//! * [`brain_goals_create`] - `POST /api/goals {"text", "plan"?}`: a new
//!   DRAFT. No card - a draft is content, not action, exactly like an
//!   email draft. Held on a stale link, like every write below.
//! * [`brain_goals_accept`] - `POST /api/goals/<id>/accept {"plan"?}`: the
//!   owner's edited plan (or the draft as it stood) is kept, and the goal
//!   becomes active. This is the ONE place anything here can raise a card:
//!   the backend sets up a weekly check-in through `jarvis_schedule.py`'s
//!   existing `schedule_repeat` mechanism - the SAME one a repeating
//!   reminder or the morning briefing already raises - approving nothing
//!   that acts.
//! * [`brain_goals_step`] - `POST /api/goals/<id>/step {"index", "done"}`:
//!   marks one step done or not. No card - the same shape as ticking off a
//!   to-do item.
//! * [`brain_goals_stop`] - `POST /api/goals/<id>/stop`: stops tracking the
//!   goal and deletes its check-in job on the PC. No card, immediate - the
//!   same rule every "stop tracking this" control in this project follows.
//!
//! ## Where the weekly check-in shows
//!
//! See `../../goals.js`'s own module doc for the full reasoning: the
//! backend registers the check-in `owner_listed=True` (its own default),
//! so it already appears on Coming up like any other repeating job, and
//! this file does not try to carve out a private channel for it - it reads
//! the same list [`super::schedule::brain_schedule`] already reads, rather
//! than inventing a second source of truth for one job's live state.
//!
//! Every write here only ever forwards the owner's own words and choices;
//! none of it decides whether a card is needed - that decision is entirely
//! the backend's (rule 4), and this file's role is only to ask, hold on a
//! stale link, and show the backend's own answer, including its own plain
//! refusal sentences (`{"ok": false, "error": "..."}`) unchanged.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no Goals yet. The phone says the same words,
/// once it has this feature too.
pub(crate) const GOALS_MISSING: &str =
    "Your PC's Jarvis does not have Goals yet - run apply-patches.ps1 on the PC.";

/// A change refused because the PC has no such route. Nothing changed.
pub(crate) const GOALS_TOO_OLD: &str = "Not changed: your PC's Jarvis does not have Goals yet.";

/// The goal is not on the list any more (a 404 that says so).
pub(crate) const NO_SUCH_GOAL: &str = "That is not on the list any more.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// A goal id as the PC makes them: "g" and ten hex digits (jarvis_goals.py,
/// `"g" + uuid.uuid4().hex[:10]`).
pub(crate) fn valid_id(id: &str) -> bool {
    id.len() == 11
        && id.starts_with('g')
        && id[1..]
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A body the backend itself classified as a refusal - `{"ok": false,
/// "error": "..."}`, its own plain sentence (jarvis_goals._err) - never
/// guessed, never reworded here. `None` for a shape this route never sends,
/// which is how an old backend's 404 (no such route at all) is told apart
/// from this feature's own "no such goal" 404.
fn backend_error(body: &str) -> Option<String> {
    let v = parsed(body)?;
    if v.get("ok").and_then(|o| o.as_bool()) != Some(false) {
        return None;
    }
    v.get("error")
        .and_then(|e| e.as_str())
        .map(str::to_string)
        .filter(|s| !s.is_empty())
}

/// [`brain_goals`]'s reading of the answer.
pub(crate) fn list_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("goals").is_some_and(|g| g.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": GOALS_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_goals_create`]'s, [`brain_goals_accept`]'s, [`brain_goals_step`]'s
/// and [`brain_goals_stop`]'s reading of the answer.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("goal").is_some())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if let Some(msg) = backend_error(body) {
        return Err(msg);
    }
    if status == 404 || status == 501 {
        return Err(GOALS_TOO_OLD.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The list with every goal's and step's own words taken out, for while the
/// private lists are hidden. Status, dates and step count stay.
pub(crate) fn redact_goals(mut list: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = list.as_object_mut() {
        if let Some(serde_json::Value::Array(goals)) = obj.get_mut("goals") {
            for g in goals.iter_mut() {
                if let Some(o) = g.as_object_mut() {
                    o.insert("text".into(), serde_json::json!(""));
                    if let Some(serde_json::Value::Array(plan)) = o.get_mut("plan") {
                        for step in plan.iter_mut() {
                            if let Some(s) = step.as_object_mut() {
                                s.insert("step".into(), serde_json::json!(""));
                                s.insert("by".into(), serde_json::json!(""));
                            }
                        }
                    }
                    o.insert("hidden".into(), serde_json::json!(true));
                }
            }
        }
        obj.insert("hidden".into(), serde_json::json!(true));
    }
    list
}

/// The goals list, plus the PC's own limits. A read.
#[tauri::command]
pub async fn brain_goals(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/goals"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = list_answer(status, &body)?;
    Ok(
        if crate::lock::private_hidden(&app) && answer.get("available") != Some(&false.into()) {
            redact_goals(answer)
        } else {
            answer
        },
    )
}

/// A new draft, in the owner's own words, with an optional plan (their own
/// edit, or something they asked Jarvis to suggest in an ordinary chat
/// message first and pasted in here). No card. Held on a stale link.
#[tauri::command]
pub async fn brain_goals_create(
    app: AppHandle,
    text: String,
    plan: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let mut body = serde_json::json!({ "text": text });
    if let Some(plan) = plan {
        body["plan"] = plan;
    }
    post(&app, "/api/goals", body).await
}

/// The owner's edited plan (or the draft as it stood) is kept, and the goal
/// becomes active. The ONE place this file can raise a card: the backend's
/// own weekly-check-in `schedule_repeat` card. Held on a stale link.
#[tauri::command]
pub async fn brain_goals_accept(
    app: AppHandle,
    id: String,
    plan: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err(NO_SUCH_GOAL.to_string());
    }
    let mut body = serde_json::json!({});
    if let Some(plan) = plan {
        body["plan"] = plan;
    }
    post(&app, &format!("/api/goals/{id}/accept"), body).await
}

/// One step, marked done or not - no card, the same shape as ticking off a
/// to-do item. Held on a stale link.
#[tauri::command]
pub async fn brain_goals_step(
    app: AppHandle,
    id: String,
    index: i64,
    done: bool,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err(NO_SUCH_GOAL.to_string());
    }
    post(
        &app,
        &format!("/api/goals/{id}/step"),
        serde_json::json!({ "index": index, "done": done }),
    )
    .await
}

/// Stops tracking the goal and deletes its check-in job on the PC. No card,
/// immediate. Held on a stale link.
#[tauri::command]
pub async fn brain_goals_stop(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err(NO_SUCH_GOAL.to_string());
    }
    post(
        &app,
        &format!("/api/goals/{id}/stop"),
        serde_json::json!({}),
    )
    .await
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    change_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_goal_id_is_g_and_ten_lowercase_hex_digits() {
        assert!(valid_id("g0123456789"));
        for bad in [
            "",
            "g012345678",
            "g01234567890",
            "G0123456789",
            "s0123456789",
            "all",
            "*",
        ] {
            assert!(!valid_id(bad), "{bad}");
        }
    }

    #[test]
    fn the_list_is_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"ok": true, "goals": [{"id": "g0123456789", "text": "insulate the garage",
            "plan": [{"step": "contact installers", "by": "", "done": false}], "status": "draft",
            "created": 1.0, "changed": 1.0}], "limits": {"text": 300, "steps": 7, "goals": 20, "by": 40}}"#;
        assert_eq!(
            list_answer(200, body).unwrap()["goals"][0]["id"],
            "g0123456789"
        );
        for old in [404, 501] {
            let a = list_answer(old, "{}").unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], GOALS_MISSING);
        }
        assert!(list_answer(200, r#"{"ok": true}"#).is_err());
        assert!(list_answer(200, "not json").is_err());
    }

    #[test]
    fn hidden_goals_keep_the_status_but_no_words() {
        let list = serde_json::json!({"goals": [
            {"id": "g0123456789", "text": "insulate the garage", "status": "active",
             "plan": [{"step": "contact installers", "by": "this week", "done": false}]},
        ]});
        let hidden = redact_goals(list);
        let s = hidden.to_string();
        assert!(!s.contains("garage") && !s.contains("installers") && !s.contains("this week"));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["goals"][0]["hidden"], true);
        assert_eq!(hidden["goals"][0]["status"], "active");
        assert_eq!(hidden["goals"][0]["plan"][0]["done"], false);
    }

    #[test]
    fn a_refused_change_says_the_backends_own_sentence_and_a_missing_route_is_never_a_success() {
        assert_eq!(
            change_answer(404, r#"{"ok": false, "error": "no such goal"}"#).unwrap_err(),
            "no such goal"
        );
        assert_eq!(
            change_answer(
                400,
                r#"{"ok": false, "error": "a plan needs at least one step"}"#
            )
            .unwrap_err(),
            "a plan needs at least one step"
        );
        assert_eq!(
            change_answer(
                409,
                r#"{"ok": false, "error": "there are already 20 goals"}"#
            )
            .unwrap_err(),
            "there are already 20 goals"
        );
        // A 404 with no such shape at all - not this feature's own refusal,
        // so it must never be misread as a real "no such goal".
        assert_eq!(change_answer(404, "").unwrap_err(), GOALS_TOO_OLD);
        assert_eq!(change_answer(404, "Not Found").unwrap_err(), GOALS_TOO_OLD);
        assert_eq!(change_answer(501, "{}").unwrap_err(), GOALS_TOO_OLD);
        assert!(change_answer(200, r#"{"ok": true, "goal": {"id": "g0123456789"}}"#).is_ok());
        assert!(change_answer(200, r#"{"ok": true}"#).is_err());
    }
}
