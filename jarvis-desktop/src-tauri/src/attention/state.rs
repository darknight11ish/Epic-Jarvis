//! The interruption budget as data, and the one rule that composes a face
//! state out of it.
//!
//! Split from the commands next door so it can be compiled and tested without
//! a Tauri app, a window or a network — this is the half where being wrong is
//! silent, so it is the half that has to be exercised.

use serde::{Deserialize, Serialize};

/// What the desktop knows about the interruption budget.
///
/// Every count is `u32` and `known` guards the lot: before the first read
/// nothing here is a fact, and a zero that means "not asked yet" would draw an
/// empty digest and a cleared badge over a queue nobody has looked at.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Attention {
    /// False until `/api/attention` or an `attention` event has been read.
    /// A surface shows "unknown", not "nothing waiting", while this is false.
    pub known: bool,
    /// Spoken interruptions allowed per day.
    pub limit: u32,
    /// Spoken interruptions left today. Zero whenever `blocked_by` is set,
    /// whatever the count.
    pub remaining: u32,
    /// Spent today. Not on the bus — only from `/api/attention`.
    pub spent: u32,
    /// Muted until tomorrow. Not on the bus; `blocked_by` reflects it, but the
    /// UI needs to know whether to offer Mute or Unmute.
    pub muted: bool,
    /// Why the budget is zero regardless of the count — Quiet, Standby, a
    /// locked session, or muted. `None` when there is budget left.
    pub blocked_by: Option<String>,
    /// Items waiting in the digest. This is the tray badge and the notch count
    /// on the reactor's rim ring — it is NOT the approval queue, which is
    /// `LinkState::approvals` and counts things awaiting a decision.
    pub pending: u32,
    /// The server's own answer to "is Jarvis sitting on things silently".
    /// Read, never derived.
    pub banked: bool,
    /// Local hour the daily brief is due at.
    pub digest_hour: u32,
    /// Whether it is due now.
    pub digest_due: bool,
}

impl Default for Attention {
    fn default() -> Self {
        Self {
            known: false,
            limit: 0,
            remaining: 0,
            spent: 0,
            muted: false,
            blocked_by: None,
            pending: 0,
            banked: false,
            digest_hour: 18,
            digest_due: false,
        }
    }
}

impl Attention {
    /// Applies an `attention` event — the five fields §4 documents, and only
    /// those. `spent`, `muted`, `digest_hour` and `digest_due` are left alone
    /// because the bus does not carry them; a full read refreshes those.
    pub fn apply_event(&mut self, data: &serde_json::Value) {
        self.known = true;
        if let Some(v) = data["limit"].as_u64() {
            self.limit = v as u32;
        }
        if let Some(v) = data["remaining"].as_u64() {
            self.remaining = v as u32;
        }
        if let Some(v) = data["pending"].as_u64() {
            self.pending = v as u32;
        }
        if let Some(v) = data["banked"].as_bool() {
            self.banked = v;
        }
        // `blocked_by` is `null` when there is budget left, and null is
        // meaningful — it clears a block. So this is not guarded by `is_some`
        // the way the counts above are.
        self.blocked_by = data["blocked_by"].as_str().map(str::to_string);
    }

    /// Applies a full `GET /api/attention` body — `jarvis_arbiter.status()`,
    /// which nests the budget one level down.
    pub fn apply_status(&mut self, body: &serde_json::Value) {
        let budget = &body["budget"];
        self.known = true;
        self.limit = budget["limit"].as_u64().unwrap_or(0) as u32;
        self.remaining = budget["remaining"].as_u64().unwrap_or(0) as u32;
        self.spent = budget["spent"].as_u64().unwrap_or(0) as u32;
        self.muted = budget["muted"].as_bool().unwrap_or(false);
        self.blocked_by = budget["blocked_by"].as_str().map(str::to_string);
        self.pending = body["pending"].as_u64().unwrap_or(0) as u32;
        self.banked = body["banked"].as_bool().unwrap_or(false);
        self.digest_hour = body["digest_hour"].as_u64().unwrap_or(18) as u32;
        self.digest_due = body["digest_due"].as_bool().unwrap_or(false);
    }
}

/// What the reactor should show, given what Jarvis is doing and whether the
/// day's interruptions are banked.
///
/// This is a line-for-line copy of `jarvis_arbiter.face_state`:
///
/// ```python
/// if activity in ("idle",) and banked(now):
///     return "banked"
/// return activity
/// ```
///
/// **JARVIS-API §5 says this resolution happens server-side and warns that "a
/// client that re-derives it will disagree with the server the first time the
/// two drift". That is a doc bug: nothing serves the result.** `face_state` is
/// called by no route, no bus publisher and no other module in the backend —
/// only by its own unit test. `/api/attention` returns `banked`, the `attention`
/// event returns `banked`, and the activity arrives separately on the
/// `activity` event and in `GET /api/version`. There is no wire format that
/// carries the composed answer, so every client has to compose it.
///
/// What the warning is really about is the *ingredients*, and that part is
/// honoured strictly: `banked` is the server's boolean, taken as given, never
/// recomputed from `remaining` and `pending`. The composition lives here alone
/// — one function, one caller vocabulary — so if the server ever does publish a
/// resolved state, this is the only thing to delete.
pub fn face_state(activity: &str, banked: bool) -> &'static str {
    // `banked` replaces a RESTING face only. If Jarvis is mid-sentence to
    // somebody who asked it something, that is foreground and keeps its own
    // state: the budget governs what Jarvis starts, never what it is in the
    // middle of.
    if activity == "idle" && banked {
        return "banked";
    }
    match activity {
        "listening" => "listening",
        "thinking" => "thinking",
        "speaking" => "speaking",
        "error" => "error",
        // `working` has no binding in the spec — the nearest bound state is
        // `thinking`: busy, and not talking.
        "working" => "thinking",
        _ => "idle",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The composition rule, against `jarvis_arbiter.face_state`'s own test
    /// (`test_arbiter.py`): idle goes to banked, every busy state keeps itself.
    #[test]
    fn banked_replaces_only_a_resting_face() {
        assert_eq!(face_state("idle", true), "banked");
        for busy in ["listening", "thinking", "speaking", "error"] {
            assert_eq!(
                face_state(busy, true),
                busy,
                "{busy} is foreground and must keep its own state while banked"
            );
        }
        // `working` has no binding of its own either way.
        assert_eq!(face_state("working", true), "thinking");
        assert_eq!(face_state("idle", false), "idle");
    }

    /// Every state this can return has to exist in the spec, or the tray
    /// resolves against nothing and falls back to idle's colour in silence.
    #[test]
    fn every_composed_state_is_bound() {
        for activity in [
            "idle",
            "listening",
            "thinking",
            "speaking",
            "working",
            "error",
            "something-the-server-added-later",
        ] {
            for banked in [false, true] {
                let id = face_state(activity, banked);
                assert!(
                    crate::spec::has_state(id),
                    "`{activity}` (banked={banked}) resolved to `{id}`, which the spec does not bind"
                );
            }
        }
    }

    /// An `attention` event carries five fields. Applying one must not clobber
    /// the four that only a full read can fill, or every event would wipe
    /// `muted` and the panel would offer Mute to somebody already muted.
    #[test]
    fn an_event_leaves_the_fields_it_does_not_carry() {
        let mut a = Attention::default();
        a.apply_status(&serde_json::json!({
            "budget": {"limit": 6, "remaining": 0, "spent": 6, "muted": true,
                       "blocked_by": "muted until tomorrow"},
            "pending": 3, "banked": true, "digest_hour": 18, "digest_due": true
        }));
        assert!(a.muted && a.spent == 6 && a.digest_due);

        a.apply_event(&serde_json::json!({
            "remaining": 0, "limit": 6, "blocked_by": "muted until tomorrow",
            "pending": 4, "banked": true
        }));
        assert_eq!(a.pending, 4, "the event's own field should land");
        assert!(a.muted, "the event does not carry `muted`; it must survive");
        assert_eq!(a.spent, 6, "the event does not carry `spent` either");
        assert!(a.digest_due);
    }

    /// `blocked_by: null` is the server clearing a block, not a missing field.
    #[test]
    fn a_null_block_reason_clears_the_block() {
        let mut a = Attention::default();
        a.apply_event(&serde_json::json!({"blocked_by": "standby", "pending": 1}));
        assert_eq!(a.blocked_by.as_deref(), Some("standby"));
        a.apply_event(&serde_json::json!({"blocked_by": null, "remaining": 5}));
        assert_eq!(a.blocked_by, None);
    }

    /// Nothing has been read yet, so nothing is known — a zero here would draw
    /// an empty digest over a queue that was never fetched.
    #[test]
    fn nothing_is_known_before_the_first_read() {
        let a = Attention::default();
        assert!(!a.known && !a.banked && a.pending == 0);
    }
}
