//! Settings -> "How Jarvis talks" -> "Anti-Slop filter" (2026-10-28): the
//! master switch, the three scopes, the During/After mode and the three
//! Liveliness dials. One route, `GET`/`POST /api/antislop`
//! (`jarvis_antislop.py`; JARVIS-API section 159).
//!
//! Two commands, Settings window only (`permissions/surfaces.toml`):
//!
//! * [`get_antislop`] - `GET /api/antislop`: the whole state, in the PC's own
//!   shape (`enabled`, `mode`, `scopes`, `dials`,
//!   `show_delivery_gate_on_ui_tasks`, `allow_em_dashes`). A read, never held.
//! * [`set_antislop`] - `POST /api/antislop` carrying ONE change.
//!
//! NEITHER DIRECTION IS HELD ON A STALE LINK and neither raises an approval
//! card, in either direction. The anti-slop filter is a wording and
//! output-quality filter: it opens no way out of the PC, reads no folder, takes
//! no action and loosens no rule. That is the same class as the prompt coach
//! beside it (`prompt_coach.rs` says the same, and for the same reason), and it
//! is written down here so it stays a decision rather than becoming an
//! oversight. The page says so in the owner's words - "costs 0 prompt tokens
//! when off" - and the master switch is the one control that decides whether
//! the filter exists at all.
//!
//! ONE COMMAND CARRIES EVERY CONTROL (`set_antislop` with a [`Change`]) for the
//! reason `prompt_coach.rs` gives at length: Tauri binds a page's argument
//! object onto a command's parameters POSITIONALLY, so four loose `Option`s
//! would turn `{mode: "after"}` into `enabled = <the mode>`. One nested object
//! has no order to get wrong, and `#[serde(default)]` on every field means a
//! change that names only one still deserialises. The body is built from the
//! fields that were actually given, so the master switch's own call still sends
//! exactly `{"enabled": bool}`.

use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// The one route. Both commands use it; a change is the same path with a POST.
pub(crate) const ANTISLOP_PATH: &str = "/api/antislop";

/// What a backend without `jarvis_antislop.py` is told. The page carries the
/// same sentence as its own fallback (`antislop.js`'s `MISSING`), so a PC that
/// answers nothing at all still says something true.
pub(crate) const ANTISLOP_MISSING: &str = "Your PC's Jarvis cannot filter AI slop yet - run \
                                          apply-patches.ps1 on the PC.";

/// A 2xx whose body this app cannot read. Never drawn as "off": a state that
/// cannot be read is not the same as a filter that is switched off.
const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// A write does no work but touch one small JSON file on the PC. The budget is
/// generous because it may queue behind a busy backend, never because it is
/// slow: nothing here calls the model.
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

/// The three dials, each 1-3 (the Liveliness Toolkit's ENERGY / RHYTHM /
/// MOTION). Every field optional, so one dial moved on its own is still one
/// small change rather than a whole table rewritten from a stale copy.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(default)]
pub struct Dials {
    pub energy: Option<u8>,
    pub rhythm: Option<u8>,
    pub motion: Option<u8>,
}

impl Dials {
    /// Only the dials that were given, in the PC's own spelling.
    fn into_json(self) -> serde_json::Map<String, serde_json::Value> {
        let mut out = serde_json::Map::new();
        for (name, value) in [
            ("energy", self.energy),
            ("rhythm", self.rhythm),
            ("motion", self.motion),
        ] {
            if let Some(v) = value {
                out.insert(name.to_string(), serde_json::json!(v));
            }
        }
        out
    }
}

/// ONE change to the anti-slop filter. Absent fields did not move.
///
/// Nothing here is validated against a list this side would have to keep in
/// step with the PC: `mode` is whichever word the page sent and `scope` is
/// whichever of `copy`/`code`/`ui` it sent, and the PC refuses an unknown one
/// in its own sentence. The three scopes and the two modes are written in the
/// page (`antislop.js`), once.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(default)]
pub struct Change {
    /// The master switch. Takes effect on the very next turn.
    pub enabled: Option<bool>,
    /// `during` (filter while writing) or `after` (list findings first).
    pub mode: Option<String>,
    /// One scope's name: `copy`, `code` or `ui`.
    pub scope: Option<String>,
    /// That scope's new state. Only read when `scope` is given.
    pub on: Option<bool>,
    /// Any of the three dials.
    pub dials: Option<Dials>,
    /// The four-block Delivery Gate on a finished screen. Sent as the PC's own
    /// field name (`show_delivery_gate_on_ui_tasks`) because that is the key
    /// its state carries, and a second spelling would need a translation table
    /// on both sides.
    pub gate: Option<bool>,
    /// The em-dash exemption (2026-10-28): keep em-dashes everywhere. Its own
    /// field on the PC, `allow_em_dashes`, sent in that spelling for the same
    /// reason as `gate`. It is NOT the voiceprint rule - the PC's own `R-37`
    /// precedence over `R-02` applies whether this is on or off - so this side
    /// only carries the owner's blanket choice and never guesses at the other.
    pub allow_em_dashes: Option<bool>,
}

/// The POST body a change becomes: exactly the fields that moved, and nothing
/// else. `{"enabled": true}` for the master switch, `{"mode": "after"}` for the
/// mode radio, `{"scopes": {"code": false}}` for one scope pill, `{"dials":
/// {"energy": 2}}` for one dial, `{"allow_em_dashes": true}` for the em-dash
/// exemption.
pub(crate) fn change_body(change: Change) -> serde_json::Map<String, serde_json::Value> {
    let mut body = serde_json::Map::new();
    if let Some(on) = change.enabled {
        body.insert("enabled".to_string(), serde_json::json!(on));
    }
    if let Some(mode) = change.mode {
        if !mode.trim().is_empty() {
            body.insert("mode".to_string(), serde_json::json!(mode));
        }
    }
    if let Some(name) = change.scope {
        let name = name.trim().to_string();
        if !name.is_empty() {
            // `on` is required with a scope: a scope with no state is not a
            // change, and guessing "on" would flip a pill nobody pressed.
            if let Some(on) = change.on {
                body.insert("scopes".to_string(), serde_json::json!({ name: on }));
            }
        }
    }
    if let Some(dials) = change.dials {
        let given = dials.into_json();
        if !given.is_empty() {
            body.insert("dials".to_string(), serde_json::Value::Object(given));
        }
    }
    if let Some(gate) = change.gate {
        body.insert(
            "show_delivery_gate_on_ui_tasks".to_string(),
            serde_json::json!(gate),
        );
    }
    if let Some(on) = change.allow_em_dashes {
        body.insert("allow_em_dashes".to_string(), serde_json::json!(on));
    }
    body
}

/// A route that this PC's backend does not have: a 404, or the 503 an
/// unpatched module answers with `available: false`.
fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_antislop`]'s reading of the answer: the PC's own body, passed on
/// exactly as it came, once it really carries the one thing the page reads it
/// for (`enabled`, a yes or no). `available: false` with [`ANTISLOP_MISSING`]
/// from a PC without the route.
///
/// The rest of the shape is NOT required here. A backend that answers the
/// switch but not the dials yet still paints its switch, and the page's
/// normaliser (`readAntislop`) falls back to its own copy of the words for the
/// half that is absent - which is what keeps an older PC honest instead of
/// blank.
pub(crate) fn view_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("enabled").is_some_and(|e| e.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": ANTISLOP_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A change's answer: the PC's own body on a 2xx (it sends the whole state
/// back), [`ANTISLOP_MISSING`] from a PC without the route, and the PC's own
/// sentence otherwise (400 for a mode it does not know, 409, 401). `enabled`
/// is required as well as an object, because the page words its own line from
/// this reply, so a body without the yes-or-no would have it claim a state the
/// PC never named.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object() && v.get("enabled").is_some_and(|e| e.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(ANTISLOP_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// The whole filter state: `GET /api/antislop`. A read.
#[tauri::command]
pub async fn get_antislop(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{ANTISLOP_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    view_answer(status, &body)
}

/// ONE change to the anti-slop filter - the master switch, one scope, the mode
/// or a dial. BOTH directions apply at once, none of them asks for a card, and
/// none is held on a stale link (see this module's note at the top).
#[tauri::command]
pub async fn set_antislop(app: AppHandle, change: Change) -> Result<serde_json::Value, String> {
    let body = change_body(change);
    if body.is_empty() {
        // Nothing moved. Saying so beats a POST that would rewrite the file
        // with the values it already holds, and it is what the page needs to
        // hear rather than a green "saved" over an empty change.
        return Err("That change did not name anything to change.".to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{ANTISLOP_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::Value::Object(body))
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
        change_answer, change_body, view_answer, Change, Dials, ANTISLOP_MISSING, ANTISLOP_PATH,
    };

    /// The PC's own answer, word for word (`jarvis_antislop.get_state()`, which
    /// the route forwards). Nothing here repaints or renames a word of it.
    const VIEW: &str = r#"{"enabled": false, "mode": "during",
        "scopes": {"copy": true, "code": true, "ui": true},
        "dials": {"energy": 1, "rhythm": 2, "motion": 1},
        "show_delivery_gate_on_ui_tasks": true, "allow_em_dashes": false,
        "updated_at": 1793164200.0}"#;

    fn change(json: &str) -> Change {
        serde_json::from_str::<Change>(json).unwrap()
    }

    #[test]
    fn the_real_view_is_passed_on_unchanged_and_the_route_is_the_agreed_one() {
        let view: serde_json::Value = serde_json::from_str(VIEW).unwrap();
        let got = view_answer(200, VIEW).unwrap();
        assert_eq!(got, view);
        // OFF is the default and it is a real answer, not a missing one.
        assert_eq!(got["enabled"], false);
        assert_eq!(got["mode"], "during");
        assert_eq!(ANTISLOP_PATH, "/api/antislop");
    }

    #[test]
    fn a_master_switch_change_is_exactly_one_json_field() {
        let body = change_body(change(r#"{"enabled": true}"#));
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"enabled": true})
        );
        let body = change_body(change(r#"{"enabled": false}"#));
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"enabled": false})
        );
    }

    #[test]
    fn the_mode_radio_sends_the_mode_and_nothing_else() {
        let body = change_body(change(r#"{"mode": "after"}"#));
        assert_eq!(body.len(), 1, "the mode radio may not drag other fields in");
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"mode": "after"})
        );
    }

    #[test]
    fn one_scope_pill_sends_only_that_scope() {
        let body = change_body(change(r#"{"scope": "code", "on": false}"#));
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"scopes": {"code": false}})
        );
        // A scope with no state is not a change: guessing "on" would flip a
        // pill nobody pressed.
        let body = change_body(change(r#"{"scope": "code"}"#));
        assert!(body.is_empty(), "a scope with no on/off must send nothing");
    }

    #[test]
    fn the_dials_send_only_the_dials_that_moved() {
        let body = change_body(change(r#"{"dials": {"energy": 2}}"#));
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"dials": {"energy": 2}})
        );
        let body = change_body(change(
            r#"{"dials": {"energy": 3, "rhythm": 1, "motion": 2}}"#,
        ));
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"dials": {"energy": 3, "rhythm": 1, "motion": 2}})
        );
        let empty = Change {
            dials: Some(Dials::default()),
            ..Change::default()
        };
        assert!(change_body(empty).is_empty());
    }

    #[test]
    fn every_field_at_once_is_still_one_body_in_the_pcs_own_spelling() {
        let body = change_body(change(
            r#"{"enabled": true, "mode": "during", "scope": "ui", "on": true,
                "dials": {"energy": 1, "rhythm": 3, "motion": 2}, "gate": false,
                "allow_em_dashes": true}"#,
        ));
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({
                "enabled": true,
                "mode": "during",
                "scopes": {"ui": true},
                "dials": {"energy": 1, "rhythm": 3, "motion": 2},
                // The PC's own field names, not a second spelling of either.
                "show_delivery_gate_on_ui_tasks": false,
                "allow_em_dashes": true
            })
        );
    }

    #[test]
    fn the_em_dash_exemption_sends_only_its_own_field() {
        // 2026-10-28: ticking "Allow em-dashes" must never drag a scope, the
        // mode, a dial or the gate along with it - the same promise every other
        // control on this card keeps.
        let body = change_body(change(r#"{"allow_em_dashes": true}"#));
        assert_eq!(
            body.len(),
            1,
            "the em-dash box may not drag other fields in"
        );
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"allow_em_dashes": true})
        );
        let body = change_body(change(r#"{"allow_em_dashes": false}"#));
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"allow_em_dashes": false}),
            "unticking sends the no, not nothing"
        );
    }

    #[test]
    fn the_delivery_gate_switch_sends_the_pcs_own_field_name() {
        let body = change_body(change(r#"{"gate": true}"#));
        assert_eq!(
            body.len(),
            1,
            "the gate switch may not drag other fields in"
        );
        assert_eq!(
            serde_json::Value::Object(body),
            serde_json::json!({"show_delivery_gate_on_ui_tasks": true})
        );
    }

    #[test]
    fn a_pc_without_the_route_says_so_instead_of_claiming_off() {
        let got = view_answer(404, "").unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], ANTISLOP_MISSING);
        let got = view_answer(503, r#"{"available": false, "why": "not installed"}"#).unwrap();
        assert_eq!(got["available"], false);
        // A 2xx that carries no yes-or-no is UNREADABLE, never "off": a state
        // nobody can read is not a filter that is switched off.
        assert!(view_answer(200, r#"{"mode": "during"}"#).is_err());
        assert!(change_answer(200, r#"{"mode": "during"}"#).is_err());
    }

    #[test]
    fn a_change_answer_keeps_the_pcs_own_body_and_its_own_refusal() {
        let view: serde_json::Value = serde_json::from_str(VIEW).unwrap();
        assert_eq!(change_answer(200, VIEW).unwrap(), view);
        // The PC's own sentence for a mode it does not know is what the owner
        // reads - this side does not invent one.
        let said = change_answer(
            400,
            r#"{"ok": false, "error": "mode must be during or after"}"#,
        )
        .unwrap_err();
        assert!(said.contains("during or after"), "{said}");
        assert_eq!(
            change_answer(404, "").unwrap_err(),
            ANTISLOP_MISSING.to_string()
        );
    }
}
