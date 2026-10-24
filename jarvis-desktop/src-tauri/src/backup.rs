//! Settings -> "Backups" (the owner's decision of 2026-09-27, CLAUDE.md:
//! "one locked backup file into a folder the owner picks ... locked with a
//! recovery code only the owner has (shown once) ... Jarvis keeps only the
//! last few"; backend/jarvis_backup.py, backup.patch; JARVIS-API.md section
//! 44).
//!
//! Six commands, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_backup`] - `GET /api/backup`: the folder, whether a card is
//!   waiting, the last backup and the last restore's outcome (a one-time
//!   recovery code included exactly once, for the safety backup a restore
//!   makes of the CURRENT state before it changes anything). A read, never
//!   held.
//! * [`set_backup_folder`] - the Windows folder picker
//!   ([`crate::folders::picker`], not a second copy of it), the PC's own checks
//!   on the folder ([`destination_problem`]), and then `POST
//!   /api/backup/folder {"path"}`: the PC raises ONE approval card. Held on
//!   a stale link (before the picker even opens): it lets Jarvis write
//!   somewhere new.
//!
//!   **The folder is checked here, before the card**, in the words the owner
//!   reads on the panel: it must be a folder that is there, Jarvis must be able
//!   to write into it, and it must be outside Jarvis's own data folder and
//!   outside the program folders. A folder on a drive that is not the one
//!   Windows is on is allowed and comes back as a question rather than a
//!   refusal. The backend's own `check_folder` still runs and is still the
//!   authority - this is the half that can say *why* in the window he is
//!   looking at, before an approval card is ever raised.
//!
//!   The one destination is `~/.openjarvis/backup.json`'s `folder` key (the
//!   owner's decision of 2026-10-14): the weekly personal-data snapshot tool
//!   (`tools/jarvis_data_backup.py`) reads the same key at run time, so both
//!   backups land in the folder chosen here.
//! * [`backup_now`] - `POST /api/backup/now {}`: no card - the folder was
//!   already approved. Not held on a stale link: nothing here depends on a
//!   live event stream, only on the folder already being set.
//! * [`list_backups`] - `GET /api/backup/list`: the files in the folder,
//!   newest first. A read.
//! * [`preview_restore`] - `POST /api/backup/restore/preview {"name",
//!   "code"}`: decrypts to read counts and the backup's own date - never
//!   any other content. Changes nothing, so not held on a stale link.
//! * [`restore_backup`] - `POST /api/backup/restore {"name", "code"}`: ONE
//!   approval card that ALWAYS needs Windows Hello on the PC
//!   (jarvis_owner_check.PC_ONLY_ACTIONS), whatever the gate's own risk
//!   table says. Held on a stale link: it replaces memory, chat history,
//!   settings and notes.
//!
//! The window never gets a file system of its own: the folder picker runs in
//! Rust, and only the path the owner chose is sent - to this PC's Jarvis,
//! nowhere else.

use std::path::{Component, Path, PathBuf};
use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};
use crate::folders::picker;

pub(crate) const PATH: &str = "/api/backup";
const FOLDER_PATH: &str = "/api/backup/folder";
const NOW_PATH: &str = "/api/backup/now";
const LIST_PATH: &str = "/api/backup/list";
const PREVIEW_PATH: &str = "/api/backup/restore/preview";
const RESTORE_PATH: &str = "/api/backup/restore";
const DELETE_OLDER_PATH: &str = "/api/backup/delete-older";
/// The route a PHONE-started run is written with, from either side (2026-10-24,
/// the owner's decision). The route already existed and is unchanged: since the
/// one-tap upgrade any caller holding the run's one-time code may commit, so
/// the phone's own finish press AND this PC's typed-code fallback both use it -
/// and the write itself is still done here, by the backend, into this PC's
/// folder.
const COMMIT_PATH: &str = "/api/backup/commit";

/// What a backend without `jarvis_backup.py` / `backup.patch` is told. The
/// phone says the same about its read-only status line.
pub(crate) const BACKUP_MISSING: &str =
    "Your PC's Jarvis cannot make backups yet - run apply-patches.ps1 on this PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// Making one backup snapshots a few SQLite databases and zips a folder or
/// two - quick, but not instant on a slow disk.
const BACKUP_TIMEOUT: Duration = Duration::from_secs(60);
/// A restore's Argon2id step runs twice (the preview already ran once, but
/// this request decrypts again rather than trust a ticket held in memory)
/// plus the safety backup and writing every file back.
const RESTORE_TIMEOUT: Duration = Duration::from_secs(90);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// A read's answer (GET /api/backup, GET /api/backup/list): the PC's own
/// body on 2xx, [`BACKUP_MISSING`] from a PC without the route, and the
/// PC's own sentence otherwise.
pub(crate) fn read_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": BACKUP_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A change's answer (setting the folder, backing up, previewing or
/// restoring): the PC's own body on a 2xx (200 done, 202 a card is up),
/// [`BACKUP_MISSING`] from a PC without the route, and the PC's own
/// sentence otherwise (traditionally 403 the PC only, 400 a wrong code or bad
/// folder,
/// 409 no folder set / already waiting).
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(BACKUP_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// Whether a change waits for a live event stream: setting the folder (a
/// card) and restoring (a card that needs Windows Hello) do; "Back up now",
/// listing and previewing never do - none of them raises a card.
pub(crate) fn held_on_stale(path: &str) -> bool {
    path == FOLDER_PATH || path == RESTORE_PATH || path == DELETE_OLDER_PATH
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

async fn get(app: &AppHandle, path: &str, timeout: Duration) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(timeout))?
        .get(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    read_answer(status, &body)
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    timeout: Duration,
) -> Result<serde_json::Value, String> {
    if held_on_stale(path) && stale(app) {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(app);
    let response = jarvis_client(Some(timeout))?
        .post(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    change_answer(status, &text)
}

/// The folder the picker returned while the window asks about the drive it is
/// on. Kept in Rust on purpose: "yes" can only ever mean the folder the picker
/// produced, never a path the page made up - the window has no file system of
/// its own, and that is the whole reason the picker runs here.
static AWAITING_DRIVE_ANSWER: std::sync::Mutex<Option<String>> = std::sync::Mutex::new(None);

/// A path that can be compared with another one: resolved when it is there,
/// lower-cased (Windows does not care about case) and with no trailing slash.
///
/// `canonicalize` answers a path that EXISTS in Windows' verbatim form
/// (`\\?\C:\...`) and one that does not in the plain form, so the prefix is
/// stripped before comparing: without that, a chosen folder that exists would
/// never look like it was inside a settings folder that does not exist yet, and
/// the check would pass in silence.
fn real(path: &Path) -> PathBuf {
    let full = std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    let text = full.to_string_lossy().to_lowercase();
    let text = text.strip_prefix(r"\\?\").unwrap_or(&text).to_string();
    PathBuf::from(text.trim_end_matches(['\\', '/']).to_string())
}

/// Whether `child` is `parent` itself or inside it. Component-wise, so
/// `C:\a\bc` is not inside `C:\a\b`.
pub(crate) fn inside(child: &Path, parent: &Path) -> bool {
    let (c, p) = (real(child), real(parent));
    c == p || c.starts_with(&p)
}

/// The drive a path names (`"C:"`), or `None` when it names none.
pub(crate) fn drive_of(path: &Path) -> Option<String> {
    match path.components().next() {
        Some(Component::Prefix(prefix)) => Some(
            prefix
                .as_os_str()
                .to_string_lossy()
                .trim_end_matches(['\\', '/'])
                .to_uppercase(),
        ),
        _ => None,
    }
}

/// Why this folder cannot be the backup folder, in the owner's own words;
/// `None` when it can.
///
/// Pure on purpose - whether the folder is there and whether it can be written
/// into are passed in - so every branch is a test, and no test has to make an
/// unwritable folder on Windows to reach one. The rules are the same three the
/// snapshot tool applies (`tools/jarvis_data_backup.py`, check_chosen_folder),
/// written once in `docs/DATA-BACKUP.md`; this is the half that says so in the
/// window, before a card is raised.
pub(crate) fn destination_problem(
    folder: &Path,
    settings_dir: Option<&Path>,
    program_dirs: &[PathBuf],
    exists: bool,
    writable: bool,
) -> Option<String> {
    if !exists {
        return Some(format!(
            "{} is not there any more. Choose the folder again.",
            folder.display()
        ));
    }
    if !writable {
        return Some(format!(
            "Jarvis cannot write into {}. Pick another folder, or check that the disk is \
             not full.",
            folder.display()
        ));
    }
    if let Some(settings) = settings_dir {
        if inside(folder, settings) {
            return Some(format!(
                "{} is inside Jarvis's own data folder - the very thing being backed up. A \
                 backup kept inside what it is backing up is not a backup, so pick a folder \
                 outside it.",
                folder.display()
            ));
        }
    }
    for program in program_dirs {
        if inside(folder, program) {
            return Some(format!(
                "{} is inside {}, where Jarvis's own program lives. A backup kept there is \
                 lost with the program - pick a folder outside it.",
                folder.display(),
                program.display()
            ));
        }
    }
    None
}

/// A sentence to put in front of the owner when the folder is not on the drive
/// Windows is on; `None` when it is.
///
/// A question, not a refusal: another disk is a perfectly good place for a
/// backup, and only he knows whether it stays plugged in.
pub(crate) fn other_drive_note(folder: &Path, system_drive: &str) -> Option<String> {
    let here = drive_of(folder)?;
    let system = system_drive.trim_end_matches(['\\', '/']).to_uppercase();
    if system.is_empty() || here == system {
        return None;
    }
    Some(format!(
        "{} is on drive {}, and Windows itself is on {}.",
        folder.display(),
        here,
        system
    ))
}

/// Whether a file can actually be created in `dir`.
///
/// One empty file with this process's id in its name, removed at once: Windows
/// has no useful "is this folder writable" flag (a folder's *read-only*
/// attribute means something else entirely), so trying it is the only honest
/// test. Nothing else in the folder is touched.
fn writable_dir(dir: &Path) -> bool {
    let probe = dir.join(format!(".jarvis-write-test-{}", std::process::id()));
    match std::fs::write(&probe, b"") {
        Ok(()) => {
            let _ = std::fs::remove_file(&probe);
            true
        }
        Err(_) => false,
    }
}

/// The folder Jarvis keeps its own data in - `OPENJARVIS_CONFIG_DIR`, then
/// `JARVIS_CONFIG_DIR`, then `~/.openjarvis`: the same order, and the same two
/// variables, that the backend (`jarvis_framework._config_dir`) and the
/// snapshot tool use, so this check is about the folder the data is really in.
fn settings_dir(app: &AppHandle) -> Option<PathBuf> {
    for name in ["OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"] {
        if let Some(explicit) = std::env::var_os(name) {
            return Some(PathBuf::from(explicit));
        }
    }
    app.path().home_dir().ok().map(|h| h.join(".openjarvis"))
}

/// The program folders a backup must never be kept in: this app's own, and the
/// folder holding `jarvis_hud.py` when the app can see where it is.
fn program_dirs(app: &AppHandle) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            out.push(dir.to_path_buf());
        }
    }
    if let Some(backend) = crate::backend_update::locate(app).backend {
        out.push(PathBuf::from(backend));
    }
    out
}

/// `Err(refusal)` when the folder cannot be used, `Ok(Some(question))` when it
/// can but is on another drive, `Ok(None)` when there is nothing to say.
fn check_chosen_folder(app: &AppHandle, path: &str) -> Result<Option<String>, String> {
    let folder = PathBuf::from(path);
    let exists = folder.is_dir();
    match destination_problem(
        &folder,
        settings_dir(app).as_deref(),
        &program_dirs(app),
        exists,
        exists && writable_dir(&folder),
    ) {
        Some(refusal) => Err(refusal),
        None => Ok(other_drive_note(
            &folder,
            &std::env::var("SystemDrive").unwrap_or_else(|_| "C:".to_string()),
        )),
    }
}

/// The folder, whether a card is waiting, the last backup and the last
/// restore's outcome (with a one-time recovery code, exactly once). A read.
#[tauri::command]
pub async fn get_backup(app: AppHandle) -> Result<serde_json::Value, String> {
    get(&app, PATH, READ_TIMEOUT).await
}

/// The files in the backup folder, newest first. A read.
#[tauri::command]
pub async fn list_backups(app: AppHandle) -> Result<serde_json::Value, String> {
    get(&app, LIST_PATH, READ_TIMEOUT).await
}

/// Runs the Windows folder picker on its own thread (the same reason as
/// "Folders Jarvis may look in": the dialog needs a single-threaded COM
/// apartment). Held on a stale link before the picker even opens.
///
/// The folder is then checked (`check_chosen_folder`) before the backend is
/// asked for anything: a refusal comes back as plain words and no card is
/// raised, and a folder on another drive comes back as a question. Answering
/// that question - a second call with `confirm: true` - uses the folder the
/// picker returned, held in [`AWAITING_DRIVE_ANSWER`], so the window can never
/// name a folder the owner did not pick.
#[tauri::command]
pub async fn set_backup_folder(
    app: AppHandle,
    confirm: Option<bool>,
) -> Result<serde_json::Value, String> {
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let path = if confirm == Some(true) {
        let remembered = AWAITING_DRIVE_ANSWER
            .lock()
            .ok()
            .and_then(|mut held| held.take());
        match remembered {
            Some(path) => path,
            None => {
                return Err(
                    "That folder is not waiting to be confirmed any more - choose \
                            it again."
                        .to_string(),
                )
            }
        }
    } else {
        let (tx, rx) = tokio::sync::oneshot::channel();
        std::thread::spawn(move || {
            let _ = tx.send(picker::pick(picker::What::Folder));
        });
        let path = rx
            .await
            .map_err(|_| "the dialog closed unexpectedly".to_string())??;
        match path {
            Some(path) => path,
            None => return Ok(serde_json::json!({ "cancelled": true })),
        }
    };
    match check_chosen_folder(&app, &path) {
        Err(refusal) => {
            // Shown on the panel, before any approval card: nothing was sent to
            // the backend, so nothing has changed.
            return Ok(serde_json::json!({
                "ok": false, "refused": true, "path": path, "error": refusal,
            }));
        }
        Ok(Some(question)) if confirm != Some(true) => {
            if let Ok(mut held) = AWAITING_DRIVE_ANSWER.lock() {
                *held = Some(path.clone());
            }
            return Ok(serde_json::json!({
                "confirm": true, "path": path, "message": question,
            }));
        }
        Ok(_) => {}
    }
    post(
        &app,
        FOLDER_PATH,
        serde_json::json!({ "path": path }),
        BACKUP_TIMEOUT,
    )
    .await
}

/// "Back up now": no card, not held on a stale link - the folder was
/// already approved and nothing here needs a live event stream.
#[tauri::command]
pub async fn backup_now(app: AppHandle) -> Result<serde_json::Value, String> {
    post(&app, NOW_PATH, serde_json::json!({}), BACKUP_TIMEOUT).await
}

/// "Write it" under "A backup was started from your phone": finishes the run
/// the PHONE asked for, using the recovery code the phone showed (2026-10-24).
///
/// The body is exactly `{"code": ...}` - `request_commit` compares only the
/// code, never the run's `id`, so the PC needs nothing from the phone but what
/// the owner wrote down. The route is the existing `/api/backup/commit`; no
/// route was added and the gate on it is untouched. This is the FALLBACK now:
/// since the owner's one-tap upgrade the phone's own finish press writes the
/// file, and this command exists for a run the phone left waiting (phone
/// unavailable) - the same route, the same code, the same one-file guarantee.
///
/// **NOT held on a stale link** ([`held_on_stale`]), exactly like "Back up
/// now": it raises no approval card, so there is no card's answer to wait for.
/// The write is the owner's own click with the code in hand - rule 4 is about
/// approvals, and none is raised anywhere on this path.
#[tauri::command]
pub async fn finish_phone_backup(
    app: AppHandle,
    code: String,
) -> Result<serde_json::Value, String> {
    post(
        &app,
        COMMIT_PATH,
        serde_json::json!({ "code": code }),
        BACKUP_TIMEOUT,
    )
    .await
}

/// Pick a file, type its recovery code, see counts and a date - never
/// content. Changes nothing.
#[tauri::command]
pub async fn preview_restore(
    app: AppHandle,
    name: String,
    code: String,
) -> Result<serde_json::Value, String> {
    post(
        &app,
        PREVIEW_PATH,
        serde_json::json!({ "name": name, "code": code }),
        BACKUP_TIMEOUT,
    )
    .await
}

/// Restore from a backup: ONE approval card that always needs Windows
/// Hello on the PC. Held on a stale link.
#[tauri::command]
pub async fn restore_backup(
    app: AppHandle,
    name: String,
    code: String,
) -> Result<serde_json::Value, String> {
    post(
        &app,
        RESTORE_PATH,
        serde_json::json!({ "name": name, "code": code }),
        RESTORE_TIMEOUT,
    )
    .await
}

/// "Delete older backups now": makes one fresh locked backup first, then
/// deletes older backup files from the folder. Raises ONE approval card.
/// Held on a stale link.
#[tauri::command]
pub async fn delete_older_backups(app: AppHandle) -> Result<serde_json::Value, String> {
    post(
        &app,
        DELETE_OLDER_PATH,
        serde_json::json!({}),
        RESTORE_TIMEOUT,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::{
        change_answer, destination_problem, drive_of, held_on_stale, inside, other_drive_note,
        read_answer, BACKUP_MISSING, COMMIT_PATH, DELETE_OLDER_PATH, FOLDER_PATH, NOW_PATH,
        RESTORE_PATH,
    };
    use std::path::{Path, PathBuf};

    #[test]
    fn a_pc_without_it_says_so() {
        let got = read_answer(404, "").unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], BACKUP_MISSING);
        assert_eq!(change_answer(404, "").unwrap_err(), BACKUP_MISSING);
        assert!(read_answer(200, "{nope").is_err());
    }

    #[test]
    fn a_real_view_is_passed_on_unchanged() {
        let body = serde_json::json!({
            "available": true, "folder": "C:\\Users\\owner\\Backups", "keep": 5,
            "last_backup": {"ok": true, "name": "jarvis-backup-20260927-030000.jbak",
                            "at": 1.0, "counts": {}, "error": ""},
            "pending_folder_card": null, "last_folder_card": null,
            "pending_restore_card": null, "last_restore": null,
            "erase_limit": "words",
        });
        let got = read_answer(200, &body.to_string()).unwrap();
        assert_eq!(got, body);
    }

    #[test]
    fn the_pcs_refusal_from_another_device_is_its_own_words() {
        let body = serde_json::json!({"ok": false, "error": "Backups are set up on the PC only \
            (Settings, Backups).", "pc_only": true});
        assert!(change_answer(403, &body.to_string()).is_err());
    }

    #[test]
    fn a_wrong_code_is_its_own_words_not_a_generic_refusal() {
        let body = serde_json::json!({"ok": false, "error": "that recovery code does not open \
            this backup", "wrong_code": true});
        let err = change_answer(400, &body.to_string()).unwrap_err();
        assert!(err.contains("recovery code"), "{err}");
    }

    #[test]
    fn setting_the_folder_restoring_and_deleting_older_wait_for_a_live_link() {
        assert!(held_on_stale(FOLDER_PATH));
        assert!(held_on_stale(RESTORE_PATH));
        assert!(held_on_stale(DELETE_OLDER_PATH));
        assert!(!held_on_stale(NOW_PATH));
        assert!(!held_on_stale(super::LIST_PATH));
        assert!(!held_on_stale(super::PREVIEW_PATH));
        // "Write it" under the phone's run raises NO card, exactly like "Back up
        // now", so it must not be held: being held would refuse the owner's own
        // click on a link that is merely catching up, for a card that never was.
        assert!(!held_on_stale(COMMIT_PATH));
    }

    /// The PC finishes a run the PHONE started (2026-10-24). The route is the
    /// EXISTING commit route - not a new one - and the body is exactly the code
    /// the phone showed, because the backend compares only `body["code"]` and
    /// never the run's id.
    #[test]
    fn finishing_a_phone_started_backup_uses_the_existing_commit_route() {
        assert_eq!(COMMIT_PATH, "/api/backup/commit");
        assert_eq!(COMMIT_PATH, format!("{}/commit", super::PATH));
        let source = include_str!("backup.rs");
        let rest = source
            .split("pub async fn finish_phone_backup(")
            .nth(1)
            .expect("finish_phone_backup is in this file");
        let command = rest.split("#[tauri::command]").next().unwrap_or(rest);
        assert!(
            command.contains("COMMIT_PATH"),
            "it posts to the commit route"
        );
        assert!(
            command.contains(r#"serde_json::json!({ "code": code })"#),
            "the body is exactly the code, and nothing else: {command}"
        );
    }

    /// A dead run (409 `COMMIT_NO_RUN`) and a wrong code (400
    /// `COMMIT_WRONG_CODE`) both arrive as the backend's own plain words, so the
    /// panel cannot invent a friendlier - and false - second explanation.
    ///
    /// The old 403 `pc_only` sentence is deliberately NOT pinned any more
    /// (2026-10-24, the owner's one-tap decision): any caller holding the live
    /// run's code may commit, so there is no device refusal left in this route
    /// to reproduce on the panel.
    #[test]
    fn a_refused_finish_is_the_backends_own_sentence() {
        let gone = "That backup run has expired or was never started, so nothing was written. \
                    Ask for a backup again from your phone.";
        let err = change_answer(
            409,
            &serde_json::json!({"ok": false, "error": gone}).to_string(),
        )
        .unwrap_err();
        assert_eq!(err, gone);
        assert!(err.contains("nothing was written"), "{err}");

        let wrong = "That is not the code for the backup waiting to be written, so nothing was \
                     written and your folder is unchanged. Ask for a backup again.";
        let err = change_answer(
            400,
            &serde_json::json!({"ok": false, "error": wrong}).to_string(),
        )
        .unwrap_err();
        assert_eq!(err, wrong);
        assert!(
            err.contains("nothing was written"),
            "the refusal says nothing was written: {err}"
        );
    }

    /// The folders the two refusals below are about. What is *in* them does not
    /// matter to the rules - only whether one path is inside another - so no
    /// test makes a folder, and none touches a real one.
    fn settings() -> PathBuf {
        PathBuf::from(r"C:\Users\owner\.openjarvis")
    }

    fn programs() -> Vec<PathBuf> {
        vec![
            PathBuf::from(r"C:\Users\owner\Documents\Claude\Open jarvis files\Desktop program"),
            PathBuf::from(r"C:\Program Files\Jarvis"),
        ]
    }

    #[test]
    fn a_folder_that_is_gone_or_unwritable_is_refused_in_plain_words() {
        let gone = destination_problem(
            Path::new(r"D:\Backups"),
            Some(&settings()),
            &programs(),
            false,
            false,
        );
        assert!(
            gone.as_deref().is_some_and(|w| w.contains("not there")),
            "{gone:?}"
        );

        let locked = destination_problem(
            Path::new(r"C:\Users\owner\Backups"),
            Some(&settings()),
            &programs(),
            true,
            false,
        );
        assert!(
            locked
                .as_deref()
                .is_some_and(|w| w.contains("cannot write")),
            "{locked:?}"
        );
    }

    #[test]
    fn a_backup_inside_the_thing_being_backed_up_is_refused() {
        for folder in [
            r"C:\Users\owner\.openjarvis",
            r"C:\Users\owner\.openjarvis\backups",
        ] {
            let why = destination_problem(
                Path::new(folder),
                Some(&settings()),
                &programs(),
                true,
                true,
            );
            assert!(
                why.as_deref().is_some_and(|w| w.contains("not a backup")),
                "{folder}: {why:?}"
            );
        }
    }

    #[test]
    fn a_backup_in_a_program_folder_is_refused_and_the_neighbour_is_not() {
        let in_backend = destination_problem(
            Path::new(r"C:\Users\owner\Documents\Claude\Open jarvis files\Desktop program\snaps"),
            Some(&settings()),
            &programs(),
            true,
            true,
        );
        assert!(
            in_backend
                .as_deref()
                .is_some_and(|w| w.contains("lost with the program")),
            "{in_backend:?}"
        );

        // One letter out is a different folder and is allowed: the check is
        // component-wise, not a string prefix.
        let beside = destination_problem(
            Path::new(r"C:\Users\owner\Documents\Claude\Open jarvis files\Desktop programs"),
            Some(&settings()),
            &programs(),
            true,
            true,
        );
        assert_eq!(beside, None);

        // A folder OUTSIDE every protected one is fine - the normal case.
        let outside = destination_problem(
            Path::new(r"C:\Users\owner\Documents\Jarvis Backups"),
            Some(&settings()),
            &programs(),
            true,
            true,
        );
        assert_eq!(outside, None);
    }

    #[test]
    fn another_drive_is_a_question_and_the_system_drive_is_silent() {
        // What this function says is the two drives, by letter. It does NOT
        // carry the "unplugged" warning: that is the confirmation sentence the
        // PAGE adds beside this message (backup-settings.js, which appends "A
        // backup on a drive that gets unplugged is a backup that stops
        // happening."). An earlier version of this test asserted "unplugged"
        // here, in the Rust string, where it has never appeared - it failed on
        // CI (rust, 2026-10-15) on a message that was correct all along. The
        // assertion below is the contract: the note names the drive it is on.
        let other = other_drive_note(Path::new(r"D:\Backups"), "C:");
        assert!(
            other.as_deref().is_some_and(|w| w.contains("drive D:")),
            "{other:?}"
        );
        assert_eq!(other_drive_note(Path::new(r"c:\Backups"), "C:"), None);
        assert_eq!(other_drive_note(Path::new(r"C:\Backups"), "C:"), None);
        assert_eq!(drive_of(Path::new(r"D:\Backups")).as_deref(), Some("D:"));
    }

    #[test]
    fn a_verbatim_path_is_the_same_place_as_a_plain_one() {
        // `canonicalize` answers `\\?\C:\...` for a path that exists and the
        // plain form for one that does not, so the two spellings must compare
        // equal - otherwise a folder inside a settings folder that does not
        // exist yet would pass the check in silence.
        assert!(inside(
            Path::new(r"\\?\C:\Users\owner\.openjarvis\backups"),
            Path::new(r"C:\Users\owner\.openjarvis")
        ));
        assert!(inside(
            Path::new(r"C:\Users\owner\.openjarvis\backups"),
            Path::new(r"\\?\C:\Users\owner\.openjarvis")
        ));
    }

    #[test]
    fn inside_is_component_wise_and_ignores_case() {
        assert!(inside(
            Path::new(r"C:\Users\owner\.openjarvis\x"),
            Path::new(r"c:\users\owner\.openjarvis")
        ));
        assert!(inside(
            Path::new(r"C:\Users\owner\.openjarvis"),
            Path::new(r"C:\Users\owner\.openjarvis")
        ));
        assert!(!inside(
            Path::new(r"C:\Users\owner\.openjarvisx"),
            Path::new(r"C:\Users\owner\.openjarvis")
        ));
        assert!(!inside(Path::new(r"C:\Backups"), Path::new(r"C:\Backup")));
    }
}
