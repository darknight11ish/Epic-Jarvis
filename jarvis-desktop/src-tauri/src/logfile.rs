//! A log file, because a release build of this app has nowhere else to write.
//!
//! ## Why this exists
//!
//! `main.rs` carries `#![cfg_attr(not(debug_assertions), windows_subsystem =
//! "windows")]`. In a release build that means the process starts with **no
//! console**, so its standard handles are invalid. Every `println!` in this
//! crate — 72 of them — went nowhere, and `std::process::Command` with no
//! `Stdio` set hands those same dead handles to the Python child, so the
//! backend's own startup banner and traceback went nowhere either.
//!
//! The install guide's advice was therefore "start the backend in a terminal
//! while setting up", which is a workaround for this file not existing. When
//! the backend fails to start, nothing anywhere recorded why.
//!
//! ## What it does not do
//!
//! No `log` crate, no `tracing`, no subscriber, no levels beyond a tag in the
//! line. Two files, append-only, rotated by size:
//!
//! ```text
//! <app log dir>/jarvis-desktop.log   this process
//! <app log dir>/backend.log          whatever the Python child prints
//! ```
//!
//! A logging framework here would be a dependency, an init order, and a
//! filter configuration, to replace `writeln!`. The value was never in the
//! formatting; it was in there being a file at all.
//!
//! ## What must never be written here
//!
//! The pairing token, the contents of an approval prompt, a chat message, or
//! a memory fact. This file is plain text on disk with no redaction pass, it
//! outlives the process, and the owner will paste it into a bug report. Log
//! that something happened and what failed, never what it was about. The
//! backend's own log obeys the same rule on its side; see
//! `docs/ARCHITECTURE.md` §4.

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use tauri::{AppHandle, Manager};

/// Rotate at 4 MiB. Big enough to hold a long session, small enough that the
/// owner can open it in Notepad without waiting.
const MAX_BYTES: u64 = 4 * 1024 * 1024;

/// Resolved once at startup. A `OnceLock` rather than a parameter on every
/// call because `log()` is called from places that have no `AppHandle` —
/// notably the SSE reader and the process-tree killer.
static DIR: OnceLock<Option<PathBuf>> = OnceLock::new();

/// Point the logger at this app's log directory. Call once, early.
///
/// Returns the directory so the caller can say where it is. `None` means the
/// path could not be resolved or created, and every later `log()` becomes a
/// no-op rather than an error — a shell that will not start because it could
/// not open its log file is a worse outcome than a missing log.
pub fn init(app: &AppHandle) -> Option<PathBuf> {
    let resolved = app
        .path()
        .app_log_dir()
        .ok()
        .filter(|dir| std::fs::create_dir_all(dir).is_ok());
    // `set` fails only if init ran twice; the first directory wins and that is
    // the right answer either way.
    let _ = DIR.set(resolved.clone());
    resolved
}

/// Where the logs are, once `init` has run.
pub fn dir() -> Option<PathBuf> {
    DIR.get().cloned().flatten()
}

/// One line, timestamped, appended to the app log.
///
/// Prints to stderr as well. In a debug build that is the terminal the
/// developer is watching; in a release build it goes to the same dead handle
/// as before and costs nothing. Keeping both means `cargo run` behaves exactly
/// as it always did.
pub fn log(line: &str) {
    eprintln!("{line}");
    if let Some(dir) = dir() {
        append(&dir.join("jarvis-desktop.log"), line);
    }
}

/// A file for the Python child's stdout and stderr.
///
/// Two handles are needed because `Stdio` consumes the `File`; both point at
/// the same path in append mode, which is what a shell's `2>&1 >>file` does
/// and is safe for the interleaved line-at-a-time writes a Python process
/// makes. Returns `None` if the file cannot be opened, and the caller then
/// falls back to inheriting as before.
pub fn backend_sinks() -> Option<(File, File)> {
    let path = dir()?.join("backend.log");
    rotate_if_large(&path);
    let out = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .ok()?;
    let err = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .ok()?;
    Some((out, err))
}

/// Write a marker into the backend log so a restart is visible in it.
pub fn mark_backend(line: &str) {
    if let Some(dir) = dir() {
        append(&dir.join("backend.log"), line);
    }
}

fn append(path: &Path, line: &str) {
    rotate_if_large(path);
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        // Errors are dropped on purpose. A full disk must not turn every
        // logged event into a second failure, and there is nowhere to report
        // a logging failure to except the log.
        let _ = writeln!(f, "{} {}", stamp(), line);
    }
}

/// Rename to `<name>.1` once the file passes the cap, keeping exactly one
/// generation. Two files of bounded size beats an unbounded one, and beats a
/// numbered series nobody will ever read the sixth of.
fn rotate_if_large(path: &Path) {
    let too_big = std::fs::metadata(path)
        .map(|m| m.len() > MAX_BYTES)
        .unwrap_or(false);
    if !too_big {
        return;
    }
    let mut previous = path.as_os_str().to_os_string();
    previous.push(".1");
    // Errors ignored: on Windows the rename fails while another handle is open
    // on the target, and the correct response is to keep writing to the file
    // that is already too big rather than to stop logging.
    let _ = std::fs::rename(path, PathBuf::from(previous));
}

/// `2026-09-15 14:03:21` in UTC, computed without a date crate.
///
/// `chrono` and `time` are both absent from this crate's direct dependencies
/// and neither is worth adding for a log prefix. This is the civil-from-days
/// algorithm, which is exact for every date after 1970 and is about fifteen
/// lines.
fn stamp() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let (days, rem) = ((secs / 86_400) as i64, secs % 86_400);
    let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);

    // Howard Hinnant's civil_from_days, shifted to an era starting 0000-03-01
    // so that the leap day lands at the end of a 400-year cycle.
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let mth = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(mth <= 2);

    format!("{y:04}-{mth:02}-{d:02} {h:02}:{m:02}:{s:02}")
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The date maths is the only part of this file that can be wrong in a way
    /// nobody notices, so it is the part with a test. Values cross-checked
    /// against `date -u -d @<secs>`.
    #[test]
    fn the_timestamp_is_a_real_date() {
        // The function reads the clock, so the algorithm is exercised through
        // a local copy of the same arithmetic with a fixed input.
        fn at(secs: u64) -> String {
            let (days, rem) = ((secs / 86_400) as i64, secs % 86_400);
            let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
            let z = days + 719_468;
            let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
            let doe = z - era * 146_097;
            let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
            let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
            let mp = (5 * doy + 2) / 153;
            let d = doy - (153 * mp + 2) / 5 + 1;
            let mth = if mp < 10 { mp + 3 } else { mp - 9 };
            let y = yoe + era * 400 + i64::from(mth <= 2);
            format!("{y:04}-{mth:02}-{d:02} {h:02}:{m:02}:{s:02}")
        }
        assert_eq!(at(0), "1970-01-01 00:00:00");
        assert_eq!(at(1_000_000_000), "2001-09-09 01:46:40");
        // 2024-02-29: a leap day, which is what the era shift is for.
        assert_eq!(at(1_709_208_000), "2024-02-29 12:00:00");
        assert_eq!(at(1_788_000_000), "2026-08-29 10:40:00");
        // A date far enough out that a bad era shift would have drifted.
        assert_eq!(at(4_000_000_000), "2096-10-02 07:06:40");
    }

    /// A no-op logger must not panic when `init` was never called. Several
    /// call sites run before it, and every test in this crate runs without it.
    #[test]
    fn logging_without_a_directory_is_silent() {
        log("a line with nowhere to go");
        backend_sinks();
        mark_backend("and another");
    }
}
