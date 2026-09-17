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
//! and never will be, and `tauri.conf.json` carries the matching public key.
//! The updater verifies the signature before it hands the bytes to the
//! installer, so a release replaced at the CDN, a hijacked DNS answer or a
//! proxy rewriting the response all fail closed. A build with no public key
//! configured cannot update at all, which is the correct behaviour rather than
//! a degraded one — see `available()`.

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
    if !configured(&app) {
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
    use super::friendly;

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
}
