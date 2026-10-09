//! Settings -> "Prompt coach" (the owner's request of 2026-10-08 and their
//! answers the same day; docs/PROMPT-COACH-DESIGN.md; backend
//! jarvis_prompt_coach.py; JARVIS-API.md section 119).
//!
//! Two commands, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_prompt_coach`] - `GET /api/prompt/coach`: whether the coach is on,
//!   in the PC's own words (LABEL, DETAIL, HEADING, BUTTON, SEND_MINE,
//!   SEND_SUGGESTION - jarvis_prompt_coach.py's constants, which this passes
//!   on as they are). A read, never held.
//! * [`set_prompt_coach`] - `POST /api/prompt/coach/setting {"enabled"}`: the
//!   switch itself, OFF by default.
//!
//! NEITHER DIRECTION IS HELD ON A STALE LINK, and no approval card is raised
//! in either direction - unlike every other setting in this app that trusts
//! more. That is written down here because it must stay a decision and never
//! become an oversight (docs/PROMPT-COACH-DESIGN.md, choice B): nothing in
//! this feature opens a way out of the PC, takes an action or loosens a rule.
//! It reads words the chat is about to send to the same local model anyway,
//! it advises and acts on nothing, and it approves nothing. So this module
//! never consults the event stream (`stream::StreamState`), and both
//! directions apply at once, whatever the link is doing. The setting's own
//! words say the same thing on screen.
//!
//! The "Coach this" button beside the box in the Jarvis bar, and the panel
//! that shows a critique, are a later piece of work: they belong to the bar
//! and send through their own commands. The switch below is the master switch
//! that decides whether that button exists at all.

use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const PROMPT_COACH_PATH: &str = "/api/prompt/coach";
const SETTING_PATH: &str = "/api/prompt/coach/setting";

/// What a backend without `jarvis_prompt_coach.py` is told. The phone says
/// the same, and so does this app's own copy of it
/// (`prompt-coach-settings.js`, `MISSING`), byte for byte.
pub(crate) const PROMPT_COACH_MISSING: &str = "Your PC's Jarvis cannot show the prompt \
     coach yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_prompt_coach`]'s reading of the answer: the PC's own body, passed on
/// exactly as it came, once it really carries the one thing the page reads it
/// for (`on`, a yes or no). `available: false` with [`PROMPT_COACH_MISSING`]
/// from a PC without the route.
pub(crate) fn coach_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("on").is_some_and(|o| o.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": PROMPT_COACH_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A change's answer: the PC's own body on a 2xx (it sends the same words
/// back), [`PROMPT_COACH_MISSING`] from a PC without the route, and the PC's
/// own sentence otherwise (409 "the setting could not be saved", 401, 503).
/// `on` is required as well as an object, one step stricter than
/// `asks_first::change_answer`: the page words its own line from this reply
/// (`"Prompt coach is on."` / `"is off."`), so a body without the yes-or-no
/// would have it claim a state the PC never named. It says so in words
/// instead, and the read that follows paints the truth.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object() && v.get("on").is_some_and(|o| o.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(PROMPT_COACH_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// Whether the prompt coach is on, in the PC's own words: `GET
/// /api/prompt/coach`. A read.
#[tauri::command]
pub async fn get_prompt_coach(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{PROMPT_COACH_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    coach_answer(status, &body)
}

/// The switch. BOTH directions apply at once, and neither asks for a card
/// (see this module's own note at the top): no stale-link check, on purpose.
#[tauri::command]
pub async fn set_prompt_coach(app: AppHandle, enabled: bool) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{SETTING_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "enabled": enabled }))
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    change_answer(status, &body)
}

#[cfg(test)]
mod tests {
    use super::{
        change_answer, coach_answer, PROMPT_COACH_MISSING, PROMPT_COACH_PATH, SETTING_PATH,
    };

    /// The PC's own answer, word for word (jarvis_prompt_coach.py's `status()`,
    /// which the route forwards). Nothing here repaints or renames a word of
    /// it - the app falls back to its own byte-identical copy only when a word
    /// is missing.
    const VIEW: &str = r#"{"ok": true, "on": false, "why": "", "label": "Prompt coach",
        "detail": "Off (the default): nothing is read and there is no Coach this button.",
        "heading": "Prompt coach", "button": "Coach this", "send_mine": "Send mine",
        "send_suggestion": "Send the suggestion"}"#;

    #[test]
    fn the_real_view_is_passed_on_unchanged_and_the_routes_are_the_agreed_ones() {
        let view: serde_json::Value = serde_json::from_str(VIEW).unwrap();
        let got = coach_answer(200, VIEW).unwrap();
        assert_eq!(got, view);
        assert_eq!(got["label"], "Prompt coach");
        assert_eq!(got["button"], "Coach this");
        assert_eq!(got["send_mine"], "Send mine");
        assert_eq!(got["send_suggestion"], "Send the suggestion");

        // The setting is a POST of exactly {"enabled": bool} to its own route.
        assert_eq!(PROMPT_COACH_PATH, "/api/prompt/coach");
        assert_eq!(SETTING_PATH, "/api/prompt/coach/setting");

        // Both directions of the switch come back the same way, and the app's
        // own line for an older PC is the one the page also holds.
        for on in ["true", "false"] {
            let body = format!(r#"{{"ok": true, "on": {on}, "why": ""}}"#);
            assert_eq!(
                change_answer(200, &body).unwrap()["on"].as_bool(),
                Some(on == "true")
            );
        }
        assert_eq!(
            PROMPT_COACH_MISSING,
            "Your PC's Jarvis cannot show the prompt coach yet - run apply-patches.ps1 on the PC."
        );
    }

    #[test]
    fn an_older_pc_says_so_and_nonsense_is_refused() {
        for code in [404u16, 503] {
            let got = coach_answer(code, r#"{"available": false}"#).unwrap();
            assert_eq!(got["available"], false);
            assert_eq!(got["why"], PROMPT_COACH_MISSING);
            assert_eq!(
                change_answer(code, r#"{"available": false}"#).unwrap_err(),
                PROMPT_COACH_MISSING
            );
        }
        // 200 with no yes-or-no in it is not something this page can paint,
        // and is never shown as "off" (which would be a claim the PC did not
        // make).
        assert!(coach_answer(200, "not json").is_err());
        assert!(coach_answer(200, r#"{"ok": true}"#).is_err());
        assert!(coach_answer(200, r#"{"on": "yes"}"#).is_err());
    }

    #[test]
    fn a_refusal_is_the_pcs_own_sentence() {
        let refused = change_answer(
            409,
            r#"{"ok": false, "error": "The prompt coach's setting could not be saved (OSError)."}"#,
        );
        assert_eq!(
            refused.unwrap_err(),
            "The prompt coach's setting could not be saved (OSError)."
        );
        assert!(coach_answer(401, r#"{"error": "bad or missing X-Jarvis-Token"}"#).is_err());
    }
}
