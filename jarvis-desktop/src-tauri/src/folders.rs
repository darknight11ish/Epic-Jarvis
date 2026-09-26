//! Settings -> "Folders Jarvis may look in" (the owner's decisions of
//! 2026-09-26: asking about PDFs and Word files, and bringing in a Notion
//! export; backend/documents.patch, jarvis_documents.py; JARVIS-API.md
//! section 35).
//!
//! Four commands, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_folders`] - `GET /api/folders`: the list, in the PC's own words,
//!   whether this request may add (the PC decides: only a request from the PC
//!   itself), a waiting card, and whether PDF and Word reading is installed.
//!   A read, never held.
//! * [`add_folder`] - the Windows folder picker, then `POST /api/folders/add
//!   {"path"}`: the PC raises ONE approval card. It lets Jarvis see more, so
//!   it is held while the event stream is stale (rule 4).
//! * [`remove_folder`] - `POST /api/folders/remove {"path"}`: at once, never
//!   held - it only lets Jarvis see less.
//! * [`import_notion`] - the Windows file picker for the `.zip` Notion made,
//!   then `POST /api/folders/import {"zip", "into"}`: the PC unzips it into a
//!   new folder inside `into`, which must be on the list. Held on a stale
//!   link. No card: the owner picked the file and the folder here.
//!
//! The window never gets a file system of its own: the pickers run here, and
//! only the path the owner chose is sent - to this PC's Jarvis, nowhere else.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const FOLDERS_PATH: &str = "/api/folders";
const ADD_PATH: &str = "/api/folders/add";
const REMOVE_PATH: &str = "/api/folders/remove";
const IMPORT_PATH: &str = "/api/folders/import";

/// What a backend without `jarvis_documents.py` / `documents.patch` is told.
/// The phone says the same (`Folders.MISSING`), and so does folders.js.
pub(crate) const FOLDERS_MISSING: &str =
    "Your PC's Jarvis cannot look in folders yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);
/// Unzipping a big export (up to 1 GB, 20,000 files) takes a while.
const IMPORT_TIMEOUT: Duration = Duration::from_secs(600);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_folders`]'s reading of the answer, tested against the contract file
/// (the real `view()`).
pub(crate) fn folders_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("folders").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": FOLDERS_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A change's answer: the PC's own body on a 2xx (200 done, 202 a card is
/// up), [`FOLDERS_MISSING`] from a PC without the route, and the PC's own
/// sentence otherwise (403 "the PC only", 400 a refused folder or zip, 409).
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(FOLDERS_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// Whether a change waits for a live event stream: adding (a card) and
/// bringing in an export do; removing never does.
pub(crate) fn held_on_stale(path: &str) -> bool {
    path != REMOVE_PATH
}

/// The folders Jarvis may look in: `GET /api/folders`. A read.
#[tauri::command]
pub async fn get_folders(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{FOLDERS_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    folders_answer(status, &body)
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

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

/// Runs a picker on its own thread: the Windows dialogs need a
/// single-threaded COM apartment, which a shared runtime worker cannot
/// promise (the same reason as the memory export's save dialog).
async fn pick(what: picker::What) -> Result<Option<String>, String> {
    let (tx, rx) = tokio::sync::oneshot::channel();
    std::thread::spawn(move || {
        let _ = tx.send(picker::pick(what));
    });
    rx.await
        .map_err(|_| "the dialog closed unexpectedly".to_string())?
}

/// Add ONE folder: the owner picks it, then the PC raises one approval card.
/// Held on a stale link (before the picker even opens).
#[tauri::command]
pub async fn add_folder(app: AppHandle) -> Result<serde_json::Value, String> {
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let Some(path) = pick(picker::What::Folder).await? else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
    post(
        &app,
        ADD_PATH,
        serde_json::json!({ "path": path }),
        WRITE_TIMEOUT,
    )
    .await
}

/// Remove ONE folder from the list. At once, never held.
#[tauri::command]
pub async fn remove_folder(app: AppHandle, path: String) -> Result<serde_json::Value, String> {
    post(
        &app,
        REMOVE_PATH,
        serde_json::json!({ "path": path }),
        WRITE_TIMEOUT,
    )
    .await
}

/// Bring in a Notion export: the owner picks the `.zip`, the PC unzips it
/// into a new folder inside `into`. Held on a stale link.
#[tauri::command]
pub async fn import_notion(app: AppHandle, into: String) -> Result<serde_json::Value, String> {
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let Some(zip) = pick(picker::What::Zip).await? else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
    post(
        &app,
        IMPORT_PATH,
        serde_json::json!({ "zip": zip, "into": into }),
        IMPORT_TIMEOUT,
    )
    .await
}

/// The Windows "Select folder" and "Open" dialogs, and nothing else.
#[cfg(windows)]
mod picker {
    use windows::core::w;
    use windows::Win32::Foundation::ERROR_CANCELLED;
    use windows::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_INPROC_SERVER,
        COINIT_APARTMENTTHREADED, COINIT_DISABLE_OLE1DDE,
    };
    use windows::Win32::UI::Shell::Common::COMDLG_FILTERSPEC;
    use windows::Win32::UI::Shell::{
        FileOpenDialog, IFileOpenDialog, FOS_FILEMUSTEXIST, FOS_FORCEFILESYSTEM, FOS_PATHMUSTEXIST,
        FOS_PICKFOLDERS, SIGDN_FILESYSPATH,
    };

    #[derive(Clone, Copy)]
    pub enum What {
        Folder,
        Zip,
    }

    /// `Ok(None)` when the owner cancelled.
    pub fn pick(what: What) -> Result<Option<String>, String> {
        // SAFETY: plain COM calls on this thread, which is ours alone and is
        // initialised as a single-threaded apartment first. Every pointer
        // handed out by COM is released: the interfaces by their Drop, the
        // path string by CoTaskMemFree.
        unsafe {
            let init = CoInitializeEx(None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
            if init.is_err() {
                return Err(format!("could not open the dialog: {init:?}"));
            }
            let out = show(what);
            CoUninitialize();
            out
        }
    }

    unsafe fn show(what: What) -> Result<Option<String>, String> {
        let fail = |e: windows::core::Error| format!("the dialog failed: {e}");
        let dialog: IFileOpenDialog =
            CoCreateInstance(&FileOpenDialog, None, CLSCTX_INPROC_SERVER).map_err(fail)?;
        let options = dialog.GetOptions().map_err(fail)?;
        match what {
            What::Folder => {
                dialog
                    .SetTitle(w!("Choose a folder Jarvis may look in"))
                    .map_err(fail)?;
                dialog
                    .SetOptions(options | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)
                    .map_err(fail)?;
            }
            What::Zip => {
                let types = [COMDLG_FILTERSPEC {
                    pszName: w!("Notion export (.zip)"),
                    pszSpec: w!("*.zip"),
                }];
                dialog.SetFileTypes(&types).map_err(fail)?;
                dialog
                    .SetTitle(w!("Choose the .zip Notion made"))
                    .map_err(fail)?;
                dialog
                    .SetOptions(
                        options | FOS_FORCEFILESYSTEM | FOS_FILEMUSTEXIST | FOS_PATHMUSTEXIST,
                    )
                    .map_err(fail)?;
            }
        }
        if let Err(e) = dialog.Show(None) {
            if e.code() == ERROR_CANCELLED.to_hresult() {
                return Ok(None);
            }
            return Err(fail(e));
        }
        let item = dialog.GetResult().map_err(fail)?;
        let raw = item.GetDisplayName(SIGDN_FILESYSPATH).map_err(fail)?;
        let path = raw.to_string();
        CoTaskMemFree(Some(raw.0 as *const _));
        path.map(Some)
            .map_err(|e| format!("the chosen path could not be read: {e}"))
    }
}

/// Not Windows: this app is only built for Windows; say so rather than guess.
#[cfg(not(windows))]
mod picker {
    #[derive(Clone, Copy)]
    pub enum What {
        Folder,
        Zip,
    }

    pub fn pick(what: What) -> Result<Option<String>, String> {
        let _ = matches!(what, What::Folder | What::Zip);
        Err("choosing a folder or a file needs the Windows dialog".to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::{
        change_answer, folders_answer, held_on_stale, ADD_PATH, FOLDERS_MISSING, IMPORT_PATH,
        REMOVE_PATH,
    };

    /// The real answers, made by `tools/gen_folders_cases.py`.
    const CASES: &str = include_str!("../../tests/fixtures/folders-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("folders-cases.json is JSON")
    }

    #[test]
    fn every_real_view_is_passed_on_unchanged() {
        let doc = cases();
        let all = doc["cases"].as_object().expect("cases");
        assert!(all.len() >= 6);
        for (name, view) in all {
            let got =
                folders_answer(200, &view.to_string()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, view, "{name}");
        }
    }

    #[test]
    fn a_pc_without_it_says_so() {
        let got = folders_answer(404, "").unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], FOLDERS_MISSING);
        assert_eq!(change_answer(404, "").unwrap_err(), FOLDERS_MISSING);
        assert!(folders_answer(200, "{nope").is_err());
    }

    #[test]
    fn the_pcs_refusal_from_another_device_is_its_own_words() {
        let doc = cases();
        let r = &doc["add_from_phone"];
        let got = change_answer(r["status"].as_u64().unwrap() as u16, &r["body"].to_string());
        assert!(got.is_err());
    }

    #[test]
    fn adding_and_importing_wait_for_a_live_link_removing_never_does() {
        assert!(held_on_stale(ADD_PATH));
        assert!(held_on_stale(IMPORT_PATH));
        assert!(!held_on_stale(REMOVE_PATH));
    }
}
