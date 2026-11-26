//! The typed answer's layout (2026-11-25): "if atlas has a long response can
//! it be put with bullet points". One route, `GET`/`POST /api/answer-style`
//! (`jarvis_answer_style.py`; the module installs it through its own drop-in
//! folder, so no patch carries this feature).
//!
//! Two commands:
//!
//! * [`get_answer_style`] - `GET /api/answer-style`: the three choices with the
//!   PC's own labels and reasons, and the one in force. A read, never held,
//!   never a card.
//! * [`set_answer_style`] - `POST /api/answer-style {"style": "auto" |
//!   "bullets" | "prose"}`: ONE change, cardless in both directions - it
//!   changes only how a TYPED answer is laid out. A SPOKEN answer is never
//!   bulleted (its own note forbids lists), and the value is the PC's own, so
//!   a chat sentence changes the same thing this picker shows.
//!
//! A MODEL ANSWER CAN NEVER CHANGE IT: there is no model tool for this
//! feature, and the only writers are this command and the deterministic chat
//! sentences in `jarvis_quick.py`.

use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// The one route. Both commands use it; a change is the same path as a POST.
pub(crate) const ANSWER_STYLE_PATH: &str = "/api/answer-style";

/// What a backend without `jarvis_answer_style.py` is told. The Settings page
/// carries the same sentence as its own fallback, so a PC that answers nothing
/// at all still says something true.
pub(crate) const ANSWER_STYLE_MISSING: &str =
    "Your PC's Jarvis has no answer-layout setting yet - \
                                              run apply-patches.ps1 on the PC.";

/// A 2xx whose body this app cannot read. Never drawn as a chosen style: a
/// state that cannot be read is not the same as one that is.
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

/// [`get_answer_style`]'s reading of the answer: the PC's own body, once it
/// really carries what the picker draws (`style`, a name, and `choices`, a
/// list). `available: false` with [`ANSWER_STYLE_MISSING`] from a PC without
/// the route.
pub(crate) fn view_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| {
                v.get("style").is_some_and(|s| s.is_string())
                    && v.get("choices").is_some_and(|c| c.is_array())
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": ANSWER_STYLE_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A change's answer: the PC's own body on a 2xx, [`ANSWER_STYLE_MISSING`] from
/// a PC without the route, and the PC's own sentence otherwise. `style` and
/// `said` are required, because the page words its line from this reply - a
/// body without them would have it claim a state the PC never named.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| {
                v.is_object()
                    && v.get("style").is_some_and(|s| s.is_string())
                    && v.get("said").is_some_and(|s| s.is_string())
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(ANSWER_STYLE_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// The setting as it stands: `GET /api/answer-style`. A read.
#[tauri::command]
pub async fn get_answer_style(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{ANSWER_STYLE_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    view_answer(status, &body)
}

/// ONE change: how a typed answer is laid out. Cardless both ways.
#[tauri::command]
pub async fn set_answer_style(app: AppHandle, style: String) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{ANSWER_STYLE_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "style": style }))
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    change_answer(status, &body)
}

#[cfg(test)]
mod tests {
    use super::{change_answer, view_answer, ANSWER_STYLE_MISSING, ANSWER_STYLE_PATH};

    /// The PC's own answer, word for word (`jarvis_answer_style.state()`).
    const VIEW: &str = r#"{"ok": true, "style": "auto", "title": "Long answers",
        "detail": "When an answer has several parts...", "default": "auto",
        "choices": [{"id": "auto", "label": "Bullet points when it helps (default)",
                     "why": "..."}]}"#;

    #[test]
    fn the_real_view_is_passed_on_unchanged_and_the_route_is_the_agreed_one() {
        let view: serde_json::Value = serde_json::from_str(VIEW).unwrap();
        let got = view_answer(200, VIEW).unwrap();
        assert_eq!(got, view);
        assert_eq!(ANSWER_STYLE_PATH, "/api/answer-style");
    }

    #[test]
    fn a_missing_module_is_said_in_words_not_read_as_a_style() {
        let got = view_answer(404, "{}").unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], ANSWER_STYLE_MISSING);
        assert_eq!(change_answer(404, "{}").unwrap_err(), ANSWER_STYLE_MISSING);
    }

    #[test]
    fn an_unreadable_body_is_never_read_as_a_chosen_style() {
        assert!(view_answer(200, r#"{"style": "auto"}"#).is_err());
        assert!(view_answer(200, r#"{"choices": []}"#).is_err());
        // ... and a change's reply must carry the style and the PC's sentence
        // before the page words a success line from it.
        assert!(change_answer(200, r#"{"ok": true}"#).is_err());
        let ok = change_answer(
            200,
            r#"{"style": "bullets", "said": "Answers with more than one part now come as bullet points."}"#,
        )
        .unwrap();
        assert_eq!(ok["style"], "bullets");
    }
}
