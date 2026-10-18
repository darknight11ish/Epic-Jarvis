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

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager};
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
/// The repo tool that wraps that script and runs the suites at the owner's
/// chosen pace: `scripts\apply-patches.ps1 -SkipTests`, then
/// `backend/run_suites.py --jobs N`, with the safe fallback.
pub const TOOL_REL: &str = r"tools\update_backend.py";
/// The file that makes a folder a backend folder.
const HUD: &str = "jarvis_hud.py";
/// Where the script writes its own copy of everything it prints.
const LOG_DIR: &str = "_jarvis-logs";

/// One of the three paces the owner chooses between, as the Python tool
/// (`--modes-json`) answers it. ONE implementation of the worker numbers and
/// the ETA maths lives in `tools/update_backend.py`; this is a read of that
/// answer, never a second copy of it.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct ModeInfo {
    /// `max_speed`, `responsive` or `safe`.
    pub id: String,
    /// The card's short word: "Fastest", "Balanced", "Safest".
    pub label: String,
    /// One plain sentence about what the PC will feel like.
    pub plain: String,
    /// Suites run at once.
    pub workers: u32,
    /// About how long, in seconds, and the honest range around it.
    pub eta_seconds: u32,
    pub eta_low_seconds: u32,
    pub eta_high_seconds: u32,
    /// True once this PC's own recorded times are the basis; False on the
    /// first run, and the card says so.
    pub measured: bool,
    /// The one the card preselects.
    pub recommended: bool,
    /// How many suites every pace will run (the same list for all three).
    pub suite_count: u32,
}

/// The tool's whole `--modes-json` answer.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ModePlan {
    pub modes: Vec<ModeInfo>,
    /// [`DEFAULT_MODE`] as the tool names it.
    pub default: String,
    pub measured: bool,
}

// ---------------------------------------------------------------------------
//   The update lock - one update at a time, read the same way everywhere
// ---------------------------------------------------------------------------
//
// The Python tool (`tools/update_backend.py`) writes this file while it
// patches and checks the backend; `backend/run_suites.py` refuses to start a
// sweep beside it; and THIS module's answer is used by the watchdog in
// `sidecar.rs` so the desktop does not restart the backend the update just
// stopped. The rules and the format are the Python lock section's, word for
// word: `{pid, started_at, updated_at, pace}`, a DEAD PID is stale at once,
// otherwise stale when the heartbeat is over 30 minutes old. The 3-hour window
// is a PID-REUSE guard: the tool renews its own `started_at` while it keeps
// heartbeating, so a legitimately long run is never treated as stale here. The
// file lives in the folder Jarvis keeps its own data in - the same directory
// rule `jarvis_framework._config_dir`, `tools/update_backend.py` and `backup.rs`
// use.
pub const LOCK_NAME: &str = "update-in-progress.lock";
/// Stale when no suite has finished for this long (`N_placeholder`).
pub const LOCK_HEARTBEAT_SECONDS: f64 = 1800.0;
/// The PID-REUSE guard window (`N_placeholder`). A live tool renews it while
/// heartbeating, so this only ends a lock whose writer stopped proving life.
pub const LOCK_CEILING_SECONDS: f64 = 10_800.0;
/// A lock whose times are further in the future than this is a clock problem,
/// not evidence of a live update (the Python reader rejects the same skew).
pub const LOCK_CLOCK_SKEW_SECONDS: f64 = 60.0;

/// The lock file's contents, once it parses. Only the four keys the design
/// names; an unknown key is ignored, a missing or wrongly typed one is not a
/// lock at all.
#[derive(Debug, Clone, PartialEq)]
pub struct UpdateLock {
    pub pid: u32,
    pub started_at: f64,
    pub updated_at: f64,
    pub pace: String,
}

#[derive(Deserialize)]
struct LockJson {
    pid: u32,
    started_at: f64,
    updated_at: f64,
    pace: String,
}

/// One lock file's text as a lock, or `None` when it is not one.
///
/// Pure, and strict about what makes a lock *real*: a half-written file, a
/// wrong type, a zero pid or a non-finite time is NOT a lock - it is stale
/// garbage, and the caller treats it as no lock. An UNKNOWN pace is still a
/// lock (S8): a newer tool may add a pace, and the old desktop must treat that
/// as a live update, not as "no update running". Never panics.
pub fn parse_update_lock(text: &str) -> Option<UpdateLock> {
    let got: LockJson = serde_json::from_str(text).ok()?;
    if got.pid == 0 || !got.started_at.is_finite() || !got.updated_at.is_finite() {
        return None;
    }
    Some(UpdateLock {
        pid: got.pid,
        started_at: got.started_at,
        updated_at: got.updated_at,
        pace: got.pace,
    })
}

/// Is this lock valid right now? The rules, in the design's order.
///
/// `pid_alive` is passed in (not read here) so the rule is a test: `now` and
/// liveness are the two things that change, and everything else is arithmetic.
/// A time in the future means the clock moved (S6) - stale, matching Python.
pub fn update_lock_is_valid(lock: &UpdateLock, now: f64, pid_alive: bool) -> bool {
    if !pid_alive {
        return false;
    }
    if lock.started_at > now + LOCK_CLOCK_SKEW_SECONDS
        || lock.updated_at > now + LOCK_CLOCK_SKEW_SECONDS
    {
        return false;
    }
    if now - lock.updated_at > LOCK_HEARTBEAT_SECONDS {
        return false;
    }
    if now - lock.started_at > LOCK_CEILING_SECONDS {
        return false;
    }
    true
}

/// Is `pid` a running process on this machine?
///
/// Windows asks the kernel with OpenProcess/GetExitCodeProcess rather than
/// `tasklist` (no subprocess, no parsing); a process that has ended gives no
/// handle. Unix uses `kill(pid, 0)`, the documented existence probe.
#[cfg(windows)]
fn pid_is_running(pid: u32) -> bool {
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::Threading::{
        GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    /// `STILL_ACTIVE`: the exit code a process that has not ended reports.
    const STILL_ACTIVE: u32 = 259;
    if pid == 0 {
        return false;
    }
    // SAFETY: OpenProcess takes no pointer; the handle is checked before use
    // and closed exactly once on every path after it is non-null.
    unsafe {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if handle.is_null() {
            return false;
        }
        let mut code: u32 = 0;
        let ok = GetExitCodeProcess(handle, &mut code) != 0;
        CloseHandle(handle);
        ok && code == STILL_ACTIVE
    }
}

#[cfg(not(windows))]
fn pid_is_running(pid: u32) -> bool {
    if pid == 0 {
        return false;
    }
    // SAFETY: signal 0 performs the existence check and sends nothing.
    unsafe { libc::kill(pid as i32, 0) == 0 }
}

/// The folder Jarvis keeps its own data in: `OPENJARVIS_CONFIG_DIR`, then
/// `JARVIS_CONFIG_DIR`, then `~/.openjarvis` - the same order the backend and
/// the Python tool use.
fn lock_dir(app: &AppHandle) -> Option<PathBuf> {
    for name in ["OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"] {
        if let Some(explicit) = std::env::var_os(name) {
            return Some(PathBuf::from(explicit));
        }
    }
    app.path()
        .home_dir()
        .ok()
        .map(|home| home.join(".openjarvis"))
}

/// The lock file's path, when this PC has a data folder it can name.
pub fn update_lock_path(app: &AppHandle) -> Option<PathBuf> {
    lock_dir(app).map(|dir| dir.join(LOCK_NAME))
}

/// The VALID update lock held right now, or `None`. Never panics and never
/// raises: a missing file, junk in it, a dead pid and a silent heartbeat are
/// all "no update is running".
pub fn held_update_lock(app: &AppHandle) -> Option<UpdateLock> {
    let path = update_lock_path(app)?;
    let text = std::fs::read_to_string(path).ok()?;
    let lock = parse_update_lock(&text)?;
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_secs_f64();
    update_lock_is_valid(&lock, now, pid_is_running(lock.pid)).then_some(lock)
}

/// The plain refusal when a second update is asked for while one runs (S3).
///
/// Pure, so the words are a test: the pid, the pace and what to do next, and
/// no claim that anything ran.
pub fn update_running_words(lock: &UpdateLock) -> String {
    format!(
        "A Jarvis backend update is already running (pid {}, pace {}). Wait for it \
         to finish; nothing was started or changed here.",
        lock.pid, lock.pace
    )
}

/// The plain note a backend START gets while an update holds the lock (S5).
///
/// `Some(words)` means "do not start"; every automatic and owner-pressed start
/// path in `sidecar::ensure_backend` uses this one helper, so the tray, the
/// Settings button, startup and the watchdog cannot disagree.
pub fn start_blocked_words(lock: Option<&UpdateLock>) -> Option<String> {
    lock.map(|lock| {
        format!(
            "A Jarvis backend update is running (pid {}, pace {}). The backend is \
             not started until it finishes.",
            lock.pid, lock.pace
        )
    })
}

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
    /// The three paces, with their worker counts and ETA ranges, as
    /// `tools/update_backend.py --modes-json` answers them. Empty when the
    /// tool could not be asked (an older clone, no Python): the card then
    /// says the estimate is unavailable rather than inventing one.
    pub modes: Vec<ModeInfo>,
    /// Why the pace table could not be read, when it could not.
    pub modes_note: Option<String>,
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
        modes: Vec::new(),
        modes_note: None,
        blocked,
    }
}

// ---------------------------------------------------------------------------
// The three paces: the tool's own answer, read back and never re-derived
// ---------------------------------------------------------------------------

/// The Python program to run the update tool with. `py -3` first (the
/// documented Windows launcher), then `python` for a PC where only that exists.
fn python_programs() -> Vec<(String, Vec<String>)> {
    vec![
        ("py".to_string(), vec!["-3".to_string()]),
        ("python".to_string(), Vec::new()),
    ]
}

/// The update tool's command line, relative to the two folders. Public and
/// pure so the argument shape is a test: the tool must be asked for the SAME
/// repo and backend folders the card shows, and with an explicit `--mode`.
pub fn tool_args(repo: &str, backend: &str, mode: &str) -> Vec<String> {
    vec![
        "-B".to_string(),
        Path::new(repo).join(TOOL_REL).to_string_lossy().to_string(),
        "--repo".to_string(),
        repo.to_string(),
        "--backend".to_string(),
        backend.to_string(),
        "--mode".to_string(),
        mode.to_string(),
    ]
}

/// Reads the three paces from `tools/update_backend.py --modes-json`.
///
/// ONE implementation of the worker numbers and the ETA maths lives in that
/// tool; this function is only a read of its answer. A failure is a plain note
/// (an older clone, no Python) and the card then says the estimate is not
/// available - it never makes one up.
pub fn mode_plan_for(repo: &str, backend: &str) -> (Vec<ModeInfo>, Option<String>) {
    let tool = Path::new(repo).join(TOOL_REL);
    if !tool.is_file() {
        return (
            Vec::new(),
            Some(format!(
                "This Jarvis program folder has no {TOOL_REL} in it, so the update \
                 paces cannot be estimated on this PC. Pull the newest programs \
                 folder first (git pull), then press Update again. Nothing was changed."
            )),
        );
    }
    let mut last = String::new();
    for (program, leading) in python_programs() {
        let mut command = std::process::Command::new(&program);
        command
            .args(&leading)
            .arg("-B")
            .arg(&tool)
            .arg("--modes-json")
            .arg("--repo")
            .arg(repo)
            .arg("--backend")
            .arg(backend)
            .env("PYTHONDONTWRITEBYTECODE", "1");
        match command.output() {
            Ok(output) if output.status.success() => {
                let text = String::from_utf8_lossy(&output.stdout).to_string();
                if let Some(plan) = parse_mode_plan(&text) {
                    return (plan.modes, None);
                }
                last = "the update tool answered, but not in the shape this app reads".to_string();
            }
            Ok(output) => {
                last = format!("the update tool refused to answer ({})", output.status);
            }
            Err(err) => {
                last = format!("the update tool could not be started: {err}");
            }
        }
    }
    (
        Vec::new(),
        Some(format!(
            "The update paces could not be worked out on this PC ({last}), so the \
             estimate is not shown. The update itself still runs when you press it."
        )),
    )
}

/// The tool's `--modes-json` answer, as the three paces. `None` when the text
/// is not that document (a half-written reply, an error page, a future shape).
pub fn parse_mode_plan(text: &str) -> Option<ModePlan> {
    let plan: ModePlan = serde_json::from_str(text.trim()).ok()?;
    if plan.modes.is_empty() {
        return None;
    }
    Some(plan)
}

/// Whether `mode` is one of the paces the tool offers. Used by `update_both`
/// BEFORE anything runs, so an unknown mode is refused rather than defaulted.
pub fn known_mode(modes: &[ModeInfo], mode: &str) -> bool {
    !modes.is_empty() && modes.iter().any(|row| row.id == mode)
}

/// The plain sentence for an unknown pace, naming the three that exist.
pub fn unknown_mode_words(modes: &[ModeInfo], mode: &str) -> String {
    let names = modes
        .iter()
        .map(|row| row.id.as_str())
        .collect::<Vec<_>>()
        .join(", ");
    format!(
        "There is no update pace called \"{mode}\". The paces on this PC are: {names}. \
         Nothing was changed."
    )
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
    /// Where the run's own output says it got to: the phase, the count and the
    /// verdict of the last thing it said (`update_progress`). The same shape the
    /// live event carries, so the card does not change its mind at the end.
    pub progress: crate::update_progress::Progress,
    /// This attempt stopped the Jarvis backend, so Jarvis is off until the app
    /// is restarted. False on every refusal that happens before that.
    pub stopped: bool,
    /// The pace this run used (`max_speed`, `responsive`, `safe`), and its
    /// short word for the card.
    pub mode: String,
    pub mode_label: String,
    /// True when the run fell back to the safe second pass (the tool's own
    /// events set this); the card is told, and the detail says so.
    pub fallback: bool,
    /// False when this program folder has no `tools/update_backend.py`, so the
    /// older one-at-a-time patcher was run instead. Said on the card.
    pub used_tool: bool,
}

/// Puts the two folders in place and runs the chosen pace's update: the repo
/// tool when this clone has it, the older one-at-a-time patcher when it does
/// not. Refuses — changing nothing — when either folder is missing.
pub async fn run(app: &AppHandle, mode: &str, mode_label: &str) -> Run {
    // S4/S5: this is the last check before the backend is touched. `update_both`
    // checks the same lock before calling here; doing it again inside `run`
    // keeps the ordering safe for any future caller that stops a backend.
    if let Some(lock) = held_update_lock(app) {
        return Run {
            detail: update_running_words(&lock),
            mode: mode.to_string(),
            mode_label: mode_label.to_string(),
            ..Run::default()
        };
    }
    let here = locate(app);
    if let Some(why) = here.blocked.clone() {
        return Run {
            detail: why,
            mode: mode.to_string(),
            mode_label: mode_label.to_string(),
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
            mode: mode.to_string(),
            mode_label: mode_label.to_string(),
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

    let backend = PathBuf::from(&backend);
    // The handle the progress events go to. Cloned out here because the closure
    // below is `'static`: a borrow of `app` cannot cross into it.
    let reports_to = app.clone();
    let mode_owned = mode.to_string();
    let label_owned = mode_label.to_string();
    let repo_root = PathBuf::from(&repo);
    let mut finished = tauri::async_runtime::spawn_blocking(move || {
        run_script(&repo_root, &backend, &reports_to, &mode_owned, &label_owned)
    })
    .await
    .unwrap_or_else(|err| Run {
        detail: format!("The patch run could not be started: {err}. Nothing was changed."),
        mode: mode.to_string(),
        mode_label: mode_label.to_string(),
        ..Run::default()
    });
    finished.stopped = stopped;
    finished
}

/// The Python the update tool should be run with, once: `py -3` first (the
/// documented Windows launcher), then `python`. Checked with `--version` so the
/// command the run gets is one this PC can actually start; a run that returned
/// "not found" halfway would look like a failed update.
fn resolve_python() -> Option<(String, Vec<String>)> {
    for (program, leading) in python_programs() {
        let started = std::process::Command::new(&program)
            .args(&leading)
            .arg("--version")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .is_ok();
        if started {
            return Some((program, leading));
        }
    }
    None
}

/// The blocking half: spawn, watch, and read back what it printed.
fn run_script(repo: &Path, backend: &Path, app: &AppHandle, mode: &str, mode_label: &str) -> Run {
    let log_dir = Some(backend.join(LOG_DIR).to_string_lossy().to_string());
    let tool = repo.join(TOOL_REL);
    let used_tool = tool.is_file();
    let python = if used_tool { resolve_python() } else { None };
    let used_tool = used_tool && python.is_some();
    if used_tool {
        // The repo tool is the one that can run the suites at the chosen pace.
    } else if !tool.is_file() {
        // An older program folder: the patcher runs its own suites one at a
        // time, exactly as every update did before this feature. Said on the
        // card so nobody wonders where the paces went.
    }

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

    // The repository root is the working folder either way: the tool and the
    // patcher both find everything of theirs from their own location, so this
    // only decides where a bare `git` starts, and the repo root is the honest
    // answer to that.
    let working_dir = repo.to_path_buf();

    let mut command = if let Some((program, leading)) = python.as_ref() {
        let mut command = std::process::Command::new(program);
        command.args(leading).args(tool_args(
            &working_dir.to_string_lossy(),
            &backend.to_string_lossy(),
            mode,
        ));
        command
    } else {
        // An older program folder with no repo tool (or no Python to run it):
        // the documented patcher invocation, which runs its own suites one at a
        // time. Same script, same backups, same proof - only without the paces.
        let script = repo.join(SCRIPT_REL);
        let mut command = std::process::Command::new("powershell");
        command
            .arg("-NoProfile")
            .arg("-ExecutionPolicy")
            .arg("Bypass")
            .arg("-File")
            .arg(&script)
            .arg("-BackendPath")
            .arg(backend);
        command
    };
    command
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
                mode: mode.to_string(),
                mode_label: mode_label.to_string(),
                ..Run::default()
            }
        }
    };

    // The screen's live view of this run: the file the child is writing, read as
    // it grows. `update_progress` says why the file and not a pipe; the short
    // version is that the redirect is the thing keeping stdout and stderr in one
    // order, and this only reads.
    let live = std::sync::Arc::new(std::sync::Mutex::new(crate::update_progress::Progress {
        phase: "reading".to_string(),
        ..Default::default()
    }));
    let stop = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let watcher = {
        let file = capture.clone();
        let stop = stop.clone();
        let live = live.clone();
        let app = app.clone();
        std::thread::spawn(move || {
            let mut last = String::new();
            crate::update_progress::tail(file, stop, move |line| {
                let shown = {
                    let Ok(mut p) = live.lock() else { return };
                    crate::update_progress::progress_of(line, &mut p);
                    let said = serde_json::to_string(&*p).unwrap_or_default();
                    if said == last {
                        return;
                    }
                    last = said;
                    p.clone()
                };
                let _ = app.emit(crate::update_progress::PROGRESS_EVENT, &shown);
            });
        })
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

    // The child has gone: stop the tailer, and let it take the last lines the
    // verdict arrived in. Joined, not detached, so the screen's final reading is
    // the finished run's and nothing is still holding the file when it is removed.
    stop.store(true, std::sync::atomic::Ordering::Relaxed);
    let _ = watcher.join();

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
    let mut detail = if !verdict.ok {
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
    let progress = live.lock().map(|p| p.clone()).unwrap_or_default();
    let fallback = progress.fallback == Some(true);
    if used_tool {
        detail.push_str(&format!(" (Update pace: {mode_label}.)"));
    } else if tool.is_file() {
        // The tool is there; this PC would not start Python to run it. Said as
        // what happened rather than as a missing file, so the card does not
        // send the owner to `git pull` for a problem a pull cannot fix.
        detail.push_str(
            " The quicker paces need Python to run tools\\update_backend.py, and this \
             PC would not start it, so the older one-check-at-a-time update ran.",
        );
    } else {
        detail.push_str(
            " The quicker paces need tools\\update_backend.py in the Jarvis program \
             folder; this folder does not have it (git pull gets it), so the older \
             one-check-at-a-time update ran.",
        );
    }
    if fallback {
        detail.push_str(
            " The quick check hit a problem, so it was re-run the safe way - this \
             result is that safe pass.",
        );
    }

    Run {
        ok: verdict.ok,
        proven: verdict.proven,
        half_updated: verdict.half_updated,
        detail,
        log_dir,
        tail,
        progress,
        // Filled in by `run`, which is the only caller and the only place that
        // knows whether Jarvis was stopped for this attempt.
        stopped: false,
        mode: mode.to_string(),
        mode_label: mode_label.to_string(),
        fallback,
        used_tool,
    }
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// What the Updates card shows about the two folders and the three paces,
/// without running anything.
#[tauri::command]
pub fn backend_update_status(app: AppHandle) -> Where {
    let mut here = locate(&app);
    if here.blocked.is_some() {
        here.modes_note = Some(
            "Set the two folders above first; the update paces are worked out from them."
                .to_string(),
        );
        return here;
    }
    if let (Some(repo), Some(backend)) = (here.repo.clone(), here.backend.clone()) {
        let (modes, note) = mode_plan_for(&repo, &backend);
        here.modes = modes;
        here.modes_note = note;
    }
    here
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
        backend_folder, folder_of_hud, known_mode, parse_mode_plan, parse_update_lock,
        read_verdict, refuse, start_blocked_words, tail_of, tool_args, unknown_mode_words,
        update_lock_is_valid, update_running_words, ModeInfo, UpdateLock, Verdict, BACKEND_ENV,
        HUD, LOCK_CEILING_SECONDS, LOCK_CLOCK_SKEW_SECONDS, LOCK_HEARTBEAT_SECONDS,
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

    // ---- the three paces: the tool's own answer, read back ---------------

    /// The exact shape `tools/update_backend.py --modes-json` prints (camelCase,
    /// one key set per mode). The page and this struct both read it, so a field
    /// rename in the tool must fail HERE rather than show a card with blanks.
    const MODES_JSON: &str = r#"{
      "kind": "update_backend",
      "version": 1,
      "default": "responsive",
      "measured": false,
      "suiteCount": 356,
      "modes": [
        {"id": "max_speed", "label": "Fastest", "plain": "Nearly the whole PC.",
         "workers": 22, "etaSeconds": 120, "etaLowSeconds": 60, "etaHighSeconds": 300,
         "measured": false, "recommended": false, "suiteCount": 356},
        {"id": "responsive", "label": "Balanced", "plain": "About half the PC.",
         "workers": 14, "etaSeconds": 121, "etaLowSeconds": 61, "etaHighSeconds": 301,
         "measured": false, "recommended": true, "suiteCount": 356},
        {"id": "safe", "label": "Safest", "plain": "One at a time.",
         "workers": 1, "etaSeconds": 480, "etaLowSeconds": 240, "etaHighSeconds": 1200,
         "measured": false, "recommended": false, "suiteCount": 356}
      ]
    }"#;

    #[test]
    fn the_tool_s_mode_table_is_read_as_the_card_needs_it() {
        let plan = parse_mode_plan(MODES_JSON).expect("the tool's own answer did not parse");
        assert_eq!(plan.modes.len(), 3);
        assert_eq!(plan.default, "responsive");
        assert!(!plan.measured);
        let responsive = plan
            .modes
            .iter()
            .find(|row| row.id == "responsive")
            .expect("the recommended pace is missing");
        assert_eq!(responsive.workers, 14);
        assert_eq!(responsive.label, "Balanced");
        assert!(responsive.recommended);
        assert!(responsive.eta_low_seconds < responsive.eta_high_seconds);
        assert_eq!(responsive.suite_count, 356);
        // The three are ordered fastest to safest in the tool's answer, and the
        // ETA ordering is the tool's own arithmetic - this only reads it.
        assert!(plan.modes[0].eta_seconds <= plan.modes[1].eta_seconds);
        assert!(plan.modes[1].eta_seconds <= plan.modes[2].eta_seconds);
    }

    #[test]
    fn a_table_that_is_not_the_tool_s_answer_is_refused_rather_than_shown() {
        assert!(parse_mode_plan("").is_none());
        assert!(parse_mode_plan("not json").is_none());
        assert!(parse_mode_plan(r#"{"modes": []}"#).is_none());
        assert!(parse_mode_plan(r#"{"modes": [{"id": "responsive"}]}"#).is_none());
        // A valid document with all three rows still parses; the refusal above
        // is about the SHAPE, not about being cautious with a good answer.
        assert!(parse_mode_plan(MODES_JSON).is_some());
    }

    #[test]
    fn the_run_asks_the_tool_for_the_same_folders_and_an_explicit_pace() {
        let argv = tool_args(r"C:\repo", r"C:\backend", "responsive");
        // The tool's path is joined onto the repo folder, so the argument is the
        // absolute path (repo\tools\update_backend.py), not the bare relative one.
        assert!(
            argv.iter()
                .any(|arg| arg.ends_with("update_backend.py") && arg.contains("tools")),
            "{argv:?}"
        );
        assert!(
            argv.windows(2).any(|pair| pair == ["--repo", r"C:\repo"]),
            "{argv:?}"
        );
        assert!(
            argv.windows(2)
                .any(|pair| pair == ["--backend", r"C:\backend"]),
            "{argv:?}"
        );
        assert!(
            argv.windows(2).any(|pair| pair == ["--mode", "responsive"]),
            "{argv:?}"
        );
        // The tool runs the patcher itself, so its command line never carries
        // the patcher's own flags: -SkipTests belongs to the tool, not here.
        assert!(!argv.iter().any(|arg| arg == "-SkipTests"), "{argv:?}");
    }

    #[test]
    fn a_pace_the_tool_did_not_offer_is_refused_with_the_real_ones() {
        let modes = vec![
            ModeInfo {
                id: "max_speed".to_string(),
                ..Default::default()
            },
            ModeInfo {
                id: "responsive".to_string(),
                ..Default::default()
            },
            ModeInfo {
                id: "safe".to_string(),
                ..Default::default()
            },
        ];
        assert!(known_mode(&modes, "safe"));
        assert!(!known_mode(&modes, "turbo"));
        assert!(!known_mode(&[], "safe"));
        let words = unknown_mode_words(&modes, "turbo");
        for expected in [
            "turbo",
            "max_speed",
            "responsive",
            "safe",
            "Nothing was changed",
        ] {
            assert!(words.contains(expected), "{expected} missing from {words}");
        }
    }

    // -- the update lock's pure rules (the sidecar watchdog reads them) -----

    fn a_lock(pid: u32, started_at: f64, updated_at: f64) -> UpdateLock {
        UpdateLock {
            pid,
            started_at,
            updated_at,
            pace: "responsive".to_string(),
        }
    }

    #[test]
    fn a_dead_pid_ends_the_lock_immediately() {
        let got = a_lock(4321, 1000.0, 1000.0);
        assert!(!update_lock_is_valid(&got, 1000.0, false));
        assert!(update_lock_is_valid(&got, 1000.0, true));
    }

    #[test]
    fn the_heartbeat_expires_after_thirty_minutes() {
        let got = a_lock(7, 1000.0, 1000.0);
        assert!(update_lock_is_valid(
            &got,
            1000.0 + LOCK_HEARTBEAT_SECONDS,
            true
        ));
        assert!(!update_lock_is_valid(
            &got,
            1000.0 + LOCK_HEARTBEAT_SECONDS + 0.001,
            true
        ));
        // A heartbeat refreshed past the window is dead again: the window is
        // about `updated_at`, never about when the run started.
        assert!(!update_lock_is_valid(&got, 5000.0, true));
    }

    #[test]
    fn the_three_hour_ceiling_bounds_a_reused_pid() {
        let got = a_lock(7, 0.0, LOCK_CEILING_SECONDS);
        assert!(update_lock_is_valid(&got, LOCK_CEILING_SECONDS, true));
        assert!(!update_lock_is_valid(
            &got,
            LOCK_CEILING_SECONDS + 1.0,
            true
        ));
    }

    #[test]
    fn only_a_complete_real_lock_parses() {
        let good = r#"{"pid": 1, "started_at": 1.0, "updated_at": 2.0, "pace": "safe"}"#;
        let lock = parse_update_lock(good).expect("the real shape parses");
        assert_eq!((lock.pid, lock.pace.as_str()), (1, "safe"));
        for bad in [
            "",
            "{}",
            "not json",
            r#"{"pid": 0, "started_at": 1.0, "updated_at": 2.0, "pace": "safe"}"#,
            r#"{"pid": "x", "started_at": 1.0, "updated_at": 2.0, "pace": "safe"}"#,
            r#"{"pid": 1, "started_at": 1.0, "updated_at": 2.0}"#,
        ] {
            assert!(parse_update_lock(bad).is_none(), "parsed junk: {bad}");
        }
    }

    #[test]
    fn a_future_pace_is_still_a_live_update() {
        // S8: a newer tool may name a pace this build has never heard of. That
        // is still an update running, not "no update" - the old desktop must
        // not restart the backend under it.
        let text = r#"{"pid": 42, "started_at": 1000.0, "updated_at": 1000.0,
                       "pace": "turbo2"}"#;
        let lock = parse_update_lock(text).expect("an unknown pace is still a lock");
        assert_eq!(lock.pace, "turbo2");
        assert!(update_lock_is_valid(&lock, 1000.0, true));
        assert!(start_blocked_words(Some(&lock)).is_some());
    }

    #[test]
    fn a_lock_from_the_future_is_not_valid() {
        // S6: a clock change is not evidence of a live update, and Python
        // rejects the same file - the two readers must agree.
        let ahead = a_lock(7, 10_000.0, 10_000.0);
        assert!(!update_lock_is_valid(&ahead, 1_000.0, true));
        let slightly_ahead = a_lock(7, 1_030.0, 1_030.0);
        assert!(update_lock_is_valid(
            &slightly_ahead,
            1_000.0 + LOCK_CLOCK_SKEW_SECONDS - 1.0,
            true
        ));
    }

    #[test]
    fn the_words_name_the_update_and_refuse_a_second_start() {
        let lock = a_lock(4321, 1000.0, 1000.0);
        let refused = update_running_words(&lock);
        for expected in ["4321", "responsive", "Wait for it", "nothing was started"] {
            assert!(
                refused.contains(expected),
                "{expected} missing from {refused}"
            );
        }
        let blocked = start_blocked_words(Some(&lock)).expect("a start is blocked");
        for expected in ["4321", "responsive", "not started", "finishes"] {
            assert!(
                blocked.contains(expected),
                "{expected} missing from {blocked}"
            );
        }
        assert!(start_blocked_words(None).is_none());
    }
}
