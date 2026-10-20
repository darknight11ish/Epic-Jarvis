//! The searchable recordings and videos index, for Settings (F5 S2, owner
//! decision of 2026-10-19; backend/jarvis_media_index.py, the drop-in folder
//! plugins/ready/media-index/; JARVIS-API section 149).
//!
//! ONE command, `media_index`, Settings only. Its four verbs are:
//!
//! "read" - the switch, the stored counts, how many recordings are still
//! waiting, and the PC's own disclosure words. A read.
//!
//! "on" - ask to keep readable words from recordings again. That raises ONE
//! normal approval card on this PC and changes nothing until a person says
//! yes; held on a stale link (rule 4).
//!
//! "off" - at once, and never held. It also takes back a waiting ON card.
//!
//! "delete" - THE ONE DELETE: removes every stored word and the index file
//! itself. It never touches a recording, and it is never held.
//!
//! THE POST CARRIES ONE BOOLEAN / ONE ACTION AND NOTHING ELSE. The PC's route
//! calls the module's own `request_enabled()` for the switch, so this command
//! cannot flip it without the approval card; Delete removes stored words only.
//!
//! THIS APP NEVER SEES THE WORDS. The index lives on the PC; this is a switch
//! position, a few counts, and the PC's own disclosure sentence.

use std::time::Duration;

use tauri::AppHandle;

use crate::look;

/// The verbs `media_index` takes.
pub(crate) const ACTIONS: &[&str] = &["read", "on", "off", "delete"];

pub(crate) const MISSING: &str = "This PC's Jarvis does not have searchable recordings yet. \
     In PowerShell on the PC, in the Jarvis folder, run: .\\scripts\\add-plugin.ps1 -Name \
     media-index . Then restart Jarvis.";
const STALE_HELD: &str = "The connection to Jarvis is catching up, so turning searchable \
     recordings back on is held until it does - try again in a moment.";
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);
const PATH: &str = "/api/media-index";

/// The body of one verb, or why it is not one. Only the switch position or
/// the delete action goes in, and nothing else at all.
pub(crate) fn body(action: &str) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!(
            "The searchable recordings setting cannot {action:?}"
        ));
    }
    Ok(match action {
        "on" => serde_json::json!({ "enabled": true }),
        "off" => serde_json::json!({ "enabled": false }),
        "delete" => serde_json::json!({ "action": "delete" }),
        _ => serde_json::json!({}),
    })
}

/// The switch and the one Delete, for Settings.
#[tauri::command]
pub async fn media_index(app: AppHandle, action: String) -> Result<serde_json::Value, String> {
    let body = body(&action)?;
    if action == "on" && look::stale(&app) {
        return Err(STALE_HELD.to_string());
    }
    let out = if action == "read" {
        look::get(&app, PATH).await
    } else {
        look::post(&app, PATH, body, WRITE_TIMEOUT).await
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
    fn the_verbs_carry_only_the_switch_or_the_one_delete() {
        assert_eq!(body("read").unwrap(), json!({}));
        assert_eq!(body("on").unwrap(), json!({ "enabled": true }));
        assert_eq!(body("off").unwrap(), json!({ "enabled": false }));
        assert_eq!(body("delete").unwrap(), json!({ "action": "delete" }));
        for bad in [
            "",
            "toggle",
            "enable",
            "delete all",
            "path",
            "read ",
            "READ",
        ] {
            assert!(body(bad).is_err(), "{bad:?}");
        }
        for verb in ACTIONS {
            assert!(body(verb).is_ok(), "{verb}");
        }
    }

    #[test]
    fn every_verb_names_the_same_route_and_delete_carries_no_choice() {
        assert_eq!(PATH, "/api/media-index");
        assert!(
            ACTIONS.contains(&"read")
                && ACTIONS.contains(&"on")
                && ACTIONS.contains(&"off")
                && ACTIONS.contains(&"delete")
        );
        // The one Delete has no path/choice field: it removes everything the
        // route claims (the stored words and the index file).
        assert_eq!(body("delete").unwrap().as_object().unwrap().len(), 1);
    }
}
