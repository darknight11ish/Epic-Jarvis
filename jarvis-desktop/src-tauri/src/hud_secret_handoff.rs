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

use std::time::Duration;

use tauri::AppHandle;

use crate::commands;

/// One host-only write. The backend types nothing until the whole body has
/// arrived, and its own engine answers in a fraction of this budget.
const WRITE_TIMEOUT: Duration = Duration::from_secs(30);

/// The engine refuses a longer secret; this command refuses before sending it.
const MAX_SECRET_CHARS: usize = 4096;

/// The engine's card ids are `sh_` + 24 lower-case hex. Anything else is not a
/// card this app ever showed, so it is refused here rather than sent.
fn card_id_ok(handoff_id: &str) -> bool {
    let bytes = handoff_id.as_bytes();
    bytes.len() == 27
        && handoff_id.starts_with("sh_")
        && bytes[3..]
            .iter()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

/// The Fill body: ONE card id and ONE secret, exactly the two fields the
/// backend's host-only route takes. No other field can leave this command.
pub(crate) fn fill_body(handoff_id: &str, secret: &str) -> Result<serde_json::Value, String> {
    if !card_id_ok(handoff_id) {
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
    if !card_id_ok(handoff_id) {
        return Err("That card is no longer valid; nothing was cancelled.".to_string());
    }
    Ok(serde_json::json!({"handoff_id": handoff_id}))
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

#[cfg(test)]
mod tests {
    use super::*;

    const CARD: &str = "sh_0123456789abcdef01234567";

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
}
