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
use crate::brain::schedule::{
    act_body, answer_body, change_body, change_timeout, hud_add_body, post, post_with_timeout,
    ScheduleChange,
};

/// The Reminders tab's Add form: ONE reminder, timer, alarm or to-do item -
/// and, since 2026-11-03, ONE routine: a reminder with 2 to 12 `steps`, each
/// with its own words, its own time and optionally its own question.
///
/// Every field is the form's own; `hud_add_body` refuses anything the backend
/// does not already take for the four kinds. Editing an existing item does not
/// come through here - it is `hud_schedule_act`'s `edit`, the same one command
/// everything else on a row goes through, so there is no second edit path.
//
// One argument per form field, on purpose: they are the page's own inputs,
// kept flat like the Brain's `brain_schedule_add_today`, and mirrored one to
// one by the tests. Grouping them into a struct would only move the same
// values behind another name.
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
    action: Option<serde_json::Value>,
    steps: Option<serde_json::Value>,
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
        action.as_ref(),
        steps.as_ref(),
    )?;
    post(&app, "/api/schedule/add", body).await
}

/// ONE job's change - the six Phase 1 actions, and since 2026-10-22 the three
/// Phase 2 verbs (edit, move, reorder) through the optional typed `change`.
/// No card is raised here; the ONE exception is the PC's own `schedule_repeat`
/// 202 for a repeat edit, whose wait gets the longer budget. This command has
/// NO list form: Ruling 15 keeps "clear named list" out of the HUD (the Brain
/// window does it), and the builders refuse anything that is not one job's.
///
/// `action: "answer"` (2026-11-02) is the tenth name and the one that changes
/// nothing: ONE button of ONE question, pressed, carrying the button's INDEX in
/// `button` and never its label. It is cardless - an answer is a log line, like
/// ticking a to-do item - and [`answer_body`] is the only way that body is
/// built, so a page can never name what is written. `step` (2026-11-03) is
/// WHICH part of a routine, also an index and also never a label; it is absent
/// for a reminder with no parts.
#[tauri::command]
pub async fn hud_schedule_act(
    app: AppHandle,
    id: String,
    action: String,
    seconds: Option<f64>,
    change: Option<ScheduleChange>,
    button: Option<u32>,
    step: Option<u32>,
) -> Result<serde_json::Value, String> {
    brain::require_link_live(&app)?;
    if action == "answer" {
        let body = answer_body(&id, button, step)?;
        return post(&app, "/api/schedule/act", body).await;
    }
    if let Some(change) = change {
        let body = change_body(&id, &action, &change)?;
        let timeout = change_timeout(&action, &change);
        return post_with_timeout(&app, "/api/schedule/act", body, timeout).await;
    }
    let body = act_body(&id, &action, seconds)?;
    post(&app, "/api/schedule/act", body).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::brain::schedule::{ACTIONS, MAX_ASK_BUTTONS, MAX_STEPS, SNOOZE_SECONDS};

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

    /// Phase 2 (2026-10-22): the HUD's ONE change path uses the shared builder,
    /// chooses `move` for a list-only edit, and gives only the repeat edit the
    /// 1,200 s budget.
    #[test]
    fn the_hud_change_path_is_the_shared_one() {
        let text = ScheduleChange {
            text: Some("buy milk".into()),
            ..Default::default()
        };
        assert_eq!(
            change_body("s0123456789", "edit", &text).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "edit", "text": "buy milk"})
        );
        assert_eq!(
            change_body(
                "s0123456789",
                "edit",
                &ScheduleChange {
                    list: Some("shopping".into()),
                    ..Default::default()
                }
            )
            .unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "move", "list": "shopping"})
        );
        let rank = ScheduleChange {
            rank: Some(0),
            ..Default::default()
        };
        assert_eq!(
            change_body("s0123456789", "reorder", &rank).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "reorder", "rank": 0})
        );
        let repeat = ScheduleChange {
            repeat: Some(serde_json::json!({"every": "day", "at": "07:00"})),
            ..Default::default()
        };
        assert_eq!(change_timeout("edit", &repeat).as_secs(), 1_200);
        assert_eq!(change_timeout("edit", &text).as_secs(), 20);
        assert_eq!(
            change_timeout("pause", &ScheduleChange::default()).as_secs(),
            20
        );
    }

    /// 2026-11-02: answering one button of one question, and the rails around
    /// it - an id the PC makes, an INDEX (never a label, never a target), and
    /// the three-button ceiling the PC enforces.
    ///
    /// 2026-11-03: and WHICH part of a routine, also an index, also never a
    /// label - absent for a reminder with no parts, so every body this app sent
    /// before today is the body it still sends.
    #[test]
    fn one_button_of_one_question_is_answered_by_index_only() {
        assert_eq!(
            answer_body("s0123456789", Some(0), None).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "answer", "button": 0})
        );
        assert_eq!(
            answer_body("s0123456789", Some(2), None).unwrap()["button"],
            serde_json::json!(2)
        );
        // A routine's part: the step rides with the same body, and a reminder
        // with no parts grows no `step` key at all.
        assert_eq!(
            answer_body("s0123456789", Some(1), Some(2)).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "answer", "button": 1,
                               "step": 2})
        );
        assert!(answer_body("s0123456789", Some(0), None)
            .unwrap()
            .get("step")
            .is_none());
        // No id the PC would make, no button, and a fourth button - refused
        // here, in the words both apps use, before anything leaves this app.
        assert!(answer_body("", Some(0), None).is_err());
        assert!(answer_body("not-an-id", Some(0), None).is_err());
        assert!(answer_body("s0123456789", None, None).is_err());
        assert!(answer_body("s0123456789", Some(3), None).is_err());
        assert!(answer_body("s0123456789", Some(99), None).is_err());
        // A thirteenth part, in the PC's own sentence.
        assert_eq!(
            answer_body("s0123456789", Some(0), Some(MAX_STEPS))
                .unwrap_err()
                .as_str(),
            "A routine has up to 12 parts."
        );
        assert!(answer_body("s0123456789", Some(0), Some(MAX_STEPS - 1)).is_ok());
        // And `answer` is reachable by NAME through the closed action list, so
        // the page's own invoke is the only door it has.
        assert!(ACTIONS.contains(&"answer"));
        assert_eq!(MAX_ASK_BUTTONS, 3);
        assert_eq!(MAX_STEPS, 12);
    }
}
