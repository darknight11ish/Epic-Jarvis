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
//!
//! THE SECOND GRAPHICS CARD. With its Pictures switch on and working, the
//! backend does NOT send a picture to `current`: it sends it to a picture
//! model (`qwen2.5vl:7b` today) on the second card (docs/SECOND-CARD.md,
//! JARVIS-API.md section 12). The two requests above would still say "cannot
//! see pictures" about `current`, which would be wrong. So a third request
//! comes FIRST: `GET /api/second-card` on the same Jarvis server. If its
//! `vision` row says `available: true`, the answer is yes, and the reason
//! names that model. Anything else - the switch off, the model not
//! installed, an older backend with no such route (404), the module missing
//! (503), no answer - and the check is exactly what it was before.
//!
//! THE WORDS IN A PICTURE (2026-09-26, the owner's "Quick wins"). The same
//! status says whether the PC reads the words in a picture itself when the
//! model cannot see it (`picture_text.available`, backend `jarvis_ocr.py`),
//! and sends them to the model marked as outside text. Then `reads_text` is
//! true and the quickbar sends the picture without asking: the reading and
//! the marking happen on the PC, never here, so an app cannot make the words
//! count as the owner's.

use std::time::Duration;

use serde::Serialize;
use tauri::AppHandle;

use crate::commands::{jarvis_base, jarvis_client, jarvis_headers, SECOND_CARD_PATH};

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
    /// The PC reads the WORDS in a picture itself when the model cannot see
    /// it, and sends them to the model marked as outside text
    /// (`jarvis_ocr.py`, 2026-09-26) - `picture_text.available` in
    /// `GET /api/second-card`. Only ever true when `vision` is not
    /// `Some(true)`: then the quickbar sends the picture without asking.
    pub reads_text: bool,
}

/// Whether the PC says it reads the words in a picture
/// (`status()["picture_text"]["available"]`, exactly `true`). An older
/// backend has no such field: false, and the quickbar asks as before.
pub fn picture_text_available(status: &serde_json::Value) -> bool {
    status
        .get("picture_text")
        .and_then(|p| p.get("available"))
        .and_then(|a| a.as_bool())
        == Some(true)
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

/// The picture model the second card is answering pictures with, out of
/// `GET /api/second-card` (`jarvis_second_card.status()`): the `vision`
/// feature's `model`, but ONLY when that row's `available` is exactly `true`
/// (the switch on, a capable card, the second Ollama running and the model
/// installed). `enabled` or `active` alone is not enough: an enabled switch
/// that is still waiting sends the picture to `current`, as before.
pub fn second_card_picture_model(status: &serde_json::Value) -> Option<String> {
    let row = status
        .get("features")?
        .as_array()?
        .iter()
        .find(|f| f.get("id").and_then(|i| i.as_str()) == Some("vision"))?;
    if row.get("available").and_then(|a| a.as_bool()) != Some(true) {
        return None;
    }
    let model = row
        .get("model")
        .and_then(|m| m.as_str())
        .map(str::trim)
        .filter(|m| !m.is_empty())
        .unwrap_or("the picture model");
    Some(model.to_string())
}

/// The answer when the second card takes pictures.
pub fn second_card_check(model: String) -> VisionCheck {
    VisionCheck {
        reason: format!("Pictures go to {model} on the second graphics card."),
        model: Some(model),
        vision: Some(true),
        reads_text: false,
    }
}

/// Asks the Jarvis server for its second-card status (which also says
/// whether it reads the words in a picture). Every failure is `None` - "not
/// that way" - so the check carries on exactly as it did before the second
/// card existed.
async fn read_second_card_status(
    app: &AppHandle,
    client: &reqwest::Client,
) -> Option<serde_json::Value> {
    let response = client
        .get(format!("{}{SECOND_CARD_PATH}", jarvis_base(app)))
        .headers(jarvis_headers(app).ok()?)
        .send()
        .await
        .ok()?;
    if !response.status().is_success() {
        return None;
    }
    response.json().await.ok()
}

/// The answer about the model, and then whether the PC reads the words in
/// the picture instead - only when the model is not a clear yes.
fn with_picture_text(mut check: VisionCheck, status: Option<&serde_json::Value>) -> VisionCheck {
    check.reads_text = check.vision != Some(true) && status.is_some_and(picture_text_available);
    check
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
    let status = read_second_card_status(&app, &client).await;
    if let Some(model) = status.as_ref().and_then(second_card_picture_model) {
        return second_card_check(model);
    }
    let model = match read_current_model(&app, &client).await {
        Ok(model) => model,
        Err(reason) => {
            return with_picture_text(
                VisionCheck {
                    reason,
                    ..VisionCheck::default()
                },
                status.as_ref(),
            )
        }
    };
    let check = match read_show(&client, &model).await {
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
                reads_text: false,
            }
        }
        Err(reason) => VisionCheck {
            model: Some(model),
            vision: None,
            reason,
            reads_text: false,
        },
    };
    with_picture_text(check, status.as_ref())
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

    /// The real `status()` output (tools/gen_second_card_cases.py) - never
    /// hand-written here.
    const SECOND_CARD: &str = include_str!("../../tests/fixtures/second-card-cases.json");

    fn second_card_cases() -> serde_json::Value {
        serde_json::from_str(SECOND_CARD).expect("second-card-cases.json is JSON")
    }

    /// In every real case the Pictures switch is not working, so the check
    /// must fall through to today's: ask about `current`, as before.
    #[test]
    fn no_real_case_with_pictures_off_claims_the_second_card() {
        let doc = second_card_cases();
        for (name, status) in doc["cases"].as_object().unwrap() {
            let row = status["features"]
                .as_array()
                .unwrap()
                .iter()
                .find(|f| f["id"] == "vision")
                .unwrap_or_else(|| panic!("{name}: no vision row"));
            assert_ne!(row["available"], true, "{name}: the fixture changed");
            assert_eq!(second_card_picture_model(status), None, "{name}");
        }
    }

    /// Pictures working: the `vision` row of a real status with `available`
    /// set true (the only field that differs when the second Ollama is up and
    /// the model is installed). The answer is yes, and names the model and
    /// the card.
    #[test]
    fn pictures_on_the_second_card_are_a_yes_naming_the_model() {
        let doc = second_card_cases();
        let mut status = doc["cases"]["running_long_context"].clone();
        for f in status["features"].as_array_mut().unwrap() {
            if f["id"] == "vision" {
                f["enabled"] = json!(true);
                f["active"] = json!(true);
                f["available"] = json!(true);
                f["model_installed"] = json!(true);
            }
        }
        let model = second_card_picture_model(&status).expect("a picture model");
        assert_eq!(model, "qwen2.5vl:7b");
        let check = second_card_check(model);
        assert_eq!(check.vision, Some(true));
        assert_eq!(check.model.as_deref(), Some("qwen2.5vl:7b"));
        assert_eq!(
            check.reason,
            "Pictures go to qwen2.5vl:7b on the second graphics card."
        );
    }

    /// On-but-waiting is not working: `enabled` and `active` without
    /// `available` sends the picture to `current`, so it must not say yes.
    #[test]
    fn enabled_but_not_available_is_not_a_yes() {
        let doc = second_card_cases();
        let mut status = doc["cases"]["card_missing_but_enabled"].clone();
        let row = status["features"]
            .as_array()
            .unwrap()
            .iter()
            .find(|f| f["id"] == "vision")
            .unwrap()
            .clone();
        assert_eq!(row["enabled"], true, "the fixture changed");
        assert_eq!(second_card_picture_model(&status), None);
        for f in status["features"].as_array_mut().unwrap() {
            if f["id"] == "vision" {
                f["active"] = json!(true);
                f["available"] = json!("true");
            }
        }
        assert_eq!(
            second_card_picture_model(&status),
            None,
            "a string is not true"
        );
    }

    /// An older backend's answers, or none at all, are "not that way".
    #[test]
    fn anything_else_is_not_that_way() {
        assert_eq!(
            second_card_picture_model(&json!({"available": false})),
            None
        );
        assert_eq!(second_card_picture_model(&json!({"features": {}})), None);
        assert_eq!(second_card_picture_model(&json!(null)), None);
        // Working, but no model named: still a yes, in words.
        let bare = json!({"features": [{"id": "vision", "available": true, "model": null}]});
        assert_eq!(
            second_card_picture_model(&bare).as_deref(),
            Some("the picture model")
        );
    }

    /// The PC reads the words in a picture (2026-09-26): read from the real
    /// status; only exactly `true` counts; and a model that can see pictures
    /// never needs it.
    #[test]
    fn the_pc_reading_the_words_is_read_from_the_real_status() {
        let doc = second_card_cases();
        let reads = &doc["cases"]["one_card_reads_words"];
        let not = &doc["cases"]["one_card"];
        assert!(picture_text_available(reads));
        assert!(!picture_text_available(not));
        assert!(!picture_text_available(
            &json!({"picture_text": {"available": "yes"}})
        ));
        assert!(!picture_text_available(&json!({})), "an older backend");
        let blind = VisionCheck {
            model: Some("qwen3:8b".into()),
            vision: Some(false),
            reason: String::new(),
            reads_text: false,
        };
        assert!(with_picture_text(blind.clone(), Some(reads)).reads_text);
        assert!(!with_picture_text(blind.clone(), Some(not)).reads_text);
        assert!(!with_picture_text(blind, None).reads_text);
        let sees = VisionCheck {
            vision: Some(true),
            ..VisionCheck::default()
        };
        assert!(!with_picture_text(sees, Some(reads)).reads_text);
    }
}
