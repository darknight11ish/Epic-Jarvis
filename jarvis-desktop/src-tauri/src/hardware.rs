//! Settings -> "Hardware and models": the graphics cards, and the three
//! setups Jarvis offers for them (backend/hardware.patch,
//! backend/jarvis_hardware.py, docs/HARDWARE-PROFILES.md).
//!
//! Four commands, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_hardware`] - `GET /api/hardware`, passed on as it is.
//! * [`apply_hardware`] - `POST /api/hardware/apply {"preset"}`: remembers
//!   the owner's choice. It changes no model and no setting by itself.
//! * [`hardware_step`] - ONE step of the chosen preset, by its id. The step's
//!   route and body are read from the backend's own answer (a fresh `GET`),
//!   never from the page, and only four routes are ever posted to - the
//!   existing model install and switch, the second-card switch, and
//!   `/api/hardware/create`. Each raises its own approval card; there is no
//!   form that sends more than one step, so nothing is approved in bulk.
//! * [`measure_hardware`] - `POST /api/hardware/measure`.
//!
//! Everything that raises a card or loads a model is held while the event
//! stream is stale (rule 4). Forgetting the choice (`preset: null`) is not:
//! it only narrows what runs. The token goes out in `X-Jarvis-Token`, with
//! `X-Jarvis-Client: hud`, through [`jarvis_headers`], and is never logged
//! or put in an error.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// `GET` here; the three `POST`s are under it.
pub(crate) const HARDWARE_PATH: &str = "/api/hardware";

/// The only routes a step may name - the backend's `STEP_ROUTES`.
pub(crate) const STEP_ROUTES: [&str; 4] = [
    "/api/models/install",
    "/api/models/switch",
    "/api/hardware/create",
    "/api/second-card",
];

/// What a backend without `jarvis_hardware.py` is told to do about it.
pub(crate) const HARDWARE_UPDATE: &str = "This PC's Jarvis does not have the hardware part yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// The words while the event stream is stale.
const STALE: &str = "The connection to Jarvis is catching up, so nothing can be asked for \
                     until it does.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

/// Whether a 404/503 means "this backend has no hardware module": a 404, or
/// the route's own 503 `{"available": false}`.
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

/// [`get_hardware`]'s reading of the answer, on its own so it can be tested
/// against `tests/fixtures/hardware-cases.json` (the real `status()`).
pub(crate) fn hardware_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| {
                v.get("presets").is_some_and(|p| p.is_array())
                    && v.get("cards").is_some_and(|c| c.is_array())
            })
            .ok_or_else(|| {
                "Jarvis answered, but not in a way this app can read. \
                 Update the backend by running apply-patches.ps1."
                    .to_string()
            });
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": HARDWARE_UPDATE }));
    }
    Err(backend_refusal(status, body))
}

/// A POST's answer: 200 is the backend's object as it is; every refusal is
/// the backend's own sentence (JARVIS-API.md: show it word for word).
pub(crate) fn hardware_post_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if missing(status, body) {
        return Err(HARDWARE_UPDATE.to_string());
    }
    Err(backend_refusal(status, body))
}

/// A preset id the backend knows, or none (forget the choice).
pub(crate) fn hardware_preset(preset: Option<&str>) -> Result<Option<&str>, String> {
    match preset.map(str::trim) {
        None => Ok(None),
        Some(p @ ("fast" | "smart" | "features")) => Ok(Some(p)),
        Some(_) => Err("That is not one of the three setups.".to_string()),
    }
}

/// The route and body of step `id` of the chosen preset, from the backend's
/// own `GET /api/hardware` answer. Only the step that is next may be asked
/// for; only the four routes in [`STEP_ROUTES`]; the body must be an object.
pub(crate) fn step_request(
    status: &serde_json::Value,
    id: &str,
) -> Result<(String, serde_json::Value), String> {
    let steps = status
        .get("applying")
        .and_then(|a| a.get("steps"))
        .and_then(|s| s.as_array())
        .ok_or_else(|| "No setup is chosen, so there is no step to ask for.".to_string())?;
    let step = steps
        .iter()
        .find(|s| s.get("id").and_then(|v| v.as_str()) == Some(id))
        .ok_or_else(|| "That step is not in the chosen setup any more.".to_string())?;
    match step.get("state").and_then(|v| v.as_str()) {
        Some("next") => {}
        Some("done") => return Err("That step is already done.".to_string()),
        Some("waiting") => {
            return Err(
                "That step's approval card is already waiting - approve or deny that one."
                    .to_string(),
            )
        }
        _ => return Err("That step waits for the one before it.".to_string()),
    }
    let route = step
        .get("route")
        .and_then(|v| v.as_str())
        .filter(|r| STEP_ROUTES.contains(r))
        .ok_or_else(|| "That step is not one this app asks for.".to_string())?;
    let body = step
        .get("body")
        .filter(|b| b.is_object())
        .cloned()
        .ok_or_else(|| "That step is not one this app asks for.".to_string())?;
    Ok((route.to_string(), body))
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

async fn read(app: &AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{HARDWARE_PATH}"))
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    hardware_answer(status, &body)
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    hardware_post_answer(status, &text)
}

/// The cards, what runs now, and the three setups: `GET /api/hardware`.
#[tauri::command]
pub async fn get_hardware(app: AppHandle) -> Result<serde_json::Value, String> {
    read(&app).await
}

/// Choose a setup, or forget the choice (`preset` absent). Choosing changes
/// no model and no setting; it is held on a stale link, forgetting is not.
#[tauri::command]
pub async fn apply_hardware(
    app: AppHandle,
    preset: Option<String>,
) -> Result<serde_json::Value, String> {
    let preset = hardware_preset(preset.as_deref())?;
    if preset.is_some() && stale(&app) {
        return Err(format!("{STALE} Forgetting a setup still works."));
    }
    post(
        &app,
        "/api/hardware/apply",
        serde_json::json!({ "preset": preset }),
    )
    .await
}

/// ONE step of the chosen setup. It raises that step's own approval card and
/// nothing more.
#[tauri::command]
pub async fn hardware_step(app: AppHandle, step_id: String) -> Result<serde_json::Value, String> {
    if step_id.is_empty() || step_id.len() > 80 {
        return Err("That is not a step of the chosen setup.".to_string());
    }
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let status = read(&app).await?;
    let (route, body) = step_request(&status, &step_id)?;
    post(&app, &route, body).await
}

/// Time each model of the setup on this PC (it loads each once).
#[tauri::command]
pub async fn measure_hardware(app: AppHandle) -> Result<serde_json::Value, String> {
    if stale(&app) {
        return Err(STALE.to_string());
    }
    post(&app, "/api/hardware/measure", serde_json::json!({})).await
}

#[cfg(test)]
mod tests {
    use super::{
        hardware_answer, hardware_post_answer, hardware_preset, step_request, HARDWARE_UPDATE,
        STEP_ROUTES,
    };

    /// The real answers, made by `tools/gen_hardware_cases.py`.
    const CASES: &str = include_str!("../../tests/fixtures/hardware-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("hardware-cases.json is JSON")
    }

    #[test]
    fn every_real_status_is_passed_on_unchanged() {
        let doc = cases();
        let all = doc["cases"].as_object().expect("cases");
        let mut n = 0;
        for (name, status) in all.iter().filter(|(k, _)| !k.starts_with("post_")) {
            let got =
                hardware_answer(200, &status.to_string()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, status, "{name}");
            n += 1;
        }
        assert!(n >= 6, "fewer cases than the fixture promised");
    }

    #[test]
    fn an_older_backend_is_told_to_update() {
        for (code, body) in [(404, ""), (503, r#"{"available": false, "error": "x"}"#)] {
            assert_eq!(hardware_answer(code, body).unwrap()["why"], HARDWARE_UPDATE);
            assert_eq!(
                hardware_post_answer(code, body).unwrap_err(),
                HARDWARE_UPDATE
            );
        }
        assert!(hardware_answer(200, r#"{"ok": true}"#).is_err());
    }

    #[test]
    fn the_backends_own_refusals() {
        let doc = cases();
        let c = &doc["cases"]["post_create_not_downloaded"];
        let said =
            hardware_post_answer(c["status"].as_u64().unwrap() as u16, &c["body"].to_string())
                .unwrap_err();
        assert!(said.starts_with("Download qwen3:4b first"), "{said}");
        let c = &doc["cases"]["post_create_pending"];
        let got = hardware_post_answer(200, &c["body"].to_string()).unwrap();
        assert_eq!(got["pending"], true);
    }

    #[test]
    fn only_the_three_presets_or_none() {
        assert_eq!(hardware_preset(Some("smart")).unwrap(), Some("smart"));
        assert_eq!(hardware_preset(None).unwrap(), None);
        assert!(hardware_preset(Some("turbo")).is_err());
    }

    #[test]
    fn a_step_is_read_from_the_backend_and_only_the_next_one() {
        let doc = cases();
        let first = &doc["cases"]["chosen_first_step"];
        let (route, body) = step_request(first, "install:qwen3:4b").unwrap();
        assert_eq!(route, "/api/models/install");
        assert_eq!(body, serde_json::json!({ "ref": "qwen3:4b" }));
        assert!(step_request(first, "create:jarvis-chat")
            .unwrap_err()
            .contains("waits"));
        assert!(step_request(first, "nope").is_err());
        let waiting = &doc["cases"]["create_waiting"];
        assert!(step_request(waiting, "create:jarvis-chat")
            .unwrap_err()
            .contains("already waiting"));
        assert!(step_request(&doc["cases"]["today_one_card"], "install:qwen3:4b").is_err());
        // A step naming any other route is never posted.
        let forged = serde_json::json!({"applying": {"steps": [
            {"id": "x", "state": "next", "route": "/api/shutdown", "body": {}}]}});
        assert!(step_request(&forged, "x").is_err());
        assert_eq!(STEP_ROUTES.len(), 4);
    }
}
