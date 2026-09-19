//! Checks `GET /api/visual-spec` against what this build has vendored, so a
//! divergence between the desktop's and the phone's copies of
//! `jarvis-visual-spec.json` shows up on its own instead of being found by
//! hand, weeks later, in a cross-branch document.
//!
//! `docs/CROSS-CLIENT-CONTRACT-REPLY-2.md`, in its own words: "the endpoint
//! is real and correct... but neither client fetches it." That document also
//! records the actual cost of that gap: two real divergences (a gradient
//! rule and a missing flicker clamp) that were only caught because someone
//! happened to compare the two files by eye. This module is the desktop half
//! of turning the endpoint on.
//!
//! ## What this does and does not do
//!
//! It **checks**, once, at startup, and tells - a system notification and a
//! console line if the two disagree, nothing at all if they agree or if the
//! server has no spec to compare against. It changes nothing: a disagreement
//! is a prompt to look, the same as `update.rs` only ever names a version and
//! points at Settings rather than installing anything.
//!
//! ## Why structural comparison, not the server's own sha256
//!
//! The route hashes the CANONICAL form of its JSON -
//! `json.dumps(spec, sort_keys=True, separators=(",", ":"))` in Python - so
//! two files agree once whitespace and key order are ignored. Reproducing
//! that exact byte sequence in Rust would mean matching Python's number
//! formatting and its default `ensure_ascii=True` escaping, and
//! `serde_json` does not do either the same way - a real drift could pass
//! undetected because the two sides normalise bytes differently, or a false
//! alarm could fire on formatting alone. `serde_json::Value`'s own
//! `PartialEq` compares the parsed STRUCTURE, not bytes, which sidesteps
//! that mismatch entirely and is the stronger check for what this exists to
//! catch. The server's own `sha256` and `version` are still carried in the
//! report, for a human comparing notes with the phone side.

use serde::Serialize;
use tauri::{AppHandle, Emitter};

use crate::commands;

/// This build's own bundled spec, exactly as `spec.rs` parses it - not a
/// second copy of the file, so this checker can never itself drift from
/// what the app actually ships.
const VENDORED_SPEC_JSON: &str = include_str!("../../src/jarvis-visual-spec.json");

const ROUTE: &str = "/api/visual-spec";

/// Short, and only ever run once at startup: nothing downstream of this
/// matters enough to hold up the window, the tray or the event stream for -
/// same reasoning `update.rs`'s own `CHECK_TIMEOUT` gives.
const TIMEOUT: std::time::Duration = std::time::Duration::from_secs(8);

/// What a check found. Carries no action - see the module doc.
#[derive(Debug, Clone, Serialize)]
pub struct DriftReport {
    /// True once a check actually ran a comparison. False for a network or
    /// client-build failure, which is not itself evidence of drift.
    pub checked: bool,
    /// True when the server answered with a spec to compare against.
    pub server_available: bool,
    /// `None` until `server_available` is true. `Some(true)` means the two
    /// specs are structurally identical.
    pub matches: Option<bool>,
    /// The server's own `version` field, for a human comparing notes.
    pub server_version: Option<i64>,
    /// The server's own canonical sha256, for a human comparing notes - see
    /// the module doc for why this checker does not compute its own.
    pub server_sha256: Option<String>,
    /// Why `checked` is false, or why `server_available` is false.
    pub note: Option<String>,
}

impl DriftReport {
    fn failed(note: impl Into<String>) -> Self {
        Self {
            checked: false,
            server_available: false,
            matches: None,
            server_version: None,
            server_sha256: None,
            note: Some(note.into()),
        }
    }

    fn unavailable(note: impl Into<String>) -> Self {
        Self {
            checked: true,
            server_available: false,
            matches: None,
            server_version: None,
            server_sha256: None,
            note: Some(note.into()),
        }
    }
}

async fn check(app: &AppHandle) -> DriftReport {
    let base = commands::jarvis_base(app);
    let client = match reqwest::Client::builder()
        .connect_timeout(TIMEOUT)
        .timeout(TIMEOUT)
        .no_proxy()
        .build()
    {
        Ok(c) => c,
        Err(e) => return DriftReport::failed(format!("could not build an HTTP client: {e}")),
    };
    let headers = match commands::jarvis_headers(app) {
        Ok(h) => h,
        Err(e) => return DriftReport::failed(e),
    };
    let response = match client
        .get(format!("{base}{ROUTE}"))
        .headers(headers)
        .send()
        .await
    {
        Ok(r) => r,
        Err(e) if e.is_connect() => {
            return DriftReport::failed(format!("Jarvis is not answering at {base}"))
        }
        Err(e) => return DriftReport::failed(format!("{ROUTE}: {e}")),
    };
    let status = response.status();
    if status.as_u16() == 404 {
        // The expected answer on a backend that predates this route -
        // nothing to compare against, not a finding worth a notification.
        return DriftReport::unavailable(format!("this backend has no {ROUTE} yet"));
    }
    if !status.is_success() {
        return DriftReport::failed(format!("{ROUTE} answered HTTP {}", status.as_u16()));
    }
    let body: serde_json::Value = match response.json().await {
        Ok(v) => v,
        Err(e) => {
            return DriftReport::failed(format!("{ROUTE} returned something unreadable: {e}"))
        }
    };
    if body.get("available").and_then(|v| v.as_bool()) != Some(true) {
        let reason = body
            .get("reason")
            .and_then(|v| v.as_str())
            .unwrap_or("no jarvis-visual-spec.json on that machine");
        return DriftReport::unavailable(reason.to_string());
    }
    let server_spec = body.get("spec").cloned().unwrap_or(serde_json::Value::Null);
    let vendored: serde_json::Value = match serde_json::from_str(VENDORED_SPEC_JSON) {
        Ok(v) => v,
        Err(e) => {
            return DriftReport::failed(format!(
                "this build's own bundled spec would not parse: {e}"
            ))
        }
    };
    DriftReport {
        checked: true,
        server_available: true,
        matches: Some(server_spec == vendored),
        server_version: body.get("version").and_then(|v| v.as_i64()),
        server_sha256: body
            .get("sha256")
            .and_then(|v| v.as_str())
            .map(str::to_string),
        note: None,
    }
}

/// The startup look. Spawned and forgotten, same as `update::spawn_startup_check` -
/// a slow or unreachable endpoint must not hold up the window, the tray or
/// the event stream.
pub fn spawn_startup_check(app: &AppHandle) {
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        let report = check(&handle).await;
        if report.matches == Some(false) {
            println!(
                "[jarvis] visual spec drift: this build's spec disagrees with the server's \
                 (server sha256: {})",
                report.server_sha256.as_deref().unwrap_or("unknown")
            );
            // Told, not acted upon - the same shape update.rs uses for a
            // newer version: name the finding, point at where to look.
            // Nothing here edits either spec.
            commands::notify(
                &handle,
                "Jarvis look spec disagrees with the server",
                "This app's built-in look spec differs from what the backend is serving. \
                 See docs/CROSS-CLIENT-CONTRACT-REPLY-2.md.",
            );
        }
        let _ = handle.emit(crate::events::VISUAL_SPEC_DRIFT, report);
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The one thing that must never silently break: the bundled spec this
    /// module compares against has to actually parse. A malformed vendored
    /// file would make `matches` false for every server, forever, which
    /// reads exactly like a real drift and is not one.
    #[test]
    fn the_vendored_spec_itself_parses() {
        let parsed: Result<serde_json::Value, _> = serde_json::from_str(VENDORED_SPEC_JSON);
        assert!(parsed.is_ok(), "jarvis-visual-spec.json failed to parse");
    }

    /// Structural comparison, not byte comparison - key order and
    /// whitespace must not read as drift.
    #[test]
    fn reordered_whitespace_differs_json_still_matches() {
        let a: serde_json::Value = serde_json::from_str(r#"{"a":1,"b":2}"#).unwrap();
        let b: serde_json::Value = serde_json::from_str("{\n  \"b\": 2,\n  \"a\": 1\n}").unwrap();
        assert_eq!(a, b, "key order and formatting must not count as drift");
    }

    /// CONTROL: a genuine content difference must still be caught.
    #[test]
    fn a_real_content_difference_does_not_match() {
        let a: serde_json::Value = serde_json::from_str(r#"{"a":1}"#).unwrap();
        let b: serde_json::Value = serde_json::from_str(r#"{"a":2}"#).unwrap();
        assert_ne!(
            a, b,
            "CONTROL: a genuine difference must not read as a match"
        );
    }
}
