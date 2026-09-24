//! The rules behind Windows Hello (lock.rs), with no Tauri in them: which
//! approvals are risky, what counts as loosening a setting, what Windows'
//! answers mean, and what the Brain's hidden lists keep.
//!
//! Split from the commands next door, like `brain/routes.rs`, so these can be
//! compiled and tested without an app, a window or Windows - they are the
//! part a mistake in would quietly weaken the lock.

use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

/// "Lock again after", in seconds: straight away, 1, 5 and 15 minutes.
pub const RELOCK_CHOICES: [u32; 4] = [0, 60, 300, 900];

/// The shortest "away" that counts. "Straight away" still has to survive the
/// Windows Hello prompt itself taking focus and handing it back, and moving
/// from one Jarvis window to another - both are a focus change of a few
/// milliseconds that must not read as the owner leaving.
const GRACE: Duration = Duration::from_secs(3);

/// The phone's own retry pause (BiometricGate.RETRY_DELAY_MS): long enough for
/// a reader another program was holding to be let go.
#[cfg_attr(not(windows), allow(dead_code))] // read only by the Windows `hello` module and the tests
pub(super) const RETRY_DELAY: Duration = Duration::from_millis(600);

// ---------------------------------------------------------------------------
// The words. One place, so every surface says the same thing.
// ---------------------------------------------------------------------------

/// The pages append " - nothing was decided. Try again." to these, so none of
/// them says "nothing was sent" itself - and none may contain the word
/// "already": main.js and widget.js read that word as "someone else answered
/// it" and would stop offering the card.
pub const NOT_CONFIRMED: &str = "Windows Hello did not confirm it was you";
pub const COULD_NOT_SHOW: &str =
    "The Windows Hello check could not be shown just now. Wait a moment";
pub const NOT_SET_UP: &str = "Windows Hello is not set up on this PC, and a lock is on in \
     Settings, so Jarvis cannot check it is you. Set up Windows Hello in Windows Settings, \
     Accounts, Sign-in options - a PIN is enough";
/// Turning a lock ON with nothing to check against would lock the owner out:
/// loosening needs Windows Hello, so there would be no way back.
pub const TURN_ON_NEEDS_HELLO: &str = "Windows Hello is not set up on this PC, so this lock \
     cannot be turned on - it could never be unlocked again. Set up Windows Hello in Windows \
     Settings, Accounts, Sign-in options (a PIN is enough), then try again.";
pub const PRIVATE_STILL_HIDDEN: &str = "What Jarvis remembers about you is hidden. Press Show \
     on the Brain's Memory tab and confirm it is you with Windows Hello first.";

/// What the Windows Hello prompt says, per purpose.
pub(super) const UNLOCK_MESSAGE: &str = "Unlock Jarvis";
pub(super) const LOOSEN_MESSAGE: &str = "Confirm it is you to loosen Jarvis's security settings";
pub(super) const REVEAL_MESSAGE: &str = "Confirm it is you to show what Jarvis remembers about you";

// ---------------------------------------------------------------------------
// The settings
// ---------------------------------------------------------------------------

/// Which approvals ask for Windows Hello. Two values and no third: there is no
/// "never", so nothing can store one.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum ApprovalCheck {
    /// The phone's rule - [`is_risky`].
    #[default]
    Risky,
    /// Every approval, risky or not.
    Every,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Security {
    /// Opening the Jarvis bar, the Brain or Settings needs Windows Hello.
    pub app_lock: bool,
    /// How long away before the lock asks again. One of [`RELOCK_CHOICES`].
    pub relock_after_secs: u32,
    pub approvals: ApprovalCheck,
    /// The Brain's memory lists and chat history stay hidden until Show passes
    /// Windows Hello (brain_read, and brain/history.rs).
    pub private_answers: bool,
}

impl Default for Security {
    fn default() -> Self {
        Self {
            app_lock: false,
            relock_after_secs: 60,
            approvals: ApprovalCheck::Risky,
            private_answers: false,
        }
    }
}

impl Security {
    /// Anything beyond the defaults. The defaults are the phone's behaviour,
    /// including its "no fingerprint set up at all: the decision proceeds";
    /// once the owner has turned a lock on, a PC with no Windows Hello refuses
    /// instead ([`approval_verdict`]).
    pub fn any_lock_on(&self) -> bool {
        self.app_lock || self.private_answers || self.approvals == ApprovalCheck::Every
    }

    /// "Lock again after", never shorter than [`GRACE`].
    pub fn relock(&self) -> Duration {
        Duration::from_secs(u64::from(self.relock_after_secs)).max(GRACE)
    }

    /// A value typed by a page: refused unless it is one of the four choices.
    pub fn validate(&self) -> Result<(), String> {
        if RELOCK_CHOICES.contains(&self.relock_after_secs) {
            Ok(())
        } else {
            Err(format!(
                "{} seconds is not one of the \"Lock again after\" choices",
                self.relock_after_secs
            ))
        }
    }

    /// A value read back from disk: an unknown relock time becomes the
    /// longest choice that is not longer than it - the stricter side.
    fn normalised(mut self) -> Self {
        if !RELOCK_CHOICES.contains(&self.relock_after_secs) {
            self.relock_after_secs = RELOCK_CHOICES
                .iter()
                .copied()
                .filter(|c| *c <= self.relock_after_secs)
                .max()
                .unwrap_or(0);
        }
        self
    }
}

/// The stored value, read. Anything unreadable is the defaults.
pub fn parse_stored(value: serde_json::Value) -> Security {
    serde_json::from_value::<Security>(value)
        .map(Security::normalised)
        .unwrap_or_default()
}

/// True when `new` loosens anything `old` had: a lock turned off, a longer
/// "Lock again after", or approvals moved from every one back to risky only.
/// Loosening needs Windows Hello first; everything else is instant.
pub fn loosens(old: &Security, new: &Security) -> bool {
    (old.app_lock && !new.app_lock)
        || new.relock_after_secs > old.relock_after_secs
        || (old.approvals == ApprovalCheck::Every && new.approvals == ApprovalCheck::Risky)
        || (old.private_answers && !new.private_answers)
}

/// True when changing `old` to `new` needs a confirmed Windows Hello check
/// first: it loosens something, and something was on to loosen. With no lock
/// on at all, "Lock again after" governs nothing yet, so moving it is not
/// held up - turning a lock on later is a tightening either way.
pub fn change_needs_hello(old: &Security, new: &Security) -> bool {
    old.any_lock_on() && loosens(old, new)
}

/// True when `new` turns on a lock `old` did not have. Instant - but refused
/// when this PC has no Windows Hello, because nothing could ever unlock it.
pub fn adds_lock(old: &Security, new: &Security) -> bool {
    (!old.app_lock && new.app_lock)
        || (!old.private_answers && new.private_answers)
        || (old.approvals == ApprovalCheck::Risky && new.approvals == ApprovalCheck::Every)
}

// ---------------------------------------------------------------------------
// Which approvals need the check - the phone's rule
// ---------------------------------------------------------------------------

/// BiometricGate.required(), on the server's own JSON row: anything the
/// server has not classified, anything that leaves this PC, anything that
/// cannot be undone, and anything outside text tried to rush. The defaults
/// are the phone's too: a missing `reach` is "outbound", a missing
/// `reversible` is "no", a missing `risk` is unclassified.
pub fn is_risky(item: &serde_json::Value) -> bool {
    let risk = &item["risk"];
    if risk["classified"].as_bool() != Some(true) {
        return true;
    }
    if risk["reach"].as_str().unwrap_or("outbound") == "outbound" {
        return true;
    }
    if risk["reversible"].as_str().unwrap_or("no") == "no" {
        return true;
    }
    // A rush latch: slowing the decision down is the entire response.
    !matches!(
        item.get("raised"),
        None | Some(serde_json::Value::Null) | Some(serde_json::Value::Bool(false))
    )
}

/// Whether approving `item` asks Windows Hello first. An id this PC cannot
/// find in its queue is treated as risky: not knowing is not "safe".
pub fn approval_needs_check(mode: ApprovalCheck, item: Option<&serde_json::Value>) -> bool {
    match mode {
        ApprovalCheck::Every => true,
        ApprovalCheck::Risky => item.is_none_or(is_risky),
    }
}

// ---------------------------------------------------------------------------
// The check's outcome
// ---------------------------------------------------------------------------

/// The phone's four outcomes (BiometricGate.Outcome), same meanings.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    /// The owner confirmed.
    Confirmed,
    /// They dismissed it, or ran out of tries. Not an error: nothing is sent.
    Cancelled,
    /// This PC has no Windows Hello at all: nothing set up, or turned off by
    /// a policy.
    Unavailable,
    /// The check exists but could not be shown just now, even after one retry.
    /// Nothing is sent - a passing glitch never waves a decision through.
    Failed,
}

/// One attempt's result: an [`Outcome`], or "try once more".
#[cfg_attr(not(windows), allow(dead_code))] // read only by the Windows `hello` module and the tests
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum Attempt {
    Done(Outcome),
    Transient,
}

/// `UserConsentVerifierAvailability`, by value, before any prompt. `None`
/// means "show the prompt". Only "nothing set up" and "turned off" pass as
/// Unavailable; busy, and anything this code does not know, is temporary.
#[cfg_attr(not(windows), allow(dead_code))]
pub(super) fn before_prompt(availability: i32) -> Option<Attempt> {
    match availability {
        0 => None,                                          // Available
        1..=3 => Some(Attempt::Done(Outcome::Unavailable)), // DeviceNotPresent, NotConfiguredForUser, DisabledByPolicy
        _ => Some(Attempt::Transient),                      // DeviceBusy, or unknown
    }
}

/// `UserConsentVerificationResult`, by value.
#[cfg_attr(not(windows), allow(dead_code))]
pub(super) fn after_prompt(result: i32) -> Attempt {
    match result {
        0 => Attempt::Done(Outcome::Confirmed),       // Verified
        1..=3 => Attempt::Done(Outcome::Unavailable), // DeviceNotPresent, NotConfiguredForUser, DisabledByPolicy
        5 | 6 => Attempt::Done(Outcome::Cancelled),   // RetriesExhausted, Canceled
        _ => Attempt::Transient,                      // DeviceBusy, or unknown
    }
}

/// What happens to an approval after the check. The one place "Unavailable"
/// splits: with no lock on, it is the phone's rule (a PC with no Windows
/// Hello answers as before); with any lock on, the owner asked for checks,
/// and a check that cannot happen refuses.
pub fn approval_verdict(outcome: Outcome, security: &Security) -> Result<(), String> {
    match outcome {
        Outcome::Confirmed => Ok(()),
        Outcome::Unavailable if !security.any_lock_on() => Ok(()),
        other => strict_verdict(other),
    }
}

/// Unlocking, loosening a setting and Show: nothing passes without a
/// confirmed check.
pub fn strict_verdict(outcome: Outcome) -> Result<(), String> {
    match outcome {
        Outcome::Confirmed => Ok(()),
        Outcome::Cancelled => Err(NOT_CONFIRMED.to_string()),
        Outcome::Unavailable => Err(NOT_SET_UP.to_string()),
        Outcome::Failed => Err(COULD_NOT_SHOW.to_string()),
    }
}

// ---------------------------------------------------------------------------
// Being away
// ---------------------------------------------------------------------------

/// True when `last` was within `relock` of `now`.
pub fn within(last: Option<Instant>, relock: Duration, now: Instant) -> bool {
    last.is_some_and(|t| now.saturating_duration_since(t) <= relock)
}

/// The prompt's words for one approval: the gate's own title (built from the
/// action name and the risk table, never the payload) and the consequence in
/// the server's words, as the phone puts on its prompt.
pub(super) fn approval_message(item: Option<&serde_json::Value>) -> String {
    let title = item
        .and_then(|i| i["notice"]["title"].as_str())
        .filter(|t| !t.trim().is_empty())
        .map(str::to_string)
        .or_else(|| {
            item.and_then(|i| i["action"].as_str())
                .map(|a| format!("Approve: {a}"))
        })
        .unwrap_or_else(|| "Approve a Jarvis action".to_string());
    let why = item
        .and_then(|i| i["risk"]["why"].as_str())
        .filter(|w| !w.trim().is_empty())
        .unwrap_or("Check the card before you confirm.");
    let text = format!("{title}\n{why}");
    text.chars().take(300).collect()
}

/// The Brain sections whose entries are private, and the key each list is in.
const PRIVATE_LISTS: &[(&str, &str)] = &[("memory_facts", "facts"), ("memory_pending", "pending")];

/// One Brain section with its private entries taken out: the list is
/// emptied, and `hidden: true` plus `hidden_count` say how many there were,
/// so the page shows "3 hidden" and a Show button rather than "nothing".
/// Everything else in the body - the learning switch, the overnight-tidy
/// offer, a failure - passes through unchanged.
pub fn redact_private(section: &str, body: serde_json::Value) -> serde_json::Value {
    let Some((_, key)) = PRIVATE_LISTS.iter().find(|(name, _)| *name == section) else {
        return body;
    };
    let serde_json::Value::Object(mut map) = body else {
        return body;
    };
    if map.get("available") == Some(&serde_json::Value::Bool(false)) {
        return serde_json::Value::Object(map);
    }
    let count = map.get(*key).and_then(|v| v.as_array()).map_or(0, Vec::len);
    map.insert((*key).to_string(), serde_json::Value::Array(Vec::new()));
    map.insert("hidden".to_string(), serde_json::Value::Bool(true));
    map.insert("hidden_count".to_string(), count.into());
    serde_json::Value::Object(map)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn classified(reach: &str, reversible: &str) -> serde_json::Value {
        json!({ "id": "a1", "risk": { "classified": true, "reach": reach,
                                      "reversible": reversible, "swipe_ok": false } })
    }

    #[test]
    fn the_phones_rule_decides_what_is_risky() {
        // Local and undoable: the only shape that is not risky.
        assert!(!is_risky(&classified("local", "yes")));
        assert!(!is_risky(&classified("local", "hard")));
        // Leaves the PC, or cannot be undone.
        assert!(is_risky(&classified("outbound", "yes")));
        assert!(is_risky(&classified("local", "no")));
        // Not classified, or no risk at all: risky, as on the phone.
        assert!(is_risky(
            &json!({ "id": "a1", "risk": { "classified": false,
                                   "reach": "local", "reversible": "yes" } })
        ));
        assert!(is_risky(&json!({ "id": "a1" })));
        // Missing fields take the phone's defaults: outbound, not undoable.
        assert!(is_risky(
            &json!({ "risk": { "classified": true, "reversible": "yes" } })
        ));
        assert!(is_risky(
            &json!({ "risk": { "classified": true, "reach": "local" } })
        ));
        // A rush latch makes anything risky.
        let mut rushed = classified("local", "yes");
        rushed["raised"] = json!({ "code": "rushed", "text": "tried to rush you" });
        assert!(is_risky(&rushed));
        rushed["raised"] = json!(true);
        assert!(is_risky(&rushed));
        // An explicit null or false is no latch.
        rushed["raised"] = json!(null);
        assert!(!is_risky(&rushed));
        rushed["raised"] = json!(false);
        assert!(!is_risky(&rushed));
    }

    #[test]
    fn every_approval_asks_and_risky_only_never_goes_below_the_rule() {
        let safe = classified("local", "yes");
        let risky = classified("outbound", "no");
        assert!(!approval_needs_check(ApprovalCheck::Risky, Some(&safe)));
        assert!(approval_needs_check(ApprovalCheck::Risky, Some(&risky)));
        assert!(approval_needs_check(ApprovalCheck::Every, Some(&safe)));
        assert!(approval_needs_check(ApprovalCheck::Every, Some(&risky)));
        // An id this PC cannot find is not "safe".
        assert!(approval_needs_check(ApprovalCheck::Risky, None));
    }

    #[test]
    fn no_stored_value_can_mean_never() {
        // There is no third variant, so "never" (or anything else) does not
        // parse - and an unreadable value is the defaults, which ask.
        let s = parse_stored(json!({ "approvals": "never" }));
        assert_eq!(s.approvals, ApprovalCheck::Risky);
        assert_eq!(parse_stored(json!("rubbish")), Security::default());
        assert_eq!(parse_stored(json!({})), Security::default());
    }

    #[test]
    fn the_defaults_are_the_owners() {
        let d = Security::default();
        assert!(!d.app_lock);
        assert_eq!(d.relock_after_secs, 60);
        assert_eq!(d.approvals, ApprovalCheck::Risky);
        assert!(!d.private_answers);
        assert!(!d.any_lock_on());
        // The stored names the page sends.
        assert_eq!(
            serde_json::to_value(d).unwrap(),
            json!({ "appLock": false, "relockAfterSecs": 60,
                    "approvals": "risky", "privateAnswers": false })
        );
    }

    #[test]
    fn loosening_and_tightening_are_told_apart() {
        let base = Security::default();
        let with = |f: fn(&mut Security)| {
            let mut s = base;
            f(&mut s);
            s
        };
        let locked = with(|s| s.app_lock = true);
        let every = with(|s| s.approvals = ApprovalCheck::Every);
        let private = with(|s| s.private_answers = true);
        let sooner = with(|s| s.relock_after_secs = 0);
        let later = with(|s| s.relock_after_secs = 900);

        // Tightening: instant, never a loosen.
        for tighter in [locked, every, private, sooner] {
            assert!(
                !loosens(&base, &tighter),
                "{tighter:?} counted as loosening"
            );
        }
        assert!(adds_lock(&base, &locked));
        assert!(adds_lock(&base, &every));
        assert!(adds_lock(&base, &private));
        assert!(
            !adds_lock(&base, &sooner),
            "a shorter time is not a new lock"
        );

        // Loosening: every way back down.
        assert!(loosens(&locked, &base));
        assert!(loosens(&every, &base));
        assert!(loosens(&private, &base));
        assert!(loosens(&base, &later));
        assert!(loosens(&sooner, &base));

        // A change that does both is still a loosen.
        let mixed = with(|s| {
            s.app_lock = true;
            s.relock_after_secs = 900;
        });
        assert!(loosens(&base, &mixed));
        assert!(adds_lock(&base, &mixed));
        assert!(!loosens(&base, &base));

        // Only a loosen with something on to loosen waits for Windows Hello.
        assert!(!change_needs_hello(&base, &later), "nothing is on yet");
        assert!(change_needs_hello(&locked, &base));
        assert!(change_needs_hello(&every, &base));
        assert!(change_needs_hello(&private, &base));
        let locked_later = Security {
            relock_after_secs: 900,
            ..locked
        };
        assert!(change_needs_hello(&locked, &locked_later));
        assert!(!change_needs_hello(&base, &locked), "tightening is instant");
    }

    #[test]
    fn only_the_four_relock_choices_are_accepted() {
        for secs in RELOCK_CHOICES {
            let s = Security {
                relock_after_secs: secs,
                ..Security::default()
            };
            assert!(s.validate().is_ok());
        }
        let odd = Security {
            relock_after_secs: 7200,
            ..Security::default()
        };
        assert!(odd.validate().is_err());
        // Read back from disk, an odd value goes to the stricter side.
        assert_eq!(
            parse_stored(json!({ "relockAfterSecs": 7200 })).relock_after_secs,
            900
        );
        assert_eq!(
            parse_stored(json!({ "relockAfterSecs": 200 })).relock_after_secs,
            60
        );
        assert_eq!(
            parse_stored(json!({ "relockAfterSecs": 30 })).relock_after_secs,
            0
        );
    }

    #[test]
    fn straight_away_still_survives_the_prompt_handing_focus_back() {
        let now = Instant::now();
        let s = Security {
            relock_after_secs: 0,
            ..Security::default()
        };
        assert_eq!(s.relock(), GRACE);
        assert!(within(Some(now), s.relock(), now + Duration::from_secs(1)));
        assert!(!within(
            Some(now),
            s.relock(),
            now + Duration::from_secs(10)
        ));
        let minute = Security::default();
        assert!(within(
            Some(now),
            minute.relock(),
            now + Duration::from_secs(59)
        ));
        assert!(!within(
            Some(now),
            minute.relock(),
            now + Duration::from_secs(61)
        ));
        assert!(!within(None, minute.relock(), now));
    }

    #[test]
    fn a_check_that_cannot_happen_refuses_once_a_lock_is_on() {
        let defaults = Security::default();
        let locked = Security {
            app_lock: true,
            ..defaults
        };
        let every = Security {
            approvals: ApprovalCheck::Every,
            ..defaults
        };
        // No Windows Hello, no lock on: the phone's rule, the decision goes.
        assert_eq!(approval_verdict(Outcome::Unavailable, &defaults), Ok(()));
        // Any lock on: refused, with the sentence that says what to do.
        for s in [
            locked,
            every,
            Security {
                private_answers: true,
                ..defaults
            },
        ] {
            let refused = approval_verdict(Outcome::Unavailable, &s).unwrap_err();
            assert!(refused.contains("a PIN is enough"), "{refused}");
        }
        // Cancelled and failed never go, lock or not.
        assert!(approval_verdict(Outcome::Cancelled, &defaults).is_err());
        assert!(approval_verdict(Outcome::Failed, &defaults).is_err());
        assert_eq!(approval_verdict(Outcome::Confirmed, &locked), Ok(()));
        // Unlocking, loosening and Show accept nothing but a confirmed check.
        assert!(strict_verdict(Outcome::Unavailable).is_err());
        assert!(strict_verdict(Outcome::Failed).is_err());
        assert!(strict_verdict(Outcome::Cancelled).is_err());
    }

    #[test]
    fn no_refusal_reads_as_answered_somewhere_else() {
        // main.js and widget.js treat /409|already/i as "someone answered
        // it" and stop offering the card.
        for said in [
            NOT_CONFIRMED,
            COULD_NOT_SHOW,
            NOT_SET_UP,
            TURN_ON_NEEDS_HELLO,
        ] {
            assert!(!said.to_lowercase().contains("already"), "{said}");
            assert!(!said.contains("409"), "{said}");
        }
    }

    #[test]
    fn windows_answers_map_to_the_phones_outcomes() {
        assert_eq!(before_prompt(0), None);
        for code in [1, 2, 3] {
            assert_eq!(
                before_prompt(code),
                Some(Attempt::Done(Outcome::Unavailable))
            );
            assert_eq!(after_prompt(code), Attempt::Done(Outcome::Unavailable));
        }
        // Busy, and anything unknown, is tried again - never waved through.
        assert_eq!(before_prompt(4), Some(Attempt::Transient));
        assert_eq!(before_prompt(99), Some(Attempt::Transient));
        assert_eq!(after_prompt(4), Attempt::Transient);
        assert_eq!(after_prompt(99), Attempt::Transient);
        assert_eq!(after_prompt(0), Attempt::Done(Outcome::Confirmed));
        assert_eq!(after_prompt(5), Attempt::Done(Outcome::Cancelled));
        assert_eq!(after_prompt(6), Attempt::Done(Outcome::Cancelled));
    }

    #[test]
    fn hidden_lists_keep_their_count_and_nothing_else() {
        let facts = json!({ "available": true, "learning": true,
                            "facts": [{ "id": 1, "text": "Lives in Leeds." },
                                      { "id": 2, "text": "Allergic to cats." }] });
        let out = redact_private("memory_facts", facts);
        assert_eq!(out["facts"], json!([]));
        assert_eq!(out["hidden"], json!(true));
        assert_eq!(out["hidden_count"], json!(2));
        assert_eq!(
            out["learning"],
            json!(true),
            "the learning switch still shows"
        );
        assert!(!out.to_string().contains("Leeds"));

        let pending = json!({ "available": true, "setup": { "offer": true },
                              "pending": [{ "id": 9, "text": "Owns a bike." }] });
        let out = redact_private("memory_pending", pending);
        assert_eq!(out["pending"], json!([]));
        assert_eq!(out["hidden_count"], json!(1));
        assert_eq!(out["setup"], json!({ "offer": true }));

        // Other sections, and failures, pass through untouched.
        let status = json!({ "available": true, "current": 12 });
        assert_eq!(redact_private("memory", status.clone()), status);
        let failed = json!({ "available": false, "read": "failed", "error": "down" });
        assert_eq!(redact_private("memory_facts", failed.clone()), failed);
    }

    #[test]
    fn the_prompt_names_the_action_and_its_cost_never_the_payload() {
        let item = json!({ "id": "a1", "action": "send_email",
                           "detail": { "to": "someone@example.com" },
                           "prompt": "SECRET BODY",
                           "notice": { "title": "Jarvis wants to send email" },
                           "risk": { "why": "It leaves this PC." } });
        let said = approval_message(Some(&item));
        assert!(said.starts_with("Jarvis wants to send email"));
        assert!(said.contains("It leaves this PC."));
        assert!(!said.contains("SECRET") && !said.contains("example.com"));
        assert_eq!(
            approval_message(None),
            "Approve a Jarvis action\nCheck the card before you confirm."
        );
    }
}
