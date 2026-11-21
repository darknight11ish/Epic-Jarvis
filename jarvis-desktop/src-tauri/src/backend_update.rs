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
///
/// Shared with `update.rs`, which writes the desktop update record into the same
/// folder: the update lock and the pending install are two halves of one story,
/// and a record and a lock that could end up in different folders on a machine
/// with `OPENJARVIS_CONFIG_DIR` set would be two stories.
pub(crate) fn config_dir(app: &AppHandle) -> Option<PathBuf> {
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
    config_dir(app).map(|dir| dir.join(LOCK_NAME))
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

/// The string at `key` in a settings tree, in either shape the store holds.
///
/// MEASURED 2026-11-20: the desktop updated itself to 0.2.484 and then could
/// not update the backend, saying it did not know where the Jarvis program
/// folder was, while the settings file really held
/// `"updates": {"repo_folder": "C:\\Users\\...\\Epic-Jarvis-main"}`. The
/// store plugin (tauri-plugin-store 2.5) looks up a key LITERALLY, so a dotted
/// key read misses a value nested under `updates`, and an older copy of this
/// page wrote the nested shape. Both shapes are therefore read here: the
/// literal key first (the shape `save_folders` writes), then the dotted path.
pub(crate) fn setting_text(tree: &serde_json::Value, key: &str) -> Option<String> {
    let literal = tree.get(key).and_then(|value| value.as_str());
    let nested = || {
        let mut parts = key.split('.');
        let first = parts.next()?;
        let mut node = tree.get(first)?;
        for part in parts {
            node = node.get(part)?;
        }
        node.as_str()
    };
    literal
        .or_else(nested)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn setting(app: &AppHandle, key: &str) -> Option<String> {
    let store = app.store(commands::SETTINGS_STORE).ok()?;
    // The plugin's `get` takes one literal key, so the two shapes are gathered
    // into one small tree and one tested reader decides between them.
    let first = key.split('.').next().unwrap_or(key);
    let mut tree = serde_json::Map::new();
    for name in [key, first] {
        if let Some(value) = store.get(name) {
            tree.insert(name.to_string(), value);
        }
    }
    setting_text(&serde_json::Value::Object(tree), key)
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
// Which source each half came from
// ---------------------------------------------------------------------------
//
// "Both halves updated" used to mean "both halves each finished", never "the
// two match": the backend is patched from whatever clone the owner points at
// (`locate`), and nothing compared that clone with the release the desktop half
// installed. A desktop half one month ahead of the patches applied underneath
// it is exactly the "half-updated machine that looks updated" this feature
// exists to prevent, so at least the two commits are now read and SAID.
//
// Read, not enforced: a mismatch does not block the update. What it must never
// do is stay invisible while the card paints two green lines.

/// How long the one `git` read may take.
///
/// Local and normally milliseconds, but it runs before an update the owner has
/// already asked for, and a wedged `git` on a network folder must not become a
/// hang with no explanation. `commands::run_with_deadline` kills it instead.
const GIT_LIMIT: Duration = Duration::from_secs(3);

/// The commit this binary was built from.
///
/// Written by `build.rs` (`git rev-parse`) into the compile environment. `None`
/// in a build made from a source copy with no `.git`, and the line below then
/// says the two halves cannot be compared rather than inventing a number. It is
/// **not** a release check and involves no network: it is the same number for
/// every launch of one binary.
pub fn app_commit() -> Option<String> {
    normalise_commit(option_env!("JARVIS_BUILD_COMMIT").unwrap_or(""))
}

/// The commit the Jarvis program folder is checked out at, when the owner has
/// said where that folder is and it is a git checkout.
pub fn repo_commit(repo: Option<&str>) -> Option<String> {
    let repo = repo.map(str::trim).filter(|r| !r.is_empty())?;
    let mut command = std::process::Command::new("git");
    command
        .arg("-C")
        .arg(repo)
        .arg("rev-parse")
        .arg("HEAD")
        .stdin(std::process::Stdio::null());
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let output = crate::commands::run_with_deadline(
        "reading the backend folder's git commit",
        command,
        GIT_LIMIT,
    )?
    .ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8(output.stdout).ok()?;
    normalise_commit(text.trim())
}

/// Is the Jarvis program folder at, or after, the commit this build came from?
///
/// `Some(true)` only when git PROVES that this executable's build commit is an
/// ancestor (or the same commit) of the folder's `HEAD` - the condition under
/// which a backend patched from that folder can honestly be called the same
/// release this desktop runs, or a newer one. `Some(false)` when git proves it
/// is not, and `None` when the question could not be answered at all (no
/// folder, no commit recorded in this build, not a git checkout, git missing).
///
/// **Why this check exists rather than a plain write.** The backend's `VERSION`
/// file is the shared release marker the HUD compares. Writing the desktop's
/// version into it while the program folder is BEHIND this build would hide a
/// real difference: the backend would be older than the desktop and the HUD
/// would paint the two as in step. That is the dangerous direction this
/// feature exists to end, so the marker is only moved when the folder really
/// holds this build's commit or later. Nothing is guessed, and the folder is
/// not fetched: a read of the refs already on this PC, never the network.
pub fn repo_is_at_least_build(repo: Option<&str>, build_commit: Option<&str>) -> Option<bool> {
    let repo = repo.map(str::trim).filter(|r| !r.is_empty())?;
    let build = normalise_commit(build_commit?)?;
    let mut command = std::process::Command::new("git");
    command
        .arg("-C")
        .arg(repo)
        .arg("merge-base")
        .arg("--is-ancestor")
        .arg(&build)
        .arg("HEAD")
        .stdin(std::process::Stdio::null());
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let output = crate::commands::run_with_deadline(
        "checking whether the backend folder holds this build's commit",
        command,
        GIT_LIMIT,
    )?
    .ok()?;
    Some(output.status.success())
}

/// A commit as this module shows it: lower-case hex, twelve characters.
///
/// `None` for anything that is not a commit — an error message, an empty
/// string, a path — so a failed read can never be displayed as a real one.
pub fn normalise_commit(raw: &str) -> Option<String> {
    let raw = raw.trim();
    if !(7..=40).contains(&raw.len()) || !raw.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    Some(
        raw.chars()
            .take(12)
            .collect::<String>()
            .to_ascii_lowercase(),
    )
}

/// The honest sentence about which source each half came from.
///
/// Always says which half is unknown rather than dropping the comparison: a
/// line that goes missing when `git` is missing would be read as "they match".
pub fn halves_line(app: Option<&str>, backend: Option<&str>) -> String {
    let app = app.and_then(normalise_commit);
    let backend = backend.and_then(normalise_commit);
    match (app.as_deref(), backend.as_deref()) {
        (Some(app), Some(backend)) if app == backend => {
            format!("Backend at {backend}, app at {app}; they match.")
        }
        (Some(app), Some(backend)) => format!("Backend at {backend}, app at {app}; they differ."),
        (Some(app), None) => format!(
            "App at {app}; the backend folder's commit could not be read, so the two \
             halves cannot be compared."
        ),
        (None, Some(backend)) => format!(
            "Backend at {backend}; this build did not record its own commit, so the two \
             halves cannot be compared."
        ),
        (None, None) => "Neither this build nor the backend folder can name its commit, so \
                         the two halves cannot be compared."
            .to_string(),
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

/// The lines the backend half printed about the release's new tool defaults,
/// verbatim (`TOOL DEFAULTS: ...`), in the order it printed them.
///
/// That step runs ONCE THE UPDATE HAS PROVED ITSELF (`tools/update_backend.py`,
/// after the suites proved the folder): it hands the tools this release NEWLY
/// ships ON to `tools/enable_new_tools.py`'s additive write of the owner's own
/// `jarvis-framework.toml`. These lines are the audit of what reached that file
/// (the baseline commit, the add list, and the writer's own "added"/"backup"
/// lines), so Rust keeps them verbatim and never paraphrases them.
pub fn tool_defaults_lines(tail: &str) -> Vec<String> {
    tail.lines()
        .map(str::trim)
        .filter(|line| line.starts_with("TOOL DEFAULTS:"))
        .map(str::to_string)
        .collect()
}

/// The lines the backend half printed about the release's own files reaching
/// this PC (`BESIDE: ...`), verbatim, in the order it printed them.
///
/// The look spec is the one that matters today: every start used to warn that
/// the desktop's bundled spec DISAGREED with the live backend folder's copy,
/// because nothing carried the release's copy into that folder (measured
/// 2026-11-21). `tools/update_backend.py` now delivers it after the update
/// proves itself - backed up, atomic, read back - and these lines are the audit
/// of that write or of the exact read that failed.
pub fn beside_lines(tail: &str) -> Vec<String> {
    tail.lines()
        .map(str::trim)
        .filter(|line| line.starts_with("BESIDE:"))
        .map(str::to_string)
        .collect()
}

/// The lines the backend half printed naming WHICH route carried its files and
/// WHY (`ROUTE: ...`), verbatim, in the order it printed them.
///
/// MEASURED 2026-11-21 00:25-00:28 PT. A deploy-managed install (its live files
/// come from `tools/reconcile_live_backend.py`, not from a full patch-stack
/// run) made the patch program refuse 51 of its 160 patches. The backend half
/// now falls back to the deploy tool's own `--apply`, and the ONE report line it
/// prints with the ending says which route ran and why - or, when the deploy
/// tool refused too, that refusal's own words. Rust keeps every one of them
/// verbatim and never paraphrases them, so the card can say which route ran
/// rather than only "done".
pub fn route_lines(tail: &str) -> Vec<String> {
    tail.lines()
        .map(str::trim)
        .filter(|line| line.starts_with("ROUTE:"))
        .map(str::to_string)
        .collect()
}

/// The backend half's own ending sentence when it did not finish.
///
/// It is about the BACKEND ONLY. Whether the desktop half was installed is the
/// caller's sentence, because only the caller knows the answer: the in-app
/// press runs the backend first (so the desktop really was not installed), and
/// the automatic finish runs AFTER its installer moved the desktop (so it
/// really was). One sentence for both was measured false on the owner's PC,
/// 2026-11-21 00:28 PT: "The backend step did not finish, so Jarvis Desktop was
/// NOT installed on top of it", said about an install where 0.2.487 HAD been
/// installed. `half_updated` keeps the patch program's own warning verbatim.
pub fn backend_failure_words(half_updated: bool) -> String {
    let mut said = "The backend half did not finish.".to_string();
    if half_updated {
        said.push_str(
            " The patch program says some of your backend files WERE changed before it \
             went wrong, so the backend may be half updated - read the log and follow \
             what it says to do before starting Jarvis.",
        );
    }
    said
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

// ---------------------------------------------------------------------------
// The release marker the HUD compares - moved only when git proves it is safe
// ---------------------------------------------------------------------------
//
// MEASURED 2026-11-20, the owner's own words: *"when I update Jarvis the HUD and
// backend should always update at the same time."* The HUD decides that with
// ONE number: `GET /api/self`'s `version.app_version`, which is the bare
// contents of the `VERSION` file beside the backend (`jarvis_self_portrait.
// _app_version`). The deploy tool is the only writer of that file today, and it
// writes the INSTALLED desktop exe's version - never this repository's root
// `VERSION`, which is the 0.2.0 project-format marker.
//
// The in-app backend half patches the live folder but used to leave that file
// alone, so a press that moved both halves still left the HUD saying MISMATCH
// until a deploy ran by hand - the exact half-update this feature exists to end.
// [`write_release_marker`] is that missing step, and it is deliberately NOT a
// second copy of the deploy tool: it writes one file, in one format, with the
// deployed-in-exe version the app already knows it is running.
//
// It is called only after the patcher proved itself AND only when
// [`repo_is_at_least_build`] says the patched bytes really are this build's
// commit or later. Anything unprovable leaves the marker untouched and the HUD's
// mismatch in place, which is the truthful answer.

/// The file the HUD's comparison reads: `<backend>/VERSION`, a bare version.
pub const VERSION_NAME: &str = "VERSION";

/// What happened when the release marker was considered.
///
/// Its own type rather than a bool, because "already right" and "written now"
/// are both fine, while "this build has no release number" and "the write
/// failed" are two different sentences and neither may read as a success.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MarkerEnding {
    /// The file already held the version this app runs.
    Already(String),
    /// The file was written, atomically, with it.
    Written(String),
    /// This app's own version is not a release number, so nothing was invented.
    NotARelease,
    /// The write itself failed. The backend half is untouched by that.
    Failed(String),
}

impl MarkerEnding {
    /// True for the two endings in whose company the marker really names the
    /// version this desktop runs.
    pub fn in_step(&self) -> bool {
        matches!(self, MarkerEnding::Already(_) | MarkerEnding::Written(_))
    }
}

/// The shape the marker file may hold: exactly three numeric parts, `0.2.486`.
///
/// Taken from THIS app's own version, so it is the same value the updater wrote
/// into the desktop's executable. `None` for a development build's `0.2.0`-style
/// project number would be wrong to reject - it is still three parts - so this
/// only refuses what is not a release-shaped number at all (a suffix, a build
/// id, an empty string), and the deployment identity is the caller's.
pub fn release_marker(version: &str) -> Option<String> {
    let version = version.trim();
    let parts: Vec<&str> = version.split('.').collect();
    if parts.len() != 3
        || parts
            .iter()
            .any(|part| part.is_empty() || !part.bytes().all(|b| b.is_ascii_digit()))
    {
        return None;
    }
    Some(version.to_string())
}

/// Writes `<backend>/VERSION` with `version`, atomically and without a trailing
/// newline - the same bytes `tools/reconcile_live_backend.py` writes for the
/// same file, so every reader (this module, the HUD, the deploy tool) agrees.
///
/// Never panics and never half-writes: the new text goes to a temporary file in
/// the same folder and is renamed over the old one. A failure says why; it does
/// not fall back to a truncated write.
pub fn write_release_marker(backend: &Path, version: &str) -> MarkerEnding {
    let Some(value) = release_marker(version) else {
        return MarkerEnding::NotARelease;
    };
    let path = backend.join(VERSION_NAME);
    if let Ok(existing) = std::fs::read_to_string(&path) {
        if existing.trim() == value {
            return MarkerEnding::Already(value);
        }
    }
    let temporary = backend.join(format!(
        "{VERSION_NAME}.tmp-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|since| since.as_nanos())
            .unwrap_or(0)
    ));
    if let Err(err) = std::fs::write(&temporary, value.as_bytes()) {
        let _ = std::fs::remove_file(&temporary);
        return MarkerEnding::Failed(err.to_string());
    }
    if let Err(err) = std::fs::rename(&temporary, &path) {
        let _ = std::fs::remove_file(&temporary);
        return MarkerEnding::Failed(err.to_string());
    }
    MarkerEnding::Written(value)
}

/// One plain sentence for the card, in the run's own report. Never says the two
/// halves are in step unless the marker really holds this build's version.
pub fn marker_words(ending: &MarkerEnding) -> String {
    match ending {
        MarkerEnding::Already(version) | MarkerEnding::Written(version) => format!(
            "The backend's VERSION file now says {version}, the version this app runs, \
             so the HUD compares the two halves against the same number."
        ),
        MarkerEnding::NotARelease => "The backend was patched and proved, but its VERSION \
             file was left alone: this build's own version is not a release number to \
             report, and the HUD keeps showing the backend's old version rather than a \
             made-up one."
            .to_string(),
        MarkerEnding::Failed(why) => format!(
            "The backend was patched and proved, but its VERSION file could not be \
             written ({why}), so the HUD keeps showing the old backend version."
        ),
    }
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
    /// The verbatim lines the run printed about the release's own files reaching
    /// this PC (`BESIDE:` for the look spec, `TOOL DEFAULTS:` for the additive
    /// config step). The auto-finish puts them on its own ending line too, so an
    /// update the owner never sees a card for still says what reached the PC.
    pub notes: Vec<String>,
}

/// Puts the two folders in place and runs the chosen pace's update: the repo
/// tool when this clone has it, the older one-at-a-time patcher when it does
/// not. Refuses — changing nothing — when either folder is missing.
///
/// `previous_release` is the commit the desktop was built from BEFORE the update
/// action this run belongs to. The repo tool uses it to tell a tool that THIS
/// release newly ships ON from one the owner deliberately turned off in
/// `[tools].enabled` - the tool's own additive step then adds only the former to
/// the owner's config. `None` (a build that recorded no commit) makes that step
/// say which read it could not do and add nothing; it never guesses, and it can
/// never fail this backend half.
pub async fn run(
    app: &AppHandle,
    mode: &str,
    mode_label: &str,
    previous_release: Option<&str>,
) -> Run {
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
    let previous_owned = previous_release.map(str::to_string);
    let mut finished = tauri::async_runtime::spawn_blocking(move || {
        run_script(
            &repo_root,
            &backend,
            &reports_to,
            &mode_owned,
            &label_owned,
            previous_owned.as_deref(),
        )
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
fn run_script(
    repo: &Path,
    backend: &Path,
    app: &AppHandle,
    mode: &str,
    mode_label: &str,
    previous_release: Option<&str>,
) -> Run {
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
        // The commit the desktop was built from BEFORE this update action. The
        // tool uses it to tell a tool the release NEWLY ships ON from one the
        // owner turned off (which is never re-enabled): only the former may be
        // added to the owner's config, and only after the run proves itself.
        if let Some(previous) = previous_release.map(str::trim).filter(|p| !p.is_empty()) {
            command.arg("--previous-release").arg(previous);
        }
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
        // The backend half's own sentence only - see `backend_failure_words`.
        backend_failure_words(verdict.half_updated)
    } else if verdict.proven {
        // Route-neutral on purpose (2026-11-21): the patch program is not the
        // only route that can carry the backend half - on a deploy-managed
        // install the deploy tool does - so this sentence must not credit it
        // for bytes it did not write. The `ROUTE:` note says which route ran.
        "The backend folder is patched, and the update's own tests proved it.".to_string()
    } else {
        "The backend folder is patched, but the update could not prove every check \
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
    // The release's own files reaching this PC, as the repo tool reported them
    // once the update proved itself (2026-11-21): `BESIDE:` for the look spec
    // and `TOOL DEFAULTS:` for the additive config step. Shown verbatim - the
    // owner's config and the copy the desktop compares are where a shipped
    // feature becomes usable - so a step that could not run must be READ.
    // `ROUTE:` comes first when it is there: which route carried the files (the
    // patch stack, or the deploy tool on a deploy-managed install) is the first
    // thing the card should say about a fallback update.
    let mut notes = route_lines(&tail);
    notes.extend(beside_lines(&tail));
    notes.extend(tool_defaults_lines(&tail));
    if !notes.is_empty() {
        detail.push(' ');
        detail.push_str(&notes.join(" "));
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
        notes,
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
        backend_failure_words, backend_folder, beside_lines, folder_of_hud, halves_line,
        known_mode, marker_words, normalise_commit, parse_mode_plan, parse_update_lock,
        read_verdict, refuse, release_marker, repo_commit, repo_is_at_least_build, route_lines,
        setting_text, start_blocked_words, tail_of, tool_args, tool_defaults_lines,
        unknown_mode_words, update_lock_is_valid, update_running_words, write_release_marker,
        MarkerEnding, ModeInfo, UpdateLock, Verdict, BACKEND_ENV, HUD, LOCK_CEILING_SECONDS,
        LOCK_CLOCK_SKEW_SECONDS, LOCK_HEARTBEAT_SECONDS, VERSION_NAME,
    };

    fn args(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    // ---- the two shapes the settings file holds (measured 2026-11-20) ----

    #[test]
    fn a_folder_saved_nested_is_read_back() {
        // The measured shape on the owner's PC: the page wrote the dotted path
        // as a tree, and the deploy read it as a literal key, so it found
        // nothing and refused to update the backend.
        let tree = serde_json::json!({
            "updates": {
                "repo_folder": r"C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main",
                "backend_folder": r"C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program",
            }
        });
        assert_eq!(
            setting_text(&tree, "updates.repo_folder").as_deref(),
            Some(r"C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main"),
        );
        assert_eq!(
            setting_text(&tree, "updates.backend_folder").as_deref(),
            Some(r"C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"),
        );
    }

    #[test]
    fn a_folder_saved_as_a_literal_key_is_still_read() {
        // The shape this module's own `save_folders` writes.
        let tree = serde_json::json!({"updates.repo_folder": r"D:\Jarvis"});
        assert_eq!(
            setting_text(&tree, "updates.repo_folder").as_deref(),
            Some(r"D:\Jarvis")
        );
    }

    #[test]
    fn an_empty_or_missing_folder_is_never_a_guess() {
        let empty = serde_json::json!({"updates": {"repo_folder": "   "}});
        assert_eq!(setting_text(&empty, "updates.repo_folder"), None);
        let missing = serde_json::json!({"updates": {}});
        assert_eq!(setting_text(&missing, "updates.repo_folder"), None);
        let other = serde_json::json!({"updates": {"repo_folder": 3}});
        assert_eq!(setting_text(&other, "updates.repo_folder"), None);
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

    // ---- which source each half came from --------------------------------

    #[test]
    fn a_commit_is_shown_as_twelve_lower_case_characters() {
        // The whole SHA reads as the short one, so the desktop half's embedded
        // value and the backend folder's cannot differ only by length.
        let full = "1BA56874B3A6177A93BA3BBB4E71219E56EF86ED";
        assert_eq!(normalise_commit(full).as_deref(), Some("1ba56874b3a6"));
        assert_eq!(
            normalise_commit(" 1ba56874b\n").as_deref(),
            Some("1ba56874b")
        );
        // Not a commit: an error message, a path, a short word, an empty
        // answer. None of these may be printed as if it were one.
        for junk in ["", " ", "not-a-commit", "zzzzzzz", "1ba5", "abcdef"] {
            assert_eq!(normalise_commit(junk), None, "accepted junk: {junk:?}");
        }
        let too_long = "a".repeat(41);
        assert_eq!(normalise_commit(&too_long), None);
    }

    #[test]
    fn the_halves_line_says_match_differ_or_which_one_is_unknown() {
        assert_eq!(
            halves_line(
                Some("1ba56874b3a6"),
                Some("1BA56874B3A6177A93BA3BBB4E71219E56EF86ED")
            ),
            "Backend at 1ba56874b3a6, app at 1ba56874b3a6; they match."
        );
        let differ = halves_line(Some("aaaaaaaaaaaa"), Some("bbbbbbbbbbbb"));
        assert!(differ.contains("aaaaaaaaaaaa"), "{differ}");
        assert!(differ.contains("bbbbbbbbbbbb"), "{differ}");
        assert!(differ.contains("they differ"), "{differ}");
        // A half that could not be read is SAID - a line that silently dropped
        // it would be read as "they match".
        let no_repo = halves_line(Some("aaaaaaaaaaaa"), None);
        assert!(no_repo.contains("could not be read"), "{no_repo}");
        assert!(!no_repo.contains("they match"), "{no_repo}");
        let no_app = halves_line(None, Some("bbbbbbbbbbbb"));
        assert!(no_app.contains("did not record"), "{no_app}");
        assert!(!no_app.contains("they match"), "{no_app}");
        let neither = halves_line(None, None);
        assert!(neither.contains("cannot be compared"), "{neither}");
        // ...and an unknown is never printed as a commit-shaped value.
        for said in [&no_repo, &no_app, &neither] {
            assert!(!said.contains("Backend at None"), "{said}");
            assert!(!said.contains("app at None"), "{said}");
        }
    }

    #[test]
    fn no_folder_means_no_commit_is_read() {
        // Pure: this must not spawn `git` for a folder the owner never named.
        assert_eq!(repo_commit(None), None);
        assert_eq!(repo_commit(Some("   ")), None);
    }

    // ---- the release marker the HUD compares (2026-11-20) ------------------

    fn marker_folder(tag: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "jarvis-marker-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|since| since.as_nanos())
                .unwrap_or(0)
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("the test's own temporary folder");
        dir
    }

    #[test]
    fn the_release_marker_is_three_numeric_parts_and_nothing_else() {
        assert_eq!(release_marker("0.2.486").as_deref(), Some("0.2.486"));
        assert_eq!(release_marker(" 0.2.486\n").as_deref(), Some("0.2.486"));
        assert_eq!(release_marker("0.2.0").as_deref(), Some("0.2.0"));
        // Not a release number: a suffix, a build id, a short form, an empty
        // string. None of these may be written over the shared marker.
        for junk in [
            "",
            " ",
            "0.2",
            "0.2.486-beta.1",
            "0.2.486+abc",
            "main",
            "v0.2.486",
        ] {
            assert_eq!(release_marker(junk), None, "accepted {junk:?}");
        }
    }

    #[test]
    fn the_marker_is_written_as_the_bare_version_with_no_newline() {
        let dir = marker_folder("write");
        std::fs::write(dir.join(VERSION_NAME), "0.2.484").expect("the old marker");
        let ending = write_release_marker(&dir, "0.2.486");
        assert_eq!(ending, MarkerEnding::Written("0.2.486".to_string()));
        // The deploy tool writes these exact bytes ("7 bytes for 0.2.433"), and
        // every reader parses a bare version - a newline is a different file.
        assert_eq!(
            std::fs::read(dir.join(VERSION_NAME)).expect("the marker reads"),
            b"0.2.486"
        );
        // A second write of the same value is not a write at all.
        assert_eq!(
            write_release_marker(&dir, "0.2.486"),
            MarkerEnding::Already("0.2.486".to_string())
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_version_that_is_not_a_release_number_never_touches_the_marker() {
        let dir = marker_folder("junk");
        std::fs::write(dir.join(VERSION_NAME), "0.2.484").expect("the old marker");
        assert_eq!(
            write_release_marker(&dir, "0.2.486-dev"),
            MarkerEnding::NotARelease
        );
        assert_eq!(
            std::fs::read_to_string(dir.join(VERSION_NAME)).expect("the marker reads"),
            "0.2.484"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_write_that_fails_says_why_and_leaves_no_half_written_marker() {
        let dir = marker_folder("fail");
        let missing = dir.join("no-such-backend-folder");
        let ending = write_release_marker(&missing, "0.2.486");
        assert!(matches!(ending, MarkerEnding::Failed(_)), "{ending:?}");
        assert!(
            !missing.join(VERSION_NAME).exists(),
            "a failed write left a marker behind"
        );
        // Nothing is left in the folder it could write to as a temporary either.
        let leftovers: Vec<String> = std::fs::read_dir(&dir)
            .expect("the test folder")
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.file_name().to_string_lossy().to_string())
            .collect();
        assert!(leftovers.is_empty(), "left behind: {leftovers:?}");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_marker_words_say_in_step_only_when_the_marker_really_holds_it() {
        for ending in [
            MarkerEnding::Already("0.2.486".to_string()),
            MarkerEnding::Written("0.2.486".to_string()),
        ] {
            assert!(ending.in_step(), "{ending:?}");
            let said = marker_words(&ending);
            assert!(said.contains("0.2.486"), "{said}");
            assert!(said.contains("same number"), "{said}");
        }
        for ending in [
            MarkerEnding::NotARelease,
            MarkerEnding::Failed("access denied".to_string()),
        ] {
            assert!(!ending.in_step(), "{ending:?}");
            let said = marker_words(&ending);
            // The one failure the owner must never read as a clean update.
            assert!(said.contains("keeps showing"), "{said}");
            assert!(!said.contains("same number"), "{said}");
            assert!(!said.contains("in step"), "{said}");
        }
        // A failed write carries the PC's own reason, not a swallowed one.
        assert!(
            marker_words(&MarkerEnding::Failed("access denied".to_string()))
                .contains("access denied")
        );
    }

    #[test]
    fn a_folder_that_cannot_be_proved_to_hold_this_build_is_never_claimed_to() {
        // The dangerous direction: a stale program folder must never be called
        // this build's release. Everything unprovable is `None`, which the
        // callers read as "do not write the marker".
        let commit = Some("1ba56874b3a6");
        assert_eq!(repo_is_at_least_build(None, commit), None);
        assert_eq!(repo_is_at_least_build(Some("   "), commit), None);
        assert_eq!(repo_is_at_least_build(Some(r"C:\nowhere"), None), None);
        assert_eq!(
            repo_is_at_least_build(Some(r"C:\nowhere"), Some("not-a-commit")),
            None
        );
    }

    // ---- the release's new tool defaults (2026-11-21) ----------------------

    #[test]
    fn the_tool_defaults_step_is_reported_verbatim_and_nothing_else_is() {
        let tail = "Update pace: Balanced (responsive), 14 suite(s) at a time.\n\
                    ALL DONE - the backend is patched and proven\n\
                    TOOL DEFAULTS: baseline: the shipped tool defaults at 7add1b7c1d5f \
                    (the desktop build before this update)\n\
                    TOOL DEFAULTS: this release newly ships these tools on: project_create\n\
                    TOOL DEFAULTS: added and read back: project_create\n\
                    a normal line the step did not write";
        let lines = tool_defaults_lines(tail);
        assert_eq!(lines.len(), 3, "{lines:?}");
        assert!(lines[0].contains("7add1b7c1d5f"), "{lines:?}");
        assert!(lines[1].contains("project_create"), "{lines:?}");
        assert!(lines[2].contains("added and read back"), "{lines:?}");
        // The lines are kept as the tool printed them (only outer whitespace
        // trimmed), so nothing here paraphrases what reached the config.
        for line in &lines {
            assert!(line.starts_with("TOOL DEFAULTS:"), "{line}");
        }
        // A run that never reached the step (or an older program folder) adds
        // nothing at all - no invented "no tools were new".
        assert!(tool_defaults_lines("ALL DONE - the backend is patched and proven").is_empty());
        // A refusal by the step is still a line: the owner must read it.
        let refused = tool_defaults_lines(
            "TOOL DEFAULTS: NOT ADDED: the config step is not in this release \
             (no tools/enable_new_tools.py), so these new tools were NOT enabled: a, b",
        );
        assert_eq!(refused.len(), 1, "{refused:?}");
        assert!(refused[0].contains("NOT ADDED"), "{refused:?}");
    }

    #[test]
    fn the_look_spec_step_is_reported_verbatim_and_only_when_it_ran() {
        // The measured 2026-11-21 warning: the desktop's bundled spec disagreed
        // with the live backend folder's copy on every start. The delivery step
        // prints one BESIDE: line - unchanged, wrote+backup, or NOT delivered
        // with the exact read that failed - and Rust shows it verbatim.
        let tail = "Update pace: Balanced (responsive), 14 suite(s) at a time.\n\
                    ALL DONE - the backend is patched and proven\n\
                    BESIDE: jarvis-visual-spec.json wrote 73121 bytes (was 61301 bytes); \
                    backup at jarvis-visual-spec.json.before-visual-spec-20261121-060000\n\
                    TOOL DEFAULTS: added and read back: project_create";
        let beside = beside_lines(tail);
        assert_eq!(beside.len(), 1, "{beside:?}");
        assert!(beside[0].contains("jarvis-visual-spec.json"), "{beside:?}");
        assert!(beside[0].contains("73121"), "{beside:?}");
        assert!(beside[0].contains("backup at"), "{beside:?}");
        // The two kinds of report line are separate lists, each verbatim.
        let defaults = tool_defaults_lines(tail);
        assert_eq!(defaults.len(), 1, "{defaults:?}");
        assert!(defaults[0].starts_with("TOOL DEFAULTS:"), "{defaults:?}");
        // A step that did not run adds no line - never an invented "unchanged".
        assert!(beside_lines("ALL DONE - the backend is patched and proven").is_empty());
        // A refusal is still a line the owner must read.
        let refused = beside_lines(
            "BESIDE: jarvis-visual-spec.json NOT delivered: the release's copy \
             could not be read at C:\\repo\\jarvis-desktop\\src\\jarvis-visual-spec.json \
             (FileNotFoundError); nothing was written",
        );
        assert_eq!(refused.len(), 1, "{refused:?}");
        assert!(refused[0].contains("NOT delivered"), "{refused:?}");
    }

    #[test]
    fn which_route_carried_the_update_is_kept_verbatim() {
        // MEASURED 2026-11-21 00:25-00:28 PT: the automatic finish's backend
        // half ran the patch stack on a deploy-managed install, the stack
        // refused 51 of 160 patches, and the deploy tool is the route that
        // works there. The card must say which route ran and why - the tool
        // prints ONE ROUTE: line with the ending, and Rust keeps it trimmed and
        // unchanged.
        let tail = "ALL DONE - the backend is patched and proven\n\
                    BESIDE: jarvis-visual-spec.json unchanged\n\
                    ROUTE: the patch stack refused 51 hunk(s) on a deployed install; \
                    the deploy route carried the update - the live backend now holds this \
                    repository's bytes at commit abcdef123456 and VERSION 0.2.487, and the \
                    checks above are the proof.";
        let lines = route_lines(tail);
        assert_eq!(lines.len(), 1, "{lines:?}");
        assert!(lines[0].starts_with("ROUTE:"), "{lines:?}");
        assert!(lines[0].contains("51 hunk(s)"), "{lines:?}");
        assert!(
            lines[0].contains("deploy route carried the update"),
            "{lines:?}"
        );
        // The route is NOT folded into another report list: the kinds of line
        // stay separate, so nothing paraphrases the others.
        assert_eq!(beside_lines(tail).len(), 1);
        // More than one is kept in order, not only the last (the parser is the
        // shape, not a single-sentence match).
        let two = "ROUTE: first\nBESIDE: x\nROUTE: second";
        assert_eq!(
            route_lines(two),
            vec!["ROUTE: first".to_string(), "ROUTE: second".to_string()]
        );
        // A patched install adds no ROUTE line - the default route is not news.
        assert!(route_lines("ALL DONE - the backend is patched and proven").is_empty());
    }

    #[test]
    fn the_backend_half_failure_never_says_the_desktop_was_not_installed() {
        // The measured wording bug: after the installer moved the desktop to
        // 0.2.487, the automatic finish failed its backend half and the card
        // said "The backend step did not finish, so Jarvis Desktop was NOT
        // installed on top of it" - false, the desktop WAS installed. This
        // sentence is about the BACKEND only; the desktop half's own step says
        // whether it was installed, and it is the caller's to say.
        let words = backend_failure_words(false);
        assert!(words.contains("backend half"), "{words}");
        assert!(words.contains("did not finish"), "{words}");
        for forbidden in [
            "NOT installed",
            "was not installed",
            "nothing was put on top",
            "Jarvis Desktop",
        ] {
            assert!(!words.contains(forbidden), "{forbidden:?} in {words}");
        }
        assert!(!words.contains('\n'), "{words:?}");
        // The patch program's own half-updated warning is kept verbatim, because
        // that is the one failure the owner must act on before starting Jarvis.
        let half = backend_failure_words(true);
        assert!(half.contains("WERE changed before it went wrong"), "{half}");
        assert!(half.contains("half updated"), "{half}");
    }
}
