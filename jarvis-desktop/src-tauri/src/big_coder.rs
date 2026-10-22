//! The big coding model (the 30B coder), for Settings (R7-era gap; backend
//! `jarvis_big_coder.py`, route `/api/big-coder` added by
//! `backend/big-coder.patch`, JARVIS-API section 126).
//!
//! WHY THIS COMMAND EXISTS. The owner's requirement of 2026-10-22: every
//! feature must be findable and adjustable in Settings, not only by typing at
//! Jarvis. `big_coder` was a real spoken setting (a BoolSetting with a state
//! reader) and a real PC route, but the desktop had no control for it at all.
//! This is that control's only path, and it is the SAME path the typed sentence
//! takes: one boolean over the existing route, which raises the EXISTING
//! approval card on ON and changes nothing on OFF.
//!
//! THE SWITCH ONLY - `read` / `on` / `off`. The route can also start and stop
//! the model, and this command deliberately cannot: starting the 30B coder
//! pauses Jarvis's other models, which is the model's own separate decision.
//! The body sent is ONE boolean and nothing else; an unknown verb is refused
//! before a request is made.
//!
//! ON IS ONE CARD AND IS HELD WHILE THE LINK IS STALE (rule 4). The PC's own
//! `set_enabled` calls `jarvis_gate.check` and waits for the person to decide
//! the card, so this command's budget for ON is twenty minutes - a person may
//! be away from the screen - the same shape File history's Restore uses. OFF is
//! immediate and never held.
//!
//! NOTHING HERE APPROVES ANYTHING. It has no decision route and no way to
//! answer a card; the card is decided in the Jarvis bar / HUD / phone queue,
//! like every other card.

use std::time::Duration;

use tauri::AppHandle;

use crate::look;

/// The verbs `big_coder` takes. Everything else is refused before a request.
pub(crate) const ACTIONS: &[&str; 3] = &["read", "on", "off"];

/// The PC's route, literal, so a page cannot build one.
pub(crate) const PATH: &str = "/api/big-coder";

/// A PC whose backend predates the big coding model's route (the same sentence
/// shape the settings page uses for other missing modules).
pub(crate) const MISSING: &str = "Your PC's Jarvis does not have the big coding model yet. \
     On the PC, in the Jarvis folder, run: .\\scripts\\apply-patches.ps1. Then restart Jarvis.";

/// Turning it ON raises a card, so it waits for a live link (rule 4).
const STALE_HELD: &str = "The connection to Jarvis is catching up, so turning the big coding \
     model on is held until it does - try again in a moment.";

/// OFF is one write with no card; ten seconds is plenty.
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);

/// ON waits for a PERSON: the PC raises the `change_own_config` card and its
/// `jarvis_gate.check` answers once the card is decided. Twenty minutes leaves
/// that budget room, exactly like File history's restore.
const ON_WAIT: Duration = Duration::from_secs(20 * 60);

/// The body of one verb, or why it is not one. Only the switch position goes
/// in - never a start/stop action, never a model name, nothing else at all.
pub(crate) fn body(action: &str) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!("The big coding model setting cannot {action:?}"));
    }
    Ok(match action {
        "on" => serde_json::json!({ "on": true }),
        "off" => serde_json::json!({ "on": false }),
        _ => serde_json::json!({}),
    })
}

/// Is this attempt held because the link is stale? Only turning it ON loosens
/// anything and raises a card; turning it off is never held.
pub(crate) fn held(action: &str, stale: bool) -> bool {
    action == "on" && stale
}

/// The big coding model's switch, for Settings.
#[tauri::command]
pub async fn big_coder(app: AppHandle, action: String) -> Result<serde_json::Value, String> {
    let body = body(&action)?;
    if held(&action, look::stale(&app)) {
        return Err(STALE_HELD.to_string());
    }
    let out = match action.as_str() {
        "read" => look::get(&app, PATH).await,
        "on" => look::post(&app, PATH, body, ON_WAIT).await,
        _ => look::post(&app, PATH, body, WRITE_TIMEOUT).await,
    };
    out.map_err(|why| {
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
    fn the_verbs_carry_only_the_switch() {
        assert_eq!(body("read").unwrap(), json!({}));
        assert_eq!(body("on").unwrap(), json!({ "on": true }));
        assert_eq!(body("off").unwrap(), json!({ "on": false }));
    }

    #[test]
    fn starting_and_stopping_the_model_are_not_settings_verbs() {
        // The route can start/stop the 30B coder; this Settings control must
        // not, because starting pauses Jarvis's own models. A start request
        // through this command is a bug, so it is refused before any send.
        for verb in ["start", "stop", "run", "", "ON"] {
            let err = body(verb).expect_err(verb);
            assert!(err.contains("cannot"), "{verb}: {err}");
        }
        assert_eq!(ACTIONS.len(), 3, "the command's whole vocabulary");
    }

    #[test]
    fn only_turning_it_on_is_held_by_a_stale_link() {
        assert!(held("on", true));
        assert!(!held("on", false));
        assert!(!held("off", true), "OFF must never be held");
        assert!(!held("read", true));
    }

    #[test]
    fn turning_it_on_waits_for_a_person_and_off_does_not() {
        // A person may take minutes to answer the one card; OFF is immediate.
        assert!(ON_WAIT >= Duration::from_secs(15 * 60));
        assert!(WRITE_TIMEOUT < ON_WAIT);
    }
}
