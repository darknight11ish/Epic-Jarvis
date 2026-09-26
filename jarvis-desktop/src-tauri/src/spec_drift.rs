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
//! It **checks**, once, at startup, and tells. Every outcome - agreement,
//! disagreement, an unreachable backend, a backend with no spec - is written
//! to the log file with its reason; a disagreement, and only a disagreement,
//! also raises a system notification. It changes nothing: a disagreement is a
//! prompt to look, the same as `update.rs` only ever names a version and
//! points at Settings rather than installing anything.
//!
//! The `VISUAL_SPEC_DRIFT` event carries the same report to the webview. No
//! window subscribes to it today; the log line is the real output.
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
    /// One of `match`, `drift`, `no-server-spec` or `check-failed`. The whole
    /// outcome in one field, so a reader does not have to reconstruct it from
    /// three booleans and an `Option`.
    pub outcome: &'static str,
    /// True only when a structural comparison actually RAN - which is exactly
    /// when `matches` is `Some`. It used to be set true on the
    /// nothing-to-compare paths as well, directly contradicting this line.
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
    /// The check could not be run at all - no network, no token, a bad
    /// response. Not evidence of drift, and not evidence of agreement either.
    fn failed(note: impl Into<String>) -> Self {
        Self {
            outcome: "check-failed",
            checked: false,
            server_available: false,
            matches: None,
            server_version: None,
            server_sha256: None,
            note: Some(note.into()),
        }
    }

    /// The server answered, and has no spec to compare against. `checked` is
    /// FALSE here: nothing was compared. It used to be true, which made a
    /// report that had compared nothing indistinguishable from one that had.
    fn unavailable(note: impl Into<String>) -> Self {
        Self {
            outcome: "no-server-spec",
            checked: false,
            server_available: false,
            matches: None,
            server_version: None,
            server_sha256: None,
            note: Some(note.into()),
        }
    }

    /// One line, for the log. Every outcome says something; only one of them
    /// used to be said out loud.
    fn summary(&self) -> String {
        match (self.outcome, self.note.as_deref()) {
            ("match", _) => "the look spec agrees with the server's copy".to_string(),
            ("drift", _) => format!(
                "the look spec DISAGREES with the server's copy (server sha256: {}, version: {})",
                self.server_sha256.as_deref().unwrap_or("unknown"),
                self.server_version
                    .map(|v| v.to_string())
                    .unwrap_or_else(|| "unknown".to_string()),
            ),
            (_, Some(note)) => format!("look spec not compared - {note}"),
            (other, None) => format!("look spec not compared - {other}"),
        }
    }
}

async fn check(app: &AppHandle) -> DriftReport {
    let base = commands::jarvis_base(app);
    let client = match reqwest::Client::builder()
        .connect_timeout(TIMEOUT)
        .timeout(TIMEOUT)
        .no_proxy()
        // Never follow a redirect: reqwest would carry X-Jarvis-Token to
        // wherever it points (apps security audit L1).
        .redirect(reqwest::redirect::Policy::none())
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
    // A 200 that says `available: true` and then carries no usable `spec` is
    // NOT drift. This used to be `unwrap_or(Value::Null)`, and `Null` never
    // equals an object, so a malformed or truncated answer fired the exact
    // false alarm the module doc says this design exists to avoid. There is
    // nothing to compare, so say that instead of accusing the build.
    let Some(server_spec) = body.get("spec").filter(|v| v.is_object()) else {
        return DriftReport::unavailable(format!(
            "{ROUTE} said it had a spec but did not send one"
        ));
    };
    let vendored: serde_json::Value = match serde_json::from_str(VENDORED_SPEC_JSON) {
        Ok(v) => v,
        Err(e) => {
            return DriftReport::failed(format!(
                "this build's own bundled spec would not parse: {e}"
            ))
        }
    };
    let matches = *server_spec == vendored;
    DriftReport {
        outcome: if matches { "match" } else { "drift" },
        checked: true,
        server_available: true,
        matches: Some(matches),
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
        // EVERY outcome is written down, not only drift. Before this, an
        // agreement, an unreachable backend, a missing token and a backend
        // with no spec were all indistinguishable from the outside: the
        // `note` field explaining each one was built and then never read by
        // anything, and the only visible output in the whole module was the
        // drift notification. "Nothing happened" and "the check never ran"
        // looked identical, which is the failure mode a checker can least
        // afford.
        crate::logfile::log(&format!("[jarvis] visual spec: {}", report.summary()));
        if report.matches == Some(false) {
            // Told, not acted upon - the same shape update.rs uses for a
            // newer version: name the finding, point at where to look.
            // Nothing here edits either spec. Drift is the one outcome that
            // interrupts; the rest stay in the log.
            commands::notify(
                &handle,
                "Jarvis look spec disagrees with the server",
                "This app's built-in look spec differs from what the backend is serving. \
                 See docs/CROSS-CLIENT-CONTRACT-REPLY-2.md.",
            );
        }
        // Emitted for any window that wants to show this. Nothing subscribes
        // today - said plainly rather than left to be discovered - so the log
        // line above is the real output, and this is the hook for a Settings
        // row if one is ever wanted.
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

    /// `checked` means a comparison ran, and the two no-comparison paths must
    /// both say so. `unavailable` used to claim `checked: true`.
    #[test]
    fn a_report_that_compared_nothing_does_not_claim_it_checked() {
        for report in [
            DriftReport::failed("no network"),
            DriftReport::unavailable("that backend has no spec"),
        ] {
            assert!(
                !report.checked,
                "{}: compared nothing, so `checked` must be false",
                report.outcome
            );
            assert_eq!(report.matches, None);
            assert!(report.note.is_some(), "every non-comparison says why");
        }
    }

    /// Every outcome produces a line worth logging - the `note` explaining a
    /// failed or skipped check used to be built and then read by nothing.
    #[test]
    fn every_outcome_says_something() {
        let failed = DriftReport::failed("Jarvis is not answering at http://x");
        assert!(failed.summary().contains("not answering"));
        let none = DriftReport::unavailable("this backend has no /api/visual-spec yet");
        assert!(none.summary().contains("no /api/visual-spec"));
    }
}
