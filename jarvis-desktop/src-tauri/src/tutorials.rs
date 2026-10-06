//! Brain -> Tutorials and the FAQ (JARVIS-API section 114,
//! backend/jarvis_tutorials.py, docs/TUTORIALS-DESIGN.md): one catalogue for
//! the PC and the phone, and the owner's reading progress, kept on the PC.
//!
//! Three commands, Brain only:
//!
//! * [`get_tutorials`] - `GET /api/tutorials`, optionally one `section`.
//! * [`mark_tutorial`] - `POST /api/tutorials/progress {"id","state","step"}`:
//!   where the owner has read to, so closing the page and coming back offers to
//!   continue instead of starting again. It acts on nothing, so it is NOT held
//!   on a stale link and raises NO card - it is the owner marking their own
//!   reading, and a card per "Next" would be absurd.
//! * [`get_faq`] - `GET /api/faq`.
//!
//! The token goes out in `X-Jarvis-Token`, with `X-Jarvis-Client: hud`, through
//! [`jarvis_headers`], and is never logged or put in an error. Nothing here
//! keeps a copy of the answers: they are the backend's, passed on as they are.

use std::time::Duration;

use serde_json::{json, Value};
use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// `GET` here; the progress `POST` is under it.
pub(crate) const TUTORIALS_PATH: &str = "/api/tutorials";
pub(crate) const TUTORIALS_PROGRESS_PATH: &str = "/api/tutorials/progress";
pub(crate) const FAQ_PATH: &str = "/api/faq";

/// One page's worth of text. Well under the phone's 20-second limit for a read.
const TUTORIALS_TIMEOUT: Duration = Duration::from_secs(10);

/// What a backend without `jarvis_tutorials.py` is told to do about it.
pub(crate) const TUTORIALS_UPDATE: &str = "This PC's Jarvis does not have the tutorials yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// The states the route accepts - the backend's own `STATES`, plus
/// `not_started`, which is how "Show this one again" clears the record.
const STATES: [&str; 4] = ["in_progress", "done", "skipped", "not_started"];

/// The backend's answer, or a plain sentence about why there is not one.
/// `want` is the key every answer of this kind must carry, so a proxy or an
/// old backend cannot be mistaken for a real answer.
pub(crate) fn tutorials_answer(status: u16, body: &str, want: &str) -> Result<Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<Value>(body)
            .ok()
            .filter(|v| v.get(want).is_some())
            .ok_or_else(|| {
                "Jarvis answered, but not in a way this app can read. \
                 Update the backend by running apply-patches.ps1."
                    .to_string()
            });
    }
    // No such route: the owner's backend predates this feature. That is not an
    // error to shout about, it is a thing to do (run the patcher).
    if status == 404 || status == 501 {
        return Ok(json!({ "available": false, "why": TUTORIALS_UPDATE }));
    }
    Err(backend_refusal(status, body))
}

/// "Tutorials": `GET /api/tutorials`, with the owner's place in each of them.
#[tauri::command]
pub async fn get_tutorials(app: AppHandle, section: Option<String>) -> Result<Value, String> {
    // Only the two real sections are passed on; anything else asks for all of
    // them, which is what the page does when it wants both lists.
    let path = match section.as_deref() {
        Some(which @ ("pc" | "phone")) => format!("{TUTORIALS_PATH}?section={which}"),
        _ => TUTORIALS_PATH.to_string(),
    };
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(TUTORIALS_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    tutorials_answer(status, &body, "tutorials")
}

/// Where the owner has read to. No card, no stale-link hold: it acts on nothing.
#[tauri::command]
pub async fn mark_tutorial(
    app: AppHandle,
    id: String,
    state: String,
    step: Option<u32>,
) -> Result<Value, String> {
    if id.trim().is_empty() {
        return Err("No tutorial was named.".to_string());
    }
    if !STATES.contains(&state.as_str()) {
        return Err("That is not one of the ways a tutorial can be marked.".to_string());
    }
    let base = jarvis_base(&app);
    let body = json!({ "id": id, "state": state, "step": step.unwrap_or(0) });
    let response = jarvis_client(Some(TUTORIALS_TIMEOUT))?
        .post(format!("{base}{TUTORIALS_PROGRESS_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    tutorials_answer(status, &text, "ok")
}

/// The questions and answers, in the backend's own order.
#[tauri::command]
pub async fn get_faq(app: AppHandle) -> Result<Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(TUTORIALS_TIMEOUT))?
        .get(format!("{base}{FAQ_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    tutorials_answer(status, &body, "questions")
}
