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
full-duplex." And the owner's answers to the design (2026-09-28):
  1. under "Only trust the talk button", a Live turn is trusted like the talk
     button by default, with a voice setting (`hands_free_live`,
     jarvis_voice.py) to give it the "Hey Jarvis" caution instead;
  2. answers about what the camera sees are read aloud like screen answers
     (CAMERA_TOOL below is on the apps' read-aloud list, and is governed by
     the same `screen_aloud` as the screen);
  3. the camera stays OFF until the 12 GB card is in and a photo test passes
     (camera_status() below: false until a passing result for the Pictures
     lane's model is on file - no words-only camera on one card).

IN PLAIN WORDS, WHAT HAPPENS
  * The owner presses Live (or says "Hey Jarvis, let's talk"). No card: it is
    the owner's own act, like the talk button or "Watch with me". ONE session
    at a time, on ONE device ("phone" or "desktop"): starting on one ends the
    other's.
  * While it is on, that device sends every sentence it hears as a clip with
    `source=live`. jarvis_speech.hear() takes such a clip exactly as it takes
    any other - speech found first, long enough, THE OWNER CHECK, and only
    then speech-to-text - with one difference: no "hey Jarvis" is needed. A
    `live` clip from a device with no session on is refused before anything
    looks at it, never checked, never transcribed.
  * It pauses (nothing heard, nothing sent) while an approval card waits -
    "Waiting for your tap on the card" - so a spoken "yes" is not even
    heard; cards are decided by tapping only. After 3 clips in a row that were
    not the owner's voice the sign says "Hearing other voices - only yours
    counts"; after 10, or two minutes of nothing but other voices, it pauses
    ("Paused: other voices") until the owner taps Carry on.
  * It ENDS when the owner presses End / Stop, says "that's all" or "bye"
    (the owner check first, like any command), on Stop everything, after 90
    seconds of quiet since Jarvis last spoke (QUIET_S), at the time limit (30
    minutes, "20 more minutes" extends, 2 hours at most), when Windows locks
    or the PC sleeps (a desktop session), or when App lock locks the phone (a
    phone session - the phone says so). It never restarts by itself.

WHAT THE APPS SEE is status(): on/off, which device, the time left, a pause,
a hint and an end reason from FIXED lists of plain words, and counts. Never a
word anyone said, never a sound. The `live` event carries status() and
nothing else; the audit log carries counts and fixed words.

NOTHING IS KEPT HERE beyond numbers: the clips are jarvis_speech's (in memory,
checked, dropped); the words become an ordinary spoken chat turn, kept in chat
history like any chat (the owner's decision of 2026-09-24).

WHAT IT CANNOT DO, SAID PLAINLY
  * A very short reply - "yes", "no", even a bare "bye" - is refused as too
    short to check (jarvis_voice.MIN_COMMAND_SECONDS: 1.5 s balanced, 2 s very
    strict, measured with a little quiet either side). The owner is asked to
    say a bit more (SAY_SHORT, at most once a minute). "That's all for now,
    bye" is long enough; the End button always works.
  * The voice check cannot tell a recording of the owner from the owner. The
    `hands_free_live` setting gives Live the "Hey Jarvis" caution for that.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
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
#: How long, by default and at most, in minutes (the same numbers as "Watch
#: with me", jarvis_screen.py).
DEFAULT_MINUTES = 30
MIN_MINUTES = 1
MAX_MINUTES = 120
#: "20 more minutes" with no number ("more time").
EXTEND_DEFAULT_MIN = 20
#: The warning before the end, in seconds.
WARN_BEFORE_S = 120
#: Quiet this long after Jarvis last spoke (or the owner last spoke, or Live
#: started) ends Live (proposed in the design: long enough to think, short
#: enough that an open microphone is not forgotten).
QUIET_S = 90
#: Clips in a row that were not the owner's voice before the sign says so...
HINT_AFTER = 3
#: ...and before Live pauses.
PAUSE_AFTER = 10
#: Or: nothing but other voices for this long.
PAUSE_AFTER_S = 120
#: "Say a bit more, so I can tell it's you." - not more often than this.
SHORT_LINE_EVERY_S = 60
#: The session's own check.
TICK_S = 1.0
#: A gap this long between two checks means the PC slept: the session ends.
SLEEP_GAP_S = 30.0

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
#: The route both apps use.
ROUTE = "/api/voice/live"
TITLE = "Jarvis Live"

OFF, ON, PAUSED, ENDED = "off", "on", "paused", "ended"

# --------------------------------------------------------------------------
#   Fixed words - the apps show and say these, never anything heard
# --------------------------------------------------------------------------

PAUSE_WORDS = {
    "card": "Waiting for your tap on the card",
    "other_voices": "Paused: other voices",
}
HINT_WORDS = {
    "other_voices": "Hearing other voices - only yours counts",
}
END_WORDS = {
    "owner": "you ended it",
    "bye": "you said that's all",
    "quiet": "it was quiet",
    "time": "the time was up",
    "stop_all": "Stop everything",
    "other_device": "Live started on your other device",
    "locked": "Windows locked",
    "slept": "the PC slept",
    "app_lock": "App lock locked the phone",
}
#: The end reasons an APP may report (POST {"do": "stop", "why": ...}). The
#: rest are the PC's own.
APP_END_REASONS = ("owner", "app_lock", "locked")

#: What Jarvis says, in fixed words - safe in any room (nothing heard, nothing
#: private). jarvis_speech hands the right one to the app as `live_say`.
SAY_STARTED = "I'm listening."
SAY_SHORT = "Say a bit more, so I can tell it's you."
SAY_BYE = "Okay. Live ended."
SAY_EXTENDED = "Okay, {n} more minutes."
SAY_WARN = "Two minutes left. Say 'more time' to keep going."
SAY_QUIET = "Live ended - it was quiet."
#: Every fixed line, for the apps' shared fixture (tools/gen_live_cases.py).
LINES = {"started": SAY_STARTED, "short": SAY_SHORT, "bye": SAY_BYE,
         "extended": SAY_EXTENDED, "warn": SAY_WARN, "quiet": SAY_QUIET}

#: Why a `live` clip was refused before anything looked at it.
NOT_ON = "Jarvis Live is not on for this device"
NOT_ON_OTHER = "Jarvis Live is on your {device}"

# --------------------------------------------------------------------------
#   What the owner says to start, end and extend it
#
#   A GRAMMAR, like jarvis_quick.py: the WHOLE sentence must match, after a
#   leading "hey Jarvis" / "Jarvis" / "okay" / "please" and a trailing
#   "please" / "thanks" / "Jarvis" are taken off. Only words that passed the
#   owner check ever reach this (jarvis_speech.hear); the model has no tool
#   that starts Live, so nothing it reads - and no schedule - can start one.
#   Plain "stop" is NOT here: it still only stops Jarvis talking, as today.
# --------------------------------------------------------------------------

START_PHRASES = frozenset({
    "let's talk", "lets talk", "let us talk", "go live", "start live",
    "start jarvis live", "start a live conversation",
})
END_PHRASES = frozenset({
    "that's all", "that is all", "thats all", "that's all for now", "that is all for now",
    "that's all for now bye", "that's all bye", "that's all thanks bye",
    "bye", "goodbye", "good bye", "bye bye", "bye for now", "ok bye", "okay bye",
    "stop live", "end live", "stop jarvis live", "end jarvis live", "exit live",
    "end the conversation", "end this conversation",
})
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10,
                 "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
                 "forty five": 45, "fifty": 50, "sixty": 60}
_EXTEND_RX = re.compile(
    r"^(?:give me |i need |add |can i have |can we have )?(?:(?P<n>\d{1,3}|"
    + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r") )?more (?:time|minutes?)$")
_LEAD = re.compile(r"^(?:(?:hey|hi|ok|okay|alright|all right|so|well|um|uh|please|jarvis)\b[\s,]*)+")
_TRAIL = re.compile(r"(?:[\s,]+(?:please|thanks|thank you|jarvis))+$")


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


def _default_cards_waiting() -> int:
    """How many approval cards wait (jarvis_gate.pending(), the owner's file).
    0 when it cannot be read: Live then listens as usual - a card still
    needs a tap either way, and never a spoken yes."""
    try:
        import jarvis_gate
        return len(jarvis_gate.pending() or [])
    except Exception:
        return 0


def _default_windows_locked() -> Optional[bool]:
    """Is the Windows lock screen in front? None when this cannot tell (not
    Windows, no reader)."""
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


def _norm_device(device) -> str:
    d = str(device or "").strip().lower()
    return d if d in DEVICES else ""


class Live:
    """One Jarvis Live session at a time. Every reader is injected, so the
    tests drive the clock, the card queue and the lock screen."""

    def __init__(self, *, clock: Callable[[], float] = time.time,
                 publish: Optional[Callable] = None,
                 cards_waiting: Optional[Callable[[], int]] = None,
                 windows_locked: Optional[Callable[[], Optional[bool]]] = None,
                 run_loop: bool = True):
        self.clock = clock
        self.publish = publish or _default_publish
        self.cards_waiting = cards_waiting or _default_cards_waiting
        self.windows_locked = windows_locked or _default_windows_locked
        self.run_loop = run_loop
        self._lock = threading.RLock()
        self.state = OFF
        self.device = ""
        self.pause: Optional[str] = None
        self.hint: Optional[str] = None
        self.ends_at = 0.0
        self.active_at = 0.0          # the quiet clock: last owner clip, Jarvis speaking, start
        self.warned = False
        self.ended_why: Optional[str] = None
        self.ended_device = ""
        self.last_tick = 0.0
        self.session = 0              # numbered, so an app can tell a new session
        self.turns = 0                # clips that became words - a number only
        self.refused_row = 0
        self.refused_since = 0.0
        self.short_said_at = -1e18
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
        self.state, self.pause, self.hint, self.ended_why = ENDED, None, None, why
        self.ends_at, self.warned = 0.0, False
        self.refused_row, self.refused_since = 0, 0.0
        self._gen += 1

    # -- start / stop / extend / resume -----------------------------------------------
    def start(self, device, minutes=None) -> dict:
        """No card: the owner's own act. Ends a session on the other device."""
        dev = _norm_device(device)
        if not dev:
            return {"ok": False, "error": "say which device: phone or desktop"}
        try:
            m = int(minutes) if minutes is not None else DEFAULT_MINUTES
        except (TypeError, ValueError):
            return {"ok": False, "error": "say how many minutes, like 30"}
        m = max(MIN_MINUTES, min(MAX_MINUTES, m))
        moved = False
        with self._lock:
            if self._on() and self.device != dev:
                moved = True
                self._end("other_device")
            now = self.clock()
            self.state, self.device = ON, dev
            self.pause = self.hint = self.ended_why = None
            self.ended_device = ""
            self.ends_at = now + m * 60
            self.active_at = self.last_tick = now
            self.warned = False
            self.refused_row, self.refused_since = 0, 0.0
            self.turns = 0
            self.session += 1
            self._gen += 1
            gen = self._gen
        _audit("voice.live", {"did": "start", "device": dev, "minutes": m,
                              "ended_other": moved})
        self.tick()
        if self.run_loop:
            threading.Thread(target=self._loop, args=(gen,), name="jarvis-live",
                             daemon=True).start()
        self._emit()
        return {"ok": True, "status": self.status()}

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
            # Never more than MAX_MINUTES from now, whatever is asked.
            self.ends_at = min(self.ends_at + m * 60, now + MAX_MINUTES * 60)
            self.active_at = now
            if self.ends_at - now > WARN_BEFORE_S:
                self.warned = False
        _audit("voice.live", {"did": "extend", "minutes": m})
        self._emit()
        return {"ok": True, "minutes": m, "status": self.status()}

    def resume(self) -> dict:
        """"Carry on" after "Paused: other voices". A card pause ends by
        itself when the card is decided."""
        with self._lock:
            if self.state != PAUSED or self.pause != "other_voices":
                return {"ok": True, "resumed": False, "status": self.status()}
            self.state, self.pause, self.hint = ON, None, None
            self.refused_row, self.refused_since = 0, 0.0
            self.active_at = self.clock()
        _audit("voice.live", {"did": "resume"})
        self.tick()
        self._emit()
        return {"ok": True, "resumed": True, "status": self.status()}

    # -- the check, once a second ----------------------------------------------------
    def tick(self, *, loop: bool = False) -> None:
        changed = False
        with self._lock:
            if not self._on():
                return
            now = self.clock()
            if loop and self.last_tick and now - self.last_tick > SLEEP_GAP_S:
                self._end("slept")
                changed = True
            elif now >= self.ends_at:
                self._end("time")
                changed = True
            else:
                self.last_tick = now
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
                        waiting = int(self.cards_waiting() or 0)
                    except Exception:
                        waiting = 0
                    if waiting > 0:
                        # A card waits: nothing is heard until it is decided
                        # or times out, and the quiet clock does not run.
                        self.active_at = now
                        if self.pause != "card":
                            self.state, self.pause = PAUSED, "card"
                            changed = True
                    elif self.pause == "card":
                        self.state, self.pause = ON, None
                        self.active_at = now
                        changed = True
                    if self._on() and self.pause != "card" and now - self.active_at >= QUIET_S:
                        self._end("quiet")
                        changed = True
                    elif self._on() and not self.warned and self.ends_at - now <= WARN_BEFORE_S:
                        self.warned = True
                        changed = True
            ended = self.state == ENDED
            why = self.ended_why
        if changed:
            if ended:
                _audit("voice.live", {"did": "end", "why": why})
            self._emit()

    # -- what jarvis_speech tells it --------------------------------------------------
    def accepts(self, device) -> tuple:
        """May a `live` clip from `device` be looked at? (ok, state, reason
        code, words). Checked BEFORE anything else in jarvis_speech.hear()."""
        self.tick()
        dev = _norm_device(device)
        with self._lock:
            if not self._on() or not dev or dev != self.device:
                if self._on() and dev and dev != self.device:
                    return False, OFF, "", NOT_ON_OTHER.format(device=self.device)
                return False, OFF, "", NOT_ON
            if self.state == PAUSED:
                return False, PAUSED, self.pause or "", PAUSE_WORDS.get(self.pause or "", "")
            return True, ON, "", ""

    def on_elsewhere(self, device) -> str:
        """The device Live is on, when it is on and is NOT `device` - for
        dropping the other device's "hey Jarvis" clips; else ""."""
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
                self.refused_row, self.refused_since, self.hint = 0, 0.0, None
        if changed:
            self._emit()

    def note_refused(self, device) -> None:
        """A `live` clip that was NOT the owner's voice. The quiet clock does
        not move (the TV must not keep Live open)."""
        changed = False
        with self._lock:
            if not self._on() or _norm_device(device) != self.device:
                return
            now = self.clock()
            if self.refused_row == 0:
                self.refused_since = now
            self.refused_row += 1
            if self.refused_row >= HINT_AFTER and self.hint != "other_voices":
                self.hint = "other_voices"
                changed = True
            if self.state == ON and (self.refused_row >= PAUSE_AFTER or
                                     now - self.refused_since >= PAUSE_AFTER_S):
                self.state, self.pause = PAUSED, "other_voices"
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

    def note_spoke(self, device="") -> None:
        """Jarvis made the sound of a sentence (jarvis_speech.say): the quiet
        clock starts again. Any device - the say route does not always say
        which app plays it."""
        with self._lock:
            if self._on() and self.pause != "card":
                self.active_at = max(self.active_at, self.clock())

    # -- what the apps see ------------------------------------------------------------
    def status(self) -> dict:
        """On/off, the device, time left and reasons from FIXED lists."""
        with self._lock:
            now = self.clock()
            on = self._on()
            left = int(max(0, round(self.ends_at - now))) if on else None
            quiet_left = (int(max(0, round(QUIET_S - (now - self.active_at))))
                          if on and self.pause != "card" else None)
            out = {
                "state": self.state,
                "on": on,
                "device": self.device if on else None,
                "session": self.session,
                "left_s": left,
                "minutes_left": (left + 59) // 60 if left is not None else None,
                "quiet_left_s": quiet_left,
                "paused": self.pause if self.state == PAUSED else None,
                "pause_words": PAUSE_WORDS.get(self.pause) if self.state == PAUSED else None,
                "hint": self.hint if on else None,
                "hint_words": HINT_WORDS.get(self.hint) if on and self.hint else None,
                "ending_soon": bool(on and self.warned),
                "ended": self.ended_why if self.state == ENDED else None,
                "ended_words": END_WORDS.get(self.ended_why) if self.state == ENDED else None,
                "ended_device": self.ended_device if self.state == ENDED else None,
                "turns": self.turns,
                "refused_in_a_row": self.refused_row if on else 0,
                "limits": {"default_minutes": DEFAULT_MINUTES, "max_minutes": MAX_MINUTES,
                           "extend_minutes": EXTEND_DEFAULT_MIN, "quiet_s": QUIET_S,
                           "warn_s": WARN_BEFORE_S},
                "lines": dict(LINES),
            }
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
    models = doc.get("models") if isinstance(doc.get("models"), dict) else {}
    got = models.get(getattr(lane, "model", ""))
    if not isinstance(got, dict) or got.get("passed") is not True:
        return {"ready": False, "why": ("The photo test passed for a different picture model "
                                        "than the one the second card runs now. Run the photo "
                                        "test again.")}
    if not CAMERA_WIRED:
        return {"ready": False, "why": ("The photo test passed. The PC's own half of the camera "
                                        "is the next build step, so the camera stays off until "
                                        "it is built.")}
    return {"ready": True, "why": ""}


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
    | {"do": "extend", "minutes"?} | {"do": "resume"}. Start, extend and resume
    are held by both apps on a stale link (rule 4); stop always goes."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "send a JSON object"}
    do = str(body.get("do") or "").strip().lower()
    if do == "start":
        out = ENGINE.start(body.get("device"), body.get("minutes"))
        return (200 if out.get("ok") else 400), out
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
    return 400, {"ok": False, "error": "do must be start, stop, extend or resume"}


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
