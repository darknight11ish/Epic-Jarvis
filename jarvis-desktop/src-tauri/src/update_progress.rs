//! What the updater is doing, while it is doing it.
//!
//! The owner asked for one thing on 2026-10-16: *"user should have visibility in
//! where the updater is currently at and if its checking anything."* The raw
//! material already exists and is already written down: `scripts/apply-patches.ps1`
//! prints `Rehearsing all 145 on a copy first.`, then one line per patch, then one
//! `ok`/`skip`/`FAIL` line per test suite, then a verdict - and `backend_update.rs`
//! redirects all of it into one file (one handle, `try_clone`d, so stdout and stderr
//! share a write position).
//!
//! **Why the file is tailed rather than the child's output piped to us.** That
//! redirect is not an accident: the comment on it says two `File::create` calls
//! would give each stream its own position and "every stderr line would overwrite
//! the stdout line under it". Reading the same file as it grows keeps that
//! guarantee, keeps the file the owner can already open and read afterwards, and
//! costs the child nothing. Polling instead of tailing would be the same work with
//! a worse answer to "is it still going?", so the tailer polls the *file* at a fixed
//! beat and emits only when something was actually said.
//!
//! Nothing here decides anything and nothing here changes anything: it reads a log
//! the updater is writing anyway, and hands the screen a phase, a count and the
//! verdict. `progress_of` is pure, so the reading of those lines is a test rather
//! than a hope - the cases in `mod tests` are the real lines out of the owner's own
//! `_jarvis-logs`.

use serde::Serialize;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::time::Duration;

/// The event the Settings card listens for. Sent with a [`Progress`].
pub const PROGRESS_EVENT: &str = "backend-update-progress";

/// How often the file is read for new lines.
const BEAT: Duration = Duration::from_millis(400);

/// The most failed checks the payload carries, so a catastrophic run cannot grow
/// the event without bound. The count itself is never capped.
const MAX_BAD: usize = 20;

/// One check the patcher reported as failed.
#[derive(Debug, Clone, Default, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct BadCheck {
    /// `test_voice_mic.py`, or `appearance.patch`.
    pub name: String,
    /// The patcher's own words after the name - shown verbatim.
    pub reason: String,
    /// False when this is a check that could not RUN on this PC rather than a
    /// check that ran and failed. See [`could_not_run`].
    pub ran_here: bool,
}

/// Where the run is, in counts - never in invented percentages.
#[derive(Debug, Clone, Default, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct Progress {
    /// `reading`, `rehearsing`, `applying`, `testing`, `done`.
    pub phase: String,
    /// Items finished in this phase (patches, or test suites).
    pub done: u32,
    /// The phase's own total when the log said one, else `None` - the screen
    /// shows a count without a denominator rather than a made-up one.
    pub total: Option<u32>,
    /// `FAIL` lines seen in this phase.
    pub failed: u32,
    /// `skip` lines seen in this phase.
    pub skipped: u32,
    /// `ok`, `problems`, `unproven`, or `None` while it is still going.
    pub verdict: Option<String>,
    /// The failed checks, at most [`MAX_BAD`] of them.
    pub bad: Vec<BadCheck>,
}

/// Is this failure a check that could not RUN here, rather than a check that ran
/// and failed?
///
/// The owner's own run on 2026-10-16 ended `DONE WITH PROBLEMS` with four
/// failures, and **three of the four were this**: the update was fine and the
/// screen said it was untrustworthy. So the two signatures below - both of which
/// are the PC refusing something, in words the check itself printed - are counted
/// apart from a real failure. **Deliberately only what can be named**: a reason
/// that is not here counts as a real failure, because calling a real failure
/// "could not run" is the dangerous direction of this mistake.
pub fn could_not_run(reason: &str) -> bool {
    let said = reason.to_ascii_lowercase();
    said.contains("access is denied") || said.contains("__pycache__")
}

/// Reads one line of the patcher's output into `p`. Pure; no I/O, no globals.
///
/// Every branch below is a line shape taken from the owner's own logs
/// (`_jarvis-logs/apply-patches-*.txt`), and the tests at the bottom of this file
/// are those lines.
pub fn progress_of(line: &str, p: &mut Progress) {
    let text = line.trim_end();
    let trimmed = text.trim();

    // --- the phase markers -------------------------------------------------
    if let Some(rest) = trimmed.strip_prefix("Rehearsing all ") {
        if let Some(count) = rest.split_whitespace().next().and_then(|n| n.parse().ok()) {
            p.phase = "rehearsing".to_string();
            p.done = 0;
            p.total = Some(count);
            p.failed = 0;
            p.skipped = 0;
            p.bad.clear();
            return;
        }
    }
    if trimmed.starts_with("Rehearsing again:") || trimmed.starts_with("Taking off ") {
        // The second rehearsal: the same list, counted from the start again.
        p.phase = "rehearsing".to_string();
        p.done = 0;
        p.failed = 0;
        p.skipped = 0;
        p.bad.clear();
        return;
    }
    if trimmed.starts_with("Applying ") && trimmed.contains("patch") {
        p.phase = "applying".to_string();
        p.done = 0;
        p.failed = 0;
        return;
    }
    if trimmed == "Running the test suites against the patched backend." {
        p.phase = "testing".to_string();
        p.done = 0;
        p.skipped = 0;
        // The suites are globbed, so the total is known only when they are done:
        // the screen shows "12 suites" rather than "12 of 300".
        p.total = None;
        return;
    }

    // --- the verdicts ------------------------------------------------------
    if trimmed.starts_with("DONE WITH PROBLEMS") {
        p.phase = "done".to_string();
        p.verdict = Some("problems".to_string());
        return;
    }
    if trimmed.starts_with("DONE - no problems") {
        p.phase = "done".to_string();
        p.verdict = Some(if trimmed.contains("NOT fully proven") {
            "unproven".to_string()
        } else {
            "ok".to_string()
        });
        return;
    }
    if trimmed.starts_with("FAIL ") && trimmed.contains("patch(es) will not apply") {
        p.phase = "done".to_string();
        p.verdict = Some("problems".to_string());
        return;
    }

    // --- one line per patch, and one per test suite ------------------------
    //   "  ok           voice-turn.patch"
    //   "  FAIL  screen.patch - will not apply"
    //   "  skip  test_decks.py - passed, but 2 part(s) were SKIPPED (not proven)"
    let body = ["ok ", "FAIL ", "skip "]
        .into_iter()
        .find_map(|kind| trimmed.strip_prefix(kind).map(|rest| (kind.trim(), rest)));
    let Some((kind, rest)) = body else { return };
    // Only the indented form is a per-item line: the script's own summary lines
    // are not indented, and counting one of those as an item would make the
    // total wrong.
    if !text.starts_with("  ") {
        return;
    }
    p.done += 1;
    if kind == "skip" {
        p.skipped += 1;
        return;
    }
    if kind != "FAIL" {
        return;
    }
    p.failed += 1;
    let (name, reason) = match rest.split_once(" - ") {
        Some((name, reason)) => (name.trim(), reason.trim()),
        None => (rest.trim(), ""),
    };
    if p.bad.len() < MAX_BAD {
        p.bad.push(BadCheck {
            name: name.to_string(),
            reason: reason.to_string(),
            ran_here: !could_not_run(reason),
        });
    }
}

/// Reads whatever the patcher has written since last time, and calls `say` for
/// each complete line.
///
/// Returns false when the file is gone (the run is over, or it never started).
pub fn read_new_lines(
    file: &Path,
    from: &mut u64,
    buffer: &mut Vec<u8>,
    mut say: impl FnMut(&str),
) -> bool {
    let Ok(mut handle) = std::fs::File::open(file) else {
        return false;
    };
    if handle.seek(SeekFrom::Start(*from)).is_err() {
        return false;
    }
    let mut fresh = Vec::new();
    if handle.read_to_end(&mut fresh).is_err() {
        return false;
    }
    *from += fresh.len() as u64;
    buffer.extend_from_slice(&fresh);
    for line in take_lines(buffer) {
        say(&line);
    }
    true
}

/// Takes every COMPLETE line out of `buffer`, leaving any half-written one behind
/// for the next read. Pure, so the rule the tailer lives by is a test and not a
/// hope: a line the child has not finished is never handed to the screen.
pub fn take_lines(buffer: &mut Vec<u8>) -> Vec<String> {
    let mut out = Vec::new();
    while let Some(end) = buffer.iter().position(|b| *b == b'\n') {
        let line: Vec<u8> = buffer.drain(..=end).collect();
        out.push(
            String::from_utf8_lossy(&line[..line.len() - 1])
                .trim_end_matches('\r')
                .to_string(),
        );
    }
    out
}

/// Watches `file` until `stop` is true, calling `say` for each new line.
///
/// Runs on its own thread for the length of the run; the caller owns the child and
/// the file, so this only ever reads.
pub fn tail(
    file: PathBuf,
    stop: std::sync::Arc<std::sync::atomic::AtomicBool>,
    mut say: impl FnMut(&str) + Send + 'static,
) {
    let mut from = 0u64;
    let mut buffer: Vec<u8> = Vec::new();
    loop {
        let alive = read_new_lines(&file, &mut from, &mut buffer, |line| say(line));
        if stop.load(std::sync::atomic::Ordering::Relaxed) {
            if !alive {
                return;
            }
            // One last read, so the verdict that lands with the child's exit is
            // never missed, then stop.
            read_new_lines(&file, &mut from, &mut buffer, |line| say(line));
            return;
        }
        std::thread::sleep(BEAT);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn read(lines: &[&str]) -> Progress {
        let mut p = Progress::default();
        for line in lines {
            progress_of(line, &mut p);
        }
        p
    }

    /// The owner's own run of 2026-10-16 (`apply-patches-2026-10-16-001320.txt`),
    /// abridged: the rehearsal that found 143 patches on, then the second
    /// rehearsal that failed 32 of them.
    #[test]
    fn the_rehearsal_is_counted_from_the_line_the_script_prints() {
        let p = read(&[
            "Rehearsing all 143 on a copy first.",
            "  ok           voice-turn.patch",
            "  ok           reach.patch",
            "  skip  embedding-guard.patch - left out whole: the rebuilt modules already carry it",
            "Rehearsing again: take those off, newest first, then put all",
            "  FAIL  rebuilt-patches\\memory-safety.patch - will not apply",
            "  ok           events-pump.patch",
        ]);
        assert_eq!(p.phase, "rehearsing");
        assert_eq!(p.total, Some(143));
        // Reset by the second rehearsal, then two items: one FAIL, one ok - the
        // skip before it belongs to the first round and is not carried over.
        assert_eq!(p.done, 2);
        assert_eq!(p.failed, 1);
        assert_eq!(p.skipped, 0);
        assert_eq!(p.bad.len(), 1);
        assert_eq!(p.bad[0].name, "rebuilt-patches\\memory-safety.patch");
        assert_eq!(p.bad[0].reason, "will not apply");
        assert!(p.bad[0].ran_here);
    }

    #[test]
    fn the_test_phase_counts_suites_and_keeps_their_reasons() {
        let p = read(&[
            "Running the test suites against the patched backend.",
            "  ok    test_agent.py",
            "  skip  test_decks.py - passed, but 2 part(s) were SKIPPED (not proven)",
            "  FAIL  test_media.py - Access is denied: the folder would not be written",
            "  FAIL  test_tools.py - the run left a __pycache__ behind and read it back",
            "  FAIL  test_real.py - three rows came back instead of four",
        ]);
        assert_eq!(p.phase, "testing");
        assert_eq!(
            p.total, None,
            "the suite count is not known until they are done"
        );
        assert_eq!(p.done, 5);
        assert_eq!(p.failed, 3);
        assert_eq!(p.skipped, 1);
        // The distinction the owner's screen needs: two of these could not RUN
        // here, one really failed. Losing it is what made 2026-10-16's screen say
        // the update was untrustworthy when three of its four failures were this.
        assert_eq!(
            p.bad.iter().map(|b| b.ran_here).collect::<Vec<_>>(),
            vec![false, false, true]
        );
        assert_eq!(
            p.bad[0].reason,
            "Access is denied: the folder would not be written"
        );
        assert_eq!(p.bad[2].name, "test_real.py");
    }

    #[test]
    fn the_verdicts_are_read_in_the_scripts_own_words() {
        let problems = read(&[" DONE WITH PROBLEMS - do not trust this update yet"]);
        assert_eq!(problems.phase, "done");
        assert_eq!(problems.verdict.as_deref(), Some("problems"));

        let clean = read(&[" DONE - no problems"]);
        assert_eq!(clean.verdict.as_deref(), Some("ok"));

        let unproven = read(&[
            " DONE - no problems, but NOT fully proven (see below)",
            "  note: The test suites were not run (-SkipTests), so this update is applied but NOT proven.",
        ]);
        assert_eq!(unproven.verdict.as_deref(), Some("unproven"));

        let refused = read(&["FAIL  32 patch(es) will not apply to your files as they are: a.patch, b.patch. Nothing was changed."]);
        assert_eq!(refused.verdict.as_deref(), Some("problems"));
    }

    #[test]
    fn a_summary_line_is_never_counted_as_an_item() {
        // Not indented, so it is the script talking about the list, not one of it.
        let p = read(&[
            "Rehearsing all 143 on a copy first.",
            "ok    All 143 patches are already applied. Nothing to do.",
            "  ok    Checked again on the real files: all 142 patches are on.",
        ]);
        assert_eq!(
            p.done, 1,
            "an unindented summary line was counted as a patch"
        );
    }

    #[test]
    fn only_named_reasons_count_as_could_not_run() {
        assert!(could_not_run(
            "Access is denied: the folder would not be written"
        ));
        assert!(could_not_run(
            "the run left a __pycache__ behind and read it back"
        ));
        assert!(!could_not_run("three rows came back instead of four"));
        assert!(!could_not_run(""));
    }

    #[test]
    fn a_half_written_line_waits_for_its_newline() {
        // The tailer's own contract, as the pure function under it. This used to
        // write a scratch file under %TEMP%, which THIS PC refuses (the same
        // `Access is denied` that makes three other suites here fail on
        // unmodified main) - a test that cannot pass at the desk is worse than no
        // test, so the rule is checked where it lives.
        let mut buffer = b"Rehearsing all 5 on a copy first.\n  ok   a.patch\n  FA".to_vec();
        let first = take_lines(&mut buffer);
        assert_eq!(
            first,
            vec!["Rehearsing all 5 on a copy first.", "  ok   a.patch"]
        );
        assert_eq!(buffer, b"  FA", "the half-written line was handed over");

        buffer.extend_from_slice(b"IL  b.patch - no\n");
        assert_eq!(take_lines(&mut buffer), vec!["  FAIL  b.patch - no"]);
        assert!(buffer.is_empty());

        // A Windows line ending is not part of the line.
        let mut crlf = b"  ok   c.patch\r\n".to_vec();
        assert_eq!(take_lines(&mut crlf), vec!["  ok   c.patch"]);
    }
}
