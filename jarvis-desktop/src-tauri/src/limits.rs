//! Settings -> "Limits and frequency" (2026-10-08; backend/limits-read.patch
//! and backend/limits-settings.patch, backend/jarvis_limits.py).
//!
//! Two commands, settings window only (permissions/surfaces.toml,
//! `limits-surface`):
//!
//! * [`get_limits`] - `GET /api/limits`: the limits this app may change, with
//!   what the owner's own settings file says now and the owner's words for each
//!   one. The PC writes every word of it; this passes the answer on as it is.
//! * [`set_limit`] - `POST /api/limits/settings`: ONE limit, one value.
//!
//! Which way a change goes is the BACKEND's decision - the value against the
//! number already in force, never a flag from here. Turning a number down
//! applies at once; RAISING one that lets Jarvis do more is a loosening, and
//! the backend puts one approval card to the owner first and writes nothing
//! until it is approved. The answer comes back whole for that reason: `said` is
//! the sentence to show, and a refusal carries the card's own words.
//!
//! A PC whose Jarvis has not had `apply-patches.ps1` run since answers 404, and
//! that is said in the owner's words rather than passed on as an HTTP line.

use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const LIMITS_PATH: &str = "/api/limits";
pub(crate) const LIMITS_SET_PATH: &str = "/api/limits/settings";

/// What a backend without the limits patch is told to do about it.
pub(crate) const LIMITS_MISSING: &str = "Your PC's Jarvis does not have this setting yet - \
     run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const TIMEOUT: Duration = Duration::from_secs(15);

/// [`get_limits`]'s reading of the answer, tested in this file. A row list is
/// required: an error body parsed as data would draw an empty card, and an
/// empty card says "there is nothing to change" over a reading that never
/// happened.
pub(crate) fn limits_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("limits").is_some_and(|r| r.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Ok(serde_json::json!({ "available": false, "why": LIMITS_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// Every limit this app may change: `GET /api/limits`.
#[tauri::command]
pub async fn get_limits(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(TIMEOUT))?
        .get(format!("{base}{LIMITS_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    limits_answer(status, &body)
}

/// Changes ONE limit: `POST /api/limits/settings` with `{key, value}`.
///
/// The value is passed as JSON exactly as the page built it (a number or a
/// bool), because the table's own `kind` decides what it means - this command
/// knows no limit by name and refuses nothing the backend would allow.
#[tauri::command]
pub async fn set_limit(
    app: AppHandle,
    key: String,
    value: serde_json::Value,
) -> Result<serde_json::Value, String> {
    if key.is_empty() {
        return Err("Send the limit you want to change.".to_string());
    }
    let body = serde_json::json!({ "key": key, "value": value });
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(TIMEOUT))?
        .post(format!("{base}{LIMITS_SET_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    if status == 404 {
        return Err(LIMITS_MISSING.to_string());
    }
    if !(200..300).contains(&status) {
        // The backend's own sentence: a denied card, a timed-out card, a
        // PC-only limit refused from a phone, or a value out of range - each
        // already in the owner's words.
        return Err(backend_refusal(status, &text));
    }
    serde_json::from_str::<serde_json::Value>(&text).map_err(|_| UNREADABLE.to_string())
}

#[cfg(test)]
mod tests {
    use super::{limits_answer, LIMITS_MISSING};

    #[test]
    fn a_real_answer_is_passed_on_unchanged() {
        let view = serde_json::json!({
            "available": true,
            "limits": [
                {"key": "undo_window", "title": "How long you can undo", "kind": "int",
                 "value": 24, "words": "keep undo for a day", "choices": [1, 24, 168],
                 "low": 1, "high": 720, "unit": "hours",
                 "note": "A longer window keeps older copies of your files on this PC.",
                 "loosen_up": true, "pc_only": false}
            ]
        });
        let got = limits_answer(200, &view.to_string()).expect("a real view");
        assert_eq!(got, view);
    }

    #[test]
    fn an_older_pc_says_so_and_nonsense_is_refused() {
        let got = limits_answer(404, r#"{"error": "no such route"}"#).unwrap();
        assert_eq!(got["why"], LIMITS_MISSING);
        assert_eq!(got["available"], serde_json::json!(false));
        // An error body parsed as data would draw an empty card; a wrong shape
        // and a bad token are both errors, not an empty list.
        assert!(limits_answer(200, "not json").is_err());
        assert!(limits_answer(200, r#"{"limits": "nope"}"#).is_err());
        assert!(limits_answer(200, r#"{"available": true}"#).is_err());
        assert!(limits_answer(401, r#"{"error": "bad or missing X-Jarvis-Token"}"#).is_err());
    }
}
