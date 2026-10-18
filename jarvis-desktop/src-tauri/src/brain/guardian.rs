//! Brain -> Projects -> "File history": the desktop drawer over the file
//! guardian (Pillar 18; backend `jarvis_file_guardian.py`, JARVIS-API section
//! 139; LM-2C).
//!
//! THE DRAWER, IN THREE CALLS
//!
//! * the list rides on the EXISTING read command: `brain_read`'s allowlist
//!   gained `guardian_history` -> `GET /api/guardian/snapshots` (routes.rs),
//!   so a new page pane needs no new read grant;
//! * [`guardian_diff`] - `GET /api/guardian/diff?path=&sha_before=`, the
//!   module's own bounded unified diff. The two values come from PAGE INPUT,
//!   so they are %-encoded here and the path is never glued into a URL raw;
//! * [`guardian_restore`] - `POST /api/guardian/restore`, the ONE write. The
//!   PC raises the EXISTING `undo_action` card and the request waits for that
//!   card's answer, which is why its own budget is twenty minutes rather than
//!   the Brain's usual twenty seconds: a person may be away from the screen.
//!   Nothing is approved here - this window cannot answer a card at all.
//!
//! THE HIDING RULE (the reason this file exists rather than the page deciding)
//!
//! A snapshot's path and reason are the owner's own work, so the whole drawer
//! hides while App lock is locked OR "Hide memory lists and chat history" is
//! on - [`words_hidden`] is exactly that pair, and [`hide_private`] replaces the
//! whole answer with ONE sentence. The hidden answer carries no row, no count
//! and no path, so a page script cannot read round it. `brain.rs` skips the
//! list section entirely while hidden and inserts the same sentence, and the
//! two commands here ask the PC for NOTHING - so while hidden not one file
//! name crosses the loopback wire at all.
//!
//! Owner-only is the backend's rule (`jarvis_owner_check.from_this_pc`): this
//! window only ever talks to `127.0.0.1`, and the PC refuses a request from
//! another device before reading it. The phone has no page for any of this, so
//! `tools/check_parity.py` calls the three routes `deliberate`
//! (ARCHITECTURE.md section 8).

use std::time::Duration;

use tauri::AppHandle;

use super::READ_TIMEOUT;
use crate::commands;

/// The three routes, literal, so a page cannot build one.
pub(crate) const SNAPSHOTS_PATH: &str = "/api/guardian/snapshots";
pub(crate) const DIFF_PATH: &str = "/api/guardian/diff";
pub(crate) const RESTORE_PATH: &str = "/api/guardian/restore";

/// While App lock or the hidden lists are on, this is the only sentence the
/// drawer gets. It names neither a file, a count nor a folder.
pub(crate) const HIDDEN_WORDS: &str =
    "Turn off Hide memory lists and chat history to see which files Jarvis kept a copy of.";

/// A PC whose backend predates the guardian routes (the same sentence shape
/// the Brain's other missing modules use).
pub(crate) const MISSING: &str = "Your PC's Jarvis does not have the file guardian yet. \
     Run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

/// The restore request waits for a PERSON: the PC raises the existing
/// `undo_action` card and answers when it is decided (or after its own
/// fifteen-minute timeout). Twenty minutes leaves that budget room.
const RESTORE_WAIT: Duration = Duration::from_secs(20 * 60);

/// The two flags that hide the drawer: App lock, and "Hide memory lists and
/// chat history". Pure so the pair can be tested without a window.
pub(crate) fn hidden_flags(app_lock: bool, hide_lists: bool) -> bool {
    app_lock || hide_lists
}

/// Is the drawer hidden right now? Both flags, read from the same store the
/// rest of the app uses; never a cached copy.
pub(crate) fn words_hidden(app: &AppHandle) -> bool {
    hidden_flags(
        crate::lock::app_locked(app),
        crate::lock::private_hidden(app),
    )
}

/// The one hidden answer the list and the diff both draw: a sentence and
/// nothing else - no rows, no count, no path, no diff.
pub(crate) fn hidden_answer(words: &str) -> serde_json::Value {
    serde_json::json!({
        "ok": true,
        "available": true,
        "hidden": true,
        "keep_on_screen": true,
        "title": "File history",
        "hidden_words": words,
    })
}

/// Replace a real answer with the hidden one. An answer that already says the
/// module is absent (`available: false`) passes through, so the drawer can
/// still say the PC has no guardian; a hidden answer stays as it is.
pub(crate) fn hide_private(answer: serde_json::Value) -> serde_json::Value {
    if answer.get("available").and_then(|a| a.as_bool()) == Some(false) {
        return answer;
    }
    if answer.get("hidden").and_then(|h| h.as_bool()) == Some(true) {
        return answer;
    }
    hidden_answer(HIDDEN_WORDS)
}

fn shown(app: &AppHandle, answer: serde_json::Value) -> serde_json::Value {
    if words_hidden(app) {
        hide_private(answer)
    } else {
        answer
    }
}

/// One query value, %-encoded (RFC 3986 unreserved kept; every other byte
/// escaped). No dependency for six lines of arithmetic, and the path can never
/// add a parameter of its own.
pub(crate) fn encode(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    for byte in value.as_bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => {
                out.push(*byte as char)
            }
            other => out.push_str(&format!("%{other:02X}")),
        }
    }
    out
}

/// The diff request line, built only from the two encoded values.
pub(crate) fn diff_path(path: &str, sha_before: &str) -> String {
    format!(
        "{DIFF_PATH}?path={}&sha_before={}",
        encode(path),
        encode(sha_before)
    )
}

/// The module's own bounded unified diff. A read; not held on a stale link.
#[tauri::command]
pub async fn guardian_diff(
    app: AppHandle,
    path: String,
    sha_before: String,
) -> Result<serde_json::Value, String> {
    if words_hidden(&app) {
        return Ok(hidden_answer(HIDDEN_WORDS));
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{}", diff_path(&path, &sha_before)))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let body = response.text().await.unwrap_or_default();
    let answer =
        serde_json::from_str::<serde_json::Value>(&body).map_err(|_| UNREADABLE.to_string())?;
    Ok(shown(&app, answer))
}

/// Put one saved version back. The PC raises the EXISTING `undo_action` card;
/// this command only waits for its answer and hands the PC's own sentence back.
/// A denied, timed-out or unraisable card changes nothing on the PC, and a
/// hidden drawer asks for nothing at all.
#[tauri::command]
pub async fn guardian_restore(
    app: AppHandle,
    path: String,
    sha_before: String,
) -> Result<serde_json::Value, String> {
    if words_hidden(&app) {
        return Ok(serde_json::json!({
            "ok": false, "refused": true, "why": "hidden",
            "path": "", "receipt_id": "", "words": HIDDEN_WORDS,
        }));
    }
    let base = commands::jarvis_base(&app);
    let body = serde_json::json!({ "path": path, "sha_before": sha_before });
    let response = commands::jarvis_client(Some(RESTORE_WAIT))?
        .post(format!("{base}{RESTORE_PATH}"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    if let Ok(answer) = serde_json::from_str::<serde_json::Value>(&text) {
        return Ok(answer);
    }
    Err(if status == 404 || status == 501 {
        MISSING.to_string()
    } else {
        UNREADABLE.to_string()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_drawer_hides_under_both_flags_and_only_without_them() {
        assert!(hidden_flags(true, false), "App lock alone must hide it");
        assert!(
            hidden_flags(false, true),
            "the hidden lists alone must hide it"
        );
        assert!(hidden_flags(true, true));
        assert!(!hidden_flags(false, false));
    }

    #[test]
    fn a_hidden_answer_names_no_file_and_no_count() {
        let value = hidden_answer(HIDDEN_WORDS);
        assert_eq!(value["hidden"], true);
        assert_eq!(value["hidden_words"], HIDDEN_WORDS);
        for forbidden in ["snapshots", "path", "diff", "count", "label"] {
            assert!(value.get(forbidden).is_none(), "{forbidden}");
        }
        // Even the shortest, most innocent answer must not carry a number.
        assert!(!value.to_string().contains("snapshots"));
    }

    #[test]
    fn a_real_answer_is_replaced_and_an_absent_one_passes_through() {
        let real = serde_json::json!({
            "ok": true, "snapshots": [{"path": "C:\\Notes\\daily.md"}], "count": 1,
        });
        let hidden = hide_private(real);
        assert_eq!(hidden["hidden"], true);
        assert!(!hidden.to_string().contains("daily.md"));
        let absent = serde_json::json!({"available": false, "error": "older PC"});
        assert_eq!(hide_private(absent.clone()), absent);
        let already = hidden_answer(HIDDEN_WORDS);
        assert_eq!(hide_private(already.clone()), already);
    }

    #[test]
    fn a_path_is_encoded_into_the_diff_request_and_cannot_add_a_parameter() {
        let url = diff_path(r"C:\Notes\my file & more.md", "ABC123");
        assert_eq!(
            url,
            "/api/guardian/diff?path=C%3A%5CNotes%5Cmy%20file%20%26%20more.md&sha_before=ABC123"
        );
        assert!(
            url.contains("%26"),
            "an ampersand from the path must be escaped"
        );
        assert_eq!(encode("plain-name_1.2~"), "plain-name_1.2~");
        assert_eq!(encode("a b"), "a%20b");
    }

    #[test]
    fn the_restore_waits_for_a_persons_card() {
        // The PC's own gate waits up to fifteen minutes for an answer.
        assert!(RESTORE_WAIT >= Duration::from_secs(15 * 60));
        assert_eq!(SNAPSHOTS_PATH, "/api/guardian/snapshots");
        assert_eq!(DIFF_PATH, "/api/guardian/diff");
        assert_eq!(RESTORE_PATH, "/api/guardian/restore");
    }
}
