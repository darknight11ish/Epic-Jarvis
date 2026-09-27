//! Settings -> "Check for tool updates" (the owner's own request, made
//! directly, not from the feasibility backlog: "a feature that allows me to
//! run it on request that looks for updates of current tools that are
//! integrated into Jarvis already (through GitHub)."; backend/
//! jarvis_tool_updates.py, tool-updates.patch; JARVIS-API.md section 53).
//!
//! Two commands, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_tool_updates`] - `GET /api/tool_updates`: whether the owner has
//!   ever approved a check, whether one is running right now, the last
//!   card's outcome, and the last finished report (Python packages, Rust
//!   crates and any pinned GitHub tool). A read, never held.
//! * [`check_tool_updates`] - `POST /api/tool_updates/check {}`: the FIRST
//!   time ever, raises ONE approval card on the PC and returns at once
//!   ("waiting"); every later press starts the check in the background and
//!   also returns at once ("checking") - it never blocks on the check
//!   itself, which can take a few minutes (crates.io is asked once per Rust
//!   crate NAME - 576 of them in this project alone today - and PyPI once
//!   per Python package). The finished report shows up on the next
//!   [`get_tool_updates`], which `tool-updates-settings.js` polls for while
//!   `waiting` or `checking` is true (the same "start it, poll for it"
//!   shape `hardware-panel.js` already uses for measuring the graphics
//!   cards).
//!
//! **Report only, never an update itself**: the backend module never runs
//! `pip install`, `cargo update`, or anything else that changes a file - it
//! only shows the exact command to run yourself, and this Rust side never
//! runs one either.
//!
//! [`get_tool_updates`] is not held on a stale link: reading changes
//! nothing. [`check_tool_updates`] IS held, unlike an earlier version of
//! this file claimed (bug audit 2026-09-27, desktop-rust finding #8): the
//! first-ever press raises an approval card the same as `set_second_card`,
//! `set_briefing` and `set_backup_folder` do, and all three of those are
//! held on a stale link so that card is answered by someone looking at a
//! live queue, not a frozen one. `backup_now`'s own "not held" reasoning
//! does not transfer here - `backup_now` never raises a card at all.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const PATH: &str = "/api/tool_updates";
pub(crate) const CHECK_PATH: &str = "/api/tool_updates/check";

/// What a backend without `jarvis_tool_updates.py` / `tool-updates.patch`
/// is told.
pub(crate) const TOOL_UPDATES_MISSING: &str =
    "Your PC's Jarvis cannot check for tool updates yet - run apply-patches.ps1 on this PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// Starting the check (or raising its card), never waiting for the check
/// itself to finish - the backend answers this request at once.
const CHECK_TIMEOUT: Duration = Duration::from_secs(15);

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

/// [`get_tool_updates`] reads and changes nothing, so it is never held.
/// [`check_tool_updates`] IS held: it can raise a fresh approval card.
pub(crate) fn held_on_stale(path: &str) -> bool {
    path == CHECK_PATH
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// `GET /api/tool_updates`'s answer: the PC's own body on 2xx,
/// [`TOOL_UPDATES_MISSING`] from a PC without the route, and the PC's own
/// sentence otherwise.
pub(crate) fn read_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": TOOL_UPDATES_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// `POST /api/tool_updates/check`'s answer: the PC's own body on a 2xx (this
/// route only ever answers 202 - "waiting" for the first-ever card, or
/// "checking" every time after; 200 never happens here), [`TOOL_UPDATES_MISSING`]
/// from a PC without the route, and the PC's own sentence otherwise (503:
/// the action is not tier "ask", or the check itself could not be started).
pub(crate) fn check_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(TOOL_UPDATES_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// Whether the owner has ever approved a check, whether one is running now,
/// the last card's outcome, and the last finished report. A read.
#[tauri::command]
pub async fn get_tool_updates(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    read_answer(status, &body)
}

/// Starts the check (or raises the one-time approval card) and returns at
/// once - never blocks on the check itself. Held on a stale link: the
/// first-ever press raises a card, and that card should be answered by
/// someone looking at a live queue (bug audit 2026-09-27, finding #8).
#[tauri::command]
pub async fn check_tool_updates(app: AppHandle) -> Result<serde_json::Value, String> {
    if held_on_stale(CHECK_PATH) && stale(&app) {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(CHECK_TIMEOUT))?
        .post(format!("{base}{CHECK_PATH}"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({}))
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    check_answer(status, &body)
}

#[cfg(test)]
mod tests {
    use super::{check_answer, held_on_stale, read_answer, CHECK_PATH, PATH, TOOL_UPDATES_MISSING};

    #[test]
    fn a_pc_without_it_says_so() {
        let got = read_answer(404, "").unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], TOOL_UPDATES_MISSING);
        assert_eq!(check_answer(404, "").unwrap_err(), TOOL_UPDATES_MISSING);
        assert!(read_answer(200, "{nope").is_err());
    }

    /// Bug audit 2026-09-27, finding #8: reading is never held, but
    /// starting a check IS - it can raise a fresh approval card, and that
    /// card should be answered by someone looking at a live queue.
    #[test]
    fn only_the_check_is_held_on_a_stale_link() {
        assert!(!held_on_stale(PATH));
        assert!(held_on_stale(CHECK_PATH));
    }

    #[test]
    fn a_real_view_is_passed_on_unchanged() {
        let body = serde_json::json!({
            "available": true, "title": "Check for tool updates",
            "detail": "detail text", "button_label": "Check for tool updates",
            "approved": false, "waiting": false, "checking": false,
            "last": null, "report": null,
        });
        let got = read_answer(200, &body.to_string()).unwrap();
        assert_eq!(got, body);
    }

    #[test]
    fn the_first_ever_check_waits_for_a_card() {
        let body = serde_json::json!({"ok": true, "waiting": true, "view": {},
            "message": "Waiting for your approval."});
        let got = check_answer(202, &body.to_string()).unwrap();
        assert_eq!(got["waiting"], true);
    }

    #[test]
    fn a_later_check_starts_in_the_background_and_never_blocks() {
        let body = serde_json::json!({"ok": true, "checking": true, "view": {},
            "message": "Checking now."});
        let got = check_answer(202, &body.to_string()).unwrap();
        assert_eq!(got["checking"], true);
    }

    #[test]
    fn a_wrong_tier_is_its_own_words_not_a_generic_refusal() {
        let body = serde_json::json!({"ok": false,
            "error": "check_tool_updates is tier 'auto' in jarvis-framework.toml"});
        let err = check_answer(503, &body.to_string()).unwrap_err();
        // backend_refusal (commands.rs's second_card_refusal) raises the
        // backend's own sentence's first letter for a user-facing line, so
        // the real string starts "Check_tool_updates...", not
        // "check_tool_updates..." - a case-sensitive contains() here always
        // failed, on Windows CI (cargo test), never caught locally where
        // only cargo check/clippy run.
        assert!(err.to_lowercase().contains("check_tool_updates"), "{err}");
    }
}
