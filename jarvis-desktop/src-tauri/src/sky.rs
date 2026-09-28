//! The sun, the moon and the weather behind the animal faces (the owner's
//! decisions of 2026-09-28; backend/jarvis_sky.py, sky.patch; JARVIS-API.md
//! section 59).
//!
//! Two commands:
//!
//! * [`get_sky`] - `GET /api/sky`: whether the sun and moon show, the town
//!   (as the PC's list names it, and its position rounded to 0.1 degree),
//!   the weather source and the weather now as five numbers, with the PC's
//!   own words. A read. Settings, the Widget and the floating face call it
//!   (`sky-feed.js`) and keep what drawing needs in this computer's
//!   localStorage, where every face page reads it - the face frames
//!   themselves hold no command at all.
//! * [`set_sky`] - `POST /api/sky` with ONE change, checked here before
//!   anything is sent: `{"show": bool}`, `{"place": "<town>"}` (this PC
//!   only - the backend checks that too), `{"forget_place": true}` or
//!   `{"weather": "off" | "home_assistant" | "open_meteo"}`. Settings only.
//!   Open-Meteo ON approves nothing here: the PC raises ONE approval card.
//!   A change that adds something (showing, a town, a weather source) is
//!   held while the event stream is stale (rule 4); one that only takes
//!   something away (hiding, forgetting the town, weather off) never is.
//!
//! The sun and moon themselves are worked out in the page (`sky.js`), on
//! this computer, from the rounded position - nothing goes online for them.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const SKY_PATH: &str = "/api/sky";

/// What a backend without `jarvis_sky.py` is told. The phone says the same
/// (`SkySettings.MISSING`), and so does the PC.
pub(crate) const SKY_MISSING: &str = "Your PC's Jarvis cannot show the sun, moon or weather \
     yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);
const SOURCES: [&str; 3] = ["off", "home_assistant", "open_meteo"];
const MAX_PLACE_CHARS: usize = 120;

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_sky`]'s reading of the answer.
pub(crate) fn sky_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("show").is_some_and(|s| s.is_boolean()))
            .filter(|v| v.get("weather").is_some_and(|w| w.is_object()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": SKY_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// The ONE change [`set_sky`] may send, and whether it adds something (and
/// so is held on a stale link). Anything else is refused before a byte is
/// sent.
pub(crate) fn sky_change(change: &serde_json::Value) -> Result<(serde_json::Value, bool), String> {
    let obj = change
        .as_object()
        .filter(|o| o.len() == 1)
        .ok_or_else(|| "Send one change at a time.".to_string())?;
    let (key, value) = obj.iter().next().expect("one entry");
    match key.as_str() {
        "show" => {
            let on = value
                .as_bool()
                .ok_or_else(|| "That is not on or off.".to_string())?;
            Ok((serde_json::json!({ "show": on }), on))
        }
        "place" => {
            let text = value
                .as_str()
                .map(|s| s.split_whitespace().collect::<Vec<_>>().join(" "))
                .filter(|s| !s.is_empty() && s.chars().count() <= MAX_PLACE_CHARS)
                .ok_or_else(|| "Type your town, or its position like 39.7, -105.0.".to_string())?;
            Ok((serde_json::json!({ "place": text }), true))
        }
        "forget_place" if value.as_bool() == Some(true) => {
            Ok((serde_json::json!({ "forget_place": true }), false))
        }
        "weather" => {
            let src = value
                .as_str()
                .filter(|s| SOURCES.contains(s))
                .ok_or_else(|| "That is not one of the three choices.".to_string())?;
            Ok((serde_json::json!({ "weather": src }), src != "off"))
        }
        _ => Err("That is not a sky setting.".to_string()),
    }
}

/// The sun, the moon and the weather: `GET /api/sky`.
#[tauri::command]
pub async fn get_sky(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{SKY_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    sky_answer(status, &body)
}

/// ONE change: `POST /api/sky`. Adding something is held on a stale link.
#[tauri::command]
pub async fn set_sky(
    app: AppHandle,
    change: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let (body, adds) = sky_change(&change)?;
    if adds && app.state::<crate::stream::StreamState>().link().stale {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{SKY_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(&text)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, &text) {
        return Err(SKY_MISSING.to_string());
    }
    // A refusal the PC worded (a town it cannot find, a phone that may not
    // set one): its own sentence, never JSON.
    if let Some(said) = serde_json::from_str::<serde_json::Value>(&text)
        .ok()
        .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(str::to_string))
        .filter(|s| !s.trim().is_empty() && s.len() <= 600)
    {
        if (400..500).contains(&status) {
            return Err(said);
        }
    }
    Err(backend_refusal(status, &text))
}

#[cfg(test)]
mod tests {
    use super::{sky_answer, sky_change, SKY_MISSING};
    use serde_json::json;

    #[test]
    fn only_one_known_change_is_ever_sent() {
        assert_eq!(
            sky_change(&json!({"show": true})).unwrap(),
            (json!({"show": true}), true)
        );
        assert_eq!(
            sky_change(&json!({"show": false})).unwrap(),
            (json!({"show": false}), false)
        );
        assert_eq!(
            sky_change(&json!({"place": "  Denver,   Colorado "})).unwrap(),
            (json!({"place": "Denver, Colorado"}), true)
        );
        assert_eq!(
            sky_change(&json!({"forget_place": true})).unwrap(),
            (json!({"forget_place": true}), false)
        );
        assert_eq!(
            sky_change(&json!({"weather": "off"})).unwrap(),
            (json!({"weather": "off"}), false)
        );
        assert_eq!(
            sky_change(&json!({"weather": "open_meteo"})).unwrap(),
            (json!({"weather": "open_meteo"}), true)
        );
        for bad in [
            json!({"show": "yes"}),
            json!({"place": ""}),
            json!({"place": "x".repeat(121)}),
            json!({"forget_place": false}),
            json!({"weather": "brave"}),
            json!({"show": true, "place": "x"}),
            json!({"lat": 1}),
            json!("show"),
        ] {
            assert!(sky_change(&bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn answers_are_read_or_refused() {
        let v = sky_answer(200, r#"{"show": false, "weather": {"source": "off"}}"#).unwrap();
        assert_eq!(v["show"], false);
        for code in [404u16, 503] {
            assert_eq!(
                sky_answer(code, r#"{"available": false}"#).unwrap()["why"],
                SKY_MISSING
            );
        }
        assert!(sky_answer(200, "not json").is_err());
        assert!(sky_answer(200, r#"{"show": "no"}"#).is_err());
        assert!(sky_answer(401, r#"{"error": "bad or missing X-Jarvis-Token"}"#).is_err());
    }
}
