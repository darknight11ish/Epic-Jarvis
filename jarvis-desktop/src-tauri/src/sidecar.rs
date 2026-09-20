//! Supervising the Python backend — build order step 4.
//!
//! DESKTOP-BUILD §5 sets five conditions, and this module is only worth having
//! if it meets all of them, because a half-supervised backend is worse than an
//! unsupervised one:
//!
//! 1. **Stop the child when the app exits.** Tauri does not; `run()` wires
//!    [`stop_owned`] into `RunEvent::ExitRequested` and `RunEvent::Exit`.
//! 2. **Kill the tree, not the process.** [`crate::proctree`] does that with a
//!    Job Object on Windows and a process group elsewhere. The Python backend
//!    starts children of its own, and a model pinned in VRAM by a grandchild
//!    nobody can see is the failure this exists to prevent.
//! 3. **Ask first.** `POST /api/shutdown` unloads the model from the GPU and
//!    then stops serving. Killing skips the handback, and on Windows there is
//!    no signal that would let the backend clean up on the way down — which is
//!    the whole reason that endpoint exists. So: ask, wait, then kill.
//! 4. **Attach, don't duplicate.** If something already answers on the port,
//!    connect to it and spawn nothing. "Two Jarvises sharing one SQLite
//!    approval queue is a bad afternoon."
//! 5. **A setting, default off.** "A user who starts Jarvis from a terminal
//!    must not have the GUI adopt and then kill their process." Nothing here
//!    runs unless it has been switched on.
//!
//! ## Why this is not a Tauri sidecar
//!
//! §5 describes `bundle.externalBin` and `app.shell().sidecar("jarvis")`. That
//! path needs a bundled `jarvis-<target-triple>.exe`, and this repository does
//! not have one — the backend is `jarvis_hud.py`, a script. Declaring
//! `externalBin` for a file that does not exist fails `tauri build` outright,
//! which would break packaging (step 7) to describe a binary nobody has built
//! yet. So supervision runs a configured program instead: `python` and the
//! script by default, or the frozen executable once one exists, by pointing
//! the same setting at it.
//!
//! It also avoids `tauri-plugin-shell` entirely, which matters beyond
//! convenience: adding it to reach `sidecar()` would put `shell:allow-execute`
//! and `shell:allow-open` within reach of a capability file, and the whole
//! point of `open_external_url` not using that plugin was to keep them out.
//! `std::process::Command` is `CreateProcess` with argument quoting `std`
//! already gets right, and no shell anywhere in the path.

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

use crate::commands;
use crate::logfile;
use crate::proctree::{self, ProcessTree};

/// Store key for the on/off switch. Absent means off.
const SUPERVISE_KEY: &str = "supervise";
/// Store key for what to run.
const BACKEND_KEY: &str = "backend";

/// How long the backend is given to stop after being asked politely.
///
/// §5 says "a few seconds". `_request_shutdown()` releases the GPU and then
/// shuts the HTTP server down on another thread, so the interesting part is
/// the GPU handback — an unload of a large model off a busy card, not an
/// instant operation.
///
/// This is also, unavoidably, how long quitting can take: the exit path blocks
/// the Win32 message pump, and Windows ghosts a window at five seconds. The
/// budget below is `ASK_TIMEOUT + SHUTDOWN_GRACE + REAP_TIMEOUT` ≈ 8 s worst
/// case, down from ~16 s. Shortening it further would mean quitting while a
/// model is still resident, which is the thing the graceful path exists to
/// prevent — a brief ghosted frame on the way out is the better trade.
const SHUTDOWN_GRACE: Duration = Duration::from_secs(4);
/// How long to wait for `/api/shutdown` itself to answer. It returns as soon as
/// the GPU is released, so it is not the slow part; the grace above is.
const ASK_TIMEOUT: Duration = Duration::from_secs(2);
/// How often the child is checked while it is stopping.
const REAP_POLL: Duration = Duration::from_millis(100);
/// How long to wait for a killed child to be reaped before giving up on it.
/// Bounded because this runs on the exit path, where blocking is visible.
const REAP_TIMEOUT: Duration = Duration::from_secs(2);
/// How long to wait for a freshly started backend to answer on its port before
/// saying so. Not a failure if it expires — Python plus a model registry is
/// slow to boot, and the event stream will connect whenever it is ready.
const STARTUP_WAIT: Duration = Duration::from_secs(25);
/// Timeout for the port probe and the shutdown request.
const PROBE_TIMEOUT: Duration = Duration::from_millis(1_500);

/// The origin the desktop's own webviews load from, which the backend has to
/// be told about or every request from the HUD page is refused as
/// cross-origin.
///
/// `jarvis_hud.py` builds its allowlist from its own configuration and merges
/// `JARVIS_HUD_ORIGINS`, comma-separated. A bundled Tauri page is served from
/// `http://tauri.localhost`, which is not a loopback URL the server could ever
/// have guessed.
const WEBVIEW_ORIGIN: &str = "http://tauri.localhost";

/// What to run, and where.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BackendConfig {
    /// The program. `python`, `pythonw.exe`, or a frozen backend executable.
    #[serde(default)]
    pub program: String,
    /// Its arguments — normally the path to `jarvis_hud.py`.
    #[serde(default)]
    pub args: Vec<String>,
    /// Working directory. Defaults to the folder holding the first argument
    /// that looks like a path, which is where the backend's siblings live.
    #[serde(default)]
    pub cwd: Option<String>,
}

impl BackendConfig {
    fn configured(&self) -> bool {
        !self.program.trim().is_empty()
    }

    /// The directory to run in: the configured one, else the folder of the
    /// script we were told to run, else wherever the app was started.
    fn working_dir(&self) -> Option<std::path::PathBuf> {
        if let Some(cwd) = self.cwd.as_ref().filter(|c| !c.trim().is_empty()) {
            return Some(std::path::PathBuf::from(cwd));
        }
        self.args
            .iter()
            .find(|arg| arg.ends_with(".py") || arg.ends_with(".exe"))
            .and_then(|arg| std::path::Path::new(arg).parent().map(|p| p.to_path_buf()))
            .filter(|dir| !dir.as_os_str().is_empty())
    }
}

/// The child this process owns, if it started one.
///
/// "Owns" is the load-bearing word: a backend that was already running when the
/// app launched is attached to, never adopted, and is not in here — so nothing
/// in this module can stop it.
#[derive(Default)]
pub struct SupervisorState {
    owned: Mutex<Option<Owned>>,
    /// Serialises start and stop against each other.
    ///
    /// Without it, `ensure_backend`'s liveness check and its port probe are
    /// separated by an `.await`, so the setup task and a tray click could both
    /// decide to start. The second `start()` overwrote the first's `Owned`, and
    /// dropping that closed a `KILL_ON_JOB_CLOSE` job — killing the backend
    /// that had just won the port, leaving the loser wedged. Two Jarvises, then
    /// none.
    gate: tokio::sync::Mutex<()>,
}

struct Owned {
    child: Child,
    tree: ProcessTree,
    started: Instant,
    /// The process we launched has exited. The *tree* may still be serving:
    /// `python.exe` on Windows is often an App Execution Alias or a launcher
    /// that re-execs, so the real server is frequently a grandchild.
    child_exited: bool,
}

impl SupervisorState {
    fn lock(&self) -> std::sync::MutexGuard<'_, Option<Owned>> {
        self.owned
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// Whether this process owns a backend tree at all.
    ///
    /// Ownership outlives the launched process. It ends when the tree is
    /// stopped, and at no other time.
    fn owns(&self) -> bool {
        self.lock().is_some()
    }

    /// The launched process's pid and whether it has exited.
    ///
    /// This used to be a `pid()` that *forgot* a child whose `try_wait` had
    /// reported an exit — and forgetting dropped `Owned`, which dropped
    /// `ProcessTree`, which closed a `KILL_ON_JOB_CLOSE` job and killed
    /// everything still inside it. It was called from `supervisor_status`, so
    /// the tray's backend row called it on every link change: with any launcher
    /// that hands off to a grandchild, the next `activity` frame killed a
    /// working backend mid-turn, and nothing logged it.
    ///
    /// It now reaps the zombie and records the fact. It never drops the tree.
    fn snapshot(&self) -> Option<(u32, bool)> {
        let mut slot = self.lock();
        let owned = slot.as_mut()?;
        if !owned.child_exited && matches!(owned.child.try_wait(), Ok(Some(_))) {
            owned.child_exited = true;
        }
        Some((owned.child.id(), owned.child_exited))
    }
}

/// What the settings screen and the tray need to know.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SupervisorStatus {
    /// Whether supervision is switched on at all.
    pub supervise: bool,
    /// Whether there is a program to run.
    pub configured: bool,
    /// Whether this process started the backend that is running.
    pub owned: bool,
    /// The launched process's pid, when this process started one.
    pub pid: Option<u32>,
    /// The launched process has exited but its tree is still ours to stop —
    /// normal for a Python launcher that re-execs.
    pub launcher_exited: bool,
    /// Seconds since this process started it.
    pub uptime_seconds: Option<u64>,
    /// What is configured, echoed back so a read-only screen can show it.
    pub backend: BackendConfig,
    /// The base the backend is expected on.
    pub base: String,
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

fn read_supervise(app: &AppHandle) -> bool {
    use tauri_plugin_store::StoreExt;
    app.store(commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(SUPERVISE_KEY))
        .and_then(|value| value.as_bool())
        // Default off. §5, and the reason is a person's terminal.
        .unwrap_or(false)
}

fn read_backend(app: &AppHandle) -> BackendConfig {
    use tauri_plugin_store::StoreExt;
    app.store(commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(BACKEND_KEY))
        .and_then(|value| serde_json::from_value(value).ok())
        .unwrap_or_default()
}

/// Current state of supervision.
#[tauri::command]
pub fn supervisor_status(app: AppHandle) -> SupervisorStatus {
    let state = app.state::<SupervisorState>();
    let snapshot = state.snapshot();
    let uptime = state
        .lock()
        .as_ref()
        .map(|owned| owned.started.elapsed().as_secs());
    let backend = read_backend(&app);
    SupervisorStatus {
        supervise: read_supervise(&app),
        configured: backend.configured(),
        owned: snapshot.is_some(),
        pid: snapshot.map(|(pid, _)| pid),
        launcher_exited: snapshot.map(|(_, exited)| exited).unwrap_or(false),
        uptime_seconds: uptime,
        backend,
        base: commands::jarvis_base(&app),
    }
}

/// Switches supervision on or off, and saves what to run.
///
/// Turning it *off* deliberately does not stop a running backend: the setting
/// says whether this app may start one, and killing something on a preference
/// change is not what a preference change should do. `stop_backend` is the
/// explicit way.
#[tauri::command]
pub fn set_supervision(
    app: AppHandle,
    supervise: Option<bool>,
    backend: Option<BackendConfig>,
) -> Result<SupervisorStatus, String> {
    use tauri_plugin_store::StoreExt;
    let store = app
        .store(commands::SETTINGS_STORE)
        .map_err(|e| format!("settings unavailable: {e}"))?;

    if let Some(supervise) = supervise {
        store.set(SUPERVISE_KEY, serde_json::json!(supervise));
    }
    if let Some(backend) = backend {
        if backend.program.contains('\0') || backend.args.iter().any(|a| a.contains('\0')) {
            // A NUL would be truncated by the OS rather than rejected, so what
            // finally runs would not be what was asked for.
            return Err("the program and its arguments cannot contain NUL".to_string());
        }
        store.set(
            BACKEND_KEY,
            serde_json::to_value(&backend).map_err(|e| format!("unusable backend config: {e}"))?,
        );
    }
    store
        .save()
        .map_err(|e| format!("unable to save settings: {e}"))?;

    Ok(supervisor_status(app))
}

// ---------------------------------------------------------------------------
// Probing
// ---------------------------------------------------------------------------

/// Is something already serving on the backend's base?
///
/// Any answer counts, including 401 and 403. The question is not "is this a
/// Jarvis I can talk to" — it is "would a second one fail to bind the port",
/// and for that, anything listening is a yes.
pub async fn backend_reachable(app: &AppHandle, base: &str) -> bool {
    let Ok(client) = reqwest::Client::builder()
        .connect_timeout(PROBE_TIMEOUT)
        .timeout(PROBE_TIMEOUT)
        .no_proxy()
        .build()
    else {
        return false;
    };
    let request = match commands::jarvis_headers(app) {
        Ok(headers) => client.get(format!("{base}/api/version")).headers(headers),
        Err(_) => client.get(format!("{base}/api/version")),
    };
    request.send().await.is_ok()
}

/// The port out of a base URL, for the child's `JARVIS_HUD_PORT`.
fn port_of(base: &str) -> Option<u16> {
    let authority = base
        .split_once("://")
        .map(|(_, rest)| rest)
        .unwrap_or(base)
        .split('/')
        .next()?;
    // Only the last colon-separated piece, and only if it is a number, so a
    // bare host or an IPv6 literal does not produce nonsense.
    authority.rsplit_once(':')?.1.parse::<u16>().ok()
}

// ---------------------------------------------------------------------------
// Starting
// ---------------------------------------------------------------------------

/// Starts the backend if supervision is on, nothing is already listening, and
/// this process is not already running one.
///
/// Returns a line describing what it decided, which is what the tray and the
/// settings screen show. Every outcome is a sentence rather than a silence:
/// "did nothing" is a legitimate result here and the user should be able to
/// find out why.
pub async fn ensure_backend(app: &AppHandle) -> Result<String, String> {
    if !read_supervise(app) {
        return Ok("Supervision is off; Jarvis Desktop will not start a backend.".to_string());
    }

    // One start or stop at a time. Held across every await below, so the
    // liveness check and the port probe cannot be overtaken between them.
    let state = app.state::<SupervisorState>();
    let _gate = state.gate.lock().await;

    let snapshot = state.snapshot();

    // A process we launched that is still running settles it on its own: there
    // is nothing to decide and no reason to pay for a port probe.
    if let Some((pid, false)) = snapshot {
        return Ok(format!("Already supervising the backend (pid {pid})."));
    }

    let base = commands::jarvis_base(app);
    let reachable = backend_reachable(app, &base).await;

    if let Some((pid, true)) = snapshot {
        // The process we launched is gone. That ALONE does not mean the backend
        // is: a launcher that re-execs leaves the real server as a grandchild
        // inside our tree, which is why `snapshot` reaps the zombie and refuses
        // to drop the tree — see its own comment for the backend this killed
        // mid-turn when an earlier version forgot an exited child.
        //
        // So ask the only question that actually settles it, rather than
        // inferring death from the exit: is anything serving?
        if reachable {
            return Ok(format!(
                "Already supervising the backend. The process we launched (pid {pid}) has \
                 exited — normal for a launcher that re-execs — and its tree is still ours \
                 to stop."
            ));
        }

        // Nothing is serving and the process we launched is gone, so this tree
        // is spent. Release it and fall through to a fresh start.
        //
        // Dropping `Owned` closes the KILL_ON_JOB_CLOSE job, which takes any
        // stuck grandchild with it — the cleanup we want here precisely
        // BECAUSE the probe above just established that nothing is serving.
        // Taken out from under the lock before the drop, for the reason
        // `stop_owned` gives: `supervisor_status` takes this same lock from
        // the tray on the main thread.
        //
        // Without this the slot stayed `Some` for the life of the app: a
        // backend that died on its own could never be restarted from the app
        // again, the tray kept offering to stop a dead pid, and the only way
        // out was Stop-then-Start, which reads to the user as a no-op.
        let spent = {
            let mut slot = state.lock();
            slot.take()
        };
        drop(spent);
    } else if reachable {
        // §5: attach, don't duplicate.
        return Ok(format!(
            "A backend is already listening on {base}; attached to it rather than starting a second."
        ));
    }

    let config = read_backend(app);
    if !config.configured() {
        return Err(
            "Supervision is on but no backend command is configured. Set the program \
             (for example `python`) and its arguments (the path to jarvis_hud.py)."
                .to_string(),
        );
    }

    start(app, &config, &base).map(|pid| format!("Started the backend (pid {pid})."))
}

/// Spawns the child, inside a process tree that can be killed whole.
fn start(app: &AppHandle, config: &BackendConfig, base: &str) -> Result<u32, String> {
    let mut command = Command::new(config.program.trim());
    command.args(&config.args);
    if let Some(dir) = config.working_dir() {
        command.current_dir(dir);
    }

    // The port we are going to look for it on, so the two cannot disagree.
    if let Some(port) = port_of(base) {
        command.env("JARVIS_HUD_PORT", port.to_string());
    }

    // Without this every request from the bundled HUD page is refused as
    // cross-origin: the page's origin is http://tauri.localhost, and the
    // server's allowlist is built from its own bind address. Appended rather
    // than assigned, so a value the user already set is not silently dropped.
    let origins = match std::env::var("JARVIS_HUD_ORIGINS") {
        Ok(existing) if !existing.trim().is_empty() => {
            if existing.split(',').any(|o| o.trim() == WEBVIEW_ORIGIN) {
                existing
            } else {
                format!("{existing},{WEBVIEW_ORIGIN}")
            }
        }
        _ => WEBVIEW_ORIGIN.to_string(),
    };
    command.env("JARVIS_HUD_ORIGINS", origins);

    // Only when we have one. Passing an empty HUD_TOKEN would *clear* a token
    // the user had set in the environment, quietly turning a token-gated
    // backend into an open one.
    if let Some(token) = commands::jarvis_token_for(app) {
        command.env("HUD_TOKEN", token);
    }

    // Off by default: with no bind address configured, the backend binds
    // its own default, which is loopback-only. Set only when the owner has
    // deliberately typed their machine's own Tailscale address into
    // Settings — see commands::validate_bind_address for why this can never
    // be "every interface". Before this, "the desktop app never tells the
    // backend to listen anywhere but loopback" (docs/INSTALL.md §3.2) meant
    // a backend this app started was unreachable from the phone no matter
    // what was set on the phone's side.
    if let Some(bind) = commands::supervised_bind_address(app) {
        command.env("JARVIS_HUD_BIND", bind);
    }

    // The whole reason the backend's failures were invisible. A release build
    // is `windows_subsystem = "windows"`, so this process has no console and
    // its standard handles are dead; inheriting them - which is what Command
    // does when no Stdio is set - handed the Python child the same dead
    // handles. Its startup banner, its bind refusal and its tracebacks all
    // went nowhere, and INSTALL.md had to tell people to run it in a terminal
    // instead. Now it goes to backend.log, which is the file the owner can
    // actually send us.
    //
    // Falls back to inheriting when the log file cannot be opened: the old
    // behaviour, which is bad, beats refusing to start the backend at all.
    match logfile::backend_sinks() {
        Some((out, err)) => {
            logfile::mark_backend(&format!(
                "\n===== starting `{}` =====",
                config.program.trim()
            ));
            command.stdout(Stdio::from(out)).stderr(Stdio::from(err));
        }
        None => logfile::log("[jarvis] no log directory; the backend's output will be lost"),
    }

    let (child, tree) = proctree::spawn(&mut command).map_err(|e| {
        format!(
            "could not start `{}`: {e}. Check that the program exists and the path to \
             jarvis_hud.py is right.",
            config.program.trim()
        )
    })?;
    let pid = child.id();

    let state = app.state::<SupervisorState>();
    *state.lock() = Some(Owned {
        child,
        tree,
        started: Instant::now(),
        child_exited: false,
    });
    logfile::log(&format!("[jarvis] backend started (pid {pid})"));
    Ok(pid)
}

/// Starts the backend on demand, from the tray or a settings screen.
#[tauri::command]
pub async fn start_backend(app: AppHandle) -> Result<String, String> {
    let outcome = ensure_backend(&app).await?;
    // Whatever just happened, the stream should look again rather than sit out
    // the rest of its backoff.
    crate::stream::kick(&app);
    Ok(outcome)
}

// ---------------------------------------------------------------------------
// Stopping
// ---------------------------------------------------------------------------

/// Asks the backend to stop, waits, then kills the tree if it is still there.
///
/// Safe to call when nothing is owned — that is the common case, because a
/// backend the user started themselves is attached to, not adopted.
pub async fn stop_owned(app: &AppHandle, reason: &str) -> String {
    let state = app.state::<SupervisorState>();
    let _gate = state.gate.lock().await;

    let Some((pid, _)) = state.snapshot() else {
        return "Nothing to stop: this app did not start the backend.".to_string();
    };
    println!("[jarvis] stopping the backend (pid {pid}): {reason}");

    // 1. Ask. This is what unloads the model from the GPU; killing skips it,
    //    and on Windows there is no signal that would let the backend do it on
    //    the way down.
    let asked = request_shutdown(app).await;

    // 2. Wait for the process itself to go. `/api/shutdown` stops the HTTP
    //    server; the process exits after that, and its children after it.
    let deadline = Instant::now() + SHUTDOWN_GRACE;
    let mut exited = false;
    while Instant::now() < deadline {
        let done = {
            let state = app.state::<SupervisorState>();
            let mut slot = state.lock();
            match slot.as_mut() {
                Some(owned) => matches!(owned.child.try_wait(), Ok(Some(_))),
                None => true,
            }
        };
        if done {
            exited = true;
            break;
        }
        tokio::time::sleep(REAP_POLL).await;
    }

    // 3. Kill the tree if asking did not work. Also on the clean path: the
    //    handle is dropped, and on Windows closing the last handle to a
    //    KILL_ON_JOB_CLOSE job takes anything still inside it with it.
    //
    //    The `Owned` is taken out from under the lock and the guard released
    //    BEFORE anything blocking happens. `Child::wait()` has no timeout, and
    //    `supervisor_status` — a synchronous command the tray calls on the main
    //    thread — takes this same lock: a kill that did not take would
    //    otherwise park a tokio worker inside `wait()` holding it, and hard-lock
    //    the UI with no window left to say why.
    let taken = {
        let mut slot = state.lock();
        slot.take()
    };
    let Some(mut owned) = taken else {
        return summarise(asked, exited, false);
    };
    let killed = if exited {
        false
    } else {
        owned.tree.kill();
        // Reap, so the child does not linger as a zombie on Unix. Bounded:
        // `TerminateJobObject` is not guaranteed to land instantly, and this
        // runs on the exit path.
        let deadline = Instant::now() + REAP_TIMEOUT;
        while Instant::now() < deadline {
            match owned.child.try_wait() {
                Ok(Some(_)) | Err(_) => break,
                Ok(None) => tokio::time::sleep(REAP_POLL).await,
            }
        }
        true
    };
    drop(owned);
    summarise(asked, exited, killed)
}

fn summarise(asked: Result<(), String>, exited: bool, killed: bool) -> String {
    let ask = match &asked {
        Ok(()) => "asked it to stop",
        Err(_) => "could not ask it to stop",
    };
    if killed {
        format!("{ask}; it was still running after the grace period, so the process tree was terminated.")
    } else if exited {
        format!("{ask}; it stopped.")
    } else {
        format!("{ask}; it had already gone.")
    }
}

/// `POST /api/shutdown`.
///
/// Loopback only on the server's side whatever the bind is, which this always
/// is. Failures are not fatal — the whole point of the grace period is that
/// this may not work.
async fn request_shutdown(app: &AppHandle) -> Result<(), String> {
    let base = commands::jarvis_base(app);
    let client = reqwest::Client::builder()
        .connect_timeout(PROBE_TIMEOUT)
        .timeout(ASK_TIMEOUT)
        .no_proxy()
        .build()
        .map_err(|e| e.to_string())?;
    let headers = commands::jarvis_headers(app)?;

    let response = client
        .post(format!("{base}/api/shutdown"))
        .headers(headers)
        .json(&serde_json::json!({}))
        .send()
        .await
        .map_err(|e| format!("{e}"))?;

    let status = response.status();
    if status.is_success() {
        Ok(())
    } else {
        Err(format!("the server answered HTTP {}", status.as_u16()))
    }
}

/// Stops the backend on demand, from the tray or a settings screen.
#[tauri::command]
pub async fn stop_backend(app: AppHandle) -> Result<String, String> {
    Ok(stop_owned(&app, "asked from the desktop").await)
}

/// The exit path. Called from `RunEvent::ExitRequested`, off the async runtime,
/// so the backend is asked and reaped before the process goes.
///
/// Blocking the main thread here is deliberate: this is the last thing that
/// happens, and the alternative is exiting while the model is still on the GPU.
pub fn stop_on_exit(app: &AppHandle) {
    if !app.state::<SupervisorState>().owns() {
        return;
    }
    let handle = app.clone();
    let outcome =
        tauri::async_runtime::block_on(
            async move { stop_owned(&handle, "the app is exiting").await },
        );
    println!("[jarvis] {outcome}");
}

/// Waits — in the background — for a freshly started backend to answer, then
/// tells the stream to try again.
pub fn watch_startup(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let base = commands::jarvis_base(&app);
        let deadline = Instant::now() + STARTUP_WAIT;
        while Instant::now() < deadline {
            if backend_reachable(&app, &base).await {
                println!("[jarvis] backend answering on {base}");
                crate::stream::kick(&app);
                return;
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
        eprintln!(
            "[jarvis] the backend did not answer on {base} within {}s; the event stream will \
             keep retrying",
            STARTUP_WAIT.as_secs()
        );
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_the_port_out_of_a_base() {
        assert_eq!(port_of("http://127.0.0.1:4719"), Some(4719));
        assert_eq!(port_of("http://localhost:4719/"), Some(4719));
        assert_eq!(port_of("https://box.tail1234.ts.net:4719/api"), Some(4719));
        // No port, so nothing to pass on — the backend keeps its own default.
        assert_eq!(port_of("http://127.0.0.1"), None);
        assert_eq!(port_of("http://localhost"), None);
        // Not a number after the colon.
        assert_eq!(port_of("http://127.0.0.1:port"), None);
    }

    /// The working directory has to land on the backend's own folder, because
    /// that is where its sibling modules and `jarvis_hud.html` live.
    #[test]
    fn working_dir_follows_the_script() {
        let config = BackendConfig {
            program: "python".into(),
            args: vec!["C:/jarvis/jarvis_hud.py".into()],
            cwd: None,
        };
        assert_eq!(
            config.working_dir(),
            Some(std::path::PathBuf::from("C:/jarvis"))
        );

        let explicit = BackendConfig {
            cwd: Some("D:/elsewhere".into()),
            ..config.clone()
        };
        assert_eq!(
            explicit.working_dir(),
            Some(std::path::PathBuf::from("D:/elsewhere"))
        );

        // A bare script name has no parent worth using; inheriting the app's
        // own directory is better than trying to run in "".
        let bare = BackendConfig {
            program: "python".into(),
            args: vec!["jarvis_hud.py".into()],
            cwd: None,
        };
        assert_eq!(bare.working_dir(), None);
    }

    #[test]
    fn unconfigured_until_a_program_is_set() {
        assert!(!BackendConfig::default().configured());
        assert!(!BackendConfig {
            program: "   ".into(),
            ..Default::default()
        }
        .configured());
        assert!(BackendConfig {
            program: "python".into(),
            ..Default::default()
        }
        .configured());
    }
}
