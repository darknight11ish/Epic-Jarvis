//! The Brain — everything Jarvis knows and everything it can do, in one window.
//!
//! The backend exposes fourteen read-only surfaces that this desktop was
//! ignoring entirely: the memory graph, the model catalogue, the compute plan,
//! installed skills, Long Fuse jobs, the undo shelf, the audit ledger, the
//! content-risk state, the GitHub watchlist, the memory store, proposed facts,
//! the initiative inbox and the parsed config. Every one of them was reachable
//! over HTTP and rendered nowhere.
//!
//! ## Why a fan-out read rather than one command per endpoint
//!
//! Fourteen `#[tauri::command]`s would be fourteen ACL entries granting the
//! same thing — read a read-only endpoint on the local backend. [`brain_read`]
//! is one command over a **fixed allowlist**: a window names sections, not
//! URLs, so it cannot reach an endpoint this file did not decide it may reach.
//! That keeps the grant honest and lets the window ask for six panes in one
//! round trip instead of six.
//!
//! The writes are the opposite: each is its own command with its own
//! permission, because reverting a file, cancelling a job and removing a skill
//! are three different powers and a window that needs one should not get all
//! three. `/api/config` is a read here and a 501 on the server — the write path
//! rewrites the tiers that decide what Jarvis may do unattended, and it needs
//! its own review before any UI drives it.
//!
//! ## What this deliberately does not do
//!
//! There is no route here that approves an approval, clears a rush latch or
//! decides anything in bulk. `/api/content-risk` is read-only by design on the
//! server and it stays read-only here: approving a tool description means a
//! person read the full current text, which happens where the scanner runs.

use std::time::Duration;
use tauri::{AppHandle, Manager};

use crate::commands;

mod routes;
use routes::{first_line, route_for};

/// Reads are small JSON except the graph, which walks several SQLite files and
/// a skills directory. Two budgets rather than one, so a slow graph cannot be
/// mistaken for a hung backend and a hung backend is not waited on for a
/// minute.
const READ_TIMEOUT: Duration = Duration::from_secs(15);
const GRAPH_TIMEOUT: Duration = Duration::from_secs(45);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

// ---------------------------------------------------------------------------
// Reading
// ---------------------------------------------------------------------------

/// Reads several backend surfaces at once and returns them keyed by section.
///
/// Every section resolves to an object. A section that failed comes back as
/// `{"available": false, "error": "..."}` rather than being dropped, because a
/// pane that renders nothing and a pane whose backend is missing look identical
/// to the user and should not.
///
/// One failing section never fails the call. These are independent modules on
/// the far side — `jarvis_ledger` being absent is not a reason to leave the
/// model catalogue unrendered.
#[tauri::command]
pub async fn brain_read(
    app: AppHandle,
    sections: Vec<String>,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let headers = commands::jarvis_headers(&app)?;

    let mut wanted: Vec<(String, &'static str)> = Vec::new();
    for section in sections {
        match route_for(&section) {
            Some(path) => wanted.push((section, path)),
            // A name that is not in the table is a bug in the caller, not a
            // request to be satisfied. Say so loudly rather than silently
            // returning fewer panes than were asked for.
            None => return Err(format!("`{section}` is not a readable Brain section")),
        }
    }
    if wanted.is_empty() {
        return Ok(serde_json::json!({}));
    }

    // Fanned out rather than sequential: these are independent modules behind
    // independent SQLite files, and the graph alone can take seconds. Six panes
    // in series would be six round trips the user waits through.
    //
    // `JoinSet` rather than `futures_util::join_all` because tokio is already a
    // direct dependency and futures-util is only a transitive one — a new
    // top-level crate for one combinator is a new thing to audit and pin.
    let mut set = tokio::task::JoinSet::new();
    for (section, path) in wanted {
        let base = base.clone();
        let headers = headers.clone();
        set.spawn(async move {
            let budget = if path == "/api/graph" {
                GRAPH_TIMEOUT
            } else {
                READ_TIMEOUT
            };
            (section, get_json_status(&base, path, headers, budget).await)
        });
    }

    let mut out = serde_json::Map::new();
    while let Some(joined) = set.join_next().await {
        // A panicked read task must not take the other panes with it.
        let (section, result) = match joined {
            Ok(pair) => pair,
            Err(err) => {
                eprintln!("[jarvis] a Brain read task failed to join: {err}");
                continue;
            }
        };
        out.insert(
            section,
            match result {
                Ok(body) => body,
                // `read` tells the window which of two very different things
                // happened, because they need different words and only one
                // of them is worth a Retry: `absent` is a 404 or 503 - this
                // backend does not have the module, a fact about the machine
                // - and `failed` is everything else, a fault that may pass.
                // Before this both arrived as the same grey "not available".
                Err((status, err)) => serde_json::json!({
                    "available": false,
                    "error": err,
                    "read": read_kind(status),
                }),
            },
        );
    }
    Ok(serde_json::Value::Object(out))
}

// ---------------------------------------------------------------------------
// Writing — one command per power
// ---------------------------------------------------------------------------

/// Puts something back. JARVIS-API calls this "the one state-changing thing a
/// phone may drive, because it only ever moves toward a state the owner
/// already had".
///
/// Gated on `StreamState.link().stale`, the same check `decide_approval` in
/// commands.rs has and this one did not. The Brain window can be open with a
/// dead event stream - a sleep/wake, a backend restart, a dropped radio - and
/// `brain.js` only ever read `link.stale` to DISPLAY it, never before firing
/// this command. jarvis-client found and fixed the identical shape on its own
/// side for this exact action (`revert`, commit 44a1202) and named it, in its
/// own comment, "the call JARVIS-API singles out as the one state-changing
/// thing a phone may drive" - the desktop's copy of that same action had no
/// gate at all.
fn require_link_live(app: &AppHandle) -> Result<(), String> {
    if app.state::<crate::stream::StreamState>().link().stale {
        return Err(
            "the event stream is stale, so this cannot be confirmed live - \
             nothing can be sent until it reconnects"
                .to_string(),
        );
    }
    Ok(())
}

#[tauri::command]
pub async fn brain_revert_undo(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    post(&app, "/api/undo/revert", serde_json::json!({ "id": id })).await
}

/// Cancels a Long Fuse job. Works mid-step, and a cancelled job is not
/// resumable — the UI must say so before it calls this, not after.
#[tauri::command]
pub async fn brain_cancel_job(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    // Same gate, same reason as brain_revert_undo above: cancelling against a
    // job list that could not be confirmed live risks cancelling one that has
    // already finished or already failed on its own.
    require_link_live(&app)?;
    post(&app, "/api/jobs/cancel", serde_json::json!({ "id": id })).await
}

/// Stops a message inside its send window.
///
/// A 409 means it has already gone. That is not an error to retry or a spinner
/// to leave running: there is no unsend after the window closes, and saying
/// otherwise would be the lie the feature exists to avoid. The message reaches
/// the caller verbatim so the UI can say exactly that.
#[tauri::command]
pub async fn brain_cancel_hold(
    app: AppHandle,
    handle: String,
) -> Result<serde_json::Value, String> {
    // Same gate: a 409 ("already gone") is the server's backstop for a race,
    // not a reason to send a cancellation we already know is unfounded
    // because the stream that would confirm the hold is still open cannot be
    // confirmed live.
    require_link_live(&app)?;
    post(
        &app,
        "/api/holds/cancel",
        serde_json::json!({ "handle": handle }),
    )
    .await
}

/// Adds a topic to the GitHub watchlist. Leave `query` empty and the name is
/// the query, which is what the server does with a missing one.
#[tauri::command]
pub async fn brain_watch_add(
    app: AppHandle,
    name: String,
    query: Option<String>,
    min_stars: Option<u32>,
    language: Option<String>,
    notify: Option<bool>,
) -> Result<serde_json::Value, String> {
    let mut body = serde_json::Map::new();
    body.insert("name".into(), serde_json::json!(name));
    if let Some(q) = query.filter(|q| !q.trim().is_empty()) {
        body.insert("query".into(), serde_json::json!(q));
    }
    if let Some(s) = min_stars {
        body.insert("min_stars".into(), serde_json::json!(s));
    }
    if let Some(l) = language.filter(|l| !l.trim().is_empty()) {
        body.insert("language".into(), serde_json::json!(l));
    }
    body.insert("notify".into(), serde_json::json!(notify.unwrap_or(false)));
    post(&app, "/api/watch/add", serde_json::Value::Object(body)).await
}

/// Forgets a topic and everything remembered about it. Destructive in a way the
/// UI must confirm: the server does not keep a copy.
#[tauri::command]
pub async fn brain_watch_remove(app: AppHandle, name: String) -> Result<serde_json::Value, String> {
    post(
        &app,
        "/api/watch/remove",
        serde_json::json!({ "name": name }),
    )
    .await
}

/// Marks the current findings read and returns them.
///
/// A POST rather than a GET, and that is the whole design: a link preview or a
/// prefetch must not be able to clear a week of findings on the owner's behalf.
/// `/api/watch/report` is the peek; this is the consume.
#[tauri::command]
pub async fn brain_watch_seen(
    app: AppHandle,
    topic: Option<String>,
) -> Result<serde_json::Value, String> {
    let mut body = serde_json::Map::new();
    if let Some(t) = topic.filter(|t| !t.trim().is_empty()) {
        body.insert("topic".into(), serde_json::json!(t));
    }
    post(&app, "/api/watch/seen", serde_json::Value::Object(body)).await
}

/// Removes a skill. Removal only — there is deliberately no route that installs
/// one, because installing runs the scanner and the gate inside the module and
/// a client that bypassed both would be the whole attack.
#[tauri::command]
pub async fn brain_remove_skill(app: AppHandle, name: String) -> Result<serde_json::Value, String> {
    post(
        &app,
        "/api/skills/decide",
        serde_json::json!({ "name": name, "remove": true }),
    )
    .await
}

/// Keeps or discards ONE proposed fact.
///
/// The extractor fills this queue on its own, so the queue is the one place
/// the owner ever sees what Jarvis wanted to remember about them. One integer
/// id, one decision, and no list form anywhere in this file — forgetting is
/// irreversible and a "keep all" would be an approve-all with another name.
#[tauri::command]
pub async fn brain_memory_decide(
    app: AppHandle,
    id: i64,
    accept: bool,
) -> Result<serde_json::Value, String> {
    // The exact same shape as decide_approval (commands.rs): a decision
    // against a review queue that could have changed since this window last
    // synced. The extractor fills this queue on its own, on a background
    // thread, independent of whatever the Brain window last fetched.
    require_link_live(&app)?;
    post(
        &app,
        "/api/memory/decide",
        serde_json::json!({ "id": id, "accept": accept }),
    )
    .await
}

/// Stops a fact being recalled.
///
/// The server retires rather than deletes: the row stays and stops being
/// current, so the history of what was once true survives. There is no undo,
/// and the UI says so before asking.
///
/// `valid_to`, optional: unix seconds for when the fact actually stopped
/// being true, if that was before now — "I moved in January" told in March.
/// Omitted, the server retires at "now" exactly as it always has.
#[tauri::command]
pub async fn brain_memory_forget(
    app: AppHandle,
    id: i64,
    valid_to: Option<f64>,
) -> Result<serde_json::Value, String> {
    // Gated like brain_memory_decide: this acts on a fact the window drew
    // from a read that may be stale, and forgetting cannot be undone.
    require_link_live(&app)?;
    let mut body = serde_json::json!({ "id": id });
    if let Some(vt) = valid_to {
        body["valid_to"] = serde_json::json!(vt);
    }
    post(&app, "/api/memory/forget", body).await
}

/// Rewords a fact by superseding it.
///
/// Separate from forget because they are different powers: this one adds a
/// replacement and can be corrected again, that one cannot be undone at all.
///
/// `valid_to`, optional, same meaning as [`brain_memory_forget`]'s: when the
/// fact being replaced stopped being true, if not now.
#[tauri::command]
pub async fn brain_memory_edit(
    app: AppHandle,
    id: i64,
    text: String,
    valid_to: Option<f64>,
) -> Result<serde_json::Value, String> {
    // Gated for the same reason as forget: it retires the fact it rewords.
    require_link_live(&app)?;
    let mut body = serde_json::json!({ "id": id, "text": text });
    if let Some(vt) = valid_to {
        body["valid_to"] = serde_json::json!(vt);
    }
    post(&app, "/api/memory/edit", body).await
}

/// Turns the background learner on or off.
///
/// `JARVIS_EXTRACT` in the environment is a floor this cannot lift, and the
/// server says so in the reply rather than reporting a success it did not
/// achieve — so the UI must render what came back, not what it asked for.
#[tauri::command]
pub async fn brain_memory_learning(
    app: AppHandle,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    // Gated like every other memory write (rule 4): the button's label came
    // from a read that a stale link cannot confirm is still true.
    require_link_live(&app)?;
    post(
        &app,
        "/api/memory/learning",
        serde_json::json!({ "enabled": enabled }),
    )
    .await
}

/// Answers the daily overnight-tidy card ("not built yet" - switching it on
/// only records the wish; nothing runs).
///
/// Two independent fields because the card offers two independent actions:
/// "enable" sends `enabled`, "stop asking" sends `remind`. "not now" calls
/// nothing at all — the server's own once-a-day tracking already keeps the
/// card from returning today regardless, so a plain dismiss needs no request.
#[tauri::command]
pub async fn brain_memory_sleep_time(
    app: AppHandle,
    enabled: Option<bool>,
    remind: Option<bool>,
) -> Result<serde_json::Value, String> {
    // Gated like brain_memory_decide above: this answers a card the Brain
    // drew from a read that may be stale, and the phone refuses the same
    // answer while its link is stale (JarvisRuntime.setSleepTime).
    require_link_live(&app)?;
    let mut body = serde_json::json!({});
    if let Some(e) = enabled {
        body["enabled"] = serde_json::json!(e);
    }
    if let Some(r) = remind {
        body["remind"] = serde_json::json!(r);
    }
    post(&app, "/api/memory/sleep_time", body).await
}

/// "Both are true": the third answer on a correction card
/// (memory-intake.patch). Keeps the new fact AND leaves the old one current -
/// nothing is retired or deleted. One proposal id, one decision, exactly like
/// [`brain_memory_decide`], and gated on a live link the same way. The window
/// offers it only on a card whose `keep_both_ok` is true, which only a
/// patched backend sends.
#[tauri::command]
pub async fn brain_memory_keep_both(app: AppHandle, id: i64) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    post(
        &app,
        "/api/memory/keep_both",
        serde_json::json!({ "id": id }),
    )
    .await
}

/// Every fact and every pending proposal, saved to a file the owner picks.
///
/// A command rather than a read section because it is large and wanted rarely;
/// putting it in the section table would fetch the whole store every time the
/// pane opened.
///
/// A FILE, not the clipboard. It used to be copied to the clipboard, and
/// Windows can sync the clipboard to the owner's other devices through their
/// Microsoft account ("Sync across your devices") - so everything Jarvis knows
/// about the owner could leave the machine with nobody deciding it should
/// (rule 1). The standard Windows "Save as" dialog is opened here, by the app,
/// so the window itself gets no file access at all; the only file written is
/// the one the owner named in that dialog.
///
/// Returns `{"saved": <path>, "facts": <count>}`, or `{"cancelled": true}`
/// when the owner closed the dialog. The facts themselves never go back to
/// the window.
#[tauri::command]
pub async fn brain_memory_export(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let headers = commands::jarvis_headers(&app)?;
    // Read first: a backend that cannot answer is said before a dialog opens.
    let export = get_json(&base, "/api/memory/export", headers, READ_TIMEOUT).await?;
    let count = export
        .get("facts")
        .and_then(|f| f.as_array())
        .map_or(0, Vec::len);
    let text = serde_json::to_string_pretty(&export)
        .map_err(|e| format!("could not write the export as JSON: {e}"))?;
    let name = export_file_name(unix_now());
    let (tx, rx) = tokio::sync::oneshot::channel();
    // Its own thread: the dialog needs a single-threaded COM apartment, which
    // a shared runtime worker thread cannot promise.
    std::thread::spawn(move || {
        let _ = tx.send(save_dialog::pick(&name));
    });
    let picked = rx
        .await
        .map_err(|_| "the save dialog closed unexpectedly".to_string())??;
    let Some(path) = picked else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
    std::fs::write(&path, text).map_err(|e| format!("could not save {}: {e}", path.display()))?;
    Ok(serde_json::json!({ "saved": path.display().to_string(), "facts": count }))
}

fn unix_now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |d| d.as_secs())
}

/// The name the dialog suggests: `jarvis-memory-2026-09-23.json` (UTC date).
fn export_file_name(unix_seconds: u64) -> String {
    // Days since 1970-01-01 to a civil date (Howard Hinnant's algorithm), so
    // no date crate is pulled in for one file name.
    let days = (unix_seconds / 86_400) as i64;
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("jarvis-memory-{y:04}-{m:02}-{d:02}.json")
}

/// The Windows "Save as" dialog, and nothing else.
#[cfg(windows)]
mod save_dialog {
    use std::path::PathBuf;
    use windows::core::{w, HSTRING};
    use windows::Win32::Foundation::ERROR_CANCELLED;
    use windows::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_INPROC_SERVER,
        COINIT_APARTMENTTHREADED, COINIT_DISABLE_OLE1DDE,
    };
    use windows::Win32::UI::Shell::Common::COMDLG_FILTERSPEC;
    use windows::Win32::UI::Shell::{
        FileSaveDialog, IFileSaveDialog, FOS_FORCEFILESYSTEM, FOS_OVERWRITEPROMPT,
        SIGDN_FILESYSPATH,
    };

    /// `Ok(None)` when the owner cancelled.
    pub fn pick(suggested: &str) -> Result<Option<PathBuf>, String> {
        // SAFETY: plain COM calls on this thread, which is ours alone and is
        // initialised as a single-threaded apartment first. Every pointer
        // handed out by COM is released: the interfaces by their Drop, the
        // path string by CoTaskMemFree.
        unsafe {
            let init = CoInitializeEx(None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
            if init.is_err() {
                return Err(format!("could not open the save dialog: {init:?}"));
            }
            let out = show(suggested);
            CoUninitialize();
            out
        }
    }

    unsafe fn show(suggested: &str) -> Result<Option<PathBuf>, String> {
        let fail = |e: windows::core::Error| format!("the save dialog failed: {e}");
        let dialog: IFileSaveDialog =
            CoCreateInstance(&FileSaveDialog, None, CLSCTX_INPROC_SERVER).map_err(fail)?;
        let types = [COMDLG_FILTERSPEC {
            pszName: w!("JSON file"),
            pszSpec: w!("*.json"),
        }];
        dialog.SetFileTypes(&types).map_err(fail)?;
        dialog.SetDefaultExtension(w!("json")).map_err(fail)?;
        dialog
            .SetTitle(w!("Save everything Jarvis remembers"))
            .map_err(fail)?;
        dialog
            .SetFileName(&HSTRING::from(suggested))
            .map_err(fail)?;
        let options = dialog.GetOptions().map_err(fail)?;
        dialog
            .SetOptions(options | FOS_OVERWRITEPROMPT | FOS_FORCEFILESYSTEM)
            .map_err(fail)?;
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
        path.map(|p| Some(PathBuf::from(p)))
            .map_err(|e| format!("the chosen file name could not be read: {e}"))
    }
}

/// Not Windows: this app is only built for Windows; say so rather than guess.
#[cfg(not(windows))]
mod save_dialog {
    pub fn pick(_suggested: &str) -> Result<Option<std::path::PathBuf>, String> {
        Err("saving the memory export needs the Windows save dialog".to_string())
    }
}

#[cfg(test)]
mod export_name_tests {
    use super::export_file_name;

    #[test]
    fn the_suggested_name_carries_the_date() {
        assert_eq!(export_file_name(0), "jarvis-memory-1970-01-01.json");
        // 2026-09-23 12:00:00 UTC
        assert_eq!(
            export_file_name(1_790_164_800),
            "jarvis-memory-2026-09-23.json"
        );
        // A leap day.
        assert_eq!(
            export_file_name(1_709_208_000),
            "jarvis-memory-2024-02-29.json"
        );
    }
}

/// What Jarvis believed at a past moment, right or wrong.
///
/// The transaction-time half of the bi-temporal store. `valid_from`/`valid_to`
/// say when a fact was true; `created`/`retired_at` say when this machine
/// thought so. A fact learned on Tuesday and retired on Friday belongs in
/// Wednesday's answer and not in today's, and only the second pair can tell
/// you that.
///
/// Its own command rather than a `brain_read` section because the section
/// table maps a name to a fixed path with no parameters — deliberately, so the
/// grant is auditable by reading one array. Rather than let a window append a
/// query string to an allowlisted path, the timestamp is formatted here, from
/// an `f64` that cannot carry anything but a number.
///
/// Read-only in both directions: the server returns the rows and offers no way
/// to change them, because the past is not editable.
#[tauri::command]
pub async fn brain_memory_as_of(app: AppHandle, when: f64) -> Result<serde_json::Value, String> {
    // NaN and the infinities format as "NaN" and "inf", which the server would
    // reject as unparseable and answer with today's facts instead — the wrong
    // answer rendered under an "as of" banner, which is worse than an error.
    if !when.is_finite() || when <= 0.0 {
        return Err(format!("{when} is not a moment in time"));
    }
    let base = commands::jarvis_base(&app);
    let headers = commands::jarvis_headers(&app)?;
    // Whole seconds. Sub-second precision means nothing here and a float in
    // exponential notation would not survive the server's float() intact.
    let path = format!("/api/memory/facts?known_at={:.0}", when);
    get_json(&base, &path, headers, READ_TIMEOUT).await
}

/// Installs, switches or rolls back a model.
///
/// Three routes behind one command because they are one power — deciding which
/// weights answer the owner's questions — and splitting them would let a
/// capability file grant `switch` while withholding `rollback`, which is the
/// wrong way round: rollback is the safe direction and is tier `auto` on the
/// server precisely so it never waits.
///
/// Install returns **202** and reports progress as `model` events; the caller
/// must treat a 202 as "started", not "done".
#[tauri::command]
pub async fn brain_model(
    app: AppHandle,
    action: String,
    reference: Option<String>,
) -> Result<serde_json::Value, String> {
    // Rule 4: nothing acts on a stale link. Switch and install only raise a
    // card, but they raise it against a model list this window read from a
    // link that has stopped updating; rollback is tier `auto` and acts at
    // once, which is the stronger reason. The phone's canAct gate is the same.
    require_link_live(&app)?;
    let path = match action.as_str() {
        "install" => "/api/models/install",
        "switch" => "/api/models/switch",
        "rollback" => "/api/models/rollback",
        other => return Err(format!("`{other}` is not a model action")),
    };
    let body = match (&action[..], reference) {
        ("rollback", _) => serde_json::json!({}),
        (_, Some(r)) if !r.trim().is_empty() => serde_json::json!({ "ref": r }),
        _ => return Err(format!("{action} needs a model reference")),
    };
    post(&app, path, body).await
}

// ---------------------------------------------------------------------------
// Plumbing
// ---------------------------------------------------------------------------

/// `"absent"` for a 404 or a 503 (the backend does not have this module),
/// `"failed"` for anything else, including no answer at all.
fn read_kind(status: Option<u16>) -> &'static str {
    match status {
        Some(404) | Some(503) => "absent",
        _ => "failed",
    }
}

/// [`get_json`], keeping the HTTP status of a refusal so [`brain_read`] can
/// tell a missing module from a fault. `None` when there was no answer.
async fn get_json_status(
    base: &str,
    path: &str,
    headers: reqwest::header::HeaderMap,
    budget: Duration,
) -> Result<serde_json::Value, (Option<u16>, String)> {
    let client = reqwest::Client::builder()
        .connect_timeout(READ_TIMEOUT)
        .timeout(budget)
        .no_proxy()
        .build()
        .map_err(|e| (None, format!("could not build an HTTP client: {e}")))?;
    let response = client
        .get(format!("{base}{path}"))
        .headers(headers)
        .send()
        .await
        .map_err(|e| {
            let why = if e.is_connect() {
                format!("could not reach the Jarvis server at {base}")
            } else if e.is_timeout() {
                format!("{path} did not answer within {}s", budget.as_secs())
            } else {
                format!("{path}: {e}")
            };
            (None, why)
        })?;
    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        return Err((
            Some(status.as_u16()),
            format!(
                "{path} answered HTTP {}{}",
                status.as_u16(),
                first_line(&body)
            ),
        ));
    }
    response
        .json()
        .await
        .map_err(|e| (None, format!("{path} returned something unreadable: {e}")))
}

/// A GET that refuses to treat an error body as data.
///
/// The status is checked before the body is parsed, because this server answers
/// perfectly valid JSON on a 401 and a 500. Parsing that into a pane would
/// render an authoritative-looking empty ledger over a request that was
/// refused.
async fn get_json(
    base: &str,
    path: &str,
    headers: reqwest::header::HeaderMap,
    budget: Duration,
) -> Result<serde_json::Value, String> {
    get_json_status(base, path, headers, budget)
        .await
        .map_err(|(_, why)| why)
}

/// A POST that hands the server's own words back on failure.
///
/// The 409s matter here: "already decided", "already sent", "already gone". The
/// UI is asked to say what happened rather than show a generic failure, so the
/// status code and the body both survive into the error string.
async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let client = reqwest::Client::builder()
        .connect_timeout(READ_TIMEOUT)
        .timeout(WRITE_TIMEOUT)
        .no_proxy()
        .build()
        .map_err(|e| format!("could not build an HTTP client: {e}"))?;
    let response = client
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {base}")
            } else {
                format!("{path} failed: {e}")
            }
        })?;
    let status = response.status();
    let text = response.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(format!("HTTP {}{}", status.as_u16(), first_line(&text)));
    }
    Ok(serde_json::from_str(&text)
        .unwrap_or_else(|_| serde_json::json!({ "ok": true, "status": status.as_u16() })))
}

#[cfg(test)]
mod read_kind_tests {
    use super::read_kind;

    /// A missing module is a fact, not a fault: no Retry for it.
    #[test]
    fn a_404_or_503_is_absent_and_anything_else_failed() {
        assert_eq!(read_kind(Some(404)), "absent");
        assert_eq!(read_kind(Some(503)), "absent");
        assert_eq!(read_kind(Some(500)), "failed");
        assert_eq!(read_kind(Some(401)), "failed");
        assert_eq!(read_kind(None), "failed");
    }
}
