//! Settings -> "Protected from Jarvis" (the owner's request of 2026-10-31:
//! *"add a list of file folders, and programs that i can manually add to (or
//! ask jarvis to exclude in chat and get a card) that blocks jarvis from
//! having any access (read or write) or the ability to make certain files or
//! folders or programs read only"*; the contract is
//! `.dsh-scratch/PROTECTED-ITEMS-2026-10-31/CONTRACT.md`).
//!
//! Five commands, settings window only (`permissions/surfaces.toml`,
//! `settings-surface`):
//!
//! * [`get_protection`] - `GET /api/protection`: the list in the PC's own
//!   words, the two modes and the card sentence. A read.
//! * [`protection_pick`] - the Windows folder or file picker, returning ONLY
//!   the chosen path. Nothing is sent until the owner presses Add: the mode
//!   is a second, explicit choice.
//! * [`protection_programs`] - the executable names of the programs running
//!   on this PC right now, so "Add a program…" offers a real list instead of
//!   asking the owner to type a name. Read locally; no backend call, no path
//!   leaves this function.
//! * [`add_protection`] - `POST /api/protection/add`. The owner's own direct
//!   act in Settings, so it is immediate (tightening, with an audit line on
//!   the PC) and never held: the backend refuses a relative path, a path that
//!   is not there, an unknown program or a duplicate with a plain sentence.
//! * [`remove_protection`] - `POST /api/protection/remove`. Removing is
//!   loosening, so the PC raises ONE approval card; the command is held while
//!   the event stream is stale (rule 4), because the card should be answered
//!   by someone looking at a live queue. A 202 means the card is up.
//!
//! The window never gets a file system of its own: both pickers run here, and
//! only the path the owner chose is sent - to this PC's Jarvis, nowhere else.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const PROTECTION_PATH: &str = "/api/protection";
const ADD_PATH: &str = "/api/protection/add";
const REMOVE_PATH: &str = "/api/protection/remove";

/// What a backend without the protected-items module is told. The page and
/// the phone (`Protection.MISSING`) say the same sentence.
pub(crate) const PROTECTION_MISSING: &str =
    "Your PC's Jarvis cannot protect things yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

/// The most programs "Add a program…" offers, and the most it will name.
const MAX_PROGRAMS: usize = 300;

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_protection`]'s reading of the answer, tested against the contract
/// file (`tests/fixtures/protection-cases.json`).
pub(crate) fn protection_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("items").is_some_and(|i| i.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({
            "available": false,
            "why": PROTECTION_MISSING,
            "items": [],
        }));
    }
    Err(backend_refusal(status, body))
}

/// A change's answer: the PC's own body on a 2xx (200 stored, 202 a card is
/// up), [`PROTECTION_MISSING`] from a PC without the route, and the PC's own
/// sentence otherwise (400 what is wrong with the path, 403 the PC only,
/// 404 unknown id, 409 already protected).
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(PROTECTION_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// Whether a change waits for a live event stream. Removing (a card) does;
/// adding does not (the owner's own direct act, and it only tightens).
pub(crate) fn held_on_stale(path: &str) -> bool {
    path == REMOVE_PATH
}

/// The protected list: `GET /api/protection`. A read.
#[tauri::command]
pub async fn get_protection(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{PROTECTION_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    protection_answer(status, &body)
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    if held_on_stale(path) && stale(app) {
        return Err(STALE.to_string());
    }
    let base = jarvis_base(app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
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

/// The Windows picker for one folder or one file, and nothing else. Only the
/// chosen path comes back; the page never gets a file system of its own.
#[tauri::command]
pub async fn protection_pick(app: AppHandle, kind: String) -> Result<serde_json::Value, String> {
    require_base_allowed(&app)?;
    let what = match kind.trim().to_ascii_lowercase().as_str() {
        "folder" => crate::folders::picker::What::ProtectFolder,
        "file" => crate::folders::picker::What::ProtectFile,
        _ => return Err("choose a folder or a file".to_string()),
    };
    let Some(path) = crate::folders::pick(what).await? else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
    Ok(serde_json::json!({ "ok": true, "path": path }))
}

/// A config dir check reused from the folders commands: a refused address
/// must not be used even for a local picker decision.
fn require_base_allowed(app: &AppHandle) -> Result<(), String> {
    match crate::commands::base_problem(app) {
        Some(problem) => Err(problem),
        None => Ok(()),
    }
}

/// `Ok(false)` for a name that is not an executable: an empty string, a bare
/// name without `.exe`, a path with a separator already stripped, or one with
/// control characters. Pure, so the rules are tested without a PC.
pub(crate) fn is_exe_name(name: &str) -> bool {
    let n = name.trim();
    if n.is_empty() || n.len() > 260 {
        return false;
    }
    let lower = n.to_ascii_lowercase();
    lower.ends_with(".exe")
        && lower != ".exe"
        && !lower
            .chars()
            .any(|c| c.is_control() || c == '"' || c == '<' || c == '>')
}

/// The exe file name from whatever `sysinfo` knows about one process: the
/// file name of its `exe()` path when there is one, else its own `name()`.
/// Lower-cased, because the backend stores programs that way.
pub(crate) fn exe_from_row(row: &str) -> Option<String> {
    let base = row.rsplit(['\\', '/']).next().unwrap_or(row).trim();
    let lower = base.to_ascii_lowercase();
    if is_exe_name(&lower) {
        Some(lower)
    } else {
        None
    }
}

/// Every distinct executable name in `rows`, lower-cased, de-duplicated,
/// sorted, in one list. The same program started three times is one entry;
/// a program with no `.exe` name (a service, a kernel thread) is not offered.
pub(crate) fn program_names<I: IntoIterator<Item = String>>(rows: I) -> Vec<String> {
    let mut out: Vec<String> = rows.into_iter().filter_map(|r| exe_from_row(&r)).collect();
    out.sort();
    out.dedup();
    out.truncate(MAX_PROGRAMS);
    out
}

fn running_rows(system: &sysinfo::System) -> Vec<String> {
    system
        .processes()
        .values()
        .map(|p| match p.exe() {
            Some(path) => path.to_string_lossy().to_string(),
            None => p.name().to_string_lossy().to_string(),
        })
        .collect()
}

/// The programs running on this PC right now, as executable names.
///
/// Local only: it reads this PC's process table, never the backend and never
/// the network, and returns names only - no path of a running program is sent
/// anywhere. The page shows them so "Add a program…" can offer real names
/// rather than making the owner type one.
#[tauri::command]
pub fn protection_programs() -> serde_json::Value {
    let mut system = sysinfo::System::new_all();
    system.refresh_processes(sysinfo::ProcessesToUpdate::All, true);
    let programs = program_names(running_rows(&system));
    serde_json::json!({
        "ok": true,
        "programs": programs,
        "count": programs.len(),
    })
}

/// Add ONE entry. The owner's own direct act in Settings: immediate, no card
/// (the contract's "manual add ... may be immediate (tightening)"). The
/// backend still refuses a relative path, a missing path, an unknown program
/// and a duplicate with a plain sentence, which the page shows as it is.
#[tauri::command]
pub async fn add_protection(
    app: AppHandle,
    kind: String,
    target: String,
    mode: String,
) -> Result<serde_json::Value, String> {
    let kind = kind.trim().to_ascii_lowercase();
    let target = target.trim();
    let mode = mode.trim().to_ascii_lowercase();
    if !matches!(kind.as_str(), "folder" | "file" | "program") {
        return Err("choose a folder, a file or a program".to_string());
    }
    if target.is_empty() {
        return Err("choose what to protect first".to_string());
    }
    if !matches!(mode.as_str(), "blocked" | "readonly") {
        return Err("choose Blocked or Read-only".to_string());
    }
    post(
        &app,
        ADD_PATH,
        serde_json::json!({ "kind": kind, "target": target, "mode": mode }),
    )
    .await
}

/// Remove ONE entry. Removing is loosening, so the PC raises ONE approval
/// card; a 202 answer carries its job id. Held on a stale link (rule 4).
#[tauri::command]
pub async fn remove_protection(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    let id = id.trim();
    if id.is_empty() {
        return Err("that entry has no id to remove".to_string());
    }
    post(&app, REMOVE_PATH, serde_json::json!({ "id": id })).await
}

#[cfg(test)]
mod tests {
    use super::{
        change_answer, exe_from_row, held_on_stale, program_names, protection_answer, ADD_PATH,
        PROTECTION_MISSING, REMOVE_PATH,
    };

    /// The PC's answers, written from CONTRACT.md: the backend lane builds the
    /// same routes against that contract, and CI is the authority on the real
    /// bytes once that lane lands.
    const CASES: &str = include_str!("../../tests/fixtures/protection-cases.json");

    fn case(name: &str) -> (u16, String) {
        let all: serde_json::Value = serde_json::from_str(CASES).expect("fixture parses");
        let c = &all["cases"][name];
        (
            c["status"].as_u64().expect("status") as u16,
            c["body"].to_string(),
        )
    }

    #[test]
    fn every_real_view_is_passed_on_unchanged() {
        for name in ["view_list", "view_empty", "view_program_readonly"] {
            let (status, body) = case(name);
            let got = protection_answer(status, &body).unwrap_or_else(|e| panic!("{name}: {e}"));
            let sent: serde_json::Value =
                serde_json::from_str(&body).expect("fixture body is JSON");
            assert_eq!(got, sent, "{name}");
        }
    }

    #[test]
    fn a_pc_without_it_says_so_and_never_looks_protected() {
        let got = protection_answer(404, "").expect("an answer");
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], PROTECTION_MISSING);
        assert!(got["items"].as_array().is_some_and(|i| i.is_empty()));
        assert_eq!(change_answer(404, "").unwrap_err(), PROTECTION_MISSING);
        assert!(protection_answer(200, "{nope").is_err());
    }

    #[test]
    fn the_pcs_refusals_are_its_own_sentences() {
        for name in [
            "add_relative",
            "add_missing",
            "add_no_program",
            "add_duplicate",
            "remove_unknown",
        ] {
            let (status, body) = case(name);
            let err = change_answer(status, &body).expect_err(name);
            assert!(!err.trim().is_empty(), "{name}");
        }
        // The "the PC only" refusal is the PC's sentence too.
        let (status, body) = case("add_from_phone");
        assert!(change_answer(status, &body).is_err());
    }

    #[test]
    fn a_waiting_remove_is_an_answer_with_its_job_id() {
        let (status, body) = case("remove_waiting");
        assert_eq!(status, 202);
        let got = change_answer(status, &body).expect("a job");
        assert_eq!(got["state"], serde_json::json!("waiting"));
        assert!(got["id"].as_str().is_some_and(|i| !i.is_empty()));
    }

    #[test]
    fn removing_waits_for_a_live_link_adding_does_not() {
        assert!(held_on_stale(REMOVE_PATH));
        assert!(!held_on_stale(ADD_PATH));
    }

    #[test]
    fn a_program_name_is_a_lowercase_exe_and_nothing_else() {
        assert_eq!(
            exe_from_row("C:\\Program Files\\Notepad++\\notepad++.exe").as_deref(),
            Some("notepad++.exe")
        );
        assert_eq!(exe_from_row("NOTEPAD.EXE").as_deref(), Some("notepad.exe"));
        assert_eq!(exe_from_row("C:/Tools/vlc.exe").as_deref(), Some("vlc.exe"));
        assert_eq!(exe_from_row("cmd.exe"), Some("cmd.exe".to_string()));
        assert_eq!(exe_from_row("chrome"), None);
        assert_eq!(exe_from_row(""), None);
        assert_eq!(exe_from_row(".exe"), None);
        assert_eq!(exe_from_row("bad\"name.exe"), None);
    }

    #[test]
    fn the_program_list_is_deduped_and_sorted() {
        let got = program_names([
            "C:\\Windows\\explorer.exe".to_string(),
            "C:\\Program Files\\Notepad++\\notepad++.exe".to_string(),
            "notepad++.exe".to_string(),
            "C:\\Windows\\System32\\svchost.exe".to_string(),
            "some-service".to_string(),
        ]);
        assert_eq!(got, ["explorer.exe", "notepad++.exe", "svchost.exe"]);
    }
}
