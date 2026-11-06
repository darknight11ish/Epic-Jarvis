//! Settings -> Hands-free mode (2026-11-04, the owner's own request;
//! `backend/jarvis_handsfree.py`, JARVIS-API section 191).
//!
//! Two commands, Settings window only (`permissions/surfaces.toml`):
//!
//! * [`get_handsfree`] - `GET /api/handsfree`: is the mode on, the answer
//!   window, the closed vocabulary, the newest read-out and whether a phone can
//!   take a text. A read, never held.
//! * [`set_handsfree`] - `POST /api/handsfree` `{"enabled": bool}`.
//!
//! **ON raises ONE approval card and the call does not turn the mode on**: the
//! backend answers the moment the card is approved, so this command can be held
//! for as long as a person takes to answer it. The page therefore draws a
//! waiting line rather than flipping the switch optimistically, and re-reads
//! with `get_handsfree` when the call returns. **OFF is immediate and cardless**,
//! and is never held on a stale link either: taking a power away is always safe.
//!
//! Nothing here decides an approval. The card this command raises is answered by
//! a person, on the PC or on the phone, through the same `/api/approve` every
//! other card uses - this module only asks for it.

use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// The one route. Both commands use it; a change is the same path with a POST.
pub(crate) const HANDSFREE_PATH: &str = "/api/handsfree";

/// What a backend without `jarvis_handsfree.py` is told. The page carries the
/// same sentence as its own fallback, so a PC that answers nothing at all still
/// says something true.
pub(crate) const HANDSFREE_MISSING: &str =
    "Your PC's Jarvis does not have hands-free mode yet - run \
                                           apply-patches.ps1 on the PC.";

/// A 2xx whose body this app cannot read. Never drawn as "off": a state that
/// cannot be read is not the same as a mode that is switched off.
const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// ON waits for a person to answer one approval card, so the budget has to be
/// longer than the card's own 15-minute wait would make comfortable here - the
/// card is answered in the app, not inside this request, and the backend returns
/// as soon as it is decided. 20 seconds covers the fast answer; a longer wait is
/// the page's own retry, never a second card (the switch asks only when it is
/// off).
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

/// The read answer, as this app reads it: the fields it draws, and nothing it
/// invents. Every field optional so an older backend that answers only
/// `{"ok": true}` still gives a readable "off".
#[derive(Debug, Default, serde::Deserialize)]
#[serde(default)]
pub struct State {
    pub ok: Option<bool>,
    pub enabled: Option<bool>,
    pub window_sec: Option<u32>,
}

/// The write answer. `message` is the PC's own sentence and is shown as it is;
/// `error` is the gate's refusal when the card was denied.
#[derive(Debug, Default, serde::Deserialize)]
#[serde(default)]
pub struct Change {
    pub ok: Option<bool>,
    pub enabled: Option<bool>,
    pub changed: Option<bool>,
    pub message: Option<String>,
    pub error: Option<String>,
}

/// What the page is handed: the readable state, or a sentence saying why not.
fn view_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if status == 404 {
        return Err(HANDSFREE_MISSING.to_string());
    }
    if !(200..300).contains(&status) {
        return match serde_json::from_str::<Change>(body) {
            Ok(change) if change.error.is_some() => {
                Err(backend_refusal(status, &change.error.unwrap_or_default()))
            }
            _ => Err(backend_refusal(status, "")),
        };
    }
    match serde_json::from_str::<State>(body) {
        Ok(state) if state.ok.unwrap_or(true) => Ok(serde_json::json!({
            "enabled": state.enabled.unwrap_or(false),
            "window_sec": state.window_sec.unwrap_or(60),
        })),
        _ => Err(UNREADABLE.to_string()),
    }
}

/// What a switch call answers: `changed` says whether the mode really moved, so
/// a card that was denied can never be drawn as on.
fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if status == 404 {
        return Err(HANDSFREE_MISSING.to_string());
    }
    match serde_json::from_str::<Change>(body) {
        Ok(change) if (200..300).contains(&status) => {
            if let Some(error) = change.error.as_deref().map(str::trim) {
                if !error.is_empty() {
                    return Err(error.to_string());
                }
            }
            if change.ok.unwrap_or(true) {
                return Ok(serde_json::json!({
                    "enabled": change.enabled.unwrap_or(false),
                    "changed": change.changed.unwrap_or(false),
                    "message": change.message.unwrap_or_default(),
                }));
            }
            Err(change
                .error
                .unwrap_or_else(|| "That did not work.".to_string()))
        }
        Ok(change) => Err(change.error.unwrap_or_else(|| backend_refusal(status, ""))),
        Err(_) => Err(UNREADABLE.to_string()),
    }
}

/// `GET /api/handsfree` - a read. Never raises a card and never decides one.
#[tauri::command]
pub async fn get_handsfree(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{HANDSFREE_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    view_answer(status, &body)
}

/// `POST /api/handsfree {"enabled": bool}`. ON is ONE approval card; the call
/// returns when that card is answered. OFF is immediate.
#[tauri::command]
pub async fn set_handsfree(app: AppHandle, enabled: bool) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{HANDSFREE_PATH}"))
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
    use super::{change_answer, view_answer, HANDSFREE_MISSING};

    #[test]
    fn a_read_is_the_states_own_numbers() {
        let body = r#"{"ok": true, "enabled": true, "window_sec": 60,
                       "vocabulary": {"confirm": ["yes"], "deny": ["no"]},
                       "phone": {"ready": true, "why": ""}, "reading": null}"#;
        let got = view_answer(200, body).expect("readable");
        assert_eq!(got["enabled"], true);
        assert_eq!(got["window_sec"], 60);
    }

    #[test]
    fn an_older_backend_answers_off_and_says_nothing_it_did_not_hear() {
        let got = view_answer(200, r#"{"ok": true}"#).expect("readable");
        assert_eq!(got["enabled"], false);
        assert_eq!(got["window_sec"], 60);
    }

    #[test]
    fn a_denied_card_is_a_sentence_not_an_enabled_mode() {
        let body = r#"{"ok": false, "enabled": false, "error": "the owner said no"}"#;
        let got = change_answer(403, body);
        assert_eq!(got, Err("the owner said no".to_string()));
    }

    #[test]
    fn an_approved_card_says_whether_the_mode_really_moved() {
        let body = r#"{"ok": true, "enabled": true, "changed": true,
                       "message": "Hands-free mode is on."}"#;
        let got = change_answer(200, body).expect("readable");
        assert_eq!(got["enabled"], true);
        assert_eq!(got["changed"], true);
        assert_eq!(got["message"], "Hands-free mode is on.");
    }

    #[test]
    fn a_backend_without_the_module_is_named_in_plain_words() {
        assert_eq!(view_answer(404, ""), Err(HANDSFREE_MISSING.to_string()));
        assert_eq!(change_answer(404, ""), Err(HANDSFREE_MISSING.to_string()));
    }

    #[test]
    fn an_unreadable_answer_is_never_off() {
        assert!(view_answer(200, "not json").is_err());
        assert!(change_answer(200, "not json").is_err());
    }
}
