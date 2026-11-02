//! The to-do list's day carry-over, for Settings (2026-11-02; the owner's
//! choice of both modes, full daily rollover as the default; Gemini's ruling 8;
//! `backend/jarvis_schedule.py`; JARVIS-API section 179).
//!
//! ONE command, `todo_carryover`, Settings only, with two shapes:
//!
//!   `todo_carryover()` - the read. GET /api/schedule and hand back ONLY the
//!   two things this card draws: the mode in force (`todo_mode`) and the two
//!   modes in the PC's own words (`todo_modes`). A read, never held.
//!
//!   `todo_carryover({ mode })` - the one change. POST
//!   /api/schedule/act {"do": "todo_mode", "mode": ...}, which is the same
//!   method a spoken sentence runs through the settings registry
//!   (`jarvis_settings_registry.set_todo_carryover`), so a tap here and a
//!   sentence cannot disagree. Held on a stale link (rule 4), like every other
//!   write in this app.
//!
//! NO APPROVAL CARD EITHER WAY, and the PC decides that, not this command: the
//! change moves no item, deletes nothing, re-stamps no day and loosens no rule -
//! it only changes how the owner's own list is drawn. `created_date` is written
//! once when an item is created, so switching back and forth loses nothing.
//!
//! The mode is ONE value on the PC. This command never keeps a second copy.

use std::time::Duration;

use tauri::AppHandle;

use crate::look;

/// The two values the PC takes. Anything else is refused here as well, so a
/// page cannot send a mode the backend has never heard of.
pub(crate) const MODES: &[&str] = &["rollover", "day"];

/// The read and the write, exactly as `jarvis_schedule` serves them.
pub(crate) const READ_PATH: &str = "/api/schedule";
pub(crate) const WRITE_PATH: &str = "/api/schedule/act";

pub(crate) const MISSING: &str = "Your PC's Jarvis does not have the to-do list yet - \
     run apply-patches.ps1 on the PC.";

const STALE_HELD: &str = "The connection to Jarvis is catching up, so the to-do list's \
     mode is held until it does - try again in a moment.";

const WRITE_TIMEOUT: Duration = Duration::from_secs(10);

/// The body of one change: the verb and the one mode, and nothing else.
pub(crate) fn body(mode: &str) -> Result<serde_json::Value, String> {
    if !MODES.contains(&mode) {
        return Err(format!(
            "The to-do list is either \"Daily rollover\" or \"Day by day\", not {mode:?}. \
             Nothing was changed."
        ));
    }
    Ok(serde_json::json!({ "do": "todo_mode", "mode": mode }))
}

/// The two things the card draws, from the PC's own answer.
pub(crate) fn view(status: &serde_json::Value) -> serde_json::Value {
    serde_json::json!({
        "mode": status.get("todo_mode").cloned()
            .unwrap_or_else(|| serde_json::json!("rollover")),
        "modes": status.get("todo_modes").cloned()
            .unwrap_or_else(|| serde_json::json!([])),
    })
}

/// Read the mode, or change it. Settings only.
#[tauri::command]
pub async fn todo_carryover(
    app: AppHandle,
    mode: Option<String>,
) -> Result<serde_json::Value, String> {
    let Some(mode) = mode else {
        let status = look::get(&app, READ_PATH).await.map_err(|why| {
            if why == look::MISSING {
                MISSING.to_string()
            } else {
                why
            }
        })?;
        return Ok(view(&status));
    };
    let body = body(&mode)?;
    if look::stale(&app) {
        return Err(STALE_HELD.to_string());
    }
    look::post(&app, WRITE_PATH, body, WRITE_TIMEOUT)
        .await
        .map_err(|why| {
            if why == look::MISSING {
                MISSING.to_string()
            } else {
                why
            }
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_body_carries_the_one_verb_and_the_one_mode() {
        assert_eq!(
            body("rollover").unwrap(),
            json!({ "do": "todo_mode", "mode": "rollover" })
        );
        assert_eq!(
            body("day").unwrap(),
            json!({ "do": "todo_mode", "mode": "day" })
        );
        for bad in ["", "ROLLOVER", "Day", "day by day", "both", "none"] {
            assert!(body(bad).is_err(), "{bad:?}");
        }
    }

    #[test]
    fn the_read_hands_back_only_what_the_card_draws() {
        let answer = json!({
            "available": true,
            "todo": [{ "id": "s0123456789", "text": "buy milk" }],
            "todo_mode": "day",
            "todo_modes": [{ "value": "rollover", "label": "Daily rollover" },
                           { "value": "day", "label": "Day by day" }],
            "jobs": [],
        });
        let out = view(&answer);
        assert_eq!(out["mode"], json!("day"));
        assert_eq!(out["modes"].as_array().unwrap().len(), 2);
        // The card never receives the owner's items from this command.
        assert!(out.get("todo").is_none());
        // An older backend sends neither key: the default is rollover.
        assert_eq!(view(&json!({})), json!({ "mode": "rollover", "modes": [] }));
    }

    #[test]
    fn the_two_paths_are_the_scheduler_ones() {
        assert_eq!(READ_PATH, "/api/schedule");
        assert_eq!(WRITE_PATH, "/api/schedule/act");
        assert_eq!(MODES, &["rollover", "day"]);
    }
}
