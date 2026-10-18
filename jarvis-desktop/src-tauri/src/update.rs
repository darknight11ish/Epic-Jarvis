//! Checking GitHub for a newer Jarvis Desktop, and never installing one on its
//! own.
//!
//! ## What this does and does not do
//!
//! It **checks**. It reports. It installs only when a person presses the
//! button. There is no setting here that turns that into an automatic install,
//! and that is deliberate rather than unfinished: an update is the single
//! largest change anything can make to this machine — it replaces the
//! executable — and "no auto-approve anywhere in Jarvis" is a rule the app
//! applies to sending one email. It would be strange to apply it there and not
//! here.
//!
//! ## What leaves the machine
//!
//! One outbound HTTPS GET to the release endpoint, carrying nothing but the
//! request: no identifier, no telemetry, no account, no crash data. The reply
//! is a small JSON manifest. That request is the entire network surface of this
//! module, and `check_on_start` in the settings store turns even that off.
//!
//! ## Why a tampered download cannot run
//!
//! Every artifact is signed with a private key that is not in this repository
//! and never will be, and `tauri.conf.json` is where the matching public key
//! goes. **That key is there now** — `plugins.updater.pubkey` in
//! `tauri.conf.json` carries a real minisign public key (checked 2026-10-13) —
//! so `configured()` below reads it, returns true, and Settings offers the
//! update instead of saying "Not set up yet". This paragraph used to say the
//! opposite — that the key was empty and this build could not update itself —
//! which stopped being true when the key landed. A comment that sends the next
//! reader looking for a bug that is not there is a defect in this project, not
//! a harmless leftover.
//!
//! `bundle.createUpdaterArtifacts` is still `false` in the committed config,
//! and that one is deliberate rather than more staleness: the private key is
//! not in the repository, so the committed file has to stay buildable without
//! it, and `.github/workflows/desktop-release.yml` turns artifact creation on
//! for the release build only.
//!
//! With the key configured: the updater verifies the signature before it hands
//! the bytes to the installer, so a release replaced at the CDN, a hijacked DNS
//! answer or a proxy rewriting the response all fail closed — and a build with
//! no public key configured cannot update at all, which is the correct
//! behaviour rather than a degraded one (see `configured()`).
//!
//! ## Both halves, in one button
//!
//! Since 2026-10-13 the same card also updates the **Python backend**, which had
//! never been driven by anything but the owner's own hands. [`update_both`] runs
//! the two halves in one deliberate order and is reachable only from the one
//! button; [`crate::backend_update`] owns the backend half and its own refusals.
//! The order, and why it is that order, is written out on [`update_both`]
//! itself.

use std::sync::atomic::{AtomicBool, Ordering};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_store::StoreExt;
use tauri_plugin_updater::UpdaterExt;

use crate::commands;

/// Store key for the one preference here.
const CHECK_ON_START: &str = "updates.check_on_start";

/// How long a check may take before it is treated as "not now".
///
/// Short on purpose: this runs at startup and nothing downstream of it matters
/// enough to hold anything up. A missed check costs a day.
const CHECK_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(12);

/// What a check found. Serialised straight into the Settings window.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Status {
    /// The version running now.
    pub current: String,
    /// The version on the other end, when it is newer than `current`.
    pub available: Option<String>,
    /// The release notes, as published.
    pub notes: Option<String>,
    /// When it was published, as published.
    pub date: Option<String>,
    /// Why the last check did not produce an answer.
    pub error: Option<String>,
    /// False when this build has no updater configured at all.
    pub supported: bool,
    /// Whether the app looks on its own at startup.
    pub check_on_start: bool,
}

/// How far a download has gotten. Sent while `install_update` is in flight —
/// informational only, the same as [`Status`]: nothing here starts, resumes
/// or retries anything on its own.
#[derive(Debug, Clone, Serialize)]
pub struct DownloadProgress {
    /// Bytes received so far, this download.
    pub downloaded: u64,
    /// Total size, when the server reported one. A release behind a proxy
    /// that strips `Content-Length` leaves this `None` rather than a fake
    /// number — better an unknown total than a progress bar that lies about
    /// how far along a hundred-plus-megabyte download actually is.
    pub total: Option<u64>,
}

/// The last answer a check produced.
///
/// Without this, `update_status` rebuilt a blank `Status` every time — so the
/// startup check could find 0.2.0, tell the tray and raise a notification, and
/// then the Settings window opened five minutes later would say "the newest
/// published". Two surfaces disagreeing about the same fact, with the quieter
/// one wrong.
#[derive(Default)]
pub struct UpdateState(std::sync::Mutex<Option<Status>>);

impl UpdateState {
    fn get(&self) -> Option<Status> {
        self.0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    fn put(&self, status: Status) {
        *self
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(status);
    }
}

/// Whether this build can update itself.
///
/// A build with no public key cannot verify a download, so it must not pretend
/// to offer updates: a Check button that always fails is worse than an honest
/// "this build cannot update itself", because the first invites someone to keep
/// pressing it.
fn configured(app: &AppHandle) -> bool {
    app.config()
        .plugins
        .0
        .get("updater")
        .and_then(|v| v.get("pubkey"))
        .and_then(|v| v.as_str())
        .is_some_and(|key| !key.trim().is_empty())
}

pub fn check_on_start(app: &AppHandle) -> bool {
    app.store(commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(CHECK_ON_START))
        .and_then(|v| v.as_bool())
        // On by default: the point of the feature is to be told. Being told is
        // not the same as being acted upon, which is the line this module draws.
        .unwrap_or(true)
}

fn version(app: &AppHandle) -> String {
    app.package_info().version.to_string()
}

fn base(app: &AppHandle) -> Status {
    Status {
        current: version(app),
        supported: configured(app),
        check_on_start: check_on_start(app),
        ..Status::default()
    }
}

/// Asks the endpoint whether there is anything newer. Downloads nothing.
pub async fn look(app: &AppHandle) -> Status {
    let mut status = base(app);
    if !status.supported {
        status.error = Some(
            "This build has no update key, so it cannot verify a download and will \
             not try. Install a signed release to enable updates."
                .to_string(),
        );
        return status;
    }

    let updater = match app.updater_builder().timeout(CHECK_TIMEOUT).build() {
        Ok(updater) => updater,
        Err(err) => {
            status.error = Some(format!("the updater could not start: {err}"));
            return status;
        }
    };

    match updater.check().await {
        // `check()` resolves to the update itself, which holds the download —
        // and is dropped here without being used. That is the whole design:
        // nothing is fetched until someone asks for it.
        Ok(Some(update)) => {
            status.available = Some(update.version.clone());
            status.notes = update.body.clone();
            status.date = update.date.map(|d| d.to_string());
        }
        Ok(None) => {}
        Err(err) => {
            status.error = Some(friendly(&err.to_string()));
        }
    }
    status
}

/// Turns the transport's wording into something worth reading.
///
/// The common failure on a repository with no releases yet is a bare 404, and
/// "404" tells the owner nothing about what to do.
fn friendly(raw: &str) -> String {
    let lower = raw.to_lowercase();
    if lower.contains("404") || lower.contains("not found") {
        return "No releases published yet, so there is nothing to compare against.".to_string();
    }
    if lower.contains("dns") || lower.contains("connect") || lower.contains("timed out") {
        return format!("Could not reach the release endpoint: {raw}");
    }
    if lower.contains("signature") {
        return format!(
            "A release was found but its signature did not verify, so it was refused: {raw}"
        );
    }
    raw.to_string()
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// The last known state without going near the network.
#[tauri::command]
pub fn update_status(app: AppHandle) -> Status {
    match app.state::<UpdateState>().get() {
        // `check_on_start` is re-read rather than served from the cache: the
        // checkbox can have been changed since, and it is the one field here
        // that a person edits.
        Some(cached) => Status {
            check_on_start: check_on_start(&app),
            ..cached
        },
        None => base(&app),
    }
}

/// Checks now, because someone pressed Check.
#[tauri::command]
pub async fn check_for_update(app: AppHandle) -> Status {
    let status = look(&app).await;
    app.state::<UpdateState>().put(status.clone());
    crate::tray::on_update_status(&app, status.available.as_deref());
    let _ = app.emit(crate::events::UPDATE_STATUS, status.clone());
    status
}

/// Turns the startup check on or off.
#[tauri::command]
pub fn set_update_check_on_start(app: AppHandle, enabled: bool) -> Result<bool, String> {
    let store = app
        .store(commands::SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    store.set(CHECK_ON_START, serde_json::Value::Bool(enabled));
    store
        .save()
        .map_err(|e| format!("could not write the settings store: {e}"))?;
    Ok(enabled)
}

/// Downloads, verifies and installs — and is reachable only from the button.
///
/// This is the only function in the module that writes anything to disk. It is
/// separate from `check_for_update` rather than a flag on it, so that no future
/// edit can make checking install something by passing `true`.
#[tauri::command]
pub async fn install_update(app: AppHandle) -> Result<String, String> {
    install_now(&app).await
}

/// The install, with no command wrapper on it — so the one button that updates
/// **both** halves can use the same code rather than a second copy of it.
///
/// Nothing else in this module may call this: it is the half of an update that
/// replaces the executable, and the only two doors into it are the Install
/// button and [`update_both`]'s second step.
async fn install_now(app: &AppHandle) -> Result<String, String> {
    if !configured(app) {
        return Err("this build has no update key, so it cannot verify a download".to_string());
    }
    let updater = app
        .updater()
        .map_err(|e| format!("the updater could not start: {e}"))?;
    let update = updater
        .check()
        .await
        .map_err(|e| friendly(&e.to_string()))?
        .ok_or_else(|| "there is no newer version to install".to_string())?;

    let version = update.version.clone();
    // `on_chunk` reports the size of the piece JUST received, not a running
    // total — the settings window showed no percentage at all before this,
    // for exactly that reason: nothing here was turning "another chunk
    // arrived" into "how far along am I" or telling anyone either number.
    let downloaded = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(0));
    let progress_app = app.clone();
    let progress_downloaded = downloaded.clone();
    // The signature is checked inside this call, before anything is executed.
    update
        .download_and_install(
            move |chunk_len, total| {
                let so_far = progress_downloaded
                    .fetch_add(chunk_len as u64, std::sync::atomic::Ordering::Relaxed)
                    + chunk_len as u64;
                let _ = progress_app.emit(
                    crate::events::UPDATE_PROGRESS,
                    DownloadProgress {
                        downloaded: so_far,
                        total,
                    },
                );
            },
            || {},
        )
        .await
        .map_err(|e| format!("the update failed to install: {e}"))?;
    Ok(version)
}

// ---------------------------------------------------------------------------
// Both halves, in one button
// ---------------------------------------------------------------------------

/// The id of the backend half in a [`Step`]. The words the card shows come from
/// `crate::backend_update`, not from here.
pub const STEP_BACKEND: &str = "backend";
/// The id of the desktop half in a [`Step`].
pub const STEP_DESKTOP: &str = "desktop";

/// The words the desktop half shows when the backend half did not finish, so
/// nothing was put on top of it.
///
/// Written once, here, rather than at the call site — and the test below reads
/// this same constant. The sentence exists to say "Not installed" about a half
/// that was not installed, and nothing can check that against a *copy* of the
/// words: a copy drifts, and the first version of that test drifted on the
/// first letter, asserting `"Not installed"` against its own lowercase fixture
/// and so failing every run from the day it was written.
const DESKTOP_SKIPPED_DETAIL: &str =
    "Not installed. The backend step did not finish, so nothing was put on top of \
     it. Fix what the log above says, then run this again - and Install on its own \
     below still works if you only want the desktop half.";

/// One half of a two-half update, as it ended.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Step {
    /// [`STEP_BACKEND`] or [`STEP_DESKTOP`].
    pub step: String,
    /// `ok`, `partial`, `failed` or `skipped`.
    ///
    /// `partial` is its own answer rather than a flavour of `ok`, because this
    /// project's rule is that a check which could not run is never a pass: a
    /// backend that patched but skipped its own tests is patched, and is not
    /// proven, and those are two different sentences.
    pub state: String,
    /// Plain words for the card. Always says what happened, and never says
    /// "updated" about a half that did not update.
    pub detail: String,
    /// The half's own log folder, for the backend half.
    pub log_dir: Option<String>,
    /// The script's own last lines, folded away behind the report.
    pub tail: String,
}

impl Step {
    fn ok(step: &str, detail: impl Into<String>) -> Step {
        Step {
            step: step.to_string(),
            state: "ok".to_string(),
            detail: detail.into(),
            log_dir: None,
            tail: String::new(),
        }
    }

    fn partial(step: &str, detail: impl Into<String>) -> Step {
        Step {
            state: "partial".to_string(),
            ..Step::ok(step, detail)
        }
    }

    fn failed(step: &str, detail: impl Into<String>) -> Step {
        Step {
            state: "failed".to_string(),
            ..Step::ok(step, detail)
        }
    }

    fn skipped(step: &str, detail: impl Into<String>) -> Step {
        Step {
            state: "skipped".to_string(),
            ..Step::ok(step, detail)
        }
    }

    /// The backend half's own log and last lines, folded onto any of the four
    /// endings above. The desktop half has neither, so this is only ever used
    /// on that one.
    fn with_log(self, log_dir: Option<String>, tail: String) -> Step {
        Step {
            log_dir,
            tail,
            ..self
        }
    }
}

/// What [`update_both`] did, half by half.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BothOutcome {
    /// Both halves, in the order they ran. A half that was not attempted is
    /// present as `skipped` with the reason, never left out — so the card
    /// cannot show one green line where two things were promised.
    pub steps: Vec<Step>,
    /// **True only when every step is `ok`.** This is the one boolean the card
    /// is allowed to paint green, and the rule it encodes is the whole point of
    /// the feature: a half-updated machine must never look updated.
    pub updated_both: bool,
    /// Whether the app or the backend was stopped and wants starting again.
    pub restart_needed: bool,
}

/// The rule above, as a function rather than a comment.
pub fn both_updated(steps: &[Step]) -> bool {
    !steps.is_empty() && steps.iter().all(|s| s.state == "ok")
}

/// **The order, in one place: backend first, the executable second, and the
/// executable not at all if the backend step did not finish.**
///
/// The owner also chooses the BACKEND's pace when the card asks: the three
/// paces (`max_speed`, `responsive`, `safe`) and their worker counts and ETA
/// ranges come from `tools/update_backend.py --modes-json`, read BEFORE
/// anything is started. An unknown pace is refused here in plain words, so a
/// page cannot send a pace this build does not have and get a different update
/// than it asked for.
///
/// **Not held on a stale link, deliberately, and that is the same decision
/// `backup_now` and `check_tool_updates` already made.** Being held belongs to
/// a command that raises or answers an approval card, so that the card is
/// decided against a live queue — this one raises none and decides none. What it
/// touches is this PC's own files and this PC's own executable, at the machine
/// the owner is sitting at, and the two steps check themselves: the patcher
/// rehearses the whole list on a copy before it writes, and `install_now`
/// verifies a signature before it runs anything.
///
/// Why this order and not the other:
///
/// * `apply-patches.ps1` refuses to touch a backend whose own `jarvis_hud.py` is
///   still running, and it is right to — a running Python has already imported
///   the modules being rewritten. This app is what started that process, so the
///   backend half is the one that needs a process stopped, and it goes first
///   while that is still true.
/// * A failure after the **first** half leaves a new backend with the old
///   desktop. That is the state this project lives in most of the time anyway
///   (the app is released far more often than the patcher is run), and every
///   screen already renders it honestly: a route the old app does not know is
///   simply not called. So it is the direction that degrades into the ordinary.
/// * A failure after the **second** half would be new desktop on an old backend:
///   the other everyday state, and also survivable — but it is the one that can
///   leave an executable that will not start, so it goes last, when the smaller,
///   signed, signature-checked step is all that is left.
/// * The backend half is also the one that can leave the machine half changed
///   (`apply-patches.ps1` says so itself, in its own words, when it has already
///   started writing). Doing it first means the run that says "not updated" is
///   the run that has *not* already replaced the executable.
///
/// **A second step that did not run is reported as `skipped`, and the whole
/// outcome is `updated_both: false`.** Nothing here can leave the card showing
/// one line where two things were asked for.
/// One `update_both` at a time inside this app (S3).
///
/// The lock FILE stops two updates on the PC (a terminal run, another build);
/// this stops a second press before it can stop the backend and only then be
/// refused, and it covers the moment before the tool has written its own lock.
static UPDATE_BOTH_RUNNING: AtomicBool = AtomicBool::new(false);

/// Held for one run; dropping it lets the next press through.
struct UpdateBothGuard;

impl Drop for UpdateBothGuard {
    fn drop(&mut self) {
        UPDATE_BOTH_RUNNING.store(false, Ordering::SeqCst);
    }
}

/// Take the in-app update slot, or `None` when one is already running.
fn claim_update_both() -> Option<UpdateBothGuard> {
    UPDATE_BOTH_RUNNING
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .ok()
        .map(|_| UpdateBothGuard)
}

///
/// Never automatic: this is a `#[tauri::command]` reachable only from the one
/// button, nothing spawns it, and there is no setting anywhere that turns it
/// into a background job.
#[tauri::command]
pub async fn update_both(app: AppHandle, mode: String) -> Result<BothOutcome, String> {
    // S3: one press at a time in this window, and no press while a run from
    // anywhere else on this PC holds the update lock. Both refusals say plainly
    // that nothing was started or changed.
    let Some(_in_app) = claim_update_both() else {
        return Err(
            "A backend update is already running in this window. Wait for it \
                    to finish; nothing was changed."
                .to_string(),
        );
    };
    if let Some(lock) = crate::backend_update::held_update_lock(&app) {
        return Err(crate::backend_update::update_running_words(&lock));
    }
    // ---- 0. the pace, read from the tool before anything runs -------------
    let here = crate::backend_update::locate(&app);
    if let Some(why) = here.blocked.clone() {
        // The same plain refusal the card already shows under the button;
        // nothing has been started, and nothing has been changed.
        return Err(why);
    }
    let (modes, modes_note) = match (here.repo.as_deref(), here.backend.as_deref()) {
        (Some(repo), Some(backend)) => crate::backend_update::mode_plan_for(repo, backend),
        _ => (Vec::new(), None),
    };
    // A program folder older than this feature has no tool to ask, so there is
    // no pace table. It can still update - the fallback path runs the patcher
    // exactly as every update did before - but only at the default pace: a
    // pace this build cannot check is never silently accepted.
    let (mode_label, workers) = if modes.is_empty() {
        if mode != "responsive" {
            return Err(modes_note.unwrap_or_else(|| {
                format!(
                    "There is no update pace called \"{mode}\" on this PC. The only pace \
                     available here is responsive (the older one-at-a-time update). \
                     Nothing was changed."
                )
            }));
        }
        ("Balanced (older one-at-a-time update)".to_string(), 1)
    } else {
        if !crate::backend_update::known_mode(&modes, &mode) {
            return Err(crate::backend_update::unknown_mode_words(&modes, &mode));
        }
        modes
            .iter()
            .find(|row| row.id == mode)
            .map(|row| (row.label.clone(), row.workers))
            .unwrap_or_else(|| (mode.clone(), 1))
    };
    let mut steps: Vec<Step> = Vec::new();

    // ---- 1. the backend ------------------------------------------------
    let opening = format!(
        "Patching the backend folder at the {mode_label} pace ({workers} check(s) at a \
         time). This can take several minutes - it applies every patch and then runs the \
         test suites."
    );
    let _ = app.emit(
        crate::events::UPDATE_STEP,
        step_starting(STEP_BACKEND, Some(&opening)),
    );
    let backend = crate::backend_update::run(&app, &mode, &mode_label).await;
    // `proven` is its own answer rather than a flavour of done: a backend that
    // patched but skipped its own checks is patched, and is not a pass.
    let backend_step = if !backend.ok {
        Step::failed(STEP_BACKEND, backend.detail.clone())
    } else if backend.proven {
        Step::ok(STEP_BACKEND, backend.detail.clone())
    } else {
        Step::partial(STEP_BACKEND, backend.detail.clone())
    }
    .with_log(backend.log_dir.clone(), backend.tail.clone());
    let _ = app.emit(crate::events::UPDATE_STEP, backend_step.clone());
    let backend_ok = backend.ok;
    let backend_stopped = backend.stopped;
    steps.push(backend_step);

    if !backend_ok {
        // STOP. The desktop half is not attempted, and the card is told so in
        // as many words rather than being left to infer it from a green line
        // that is not there.
        let skipped = Step::skipped(STEP_DESKTOP, DESKTOP_SKIPPED_DETAIL);
        let _ = app.emit(crate::events::UPDATE_STEP, skipped.clone());
        steps.push(skipped);
        return Ok(BothOutcome {
            updated_both: both_updated(&steps),
            steps,
            // Only when this attempt actually stopped Jarvis. A refusal that
            // never got that far has nothing to start again.
            restart_needed: backend_stopped,
        });
    }

    // ---- 2. the executable ---------------------------------------------
    let _ = app.emit(
        crate::events::UPDATE_STEP,
        step_starting(STEP_DESKTOP, None),
    );
    let desktop_step = match install_now(&app).await {
        Ok(version) => Step::ok(
            STEP_DESKTOP,
            format!("Jarvis Desktop {version} is installed and restarts as {version}."),
        ),
        Err(err) => Step::failed(
            STEP_DESKTOP,
            format!(
                "Jarvis Desktop was NOT installed: {err}. The backend half above is done; \
                 press Install on its own below to try this half again."
            ),
        ),
    };
    let installed = desktop_step.state == "ok";
    let _ = app.emit(crate::events::UPDATE_STEP, desktop_step.clone());
    steps.push(desktop_step);

    let outcome = BothOutcome {
        updated_both: both_updated(&steps),
        steps,
        // Either the new executable is on disk and the old one is still
        // running, or Jarvis was stopped for the backend half and is still off.
        restart_needed: installed || backend_stopped,
    };
    Ok(outcome)
}

/// The placeholder a step emits when it starts, so the card can say which half
/// is running rather than sitting silent for the minutes a patch run takes.
/// The backend half carries the chosen pace's own words (`opening`).
fn step_starting(step: &str, opening: Option<&str>) -> Step {
    Step {
        step: step.to_string(),
        state: "running".to_string(),
        detail: if step == STEP_BACKEND {
            opening.map(str::to_string).unwrap_or_else(|| {
                "Patching the backend folder. This can take several minutes - it \
                     applies every patch and then runs the test suites."
                    .to_string()
            })
        } else {
            "Downloading and verifying Jarvis Desktop.".to_string()
        },
        log_dir: None,
        tail: String::new(),
    }
}

/// Restarts the app — reachable only from the button the install's own
/// success message now offers, never called automatically.
///
/// `request_restart` rather than `restart`: `restart` only skips the normal
/// `ExitRequested`/`Exit` sequence when it is called ON Tauri's main thread,
/// where it cleans up and re-execs directly; called from anywhere else it
/// falls back to that same event sequence anyway. This command handler is
/// dispatched off the main thread regardless — sync command handlers like
/// this one run on Tauri's own threadpool, not literally on the main thread —
/// so `restart` here would already take the safe path. `request_restart` is
/// kept anyway because it always takes that path outright, with no dependency
/// on which thread happens to call it, so `sidecar::stop_on_exit` reliably
/// stops a supervised backend first.
#[tauri::command]
pub fn restart_app(app: AppHandle) {
    app.request_restart();
}

/// The startup look, if the owner has left it on.
///
/// Spawned and forgotten: a slow or unreachable endpoint must not hold up the
/// window, the tray or the event stream.
pub fn spawn_startup_check(app: &AppHandle) {
    if !check_on_start(app) || !configured(app) {
        return;
    }
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        let status = look(&handle).await;
        handle.state::<UpdateState>().put(status.clone());
        if let Some(version) = status.available.as_deref() {
            println!("[jarvis] update available: {version}");
            // Told, not acted upon. The notification names the version and
            // says where to go; it cannot install anything and neither can the
            // tray row it points at.
            commands::notify(
                &handle,
                "Jarvis Desktop update available",
                &format!("Version {version} is ready to install from Settings."),
            );
        }
        crate::tray::on_update_status(&handle, status.available.as_deref());
        let _ = handle.emit(crate::events::UPDATE_STATUS, status);
    });
}

#[cfg(test)]
mod tests {
    use super::{
        both_updated, claim_update_both, friendly, step_starting, Step, DESKTOP_SKIPPED_DETAIL,
        STEP_BACKEND, STEP_DESKTOP,
    };

    #[test]
    fn a_missing_release_is_explained_rather_than_numbered() {
        // The first state this feature is ever in: the repository has no
        // releases, and "404" tells the owner nothing about what to do.
        let out = friendly("Network Error: http error 404 Not Found");
        assert!(out.contains("No releases published yet"), "{out}");
    }

    #[test]
    fn a_bad_signature_says_it_was_refused() {
        // The one failure that must never read as a routine network problem.
        let out = friendly("signature verification failed");
        assert!(out.to_lowercase().contains("refused"), "{out}");
    }

    #[test]
    fn an_unknown_failure_is_passed_through_rather_than_swallowed() {
        assert_eq!(friendly("something odd"), "something odd");
    }

    // ---- both halves ------------------------------------------------------

    fn done(step: &str) -> Step {
        Step::ok(step, "fine")
    }

    #[test]
    fn only_two_ok_halves_read_as_updated() {
        // The load-bearing rule of the whole feature, as a function: a machine
        // with one half done is NOT an updated machine, and a card that said
        // otherwise would be the exact failure this was built to avoid.
        assert!(both_updated(&[done(STEP_BACKEND), done(STEP_DESKTOP)]));
        // A backend that patched but could not prove itself is not a pass.
        assert!(!both_updated(&[
            Step::partial(STEP_BACKEND, "patched, unproven"),
            done(STEP_DESKTOP)
        ]));
        // A refused or failed backend half, with the desktop half not tried.
        assert!(!both_updated(&[
            Step::failed(STEP_BACKEND, "did not finish"),
            Step::skipped(STEP_DESKTOP, "not installed")
        ]));
        // A backend that worked and a desktop half that did not.
        assert!(!both_updated(&[
            done(STEP_BACKEND),
            Step::failed(STEP_DESKTOP, "no newer version")
        ]));
        // Nothing at all is not "updated" either.
        assert!(!both_updated(&[]));
    }

    #[test]
    fn a_skipped_half_is_reported_rather_than_dropped() {
        // The sentence the card is actually handed, not a copy of it: this test
        // used to assert "Not installed" against a fixture it had typed as
        // "not installed" itself, so it failed every run without ever looking at
        // the words the owner sees.
        let skipped = Step::skipped(STEP_DESKTOP, DESKTOP_SKIPPED_DETAIL);
        assert_eq!(skipped.state, "skipped");
        // ...and it says it was NOT installed, not that it was.
        assert!(
            skipped.detail.contains("Not installed"),
            "{}",
            skipped.detail
        );
        assert!(
            !skipped.detail.contains("is installed"),
            "the skipped half reads as if it had been installed: {}",
            skipped.detail
        );
        assert_ne!(skipped.state, "ok");
    }

    #[test]
    fn a_running_half_says_which_half_and_never_reads_as_finished() {
        let backend = step_starting(STEP_BACKEND, None);
        let desktop = step_starting(STEP_DESKTOP, None);
        assert_eq!(backend.state, "running");
        assert_eq!(desktop.state, "running");
        assert!(backend.detail.contains("Patching the backend"));
        assert!(desktop.detail.contains("Downloading"));
        // Neither can be mistaken for an ending: if a window is closed and
        // reopened mid-run the card must not paint either as done.
        assert_ne!(backend.state, "ok");
    }

    /// The pace words the card shows come from the tool's own answer, read
    /// before anything runs; an unknown one is refused in plain words naming
    /// the three that exist, never silently defaulted.
    #[test]
    fn an_unknown_pace_is_refused_with_the_three_that_exist() {
        let modes = vec![
            crate::backend_update::ModeInfo {
                id: "max_speed".to_string(),
                label: "Fastest".to_string(),
                ..Default::default()
            },
            crate::backend_update::ModeInfo {
                id: "responsive".to_string(),
                label: "Balanced".to_string(),
                recommended: true,
                ..Default::default()
            },
            crate::backend_update::ModeInfo {
                id: "safe".to_string(),
                label: "Safest".to_string(),
                ..Default::default()
            },
        ];
        assert!(crate::backend_update::known_mode(&modes, "responsive"));
        assert!(!crate::backend_update::known_mode(&modes, "turbo"));
        // An empty table is "not known", not "everything is allowed".
        assert!(!crate::backend_update::known_mode(&[], "responsive"));
        let said = crate::backend_update::unknown_mode_words(&modes, "turbo");
        for expected in [
            "turbo",
            "max_speed",
            "responsive",
            "safe",
            "Nothing was changed",
        ] {
            assert!(said.contains(expected), "{expected} missing from {said}");
        }
    }

    /// The pace's own words reach the running step, so the card says which pace
    /// is running rather than the same sentence for all three.
    #[test]
    fn a_running_backend_step_names_the_chosen_pace() {
        let words = "Patching the backend folder at the Balanced pace (14 check(s) at a time).";
        let step = step_starting(STEP_BACKEND, Some(words));
        assert_eq!(step.detail, words);
        assert_eq!(step.state, "running");
    }

    /// S3: a second press must be refused inside the app before it can stop the
    /// backend - the lock file alone arrives too late for that.
    #[test]
    fn only_one_update_both_can_be_in_flight_in_this_app() {
        let first = claim_update_both().expect("the first run takes the slot");
        assert!(
            claim_update_both().is_none(),
            "a second press was allowed while the first run was in flight"
        );
        drop(first);
        assert!(
            claim_update_both().is_some(),
            "the slot was not released when the first run ended"
        );
    }
}
