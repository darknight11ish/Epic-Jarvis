//! Checking GitHub for a newer Jarvis Desktop, and never installing one on its
//! own.
//!
//! ## Four states, and no invented "up to date"
//!
//! `Status::state` is one of `unknown`, `cannot_check`, `up_to_date` and
//! `update_available`, computed by `state_of` from what a check actually
//! recorded (Task-50, Wave 12). Before that, a fresh launch sent no version,
//! no error and no time, and Settings drew that as "the newest published" - a
//! claim no check had made. The rule now: `up_to_date` is reachable only after
//! a check really asked the endpoint and got an answer; a failed check is
//! `cannot_check`, carrying its reason; a build with no update key is
//! `cannot_check` and never carries a time (it never asked); and no check yet
//! is `unknown`. `Status::checked_at` is the owner's own wall clock at the
//! moment the check finished ("YYYY-MM-DD HH:MM") - the tray row and the
//! Settings card both print that same field, so the time is the check's, not
//! the screen's.
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
//! the two halves in one deliberate order; it runs from the Settings button,
//! since 2026-10-26 from `run_approved_update` after an answered
//! `desktop_update` card, and since 2026-11-04 from the tray's own update row
//! (`install_from_tray`) - never from a page, a timer or a setting.
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
use crate::update_window;

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
    /// The four-state truth, computed by [`finish`] from the fields above and
    /// never typed in by a screen: `"unknown"` (no check has run),
    /// `"cannot_check"` (the last check could not answer, or this build cannot
    /// check at all), `"up_to_date"` (a check ran and found nothing newer) or
    /// `"update_available"` (`available` is `Some`).
    ///
    /// It exists because a fresh launch used to send `available: None,
    /// error: None` and Settings drew that as "the newest published" - a claim
    /// no check had made. The tray reads this same field, so the menu row and
    /// the card cannot hold different views of the same fact.
    #[serde(default)]
    pub state: String,
    /// When the last check COMPLETED - success or failure - as the owner's own
    /// wall clock, `"YYYY-MM-DD HH:MM"`, read from the OS at that moment.
    ///
    /// `None` means no check has run since this process started, and is the
    /// only honest answer before one has: a time beside a state no check
    /// produced would be a made-up time. A build with no update key never
    /// checks, so it never carries one either.
    #[serde(default)]
    pub checked_at: Option<String>,
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
    finish(Status {
        current: version(app),
        supported: configured(app),
        check_on_start: check_on_start(app),
        ..Status::default()
    })
}

/// The owner's wall clock at the moment it is called, `"YYYY-MM-DD HH:MM"`.
///
/// Read from the OS, not computed from an epoch: this is the time the owner
/// read off their own clock, and a UTC figure would be an hour or more out for
/// most of the year on this PC. Off Windows there is no local-time call here,
/// so the figure is UTC - the updater's real target is Windows, and the one
/// place this is drawn (Settings, the tray) is a Windows surface.
fn local_stamp() -> String {
    match local_clock() {
        Some((y, m, d, h, min)) => format!("{y:04}-{m:02}-{d:02} {h:02}:{min:02}"),
        // A clock that cannot be read must not become a made-up time. The
        // empty string says "no time to show" to every caller, and the state
        // still says what the check found.
        None => String::new(),
    }
}

/// The OS's local date, `"YYYY-MM-DD"`, for deciding whether a checked stamp
/// is today's. `None` when the clock cannot be read - the tray then prints the
/// full stamp instead of guessing that an old check happened today.
pub(crate) fn local_day() -> Option<String> {
    local_clock().map(|(y, m, d, _, _)| format!("{y:04}-{m:02}-{d:02}"))
}

#[cfg(windows)]
fn local_clock() -> Option<(u16, u16, u16, u16, u16)> {
    use windows_sys::Win32::Foundation::SYSTEMTIME;
    use windows_sys::Win32::System::SystemInformation::GetLocalTime;
    // SAFETY: `SYSTEMTIME` is a plain struct of `u16`s, so all-zero is a valid
    // value - which is the function's only requirement. `GetLocalTime` returns
    // nothing and cannot fail.
    let mut now: SYSTEMTIME = unsafe { std::mem::zeroed() };
    unsafe { GetLocalTime(&mut now) };
    if now.wYear == 0 {
        return None;
    }
    Some((now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute))
}

#[cfg(not(windows))]
fn local_clock() -> Option<(u16, u16, u16, u16, u16)> {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).ok()?.as_secs() as i64;
    let days = secs.div_euclid(86_400);
    let rem = secs.rem_euclid(86_400);
    // Civil-from-days (Howard Hinnant's algorithm), the standard conversion
    // from a Unix day count to a calendar date - no dependency needed for the
    // one line this file draws.
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    Some((
        y as u16,
        m as u16,
        d as u16,
        (rem / 3_600) as u16,
        ((rem % 3_600) / 60) as u16,
    ))
}

/// The four-state truth, computed in ONE place from what a check actually set.
///
/// Public to this crate so the tray and the tests read the same rule Settings
/// is sent: a second implementation in JavaScript or in `tray.rs` is how the
/// menu row and the card would end up disagreeing about the same fact.
///
/// The order is deliberate. An update that IS known wins over everything: it is
/// the one state the owner can act on. Then a failure, because "we could not
/// tell" must never be drawn as "nothing to do". Then a build that can never
/// check, which is a failure that keeps being true. Only a successful check
/// with nothing newer is `up_to_date`, and only a successful check carries a
/// time - there is no fifth "probably fine".
pub(crate) fn state_of(
    available: Option<&str>,
    error: Option<&str>,
    supported: bool,
    checked_at: Option<&str>,
) -> &'static str {
    if available.is_some() {
        return "update_available";
    }
    if error.is_some() || !supported {
        return "cannot_check";
    }
    // `Some` - even an unreadable clock's empty string - means a check really
    // finished. Only `None` (no check since launch) is `unknown`.
    if checked_at.is_some() {
        return "up_to_date";
    }
    "unknown"
}

/// [`state_of`] over a whole `Status`, so a caller cannot pass the fields in
/// the wrong order or forget one.
fn finish(mut status: Status) -> Status {
    status.state = state_of(
        status.available.as_deref(),
        status.error.as_deref(),
        status.supported,
        status.checked_at.as_deref(),
    )
    .to_string();
    status
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
        // NO checked_at here on purpose: this build never asked anything, so a
        // time would say a check happened that did not.
        return finish(status);
    }

    let updater = match app.updater_builder().timeout(CHECK_TIMEOUT).build() {
        Ok(updater) => updater,
        Err(err) => {
            // The check was attempted and failed before it left this PC; that
            // is a failure to report, and it is not a made-up "up to date".
            status.checked_at = Some(local_stamp());
            status.error = Some(format!("the updater could not start: {err}"));
            return finish(status);
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
    // Every ending that got this far really did ask the endpoint: that moment
    // is what "checked HH:MM" means, whichever way the answer went.
    status.checked_at = Some(local_stamp());
    finish(status)
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

/// The version a check has found and not installed, read from the cache the
/// Settings card reads.
///
/// **The tray's only source of "is there an update?"** (owner, 2026-11-03): one
/// read of [`UpdateState`], never a second network check. Two finders would
/// eventually disagree, and then the menu row and the Updates card would name
/// different versions. `None` means "no update is known" - which for the tray
/// means the row is not in the menu at all.
pub fn available_version(app: &AppHandle) -> Option<String> {
    app.state::<UpdateState>()
        .get()
        .and_then(|status| status.available)
}

/// The whole answer for the tray's own status row: the cache when a check has
/// answered, or the fresh-launch one before that.
///
/// `base()` is not a made-up status - it carries the running version, whether
/// this build can check at all, and `checked_at: None`, which `state_of` reads
/// as `unknown` (or `cannot_check` for a build with no update key). That is
/// exactly what the row should say at launch, and it is why this returns a
/// `Status` rather than an `Option` a caller might mistake for an answer.
pub(crate) fn last_status(app: &AppHandle) -> Status {
    app.state::<UpdateState>()
        .get()
        .unwrap_or_else(|| base(app))
}

/// Checks now, because someone pressed Check.
#[tauri::command]
pub async fn check_for_update(app: AppHandle) -> Status {
    let status = look(&app).await;
    app.state::<UpdateState>().put(status.clone());
    crate::tray::on_update_status(&app, &status);
    say_available_in_hud(&app, status.available.as_deref());
    let _ = app.emit(crate::events::UPDATE_STATUS, status.clone());
    status
}

/// Says in the HUD's own chat log that a newer version exists - and that the
/// one Update button installs BOTH halves.
///
/// The owner's requirement of 2026-11-03: *"when i click update on the jarvis
/// hud i want it linked to the back end so both are always updated at the same
/// time"*. This line is where the HUD is told that, in the same sentence that
/// says an update exists - so the door the owner finds is the both-halves one
/// (Settings, then Updates, whose Install button runs `update_both`), not the
/// desktop-only control this build used to offer. It carries no click and
/// starts nothing: the click is still the owner's, on the card.
fn say_available_in_hud(app: &AppHandle, available: Option<&str>) {
    let Some(version) = available else {
        return;
    };
    crate::push_to_hud(
        app,
        "update",
        &UpdateWord {
            state: "available".to_string(),
            detail: format!(
                "Jarvis Desktop {version} is available. One Update press installs BOTH \
                 halves - the backend first, then the desktop app. Settings, then Updates, \
                 has the button."
            ),
        },
    );
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

/// Downloads, verifies and installs — and refuses outright unless the backend
/// half can run.
///
/// Separate from `check_for_update` rather than a flag on it, so that no future
/// edit can make checking install something by passing `true`.
///
/// **BOTH OR NEITHER (the owner's standing rule, stated 2026-11-20 21:12 PT:
/// *"when I update Jarvis the HUD and backend should always update at the same
/// time"*).** The Windows installer path cannot be hooked, and that is the one
/// desktop-only update nobody can gate — which is why the next start finishes
/// the backend half automatically ([`finish_backend_if_desktop_ahead`]). But
/// this app's OWN action can be gated, and it is: before a single byte is
/// downloaded, `locate()`'s own `blocked` field says whether the backend half
/// can run, and when it cannot this returns the one plain line naming what is
/// missing and changes nothing. A half-Jarvis is not an update.
///
/// Since 2026-11-04 this is the fallback door only: the Settings Install press
/// and the tray's update row run [`update_both`], and there is no in-app path
/// left that reaches this command while the backend half is blocked.
#[tauri::command]
pub async fn install_update(app: AppHandle) -> Result<String, String> {
    let here = crate::backend_update::locate(&app);
    // The gate is a pure function so the rule is a test rather than a comment:
    // a desktop install is allowed only when `locate()` says the backend half
    // can run, and refused with the folder/thing that is missing when it says
    // otherwise.
    if let Err(why) = desktop_install_gate(here.blocked.as_deref()) {
        // Said out loud before anything else: the HUD's chat is the surface the
        // owner may be reading, and the log keeps the record. Never "updated".
        crate::logfile::log(&format!("[jarvis] {why}"));
        say_in_hud(&app, "failed", &why);
        return Err(why);
    }
    let backend_commit = crate::backend_update::repo_commit(here.repo.as_deref());
    // Said before anything is downloaded: on Windows this process ends when the
    // installer starts, so there is no second chance to say it.
    crate::logfile::log(&format!("[jarvis] {INSTALL_CLOSES_AND_RESTARTS}"));
    say_in_hud(&app, "running", INSTALL_CLOSES_AND_RESTARTS);
    let ready = prepare_desktop_half(&app, None, backend_commit).await?;
    install_now(&app, ready).await
}

/// The both-or-neither gate before a desktop install: `Ok(())` only when
/// `locate()` says the backend half can run, otherwise the ONE plain line the
/// owner is told, naming the folder or program that is missing.
///
/// Pure, and public to this crate, because this is the whole of rule 1: an
/// in-app update either moves both halves or installs nothing. Every caller
/// (`install_update` here; the Settings Install press and the tray row through
/// their own check) answers with `locate()`'s own `blocked` field, so no two
/// doors can disagree about whether the backend half can run.
pub fn desktop_install_gate(blocked: Option<&str>) -> Result<(), String> {
    match blocked.map(str::trim).filter(|why| !why.is_empty()) {
        None => Ok(()),
        Some(why) => Err(format!(
            "Jarvis Desktop was NOT installed. The update moves both halves, and the \
             backend half cannot run on this PC: {why}"
        )),
    }
}

/// Why the BACKEND half cannot run on this PC, in the words the Settings
/// Updates card shows - or `None` when it can.
///
/// It is [`crate::backend_update::locate`]'s `blocked` field, the same field
/// [`crate::backend_update::backend_update_status`] - the command that card
/// reads - is built from. Read here rather than invented, so the tray and the
/// Settings card cannot take different views of whether the backend half can
/// run.
fn backend_half_blocked(app: &AppHandle) -> Option<String> {
    crate::backend_update::locate(app).blocked
}

/// The tray's "Update Jarvis to <version>" row: the same both-halves update the
/// Settings Install press runs, reached from the context menu.
///
/// Not a second updater and not an automatic one. The row that fires it exists
/// only while [`available_version`] answers `Some` (`tray::update_row` is that
/// rule), and this function only runs because the owner pressed it.
///
/// The owner's requirement of 2026-11-03 was that ONE Update press keeps both
/// halves together, so the ordinary press runs [`update_both`] - the backend
/// first, then Jarvis Desktop. The old desktop-only fallback (install the
/// desktop alone where the backend half cannot run) is **gone** as of the
/// owner's standing rule of 2026-11-20 21:12 PT: *"when I update Jarvis the HUD
/// and backend should always update at the same time."* When the backend half
/// cannot run, this press installs nothing and says in one line which folder or
/// program is missing ([`desktop_install_gate`]); the app never calls a
/// half-update "updated".
///
/// The row is turned into "Updating Jarvis to <version>…" and disabled FIRST, so
/// a second press cannot start a second run. A failure re-reads the real state
/// with the same command the Settings Check button uses, so the row is rebuilt
/// from what is true now rather than left on "Updating…" for ever. On a
/// successful Windows install this function never returns: the installer ends
/// the process, and the next launch starts with no row because the new version
/// is the one running.
///
/// **App lock comes before any of that** (DEF-045): right-clicking the tray is
/// enough to reach this row, and it patches the LIVE backend, so with App lock
/// on and the owner away it asks Windows Hello exactly as the tray's window
/// rows do ([`crate::lock::require_unlocked`]) and starts nothing without a
/// confirmed answer. A declined check is said out loud, because a tray row that
/// does nothing reads as broken. With App lock off, or the owner still here,
/// the gate returns at once and every line below is unchanged.
pub async fn install_from_tray(app: AppHandle) {
    if let Err(why) = crate::lock::require_unlocked(&app).await {
        // Fixed words from the lock's own table, about Windows Hello and the
        // lock itself - never the owner's business - so it is safe to show
        // while locked, and it is what says whether to try again or to set
        // Windows Hello up. Said rather than swallowed: the press must not
        // look like a row that does nothing.
        crate::logfile::log(&format!("[jarvis] tray update held by the App lock: {why}"));
        commands::notify(
            &app,
            "Atlas Desktop update",
            &format!("The update was not started. {why}."),
        );
        return;
    }
    let Some(version) = available_version(&app) else {
        // A check cleared the availability between the right-click and the
        // click, so the row is already gone from the menu this same cache
        // feeds. Say so rather than doing nothing at all: the owner did press
        // something, and silence reads as a broken row.
        commands::notify(
            &app,
            "Atlas Desktop update",
            "There is no newer version to install now, so nothing was changed.",
        );
        return;
    };
    crate::tray::update_started(&app, &version);
    // ONE check decides which door this press takes, and it is the same one the
    // Settings Install press makes before it chooses between its own branches.
    match backend_half_blocked(&app) {
        // The ordinary press, and the one the owner asked for: both halves,
        // through the SAME runner Settings' Install press and an answered
        // `desktop_update` card use.
        None => update_both_from_tray(app, &version).await,
        // Both or neither: the blocked arm installs nothing and says exactly
        // which folder or program is missing, never "updated".
        Some(why) => refuse_tray_update(app, why).await,
    }
}

/// The ordinary tray press: both halves, through the one runner.
///
/// The tray has no card, so the toast before the run is where the owner is told
/// what is about to happen: the backend is patched first, then Jarvis Desktop
/// installs, and Jarvis closes and starts again - and it can take several
/// minutes. Nothing here starts by itself; it runs because the row was pressed.
async fn update_both_from_tray(app: AppHandle, version: &str) {
    commands::notify(
        &app,
        "Atlas update",
        &format!(
            "Updating both halves: the backend is patched first, then Jarvis Desktop \
             {version} installs. This can take several minutes. {INSTALL_CLOSES_AND_RESTARTS}"
        ),
    );
    let outcome = update_both(app.clone(), "responsive".to_string()).await;
    // The row must not sit on "Updating…" for ever, and it must not name a
    // version the endpoint no longer offers: re-read, and let `on_update_status`
    // rebuild it from the answer. Every ending that reaches this line needs that
    // - a desktop half that installed ends the process before it instead.
    let _ = check_for_update(app.clone()).await;
    match outcome {
        Ok(outcome) if outcome.updated_both => {
            commands::notify(
                &app,
                "Atlas updated",
                "Both halves are updated. Restart Jarvis to run the new version.",
            );
        }
        Ok(outcome) => {
            // A half that did not finish is not "updated", and the toast says
            // which one rather than a green sentence the tray cannot justify.
            // The Settings card says the rest when it is open; each half's own
            // line goes to the log here, because the tray has no card to show it.
            let not_done: Vec<&str> = outcome
                .steps
                .iter()
                .filter(|step| step.state != "ok")
                .map(|step| step.step.as_str())
                .collect();
            let needs_restart = if outcome.restart_needed {
                " Jarvis needs a restart before the backend is back; Settings, then \
                 Updates, has the Restart button."
            } else {
                ""
            };
            let plain = if not_done.is_empty() {
                format!("The update did not finish, so the two halves may differ.{needs_restart}")
            } else {
                format!(
                    "The update did not finish: {} did not. The two halves may differ \
                     until it is finished.{needs_restart}",
                    not_done.join(" and ")
                )
            };
            let detail: Vec<String> = outcome
                .steps
                .iter()
                .filter(|step| step.state != "ok")
                .map(|step| step.detail.clone())
                .collect();
            commands::notify_failed(
                &app,
                "Atlas update",
                &plain,
                &detail.join(" "),
                commands::Details::Log,
            );
        }
        Err(err) => commands::notify_failed(
            &app,
            "Atlas update",
            "The update was not started.",
            &err,
            commands::Details::Log,
        ),
    }
}

/// The tray press on a PC whose backend half cannot run: it installs NOTHING.
///
/// The owner's standing rule of 2026-11-20, and rule 1 of this feature: the
/// in-app update action moves both halves or none. The tray has no card to show
/// a long refusal, so the toast is the whole of what the owner is told - the ONE
/// plain line naming the folder or program that is missing, in the same words
/// the Settings Install press and [`install_update`] itself use. It is guarded
/// because that line can name a folder on this PC and a toast can be read from a
/// locked screen; it is never silent, because a row that does nothing reads as
/// broken.
async fn refuse_tray_update(app: AppHandle, why: String) {
    let words = desktop_install_gate(Some(&why))
        .expect_err("a blocked backend half is exactly what the gate refuses");
    crate::logfile::log(&format!("[jarvis] tray update: {words}"));
    commands::notify_guarded(&app, "Atlas Desktop update", &words, None);
    // The row was turned into "Updating…" before this arm ran, so it is rebuilt
    // from a real check rather than left that way for ever.
    let _ = check_for_update(app.clone()).await;
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
    repo: Option<&str>,
) -> String {
    // WHICH HALF IS AHEAD, asked once, from git (`is_ancestor`), never inferred
    // from the version numbers: they are CI run numbers, so two different trees
    // can both call themselves 0.2.502 - which is exactly what happened on the
    // owner's PC on 2026-11-24. `repo` is the folder the backend came from; with
    // no folder the answer is Unknown and the sentence says so.
    let app_in_backend = crate::backend_update::is_ancestor(repo, app_commit, backend_commit);
    let backend_in_app = crate::backend_update::is_ancestor(repo, backend_commit, app_commit);
    let class = crate::backend_update::classify_halves(
        app_commit,
        backend_commit,
        app_in_backend,
        backend_in_app,
    );
    let halves = crate::backend_update::halves_sentence(class, app_commit, backend_commit);
    // "Both halves are done" may only be said of ONE RELEASE - both halves on
    // the same commit. Before 2026-11-24 this clause came from the backend
    // half's own state alone, so a card could read "so both halves are done"
    // and then, in the next clause, "they differ".
    let done = if class == crate::backend_update::Halves::Same {
        " Both halves are done."
    } else {
        ""
    };
    match ending {
        DesktopEnding::Finished {
            from,
            target,
            backend,
            ..
        } => format!(
            "Jarvis Desktop is now {target}; it was {from} when the Windows installer \
             started.{}{done} {halves}",
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
///
/// This function may say what the BACKEND HALF did; it may never say the two
/// halves are one release, because it does not know the commits. That claim
/// lives in `ending_words`, which asks git - until 2026-11-24 this arm ended
/// "so both halves are done", and the card then said "they differ" in the very
/// next clause, on a machine whose backend was one commit AHEAD (benign).
fn backend_finished_sentence(backend: &Option<BackendHalf>) -> &'static str {
    match backend.as_ref().map(|half| half.state.as_str()) {
        Some("ok") => " The backend half had already finished before the installer ran.",
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
        DesktopEnding::Finished { .. } => "Atlas Desktop is updated",
        DesktopEnding::NotLaunched { .. } | DesktopEnding::NotInstalled { .. } => {
            "Atlas Desktop was not updated"
        }
        DesktopEnding::OtherVersion { .. } => "Atlas Desktop update: check what happened",
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
    // The build the desktop ran BEFORE this installer: the automatic finish and
    // the tool-defaults step need it to tell what THIS release newly ships. Only
    // a finished install proves the replacement happened; every other ending
    // leaves the old build running, so the caller falls back to this binary's
    // own commit (the same one).
    if matches!(ending, DesktopEnding::Finished { .. }) {
        remember_previous_desktop_build(pending.app_commit.as_deref());
    }
    let words = ending_words(
        &ending,
        crate::backend_update::app_commit().as_deref(),
        pending.backend_commit.as_deref(),
        // No repository is at hand on this startup path - the pending record
        // carries the backend's commit but not the folder it came from. So git
        // is not asked, and a difference is reported as "which one is newer
        // could not be read" rather than guessed at. The interactive update
        // path does have the folder and classifies it exactly.
        None,
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

/// `true` while a BACKEND half is being run on this PC by this app: the
/// automatic finish at start-up, or an "Update everything" press.
///
/// WHY IT IS A SHARED FLAG AND NOT A PAGE'S OWN BIT. The owner's report of
/// 2026-11-21: the Updates card read the versions in the middle of a run and
/// said the backend was still 0.2.491, while the run had already written
/// 0.2.492 - a card opened during a run was reading a moment that was about to
/// be replaced. `backend_self::read` carries this flag out with the versions, so
/// the card can say "Finishing the backend half now" instead of drawing a
/// mismatch that is being fixed at that instant. It is the backend HALF that is
/// marked, not the whole `update_both` run: the desktop half installs and ends
/// this process, and nothing can read a card through that.
static BACKEND_HALF_RUNNING: AtomicBool = AtomicBool::new(false);

/// Is a backend half running right now? Read by `backend_self::read`.
pub fn backend_half_running() -> bool {
    BACKEND_HALF_RUNNING.load(Ordering::SeqCst)
}

/// Held for one backend-half run; dropping it clears the flag.
struct BackendHalfRunningGuard;

impl Drop for BackendHalfRunningGuard {
    fn drop(&mut self) {
        BACKEND_HALF_RUNNING.store(false, Ordering::SeqCst);
    }
}

/// Mark a backend half as running for as long as the returned guard lives.
fn claim_backend_half_running() -> BackendHalfRunningGuard {
    BACKEND_HALF_RUNNING.store(true, Ordering::SeqCst);
    BackendHalfRunningGuard
}

///
/// Never automatic: this is a `#[tauri::command]` reachable from the Settings
/// button, since 2026-10-26 from `run_approved_update` after an answered
/// `desktop_update` card, and since 2026-11-04 from the tray's update row - and
/// only where the backend half can run there, because where it cannot the tray
/// falls back to the desktop-only [`install_update`] and says the BACKEND was
/// NOT updated. Never from a page, a timer or a setting that turns it into a
/// background job.
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
    // stops "both halves" from meaning only "both ran". `here.repo` is the folder
    // the backend half will be installed from, so git can be asked which of the
    // two commits contains the other - the difference between "the backend is
    // newer, which is fine" and "the backend is older, which is the problem".
    let backend_commit = crate::backend_update::repo_commit(here.repo.as_deref());
    let halves = crate::backend_update::halves_line_in(
        here.repo.as_deref(),
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
    // ONE WINDOW, AND IT OPENS BEFORE THE RUN DOES (DEF-098). It is opened from
    // HERE, not from the Settings page or the tray, so every door that reaches
    // an update - the Settings button, the tray row and an approved
    // `desktop_update` card - gets the same window and no page can open one on
    // its own. `open` is best-effort and returns nothing: a machine that cannot
    // draw a window must still update, and there is no error here that a later
    // edit could turn into "the update did not start".
    update_window::open(&app, &opening);
    announce_step(&app, &step_starting(STEP_BACKEND, Some(&opening)));
    // The build the desktop is running NOW - the release before this action.
    // The backend tool needs it to tell the tools THIS release newly ships ON
    // from one the owner turned off on purpose (never re-enabled), and to hand
    // only the former to the additive config step after the run proves itself.
    let previous_release = crate::backend_update::app_commit();
    // Marked only around the BACKEND run: a read taken while it works says
    // "Finishing the backend half now" instead of drawing a mismatch that is
    // being fixed at that instant (owner's 2026-11-21 report). The mark is
    // dropped before the desktop half, which is not a backend run.
    let backend = {
        let _backend_half = claim_backend_half_running();
        crate::backend_update::run(&app, &mode, &mode_label, previous_release.as_deref()).await
    };
    // ONE ENDING RULE FOR BOTH DOORS (2026-11-21). `Run::ending` reads the two
    // versions re-read AFTER the attempt - the same function the automatic
    // finish uses - so a press and a start-up cannot report the same run
    // differently. A run the bound ended is `partial` when its marker read back
    // as the installed desktop's version (the files and version are updated;
    // the full check did not finish) and `failed` when it did not, so an old
    // version is never painted as if it were still there. `proven` stays its
    // own answer: a backend that patched but skipped its own checks is patched,
    // and is not a pass.
    let (backend_state, backend_detail) = backend.ending();
    let backend_step = match backend_state {
        "ok" => Step::ok(STEP_BACKEND, backend_detail),
        "partial" => Step::partial(STEP_BACKEND, backend_detail),
        _ => Step::failed(STEP_BACKEND, backend_detail),
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
        let outcome = BothOutcome {
            updated_both: both_updated(&steps),
            steps,
            // Only when this attempt actually stopped Jarvis. A refusal that
            // never got that far has nothing to start again.
            restart_needed: backend_stopped,
        };
        // The window says the same ending, so a run that stopped here cannot
        // sit under a bar that still looks like it is working.
        update_window::ended(&app, &outcome);
        return Ok(outcome);
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
            let outcome = BothOutcome {
                updated_both: both_updated(&steps),
                steps,
                // The refusal happens before the desktop half stops anything,
                // so Jarvis is off only if the backend half itself stopped it.
                restart_needed: backend_stopped,
            };
            update_window::ended(&app, &outcome);
            return Ok(outcome);
        }
    };
    // The last honest note this process can send about the desktop half: the
    // package is verified, the record is written and read back, and the backend
    // is stopped - the installer is the next line, and it ends this process.
    // The window says what is about to happen instead of pretending to watch it
    // (see `update_window.rs`'s module docs).
    update_window::installing(&app);
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
    // This line is reached only when the installer did NOT take the process
    // (a failed install, or a platform without the Windows exit): the window
    // gets the ending here, and stays open until the owner closes it.
    update_window::ended(&app, &outcome);
    Ok(outcome)
}

// ---------------------------------------------------------------------------
// The automatic finish: a desktop-only update's backend half (2026-11-20)
// ---------------------------------------------------------------------------
//
// The owner's standing rule, stated 2026-11-20 21:12 PT after two half-updates
// left the HUD saying MISMATCH: *"when I update Jarvis the HUD and backend
// should always update at the same time."*
//
// Rule 1 (`desktop_install_gate`) covers every in-app update action. The Windows
// installer path cannot be hooked - the updater runs it and then exits this
// process - so a desktop-only update can still happen. This section is the
// answer to that one: on the next start, the running desktop version is compared
// with the backend's own reported version, and when the backend is the OLDER one
// the app runs the backend half of the same "Update everything" action by
// itself, at the default pace, and says what it is doing and what happened.
//
// What it is, said plainly: **the owner's own update action continuing**, not a
// new one. It raises no card, approves nothing, changes no setting, and adds no
// network path - it runs the same local patcher the button runs. The three
// limits are held by the code below rather than by this comment:
//
// * it tries ONCE for one exact `(desktop, backend)` mismatch, ever (a
//   process-level record), so a PC that cannot finish it says so once and does
//   not loop;
// * it never starts when the two versions are equal or the backend is NEWER -
//   that is the safe direction the HUD already explains;
// * it does not run at all when the Jarvis program folder cannot be proved to
//   hold this build's commit (or a later one): patching from an older folder
//   would make the backend older than the desktop, and moving the HUD's marker
//   would then hide exactly the difference this rule exists to show. That
//   attempt says why and claims nothing.

/// The decision the start-up comparison makes about a desktop that has moved
/// ahead of its backend. Pure, so every branch is a test.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AutoFinish {
    /// Nothing to do: versions equal, backend newer, or no comparable answer.
    Nothing,
    /// The backend is older and can be finished here: run the backend half.
    Run,
    /// The backend is older and cannot be finished here. `String` is the ONE
    /// line the owner is told; nothing is installed and nothing is claimed.
    Blocked(String),
}

/// What the start-up comparison decides, from the handshake's own answer and
/// `locate()`'s own refusal - the same two sources the Updates card renders, so
/// the automatic finish and the card cannot disagree.
pub fn auto_finish_plan(
    state: crate::backend_self::SyncState,
    blocked: Option<&str>,
) -> AutoFinish {
    if state != crate::backend_self::SyncState::BackendOlder {
        // IN SYNC is done. A NEWER backend is the safe direction, and the HUD
        // already says so; so is "unreachable" and "different numbering", where
        // there is no mismatch to run against. None of those may start an
        // update.
        return AutoFinish::Nothing;
    }
    match blocked.map(str::trim).filter(|why| !why.is_empty()) {
        None => AutoFinish::Run,
        Some(why) => AutoFinish::Blocked(format!(
            "Jarvis Desktop is ahead of the backend, but the backend half cannot be \
             finished automatically on this PC: {why}"
        )),
    }
}

/// The line said BEFORE the automatic run. It says what is happening NOW - the
/// owner's 2026-11-21 report was a stale MISMATCH still on screen while the
/// backend half was being finished, so this line replaces that one and carries
/// the words for it. Names the versions, promises no ending.
pub fn auto_finish_opening(desktop: &str, backend: Option<&str>) -> String {
    let installed = match backend.map(str::trim).filter(|b| !b.is_empty()) {
        Some(version) => format!("the backend is {version}"),
        None => "a backend so old it does not report its version".to_string(),
    };
    format!(
        "Finishing the backend half now. Jarvis Desktop {desktop} is installed and \
         {installed} - the same update \"Update everything\" runs, at the default \
         pace. This can take several minutes."
    )
}

/// The one honest line for the attempt that could not run because the Jarvis
/// program folder is not this build's commit (or a later one).
///
/// Pure, and it must never claim an update: this is the case where patching
/// would leave the backend OLDER than the desktop, so the app refuses instead of
/// hiding it. `repo` and `build` are the short or full commits, named only when
/// they were really read.
pub fn auto_finish_behind_words(desktop: &str, repo: Option<&str>, build: Option<&str>) -> String {
    let named = match (repo, build) {
        (Some(repo), Some(build)) => {
            format!("the Jarvis program folder is at {repo} and this app was built from {build}")
        }
        (Some(repo), None) => format!(
            "the Jarvis program folder is at {repo} and this build does not record which \
             commit it came from"
        ),
        _ => "this app cannot read which commit the Jarvis program folder is at".to_string(),
    };
    format!(
        "Jarvis Desktop {desktop} is ahead of the backend, but {named}, so patching the \
         backend from that folder would not make the two halves the same release. Nothing \
         was changed. Pull the program folder (git pull), then Settings, then Updates, and \
         press Update everything."
    )
}

/// The one honest line for an automatic finish that RAN and did not finish.
///
/// WHAT IS WRONG AND WHAT IS NOT. The desktop half was installed by its own
/// installer BEFORE this attempt started - that is the whole reason the run
/// happened - so this line must never say the desktop was not installed. That
/// exact claim was measured false on the owner's PC, 2026-11-21 00:28 PT: after
/// 0.2.487 was installed, the backend half failed and the HUD said "The backend
/// step did not finish, so Jarvis Desktop was NOT installed on top of it".
///
/// WHAT THE BACKEND VERSION IS. `detail` is the run's own ending
/// ([`crate::backend_update::Run::ending`]): it already carries the two
/// versions RE-READ after the attempt, so this function never restates an old
/// version as if it were still true - the measured 2026-11-21 12:08:54Z line
/// said "The backend is still 0.2.487" when the marker read 0.2.488. `log_dir`
/// names the run's own log. Pure, so both outcomes are tests rather than hopes.
pub fn auto_finish_failed_words(desktop: &str, detail: &str, log_dir: Option<&str>) -> String {
    let mut words = format!(
        "Jarvis Desktop {desktop} is installed; the backend half is the one that did \
         not finish. Press \"Update everything\" to try the backend half again."
    );
    let detail = detail.trim();
    if !detail.is_empty() {
        words.push(' ');
        words.push_str(detail);
    }
    match log_dir.map(str::trim).filter(|dir| !dir.is_empty()) {
        Some(dir) => words.push_str(&format!(" The run's own log is in {dir}.")),
        None => words.push_str(" The run's own log is the printout above."),
    }
    words
}

/// The automatic finish's line for a run a BOUND ended AFTER the file half had
/// been proved and the marker read back as the installed desktop's own version.
///
/// WHAT IS TRUE AND WHAT IS NOT. The desktop half was installed before this
/// ran, so the line says that first; the bound's own words then say which bound
/// ended the run, after how long, what the re-read found, and that a restart's
/// handshake may now read IN SYNC. It never says the two halves now match - the
/// bound ended the run before the proof suites finished, and only the next
/// start's own handshake is the read-back that may say IN SYNC. Pure.
pub fn auto_finish_bound_words(desktop: &str, bound_words: &str, log_dir: Option<&str>) -> String {
    let mut words = format!(
        "Jarvis Desktop {desktop} is installed. {}",
        bound_words.trim()
    );
    match log_dir.map(str::trim).filter(|dir| !dir.is_empty()) {
        Some(dir) => words.push_str(&format!(" The run's own log is in {dir}.")),
        None => words.push_str(" The run's own log is the printout above."),
    }
    words
}

/// The one line for an automatic finish that proved itself AND read the two
/// versions back as in step. "Both halves now match" may be said only here: the
/// caller reaches this with an IN SYNC read-back, never with a plan or a hope.
/// `files` carries the release's own `BESIDE:` / `TOOL DEFAULTS:` lines when it
/// has them, so an update nobody pressed a button for still says what reached
/// the PC.
pub fn auto_finish_ok_words(desktop: &str, backend: Option<&str>, files: &str) -> String {
    let backend = backend
        .map(str::trim)
        .filter(|version| !version.is_empty())
        .unwrap_or("the same version");
    let files = files.trim();
    let mut words = format!(
        "The backend half finished, and both halves now match: Jarvis Desktop {desktop} and \
         the backend {backend}."
    );
    if !files.is_empty() {
        words.push(' ');
        words.push_str(files);
    }
    words
}

/// One automatic attempt is allowed per exact mismatch, in this process.
///
/// A record rather than a comment: "once per mismatch, never in a loop" is a
/// test. `claim` is `true` the first time for one `(desktop, backend)` pair and
/// `false` every time after; a different pair is a new mismatch and starts a new
/// single attempt.
#[derive(Debug, Default)]
pub struct AutoFinishAttempts(std::sync::Mutex<Option<(String, String)>>);

impl AutoFinishAttempts {
    pub fn new() -> Self {
        Self::default()
    }

    /// The pair as this record keys it. An unknown backend version is its own
    /// key (`""`), because two failures with no version to name are still the
    /// same mismatch.
    fn key(desktop: &str, backend: Option<&str>) -> (String, String) {
        (
            desktop.trim().to_string(),
            backend.map(str::trim).unwrap_or("").to_string(),
        )
    }

    /// Claim the one attempt for this mismatch. Never touches the record for a
    /// mismatch it has already claimed.
    pub fn claim(&self, desktop: &str, backend: Option<&str>) -> bool {
        let wanted = Self::key(desktop, backend);
        let mut slot = self
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if slot.as_ref() == Some(&wanted) {
            return false;
        }
        *slot = Some(wanted);
        true
    }
}

/// The app's own record. Only the startup path reads it, and only [`claim`] is
/// ever called on it.
static AUTO_FINISH_ATTEMPTS: AutoFinishAttempts = AutoFinishAttempts(std::sync::Mutex::new(None));

/// The commit the desktop binary ran BEFORE the installer that just finished,
/// remembered by [`reconcile_pending_at_startup`] for the automatic finish.
///
/// `pending-desktop-update.json` is written by the OLD process and carries
/// `appCommit` - the build it was running. After the installer ends it, the new
/// process's own commit is the RELEASE; the old one is the baseline the tool
/// defaults step compares against (so a tool THIS release newly ships ON is told
/// from one the owner turned off, which is never re-enabled). One value per
/// process, set once, and only when the installer really finished.
static PREVIOUS_DESKTOP_BUILD: std::sync::Mutex<Option<String>> = std::sync::Mutex::new(None);

/// Remember the build commit recorded by the pending install that just finished.
/// Returns what was stored, so a caller can log it.
pub fn remember_previous_desktop_build(commit: Option<&str>) -> Option<String> {
    let commit = commit
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string);
    let mut slot = PREVIOUS_DESKTOP_BUILD
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    *slot = commit;
    slot.clone()
}

/// The build commit the desktop ran before the update that just installed, when
/// the startup reconcile saw such an update finish.
pub fn previous_desktop_build() -> Option<String> {
    PREVIOUS_DESKTOP_BUILD
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .clone()
}

/// One line for the HUD's chat, on the feed's `version` channel - the same
/// channel the MISMATCH sentence arrives on, so the story is in one place.
fn say_version_line(app: &AppHandle, state: &str, words: &str) {
    crate::push_to_hud(
        app,
        "version",
        &crate::backend_self::VersionLine {
            state: state.to_string(),
            words: words.to_string(),
        },
    );
}

/// Runs the automatic finish, if the start-up comparison says it should.
///
/// Called from [`crate::backend_self::spawn_startup_handshake`] and nowhere
/// else, after the handshake has already told the HUD it is behind. Everything
/// this does is reported, once before and once after; nothing here can approve
/// or configure anything.
pub async fn finish_backend_if_desktop_ahead(
    app: &AppHandle,
    sync: &crate::backend_self::VersionSync,
) {
    let here = crate::backend_update::locate(app);
    let plan = auto_finish_plan(sync.state, here.blocked.as_deref());
    if plan == AutoFinish::Nothing {
        return;
    }
    // Once per mismatch, before anything else: a blocked attempt counts too, so
    // a PC that cannot finish it says why once and never retries in a loop.
    if !AUTO_FINISH_ATTEMPTS.claim(&sync.desktop, sync.backend.as_deref()) {
        return;
    }
    match plan {
        AutoFinish::Nothing => {}
        AutoFinish::Blocked(why) => {
            crate::logfile::log(&format!("[jarvis] automatic backend finish: {why}"));
            say_version_line(app, "failed", &why);
        }
        AutoFinish::Run => finish_backend_half(app, sync, &here).await,
    }
}

/// The run itself: the same checks and the same runner an "Update everything"
/// press uses, minus the desktop half (that one already installed).
async fn finish_backend_half(
    app: &AppHandle,
    sync: &crate::backend_self::VersionSync,
    here: &crate::backend_update::Where,
) {
    // The program folder must really hold this build's commit (or a later one).
    // Anything unprovable is a single honest line, never a run the HUD would
    // then lie about.
    let build = crate::backend_update::app_commit();
    let proved = matches!((here.repo.as_deref(), build.as_deref()), (Some(_), Some(_)))
        && crate::backend_update::repo_is_at_least_build(here.repo.as_deref(), build.as_deref())
            == Some(true);
    if !proved {
        let repo = crate::backend_update::repo_commit(here.repo.as_deref());
        let words = auto_finish_behind_words(&sync.desktop, repo.as_deref(), build.as_deref());
        crate::logfile::log(&format!("[jarvis] automatic backend finish: {words}"));
        say_version_line(app, "failed", &words);
        return;
    }
    // The same two pre-checks a press makes: one run in this app, and no run
    // beside another update already held on this PC. Both refuse in words that
    // say nothing was started.
    let Some(_in_app) = claim_update_both() else {
        let words = "Jarvis Desktop is ahead of the backend, but a backend update is \
                     already running in this window. Nothing was started; the next start \
                     finishes the backend half if it is still ahead."
            .to_string();
        crate::logfile::log(&format!("[jarvis] automatic backend finish: {words}"));
        say_version_line(app, "failed", &words);
        return;
    };
    if let Some(lock) = crate::backend_update::held_update_lock(app) {
        let words = format!(
            "Jarvis Desktop is ahead of the backend, but a Jarvis backend update is \
             already running on this PC (pid {}, pace {}). Nothing was started.",
            lock.pid, lock.pace
        );
        crate::logfile::log(&format!("[jarvis] automatic backend finish: {words}"));
        say_version_line(app, "failed", &words);
        return;
    }
    // The default pace is the press's default. The label comes from the tool's
    // own answer when the folder has it; a folder too old for the tool runs the
    // older one-at-a-time patcher, exactly as a press would.
    let label = match (here.repo.as_deref(), here.backend.as_deref()) {
        (Some(repo), Some(backend)) => crate::backend_update::mode_plan_for(repo, backend)
            .0
            .iter()
            .find(|row| row.id == "responsive")
            .map(|row| row.label.clone())
            .unwrap_or_else(|| "Balanced (older one-at-a-time update)".to_string()),
        _ => "Balanced (older one-at-a-time update)".to_string(),
    };
    let opening = auto_finish_opening(&sync.desktop, sync.backend.as_deref());
    crate::logfile::log(&format!("[jarvis] {opening}"));
    // The card (and any Settings window opened while this runs) reads this flag
    // through `backend_self::read`, so the stale MISMATCH is replaced by
    // "Finishing the backend half now" rather than staying on screen while the
    // versions change underneath it.
    let _backend_half = claim_backend_half_running();
    say_version_line(app, "running", &opening);

    // THE SAME runner the button uses, at the default pace. It stops the
    // supervised backend itself, patches, runs the suites and reports a verdict.
    // The tool-defaults step compares against the build the desktop had BEFORE
    // the installer that started this launch - remembered from the pending
    // record - and falls back to this build when there was no such record.
    let previous_release = previous_desktop_build().or_else(crate::backend_update::app_commit);
    let backend =
        crate::backend_update::run(app, "responsive", &label, previous_release.as_deref()).await;
    let (state, mut words) = if backend.bound.is_some() {
        // THE BOUND ENDED IT, NOT THE RUN'S OWN VERDICT (2026-11-21). What is
        // true is what the two versions read back AFTER it ended, and the one
        // ending rule (`Run::ending`) says it the same way the press path does.
        // The desktop half was installed by its installer before this ran, so
        // the line says that first - never "Jarvis Desktop was NOT installed".
        let (state, detail) = backend.ending();
        if state == "partial" {
            (
                state,
                auto_finish_bound_words(&sync.desktop, &detail, backend.log_dir.as_deref()),
            )
        } else {
            (
                state,
                auto_finish_failed_words(&sync.desktop, &detail, backend.log_dir.as_deref()),
            )
        }
    } else if !backend.ok {
        // The desktop half was installed by its installer before this ran, so
        // the failure line names the BACKEND half as the incomplete one and the
        // press that would retry it - never "Jarvis Desktop was NOT installed"
        // (measured false on the owner's PC, 2026-11-21 00:28 PT).
        (
            "failed",
            auto_finish_failed_words(
                &sync.desktop,
                &backend.ending().1,
                backend.log_dir.as_deref(),
            ),
        )
    } else if !backend.proven {
        (
            "partial",
            format!(
                "The automatic backend update patched the backend, but could not prove \
                 every check - and an unproven backend is not a pass here, so the two \
                 halves are not claimed to match. {}",
                backend.ending().1
            ),
        )
    } else {
        // The patched backend can be called this release only if the marker the
        // HUD compares moves with it. The value is this app's own version (the
        // one the installer just put here), and it is written only because the
        // check above proved the program folder holds this build's commit.
        let backend_dir = Path::new(here.backend.as_deref().unwrap_or_default());
        let marker = crate::backend_update::write_release_marker(backend_dir, &sync.desktop);
        let marker_said = crate::backend_update::marker_words(&marker);
        crate::logfile::log(&format!("[jarvis] automatic backend finish: {marker_said}"));
        // The backend was stopped for the patch; start it again so the version
        // it reports is the code and marker that were just put down, then read
        // the pair back. Bounded, and never retried beyond that.
        let after = restart_and_read(app).await;
        if marker.in_step() && after.state == crate::backend_self::SyncState::InSync {
            // What the release's own files did, when they had anything to say:
            // the look spec delivered beside the backend, and the new tool
            // defaults added to the owner's config. Verbatim on the ending line,
            // so an update nobody presses a button for still says what reached
            // this PC.
            let files = if backend.notes.is_empty() {
                String::new()
            } else {
                format!(" {}", backend.notes.join(" "))
            };
            (
                "ok",
                auto_finish_ok_words(&after.desktop, after.backend.as_deref(), &files),
            )
        } else {
            let extra = if marker.in_step() {
                format!("The two versions still differ: {}", after.words)
            } else {
                format!("{marker_said} {}", after.words)
            };
            (
                "partial",
                format!(
                    "The automatic backend update patched the backend and proved its \
                     tests, but the two halves are not in step yet. {extra}"
                ),
            )
        }
    };
    if words.is_empty() {
        words = "The automatic backend update ended without a sentence to say what it \
                 did, so nothing is claimed about it."
            .to_string();
    }
    crate::logfile::log(&format!("[jarvis] automatic backend finish: {words}"));
    say_version_line(app, state, &words);
}

/// Starts the supervised backend again after the patch run stopped it, then
/// reads the two versions back - a few bounded attempts, because a backend that
/// was just started is not answering on its first millisecond.
///
/// This is not an update retry loop: the run happens once, and this only waits
/// for the process the run itself needs to report its own version.
async fn restart_and_read(app: &AppHandle) -> crate::backend_self::VersionSync {
    match crate::sidecar::ensure_backend(app).await {
        Ok(said) => crate::logfile::log(&format!("[jarvis] automatic backend finish: {said}")),
        Err(err) => crate::logfile::log(&format!(
            "[jarvis] automatic backend finish: the backend could not be started again \
             ({err}); the version it reports cannot be read"
        )),
    }
    let mut last = crate::backend_self::read(app).await;
    for _ in 0..5 {
        if last.state != crate::backend_self::SyncState::Unreachable {
            return last;
        }
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        last = crate::backend_self::read(app).await;
    }
    last
}

/// The update a chat message asked for, after its ONE card was approved.
///
/// HOW IT IS REACHED, AND WHY THAT IS THE GATE. The backend's chat fast path
/// raises one approval card (`jarvis_quick.py`, action `desktop_update`,
/// risky and therefore Windows Hello here) and downloads nothing. The
/// owner's Approve is sent by [`crate::commands::answer_approval`], which
/// reads the card it is answering from the queue it already holds and, only
/// when that card's action is the update one, calls this. (Since 2026-11-18
/// the phone may answer that same card with its own fingerprint; that path
/// never reaches this command - the backend runs the same updater itself,
/// `jarvis_update.py` - so the PC road below is unchanged.) So the path is:
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
                "Atlas Desktop update available",
                &format!("Version {version} is ready to install from Settings. {INSTALL_CLOSES_AND_RESTARTS}"),
            );
        }
        crate::tray::on_update_status(&handle, &status);
        let _ = handle.emit(crate::events::UPDATE_STATUS, status);
    });
}

#[cfg(test)]
mod tests {
    use super::{
        auto_finish_behind_words, auto_finish_bound_words, auto_finish_failed_words,
        auto_finish_ok_words, auto_finish_opening, auto_finish_plan, backend_half_running,
        both_updated, chat_facts, claim_backend_half_running, claim_update_both, clear_pending,
        desktop_half_allowed, desktop_half_trace, desktop_install_gate, ending_words, finish,
        friendly, install_notice_for, is_update_card, local_stamp, mark_launched,
        previous_desktop_build, read_pending, reconcile, remember_previous_desktop_build,
        same_version, state_of, step_starting, write_pending, AutoFinish, AutoFinishAttempts,
        BackendHalf, BeforeInstaller, DesktopEnding, DesktopHalf, PendingDesktopInstall, Status,
        Step, BEFORE_INSTALLER, DESKTOP_HALF, DESKTOP_SKIPPED_DETAIL, DESKTOP_UNPROVEN_DETAIL,
        INSTALL_CLOSES_AND_RESTARTS, PENDING_FILE, STEP_BACKEND, STEP_DESKTOP,
    };

    // ---- the four-state truth (Task-50, Wave 12) ---------------------------

    /// A Status built the way `look()` builds one, then finished the one way
    /// every surface gets it.
    fn checked(
        available: Option<&str>,
        error: Option<&str>,
        supported: bool,
        at: Option<&str>,
    ) -> Status {
        finish(Status {
            current: "0.2.320".to_string(),
            available: available.map(str::to_string),
            error: error.map(str::to_string),
            supported,
            checked_at: at.map(str::to_string),
            ..Status::default()
        })
    }

    #[test]
    fn a_fresh_launch_is_unknown_and_never_up_to_date() {
        let status = checked(None, None, true, None);
        assert_eq!(status.state, "unknown");
        assert!(status.checked_at.is_none());
        // The old bug in one line: `available: None, error: None` used to be
        // drawn as "the newest published" with no check behind it.
        assert_ne!(status.state, "up_to_date");
    }

    #[test]
    fn a_successful_check_with_nothing_newer_is_up_to_date_with_its_time() {
        let status = checked(None, None, true, Some("2026-11-09 02:14"));
        assert_eq!(status.state, "up_to_date");
        assert_eq!(status.checked_at.as_deref(), Some("2026-11-09 02:14"));
    }

    #[test]
    fn a_found_update_is_update_available() {
        let status = checked(Some("0.2.400"), None, true, Some("2026-11-09 02:14"));
        assert_eq!(status.state, "update_available");
    }

    #[test]
    fn a_failed_check_is_cannot_check_and_keeps_the_reason() {
        let status = checked(
            None,
            Some("Could not reach the release endpoint"),
            true,
            Some("2026-11-09 02:14"),
        );
        assert_eq!(status.state, "cannot_check");
        assert!(status.error.unwrap().contains("Could not reach"));
        // It did ask, so the time is real and stays.
        assert_eq!(status.checked_at.as_deref(), Some("2026-11-09 02:14"));
    }

    #[test]
    fn a_build_that_cannot_check_says_so_and_never_claims_a_time() {
        let status = checked(None, Some("This build has no update key"), false, None);
        assert_eq!(status.state, "cannot_check");
        assert!(
            status.checked_at.is_none(),
            "a build that never asked carried a checked time"
        );
    }

    #[test]
    fn the_state_is_derived_not_copied() {
        // A Status that arrives with a wrong state (an older cached answer, a
        // fixture) is recomputed from the facts before any screen sees it.
        let mut status = checked(None, None, true, None);
        status.state = "up_to_date".to_string();
        assert_eq!(finish(status).state, "unknown");
    }

    #[test]
    fn a_finished_check_with_an_unreadable_clock_is_still_up_to_date() {
        // `Some("")` is what `local_stamp()` writes when the OS clock cannot be
        // read: the check DID happen, so the state is the good one and only the
        // time is missing. `None` is the only "no check" answer.
        assert_eq!(state_of(None, None, true, Some("")), "up_to_date");
        assert_eq!(state_of(None, None, true, Some("   ")), "up_to_date");
        assert_eq!(state_of(None, None, true, None), "unknown");
    }

    #[test]
    fn an_update_outranks_a_half_read() {
        // A known update is the one thing the owner can act on; nothing may
        // hide it behind "cannot check".
        assert_eq!(
            state_of(Some("0.2.400"), Some("boom"), true, None),
            "update_available"
        );
    }

    #[test]
    fn the_stamp_is_a_real_wall_clock_string() {
        let stamp = local_stamp();
        assert_eq!(stamp.len(), 16, "not YYYY-MM-DD HH:MM: {stamp:?}");
        let at: Vec<char> = stamp.chars().collect();
        assert_eq!(
            (at[4], at[7], at[10], at[13]),
            ('-', '-', ' ', ':'),
            "{stamp}"
        );
        let hour: u32 = stamp[11..13].parse().expect("hour");
        let minute: u32 = stamp[14..16].parse().expect("minute");
        assert!(hour < 24 && minute < 60, "{stamp}");
        // A zero epoch would be exactly the invented time this module refuses.
        assert_ne!(stamp, "1970-01-01 00:00");
    }

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

    /// The tray's update row must be ADDED and REMOVED (never left disabled),
    /// and pressing it must run THIS module's **both-halves** update - the same
    /// runner the Settings Install press and an answered `desktop_update` card
    /// use - falling back to the desktop-only install ONLY where the backend
    /// half cannot run, and there only with a sentence that says the BACKEND was
    /// NOT updated.
    ///
    /// Source pins, because no pure test can reach a native menu or an
    /// `AppHandle`. The needles are `concat!`-split, so this test's own text
    /// cannot satisfy them: only the real code can.
    #[test]
    fn the_tray_rows_update_press_updates_both_halves_and_the_row_comes_and_goes() {
        let tray = include_str!("tray.rs");
        // Absence is the no-update state: the row is parented and unparented.
        assert!(
            tray.contains("rows.more.append(&rows.update)"),
            "the update row is never added to the menu"
        );
        assert!(
            tray.contains("rows.more.remove(&rows.update)"),
            "the update row is never removed from the menu, so it would stay \
             there when no update exists"
        );
        // It is fed from the one real check, not a second network path.
        assert!(
            tray.contains("crate::update::available_version(app)"),
            "the tray does not read the update check's own answer"
        );
        // The press goes to this module.
        assert!(
            tray.contains("ID_UPDATE => run_update_from_tray(app)"),
            "the update row is not dispatched"
        );
        assert!(
            tray.contains("crate::update::install_from_tray(handle).await"),
            "the tray press no longer reaches update.rs's install"
        );

        // This module takes that press to ONE of two doors, and the choice is
        // the same check the Settings card makes (`backend_update_status`'
        // `blocked` field, from `backend_update::locate`).
        let src = include_str!("update.rs");
        let entrance = &src[src
            .find(concat!("pub async fn install_from_", "tray"))
            .expect("update.rs has no install_from_tray")..];
        let entrance = &entrance[..entrance
            .find(concat!("async fn update_both_", "from_tray"))
            .expect("install_from_tray no longer chooses between the two doors")];
        assert!(
            entrance.contains(concat!("backend_half_", "blocked(&app)")),
            "the tray press no longer asks whether the backend half can run"
        );
        // Neither update runs from the deciding function itself: it chooses.
        assert!(
            !entrance.contains(concat!("install_", "update(app.clone()).await")),
            "install_from_tray runs the desktop-only install itself"
        );
        assert!(
            !entrance.contains(concat!(
                "update_both(app.clone(), ",
                "\"responsive\".to_string())"
            )),
            "install_from_tray runs the both-halves update itself instead of choosing"
        );

        // The ordinary door is `update_both`, at the pace the Settings Install
        // press uses.
        let both = &src[src
            .find(concat!("async fn update_both_", "from_tray("))
            .expect("update.rs has no update_both_from_tray")..];
        let both = &both[..both
            .find(concat!("async fn refuse_", "tray_update("))
            .expect("update.rs no longer has the blocked tray arm")];
        let both_call = concat!("update_both(app.clone(), ", "\"responsive\".to_string())");
        assert!(
            both.contains(both_call),
            "the tray press no longer runs the SAME both-halves runner Settings' \
             Install press runs, at the same default pace"
        );
        assert!(
            !both.contains(concat!("install_", "update(app.clone()).await")),
            "the both-halves arm still installs the desktop on its own"
        );

        // The blocked arm installs NOTHING (the owner's both-or-neither rule,
        // 2026-11-20) and its one line is the gate's own words - there is no
        // desktop-only fallback any more.
        let blocked = &src[src
            .find(concat!("async fn refuse_", "tray_update("))
            .expect("update.rs has no refuse_tray_update")..];
        let blocked = &blocked[..blocked.find("\n}\n").expect("it has no end")];
        assert!(
            blocked.contains(concat!("desktop_install_", "gate(Some(&why))")),
            "the blocked tray arm does not use the both-or-neither gate's own line"
        );
        assert!(
            !blocked.contains(concat!("install_", "update(app.clone()).await")),
            "the blocked tray arm still runs a desktop-only install"
        );
        assert!(
            !blocked.contains("Installing Jarvis Desktop on"),
            "the blocked tray arm still says it is installing the desktop"
        );
        assert!(
            blocked.contains("check_for_update(app.clone())"),
            "the blocked tray arm leaves the row on \"Updating…\" for ever"
        );
        // ...and the old fallback function is gone, not merely unreachable.
        assert!(
            !src.contains(concat!("async fn install_desktop_", "alone(")),
            "the desktop-only fallback is still defined"
        );
    }

    /// DEF-045: the tray's update row patches the live backend, and
    /// right-clicking the tray is enough to reach it. App lock must be asked
    /// FIRST, and a refused check must start nothing. Pinned as source,
    /// because this crate has no headless way to build a Tauri app and press
    /// the row; the three lock cases themselves are
    /// `lock::rules::tests::the_tray_update_is_held_only_while_the_lock_has_the_owner_away`.
    #[test]
    fn the_tray_update_asks_for_unlock_before_anything_is_started() {
        let src = include_str!("update.rs");
        let entrance = &src[src
            .find(concat!("pub async fn install_from_", "tray"))
            .expect("update.rs has no install_from_tray")..];
        let entrance = &entrance[..entrance
            .find(concat!("async fn update_both_", "from_tray"))
            .expect("install_from_tray no longer chooses between the two doors")];

        let gate = entrance
            .find(concat!("crate::lock::require_", "unlocked(&app).await"))
            .expect("install_from_tray no longer asks the App lock");
        let announced = entrance
            .find(concat!("crate::tray::update_", "started(&app, &version)"))
            .expect("the tray press no longer turns the row into \"Updating…\"");
        let branch = entrance
            .find(concat!("match backend_half_", "blocked(&app)"))
            .expect("the tray press no longer asks whether the backend half can run");
        assert!(
            gate < announced && gate < branch,
            "the App lock is asked after the update has been announced or started"
        );

        // A refused check returns before either door, and says so: silence
        // would read as a broken row rather than as the lock refusing.
        let refused = &entrance[gate..];
        let stop = refused
            .find("\n        return;")
            .expect("a refused App-lock check does not stop the update");
        let version = refused
            .find("let Some(version)")
            .expect("install_from_tray no longer names the version");
        assert!(
            stop < version,
            "a refused App-lock check falls through into the update:\n{refused}"
        );
        assert!(
            entrance.contains("The update was not started."),
            "a refused App-lock check does not tell the owner nothing was started"
        );
    }

    // ---- both or neither (the owner's standing rule, 2026-11-20 21:12 PT) --
    //
    // Rule 1: the in-app update action installs the desktop half only when the
    // backend half can run, and otherwise says in one line which folder/program
    // is missing and installs nothing.

    #[test]
    fn the_both_or_neither_gate_allows_a_desktop_install_only_with_a_runnable_backend() {
        // `locate()` answering "nothing blocked" is the whole permission.
        assert_eq!(desktop_install_gate(None), Ok(()));
        assert_eq!(desktop_install_gate(Some("   ")), Ok(()));

        let why = "This app does not know where the Jarvis program folder is on this PC, \
                   so it cannot update the backend. Nothing was changed.";
        let refused = desktop_install_gate(Some(why))
            .expect_err("a blocked backend half must refuse the desktop install");
        // ONE plain line that names the thing that is missing...
        assert!(refused.contains("NOT installed"), "{refused}");
        assert!(refused.contains(why), "{refused}");
        assert!(refused.contains("both halves"), "{refused}");
        // ...and never a claim that Jarvis was updated.
        for forbidden in ["was updated", "is updated", "both halves are"] {
            assert!(!refused.contains(forbidden), "{forbidden:?} in {refused}");
        }
        assert!(
            !refused.contains('\n'),
            "the refusal is not one line: {refused:?}"
        );
    }

    /// The gate comes BEFORE the download, the record, the backend stop and the
    /// installer - so a blocked PC downloads nothing and changes nothing. And
    /// `install_update` is the only in-app command that can install the desktop
    /// alone; the tray uses the same gate's words rather than a second rule.
    #[test]
    fn a_desktop_install_checks_the_gate_before_anything_else_happens() {
        let src = include_str!("update.rs");
        let install = &src[src
            .find("pub async fn install_update")
            .expect("update.rs has no install_update")..];
        let install = &install[..install.find("\n}\n").expect("it has no end")];
        let gate = install
            .find("desktop_install_gate(here.blocked.as_deref())")
            .expect("install_update no longer asks the both-or-neither gate");
        for later in [
            "prepare_desktop_half",
            "install_now",
            concat!("INSTALL_CLOSES_AND", "_RESTARTS"),
        ] {
            let at = install
                .find(later)
                .unwrap_or_else(|| panic!("install_update never reaches {later}"));
            assert!(
                gate < at,
                "the gate is checked after `{later}` - a blocked PC would already have \
                 downloaded, stopped or installed something"
            );
        }
        // The tray's blocked arm is the same gate, so the two doors cannot
        // disagree about the one line the owner is told.
        assert!(
            src.contains(concat!("desktop_install_", "gate(Some(&why))")),
            "the tray blocked arm does not use the gate's own line"
        );
    }

    // ---- the automatic finish (rule 2) ------------------------------------

    #[test]
    fn a_desktop_ahead_of_its_backend_runs_the_backend_half_automatically() {
        // The measured history in one decision: desktop 0.2.486, backend
        // 0.2.484, both folders locatable -> the backend half runs.
        assert_eq!(
            auto_finish_plan(crate::backend_self::SyncState::BackendOlder, None),
            AutoFinish::Run
        );
    }

    #[test]
    fn a_blocked_automatic_finish_says_why_and_installs_nothing() {
        let why = "This app does not know where the Jarvis program folder is on this PC, \
                   so it cannot update the backend. Nothing was changed.";
        match auto_finish_plan(crate::backend_self::SyncState::BackendOlder, Some(why)) {
            AutoFinish::Blocked(words) => {
                // Exactly why, in one line...
                assert!(words.contains(why), "{words}");
                assert!(
                    words.contains("cannot be finished automatically"),
                    "{words}"
                );
                // ...and no claim that anything happened. The ONLY arms that can
                // install are Run; a blocked answer never reaches them.
                for forbidden in ["was updated", "is updated", "installed", "now match"] {
                    assert!(!words.contains(forbidden), "{forbidden:?} in {words}");
                }
                assert!(!words.contains('\n'), "{words:?}");
            }
            other => panic!("a blocked backend half planned {other:?}"),
        }
        // Whitespace is not a reason.
        assert_eq!(
            auto_finish_plan(crate::backend_self::SyncState::BackendOlder, Some("  ")),
            AutoFinish::Run
        );
    }

    #[test]
    fn equal_or_newer_versions_never_start_an_automatic_finish() {
        // The rule, exhaustively over the handshake's own states. Only "the
        // backend is older" may run; every other answer is nothing - even when
        // the folders are blocked.
        for state in [
            crate::backend_self::SyncState::InSync,
            crate::backend_self::SyncState::BackendNewer,
            crate::backend_self::SyncState::Different,
            crate::backend_self::SyncState::Unavailable,
            crate::backend_self::SyncState::Unreachable,
        ] {
            assert_eq!(
                auto_finish_plan(state, None),
                AutoFinish::Nothing,
                "{state:?}"
            );
            assert_eq!(
                auto_finish_plan(state, Some("the folders are not set")),
                AutoFinish::Nothing,
                "{state:?}"
            );
        }
    }

    #[test]
    fn one_mismatch_gets_exactly_one_automatic_attempt() {
        let attempts = AutoFinishAttempts::new();
        // The same mismatch, three times over: the first claim only.
        assert!(attempts.claim("0.2.486", Some("0.2.484")));
        assert!(!attempts.claim("0.2.486", Some("0.2.484")));
        assert!(!attempts.claim("0.2.486", Some("0.2.484")));
        // A DIFFERENT mismatch is a new single attempt, not "already tried".
        assert!(attempts.claim("0.2.490", Some("0.2.486")));
        assert!(!attempts.claim("0.2.490", Some("0.2.486")));
        // A backend too old to report a version is still one mismatch.
        assert!(attempts.claim("0.2.490", None));
        assert!(!attempts.claim("0.2.490", None));
        // Whitespace never makes a second key for the same pair.
        assert!(!attempts.claim(" 0.2.490 ", Some("")));
    }

    #[test]
    fn the_automatic_opening_says_it_is_finishing_now_and_promises_no_ending() {
        let opening = auto_finish_opening("0.2.486", Some("0.2.484"));
        assert!(opening.contains("Jarvis Desktop 0.2.486"), "{opening}");
        assert!(opening.contains("0.2.484"), "{opening}");
        // The owner's 2026-11-21 report: the MISMATCH line stayed on screen
        // while the backend half was being finished. The line said BEFORE the
        // run carries the in-flight words, so the stale warning is replaced the
        // moment the run starts.
        assert!(
            opening
                .to_lowercase()
                .contains("finishing the backend half now"),
            "{opening}"
        );
        assert!(opening.contains("Update everything"), "{opening}");
        assert!(opening.contains("default pace"), "{opening}");
        // It says what is happening, never what happened.
        for forbidden in ["now match", "finished", "IN SYNC", "are equal"] {
            assert!(!opening.contains(forbidden), "{forbidden:?} in {opening}");
        }
        // A backend too old to report a version is still named honestly.
        let old = auto_finish_opening("0.2.486", None);
        assert!(old.contains("does not report its version"), "{old}");
        assert!(
            old.to_lowercase()
                .contains("finishing the backend half now"),
            "{old}"
        );
    }

    /// The Updates card knows a backend half is live because this flag says so.
    /// A run in flight has to be readable on the OTHER side of the app (the
    /// Settings card calls `shell_version_sync` while the run is going), which
    /// is why it is a process flag and not a local in the run's own function.
    #[test]
    fn a_backend_half_is_marked_running_only_while_it_really_is() {
        assert!(!backend_half_running(), "a fresh process claims a run");
        {
            let _running = claim_backend_half_running();
            assert!(
                backend_half_running(),
                "a live backend half does not say it is running"
            );
            // The card's own read (`backend_self::words_for`) is held by its own
            // test; this one holds the flag the read is fed from.
            assert!(
                crate::backend_self::words_for(
                    "0.2.492",
                    Some("0.2.491"),
                    crate::backend_self::SyncState::BackendOlder,
                    backend_half_running(),
                )
                .to_lowercase()
                .contains("finishing the backend half now"),
                "the handshake read during a run would still say MISMATCH"
            );
        }
        assert!(
            !backend_half_running(),
            "the flag outlived the run it described"
        );
    }

    /// Both doors that run a backend half mark it, and both mark it where the
    /// card can see it: a press from the page and the automatic finish. Held by
    /// reading the source, because neither function can be driven in a unit test
    /// without a PC, a patch stack and a process restart.
    #[test]
    fn both_doors_that_run_a_backend_half_mark_it_running() {
        let source = include_str!("update.rs");
        for door in ["pub async fn update_both", "async fn finish_backend_half"] {
            let at = source
                .find(door)
                .unwrap_or_else(|| panic!("{door} is gone"));
            let end = source[at..]
                .find("\n}\n")
                .map(|n| at + n)
                .unwrap_or(source.len());
            assert!(
                source[at..end].contains("claim_backend_half_running()"),
                "{door} runs a backend half without saying it is running"
            );
        }
    }

    #[test]
    fn a_program_folder_behind_this_build_is_never_claimed_as_this_release() {
        let words = auto_finish_behind_words("0.2.486", Some("c75ee418a"), Some("97edfab81"));
        assert!(words.contains("Jarvis Desktop 0.2.486"), "{words}");
        assert!(words.contains("c75ee418a"), "{words}");
        assert!(words.contains("97edfab81"), "{words}");
        assert!(words.contains("Nothing was changed"), "{words}");
        assert!(
            words.contains("git pull") && words.contains("Update everything"),
            "{words}"
        );
        // It must never read as an update, and never claim the halves are in step.
        for forbidden in ["now match", "IN SYNC", "are equal", "was updated"] {
            assert!(!words.contains(forbidden), "{forbidden:?} in {words}");
        }
        // An unreadable half is still named as unreadable rather than left out.
        let unknown = auto_finish_behind_words("0.2.486", None, None);
        assert!(unknown.contains("cannot read"), "{unknown}");
        let build_only = auto_finish_behind_words("0.2.486", Some("c75ee418a"), None);
        assert!(build_only.contains("does not record"), "{build_only}");
    }

    // ---- the automatic finish's endings (2026-11-21) ----------------------

    #[test]
    fn the_automatic_finish_never_says_the_desktop_was_not_installed() {
        // THE MEASURED WORDING BUG. 2026-11-21 00:25-00:28 PT: the installer had
        // put Jarvis Desktop 0.2.487 on the PC, the automatic finish failed its
        // backend half, and the app said "The backend step did not finish, so
        // Jarvis Desktop was NOT installed on top of it" - false about the half
        // that was installed. The honest line names the incomplete half, the one
        // press that retries it, and the run's log. The version it names is the
        // one RE-READ after the attempt: a sentence saying "the backend is still
        // 0.2.486" was measured false at 12:08:54Z, when the marker read 0.2.488.
        let read_back = crate::backend_update::VersionReadBack {
            desktop: "0.2.487".to_string(),
            before: Some("0.2.486".to_string()),
            after: Some("0.2.486".to_string()),
        };
        let detail = format!(
            "{} {}",
            crate::backend_update::backend_failure_words(false),
            read_back.facts()
        );
        let words = auto_finish_failed_words(
            "0.2.487",
            &detail,
            Some(
                r"C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\_jarvis-logs",
            ),
        );
        // What is what: the desktop IS installed; the BACKEND half is the one
        // that did not finish, and the marker still says the older version.
        assert!(
            words.contains("Jarvis Desktop 0.2.487 is installed"),
            "{words}"
        );
        assert!(words.contains("backend half"), "{words}");
        assert!(words.contains("did not finish"), "{words}");
        assert!(words.contains("0.2.486"), "{words}");
        assert!(words.contains("two halves still differ"), "{words}");
        // The one press that would retry it is named, and the log is named.
        assert!(words.contains("Update everything"), "{words}");
        assert!(words.contains("_jarvis-logs"), "{words}");
        // The false claim, in every spelling the old sentence used, is gone -
        // and so is "the backend is still <old>", which the re-read replaced.
        for forbidden in [
            "Jarvis Desktop was NOT installed",
            "was NOT installed on top",
            "nothing was put on top",
            "The backend step did not finish",
            "The backend is still",
        ] {
            assert!(!words.contains(forbidden), "{forbidden:?} in {words}");
        }
        // Nothing here claims the halves match.
        for forbidden in ["now match", "IN SYNC", "both halves"] {
            assert!(!words.contains(forbidden), "{forbidden:?} in {words}");
        }
        assert!(!words.contains('\n'), "{words:?}");
        // A detail that names no version is still honest, and a log that is
        // only the printout above is named as that.
        let old = auto_finish_failed_words("0.2.487", "", None);
        assert!(
            old.contains("The run's own log is the printout above"),
            "{old}"
        );
        assert!(!old.contains("0.2.486"), "{old}");
    }

    #[test]
    fn the_automatic_finish_reports_a_bound_that_ended_a_healthy_file_half() {
        // THE MEASURED FAILURE THIS PR FIXES. 2026-11-21: auto-finish started at
        // 11:08:54Z; the deploy route wrote VERSION 0.2.488 and SOURCE-COMMIT
        // d7003442e; the proof suites then legitimately ran ~57+ minutes; at
        // 12:08:54Z the one-hour wall clock killed the run and the HUD said the
        // backend half did not finish and "The backend is still 0.2.487" - both
        // false, the backend read 0.2.488. The ending now reports what the two
        // versions read back after the stop, says the desktop half is installed,
        // which bound ended it and after how long, and that the restart's own
        // handshake - not this line - may say IN SYNC.
        let read_back = crate::backend_update::VersionReadBack {
            desktop: "0.2.488".to_string(),
            before: Some("0.2.487".to_string()),
            after: Some("0.2.488".to_string()),
        };
        let bound = crate::backend_update::RunBound::Silence {
            ran: std::time::Duration::from_secs(3600 + 23 * 60),
            silent: std::time::Duration::from_secs(15 * 60),
        };
        let detail = crate::backend_update::bound_ending_words(&bound, &read_back);
        let words = auto_finish_bound_words("0.2.488", &detail, Some(r"C:\backend\_jarvis-logs"));
        for expected in [
            "Jarvis Desktop 0.2.488 is installed",
            "silence bound",
            "1h 23m",
            "files and version are updated",
            "VERSION file reads 0.2.488",
            "full check did not finish",
            "Restart Jarvis",
            "will read IN SYNC",
            "_jarvis-logs",
        ] {
            assert!(
                words.contains(expected),
                "{expected:?} missing from {words}"
            );
        }
        for forbidden in [
            "The backend is still",
            "still 0.2.487",
            "both halves now match",
            "now match",
            "are in sync",
            "was NOT installed",
        ] {
            assert!(!words.contains(forbidden), "{forbidden:?} in {words}");
        }
        assert!(!words.contains('\n'), "{words:?}");
    }

    #[test]
    fn no_success_words_without_the_read_back() {
        // "both halves now match" exists in exactly ONE shape: the in-sync
        // handshake read-back, which the caller reaches only after
        // `restart_and_read` says InSync. A bound's marker read is NOT that
        // read-back - it may only promise that a restart WILL read IN SYNC - and
        // a failure never says either.
        let ok = auto_finish_ok_words("0.2.488", Some("0.2.488"), "");
        assert!(ok.contains("both halves now match"), "{ok}");

        let read_back = crate::backend_update::VersionReadBack {
            desktop: "0.2.488".to_string(),
            before: Some("0.2.487".to_string()),
            after: Some("0.2.488".to_string()),
        };
        let detail = crate::backend_update::bound_ending_words(
            &crate::backend_update::RunBound::HardCeiling {
                ran: std::time::Duration::from_secs(3 * 60 * 60),
            },
            &read_back,
        );
        let bound = auto_finish_bound_words("0.2.488", &detail, None);
        assert!(bound.contains("will read IN SYNC"), "{bound}");
        for forbidden in ["both halves now match", "now match", "are in sync"] {
            assert!(!bound.contains(forbidden), "{forbidden:?} in {bound}");
        }

        let failed = auto_finish_failed_words("0.2.488", "The run stopped.", None);
        for forbidden in ["both halves now match", "now match", "IN SYNC"] {
            assert!(!failed.contains(forbidden), "{forbidden:?} in {failed}");
        }
    }

    #[test]
    fn the_press_and_the_automatic_finish_share_the_bound_and_the_read_back() {
        // THE ONE RUNNER, ONE BOUND, ONE ENDING. The bound (progress, not wall
        // clock) lives in `backend_update::RunWatch`, and the state and words of
        // every ending come from `Run::ending`. BOTH doors call the same runner
        // and the same ending function, so a press cannot be killed at one hour
        // while a run is healthy and cannot report a run differently from a
        // start-up.
        let backend = include_str!("backend_update.rs");
        assert!(
            !backend.contains("SCRIPT_LIMIT"),
            "a fixed wall-clock limit came back"
        );
        assert!(
            backend.contains("pub fn observe(&mut self")
                && backend.contains("SCRIPT_SILENCE_LIMIT")
                && backend.contains("SCRIPT_HARD_CEILING"),
            "the progress bound is no longer one tested state machine"
        );

        let src = include_str!("update.rs");
        let production = &src[..src.find("#[cfg(test)]").expect("no test module")];
        let press = &production[production
            .find("pub async fn update_both")
            .expect("update.rs has no update_both")..];
        let press = &press[..press
            .find("// STOP.")
            .expect("update_both has no early return")];
        assert!(
            press.contains("backend.ending()"),
            "the press path does not use the one ending rule"
        );
        let automatic = &production[production
            .find("pub async fn finish_backend_if_desktop_ahead")
            .expect("update.rs has no automatic finish")..];
        let automatic = &automatic[..automatic
            .find("/// The update a chat message asked for")
            .expect("the automatic finish has no end")];
        assert!(
            automatic.contains("backend.ending()"),
            "the automatic finish does not use the one ending rule"
        );
        assert!(
            automatic.contains("backend.bound.is_some()"),
            "the automatic finish no longer recognises a bound ending"
        );
        assert!(
            automatic.contains("auto_finish_bound_words(")
                && automatic.contains("auto_finish_failed_words("),
            "the automatic finish writes its bound/failure lines at the call site"
        );
        assert!(
            !press.contains("SCRIPT_LIMIT") && !automatic.contains("SCRIPT_LIMIT"),
            "a path grew its own wall-clock limit instead of the shared bound"
        );
    }

    #[test]
    fn the_automatic_finish_claims_a_match_only_from_the_read_back() {
        // The SUCCESS ending is a pure function too, and it exists in exactly
        // one shape: both versions read back equal. The caller reaches it only
        // after `restart_and_read` said IN SYNC, so "both halves now match" can
        // never be painted from a plan or a hope.
        let words = auto_finish_ok_words(
            "0.2.487",
            Some("0.2.487"),
            "BESIDE: jarvis-visual-spec.json wrote 73121 bytes (was 61301 bytes)",
        );
        assert!(words.contains("both halves now match"), "{words}");
        assert!(words.contains("Jarvis Desktop 0.2.487"), "{words}");
        assert!(words.contains("the backend 0.2.487"), "{words}");
        // The release's own lines ride on the ending, so an update nobody
        // pressed a button for still says what reached the PC.
        assert!(words.contains("BESIDE:"), "{words}");
        assert!(!words.contains('\n'), "{words:?}");
        // A version the read-back could not name is not invented.
        let unknown = auto_finish_ok_words("0.2.487", None, "");
        assert!(unknown.contains("the same version"), "{unknown}");
        assert!(unknown.contains("both halves now match"), "{unknown}");
    }

    /// The wiring, which no pure test can reach: the start-up handshake is the
    /// ONE caller, it runs the SAME backend runner the button runs, at the
    /// default pace, and the automatic path never touches the desktop install.
    #[test]
    fn the_startup_handshake_is_the_one_place_the_automatic_finish_runs() {
        let self_rs = include_str!("backend_self.rs");
        assert!(
            self_rs
                .contains("crate::update::finish_backend_if_desktop_ahead(&handle, &sync).await"),
            "the start-up handshake never asks for the automatic finish"
        );

        let src = include_str!("update.rs");
        let production = &src[..src.find("#[cfg(test)]").expect("no test module")];
        let start = production
            .find("pub async fn finish_backend_if_desktop_ahead")
            .expect("update.rs has no automatic finish");
        let automatic = &production[start
            ..production
                .find("/// The update a chat message asked for")
                .expect("the automatic finish has no end")];
        // Once per mismatch is claimed before anything runs...
        let claim = automatic
            .find("AUTO_FINISH_ATTEMPTS.claim(")
            .expect("the automatic finish has no once-per-mismatch record");
        let run = automatic
            .find("crate::backend_update::run(")
            .expect("the automatic finish never runs the backend half");
        let run_call = &automatic[run..automatic
            .find("\n    .await;")
            .filter(|end| *end > run)
            .unwrap_or(automatic.len())];
        for part in [
            "app,",
            "\"responsive\"",
            "&label",
            "previous_release.as_deref()",
        ] {
            assert!(
                run_call.contains(part),
                "the automatic finish's backend run no longer carries `{part}`:\n{run_call}"
            );
        }
        assert!(
            claim < run,
            "the automatic finish runs before it claims its attempt"
        );
        // ...the same runner and the same default pace the button uses...
        assert!(
            automatic.contains("backend_update::mode_plan_for"),
            "the automatic finish invents its own pace instead of reading the tool's"
        );
        // ...and it never installs the desktop half, because it runs only after
        // the desktop was already installed by the Windows installer.
        for forbidden in ["install_now(", "install_update(", "prepare_desktop_half("] {
            assert!(
                !automatic.contains(forbidden),
                "the automatic backend finish reaches `{forbidden}`"
            );
        }
        // The wait for the restarted backend is bounded, never a retry loop of
        // the update itself.
        assert!(
            automatic.contains("for _ in 0..5"),
            "the restart-and-read wait is not bounded"
        );
        // Its two endings are the PURE functions above, not sentences written
        // at the call site: the failure ending must never say the desktop was
        // not installed (measured false 2026-11-21 00:28 PT), and the success
        // ending is only reachable from the in-sync read-back.
        assert!(
            automatic.contains("auto_finish_failed_words("),
            "the automatic finish writes its failure line at the call site"
        );
        assert!(
            automatic.contains("auto_finish_ok_words("),
            "the automatic finish writes its success line at the call site"
        );
    }

    /// The baseline for the release's NEW tool defaults (2026-11-21): the build
    /// the desktop ran BEFORE the installer that just finished. The reconcile is
    /// the only place that knows it, and every step after it reads it from here.
    #[test]
    fn the_build_the_installer_replaced_is_remembered_for_the_release_steps() {
        // Before any finished install there is no such build: the callers fall
        // back to this binary's own commit, which is the same release.
        assert_eq!(remember_previous_desktop_build(None), None);
        assert_eq!(previous_desktop_build(), None);
        // Whitespace is not a commit.
        assert_eq!(remember_previous_desktop_build(Some("  ")), None);
        let remembered = remember_previous_desktop_build(Some("7add1b7c1d5f"));
        assert_eq!(remembered.as_deref(), Some("7add1b7c1d5f"));
        assert_eq!(previous_desktop_build().as_deref(), Some("7add1b7c1d5f"));
        // One value per process; a second finished install replaces it.
        remember_previous_desktop_build(Some("97edfab81dd4"));
        assert_eq!(previous_desktop_build().as_deref(), Some("97edfab81dd4"));
        // Leave the process as it was for anything else that reads it.
        remember_previous_desktop_build(None);
        assert_eq!(previous_desktop_build(), None);
    }

    /// The wiring of the two release-file steps: the in-app press passes the
    /// running build as the baseline; the automatic finish prefers the build the
    /// installer replaced; the reconcile stores it only for a FINISHED install.
    #[test]
    fn the_release_file_steps_are_wired_to_the_right_baseline() {
        let src = include_str!("update.rs");
        let both = &src[src
            .find("pub async fn update_both")
            .expect("update.rs has no update_both")..];
        let both = &both[..both
            .find("// ---- 2. the executable")
            .expect("update_both has no desktop half")];
        assert!(
            both.contains("let previous_release = crate::backend_update::app_commit();"),
            "the in-app press no longer passes the running build as the baseline"
        );
        assert!(
            both.contains("previous_release.as_deref()"),
            "the in-app press never gives the backend tool its baseline"
        );

        let start = src
            .find("pub async fn finish_backend_if_desktop_ahead")
            .expect("update.rs has no automatic finish");
        let automatic = &src[start
            ..src
                .find("/// The update a chat message asked for")
                .expect("the automatic finish has no end")];
        assert!(
            automatic
                .contains("previous_desktop_build().or_else(crate::backend_update::app_commit)"),
            "the automatic finish does not prefer the build the installer replaced"
        );

        let reconcile = &src[src
            .find("pub fn reconcile_pending_at_startup")
            .expect("update.rs has no startup reconcile")..];
        let reconcile = &reconcile[..reconcile.find("\n}\n").expect("it has no end")];
        assert!(
            reconcile.contains("remember_previous_desktop_build(pending.app_commit.as_deref())"),
            "the startup reconcile no longer remembers the replaced build"
        );
        assert!(
            reconcile.contains("matches!(ending, DesktopEnding::Finished { .. })"),
            "the replaced build is remembered for an install that did not finish"
        );
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
        let said = ending_words(&ending, Some("333333333333"), Some("222222222222"), None);
        assert!(said.contains("is now 0.2.500"), "{said}");
        assert!(said.contains("was 0.2.412"), "{said}");
        // A finished desktop half plus a backend half that ended `ok` is NOT
        // enough to say both halves are done: they must be the same RELEASE.
        // These two commits differ, so the sentence may not claim it - and this
        // is the assertion that would have caught the card the owner read on
        // 2026-11-24, which said "both halves are done ... they differ".
        assert!(!said.contains("both halves are done"), "{said}");
        assert!(
            said.contains("The backend half had already finished"),
            "{said}"
        );
        // ...and the comparison is part of the same sentence, from the NEW app's
        // commit, so "both halves" is never just "both ran". With no folder to
        // ask, it must say the newer one could not be read rather than guess.
        assert!(said.contains("they differ"), "{said}");
        assert!(
            said.contains("which one is newer could not be read"),
            "{said}"
        );
        assert!(said.contains("222222222222"), "{said}");
        assert!(said.contains("333333333333"), "{said}");
    }

    #[test]
    fn one_release_is_the_only_thing_that_may_say_both_halves_are_done() {
        let pending = a_pending("0.2.500", true, Some(an_ok_backend_half()));
        let ending = reconcile(Some(&pending), "0.2.500").expect("a record was there");
        let same = ending_words(&ending, Some("222222222222"), Some("222222222222"), None);
        assert!(same.contains("Both halves are done."), "{same}");
        assert!(same.contains("they match"), "{same}");
        // With no commit for either half, nothing may be claimed - an unreadable
        // answer must never read as a match.
        let unknown = ending_words(&ending, None, None, None);
        assert!(!unknown.contains("Both halves are done."), "{unknown}");
        assert!(unknown.contains("cannot be compared"), "{unknown}");
    }

    #[test]
    fn a_partial_backend_half_may_never_be_painted_as_both_done() {
        let partial = BackendHalf {
            state: "partial".to_string(),
            detail: "Patched, unproven.".to_string(),
        };
        let pending = a_pending("0.2.500", true, Some(partial));
        let ending = reconcile(Some(&pending), "0.2.500").expect("a record was there");
        let said = ending_words(&ending, Some("333333333333"), Some("222222222222"), None);
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
        let said = ending_words(&ending, None, None, None);
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
        let said = ending_words(&ending, Some("111111111111"), Some("222222222222"), None);
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
        let said = ending_words(&ending, Some("111111111111"), Some("222222222222"), None);
        assert!(said.contains("has not taken effect"), "{said}");
        assert!(said.contains("cancelled"), "{said}");
        assert!(!said.contains("is now 0.2.500"), "{said}");
    }

    #[test]
    fn a_third_version_is_never_claimed_either_way() {
        let pending = a_pending("0.2.500", true, None);
        let ending = reconcile(Some(&pending), "0.2.501").expect("a record was there");
        assert!(matches!(ending, DesktopEnding::OtherVersion { .. }));
        let said = ending_words(&ending, Some("111111111111"), Some("222222222222"), None);
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

    /// DEF-036: the startup line is the ONE place the app says what it is, and
    /// the update answer reads it to compare the desktop with the backend.
    /// `Cargo.toml` and the committed `tauri.conf.json` say `0.2.0` for ever
    /// while the release build stamps `0.2.<run number>`, so reading the CRATE
    /// version wrote "Jarvis Desktop 0.2.0 starting" into every log while the
    /// About card said 0.2.503 - and the answer could then never match it
    /// against the installed version, so it said "I cannot tell" on the
    /// owner's own PC (measured 2026-11-25).
    #[test]
    fn the_startup_line_names_the_installed_version_not_the_crate_version() {
        let src = include_str!("lib.rs");
        // Built at compile time so this test does not contain the very string
        // it forbids: the needle would otherwise match its own assertion.
        let crate_version = concat!("env!(\"CARGO_PKG", "_VERSION\")");
        assert!(
            !src.contains(crate_version),
            "the startup line prints the crate version (0.2.0) instead of the \
             installed app's version, so the update answer can never match it"
        );
        assert!(
            src.contains(".package_info().version,"),
            "the startup line does not name the running app's own version"
        );
    }
}
