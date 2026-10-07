//! "Chatbot money limits" (docs/ACCOUNT-KEYS-DESIGN.md steps 3-5, the owner's
//! approval of 2026-10-06; JARVIS-API section 87.4.1; backend
//! `jarvis_chatbot_limits.py`, `chatbot-limits.patch`).
//!
//! The other half of the keys box beside this one: a key with no monthly
//! money limit leaves the service unusable ("no limit, no conversation"), and
//! a limit with no way to raise it puts the owner back in PowerShell exactly
//! when the app should be enough. That is why the two were built together
//! (decision 1).
//!
//! Two commands, in the Settings window only (`permissions/surfaces.toml`,
//! `settings-surface`):
//!
//! * [`chatbot_money`] - `GET /api/chatbot/money`. A read: every service's
//!   limit, what is spent, what is left, and its model's price WITH where that
//!   number came from ("yours" or "default, unverified, written 2026-09-28")
//!   and when it was set. Never held on a stale link.
//! * [`set_chatbot_money`] - `POST /api/chatbot/money`, ONE change. Held on a
//!   stale event stream (rule 4), like every other write from this app.
//!
//! (Named `chatbot_money`, not `chatbot_limits`, because
//! `brain/chatbot.rs` already owns a `chatbot_limits` command - that one
//! changes a CONVERSATION's messages and minutes, which is a different thing
//! from what a service may spend in a month.)
//!
//! THE ONE RULE THIS FILE MUST NOT SOFTEN. Raising a limit is a loosening: it
//! needs ONE approval card and Windows Hello on this PC, and the backend
//! refuses it from any other device. Lowering one, removing one and
//! correcting a price only tighten or correct, so they need no card. The
//! BACKEND decides which of the two a request is, from the amount against the
//! limit it already holds - never this file, and never the page. So the page
//! sends the amount and the intent the owner chose ("raise" or "lower"), and
//! the backend is free to answer that a "raise" to no more than the current
//! amount was treated as a lowering; the answer's `raised` says which
//! actually happened.
//!
//! NOTHING TO DO WITH A KEY. This file never reads, names or carries an API
//! key: a key goes into Credential Manager from Rust and nowhere else
//! (`account_secrets.rs`). What travels here is a service name, a number of
//! dollars, a model name, and prices - never a secret, never a message.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run against the shapes the backend really sends.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const MONEY_PATH: &str = "/api/chatbot/money";

/// A PC without `jarvis_chatbot_limits.py` / `chatbot-limits.patch`. Same
/// shape as the other "run apply-patches.ps1" lines.
pub(crate) const CHATBOT_MONEY_MISSING: &str =
    "Your PC's Jarvis cannot set chatbot money limits yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// A RAISE waits for the owner: the card sits on the PC until it is answered,
/// and Windows Hello is asked while it waits. The backend's own approval
/// timeout bounds the wait, so this only has to outlast it.
const RAISE_TIMEOUT: Duration = Duration::from_secs(300);

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A 404 that the module itself sent carries `"ok": false`; a PC without the
/// route at all does not.
fn own_404(body: &str) -> bool {
    parsed(body).and_then(|v| v.get("ok").and_then(|o| o.as_bool())) == Some(false)
}

/// The PC's own words for a refusal: its `message` as given (403 `pc_only`,
/// 400 with the reason an amount or a price was refused, 409 "not approved"),
/// else the shared reading of `{"error": ...}`.
pub(crate) fn refusal(status: u16, body: &str) -> String {
    if let Some(message) = parsed(body)
        .and_then(|v| {
            v.get("message")
                .and_then(|m| m.as_str().map(str::to_string))
        })
        .filter(|m| !m.trim().is_empty())
    {
        return message;
    }
    backend_refusal(status, body)
}

/// [`chatbot_money`]'s reading of the answer: the PC's own body on a 2xx;
/// `{"available": false, "why": CHATBOT_MONEY_MISSING}` from a PC without the
/// route; the PC's own sentence otherwise.
pub(crate) fn limits_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("services").is_some_and(|s| s.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if (status == 404 && !own_404(body)) || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": CHATBOT_MONEY_MISSING }));
    }
    Err(refusal(status, body))
}

/// [`set_chatbot_money`]'s reading: the PC's own body on a 2xx (the whole
/// view comes back with it, so the page needs no second read), the PC's own
/// words on 400 / 403 / 409, the missing line from a PC without the route.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("services").is_some_and(|s| s.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if (status == 404 && !own_404(body)) || status == 501 {
        return Err(CHATBOT_MONEY_MISSING.to_string());
    }
    Err(refusal(status, body))
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

/// Settings -> Chatbot API keys: `GET /api/chatbot/money`. A read.
#[tauri::command]
pub async fn chatbot_money(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{MONEY_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    limits_answer(status, &body)
}

/// The three things the page may ask for. Anything else is refused here, so a
/// stray key in the body cannot reach the backend.
pub(crate) fn limit_action(action: &str) -> Option<&'static str> {
    match action {
        "raise_limit" => Some("raise_limit"),
        "lower_limit" => Some("lower_limit"),
        "remove_limit" => Some("remove_limit"),
        "set_price" => Some("set_price"),
        "reset_price" => Some("reset_price"),
        _ => None,
    }
}

/// The body of `POST /api/chatbot/money`: only the known keys, built here
/// rather than forwarded, so the page cannot smuggle anything else through.
/// `Err` when the action or the service is missing.
pub(crate) fn limit_body(
    service: &str,
    action: &str,
    dollars: Option<f64>,
    price_in: Option<f64>,
    price_out: Option<f64>,
) -> Result<serde_json::Value, String> {
    let action = limit_action(action)
        .ok_or_else(|| "That is not one of the chatbot money changes.".to_string())?;
    let service = service.trim();
    if service.is_empty() || service.len() > 32 || !service.bytes().all(|b| b.is_ascii_lowercase())
    {
        return Err("Say which chatbot service.".to_string());
    }
    let mut out = serde_json::Map::new();
    out.insert("action".into(), serde_json::json!(action));
    out.insert("service".into(), serde_json::json!(service));
    match action {
        "raise_limit" | "lower_limit" => {
            let Some(amount) = dollars else {
                return Err("Type how many dollars a month first.".to_string());
            };
            if !amount.is_finite() || amount < 0.0 {
                return Err("A monthly limit is a number of dollars, from 0 up.".to_string());
            }
            out.insert("dollars".into(), serde_json::json!(amount));
        }
        "set_price" => {
            let (Some(pin), Some(pout)) = (price_in, price_out) else {
                return Err("Type both prices: dollars per million in, then out.".to_string());
            };
            if !pin.is_finite() || !pout.is_finite() || pin < 0.0 || pout < 0.0 {
                return Err("Each price is a number of dollars per million, from 0 up.".to_string());
            }
            out.insert("in".into(), serde_json::json!(pin));
            out.insert("out".into(), serde_json::json!(pout));
        }
        _ => {}
    }
    Ok(serde_json::Value::Object(out))
}

/// ONE change, held on a stale event stream. The backend decides whether it
/// needs a card; this only carries the request and the answer's words.
#[tauri::command]
pub async fn set_chatbot_money(
    app: AppHandle,
    service: String,
    action: String,
    dollars: Option<f64>,
    price_in: Option<f64>,
    price_out: Option<f64>,
) -> Result<serde_json::Value, String> {
    let body = limit_body(&service, &action, dollars, price_in, price_out)?;
    if stale(&app) {
        return Err(STALE.to_string());
    }
    // A raise waits on the owner's card, so it gets the long timeout; the
    // others answer at once. Read from the built body, never from the raw
    // string the page sent.
    let raising = body.get("action").and_then(|a| a.as_str()) == Some("raise_limit");
    let timeout = if raising { RAISE_TIMEOUT } else { READ_TIMEOUT };
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(timeout))?
        .post(format!("{base}{MONEY_PATH}"))
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
    use super::*;

    fn view() -> String {
        serde_json::json!({
            "ok": true, "available": true, "can_change": true,
            "raise_action": "raise_api_limit", "lower_action": "lower_api_limit",
            "services": [{"service": "openai", "limit": 5.0, "price": {"source": "default"}}],
        })
        .to_string()
    }

    #[test]
    fn a_real_view_reads_and_a_pc_without_it_says_so() {
        let got = limits_answer(200, &view()).unwrap();
        assert_eq!(got["services"][0]["service"], "openai");
        let got = limits_answer(404, r#"{"error": "not found"}"#).unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], CHATBOT_MONEY_MISSING);
        let got = limits_answer(501, "").unwrap();
        assert_eq!(got["available"], false);
        assert!(limits_answer(200, "{nope").is_err());
        assert!(limits_answer(200, r#"{"ok": true}"#).is_err());
        // The module's own 404 is a refusal, not "missing".
        assert_ne!(
            limits_answer(404, r#"{"ok": false, "error": "gone"}"#).unwrap_err(),
            CHATBOT_MONEY_MISSING
        );
    }

    #[test]
    fn the_pcs_own_words_win_over_its_error_code() {
        let pc_only = serde_json::json!({
            "ok": false, "error": "pc_only", "pc_only": true,
            "message": "This is set on the PC only, so nothing was changed."
        })
        .to_string();
        assert_eq!(
            change_answer(403, &pc_only).unwrap_err(),
            "This is set on the PC only, so nothing was changed."
        );
        let denied = serde_json::json!({
            "ok": false, "error": "not_approved", "message": "You said no, so the limit was not raised."
        })
        .to_string();
        assert!(change_answer(409, &denied).unwrap_err().contains("said no"));
        assert_eq!(change_answer(404, "").unwrap_err(), CHATBOT_MONEY_MISSING);
    }

    #[test]
    fn a_change_carries_the_whole_new_view_back() {
        let got = change_answer(200, &view()).unwrap();
        assert_eq!(got["services"][0]["limit"], 5.0);
        assert_eq!(got["raise_action"], "raise_api_limit");
    }

    #[test]
    fn only_the_five_known_actions_are_ever_sent() {
        assert_eq!(limit_action("raise_limit"), Some("raise_limit"));
        assert_eq!(limit_action("lower_limit"), Some("lower_limit"));
        assert_eq!(limit_action("remove_limit"), Some("remove_limit"));
        assert_eq!(limit_action("set_price"), Some("set_price"));
        assert_eq!(limit_action("reset_price"), Some("reset_price"));
        for bad in ["", "make_it_free", "RAISE_LIMIT", "raise limit", "key"] {
            assert_eq!(limit_action(bad), None, "{bad}");
        }
    }

    #[test]
    fn a_limit_body_holds_only_the_known_keys() {
        let body = limit_body("openai", "raise_limit", Some(10.0), None, None).unwrap();
        let obj = body.as_object().unwrap();
        assert_eq!(obj["action"], "raise_limit");
        assert_eq!(obj["service"], "openai");
        assert_eq!(obj["dollars"], 10.0);
        assert_eq!(obj.len(), 3);
        // A key smuggled in beside them cannot be built here at all.
        let price = limit_body("groq", "set_price", None, Some(0.1), Some(0.5)).unwrap();
        let obj = price.as_object().unwrap();
        assert_eq!(obj["in"], 0.1);
        assert_eq!(obj["out"], 0.5);
        assert_eq!(obj.len(), 4);
        let reset = limit_body("groq", "reset_price", None, None, None).unwrap();
        assert_eq!(reset.as_object().unwrap().len(), 2);
    }

    #[test]
    fn a_missing_or_impossible_amount_is_refused_before_anything_is_sent() {
        assert!(limit_body("openai", "raise_limit", None, None, None).is_err());
        assert!(limit_body("openai", "lower_limit", Some(-1.0), None, None).is_err());
        assert!(limit_body("openai", "lower_limit", Some(f64::NAN), None, None).is_err());
        assert!(limit_body("openai", "set_price", None, Some(1.0), None).is_err());
        assert!(limit_body("openai", "set_price", None, Some(-1.0), Some(1.0)).is_err());
        for bad in [
            "",
            "OpenAI",
            "openai api",
            "a".repeat(33).as_str(),
            "openai;drop",
        ] {
            assert!(
                limit_body(bad, "lower_limit", Some(1.0), None, None).is_err(),
                "{bad}"
            );
        }
    }

    #[test]
    fn a_service_name_can_never_carry_a_path_or_a_query_into_the_route() {
        for bad in ["../openai", "openai?x=1", "openai/../..", "openai&y"] {
            assert!(
                limit_body(bad, "lower_limit", Some(1.0), None, None).is_err(),
                "{bad}"
            );
        }
        assert!(limit_body("openrouter", "lower_limit", Some(1.0), None, None).is_ok());
    }
}
