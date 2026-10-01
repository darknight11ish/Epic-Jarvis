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
//!   ([`crate::folders::picker`], not a second copy of it), then `POST
//!   /api/backup/folder {"path"}`: the PC raises ONE approval card. Held on
//!   a stale link (before the picker even opens): it lets Jarvis write
//!   somewhere new.
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
/// sentence otherwise (403 the PC only, 400 a wrong code or bad folder,
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
#[tauri::command]
pub async fn set_backup_folder(app: AppHandle) -> Result<serde_json::Value, String> {
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let (tx, rx) = tokio::sync::oneshot::channel();
    std::thread::spawn(move || {
        let _ = tx.send(picker::pick(picker::What::Folder));
    });
    let path = rx
        .await
        .map_err(|_| "the dialog closed unexpectedly".to_string())??;
    let Some(path) = path else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
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
        change_answer, held_on_stale, read_answer, BACKUP_MISSING, DELETE_OLDER_PATH, FOLDER_PATH,
        NOW_PATH, RESTORE_PATH,
    };

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
    }
}
