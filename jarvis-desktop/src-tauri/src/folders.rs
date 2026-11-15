//! Settings -> "Folders Jarvis may look in" (the owner's decisions of
//! 2026-09-26: asking about PDFs and Word files, and bringing in a Notion
//! export; backend/documents.patch, jarvis_documents.py; JARVIS-API.md
//! section 35).
//!
//! Five commands, settings window only (permissions/surfaces.toml,
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
//! * [`prepare_file_for_phone`] - "Send a file to your phone…" (the owner's
//!   design of 2026-11-14, `SEND-TO-PHONE-2GB-DESIGN-2026-11-14.md` sections 6
//!   and 8): the Windows OPEN-FILE dialog, then `POST /api/files/prepare
//!   {"path"}`. The PC checks the one file, registers it and raises the SAME
//!   `send_file_to_phone` approval card the chat route uses; nothing is
//!   fetchable before that yes. The command takes NO argument, so the page
//!   can never name a path on this route - the owner's pick in the dialog is
//!   the only source. Held on a stale link (rule 4: it raises a card).
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
/// "Send a file to your phone…": the button's one route, and the only place a
/// path may name a file OUTSIDE the list above, because the owner picked it
/// in the dialog himself (the design's section 6).
pub(crate) const PREPARE_PATH: &str = "/api/files/prepare";

/// What a backend without `jarvis_documents.py` / `documents.patch` is told.
/// The phone says the same (`Folders.MISSING`), and so does folders.js.
pub(crate) const FOLDERS_MISSING: &str =
    "Your PC's Jarvis cannot look in folders yet - run apply-patches.ps1 on the PC.";

/// What a backend without `/api/files/prepare` is told when the button asks.
/// The route arrives with the send-to-phone module (2026-11-14), so a PC that
/// has the folders list and not this is simply behind on its backend.
pub(crate) const SEND_FILE_MISSING: &str = "Your PC's Jarvis cannot send a file to your phone \
                                            yet - update the backend by running \
                                            apply-patches.ps1 on the PC, then try again.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);
/// Unzipping a big export takes a while. It was 600 s, sized for the old 1 GB
/// ceiling; an import may now unpack up to 4 GB (2026-11-09), which is minutes
/// of copying on a slow disk, so the window waits up to half an hour. The
/// Settings page shows the PC's own live counts while it waits, so the wait is
/// visible rather than a frozen button.
const IMPORT_TIMEOUT: Duration = Duration::from_secs(1800);
/// "Send a file to your phone…": `POST /api/files/prepare` checks the one file,
/// registers it and raises the card - it does NOT wait for the owner's yes (the
/// answer arrives on the event stream), so this waits on file metadata, never
/// on a transfer or on a person. 30 s is generous for a 2 GB file on a slow
/// disk. The dialog itself has no clock: it is opened before this is called.
const PREPARE_TIMEOUT: Duration = Duration::from_secs(30);

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
    post_with(app, path, body, timeout, change_answer).await
}

/// The one POST every command here makes, with the reading of the answer
/// passed in: the folders routes answer like [`change_answer`], and the
/// button's own route answers like [`send_file_answer`] (the same shape, but a
/// refusal comes back as a sentence for the page instead of an error).
///
/// Held on a stale link unless [`held_on_stale`] says otherwise. The token,
/// `X-Jarvis-Client` and `X-Jarvis-Surface` are [`jarvis_headers`]'s, the same
/// headers every other desktop call carries.
async fn post_with(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    timeout: Duration,
    answer: fn(u16, &str) -> Result<serde_json::Value, String>,
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
    answer(status, &text)
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

/// Runs a picker on its own thread: the Windows dialogs need a
/// single-threaded COM apartment, which a shared runtime worker cannot
/// promise (the same reason as the memory export's save dialog).
pub(crate) async fn pick(what: picker::What) -> Result<Option<String>, String> {
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

// ── "Send a file to your phone…" (2026-11-14) ───────────────────────────────
//
// SEND-TO-PHONE-2GB-DESIGN-2026-11-14.md sections 6 and 8: a button in THIS
// card, the Windows open-file dialog, then `POST /api/files/prepare
// {"path"}`. The PC checks the one file (present, not protected, under
// CAP_BYTES), registers it and raises the SAME `send_file_to_phone`
// approval card the chat route uses - at most 2 GB, and nothing is fetchable
// until that card is answered.
//
// This is a ROUTE, not a tool: `prepare_file_for_phone` takes no argument, so
// no page can name a path here. The only path that ever reaches this route is
// the one the owner just picked in the dialog, held in a local string.

/// The request body the button sends: exactly `{"path": ...}` and nothing
/// else - one field, the absolute path of the one file the owner picked. The
/// page never supplies it (the command has no parameters), and no second field
/// rides along: `prepare_route` reads `body["path"]` and nothing else.
pub(crate) fn prepare_body(path: &str) -> serde_json::Value {
    serde_json::json!({ "path": path })
}

/// The owner closed the dialog: nothing is sent, no card is raised, and the
/// page is told the same `{"cancelled": true}` every other picker command
/// returns, so it clears its line instead of showing an error.
pub(crate) fn cancelled_answer() -> serde_json::Value {
    serde_json::json!({ "cancelled": true })
}

/// The PC's own sentence out of a `/api/files/prepare` answer. `said` is the
/// key the design pins (the 202's, and every refusal the module writes);
/// `error`, `detail` and `message` are accepted too, so a refusal is never
/// shown as a bare status code.
fn prepare_sentence(body: &str) -> Option<String> {
    let parsed: serde_json::Value = serde_json::from_str(body).ok()?;
    ["said", "error", "detail", "message"]
        .iter()
        .find_map(|key| {
            parsed
                .get(*key)
                .and_then(|v| v.as_str())
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .map(str::to_string)
        })
}

/// Whether the answer carries this module's own `said` key at all - the mark
/// of the send-to-phone module answering rather than the app's own generic
/// "no such route" (which this PC's Jarvis writes as `{"error": "no such
/// route"}`, measured against `jarvis_hud.py`).
fn prepare_has_said(body: &str) -> bool {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| {
            v.get("said")
                .and_then(|s| s.as_str())
                .map(|s| !s.trim().is_empty())
        })
        .unwrap_or(false)
}

/// What [`prepare_file_for_phone`] hands the page.
///
/// * 2xx (the design's `202 {ok, waiting, id, name, folder, size, mime,
///   said}`) - `{"ok": true, "name", "size", "said"}`. The file's name and
///   size, and the PC's own sentence. The `folder` the PC named stays on the
///   PC: this window asked which file, not where it lives, and the id is the
///   approval queue's business, not the page's.
/// * A refusal (a missing file, a protected path, one over the cap) - the
///   PC's own sentence, `{"ok": false, "said": "..."}`, so the page shows it
///   word for word with nothing sent and no card raised.
/// * No route at all - [`SEND_FILE_MISSING`], or the PC's sentence when the
///   answer carried one (a real refusal is never mistaken for an old PC).
/// * Anything this app cannot read - an error, never half a sentence.
pub(crate) fn send_file_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let parsed: serde_json::Value = serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("name").is_some_and(|n| n.is_string()))
            .ok_or_else(|| UNREADABLE.to_string())?;
        return Ok(serde_json::json!({
            "ok": true,
            "name": parsed["name"],
            "size": parsed["size"],
            "said": parsed["said"],
        }));
    }
    let said = prepare_sentence(body);
    // An OLD PC answers `404 {"error": "no such route"}` - the app's own JSON,
    // not this module. Every refusal this module writes carries `said`, so a
    // 404 / 503 without one is "update the backend", never a refusal sentence.
    if !prepare_has_said(body) && missing(status, body) {
        return Err(SEND_FILE_MISSING.to_string());
    }
    match said {
        Some(said) => Ok(serde_json::json!({ "ok": false, "said": said })),
        None => Err(backend_refusal(status, body)),
    }
}

/// "Send a file to your phone…": the owner picks ONE file in the Windows
/// open-file dialog, then this PC's Jarvis registers it and raises the
/// `send_file_to_phone` approval card.
///
/// The button the page draws, and the only way a path outside "Folders Jarvis
/// may look in" reaches a send: the owner chose it himself, here. Held on a
/// stale link before the dialog even opens, because answering the card needs a
/// live link (rule 4) - the same shape as [`add_folder`].
#[tauri::command]
pub async fn prepare_file_for_phone(app: AppHandle) -> Result<serde_json::Value, String> {
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let Some(path) = pick(picker::What::SendFile).await? else {
        return Ok(cancelled_answer());
    };
    post_with(
        &app,
        PREPARE_PATH,
        prepare_body(&path),
        PREPARE_TIMEOUT,
        send_file_answer,
    )
    .await
}

/// The Windows "Select folder" and "Open" dialogs, and nothing else.
/// `pub(crate)`, not just `pub`, so `backup.rs` can reuse `picker::pick` and
/// `picker::What::Folder` for "Choose a folder for backups" - the exact same
/// Windows "Select folder" dialog "Folders Jarvis may look in" uses, not a
/// second copy of it.
#[cfg(windows)]
pub(crate) mod picker {
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
        /// A ChatGPT, Claude, Gemini or DeepSeek export (`.zip` or `.json`), for the
        /// Brain's "Bring in chats" (brain/history_import.rs).
        ChatExport,
        /// One folder the owner protects from Jarvis (Settings' "Protected from
        /// Jarvis", protected.rs).
        ProtectFolder,
        /// One file the owner protects from Jarvis (the same card).
        ProtectFile,
        /// One skill folder: a folder with a SKILL.md in it, for Settings'
        /// "Skills" (skills_menu.rs, 2026-11-02).
        SkillFolder,
        /// One skill `.zip`, for the same card.
        SkillZip,
        /// One file the owner sends to his phone (Settings' "Send a file to
        /// your phone…", prepare_file_for_phone). Any type at all - a PDF, a
        /// photo, an archive - so there is no filter, only "it must exist".
        SendFile,
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
            What::ProtectFolder => {
                dialog
                    .SetTitle(w!("Choose a folder Jarvis must leave alone"))
                    .map_err(fail)?;
                dialog
                    .SetOptions(options | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)
                    .map_err(fail)?;
            }
            What::ProtectFile => {
                dialog
                    .SetTitle(w!("Choose a file Jarvis must leave alone"))
                    .map_err(fail)?;
                dialog
                    .SetOptions(
                        options | FOS_FORCEFILESYSTEM | FOS_FILEMUSTEXIST | FOS_PATHMUSTEXIST,
                    )
                    .map_err(fail)?;
            }
            What::ChatExport => {
                let types = [COMDLG_FILTERSPEC {
                    pszName: w!("Chat export (.zip, .json)"),
                    pszSpec: w!("*.zip;*.json"),
                }];
                dialog.SetFileTypes(&types).map_err(fail)?;
                dialog
                    .SetTitle(w!("Choose the export ChatGPT, Claude or Google sent you"))
                    .map_err(fail)?;
                dialog
                    .SetOptions(
                        options | FOS_FORCEFILESYSTEM | FOS_FILEMUSTEXIST | FOS_PATHMUSTEXIST,
                    )
                    .map_err(fail)?;
            }
            What::SkillFolder => {
                dialog
                    .SetTitle(w!("Choose a skill folder (one with a SKILL.md in it)"))
                    .map_err(fail)?;
                dialog
                    .SetOptions(options | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)
                    .map_err(fail)?;
            }
            What::SkillZip => {
                let types = [COMDLG_FILTERSPEC {
                    pszName: w!("Skill archive (.zip)"),
                    pszSpec: w!("*.zip"),
                }];
                dialog.SetFileTypes(&types).map_err(fail)?;
                dialog.SetTitle(w!("Choose a skill .zip")).map_err(fail)?;
                dialog
                    .SetOptions(
                        options | FOS_FORCEFILESYSTEM | FOS_FILEMUSTEXIST | FOS_PATHMUSTEXIST,
                    )
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
            What::SendFile => {
                // The Windows OPEN-FILE dialog, not the folder one: no
                // FOS_PICKFOLDERS anywhere in this arm, and FOS_FILEMUSTEXIST
                // so the PC is never asked about a folder or a gone file. No
                // file-type filter: the owner may send any file at all.
                dialog
                    .SetTitle(w!("Choose a file to send to your phone"))
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
pub(crate) mod picker {
    #[derive(Clone, Copy)]
    pub enum What {
        Folder,
        Zip,
        /// A ChatGPT, Claude, Gemini or DeepSeek export (`.zip` or `.json`), for the
        /// Brain's "Bring in chats" (brain/history_import.rs).
        ChatExport,
        /// One folder the owner protects from Jarvis (protected.rs).
        ProtectFolder,
        /// One file the owner protects from Jarvis (protected.rs).
        ProtectFile,
        /// One skill folder, and one skill `.zip`, for Settings' "Skills"
        /// (skills_menu.rs).
        SkillFolder,
        SkillZip,
        /// One file the owner sends to his phone (prepare_file_for_phone).
        SendFile,
    }

    pub fn pick(what: What) -> Result<Option<String>, String> {
        let _ = matches!(
            what,
            What::Folder
                | What::Zip
                | What::ChatExport
                | What::ProtectFolder
                | What::ProtectFile
                | What::SkillFolder
                | What::SkillZip
                | What::SendFile
        );
        Err("choosing a folder or a file needs the Windows dialog".to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::{
        cancelled_answer, change_answer, folders_answer, held_on_stale, prepare_body,
        send_file_answer, ADD_PATH, FOLDERS_MISSING, IMPORT_PATH, PREPARE_PATH, REMOVE_PATH,
        SEND_FILE_MISSING, UNREADABLE,
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
        // The button raises the send_file_to_phone card, so rule 4 holds it.
        assert!(held_on_stale(PREPARE_PATH));
    }

    // ── "Send a file to your phone…" (2026-11-14) ───────────────────────────

    /// The request body is exactly the one path the owner picked: one field,
    /// backslashes escaped, and no way for a second field to ride along.
    #[test]
    fn the_body_is_the_one_picked_path_and_nothing_else() {
        let path = r"C:\Users\owner\My Documents\report.pdf";
        let body = prepare_body(path);
        assert_eq!(body.as_object().map(serde_json::Map::len), Some(1));
        assert_eq!(body["path"], path);
        assert_eq!(
            body.to_string(),
            r#"{"path":"C:\\Users\\owner\\My Documents\\report.pdf"}"#
        );
    }

    /// A closed dialog sends nothing and raises nothing. The picker's `None`
    /// has to return before the POST - otherwise the backend would register a
    /// file the owner never chose - and the command must take no path
    /// argument, so no page can name one.
    #[test]
    fn a_closed_dialog_sends_nothing() {
        let source = include_str!("folders.rs");
        assert!(
            source.contains(
                "pub async fn prepare_file_for_phone(app: AppHandle) -> \
                 Result<serde_json::Value, String>"
            ),
            "the command takes no path from the page"
        );
        let pick_at = source
            .find("pick(picker::What::SendFile)")
            .expect("the button opens the open-file dialog");
        let after_pick = &source[pick_at..];
        let cancel_at = after_pick
            .find("return Ok(cancelled_answer());")
            .expect("a closed dialog returns the cancelled answer");
        let post_at = after_pick
            .find("post_with(")
            .expect("the chosen path is the only thing posted");
        assert!(
            cancel_at < post_at,
            "the cancelled branch must return BEFORE anything is sent"
        );
        let answer = cancelled_answer();
        assert_eq!(answer, serde_json::json!({ "cancelled": true }));
        assert_eq!(answer.as_object().map(serde_json::Map::len), Some(1));
    }

    /// The design's 202, read into what the page needs - and NOT the folder
    /// the PC named: this window asked which file, not where it lives.
    #[test]
    fn the_page_gets_the_name_and_the_size_and_never_a_path() {
        let body = serde_json::json!({
            "ok": true,
            "waiting": true,
            "id": "f-123",
            "name": "report.pdf",
            "folder": "C:\\Users\\owner\\Documents",
            "size": 2_411_724,
            "mime": "application/pdf",
            "said": "Waiting for your yes on this PC.",
        });
        let got = send_file_answer(202, &body.to_string()).expect("a 202 is an answer");
        assert_eq!(got["ok"], true);
        assert_eq!(got["name"], "report.pdf");
        assert_eq!(got["size"], 2_411_724);
        assert_eq!(got["said"], "Waiting for your yes on this PC.");
        let mut keys: Vec<&str> = got
            .as_object()
            .expect("an object")
            .keys()
            .map(String::as_str)
            .collect();
        keys.sort_unstable();
        assert_eq!(keys, ["name", "ok", "said", "size"]);
        assert!(
            !got.to_string().contains("owner"),
            "no part of the path reaches the page"
        );
    }

    /// A refusal is the PC's own sentence, word for word, and a plain result
    /// rather than an error - a file too big is an outcome, not a crash.
    #[test]
    fn a_refusal_is_the_pcs_own_sentence() {
        let big = "That file is bigger than 2 GB - pick a smaller one.";
        let got = send_file_answer(
            400,
            &serde_json::json!({ "ok": false, "said": big }).to_string(),
        )
        .expect("a refusal is not an error");
        assert_eq!(got["ok"], false);
        assert_eq!(got["said"], big);
        // An `error` sentence is accepted too, so a refusal never shows as a
        // bare status code.
        let err = send_file_answer(400, r#"{"error":"That path is protected."}"#).unwrap();
        assert_eq!(err["said"], "That path is protected.");
        // Nothing readable at all: a plain line with the code, never the body.
        let bare = send_file_answer(500, r#"{"nope":1}"#).unwrap_err();
        assert!(bare.contains("500"), "{bare}");
        // A 2xx this app cannot read is an error, not half a sentence.
        assert_eq!(send_file_answer(202, "{nope").unwrap_err(), UNREADABLE);
        assert_eq!(
            send_file_answer(202, r#"{"ok":true}"#).unwrap_err(),
            UNREADABLE
        );
    }

    /// A PC behind on its backend says what to do - and a 404 that carries the
    /// module's own `said` is still that sentence, not "update the backend".
    #[test]
    fn a_pc_without_the_route_says_what_to_do() {
        assert_eq!(send_file_answer(404, "").unwrap_err(), SEND_FILE_MISSING);
        // The app's own 404 on this PC, measured: `jarvis_hud.py` writes
        // `{"error": "no such route"}`. That must say what to DO, not repeat
        // the app's two words back at the owner.
        assert_eq!(
            send_file_answer(404, r#"{"error": "no such route"}"#).unwrap_err(),
            SEND_FILE_MISSING
        );
        assert_eq!(
            send_file_answer(503, r#"{"available":false}"#).unwrap_err(),
            SEND_FILE_MISSING
        );
        let refused = send_file_answer(404, r#"{"said":"That file has gone."}"#).unwrap();
        assert_eq!(refused["ok"], false);
        assert_eq!(refused["said"], "That file has gone.");
    }
}
