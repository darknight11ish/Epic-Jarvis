//! The interruption budget, the digest, and the one face state the server owns.
//!
//! `jarvis_arbiter` decides how many times a day Jarvis may interrupt out loud.
//! When that budget is spent and things are still waiting, the reactor goes to
//! `banked`: dimmed, still, silent until tapped, with one notch on the rim per
//! waiting item. This module is where the desktop learns all of that.
//!
//! ## Why this is an exception to "an event is a doorbell"
//!
//! JARVIS-API §3 rule 1 is that an event says *something changed* and the
//! client re-fetches the real endpoint. `attention` is the one kind that
//! carries its own state instead — §4 documents the payload as
//! `{remaining, limit, blocked_by, pending, banked}` and
//! `jarvis_arbiter._publish_state` sends exactly those five fields, only when
//! they change. The desktop update order says it in as many words: "use the
//! event, poll only on resume". So the event is applied directly and
//! `GET /api/attention` is read on connect, on resume, and after a mute — the
//! three moments when the five fields are not enough, because `spent`,
//! `muted`, `digest_hour` and `digest_due` are not on the bus at all.
//!
//! ## Why the desktop does not recompute `banked`
//!
//! It would be two lines — `remaining == 0 && pending > 0` — and it would be
//! wrong the first time the server's rule moves. `banked` is read off the wire
//! and never derived here. The one thing this module *does* compose is
//! `face_state`, and it composes it exactly as `jarvis_arbiter.face_state`
//! does, from that same server flag; see [`face_state`] for why there is no
//! endpoint to ask instead.

use std::time::Duration;
use tauri::AppHandle;

use crate::commands;

mod state;
pub use state::{face_state, Attention};

/// Timeout for the small JSON reads and writes here. The arbiter answers from
/// SQLite on the same machine; anything slower than this is a hang, not a slow
/// answer.
const TIMEOUT: Duration = Duration::from_secs(10);

// ---------------------------------------------------------------------------
// Reading it
// ---------------------------------------------------------------------------

/// Reads `GET /api/attention` and publishes the result to every surface and
/// the tray.
///
/// Called on connect, on a stale resume, and after a mute or unmute. Not on a
/// timer: the `attention` event covers every change in between, which is the
/// whole point of the budget existing on the bus.
pub async fn refresh(app: &AppHandle, base: &str) {
    let Some(body) = get_json(app, base, "/api/attention").await else {
        return;
    };
    // `{"available": false, "error": ...}` means the arbiter module is not
    // installed. §7: a false capability means hide the UI, not show an empty
    // one — so leave `known` false rather than publishing a confident zero.
    if body["available"].as_bool() == Some(false) {
        eprintln!(
            "[jarvis] /api/attention: the arbiter is unavailable ({})",
            body["error"].as_str().unwrap_or("no reason given")
        );
        return;
    }
    crate::stream::publish_link(app, |link| link.attention.apply_status(&body));
}

/// The daily brief, ranked by consequence, straight from the server.
///
/// Returned to the caller rather than held in state: the digest is a screen
/// somebody opened, not something the tray or the widget follows. Nothing here
/// re-sorts it — `jarvis_arbiter._rank` orders by *what kind of thing it is*,
/// deliberately never by urgency, because an item that could move itself up the
/// list by saying it was urgent would implement the attack the content-risk
/// scanner exists to catch.
#[tauri::command]
pub async fn get_digest(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    get_json(&app, &base, "/api/digest")
        .await
        .ok_or_else(|| format!("could not read the digest from {base}"))
}

/// Marks digest rows read. **Marking read is not approving anything in them**
/// — `mark_digest_delivered` only stamps a delivery time, and there is no route
/// in the whole API that decides an approval in bulk.
///
/// `ids` empty means "all of it", which is what `{}` means to the server.
#[tauri::command]
pub async fn mark_digest_seen(
    app: AppHandle,
    ids: Vec<String>,
) -> Result<serde_json::Value, String> {
    let body = if ids.is_empty() {
        serde_json::json!({})
    } else {
        serde_json::json!({ "ids": ids })
    };
    let base = commands::jarvis_base(&app);
    let out = post_json(&app, &base, "/api/digest/seen", body).await?;
    // Marking read empties the queued set, which moves `pending` and can clear
    // `banked`. The server publishes an `attention` event for that, but only on
    // its next tick; read it now so the badge does not lag the click.
    refresh(&app, &base).await;
    Ok(out)
}

/// Mutes or unmutes spoken interruptions **for the rest of today**.
///
/// One command for both directions so the two routes cannot drift apart. There
/// is no "mute forever" here because there is none in the API: a mute with no
/// end is how a feature gets switched off once and never reconsidered, and this
/// one has a natural end at midnight.
#[tauri::command]
pub async fn set_attention_muted(app: AppHandle, muted: bool) -> Result<serde_json::Value, String> {
    let route = if muted {
        "/api/attention/mute"
    } else {
        "/api/attention/unmute"
    };
    let base = commands::jarvis_base(&app);
    let out = post_json(&app, &base, route, serde_json::json!({})).await?;
    // The response is `budget()`, not `status()`, so it cannot fill in
    // `pending`, `banked` or the digest fields. Re-read rather than apply half
    // an update and leave the rest stale.
    refresh(&app, &base).await;
    Ok(out)
}

// ---------------------------------------------------------------------------
// Plumbing
// ---------------------------------------------------------------------------

/// A GET that refuses to treat an error body as data.
///
/// The status is checked before the body is parsed. A 401 or a 500 from this
/// server still answers valid JSON, and `serde` will happily turn
/// `{"error": "..."}` into a struct full of defaults — which for this module
/// means a confident "nothing is waiting" over a queue that was never read.
async fn get_json(app: &AppHandle, base: &str, path: &str) -> Option<serde_json::Value> {
    let client = reqwest::Client::builder()
        .connect_timeout(TIMEOUT)
        .timeout(TIMEOUT)
        .no_proxy()
        .build()
        .ok()?;
    let headers = commands::jarvis_headers(app).ok()?;
    let response = match client
        .get(format!("{base}{path}"))
        .headers(headers)
        .send()
        .await
    {
        Ok(response) => response,
        Err(err) => {
            eprintln!("[jarvis] {path} unavailable: {err}");
            return None;
        }
    };
    let status = response.status();
    if !status.is_success() {
        eprintln!("[jarvis] {path} answered HTTP {}", status.as_u16());
        return None;
    }
    match response.json().await {
        Ok(body) => Some(body),
        Err(err) => {
            eprintln!("[jarvis] {path} returned something unreadable: {err}");
            None
        }
    }
}

/// A POST that reports the server's own words on failure.
///
/// The 409 the API uses for "already handled" reaches the caller as the message
/// rather than a generic failure, because the surfaces are asked to say "that
/// has already gone" instead of showing a spinner that never resolves.
async fn post_json(
    app: &AppHandle,
    base: &str,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder()
        .connect_timeout(TIMEOUT)
        .timeout(TIMEOUT)
        .no_proxy()
        .build()
        .map_err(|e| format!("could not build an HTTP client: {e}"))?;
    let headers = commands::jarvis_headers(app)?;
    let response = client
        .post(format!("{base}{path}"))
        .headers(headers)
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
        return Err(format!(
            "the server answered HTTP {} to {path}: {}",
            status.as_u16(),
            text.trim()
        ));
    }
    Ok(serde_json::from_str(&text).unwrap_or_else(|_| serde_json::json!({ "ok": true })))
}
