//! Settings -> "Accounts", the ADDRESS half (the owner's decision of
//! 2026-10-06: "anything needing a key or a sign-in should be settable in the
//! Jarvis app itself, desktop only, stored under rule 3";
//! backend/accounts.patch, backend/jarvis_accounts.py).
//!
//! The same card already collects four SECRETS - the IMAP username, the IMAP
//! password, the private calendar link and the Home Assistant token - through
//! [`crate::account_secrets`], which writes them straight into Windows
//! Credential Manager on this PC and never sends them anywhere. It collected
//! no server ADDRESS at all, so email answered "JARVIS_IMAP_HOST is not set -
//! there is no mail server to read" and Home Assistant answered "not set up on
//! this PC": the addresses could only be plain-text Windows environment
//! variables.
//!
//! An ADDRESS (or a choice) is the other shape, and it already has a proven
//! model in this tree: `jarvis_search.py`'s `<config>/web-search.json` with
//! `POST /api/search/settings` ([`crate::web_search`]). So these two commands
//! are the same shape as that one - the backend route owns the file, and this
//! side only asks for it. There is a code-proven reason not to put an address
//! in Credential Manager: a store-sourced value is redacted BY EXACT VALUE,
//! which would swallow harmless surrounding text such as a host name
//! (backend/test_account_secrets.py's own first bullet).
//!
//! Two commands, Settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_account_addresses`] - `GET /api/accounts/addresses`: the eight, in
//!   the PC's order, each with the environment variable it has always been
//!   read under and whether that variable is already set on this PC. An
//!   environment variable's VALUE never comes back - only whether it wins.
//! * [`save_account_address`] - `POST /api/accounts/addresses` with ONE
//!   change. Held while the event stream is stale, like every other change
//!   sent to the PC. The backend refuses any name but the eight, so nothing
//!   this command can send puts a key, a password or a token in a plain-text
//!   file (CLAUDE.md rule 3) - and this side refuses first, before the
//!   request is even built.
//!
//! BACKWARD COMPATIBILITY: the environment variable, if the owner already has
//! one, keeps winning on the backend whatever is or is not saved here.
//! Saving here never overwrites or clears one, and this page cannot either.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// One path, read and written: the addresses are one record, not a list.
pub(crate) const ADDRESSES_PATH: &str = "/api/accounts/addresses";

/// The eight, in the PC's order - `jarvis_accounts.FIELDS`, and the only
/// names this side will send. A SECRET is deliberately not one of them.
pub(crate) const FIELDS: [&str; 8] = [
    "imap_host",
    "imap_port",
    "imap_mailbox",
    "smtp_host",
    "smtp_port",
    "smtp_tls",
    "home_url",
    "caldav_url",
];

/// What a PC without `jarvis_accounts.py` is told to do about it.
pub(crate) const ADDRESSES_MISSING: &str = "Your PC's Jarvis does not have the account \
     addresses yet - run apply-patches.ps1 on the PC.";

const STALE: &str = "The connection to Jarvis is catching up, so nothing can be sent until \
                     it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_account_addresses`]'s reading of the answer: the PC's own object
/// when it has one and it holds the eight.
pub(crate) fn addresses_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("fields").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": ADDRESSES_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A POST's answer: the PC's object as it is; a refusal is the PC's own
/// sentence.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(ADDRESSES_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// The body of ONE change: `{"<name>": "<value>"}`.
///
/// The name must be one of the eight - checked HERE, before anything is sent,
/// so this command has no way to ask the backend to store a secret even if
/// the backend's own whitelist were ever loosened by mistake. The value is
/// trimmed and length-capped, and "" is allowed: it means "not set here",
/// which is how the owner clears one.
pub(crate) fn change_body(name: &str, value: &str) -> Result<serde_json::Value, String> {
    if !FIELDS.contains(&name) {
        return Err("That is not one of the account addresses.".to_string());
    }
    let value = value.trim();
    if value.len() > 200 {
        return Err("That address is too long.".to_string());
    }
    let mut map = serde_json::Map::new();
    map.insert(
        name.to_string(),
        serde_json::Value::String(value.to_string()),
    );
    Ok(serde_json::Value::Object(map))
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

/// The eight addresses and choices, and whether each is already set as an
/// environment variable on this PC: `GET /api/accounts/addresses`.
#[tauri::command]
pub async fn get_account_addresses(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{ADDRESSES_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    addresses_answer(status, &body)
}

/// ONE address saved on this PC (`""` clears it here). Held on a stale link.
/// An environment variable the owner already set still wins, on every read.
#[tauri::command]
pub async fn save_account_address(
    app: AppHandle,
    name: String,
    value: String,
) -> Result<serde_json::Value, String> {
    let body = change_body(&name, &value)?;
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{ADDRESSES_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    change_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::{addresses_answer, change_body, ADDRESSES_MISSING, FIELDS};

    #[test]
    fn only_the_eight_names_can_be_sent() {
        for name in FIELDS {
            let body = change_body(name, "x.example.com").expect(name);
            assert_eq!(body[name], "x.example.com");
            assert_eq!(body.as_object().unwrap().len(), 1);
        }
    }

    #[test]
    fn a_secret_is_refused_before_anything_is_sent() {
        for name in [
            "imap_password",
            "imap_user",
            "home_token",
            "calendar_ics_url",
            "tavily_key",
            "password",
            "token",
            "anything_at_all",
        ] {
            assert!(change_body(name, "hunter2").is_err(), "{name}");
        }
    }

    #[test]
    fn the_value_is_trimmed_and_capped_and_empty_means_cleared() {
        assert_eq!(
            change_body("imap_host", "  a.example.com ").unwrap()["imap_host"],
            "a.example.com"
        );
        assert_eq!(change_body("imap_host", "").unwrap()["imap_host"], "");
        assert!(change_body("imap_host", &"x".repeat(201)).is_err());
        assert!(change_body("imap_host", &"x".repeat(200)).is_ok());
    }

    #[test]
    fn a_pc_without_it_says_so_and_refusals_are_the_pcs_words() {
        for code in [404u16, 503] {
            let got = addresses_answer(code, r#"{"available": false}"#).unwrap();
            assert_eq!(got["why"], ADDRESSES_MISSING);
        }
        let err = change_body("imap_password", "hunter2").unwrap_err();
        assert!(err.contains("not one of the account addresses"), "{err}");
        assert!(!err.contains("hunter2"), "the value is in the error");
    }

    #[test]
    fn an_answer_without_the_eight_is_not_believed() {
        assert!(addresses_answer(200, r#"{"available": true}"#).is_err());
        let ok = addresses_answer(200, r#"{"available": true, "fields": []}"#).unwrap();
        assert!(ok["fields"].is_array());
    }
}
