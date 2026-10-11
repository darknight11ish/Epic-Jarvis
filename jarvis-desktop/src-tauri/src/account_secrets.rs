//! Settings -> "Accounts" (ease-of-use audit row 15, "Security G3";
//! JARVIS-API.md section 44; `backend/jarvis_token_store.resolve_secret`,
//! `jarvis_email.py`, `jarvis_calendar.py`, `jarvis_home.py`).
//!
//! The IMAP username and password, the private calendar link, and the Home
//! Assistant token used to be set only as plain Windows user environment
//! variables - which Windows itself stores as plain text (`[Environment]::
//! SetEnvironmentVariable`, `backend/README.md`'s own PowerShell lines). This
//! gives each its own box in Settings, written straight into Windows
//! Credential Manager on this PC - never sent over HTTP to the backend, and
//! never to the phone, exactly like [`crate::web_search`]'s Exa/Tavily/Brave
//! key boxes.
//!
//! Three commands, Settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_account_secrets`] - a read: for each of the four, whether the
//!   matching environment variable is already set on this PC (never its
//!   value - `account_secret_env_set`), and, when it is not, whether
//!   Credential Manager holds one (`account_secret_saved`). No backend
//!   route is involved: both checks are made on this PC alone, the same way
//!   [`crate::web_search::save_search_key`] never touches the backend either.
//! * [`save_account_secret`] - one value into Credential Manager
//!   ([`crate::token_store::write_account_secret`]), after
//!   [`crate::token_store::account_secret_problem`]'s check. Returns words
//!   only - never the value, and never even echoes whether the environment
//!   variable would still win (the page already knows that from the last
//!   [`get_account_secrets`]).
//! * [`forget_account_secret`] - removes one from Credential Manager
//!   ([`crate::token_store::delete_account_secret`]). Never touches the
//!   environment variable - there is no way to unset another program's
//!   environment variable from here, and the page says so.
//!
//! BACKWARD COMPATIBILITY, said again where the desktop enforces its half:
//! the environment variable, if the owner already has one, keeps winning on
//! the backend (`resolve_secret`'s own rule) whatever is or is not saved
//! here - saving a value here never overwrites or clears it, and this page
//! cannot either.
//!
//! # The six chatbot API keys (2026-10-06)
//!
//! `docs/ACCOUNT-KEYS-DESIGN.md` steps 1-2, the owner's decision 1: "keys
//! and limits together". The chatbot driver's six API services (OpenAI,
//! DeepSeek, Mistral, xAI, OpenRouter, Groq) used to be settable only from
//! the PC's own command line - `py -3 jarvis_chatbot_api.py key <service>` -
//! and this app never mentioned them at all. The same three commands, in the
//! same shape, now cover their keys:
//!
//! * [`get_chatbot_api_keys`] - for each of the six, whether Credential
//!   Manager holds a key (never the key).
//! * [`save_chatbot_api_key`] / [`forget_chatbot_api_key`] - one key into (or
//!   out of) Credential Manager on this PC.
//!
//! Two differences from the four account secrets, both deliberate:
//!
//! * **No environment variable wins here.** `jarvis_chatbot_api.py` has
//!   never read one for a key (its own docstring: "No environment variable,
//!   no file, no new store"), so the status answer always carries
//!   `env_set: false` and a box is never disabled for that reason.
//! * **No approval card**, matching the Accounts page above and
//!   `docs/JARVIS-API.md:8471-8475`: saving the owner's own key for the
//!   owner's own account is the owner configuring their own accounts. It is
//!   the *money limit* that raises a card, and that is a separate route.
//!
//! Rule 3 is the whole point of the shape: the key is typed here, written
//! straight into Credential Manager by [`crate::token_store`], and never
//! sent over HTTP, never to the phone, and never shown again. There is no
//! backend route for a key, on purpose - `jarvis_chatbot_api.save_key`'s own
//! docstring says so, and `backend/test_chatbot_keys.py` fails if one
//! appears.

use crate::token_store;

/// One secret's status for the page: never the value.
fn status(name: &str) -> serde_json::Value {
    let env_set = token_store::account_secret_env_set(name).unwrap_or(false);
    // Credential Manager is not even asked when the environment variable
    // already wins - matching what the backend actually does.
    let saved = if env_set {
        None
    } else {
        token_store::account_secret_saved(name).ok().flatten()
    };
    serde_json::json!({
        "name": name,
        "env_set": env_set,
        "saved": saved,
    })
}

/// The four secrets' status: `GET`-shaped, but never leaves this PC.
#[tauri::command]
pub async fn get_account_secrets() -> Result<serde_json::Value, String> {
    let secrets: Vec<serde_json::Value> = token_store::ACCOUNT_SECRET_TARGETS
        .iter()
        .map(|(name, _, _)| status(name))
        .collect();
    Ok(serde_json::json!({ "secrets": secrets }))
}

/// Saves one of the four secrets in Credential Manager on this PC. Returns
/// words only - never the value.
#[tauri::command]
pub async fn save_account_secret(name: String, value: String) -> Result<serde_json::Value, String> {
    if token_store::account_secret_target(&name).is_none() {
        return Err("That is not one of the four account secrets.".to_string());
    }
    if let Some(why) = token_store::account_secret_problem(&name, &value) {
        return Err(why.to_string());
    }
    token_store::write_account_secret(&name, &value)
        .map_err(|e| crate::plain_errors::key_store_words(&e.to_string()))?;
    Ok(serde_json::json!({
        "ok": true,
        "said": "Saved in Windows Credential Manager on this PC. Quit Jarvis Desktop from \
                 the tray icon and start it again so the backend picks it up.",
    }))
}

/// Removes one of the four secrets from Credential Manager on this PC. Never
/// touches an environment variable of the same name.
#[tauri::command]
pub async fn forget_account_secret(name: String) -> Result<serde_json::Value, String> {
    if token_store::account_secret_target(&name).is_none() {
        return Err("That is not one of the four account secrets.".to_string());
    }
    token_store::delete_account_secret(&name).map_err(|e| format!("Not removed: {e}."))?;
    Ok(serde_json::json!({
        "ok": true,
        "said": "Removed from Windows Credential Manager on this PC.",
    }))
}

/// One chatbot service's status for the page: never the key itself.
fn chatbot_status(service: &str) -> serde_json::Value {
    // There is no environment variable for a chatbot API key (the module
    // note above), so this is always false - kept in the answer so the page
    // reads one shape for both kinds of box.
    let saved = token_store::chatbot_api_key_saved(service).ok().flatten();
    serde_json::json!({
        "service": service,
        "env_set": false,
        "saved": saved,
    })
}

/// The six chatbot API keys' status: `GET`-shaped, but never leaves this PC.
#[tauri::command]
pub async fn get_chatbot_api_keys() -> Result<serde_json::Value, String> {
    let services: Vec<serde_json::Value> = token_store::CHATBOT_API_KEY_TARGETS
        .iter()
        .map(|(service, company)| {
            let mut row = chatbot_status(service);
            row["company"] = serde_json::json!(company);
            row
        })
        .collect();
    Ok(serde_json::json!({ "services": services }))
}

/// Saves one chatbot API key in Credential Manager on this PC. Returns words
/// only - never the key.
#[tauri::command]
pub async fn save_chatbot_api_key(
    service: String,
    value: String,
) -> Result<serde_json::Value, String> {
    if token_store::chatbot_api_service(&service).is_none() {
        return Err("That is not one of the six chatbot services.".to_string());
    }
    if let Some(why) = token_store::chatbot_api_key_problem(&value) {
        return Err(why.to_string());
    }
    token_store::write_chatbot_api_key(&service, &value)
        .map_err(|e| crate::plain_errors::key_store_words(&e.to_string()))?;
    Ok(serde_json::json!({
        "ok": true,
        "said": "Saved in Windows Credential Manager on this PC. Quit Jarvis Desktop from \
                 the tray icon and start it again so the backend picks it up.",
    }))
}

/// Removes one chatbot API key from Credential Manager on this PC.
#[tauri::command]
pub async fn forget_chatbot_api_key(service: String) -> Result<serde_json::Value, String> {
    if token_store::chatbot_api_service(&service).is_none() {
        return Err("That is not one of the six chatbot services.".to_string());
    }
    token_store::delete_chatbot_api_key(&service).map_err(|e| format!("Not removed: {e}."))?;
    Ok(serde_json::json!({
        "ok": true,
        "said": "Removed from Windows Credential Manager on this PC.",
    }))
}

#[cfg(test)]
mod tests {
    use super::{chatbot_status, status};

    #[test]
    fn the_status_never_carries_a_value_field() {
        let v = status("imap_user");
        assert!(v.get("value").is_none());
        assert_eq!(v["name"], "imap_user");
        assert!(v["env_set"].is_boolean());
    }

    #[test]
    fn an_unknown_name_reports_nothing_saved_rather_than_guessing() {
        // Not reachable through the Tauri commands (they refuse first), but
        // `status` itself must not panic on a name outside the four.
        let v = status("not_one_of_them");
        assert_eq!(v["env_set"], false);
        assert!(v["saved"].is_null());
    }

    /// The same rule for the six chatbot keys: a status never carries the
    /// key, and there is no environment variable that could win here.
    #[test]
    fn a_chatbot_status_carries_the_service_and_never_the_key() {
        let v = chatbot_status("openai");
        assert!(v.get("value").is_none());
        assert!(v.get("key").is_none());
        assert_eq!(v["service"], "openai");
        assert_eq!(v["env_set"], false);
        let v = chatbot_status("not_one_of_them");
        assert_eq!(v["env_set"], false);
        assert!(v["saved"].is_null());
    }

    /// The four account secrets are still exactly four, and the six chatbot
    /// keys are still exactly six: two tables, neither one grown by accident.
    #[test]
    fn the_two_tables_hold_four_and_six() {
        use crate::token_store::{ACCOUNT_SECRET_TARGETS, CHATBOT_API_KEY_TARGETS};
        assert_eq!(ACCOUNT_SECRET_TARGETS.len(), 4);
        assert_eq!(CHATBOT_API_KEY_TARGETS.len(), 6);
        // No name is claimed by both tables: the two pages would then fight
        // over one Credential Manager entry.
        let account: Vec<&str> = ACCOUNT_SECRET_TARGETS.iter().map(|(n, _, _)| *n).collect();
        let chatbot: Vec<&str> = CHATBOT_API_KEY_TARGETS.iter().map(|(s, _)| *s).collect();
        assert!(account.iter().all(|n| !chatbot.contains(n)));
    }
}
