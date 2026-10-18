//! The data and maths sandbox's own switch, for Settings (LM-1C, 2026-10-18;
//! backend/jarvis_sandbox_exec.py, the drop-in folder plugins/ready/sandbox/;
//! JARVIS-API section 193).
//!
//! ONE command, `sandbox_exec`, Settings only:
//!  * "read" - the setting: on or off, whether a card is waiting, and the PC's
//!    own line about what last happened. A read.
//!  * "on"   - asks for the sandbox to be offered to the AI model. That raises
//!    ONE normal approval card on this PC and changes nothing until a person
//!    says yes; held on a stale link (rule 4).
//!  * "off"  - at once, and never held. It also takes back a waiting ON card.
//!
//! THE POST CARRIES ONE BOOLEAN AND NOTHING ELSE. The PC's route calls the
//! module's own request_enabled(), the same function the chat/voice phrase
//! uses, so this command cannot flip the switch without the approval card.
//!
//! THIS APP NEVER RUNS A SCRIPT FOR IT. The sandbox runs on the PC, and every
//! actual run is decided there under the agent's own gate actions with the
//! module's refusals (no network, no file writes, only the files the owner
//! listed, time/output/memory caps) unchanged.

use std::time::Duration;

use tauri::AppHandle;

use crate::look;

/// The verbs `sandbox_exec` takes.
pub(crate) const ACTIONS: &[&str] = &["read", "on", "off"];

pub(crate) const MISSING: &str = "This PC's Jarvis does not have the data sandbox switch yet. \
     In PowerShell on the PC, in the Jarvis folder, run: .\\scripts\\add-plugin.ps1 -Name sandbox \
     . Then restart Jarvis.";
const STALE_HELD: &str = "The connection to Jarvis is catching up, so turning on the data \
     sandbox is held until it does - try again in a moment.";
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);
const PATH: &str = "/api/sandbox";

/// The body of one verb, or why it is not one. Only `{"enabled": bool}` goes
/// in on a change, and nothing else at all.
pub(crate) fn body(action: &str) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!("The data sandbox setting cannot {action:?}"));
    }
    Ok(match action {
        "on" => serde_json::json!({ "enabled": true }),
        "off" => serde_json::json!({ "enabled": false }),
        _ => serde_json::json!({}),
    })
}

/// The switch, for Settings. "read" gets it; "on" raises ONE approval card on
/// this PC (held on a stale link); "off" is at once and never held.
#[tauri::command]
pub async fn sandbox_exec(app: AppHandle, action: String) -> Result<serde_json::Value, String> {
    let body = body(&action)?;
    if action == "on" && look::stale(&app) {
        return Err(STALE_HELD.to_string());
    }
    let out = if action == "read" {
        look::get(&app, PATH).await
    } else {
        look::post(&app, PATH, body, WRITE_TIMEOUT).await
    };
    // A PC without the drop-in folder answers 404: say which one command puts
    // it back rather than an HTTP code.
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
    fn the_verbs_carry_only_the_switch_position() {
        assert_eq!(body("read").unwrap(), json!({}));
        assert_eq!(body("on").unwrap(), json!({ "enabled": true }));
        assert_eq!(body("off").unwrap(), json!({ "enabled": false }));
        for bad in ["", "toggle", "enable", "on ", "ON", "set", "write", "run"] {
            assert!(body(bad).is_err(), "{bad:?}");
        }
        for verb in ACTIONS {
            assert!(body(verb).is_ok(), "{verb}");
        }
    }

    #[test]
    fn every_verb_names_the_same_route() {
        assert_eq!(PATH, "/api/sandbox");
        assert!(ACTIONS.contains(&"read") && ACTIONS.contains(&"on") && ACTIONS.contains(&"off"));
    }
}
