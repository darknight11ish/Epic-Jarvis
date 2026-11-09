//! The auto Wi-Fi reconnect switch (2026-11-08; `jarvis_wifi.py`, GET/POST
//! `/api/wifi-reconnect`; the owner's ask that it default on and be changeable in
//! Settings or chat).
//!
//! Two commands, Settings window only:
//!
//! * [`get_wifi_reconnect`] - `GET /api/wifi-reconnect`: the switch as the PC
//!   holds it (`enabled`, `default`, `known`, `dry_run`, the last check and the
//!   PC's own `words`). A read, never held, never a card.
//! * [`set_wifi_reconnect`] - `POST /api/wifi-reconnect {"enabled": bool}`: ONE
//!   change. Cardless in both directions: OFF removes the two-hourly automatic
//!   attempt and cannot loosen anything; ON restores the shipped default the
//!   owner asked for. See `jarvis_wifi.py`'s own header for the permission
//!   argument and its one narrow standing action (saved password-protected
//!   profiles only, never open, never new, never while Jarvis is answering).
//!
//! The route is PC-only by the backend's own rule, so nothing here sends a
//! network name or asks for a password: the page draws the switch, the PC's own
//! sentence and its last result, and nothing else.

use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// The one route. Both commands use it; a change is the same path as a POST.
pub(crate) const WIFI_RECONNECT_PATH: &str = "/api/wifi-reconnect";

/// What a backend without `jarvis_wifi.py` is told. The Settings page carries the
/// same sentence as its own fallback, so a PC that answers nothing at all still
/// says something true.
pub(crate) const WIFI_RECONNECT_MISSING: &str =
    "Your PC's Jarvis has no Wi-Fi reconnect switch yet - run apply-patches.ps1 on the PC.";

/// A 2xx whose body this app cannot read. Never drawn as "off": a state that
/// cannot be read is not the same as a switch that is turned off.
const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// A write touches one small JSON file on the PC. Generous because it may queue
/// behind a busy backend, never because it is slow: nothing here calls a model.
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

/// A route this PC's backend does not have: a 404, or the 503 an unpatched
/// module answers with `available: false`.
fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_wifi_reconnect`]'s reading of the answer: the PC's own body, once it
/// really carries the one thing the page reads it for (`enabled`, a yes or no).
pub(crate) fn view_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("enabled").is_some_and(|e| e.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": WIFI_RECONNECT_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A change's answer: the PC's own body on a 2xx, [`WIFI_RECONNECT_MISSING`] from
/// a PC without the route, and the PC's own sentence otherwise. `enabled` is
/// required as well as an object, because the page words its line from this
/// reply - a body without the yes-or-no would have it claim a state the PC never
/// named.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object() && v.get("enabled").is_some_and(|e| e.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(WIFI_RECONNECT_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// The switch as it stands: `GET /api/wifi-reconnect`. A read.
#[tauri::command]
pub async fn get_wifi_reconnect(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{WIFI_RECONNECT_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    view_answer(status, &body)
}

/// ONE change: the auto Wi-Fi reconnect on, or off. Cardless both ways.
#[tauri::command]
pub async fn set_wifi_reconnect(
    app: AppHandle,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{WIFI_RECONNECT_PATH}"))
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
    use super::{change_answer, view_answer, WIFI_RECONNECT_MISSING, WIFI_RECONNECT_PATH};

    /// The PC's own answer, word for word (`jarvis_wifi.state()`).
    const VIEW: &str = r#"{"ok": true, "enabled": true, "default": true,
        "known": true, "dry_run": false,
        "words": "On. Every 2 hours while this PC has no internet, Jarvis tries the saved password-protected Wi-Fi networks it already knows."}"#;

    #[test]
    fn the_real_view_is_passed_on_unchanged_and_the_route_is_the_agreed_one() {
        let view: serde_json::Value = serde_json::from_str(VIEW).unwrap();
        let got = view_answer(200, VIEW).unwrap();
        assert_eq!(got, view);
        // OFF is a real answer, not a missing one.
        assert_eq!(
            view_answer(200, r#"{"enabled": false, "default": true, "known": true}"#).unwrap()
                ["enabled"],
            false
        );
        assert_eq!(WIFI_RECONNECT_PATH, "/api/wifi-reconnect");
    }

    #[test]
    fn a_missing_module_is_said_in_words_not_read_as_off() {
        let got = view_answer(404, "{}").unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], WIFI_RECONNECT_MISSING);
        assert_eq!(
            change_answer(404, "{}").unwrap_err(),
            WIFI_RECONNECT_MISSING
        );
    }

    #[test]
    fn an_unreadable_body_is_never_read_as_off() {
        let err = view_answer(200, r#"{"words": "maybe"}"#).unwrap_err();
        assert!(!err.contains("off"), "{err}");
        // ... and a change's reply must carry the yes-or-no before the page
        // words a success line from it.
        assert!(change_answer(200, r#"{"ok": true}"#).is_err());
        let ok = change_answer(
            200,
            r#"{"enabled": false, "words": "The auto Wi-Fi reconnect is off now."}"#,
        )
        .unwrap();
        assert_eq!(ok["enabled"], false);
    }
}
