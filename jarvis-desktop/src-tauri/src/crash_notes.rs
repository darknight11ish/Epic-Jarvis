//! Hang and crash notes (feasibility I99).
//!
//! WHAT THIS IS FOR, IN ONE SENTENCE
//!
//! When the desktop app panics, or the Python backend crashes or stops
//! answering, the owner should not have to go hunting through
//! `jarvis-desktop.log`/`backend.log` to find out that it happened at all -
//! so the newest [`MAX_NOTES`] of these are kept in one small file,
//! `crash-notes.json`, next to those logs, and [`crash_notes`] serves them
//! to a Settings/diagnostics screen.
//!
//! WHY A SEPARATE FILE, NOT MORE LINES IN THE EXISTING LOG
//!
//! `logfile.rs`'s own doc comment is explicit that its two logs have "no
//! redaction pass" and rely on discipline about what is ever printed to
//! them. A panic message is NOT under that discipline - it is whatever
//! `std::fmt::Display`/`Debug` happened to produce for the value that broke,
//! which can legitimately be a file path carrying the owner's Windows user
//! name, or - if a future bug ever formats one into an error - a token or a
//! password. So panic text (and the backend crash/hang text the watchdog in
//! `sidecar.rs` hands this module) goes through [`scrub`] first, and only the
//! scrubbed text is ever written to `crash-notes.json` or returned to a
//! window.
//!
//! `scrub` HERE VS `jarvis_scrub.py` ON THE BACKEND
//!
//! They are not the same code, on purpose, and this one is deliberately
//! lighter:
//! - The backend's has a KNOWN-VALUES layer (the pairing token, everything
//!   named like a secret in the environment). This process holds no working
//!   backend secret to register against - the desktop's own pairing token is
//!   read from Credential Manager, on demand, not kept in a table this
//!   module could consult - so there is nothing for that layer to do here.
//! - A panic can happen before the async runtime, before an `AppHandle`
//!   exists, and before the backend can be reached at all (that is exactly
//!   the situation this module exists for), so calling the backend's own
//!   `/api/... ` scrubbing route is not an option: the one moment this needs
//!   to work reliably is the moment the backend may be down.
//! - So [`scrub`] covers the SHAPES that matter in a short panic message or
//!   watchdog note: a bearer/`X-Jarvis-Token` header, a `name=value` pair
//!   whose name looks like a secret, credentials in a URL
//!   (`scheme://user:pass@host`), and the Windows user-folder segment of a
//!   path (`C:\Users\<name>`). Bare numbers, IP addresses and anything that
//!   merely "looks random" are left alone - the same restraint
//!   `jarvis_scrub.py` documents for the same reason: a bug report needs
//!   something left to read.
//!
//! WHAT WRITES A NOTE
//! - [`install_panic_hook`], called once at the very top of [`crate::run`]:
//!   every panic in this process, on any thread, adds one note (`source`:
//!   `"desktop"`, `kind`: `"panic"`) and then still runs the previous hook
//!   (Tauri's own, which is what actually prints/aborts) - this never
//!   changes what a panic *does*, only records that it happened.
//! - `sidecar.rs`'s `ensure_backend`'s own failure path, and its watchdog,
//!   call [`record`] with `source: "backend"` and `kind: "crash"` or
//!   `"hang"` for the same two conditions the watchdog already restarts on.
//!
//! WHAT NEVER HAPPENS HERE: nothing in this module fixes, restarts, or
//! otherwise acts on anything - see `sidecar.rs`'s watchdog for the actual
//! restart-with-a-cap logic. This module only remembers that something went
//! wrong, in words that are safe to show and safe to paste into a bug report.

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::SystemTime;

use serde::{Deserialize, Serialize};

use crate::logfile;

/// The newest this many notes are kept; older ones are dropped, oldest first.
pub const MAX_NOTES: usize = 10;

/// One hang or crash, already scrubbed - safe to show on screen or paste
/// into a bug report.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CrashNote {
    /// Unix seconds, UTC.
    pub when: u64,
    /// `"desktop"` (this process panicked) or `"backend"` (the Python
    /// backend crashed or stopped answering).
    pub source: String,
    /// `"panic"`, `"crash"`, `"hang"` or `"start"` (a backend that could not be started).
    pub kind: String,
    /// The scrubbed text. Never the raw panic payload or raw watchdog
    /// detail - see [`scrub`].
    pub detail: String,
}

/// Serialises writes to `crash-notes.json` against each other. A panic
/// handler and the watchdog can both call [`record`] from different
/// threads; without this, two notes written at nearly the same moment could
/// each read the file before the other's write, and one would be lost.
static WRITE_LOCK: Mutex<()> = Mutex::new(());

fn notes_path() -> Option<PathBuf> {
    logfile::dir().map(|d| d.join("crash-notes.json"))
}

fn load(path: &Path) -> Vec<CrashNote> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save(path: &Path, notes: &[CrashNote]) {
    // Errors dropped on purpose, the same as `logfile::append` - a full disk
    // must not turn a crash note into a second failure, and this already
    // runs from inside a panic hook, where doing less is safer than doing
    // more.
    if let Ok(text) = serde_json::to_string_pretty(notes) {
        let _ = std::fs::write(path, text);
    }
}

fn now() -> u64 {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Adds one note, scrubbed, keeping only the newest [`MAX_NOTES`].
///
/// Silent if the log directory has not been resolved yet (`logfile::init`
/// has not run) - the same fallback `logfile::log` itself makes, and for the
/// same reason: a note that cannot be written is better lost than crashing
/// the crash handler.
pub fn record(source: &str, kind: &str, detail: &str) {
    let scrubbed = scrub(detail);
    logfile::log(&format!("[jarvis] {source} {kind}: {scrubbed}"));
    let Some(path) = notes_path() else { return };
    let _guard = WRITE_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let mut notes = load(&path);
    notes.push(CrashNote {
        when: now(),
        source: source.to_string(),
        kind: kind.to_string(),
        detail: scrubbed,
    });
    if notes.len() > MAX_NOTES {
        let drop = notes.len() - MAX_NOTES;
        notes.drain(0..drop);
    }
    save(&path, &notes);
}

/// Installs a panic hook that records a scrubbed note and then still runs
/// whatever hook was already installed (Tauri's own default, which is what
/// actually prints the panic and, on `panic = "abort"`, ends the process).
/// **This never changes what a panic does** - it only makes sure it left a
/// note behind first.
///
/// Called once, at the very top of [`crate::run`], before anything else can
/// panic.
pub fn install_panic_hook() {
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        record("desktop", "panic", &info.to_string());
        previous(info);
    }));
}

/// `GET` for a Settings/diagnostics screen: the newest notes, newest last -
/// the same order they were recorded in, so a list that appends a new row
/// at the bottom reads top-to-bottom as oldest-to-newest.
#[tauri::command]
pub fn crash_notes() -> Vec<CrashNote> {
    notes_path().map(|p| load(&p)).unwrap_or_default()
}

// ---------------------------------------------------------------------------
// Scrubbing
// ---------------------------------------------------------------------------

/// Every replacement starts with this - the same convention `jarvis_scrub.py`
/// uses, and for the same reason: no pattern below can match text that
/// starts with it, so running `scrub()` on already-scrubbed text is a no-op
/// rather than a second, garbled redaction.
const MARK: &str = "[redacted";

/// Names that mark a `name=value`/`name: value`/`"name": "value"` pair as
/// worth redacting, whatever the value looks like - the same word list
/// `jarvis_scrub.py` and `jarvis_child_env.py` use for "does this
/// environment variable's NAME say it is a secret".
const SECRET_WORDS: [&str; 7] = [
    "TOKEN",
    "KEY",
    "PASSWORD",
    "PASSWD",
    "SECRET",
    "CREDENTIAL",
    "AUTH",
];

fn looks_secret_named(name: &str) -> bool {
    let up = name.to_ascii_uppercase();
    SECRET_WORDS.iter().any(|w| up.contains(w))
}

/// Is `b` one of the separators/quote characters allowed right before a
/// `name=`/`name:` pair's value, or right after it?
fn is_word_boundary(b: u8) -> bool {
    !(b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}

/// One pass over `s`, replacing every `name<sep>value` pair whose `name`
/// looks like a secret (see [`looks_secret_named`]) with
/// `name<sep>[redacted: looks like a secret]`. `sep` is `=`, `:` or `":"`
/// (JSON), optionally followed by spaces and an opening quote.
fn redact_named_secrets(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = String::with_capacity(s.len());
    let mut i = 0usize;
    while i < bytes.len() {
        // A run of "name" characters.
        let start = i;
        while i < bytes.len() && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_') {
            i += 1;
        }
        if i == start {
            out.push(s[i..].chars().next().unwrap_or(' '));
            i += s[i..].chars().next().map(|c| c.len_utf8()).unwrap_or(1);
            continue;
        }
        let name = &s[start..i];
        // Optional closing quote right after the name (JSON: "TOKEN").
        let mut j = i;
        if bytes.get(j) == Some(&b'"') {
            j += 1;
        }
        // Skip spaces, then require one of = : to call this a pair at all.
        let mut k = j;
        while bytes.get(k) == Some(&b' ') {
            k += 1;
        }
        let sep = bytes.get(k).copied();
        if !looks_secret_named(name) || (sep != Some(b'=') && sep != Some(b':')) {
            out.push_str(name);
            continue;
        }
        k += 1; // past = or :
        while bytes.get(k) == Some(&b' ') {
            k += 1;
        }
        let quoted = bytes.get(k) == Some(&b'"');
        if quoted {
            k += 1;
        }
        let value_start = k;
        while k < bytes.len() {
            if quoted {
                if bytes[k] == b'"' {
                    break;
                }
            } else if is_word_boundary(bytes[k]) {
                break;
            }
            k += 1;
        }
        if k == value_start {
            // No value followed after all (e.g. "TOKEN:" at end of line) -
            // leave it exactly as it was rather than inventing a redaction.
            out.push_str(&s[start..i]);
            continue;
        }
        out.push_str(&s[start..i]);
        // The separator and any quote/spacing between name and value, kept
        // verbatim so the shape of the line is not disturbed.
        out.push_str(&s[i..value_start]);
        out.push_str("[redacted: looks like a secret]");
        if quoted && bytes.get(k) == Some(&b'"') {
            // The closing quote the value's own scan stopped at (`k` never
            // advanced past it), so the redaction reads `"[redacted: ...]"`
            // rather than losing its closing quote.
            out.push('"');
            i = k + 1;
        } else {
            i = k;
        }
    }
    out
}

/// Redacts `user:pass@` inside a `scheme://user:pass@host` URL. Only fires
/// when a colon appears between `://` and the `@`, on the SAME "word" (no
/// slash in between) - so an ordinary `https://example.com/a@b` is untouched.
fn redact_url_credentials(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    loop {
        let Some(scheme_at) = rest.find("://") else {
            out.push_str(rest);
            break;
        };
        let after = &rest[scheme_at + 3..];
        let seg_end = after
            .find(|c: char| c == '/' || c == ' ' || c == '"' || c == '\'' || c.is_whitespace())
            .unwrap_or(after.len());
        let authority = &after[..seg_end];
        out.push_str(&rest[..scheme_at + 3]);
        if let Some(at) = authority.rfind('@') {
            let userinfo = &authority[..at];
            if userinfo.contains(':') {
                out.push_str("[redacted: URL credentials]");
                out.push_str(&authority[at..]);
            } else {
                out.push_str(authority);
            }
        } else {
            out.push_str(authority);
        }
        rest = &after[seg_end..];
    }
    out
}

/// Redacts an `Authorization: <scheme> <value>` header line and a bare
/// `Bearer <token>`/`X-Jarvis-Token: <value>` wherever they appear, not only
/// at the start of a line.
///
/// The three markers below are matched one after another, and
/// `"Authorization: Bearer <token>"` matches BOTH the first and the second -
/// the `"bearer "` pass would otherwise walk straight into the first pass's
/// own `[redacted: ...]` text and mangle it. [`redact_after`]'s
/// `already_redacted` check is what stops that: once a marker's own output
/// is seen, it is copied through untouched rather than redacted a second
/// time - the same "a marker can never be matched again" rule
/// `jarvis_scrub.py`'s own `MARK` documents.
fn redact_headers(s: &str) -> String {
    let s = redact_after(s, "authorization:", true);
    let s = redact_after(&s, "bearer ", false);
    redact_after(&s, "x-jarvis-token:", false)
}

/// One `marker` (matched case-insensitively, wherever it appears), then -
/// optionally, for a header that names one - a scheme word ("Bearer"), then
/// one more "word" (a run with no whitespace) redacted as
/// `[redacted: an authorization value]`.
///
/// If what follows the marker (and scheme) is already a `[redacted: ...]`
/// marker from an earlier pass, it is copied through unchanged instead -
/// see [`redact_headers`]'s own doc comment for why this matters.
fn redact_after(s: &str, marker: &str, keep_scheme: bool) -> String {
    let marker_lower = marker.to_ascii_lowercase();
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    loop {
        let lower_rest = rest.to_ascii_lowercase();
        let Some(pos) = lower_rest.find(&marker_lower) else {
            out.push_str(rest);
            break;
        };
        let after_marker = pos + marker.len();
        out.push_str(&rest[..after_marker]);
        rest = &rest[after_marker..];

        let ws = rest.len() - rest.trim_start().len();
        out.push_str(&rest[..ws]);
        rest = &rest[ws..];

        if keep_scheme {
            let word_len = rest.find(char::is_whitespace).unwrap_or(rest.len());
            out.push_str(&rest[..word_len]);
            rest = &rest[word_len..];
            let ws2 = rest.len() - rest.trim_start().len();
            out.push_str(&rest[..ws2]);
            rest = &rest[ws2..];
        }

        if rest.starts_with(MARK) {
            let end = rest.find(']').map(|i| i + 1).unwrap_or(rest.len());
            out.push_str(&rest[..end]);
            rest = &rest[end..];
            continue;
        }

        let word_len = rest.find(char::is_whitespace).unwrap_or(rest.len());
        if word_len > 0 {
            out.push_str("[redacted: an authorization value]");
        }
        rest = &rest[word_len..];
    }
    out
}

/// Redacts the Windows user-folder segment of a path: `C:\Users\<name>\...`
/// or `C:/Users/<name>/...` becomes `C:\Users\[redacted: Windows user
/// name]\...`. Case-insensitive on `Users` (Windows paths are), and works
/// whether the path uses `\` or `/`.
fn redact_windows_username(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let lower = s.to_ascii_lowercase();
    let mut i = 0usize;
    while let Some(off) = lower[i..].find("users") {
        let start = i + off;
        out.push_str(&s[i..start]);
        let before_ok = start == 0 || matches!(s.as_bytes()[start - 1], b'\\' | b'/' | b':');
        let after = &s[start + 5..];
        let sep_ok = after.starts_with('\\') || after.starts_with('/');
        if !before_ok || !sep_ok {
            out.push_str(&s[start..start + 5]);
            i = start + 5;
            continue;
        }
        let sep = after.chars().next().unwrap();
        let rest = &after[1..];
        let name_len = rest.find(['\\', '/']).unwrap_or(rest.len());
        if name_len == 0 {
            out.push_str(&s[start..start + 5]);
            i = start + 5;
            continue;
        }
        out.push_str("Users");
        out.push(sep);
        out.push_str("[redacted: Windows user name]");
        i = start + 5 + 1 + name_len;
    }
    out.push_str(&s[i..]);
    out
}

/// Redacts a per-device key (docs/PAIRING-DESIGN.md 5.1, 8.6) wherever it
/// appears, even with no header or name around it: `jdk1.`, `d` and 8
/// lowercase hex characters, `.`, then 43 characters of `A-Z a-z 0-9 - _`,
/// the design's `jdk1\.d[0-9a-f]{8}\.[A-Za-z0-9_-]{43}`, matched by plain
/// scanning (no regex crate here, and nothing that can fail in a panic
/// hook). The prefix is kept so a bug report still says a key was there.
fn redact_device_keys(s: &str) -> String {
    const PREFIX: &str = "jdk1.";
    let key_char = |b: u8| b.is_ascii_alphanumeric() || b == b'-' || b == b'_';
    let bytes = s.as_bytes();
    let mut out = String::with_capacity(s.len());
    let mut i = 0usize;
    while let Some(off) = s[i..].find(PREFIX) {
        let start = i + off;
        let id = start + PREFIX.len();
        let secret = id + 10;
        let end = secret + 43;
        let shaped = bytes.len() >= end
            && bytes[id] == b'd'
            && bytes[id + 1..id + 9]
                .iter()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(b))
            && bytes[id + 9] == b'.'
            && bytes[secret..end].iter().all(|b| key_char(*b));
        out.push_str(&s[i..start]);
        if shaped {
            out.push_str("jdk1.[redacted: a device key]");
            // A longer run of key characters (or a second key run straight
            // on) is still part of the same blob; swallow it rather than
            // leave a tail of a secret.
            let mut j = end;
            while j < bytes.len() && (key_char(bytes[j]) || bytes[j] == b'.') {
                j += 1;
            }
            i = j;
        } else {
            out.push_str(PREFIX);
            i = id;
        }
    }
    out.push_str(&s[i..]);
    out
}

/// Scrubs one piece of text before it is ever written to `crash-notes.json`
/// or shown on screen. See the module doc comment for what this covers and
/// why it is a lighter, Rust-side subset of `jarvis_scrub.py` rather than a
/// full port of it. Never panics: this runs inside a panic hook, where a
/// second panic would be lost, so every step here is plain string scanning,
/// no parsing that can fail.
pub fn scrub(text: &str) -> String {
    // Bounded: a panic payload or a chained error can be arbitrarily long
    // (a whole HTML page, a stack of causes); a crash note is a diagnostic
    // line, not a full log.
    let bounded: String = text.chars().take(2000).collect();
    let s = redact_device_keys(&bounded);
    let s = redact_headers(&s);
    let s = redact_url_credentials(&s);
    let s = redact_named_secrets(&s);
    redact_windows_username(&s)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn redacts_a_device_key_with_nothing_around_it() {
        let key = format!("jdk1.d3f9a1c2e.{}", "Ab9_-".repeat(8) + "xyz");
        assert_eq!(key.len(), 58);
        let got = scrub(&format!("could not save {key} to the store"));
        assert_eq!(
            got,
            "could not save jdk1.[redacted: a device key] to the store"
        );
        assert!(!got.contains("Ab9_-"));
        // Not the shape: left as it is.
        assert_eq!(scrub("jdk1.d3f9a1c2e.short"), "jdk1.d3f9a1c2e.short");
        assert_eq!(scrub("jdk1.D3F9A1C2E.x"), "jdk1.D3F9A1C2E.x");
        assert_eq!(scrub("ends with jdk1."), "ends with jdk1.");
        // Two keys run together leave no tail of the second one.
        assert_eq!(
            scrub(&format!("{key}{key}")),
            "jdk1.[redacted: a device key]"
        );
    }

    #[test]
    fn leaves_ordinary_text_alone() {
        assert_eq!(
            scrub("index out of bounds: len 3 but index 5"),
            "index out of bounds: len 3 but index 5"
        );
        assert_eq!(
            scrub("connection refused (os error 10061)"),
            "connection refused (os error 10061)"
        );
    }

    #[test]
    fn redacts_a_named_secret_in_key_value_shape() {
        let got =
            scrub("panicked at src/token_store.rs:42: HUD_TOKEN=abc123def456 is not 32 bytes");
        assert!(!got.contains("abc123def456"), "{got}");
        assert!(got.contains("HUD_TOKEN"), "{got}");
        assert!(got.contains("[redacted: looks like a secret]"), "{got}");
    }

    #[test]
    fn redacts_a_json_shaped_secret() {
        let got = scrub(r#"could not parse {"password": "hunter2", "ok": true}"#);
        assert!(!got.contains("hunter2"), "{got}");
        assert!(got.contains("ok"), "{got}");
        assert!(got.contains("true"), "{got}");
    }

    #[test]
    fn leaves_a_non_secret_name_value_pair_alone() {
        let got = scrub("width=1024 height=768");
        assert_eq!(got, "width=1024 height=768");
    }

    #[test]
    fn redacts_authorization_and_bearer_and_the_pairing_token_header() {
        let got = scrub("sent Authorization: Bearer sk-abcDEF0123456789 to the server");
        assert!(!got.contains("sk-abcDEF0123456789"), "{got}");
        let got2 = scrub("header X-Jarvis-Token: 9f8e7d6c5b4a3928 refused");
        assert!(!got2.contains("9f8e7d6c5b4a3928"), "{got2}");
        assert!(got2.contains("refused"), "{got2}");
    }

    #[test]
    fn redacts_url_credentials_but_not_an_ordinary_path_with_an_at_sign() {
        let got = scrub("GET https://alex:s3cr3t@mail.example.com/inbox failed");
        assert!(!got.contains("s3cr3t"), "{got}");
        assert!(got.contains("mail.example.com"), "{got}");
        let ordinary = "see https://example.com/a@b for details";
        assert_eq!(scrub(ordinary), ordinary);
    }

    #[test]
    fn redacts_the_windows_user_folder_segment_both_slash_styles() {
        let a = scrub(r"failed to read C:\Users\pcadmin\Documents\jarvis-framework.toml");
        assert!(!a.contains("pcadmin"), "{a}");
        assert!(a.contains("jarvis-framework.toml"), "{a}");
        assert!(a.contains(r"C:\Users\"), "{a}");
        let b = scrub("failed to read C:/Users/pcadmin/Documents/jarvis-framework.toml");
        assert!(!b.contains("pcadmin"), "{b}");
    }

    #[test]
    fn a_marker_never_gets_scrubbed_twice_into_nonsense() {
        let once = scrub("HUD_TOKEN=abc123def456");
        let twice = scrub(&once);
        assert_eq!(once, twice);
    }

    #[test]
    fn never_panics_on_pathological_input() {
        // Trailing separators, lone markers, empty values, non-ASCII: none
        // of this may panic, because scrub() runs inside a panic hook.
        for input in [
            "",
            "HUD_TOKEN=",
            "HUD_TOKEN:",
            "Authorization:",
            "Bearer",
            "://",
            "://@",
            "C:\\Users\\",
            "C:\\Users",
            "caf\u{e9} HUD_TOKEN=caf\u{e9} \u{1f600}",
        ] {
            let _ = scrub(input);
        }
    }

    /// A throwaway file under the OS temp dir, unique per call - avoids
    /// adding a `tempfile` dev-dependency to `Cargo.toml` for two tests.
    /// Cleaned up by the caller with [`cleanup`].
    fn scratch_path(tag: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "jarvis-crash-notes-test-{tag}-{}-{:?}.json",
            std::process::id(),
            std::time::SystemTime::now()
        ))
    }

    fn cleanup(path: &Path) {
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn record_and_read_round_trip_and_keep_only_the_newest() {
        let path = scratch_path("round-trip");
        let mut notes = Vec::new();
        for i in 0..(MAX_NOTES + 3) {
            notes.push(CrashNote {
                when: i as u64,
                source: "backend".into(),
                kind: "crash".into(),
                detail: format!("note {i}"),
            });
        }
        save(&path, &notes);
        let loaded = load(&path);
        assert_eq!(loaded.len(), MAX_NOTES + 3);
        assert_eq!(loaded[0].detail, "note 0");

        // record() itself, through the same trim-to-MAX_NOTES logic.
        let _guard = WRITE_LOCK.lock().unwrap();
        let mut trimmed = load(&path);
        trimmed.push(CrashNote {
            when: 999,
            source: "desktop".into(),
            kind: "panic".into(),
            detail: "the newest one".into(),
        });
        if trimmed.len() > MAX_NOTES {
            let drop = trimmed.len() - MAX_NOTES;
            trimmed.drain(0..drop);
        }
        save(&path, &trimmed);
        drop(_guard);
        let after = load(&path);
        assert_eq!(after.len(), MAX_NOTES);
        assert_eq!(after.last().unwrap().detail, "the newest one");
        assert_eq!(after[0].detail, "note 4"); // the oldest 4 were dropped
        cleanup(&path);
    }

    #[test]
    fn a_missing_file_reads_as_empty_not_an_error() {
        let path = scratch_path("missing");
        assert_eq!(load(&path), Vec::<CrashNote>::new());
    }
}
