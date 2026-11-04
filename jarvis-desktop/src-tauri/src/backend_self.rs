//! The version handshake between this desktop build and the backend on this PC.
//!
//! The owner's ask of 2026-11-03: *"when i click update on the jarvis hud i
//! want it linked to the back end so both are always updated at the same
//! time"*. The update itself is `update.rs`'s `update_both` - backend half
//! first, this executable second - and the Settings card now presses that one
//! command instead of the desktop-only `install_update`. This module answers
//! the other half of the ask: after an update, and whenever Settings is open,
//! the two halves are READ BACK from both sides and the result is said in
//! words.
//!
//! # Where the two versions come from
//!
//! * This executable: `app.package_info().version`, the version the installer
//!   put there. The same number the tray row and the Updates card show.
//! * The backend: `GET /api/self`'s `backend.version` (the endpoint the F6
//!   interface introduces; `hud_proxy.rs`'s allowlist carries the same route so
//!   the HUD page can read it too). An older backend answers 404 - and that is
//!   itself the honest answer: a backend without `/api/self` predates what this
//!   build needs, so it is reported as OLDER, never as "fine".
//!
//! # The rules this file keeps
//!
//! * **Never "up to date" while the two differ.** [`SyncState::InSync`] is
//!   reachable only when both sides parse to the same version.
//! * **A different numbering scheme is not a sync claim.** If one side is
//!   `0.2.0` and the other is a date build id, the answer is
//!   [`SyncState::Different`] and the words say the two cannot be compared -
//!   never a made-up "in sync".
//! * **Unreachable is its own answer.** Nothing crashes, no window waits on
//!   this: the read has a short timeout and every failure maps to
//!   [`SyncState::Unreachable`] with the reason in words.
//! * **A newer backend is not an error.** It means the backend can do more
//!   than this desktop build knows about; the desktop must keep working (the
//!   route is additive), and the words say so.
//!
//! The pure part - parsing both versions and choosing the state and words -
//! is [`compare`] / [`words`], tested without a network or a window. The one
//! network read is [`read`], which goes through the same base/token helpers
//! every other backend call uses.

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

/// The endpoint this handshake reads. One spelling, also in
/// `hud_proxy.rs`'s allowlist so the HUD page may read the same route.
pub const SELF_PATH: &str = "/api/self";

/// How long the handshake read may take. Short on purpose: it is a sentence
/// on a card and a start-up line, not a gate on anything.
const TIMEOUT: std::time::Duration = std::time::Duration::from_secs(5);

/// Which half is ahead, as far as the two version strings can say.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum SyncState {
    /// Both sides name the same version.
    InSync,
    /// The backend is older than this desktop build (including a backend that
    /// has no `/api/self` at all).
    BackendOlder,
    /// The backend is newer than this desktop build.
    BackendNewer,
    /// Both answered, but the two strings are not one numbering scheme (or one
    /// of them has no version), so no sync claim can be made.
    Different,
    /// The backend answered, but without a version this build can read.
    Unavailable,
    /// Nothing was listening, or the read failed.
    Unreachable,
}

/// The answer the Settings card and the HUD's start-up line are drawn from.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VersionSync {
    /// The version this executable is running.
    pub desktop: String,
    /// `backend.version`, when the backend answered with one.
    pub backend: Option<String>,
    pub state: SyncState,
    /// One plain sentence for the owner. Always says what is true of each half
    /// it knows about, and never says "up to date" unless it is.
    pub words: String,
}

/// A parsed numeric version: `0.2.0`, `v1.2`, `2026.11.03` -> its numbers.
/// `None` when the string is not one (a commit hash, a date with letters, an
/// empty string).
pub fn parse_version(raw: &str) -> Option<Vec<u64>> {
    let raw = raw.trim();
    let raw = raw
        .strip_prefix('v')
        .or_else(|| raw.strip_prefix('V'))
        .unwrap_or(raw);
    // The first whitespace-delimited word, so "0.2.0 (abc123)" still parses.
    let first = raw.split_whitespace().next()?;
    let core = first
        // A build suffix like `0.2.0-beta` or `0.2.0+abc`: compare the numeric
        // core only. A suffix says how a release was built, not when it came.
        .split(['-', '+'])
        .next()?;
    if core.is_empty() {
        return None;
    }
    let mut parts = Vec::new();
    for part in core.split('.') {
        if part.is_empty() || !part.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
        parts.push(part.parse::<u64>().ok()?);
    }
    // A version is at least one number; `1` and `1.2` are both real versions.
    (!parts.is_empty()).then_some(parts)
}

/// Compares two versions numerically, treating `1` and `1.0` as the same.
fn order(a: &[u64], b: &[u64]) -> std::cmp::Ordering {
    let len = a.len().max(b.len());
    for i in 0..len {
        let x = a.get(i).copied().unwrap_or(0);
        let y = b.get(i).copied().unwrap_or(0);
        if x != y {
            return x.cmp(&y);
        }
    }
    std::cmp::Ordering::Equal
}

/// The state, given the two version strings and whether the backend answered
/// at all. Pure: every branch is testable.
pub fn state_for(desktop: &str, backend: Option<&str>, reachable: bool) -> SyncState {
    if !reachable {
        return SyncState::Unreachable;
    }
    let Some(backend) = backend.map(str::trim).filter(|b| !b.is_empty()) else {
        // It answered, and did not say a version this build can read.
        return SyncState::Unavailable;
    };
    let (Some(mine), Some(theirs)) = (parse_version(desktop), parse_version(backend)) else {
        return SyncState::Different;
    };
    match order(&mine, &theirs) {
        std::cmp::Ordering::Equal => SyncState::InSync,
        std::cmp::Ordering::Less => SyncState::BackendNewer,
        std::cmp::Ordering::Greater => SyncState::BackendOlder,
    }
}

/// The sentence for one state. Plain words, one line, what to do next.
pub fn words(desktop: &str, backend: Option<&str>, state: SyncState) -> String {
    let named = backend
        .map(str::trim)
        .filter(|b| !b.is_empty())
        .map(|b| format!("backend {b}"))
        .unwrap_or_else(|| "no version".to_string());
    match state {
        SyncState::InSync => format!("Jarvis Desktop {desktop} and the {named} - IN SYNC."),
        SyncState::BackendOlder => format!(
            "MISMATCH: the {named}, but this HUD expects {desktop}. Finish the backend \
             update - Settings, then Updates, and press Install (that updates both halves)."
        ),
        SyncState::BackendNewer => format!(
            "The {named} is newer than Jarvis Desktop {desktop}. That is safe - the HUD \
             keeps working and adds nothing it does not know - but updating Jarvis Desktop \
             gets the two in step."
        ),
        SyncState::Different => format!(
            "Jarvis Desktop {desktop} and the {named} are different kinds of version, so \
             they cannot be compared. Check both in Settings, then Updates."
        ),
        SyncState::Unavailable => format!(
            "Jarvis Desktop {desktop}: the backend answered but did not report which version \
             it is. It may be older than this build. Run the backend update from Settings, \
             then Updates."
        ),
        SyncState::Unreachable => format!(
            "Jarvis Desktop {desktop}: backend unreachable, so the two versions cannot be \
             compared. Nothing was changed."
        ),
    }
}

/// The backend's own version, out of a `/api/self` answer. Tolerant of the
/// shape because the endpoint is being built beside this code: the contract
/// wraps a version OBJECT (`version.app_version`), with flat `version`/`app`
/// shapes accepted too so an older or plainer route still answers.
///
/// The object shape matters and is not a guess: the backend answers
/// `"version": version_block()` = `{app_version, app_version_source,
/// api_version, server, started_at, deploy{...}}`, so a plain `.as_str()` on
/// `/version` would find nothing and this handshake would call a healthy
/// backend "unavailable" (integration gap found by f6-docs, 2026-11-03).
pub fn backend_version(self_doc: &serde_json::Value) -> Option<String> {
    // The deployed app version first: that is the number a desktop release is
    // installed over and the one the Update click moves. `api_version` is the
    // route contract's own number and is deliberately NOT used here - it does
    // not change when the desktop half updates.
    for pointer in [
        "/version/app_version",
        "/backend/version",
        "/version",
        "/app/version",
        "/hud_version",
    ] {
        if let Some(v) = self_doc.pointer(pointer).and_then(|v| v.as_str()) {
            if !v.trim().is_empty() {
                return Some(v.trim().to_string());
            }
        }
    }
    None
}

/// Reads `GET /api/self` and compares it with this executable.
///
/// Every failure is a [`VersionSync`] with words, not an error: the callers
/// draw a card line and a chat line, neither of which may fail because the
/// backend is down.
pub async fn read(app: &AppHandle) -> VersionSync {
    let desktop = app.package_info().version.to_string();
    let Ok(base) = commands_base(app) else {
        return VersionSync {
            desktop: desktop.clone(),
            backend: None,
            state: SyncState::Unreachable,
            words: words(&desktop, None, SyncState::Unreachable),
        };
    };
    let client = match reqwest::Client::builder()
        .timeout(TIMEOUT)
        .connect_timeout(TIMEOUT)
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .build()
    {
        Ok(client) => client,
        Err(_) => {
            return VersionSync {
                desktop: desktop.clone(),
                backend: None,
                state: SyncState::Unreachable,
                words: words(&desktop, None, SyncState::Unreachable),
            }
        }
    };
    let url = format!("{base}{SELF_PATH}");
    let request = match crate::commands::jarvis_headers(app) {
        Ok(headers) => client.get(&url).headers(headers),
        Err(_) => client.get(&url),
    };
    let (backend, reachable) = match request.send().await {
        Ok(response) if response.status().is_success() => {
            match response.json::<serde_json::Value>().await {
                // It answered; the version may still be missing (an older
                // backend with a partial route), which is `Unavailable`.
                Ok(doc) => (backend_version(&doc), true),
                Err(_) => (None, true),
            }
        }
        // A 404 is an ANSWER: a backend without `/api/self` is older than this
        // build needs, and that is reported as such rather than as a network
        // problem. `reachable = true`, `backend = None` -> Unavailable... but
        // an older backend is the OLDER story, so pin it at the call site.
        Ok(response) if response.status().as_u16() == 404 => (Some(String::new()), true),
        Ok(_) | Err(_) => (None, false),
    };
    let state = state_for(&desktop, backend.as_deref(), reachable);
    // A 404 is not "unavailable": the backend predates the endpoint, so it IS
    // older than this HUD needs. The empty string above keeps `state_for`
    // honest for the other shapes; this branch is the one that knows more.
    let state = if reachable && backend.as_deref() == Some("") {
        SyncState::BackendOlder
    } else {
        state
    };
    let backend = backend.filter(|b| !b.is_empty());
    VersionSync {
        words: words(&desktop, backend.as_deref(), state),
        desktop,
        backend,
        state,
    }
}

/// The command Settings calls: the version handshake, on demand, never an
/// update. It reads one route and writes nothing.
#[tauri::command]
pub async fn shell_version_sync(app: AppHandle) -> Result<VersionSync, String> {
    Ok(read(&app).await)
}

/// One read at start-up, so a desktop newer than its backend says so once,
/// in the HUD's own chat log, instead of pretending all is well. Only the
/// OLDER answer is spoken: "in sync" on every launch is noise, and a backend
/// that is down is already the page's own standing line.
pub fn spawn_startup_handshake(app: &AppHandle) {
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        // Give the one stream a moment: its hello is the first real backend
        // contact, and a read that loses that race would say "unreachable"
        // about a backend that is merely still starting.
        tokio::time::sleep(std::time::Duration::from_secs(8)).await;
        let sync = read(&handle).await;
        crate::logfile::log(&format!(
            "[jarvis] version handshake: {} ({:?})",
            sync.words, sync.state
        ));
        if sync.state == SyncState::BackendOlder {
            crate::push_to_hud_main(
                &handle,
                "version",
                &VersionLine {
                    state: "older".to_string(),
                    words: sync.words.clone(),
                },
            );
        }
        // The card may be open already, and the state is worth having even if
        // no one asked: remember the last answer for the next Settings open.
        if let Some(state) = handle.try_state::<LastSync>() {
            if let Ok(mut slot) = state.0.lock() {
                *slot = Some(sync);
            }
        }
    });
}

/// The last handshake this process ran. Settings may read it on open instead
/// of asking again on the same second as the start-up read.
#[derive(Default)]
pub struct LastSync(pub std::sync::Mutex<Option<VersionSync>>);

/// One line for the HUD's chat log, on the feed's `version` channel.
#[derive(Debug, Clone, Serialize)]
pub struct VersionLine {
    /// `older` - the only state spoken at start-up.
    pub state: String,
    pub words: String,
}

/// `commands::jarvis_base`, behind a `Result` so this module's failure path is
/// one shape. A refused base (a public bind address) is not reachable.
fn commands_base(app: &AppHandle) -> Result<String, String> {
    crate::commands::require_base_allowed(app)?;
    Ok(crate::commands::jarvis_base(app))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ordinary_versions_parse_with_or_without_a_leading_v() {
        assert_eq!(parse_version("0.2.0"), Some(vec![0, 2, 0]));
        assert_eq!(parse_version("v0.2.0"), Some(vec![0, 2, 0]));
        assert_eq!(parse_version(" 1.2 "), Some(vec![1, 2]));
        assert_eq!(parse_version("2026.11.03"), Some(vec![2026, 11, 3]));
    }

    #[test]
    fn a_build_suffix_does_not_change_the_ordering() {
        assert_eq!(parse_version("0.2.0-beta.1"), Some(vec![0, 2, 0]));
        assert_eq!(parse_version("0.2.0+abc123"), Some(vec![0, 2, 0]));
    }

    #[test]
    fn a_string_that_is_not_a_version_returns_none() {
        assert_eq!(parse_version(""), None);
        assert_eq!(parse_version("main"), None);
        assert_eq!(parse_version("abc.def"), None);
        assert_eq!(parse_version("0.2.x"), None);
    }

    #[test]
    fn the_two_versions_in_step_is_the_only_in_sync_case() {
        assert_eq!(state_for("0.2.0", Some("0.2.0"), true), SyncState::InSync);
        // `1` and `1.0` are the same release.
        assert_eq!(state_for("1", Some("1.0.0"), true), SyncState::InSync);
    }

    #[test]
    fn a_backend_on_a_lower_version_is_older() {
        assert_eq!(
            state_for("0.3.0", Some("0.2.9"), true),
            SyncState::BackendOlder
        );
        assert_eq!(
            state_for("2026.12.01", Some("2026.11.03"), true),
            SyncState::BackendOlder
        );
    }

    #[test]
    fn a_backend_ahead_of_this_build_is_newer_and_not_an_error() {
        assert_eq!(
            state_for("0.2.0", Some("0.3.0"), true),
            SyncState::BackendNewer
        );
    }

    #[test]
    fn two_numbering_schemes_are_different_and_never_in_sync() {
        assert_eq!(
            state_for("0.2.0", Some("release-main"), true),
            SyncState::Different
        );
        assert_eq!(
            state_for("main-build", Some("0.2.0"), true),
            SyncState::Different
        );
    }

    #[test]
    fn unreachable_and_no_version_are_their_own_answers() {
        assert_eq!(
            state_for("0.2.0", Some("0.2.0"), false),
            SyncState::Unreachable
        );
        assert_eq!(state_for("0.2.0", None, true), SyncState::Unavailable);
        assert_eq!(state_for("0.2.0", Some(""), true), SyncState::Unavailable);
    }

    #[test]
    fn only_the_in_sync_sentence_says_in_sync() {
        let states = [
            SyncState::InSync,
            SyncState::BackendOlder,
            SyncState::BackendNewer,
            SyncState::Different,
            SyncState::Unavailable,
            SyncState::Unreachable,
        ];
        for state in states {
            let sentence = words("0.2.0", Some("0.2.0"), state);
            assert!(!sentence.is_empty(), "{state:?}");
            let claims_sync = sentence.contains("IN SYNC");
            assert_eq!(
                claims_sync,
                state == SyncState::InSync,
                "{state:?}: {sentence}"
            );
            // The desktop's own version is always named, so a card can never
            // show a sentence that belongs to another build.
            assert!(sentence.contains("0.2.0"), "{state:?}: {sentence}");
        }
    }

    #[test]
    fn the_older_sentence_says_what_to_do() {
        let sentence = words("0.3.0", Some("0.2.9"), SyncState::BackendOlder);
        assert!(sentence.starts_with("MISMATCH"));
        assert!(sentence.contains("0.2.9"));
        assert!(sentence.contains("0.3.0"));
        assert!(sentence.contains("Install"), "{sentence}");
    }

    #[test]
    fn the_backend_version_is_read_out_of_every_shape_this_code_can_meet() {
        // The REAL shape (f6-docs, 2026-11-03): `version` is the backend's
        // version BLOCK, an object, and the deployed app version lives in
        // `version.app_version`. Reading only strings at `/version` made a
        // healthy backend report "did not report which version it is".
        let real = serde_json::json!({
            "version": {
                "app_version": "0.2.320",
                "app_version_source": "deploy",
                "api_version": 3,
                "server": "jarvis_hud.py",
                "started_at": 1,
                "deploy": {"commit": "abc1234"}
            }
        });
        assert_eq!(backend_version(&real), Some("0.2.320".to_string()));
        let contract = serde_json::json!({"backend": {"version": "0.2.0", "started_at": 1}});
        assert_eq!(backend_version(&contract), Some("0.2.0".to_string()));
        assert_eq!(
            backend_version(&serde_json::json!({"version": "0.2.1"})),
            Some("0.2.1".to_string())
        );
        assert_eq!(
            backend_version(&serde_json::json!({"app": {"version": " v9.9 "}})),
            Some("v9.9".to_string())
        );
        assert_eq!(backend_version(&serde_json::json!({"backend": {}})), None);
        assert_eq!(
            backend_version(&serde_json::json!({"version": {"api_version": 3}})),
            None
        );
        assert_eq!(backend_version(&serde_json::json!("nonsense")), None);
    }

    #[test]
    fn the_real_shape_reads_back_as_a_decision_after_an_update() {
        // The owner's requirement, walked end to end without a network: after
        // the desktop half moved to 0.2.320 and the backend block reports the
        // same, the handshake says IN SYNC; one behind, it says MISMATCH and
        // what to do.
        let doc =
            |app: &str| serde_json::json!({"version": {"app_version": app, "api_version": 3}});
        let read = backend_version(&doc("0.2.320"));
        assert_eq!(
            state_for("0.2.320", read.as_deref(), true),
            SyncState::InSync
        );
        let behind = backend_version(&doc("0.2.310"));
        let state = state_for("0.2.320", behind.as_deref(), true);
        assert_eq!(state, SyncState::BackendOlder);
        let sentence = words("0.2.320", behind.as_deref(), state);
        assert!(sentence.starts_with("MISMATCH"), "{sentence}");
        assert!(sentence.contains("0.2.310"), "{sentence}");
        assert!(sentence.contains("0.2.320"), "{sentence}");
    }
}
