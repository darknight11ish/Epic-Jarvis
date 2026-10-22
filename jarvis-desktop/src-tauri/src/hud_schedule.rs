//! The HUD Reminders tab's writes (2026-10-21, the owner's request): ONE
//! schedule change or ONE new item at a time.
//!
//! The HUD page holds NO pairing token (apps security audit M2), so its
//! writes cannot be its own POSTs: `hud_bootstrap.js` refuses those, and
//! these two commands are the only door. They post the same backend routes
//! and bodies the Brain's Coming up uses (`brain/schedule.rs`) - the
//! builders are shared, not copied - and they hold the same stale-link rule
//! (`brain::require_link_live`): nothing is sent until the event stream says
//! the link is live.
//!
//! Neither raises an approval card: adding one item and pausing/deleting one
//! only adds or quiets. There is no list form and no "delete all", and this
//! window has NO clear-list command at all (Ruling 15: the HUD's scope is add
//! plus one job's snooze/add-time/pause/resume/done/delete; clearing a whole
//! named list stays the Brain window's). The to-do list itself has no Clear.
//!
//! Reads are NOT here: the page's `GET /api/schedule` goes through
//! `hud_proxy.rs`, where the words are taken out while App lock or the
//! private lists are hidden.

use tauri::AppHandle;

use crate::brain;
use crate::brain::schedule::{act_body, hud_add_body, post};

/// The Reminders tab's Add form: ONE reminder, timer, alarm or to-do item.
///
/// Every field is the form's own; `hud_add_body` refuses anything the
/// backend does not already take for the four kinds (and PHASE 1 has no
/// body for editing an existing item - that needs backend actions).
//
// One argument per form field, on purpose: they are the page's own inputs,
// kept flat like the Brain's `brain_schedule_add_today`, and mirrored one to
// one by the tests. Grouping them into a struct would only move the same
// eight values behind another name.
#[allow(clippy::too_many_arguments)]
#[tauri::command]
pub async fn hud_schedule_add(
    app: AppHandle,
    kind: String,
    text: Option<String>,
    notes: Option<String>,
    seconds: Option<f64>,
    date: Option<String>,
    time: Option<String>,
    repeat: Option<serde_json::Value>,
    list: Option<String>,
) -> Result<serde_json::Value, String> {
    brain::require_link_live(&app)?;
    let body = hud_add_body(
        &kind,
        text.as_deref(),
        notes.as_deref(),
        seconds,
        date.as_deref(),
        time.as_deref(),
        repeat.as_ref(),
        list.as_deref(),
    )?;
    post(&app, "/api/schedule/add", body).await
}

/// ONE job's action - snooze, add time, pause, resume, done or delete. No
/// card; stale link held. This command has NO list form: Ruling 15 keeps
/// "clear named list" out of the HUD (the Brain window does it), and
/// `act_body` refuses every action that is not one job's.
#[tauri::command]
pub async fn hud_schedule_act(
    app: AppHandle,
    id: String,
    action: String,
    seconds: Option<f64>,
) -> Result<serde_json::Value, String> {
    brain::require_link_live(&app)?;
    let body = act_body(&id, &action, seconds)?;
    post(&app, "/api/schedule/act", body).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::brain::schedule::SNOOZE_SECONDS;

    #[test]
    fn one_job_actions_keep_the_brains_own_rules() {
        let body = |id: &str, action: &str, seconds: Option<f64>| act_body(id, action, seconds);
        assert_eq!(
            body("s0123456789", "pause", None).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "pause"})
        );
        assert_eq!(
            body("s0123456789", "add_time", Some(300.0)).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "add_time", "seconds": 300.0})
        );
        assert_eq!(
            body("s0123456789", "snooze", None).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "snooze", "seconds": SNOOZE_SECONDS})
        );
        // No id, a made-up id, and an action that is not one job's are refused.
        assert!(body("", "pause", None).is_err());
        assert!(body("not-an-id", "pause", None).is_err());
        assert!(body("s0123456789", "delete_all", None).is_err());
        // Ruling 15: the HUD has no list form, so a clear-list body can never
        // leave this command - the Brain keeps that action.
        assert!(body("s0123456789", "clear_list", None).is_err());
        assert!(body("s0123456789", "clear_all", None).is_err());
        // add_time needs its seconds; never a guessed amount.
        assert!(body("s0123456789", "add_time", None).is_err());
    }
}
