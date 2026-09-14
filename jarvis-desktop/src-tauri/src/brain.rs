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
use tauri::AppHandle;

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
            (section, get_json(&base, path, headers, budget).await)
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
                Err(err) => serde_json::json!({ "available": false, "error": err }),
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
#[tauri::command]
pub async fn brain_revert_undo(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    post(&app, "/api/undo/revert", serde_json::json!({ "id": id })).await
}

/// Cancels a Long Fuse job. Works mid-step, and a cancelled job is not
/// resumable — the UI must say so before it calls this, not after.
#[tauri::command]
pub async fn brain_cancel_job(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
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
    let client = reqwest::Client::builder()
        .connect_timeout(READ_TIMEOUT)
        .timeout(budget)
        .no_proxy()
        .build()
        .map_err(|e| format!("could not build an HTTP client: {e}"))?;
    let response = client
        .get(format!("{base}{path}"))
        .headers(headers)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {base}")
            } else if e.is_timeout() {
                format!("{path} did not answer within {}s", budget.as_secs())
            } else {
                format!("{path}: {e}")
            }
        })?;
    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        return Err(format!(
            "{path} answered HTTP {}{}",
            status.as_u16(),
            first_line(&body)
        ));
    }
    response
        .json()
        .await
        .map_err(|e| format!("{path} returned something unreadable: {e}"))
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
