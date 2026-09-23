//! Can the model that will answer actually see a picture?
//!
//! Alt+Shift+S attaches a screen capture to the next question. The image
//! rides inside the user message (see `stream_chat`), and the backend sends
//! it to the LOCAL model - `jarvis_router.choose()` keeps any turn with a
//! picture on this machine, because a screenshot can show anything: an
//! email, a password manager, a bank statement. Rule 1.
//!
//! The local model today is `qwen3:8b` (`backend/jarvis-primary.Modelfile`),
//! which reads text only. Sent a picture, it answers as if there were none,
//! and the owner has no way to know the answer ignored what they showed it.
//! So before a capture is sent, the quickbar asks this module, and when the
//! answer is "no" (or "cannot tell") it says so and offers to send the words
//! alone.
//!
//! HOW IT KNOWS. Two local requests, nothing else:
//!
//! 1. `GET /api/models` on the Jarvis server, for `current` - the model the
//!    local lane will use (the same field Brain -> Faculties shows).
//! 2. `POST /api/show` on Ollama (`OLLAMA_URL`, loopback) with that name.
//!    Ollama answers with `capabilities`, e.g. `["completion", "tools",
//!    "thinking"]`; a picture model also lists `"vision"`. Older Ollama
//!    builds have no `capabilities` field; for those, a `projector_info`
//!    block (the part of a vision model that reads images) counts as yes,
//!    and its absence is "cannot tell", not "no".
//!
//! Nothing is sent anywhere but those two loopback services, and nothing
//! about the picture is sent at all - only the model's name.

use std::time::Duration;

use serde::Serialize;
use tauri::AppHandle;

use crate::commands::{jarvis_base, jarvis_client, jarvis_headers};

/// Both requests are loopback and small. A model that is still loading can
/// make `/api/show` slow; past this, the answer is "cannot tell".
const TIMEOUT: Duration = Duration::from_secs(4);

/// What the quickbar needs to decide whether to send a picture.
#[derive(Debug, Clone, Default, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct VisionCheck {
    /// The model the local lane will use, when the server named one.
    pub model: Option<String>,
    /// `Some(true)`: it can see pictures. `Some(false)`: it cannot.
    /// `None`: could not tell (older Ollama, a server that did not answer).
    pub vision: Option<bool>,
    /// One plain sentence on how that answer was reached, for the notice.
    pub reason: String,
}

/// The current model's name out of `/api/models`. `current` is a string on
/// every backend seen so far; an object with a `name` is accepted too rather
/// than guessed wrong.
pub fn current_model(models: &serde_json::Value) -> Option<String> {
    let current = models.get("current")?;
    let name = current
        .as_str()
        .or_else(|| current.get("name").and_then(|n| n.as_str()))?
        .trim();
    (!name.is_empty()).then(|| name.to_string())
}

/// Whether Ollama's `/api/show` reply describes a model that takes images.
pub fn vision_from_show(show: &serde_json::Value) -> Option<bool> {
    if let Some(caps) = show.get("capabilities").and_then(|c| c.as_array()) {
        return Some(
            caps.iter()
                .filter_map(|c| c.as_str())
                .any(|c| c.eq_ignore_ascii_case("vision")),
        );
    }
    match show.get("projector_info") {
        Some(info) if !info.is_null() => Some(true),
        _ => None,
    }
}

async fn read_current_model(app: &AppHandle, client: &reqwest::Client) -> Result<String, String> {
    let url = format!("{}/api/models", jarvis_base(app));
    let response = client
        .get(&url)
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| format!("the Jarvis server did not answer ({e})"))?;
    if !response.status().is_success() {
        return Err(format!(
            "the Jarvis server would not say which model is loaded (HTTP {})",
            response.status().as_u16()
        ));
    }
    let body: serde_json::Value = response
        .json()
        .await
        .map_err(|e| format!("the model list was not readable ({e})"))?;
    current_model(&body).ok_or_else(|| "the Jarvis server did not name a model".to_string())
}

async fn read_show(client: &reqwest::Client, model: &str) -> Result<serde_json::Value, String> {
    let response = client
        .post(format!("{}/api/show", crate::OLLAMA_URL))
        // `model` is the current field name; `name` is what older Ollama
        // builds read. Sending both costs nothing.
        .json(&serde_json::json!({ "model": model, "name": model }))
        .send()
        .await
        .map_err(|e| format!("Ollama did not answer ({e})"))?;
    if !response.status().is_success() {
        return Err(format!(
            "Ollama would not describe {model} (HTTP {})",
            response.status().as_u16()
        ));
    }
    response
        .json()
        .await
        .map_err(|e| format!("Ollama's answer was not readable ({e})"))
}

/// Asks whether the local model can see pictures. Never fails: every problem
/// becomes `vision: None` with the reason, because the quickbar has to show
/// the owner something either way.
#[tauri::command]
pub async fn local_model_vision(app: AppHandle) -> VisionCheck {
    let client = match jarvis_client(Some(TIMEOUT)) {
        Ok(client) => client,
        Err(reason) => {
            return VisionCheck {
                reason,
                ..VisionCheck::default()
            }
        }
    };
    let model = match read_current_model(&app, &client).await {
        Ok(model) => model,
        Err(reason) => {
            return VisionCheck {
                reason,
                ..VisionCheck::default()
            }
        }
    };
    match read_show(&client, &model).await {
        Ok(show) => {
            let vision = vision_from_show(&show);
            let reason = match vision {
                Some(true) => format!("Ollama lists {model} as able to see pictures."),
                Some(false) => {
                    format!("Ollama lists what {model} can do, and pictures are not on the list.")
                }
                None => {
                    format!("This version of Ollama does not say whether {model} can see pictures.")
                }
            };
            VisionCheck {
                model: Some(model),
                vision,
                reason,
            }
        }
        Err(reason) => VisionCheck {
            model: Some(model),
            vision: None,
            reason,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn current_model_reads_a_string_or_a_name() {
        assert_eq!(
            current_model(&json!({"available": true, "current": "qwen3:8b"})),
            Some("qwen3:8b".to_string())
        );
        assert_eq!(
            current_model(&json!({"current": {"name": "jarvis-primary"}})),
            Some("jarvis-primary".to_string())
        );
        assert_eq!(current_model(&json!({"current": ""})), None);
        assert_eq!(current_model(&json!({"available": false})), None);
    }

    #[test]
    fn a_text_model_is_a_clear_no() {
        // What Ollama answers for qwen3:8b and for jarvis-primary built FROM it.
        let show = json!({"capabilities": ["completion", "tools", "thinking"]});
        assert_eq!(vision_from_show(&show), Some(false));
    }

    #[test]
    fn a_vision_model_is_a_yes() {
        let show = json!({"capabilities": ["completion", "vision"]});
        assert_eq!(vision_from_show(&show), Some(true));
        // An older Ollama with no capabilities list, but a projector.
        let old = json!({"projector_info": {"clip.has_vision_encoder": true}});
        assert_eq!(vision_from_show(&old), Some(true));
    }

    #[test]
    fn no_capabilities_and_no_projector_is_cannot_tell_not_no() {
        assert_eq!(vision_from_show(&json!({"modelfile": "FROM x"})), None);
        assert_eq!(vision_from_show(&json!({"projector_info": null})), None);
    }
}
