//! When to put the owner's clipboard back after talk-to-type pasted.
//!
//! Adapted from Handy (https://github.com/cjpais/Handy,
//! `src-tauri/src/paste_tx/mod.rs`, read 2026-09-28). What was changed: the
//! macOS half, the "auto-submit" Enter and the paste-method setting are gone
//! (Jarvis pastes with Ctrl+V only and never presses Enter for the owner);
//! the comments are rewritten for this project. The decision itself -
//! [`evaluate`] and its timings - is Handy's, unchanged.
//!
//! MIT License
//!
//! Copyright (c) 2025 CJ Pais
//!
//! Permission is hereby granted, free of charge, to any person obtaining a
//! copy of this software and associated documentation files (the
//! "Software"), to deal in the Software without restriction, including
//! without limitation the rights to use, copy, modify, merge, publish,
//! distribute, sublicense, and/or sell copies of the Software, and to permit
//! persons to whom the Software is furnished to do so, subject to the
//! following conditions:
//!
//! The above copyright notice and this permission notice shall be included
//! in all copies or substantial portions of the Software.
//!
//! THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
//! OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
//! MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
//! NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
//! DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
//! OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
//! USE OR OTHER DEALINGS IN THE SOFTWARE.
//!
//! ## What it is for, in plain words
//!
//! Talk-to-type puts the words on the clipboard and presses Ctrl+V for the
//! owner. The program in front reads the clipboard whenever it gets round to
//! it, so putting the owner's own clipboard back after a FIXED wait can lose
//! the race and paste their old clipboard instead. So the words are offered
//! as a promise, and Windows tells this app when a program actually reads
//! them - a "receipt". Two rules make a receipt mean something:
//!
//! 1. Only a read AFTER Ctrl+V was pressed counts. A read before it is
//!    another program (a clipboard manager) reacting to the change itself.
//! 2. The owner's clipboard is put back only while the words are still the
//!    newest thing on it. If the owner copied something else meanwhile,
//!    their copy wins and nothing is put back over it.
//!
//! The words stay on the clipboard for a short quiet time after the LAST
//! read (some programs read twice per paste), and never longer than
//! [`RESTORE_TIMEOUT`].

#![cfg_attr(not(windows), allow(dead_code))]

use std::time::{Duration, Instant};

/// How long after the LAST read the words stay on the clipboard before the
/// owner's clipboard is put back (Handy: some programs read twice).
pub(crate) const QUIET_PERIOD: Duration = Duration::from_millis(200);

/// The longest the words may sit on the clipboard, read or not.
pub(crate) const RESTORE_TIMEOUT: Duration = Duration::from_secs(8);

/// When Ctrl+V could not be sent at all, no real read can come, so the
/// owner's clipboard goes back quickly.
pub(crate) const FAILED_INJECTION_TIMEOUT: Duration = Duration::from_millis(500);

/// How long Ctrl stays down around the V (Handy's number: some systems
/// dropped a chord released faster).
pub(crate) const CHORD_HOLD: Duration = Duration::from_millis(100);

/// One paste, shared between the thread that owns the clipboard and the one
/// that presses Ctrl+V.
#[derive(Debug)]
pub(crate) struct TxState {
    /// When the words were put on the clipboard.
    pub published_at: Instant,
    /// When Ctrl+V was sent. Only reads after this count.
    pub injected_at: Option<Instant>,
    /// Ctrl+V could not be sent.
    pub injection_failed: bool,
    /// When a program asked for the words.
    pub receipts: Vec<Instant>,
    /// Someone else took the clipboard (the owner copied something).
    pub ownership_lost: bool,
    /// Settled early (a newer paste, or Stop everything).
    pub cancelled: bool,
}

impl TxState {
    pub fn new() -> Self {
        Self {
            published_at: Instant::now(),
            injected_at: None,
            injection_failed: false,
            receipts: Vec::new(),
            ownership_lost: false,
            cancelled: false,
        }
    }

    pub fn record_receipt(&mut self, at: Instant) {
        self.receipts.push(at);
    }

    pub fn last_receipt_after_injection(&self) -> Option<Instant> {
        let injected = self.injected_at?;
        self.receipts.iter().copied().rev().find(|t| *t >= injected)
    }

    pub fn any_receipt_after_injection(&self) -> bool {
        self.last_receipt_after_injection().is_some()
    }
}

pub(crate) enum WaitDecision {
    KeepWaiting,
    /// Stop waiting and settle: put the owner's clipboard back if it is
    /// still ours to put back.
    Finish,
}

/// Keep waiting for the program to read, or finish now. Handy's rule,
/// unchanged.
pub(crate) fn evaluate(state: &TxState, now: Instant) -> WaitDecision {
    if state.ownership_lost || state.cancelled {
        return WaitDecision::Finish;
    }
    if let Some(last) = state.last_receipt_after_injection() {
        if now.duration_since(last) >= QUIET_PERIOD {
            return WaitDecision::Finish;
        }
    }
    let deadline = if state.injection_failed {
        FAILED_INJECTION_TIMEOUT
    } else {
        RESTORE_TIMEOUT
    };
    if now.duration_since(state.published_at) >= deadline {
        return WaitDecision::Finish;
    }
    WaitDecision::KeepWaiting
}

/// How one paste ended, for the owner's message.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Settled {
    /// The program in front read the words after Ctrl+V.
    Read,
    /// Nothing read them before the timeout: the program in front did not
    /// take a paste (a program running as administrator ignores keys from
    /// one that is not, and Windows gives no sign of it).
    NotRead,
    /// Ctrl+V could not be sent.
    KeysRefused,
}

impl Settled {
    pub(crate) fn from_state(state: &TxState) -> Self {
        if state.any_receipt_after_injection() {
            Settled::Read
        } else if state.injection_failed {
            Settled::KeysRefused
        } else {
            Settled::NotRead
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn state_after_publish(published_ago: Duration) -> TxState {
        let mut s = TxState::new();
        s.published_at = Instant::now() - published_ago;
        s
    }

    #[test]
    fn keeps_waiting_without_receipt_within_timeout() {
        let s = state_after_publish(Duration::from_millis(100));
        assert!(matches!(
            evaluate(&s, Instant::now()),
            WaitDecision::KeepWaiting
        ));
    }

    #[test]
    fn finishes_after_quiet_period_once_read() {
        let mut s = state_after_publish(Duration::from_millis(300));
        s.injected_at = Some(Instant::now() - Duration::from_millis(250));
        s.receipts.push(Instant::now() - QUIET_PERIOD);
        assert!(matches!(evaluate(&s, Instant::now()), WaitDecision::Finish));
        assert_eq!(Settled::from_state(&s), Settled::Read);
    }

    #[test]
    fn waits_through_quiet_period_after_recent_read() {
        let mut s = state_after_publish(Duration::from_millis(300));
        s.injected_at = Some(Instant::now() - Duration::from_millis(100));
        s.receipts.push(Instant::now() - Duration::from_millis(50));
        assert!(matches!(
            evaluate(&s, Instant::now()),
            WaitDecision::KeepWaiting
        ));
    }

    #[test]
    fn pre_injection_receipt_does_not_count() {
        let mut s = state_after_publish(Duration::from_millis(300));
        s.receipts.push(Instant::now() - Duration::from_millis(200));
        s.injected_at = Some(Instant::now() - Duration::from_millis(100));
        assert!(!s.any_receipt_after_injection());
        assert!(matches!(
            evaluate(&s, Instant::now()),
            WaitDecision::KeepWaiting
        ));
        assert_eq!(Settled::from_state(&s), Settled::NotRead);
    }

    #[test]
    fn finishes_on_timeout_without_receipt() {
        let s = state_after_publish(RESTORE_TIMEOUT);
        assert!(matches!(evaluate(&s, Instant::now()), WaitDecision::Finish));
    }

    #[test]
    fn failed_injection_uses_short_timeout() {
        let mut s = state_after_publish(FAILED_INJECTION_TIMEOUT);
        s.injection_failed = true;
        assert!(matches!(evaluate(&s, Instant::now()), WaitDecision::Finish));
        assert_eq!(Settled::from_state(&s), Settled::KeysRefused);
    }

    #[test]
    fn ownership_loss_finishes_immediately() {
        let mut s = state_after_publish(Duration::from_millis(10));
        s.ownership_lost = true;
        assert!(matches!(evaluate(&s, Instant::now()), WaitDecision::Finish));
    }
}
