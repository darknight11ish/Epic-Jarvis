#!/usr/bin/env python3
"""Writes Jarvis Live's shared table for both apps, and checks it.

    python3 tools/gen_live_cases.py            # write both copies
    python3 tools/gen_live_cases.py --check    # compare only

Jarvis Live (the owner's decision and answers of 2026-09-28,
docs/LIVE-DESIGN.md) runs on the PC and on the phone. The session itself is
the PC's (backend/jarvis_live.py); what each app decides on its own is small
and must be the SAME on both:

  sign        what the "Live" sign says: the always-on-top badge on the PC,
              the Live screen and the ongoing notification on the phone -
              the title, one line of detail, and which buttons it offers
              (Stop/End, Mute/Unmute, Carry on, Resume Live)
  listen      whether the app may send the next `live` clip, and whether its
              microphone may even be OPEN: closed while a card waits (cards
              are decided by tapping only), on a stale link (rule 4), while
              muted or on a call, with App lock on; open but CHECK-ONLY
              during a voice pause, so the owner's voice carries on; during
              an answer only when "Interrupt by voice" is chosen
  reply       what to do with the PC's answer to a `live` clip: end Live,
              answer, show "didn't catch that", offer to move Live here,
              stop talking, pause, or listen on - and the fixed line to say
  transition  the fixed line to say when the status changed by itself (two
              minutes left; ended because it was quiet)
  chips       the tap buttons after a spoken question ("Yes", "No", or the
              short options Jarvis named) - sent as the owner's typed words,
              never shown while a card waits
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
LINK_WORDS = "Paused: link lost"
#: What the phone says in its own offline voice when the link drops in Live.
LINK_LOST_SAID = "I've lost the link to your PC."
#: The per-app setting, in both apps' settings, same words. Default "voice".
INTERRUPT = [
    {"id": "voice", "label": "Interrupt by voice", "recommended": True,
     "detail": "In Jarvis Live, start talking while Jarvis talks and it stops for your voice."},
    {"id": "tap", "label": "Interrupt by tap only",
     "detail": ("In Jarvis Live, talking over Jarvis does not stop it - tap Stop talking "
                "instead. Good for a noisy room.")},
]
INTERRUPT_TITLE = "Interrupting Jarvis in Live"
STOP_TALKING = "Stop talking"
#: Smart Turn in Live: a sentence it thinks is unfinished may pause this long.
TURN = {"ask_after_ms": 200, "max_pause_ms": 3000}
#: How far Jarvis's volume drops while another voice is being checked.
DUCK_VOLUME = 0.3
#: At most this many option chips.
MAX_CHIPS = 3
_YES_NO_START = ("do", "does", "did", "is", "are", "was", "were", "should", "shall", "can",
                 "could", "will", "would", "have", "has", "want", "may", "am")


# --------------------------------------------------------------------------
#   The rules, once, in Python - the reference both apps are held to
# --------------------------------------------------------------------------

def on_here(st: dict, me: str) -> bool:
    return bool(st.get("on")) and st.get("device") == me


def sign(st: dict, me: str, stale: bool = False, thinking: bool = False,
         short: bool = False) -> dict:
    """What the sign says on device `me`: title, one line, and buttons."""
    none = {"show": False, "title": "", "detail": "", "stop": "", "mute": "",
            "carry_on": False, "resume": False}
    if st.get("state") == "ended" and st.get("ended_device") == me:
        words = st.get("ended_words") or ""
        return dict(none, show=True, title=f"{TITLE} ended",
                    detail=f"It ended: {words}." if words else "",
                    resume=bool(st.get("resumable")))
    if not on_here(st, me):
        return none
    mins = st.get("minutes_left")
    title = TITLE + (f"{DOT}{mins} min left" if isinstance(mins, int) else "")
    if stale:
        detail = LINK_WORDS
    elif st.get("muted"):
        detail = st.get("muted_words") or ""
    elif st.get("paused"):
        detail = st.get("pause_words") or ""
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
    return dict(none, show=True, title=title, detail=detail,
                stop="End" if me == "phone" else "Stop",
                mute="Unmute" if st.get("muted") else "Mute",
                carry_on=st.get("paused") in L.VOICE_PAUSES)


def listen(st: dict, me: str, *, stale: bool, card_shown: bool, answering: bool,
           app_locked: bool = False, interrupt: str = "voice") -> dict:
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
        return {"listen": False, "mic": interrupt == "voice", "why": "answering"}
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
    if live == "off" or h.get("available") is False:
        return {"action": "end", "say": ""}
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
    if (after.get("state") == "ended" and after.get("ended") == "quiet"
            and after.get("ended_device") == me and on_here(before, me)):
        return L.SAY_QUIET
    if on_here(after, me) and after.get("ending_soon") and not before.get("ending_soon") \
            and before.get("session") == after.get("session"):
        return L.SAY_WARN
    return ""


def _cap(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:] if s else s


def chips(answer: str, card_shown: bool = False) -> list:
    """The tap buttons after a spoken answer that ends with a question."""
    if card_shown:
        return []
    text = " ".join(str(answer or "").split())
    if not text.endswith("?"):
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    q = parts[-1].rstrip("?").strip()
    words = q.lower().split()
    if " or " in q:
        left, right = q.rsplit(" or ", 1)
        right = right.strip(" ,")
        rwords = right.split()
        if 1 <= len(rwords) <= 4:
            n = len(rwords)
            segs = [s.strip() for s in left.split(",")]
            first = segs[0].split()
            options = [" ".join(first[-n:])] if len(first) >= n else []
            options += [s for s in segs[1:] if s and len(s.split()) <= 4]
            options = [o for o in options if o] + [right]
            if 2 <= len(options) <= MAX_CHIPS:
                return [_cap(o) for o in options]
        # An either-or whose options are too long for a button: no chips
        # rather than a wrong "Yes" / "No".
        return []
    if words and words[0] in _YES_NO_START:
        return ["Yes", "No"]
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
               voice_ready=lambda d: None, power_mode=lambda: "active", warm=lambda: None)
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
    e2, c2, _ = _engine()
    e2.start("phone")
    out["phone_fresh"] = _st(e2)
    c2.t += L.QUIET_S + 1
    e2.tick()
    out["phone_quiet"] = _st(e2)
    e3, c3, _ = _engine()
    e3.start("desktop")
    out["desktop_on"] = _st(e3)
    e3.stop("owner")
    out["desktop_stopped"] = _st(e3)
    e4, _, box4 = _engine(cards=lambda_raise())
    e4.start("desktop")
    out["desktop_cards_unknown"] = _st(e4)
    e5, _, _ = _engine()
    e5.start("phone")
    e5.stop("app_lock", device="phone")
    out["phone_app_lock"] = _st(e5)
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
                              "short": False, "want": sign(st, me, stale)})
            cameras.append({"name": f"{name}, on the {me}", "status": name, "me": me,
                            "want": camera_shown(st, me)})
    for name in ("phone_on", "phone_hint", "phone_quiet_warn", "phone_card"):
        for thinking, short in ((True, False), (False, True), (True, True)):
            signs.append({"name": f"{name}, on the phone, thinking={thinking} short={short}",
                          "status": name, "me": "phone", "stale": False, "thinking": thinking,
                          "short": short, "want": sign(S[name], "phone", False, thinking, short)})
    for name in ("off", "phone_on", "phone_card", "phone_other_voices", "phone_voice_trouble",
                 "phone_hint", "phone_muted", "phone_call", "desktop_on", "desktop_cards_unknown",
                 "phone_quiet"):
        for me in ("phone", "desktop"):
            for stale in (False, True):
                for card in (False, True):
                    for answering in (False, True):
                        for locked in ((False, True) if me == "phone" else (False,)):
                            for interrupt in ("voice", "tap"):
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
        ("an older PC (no live field), unavailable", {"ok": False, "available": False,
                                                      "text": ""}),
        ("that's all for now", {"ok": True, "owner": True, "available": True, "text": "",
                                "live": "ended", "live_ended": "bye", "live_say": L.SAY_BYE}),
        ("give me twenty more minutes", {"ok": True, "owner": True, "available": True,
                                         "text": "", "live": "on",
                                         "live_say": L.SAY_EXTENDED.format(n=20)}),
        ("owner, but no speech-to-text", {"ok": False, "owner": True, "available": False,
                                          "text": "", "live": "on"}),
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
                                                 "reason": L.NEEDS_VOICE}),
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
        ("ended by the owner: nothing to say", "desktop_on", "desktop_stopped", "desktop"),
        ("nothing changed", "phone_on", "phone_on", "phone"),
        ("a card came", "phone_24_min", "phone_card", "phone"),
        ("the quiet warning is seen, never said", "phone_24_min", "phone_quiet_warn", "phone"),
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
        ("an open question", "What would you like me to call it?", False),
        ("not a question", "It's 14 degrees and sunny.", False),
        ("a question in the middle only", "Is it cold? Not really, 14 degrees.", False),
        ("a long either-or: no chips", "Is it the one about the garden or the one about work "
                                     "meetings next week?", False),
        ("a card waits: never", "Do you want me to send it?", True),
        ("empty", "", False),
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
    return {
        "_comment": ("Generated by tools/gen_live_cases.py. Do not edit by hand. Jarvis Live "
                     "(owner, 2026-09-28; docs/LIVE-DESIGN.md): what the Live sign says, when "
                     "an app may send the next clip and keep its microphone open (never "
                     "while a card waits, never on a stale link, never while muted), what to "
                     "do with the PC's reply, the fixed lines, the tap chips (never on a "
                     "card), side talk (never spoken), interrupting (duck, then stop only for "
                     "the owner), and that the camera switch shows only on the phone and "
                     "only when the PC says it is ready."),
        "title": TITLE,
        "dot": DOT,
        "link_words": LINK_WORDS,
        "link_lost_said": LINK_LOST_SAID,
        "lines": dict(L.LINES),
        "seen": dict(L.SEEN),
        "pause_words": dict(L.PAUSE_WORDS),
        "hint_words": dict(L.HINT_WORDS),
        "mute_words": dict(L.MUTE_WORDS),
        "end_words": dict(L.END_WORDS),
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
                   "resume_s": L.RESUME_S},
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
        "camera": cameras,
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
