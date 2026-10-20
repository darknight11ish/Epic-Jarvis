//! Write Like Me (jarvis_voiceprint.py): the desktop bridge for the settings page.
//!
//! NEW FILE, deliberately not registered yet: `src/lib.rs` (mod + generate_handler)
//! is owned by the setup-UI slice until the Lead clears the wiring. The exact
//! hunks are in the PR body, and every command here stays unreachable until then.
//!
//! The four commands are thin: the PC owns the truth (`GET /api/voiceprint`,
//! `POST /api/voiceprint/sample|forget|enabled`), the phone and the desktop render
//! the same words, and nothing here approves a card or applies anything by itself.
//! Each request is bounded to 30 s; the client never follows a redirect (a
//! redirect would carry `X-Jarvis-Token` to wherever it pointed) and never uses a
//! proxy, the same shape `appearance.rs` uses.

use serde::{Deserialize, Serialize};
use tauri::AppHandle;

use crate::commands;
use crate::look;

const LIST: &str = "/api/voiceprint";
const SAMPLE: &str = "/api/voiceprint/sample";
const FORGET: &str = "/api/voiceprint/forget";
const ENABLED: &str = "/api/voiceprint/enabled";

/// Writes are held while the link catches up (CLAUDE.md rule 4): the same
/// sentence every other Settings write uses, and the page greys its controls
/// with the same words. A READ is never held.
const STALE_HELD: &str = "The connection to Jarvis is catching up, so nothing can be sent \
     until it does.";

/// Why one of the three writes may not be sent now, or `None` when it may.
fn held(app: &AppHandle) -> Option<&'static str> {
    if look::stale(app) {
        Some(STALE_HELD)
    } else {
        None
    }
}

/// One sample the owner taught. Text is already stripped by the PC.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Sample {
    pub id: String,
    #[serde(default)]
    pub text: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub prompt: String,
}

/// `GET /api/voiceprint`, in the shape the page and the phone render.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Status {
    #[serde(default)]
    pub available: bool,
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub samples: Vec<Sample>,
    #[serde(default)]
    pub count: i64,
    #[serde(default)]
    pub scrubber: bool,
    #[serde(default)]
    pub message: String,
}

fn client() -> Option<reqwest::Client> {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .ok()
}

fn sample_problem(text: &str) -> Option<String> {
    let t = text.trim();
    if t.is_empty() {
        return Some("Write or paste something first.".into());
    }
    if t.chars().count() > 4000 {
        return Some("That is too long - at most 4000 characters.".into());
    }
    None
}

fn forget_problem(id: &str, confirm: bool) -> Option<String> {
    if id.trim().is_empty() {
        return Some("There is no sample to forget.".into());
    }
    if !confirm {
        return Some("Forgetting a sample asks first: it cannot be undone.".into());
    }
    None
}

/// The command answers the page's exact words; kept pure so the tests can pin it.
fn enabled_body(on: bool) -> serde_json::Value {
    serde_json::json!({ "enabled": on })
}

async fn answer(response: reqwest::Response) -> Result<serde_json::Value, String> {
    let status = response.status();
    let body: serde_json::Value = response
        .json()
        .await
        .map_err(|e| format!("The PC's answer could not be read ({e})."))?;
    if !status.is_success() {
        let why = body
            .get("message")
            .and_then(|v| v.as_str())
            .unwrap_or("The PC refused that.");
        return Err(why.to_string());
    }
    Ok(body)
}

fn send_error(e: reqwest::Error) -> String {
    if e.is_timeout() {
        "The PC did not answer within 30 seconds, so nothing was changed.".into()
    } else {
        "Jarvis Desktop could not reach the PC's style engine. Nothing was changed.".into()
    }
}

#[tauri::command]
pub async fn voiceprint_status(app: AppHandle) -> Result<serde_json::Value, String> {
    let Some(client) = client() else {
        return Err("Could not build an HTTP client.".into());
    };
    let url = format!("{}{LIST}", commands::jarvis_base(&app));
    let response = client
        .get(url)
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(send_error)?;
    answer(response).await
}

#[tauri::command]
pub async fn voiceprint_add(app: AppHandle, text: String, prompt: Option<String>) -> Result<serde_json::Value, String> {
    if let Some(why) = held(&app) {
        return Err(why.to_string());
    }
    if let Some(problem) = sample_problem(&text) {
        return Err(problem);
    }
    let Some(client) = client() else { return Err("Could not build an HTTP client.".into()) };
    let url = format!("{}{SAMPLE}", commands::jarvis_base(&app));
    let response = client
        .post(url)
        .headers(commands::jarvis_headers(&app)?)
        .json(&serde_json::json!({ "text": text, "prompt": prompt.unwrap_or_default() }))
        .send()
        .await
        .map_err(send_error)?;
    answer(response).await
}

#[tauri::command]
pub async fn voiceprint_forget(app: AppHandle, id: String, confirm: bool) -> Result<serde_json::Value, String> {
    if let Some(why) = held(&app) {
        return Err(why.to_string());
    }
    if let Some(problem) = forget_problem(&id, confirm) {
        return Err(problem);
    }
    let Some(client) = client() else { return Err("Could not build an HTTP client.".into()) };
    let url = format!("{}{FORGET}", commands::jarvis_base(&app));
    let response = client
        .post(url)
        .headers(commands::jarvis_headers(&app)?)
        .json(&serde_json::json!({ "id": id, "confirm": true }))
        .send()
        .await
        .map_err(send_error)?;
    answer(response).await
}

/// The local-only ON/OFF switch: no card, no model, one small JSON file on the PC.
/// Held while the link catches up, like the two writes above.
#[tauri::command]
pub async fn voiceprint_set_enabled(app: AppHandle, on: bool) -> Result<serde_json::Value, String> {
    if let Some(why) = held(&app) {
        return Err(why.to_string());
    }
    let Some(client) = client() else { return Err("Could not build an HTTP client.".into()) };
    let url = format!("{}{ENABLED}", commands::jarvis_base(&app));
    let response = client
        .post(url)
        .headers(commands::jarvis_headers(&app)?)
        .json(&enabled_body(on))
        .send()
        .await
        .map_err(send_error)?;
    answer(response).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sample_guard_refuses_empty_and_over_long() {
        assert!(sample_problem("   ").is_some());
        assert!(sample_problem(&"x".repeat(4001)).is_some());
        assert!(sample_problem("A normal message.").is_none());
    }

    #[test]
    fn forget_needs_the_question_answered() {
        assert!(forget_problem("vp1", false).is_some());
        assert!(forget_problem("", true).is_some());
        assert!(forget_problem("vp1", true).is_none());
    }

    #[test]
    fn the_switch_sends_exactly_on() {
        assert_eq!(enabled_body(true), serde_json::json!({ "enabled": true }));
        assert_eq!(enabled_body(false), serde_json::json!({ "enabled": false }));
    }
}
