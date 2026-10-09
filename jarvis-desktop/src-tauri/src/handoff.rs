//! How long "Solve it here" stays on offer, for Settings (the owner's own
//! decision of 2026-10-08: "make this a setting for both options with 1 as the
//! default"; backend/jarvis_handoff_mode.py; docs/CAPTCHA-HANDOFF-DESIGN.md
//! section 5).
//!
//! ONE command, `handoff_mode`, Settings only:
//!  * "read" - the choice, its two names, the PC's own lines and whether a card
//!    is waiting. A read: never held on a stale link.
//!  * "set"  - "stop_early" is applied at once and is NEVER held (it only makes
//!    Jarvis do less); "keep_offering" raises ONE approval card on this PC,
//!    decided in the Jarvis bar with Windows Hello, and is held on a stale link.
//!
//! THIS APP NEVER PICTURES A BROWSER WINDOW. The live picture of the paused page
//! goes PC to the owner's own phone, and this settings window never asks for it
//! (tests/handoff.mjs checks the desktop names none of those routes). Only a
//! choice, a card state and fixed words pass through here.
use std::time::Duration;

use tauri::AppHandle;

use crate::look;

/// The verbs `handoff_mode` takes.
pub(crate) const ACTIONS: &[&str] = &["read", "set"];
/// The two choices. Must match `MODES` in backend/jarvis_handoff_mode.py, and
/// the phone's `Handoff.MODES`.
pub(crate) const MODES: &[&str] = &["stop_early", "keep_offering"];

pub(crate) const MISSING: &str = "This PC's Jarvis is missing this feature. In PowerShell on the \
     PC, in the Jarvis folder, run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis.";
const STALE_HELD: &str = "The connection to Jarvis is catching up, so keeping the hand-off on \
     offer for the full 15 minutes is held until it does - try again in a moment.";
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);
const PATH: &str = "/api/chatbot/handoff_mode";

/// The body of one verb, or why it is not one. Only one of the two choice names
/// goes in - never a picture, a page or a tap.
pub(crate) fn body(action: &str, mode: Option<&str>) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!("The hand-off setting cannot {action:?}"));
    }
    Ok(match action {
        "set" => {
            let mode = mode.unwrap_or("");
            if !MODES.contains(&mode) {
                return Err("Choose \"Stop early\" or \"Keep offering it\".".to_string());
            }
            serde_json::json!({ "mode": mode })
        }
        _ => serde_json::json!({}),
    })
}

/// The hand-off's own setting, for Settings. "read" gets it; "set" applies
/// "stop_early" at once and never holds it, while "keep_offering" raises ONE
/// approval card on this PC and is held on a stale link.
#[tauri::command]
pub async fn handoff_mode(
    app: AppHandle,
    action: String,
    mode: Option<String>,
) -> Result<serde_json::Value, String> {
    let body = body(&action, mode.as_deref())?;
    // Only the loosening waits for a fresh link: turning the setting back to
    // "Stop early" only ever makes Jarvis do less.
    if action == "set" && mode.as_deref() != Some("stop_early") && look::stale(&app) {
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
    fn the_verbs_carry_only_a_choice() {
        assert_eq!(body("read", None).unwrap(), json!({}));
        assert_eq!(
            body("set", Some("stop_early")).unwrap(),
            json!({ "mode": "stop_early" })
        );
        assert_eq!(
            body("set", Some("keep_offering")).unwrap(),
            json!({ "mode": "keep_offering" })
        );
        // One entry per line: rustfmt's own layout (2026-10-09). `cargo fmt
        // --check` is the rust job's first step, so this array being on one
        // line failed CI before `cargo check` ever ran.
        for bad in [
            "",
            "toggle",
            "on",
            "stop",
            "patient",
            "STOP_EARLY",
            "stop_early ",
        ] {
            assert!(body("set", Some(bad)).is_err(), "{bad:?}");
        }
        for verb in ACTIONS {
            if *verb != "set" {
                assert!(body(verb, None).is_ok(), "{verb}");
            }
        }
        for bad in ["", "read ", "READ", "picture", "frame", "input", "end"] {
            assert!(body(bad, None).is_err(), "{bad:?}");
        }
    }

    #[test]
    fn only_the_two_choices_are_taken() {
        assert_eq!(MODES.len(), 2);
        assert!(MODES.contains(&"stop_early"));
        assert!(MODES.contains(&"keep_offering"));
    }

    #[test]
    fn the_setting_has_a_path_of_its_own() {
        // The exact route, and that it is NOT one of the hand-off's own picture
        // or input routes, are checked where naming those is safe:
        // tests/handoff-mode.mjs and tests/handoff.mjs. Nothing here writes that
        // other path out, because check_parity.py reads this file and would read
        // it as a call.
        assert_eq!(PATH, "/api/chatbot/handoff_mode");
        assert!(PATH.ends_with("handoff_mode"));
    }

    #[test]
    fn the_words_say_what_happens_either_way() {
        assert!(MISSING.contains("apply-patches.ps1"));
        assert!(STALE_HELD.contains("held"));
        assert!(STALE_HELD.contains("15 minutes"));
    }
}
