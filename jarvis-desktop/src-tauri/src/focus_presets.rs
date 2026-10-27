//! Focus presets on the PC (backend/jarvis_presets.py, JARVIS-API section 128's
//! successor, PRs #603/#611): the five presets, the hardware block and the ONE
//! approval-gated apply.
//!
//! Three commands, granted to the quickbar, Settings and the HUD:
//!
//! * [`get_focus_presets`] - `GET /api/work`, passed on as it is. The route is
//!   the existing work route; a backend that still answers the old five-setup
//!   shape is reported as needing an update, never guessed at.
//! * [`apply_focus_preset`] - `POST /api/work/apply {"preset": "<id>"}`, with an
//!   OPTIONAL `provider` for the Presets menu's Cloud row (2026-10-27: picking
//!   an API service is the same apply with one more field, never a second
//!   route). This approves nothing itself: the backend starts the named lane on
//!   demand and raises the ONE existing `switch_model` ask card. A stale link is
//!   refused before anything is sent (rule 4), like every other card-raising
//!   write.
//! * [`hud_cloud_escalate`] - `POST /api/work/cloud-escalate {"on": true|false}`:
//!   the HUD Presets menu's "Escalate to the cloud when the work is too complex"
//!   switch. ONE boolean, and the PC decides: ON is a loosening and the PC
//!   raises its ONE `change_own_config` card, OFF is instant. The page holds no
//!   token, so this exists rather than a page POST - and it is deliberately its
//!   own narrow command, not a grant of `set_manner`/the Settings window.
//!
//! Both answers are the PC's own: a 2xx JSON object is handed on unchanged;
//! a refusal is the backend's own `error`/`message` sentence (or a plain line
//! carrying its HTTP code when the backend sent none). No token is logged or
//! put in an error, and every request carries `X-Jarvis-Token` through
//! [`jarvis_headers`], with `X-Jarvis-Client: hud`.
//!
//! The app-side wiring is why `focus-presets.js` may now set
//! `APPLY_BRIDGE_WIRED` to true: before this module, the contract could
//! advertise `/api/work/apply` while no Tauri command existed to send it.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// `GET` the presets; the apply POST sits under it.
pub(crate) const FOCUS_PRESETS_PATH: &str = "/api/work";
pub(crate) const FOCUS_PRESETS_APPLY_PATH: &str = "/api/work/apply";
/// The HUD's own escalate switch (2026-10-27): one boolean, one POST.
pub(crate) const CLOUD_ESCALATE_PATH: &str = "/api/work/cloud-escalate";

/// What an older backend is told to do about it.
const PRESETS_UPDATE: &str = "This PC's Jarvis does not have the focus presets yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// The same advice for a backend that has no escalate switch yet.
const CLOUD_ESCALATE_MISSING: &str = "This PC's Jarvis does not have the cloud \
     escalation switch yet. Update the backend by running apply-patches.ps1, then try again.";

/// The words while the event stream is stale. Applying can change the chat lane,
/// so it is held until the link is live again.
const STALE: &str = "The connection to Jarvis is catching up, so nothing can be applied \
                     until it does.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// The apply waits on the PC's switch_model approval card. The gate may wait up to
/// its default 900 s; 1,200 s leaves room for the lane start, the switch and the
/// response. The JS budget is 1,250 s, a little longer again.
const APPLY_TIMEOUT: Duration = Duration::from_secs(1_200);

/// Is a 404/503 "this backend has no focus-presets contract yet"? A 404, or the
/// route's own 503 `{"available": false}`. A real refusal keeps its sentence.
fn missing(code: u16, body: &str) -> bool {
    if code == 404 {
        return true;
    }
    code == 503
        && serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
            == Some(false)
}

/// [`get_focus_presets`]'s reading of the answer, on its own so it is testable.
/// Only the object shape matters here: `presets` must be the list the contract
/// promises. A 200 without it is an older `/api/work` answer (the five setups),
/// not a preset list to invent words for.
pub(crate) fn presets_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("presets").is_some_and(|p| p.is_array()))
            .ok_or_else(|| {
                "Jarvis answered, but not with the focus presets. Update the backend \
                 by running apply-patches.ps1."
                    .to_string()
            });
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": PRESETS_UPDATE }));
    }
    Err(backend_refusal(status, body))
}

/// [`apply_focus_preset`]'s reading: 2xx object passed on; every refusal is the
/// backend's own sentence (with its HTTP code when the backend gave no words).
pub(crate) fn apply_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if missing(status, body) {
        return Err(PRESETS_UPDATE.to_string());
    }
    Err(backend_refusal(status, body))
}

/// The preset id is the PC's own; this only refuses an empty or plainly unusable
/// value before it reaches the network. Unknown ids are the backend's answer.
pub(crate) fn preset_id(preset: &str) -> Result<&str, String> {
    let id = preset.trim();
    if id.is_empty() || id.len() > 64 || id.chars().any(char::is_control) {
        return Err("That is not a focus preset this app can ask for.".to_string());
    }
    Ok(id)
}

/// An API service id from the PC's own provider list (`deepseek_api`, ...).
/// The same narrow shape [`crate::plain_errors::manner_change_body`] gives a
/// personality id: 1-64 characters, lowercase letters, digits, `_`, `-`. What a
/// provider MEANS is still the PC's business.
pub(crate) fn provider_id(provider: &str) -> Result<&str, String> {
    let id = provider.trim();
    let shape = (1..=64).contains(&id.len())
        && id.starts_with(|c: char| c.is_ascii_lowercase() || c.is_ascii_digit())
        && id
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-');
    if !shape {
        return Err("That is not a cloud service this PC offers.".to_string());
    }
    Ok(id)
}

/// The body of one apply. With no provider it is byte-for-byte the body every
/// preset click has always sent (`{"preset": "<id>"}`); the Cloud row adds the
/// ONE provider id and nothing else (2026-10-27).
pub(crate) fn model_apply_body(
    preset: &str,
    provider: Option<&str>,
) -> Result<serde_json::Value, String> {
    let mut body = serde_json::Map::new();
    body.insert("preset".into(), serde_json::json!(preset));
    if let Some(provider) = provider {
        body.insert("provider".into(), serde_json::json!(provider_id(provider)?));
    }
    Ok(serde_json::Value::Object(body))
}

/// The body of one escalate change: ONE boolean, so a caller cannot smuggle a
/// lane, a provider or a "yes" for one turn into a stored setting.
pub(crate) fn cloud_escalate_body(on: bool) -> serde_json::Value {
    serde_json::json!({ "on": on })
}

/// [`hud_cloud_escalate`]'s reading: 2xx object passed on; a missing route says
/// so; every other refusal is the backend's own sentence.
pub(crate) fn cloud_escalate_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if missing(status, body) {
        return Err(CLOUD_ESCALATE_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// What the PC has to offer: `GET /api/work` (`jarvis_presets`).
///
/// Quickbar and Settings both draw it. Read-only - no stale-link hold, nothing
/// changes, and no token is kept in the page.
#[tauri::command]
pub async fn get_focus_presets(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{FOCUS_PRESETS_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    presets_answer(status, &body)
}

/// The ONE action: `POST /api/work/apply {"preset": "<id>"}` - and the ONE
/// optional `provider` the Cloud row adds.
///
/// Nothing is approved here. The backend starts exactly one named lane on
/// demand and raises the existing `switch_model` ask card; the answer is the
/// backend's. Applying is held while the event stream is stale (rule 4).
#[tauri::command]
pub async fn apply_focus_preset(
    app: AppHandle,
    preset: String,
    provider: Option<String>,
) -> Result<serde_json::Value, String> {
    let preset = preset_id(&preset)?;
    let body = model_apply_body(preset, provider.as_deref())?;
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(APPLY_TIMEOUT))?
        .post(format!("{base}{FOCUS_PRESETS_APPLY_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    apply_answer(status, &text)
}

/// The HUD Presets menu's escalate switch (2026-10-27):
/// `POST /api/work/cloud-escalate {"on": true|false}`.
///
/// ONE boolean. The PC is the decider: ON is a loosening and raises its ONE
/// `change_own_config` card (so this can wait as long as an apply), OFF is
/// instant. Held on a stale link like every other write (rule 4). Nothing is
/// stored or decided in this window - the answer is the PC's, and the page
/// draws the checkbox from a REFETCH of the PC's own contract.
#[tauri::command]
pub async fn hud_cloud_escalate(app: AppHandle, on: bool) -> Result<serde_json::Value, String> {
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(APPLY_TIMEOUT))?
        .post(format!("{base}{CLOUD_ESCALATE_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&cloud_escalate_body(on))
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    cloud_escalate_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_real_preset_list_is_passed_on_unchanged() {
        let body = r#"{"found":"5 focus presets","presets":[{"id":"general"}],"chosen":"general"}"#;
        let got = presets_answer(200, body).expect("real list");
        assert_eq!(
            got,
            serde_json::from_str::<serde_json::Value>(body).unwrap()
        );
    }

    #[test]
    fn an_older_work_answer_is_not_guessed_as_presets() {
        assert!(presets_answer(200, r#"{"setups":[{"id":"everyday"}]}"#).is_err());
        assert!(presets_answer(200, "not json").is_err());
    }

    #[test]
    fn a_missing_presets_contract_says_so_instead_of_an_error() {
        let got = presets_answer(503, r#"{"available":false,"why":"off"}"#).expect("missing");
        assert_eq!(got["available"], serde_json::json!(false));
        assert_eq!(got["why"], serde_json::json!(PRESETS_UPDATE));
        assert_eq!(apply_answer(404, "{}").unwrap_err(), PRESETS_UPDATE,);
    }

    #[test]
    fn a_refusal_is_the_pcs_own_sentence() {
        let got = apply_answer(
            409,
            r#"{"ok":false,"changed":false,"error":"the model switch did not happen: refused"}"#,
        )
        .unwrap_err();
        assert!(
            got.to_lowercase()
                .contains("the model switch did not happen: refused"),
            "{got}"
        );
        assert!(apply_answer(200, r#"{"ok":true,"changed":true}"#).is_ok());
        assert!(apply_answer(200, "[]").is_err());
    }

    #[test]
    fn the_apply_timeout_outlasts_the_approval_gate() {
        // The PC's approval gate may wait 900 s; the command must not give up
        // before a real card can still be answered.
        assert!(APPLY_TIMEOUT >= Duration::from_secs(1_200));
        assert!(APPLY_TIMEOUT > Duration::from_secs(900));
    }

    #[test]
    fn an_unusable_preset_id_never_reaches_the_network() {
        assert_eq!(preset_id("  fast  "), Ok("fast"));
        assert!(preset_id("").is_err());
        assert!(preset_id("bad\nid").is_err());
        assert!(preset_id(&"x".repeat(65)).is_err());
    }

    #[test]
    fn no_provider_sends_exactly_the_body_every_preset_click_sent_before() {
        // 2026-10-27: the provider field is additive, and an older call must
        // produce byte-for-byte the body it always did - no `provider` key at
        // all, not a null.
        let body = model_apply_body("coding", None).expect("a real preset");
        assert_eq!(body, serde_json::json!({ "preset": "coding" }));
        assert!(body.get("provider").is_none());
    }

    #[test]
    fn the_cloud_row_carries_the_one_provider_it_was_given() {
        let body = model_apply_body("cloud", Some("deepseek_api")).expect("a real provider");
        assert_eq!(
            body,
            serde_json::json!({ "preset": "cloud", "provider": "deepseek_api" })
        );
        // Trimmed, like the preset id.
        assert_eq!(
            model_apply_body("cloud", Some("  groq_api ")).unwrap()["provider"],
            serde_json::json!("groq_api")
        );
    }

    #[test]
    fn an_unusable_provider_id_never_reaches_the_network() {
        assert!(provider_id("deepseek_api").is_ok());
        assert!(provider_id("").is_err());
        assert!(provider_id("DeepSeek").is_err());
        assert!(provider_id("bad id").is_err());
        assert!(provider_id("bad\nid").is_err());
        assert!(provider_id(&"x".repeat(65)).is_err());
        assert!(model_apply_body("cloud", Some("bad/id")).is_err());
    }

    #[test]
    fn the_escalate_command_sends_one_boolean_and_nothing_else() {
        // The whole point of `hud_cloud_escalate`: a stored setting, so the
        // body cannot carry a lane, a provider or a one-turn "yes".
        assert_eq!(cloud_escalate_body(true), serde_json::json!({ "on": true }));
        assert_eq!(
            cloud_escalate_body(false),
            serde_json::json!({ "on": false })
        );
        let body = cloud_escalate_body(true);
        assert_eq!(body.as_object().map(|object| object.len()), Some(1));
        assert_eq!(CLOUD_ESCALATE_PATH, "/api/work/cloud-escalate");
    }

    #[test]
    fn the_escalate_answer_is_the_pcs_own_and_a_missing_route_says_so() {
        let got = cloud_escalate_answer(200, r#"{"ok":true,"on":true}"#).expect("the PC's answer");
        assert_eq!(got["on"], serde_json::json!(true));
        // A 409 refusal is the PC's sentence, never a made-up success.
        let refused = cloud_escalate_answer(
            409,
            r#"{"ok":false,"changed":false,"error":"the card was refused"}"#,
        )
        .unwrap_err();
        assert!(
            refused.to_lowercase().contains("the card was refused"),
            "{refused}"
        );
        // An older backend, and a 200 that is not an object.
        assert_eq!(
            cloud_escalate_answer(404, "{}").unwrap_err(),
            CLOUD_ESCALATE_MISSING
        );
        assert_eq!(
            cloud_escalate_answer(503, r#"{"available":false}"#).unwrap_err(),
            CLOUD_ESCALATE_MISSING
        );
        assert!(cloud_escalate_answer(200, "[]").is_err());
    }
}
