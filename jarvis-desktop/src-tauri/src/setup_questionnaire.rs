//! The setup questionnaire, for Settings (JARVIS-API section 147; the PC's
//! module is `backend/jarvis_setup.py`, and `backend/setup.patch` installs its
//! three routes: `GET /api/setup`, `POST /api/setup/plan`,
//! `POST /api/setup/apply`).
//!
//! ONE command, `setup_questionnaire`, with three verbs and no fourth:
//!
//! * `"read"` - `GET /api/setup`: the fourteen questions, the current values,
//!   the last accepted answers and outcomes, and how long a card may wait. A
//!   read; no stale-link hold.
//! * `"plan"` - `POST /api/setup/plan {"answers": {...}}`: READ-ONLY on the
//!   PC. The module writes nothing and raises no card for it, so this command
//!   sends only the answers object - never `confirm`. A stale link does not
//!   hold it, because it changes nothing.
//! * `"apply"` - `POST /api/setup/apply {"answers": {...}, "confirm": true}`:
//!   the one write. It refuses unless the `confirm` argument is exactly
//!   `true`, so an accidental or invented call cannot change anything; the
//!   body it builds carries `confirm: true` and nothing else beside the
//!   answers. It is held while the event stream is stale (rule 4) before
//!   anything is sent.
//!
//! NOTHING HERE DECIDES, APPROVES OR RETRIES. The PC's module calls the
//! EXISTING setters (the same functions the matching Settings controls call):
//! a loosening change raises its own existing approval card, one at a time,
//! and waits for it. The answer is handed back unchanged, so the page draws
//! the PC's own outcomes - a card still waiting is `asked-no-answer`, not a
//! failure and not a success.
//!
//! The apply can take a long time: each carded change waits for a person, and
//! the PC's patience is `card_wait_s` (300 s by default, up to 900 s per
//! card). The command's timeout is therefore an hour, and the page's own
//! budget is longer again (`setup-bridge.js`), so a real card can still be
//! answered before either gives up. Giving up never means "it failed": the
//! page re-reads what the PC saved (`last_outcomes`) and says so.
//!
//! Settings only, through `permissions/surfaces.toml`'s `setup-questionnaire`
//! set. The page holds no token and names no route.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// The three routes the PC's module installs.
pub(crate) const PATH: &str = "/api/setup";
pub(crate) const PLAN_PATH: &str = "/api/setup/plan";
pub(crate) const APPLY_PATH: &str = "/api/setup/apply";

/// The verbs this command takes. Anything else is refused before the network.
pub(crate) const ACTIONS: &[&str] = &["read", "plan", "apply"];

/// What an older backend is told to do about it.
const UPDATE_WORDS: &str = "This PC's Jarvis does not have the setup questionnaire yet. \
     In PowerShell on the PC, in the Jarvis folder, run: .\\scripts\\apply-patches.ps1 . \
     Then restart Jarvis and open this again.";

/// The reading and the plan are quick. The plan walks every answer, so it gets
/// twice the read's time.
const READ_TIMEOUT: Duration = Duration::from_secs(15);
const PLAN_TIMEOUT: Duration = Duration::from_secs(30);

/// The apply works through changes one at a time, waiting on each existing
/// approval card. The gate may wait 900 s on one card alone, and a full pass
/// can hold several, so an hour is not generous - it is the smallest timeout
/// that does not claim a real pass failed. The page's budget is longer again.
const APPLY_TIMEOUT: Duration = Duration::from_secs(3_600);

/// A missing route, or a PC that answers the route with its own "not here"
/// 503.
fn missing(code: u16, body: &str) -> bool {
    if code == 404 || code == 501 {
        return true;
    }
    code == 503
        && serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
            == Some(false)
}

/// The PC's answer: a 2xx JSON object passed on unchanged; a missing route in
/// the page's own words; everything else as the backend's own sentence (with
/// its HTTP code when it sent none).
pub(crate) fn answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|value| value.is_object())
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if missing(status, body) {
        return Err(UPDATE_WORDS.to_string());
    }
    Err(backend_refusal(status, body))
}

/// The answers object, or why it is unusable. Only a JSON object ever goes to
/// the PC; an array, a string or a number is refused before the network.
fn answers_object(
    answers: Option<&serde_json::Value>,
    allow_empty: bool,
) -> Result<serde_json::Value, String> {
    let value = answers.cloned().unwrap_or_else(|| serde_json::json!({}));
    let object = value.as_object().ok_or_else(|| {
        "The answers must be one JSON object, like {\"talk_style\": \"warm\"}.".to_string()
    })?;
    if !allow_empty && object.is_empty() {
        return Err("Nothing was changed. Choose at least one answer first.".to_string());
    }
    Ok(value)
}

/// `POST /api/setup/plan`'s body: the answers, and NOTHING else. There is no
/// `confirm` field in a plan, so a plan can never change a setting.
pub(crate) fn plan_body(answers: Option<&serde_json::Value>) -> Result<serde_json::Value, String> {
    let answers = answers_object(answers, true)?;
    Ok(serde_json::json!({ "answers": answers }))
}

/// `POST /api/setup/apply`'s body: the answers and `confirm: true`.
///
/// The confirm is a parameter and must be the boolean `true`; a missing, false
/// or non-boolean value refuses here, in the app, as well as on the PC. That
/// is deliberate defence in depth: the route refuses without it, and this
/// command cannot build a body without it either.
pub(crate) fn apply_body(
    answers: Option<&serde_json::Value>,
    confirm: Option<bool>,
) -> Result<serde_json::Value, String> {
    if confirm != Some(true) {
        return Err("Nothing was changed. Send confirm: true to apply these settings.".to_string());
    }
    let answers = answers_object(answers, false)?;
    Ok(serde_json::json!({ "answers": answers, "confirm": true }))
}

async fn get(app: &AppHandle, path: &str) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    answer(status, &body)
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    timeout: Duration,
) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(timeout))?
        .post(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    answer(status, &text)
}

/// The questionnaire's three verbs, for Settings. See this module's docstring.
#[tauri::command]
pub async fn setup_questionnaire(
    app: AppHandle,
    action: String,
    answers: Option<serde_json::Value>,
    confirm: Option<bool>,
) -> Result<serde_json::Value, String> {
    // The four-verb guard: a page cannot name a verb this command does not
    // send, and it is refused before any body is built or the network touched.
    let verb = action.as_str();
    if !ACTIONS.contains(&verb) {
        return Err(format!(
            "The setup questionnaire cannot {verb:?}. It can read, plan or apply."
        ));
    }
    match verb {
        "read" => get(&app, PATH).await,
        "plan" => {
            let body = plan_body(answers.as_ref())?;
            post(&app, PLAN_PATH, body, PLAN_TIMEOUT).await
        }
        // The only verb left once the guard above has passed: apply.
        _ => {
            let body = apply_body(answers.as_ref(), confirm)?;
            // Rule 4: a change to settings is never sent while the event
            // stream is stale. The plan above is not held - it changes nothing.
            if app.state::<crate::stream::StreamState>().link().stale {
                return Err(
                    "The connection to Jarvis is catching up. Applying your answers \
                            waits until it is back."
                        .to_string(),
                );
            }
            post(&app, APPLY_PATH, body, APPLY_TIMEOUT).await
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn answers() -> serde_json::Value {
        json!({ "talk_style": "warm", "humour": "on" })
    }

    #[test]
    fn the_verbs_are_the_three_routes_and_no_others() {
        assert_eq!(PATH, "/api/setup");
        assert_eq!(PLAN_PATH, "/api/setup/plan");
        assert_eq!(APPLY_PATH, "/api/setup/apply");
        assert_eq!(ACTIONS, &["read", "plan", "apply"]);
        for verb in ACTIONS {
            assert!(
                ["read", "plan", "apply"].contains(verb),
                "{verb} is not a route this command sends"
            );
        }
        // The command refuses a fourth verb before anything is sent.
        assert!(!ACTIONS.contains(&"approve"));
        assert!(!ACTIONS.contains(&"apply_all"));
        assert!(!ACTIONS.contains(&"set"));
    }

    #[test]
    fn a_plan_carries_the_answers_and_never_confirm() {
        let body = plan_body(Some(&answers())).expect("plan body");
        assert_eq!(body, json!({ "answers": answers() }));
        let keys: Vec<&str> = body
            .as_object()
            .expect("object")
            .keys()
            .map(String::as_str)
            .collect();
        assert_eq!(keys, vec!["answers"]);
        assert!(!body.to_string().contains("confirm"));
        // An empty answers object is a legal plan: it changes nothing.
        assert_eq!(
            plan_body(Some(&json!({}))).expect("empty plan"),
            json!({ "answers": {} }),
        );
        // No answers at all is the same empty plan, not an error.
        assert_eq!(
            plan_body(None).expect("no answers"),
            json!({ "answers": {} })
        );
    }

    #[test]
    fn an_apply_refuses_unless_confirm_is_exactly_true() {
        for bad in [None, Some(false)] {
            let err = apply_body(Some(&answers()), bad).expect_err("no confirm");
            assert!(err.to_lowercase().contains("confirm"), "{err}");
            assert!(err.to_lowercase().contains("nothing was changed"), "{err}");
        }
        let body = apply_body(Some(&answers()), Some(true)).expect("apply body");
        assert_eq!(body, json!({ "answers": answers(), "confirm": true }));
        let keys: Vec<&str> = body
            .as_object()
            .expect("object")
            .keys()
            .map(String::as_str)
            .collect();
        assert_eq!(keys, vec!["answers", "confirm"]);
        assert_eq!(body["confirm"], json!(true));
    }

    #[test]
    fn only_a_json_object_of_answers_ever_reaches_the_pc() {
        for bad in [
            json!("warm"),
            json!([["talk_style", "warm"]]),
            json!(7),
            json!(null),
        ] {
            assert!(plan_body(Some(&bad)).is_err(), "{bad}");
            assert!(apply_body(Some(&bad), Some(true)).is_err(), "{bad}");
        }
        assert!(
            apply_body(Some(&json!({})), Some(true)).is_err(),
            "empty apply"
        );
        assert!(apply_body(None, Some(true)).is_err(), "no answers at all");
    }

    #[test]
    fn the_pcs_answer_is_passed_on_and_a_refusal_keeps_its_own_words() {
        let body = r#"{"ok":true,"changes":[],"summary":[],"skipped":[]}"#;
        assert_eq!(
            answer(200, body).expect("a real answer"),
            serde_json::from_str::<serde_json::Value>(body).unwrap(),
        );
        // A 2xx that is not an object is not a plan to guess at.
        assert!(answer(200, "[]").is_err());
        assert!(answer(200, "not json").is_err());

        // A refusal is the backend's own sentence, not a generic failure.
        let refusal = answer(
            400,
            r#"{"ok":false,"confirmed":false,"error":"Nothing was changed. Send confirm: true to apply these settings."}"#,
        )
        .unwrap_err();
        assert!(refusal.contains("Nothing was changed"), "{refusal}");

        // A backend without the route says how to get it.
        assert_eq!(answer(404, "{}").unwrap_err(), UPDATE_WORDS);
        assert_eq!(
            answer(503, r#"{"available":false}"#).unwrap_err(),
            UPDATE_WORDS,
        );
    }

    #[test]
    fn the_apply_timeout_outlasts_several_cards_and_the_page_outlasts_it() {
        // The PC's approval gate may wait 900 s on ONE card; a full pass can
        // hold several, so the command must not give up before a real card can
        // still be answered.
        assert!(APPLY_TIMEOUT > Duration::from_secs(900));
        assert!(APPLY_TIMEOUT >= Duration::from_secs(3_600));
        assert!(APPLY_TIMEOUT > PLAN_TIMEOUT);
        assert!(PLAN_TIMEOUT > READ_TIMEOUT);
        // `setup-bridge.js` sets APPLY_BUDGET_MS above this; the desktop suite
        // reads both numbers and pins the order.
    }
}
