//! "Bring in chats from ChatGPT, Claude or Gemini" (the owner's choice,
//! 2026-09-28; backend `jarvis_history_import.py` and `import_history.py`,
//! history-import.patch; JARVIS-API.md section 85).
//!
//! Three commands, Brain window only (permissions/surfaces.toml,
//! `brain-history-import`):
//!
//! * [`history_import_status`] - `GET /api/memory/import_chats`: where a run
//!   is, as counts and the PC's own sentence. A read, never held.
//! * [`history_import_start`] - the Windows "Open" dialog for the export
//!   (`.zip` or `.json`), then `POST /api/memory/import_chats/start
//!   {"path"}`. The PC reads the owner's own messages in the background and
//!   PROPOSES facts: each one waits in "Waiting for you" for its own yes -
//!   nothing is saved by itself. Held while the event stream is stale
//!   (rule 4), before the dialog even opens.
//! * [`history_import_cancel`] - `POST /api/memory/import_chats/cancel`: stop
//!   after the chat being read. Never held - it only makes Jarvis do less.
//!
//! The window never gets a file system of its own: the picker runs here, and
//! only the path the owner chose is sent - to this PC's Jarvis, nowhere else.
//! The phone has none of this (ARCHITECTURE.md section 8): the export is a
//! file on the PC. Its review queue shows the resulting cards as usual.

use std::time::Duration;

use tauri::AppHandle;

use super::require_link_live;
use crate::commands;
use crate::folders::{pick, picker};

pub(crate) const STATUS_PATH: &str = "/api/memory/import_chats";
const START_PATH: &str = "/api/memory/import_chats/start";
const CANCEL_PATH: &str = "/api/memory/import_chats/cancel";

/// A PC without the route. history-import.js says the same.
pub(crate) const IMPORT_MISSING: &str =
    "Your PC's Jarvis cannot bring in old chats yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

fn missing(status: u16, body: &str) -> bool {
    status == 404
        || status == 501
        || (status == 503
            && parsed(body).and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`history_import_status`]'s reading: the PC's view (it has a `state`),
/// `{"available": false, "why"}` from a PC without the route, or the PC's
/// own sentence.
pub(crate) fn status_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("state").is_some_and(|s| s.is_string()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": IMPORT_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// A start or a cancel: the PC's own body on a 2xx (202 started, 200
/// cancelling), [`IMPORT_MISSING`] from a PC without the route, and the PC's
/// own sentence otherwise (403 "the PC only", 400 a refused file, 409
/// already running or the model is not on this PC).
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(IMPORT_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

async fn send(
    app: &AppHandle,
    path: &str,
    body: Option<serde_json::Value>,
    timeout: Duration,
) -> Result<(u16, String), String> {
    let base = commands::jarvis_base(app);
    let client = commands::jarvis_client(Some(timeout))?;
    let request = match body {
        Some(json) => client.post(format!("{base}{path}")).json(&json),
        None => client.get(format!("{base}{path}")),
    };
    let response = request
        .headers(commands::jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    Ok((status, text))
}

/// Where a run is. A read.
#[tauri::command]
pub async fn history_import_status(app: AppHandle) -> Result<serde_json::Value, String> {
    let (status, text) = send(&app, STATUS_PATH, None, READ_TIMEOUT).await?;
    status_answer(status, &text)
}

/// The owner picks the export on this PC; the PC starts reading it in the
/// background. Held on a stale link, before the dialog opens.
#[tauri::command]
pub async fn history_import_start(app: AppHandle) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let Some(path) = pick(picker::What::ChatExport).await? else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
    // Checked again after the dialog: the link may have gone stale while
    // the owner was choosing.
    require_link_live(&app)?;
    let (status, text) = send(
        &app,
        START_PATH,
        Some(serde_json::json!({ "path": path })),
        WRITE_TIMEOUT,
    )
    .await?;
    change_answer(status, &text)
}

/// Stop after the chat being read. Never held: it only does less.
#[tauri::command]
pub async fn history_import_cancel(app: AppHandle) -> Result<serde_json::Value, String> {
    let (status, text) = send(
        &app,
        CANCEL_PATH,
        Some(serde_json::json!({})),
        WRITE_TIMEOUT,
    )
    .await?;
    change_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_real_view_is_passed_on() {
        let v = status_answer(
            200,
            r#"{"ok":true,"state":"running","read":3,"waiting":1,"words":"Reading"}"#,
        )
        .unwrap();
        assert_eq!(v["state"], "running");
        assert!(status_answer(200, r#"{"ok":true}"#).is_err());
        assert!(status_answer(200, "not json").is_err());
    }

    #[test]
    fn a_pc_without_it_says_so() {
        let v = status_answer(404, "").unwrap();
        assert_eq!(v["available"], false);
        assert_eq!(v["why"], IMPORT_MISSING);
        assert_eq!(change_answer(404, "").unwrap_err(), IMPORT_MISSING);
        assert_eq!(
            change_answer(503, r#"{"available":false,"error":"x"}"#).unwrap_err(),
            IMPORT_MISSING
        );
    }

    #[test]
    fn the_pcs_own_refusal_is_passed_on() {
        let why = change_answer(
            409,
            r#"{"ok":false,"error":"Jarvis is already bringing in chats. Stop it first, or let it finish."}"#,
        )
        .unwrap_err();
        assert!(why.contains("already bringing in chats"), "{why}");
        let ok = change_answer(202, r#"{"ok":true,"state":"running","started_now":true}"#).unwrap();
        assert_eq!(ok["started_now"], true);
    }
}
