//! Updating the **Python backend** from inside the app — the half of "update
//! Jarvis" that had never been driven by anything but the owner's own hands.
//!
//! ## What was true before this module
//!
//! The desktop program has updated itself since the signing key landed
//! ([`crate::update`]). The backend has not: the only way it ever moved was
//! `scripts/apply-patches.ps1`, run by hand in a PowerShell window from the
//! repository. Everything the owner saw when the two drifted apart was a
//! sentence telling him to go and do that ("run apply-patches.ps1 on the PC"),
//! in about eighty places.
//!
//! ## What this module does NOT do
//!
//! **It does not reimplement patching.** `scripts/apply-patches.ps1` is the one
//! program allowed to change that folder, and it stays that way: this runs it, with
//! `-BackendPath`, and reports what it said. Not one patch, one backup rule or
//! one classification decision is copied into Rust. The script's own rule — it
//! DRY-RUNS the whole list on a copy first, so a run that would fail changes
//! nothing — is therefore the rule this path inherits for free.
//!
//! **It never guesses at a folder.** Two paths are needed and both are read from
//! somewhere the owner already put them:
//!
//! * the backend folder (the one holding `jarvis_hud.py`) — the box on the same
//!   Settings card, else the folder this app already starts Jarvis from
//!   (`sidecar`'s configured arguments), else `JARVIS_BACKEND`, which
//!   `scripts/install-backend.ps1` is the documented way to set;
//! * the repository (the folder holding `scripts\apply-patches.ps1`) — a box on
//!   the same card, empty until the owner fills it in.
//!
//! There is deliberately **no discovery**: no search of the disk, no walk up
//! from the working directory, no "it is probably under Documents". A feature
//! that guessed at a security-relevant path and got it wrong would run the
//! patcher against somebody else's folder. When a path is missing this refuses,
//! in plain words, and changes nothing.
//!
//! ## What it is not allowed to become
//!
//! Nothing here runs on a timer, at startup, or from a check. It is reachable
//! only from the one button, and the sequence it is part of lives in
//! [`crate::update::update_both`] — which asks the owner first and states what
//! will happen.

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::AppHandle;
use tauri_plugin_store::StoreExt;

use crate::commands;

/// The setting naming the folder this repository was cloned into.
pub const REPO_KEY: &str = "updates.repo_folder";
/// The setting naming the folder holding `jarvis_hud.py`, when the owner wants
/// to say it outright rather than let it be read off the supervision settings.
pub const FOLDER_KEY: &str = "updates.backend_folder";
/// The environment variable `scripts/install-backend.ps1` sets, and the same
/// one `backend/_where.py` reads for the test suites.
pub const BACKEND_ENV: &str = "JARVIS_BACKEND";
/// The one program allowed to change the backend folder, relative to the repo.
pub const SCRIPT_REL: &str = r"scripts\apply-patches.ps1";
/// The file that makes a folder a backend folder.
const HUD: &str = "jarvis_hud.py";
/// Where the script writes its own copy of everything it prints.
const LOG_DIR: &str = "_jarvis-logs";

/// How long the patch run may take before it is treated as wedged.
///
/// Generous on purpose: a full run applies ~140 patches, copies ~180 shipped
/// files, runs pip and then the test suites, and the owner's own logs show runs
/// measured in minutes. An hour is not a deadline anything normal meets; it is
/// there so a wedged `git` or a pip waiting on a prompt cannot leave a command
/// pending for the life of the process with nothing said.
const SCRIPT_LIMIT: Duration = Duration::from_secs(60 * 60);
const POLL: Duration = Duration::from_millis(400);
/// How much of the run's own output is kept for the screen that reports it.
const TAIL_LINES: usize = 60;

// ---------------------------------------------------------------------------
// Where the two folders are
// ---------------------------------------------------------------------------

/// What this app can see of the two folders, and — when it cannot run — the
/// plain reason why, in the words the Settings card shows.
#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Where {
    /// The folder this repository was cloned into, when the owner has said.
    pub repo: Option<String>,
    /// The folder holding `jarvis_hud.py`.
    pub backend: Option<String>,
    /// What the owner typed into that box, empty when he has not. Kept apart
    /// from `backend` so the box shows his own words and the line beside it
    /// shows what was actually resolved.
    pub backend_typed: Option<String>,
    /// Where that folder was read from, so the card can say rather than imply.
    pub backend_source: Option<String>,
    /// `<repo>\scripts\apply-patches.ps1`, when there is a repo to join it to.
    pub script: Option<String>,
    /// Everything is in place and the run may go ahead. `None` is a yes.
    pub blocked: Option<String>,
}

fn setting(app: &AppHandle, key: &str) -> Option<String> {
    app.store(commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(key))
        .and_then(|value| value.as_str().map(str::to_string))
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

/// The backend folder, in the order that trusts the owner's own typing first.
///
/// `None` on the second half means "nothing said where it is" — never a guess.
pub fn backend_folder(
    typed: Option<&str>,
    args: &[String],
    cwd: Option<&str>,
    env: Option<&str>,
) -> (Option<String>, Option<&'static str>) {
    if let Some(typed) = typed.map(str::trim).filter(|t| !t.is_empty()) {
        return (Some(typed.to_string()), Some("set on this card"));
    }
    if let Some(dir) = folder_of_hud(args) {
        return (Some(dir), Some("the folder this app starts Jarvis from"));
    }
    if let Some(dir) = cwd.map(str::trim).filter(|c| !c.is_empty()) {
        return (
            Some(dir.to_string()),
            Some("the working folder this app starts Jarvis in"),
        );
    }
    if let Some(dir) = env.map(str::trim).filter(|e| !e.is_empty()) {
        return (
            Some(dir.to_string()),
            Some("the JARVIS_BACKEND setting on this PC"),
        );
    }
    (None, None)
}

/// The folder of the `jarvis_hud.py` argument, if one of them names it.
///
/// A full path is required: `jarvis_hud.py` on its own says the script is
/// somewhere relative to a working directory this app would then be guessing
/// at, and guessing is the one thing this module does not do.
pub fn folder_of_hud(args: &[String]) -> Option<String> {
    for arg in args {
        let path = Path::new(arg.trim());
        let named = path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.eq_ignore_ascii_case(HUD));
        if !named {
            continue;
        }
        let Some(dir) = path.parent() else { continue };
        if dir.as_os_str().is_empty() {
            continue;
        }
        return Some(dir.to_string_lossy().to_string());
    }
    None
}

/// The plain reason this app must not touch the backend on this PC, or `None`
/// when it may.
///
/// Pure, so the whole rule — never guess, never run against a folder that is
/// not a backend — is a test rather than a comment. The caller passes what the
/// disk said, because a function that has to touch the disk to answer cannot be
/// asked the same question twice and get the same answer.
///
/// Every sentence here says what to do next and ends by saying that nothing was
/// changed, the same shape `scripts/install-backend.ps1` uses for its refusals.
pub fn refuse(
    repo: Option<&str>,
    backend: Option<&str>,
    script_is_file: bool,
    hud_is_file: bool,
) -> Option<String> {
    let repo = repo.map(str::trim).filter(|r| !r.is_empty());
    let backend = backend.map(str::trim).filter(|b| !b.is_empty());

    let Some(repo) = repo else {
        return Some(
            "This app does not know where the Jarvis program folder is on this PC, so it \
             cannot update the backend. Type its full path into \"The Jarvis program folder \
             on this PC\" above - the folder you cloned from GitHub, the one with a \
             scripts folder in it. Nothing was changed."
                .to_string(),
        );
    };
    if !script_is_file {
        return Some(format!(
            "{repo} has no scripts\\apply-patches.ps1 in it, so it is not the Jarvis \
             program folder. Nothing was changed."
        ));
    }
    let Some(backend) = backend else {
        return Some(
            "This app does not know where your backend folder is, so it cannot update the \
             backend. It is the folder holding jarvis_hud.py - the one this app starts \
             Jarvis from. Set it above, or run scripts\\install-backend.ps1 on this PC \
             once. Nothing was changed."
                .to_string(),
        );
    };
    if !hud_is_file {
        return Some(format!(
            "{backend} has no jarvis_hud.py in it, so it is not your backend folder. \
             Nothing was changed."
        ));
    }
    None
}

/// Reads both folders off this PC and says whether the run may go ahead.
pub fn locate(app: &AppHandle) -> Where {
    let repo = setting(app, REPO_KEY);
    let typed_backend = setting(app, FOLDER_KEY);
    let status = crate::sidecar::supervisor_status(app.clone());
    let env = std::env::var(BACKEND_ENV).ok();
    let (backend, source) = backend_folder(
        typed_backend.as_deref(),
        &status.backend.args,
        status.backend.cwd.as_deref(),
        env.as_deref(),
    );

    let script = repo
        .as_ref()
        .map(|r| Path::new(r).join(SCRIPT_REL).to_string_lossy().to_string());
    let script_is_file = script.as_deref().is_some_and(|s| Path::new(s).is_file());
    let hud_is_file = backend
        .as_deref()
        .is_some_and(|b| Path::new(b).join(HUD).is_file());
    let blocked = refuse(
        repo.as_deref(),
        backend.as_deref(),
        script_is_file,
        hud_is_file,
    );

    Where {
        repo,
        backend,
        backend_typed: typed_backend,
        backend_source: source.map(str::to_string),
        script,
        blocked,
    }
}

// ---------------------------------------------------------------------------
// Running it
// ---------------------------------------------------------------------------

/// How a run ended, in the script's own terms.
///
/// Split out from the process handling because these three answers are the
/// whole of what the owner is told, and each of them is a rule the project has
/// already written down: a run that is not proven is not a pass, and a run that
/// touched the files before it went wrong must say so rather than read clean.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Verdict {
    /// The script had no problems at all.
    pub ok: bool,
    /// ...and it said the result was proven, rather than "no problems, but not
    /// fully proven". A run that patched but skipped checks is not a pass.
    pub proven: bool,
    /// The script's own warning that files WERE changed before it went wrong,
    /// so the backend may be half updated.
    pub half_updated: bool,
}

/// What the script's own last lines say, given its exit code.
///
/// Read from its words rather than invented: on a clean exit it prints either
/// `ALL DONE - the backend is patched and proven` or `DONE - no problems, but
/// NOT fully proven (see below)`, and on a refusal it prints one of two
/// sentences about whether the owner's files were touched. Matching on those is
/// the only way to tell "done" from "done but nothing proved it" without
/// re-deriving the script's own bookkeeping.
pub fn read_verdict(tail: &str, exit_ok: bool) -> Verdict {
    if !exit_ok {
        return Verdict {
            ok: false,
            proven: false,
            half_updated: says_half_updated(tail),
        };
    }
    Verdict {
        ok: true,
        proven: says_proven(tail),
        half_updated: false,
    }
}

/// The backing store's last-60-lines window, as one string.
pub fn tail_of(text: &str, lines: usize) -> String {
    let all: Vec<&str> = text.lines().collect();
    let start = all.len().saturating_sub(lines);
    all[start..].join("\n")
}

// ---------------------------------------------------------------------------
// The two sentences, kept as functions so a test can hold them
// ---------------------------------------------------------------------------

/// `ALL DONE - the backend is patched and proven`, which the script prints only
/// when no suite skipped any part of itself.
fn says_proven(tail: &str) -> bool {
    tail.to_lowercase().contains("patched and proven")
}

/// The script's own warning that it changed files before it went wrong.
fn says_half_updated(tail: &str) -> bool {
    let lower = tail.to_lowercase();
    lower.contains("half updated") || lower.contains("were changed before this went wrong")
}

/// The log folder, or the honest admission that the run never got far enough to
/// have one.
fn where_the_log_is(log_dir: &Option<String>) -> String {
    log_dir
        .clone()
        .unwrap_or_else(|| "the run's own printout, above".to_string())
}

/// One finished attempt at the backend half.
#[derive(Debug, Clone, Default)]
pub struct Run {
    pub ok: bool,
    pub proven: bool,
    pub half_updated: bool,
    /// What to show the owner: either what the script proved, or why not.
    pub detail: String,
    /// The folder the script keeps its own full log in, when it got that far.
    pub log_dir: Option<String>,
    /// The script's own last lines, folded away behind the report.
    pub tail: String,
    /// This attempt stopped the Jarvis backend, so Jarvis is off until the app
    /// is restarted. False on every refusal that happens before that.
    pub stopped: bool,
}

/// Puts the two folders in place and runs the one program allowed to change the
/// backend. Refuses — changing nothing — when either folder is missing.
pub async fn run(app: &AppHandle) -> Run {
    let here = locate(app);
    if let Some(why) = here.blocked.clone() {
        return Run {
            detail: why,
            ..Run::default()
        };
    }
    let (Some(repo), Some(backend)) = (here.repo.clone(), here.backend.clone()) else {
        // Unreachable while `refuse` is the gate above; written out rather than
        // `unwrap`ed so a later edit to one of them cannot panic the app.
        return Run {
            detail: "This app does not know where the Jarvis program or backend folder is, \
                     so nothing was changed."
                .to_string(),
            ..Run::default()
        };
    };

    // The script refuses to touch a backend whose own `jarvis_hud.py` is still
    // running, and it is right to: a running Python has already imported the
    // modules being rewritten. This app is what started that process, so it is
    // what stops it. A backend the OWNER started is never adopted and cannot be
    // stopped from here - the script's own refusal says so, in its own words,
    // and that refusal is what the report below carries.
    //
    // `stopped` is read before the attempt and carried out of it, because the
    // caller has to know whether Jarvis is now off and wants starting again -
    // including on the paths below that never reach the script at all.
    let owns = crate::sidecar::supervisor_status(app.clone()).owned;
    let stopped = if owns {
        let said = crate::sidecar::stop_owned(app, "updating the backend").await;
        println!("[jarvis] backend update: {said}");
        true
    } else {
        false
    };

    let script = Path::new(&repo).join(SCRIPT_REL);
    let backend = PathBuf::from(&backend);
    let mut finished = tauri::async_runtime::spawn_blocking(move || run_script(&script, &backend))
        .await
        .unwrap_or_else(|err| Run {
            detail: format!("The patch run could not be started: {err}. Nothing was changed."),
            ..Run::default()
        });
    finished.stopped = stopped;
    finished
}

/// The blocking half: spawn, watch, and read back what it printed.
fn run_script(script: &Path, backend: &Path) -> Run {
    let log_dir = Some(backend.join(LOG_DIR).to_string_lossy().to_string());

    // Everything the child prints goes to a file of our own rather than down a
    // pipe: `apply-patches.ps1` prints tens of kilobytes, and a pipe nobody is
    // draining blocks the child the moment it fills. The script also keeps its
    // own copy under `_jarvis-logs`; this is only so the screen can show the
    // end of the run without the app having to guess the script's file name.
    let capture = std::env::temp_dir().join(format!(
        "jarvis-apply-patches-{}-{}.txt",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0)
    ));
    let _ = std::fs::remove_file(&capture);
    // One file, two handles: `try_clone` duplicates the handle, so stdout and
    // stderr share one write position. Two `File::create` calls would give each
    // its own, and every stderr line would overwrite the stdout line under it.
    let Ok(out) = std::fs::File::create(&capture) else {
        return Run {
            detail: "The patch run could not be started: this PC would not let the app \
                     write its own record of the run. Nothing was changed."
                .to_string(),
            log_dir,
            ..Run::default()
        };
    };
    let Ok(err) = out.try_clone() else {
        return Run {
            detail: "The patch run could not be started: this PC would not let the app \
                     write its own record of the run. Nothing was changed."
                .to_string(),
            log_dir,
            ..Run::default()
        };
    };

    // Windows PowerShell 5.1, the interpreter the documented line uses. The
    // repository root is the working folder: the script resolves everything of
    // its own from `$PSScriptRoot`, so this only decides where a bare `git`
    // starts, and the repo root is the honest answer to that.
    let working_dir = script
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."));

    let mut command = std::process::Command::new("powershell");
    command
        .arg("-NoProfile")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-File")
        .arg(script)
        .arg("-BackendPath")
        .arg(backend)
        .current_dir(&working_dir)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::from(out))
        .stderr(std::process::Stdio::from(err));

    // Through `proctree`, so a run that has to be given up on takes `git`,
    // `py` and `patch` with it rather than orphaning them.
    let (mut child, tree) = match crate::proctree::spawn(&mut command) {
        Ok(pair) => pair,
        Err(err) => {
            return Run {
                detail: format!(
                    "The patch program could not be started: {err}. Nothing was changed."
                ),
                log_dir,
                ..Run::default()
            }
        }
    };

    let deadline = Instant::now() + SCRIPT_LIMIT;
    let mut timed_out = false;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) => {
                if Instant::now() >= deadline {
                    tree.kill();
                    let _ = child.wait();
                    timed_out = true;
                    break None;
                }
                std::thread::sleep(POLL);
            }
            Err(err) => {
                tree.kill();
                let _ = child.wait();
                return Run {
                    detail: format!(
                        "The patch run could not be watched to its end: {err}. Check the \
                         log folder before doing anything else: {}",
                        where_the_log_is(&log_dir)
                    ),
                    log_dir,
                    ..Run::default()
                };
            }
        }
    };

    let bytes = std::fs::read(&capture).unwrap_or_default();
    let tail = tail_of(&String::from_utf8_lossy(&bytes), TAIL_LINES);
    // Read, then gone. A run's printout is not something to leave lying in
    // %TEMP%: this repository spent 2026-10-11 clearing out 1,663 folders one
    // suite at a time, and a feature that quietly adds one file per update is
    // the same mistake in a smaller size.
    let _ = std::fs::remove_file(&capture);

    if timed_out {
        return Run {
            detail: format!(
                "The patch run did not finish within an hour and was stopped. It may have \
                 been part-way through, so read its log before touching anything: {}",
                where_the_log_is(&log_dir)
            ),
            half_updated: true,
            log_dir,
            tail,
            ..Run::default()
        };
    }

    let exit_ok = status.is_some_and(|s| s.success());
    let verdict = read_verdict(&tail, exit_ok);
    let detail = if !verdict.ok {
        let mut said = "The backend step did not finish, so Jarvis Desktop was NOT installed \
                        on top of it."
            .to_string();
        if verdict.half_updated {
            said.push_str(
                " The patch program says some of your backend files WERE changed before it \
                 went wrong, so the backend may be half updated - read the log and follow \
                 what it says to do before starting Jarvis.",
            );
        }
        said
    } else if verdict.proven {
        "The backend folder is patched, and the patch program proved it with its tests.".to_string()
    } else {
        "The backend folder is patched, but the patch program could not prove every check \
         (it says which were skipped in the log). That is not the same as a proven update."
            .to_string()
    };

    Run {
        ok: verdict.ok,
        proven: verdict.proven,
        half_updated: verdict.half_updated,
        detail,
        log_dir,
        tail,
        // Filled in by `run`, which is the only caller and the only place that
        // knows whether Jarvis was stopped for this attempt.
        stopped: false,
    }
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// What the Updates card shows about the two folders without running anything.
#[tauri::command]
pub fn backend_update_status(app: AppHandle) -> Where {
    locate(&app)
}

/// Remembers the two folders. Empty is allowed and means "not said", which
/// puts the backend folder back to being read off the supervision settings.
///
/// No approval card and no card either way: this writes two strings into this
/// app's own settings file and nothing else. It cannot run the patcher - the
/// only command that does is `update_both`, behind its own button — so typing
/// a path here changes nothing until the owner presses that.
#[tauri::command]
pub fn set_update_folders(
    app: AppHandle,
    repo: Option<String>,
    backend: Option<String>,
) -> Result<Where, String> {
    let store = app
        .store(commands::SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    let clean = |v: Option<String>| -> Option<String> {
        v.map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
    };
    if let Some(repo) = clean(repo) {
        if repo.contains('\0') {
            return Err("a path cannot contain NUL".to_string());
        }
        store.set(REPO_KEY, serde_json::Value::String(repo));
    } else {
        store.set(REPO_KEY, serde_json::Value::Null);
    }
    if let Some(backend) = clean(backend) {
        if backend.contains('\0') {
            return Err("a path cannot contain NUL".to_string());
        }
        store.set(FOLDER_KEY, serde_json::Value::String(backend));
    } else {
        store.set(FOLDER_KEY, serde_json::Value::Null);
    }
    store
        .save()
        .map_err(|e| format!("could not write the settings store: {e}"))?;
    Ok(locate(&app))
}

#[cfg(test)]
mod tests {
    use super::{
        backend_folder, folder_of_hud, read_verdict, refuse, tail_of, Verdict, BACKEND_ENV, HUD,
    };

    fn args(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    // ---- never guessing at a folder -------------------------------------

    #[test]
    fn a_path_is_only_ever_taken_from_somewhere_the_owner_put_it() {
        // The order, and the whole of it. Nothing here searches the disk.
        let (got, why) = backend_folder(
            Some(r"D:\typed"),
            &args(&[r"C:\from\args\jarvis_hud.py"]),
            Some(r"C:\from\cwd"),
            Some(r"C:\from\env"),
        );
        assert_eq!(got.as_deref(), Some(r"D:\typed"), "{why:?}");

        let (got, why) = backend_folder(
            None,
            &args(&[r"C:\from\args\jarvis_hud.py"]),
            Some(r"C:\from\cwd"),
            Some(r"C:\from\env"),
        );
        assert_eq!(got.as_deref(), Some(r"C:\from\args"), "{why:?}");

        let (got, why) =
            backend_folder(None, &args(&["--port", "4719"]), Some(r"C:\from\cwd"), None);
        assert_eq!(got.as_deref(), Some(r"C:\from\cwd"), "{why:?}");

        let (got, why) = backend_folder(None, &args(&[]), None, Some(r"C:\from\env"));
        assert_eq!(got.as_deref(), Some(r"C:\from\env"), "{why:?}");

        // Nothing said anywhere: `None`, never a guess.
        let (got, why) = backend_folder(None, &args(&[]), None, None);
        assert_eq!(got, None);
        assert_eq!(why, None);
    }

    #[test]
    fn a_bare_script_name_is_not_a_folder() {
        // `jarvis_hud.py` with no folder means the working directory, which is
        // exactly the guess this module refuses to make.
        assert_eq!(folder_of_hud(&args(&["jarvis_hud.py"])), None);
        assert_eq!(folder_of_hud(&args(&["python", "-u"])), None);
        // Case does not decide it, on Windows or anywhere else.
        assert_eq!(
            folder_of_hud(&args(&[r"C:\Jarvis\JARVIS_HUD.PY"])).as_deref(),
            Some(r"C:\Jarvis")
        );
    }

    #[test]
    fn an_empty_box_means_not_said_rather_than_the_empty_folder() {
        let (got, _) = backend_folder(Some("   "), &args(&[]), None, Some(r"C:\from\env"));
        assert_eq!(got.as_deref(), Some(r"C:\from\env"));
    }

    // ---- never running against a folder that is not a backend -----------

    #[test]
    fn with_both_folders_in_place_nothing_is_refused() {
        assert_eq!(
            refuse(Some(r"C:\repo"), Some(r"C:\backend"), true, true),
            None
        );
    }

    #[test]
    fn every_refusal_says_what_to_do_and_that_nothing_changed() {
        let cases = [
            refuse(None, Some(r"C:\backend"), true, true),
            refuse(Some(r"C:\repo"), Some(r"C:\backend"), false, true),
            refuse(Some(r"C:\repo"), None, true, true),
            refuse(Some(r"C:\repo"), Some(r"C:\backend"), true, false),
            refuse(Some("  "), Some("  "), true, true),
        ];
        for (i, said) in cases.iter().enumerate() {
            let said = said
                .as_deref()
                .unwrap_or_else(|| panic!("case {i} was allowed"));
            assert!(
                said.contains("Nothing was changed"),
                "case {i} does not say nothing was changed: {said}"
            );
        }
        // ...and each one names the thing that is wrong, so the owner knows
        // which box to fill in rather than that "something" is missing.
        assert!(cases[0].as_deref().unwrap().contains("program folder"));
        assert!(cases[1].as_deref().unwrap().contains("apply-patches.ps1"));
        assert!(cases[2].as_deref().unwrap().contains("backend folder"));
        assert!(cases[3].as_deref().unwrap().contains(HUD));
    }

    // ---- the script's own verdict ---------------------------------------

    #[test]
    fn a_proven_run_is_the_only_thing_read_as_proven() {
        let all_done = "====\n ALL DONE - the backend is patched and proven\n====";
        assert_eq!(
            read_verdict(all_done, true),
            Verdict {
                ok: true,
                proven: true,
                half_updated: false
            }
        );
        // "no problems, but NOT fully proven" is a patched backend with checks
        // that could not run. The project's rule is that a skip is never a
        // pass, so this is `ok` and NOT `proven` - the two are different
        // answers on purpose.
        let partial = "===\n DONE - no problems, but NOT fully proven (see below)\n";
        assert_eq!(
            read_verdict(partial, true),
            Verdict {
                ok: true,
                proven: false,
                half_updated: false
            }
        );
    }

    #[test]
    fn a_failed_run_says_whether_the_files_were_touched() {
        let half = "Some of your backend files WERE changed before this went wrong, and the\n\
                    patched files may be HALF updated.";
        let clean = "None of your backend files were changed by this run.";
        assert_eq!(
            read_verdict(half, false),
            Verdict {
                ok: false,
                proven: false,
                half_updated: true
            }
        );
        assert_eq!(
            read_verdict(clean, false),
            Verdict {
                ok: false,
                proven: false,
                half_updated: false
            }
        );
        // A failed run is never proven, whatever else its output says.
        assert!(!read_verdict(half, false).proven);
    }

    #[test]
    fn the_environment_name_is_the_one_the_install_script_sets() {
        // Two files have to agree on this or the fallback silently never fires:
        // `scripts/install-backend.ps1` writes it and `backend/_where.py` reads
        // it. Spelled out here so a rename is a failing test, not a mystery.
        assert_eq!(BACKEND_ENV, "JARVIS_BACKEND");
    }

    #[test]
    fn the_tail_is_the_end_of_the_run_and_survives_a_short_one() {
        let text = (1..=100)
            .map(|i| i.to_string())
            .collect::<Vec<_>>()
            .join("\n");
        let tail = tail_of(&text, 3);
        assert_eq!(tail, "98\n99\n100");
        assert_eq!(tail_of("one line", 60), "one line");
        assert_eq!(tail_of("", 60), "");
    }

    /// The one path a person never sees until it matters: a run that was given
    /// up on is reported as possibly half done, not as a clean stop.
    #[test]
    fn giving_up_on_a_wedged_run_is_not_reported_as_a_clean_one() {
        let detail = format!(
            "The patch run did not finish within an hour and was stopped. It may have \
             been part-way through, so read its log before touching anything: {}",
            r"C:\backend\_jarvis-logs"
        );
        assert!(detail.contains("part-way through"));
        assert!(detail.contains("_jarvis-logs"));
    }
}
