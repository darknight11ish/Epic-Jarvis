//! The headless browser (Obscura) setting, for Settings (the owner's decision
//! of 2026-09-29; backend/jarvis_browser_engine.py and jarvis_obscura.py;
//! JARVIS-API section 97).
//!
//! ONE command, `browser_engine`, Settings only:
//!  * "read"  - the setting: on or off, which browser Jarvis uses by default,
//!    the install status, and the one PowerShell line that downloads one named
//!    release of Obscura and prints its checksums (it does not run it). A read.
//!  * "on"    - asks for the headless browser to be turned on. That raises ONE
//!    approval card on this PC and changes nothing until a person says yes;
//!    held on a stale link (rule 4).
//!  * "off"   - at once, and never held. It also stops the program.
//!  * "mode"  - which browser Jarvis picks by default: "auto", "visible" or
//!    "headless". At once, no card (it only chooses between two browsers
//!    that each still ask on every plan).
//!
//! THIS APP NEVER RUNS A BROWSER FOR IT. Obscura runs on the PC's backend, and
//! every page it opens, click and box it fills is still its own plan card in
//! the Jarvis bar, exactly as for the visible browser. Nothing from a web page
//! passes through here: only a switch position, a mode and fixed words.

use std::time::Duration;

use tauri::AppHandle;

use crate::look;

/// The verbs `browser_engine` takes.
pub(crate) const ACTIONS: &[&str] = &["read", "on", "off", "mode"];
/// The modes Jarvis's default can be. Must match `MODES` in
/// backend/jarvis_browser_engine.py.
pub(crate) const MODES: &[&str] = &["auto", "visible", "headless"];

pub(crate) const MISSING: &str = "This PC's Jarvis does not have the headless browser yet. Run \
     scripts\\apply-patches.ps1 on the PC to add it.";
const STALE_HELD: &str = "The connection to Jarvis is catching up, so turning on the headless \
     browser is held until it does - try again in a moment.";
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);
const PATH: &str = "/api/browser/engine";

/// The body of one verb, or why it is not one. Only a switch position or one
/// of the three mode names goes in - nothing else.
pub(crate) fn body(action: &str, mode: Option<&str>) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!("The headless browser setting cannot {action:?}"));
    }
    Ok(match action {
        "on" => serde_json::json!({ "obscura": true }),
        "off" => serde_json::json!({ "obscura": false }),
        "mode" => {
            let mode = mode.unwrap_or("");
            if !MODES.contains(&mode) {
                return Err("Choose Automatic, Visible or Headless.".to_string());
            }
            serde_json::json!({ "mode": mode })
        }
        _ => serde_json::json!({}),
    })
}

/// The headless browser's switch and default, for Settings. "read" gets the
/// setting; "on" raises ONE approval card on this PC and "mode" changes the
/// default at once (both held on a stale link); "off" is at once and never held.
#[tauri::command]
pub async fn browser_engine(
    app: AppHandle,
    action: String,
    mode: Option<String>,
) -> Result<serde_json::Value, String> {
    let body = body(&action, mode.as_deref())?;
    if (action == "on" || action == "mode") && look::stale(&app) {
        return Err(STALE_HELD.to_string());
    }
    let out = if action == "read" {
        look::get(&app, PATH).await
    } else {
        look::post(&app, PATH, body, WRITE_TIMEOUT).await
    };
    // A PC without this route answers 404: say which feature is missing.
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
    fn the_verbs_carry_only_a_switch_position_or_a_mode() {
        assert_eq!(body("read", None).unwrap(), json!({}));
        assert_eq!(body("on", None).unwrap(), json!({ "obscura": true }));
        assert_eq!(body("off", None).unwrap(), json!({ "obscura": false }));
        assert_eq!(
            body("mode", Some("headless")).unwrap(),
            json!({ "mode": "headless" })
        );
        for bad in [
            "", "toggle", "enable", "on ", "ON", "install", "download", "proxy",
        ] {
            assert!(body(bad, None).is_err(), "{bad:?}");
        }
        for verb in ACTIONS {
            if *verb != "mode" {
                assert!(body(verb, None).is_ok(), "{verb}");
            }
        }
    }

    #[test]
    fn only_the_three_modes_are_taken() {
        for good in MODES {
            assert!(body("mode", Some(good)).is_ok(), "{good}");
        }
        for bad in ["", "Auto", "stealth", "headless ", "proxy", "auto,visible"] {
            assert!(body("mode", Some(bad)).is_err(), "{bad:?}");
        }
        assert!(body("mode", None).is_err());
    }
}
