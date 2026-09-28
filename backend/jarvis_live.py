"""jarvis_live.py - Jarvis Live: a back-and-forth voice conversation the owner
starts and stops, with no "hey Jarvis" between turns.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
live.patch installs its one route, /api/voice/live, the way chatbot-routes
installs its own). docs/LIVE-DESIGN.md build steps 1 and 2 (the session, the
`live` clip source, the route, the words) and step 8 (the camera's readiness,
switched off). The desktop's and the phone's halves are steps 3 and 4.

THE OWNER'S DECISION (2026-09-28, CLAUDE.md "Jarvis Live"): "a back-and-forth
voice conversation the owner starts and stops, with no wake word between turns
and interrupting at any time, plus showing Jarvis the phone's camera. The
voice check still runs on every clip, cards are still decided by tapping
(never by voice), and everything stays on the owner's own devices. Not
full-duplex." And the owner's answers (2026-09-28):
  1. under "Only trust the talk button", a Live turn is trusted like the talk
     button by default HOWEVER Live was started; the voice setting
     `hands_free_live` (jarvis_voice.py) has two stricter choices - "Only
     when I start it with the button" and "Be as careful as with Hey Jarvis"
     (trust_source below says how a session started);
  2. answers about what the camera sees are read aloud like screen answers
     (CAMERA_TOOL below is on the apps' read-aloud list, and is governed by
     the same `screen_aloud` as the screen);
  3. the camera stays OFF until the 12 GB card is in and a photo test passes
     (camera_status() below: false until a passing result for the Pictures
     lane's model is on file - no words-only camera on one card);
  4. Live keeps the 2-second voice check - no "Balanced" for Live; the tap
     buttons cover quick answers;
  5. side talk is ignored: a Live clip clearly said to someone else gets no
     answer spoken, and nothing is learned or counted from it (MODEL_NOTE,
     SIDE_TALK_MARK, note_side_talk);
  6. Live pauses itself during a phone or video call and carries on after
     (mute with why "call" / "mic_in_use", reported by the apps).

IN PLAIN WORDS, WHAT HAPPENS
  * The owner presses Live (or says "Hey Jarvis, let's talk"). No card: it is
    the owner's own act, like the talk button or "Watch with me". ONE session
    at a time, on ONE device ("phone" or "desktop"): starting on one ends the
    other's. Pressing Live warms the everyday model so the first answer is not
    slow - but never on Standby: then Jarvis says "Waking up, a few seconds."
    and the first question wakes it, as any question would.
  * While it is on, that device sends every sentence it hears as a clip with
    `source=live`. jarvis_speech.hear() takes such a clip exactly as it takes
    any other - speech found first, long enough, THE OWNER CHECK, and only
    then speech-to-text - with one difference: no "hey Jarvis" is needed. A
    `live` clip from a device with no session on is refused before anything
    looks at it, never checked, never transcribed.
  * MUTE: the microphone closes (nothing captured, nothing sent), the session
    and its time limit carry on, the sign says "Muted", Unmute listens again.
    A phone or video call does the same by itself ("Paused: you're on a
    call") and carries on after. While muted the quiet clock stands still:
    it exists so an OPEN microphone is not forgotten, and a muted one is
    closed.
  * It pauses (nothing heard, nothing sent) while an approval card RAISED
    SINCE LIVE STARTED waits - "Waiting for your tap on the card" - so a
    spoken "yes" is not even heard; cards are decided by tapping only. A card
    that was already waiting before Live started does not pause it. If the
    queue cannot be read, Live pauses too ("Paused: can't check for cards") -
    fail closed. Memory's review list ("remember this?") does not pause it:
    those rows wait in Brain as long as the owner likes, nothing Jarvis is
    doing waits on them, and nothing can answer them by voice.
  * OTHER VOICES: after 3 clips in a row that were not the owner's voice the
    sign says "Hearing other voices - only yours counts"; after 10, or two
    minutes of nothing but refusals, Live pauses - and keeps CHECKING (never
    transcribing) so the owner's own voice carries on without a tap. When
    most of those refusals were near misses, it is probably the owner's own
    voice failing, and the sign says "I'm having trouble recognising your
    voice - move closer or retrain" instead.
  * It ENDS when the owner presses End / Stop, says "that's all for now" (the
    owner check first, like any command), on Stop everything, after 90
    seconds of quiet since Jarvis last spoke (QUIET_S; a warning shows 15
    seconds before), at the time limit (30 minutes; "give me twenty more
    minutes" extends it, never more than 2 hours ahead of now), on Standby,
    when Windows locks or the PC sleeps (a desktop session), or when App lock
    comes on (reported by the app). It never restarts by itself.

THE RULES ADDED BY THE RULES REVIEW (2026-09-28, before anything shipped):
  * NO LIVE WITHOUT A REAL VOICE CHECK: owner mode, a trained voice print for
    that microphone and the voice-ID model installed (voice_ready) - else
    "Jarvis Live didn't start: it needs your voice trained first - " and
    where that app trains it (needs_voice_words).
  * A CRISIS TURN (note_crisis, from jarvis_agent.note_crisis_turn) turns the
    quiet timeout and the "minutes left" warning off for the rest of the
    session, and Live does not end at its time limit until at least
    CRISIS_MORE_S (30 minutes) after the last crisis turn (the owner's
    answer of 2026-09-28). Live's own numbers (turns, refusals) feed no
    other counter. (Ordinary Live turns DO feed "suggest the bigger model",
    like any turn; crisis and side-talk turns do not.)
  * "WATCH WITH ME" + LIVE: a screen picture may go with a Live question
    asked AT THE PC only (screen_picture_allowed).
  * Quiet and a focus session do not end Live - it is a conversation the
    owner started - and each keeps its own rules. Standby does.

WHAT THE APPS SEE is status(): on/off, which device, the time left, a pause,
a hint and an end reason from FIXED lists of plain words, and counts. Never a
word anyone said, never a sound. The `live` event carries status() and
nothing else; the audit log carries counts and fixed words.

NOTHING IS KEPT HERE beyond numbers - and, for side talk, a one-way hash of
the owner's words for a day, so the learner can skip them (never the words).
The clips are jarvis_speech's (in memory, checked, dropped); the words become
an ordinary spoken chat turn, kept in chat history like any chat.

WHAT IT CANNOT DO, SAID PLAINLY
  * A very short reply - "yes", "no", even a bare "bye" - is refused as too
    short to check (jarvis_voice.MIN_COMMAND_SECONDS: 2 seconds OUT OF THE
    BOX, because Very strict is the default, and the owner chose to keep it
    for Live; 1.5 seconds at Balanced - measured with 0.3 s of quiet either
    side, so about 1.4 or 0.9 seconds of words). A short clip is checked
    (never turned into words) only to decide whether it was probably the
    owner - then Jarvis asks for a bit more, at most once a minute, and the
    sign says "Didn't catch that - say a bit more" - or someone else (counted
    as another voice, nothing said). Both apps offer tap buttons ("Yes",
    "No") after a spoken question instead, sent as the owner's typed words.
  * The voice check cannot tell a recording of the owner from the owner. The
    `hands_free_live` setting gives Live the "Hey Jarvis" caution for that.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Knobs (docs/LIVE-DESIGN.md section 2 and 3)
# --------------------------------------------------------------------------

#: The devices a session can be on - jarvis_speech's `mic` names.
DEVICES = ("phone", "desktop")
#: How long, by default and at most ahead of now, in minutes (the same
#: numbers as "Watch with me", jarvis_screen.py). It can be extended, but
#: never to more than MAX_MINUTES from now.
DEFAULT_MINUTES = 30
MIN_MINUTES = 1
MAX_MINUTES = 120
#: "give me twenty more minutes" / "more time" with no number.
EXTEND_DEFAULT_MIN = 20
#: The warning before the end, in seconds.
WARN_BEFORE_S = 120
#: Quiet this long after Jarvis last spoke (or the owner last spoke, or Live
#: started) ends Live (the design: long enough to think, short enough that an
#: open microphone is not forgotten). Kept at 90 s (owner's call pending).
QUIET_S = 90
#: The visible "Live ends soon - it's quiet" this long before that.
QUIET_WARN_S = 15
#: After Live ended on its own, both apps offer "Resume Live" this long; it
#: carries on the SAME chat (the apps keep the conversation).
RESUME_S = 600
#: Clips in a row that were not the owner's voice before the sign says so...
HINT_AFTER = 3
#: ...and before Live pauses.
PAUSE_AFTER = 10
#: Or: nothing but refusals for this long.
PAUSE_AFTER_S = 120
#: A refusal this close to the voice check's bar (as a share of it) is a
#: near miss: probably the owner, recognised badly (a far microphone, a cold).
NEAR_MISS = 0.85
#: "Say a bit more, so I can tell it's you." - not more often than this.
SHORT_LINE_EVERY_S = 60
#: The session's own check.
TICK_S = 1.0
#: A gap this long between two checks means the PC slept: the session ends.
SLEEP_GAP_S = 30.0
#: A card raised this long before Live started still counts as new (clocks).
CARD_SLACK_S = 2.0
#: After a crisis turn (the owner's answer of 2026-09-28): Live does not end
#: at its time limit until at least this long after the LAST crisis turn, and
#: says no "minutes left" warning for the rest of that session. The quiet end
#: is off for the rest of the session too. The owner can still end it at any
#: time (End Live, "that's all", Stop everything), and App lock, Windows'
#: lock, the PC sleeping and Standby still end it.
CRISIS_MORE_S = 30 * 60
#: How long the apps show "Jarvis Live ended" (and why) after an end that
#: cannot be resumed. A resumable end shows "Resume Live" for RESUME_S.
ENDED_SHOW_S = 15
#: How long a side-talk sentence's hash is kept for the learner to skip.
SIDE_TALK_KEEP_S = 24 * 3600
SIDE_TALK_MAX = 500

#: The name a Live camera turn records as read, like a reading tool's (the
#: owner's answer of 2026-09-28: camera answers are read aloud like screen
#: answers, jarvis_screen.SCREEN_TOOL). On the apps' read-aloud list
#: (tools/gen_private_aloud_cases.py) and in jarvis_agent.STEP_READS. The
#: camera is switched off (camera_status), so nothing records it yet.
CAMERA_TOOL = "read_camera"

#: Stop everything's name for this feature.
STOP_ALL_NAME = "live"
#: The event kind the status goes out under.
EVENT_KIND = "live"
#: How a session may start. "voice" is jarvis_speech's own (the owner's
#: words, checked); an app says one of the other three.
STARTED_BY = ("button", "tray", "hotkey", "voice")
APP_STARTS = ("button", "tray", "hotkey")
#: The trust source hear() asks jarvis_voice.hands_free_trusted about for a
#: Live clip: "live" when the session was started with a button (the Live
#: button, the tray, a key), "live_voice" when it was started by voice. The
#: owner's `hands_free_live` setting decides what each is trusted as.
TRUST_LIVE = "live"
TRUST_VOICE_STARTED = "live_voice"
#: The route both apps use.
ROUTE = "/api/voice/live"
TITLE = "Jarvis Live"

OFF, ON, PAUSED, ENDED = "off", "on", "paused", "ended"

# --------------------------------------------------------------------------
#   Fixed words - the apps show and say these, never anything heard
# --------------------------------------------------------------------------

#: Every pause line says what happens next, or what to do (the review of
#: 2026-09-28). Neither "tap" nor "click": the same words go to both apps.
PAUSE_WORDS = {
    "card": "Waiting for the card - approve or deny it, and Live carries on",
    "cards_unknown": "Paused: can't check for cards - Live carries on when it can, or use End Live",
    "other_voices": "Paused: other voices - just talk to carry on, or use Carry on",
    "voice_trouble": ("Paused: I'm having trouble recognising your voice - move closer or "
                      "retrain, then talk to carry on"),
}
#: The pauses the owner's own voice ends by itself (the clip is CHECKED, never
#: transcribed, while paused; the owner's voice carries on without a tap).
VOICE_PAUSES = ("other_voices", "voice_trouble")
#: The pauses for cards: nothing is checked until the card is decided.
CARD_PAUSES = ("card", "cards_unknown")
HINT_WORDS = {
    "other_voices": "Hearing other voices - only yours counts",
    "voice_trouble": "I'm having trouble recognising your voice - move closer or retrain",
}
#: Why the microphone is closed: the owner muted, or a call (the apps see it:
#: the phone's call state, another program using the PC's microphone).
MUTE_WORDS = {
    "owner": "Mic off - Jarvis can't hear you. Use Mic on to carry on",
    "call": "Paused: you're on a call - Live carries on after it, or use Listen anyway",
    "mic_in_use": ("Paused: another program is using the microphone - Live carries on when "
                   "it lets go, or use Listen anyway"),
}
MUTE_WHYS = tuple(MUTE_WORDS)
#: Why it ended, as whole sentences - shown under "Jarvis Live ended".
END_WORDS = {
    "owner": "You ended it.",
    "bye": "You said that's all.",
    "quiet": "It was quiet for a while.",
    "time": "The time was up.",
    "stop_all": "Stop everything ended it.",
    "other_device": "It moved to your other device.",
    "locked": "Windows locked.",
    "slept": "The PC went to sleep.",
    "app_lock": "App lock came on.",
    "standby": "Jarvis went on standby.",
    # The phone's "End Live when: Only when the phone's screen locks" (the
    # owner's decision of 2026-09-28, the Jarvis Live extras): the phone
    # reports it when its own screen lock comes on.
    "screen_lock": "The phone's screen locked.",
}
#: The end reasons an APP may report (POST {"do": "stop", "why": ...}). The
#: rest are the PC's own.
APP_END_REASONS = ("owner", "app_lock", "locked", "screen_lock")

#: What Jarvis says, in fixed words - safe in any room (nothing heard, nothing
#: private). jarvis_speech hands the right one to the app as `live_say`. Any
#: phrase they ask the owner to say is long enough to pass the 2-second
#: voice check at Very strict.
SAY_STARTED = "I'm listening."
SAY_WAKING = "Waking up, a few seconds."
SAY_SHORT = "Say a bit more, so I can tell it's you."
SAY_BYE = "Okay. Live ended."
SAY_EXTENDED = "Okay, {n} more minutes."
SAY_WARN = "Two minutes left. To keep going, say: give me twenty more minutes."
SAY_QUIET = "Live ended - it was quiet."
#: What the device the session was on SAYS when Live ended by itself (the
#: review of 2026-09-28: it used to end without a word for most reasons).
#: None for the owner's own End (a short end tone only), "that's all"
#: (SAY_BYE already), Stop everything (the owner asked for quiet), or a
#: locked or sleeping PC (nobody is there to hear it).
END_SAID = {
    "quiet": SAY_QUIET,
    "time": "Live ended - the time was up.",
    "app_lock": "Live ended - App lock came on.",
    "standby": "Live ended - Jarvis is on standby.",
    "other_device": "Live moved to your other device.",
}
#: Every fixed line, for the apps' shared fixture (tools/gen_live_cases.py).
LINES = {"started": SAY_STARTED, "waking": SAY_WAKING, "short": SAY_SHORT, "bye": SAY_BYE,
         "extended": SAY_EXTENDED, "warn": SAY_WARN, "quiet": SAY_QUIET}
#: Lines that must NOT restart the quiet clock when Jarvis says them: asking
#: for more words is not a conversation going on.
QUIET_KEEPS = frozenset({SAY_SHORT})

#: What both apps SHOW (never say): fixed words.
SEEN = {
    "short": "Didn't catch that - say a bit more",
    "heard": "Heard you - thinking",
    "quiet_warn": "Live ends soon - it's quiet. Say something to keep going",
    "end_hint": "To end, say \"Okay Jarvis, that's all for now\", or use End Live.",
    "call_unknown": "Jarvis can't tell when you're on a call - use Mic off",
    "move": "Live is on your {device} - move it here?",
    "elsewhere": "Jarvis Live is on your {device}",
    "not_for_me": "(not for Jarvis)",
    "trouble": "Heard you, but the words couldn't be made out - say it again",
    "busy_mic": "Jarvis Live is already listening - just talk",
}
#: How each device is named in words ("Live is on your PC") - never
#: "desktop" in anything the owner reads or hears.
DEVICE_WORDS = {"desktop": "PC", "phone": "phone"}


def device_words(device) -> str:
    """"PC", "phone", or "other device"."""
    return DEVICE_WORDS.get(str(device or ""), "other device")


#: Why Live will not start: no real voice check (broad mode, no voice print
#: for this microphone, or no voice-ID model). Each app's own place to train
#: it is added (needs_voice_words); both apps also offer a button there.
NEEDS_VOICE = "Jarvis Live didn't start: it needs your voice trained first."
NEEDS_VOICE_WHERE = {"desktop": "Settings, then Voice", "phone": "Settings, then Train my voice"}
#: Why a `live` clip was refused before anything looked at it.
NOT_ON = "Jarvis Live is not on for this device"
NOT_ON_OTHER = "Jarvis Live is on your {device}"

# --------------------------------------------------------------------------
#   When App lock ends a session on the PC (the owner's decision of
#   2026-09-28): by default when App lock would ask again ("Lock again
#   after", 1 minute after the owner last touched a Jarvis window - talking
#   does not count), with the voice setting `live_end` to end it only when
#   Windows itself locks. The looser choice is an approval card
#   (jarvis_voice_enroll); the stricter one is immediate. The desktop app
#   reads it from status()["end_on"]. The phone keeps App lock's own rule.
# --------------------------------------------------------------------------

END_ON_APP_LOCK = "app_lock"
END_ON_WINDOWS_LOCK = "windows_lock"
#: jarvis_voice's `live_end` values, and what each means here.
_END_ON = {"live_end_app_lock": END_ON_APP_LOCK, "live_end_windows_lock": END_ON_WINDOWS_LOCK}


def needs_voice_words(device) -> str:
    """NEEDS_VOICE, with where to train the voice on `device`."""
    where = NEEDS_VOICE_WHERE.get(str(device or ""))
    return f"{NEEDS_VOICE[:-1]} - {where}." if where else NEEDS_VOICE

# --------------------------------------------------------------------------
#   Side talk (the owner's answer of 2026-09-28): the owner talking to
#   someone else. The model is told (MODEL_NOTE, added by jarvis_agent to a
#   spoken Live turn only) to answer with the marker alone; both apps then
#   say nothing and show at most "(not for Jarvis)", and the turn is never
#   learned from or counted. It is NOT kept in chat history at all (the
#   owner's answer of 2026-09-28): jarvis_chat_log.record_turn drops a turn
#   whose `side_talk` is true, and both apps leave it out of the
#   conversation they send next.
# --------------------------------------------------------------------------

SIDE_TALK_MARK = "[not for me]"
#: The note jarvis_agent adds, never first, to a SPOKEN Live turn's request
#: for this PC's model - never to the caller's messages, never to a cloud
#: model (the same placing as SPOKEN_NOTE).
MODEL_NOTE = (
    "This is a live spoken conversation. The owner's very short replies, like yes or no, "
    "cannot be checked by their voice, so do not end with a yes-or-no question: when you "
    "need a choice, name the options in a few words each, so the owner can say one as a "
    "full phrase. If these words were clearly said to someone else in the room and not to "
    "you, reply with exactly " + SIDE_TALK_MARK + " and nothing else.")


def is_side_talk(answer) -> bool:
    """Is this whole answer the side-talk marker (any case, a full stop or
    spaces around it allowed)?"""
    a = str(answer or "").strip().lower().rstrip(".").strip()
    return a == SIDE_TALK_MARK


_SIDE: "OrderedDict[str, float]" = OrderedDict()
_SIDE_LOCK = threading.Lock()


def _side_key(text) -> str:
    t = " ".join(str(text or "").lower().split())
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def note_side_talk(text, now: Optional[float] = None) -> None:
    """jarvis_agent: the model called this turn side talk. Its words are
    remembered as a one-way hash, for a day, so the learner skips them
    (was_side_talk) - never the words themselves. Live's turn count does not
    count it either."""
    if not str(text or "").strip():
        return
    now = time.time() if now is None else now
    with _SIDE_LOCK:
        _SIDE.pop(_side_key(text), None)
        _SIDE[_side_key(text)] = now
        while len(_SIDE) > SIDE_TALK_MAX:
            _SIDE.popitem(last=False)
    try:
        ENGINE.uncount_turn()
    except Exception:
        pass


def was_side_talk(text, now: Optional[float] = None) -> bool:
    """jarvis_intake.owner_turns: were these words side talk (within a day)?"""
    now = time.time() if now is None else now
    with _SIDE_LOCK:
        at = _SIDE.get(_side_key(text))
    return at is not None and now - at <= SIDE_TALK_KEEP_S


# --------------------------------------------------------------------------
#   What the owner says to start, end and extend it
#
#   A GRAMMAR, like jarvis_quick.py: the WHOLE sentence must match, after a
#   leading "hey Jarvis" / "Jarvis" / "okay" / "thanks" / "no" / "please" and
#   a trailing "please" / "thanks" / "Jarvis" are taken off. Only words that
#   passed the owner check ever reach this (jarvis_speech.hear); the model has
#   no tool that starts Live, so nothing it reads - and no schedule - can
#   start one. Plain "stop" is NOT here: it still only stops Jarvis talking.
#   A phrase must still be LONG ENOUGH for the voice check (2 seconds at Very
#   strict, quiet included) - said on its own, "bye" is refused as too
#   short, so every phrase Jarvis teaches is a longer one.
# --------------------------------------------------------------------------

START_PHRASES = frozenset({
    "let's talk", "lets talk", "let us talk", "go live", "start live",
    "start jarvis live", "start a live conversation",
})
#: Not here, on purpose (the review of 2026-09-28): a bare "that's it",
#: "I'm done", "we're done" or "all done" - everyday confirmations ("Right,
#: that's it.", "Okay, I'm done." about a task) that used to end Live. Each
#: counts only with "for now" or with Live named.
END_PHRASES = frozenset({
    "that's all", "that is all", "thats all", "that's all for now", "that is all for now",
    "that's all for now bye", "that's all bye", "that's all thanks bye",
    "that's it for now", "that is it for now", "thats it for now",
    "that'll be all", "that will be all", "thatll be all",
    "i'm done for now", "i am done for now", "im done for now",
    "we're done for now", "we are done for now",
    "i'm done with live", "we're done with live", "that's it for live",
    "bye", "goodbye", "good bye", "bye bye", "bye for now", "bye then",
    "stop live", "end live", "stop jarvis live", "end jarvis live", "exit live",
    "end the conversation", "end this conversation",
})
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10,
                 "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
                 "forty five": 45, "fifty": 50, "sixty": 60}
_EXTEND_RX = re.compile(
    r"^(?:give me |i need |add |can i have |can we have |let's have |another )?"
    r"(?:(?P<n>\d{1,3}|"
    + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r") )?more (?:time|minutes?)$")
_LEAD = re.compile(r"^(?:(?:hey|hi|ok|okay|alright|all right|so|well|um|uh|please|jarvis|"
                   r"thanks|thank you|cheers|great|perfect|right|no(?! more))\b[\s,]*)+")
_TRAIL = re.compile(r"(?:[\s,]+(?:please|thanks|thank you|jarvis|then))+$")


def normalise(text) -> str:
    t = str(text or "").lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    t = " ".join(t.split())
    # "that's all" keeps its apostrophe; a stray leading or trailing one goes.
    t = t.strip("' ")
    prev = None
    while prev != t:
        prev = t
        t = _LEAD.sub("", t).strip()
        t = _TRAIL.sub("", t).strip()
    return t


def phrase(text) -> Optional[tuple]:
    """("start"|"end"|"extend", minutes or None) when the whole sentence is one
    of Live's own phrases, else None."""
    t = normalise(text)
    if not t:
        return None
    if t in START_PHRASES:
        return ("start", None)
    if t in END_PHRASES:
        return ("end", None)
    m = _EXTEND_RX.match(t)
    if m:
        n = m.group("n")
        if n is None:
            return ("extend", None)
        minutes = int(n) if n.isdigit() else _NUMBER_WORDS.get(n)
        return ("extend", minutes)
    return None


# --------------------------------------------------------------------------
#   The session
# --------------------------------------------------------------------------

def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _default_publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _default_cards_waiting() -> list:
    """The approval cards waiting (jarvis_gate.pending(), the owner's file).
    RAISES when it cannot be read: Live then pauses ("Paused: can't check for
    cards") - fail closed."""
    import jarvis_gate
    return list(jarvis_gate.pending() or [])


def _default_voice_ready(device: str) -> Optional[str]:
    """None when Live may start on `device`, else why not (NEEDS_VOICE).
    Owner mode, the voice check switched on, a voice print for that
    microphone (or the general one it falls back to), and the voice-ID model
    installed - not the spectral fallback, which refuses everyone."""
    try:
        import jarvis_voice as V
        cfg = getattr(V, "_cfg")
        if not bool(cfg("enabled", True)):
            return NEEDS_VOICE
        if str(cfg("mode", "owner") or "owner").strip().lower() != "owner":
            return NEEDS_VOICE
        if V.find_profile(device)[0] is None:
            return NEEDS_VOICE
        if not V.speaker_model_path().is_file():
            return NEEDS_VOICE
        return None
    except Exception:
        return NEEDS_VOICE


def _default_power_mode() -> str:
    """"active", "quiet" or "standby" (jarvis_power.py); "" unknown."""
    try:
        import jarvis_power
        return str(jarvis_power.current() or "")
    except Exception:
        return ""


def _default_warm() -> None:
    """Loads the everyday model in the background (jarvis_agent.warm_everyday,
    this PC's Ollama only), so Live's first answer does not wait for it."""
    def run():
        try:
            import jarvis_agent
            jarvis_agent.warm_everyday()
        except Exception:
            pass
    threading.Thread(target=run, name="jarvis-live-warm", daemon=True).start()


def _default_windows_locked() -> Optional[bool]:
    """Is the Windows lock screen in front? None when this cannot tell. Only
    a positive "locked" ends a session here; the desktop app reports the lock
    itself, and pauses Live when IT cannot tell (live.rs)."""
    if os.name != "nt":
        return None
    try:
        import jarvis_front
        read = getattr(jarvis_front, "_windows_front", None)
        front = read() if read else None
    except Exception:
        return None
    if not front:
        return None
    import ntpath
    return ntpath.basename(str(front.get("exe") or "")).lower() == "lockapp.exe"


def _default_end_on() -> str:
    """END_ON_APP_LOCK or END_ON_WINDOWS_LOCK, from jarvis_voice's `live_end`
    setting. The stricter one when it cannot be read (an older
    jarvis_voice.py, a damaged file)."""
    try:
        import jarvis_voice as V
        return _END_ON.get(str(V.settings().get("live_end") or ""), END_ON_APP_LOCK)
    except Exception:
        return END_ON_APP_LOCK


def _norm_device(device) -> str:
    d = str(device or "").strip().lower()
    return d if d in DEVICES else ""


def _created(row) -> Optional[float]:
    v = row.get("created") if isinstance(row, dict) else None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


class Live:
    """One Jarvis Live session at a time. Every reader is injected, so the
    tests drive the clock, the card queue, the power mode and the lock."""

    def __init__(self, *, clock: Callable[[], float] = time.time,
                 publish: Optional[Callable] = None,
                 cards_waiting: Optional[Callable[[], object]] = None,
                 windows_locked: Optional[Callable[[], Optional[bool]]] = None,
                 voice_ready: Optional[Callable[[str], Optional[str]]] = None,
                 power_mode: Optional[Callable[[], str]] = None,
                 warm: Optional[Callable[[], None]] = None,
                 end_on: Optional[Callable[[], str]] = None,
                 run_loop: bool = True):
        self.clock = clock
        self.publish = publish or _default_publish
        self.cards_waiting = cards_waiting or _default_cards_waiting
        self.windows_locked = windows_locked or _default_windows_locked
        self.voice_ready = voice_ready or _default_voice_ready
        self.power_mode = power_mode or _default_power_mode
        self.warm = warm or _default_warm
        self.end_on = end_on or _default_end_on
        self.run_loop = run_loop
        # Whether the session's own loop ticks (so a gap in its ticks means
        # the PC slept). The tests set it without starting the thread.
        self.loop_ticks = run_loop
        self._lock = threading.RLock()
        self.state = OFF
        self.device = ""
        self.pause: Optional[str] = None
        self.hint: Optional[str] = None
        self.started_at = 0.0
        self.ends_at = 0.0
        self.active_at = 0.0          # the quiet clock: last owner clip, Jarvis speaking, start
        self.warned = False
        self.ended_why: Optional[str] = None
        self.ended_device = ""
        self.ended_at = 0.0
        self.last_tick = 0.0
        # The session's own loop's last tick - only the loop sets it, so a
        # status read after the PC slept cannot hide the gap (B8 of the
        # review, 2026-09-28).
        self.last_loop_tick = 0.0
        self.crisis_at = 0.0
        self.session = 0             # numbered, so an app can tell a new session
        self.turns = 0                # clips that became words - a number only
        self.refused_row = 0
        self.near_row = 0
        self.refused_since = 0.0
        self.short_said_at = -1e18
        self.muted = False
        self.muted_why = ""
        self.started_by = ""
        self.crisis = False
        self.awake_seen = False       # the power mode was not standby at some tick
        self._gen = 0

    # -- plumbing -----------------------------------------------------------------
    def _emit(self) -> None:
        try:
            self.publish(EVENT_KIND, self.status())
        except Exception:
            pass

    def _on(self) -> bool:
        return self.state in (ON, PAUSED)

    def _end(self, why: str) -> None:
        # Called with the lock held.
        self.ended_device = self.device
        self.ended_at = self.clock()
        self.state, self.pause, self.hint, self.ended_why = ENDED, None, None, why
        self.ends_at, self.warned, self.crisis = 0.0, False, False
        self.muted, self.muted_why = False, ""
        self.refused_row, self.near_row, self.refused_since = 0, 0, 0.0
        self._gen += 1

    def _mode(self) -> str:
        try:
            return str(self.power_mode() or "")
        except Exception:
            return ""

    # -- start / stop / extend / resume / mute ----------------------------------------
    def start(self, device, minutes=None, by: str = "button") -> dict:
        """No card: the owner's own act. Ends a session on the other device.
        Refused without a real voice check (voice_ready). On standby it starts
        and says "Waking up" - the first question wakes the model, as any
        question does; nothing here loads it then."""
        dev = _norm_device(device)
        if not dev:
            return {"ok": False, "error": "say which device: phone or desktop"}
        by = by if by in STARTED_BY else "button"
        try:
            why = self.voice_ready(dev)
        except Exception:
            why = NEEDS_VOICE
        if why:
            if why == NEEDS_VOICE:
                why = needs_voice_words(dev)
            return {"ok": False, "error": why, "needs": "voice"}
        try:
            m = int(minutes) if minutes is not None else DEFAULT_MINUTES
        except (TypeError, ValueError):
            return {"ok": False, "error": "say how many minutes, like 30"}
        m = max(MIN_MINUTES, min(MAX_MINUTES, m))
        standby = self._mode() == "standby"
        moved = False
        with self._lock:
            if self._on() and self.device != dev:
                moved = True
                self._end("other_device")
            now = self.clock()
            self.state, self.device = ON, dev
            self.pause = self.hint = self.ended_why = None
            self.ended_device, self.ended_at = "", 0.0
            self.started_at = now
            self.ends_at = now + m * 60
            self.active_at = self.last_tick = self.last_loop_tick = now
            self.warned = self.crisis = False
            self.crisis_at = 0.0
            self.muted, self.muted_why = False, ""
            self.started_by = by
            self.refused_row, self.near_row, self.refused_since = 0, 0, 0.0
            self.turns = 0
            self.awake_seen = not standby
            self.session += 1
            self._gen += 1
            gen = self._gen
        _audit("voice.live", {"did": "start", "device": dev, "minutes": m, "by": by,
                              "ended_other": moved, "standby": standby})
        if not standby:
            # Warm the everyday model now, so the first answer does not wait
            # for it to load. Never on Standby: that is the owner's to end.
            try:
                self.warm()
            except Exception:
                pass
        self.tick()
        if self.run_loop:
            threading.Thread(target=self._loop, args=(gen,), name="jarvis-live",
                             daemon=True).start()
        self._emit()
        return {"ok": True, "status": self.status(),
                "say": SAY_WAKING if standby else SAY_STARTED}

    def _loop(self, gen: int) -> None:
        while True:
            time.sleep(TICK_S)
            with self._lock:
                if gen != self._gen or not self._on():
                    return
            try:
                self.tick(loop=True)
            except Exception:
                pass

    def stop(self, why: str = "owner", device=None) -> dict:
        """End it. Always allowed - never held on a stale link, never a card.
        `device`: only end a session on that device (a phone's App lock must
        not end the desktop's session)."""
        why = why if why in END_WORDS else "owner"
        dev = _norm_device(device)
        with self._lock:
            was = self._on() and (not dev or dev == self.device)
            if was:
                self._end(why)
        if was:
            _audit("voice.live", {"did": "end", "why": why})
            self._emit()
        return {"ok": True, "stopped": was, "status": self.status()}

    def extend(self, minutes=None) -> dict:
        try:
            m = int(minutes) if minutes is not None else EXTEND_DEFAULT_MIN
        except (TypeError, ValueError):
            return {"ok": False, "error": "say how many more minutes, like 20"}
        if m < 1:
            return {"ok": False, "error": "say how many more minutes, like 20"}
        with self._lock:
            if not self._on():
                return {"ok": False, "error": "Jarvis Live is not on."}
            now = self.clock()
            # Never more than MAX_MINUTES from now, whatever is asked - but
            # never sooner than a crisis turn's extra time either.
            self.ends_at = max(min(self.ends_at + m * 60, now + MAX_MINUTES * 60),
                               self.ends_at if self.crisis else 0.0)
            self.active_at = now
            if self.ends_at - now > WARN_BEFORE_S:
                self.warned = False
        _audit("voice.live", {"did": "extend", "minutes": m})
        self._emit()
        return {"ok": True, "minutes": m, "status": self.status()}

    def resume(self) -> dict:
        """"Carry on" after a voice pause (other voices, or trouble with the
        owner's voice). A card pause ends by itself when the card is decided."""
        with self._lock:
            if self.state != PAUSED or self.pause not in VOICE_PAUSES:
                return {"ok": True, "resumed": False, "status": self.status()}
            self._carry_on()
        _audit("voice.live", {"did": "resume"})
        self.tick()
        self._emit()
        return {"ok": True, "resumed": True, "status": self.status()}

    def _carry_on(self) -> None:
        # Called with the lock held.
        self.state, self.pause, self.hint = ON, None, None
        self.refused_row, self.near_row, self.refused_since = 0, 0, 0.0
        self.active_at = self.clock()

    def mute(self, muted: bool, device=None, why: str = "owner") -> dict:
        """Mute: the app closes its microphone and sends nothing; the session
        and its time limit carry on, the quiet clock stands still. Unmute
        listens again, and the quiet clock starts from then. `why`: "owner"
        (the Mute button), "call" (the phone is on a call) or "mic_in_use"
        (another program has the PC's microphone). A call ending never
        unmutes what the OWNER muted. Neither is held on a stale link:
        muting only makes Jarvis hear less, and unmuting changes nothing the
        owner did not already start."""
        dev = _norm_device(device)
        why = why if why in MUTE_WHYS else "owner"
        with self._lock:
            if not self._on() or (dev and dev != self.device):
                return {"ok": False, "error": "Jarvis Live is not on."}
            before = (self.muted, self.muted_why)
            if muted:
                if not (self.muted and self.muted_why == "owner"):
                    self.muted, self.muted_why = True, why
            elif not (why != "owner" and self.muted_why == "owner"):
                self.muted, self.muted_why = False, ""
            self.active_at = self.clock()
            changed = before != (self.muted, self.muted_why)
        if changed:
            _audit("voice.live", {"did": "mute" if muted else "unmute", "why": why})
            self._emit()
        return {"ok": True, "status": self.status()}

    def note_active(self, device=None) -> dict:
        """The owner typed, or tapped a quick answer, in Live on `device` (B4
        of the review, 2026-09-28): that is the conversation going on too,
        so the quiet clock starts again - as a spoken sentence does. Nothing
        else changes, and nothing typed comes here (the words go to the chat
        route as usual). Not held on a stale link: it can only keep open a
        session the owner started, never start or widen anything."""
        dev = _norm_device(device)
        with self._lock:
            if not self._on() or (dev and dev != self.device):
                return {"ok": False, "error": "Jarvis Live is not on."}
            if self.pause not in CARD_PAUSES and not self.muted:
                self.active_at = max(self.active_at, self.clock())
        return {"ok": True, "status": self.status()}

    # -- the check, once a second ----------------------------------------------------
    def _new_cards(self) -> int:
        """Approval cards raised since this session started (a card with no
        readable time counts as new); RAISES when the queue cannot be read."""
        rows = self.cards_waiting()
        if isinstance(rows, bool):
            rows = []
        if isinstance(rows, int):
            return rows
        n = 0
        for row in rows or []:
            t = _created(row)
            if t is None or t >= self.started_at - CARD_SLACK_S:
                n += 1
        return n

    def tick(self, *, loop: bool = False) -> None:
        changed = False
        with self._lock:
            if not self._on():
                return
            now = self.clock()
            mode = self._mode()
            if mode and mode != "standby":
                self.awake_seen = True
            # The PC slept: the session's own loop could not tick for a
            # while. Checked on EVERY tick (a status read or a clip after the
            # PC woke may come before the loop's next one), against the
            # loop's own last tick - which only the loop moves - so a read
            # cannot hide the gap. Only when the loop runs at all (the tests
            # drive the clock without it).
            if (loop or self.loop_ticks) and self.last_loop_tick \
                    and now - self.last_loop_tick > SLEEP_GAP_S:
                self._end("slept")
                changed = True
            elif now >= self.ends_at:
                self._end("time")
                changed = True
            elif mode == "standby" and self.awake_seen:
                # Standby began DURING Live (by hand or by the schedule).
                self._end("standby")
                changed = True
            else:
                self.last_tick = now
                if loop:
                    self.last_loop_tick = now
                locked = None
                if self.device == "desktop":
                    try:
                        locked = self.windows_locked()
                    except Exception:
                        locked = None
                if locked is True:
                    self._end("locked")
                    changed = True
                else:
                    try:
                        waiting = self._new_cards()
                    except Exception:
                        waiting = -1          # cannot tell: fail closed
                    held = "card" if waiting > 0 else "cards_unknown" if waiting < 0 else None
                    if held:
                        # A card waits (or the queue cannot be read): nothing
                        # is heard until it is decided or times out, and the
                        # quiet clock does not run.
                        self.active_at = now
                        if self.pause != held:
                            self.state, self.pause = PAUSED, held
                            changed = True
                    elif self.pause in CARD_PAUSES:
                        self.state, self.pause = ON, None
                        self.active_at = now
                        changed = True
                    if self.muted:
                        # A closed microphone cannot be forgotten open: the
                        # quiet clock waits for Unmute.
                        self.active_at = now
                    if (self._on() and self.pause not in CARD_PAUSES
                            and not self.crisis and now - self.active_at >= QUIET_S):
                        self._end("quiet")
                        changed = True
                    elif (self._on() and not self.warned and not self.crisis
                          and self.ends_at - now <= WARN_BEFORE_S):
                        # No "minutes left" warning after a crisis turn.
                        self.warned = True
                        changed = True
            ended = self.state == ENDED
            why = self.ended_why
        if changed:
            if ended:
                _audit("voice.live", {"did": "end", "why": why})
            self._emit()

    def note_crisis(self) -> None:
        """A crisis turn while Live is on (jarvis_agent.note_crisis_turn): no
        quiet-timeout end and no "minutes left" warning for the rest of this
        session, and the time limit moves to at least CRISIS_MORE_S after
        this turn (the owner's answer of 2026-09-28) - quietly: nothing is
        said or shown about it beyond the minutes left."""
        changed = False
        with self._lock:
            if self._on():
                now = self.clock()
                self.crisis, self.crisis_at = True, now
                self.warned = False
                if self.ends_at < now + CRISIS_MORE_S:
                    self.ends_at = now + CRISIS_MORE_S
                changed = True
        if changed:
            self._emit()

    def trust_source(self, device) -> str:
        """What a Live clip from `device` asks jarvis_voice.hands_free_trusted
        about: TRUST_VOICE_STARTED when the session was started by voice,
        TRUST_LIVE otherwise."""
        with self._lock:
            by = self.started_by if self._on() else ""
        return TRUST_VOICE_STARTED if by == "voice" else TRUST_LIVE

    # -- what jarvis_speech tells it --------------------------------------------------
    def accepts(self, device) -> dict:
        """May a `live` clip from `device` be looked at? Checked BEFORE
        anything else in jarvis_speech.hear().

        {"ok": True} - look at it as usual.
        {"ok": False, "state", "code", "words", "check": bool} - refused;
        with `check` (a voice pause) it may still be put to the voice check
        - never to speech-to-text - so the owner's voice can carry on."""
        self.tick()
        dev = _norm_device(device)
        with self._lock:
            if not self._on() or not dev or dev != self.device:
                if self._on() and dev and dev != self.device:
                    return {"ok": False, "state": OFF, "code": "",
                            "words": NOT_ON_OTHER.format(device=device_words(self.device)),
                            "check": False}
                return {"ok": False, "state": OFF, "code": "", "words": NOT_ON, "check": False}
            if self.muted:
                return {"ok": False, "state": PAUSED, "code": "muted",
                        "words": MUTE_WORDS.get(self.muted_why, MUTE_WORDS["owner"]),
                        "check": False}
            if self.state == PAUSED:
                return {"ok": False, "state": PAUSED, "code": self.pause or "",
                        "words": PAUSE_WORDS.get(self.pause or "", ""),
                        "check": self.pause in VOICE_PAUSES}
            return {"ok": True, "state": ON, "code": "", "words": "", "check": False}

    def carry_on_by_voice(self, device) -> bool:
        """The owner's voice passed the check during a voice pause: Live
        carries on without a tap. True when it was paused that way."""
        with self._lock:
            if (not self._on() or _norm_device(device) != self.device
                    or self.state != PAUSED or self.pause not in VOICE_PAUSES):
                return False
            self._carry_on()
        _audit("voice.live", {"did": "resume", "by": "voice"})
        self._emit()
        return True

    def on_elsewhere(self, device) -> str:
        """The device Live is on, when it is on and is NOT `device`; else ""."""
        dev = _norm_device(device)
        with self._lock:
            if self._on() and dev and self.device != dev:
                return self.device
        return ""

    def note_owner(self, device) -> None:
        """A `live` clip passed the owner check and became words."""
        changed = False
        with self._lock:
            if not self._on() or _norm_device(device) != self.device:
                return
            self.turns += 1
            self.active_at = self.clock()
            if self.refused_row or self.hint:
                changed = self.hint is not None
                self.refused_row, self.near_row, self.refused_since = 0, 0, 0.0
                self.hint = None
        if changed:
            self._emit()

    def uncount_turn(self) -> None:
        """A turn the model called side talk is not counted either."""
        with self._lock:
            if self._on() and self.turns > 0:
                self.turns -= 1

    def note_refused(self, device, near_miss: bool = False) -> None:
        """A `live` clip that was NOT the owner's voice. The quiet clock does
        not move (the TV must not keep Live open). `near_miss`: it was close
        to the bar - most such in a row means the owner's own voice is
        failing, and the sign says so instead of "other voices"."""
        changed = False
        with self._lock:
            if not self._on() or _norm_device(device) != self.device:
                return
            now = self.clock()
            if self.refused_row == 0:
                self.refused_since = now
            self.refused_row += 1
            self.near_row += 1 if near_miss else 0
            kind = "voice_trouble" if self.near_row * 2 > self.refused_row else "other_voices"
            if self.refused_row >= HINT_AFTER and self.hint != kind:
                self.hint = kind
                changed = True
            if self.state == ON and (self.refused_row >= PAUSE_AFTER or
                                     now - self.refused_since >= PAUSE_AFTER_S):
                self.state, self.pause = PAUSED, kind
                changed = True
            elif self.state == PAUSED and self.pause in VOICE_PAUSES and self.pause != kind:
                self.pause = kind
                changed = True
        if changed:
            _audit("voice.live", {"did": "refusals", "in_a_row": self.refused_row,
                                  "paused": self.state == PAUSED})
            self._emit()

    def short_line_due(self) -> bool:
        """Say SAY_SHORT now? At most once every SHORT_LINE_EVERY_S."""
        with self._lock:
            now = self.clock()
            if now - self.short_said_at < SHORT_LINE_EVERY_S:
                return False
            self.short_said_at = now
            return True

    def note_spoke(self, device="", text: str = "") -> None:
        """Jarvis made the sound of a sentence (jarvis_speech.say): the quiet
        clock starts again - unless the sentence was only Live asking for
        more words (QUIET_KEEPS). Any device - the say route does not always
        say which app plays it."""
        if text in QUIET_KEEPS:
            return
        with self._lock:
            if self._on() and self.pause not in CARD_PAUSES:
                self.active_at = max(self.active_at, self.clock())

    # -- what the apps see ------------------------------------------------------------
    def status(self) -> dict:
        """On/off, the device, time left and reasons from FIXED lists."""
        with self._lock:
            now = self.clock()
            on = self._on()
            left = int(max(0, round(self.ends_at - now))) if on else None
            quiet_left = (int(max(0, round(QUIET_S - (now - self.active_at))))
                          if on and self.pause not in CARD_PAUSES
                          and not self.muted and not self.crisis else None)
            resumable = (self.state == ENDED and self.ended_why in ("quiet", "time")
                         and now - self.ended_at <= RESUME_S)
            ended = self.state == ENDED
            # Seconds since it ended, as the PC counts them: the apps show
            # "Jarvis Live ended" for ENDED_SHOW_S (or "Resume Live" while
            # resumable) from this, counting on by themselves - a status
            # read once is never taken as "just now" (the review's #4, #5).
            ended_ago = int(max(0, round(now - self.ended_at))) if ended else None
            out = {
                "state": self.state,
                "on": on,
                "device": self.device if on else None,
                "session": self.session,
                "left_s": left,
                "minutes_left": (left + 59) // 60 if left is not None else None,
                "quiet_left_s": quiet_left,
                "quiet_warn": bool(quiet_left is not None and quiet_left <= QUIET_WARN_S),
                "paused": self.pause if self.state == PAUSED else None,
                "pause_words": PAUSE_WORDS.get(self.pause) if self.state == PAUSED else None,
                "muted": bool(on and self.muted),
                "muted_why": self.muted_why if on and self.muted else None,
                "muted_words": (MUTE_WORDS.get(self.muted_why) if on and self.muted else None),
                "started_by": self.started_by if on else None,
                # When it started, by the PC's clock - the same clock an
                # approval card's `created` is on, so an app can tell a card
                # raised in THIS session from one that was already waiting
                # (the design's C8; the review's B8: an old card must not
                # hold Live, nor hide the tap buttons).
                "started_at": self.started_at if on else None,
                "hint": self.hint if on else None,
                "hint_words": HINT_WORDS.get(self.hint) if on and self.hint else None,
                "ending_soon": bool(on and self.warned),
                "ended": self.ended_why if ended else None,
                "ended_words": END_WORDS.get(self.ended_why) if ended else None,
                "ended_say": END_SAID.get(self.ended_why) if ended else None,
                "ended_device": self.ended_device if ended else None,
                "ended_ago_s": ended_ago,
                "resumable": resumable,
                "turns": self.turns,
                "refused_in_a_row": self.refused_row if on else 0,
                "limits": {"default_minutes": DEFAULT_MINUTES, "max_minutes": MAX_MINUTES,
                           "extend_minutes": EXTEND_DEFAULT_MIN, "quiet_s": QUIET_S,
                           "quiet_warn_s": QUIET_WARN_S, "warn_s": WARN_BEFORE_S,
                           "resume_s": RESUME_S, "ended_show_s": ENDED_SHOW_S,
                           "crisis_more_s": CRISIS_MORE_S},
                "lines": dict(LINES),
                "seen": dict(SEEN),
            }
        try:
            end_on = str(self.end_on() or END_ON_APP_LOCK)
        except Exception:
            end_on = END_ON_APP_LOCK
        # When App lock ends a session on the PC (the `live_end` setting).
        out["end_on"] = end_on if end_on in (END_ON_APP_LOCK, END_ON_WINDOWS_LOCK) \
            else END_ON_APP_LOCK
        out["camera"] = camera_status()
        return out

    def stop_everything(self) -> Optional[str]:
        with self._lock:
            was = self._on()
            if was:
                self._end("stop_all")
        if not was:
            return None
        _audit("voice.live", {"did": "end", "why": "stop_all"})
        self._emit()
        return "Jarvis Live ended."


# --------------------------------------------------------------------------
#   The camera - built switched OFF (the owner's answer 3, 2026-09-28)
# --------------------------------------------------------------------------
#
# The camera switch appears in the phone ONLY when this says `ready`: the
# second card's Pictures lane is running AND jarvis_live_photo_test.py has
# written a PASSING result on this PC for the model that lane uses. No
# words-only camera on one card. On a one-card PC - the owner's PC today -
# there is no passing result, so this is false and cheap (one folder read).

PHOTO_TEST_DIR_NAME = "photo-test"
CAMERA_NEEDS = ("The camera needs the second graphics card (the 12 GB one) and a passed photo "
                "test on this PC. Until then it stays off.")


def _config_dir() -> Path:
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def photo_test_dir() -> Path:
    """Where jarvis_live_photo_test.py writes one folder per run."""
    return _config_dir() / "live" / PHOTO_TEST_DIR_NAME


#: The PC's own half of a camera question - recording CAMERA_TOOL for the
#: turn, and telling the picture model never to name a person from their
#: face (the design's section 5) - is wired when the camera is switched on,
#: build step 10, after the card is measured. Until then the camera is not
#: ready even with a passing photo test: it stays off rather than half-built.
CAMERA_WIRED = False


def is_cloud_model(name) -> bool:
    """A model name Ollama answers off this machine ("...-cloud",
    "...:cloud"): never used for a picture (ARCHITECTURE section 4)."""
    n = str(name or "").strip().lower()
    return n.endswith("-cloud") or n.endswith(":cloud") or ":cloud" in n or "-cloud:" in n


def newest_photo_test() -> Optional[dict]:
    """The newest photo-test run's results (jarvis_live_photo_test.py), or
    None. Only the newest run counts: a later failing run takes the camera
    away again. A run whose results cannot be read counts as not passed."""
    root = photo_test_dir()
    try:
        runs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)
    except Exception:
        return None
    if not runs:
        return None
    try:
        doc = json.loads((runs[-1] / "results.json").read_text(encoding="utf-8"))
    except Exception:
        return {"passed": False}
    return doc if isinstance(doc, dict) else {"passed": False}


def _vision_lane():
    try:
        import jarvis_second_card
        return jarvis_second_card.lane_for("vision")
    except Exception:
        return None


def camera_status(*, lane_reader: Optional[Callable] = None) -> dict:
    """{"ready": bool, "why": str}. Ready only when the newest photo test
    PASSED for the model the second card's Pictures lane runs NOW - and the
    PC's half of a camera question is built (CAMERA_WIRED). Cheap on a
    one-card PC: one folder read, and the lane is not even asked."""
    doc = newest_photo_test()
    if doc is None or doc.get("passed") is not True:
        return {"ready": False, "why": CAMERA_NEEDS}
    lane = (lane_reader or _vision_lane)()
    if lane is None:
        return {"ready": False, "why": ("The photo test passed, but the second card's Pictures "
                                        "lane is not running now. Switch Pictures on in \"Your "
                                        "second graphics card\".")}
    lane_model = str(getattr(lane, "model", "") or "")
    if is_cloud_model(lane_model):
        # ARCHITECTURE section 4: a picture never leaves this PC.
        return {"ready": False, "why": ("The Pictures lane names a cloud model. A picture never "
                                        "leaves this PC, so the camera stays off.")}
    models = doc.get("models") if isinstance(doc.get("models"), dict) else {}
    got = models.get(lane_model)
    if not isinstance(got, dict) or got.get("passed") is not True:
        return {"ready": False, "why": ("The photo test passed for a different picture model "
                                        "than the one the second card runs now. Run the photo "
                                        "test again.")}
    if not CAMERA_WIRED:
        return {"ready": False, "why": ("The photo test passed. The PC's own half of the camera "
                                        "is the next build step, so the camera stays off until "
                                        "it is built.")}
    return {"ready": True, "why": ""}


def screen_picture_allowed(device) -> bool:
    """May a "Watch with me" screen picture go with a Live question asked on
    `device`? Only at the PC: a question asked on the phone never picks up
    the PC's screen (the rules review, 2026-09-28). For the chat route's
    screen wiring (docs/SCREEN-DESIGN.md step 3), which is not built yet."""
    return _norm_device(device) == "desktop"


# --------------------------------------------------------------------------
#   The one engine, Stop everything, and the route
# --------------------------------------------------------------------------

ENGINE = Live()


def _stop_for_stop_all() -> Optional[str]:
    return ENGINE.stop_everything()


try:
    import jarvis_stop_all
    jarvis_stop_all.register(STOP_ALL_NAME, _stop_for_stop_all)
except Exception:
    pass    # without Stop everything on this PC, Live is ended by its own End button


def handle_get(query: str = "") -> tuple:
    ENGINE.tick()
    return 200, ENGINE.status()


def handle_post(body) -> tuple:
    """{"do": "start", "device", "minutes"?} | {"do": "stop", "why"?, "device"?}
    | {"do": "extend", "minutes"?} | {"do": "resume"} | {"do": "mute"|"unmute",
    "device"?, "why"?: "owner"|"call"|"mic_in_use"} | {"do": "active",
    "device"?} (the owner typed or tapped in Live: the quiet clock starts
    again). Start, extend and resume are held by both apps on a stale link
    (rule 4); stop, mute, unmute and active always go."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    do = str(body.get("do") or "").strip().lower()
    if do == "start":
        by = str(body.get("by") or "button").strip().lower()
        out = ENGINE.start(body.get("device"), body.get("minutes"),
                           by=by if by in APP_STARTS else "button")
        return (200 if out.get("ok") else 409 if out.get("needs") else 400), out
    if do == "stop":
        why = str(body.get("why") or "owner").strip().lower()
        if why not in APP_END_REASONS:
            why = "owner"
        return 200, ENGINE.stop(why, device=body.get("device"))
    if do == "extend":
        out = ENGINE.extend(body.get("minutes"))
        return (200 if out.get("ok") else 409), out
    if do == "resume":
        return 200, ENGINE.resume()
    if do in ("mute", "unmute"):
        why = str(body.get("why") or "owner").strip().lower()
        out = ENGINE.mute(do == "mute", device=body.get("device"),
                          why=why if why in MUTE_WHYS else "owner")
        return (200 if out.get("ok") else 409), out
    if do == "active":
        out = ENGINE.note_active(body.get("device"))
        return (200 if out.get("ok") else 409), out
    return 400, {"ok": False,
                 "error": "do must be start, stop, extend, resume, mute, unmute or active"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so /api/voice/live is answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_live", False):
        return "  live       Jarvis Live (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parsed = urlsplit(str(getattr(self, "path", "") or ""))
        if parsed.path.rstrip("/") != ROUTE:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(parsed.query)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != ROUTE:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(body)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_live = True
    do_POST._jarvis_live = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  live       Jarvis Live: talk back and forth (camera off until the second card passes)"


def _reset_for_tests(**kw) -> "Live":
    """A fresh engine (tests)."""
    global ENGINE
    kw.setdefault("run_loop", False)
    ENGINE = Live(**kw)
    return ENGINE
