//! Plain words when something goes wrong, and "How Jarvis talks" (the
//! creativity audit, 2026-09-25: item 5, and the owner's manner decision).
//!
//! The words themselves live in ONE list, `tools/gen_plain_error_cases.py`,
//! written to `tests/fixtures/plain-error-cases.json` (and a byte-identical
//! copy the phone reads). The page's `src/plain-errors.js` holds all of them;
//! the Rust side says only the three a request that never reached Jarvis can
//! end in ([`unreachable_words`]), and tags a failed chat so the page can
//! pick the words itself ([`chat_failure`]). The tests below fail if a word
//! here differs from the file.
//!
//! Two commands for Settings -> "How Jarvis talks" (backend/manner.patch,
//! jarvis_manner.py; JARVIS-API.md section 27), settings window only:
//!
//! * [`get_manner`] - `GET /api/manner`: "warm" (the default) or "plain",
//!   with the PC's own words for both.
//! * [`set_manner`] - `POST /api/manner {"manner": ...}`: at once, NO
//!   approval card either way - it changes only how answers are worded,
//!   never what Jarvis does, asks, remembers or sends. Held on a stale link
//!   all the same (rule 4: nothing is sent while the link is stale).
//!
//! And one for the quickbar: [`open_fix_place`] opens Settings or the Brain
//! when the owner presses an error's fix button ("Check the connection
//! settings", "Choose a model"). It opens a window and nothing else; the
//! app lock still applies (windows.rs).

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// `jarvis_not_running`: nothing listens at the address (connection refused).
pub(crate) const NOT_RUNNING_SAYS: &str = "Jarvis isn't running on your PC.";
pub(crate) const NOT_RUNNING_FIX: &str = "The PC is on, but Jarvis is not started. On the PC, \
     open Jarvis Desktop's Settings, then More options, and press Start under \"Starting Jarvis \
     for you\" (it needs \"Let Jarvis Desktop start and stop Jarvis\" on). Or start it in \
     PowerShell, the way you set it up. Then try again.";
/// `timeout`: connected, then no answer in time.
pub(crate) const TIMEOUT_SAYS: &str = "Jarvis took too long to answer.";
pub(crate) const TIMEOUT_FIX: &str =
    "Try again in a moment. If it keeps happening, restart Ollama on the PC.";
/// `connection_dropped`: the request broke on the way.
pub(crate) const DROPPED_SAYS: &str = "The connection to your PC dropped.";
pub(crate) const DROPPED_FIX: &str =
    "Try again. If it keeps happening, check the private network is steady at both ends.";

/// `key_store_refused`: Credential Manager would not save a key.
pub(crate) const KEY_STORE_SAYS: &str = "Windows Credential Manager wouldn't save it.";
pub(crate) const KEY_STORE_FIX: &str = "Nothing was written anywhere else. Try again; if it \
     keeps failing, restart the PC and try once more.";

/// The sentence for a key Credential Manager refused, with its reason (a
/// code from Windows, never the key) for a bug report.
pub(crate) fn key_store_words(reason: &str) -> String {
    format!("{KEY_STORE_SAYS} {KEY_STORE_FIX} (Details: {reason}.)")
}

/// Starts a failed chat's one line, instead of a sentence: what the page
/// needs to pick the plain words (plain-errors.js `fromChatFailure`). A
/// unit-separator control character never starts a real sentence.
pub const ERROR_LINE_PREFIX: &str = "\u{1f}jarvis-error:";

/// The network failure's kind, in the contract file's words.
pub(crate) fn network_kind(is_connect: bool, is_timeout: bool) -> &'static str {
    if is_connect && is_timeout {
        "connect_timeout"
    } else if is_connect {
        "refused"
    } else if is_timeout {
        "read_timeout"
    } else {
        "dropped"
    }
}

/// The sentence for a request that never got an answer from Jarvis.
pub(crate) fn unreachable_words(is_connect: bool, is_timeout: bool) -> String {
    let (says, fix) = match network_kind(is_connect, is_timeout) {
        "refused" | "connect_timeout" => (NOT_RUNNING_SAYS, NOT_RUNNING_FIX),
        "read_timeout" => (TIMEOUT_SAYS, TIMEOUT_FIX),
        _ => (DROPPED_SAYS, DROPPED_FIX),
    };
    format!("{says} {fix}")
}

/// A failed chat, as the one tagged line the page reads: the network kind
/// or the HTTP status, the PC's own sentence when it sent one, and the
/// technical detail for the page's "Details" (which it scrubs).
pub(crate) fn chat_failure(
    network: Option<&str>,
    http: Option<u16>,
    said: Option<&str>,
    detail: &str,
) -> String {
    let mut out = serde_json::Map::new();
    if let Some(n) = network {
        out.insert("network".into(), serde_json::json!(n));
    }
    if let Some(code) = http {
        out.insert("http".into(), serde_json::json!(code));
    }
    if let Some(s) = said.map(str::trim).filter(|s| !s.is_empty()) {
        out.insert("said".into(), serde_json::json!(s));
    }
    // Bounded: a whole HTML error page is not a detail.
    let detail: String = detail.chars().take(1000).collect();
    out.insert("detail".into(), serde_json::json!(detail));
    format!("{ERROR_LINE_PREFIX}{}", serde_json::Value::Object(out))
}

const MANNER_PATH: &str = "/api/manner";
const MANNERS: [&str; 2] = ["warm", "plain"];
const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

/// What a backend without jarvis_manner.py is told. The phone says the same.
pub(crate) const MANNER_MISSING: &str =
    "Your PC's Jarvis does not have this setting yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || code == 501
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_manner`]'s reading of the answer, tested against the contract file.
pub(crate) fn manner_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("choices").is_some_and(|c| c.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": MANNER_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// The body of the one change: "warm" or "plain", nothing else.
pub(crate) fn manner_body(manner: &str) -> Result<serde_json::Value, String> {
    if !MANNERS.contains(&manner) {
        return Err("That is not one of the two choices.".to_string());
    }
    Ok(serde_json::json!({ "manner": manner }))
}

/// "How Jarvis talks": `GET /api/manner`.
#[tauri::command]
pub async fn get_manner(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{MANNER_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    manner_answer(status, &body)
}

/// Warm or plain, at once, with no card. Held on a stale link.
#[tauri::command]
pub async fn set_manner(app: AppHandle, manner: String) -> Result<serde_json::Value, String> {
    let body = manner_body(&manner)?;
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{MANNER_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&body)
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
        return Err(MANNER_MISSING.to_string());
    }
    Err(backend_refusal(status, &text))
}

/// The place an error's fix button opens: "settings" or "brain". Nothing
/// else is accepted.
#[tauri::command]
pub fn open_fix_place(app: AppHandle, place: String) -> Result<(), String> {
    match place.as_str() {
        "settings" => crate::windows::show_settings(&app),
        "brain" => crate::windows::show_brain(&app),
        _ => Err("That is not a place this button opens.".to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The one list of words, made by `tools/gen_plain_error_cases.py`.
    const CASES: &str = include_str!("../../tests/fixtures/plain-error-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("plain-error-cases.json is JSON")
    }

    fn words(kind: &str) -> (String, String) {
        let doc = cases();
        let k = &doc["kinds"][kind];
        (
            k["says"].as_str().expect("says").to_string(),
            k["fix"].as_str().expect("fix").to_string(),
        )
    }

    #[test]
    fn the_rust_words_are_the_contract_words() {
        assert_eq!(
            words("jarvis_not_running"),
            (NOT_RUNNING_SAYS.into(), NOT_RUNNING_FIX.into())
        );
        assert_eq!(words("timeout"), (TIMEOUT_SAYS.into(), TIMEOUT_FIX.into()));
        assert_eq!(
            words("connection_dropped"),
            (DROPPED_SAYS.into(), DROPPED_FIX.into())
        );
        assert_eq!(
            words("key_store_refused"),
            (KEY_STORE_SAYS.into(), KEY_STORE_FIX.into())
        );
    }

    #[test]
    fn a_network_failure_is_classified_as_the_contract_says() {
        let doc = cases();
        for case in doc["classify"].as_array().expect("classify") {
            let Some(net) = case["input"]["network"].as_str() else {
                continue;
            };
            let flags = match net {
                "refused" => (true, false),
                "connect_timeout" => (true, true),
                "read_timeout" => (false, true),
                "dropped" => (false, false),
                _ => continue, // names and routes: the phone's
            };
            assert_eq!(network_kind(flags.0, flags.1), net);
        }
    }

    #[test]
    fn the_chat_failure_line_carries_facts_not_words() {
        let line = chat_failure(Some("refused"), None, None, "error sending request");
        let json = line.strip_prefix(ERROR_LINE_PREFIX).expect("tagged");
        let v: serde_json::Value = serde_json::from_str(json).expect("json");
        assert_eq!(v["network"], "refused");
        assert!(v.get("said").is_none());
        let line = chat_failure(None, Some(503), Some("  the model is loading "), "x");
        let v: serde_json::Value =
            serde_json::from_str(line.strip_prefix(ERROR_LINE_PREFIX).unwrap()).unwrap();
        assert_eq!(v["http"], 503);
        assert_eq!(v["said"], "the model is loading");
    }

    #[test]
    fn manner_choices_and_bodies() {
        assert!(manner_body("warm").is_ok());
        assert!(manner_body("plain").is_ok());
        assert!(manner_body("rude").is_err());
        let doc = cases();
        let ids: Vec<&str> = doc["manner"]["choices"]
            .as_array()
            .expect("choices")
            .iter()
            .map(|c| c["id"].as_str().unwrap())
            .collect();
        assert_eq!(ids, MANNERS);
        assert!(manner_answer(404, "").unwrap()["available"] == false);
        assert!(manner_answer(200, "{}").is_err());
    }
}
