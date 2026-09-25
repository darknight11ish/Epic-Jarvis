//! Settings -> "Sending email" (the owner's decision of 2026-09-25, after the
//! Muse audit; backend/email-send.patch, backend/jarvis_email_send.py;
//! JARVIS-API.md section 24).
//!
//! One command, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_email_sending`] - `GET /api/email/sending`: whether sending is set
//!   up, from which address, through which server and how encrypted, and the
//!   one line both apps show in the PC's own words. Whether a password is set
//!   - yes or no, never the password: the backend has no route that returns
//!     it, and there is none that takes one either. It is set on the PC only,
//!     the same variable email reading already uses.
//!
//! Sending itself is not here: an email is written by the model on the PC
//! and put to the approval gate there, one card per email, answered through
//! [`crate::commands::decide_approval`] like every other card. What this
//! module adds to that path lives in `commands.rs` (the widget sends an
//! email's Approve to the Jarvis bar, where the whole email can be read).

use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const SENDING_PATH: &str = "/api/email/sending";

/// The gate action every email is asked under (jarvis_email_send.ACTION).
pub(crate) const SEND_EMAIL_ACTION: &str = "send_email";

/// What a backend without `jarvis_email_send.py` is told to do about it. The
/// phone says the same (`EmailSending.MISSING`).
pub(crate) const SENDING_MISSING: &str =
    "Your PC's Jarvis cannot send email yet - run apply-patches.ps1 on the PC.";

/// What the widget is told when its Approve is pressed on an email: the
/// Jarvis bar opens on the card instead. The widget says the same
/// (`EMAIL_APPROVE` in widget.js).
pub(crate) const EMAIL_APPROVES_IN_BAR: &str = "An email is approved in the Jarvis bar, where \
     all of it can be read - it has been opened for you. Nothing was approved here.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_email_sending`]'s reading of the answer, tested against
/// `tests/fixtures/email-sending-cases.json` (the real `view()`).
pub(crate) fn sending_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("said").is_some_and(|s| s.is_string()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "said": SENDING_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// Whether sending is set up: `GET /api/email/sending`. A read; it sends
/// nothing and connects the PC to no mail server.
#[tauri::command]
pub async fn get_email_sending(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{SENDING_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    sending_answer(status, &body)
}

/// Whether a waiting approval row is an email. Such a card is approved only
/// in the Jarvis bar, where all of it can be read - never from the widget,
/// which shows one line (see `commands::answer_approval`).
pub(crate) fn is_email(item: &serde_json::Value) -> bool {
    item.get("action").and_then(|a| a.as_str()) == Some(SEND_EMAIL_ACTION)
}

#[cfg(test)]
mod tests {
    use super::{is_email, sending_answer, SENDING_MISSING};

    /// The real answers, made by `tools/gen_email_sending_cases.py`.
    const CASES: &str = include_str!("../../tests/fixtures/email-sending-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("email-sending-cases.json is JSON")
    }

    #[test]
    fn every_real_view_is_passed_on_unchanged() {
        let doc = cases();
        let all = doc["cases"].as_object().expect("cases");
        assert!(all.len() >= 5);
        for (name, view) in all {
            let got =
                sending_answer(200, &view.to_string()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, view, "{name}");
            assert!(got.get("password").is_none(), "{name}");
        }
    }

    #[test]
    fn a_pc_without_it_says_so() {
        let doc = cases();
        let m = &doc["missing"];
        let got =
            sending_answer(m["status"].as_u64().unwrap() as u16, &m["body"].to_string()).unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["said"], SENDING_MISSING);
        assert_eq!(sending_answer(404, "").unwrap()["said"], SENDING_MISSING);
        assert!(sending_answer(200, "{nope").is_err());
        assert!(sending_answer(500, r#"{"error": "boom"}"#).is_err());
    }

    #[test]
    fn an_email_card_is_known_by_its_action() {
        assert!(is_email(
            &serde_json::json!({ "id": "a", "action": "send_email" })
        ));
        assert!(!is_email(
            &serde_json::json!({ "id": "a", "action": "email_read" })
        ));
        assert!(!is_email(&serde_json::json!({ "id": "a" })));
    }
}
