//! Focus presets on the PC (backend/jarvis_presets.py, JARVIS-API section 128's
//! successor, PRs #603/#611): the five presets, the hardware block and the ONE
//! approval-gated apply.
//!
//! Two commands, granted to the quickbar and Settings:
//!
//! * [`get_focus_presets`] - `GET /api/work`, passed on as it is. The route is
//!   the existing work route; a backend that still answers the old five-setup
//!   shape is reported as needing an update, never guessed at.
//! * [`apply_focus_preset`] - `POST /api/work/apply {"preset": "<id>"}`. This
//!   approves nothing itself: the backend starts the named lane on demand and
//!   raises the ONE existing `switch_model` ask card. A stale link is refused
//!   before anything is sent (rule 4), like every other card-raising write.
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

/// What an older backend is told to do about it.
const PRESETS_UPDATE: &str = "This PC's Jarvis does not have the focus presets yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

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

/// The ONE action: `POST /api/work/apply {"preset": "<id>"}`.
///
/// Nothing is approved here. The backend starts exactly one named lane on
/// demand and raises the existing `switch_model` ask card; the answer is the
/// backend's. Applying is held while the event stream is stale (rule 4).
#[tauri::command]
pub async fn apply_focus_preset(
    app: AppHandle,
    preset: String,
) -> Result<serde_json::Value, String> {
    let preset = preset_id(&preset)?;
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(APPLY_TIMEOUT))?
        .post(format!("{base}{FOCUS_PRESETS_APPLY_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "preset": preset }))
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    apply_answer(status, &body)
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
}
