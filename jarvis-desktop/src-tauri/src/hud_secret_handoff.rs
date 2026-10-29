//! The HUD owner-secret hand-off card's two writes (2026-10-26).
//!
//! The HUD page holds NO pairing token (apps security audit M2), so the
//! card's Fill and Cancel cannot be the page's own POSTs: `hud_bootstrap.js`
//! refuses those. These two commands are the only door, and they post the two
//! host-only backend routes with the token added HERE, in Rust.
//!
//! The secret crosses this file once, as an argument. It is never logged,
//! never included in an error sentence and never kept: the request body is
//! built in [`fill_body`], sent, and dropped with this call.
//!
//! Reads are NOT here: the card's pending list is a fixed `hud_proxy.rs` read.
//!
//! AND THE CONNECT-ACCOUNT CARD (2026-10-28). The same door carries the second
//! card kind: `connect_account` asks the owner for a token, a private calendar
//! link, or a username and password, and the host saves it straight into
//! Windows Credential Manager (it types nothing into a control, so there is no
//! taint and no window to re-measure). [`save_body`] is its only shape, built
//! the same way: the card id and the card's own field values, and nothing
//! else. The values cross this file once, are never logged and are never in an
//! error sentence - [`save_body`]'s refusals name a field, never a value.

use std::time::Duration;

use tauri::AppHandle;

use crate::commands;

/// One host-only write. The backend types nothing until the whole body has
/// arrived, and its own engine answers in a fraction of this budget.
const WRITE_TIMEOUT: Duration = Duration::from_secs(30);

/// The engine refuses a longer secret; this command refuses before sending it.
const MAX_SECRET_CHARS: usize = 4096;

/// The connect card's engine caps a value at the same length.
const MAX_CONNECT_VALUE_CHARS: usize = 4096;

/// A card has at most this many boxes (the engine's biggest service has two).
/// Refusing a longer list here means a page cannot post an arbitrary map.
const MAX_CONNECT_FIELDS: usize = 4;

/// The engine's card ids are `sh_` (hand-off) / `ca_` (connect) + 24 lower-case
/// hex. Anything else is not a card this app ever showed, so it is refused
/// here rather than sent.
fn card_id_ok(handoff_id: &str, prefix: &str) -> bool {
    let bytes = handoff_id.as_bytes();
    bytes.len() == 27
        && handoff_id.starts_with(prefix)
        && bytes[3..]
            .iter()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

/// The Fill body: ONE card id and ONE secret, exactly the two fields the
/// backend's host-only route takes. No other field can leave this command.
pub(crate) fn fill_body(handoff_id: &str, secret: &str) -> Result<serde_json::Value, String> {
    if !card_id_ok(handoff_id, "sh_") {
        return Err("That card is no longer valid; ask Jarvis for a new one.".to_string());
    }
    if secret.is_empty() {
        return Err("Type the secret first.".to_string());
    }
    if secret.chars().count() > MAX_SECRET_CHARS {
        return Err("That secret is too long; nothing was typed.".to_string());
    }
    Ok(serde_json::json!({"handoff_id": handoff_id, "secret": secret}))
}

/// The Cancel body: ONE card id.
pub(crate) fn cancel_body(handoff_id: &str) -> Result<serde_json::Value, String> {
    if !card_id_ok(handoff_id, "sh_") {
        return Err("That card is no longer valid; nothing was cancelled.".to_string());
    }
    Ok(serde_json::json!({"handoff_id": handoff_id}))
}

/// A connect-card field name is one of the engine's own: lower-case letters and
/// underscores, short. Anything else is refused BEFORE a body is built, so the
/// page cannot post a key the engine never declared.
fn field_name_ok(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 32
        && name.bytes().all(|b| b.is_ascii_lowercase() || b == b'_')
}

/// The Save body: ONE card id and the card's OWN fields, and nothing else.
///
/// Every refusal names a field or the card - never a value - because this is
/// the one command where a value is an argument.
pub(crate) fn save_body(
    card_id: &str,
    values: &std::collections::BTreeMap<String, String>,
) -> Result<serde_json::Value, String> {
    if !card_id_ok(card_id, "ca_") {
        return Err("That card is no longer valid; ask Jarvis for a new one.".to_string());
    }
    if values.is_empty() {
        return Err("Fill in the card first.".to_string());
    }
    if values.len() > MAX_CONNECT_FIELDS {
        return Err("That card asked for fewer values than this.".to_string());
    }
    for (name, value) in values {
        if !field_name_ok(name) {
            return Err("That card has a field this app does not know.".to_string());
        }
        if value.trim().is_empty() {
            return Err(format!("The {} box is empty.", name.replace('_', " ")));
        }
        if value.chars().count() > MAX_CONNECT_VALUE_CHARS {
            return Err("One of those values is too long; nothing was saved.".to_string());
        }
    }
    Ok(serde_json::json!({"card_id": card_id, "values": values}))
}

/// The connect card's Cancel body: ONE card id.
pub(crate) fn connect_cancel_body(card_id: &str) -> Result<serde_json::Value, String> {
    if !card_id_ok(card_id, "ca_") {
        return Err("That card is no longer valid; nothing was cancelled.".to_string());
    }
    Ok(serde_json::json!({"card_id": card_id}))
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    if (200..300).contains(&status) {
        return serde_json::from_str(&text)
            .map_err(|_| "The PC answered something this app could not read.".to_string());
    }
    // The backend's own error sentence; a body without one gets a plain line.
    let said = serde_json::from_str::<serde_json::Value>(&text)
        .ok()
        .and_then(|value| {
            value
                .get("error")
                .and_then(|e| e.as_str())
                .map(str::to_string)
        });
    Err(said.unwrap_or_else(|| "The PC refused the request.".to_string()))
}

/// Fill the card the owner just answered: Rust POSTs `/api/secret-handoff/fill`
/// with the token. The engine types the secret, or voids with zero typed; this
/// command adds nothing to that decision.
#[tauri::command]
pub async fn hud_secret_handoff_fill(
    app: AppHandle,
    handoff_id: String,
    secret: String,
) -> Result<serde_json::Value, String> {
    let body = fill_body(&handoff_id, &secret)?;
    crate::brain::require_link_live(&app)?;
    post(&app, "/api/secret-handoff/fill", body).await
}

/// Cancel the card: Rust POSTs `/api/secret-handoff/cancel` with the token.
#[tauri::command]
pub async fn hud_secret_handoff_cancel(
    app: AppHandle,
    handoff_id: String,
) -> Result<serde_json::Value, String> {
    let body = cancel_body(&handoff_id)?;
    crate::brain::require_link_live(&app)?;
    post(&app, "/api/secret-handoff/cancel", body).await
}

/// Save the connect-account card's values: Rust POSTs
/// `/api/connect-account/save` with the token, and the backend writes them
/// straight into Windows Credential Manager, then tests the service once.
///
/// The values are arguments of this call and of nothing else: not logged, not
/// in an error sentence, not kept. `save_body` is their only shape.
#[tauri::command]
pub async fn hud_connect_account_save(
    app: AppHandle,
    card_id: String,
    values: std::collections::BTreeMap<String, String>,
) -> Result<serde_json::Value, String> {
    let body = save_body(&card_id, &values)?;
    crate::brain::require_link_live(&app)?;
    post(&app, "/api/connect-account/save", body).await
}

/// Cancel the connect-account card: Rust POSTs `/api/connect-account/cancel`.
#[tauri::command]
pub async fn hud_connect_account_cancel(
    app: AppHandle,
    card_id: String,
) -> Result<serde_json::Value, String> {
    let body = connect_cancel_body(&card_id)?;
    crate::brain::require_link_live(&app)?;
    post(&app, "/api/connect-account/cancel", body).await
}

#[cfg(test)]
mod tests {
    use super::*;

    const CARD: &str = "sh_0123456789abcdef01234567";
    const CONNECT: &str = "ca_0123456789abcdef01234567";

    fn values(pairs: &[(&str, &str)]) -> std::collections::BTreeMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    #[test]
    fn the_fill_body_is_one_card_and_one_secret() {
        assert_eq!(
            fill_body(CARD, "hunter2").unwrap(),
            serde_json::json!({"handoff_id": CARD, "secret": "hunter2"})
        );
        assert!(fill_body("", "hunter2").is_err());
        assert!(fill_body("not-a-card", "hunter2").is_err());
        assert!(fill_body(&CARD.replace("sh_", "SH_"), "hunter2").is_err());
        assert!(fill_body(CARD, "").is_err());
        assert!(fill_body(CARD, &"x".repeat(MAX_SECRET_CHARS + 1)).is_err());
        assert!(fill_body(CARD, &"x".repeat(MAX_SECRET_CHARS)).is_ok());
    }

    #[test]
    fn the_cancel_body_is_one_card() {
        assert_eq!(
            cancel_body(CARD).unwrap(),
            serde_json::json!({"handoff_id": CARD})
        );
        assert!(cancel_body("not-a-card").is_err());
    }

    #[test]
    fn a_bad_card_never_puts_the_secret_in_its_sentence() {
        let said = fill_body("not-a-card", "hunter2").unwrap_err();
        assert!(!said.contains("hunter2"), "{said}");
    }

    #[test]
    fn the_save_body_is_one_card_and_its_own_fields() {
        let got = save_body(CONNECT, &values(&[("token", "ghp_x")])).unwrap();
        assert_eq!(
            got,
            serde_json::json!({"card_id": CONNECT, "values": {"token": "ghp_x"}})
        );
        // A hand-off id is not a connect id, and the other way round.
        assert!(save_body(CARD, &values(&[("token", "ghp_x")])).is_err());
        assert!(connect_cancel_body(CARD).is_err());
        assert!(save_body(CONNECT, &values(&[])).is_err());
        assert!(save_body(
            CONNECT,
            &values(&[("a", "1"), ("b", "2"), ("c", "3"), ("d", "4"), ("e", "5")])
        )
        .is_err());
        assert!(save_body(CONNECT, &values(&[("Token", "x")])).is_err());
        assert!(save_body(CONNECT, &values(&[("token", "   ")])).is_err());
        assert!(save_body(
            CONNECT,
            &values(&[("token", &"x".repeat(MAX_CONNECT_VALUE_CHARS + 1))])
        )
        .is_err());
    }

    #[test]
    fn a_save_refusal_names_a_field_never_a_value() {
        let said = save_body(CONNECT, &values(&[("password", "   ")])).unwrap_err();
        assert!(said.contains("password"), "{said}");
        let said = save_body(CONNECT, &values(&[("token", &"s".repeat(9_999))])).unwrap_err();
        assert!(!said.contains("ssss"), "{said}");
        let said = save_body("nope", &values(&[("token", "hunter2")])).unwrap_err();
        assert!(!said.contains("hunter2"), "{said}");
    }

    #[test]
    fn the_connect_cancel_body_is_one_card() {
        assert_eq!(
            connect_cancel_body(CONNECT).unwrap(),
            serde_json::json!({"card_id": CONNECT})
        );
        assert!(connect_cancel_body("ca_zzzz").is_err());
    }
}
