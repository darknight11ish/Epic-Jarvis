//! The HUD calendar's writes (2026-10-29, the owner's desktop HUD request):
//! ONE local event added, changed or deleted at a time.
//!
//! The HUD page holds NO pairing token (apps security audit M2), so its writes
//! cannot be its own POSTs: `hud_bootstrap.js` refuses those, and these two
//! commands are the only door. They post the same backend routes the contract
//! names (`POST /api/calendar/add`, `POST /api/calendar/act`), with the token
//! added in Rust, and they hold the same stale-link rule as the Brain
//! (`brain::require_link_live`): nothing is sent until the event stream says
//! the link is live.
//!
//! Neither raises an approval card. Adding one event writes one row on this
//! PC, changing it changes that one row, and deleting it only makes things
//! quieter - the same "one job, and no list form" rule `/api/schedule/act` has.
//! There is deliberately NO delete-all, no clear-range and no bulk anything:
//! `brain::calendar::act_body` accepts exactly two verbs.
//!
//! Reads are NOT here: the page's `GET /api/calendar?days=N` goes through
//! `hud_proxy.rs`, where the titles, places and notes are taken out while App
//! lock or "Hide memory lists" is on.

use tauri::AppHandle;

use crate::brain;
use crate::brain::calendar::{act_body, add_body, CalendarChange};
use crate::brain::schedule::post;

/// The HUD calendar's Add form: ONE event, every field the contract names.
///
// One argument per form field, on purpose: they are the page's own inputs,
// kept flat like `hud_schedule_add` and mirrored one to one by the tests.
// Grouping them into a struct would only move the same ten values behind
// another name - and `CalendarChange` already IS that struct for an update.
#[allow(clippy::too_many_arguments)]
#[tauri::command]
pub async fn hud_calendar_add(
    app: AppHandle,
    title: String,
    date: String,
    time: Option<String>,
    end_date: Option<String>,
    end_time: Option<String>,
    all_day: Option<bool>,
    place: Option<String>,
    notes: Option<String>,
    remind_minutes: Option<i64>,
    recurrence: Option<String>,
) -> Result<serde_json::Value, String> {
    brain::require_link_live(&app)?;
    let body = add_body(
        &title,
        &date,
        time.as_deref(),
        end_date.as_deref(),
        end_time.as_deref(),
        all_day.unwrap_or(false),
        place.as_deref(),
        notes.as_deref(),
        remind_minutes,
        recurrence.as_deref(),
    )?;
    post(&app, "/api/calendar/add", body).await
}

/// ONE event's change: `delete`, or `update` with the fields the owner
/// changed. The page's own `action` name is `do` on the wire - the backend's
/// word - exactly as `hud_schedule_act` maps its `action`.
#[tauri::command]
pub async fn hud_calendar_act(
    app: AppHandle,
    id: String,
    action: String,
    change: Option<CalendarChange>,
) -> Result<serde_json::Value, String> {
    brain::require_link_live(&app)?;
    let body = act_body(&id, &action, change.as_ref())?;
    post(&app, "/api/calendar/act", body).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// The page's ten form fields, and the exact body they become: the same
    /// shape `tests/calendar.mjs` asserts on the page's side.
    #[test]
    fn the_add_form_is_the_contract_and_nothing_else() {
        let body = add_body(
            "Dentist",
            "2026-11-03",
            Some("14:30"),
            Some("2026-11-03"),
            Some("15:30"),
            false,
            Some("High Street"),
            Some("Bring the form"),
            Some(15),
            None,
        )
        .unwrap();
        assert_eq!(
            body,
            json!({
                "title": "Dentist", "date": "2026-11-03", "all_day": false,
                "time": "14:30", "end_time": "15:30",
                "place": "High Street", "notes": "Bring the form",
                "remind_minutes": 15,
            })
        );
        // The page's all-day tick is the same form with the times left out.
        let all_day = add_body("Trip", "2026-11-03", None, None, None, true,
            None, None, None, None).unwrap();
        assert_eq!(all_day["all_day"], true);
        assert!(all_day.get("time").is_none(), "{all_day}");
    }

    /// One job's change, with no list form: the same narrowness the reminders'
    /// own command has (Ruling 15's sibling rule for the calendar).
    #[test]
    fn one_change_is_one_event_and_two_verbs() {
        let change = CalendarChange {
            title: Some("Dentist, moved".into()),
            date: Some("2026-11-04".into()),
            time: Some("10:00".into()),
            ..Default::default()
        };
        assert_eq!(
            act_body("c0123456789", "update", Some(&change)).unwrap(),
            json!({"id": "c0123456789", "do": "update", "title": "Dentist, moved",
                   "date": "2026-11-04", "time": "10:00"})
        );
        assert_eq!(
            act_body("c0123456789", "delete", None).unwrap(),
            json!({"id": "c0123456789", "do": "delete"})
        );
        for action in ["delete_all", "clear_range", "add", "move"] {
            assert!(act_body("c0123456789", action, None).is_err(), "{action}");
        }
    }
}
