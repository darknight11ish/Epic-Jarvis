//! "Animal options" - the switches shared with the phone (the owner's
//! decisions of 2026-09-28; backend/jarvis_animal.py, animal.patch;
//! JARVIS-API.md section 60).
//!
//! Three commands:
//!
//! * [`get_animal`] - `GET /api/animal`: "Keep the animal still" and the
//!   behaviour switches, each with its value and the PC's own words. A read.
//!   Settings only.
//! * [`set_animal`] - `POST /api/animal` with ONE change, `{"<id>": bool}`,
//!   checked here before anything is sent. Cosmetic, so no card either way;
//!   turning one ON is held while the event stream is stale (rule 4, the
//!   same line sky.rs draws), turning one OFF never is. Settings only. On
//!   success the appearance document is read again, so every window and
//!   the face frames change at once rather than on the event.
//! * [`migrate_animal_still`] - once per install: this computer's old
//!   "Keep the animal still" (it used to live only here, in face-tuning.js)
//!   is sent to the PC, and only if it was ON - "if either device had Still
//!   on, keep it on". It can only ever send `{"still": true}`, and only
//!   once: a flag in the settings store says it has been done. Every window
//!   with jarvis-link.js may call it (the first one open does it), because
//!   the Settings window may never be opened.
//!
//! The values themselves reach every window through the appearance document
//! (`appearance.rs`, field `animal`), which is read again on every
//! `appearance` event - the one the PC rings on each change.

use std::time::Duration;

use tauri::{AppHandle, Manager};
use tauri_plugin_store::StoreExt;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const ANIMAL_PATH: &str = "/api/animal";

/// What a backend without `jarvis_animal.py` is told. The phone says the
/// same (`AnimalOptions.MISSING`), and so does the PC.
pub(crate) const ANIMAL_MISSING: &str = "Your PC's Jarvis cannot share the animal options yet - \
     run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

/// The switches the PC knows (jarvis_animal.SWITCHES). Anything else is
/// refused before a byte is sent.
pub(crate) const SWITCH_IDS: [&str; 7] = [
    "still",
    "nods",
    "focus_buddy",
    "acks",
    "petting",
    "cute_moments",
    "seasonal",
];

/// The settings-store key that says the old Still has been sent.
const MIGRATED_KEY: &str = "animal_still_migrated";

const READ_TIMEOUT: Duration = Duration::from_secs(10);
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_animal`]'s reading of the answer.
pub(crate) fn animal_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("values").is_some_and(|s| s.is_object()))
            .filter(|v| v.get("switches").is_some_and(|w| w.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": ANIMAL_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// The ONE change [`set_animal`] may send, and whether it turns something
/// on (and so is held on a stale link).
pub(crate) fn animal_change(
    change: &serde_json::Value,
) -> Result<(serde_json::Value, bool), String> {
    let obj = change
        .as_object()
        .filter(|o| o.len() == 1)
        .ok_or_else(|| "Send one change at a time.".to_string())?;
    let (key, value) = obj.iter().next().expect("one entry");
    if !SWITCH_IDS.contains(&key.as_str()) {
        return Err("That is not an animal option.".to_string());
    }
    let on = value
        .as_bool()
        .ok_or_else(|| "That is not on or off.".to_string())?;
    Ok((serde_json::json!({ key.as_str(): on }), on))
}

async fn post(app: &AppHandle, body: &serde_json::Value) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{ANIMAL_PATH}"))
        .headers(jarvis_headers(app)?)
        .json(body)
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
        return Err(ANIMAL_MISSING.to_string());
    }
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

/// The shared animal options: `GET /api/animal`.
#[tauri::command]
pub async fn get_animal(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{ANIMAL_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    animal_answer(status, &body)
}

/// ONE change: `POST /api/animal`. Turning one on is held on a stale link.
#[tauri::command]
pub async fn set_animal(
    app: AppHandle,
    change: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let (body, on) = animal_change(&change)?;
    if on && app.state::<crate::stream::StreamState>().link().stale {
        return Err(STALE.to_string());
    }
    let out = post(&app, &body).await?;
    // Every window and face frame wears it now, not when the event arrives.
    crate::appearance::refresh_from_server(&app).await;
    Ok(out)
}

/// Once per install: this computer's old "Keep the animal still", sent to
/// the PC only if it was on. Returns "sent", "done" (already), or an error
/// in words (an older PC, or not reachable - tried again next time).
#[tauri::command]
pub async fn migrate_animal_still(app: AppHandle) -> Result<String, String> {
    let store = app
        .store(crate::commands::SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    if store.get(MIGRATED_KEY).and_then(|v| v.as_bool()) == Some(true) {
        return Ok("done".into());
    }
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(STALE.to_string());
    }
    // Only while nobody has chosen anything on the PC yet: once a switch was
    // changed there (on the phone, by asking Jarvis, or here), that choice
    // is newer than this computer's old one and wins.
    let now = get_animal(app.clone()).await?;
    if !still_move_needed(&now) {
        store.set(MIGRATED_KEY, serde_json::json!(true));
        let _ = store.save();
        return Ok("done".into());
    }
    post(&app, &serde_json::json!({ "still": true })).await?;
    store.set(MIGRATED_KEY, serde_json::json!(true));
    let _ = store.save();
    crate::appearance::refresh_from_server(&app).await;
    Ok("sent".into())
}

/// Whether this computer's old "on" should still be sent: the PC answered,
/// its Still is off, and Still itself has not been chosen there yet (another
/// switch being changed does not count; an older PC without `still_changed`
/// is judged by `changed`).
pub(crate) fn still_move_needed(view: &serde_json::Value) -> bool {
    view.get("available").and_then(|a| a.as_bool()) != Some(false)
        && view["values"]["still"].as_bool() == Some(false)
        && view
            .get("still_changed")
            .or_else(|| view.get("changed"))
            .and_then(|c| c.as_f64())
            .unwrap_or(0.0)
            <= 0.0
}

#[cfg(test)]
mod tests {
    use super::{animal_answer, animal_change, still_move_needed, ANIMAL_MISSING, SWITCH_IDS};
    use serde_json::json;

    #[test]
    fn only_one_known_switch_is_ever_sent() {
        for id in SWITCH_IDS {
            assert_eq!(
                animal_change(&json!({ id: true })).unwrap(),
                (json!({ id: true }), true)
            );
            assert_eq!(
                animal_change(&json!({ id: false })).unwrap(),
                (json!({ id: false }), false)
            );
        }
        for bad in [
            json!({"still": "yes"}),
            json!({"sparkles": true}),
            json!({"still": true, "nods": false}),
            json!({}),
            json!("still"),
        ] {
            assert!(animal_change(&bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn the_old_still_moves_only_before_anyone_chose() {
        assert!(still_move_needed(
            &json!({"values": {"still": false}, "changed": 0.0})
        ));
        assert!(!still_move_needed(
            &json!({"values": {"still": true}, "changed": 0.0})
        ));
        assert!(!still_move_needed(
            &json!({"values": {"still": false}, "changed": 1759000000.0})
        ));
        assert!(!still_move_needed(&json!({"available": false})));
    }

    #[test]
    fn another_switch_changing_does_not_stop_the_old_still() {
        assert!(still_move_needed(
            &json!({"values": {"still": false}, "changed": 1759000000.0, "still_changed": 0.0})
        ));
        assert!(!still_move_needed(
            &json!({"values": {"still": false}, "changed": 1759000000.0, "still_changed": 1759000000.0})
        ));
    }

    #[test]
    fn answers_are_read_or_refused() {
        let v = animal_answer(200, r#"{"values": {"still": true}, "switches": []}"#).unwrap();
        assert_eq!(v["values"]["still"], true);
        for code in [404u16, 503] {
            assert_eq!(
                animal_answer(code, r#"{"available": false}"#).unwrap()["why"],
                ANIMAL_MISSING
            );
        }
        assert!(animal_answer(200, "not json").is_err());
        assert!(animal_answer(200, r#"{"values": []}"#).is_err());
        assert!(animal_answer(401, r#"{"error": "bad or missing X-Jarvis-Token"}"#).is_err());
    }
}
