//! The Jarvis bar's one read: what the owner had highlighted when the bar
//! opened (Pillar 24-B; backend `jarvis_ui_control.read_selection()`, through
//! `jarvis_brain_reads.py`'s `GET /api/selection`, JARVIS-API section 141).
//!
//! WHY THIS IS RUST AND NOT THE PAGE. The bar takes the focus the moment it is
//! shown, and Windows UI Automation reports the FOCUSED control's selection -
//! so by the time a page script could ask, the owner's selection is already
//! "nothing". The read therefore happens BEFORE the bar is revealed, on the
//! bar-open path (`windows::toggle_quickbar`), and its answer is handed to the
//! page as the `selection-read` event. Nothing reaches the model: the page
//! only puts the words in the box, and the owner presses Enter.
//!
//! WHAT THIS MODULE DOES NOT DO: it does not read a window itself, decide
//! what is private, or widen a selection. All of that is the backend's
//! (`jarvis_ui_control` reuses the screen's "Never look at" list, private
//! windows, password boxes and the scrubber; a request from another device is
//! refused there before anything is read). This module posts one GET and
//! passes the answer back UNCHANGED - the same shape the Python function
//! returns - or turns a transport/old-backend failure into the same refusal
//! shape with a sentence. It logs nothing, keeps nothing, and is not held on
//! a stale link (a read changes nothing).
//!
//! The command [`read_selection`] is the same read for an explicit call. The
//! bar itself is served by [`read_selection_quiet`] before it takes focus.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

/// `GET` here; the answer is the Python function's own dict.
pub(crate) const SELECTION_PATH: &str = "/api/selection";

/// What an older backend (no route, no module) is told to do about it.
pub(crate) const SELECTION_UPDATE: &str =
    "This PC's Jarvis does not have the selection reader yet. \
     Update the backend by running apply-patches.ps1, then try again.";

/// A loopback read of a few milliseconds; the bar-open path waits for it
/// before taking focus, so the limit is short on purpose.
const SELECTION_TIMEOUT: Duration = Duration::from_secs(3);

/// What the bar-open path must do, from the lock reading BEFORE it starts
/// and the one AFTER the read answers (S-3).
///
/// The decision is a pure function of the two booleans so its four cases can
/// be tested without a window: the app's own `toggle_quickbar` only wires it.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum BarRead {
    /// Unlocked both times: read, show the bar with the answer.
    Read,
    /// Locked BEFORE: do not read at all; show the lock's own path.
    DoNotRead,
    /// Unlocked when it started, locked when the read answered: the text is
    /// thrown away and the page is told (which also clears a chip drawn before
    /// the lock); the show path still runs so the lock card can appear.
    ReadThenClear,
}

pub(crate) fn bar_read(locked_before: bool, locked_after: bool) -> BarRead {
    if locked_before {
        BarRead::DoNotRead
    } else if locked_after {
        BarRead::ReadThenClear
    } else {
        BarRead::Read
    }
}

/// The refusal the bar's page draws when App lock is on. It has the 24-A
/// refusal shape, so the one chip rule that already exists (`ok !== true`
/// means no chip) also clears a chip left over from before the lock (S-3).
pub(crate) fn locked_answer() -> serde_json::Value {
    serde_json::json!({
        "ok": false, "refused": true, "why": "locked", "text": "", "app": "",
        "chars": 0, "truncated": false, "scrubbed": false,
        "words": "Jarvis is locked, so the highlighted text was not shown. \
                  Unlock it and press the key again.",
    })
}

/// One bar-open read at a time (S-5): two quick presses must not start two
/// readers, and a slow first read must not have its chip erased by a refusal
/// from a second read that found the bar in focus.
static READ_PENDING: AtomicBool = AtomicBool::new(false);

/// true when this caller may start the read; false while one is in flight.
pub(crate) fn begin_bar_read() -> bool {
    !READ_PENDING.swap(true, Ordering::SeqCst)
}

/// The read finished (whatever it found): the next bar open may start one.
pub(crate) fn end_bar_read() {
    READ_PENDING.store(false, Ordering::SeqCst);
}

/// One refusal in the 24-A shape, for a read the transport could not make.
fn unavailable() -> serde_json::Value {
    serde_json::json!({
        "ok": false, "refused": true, "why": "unavailable", "text": "", "app": "",
        "chars": 0, "truncated": false, "scrubbed": false,
        "words": "The highlighted text could not be read: Jarvis did not answer. \
                  Nothing was attached.",
    })
}

/// [`read_selection`]'s reading of the answer, on its own so it can be tested
/// against the real shape (200: the Python dict, possibly its own refusal;
/// 404/501/503: an older backend, said in words; anything else: refused).
pub(crate) fn selection_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("ok").is_some_and(|ok| ok.is_boolean()))
            .ok_or_else(|| {
                "Jarvis answered, but not in a way this app can read. \
                 Update the backend by running apply-patches.ps1."
                    .to_string()
            });
    }
    if status == 404 || status == 501 || status == 503 {
        return Err(SELECTION_UPDATE.to_string());
    }
    Err(backend_refusal(status, body))
}

/// The one GET, shared by the command and the bar-open path.
async fn ask(app: &AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(SELECTION_TIMEOUT))?
        .get(format!("{base}{SELECTION_PATH}"))
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    selection_answer(status, &body)
}

/// The same read for an explicit call. Returns the 24-A dict unchanged.
#[tauri::command]
pub async fn read_selection(app: AppHandle) -> Result<serde_json::Value, String> {
    ask(&app).await
}

/// The bar-open read: the answer, or a same-shape refusal when the transport
/// failed. NEVER returns Err, because the bar is opening either way and a
/// chip that cannot be drawn is simply no chip.
pub(crate) async fn read_selection_quiet(app: &AppHandle) -> serde_json::Value {
    match ask(app).await {
        Ok(value) => value,
        Err(_why) => unavailable(),
    }
}

#[cfg(test)]
mod tests {
    use super::selection_answer;
    use super::{bar_read, begin_bar_read, end_bar_read, locked_answer, BarRead};

    #[test]
    fn the_locked_paths_never_hand_the_selection_over() {
        // S-3: locked before -> no read; locked while reading -> throw it away.
        assert_eq!(bar_read(true, false), BarRead::DoNotRead);
        assert_eq!(bar_read(true, true), BarRead::DoNotRead);
        assert_eq!(bar_read(false, true), BarRead::ReadThenClear);
        assert_eq!(bar_read(false, false), BarRead::Read);

        let value = locked_answer();
        assert_eq!(value["ok"], false);
        assert_eq!(value["refused"], true);
        assert_eq!(value["why"], "locked");
        assert_eq!(value["text"], "");
        // The word "locked" is in the sentence a person reads.
        assert!(value["words"].as_str().unwrap_or("").contains("locked"));
    }

    #[test]
    fn only_one_bar_read_runs_at_a_time() {
        // S-5: the guard is process-wide; after the first read ends, the next
        // bar open may start again. (No other test touches this flag.)
        assert!(begin_bar_read(), "the first read may start");
        assert!(
            !begin_bar_read(),
            "a second read while one is in flight must not start"
        );
        end_bar_read();
        assert!(
            begin_bar_read(),
            "after the read ends the next one may start"
        );
        end_bar_read();
    }

    /// The real shape `jarvis_ui_control.read_selection()` returns on success.
    const GOOD: &str = r#"{"ok":true,"refused":false,"why":"","text":"the selected words",
        "app":"notepad","chars":18,"truncated":false,"scrubbed":true,
        "words":"Read the highlighted text from notepad."}"#;

    #[test]
    fn a_successful_answer_is_passed_back_unchanged() {
        let got = selection_answer(200, GOOD).expect("a 200 must be readable");
        assert_eq!(got["ok"], true);
        assert_eq!(got["text"], "the selected words");
        assert_eq!(got["app"], "notepad");
        assert_eq!(got["scrubbed"], true);
        assert!(
            got.get("title").is_none(),
            "the payload names no window title"
        );
    }

    #[test]
    fn a_twenty_four_a_refusal_is_an_answer_not_a_transport_error() {
        let body = r#"{"ok":false,"refused":true,"why":"no_selection","text":"",
                       "app":"","chars":0,"truncated":false,"scrubbed":false,
                       "words":"There is no highlighted text in the window in front."}"#;
        let got = selection_answer(200, body).expect("a refusal from the PC is still an answer");
        assert_eq!(got["ok"], false);
        assert_eq!(got["why"], "no_selection");
        assert_eq!(got["text"], "");
    }

    #[test]
    fn an_older_backend_says_update() {
        for status in [404u16, 501, 503] {
            let err = selection_answer(status, "{}").expect_err("an older backend is not a read");
            assert!(err.contains("apply-patches.ps1"), "{err}");
        }
    }

    #[test]
    fn anything_that_is_not_the_known_shape_is_refused_not_guessed() {
        assert!(selection_answer(200, "not json").is_err());
        assert!(selection_answer(200, r#"{"text":"no ok field"}"#).is_err());
        assert!(selection_answer(500, r#"{"error":"boom"}"#).is_err());
    }
}
