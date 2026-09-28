//! Talk-to-type's rules and words, with no Tauri and no Windows calls in
//! them, so their tests build anywhere.

use std::time::Duration;

use serde_json::Value;

use crate::voice::HeardReply;

/// A press shorter than this is a TAP: listening carries on after the key
/// is let go, until the key is pressed again. Longer is a HOLD: letting go
/// ends it.
pub(crate) const TAP: Duration = Duration::from_millis(350);

/// The longest talk-to-type listens, held or tapped - the same two minutes
/// as the Jarvis bar's talk button (a longer clip would pass the server's
/// size limit). Listening stops by itself here, and what was said is typed.
pub(crate) const MAX_LISTEN: Duration = Duration::from_secs(120);

/// How long "the PC said it is on" is trusted before asking again. The PC
/// refuses a clip itself while the switch is off, so this only saves a
/// question per press; turning it off in Settings forgets it at once.
pub(crate) const SWITCH_TRUSTED_FOR: Duration = Duration::from_secs(60);

/// How long to wait for Ctrl, Alt, Shift and Win to be let go before
/// pressing Ctrl+V.
pub(crate) const KEYS_UP_WAIT: Duration = Duration::from_secs(2);

pub(crate) fn is_tap(held: Duration) -> bool {
    held < TAP
}

/// What `GET /api/voice/status` says about the switch (`gate.talk_to_type`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Switch {
    On,
    Off,
    /// An older PC, which has no talk-to-type at all.
    NotOnThisPc,
}

pub(crate) fn switch_from_status(status: &Value) -> Switch {
    match status.pointer("/gate/talk_to_type").and_then(Value::as_str) {
        Some("on") => Switch::On,
        Some("off") => Switch::Off,
        _ => Switch::NotOnThisPc,
    }
}

// ---------------------------------------------------------------------------
// The words the owner sees (a notification each; never the words spoken)
// ---------------------------------------------------------------------------

pub(crate) const TITLE: &str = "Talk-to-type";
pub(crate) const OFF: &str =
    "Talk-to-type is off. Turn it on in Settings, Voice - it shows you an approval card first.";
pub(crate) const NOT_ON_THIS_PC: &str =
    "Jarvis on this PC does not have talk-to-type yet. Update the backend by running \
     apply-patches.ps1, then try again.";
pub(crate) const STALE: &str =
    "The connection to Jarvis is catching up, so nothing was typed. Try again in a moment.";
pub(crate) const LOCKED: &str = "Jarvis is locked, so it did not listen. Open the Jarvis bar \
     and unlock it with Windows Hello, then try again.";
pub(crate) const NOT_THIS_PC: &str = "Talk-to-type works only when Jarvis runs on this PC, so \
     your voice never leaves it. Settings, Connection points Jarvis somewhere else.";
pub(crate) const MIC_WAKE: &str = "Jarvis is listening for \"hey Jarvis\", and both cannot use \
     the microphone at once. Turn listening off in the Jarvis bar, then try again.";
pub(crate) const MIC_TALK: &str =
    "The Jarvis bar's talk button is using the microphone. Let go of it first.";
pub(crate) const NOT_YOU: &str = "That did not sound like you, so nothing was typed.";
pub(crate) const NOTHING_HEARD: &str = "Nothing was heard, so nothing was typed.";
pub(crate) const NO_WORDS: &str =
    "Jarvis on this PC could not turn that into words, so nothing was typed.";
pub(crate) const TOO_LONG: &str =
    "That was over two minutes, so nothing was typed. Say a long piece in parts.";
pub(crate) const MOVED: &str = "You moved to another window while Jarvis was listening, so \
     nothing was typed. Try again in the window you want.";
pub(crate) const NO_TARGET: &str = "No program was in front to type into, so nothing was typed.";
pub(crate) const PASSWORD: &str =
    "That box is for a password, so Jarvis did not type into it. Type passwords yourself.";
pub(crate) const KEYS_HELD: &str =
    "Keys were still held down, so nothing was typed. Let go of every key, then try again.";
pub(crate) const NOT_TAKEN: &str = "The program in front did not take the words. If it runs as \
     administrator, Jarvis cannot type into it.";
pub(crate) const KEYS_REFUSED: &str =
    "Windows would not let Jarvis press Ctrl+V, so nothing was typed.";
#[cfg(not(windows))]
pub(crate) const NEEDS_WINDOWS: &str = "Talk-to-type needs Windows.";
pub(crate) const MIC_SLOW: &str = "The microphone was still starting when you let go, so \
     nothing was typed. Hold the key a moment longer.";
/// The tray icon's first line while listening.
pub(crate) const TRAY_LISTENING: &str = "Jarvis — listening to type what you say";

/// A reason from the PC as a sentence: a capital first, a full stop last.
pub(crate) fn sentence(reason: &str) -> String {
    let t = reason.trim();
    let mut chars = t.chars();
    let Some(first) = chars.next() else {
        return String::new();
    };
    let mut out: String = first.to_uppercase().chain(chars).collect();
    if !out.ends_with(['.', '!', '?']) {
        out.push('.');
    }
    out
}

/// What to type, or - in words - why nothing is typed. The PC has already
/// checked the voice before any words existed; this only reads its answer.
pub(crate) fn words_to_type(reply: &HeardReply) -> Result<String, String> {
    if !reply.available {
        let why = sentence(&reply.reason);
        return Err(if why.is_empty() {
            NO_WORDS.to_string()
        } else {
            format!("{why} Nothing was typed.")
        });
    }
    if reply.too_short {
        let why = sentence(&reply.reason);
        return Err(if why.is_empty() {
            NOTHING_HEARD.to_string()
        } else {
            format!("{why} Nothing was typed.")
        });
    }
    if !reply.is_owner {
        return Err(if reply.reason.contains("no speech") {
            NOTHING_HEARD.to_string()
        } else {
            NOT_YOU.to_string()
        });
    }
    let text = reply.text.trim();
    if text.is_empty() {
        return Err(NOTHING_HEARD.to_string());
    }
    Ok(text.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn reply(is_owner: bool, text: &str) -> HeardReply {
        let mut r = HeardReply::unavailable(String::new());
        r.available = true;
        r.is_owner = is_owner;
        r.text = text.to_string();
        r.source = "talk_to_type".to_string();
        r
    }

    #[test]
    fn a_short_press_is_a_tap_and_a_long_one_a_hold() {
        assert!(is_tap(Duration::from_millis(120)));
        assert!(!is_tap(Duration::from_millis(900)));
        assert!(!is_tap(TAP));
    }

    #[test]
    fn the_switch_is_read_from_the_gate() {
        assert_eq!(
            switch_from_status(&json!({"gate": {"talk_to_type": "on"}})),
            Switch::On
        );
        assert_eq!(
            switch_from_status(&json!({"gate": {"talk_to_type": "off"}})),
            Switch::Off
        );
        // An older PC: no key, or "" from a voice module older than it.
        assert_eq!(
            switch_from_status(&json!({"gate": {}})),
            Switch::NotOnThisPc
        );
        assert_eq!(
            switch_from_status(&json!({"gate": {"talk_to_type": ""}})),
            Switch::NotOnThisPc
        );
        assert_eq!(switch_from_status(&json!({})), Switch::NotOnThisPc);
    }

    #[test]
    fn only_the_owners_words_are_typed() {
        assert_eq!(
            words_to_type(&reply(true, "  Send it tomorrow ")).unwrap(),
            "Send it tomorrow"
        );
        assert_eq!(words_to_type(&reply(false, "")).unwrap_err(), NOT_YOU);
        assert_eq!(
            words_to_type(&reply(true, "  ")).unwrap_err(),
            NOTHING_HEARD
        );
        let mut quiet = reply(false, "");
        quiet.reason = "no speech in that recording".to_string();
        assert_eq!(words_to_type(&quiet).unwrap_err(), NOTHING_HEARD);
    }

    #[test]
    fn the_pcs_own_reason_is_passed_on_as_a_sentence() {
        let mut off = reply(false, "");
        off.available = false;
        off.reason = "talk-to-type is switched off on this PC".to_string();
        assert_eq!(
            words_to_type(&off).unwrap_err(),
            "Talk-to-type is switched off on this PC. Nothing was typed."
        );
        let mut short = reply(false, "");
        short.too_short = true;
        short.reason = "that was too short to be sure it was you - say a little more".to_string();
        assert!(words_to_type(&short)
            .unwrap_err()
            .starts_with("That was too short"));
        let mut blank = reply(false, "");
        blank.available = false;
        assert_eq!(words_to_type(&blank).unwrap_err(), NO_WORDS);
    }

    #[test]
    fn sentences_are_tidy() {
        assert_eq!(sentence("hello"), "Hello.");
        assert_eq!(sentence("Done!"), "Done!");
        assert_eq!(sentence("   "), "");
    }
}
