//! Settings -> "Prompt coach" (the owner's request of 2026-10-08 and their
//! answers the same day; docs/PROMPT-COACH-DESIGN.md; backend
//! jarvis_prompt_coach.py; JARVIS-API.md section 119).
//!
//! Three commands, in two windows (permissions/surfaces.toml):
//!
//! Settings (`settings-surface`):
//!
//! * [`get_prompt_coach`] - `GET /api/prompt/coach`: whether the coach is on,
//!   in the PC's own words (LABEL, DETAIL, HEADING, BUTTON, SEND_MINE,
//!   SEND_SUGGESTION - jarvis_prompt_coach.py's constants, which this passes
//!   on as they are). A read, never held.
//! * [`set_prompt_coach`] - `POST /api/prompt/coach/setting {"enabled"}`: the
//!   switch itself, OFF by default.
//!
//! The Jarvis bar (`quickbar-surface`):
//!
//! * [`coach_prompt`] - `POST /api/prompt/coach {"text", "history"}`: criticise
//!   ONE prompt the owner is about to send - a score out of 10, up to four
//!   gaps, the questions it would have to ask, and a rewritten version. It
//!   SENDS NOTHING and decides nothing: the bar shows the critique, and only
//!   the owner's own press of "Send mine" or "Send the suggestion" sends a
//!   turn (main.js). The words and the history it carries are the box's own -
//!   the last few turns the bar was already going to re-send to the same local
//!   model - and nothing is kept by the PC (jarvis_prompt_coach.py: no chat
//!   history, no fact, no count).
//!
//! NONE OF THE THREE IS HELD ON A STALE LINK, and no approval card is raised
//! by any of them - unlike every other setting in this app that trusts more.
//! That is written down here because it must stay a decision and never become
//! an oversight (docs/PROMPT-COACH-DESIGN.md, choice B): nothing in this
//! feature opens a way out of the PC, takes an action or loosens a rule. It
//! reads words the chat is about to send to the same local model anyway, it
//! advises and acts on nothing, and it approves nothing. So this module never
//! consults the event stream (`stream::StreamState`), and every call applies at
//! once, whatever the link is doing. The setting's own words say the same thing
//! on screen.
//!
//! The switch is the master switch that decides whether the bar's button
//! exists at all: `prompt-coach-panel.js` hides it unless `get_prompt_coach`
//! says the coach is on.

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
/// A critique is one local model call over the question and the last few
/// turns - jarvis_prompt_coach.py's own `TIMEOUT_SECONDS` is 120 s, and it may
/// have to load the model first. This waits a little longer than the PC does,
/// so the PC's own sentence ("The model on this PC did not answer...") is what
/// the owner sees rather than this side giving up first.
const COACH_TIMEOUT: Duration = Duration::from_secs(150);

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

/// The critique's answer: the PC's own body on a 2xx, passed on exactly as it
/// came once it really carries the one thing the panel reads it for (a `coach`
/// object with a number `score` in it). [`PROMPT_COACH_MISSING`] from a PC
/// without the route, and the PC's own sentence (409: "the model did not
/// answer", "that is too short to coach", "The prompt coach is switched off.")
/// otherwise. A 2xx without a `coach` object is [`UNREADABLE`], never an empty
/// panel: a critique that cannot be read is not the same as one that says
/// nothing is wrong.
///
/// The score is NOT a gate and is not checked for a passing value - 1 out of 10
/// is passed on and shown like any other. Only its presence is required, so the
/// page never paints "1 out of 10" over a body that carried no score at all.
pub(crate) fn coach_prompt_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| {
                v.get("coach")
                    .is_some_and(|c| c.get("score").is_some_and(|s| s.is_number()))
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(PROMPT_COACH_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// "Coach this": `POST /api/prompt/coach {"text", "history"}`. One local model
/// call, nothing sent and nothing kept - see this module's note at the top.
///
/// `history` is the bar's own last few turns, each already shaped
/// `{"who": "owner"|"jarvis", "text": "..."}` (prompt-coach-panel.js caps how
/// many; the PC caps them again at `MAX_TURNS`). It is typed as JSON rather
/// than a Rust struct on purpose: this side only carries it, and anything the
/// PC would drop is dropped there (`_turns`), so nothing here has to agree with
/// it field for field.
#[tauri::command]
pub async fn coach_prompt(
    app: AppHandle,
    text: String,
    history: Vec<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(COACH_TIMEOUT))?
        .post(format!("{base}{PROMPT_COACH_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "text": text, "history": history }))
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    coach_prompt_answer(status, &body)
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
        change_answer, coach_answer, coach_prompt_answer, PROMPT_COACH_MISSING, PROMPT_COACH_PATH,
        SETTING_PATH,
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

    /// What `POST /api/prompt/coach` really answers: jarvis_prompt_coach.py's
    /// `handle_post`, forwarded by the route as `{"ok": true, "coach": ...}`.
    /// The critique inside is the shape `parse()` returns - score, clear,
    /// issues of what/why/fix, missing, suggestion.
    const CRITIQUE: &str = r#"{"ok": true, "coach": {"score": 4, "clear": false,
        "issues": [{"what": "No output shape", "why": "The answer could be prose or a list",
                    "fix": "Say: a table, one row per model."}],
        "missing": ["Which PC is this for?"],
        "suggestion": "Compare qwen3:8b and llama3.1:8b on my RTX 2080, as a table."}}"#;

    #[test]
    fn a_critique_is_passed_on_unchanged_and_its_route_is_the_agreed_one() {
        let whole: serde_json::Value = serde_json::from_str(CRITIQUE).unwrap();
        let got = coach_prompt_answer(200, CRITIQUE).unwrap();
        assert_eq!(got, whole, "not a word of the PC's answer is repainted");
        assert_eq!(got["coach"]["score"], 4);
        assert_eq!(got["coach"]["issues"][0]["what"], "No output shape");
        assert_eq!(got["coach"]["missing"][0], "Which PC is this for?");
        assert_eq!(
            got["coach"]["suggestion"],
            "Compare qwen3:8b and llama3.1:8b on my RTX 2080, as a table."
        );

        // A 1 out of 10 is not a gate: it is passed on exactly as it came.
        let one = coach_prompt_answer(
            200,
            r#"{"ok": true, "coach": {"score": 1, "clear": false, "issues": [],
                "missing": [], "suggestion": ""}}"#,
        )
        .unwrap();
        assert_eq!(one["coach"]["score"], 1);
        // ...and a critique that says the prompt is already fine comes back
        // whole too: an empty `issues` is a real answer, not a failure.
        let clear = coach_prompt_answer(
            200,
            r#"{"ok": true, "coach": {"score": 10, "clear": true, "issues": [],
                "missing": [], "suggestion": "Do the thing."}}"#,
        )
        .unwrap();
        assert_eq!(clear["coach"]["clear"], true);

        assert_eq!(PROMPT_COACH_PATH, "/api/prompt/coach");
    }

    #[test]
    fn a_refusal_from_the_coach_is_the_pcs_own_sentence() {
        // The coach is off, the question is too short, or the model did not
        // answer - all three are 409 with `error` in the PC's words.
        for said in [
            "The prompt coach is switched off.",
            "That is too short to coach - write a little more and try again.",
            "The model on this PC did not answer, so there is no coaching to show. \
             Nothing was sent anywhere.",
        ] {
            let body = serde_json::json!({ "ok": false, "error": said }).to_string();
            assert_eq!(coach_prompt_answer(409, &body).unwrap_err(), said);
        }
        // An older PC, both the way the GET route says it (503) and a missing
        // route (404).
        for code in [404u16, 503] {
            assert_eq!(
                coach_prompt_answer(code, r#"{"available": false}"#).unwrap_err(),
                PROMPT_COACH_MISSING
            );
        }
        assert!(coach_prompt_answer(401, r#"{"error": "bad or missing X-Jarvis-Token"}"#).is_err());
    }

    #[test]
    fn a_critique_this_side_cannot_read_is_never_an_empty_panel() {
        // "Nothing is wrong with your prompt" is a real answer with a score of
        // its own; a body with no critique at all is not, and is refused rather
        // than painted as one.
        assert!(coach_prompt_answer(200, "not json").is_err());
        assert!(coach_prompt_answer(200, r#"{"ok": true}"#).is_err());
        assert!(coach_prompt_answer(200, r#"{"ok": true, "coach": {}}"#).is_err());
        assert!(
            coach_prompt_answer(
                200,
                r#"{"ok": true, "coach": {"score": "4", "issues": []}}"#
            )
            .is_err(),
            "a score that is not a number is not a score"
        );
    }
}
