//! Jarvis's own calendar's ONE switch, for Settings (2026-10-30; JARVIS-API
//! section 166; `backend/jarvis_local_calendar.py`'s `POST /api/calendar/settings`).
//!
//! WHY THIS EXISTS. The PHONE has drawn this switch since its own slice
//! (`CalendarSettingsPlate.kt`, `JarvisRuntime.calendarSettings`), and the
//! DESKTOP's calendar lives in the HUD, which is another window with no
//! Settings page - so before this, "turn the Jarvis Calendar off" had no
//! desktop control at all and the owner's own rule ("every switch findable AND
//! adjustable in Settings too", 2026-10-22) was not met for it. This is the
//! Settings window's own narrow path: the ONE switch, read and written.
//!
//! ONE FIELD PER REQUEST. The route's contract is `{"on": bool}` and this
//! command sends exactly that - there is no second field, no list form and no
//! route by which this window can add, change or delete an event. The HUD's own
//! two write commands belong to that page, not here.
//!
//! NO CARD EITHER WAY, and that is the owner's ruling of 2026-10-29 rather
//! than an omission: OFF only narrows what Jarvis does, ON is the same feature
//! back in one press, and the switch is a preference he can change back at
//! once - the same shape as the Anti-Slop filter. **OFF never deletes an
//! event**: the store keeps every row and the two apps stop drawing it.
//!
//! THE READ IS THE SWITCH ONLY. There is no `GET /api/calendar/settings`
//! route; the switch rides on `GET /api/calendar?days=1`'s `on` field. This
//! command asks for that one-day window and returns `on` plus the PC's own
//! `why` (a damaged settings file reads as off WITH a reason) - and nothing
//! else. Not one event, title, place or count crosses the loopback wire into
//! the Settings page, because that page draws one row and has no calendar in
//! it. The HUD's own read is `hud_proxy.rs`'s; this is not a second idea of it.

use std::time::Duration;

use tauri::AppHandle;

use crate::look;

/// The verbs this command takes. Three, and no fourth: a read, and the switch
/// in each direction.
pub(crate) const ACTIONS: &[&str; 3] = &["read", "on", "off"];

/// The one route a change goes to (the switch), and the read the switch rides
/// on. `days=1` because nothing from that answer is returned - only `on`.
const PATH: &str = "/api/calendar/settings";
const STATUS_PATH: &str = "/api/calendar?days=1";

/// A PC whose backend predates the calendar (the same words the phone's plate
/// shows when its route 404s).
pub(crate) const MISSING: &str = "This PC's Jarvis does not have the calendar yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// One small write: ten seconds is plenty.
const WRITE_TIMEOUT: Duration = Duration::from_secs(10);

/// The body of one verb - ONE field, exactly as the route documents.
pub(crate) fn body(action: &str) -> Result<serde_json::Value, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!("The calendar setting cannot {action:?}"));
    }
    match action {
        "on" => Ok(serde_json::json!({ "on": true })),
        "off" => Ok(serde_json::json!({ "on": false })),
        _ => Ok(serde_json::json!({})),
    }
}

/// The switch and nothing else from `GET /api/calendar`'s answer.
///
/// FAIL CLOSED, the same rule the page keeps (2026-10-30): an answer that does
/// not say `on` as a real boolean is an ERROR, never "off" and never "on" - a
/// switch drawn from a shape nobody understood is a lie about what the store
/// will do. Everything else in the answer (the events, their titles, the
/// sources block) is dropped here, in Rust, so the Settings page cannot read
/// the owner's calendar even by accident.
pub(crate) fn switch_only(v: &serde_json::Value) -> Result<serde_json::Value, String> {
    let on = v
        .get("on")
        .and_then(|b| b.as_bool())
        .ok_or_else(|| "the calendar's answer did not say whether it is on".to_string())?;
    let why = v
        .get("why")
        .and_then(|s| s.as_str())
        .unwrap_or("")
        .to_string();
    Ok(serde_json::json!({
        "ok": true,
        "on": on,
        "why": why,
    }))
}

/// What a switch answer means for the page: the PC's own words plus the value
/// it repaints from. `look::post` has already turned every non-2xx into its
/// refusal sentence, so this only reads the successful shape.
pub(crate) fn answer(v: &serde_json::Value) -> serde_json::Value {
    let mut out = serde_json::Map::new();
    out.insert("ok".into(), serde_json::json!(true));
    if let Some(on) = v.get("on").and_then(|b| b.as_bool()) {
        out.insert("on".into(), serde_json::json!(on));
    }
    if let Some(said) = v.get("said").and_then(|s| s.as_str()) {
        out.insert("said".into(), serde_json::json!(said));
    }
    serde_json::Value::Object(out)
}

/// The Jarvis Calendar's switch, for Settings.
#[tauri::command]
pub async fn calendar_settings(
    app: AppHandle,
    action: String,
) -> Result<serde_json::Value, String> {
    let body = body(&action)?;
    if action == "read" {
        let out = look::get(&app, STATUS_PATH).await.map_err(|why| {
            if why == look::MISSING {
                MISSING.to_string()
            } else {
                why
            }
        })?;
        return switch_only(&out);
    }
    // The switch is NOT held on a stale link: it is a preference on this PC
    // that opens no way out of it, the same class as the Anti-Slop filter's
    // switches (antislop.rs, surfaces.toml) - and a stale event stream says
    // nothing about whether the owner wants his calendar drawn.
    let said = look::post(&app, PATH, body, WRITE_TIMEOUT)
        .await
        .map_err(|why| {
            if why == look::MISSING {
                MISSING.to_string()
            } else {
                why
            }
        })?;
    Ok(answer(&said))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn each_change_sends_exactly_one_field() {
        assert_eq!(body("read").unwrap(), json!({}));
        assert_eq!(body("on").unwrap(), json!({ "on": true }));
        assert_eq!(body("off").unwrap(), json!({ "on": false }));
        // There is no third write, no bulk verb and no event field: the two
        // HUD write commands are a different window's, and this one cannot
        // reach them.
        for other in [
            "add",
            "delete",
            "delete_all",
            "clear",
            "days",
            "set",
            "events",
            "",
        ] {
            assert!(body(other).is_err(), "{other} was accepted");
        }
        for key in ["title", "date", "id", "events"] {
            let text = body("on").unwrap().to_string();
            assert!(!text.contains(key), "the switch body grew a {key}: {text}");
        }
    }

    #[test]
    fn the_read_is_the_switch_and_never_an_event() {
        let out = switch_only(&json!({
            "available": true,
            "on": false,
            "why": "The calendar's settings file could not be read, so it is off.",
            "days": 1,
            "window": { "start": "2026-10-30", "end": "2026-10-31" },
            "sources": { "local": { "state": "off", "count": 2 } },
            "events": [
                {"id": "c0123456789", "title": "Dentist", "date": "2026-11-03",
                 "time": "14:30", "place": "High Street", "notes": "Bring the form"}
            ]
        }))
        .unwrap();
        assert_eq!(out["on"], false);
        assert!(out["why"].as_str().unwrap().contains("could not be read"));
        let text = out.to_string();
        for word in [
            "Dentist",
            "High Street",
            "form",
            "events",
            "window",
            "sources",
        ] {
            assert!(
                !text.contains(word),
                "the Settings row received {word}: {text}"
            );
        }
    }

    #[test]
    fn an_answer_that_does_not_say_on_is_an_error_and_not_off() {
        // FAIL CLOSED: every one of these is refused rather than drawn as a
        // switch. `{"event": ...}` is the `?id=` shape, which is NOT a read of
        // the list and carries no switch at all.
        for shape in [
            json!({}),
            json!({"available": true, "events": []}),
            json!({"ok": true, "event": {"id": "c0123456789"}}),
            json!({"on": "off"}),
            json!({"on": 1}),
            json!({"on": null}),
            json!(null),
        ] {
            assert!(
                switch_only(&shape).is_err(),
                "a switch was drawn from {shape}"
            );
        }
        // A real boolean, in either direction, is the one shape accepted.
        assert_eq!(switch_only(&json!({"on": true})).unwrap()["on"], true);
        assert_eq!(switch_only(&json!({"on": false})).unwrap()["on"], false);
    }

    #[test]
    fn a_switch_answer_keeps_the_pcs_words_and_the_value() {
        assert_eq!(
            answer(&json!({"ok": true, "on": true, "said": "The Jarvis Calendar is on."})),
            json!({"ok": true, "on": true, "said": "The Jarvis Calendar is on."})
        );
        // Nothing else is copied through: the answer is the switch.
        let out = answer(&json!({"ok": true, "on": false, "events": [{"title": "x"}]}));
        assert_eq!(out, json!({"ok": true, "on": false}));
    }

    #[test]
    fn this_module_has_no_network_of_its_own() {
        let source = include_str!("calendar_settings.rs");
        let head = source.split("mod tests").next().unwrap_or(source);
        for word in ["reqwest", "socket", "TcpStream", "urllib"] {
            assert!(!head.contains(word), "the calendar switch grew a {word}");
        }
        // And it never spells a write path of its own: every request is
        // `look::get` / `look::post`, which add the token in Rust.
        assert!(
            head.contains("look::post"),
            "the switch stopped using look::post"
        );
        assert!(
            !head.contains("hud_calendar"),
            "this module reached the HUD's writes"
        );
    }
}
