//! "Check my setup": run the live preflight and hand its words back to the window.
//!
//! WHY THIS RUNS THE REPOSITORY'S COPY INSTEAD OF ONE SHIPPED INTO HIS BACKEND
//! FOLDER (measured 2026-10-11). `backend/selftest.py --preflight` is the live
//! health check - "the Jarvis that is RUNNING now, every chain end to end",
//! read-only, ending "N pass, N fail, N warn" - and its most valuable answer on
//! this PC is the six lines that say his deployment is behind (`work.patch`,
//! `card-prefs.patch` and `pictures.patch` not in `jarvis_hud.py`, and
//! `jarvis_work.py`, `jarvis_card_summary.py`, `jarvis_pictures.py` absent).
//! That check imports `_stack` (which imports `_gitapply`) and reads every
//! `backend/*.patch` - 144 files - to work out which lines each patch adds.
//! NONE of those four files and NONE of that patch tree is in his live backend
//! folder: shipping the tool whole would mean 148 files inside his running
//! install, including a duplicate patch tree that has to be kept in step with
//! this repository for ever. A health check comparing against the WRONG patches
//! and saying everything is fine is worse than one that cannot compare, so the
//! panel runs THIS repository's copy - the very command `README.md` and
//! `docs/INSTALL.md` 1.10 already give him - and tells him both folders.
//!
//! READ-ONLY, AND THE TOKEN NEVER PASSES THROUGH HERE. `--preflight` approves
//! nothing, sends no email, unloads no model and changes no setting (its own
//! docstring); it reads the pairing token itself, from the same places the
//! backend does. This module passes no token in any argument or environment
//! variable, and never prints one - `t_no_token_anywhere` holds that.

use serde::Serialize;
use std::path::{Path, PathBuf};
use std::process::Command;

use tauri::AppHandle;

/// Where a clone is, when it is not in the documented place.
///
/// `docs/INSTALL.md` tells the owner to clone to `%USERPROFILE%\Epic-Jarvis`,
/// and that is the default - so the common case needs no setting at all. This
/// key is the row for "somewhere else", and nothing else.
const REPO_KEY: &str = "preflight_repo";

/// What the panel shows. Everything is filled in, always: a run that could not
/// happen carries the reason in `why` rather than an empty summary.
#[derive(Debug, Clone, Serialize)]
pub struct PreflightRun {
    /// The folder the checker ran FROM (the repository).
    pub ran_from: String,
    /// The backend folder it was told to CHECK (`JARVIS_BACKEND`).
    pub checked: String,
    /// Every line the checker printed, exactly as printed.
    pub text: String,
    /// Whether it exited 0 - no FAIL line.
    pub ok: bool,
    /// The exit code, or `None` when it never started.
    pub code: Option<i32>,
    /// Why nothing ran, in words. Empty when it ran.
    pub why: String,
}

/// The documented clone location, per `docs/INSTALL.md` §1.1.
fn default_repo() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(PathBuf::from))
        .unwrap_or_default()
        .join("Epic-Jarvis")
}

/// The repository to run from: the configured one, else the documented clone.
fn repo_dir(app: &AppHandle) -> PathBuf {
    use tauri_plugin_store::StoreExt;
    app.store(crate::commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(REPO_KEY))
        .and_then(|value| value.as_str().map(str::to_string))
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(default_repo)
}

/// The command, exactly as it is built - separated so a test can read its own
/// arguments and environment without starting anything.
fn command_for(program: &str, repo: &Path, backend: &Path) -> Command {
    let mut command = Command::new(program);
    command
        .arg(repo.join("backend").join("selftest.py"))
        .arg("--preflight")
        .env("JARVIS_BACKEND", backend)
        // The checker prints check marks and dashes; without this a Windows
        // console defaults to a code page that mangles them.
        .env("PYTHONIOENCODING", "utf-8")
        .current_dir(repo.join("backend"));
    command
}

/// Run the preflight. Never panics; every failure is a sentence in `why`.
fn run_preflight(repo: &Path, backend: Option<&Path>, program: Option<&str>) -> PreflightRun {
    let checker = repo.join("backend").join("selftest.py");
    let backend_display = backend
        .map(|p| p.display().to_string())
        .unwrap_or_else(|| "(the app does not know it yet)".to_string());
    let mut run = PreflightRun {
        ran_from: repo.display().to_string(),
        checked: backend_display,
        text: String::new(),
        ok: false,
        code: None,
        why: String::new(),
    };
    if !checker.is_file() {
        run.why = format!(
            "No Jarvis repository at {} - there is no backend/selftest.py to run. \
             Clone it there, or set the folder in Settings.",
            repo.display()
        );
        return run;
    }
    let Some(backend) = backend else {
        run.why = "The app does not know which folder Jarvis runs from yet, so it \
                   cannot check it. Turn on \"Let Jarvis Desktop start and stop \
                   Jarvis\" in Settings and set the program there."
            .to_string();
        return run;
    };
    let Some(program) = program.map(str::trim).filter(|p| !p.is_empty()) else {
        run.why = "The app does not know which Python runs Jarvis yet. Turn on \
                   \"Let Jarvis Desktop start and stop Jarvis\" in Settings and set \
                   the program there."
            .to_string();
        return run;
    };
    match command_for(program, repo, backend).output() {
        Ok(out) => {
            let mut text = String::from_utf8_lossy(&out.stdout).to_string();
            let err = String::from_utf8_lossy(&out.stderr);
            if !err.trim().is_empty() {
                text.push_str("\n");
                text.push_str(&err);
            }
            run.text = text.trim_end().to_string();
            run.code = out.status.code();
            run.ok = out.status.success();
            run
        }
        Err(exc) => {
            run.why = format!(
                "The check could not start: {exc}. Is the program above still installed?"
            );
            run
        }
    }
}

/// The button: run the repository's preflight against the running Jarvis.
///
/// No token, no card, no change: the checker is read-only and this only reads
/// its output. The two folders are returned so the panel can show the folder it
/// ran FROM next to the folder it CHECKED - the pair is what answers "is it even
/// looking at my Jarvis?".
#[tauri::command]
pub fn check_my_setup(app: AppHandle) -> PreflightRun {
    let repo = repo_dir(&app);
    let backend = crate::sidecar::backend_dir(&app);
    let program = crate::sidecar::backend_program(&app);
    run_preflight(&repo, backend.as_deref(), program.as_deref())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn t_missing_clone_says_so_in_words() {
        let run = run_preflight(Path::new("/nowhere/at/all"), None, None);
        assert!(run.text.is_empty());
        assert!(run.code.is_none());
        assert!(run.why.contains("no backend/selftest.py"), "{}", run.why);
        assert!(run.ran_from.contains("nowhere"));
    }

    #[test]
    fn t_unknown_folder_and_python_are_named_not_silent() {
        let repo = std::env::temp_dir();
        std::fs::create_dir_all(repo.join("backend")).ok();
        std::fs::write(repo.join("backend").join("selftest.py"), b"# stand-in\n").ok();
        let no_backend = run_preflight(&repo, None, Some("python"));
        assert!(no_backend.why.contains("which folder Jarvis runs from"), "{}", no_backend.why);
        let no_python = run_preflight(&repo, Some(Path::new("/tmp")), None);
        assert!(no_python.why.contains("which Python runs Jarvis"), "{}", no_python.why);
        std::fs::remove_file(repo.join("backend").join("selftest.py")).ok();
    }

    #[test]
    fn t_the_command_is_the_documented_one_and_carries_no_token() {
        let command = command_for("py", Path::new("/repo"), Path::new("/backend folder"));
        let args: Vec<String> = command
            .get_args()
            .map(|a| a.to_string_lossy().to_string())
            .collect();
        assert!(args.iter().any(|a| a.ends_with("selftest.py")), "{args:?}");
        assert!(args.iter().any(|a| a == "--preflight"), "{args:?}");
        let envs: Vec<(String, String)> = command
            .get_envs()
            .map(|(k, v)| {
                (
                    k.to_string_lossy().to_string(),
                    v.map(|v| v.to_string_lossy().to_string()).unwrap_or_default(),
                )
            })
            .collect();
        let names: Vec<&str> = envs.iter().map(|(k, _)| k.as_str()).collect();
        assert!(names.contains(&"JARVIS_BACKEND"), "{names:?}");
        assert!(names.contains(&"PYTHONIOENCODING"), "{names:?}");
        // THE CLAIM A REVIEWER WILL WANT: nothing here names a token.
        for (key, value) in &envs {
            let both = format!("{key}={value}").to_lowercase();
            assert!(!both.contains("token"), "an environment variable names a token: {both}");
        }
        for arg in &args {
            assert!(!arg.to_lowercase().contains("token"), "an argument names a token: {arg}");
        }
    }
}
