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
//! the two halves in one deliberate order; it runs from the Settings button and,
//! since 2026-10-26, from `run_approved_update` after an answered
//! `desktop_update` card - never from a page, a timer or a setting.
//! [`crate::backend_update`] owns the backend half and its own refusals. The
//! order, and why it is that order, is written out on [`update_both`] itself.
//!
//! ## What really happens on Windows, and why the ending is written down
//!
//! `tauri-plugin-updater`'s Windows installer path ends this process with
//! `std::process::exit(0)` *after* it has launched the installer. The crate says
//! so itself on `Update::install` ("this function exits the app after launching
//! the updater installer successfully"), and the pinned source shows the order:
//! the `on_before_exit` hook, then `ShellExecuteW`, then the exit. Nothing after
//! the install call in this process can run - not a line of ours, not
//! `RunEvent::ExitRequested`, not `Drop` - so the desktop half **cannot report
//! its own ending**. This module does not pretend otherwise:
//!
//! * the package is downloaded and its signature verified **before anything on
//!   this PC is changed** ([`verify_desktop_package`]);
//! * a record (`pending-desktop-update.json`, in `~/.openjarvis` beside the
//!   update lock) is then written **atomically** and read back - naming the
//!   version being replaced, the version being installed, which commit each
//!   half came from, and what the backend half did ([`write_desktop_record`]);
//! * only then is the Python backend stopped, waiting at most three seconds
//!   ([`crate::sidecar::stop_for_installer`]), and only then is the installer
//!   called - last ([`install_now`]);
//! * the updater's own `on_before_exit` hook marks the record "installer
//!   launched" immediately before `ShellExecuteW`. If this process dies before
//!   that line, the record still says the installer never ran, which is the
//!   truth;
//! * the **next launch** reconciles that record against the version actually
//!   running and says what really happened (a notification, a log line, and a
//!   line in the chat the update may have started from), then deletes it.
//!
//! The order is not a comment. Each step produces the value the next one needs
//! ([`VerifiedDesktop`] -> [`RecordedDesktop`] -> [`StoppedDesktop`]), so an
//! edit that tried to install first, or to stop the backend before the record
//! was written, would not compile. See [`prepare_desktop_half`].
//!
//! That is the only success path for the desktop half on Windows. It is why
//! [`BothOutcome::updated_both`] is not reachable there: an in-process "both
//! succeeded" would be a claim made after a process that has already ended. The
//! chat path therefore says what is about to happen before it happens, and the
//! next launch says how it ended; neither promises an ending it cannot see.
//!
//! ## What the controls say BEFORE they are pressed
//!
//! The Windows installer closes Jarvis and the new version starts again
//! afterwards. That is said before the press, not after it
//! ([`INSTALL_CLOSES_AND_RESTARTS`]): in the data the Updates card already reads
//! (`Status::install_notice`), in the notification that announces a new version,
//! in the first line the desktop half emits, and in the chat line an approved
//! update starts with. The Settings page renders that field in its own four
//! lines; that page belongs to another lane, so this module supplies the words
//! and the field rather than editing it.

//!
//! ## There is no rollback
//!
//! Nothing here can put the previous desktop version back. Every publish
//! recreates the rolling release with only the new installers
//! (`.github/workflows/desktop-release.yml`), the run copy kept as an artifact
//! expires, and `allowDowngrades` is `false` in `tauri.conf.json`, so an older
//! installer may refuse to run even where one still exists. A bad desktop
//! release is an owner decision to recover from (install a build you already
//! have, or a fresh clone and build); this module deliberately does not grow a
//! half-built rollback system that would imply otherwise. The backend half is
//! the only one with file backups (`_jarvis-backup-<date>`, made by
//! `scripts/apply-patches.ps1`).

use std::io::Write;
use std::path::{Path, PathBuf};
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

/// The sentence the update controls must carry BEFORE they are pressed.
///
/// The Windows installer closes Jarvis, and the new version is started again by
/// the installer when it is done (the crate's `restart_after_install` defaults
/// to true and this build does not turn it off). Somebody about to press a
/// button in the middle of something deserves that sentence first, not
/// afterwards - so it is in the data the Updates card already reads
/// ([`Status::install_notice`]), in the notification that announces a new
/// version, in the first line the desktop half emits, and in the chat line an
/// approved update starts with.
pub const INSTALL_CLOSES_AND_RESTARTS: &str =
    "Jarvis closes while this installs, and starts again by itself when it is \
     done. Save anything you are working on first.";

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
    /// What the Install / Update-both controls must say before they are pressed:
    /// the app closes while it installs and starts again afterwards. `None` when
    /// there is nothing to install, so a card with no Install button has nothing
    /// to warn about.
    pub install_notice: Option<String>,
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
            // The Install control is about to exist on the card, so the
            // sentence it must carry before the press exists with it.
            status.install_notice = install_notice_for(status.available.as_deref());
        }
        Ok(None) => {}
        Err(err) => {
            status.error = Some(friendly(&err.to_string()));
        }
    }
    status
}

/// The pre-click sentence, or `None` when there is no Install control to show.
///
/// Pure, so the rule is a test: the sentence is offered exactly when there is a
/// version to install - and never for a build that cannot verify a download,
/// because that build shows no Install button at all.
fn install_notice_for(available: Option<&str>) -> Option<String> {
    available.map(|_| INSTALL_CLOSES_AND_RESTARTS.to_string())
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
/// Separate from `check_for_update` rather than a flag on it, so that no future
/// edit can make checking install something by passing `true`.
///
/// The lone **Install** button is the second door into the desktop half, and it
/// goes through the same ordered preparation as "update both halves": the
/// package is downloaded and checked, the record is written, the backend is
/// stopped, and only then is the installer called. Before this round it reached
/// the installer with a supervised backend still running.
#[tauri::command]
pub async fn install_update(app: AppHandle) -> Result<String, String> {
    let here = crate::backend_update::locate(&app);
    let backend_commit = crate::backend_update::repo_commit(here.repo.as_deref());
    // Said before anything is downloaded: on Windows this process ends when the
    // installer starts, so there is no second chance to say it.
    crate::logfile::log(&format!("[jarvis] {INSTALL_CLOSES_AND_RESTARTS}"));
    say_in_hud(&app, "running", INSTALL_CLOSES_AND_RESTARTS);
    let ready = prepare_desktop_half(&app, None, backend_commit).await?;
    install_now(&app, ready).await
}

// ---------------------------------------------------------------------------
// The desktop half: verify, record, stop, and only then install
// ---------------------------------------------------------------------------
//
// The four steps are values rather than a comment, so their order cannot be
// rearranged by a later edit without the compiler objecting:
//
//   (b) `verify_desktop_package` -> `VerifiedDesktop`
//   (c) `write_desktop_record`   -> `RecordedDesktop`
//   (d) `stop_backend_for_installer` -> `StoppedDesktop`
//   (e) `install_now` takes a `StoppedDesktop`, so it cannot be reached before
//       (b), (c) and (d) have happened.
//
// A second, ordered list in one place documents the same thing for the tests
// and for a reader: [`DESKTOP_HALF`].

/// One step of the desktop half, in the order the design fixes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DesktopHalf {
    /// (b) Download the package and check its signature. Changes nothing local.
    VerifyPackage,
    /// (c) Write the pending-install record, atomically, and read it back.
    WriteRecord,
    /// (d) Stop the supervised backend, waiting at most three seconds.
    StopBackend,
    /// (e) Hand the verified package to the installer. Last, and the only step
    /// that can end this process on Windows.
    Install,
}

/// The order, in one place.
///
/// A value rather than a comment: this is the fix (the backend is stopped and
/// the record is written before the installer can replace files), and an edit
/// that moved the install earlier - or the stop after the install, where it
/// could never run on Windows - would be changing this array.
const DESKTOP_HALF: [DesktopHalf; 4] = [
    DesktopHalf::VerifyPackage,
    DesktopHalf::WriteRecord,
    DesktopHalf::StopBackend,
    DesktopHalf::Install,
];

/// The order above, as one line for the log of every install.
///
/// It reads [`DESKTOP_HALF`] rather than repeating it, so the log the owner can
/// send names the order the run actually used - and so the array is not a
/// comment in disguise: it is written into the log before the desktop half
/// starts, and a real update's log is where a wrong order would first be seen.
fn desktop_half_trace() -> String {
    DESKTOP_HALF
        .iter()
        .map(|step| match step {
            DesktopHalf::VerifyPackage => "check the package",
            DesktopHalf::WriteRecord => "write the record",
            DesktopHalf::StopBackend => "stop the backend",
            DesktopHalf::Install => "install",
        })
        .collect::<Vec<_>>()
        .join(" -> ")
}

/// A desktop package that has been downloaded and whose signature has been
/// checked, but that has not been installed. Step (b).
struct VerifiedDesktop {
    update: tauri_plugin_updater::Update,
    /// The bytes the installer will run. `download` verifies them before it
    /// returns; nothing here is executed until step (e).
    bytes: Vec<u8>,
    /// The version this package installs.
    target: String,
}

/// ... and whose record is on disk and readable. Step (c).
struct RecordedDesktop {
    verified: VerifiedDesktop,
    /// Where the record is. Also the path the updater's hook marks "launched".
    record: PathBuf,
}

/// ... and whose backend has been stopped. Step (d).
///
/// The only value [`install_now`] accepts, which is what makes step (e) last.
struct StoppedDesktop {
    recorded: RecordedDesktop,
}

/// Steps (b), (c) and (d) of the desktop half, in the fixed order.
///
/// The order is not a comment here either: each step consumes the value the
/// previous one produced. What it buys:
///
/// * the package is known good **before** anything on this PC is changed, so a
///   refused signature or a failed download leaves the backend running and
///   writes no record;
/// * the record is on disk - and read back - **before** the backend is stopped,
///   so a process that dies during the stop still leaves the truth ("the
///   installer never ran");
/// * the backend is stopped **before** the installer can replace the files it is
///   running from, and the wait is bounded so a wedged backend cannot hold the
///   installer for ever.
async fn prepare_desktop_half(
    app: &AppHandle,
    backend: Option<BackendHalf>,
    backend_commit: Option<String>,
) -> Result<StoppedDesktop, String> {
    let Some(record) = pending_path(app) else {
        // No record means no honest ending: the desktop half would vanish with
        // nothing left behind to read. Refusing is the smaller failure.
        return Err(
            "Jarvis could not find the folder where its update record has to go, so it \
             did not start the installer. Nothing was changed."
                .to_string(),
        );
    };
    // The order this run will use, written into the log the owner can send, so
    // a wrong order would be visible in a real update's log rather than only in
    // this file. It reads `DESKTOP_HALF`; it does not restate it.
    crate::logfile::log(&format!(
        "[jarvis] desktop half order: {}",
        desktop_half_trace()
    ));
    let verified = verify_desktop_package(app, &record).await?;
    let recorded = write_desktop_record(app, &record, verified, backend, backend_commit)?;
    Ok(stop_backend_for_installer(app, recorded))
}
/// Step (b): checks for a newer release, downloads it and verifies its
/// signature. Nothing on this PC is changed, and nothing is executed.
///
/// The updater's `on_before_exit` hook is registered HERE rather than at the
/// install, because the crate keeps the hook on the updater that produced the
/// `Update`: a hook added later would never run at all. It is the last code of
/// ours that runs on Windows (pinned source: the hook, then `ShellExecuteW`,
/// then `process::exit(0)`).
async fn verify_desktop_package(app: &AppHandle, record: &Path) -> Result<VerifiedDesktop, String> {
    if !configured(app) {
        return Err("this build has no update key, so it cannot verify a download".to_string());
    }
    let hook_app = app.clone();
    let hook_record = record.to_path_buf();
    let updater = app
        .updater_builder()
        .on_before_exit(move || before_installer_runs(&hook_app, &hook_record))
        .build()
        .map_err(|e| format!("the updater could not start: {e}"))?;
    let update = updater
        .check()
        .await
        .map_err(|e| friendly(&e.to_string()))?
        .ok_or_else(|| "there is no newer version to install".to_string())?;
    let target = update.version.clone();

    // `on_chunk` reports the size of the piece JUST received, not a running
    // total — the settings window showed no percentage at all before this,
    // for exactly that reason: nothing here was turning "another chunk
    // arrived" into "how far along am I" or telling anyone either number.
    let downloaded = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(0));
    let progress_app = app.clone();
    let progress_downloaded = downloaded.clone();
    // The signature is checked inside this call, before the bytes come back and
    // before anything can run: a release replaced at the CDN, a hijacked DNS
    // answer or a proxy rewriting the response all fail here, with nothing on
    // this PC changed.
    let bytes = update
        .download(
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
        .map_err(|e| friendly(&e.to_string()))?;
    Ok(VerifiedDesktop {
        update,
        bytes,
        target,
    })
}

/// Step (c): the record, written atomically and read back before anything is
/// stopped or installed.
///
/// A record the next launch cannot read is the same as no record at all, so the
/// write is checked by reading it back with the same function the next launch
/// uses.
fn write_desktop_record(
    app: &AppHandle,
    record: &Path,
    verified: VerifiedDesktop,
    backend: Option<BackendHalf>,
    backend_commit: Option<String>,
) -> Result<RecordedDesktop, String> {
    let pending = PendingDesktopInstall {
        target_version: verified.target.clone(),
        from_version: version(app),
        started_at: unix_now(),
        installer_launched: false,
        app_commit: crate::backend_update::app_commit(),
        backend_commit,
        backend_step: backend,
    };
    write_pending(record, &pending).map_err(|err| {
        format!(
            "Jarvis could not write its update record ({err}), so it did not start the \
             installer. Nothing was changed."
        )
    })?;
    if read_pending(record) != Some(pending) {
        clear_pending(record);
        return Err(
            "Jarvis wrote its update record but could not read it back, so it did not \
             start the installer. Nothing was changed."
                .to_string(),
        );
    }
    Ok(RecordedDesktop {
        verified,
        record: record.to_path_buf(),
    })
}

/// Step (d): stop the supervised backend, bounded, and hand (e) its value.
///
/// The stop is the same function the updater's own hook calls, so the two
/// cannot disagree about how a backend is stopped - and it is idempotent: by
/// the time the hook runs, this app has already let go of the child, so the
/// hook's own stop is a no-op.
fn stop_backend_for_installer(app: &AppHandle, recorded: RecordedDesktop) -> StoppedDesktop {
    let outcome = crate::sidecar::stop_for_installer(app);
    crate::logfile::log(&format!(
        "[jarvis] {}",
        crate::sidecar::stop_for_installer_words(outcome)
    ));
    StoppedDesktop { recorded }
}

/// Step (e), LAST: hands the verified package to the Windows installer.
///
/// It takes a [`StoppedDesktop`], so there is no way to call it before the
/// package was verified, the record was written and the backend was stopped:
/// the order is the type, not a comment.
///
/// # What happens after the last line of this function on Windows
///
/// Nothing of ours. This call reaches the crate's Windows installer path, which
/// launches the installer and then calls `std::process::exit(0)`; the `Ok`/`Err`
/// returned here is reached only when the installer was NOT launched (a failed
/// extraction) or on a platform without that exit. The ending is therefore
/// written down first, and reported by the next launch - see this module's own
/// docs.
async fn install_now(app: &AppHandle, ready: StoppedDesktop) -> Result<String, String> {
    let RecordedDesktop { verified, record } = ready.recorded;
    let VerifiedDesktop {
        update,
        bytes,
        target,
    } = verified;
    crate::logfile::log(&format!(
        "[jarvis] installing Jarvis Desktop {target} over {}: the record is written and \
         the backend is stopped.",
        version(app)
    ));
    let result = update.install(&bytes);

    // On Windows this point is reached only when the installer was NOT
    // launched - the process that launched it is already gone. This process is
    // still here, so it says what happened itself and clears the record.
    clear_pending(&record);
    result.map_err(|e| format!("the update failed to install: {e}"))?;
    Ok(target)
}

// ---------------------------------------------------------------------------
// The desktop half across the process that ends it
// ---------------------------------------------------------------------------
//
// The crate's Windows path is: `on_before_exit` hook -> `ShellExecuteW` ->
// `std::process::exit(0)`. The hook is the only place left to act, and the next
// launch is the only place left to report. Everything below is that hand-over:
// a small JSON record written before the backend is stopped, marked "launched"
// by the hook immediately before the installer runs, and reconciled against the
// running version on the next start.

/// The record's file name, inside the folder Jarvis keeps its own data in.
///
/// `~/.openjarvis` - or `OPENJARVIS_CONFIG_DIR` / `JARVIS_CONFIG_DIR` when one
/// is set, the same order `backend_update::config_dir` uses for the update lock.
/// It is deliberately NOT this app's log folder: a log can be cleared, and the
/// record has to be readable by the next launch even then.
const PENDING_FILE: &str = "pending-desktop-update.json";

/// What the backend half did in the same press.
///
/// Carried across the restart so the next launch can say whether BOTH halves
/// finished - and never say more than the two states support.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BackendHalf {
    /// The same `ok` / `partial` / `failed` / `skipped` as [`Step::state`].
    pub state: String,
    /// The sentence the card already shows for that half.
    pub detail: String,
}

/// The desktop half, written to disk before the backend is stopped and before
/// the installer can run.
///
/// It has to survive this process: the Windows installer path ends it, so
/// nothing here can report the ending. Nothing secret goes in it - two versions,
/// two commit hashes and the backend half's own sentence.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PendingDesktopInstall {
    /// The version the installer was asked to put on disk.
    #[serde(alias = "target")]
    pub target_version: String,
    /// The version this process was running when it asked.
    #[serde(alias = "from")]
    pub from_version: String,
    /// Unix seconds. The record is never acted on by age; this is so a person
    /// reading the file knows when it was written.
    pub started_at: u64,
    /// True only once the updater's own `on_before_exit` hook has run - after the
    /// backend is stopped and immediately before the installer is launched. A
    /// record that still says `false` is an install that never reached the
    /// installer.
    pub installer_launched: bool,
    /// The commit the app being replaced was built from.
    pub app_commit: Option<String>,
    /// The commit the backend folder was at, when it could be read.
    pub backend_commit: Option<String>,
    /// The backend half's ending, when the same press ran one. Named
    /// `backend_step` because that is what it is: the backend [`Step`]'s own
    /// state and sentence, carried across the restart.
    #[serde(alias = "backend")]
    pub backend_step: Option<BackendHalf>,
}

/// What the next launch can honestly say about the desktop half.
#[derive(Debug, Clone, PartialEq)]
pub enum DesktopEnding {
    /// The version running now is the one the installer was asked for.
    Finished {
        from: String,
        target: String,
        backend: Option<BackendHalf>,
    },
    /// The record exists but the hook never ran: the installer never started.
    NotLaunched {
        from: String,
        target: String,
        backend: Option<BackendHalf>,
    },
    /// The installer was started, and the version running is the OLD one.
    NotInstalled {
        from: String,
        target: String,
        running: String,
        backend: Option<BackendHalf>,
    },
    /// The installer was started and neither the old nor the target version is
    /// running. Say so rather than guessing which one won.
    OtherVersion {
        from: String,
        target: String,
        running: String,
        backend: Option<BackendHalf>,
    },
}

/// Reads the record against the version actually running.
///
/// Pure, so every branch is a test: this is the one place in the module that
/// decides whether a desktop update is allowed to count as done.
pub fn reconcile(pending: Option<&PendingDesktopInstall>, running: &str) -> Option<DesktopEnding> {
    let pending = pending?;
    let backend = pending.backend_step.clone();
    if same_version(running, &pending.target_version) {
        return Some(DesktopEnding::Finished {
            from: pending.from_version.clone(),
            target: pending.target_version.clone(),
            backend,
        });
    }
    if !pending.installer_launched {
        return Some(DesktopEnding::NotLaunched {
            from: pending.from_version.clone(),
            target: pending.target_version.clone(),
            backend,
        });
    }
    if same_version(running, &pending.from_version) {
        return Some(DesktopEnding::NotInstalled {
            from: pending.from_version.clone(),
            target: pending.target_version.clone(),
            running: running.to_string(),
            backend,
        });
    }
    Some(DesktopEnding::OtherVersion {
        from: pending.from_version.clone(),
        target: pending.target_version.clone(),
        running: running.to_string(),
        backend,
    })
}

/// Two version strings name the same release.
///
/// Both sides are semver and normally identical character for character. The
/// only differences forgiven here are the ones a person would forgive - case and
/// a leading `v`. Build metadata is NOT stripped: it is part of what a version
/// says.
fn same_version(a: &str, b: &str) -> bool {
    let norm = |s: &str| {
        s.trim()
            .trim_start_matches(['v', 'V'])
            .trim()
            .to_ascii_lowercase()
    };
    norm(a) == norm(b)
}

/// The plain sentence for the owner, from the reconciled ending.
///
/// Every branch names the versions it actually knows and what it cannot see.
/// The backend sentence is assembled from the state the backend half really
/// ended in, so "both halves are done" can only appear for a desktop half that
/// landed AND a backend half that was `ok` (which already means proven).
pub fn ending_words(
    ending: &DesktopEnding,
    app_commit: Option<&str>,
    backend_commit: Option<&str>,
) -> String {
    let halves = crate::backend_update::halves_line(app_commit, backend_commit);
    match ending {
        DesktopEnding::Finished {
            from,
            target,
            backend,
            ..
        } => format!(
            "Jarvis Desktop is now {target}; it was {from} when the Windows installer \
             started.{} {halves}",
            backend_finished_sentence(backend)
        ),
        DesktopEnding::NotLaunched {
            from,
            target,
            backend,
        } => format!(
            "A desktop update from {from} to {target} was started, but the Windows \
             installer never ran, so Jarvis Desktop is still {from}. Press Install in \
             Settings, then Updates, to try again.{} {halves}",
            backend_missing_sentence(backend)
        ),
        DesktopEnding::NotInstalled {
            from,
            target,
            running,
            backend,
        } => format!(
            "The Windows installer for {target} was started, but Jarvis came back as \
             {running} (it was {from} when the installer started), so the desktop half \
             has not taken effect - it may have been cancelled, or it may still be \
             running.{} {halves}",
            backend_missing_sentence(backend)
        ),
        DesktopEnding::OtherVersion {
            from,
            target,
            running,
            backend,
        } => format!(
            "Jarvis is running {running}; an installer for {target} was started from \
             {from}. This launch cannot say which version the installer left, so check \
             Settings, then Updates.{} {halves}",
            backend_missing_sentence(backend)
        ),
    }
}

/// One sentence about the backend half, when the desktop half did land.
fn backend_finished_sentence(backend: &Option<BackendHalf>) -> &'static str {
    match backend.as_ref().map(|half| half.state.as_str()) {
        Some("ok") => {
            " The backend half had already finished before the installer ran, so both \
             halves are done."
        }
        Some("partial") => {
            " The backend half had patched but its checks were skipped, so it is not \
             proven; only the desktop half finished cleanly."
        }
        Some(_) => " The backend half did not finish, so only the desktop half changed.",
        None => " No backend update ran with it, so only the desktop half changed.",
    }
}

/// One sentence about the backend half, when the desktop half did not land.
fn backend_missing_sentence(backend: &Option<BackendHalf>) -> &'static str {
    match backend.as_ref().map(|half| half.state.as_str()) {
        Some("ok") => " The backend half had already finished.",
        Some("partial") => " The backend half had patched but its checks were skipped.",
        Some(_) => " The backend half did not finish.",
        None => "",
    }
}

/// The notification's title: never "updated" about a half that did not.
fn ending_title(ending: &DesktopEnding) -> &'static str {
    match ending {
        DesktopEnding::Finished { .. } => "Jarvis Desktop is updated",
        DesktopEnding::NotLaunched { .. } | DesktopEnding::NotInstalled { .. } => {
            "Jarvis Desktop was not updated"
        }
        DesktopEnding::OtherVersion { .. } => "Jarvis Desktop update: check what happened",
    }
}

/// The state word for the HUD's chat line (`UpdateWord`).
fn ending_state(ending: &DesktopEnding) -> &'static str {
    match ending {
        DesktopEnding::Finished { .. } => "ok",
        _ => "failed",
    }
}

/// The two things that must happen between "the installer is about to run" and
/// the installer running, in the only order that keeps the record true.
///
/// A value rather than a comment: the order is the fix for the orphaned backend,
/// and an edit that swaps it - marking the record "launched" before the stop -
/// would make a process that dies during the stop leave a record claiming an
/// installer that never ran. The test holds this array.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BeforeInstaller {
    /// Ask the Python backend to stop, and wait for it. The installer replaces
    /// files the running backend has already imported.
    StopBackend,
    /// Only now write "installer launched" into the record.
    MarkLaunched,
}

const BEFORE_INSTALLER: [BeforeInstaller; 2] =
    [BeforeInstaller::StopBackend, BeforeInstaller::MarkLaunched];

/// The updater's `on_before_exit` hook: the last code of ours that runs on
/// Windows, immediately before the crate launches the installer and exits.
fn before_installer_runs(app: &AppHandle, path: &Path) {
    for step in BEFORE_INSTALLER {
        match step {
            BeforeInstaller::StopBackend => stop_sidecar_for_installer(app),
            BeforeInstaller::MarkLaunched => mark_launched(path),
        }
    }
    let words = "Installing Jarvis Desktop now. Jarvis is closing, and the next start says \
                 whether the desktop half finished.";
    crate::logfile::log(&format!("[jarvis] {words}"));
    announce_step(app, &Step::running(STEP_DESKTOP, words));
}

/// Stops the supervised backend from inside the updater's hook - the second,
/// last-gate check, after [`stop_backend_for_installer`]'s bounded one.
///
/// The hook runs on the async runtime's thread (inside the install call's
/// `.await`), and [`crate::sidecar::stop_on_exit`] uses `block_on` - calling it
/// straight from here would be a nested `block_on` on the same runtime, which
/// panics. So the stop moves to a plain OS thread and this waits for it: the
/// hook must not return until the backend is gone, because the installer starts
/// the moment it does.
///
/// This one is deliberately NOT bounded, unlike the explicit stop three seconds
/// earlier: by the time the hook runs the app has already let go of the child,
/// so this is a no-op (`stop_on_exit` returns immediately when nothing is
/// owned) - and if it is not a no-op, a wedged backend must hold the installer
/// rather than let it replace files the backend is still using. A panic in the
/// stop is reported and swallowed rather than aborting the install, and it
/// cannot leave the news unsaid, because the record is already on disk.
fn stop_sidecar_for_installer(app: &AppHandle) {
    let handle = app.clone();
    let joined = std::thread::spawn(move || crate::sidecar::stop_on_exit(&handle)).join();
    if joined.is_err() {
        crate::logfile::log(
            "[jarvis] the backend could not be stopped on the way into the installer; the \
             installer still runs, so the backend may be left running",
        );
    }
}

/// Marks the record "installer launched" - after the backend is stopped, and
/// before the crate reaches `ShellExecuteW`.
fn mark_launched(path: &Path) {
    let Some(mut pending) = read_pending(path) else {
        return;
    };
    pending.installer_launched = true;
    if let Err(err) = write_pending(path, &pending) {
        crate::logfile::log(&format!(
            "[jarvis] the update record could not be marked as launched: {err}"
        ));
    }
}

/// Where the record lives: the folder Jarvis keeps its own data in
/// (`~/.openjarvis`), beside the update lock.
///
/// The folder is created by the write when it is not there. A folder that cannot
/// be named at all is a refusal, never a silent install: without a record there
/// is no honest ending to report.
fn pending_path(app: &AppHandle) -> Option<PathBuf> {
    crate::backend_update::config_dir(app).map(|dir| dir.join(PENDING_FILE))
}

fn unix_now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|since| since.as_secs())
        .unwrap_or(0)
}

/// Reads a record, or `None` when there is none or it is not readable.
///
/// A half-written record reads as "no record" rather than as a guess: the file
/// is written before the installer runs, so the only way to see half of one is
/// a crash during that write, and in that case there is nothing true to say.
/// [`write_pending`] makes even that unlikely: the record is replaced by a
/// rename, so a reader sees the whole old one or the whole new one.
fn read_pending(path: &Path) -> Option<PendingDesktopInstall> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

/// Writes the record atomically, and flushes it to disk before returning.
///
/// Two things this has to promise:
///
/// * **It is on disk, not only in the page cache.** The process the installer
///   ends never gets another chance to flush.
/// * **A reader never sees half of it.** The text goes to a temporary file in
///   the same folder (same volume), is flushed, and is then moved over the
///   record with one rename. Before the rename a reader sees the old record,
///   after it the new one; the only way to see a partial file would be to read
///   the temporary name, which nothing does.
fn write_pending(path: &Path, pending: &PendingDesktopInstall) -> Result<(), String> {
    let text = serde_json::to_string_pretty(pending)
        .map_err(|err| format!("the record could not be written: {err}"))?;
    let dir = path
        .parent()
        .ok_or_else(|| format!("{}: the record has no folder", path.display()))?;
    std::fs::create_dir_all(dir).map_err(|err| format!("{}: {err}", dir.display()))?;
    // The process id keeps two Jarvises on one PC from writing the same
    // temporary name; the rename below is the only thing a reader can see.
    let temporary = dir.join(format!("{PENDING_FILE}.{}.tmp", std::process::id()));
    let written = (|| -> std::io::Result<()> {
        let mut file = std::fs::File::create(&temporary)?;
        file.write_all(text.as_bytes())?;
        file.sync_all()
    })();
    if let Err(err) = written {
        let _ = std::fs::remove_file(&temporary);
        return Err(format!("{}: {err}", path.display()));
    }
    if let Err(err) = std::fs::rename(&temporary, path) {
        let _ = std::fs::remove_file(&temporary);
        return Err(format!("{}: {err}", path.display()));
    }
    Ok(())
}

fn clear_pending(path: &Path) {
    let _ = std::fs::remove_file(path);
}

/// The next launch's half of the hand-over: says what the previous one's
/// installer really did, then forgets it.
///
/// Called once, from `lib.rs`'s setup, after the log folder exists and after the
/// notification plugin is up. The notification is the reliable half; the HUD
/// line is the chat's own surface and is best-effort (the page runs its own
/// bootstrap, so it is given a few seconds).
pub fn reconcile_pending_at_startup(app: &AppHandle) {
    let Some(path) = pending_path(app) else {
        return;
    };
    let Some(pending) = read_pending(&path) else {
        return;
    };
    let Some(ending) = reconcile(Some(&pending), &version(app)) else {
        return;
    };
    let words = ending_words(
        &ending,
        crate::backend_update::app_commit().as_deref(),
        pending.backend_commit.as_deref(),
    );
    // Forgot before it is said: the sentence is in memory and in the log, and a
    // notification that fails must not make the same news arrive on every launch.
    clear_pending(&path);
    crate::logfile::log(&format!("[jarvis] {words}"));
    commands::notify(app, ending_title(&ending), &words);

    let handle = app.clone();
    let state = ending_state(&ending).to_string();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_secs(4)).await;
        crate::push_to_hud(
            &handle,
            "update",
            &UpdateWord {
                state,
                detail: words,
            },
        );
    });
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

/// The words for the other refusal: the backend patched, but its own checks
/// could not run, so it is not **proven** - and an unproven half is not a pass
/// in this project.
///
/// A separate sentence rather than reusing the one above, because "did not
/// finish" would be false about a backend that did patch.
const DESKTOP_UNPROVEN_DETAIL: &str =
    "Not installed. The backend step patched, but its own checks could not run, so \
     it is not proven - and an unproven backend is not treated as a pass here, so \
     nothing was put on top of it. Fix what the log above says, then run this \
     again - and Install on its own below still works if you only want the \
     desktop half.";

/// Whether the desktop half may start: only for a backend half that is `ok`,
/// which [`update_both`] builds only when the patcher proved itself.
///
/// `partial` is its own state precisely so this can be a plain decision rather
/// than a judgement call: a backend whose checks were skipped is patched and is
/// not proven, and the installer does not go on top of it.
fn desktop_half_allowed(backend: &Step) -> bool {
    backend.state == "ok"
}

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

    /// A half that is under way right now. Used by [`step_starting`] and by the
    /// installer hook, where the line is the last one the card will get.
    fn running(step: &str, detail: impl Into<String>) -> Step {
        Step {
            state: "running".to_string(),
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
    ///
    /// **On Windows a successful desktop half never reaches this struct.** The
    /// installer ends the process (see this module's docs), so `update_both`
    /// returns only when the desktop half did NOT hand off - a failed download,
    /// a refused signature - or on a platform without that exit. The successful
    /// both-halves ending is the one the NEXT launch reconciles from disk
    /// ([`reconcile_pending_at_startup`]), never a value this process invents.
    pub updated_both: bool,
    /// Whether the app or the backend was stopped and wants starting again.
    pub restart_needed: bool,
}

/// The rule above, as a function rather than a comment.
pub fn both_updated(steps: &[Step]) -> bool {
    !steps.is_empty() && steps.iter().all(|s| s.state == "ok")
}

/// **The order, in one place: backend first, the executable second, and the
/// executable not at all unless the backend step proved itself.**
///
/// The desktop half has its own fixed order after that, and it is held by the
/// types rather than by this comment: the package is downloaded and its
/// signature checked (`verify_desktop_package`), the pending-install record is
/// written atomically and read back (`write_desktop_record`), the backend is
/// stopped and waited for (`stop_backend_for_installer`, at most three seconds),
/// and only then is the installer called (`install_now`, which takes the value
/// those three steps produce). See [`DESKTOP_HALF`].
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
/// Never automatic: this is a `#[tauri::command]` reachable from the Settings
/// button and, since 2026-10-26, from `run_approved_update` after an answered
/// `desktop_update` card - never from a page, a timer or a setting that turns it
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
    // Which source each half is coming from. Read and said, never enforced: an
    // older program folder still patches the backend, and this sentence is what
    // stops "both halves" from meaning only "both ran".
    let backend_commit = crate::backend_update::repo_commit(here.repo.as_deref());
    let halves = crate::backend_update::halves_line(
        crate::backend_update::app_commit().as_deref(),
        backend_commit.as_deref(),
    );
    let mut steps: Vec<Step> = Vec::new();

    // ---- 1. the backend ------------------------------------------------
    let opening = format!(
        "Patching the backend folder at the {mode_label} pace ({workers} check(s) at a \
         time). This can take several minutes - it applies every patch and then runs the \
         test suites. {halves}"
    );
    announce_step(&app, &step_starting(STEP_BACKEND, Some(&opening)));
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
    // What the backend half did rides into the desktop half's record, so the
    // next launch can say whether BOTH finished. Built before the step is moved
    // into the list.
    let backend_half = BackendHalf {
        state: backend_step.state.clone(),
        detail: backend_step.detail.clone(),
    };
    announce_step(&app, &backend_step);
    let backend_proved = desktop_half_allowed(&backend_step);
    let backend_stopped = backend.stopped;
    let backend_failed = backend_step.state == "failed";
    steps.push(backend_step);

    if !backend_proved {
        // STOP. The desktop half is not attempted - not for a backend that
        // failed, and not for one that patched without proving its own checks
        // either (an unproven half is not a pass here). The card is told so in
        // as many words rather than being left to infer it from a green line
        // that is not there.
        let skipped = if backend_failed {
            Step::skipped(STEP_DESKTOP, DESKTOP_SKIPPED_DETAIL)
        } else {
            Step::skipped(STEP_DESKTOP, DESKTOP_UNPROVEN_DETAIL)
        };
        announce_step(&app, &skipped);
        steps.push(skipped);
        return Ok(BothOutcome {
            updated_both: both_updated(&steps),
            steps,
            // Only when this attempt actually stopped Jarvis. A refusal that
            // never got that far has nothing to start again.
            restart_needed: backend_stopped,
        });
    }

    // ---- 2. the executable: verify, record, stop, and install LAST ------
    //
    // The order is the fix, and it is held by the values `prepare_desktop_half`
    // produces: the package is verified, then the record is written atomically
    // and read back, then the backend is stopped (bounded), and only then can
    // `install_now` be called - it takes the `StoppedDesktop` value and there is
    // no other way to get one. See [`DESKTOP_HALF`].
    //
    // On Windows the install call does not come back: the crate launches the
    // installer and exits the process (see the module docs). Everything the
    // owner is told about this half is therefore written to disk first and said
    // by the NEXT launch. The `Ok` arm below is reached only when the installer
    // was not launched (or off Windows), and it says only what that arm can know.
    announce_step(&app, &step_starting(STEP_DESKTOP, None));
    let ready = match prepare_desktop_half(&app, Some(backend_half), backend_commit).await {
        Ok(ready) => ready,
        Err(err) => {
            // Refused before anything on this PC was replaced: say so, and say
            // that the backend half above is not undone by it.
            let failed = Step::failed(
                STEP_DESKTOP,
                format!(
                    "Jarvis Desktop was NOT installed: {err}. The backend half above is \
                     done; press Install on its own below to try this half again."
                ),
            );
            announce_step(&app, &failed);
            steps.push(failed);
            return Ok(BothOutcome {
                updated_both: both_updated(&steps),
                steps,
                // The refusal happens before the desktop half stops anything,
                // so Jarvis is off only if the backend half itself stopped it.
                restart_needed: backend_stopped,
            });
        }
    };
    let desktop_step = match install_now(&app, ready).await {
        Ok(target) => Step::ok(
            STEP_DESKTOP,
            format!("Jarvis Desktop {target} is installed. Restart Jarvis to run it."),
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
    announce_step(&app, &desktop_step);
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

/// The update a chat message asked for, after its ONE card was approved.
///
/// HOW IT IS REACHED, AND WHY THAT IS THE GATE. The backend's chat fast path
/// raises one approval card (`jarvis_quick.py`, action `desktop_update`,
/// PC-only and therefore Windows Hello) and downloads nothing. The owner's
/// Approve is sent by [`crate::commands::answer_approval`], which reads the
/// card it is answering from the queue it already holds and, only when that
/// card's action is the update one, calls this. So the path is:
///
///   chat message -> ONE card -> the owner's yes -> this function -> the
///   SAME `update_both` the Settings button uses.
///
/// Nothing here can be started by a timer, a startup path, a page, the model
/// or the backend on its own: no card, no call. That is what stops the desktop
/// updater being the one self-modification path outside the gate (the
/// self-improvement audit's finding S3).
///
/// It re-checks before it starts, because the card may have waited a while and
/// the published release can move: if there is nothing newer now, nothing is
/// changed and the chat says so. A failure anywhere is said in the chat and
/// never painted as done.
///
/// **The desktop half's ending is not said here on Windows.** That half ends
/// this process, so the chat gets what is about to happen before it happens,
/// and the next start says how it ended (see the module docs). The
/// `updated_both` arm below is reachable only off Windows.
pub async fn run_approved_update(app: AppHandle) {
    let status = look(&app).await;
    if let Some(err) = status.error.clone() {
        say_in_hud(
            &app,
            "failed",
            format!("The update was not started: {err} Nothing was changed."),
        );
        return;
    }
    if status.available.is_none() {
        say_in_hud(
            &app,
            "skipped",
            "There is no newer version to install now, so nothing was changed.",
        );
        return;
    }
    // Said BEFORE the run: the desktop half closes Jarvis when its installer
    // starts, so this is the last sentence the chat can be given about it in
    // this process. It promises no ending - that is the next start's job.
    say_in_hud(
        &app,
        "running",
        format!(
            "Starting the update: the backend half first, then Jarvis Desktop. \
             {INSTALL_CLOSES_AND_RESTARTS} The next start says whether both halves finished."
        ),
    );
    match update_both(app.clone(), "responsive".to_string()).await {
        Ok(outcome) if outcome.updated_both => {
            say_in_hud(
                &app,
                "ok",
                "Both halves are updated. Restarting Jarvis now.",
            );
            // Let the line reach the page before the process goes; the restart
            // is what the card promised, and the new executable only runs
            // after it (`restart_app`'s own comment says why this call is safe
            // from a background task).
            tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
            app.request_restart();
        }
        Ok(outcome) => {
            // Each half has already said its own words in the chat; this adds
            // the one sentence a half-updated machine must never lose.
            let not_done: Vec<&str> = outcome
                .steps
                .iter()
                .filter(|s| s.state != "ok")
                .map(|s| s.step.as_str())
                .collect();
            let needs_restart = if outcome.restart_needed {
                " Jarvis needs a restart before the backend is back; Settings, then \
                 Updates, has the Restart button."
            } else {
                ""
            };
            say_in_hud(
                &app,
                "failed",
                if not_done.is_empty() {
                    format!("Not everything updated. Nothing was restarted.{needs_restart}")
                } else {
                    format!(
                        "Not everything updated ({}). Nothing was restarted - the \
                         lines above say what each half did.{needs_restart}",
                        not_done.join(" and ")
                    )
                },
            );
        }
        Err(err) => say_in_hud(&app, "failed", err),
    }
}

/// The placeholder a step emits when it starts, so the card can say which half
/// is running rather than sitting silent for the minutes a patch run takes.
/// The backend half carries the chosen pace's own words (`opening`).
fn step_starting(step: &str, opening: Option<&str>) -> Step {
    if step == STEP_BACKEND {
        return Step::running(
            step,
            opening.map(str::to_string).unwrap_or_else(|| {
                "Patching the backend folder. This can take several minutes - it \
                 applies every patch and then runs the test suites."
                    .to_string()
            }),
        );
    }
    // The desktop half never returns on Windows (see the module docs): the
    // installer ends this process, and the next start says how it ended. The
    // card must not imply this line will be followed by a result in THIS run -
    // and it says what happens to the window BEFORE the download, because after
    // it there may be no window left to say it in.
    Step::running(
        step,
        format!(
            "Downloading and checking Jarvis Desktop before anything on this PC is changed. \
             {INSTALL_CLOSES_AND_RESTARTS} The next start says whether the desktop half \
             finished."
        ),
    )
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

/// What the app tells its own backend about this build, on every chat request
/// (`commands.rs` `chat_extras`, `hud_proxy.rs` `hud_chat`).
///
/// The update answers in `backend/jarvis_quick.py` need exactly two facts the
/// shell alone has: which version is running, and whether this build carries
/// an update key. A page cannot supply either - the HUD's chat payload keeps
/// only the fields the page sends, and this is added in Rust after it.
pub fn desktop_chat_facts(app: &AppHandle) -> serde_json::Value {
    chat_facts(&version(app), configured(app))
}

/// The shape [`desktop_chat_facts`] sends, kept pure so the test can read it.
pub fn chat_facts(version: &str, can_update: bool) -> serde_json::Value {
    serde_json::json!({ "version": version, "can_update": can_update })
}

/// Whether a pending approval row is the update card ("update Jarvis").
///
/// The action is the backend's own name for the card
/// (`jarvis_quick.UPDATE_ACTION`), never the page's words: this is what decides
/// whether an approval makes this shell run its updater.
pub fn is_update_card(item: &serde_json::Value) -> bool {
    item.get("action").and_then(|a| a.as_str()) == Some("desktop_update")
}

/// One line for the HUD's chat, pushed on the feed's `update` channel.
///
/// The HUD page is the backend's own and this shell does not fork it, so
/// progress is delivered the way every other shell message is (`lib.rs`
/// `push_to_hud`) and the bootstrap puts it in the page's log.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateWord {
    /// `running`, `ok`, `partial`, `failed`, `skipped`, or `word` for a plain
    /// sentence that is not a half's state.
    pub state: String,
    /// Plain words. Always says what happened, never "updated" about a half
    /// that was not.
    pub detail: String,
}

/// Says one line in the HUD's chat, when that window is open.
fn say_in_hud(app: &AppHandle, state: &str, detail: impl Into<String>) {
    crate::push_to_hud(
        app,
        "update",
        &UpdateWord {
            state: state.to_string(),
            detail: detail.into(),
        },
    );
}

/// One half's step, to every window (the Settings listener) and to the HUD's
/// chat (the owner may have started this from a chat message).
fn announce_step(app: &AppHandle, step: &Step) {
    let _ = app.emit(crate::events::UPDATE_STEP, step.clone());
    crate::push_to_hud(app, "update", step);
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
            // tray row it points at. It also says, BEFORE anyone presses that
            // button, that Jarvis closes while the install runs.
            commands::notify(
                &handle,
                "Jarvis Desktop update available",
                &format!("Version {version} is ready to install from Settings. {INSTALL_CLOSES_AND_RESTARTS}"),
            );
        }
        crate::tray::on_update_status(&handle, status.available.as_deref());
        let _ = handle.emit(crate::events::UPDATE_STATUS, status);
    });
}

#[cfg(test)]
mod tests {
    use super::{
        both_updated, chat_facts, claim_update_both, clear_pending, desktop_half_allowed,
        desktop_half_trace, ending_words, friendly, install_notice_for, is_update_card,
        mark_launched, read_pending, reconcile, same_version, step_starting, write_pending,
        BackendHalf, BeforeInstaller, DesktopEnding, DesktopHalf, PendingDesktopInstall, Status,
        Step, BEFORE_INSTALLER, DESKTOP_HALF, DESKTOP_SKIPPED_DETAIL, DESKTOP_UNPROVEN_DETAIL,
        INSTALL_CLOSES_AND_RESTARTS, PENDING_FILE, STEP_BACKEND, STEP_DESKTOP,
    };

    // ---- what the chat answers read (2026-10-26) --------------------------

    #[test]
    fn the_chat_facts_carry_the_running_version_and_whether_it_can_update() {
        let yes = chat_facts("0.2.320", true);
        assert_eq!(yes["version"], "0.2.320");
        assert_eq!(yes["can_update"], true);
        // A build with no update key says so rather than offering an install
        // nobody can do.
        assert_eq!(chat_facts("0.2.320", false)["can_update"], false);
    }

    /// The decision path: the approve command reads the answered card's action
    /// BEFORE the decision leaves, and only the update card starts an install.
    /// A source pin, because there is no `AppHandle` in `cargo test` and this
    /// is the one wiring a later edit could quietly move.
    #[test]
    fn only_an_approved_update_card_starts_an_install() {
        let src = include_str!("commands.rs");
        let at = src
            .find("async fn answer_approval(")
            .expect("commands.rs has no answer_approval");
        let body = &src[at..];
        let read = body
            .find("let start_update = approved && waiting_update(&app, id);")
            .expect("answer_approval no longer reads the answered card's action");
        let sent = body
            .find("let endpoint = if approved")
            .expect("answer_approval no longer sends an approve/deny");
        assert!(
            read < sent,
            "the card is read AFTER the decision is sent - it must be read first"
        );
        assert!(
            body.contains("crate::update::run_approved_update(handle).await"),
            "an approved update card no longer starts the updater"
        );
        // ...and the update is started only inside that `if`.
        let start = body
            .find("if start_update {")
            .expect("no start_update gate");
        let call = body
            .find("crate::update::run_approved_update(handle).await")
            .expect("no updater call");
        assert!(
            start < call,
            "the updater is called outside the start_update gate"
        );
        // A deny never starts it.
        assert!(body.contains("let start_update = approved &&"));
    }

    #[test]
    fn only_the_update_cards_action_counts() {
        // The action is the backend's own name for the card, never the words
        // on it: this is what decides whether an approval starts the updater.
        assert!(is_update_card(
            &serde_json::json!({"id": "abc", "action": "desktop_update"})
        ));
        assert!(!is_update_card(
            &serde_json::json!({"id": "abc", "action": "send_email"})
        ));
        assert!(!is_update_card(&serde_json::json!({"id": "abc"})));
        assert!(!is_update_card(&serde_json::json!({"action": 7})));
        assert!(!is_update_card(&serde_json::json!(null)));
    }

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

    // ---- the desktop half across the process that ends it ----------------
    //
    // The Windows installer path calls `std::process::exit(0)`, so the desktop
    // half cannot report its own ending. What CAN be tested without an
    // installer is the whole decision: what is written down, and what the next
    // launch is allowed to say about it.

    fn a_pending(
        target: &str,
        launched: bool,
        backend: Option<BackendHalf>,
    ) -> PendingDesktopInstall {
        PendingDesktopInstall {
            target_version: target.to_string(),
            from_version: "0.2.412".to_string(),
            started_at: 1_760_000_000,
            installer_launched: launched,
            app_commit: Some("111111111111".to_string()),
            backend_commit: Some("222222222222".to_string()),
            backend_step: backend,
        }
    }

    fn an_ok_backend_half() -> BackendHalf {
        BackendHalf {
            state: "ok".to_string(),
            detail: "The backend is patched and proven.".to_string(),
        }
    }

    #[test]
    fn the_next_launch_says_the_desktop_half_finished_only_when_that_version_runs() {
        let pending = a_pending("0.2.500", true, Some(an_ok_backend_half()));
        let ending = reconcile(Some(&pending), "0.2.500").expect("a record was there");
        assert_eq!(
            ending,
            DesktopEnding::Finished {
                from: "0.2.412".to_string(),
                target: "0.2.500".to_string(),
                backend: Some(an_ok_backend_half()),
            }
        );
        let said = ending_words(&ending, Some("333333333333"), Some("222222222222"));
        assert!(said.contains("is now 0.2.500"), "{said}");
        assert!(said.contains("was 0.2.412"), "{said}");
        // ONLY a finished desktop half plus a backend half that ended `ok`
        // (which already means proven) may say both are done.
        assert!(said.contains("both halves are done"), "{said}");
        // ...and the version comparison is part of the same sentence, from the
        // NEW app's commit, so "both halves" is never just "both ran".
        assert!(said.contains("they differ"), "{said}");
        assert!(said.contains("222222222222"), "{said}");
        assert!(said.contains("333333333333"), "{said}");
    }

    #[test]
    fn a_partial_backend_half_may_never_be_painted_as_both_done() {
        let partial = BackendHalf {
            state: "partial".to_string(),
            detail: "Patched, unproven.".to_string(),
        };
        let pending = a_pending("0.2.500", true, Some(partial));
        let ending = reconcile(Some(&pending), "0.2.500").expect("a record was there");
        let said = ending_words(&ending, Some("333333333333"), Some("222222222222"));
        assert!(!said.contains("both halves are done"), "{said}");
        assert!(said.contains("not proven"), "{said}");
        assert!(
            said.contains("only the desktop half finished cleanly"),
            "{said}"
        );
        // The desktop half did finish, so it is still said to have.
        assert!(said.contains("is now 0.2.500"), "{said}");

        // A lone Install (no backend half at all) can never say both either.
        let lone = a_pending("0.2.500", true, None);
        let ending = reconcile(Some(&lone), "0.2.500").expect("a record was there");
        let said = ending_words(&ending, None, None);
        assert!(!said.contains("both halves are done"), "{said}");
        assert!(said.contains("No backend update ran with it"), "{said}");
        assert!(said.contains("cannot be compared"), "{said}");
    }

    #[test]
    fn a_record_that_never_reached_the_installer_is_not_reported_as_installed() {
        // The download failed, or the owner quit during it: the hook never ran,
        // so the installer never started. The old version is still running.
        let pending = a_pending("0.2.500", false, Some(an_ok_backend_half()));
        let ending = reconcile(Some(&pending), "0.2.412").expect("a record was there");
        assert!(matches!(ending, DesktopEnding::NotLaunched { .. }));
        let said = ending_words(&ending, Some("111111111111"), Some("222222222222"));
        assert!(said.contains("installer never ran"), "{said}");
        assert!(said.contains("still 0.2.412"), "{said}");
        assert!(said.contains("Press Install"), "{said}");
        // The backend half DID finish before the desktop half was attempted.
        assert!(
            said.contains("The backend half had already finished."),
            "{said}"
        );
        assert!(!said.contains("is now 0.2.500"), "{said}");
    }

    #[test]
    fn an_installer_that_left_the_old_version_running_is_not_reported_as_done() {
        let pending = a_pending("0.2.500", true, Some(an_ok_backend_half()));
        let ending = reconcile(Some(&pending), "0.2.412").expect("a record was there");
        assert_eq!(
            ending,
            DesktopEnding::NotInstalled {
                from: "0.2.412".to_string(),
                target: "0.2.500".to_string(),
                running: "0.2.412".to_string(),
                backend: Some(an_ok_backend_half()),
            }
        );
        let said = ending_words(&ending, Some("111111111111"), Some("222222222222"));
        assert!(said.contains("has not taken effect"), "{said}");
        assert!(said.contains("cancelled"), "{said}");
        assert!(!said.contains("is now 0.2.500"), "{said}");
    }

    #[test]
    fn a_third_version_is_never_claimed_either_way() {
        let pending = a_pending("0.2.500", true, None);
        let ending = reconcile(Some(&pending), "0.2.501").expect("a record was there");
        assert!(matches!(ending, DesktopEnding::OtherVersion { .. }));
        let said = ending_words(&ending, Some("111111111111"), Some("222222222222"));
        assert!(said.contains("cannot say which version"), "{said}");
        assert!(!said.contains("is now 0.2.500"), "{said}");
        assert!(!said.contains("both halves"), "{said}");
    }

    #[test]
    fn no_record_means_nothing_to_say() {
        assert_eq!(reconcile(None, "0.2.412"), None);
    }

    #[test]
    fn a_version_with_a_leading_v_is_the_same_release() {
        // The manifest and `package_info()` are both semver; the only slips a
        // person would forgive are case and a leading `v`.
        assert!(same_version("0.2.500", "0.2.500"));
        assert!(same_version("v0.2.500", "0.2.500"));
        assert!(same_version(" 0.2.500\n", "V0.2.500"));
        assert!(!same_version("0.2.500", "0.2.501"));
        assert!(!same_version("0.2.500", "0.2.5001"));
        assert!(!same_version("", "0.2.500"));
    }

    /// The record has to survive the process, so a write/read round trip on the
    /// real serializer is the test - not a hand-typed JSON fixture that could
    /// drift from the struct.
    #[test]
    fn the_record_round_trips_through_the_disk() {
        let path = std::env::temp_dir().join(format!(
            "jarvis-pending-update-test-{}-{}.json",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|since| since.as_nanos())
                .unwrap_or(0)
        ));
        let _ = std::fs::remove_file(&path);
        assert!(
            read_pending(&path).is_none(),
            "a missing file read as a record"
        );
        let pending = a_pending("0.2.500", false, Some(an_ok_backend_half()));
        write_pending(&path, &pending).expect("the record could not be written");
        assert_eq!(read_pending(&path), Some(pending));
        // Marking it launched is a read-modify-write, and the flag must stick.
        mark_launched(&path);
        let read = read_pending(&path).expect("the record disappeared after marking it");
        assert!(read.installer_launched, "the launched mark was not written");
        // The update's own identity is unchanged by marking.
        assert_eq!(read.target_version, "0.2.500");
        assert_eq!(read.from_version, "0.2.412");
        clear_pending(&path);
        assert!(read_pending(&path).is_none(), "the record was not cleared");
        // Junk reads as "no record" rather than as a guess.
        std::fs::write(&path, "{ not json").expect("the test could not write junk");
        assert!(read_pending(&path).is_none());
        let _ = std::fs::remove_file(&path);
    }

    /// The order inside the hook is the fix for the orphaned backend: stop it
    /// FIRST, and only then write "launched". If this array is swapped, a
    /// process that dies during the stop would leave a record claiming an
    /// installer that never ran.
    #[test]
    fn the_backend_is_stopped_before_the_record_says_the_installer_is_launched() {
        assert_eq!(
            BEFORE_INSTALLER,
            [BeforeInstaller::StopBackend, BeforeInstaller::MarkLaunched]
        );
        // ...and the hook really walks that array, rather than keeping a second
        // copy of the order in its body.
        let src = include_str!("update.rs");
        let body = &src[src
            .find("fn before_installer_runs(")
            .expect("update.rs has no before_installer_runs")..];
        assert!(
            body.contains("for step in BEFORE_INSTALLER"),
            "the hook no longer follows BEFORE_INSTALLER"
        );
    }

    // ---- the desktop half's order (corrections round, 2026-10-27) ---------
    //
    // The design: (a) the backend half proves itself, (b) the desktop package
    // is downloaded and its signature checked, (c) the record is written
    // atomically and read back, (d) the backend is stopped and waited for, (e)
    // the installer is called LAST. These hold the order; the types in
    // `prepare_desktop_half` make it impossible to build differently.

    /// The order, in one place, and the code really walking it: the prepare
    /// half verifies, records and stops - in that order - and never calls the
    /// installer; `update_both` hands the prepared value to the installer last.
    #[test]
    fn the_desktop_half_is_verified_recorded_stopped_then_installed() {
        assert_eq!(
            DESKTOP_HALF,
            [
                DesktopHalf::VerifyPackage,
                DesktopHalf::WriteRecord,
                DesktopHalf::StopBackend,
                DesktopHalf::Install,
            ]
        );
        // ...and it is the order the log of a real run names, from that array.
        assert_eq!(
            desktop_half_trace(),
            "check the package -> write the record -> stop the backend -> install"
        );
        let src = include_str!("update.rs");

        // (b), (c), (d) in that order, and no install among them.
        let prepare = &src[src
            .find("async fn prepare_desktop_half(")
            .expect("update.rs has no prepare_desktop_half")..];
        let prepare = &prepare[..prepare.find("\n}\n").expect("it has no end")];
        let verify = prepare
            .find("verify_desktop_package(")
            .expect("the package is never verified");
        let record = prepare
            .find("write_desktop_record(")
            .expect("the record is never written");
        let stop = prepare
            .find("stop_backend_for_installer(")
            .expect("the backend is never stopped for the installer");
        assert!(
            verify < record,
            "the record is written before the package is verified"
        );
        assert!(
            record < stop,
            "the backend is stopped before the record is written - a process that \
             dies during the stop would leave no record at all"
        );
        assert!(
            !prepare.contains("install_now("),
            "the install is called from the prepare half, so it can happen before the stop"
        );

        // (e) is last, and it is last because it takes the value (d) produced:
        // there is no other way to obtain one. The slice stops at the section
        // that follows, so the tests further down cannot make this pass (or
        // fail) by naming the same calls.
        let install_fn = &src[src
            .find("async fn install_now(")
            .expect("update.rs has no install_now")..];
        let install_fn = &install_fn[..install_fn
            .find("\n// ---------------------------------------------------------------------------\n// The desktop half across the process that ends it")
            .expect("install_now has no end")];
        assert!(
            install_fn.contains("ready: StoppedDesktop"),
            "the install step no longer requires the stopped value"
        );
        assert!(
            install_fn.contains("update.install(&bytes)"),
            "the install step no longer installs the bytes step (b) verified"
        );
        assert!(
            !install_fn.contains(".download("),
            "the install step downloads, so the package is not verified before it"
        );
        assert!(
            !install_fn.contains(".on_before_exit(") && !install_fn.contains("write_pending("),
            "the hook or the record moved into the last step"
        );

        let both = &src[src
            .find("pub async fn update_both")
            .expect("update.rs has no update_both")..];
        let prepared = both
            .find("prepare_desktop_half(&app")
            .expect("update_both prepares no desktop half");
        let installed = both
            .find("install_now(&app")
            .expect("update_both never installs");
        assert!(
            prepared < installed,
            "update_both installs before it verifies, records and stops"
        );
    }

    /// A backend half that patched but could not prove its checks is NOT a pass,
    /// so the desktop half is not started on top of it.
    #[test]
    fn a_backend_half_that_did_not_prove_itself_stops_the_desktop_half() {
        assert!(desktop_half_allowed(&Step::ok(
            STEP_BACKEND,
            "patched and proven"
        )));
        for unproven in [
            Step::partial(STEP_BACKEND, "patched, checks skipped"),
            Step::failed(STEP_BACKEND, "did not finish"),
            Step::skipped(STEP_BACKEND, "not attempted"),
            Step::running(STEP_BACKEND, "under way"),
        ] {
            assert!(
                !desktop_half_allowed(&unproven),
                "the desktop half was allowed after a backend that ended {}",
                unproven.state
            );
        }
        // The two refusals are two sentences, because "did not finish" is false
        // about a backend that did patch. Neither may read as an install.
        assert!(
            DESKTOP_SKIPPED_DETAIL.contains("did not finish"),
            "{DESKTOP_SKIPPED_DETAIL}"
        );
        assert!(
            DESKTOP_UNPROVEN_DETAIL.contains("could not run"),
            "{DESKTOP_UNPROVEN_DETAIL}"
        );
        for words in [DESKTOP_SKIPPED_DETAIL, DESKTOP_UNPROVEN_DETAIL] {
            assert!(words.contains("Not installed"), "{words}");
            assert!(!words.contains("is installed"), "{words}");
        }
    }

    /// The record names the backend step and the target version, is replaced by
    /// a rename rather than truncated in place, and leaves no temporary file.
    #[test]
    fn the_record_is_written_atomically_and_names_the_backend_step() {
        let dir = std::env::temp_dir().join(format!(
            "jarvis-pending-atomic-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|since| since.as_nanos())
                .unwrap_or(0)
        ));
        let _ = std::fs::remove_dir_all(&dir);
        // The folder is created by the write when it is not there: the Jarvis
        // data folder may not exist on a fresh PC, and that must not refuse an
        // update the owner asked for.
        let path = dir.join(PENDING_FILE);
        let first = a_pending("0.2.500", false, None);
        write_pending(&path, &first).expect("the first write");
        assert_eq!(read_pending(&path), Some(first));
        // A second write replaces it whole.
        let second = a_pending("0.2.501", true, Some(an_ok_backend_half()));
        write_pending(&path, &second).expect("the replace");
        assert_eq!(read_pending(&path), Some(second));
        // No temporary file is left behind.
        let leftovers: Vec<String> = std::fs::read_dir(&dir)
            .expect("the record's folder")
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.file_name().to_string_lossy().to_string())
            .filter(|name| name.ends_with(".tmp"))
            .collect();
        assert!(leftovers.is_empty(), "temporary files left: {leftovers:?}");
        // The file is a complete JSON object that names what step (c) must
        // name: the backend step and the target version.
        let text = std::fs::read_to_string(&path).expect("the record reads");
        let json: serde_json::Value =
            serde_json::from_str(&text).expect("the record is not complete JSON");
        assert_eq!(json["targetVersion"], "0.2.501");
        assert_eq!(json["fromVersion"], "0.2.412");
        assert_eq!(json["backendStep"]["state"], "ok");
        assert_eq!(json["installerLaunched"], true);
        // ...and the replace is one rename in the same folder, flushed first.
        // A source pin: a single-threaded test cannot observe the atomicity
        // itself, only the mechanism that gives it.
        let src = include_str!("update.rs");
        let body = &src[src.find("fn write_pending(").expect("no write_pending")..];
        let body = &body[..body.find("\n}\n").expect("it has no end")];
        assert!(
            body.contains("std::fs::rename"),
            "the record is not replaced by a rename"
        );
        assert!(
            body.contains("sync_all"),
            "the record is not flushed before the rename"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// A record written by an older build - `target` / `from` / `backend` -
    /// still reads, so this round extends the record rather than replacing it.
    #[test]
    fn an_older_record_still_reads() {
        let old = serde_json::json!({
            "target": "0.2.500",
            "from": "0.2.412",
            "startedAt": 1_760_000_000,
            "installerLaunched": true,
            "appCommit": "111111111111",
            "backendCommit": "222222222222",
            "backend": { "state": "ok", "detail": "done" }
        });
        let read: PendingDesktopInstall =
            serde_json::from_value(old).expect("an older record no longer reads");
        assert_eq!(read.target_version, "0.2.500");
        assert_eq!(read.from_version, "0.2.412");
        assert_eq!(
            read.backend_step.map(|half| half.state),
            Some("ok".to_string())
        );
        // And the record is still written under the name the design fixes, in
        // the folder Jarvis keeps its own data in.
        assert_eq!(PENDING_FILE, "pending-desktop-update.json");
    }

    /// The sentence the controls must carry BEFORE the press, and the places it
    /// reaches without a page being edited: the data the card reads, the
    /// notification, the desktop half's first line and the chat's opening line.
    #[test]
    fn the_install_controls_say_the_app_closes_before_they_are_pressed() {
        // No Install control, no sentence.
        assert_eq!(install_notice_for(None), None);
        let notice = install_notice_for(Some("0.2.500")).expect("a notice");
        assert_eq!(notice, INSTALL_CLOSES_AND_RESTARTS);
        for expected in ["closes", "starts again", "Save anything"] {
            assert!(
                notice.contains(expected),
                "`{expected}` missing from the pre-click sentence: {notice}"
            );
        }
        // It rides the same struct the Updates card already reads, so a card can
        // paint it before the press without this module changing a page.
        let status = Status {
            available: Some("0.2.500".to_string()),
            install_notice: install_notice_for(Some("0.2.500")),
            ..Status::default()
        };
        let json = serde_json::to_value(&status).expect("Status serialises");
        assert_eq!(json["install_notice"], INSTALL_CLOSES_AND_RESTARTS);

        // The desktop half's own running line says it, before the download.
        let step = step_starting(STEP_DESKTOP, None);
        assert!(step.detail.contains("closes"), "{}", step.detail);
        assert!(step.detail.contains("starts again"), "{}", step.detail);
        assert!(step.detail.contains("Downloading"), "{}", step.detail);

        // ...and it is used in at least four places in this module: the
        // constant itself, the check that offers it, the startup notification,
        // the chat's opening line and the desktop step's line.
        let src = include_str!("update.rs");
        let production = &src[..src.find("#[cfg(test)]").expect("no test module")];
        assert!(
            production.matches("INSTALL_CLOSES_AND_RESTARTS").count() >= 5,
            "the pre-click sentence is no longer said everywhere it must be"
        );
    }

    /// The hook is registered before the download (a hook added later would
    /// never run), and the record is written before the install call - the two
    /// hand-over invariants, now held by the prepare half rather than by
    /// `install_now`.
    #[test]
    fn the_hook_and_the_record_come_before_the_installer_can_run() {
        let src = include_str!("update.rs");
        let verify = &src[src
            .find("async fn verify_desktop_package(")
            .expect("update.rs has no verify_desktop_package")..];
        let verify = &verify[..verify.find("\n}\n").expect("it has no end")];
        let hook = verify
            .find(".on_before_exit(")
            .expect("the updater's on_before_exit hook is no longer registered");
        let download = verify
            .find(".download(")
            .expect("the package is no longer downloaded here");
        assert!(
            hook < download,
            "the hook is registered after the download - the crate would never call it"
        );
        let record = &src[src
            .find("fn write_desktop_record(")
            .expect("update.rs has no write_desktop_record")..];
        let record = &record[..record.find("\n}\n").expect("it has no end")];
        assert!(
            record.contains("write_pending(record, &pending)"),
            "the record is no longer written"
        );
        assert!(
            record.contains("read_pending(record) != Some(pending)"),
            "the record is no longer read back - a record the next launch cannot \
             read is the same as no record"
        );
        assert!(
            !record.contains("install("),
            "the record step installs something"
        );
    }

    /// The startup reconcile is only worth anything if something calls it.
    /// `lib.rs` owns startup, and a call that is deleted there is otherwise
    /// silent.
    #[test]
    fn the_next_launch_really_reconciles_the_record() {
        let src = include_str!("lib.rs");
        assert!(
            src.contains("update::reconcile_pending_at_startup(&handle);"),
            "lib.rs no longer reconciles the desktop update record at startup"
        );
    }
}
