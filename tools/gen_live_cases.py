#!/usr/bin/env python3
"""Writes Jarvis Live's shared table for both apps, and checks it.

    python3 tools/gen_live_cases.py            # write both copies
    python3 tools/gen_live_cases.py --check    # compare only

Jarvis Live (the owner's decision and answers of 2026-09-28,
docs/LIVE-DESIGN.md) runs on the PC and on the phone. The session itself is
the PC's (backend/jarvis_live.py); what each app decides on its own is small
and must be the SAME on both:

  sign        what the "Live" sign says: the always-on-top badge and the
              Jarvis bar's strip on the PC, the Live screen, the Home strip
              and the ongoing notification on the phone - the title, one line
              of detail, and which buttons it offers (End Live, Mic off / Mic
              on / Listen anyway, Carry on, Resume Live, 20 more minutes,
              Show the card, Move it here). A session on the OTHER device
              shows as "Jarvis Live is on your PC/phone" with Move it here; an
              ended one shows for ENDED_SHOW_S, or with Resume Live while it
              can be resumed, counted from `ended_ago_s` - never forever
  listen      whether the app may send the next `live` clip, and whether its
              microphone may even be OPEN: closed while a card waits (cards
              are decided by tapping only), on a stale link (rule 4), while
              muted or on a call, with App lock on; open but CHECK-ONLY
              during a voice pause, so the owner's voice carries on; during
              an answer only when "Interrupt by voice" is chosen
  reply       what to do with the PC's answer to a `live` clip: end Live,
              answer, show "didn't catch that", offer to move Live here,
              stop talking, pause, "couldn't make out the words" (keep
              listening), or listen on - and the fixed line to say
  transition  the fixed line to say when the status changed by itself (two
              minutes left - never after a crisis turn; ended because it was
              quiet, the time was up, App lock, Standby; moved away)
  chips       the tap buttons after a spoken question ("Yes", "No", or the
              short options Jarvis named) - sent as the owner's typed words,
              never shown while a card waits. A mid-phrase or garbled option
              ("- the red", "One you mean", "Prefer") is never offered: no
              buttons rather than wrong ones
  side_talk   an answer that is only the side-talk marker is never spoken
              and shows as "(not for Jarvis)"; speech waits while an answer
              could still turn out to be the marker
  barge       interrupting in Live: another voice starting LOWERS Jarvis's
              volume; it stops only when the PC says it was the owner
  fold        a second thought said before Jarvis's first sound is folded
              into the same question
  camera      whether the phone shows the camera switch: only when the PC
              says the camera is ready (the second card passed the photo
              test) - never on the desktop
  interrupt   the ONE "Interrupting Jarvis" setting both apps keep for
              themselves (the owner's answer of 2026-09-28: the older
              "Interrupt Jarvis while it talks" switch and "Interrupting
              Jarvis in Live" became one) - its words, and how an older
              choice carries over

The words come from jarvis_live.py itself, so an app cannot word them
differently. This writes the SAME file into

    jarvis-desktop/tests/fixtures/live-cases.json
    jarvis-client/app/src/test/resources/contract/live-cases.json

(byte-identical). The desktop's tests/jarvis-live.mjs runs every case through
src/live-rules.js, the phone's LiveRulesTest through voice/LiveRules.kt, and
backend/test_live.py checks both copies are current.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_live as L  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "live-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "live-cases.json")
COPIES = (DESKTOP, PHONE)

DOT = " · "
TITLE = L.TITLE
#: The app's own pause: its event stream went stale (rule 4).
LINK_WORDS = "Paused: link lost - Live carries on when the link is back"
#: What the phone says in its own offline voice when the link drops in Live.
LINK_LOST_SAID = "I've lost the link to your PC."
#: ...and when it comes back and the phone listens again.
LINK_BACK_SAID = "I'm back."
#: The buttons, the same words on both apps.
END_LIVE = "End Live"
MIC_OFF = "Mic off"
MIC_ON = "Mic on"
LISTEN_ANYWAY = "Listen anyway"
MORE_TIME = "20 more minutes"
#: "20 more minutes" shows only in the last few minutes.
MORE_TIME_WITHIN_MIN = 5
#: The ONE interrupt setting, in both apps' settings, same words, this
#: device's own (no card either way: it only changes when this device
#: listens). The owner's answer of 2026-09-28 merged the older "Interrupt
#: Jarvis while it talks" switch and "Interrupting Jarvis in Live" into it.
INTERRUPT_TITLE = "Interrupting Jarvis"
INTERRUPT_VOICE, INTERRUPT_TAP, INTERRUPT_OFF = "voice", "tap", "off"
INTERRUPT = [
    {"id": INTERRUPT_VOICE, "label": "Interrupt by voice", "recommended": True,
     "detail": ("While Jarvis talks, say \"stop\" or just start talking, and it stops for "
                "your voice. The Stop talking button works too.")},
    {"id": INTERRUPT_TAP, "label": "By button only",
     "detail": ("Talking over Jarvis doesn't stop it - use the Stop talking button instead. "
                "Good for a noisy room. In Jarvis Live the microphone closes while Jarvis "
                "talks.")},
    {"id": INTERRUPT_OFF, "label": "Don't interrupt",
     "detail": ("Jarvis finishes what it is saying: talking over it doesn't stop it, and "
                "there is no Stop talking button. End Live and Stop everything still stop "
                "it.")},
]
STOP_TALKING = "Stop talking"
#: Smart Turn in Live: a sentence it thinks is unfinished may pause this long.
TURN = {"ask_after_ms": 200, "max_pause_ms": 3000}
#: How far Jarvis's volume drops while another voice is being checked.
DUCK_VOLUME = 0.3
#: At most this many option chips.
MAX_CHIPS = 3
_YES_NO_START = ("do", "does", "did", "is", "are", "was", "were", "should", "shall", "can",
                 "could", "will", "would", "have", "has", "want", "may", "am")
#: Words a question that NAMES its choices after a comma starts with ("Which
#: do you prefer, Italian or Thai?"): the part before the comma holds none.
_WH_START = ("which", "what", "who", "where", "when", "how", "why")
#: A choice of more than one word taken from the end of the question itself
#: ("Do you want the red one or the blue one?") must start like a thing
#: named - otherwise it is the middle of a phrase ("One you mean").
_DETERMINERS = ("the", "a", "an", "my", "your", "this", "that", "these", "those", "some")
#: Stripped from each end of a choice.
_TRIM = " ,;:\"'.-–—"


# --------------------------------------------------------------------------
#   The rules, once, in Python - the reference both apps are held to
# --------------------------------------------------------------------------

def on_here(st: dict, me: str) -> bool:
    return bool(st.get("on")) and st.get("device") == me


def move_words(device: str) -> str:
    """"Live is on your PC - move it here?" for the device Live is on."""
    return L.SEEN["move"].replace("{device}", L.device_words(device))


def _limit(st: dict, key: str, default: int) -> int:
    lim = st.get("limits") if isinstance(st.get("limits"), dict) else {}
    v = lim.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) else default


def sign(st: dict, me: str, stale: bool = False, thinking: bool = False,
         short: bool = False, card_shown: bool = False, ended_ago=None) -> dict:
    """What the sign says on device `me`: title, one line, and buttons.
    `card_shown`: this app shows a card raised in this session (the PC's
    pause may be a second behind). `ended_ago`: seconds since it ended, as
    this app counts them on from the PC's `ended_ago_s`."""
    none = {"show": False, "title": "", "detail": "", "stop": "", "mute": "",
            "carry_on": False, "resume": False, "more_time": False, "show_card": False,
            "move": False}
    if st.get("state") == "ended" and st.get("ended_device") == me:
        ago = ended_ago
        if not isinstance(ago, int) or isinstance(ago, bool):
            raw = st.get("ended_ago_s")
            ago = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
        resume = bool(st.get("resumable")) and ago <= _limit(st, "resume_s", L.RESUME_S)
        if not resume and ago > _limit(st, "ended_show_s", L.ENDED_SHOW_S):
            return none
        return dict(none, show=True, title=f"{TITLE} ended",
                    detail=st.get("ended_words") or "", resume=resume)
    if st.get("on") and st.get("device") in L.DEVICE_WORDS and st.get("device") != me:
        return dict(none, show=True,
                    title=L.SEEN["elsewhere"].replace("{device}",
                                                      L.device_words(st.get("device"))),
                    move=True)
    if not on_here(st, me):
        return none
    mins = st.get("minutes_left")
    title = TITLE + (f"{DOT}{mins} min left" if isinstance(mins, int) else "")
    paused = st.get("paused") or ""
    if stale:
        detail = LINK_WORDS
    elif st.get("muted"):
        detail = st.get("muted_words") or ""
    elif paused:
        detail = st.get("pause_words") or ""
    elif card_shown:
        detail = L.PAUSE_WORDS["card"]
    elif st.get("quiet_warn"):
        detail = L.SEEN["quiet_warn"]
    elif thinking:
        detail = L.SEEN["heard"]
    elif short:
        detail = L.SEEN["short"]
    elif st.get("hint"):
        detail = st.get("hint_words") or ""
    else:
        detail = ""
    if not st.get("muted"):
        mute = MIC_OFF
    elif st.get("muted_why") in ("call", "mic_in_use"):
        mute = LISTEN_ANYWAY
    else:
        mute = MIC_ON
    return dict(none, show=True, title=title, detail=detail, stop=END_LIVE, mute=mute,
                carry_on=paused in L.VOICE_PAUSES,
                more_time=isinstance(mins, int) and mins <= MORE_TIME_WITHIN_MIN,
                show_card=paused == "card" or card_shown)


def listen(st: dict, me: str, *, stale: bool, card_shown: bool, answering: bool,
           app_locked: bool = False, interrupt: str = INTERRUPT_VOICE) -> dict:
    """{"listen", "mic", "why"}: may the app send the next `live` clip, and
    may its microphone be open at all? The order is the order of the
    checks."""
    if not on_here(st, me):
        return {"listen": False, "mic": False, "why": "off"}
    if app_locked:
        return {"listen": False, "mic": False, "why": "locked"}
    if stale:
        return {"listen": False, "mic": False, "why": "link"}
    if st.get("muted"):
        return {"listen": False, "mic": False, "why": "muted"}
    if card_shown or st.get("paused") in L.CARD_PAUSES:
        return {"listen": False, "mic": False, "why": "card"}
    if st.get("paused") in L.VOICE_PAUSES:
        # Checked only, never transcribed unless it is the owner: the
        # owner's own voice carries Live on without a tap.
        return {"listen": True, "mic": True, "why": "check"}
    if answering:
        return {"listen": False, "mic": interrupt == INTERRUPT_VOICE, "why": "answering"}
    return {"listen": True, "mic": True, "why": ""}


def reply(h: dict) -> dict:
    """{"action", "say"} for the PC's answer to one clip in Live."""
    say = h.get("live_say") or ""
    live = h.get("live") or ""
    if live == "ended":
        return {"action": "end", "say": say}
    if live == "refused":
        return {"action": "refused", "say": ""}
    if live == "started":
        return {"action": "start", "say": say}
    if h.get("live_elsewhere"):
        return {"action": "move", "say": ""}
    if live == "off":
        return {"action": "end", "say": ""}
    if h.get("available") is False:
        # The owner's voice, but no words could be made of it (no speech-to-
        # text model, a failed transcription): Live carries on, and the app
        # says so - it is not the end of Live.
        return {"action": "trouble", "say": ""}
    if h.get("stop"):
        return {"action": "stop", "say": ""}
    if live == "paused":
        return {"action": "pause", "say": say}
    text = (h.get("text") or "").strip()
    if h.get("ok") and text:
        return {"action": "answer", "say": ""}
    if h.get("too_short") and h.get("live_short") == "owner":
        return {"action": "short", "say": say}
    return {"action": "listen", "say": say}


def transition(before: dict, after: dict, me: str) -> str:
    """The fixed line to say when the status changed by itself."""
    if (after.get("state") == "ended" and after.get("ended_device") == me
            and on_here(before, me)):
        return after.get("ended_say") or ""
    if on_here(before, me) and after.get("on") and after.get("device") not in (None, me):
        return L.END_SAID["other_device"]
    if on_here(after, me) and after.get("ending_soon") and not before.get("ending_soon") \
            and before.get("session") == after.get("session"):
        return L.SAY_WARN
    return ""


def _cap(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:] if s else s


def _trim(s: str) -> str:
    return s.strip(_TRIM)


def chips(answer: str, card_shown: bool = False) -> list:
    """The tap buttons after a spoken answer that ends with a question.

    With " or " in the last sentence: the choices are what comes after a
    colon or a dash, if there is one, split at the commas. A first part
    that starts like a question ("Which do you prefer", "Do you want...")
    is the question itself: after "which/what..." it holds no choice; after
    "do/should/is..." its last words are the first choice, as many as the
    next one has - and a choice of several words taken that way must start
    like a thing named ("the red one"), or there are no buttons. Every
    choice has at most 4 words, and 2 or 3 of them. Without " or ": "Yes"
    and "No" after a yes-or-no question."""
    if card_shown:
        return []
    text = " ".join(str(answer or "").split())
    if not text.endswith("?"):
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    q = parts[-1].rstrip("?").strip()
    words = q.lower().split()
    at = q.rfind(" or ")
    if at < 0:
        if words and words[0] in _YES_NO_START:
            return ["Yes", "No"]
        return []
    left, right = q[:at], _trim(q[at + 4:])
    cut, cut_len = -1, 0
    for sep in (": ", " - ", " – ", " — "):
        i = left.rfind(sep)
        if i > cut:
            cut, cut_len = i, len(sep)
    if cut >= 0:
        left = left[cut + cut_len:]
    rwords = right.split()
    if not 1 <= len(rwords) <= 4:
        # An either-or whose last choice is too long for a button: none,
        # rather than a wrong "Yes" / "No".
        return []
    segs = [_trim(s) for s in left.split(",")]
    segs = [s for s in segs if s]
    if not segs:
        return []
    lead = segs[0].split()[0].lower()
    if lead in _WH_START and len(segs) >= 2:
        options = segs[1:]
    elif lead in _WH_START or lead in _YES_NO_START:
        first = segs[0].split()
        n = len(segs[1].split()) if len(segs) >= 2 else len(rwords)
        if len(first) <= n:
            return []
        tail = first[-n:]
        if n > 1 and tail[0].lower() not in _DETERMINERS:
            return []
        if tail[0].lower() in _YES_NO_START or tail[0].lower() in _WH_START:
            return []
        options = [" ".join(tail)] + segs[1:]
    else:
        options = segs
    options = [o for o in options if o] + [right]
    if any(len(o.split()) > 4 for o in options):
        return []
    if 2 <= len(options) <= MAX_CHIPS:
        return [_cap(o) for o in options]
    return []


def could_be_side_talk(partial: str) -> bool:
    """Speech waits while the answer so far could still be the marker."""
    p = str(partial or "").strip().lower()
    return bool(p) and (L.SIDE_TALK_MARK.startswith(p) or L.is_side_talk(p))


def barge(event: str) -> str:
    """Interrupting in Live: "onset" (another voice started while Jarvis
    talks), "owner" (the PC says it was the owner, or "stop"), "not_owner",
    "timeout" (no answer in time)."""
    return {"onset": "duck", "owner": "stop"}.get(event, "restore")


def fold(previous: str, new: str, sounded: bool) -> str:
    """A second thought said before Jarvis's first sound joins the question."""
    if sounded or not str(previous or "").strip():
        return str(new or "").strip()
    return f"{str(previous).strip()} {str(new).strip()}".strip()


def camera_shown(st: dict, me: str) -> bool:
    cam = st.get("camera") if isinstance(st.get("camera"), dict) else {}
    return me == "phone" and on_here(st, me) and cam.get("ready") is True


def card_in_session(created, st: dict) -> bool:
    """Does a card the app shows hold Live? Only one raised in THIS session
    (the design's C8, the PC's own rule): a card that was already waiting
    before Live started does not. Fail closed: a card whose time cannot be
    read, or a status without `started_at`, counts."""
    started = st.get("started_at")
    if isinstance(created, bool) or not isinstance(created, (int, float)):
        return True
    if isinstance(started, bool) or not isinstance(started, (int, float)):
        return True
    return created >= started - L.CARD_SLACK_S


#: The short sound both apps play when Live ends on them (the review of
#: 2026-09-28: there was none): the "I heard you" sound's two notes the other
#: way round, a little longer. (hz, ms); made like that sound.
END_TONE = [[990, 75], [660, 90]]


def interrupt_choice(saved, old_barge_in, old_live, echo: bool) -> str:
    """The ONE interrupt setting, from what is stored. `saved`: the new
    setting, when chosen; `old_barge_in`: the older "Interrupt Jarvis while
    it talks" switch (True, False, or None never chosen); `old_live`: the
    older "Interrupting Jarvis in Live" ("voice", "tap", or None); `echo`:
    this device can cancel its own voice's echo (the phone's echo canceller;
    always true on the PC, whose switch was on by default). An old switch
    turned OFF carries over as "Don't interrupt"; Live's "tap only" as "By
    button only"."""
    if saved in (INTERRUPT_VOICE, INTERRUPT_TAP, INTERRUPT_OFF):
        return saved
    if old_barge_in is False:
        return INTERRUPT_OFF
    if old_live == INTERRUPT_TAP:
        return INTERRUPT_TAP
    if old_barge_in is True:
        return INTERRUPT_VOICE
    return INTERRUPT_VOICE if echo else INTERRUPT_TAP


# --------------------------------------------------------------------------
#   The cases - statuses made by the REAL engine
# --------------------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def _engine(cards=None):
    clock = _Clock()
    box = {"cards": cards if cards is not None else []}
    e = L.Live(clock=clock, publish=lambda k, d: None, run_loop=False,
               cards_waiting=lambda: box["cards"], windows_locked=lambda: None,
               voice_ready=lambda d: None, power_mode=lambda: "active", warm=lambda: None,
               end_on=lambda: L.END_ON_APP_LOCK)
    return e, clock, box


NO_CAMERA = {"ready": False, "why": L.CAMERA_NEEDS}


def _st(e) -> dict:
    s = e.status()
    # The camera block is the PC's to fill; the table pins it.
    s["camera"] = dict(NO_CAMERA)
    return s


def statuses() -> dict:
    out = {}
    e, c, box = _engine()
    out["off"] = _st(e)
    e.start("phone")
    out["phone_on"] = _st(e)
    c.t += 60 * 6
    e.note_spoke()
    e.tick()
    out["phone_24_min"] = _st(e)
    box["cards"] = [{"id": "c1", "created": c.t}]
    e.tick()
    out["phone_card"] = _st(e)
    box["cards"] = []
    e.tick()
    for _ in range(L.HINT_AFTER):
        e.note_refused("phone")
    out["phone_hint"] = _st(e)
    for _ in range(L.PAUSE_AFTER):
        e.note_refused("phone")
    out["phone_other_voices"] = _st(e)
    e.resume()
    for _ in range(L.PAUSE_AFTER):
        e.note_refused("phone", near_miss=True)
    out["phone_voice_trouble"] = _st(e)
    e.resume()
    e.mute(True, "phone")
    out["phone_muted"] = _st(e)
    e.mute(False, "phone")
    e.mute(True, "phone", why="call")
    out["phone_call"] = _st(e)
    e.mute(False, "phone", why="call")
    c.t += L.QUIET_S - L.QUIET_WARN_S
    e.tick()
    out["phone_quiet_warn"] = _st(e)
    e.note_spoke()
    c.t = e.ends_at - L.WARN_BEFORE_S + 1
    e.note_spoke()
    out["phone_before_warn"] = _st(e)
    e.tick()
    out["phone_ending_soon"] = _st(e)
    c.t = e.ends_at
    e.tick()
    out["phone_time_up"] = _st(e)
    e2, c2, _ = _engine()
    e2.start("phone")
    out["phone_fresh"] = _st(e2)
    c2.t += L.QUIET_S + 1
    e2.tick()
    out["phone_quiet"] = _st(e2)
    c2.t += L.RESUME_S + 1
    out["phone_quiet_long_ago"] = _st(e2)
    e3, c3, _ = _engine()
    e3.start("desktop")
    out["desktop_on"] = _st(e3)
    c3.t += 60 * 26
    e3.note_spoke()
    e3.tick()
    out["desktop_4_min"] = _st(e3)
    e3.mute(True, "desktop", why="mic_in_use")
    out["desktop_mic_in_use"] = _st(e3)
    e3.mute(False, "desktop", why="mic_in_use")
    e3.stop("owner")
    out["desktop_stopped"] = _st(e3)
    c3.t += L.ENDED_SHOW_S + 1
    out["desktop_stopped_long_ago"] = _st(e3)
    e4, _, box4 = _engine(cards=lambda_raise())
    e4.start("desktop")
    out["desktop_cards_unknown"] = _st(e4)
    e5, _, _ = _engine()
    e5.start("phone")
    e5.stop("app_lock", device="phone")
    out["phone_app_lock"] = _st(e5)
    # A crisis turn five minutes before the end: more time, no warning.
    e6, c6, _ = _engine()
    e6.start("phone")
    c6.t += 25 * 60
    e6.note_spoke()
    e6.tick()
    out["phone_before_crisis"] = _st(e6)
    e6.note_crisis()
    c6.t = e6.ends_at - L.WARN_BEFORE_S + 1
    e6.note_spoke()
    e6.tick()
    out["phone_crisis_near_end"] = _st(e6)
    ready = dict(out["phone_on"])
    ready["camera"] = {"ready": True, "why": ""}
    out["phone_camera_ready"] = ready
    dready = dict(out["desktop_on"])
    dready["camera"] = {"ready": True, "why": ""}
    out["desktop_camera_ready"] = dready
    return out


class _Raises:
    def __iter__(self):
        raise RuntimeError("the queue cannot be read")


def lambda_raise():
    return _Raises()


def build() -> dict:
    S = statuses()
    signs, listens, replies, transitions, cameras = [], [], [], [], []
    for name, st in S.items():
        for me in ("phone", "desktop"):
            for stale in (False, True):
                signs.append({"name": f"{name}, on the {me}" + (", stale link" if stale else ""),
                              "status": name, "me": me, "stale": stale, "thinking": False,
                              "short": False, "card_shown": False, "ended_ago": None,
                              "want": sign(st, me, stale)})
            cameras.append({"name": f"{name}, on the {me}", "status": name, "me": me,
                            "want": camera_shown(st, me)})
    for name in ("phone_on", "phone_hint", "phone_quiet_warn", "phone_card"):
        for thinking, short in ((True, False), (False, True), (True, True)):
            signs.append({"name": f"{name}, on the phone, thinking={thinking} short={short}",
                          "status": name, "me": "phone", "stale": False, "thinking": thinking,
                          "short": short, "card_shown": False, "ended_ago": None,
                          "want": sign(S[name], "phone", False, thinking, short)})
    # A card on screen in the app, before the PC's own pause catches up.
    for name in ("phone_on", "desktop_on", "phone_muted", "phone_other_voices"):
        me = "desktop" if name.startswith("desktop") else "phone"
        signs.append({"name": f"{name}, on the {me}, a card on screen", "status": name,
                      "me": me, "stale": False, "thinking": True, "short": False,
                      "card_shown": True, "ended_ago": None,
                      "want": sign(S[name], me, False, True, False, card_shown=True)})
    # Ended: counted on by the app from the PC's ended_ago_s.
    for name, me, ago in (("phone_quiet", "phone", 0), ("phone_quiet", "phone", 599),
                          ("phone_quiet", "phone", 601), ("desktop_stopped", "desktop", 15),
                          ("desktop_stopped", "desktop", 16), ("phone_app_lock", "phone", 3),
                          ("phone_time_up", "phone", 30)):
        signs.append({"name": f"{name}, on the {me}, ended {ago} s ago (counted by the app)",
                      "status": name, "me": me, "stale": False, "thinking": False,
                      "short": False, "card_shown": False, "ended_ago": ago,
                      "want": sign(S[name], me, ended_ago=ago)})
    for name in ("off", "phone_on", "phone_card", "phone_other_voices", "phone_voice_trouble",
                 "phone_hint", "phone_muted", "phone_call", "desktop_on", "desktop_cards_unknown",
                 "phone_quiet"):
        for me in ("phone", "desktop"):
            for stale in (False, True):
                for card in (False, True):
                    for answering in (False, True):
                        for locked in ((False, True) if me == "phone" else (False,)):
                            for interrupt in (INTERRUPT_VOICE, INTERRUPT_TAP, INTERRUPT_OFF):
                                listens.append({
                                    "name": (f"{name} on the {me}: stale={stale} card={card} "
                                             f"answering={answering} app_locked={locked} "
                                             f"interrupt={interrupt}"),
                                    "status": name, "me": me, "stale": stale,
                                    "card_shown": card, "answering": answering,
                                    "app_locked": locked, "interrupt": interrupt,
                                    "want": listen(S[name], me, stale=stale, card_shown=card,
                                                   answering=answering, app_locked=locked,
                                                   interrupt=interrupt)})
    heards = [
        ("the owner, words", {"ok": True, "owner": True, "available": True,
                              "text": "what's the weather", "live": "on"}),
        ("not the owner", {"ok": False, "owner": False, "available": True, "text": "",
                           "live": "on", "reason": "that did not sound like you"}),
        ("not the owner, the sign's hint", {"ok": False, "owner": False, "available": True,
                                            "text": "", "live": "on",
                                            "live_hint": "other_voices"}),
        ("too short, probably the owner, the spoken line",
         {"ok": False, "owner": False, "available": True, "too_short": True, "text": "",
          "live": "on", "live_short": "owner", "live_say": L.SAY_SHORT}),
        ("too short, probably the owner, within the minute (seen only)",
         {"ok": False, "owner": False, "available": True, "too_short": True, "text": "",
          "live": "on", "live_short": "owner"}),
        ("too short, someone else (nothing said, nothing shown)",
         {"ok": False, "owner": False, "available": True, "too_short": True, "text": "",
          "live": "on", "live_short": "other"}),
        ("paused for a card", {"ok": False, "owner": False, "available": True, "text": "",
                               "live": "paused", "live_pause": "card"}),
        ("paused: other voices", {"ok": False, "owner": False, "available": True, "text": "",
                                  "live": "paused", "live_pause": "other_voices"}),
        ("muted", {"ok": False, "owner": False, "available": True, "text": "",
                   "live": "paused", "live_pause": "muted"}),
        ("no session on this device", {"ok": False, "owner": False, "available": False,
                                       "text": "", "live": "off", "reason": L.NOT_ON}),
        ("an older PC (no live field), unavailable: keep listening, say so",
         {"ok": False, "available": False, "text": ""}),
        ("that's all for now", {"ok": True, "owner": True, "available": True, "text": "",
                                "live": "ended", "live_ended": "bye", "live_say": L.SAY_BYE}),
        ("give me twenty more minutes", {"ok": True, "owner": True, "available": True,
                                         "text": "", "live": "on",
                                         "live_say": L.SAY_EXTENDED.format(n=20)}),
        ("owner, but no speech-to-text: Live carries on (bug 2 of the review)",
         {"ok": False, "owner": True, "available": False, "text": "", "live": "on"}),
        ("owner, but the words could not be made out, while paused",
         {"ok": False, "owner": True, "available": False, "text": "", "live": "paused",
          "live_pause": "other_voices"}),
        ("owner, empty words", {"ok": True, "owner": True, "available": True, "text": "  ",
                                "live": "on"}),
        ("no speech in it", {"ok": False, "owner": False, "available": True, "text": "",
                             "live": "", "reason": "no speech in that recording"}),
        ("stop", {"ok": False, "owner": False, "available": True, "text": "", "stop": True,
                  "live": "on"}),
        ("let's talk: started", {"ok": True, "owner": True, "available": True, "text": "",
                                 "live": "started", "live_say": L.SAY_STARTED}),
        ("let's talk: refused, no voice print", {"ok": True, "owner": True, "available": True,
                                                 "text": "", "live": "refused",
                                                 "reason": L.needs_voice_words("phone")}),
        ("hey Jarvis here while Live is on the phone", {"ok": True, "owner": True,
                                                        "available": True, "text": "",
                                                        "other_device": True,
                                                        "live_elsewhere": "phone"}),
    ]
    for name, h in heards:
        replies.append({"name": name, "heard": h, "want": reply(h)})
    pairs = [
        ("two minutes left", "phone_before_warn", "phone_ending_soon", "phone"),
        ("two minutes left, the other device", "phone_before_warn", "phone_ending_soon", "desktop"),
        ("already warned", "phone_ending_soon", "phone_ending_soon", "phone"),
        ("ended: quiet", "phone_fresh", "phone_quiet", "phone"),
        ("ended: quiet, the other device", "phone_fresh", "phone_quiet", "desktop"),
        ("ended: the time was up", "phone_ending_soon", "phone_time_up", "phone"),
        ("ended: App lock", "phone_fresh", "phone_app_lock", "phone"),
        ("ended by the owner: nothing to say (a tone only)", "desktop_on", "desktop_stopped",
         "desktop"),
        ("moved to the other device: said on the one it left", "desktop_on", "phone_on",
         "desktop"),
        ("moved here: nothing to say", "desktop_on", "phone_on", "phone"),
        ("nothing changed", "phone_on", "phone_on", "phone"),
        ("a card came", "phone_24_min", "phone_card", "phone"),
        ("the quiet warning is seen, never said", "phone_24_min", "phone_quiet_warn", "phone"),
        ("after a crisis turn: no 'minutes left' warning", "phone_before_crisis",
         "phone_crisis_near_end", "phone"),
    ]
    for name, a, b, me in pairs:
        transitions.append({"name": name, "before": a, "after": b, "me": me,
                            "want": transition(S[a], S[b], me)})
    chip_answers = [
        ("a yes-or-no question", "I found two timers. Do you want me to cancel both?", False),
        ("options named", "Sure. Do you want the red one or the blue one?", False),
        ("three options", "Which one: red, green or blue?", False),
        ("numbers", "Should I set it for 7 or 8?", False),
        ("two words", "Tea or coffee?", False),
        ("now or later", "Would you like me to read it now, or later?", False),
        ("a list after a yes-or-no start", "Would you like tea, coffee or juice?", False),
        ("an open question", "What would you like me to call it?", False),
        ("not a question", "It's 14 degrees and sunny.", False),
        ("a question in the middle only", "Is it cold? Not really, 14 degrees.", False),
        ("a long either-or: no chips", "Is it the one about the garden or the one about work "
                                     "meetings next week?", False),
        ("a card waits: never", "Do you want me to send it?", True),
        ("empty", "", False),
        # Garbled before the review of 2026-09-28 (both reports list them).
        ("a dash before the list (was '- the red')",
         "Which one - the red, the blue or the green one?", False),
        ("a mid-phrase first choice: none (was 'One you mean')",
         "Is that the one you mean, or the other one?", False),
        ("the question before a comma holds no choice (was 'Prefer')",
         "Which do you prefer, Italian or Thai?", False),
        ("'which one' before a comma (was 'Which one')", "Which one, the red or the blue?",
         False),
        ("two actions: none (was 'I read it out')",
         "Shall I read it out, or keep it on screen?", False),
        ("'or is there more': none (was 'Is that everything')",
         "Is that everything, or is there more?", False),
        ("a dash, and the choices after it", "Pick one — pasta, curry or salad?", False),
    ]
    chip_cases = [{"name": n, "answer": a, "card_shown": c, "want": chips(a, c)}
                  for n, a, c in chip_answers]
    side = [
        ("the marker", "[not for me]"), ("the marker, capitals and a full stop", "[Not for me]."),
        ("the marker, spaces", "  [not for me]  "), ("an ordinary answer", "It's four o'clock."),
        ("the marker inside words", "I think [not for me] means nothing."),
        ("a bracket, then words", "[laughs] That's funny."),
    ]
    side_cases = [{"name": n, "answer": a, "side_talk": L.is_side_talk(a)} for n, a in side]
    partials = ["[", "[not", "[not for", "[not for me", "[not for me]", "[nob", "It", "", "  [n"]
    partial_cases = [{"partial": p, "hold": could_be_side_talk(p)} for p in partials]
    barges = [{"event": ev, "want": barge(ev)}
              for ev in ("onset", "owner", "not_owner", "timeout")]
    folds = [
        {"previous": "set a timer", "new": "for ten minutes", "sounded": False,
         "want": fold("set a timer", "for ten minutes", False)},
        {"previous": "set a timer", "new": "what's the weather", "sounded": True,
         "want": fold("set a timer", "what's the weather", True)},
        {"previous": "", "new": "hello there", "sounded": False,
         "want": fold("", "hello there", False)},
    ]
    moves = [{"device": d, "want": move_words(d)} for d in ("desktop", "phone")]
    started = S["phone_on"]["started_at"]
    card_cases = [
        {"name": n, "created": created, "status": status,
         "want": card_in_session(created, S[status])}
        for n, created, status in (
            ("raised after Live started", started + 30, "phone_on"),
            ("raised a second before (clocks)", started - 1, "phone_on"),
            ("waiting from long before Live", started - 3600, "phone_on"),
            ("no readable time: counts", None, "phone_on"),
            ("a time that is words: counts", "yesterday", "phone_on"),
            ("Live not on (no started_at): counts", started - 3600, "off"),
        )]
    interrupt_cases = []
    for saved in (None, INTERRUPT_VOICE, INTERRUPT_TAP, INTERRUPT_OFF, "nonsense"):
        for old_barge in (None, True, False):
            for old_live in (None, INTERRUPT_VOICE, INTERRUPT_TAP):
                for echo in (True, False):
                    interrupt_cases.append({
                        "saved": saved, "old_barge_in": old_barge, "old_live": old_live,
                        "echo": echo,
                        "want": interrupt_choice(saved, old_barge, old_live, echo)})
    return {
        "_comment": ("Generated by tools/gen_live_cases.py. Do not edit by hand. Jarvis Live "
                     "(owner, 2026-09-28; docs/LIVE-DESIGN.md): what the Live sign says, when "
                     "an app may send the next clip and keep its microphone open (never "
                     "while a card waits, never on a stale link, never while muted), what to "
                     "do with the PC's reply, the fixed lines, the tap chips (never on a "
                     "card, never garbled), side talk (never spoken), interrupting (duck, "
                     "then stop only for the owner), the one Interrupting Jarvis setting, "
                     "and that the camera switch shows only on the phone and only when the "
                     "PC says it is ready."),
        "title": TITLE,
        "dot": DOT,
        "link_words": LINK_WORDS,
        "link_lost_said": LINK_LOST_SAID,
        "link_back_said": LINK_BACK_SAID,
        "buttons": {"end_live": END_LIVE, "mic_off": MIC_OFF, "mic_on": MIC_ON,
                    "listen_anyway": LISTEN_ANYWAY, "more_time": MORE_TIME,
                    "stop_talking": STOP_TALKING},
        "more_time_within_min": MORE_TIME_WITHIN_MIN,
        "lines": dict(L.LINES),
        "seen": dict(L.SEEN),
        "device_words": dict(L.DEVICE_WORDS),
        "pause_words": dict(L.PAUSE_WORDS),
        "hint_words": dict(L.HINT_WORDS),
        "mute_words": dict(L.MUTE_WORDS),
        "end_words": dict(L.END_WORDS),
        "end_said": dict(L.END_SAID),
        "needs_voice": L.NEEDS_VOICE,
        "needs_voice_where": dict(L.NEEDS_VOICE_WHERE),
        "app_end_reasons": list(L.APP_END_REASONS),
        "voice_pauses": list(L.VOICE_PAUSES),
        "card_pauses": list(L.CARD_PAUSES),
        "side_talk_mark": L.SIDE_TALK_MARK,
        "interrupt_title": INTERRUPT_TITLE,
        "interrupt": INTERRUPT,
        "stop_talking": STOP_TALKING,
        "turn": dict(TURN),
        "duck_volume": DUCK_VOLUME,
        "max_chips": MAX_CHIPS,
        "limits": {"default_minutes": L.DEFAULT_MINUTES, "max_minutes": L.MAX_MINUTES,
                   "extend_minutes": L.EXTEND_DEFAULT_MIN, "quiet_s": L.QUIET_S,
                   "quiet_warn_s": L.QUIET_WARN_S, "warn_s": L.WARN_BEFORE_S,
                   "resume_s": L.RESUME_S, "ended_show_s": L.ENDED_SHOW_S,
                   "crisis_more_s": L.CRISIS_MORE_S},
        "statuses": S,
        "sign": signs,
        "listen": listens,
        "reply": replies,
        "transition": transitions,
        "chips": chip_cases,
        "side_talk": side_cases,
        "side_talk_partial": partial_cases,
        "barge": barges,
        "fold": folds,
        "move": moves,
        "card_in_session": card_cases,
        "card_slack_s": L.CARD_SLACK_S,
        "end_tone": END_TONE,
        "camera": cameras,
        "interrupt_choice": interrupt_cases,
    }


def document() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    doc = document()
    if "--check" in sys.argv:
        bad = [p for p in COPIES
               if not p.exists() or p.read_text(encoding="utf-8") != doc]
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_live_cases.py")
        if not bad:
            print("live-cases.json: both copies match")
        return 1 if bad else 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
