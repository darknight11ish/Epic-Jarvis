//! Opening what ONE reminder's action points at (2026-10-27).
//!
//! The owner's request: *"id likee to set custom reminders that open something
//! or do an action if i ask jarvos to make a specific remonder. ... like makinf
//! a reminder that opens a specific image or webpage"*. A reminder may carry ONE
//! action (`jarvis_schedule.ACTION_KINDS`), and the two display kinds that open
//! something are `open-webpage` and `open-file`. Nothing about them acts on its
//! own: the reminder goes off, both apps say what it will open, and **nothing
//! opens until a person presses Open**. That press IS the approval - there is no
//! card, because opening writes nothing (the same reasoning `open_app.rs` and
//! `jarvis_open.py` already give), and because a card dies after fifteen minutes
//! while "look at this when you get to it" has to survive the shower.
//!
//! WHY THE COMMAND TAKES AN ID AND NEVER A TARGET
//! `open_reminder_target(id)` is the ONE new Tauri command this feature adds: a
//! page passes the job's id and nothing else, exactly like the toast buttons
//! ("Both carry the job id only, never the owner's words", `winrt_toast.rs`). The
//! target is read back from this PC (`GET /api/schedule?id=`), so a page cannot
//! hand Windows a path or a URL of its own. A control whose target the page had
//! chosen would make every window that holds the grant an exec primitive.
//!
//! WHY IT RE-CHECKS THE TARGET, WHICH THE BACKEND ALSO DID
//! The row is plain SQLite on the owner's own disk and anything on that PC can
//! edit it, so the PC's own answer is asked again at the moment of the tap:
//!
//!   * the job must have GONE OFF (`fired_at` is set) - a reminder that is not
//!     due yet cannot be opened early;
//!   * the PC's own second check, `action_problem`, must be absent. That is the
//!     backend's re-run of the folder allow-list and the URL rules
//!     (`jarvis_schedule._action_problem`) and its sentence is passed straight
//!     through, so the owner reads why instead of a silent no-op;
//!   * this file re-checks what it can on its own, with no Python in the way: the
//!     scheme is `https`, the address has a real host, and a file's extension is
//!     on the allow-list - the boundary that stops "open a file" from becoming
//!     "run whatever is registered for it";
//!   * a file that is not there any more says so in one sentence: "a silent
//!     failure looks like a broken feature" (`open_app.rs`).
//!
//! WHAT IT CANNOT DO, SAID PLAINLY
//! It does not re-run `jarvis_documents.allowed_path` in Rust - that function is
//! Python, in the backend, and re-implementing its link/junction/hidden-folder
//! resolution here would be a second, weaker copy of a security check. It relies
//! on the PC's answer for that (`action_problem`) and adds its own extension and
//! scheme checks on top. A stale link refuses like every other write
//! (`brain::require_link_live`): acting is held, reading is not.

use tauri::AppHandle;

use crate::brain;
use crate::brain::schedule::{read_job, valid_id};
use crate::commands;

/// The extensions "open a file" may open. The same list as
/// `jarvis_schedule.ACTION_FILE_EXTS`, deliberately duplicated: the backend
/// decides whether a reminder may be SAVED with this path, and this side decides
/// whether Windows is handed it now. A shortcut, a program, a script or a web
/// page is never on it, so `ShellExecuteExW` can only ever open a document.
pub(crate) const OPENABLE_EXTENSIONS: &[&str] = &[
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "pdf", "txt", "md", "docx", "doc", "xlsx", "pptx",
    "csv",
];

/// The longest address or path a reminder may carry, matching the backend.
pub(crate) const MAX_TARGET: usize = 1024;

/// The one sentence a late tap gets when the file has gone. One sentence, not a
/// code: it is shown to the owner as it is.
pub(crate) const NOT_THERE: &str = "That file is not there any more.";

/// `""` when this address is one a reminder may open, else the sentence to show.
///
/// https only, though [`commands::validate_external_url`] also allows http: an
/// address written once and opened for months is not the same risk as a link the
/// owner just clicked in an answer, and a plain-http page is the one an attacker
/// on the same cafe Wi-Fi can rewrite.
pub(crate) fn url_problem(url: &str) -> String {
    if url.is_empty() {
        return "That reminder has no web address to open.".to_string();
    }
    if url.len() > MAX_TARGET {
        return "That web address is too long to open.".to_string();
    }
    if !url.starts_with("https://") {
        return "Only an https:// address can be opened from a reminder.".to_string();
    }
    if url.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return "That web address has a space or a control character in it.".to_string();
    }
    if url.contains('\\') {
        return "That web address has a backslash in it.".to_string();
    }
    if commands::validate_external_url(url).is_err() {
        return "That web address is not one Jarvis will open.".to_string();
    }
    // `https://github.com@evil.example/` has a host of `evil.example`; the part
    // before the `@` is userinfo and every resolver ignores it.
    let host = url
        .split_once("//")
        .map(|(_, rest)| rest.split(['/', '?', '#']).next().unwrap_or(""))
        .unwrap_or("");
    if host.is_empty() || host.contains('@') {
        return "That web address has no real site name in it.".to_string();
    }
    String::new()
}

/// `""` when this file may be handed to Windows, else the sentence to show.
///
/// The EXTENSION is the boundary, and it is checked here as well as by the
/// backend: "open a file" means "run whatever is registered for it", so a
/// `.lnk`, an `.exe`, a script or an `.html` page must never reach the shell -
/// and a row edited by hand on this PC could name one.
pub(crate) fn path_problem(path: &str) -> String {
    if path.is_empty() {
        return "That reminder has no file to open.".to_string();
    }
    if path.len() > MAX_TARGET {
        return "That file's path is too long to open.".to_string();
    }
    if path.chars().any(|c| c.is_control()) {
        return "That file's path holds a character a path cannot have.".to_string();
    }
    let extension = std::path::Path::new(path)
        .extension()
        .and_then(|e| e.to_str())
        .map(str::to_ascii_lowercase)
        .unwrap_or_default();
    if !OPENABLE_EXTENSIONS.contains(&extension.as_str()) {
        return "Jarvis can open pictures, PDFs, text and Office files. It will not start a \
                program from a file."
            .to_string();
    }
    if !std::path::Path::new(path).is_absolute() {
        return "That file's path is not a whole path.".to_string();
    }
    if !std::path::Path::new(path).exists() {
        return NOT_THERE.to_string();
    }
    String::new()
}

/// ONE reminder's action, from the PC's own answer: `(kind, target)`.
///
/// `Err` carries the sentence to show: the reminder has no action, has not gone
/// off yet, or the PC's own second check refused it.
fn target_of(job: &serde_json::Value) -> Result<(String, String), String> {
    let action = job
        .get("action")
        .and_then(|v| v.as_object())
        .ok_or_else(|| "That reminder does not open anything.".to_string())?;
    let kind = action
        .get("kind")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if job.get("fired_at").and_then(|v| v.as_f64()).is_none() {
        // Nothing opens before its time: the Open button is drawn on a row that
        // has gone off, and a page asking for any other id is asking for
        // something this feature does not offer.
        return Err("That reminder has not gone off yet.".to_string());
    }
    if let Some(problem) = job.get("action_problem").and_then(|v| v.as_str()) {
        if !problem.is_empty() {
            // The PC's own re-check, in its own words ("it is not in a folder
            // Jarvis may look in", "that file is not there any more").
            return Err(problem.to_string());
        }
    }
    let key = match kind.as_str() {
        "open-webpage" => "url",
        "open-file" => "path",
        _ => return Err("That reminder does not open anything.".to_string()),
    };
    let target = action
        .get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    Ok((kind, target))
}

/// Open what ONE reminder's action points at. The job id only, never a target.
///
/// Held on a stale link, because this is acting: the event stream is the apps'
/// doorbell, and a link that is not live cannot confirm the job is still the one
/// the owner saw.
#[tauri::command]
pub async fn open_reminder_target(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    brain::require_link_live(&app)?;
    if !valid_id(&id) {
        return Err("That is not one reminder's id.".to_string());
    }
    let base = commands::jarvis_base(&app);
    let job = read_job(&app, &base, &id)
        .await
        .ok_or_else(|| "That reminder is not on the list any more.".to_string())?;
    let (kind, target) = target_of(&job)?;
    match kind.as_str() {
        "open-webpage" => {
            let problem = url_problem(&target);
            if !problem.is_empty() {
                return Err(problem);
            }
            // The one hardened path the app already trusts for a link in an
            // answer: length, http(s) only, no whitespace or control characters,
            // no `@` before the host, no backslash.
            commands::open_external_url(target.clone())?;
            Ok(serde_json::json!({ "opened": "page", "id": id }))
        }
        _ => {
            let problem = path_problem(&target);
            if !problem.is_empty() {
                return Err(problem);
            }
            commands::open_document(&target)?;
            Ok(serde_json::json!({ "opened": "file", "id": id }))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn job(action: serde_json::Value, fired: bool) -> serde_json::Value {
        let mut job =
            serde_json::json!({ "id": "s0123456789", "kind": "reminder", "action": action });
        if fired {
            job["fired_at"] = serde_json::json!(1_793_000_000.0);
        }
        job
    }

    #[test]
    fn a_page_must_be_https_with_a_real_host() {
        assert_eq!(url_problem("https://example.com/invoice-42"), "");
        assert!(!url_problem("http://example.com").is_empty());
        assert!(!url_problem("file:///C:/Users/x/a.png").is_empty());
        assert!(!url_problem("javascript:alert(1)").is_empty());
        assert!(!url_problem("https://github.com@evil.example/").is_empty());
        assert!(!url_problem("https://example.com\\@evil.example").is_empty());
        assert!(!url_problem("https://exa mple.com").is_empty());
        assert!(!url_problem("").is_empty());
        assert!(!url_problem(&format!("https://e.com/{}", "a".repeat(MAX_TARGET))).is_empty());
    }

    #[test]
    fn a_file_s_extension_is_the_boundary_not_its_folder() {
        // No such file, so the first refusal is the extension for these, and
        // NOT_THERE for an allowed one: the point is what never gets through.
        for refused in [
            "C:\\Users\\pcadmin\\Desktop\\setup.exe",
            "C:\\Users\\pcadmin\\Desktop\\invoice.lnk",
            "C:\\Users\\pcadmin\\Desktop\\run.bat",
            "C:\\Users\\pcadmin\\Desktop\\run.ps1",
            "C:\\Users\\pcadmin\\Desktop\\page.html",
            "C:\\Users\\pcadmin\\Desktop\\page.svg",
            "C:\\Users\\pcadmin\\Desktop\\notes.PS1",
        ] {
            let problem = path_problem(refused);
            assert!(
                problem.contains("will not start a program"),
                "{refused} said {problem:?}"
            );
        }
        let picture = "C:\\Users\\pcadmin\\Pictures\\taxes.png";
        assert_eq!(path_problem(picture), NOT_THERE);
        assert!(
            !path_problem("taxes.png").contains("will not start"),
            "relative"
        );
        assert!(!path_problem("C:\\a\\b.txt\\..\\c.exe").is_empty());
        assert!(!path_problem("").is_empty());
    }

    #[test]
    fn only_a_reminder_that_has_gone_off_and_opens_something_can_be_opened() {
        let page = || serde_json::json!({ "kind": "open-webpage", "url": "https://example.com" });
        assert!(target_of(&job(page(), false)).is_err(), "before its time");
        assert_eq!(
            target_of(&job(page(), true)).unwrap(),
            (
                "open-webpage".to_string(),
                "https://example.com".to_string()
            )
        );
        // The PC's own second check is passed straight through, in its words.
        let mut stale = job(page(), true);
        stale["action_problem"] = serde_json::json!("That file is not there any more.");
        assert_eq!(
            target_of(&stale),
            Err("That file is not there any more.".to_string())
        );
        // The two kinds that are not "open something" never are.
        for action in [
            serde_json::json!({ "kind": "show-note", "note": "take the blue folder" }),
            serde_json::json!({ "kind": "run-task", "task": "briefing" }),
        ] {
            assert!(target_of(&job(action, true)).is_err());
        }
        assert!(target_of(&serde_json::json!({ "id": "s0123456789" })).is_err());
    }

    #[test]
    fn the_id_is_the_only_thing_a_page_can_say() {
        // A compile-time shape, pinned as text: the command takes ONE argument
        // and it is the job's id. A second argument here would be the page
        // choosing what Windows opens.
        let source = include_str!("reminder_open.rs");
        let start = source.find("pub async fn open_reminder_target(").unwrap();
        let end = source[start..].find(')').unwrap() + start;
        let signature = &source[start..end];
        assert_eq!(signature.matches(':').count(), 2, "{signature}");
        assert!(signature.contains("id: String"), "{signature}");
        assert!(!signature.contains("url"), "{signature}");
        assert!(!signature.contains("path"), "{signature}");
    }
}
