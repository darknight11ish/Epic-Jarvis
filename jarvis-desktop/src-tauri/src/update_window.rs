//! The small window that shows an update while it runs.
//!
//! The owner asked for this on 2026-11-24, in their own words: *"when i update
//! jarvis there should be a pop up with a progress bar"* (DEF-098). Before it,
//! a nine-minute run was reported as one sentence in Settings - "This can take
//! several minutes" - with no position, and a run that failed left the owner
//! reading four paragraphs of prose in a log file after the fact.
//!
//! ## One window, three doors, and no new door
//!
//! There is exactly one updater and exactly three ways to reach it: the
//! Settings button, the tray's update row, and an approved `desktop_update`
//! card. All three run [`crate::update::update_both`], and that function is the
//! only caller of [`open`] - so every door gets the same window and no page can
//! open one on its own. Nothing here decides anything: it draws what the
//! updater already reports, and a machine that cannot draw the window still
//! updates, because [`open`] logs its own failure and returns.
//!
//! ## Where the numbers come from
//!
//! The window page listens to four events, all of which already existed except
//! the last:
//!
//! * `backend-update-progress` - [`crate::update_progress::Progress`], one
//!   `JARVIS-EVENT` line from `tools/update_backend.py` at a time. The bar is
//!   its own `fraction`, or its `done`/`total` counts when the tool did not give
//!   a fraction (a legacy run), and nothing at all before its first event. The
//!   page never advances the bar on a timer and never invents a denominator.
//! * `update-progress` - [`crate::update::DownloadProgress`], the desktop
//!   package's bytes so far and its total when the server sent one. Again the
//!   bar is only those bytes, never a guess.
//! * `update-step` - [`crate::update::Step`], which half is running and, on a
//!   failure, the tool's own sentence about it.
//! * `update-window-note` - this module's own one-liners: the run started (with
//!   the pace's words), the installer is about to take over, and how the run
//!   ended. The start note is sent from the page-load hook, so a slow first
//!   paint cannot miss it.
//!
//! ## What the window cannot show, and says so instead
//!
//! On Windows the updater's installer path ends this process after it launches
//! the installer (`update.rs`'s module docs write the order down). A window
//! inside a process that is gone cannot draw. So the last thing this window is
//! told is what is ABOUT to happen - the installer starts, Atlas closes and
//! starts again - and the bar stops there rather than pretending to move. The
//! pending record written before the installer runs is what carries the truth
//! to the next launch, which reconciles it and says how it ended. This module
//! neither duplicates that record nor offers an ending of its own.
//!
//! ## What it never carries
//!
//! Fixed words, phases, counts, byte totals, the tool's own failing file names
//! and its own reason sentence - the same words Settings and the run's log
//! already show. It never reads or draws the owner's notes, files, memory or
//! chat: this window knows about the update and nothing else.

use serde::Serialize;
use tauri::webview::PageLoadEvent;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

/// Label of the window. The page's capability file names this same label, and a
/// test holds the two together.
pub const LABEL: &str = "update-progress";

/// The event this module sends its [`Note`] on. The page listens for it; the
/// other three event names are the updater's own (`crate::events`,
/// `crate::update_progress`), so no second channel was invented for them.
pub const NOTE_EVENT: &str = crate::events::UPDATE_WINDOW_NOTE;

/// The words the window shows at the moment the installer is handed the
/// package.
///
/// This is the last honest thing that can be said in this process: after it,
/// Windows launches the installer and ends Atlas. It promises no ending and it
/// explains why the bar stops.
pub const INSTALLER_WORDS: &str = "The installer is starting now. Atlas closes and starts \
     again by itself, and the next start says whether the desktop half finished. The \
     installer cannot report its own progress to Atlas, so the bar stops here instead of \
     pretending to move.";

/// One sentence for the window, above its bar.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Note {
    /// `started`, `installing` or `ended`.
    pub kind: String,
    /// The sentence itself. Fixed words, counts or the tool's own sentence -
    /// never anything the owner wrote.
    pub line: String,
    /// True only for an `ended` note about a run that did not finish, so the
    /// page can colour it as a failure without guessing from the text.
    pub bad: bool,
}

impl Note {
    fn started(line: &str) -> Note {
        Note {
            kind: "started".to_string(),
            line: line.to_string(),
            bad: false,
        }
    }

    fn installing() -> Note {
        Note {
            kind: "installing".to_string(),
            line: INSTALLER_WORDS.to_string(),
            bad: false,
        }
    }

    fn ended(line: String, bad: bool) -> Note {
        Note {
            kind: "ended".to_string(),
            line,
            bad,
        }
    }
}

/// Opens the update window, or brings the one already open back, and tells it
/// the run has started.
///
/// **Best effort on purpose.** A machine that refuses a window (a broken
/// webview, a policy, a desktop session that cannot composite one) must still
/// update: the failure is written as one fixed line - no path, no error text -
/// and the run carries on. That is why this returns nothing at all: there is no
/// error a caller could accidentally turn into "the update did not start".
pub fn open(app: &AppHandle, opening: &str) {
    let note = Note::started(opening);
    if let Some(window) = app.get_webview_window(LABEL) {
        // A second run in the same session: the page is already loaded, so the
        // start note both reaches it at once and resets its state.
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.emit(NOTE_EVENT, note);
        return;
    }
    // The page takes a moment to load, so the start note waits for its own
    // finished load rather than being emitted into a document that is not
    // listening yet (`on_page_load` is called on the window's builder even when
    // the first frame is still blank).
    let on_load = note.clone();
    let built = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("update-window.html".into()))
        .title("Atlas update")
        .inner_size(560.0, 330.0)
        .min_inner_size(440.0, 300.0)
        .resizable(false)
        .maximizable(false)
        .minimizable(true)
        .center()
        .focused(true)
        .theme(Some(tauri::Theme::Dark))
        .on_page_load(move |window, payload| {
            if payload.event() == PageLoadEvent::Finished {
                let _ = window.emit(NOTE_EVENT, on_load.clone());
            }
        })
        .build();
    if built.is_err() {
        // Fixed words and nothing else: the error text can carry a path, and
        // this project's rule is that no new log line does. The update itself
        // is untouched by this line.
        crate::logfile::log(
            "[jarvis] the update progress window could not be opened; the update carries on",
        );
    }
}

/// Tells the window the installer is about to take over, immediately before
/// [`crate::update::update_both`] calls the install.
///
/// This is sent as a best-effort note, not a promise that it was painted: the
/// Windows installer path exits this process at once, so the page also words
/// the same fact from the download reaching its end. Neither half claims to
/// show installer progress.
pub fn installing(app: &AppHandle) {
    send(app, Note::installing());
}

/// Tells the window how the run ended. Called on every ending that returns to
/// `update_both`; the ending that ends the process never reaches it, which is
/// exactly why the next launch reconciles the record instead.
pub fn ended(app: &AppHandle, outcome: &crate::update::BothOutcome) {
    send(app, Note::ended(ended_line(outcome), !outcome.updated_both));
}

/// One plain sentence about a returned outcome.
///
/// Pure, so the rule is a test: a half that did not finish is never "updated".
/// The same truth Settings, the tray and the chat already say, in the window's
/// own one line.
pub fn ended_line(outcome: &crate::update::BothOutcome) -> String {
    if outcome.updated_both {
        return "Both halves are updated. Restart Atlas to run the new version.".to_string();
    }
    let not_done: Vec<&str> = outcome
        .steps
        .iter()
        .filter(|step| step.state != "ok")
        .map(|step| step.step.as_str())
        .collect();
    if not_done.is_empty() {
        "The update did not finish, so the two halves may differ until it is finished.".to_string()
    } else {
        format!(
            "The update did not finish: {} did not. The two halves may differ until it is \
             finished.",
            not_done.join(" and ")
        )
    }
}

/// Sends one note to the window, if it is on screen. Nothing is retried and
/// nothing is queued: a closed window is the owner's choice, and the run does
/// not depend on a note being seen.
fn send(app: &AppHandle, note: Note) {
    if let Some(window) = app.get_webview_window(LABEL) {
        let _ = window.emit(NOTE_EVENT, note);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The window is opened by `update_both` itself, BEFORE either half runs -
    /// which is what gives all three doors the same window without a fourth
    /// path. Source pins, with the needles split so this test's own text cannot
    /// satisfy them: only the real code can.
    #[test]
    fn update_both_is_what_opens_the_window_before_either_half_runs() {
        let src = include_str!("update.rs");
        let start = src
            .find("pub async fn update_both(")
            .expect("update.rs has no update_both");
        let body = &src[start..];

        let open = body
            .find(concat!("update_window::", "open(&app, &opening);"))
            .expect("update_both no longer opens the update window");
        let announced = body
            .find(concat!(
                "announce_step(&app, &step_starting(STEP_",
                "BACKEND"
            ))
            .expect("update_both no longer announces the backend half");
        let first_half = body
            .find(concat!("crate::backend_update::", "run("))
            .expect("update_both no longer runs the backend half");
        assert!(
            open < announced,
            "the window is opened after the run was announced - it must open first"
        );
        assert!(
            open < first_half,
            "the window is opened after the backend half started - it must open first"
        );

        // The installer note is the LAST thing update_both can say about the
        // desktop half: after the record and the stop, immediately before the
        // install call that ends the process.
        let prepared = body
            .find(concat!(
                "match prepare_desktop_",
                "half(&app, Some(backend_half), backend_commit).await"
            ))
            .expect("update_both no longer prepares the desktop half");
        let installing = body
            .find(concat!("update_window::", "installing(&app);"))
            .expect("update_both no longer tells the window the installer is next");
        let install = body
            .find(concat!("match install_", "now(&app, ready).await"))
            .expect("update_both no longer installs the desktop half");
        assert!(
            prepared < installing,
            "the installer note is sent before the package was verified and recorded"
        );
        assert!(
            installing < install,
            "the installer note is sent after the installer was called"
        );

        // Every ending that returns to this process tells the window, so a
        // refusal cannot sit under a bar that still looks like it is working.
        let ended = concat!("update_window::", "ended(&app, &outcome);");
        assert!(
            body.matches(ended).count() >= 3,
            "not every ending in update_both tells the window how it ended"
        );
    }

    /// The note the page draws is this shape. The field names are the wire, so
    /// a rename that the page would silently miss fails here.
    #[test]
    fn the_note_payload_is_the_shape_the_page_reads() {
        let started = serde_json::to_value(Note::started("Patching the backend folder."))
            .expect("a note serialises");
        assert_eq!(started["kind"], "started");
        assert_eq!(started["line"], "Patching the backend folder.");
        assert_eq!(started["bad"], false);

        let installing = serde_json::to_value(Note::installing()).expect("a note serialises");
        assert_eq!(installing["kind"], "installing");
        assert!(installing["line"]
            .as_str()
            .unwrap_or("")
            .contains("installer"));

        let ended = serde_json::to_value(Note::ended("did not finish".to_string(), true))
            .expect("a note serialises");
        assert_eq!(ended["kind"], "ended");
        assert_eq!(ended["bad"], true);
    }

    /// The backend progress the window's bar is painted from is the updater
    /// tool's own event payload, parsed by `update_progress::progress_of` and
    /// serialised for the page. These are the exact fields the page reads, so a
    /// rename on either side fails here rather than drawing an empty bar on the
    /// owner's PC.
    #[test]
    fn the_backend_progress_payload_carries_the_fields_the_bar_reads() {
        let mut p = crate::update_progress::Progress::default();
        crate::update_progress::progress_of(
            r#"JARVIS-EVENT {"done": 12, "failed": 1, "fraction": 0.4321, "kind": "update_backend", "measured": true, "mode": "responsive", "phase": "testing", "total": 356}"#,
            &mut p,
        );
        let wire = serde_json::to_value(&p).expect("progress serialises");
        assert_eq!(wire["phase"], "testing");
        assert_eq!(wire["fraction"], 0.4321);
        assert_eq!(wire["done"], 12);
        assert_eq!(wire["total"], 356);
        assert_eq!(wire["measured"], true);
        assert_eq!(wire["verdict"], serde_json::Value::Null);
        assert!(wire["bad"].is_array());

        // The ETA fields, when the tool gives them, are the same camelCase the
        // page reads; a missing one stays null rather than becoming zero.
        crate::update_progress::progress_of(
            r#"JARVIS-EVENT {"etaSeconds": 90, "etaLowSeconds": 60, "etaHighSeconds": 120, "phase": "testing"}"#,
            &mut p,
        );
        let wire = serde_json::to_value(&p).expect("progress serialises");
        assert_eq!(wire["etaSeconds"], 90);
        assert_eq!(wire["etaLowSeconds"], 60);
        assert_eq!(wire["etaHighSeconds"], 120);
    }

    /// The desktop download the page words is `DownloadProgress`, and a total
    /// the server did not send is null - never a made-up denominator.
    #[test]
    fn the_download_payload_carries_bytes_and_an_optional_total() {
        let known = serde_json::to_value(crate::update::DownloadProgress {
            downloaded: 512,
            total: Some(1024),
        })
        .expect("download progress serialises");
        assert_eq!(known["downloaded"], 512);
        assert_eq!(known["total"], 1024);

        let unknown = serde_json::to_value(crate::update::DownloadProgress {
            downloaded: 512,
            total: None,
        })
        .expect("download progress serialises");
        assert!(
            unknown["total"].is_null(),
            "an unknown total became a number"
        );
    }

    /// The capability file must name this window and grant it the one thing it
    /// needs - listening - and no command at all. A page that can only listen
    /// cannot start, approve or install anything.
    #[test]
    fn the_window_holds_an_event_listener_and_no_command() {
        let cap: serde_json::Value =
            serde_json::from_str(include_str!("../capabilities/update-window.json"))
                .expect("the update window's capability file is not valid JSON");
        assert_eq!(
            cap["windows"],
            serde_json::json!([LABEL]),
            "the capability file does not name the window this module creates"
        );
        let permissions: Vec<&str> = cap["permissions"]
            .as_array()
            .expect("the capability file has no permissions list")
            .iter()
            .filter_map(|v| v.as_str())
            .collect();
        assert!(
            permissions.contains(&"core:event:allow-listen"),
            "the window cannot hear the events it draws"
        );
        for permission in &permissions {
            assert!(
                !permission.contains("update")
                    && !permission.starts_with("commands")
                    && !permission.contains("allow-invoke"),
                "the update window holds {permission}, which could start something"
            );
        }
    }

    /// This module only reports. It holds no command, calls no updater and
    /// reaches no network - the three ways it could become a second door.
    #[test]
    fn the_window_module_only_reports() {
        let src = include_str!("update_window.rs");
        let production = &src[..src.find("#[cfg(test)]").expect("no test module")];
        for forbidden in [
            concat!("#[tauri::", "command]"),
            concat!(".instal", "l("),
            concat!("backend_update::", "run("),
            concat!("update::install_", "now("),
            concat!("reqwest", "::"),
        ] {
            assert!(
                !production.contains(forbidden),
                "the update window module can act through {forbidden}"
            );
        }
        // The start note goes out from the page-load hook, so a slow first
        // paint is not a missed run.
        assert!(
            production.contains(".on_page_load("),
            "the start note is emitted before the page can be listening"
        );
    }

    /// A run that did not finish is never called updated, and the sentence
    /// names the half that did not - the same rule Settings and the chat obey.
    #[test]
    fn an_ending_that_did_not_finish_is_never_called_updated() {
        let step = |step: &str, state: &str| crate::update::Step {
            step: step.to_string(),
            state: state.to_string(),
            detail: "the tool's own sentence".to_string(),
            log_dir: None,
            tail: String::new(),
        };

        let finished = crate::update::BothOutcome {
            steps: vec![
                step(crate::update::STEP_BACKEND, "ok"),
                step(crate::update::STEP_DESKTOP, "ok"),
            ],
            updated_both: true,
            restart_needed: true,
        };
        let words = ended_line(&finished);
        assert!(words.contains("Both halves are updated"), "{words}");
        assert!(!words.contains("did not finish"), "{words}");

        let stopped = crate::update::BothOutcome {
            steps: vec![
                step(crate::update::STEP_BACKEND, "failed"),
                step(crate::update::STEP_DESKTOP, "skipped"),
            ],
            updated_both: false,
            restart_needed: true,
        };
        let words = ended_line(&stopped);
        assert!(words.contains("did not finish"), "{words}");
        assert!(words.contains("backend"), "{words}");
        assert!(words.contains("desktop"), "{words}");
        assert!(!words.contains("updated"), "{words}");
    }
}
