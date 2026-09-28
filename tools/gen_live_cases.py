#!/usr/bin/env python3
"""Writes Jarvis Live's shared table for both apps, and checks it.

    python3 tools/gen_live_cases.py            # write both copies
    python3 tools/gen_live_cases.py --check    # compare only

Jarvis Live (the owner's decision and answers of 2026-09-28,
docs/LIVE-DESIGN.md) runs on the PC and on the phone. The session itself is
the PC's (backend/jarvis_live.py); what each app decides on its own is small
and must be the SAME on both:

  sign        what the "Live" sign says: the always-on-top badge on the PC,
              the Live screen and the ongoing notification on the phone
  listen      whether the app may record and send the next `live` clip now
              (not while a card waits - cards are decided by tapping only -
              not on a stale link, rule 4, not while App lock is locked on
              the phone, not while Jarvis is answering)
  reply       what to do with the PC's answer to a `live` clip: end Live,
              answer it, pause, or listen on - and the fixed line to say
  transition  the fixed line to say when the status changes by itself
              (two minutes left; ended because it was quiet)
  camera      whether the phone shows the camera switch: only when the PC
              says the camera is ready (the second card passed the photo
              test) - never on the desktop

The words (pause, hint, end reasons and every spoken line) come from
jarvis_live.py itself, so an app cannot word them differently. This writes
the SAME file into

    jarvis-desktop/tests/fixtures/live-cases.json
    jarvis-client/app/src/test/resources/contract/live-cases.json

(byte-identical). The desktop's tests/jarvis-live.mjs runs every case through
src/live-rules.js, the phone's LiveRulesTest through voice/LiveRules.kt, and
backend/test_live.py checks both copies are current.
"""
import json
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


# --------------------------------------------------------------------------
#   The rules, once, in Python - the reference both apps are held to
# --------------------------------------------------------------------------

def on_here(st: dict, me: str) -> bool:
    return bool(st.get("on")) and st.get("device") == me


def sign(st: dict, me: str, stale: bool = False) -> dict:
    """{"show", "title", "detail", "stop"} - what the sign says on device `me`."""
    if st.get("state") == "ended" and st.get("ended_device") == me:
        words = st.get("ended_words") or ""
        return {"show": True, "title": f"{TITLE} ended",
                "detail": f"It ended: {words}." if words else "", "stop": ""}
    if not on_here(st, me):
        return {"show": False, "title": "", "detail": "", "stop": ""}
    mins = st.get("minutes_left")
    title = TITLE + (f"{DOT}{mins} min left" if isinstance(mins, int) else "")
    if stale:
        detail = LINK_WORDS
    elif st.get("paused"):
        detail = st.get("pause_words") or ""
    elif st.get("hint"):
        detail = st.get("hint_words") or ""
    else:
        detail = ""
    return {"show": True, "title": title, "detail": detail,
            "stop": "End" if me == "phone" else "Stop"}


def listen(st: dict, me: str, *, stale: bool, card_waiting: bool, answering: bool,
           app_locked: bool = False) -> dict:
    """{"listen": bool, "why": code} - may the app record and send the next
    `live` clip now? The order is the order of the checks."""
    if not on_here(st, me):
        return {"listen": False, "why": "off"}
    if app_locked:
        return {"listen": False, "why": "locked"}
    if stale:
        return {"listen": False, "why": "link"}
    if card_waiting or st.get("paused") == "card":
        return {"listen": False, "why": "card"}
    if st.get("paused"):
        return {"listen": False, "why": "paused"}
    if answering:
        return {"listen": False, "why": "answering"}
    return {"listen": True, "why": ""}


def reply(h: dict) -> dict:
    """{"action", "say"} for the PC's answer to one `live` clip."""
    say = h.get("live_say") or ""
    live = h.get("live") or ""
    if live == "ended":
        return {"action": "end", "say": say}
    if live == "off" or h.get("available") is False:
        return {"action": "end", "say": ""}
    if live == "paused":
        return {"action": "pause", "say": say}
    text = (h.get("text") or "").strip()
    if h.get("ok") and text:
        return {"action": "answer", "say": ""}
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


def _engine(cards=0, locked=None):
    clock = _Clock()
    box = {"cards": cards, "locked": locked}
    e = L.Live(clock=clock, publish=lambda k, d: None, run_loop=False,
               cards_waiting=lambda: box["cards"], windows_locked=lambda: box["locked"])
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
    box["cards"] = 1
    e.tick()
    out["phone_card"] = _st(e)
    box["cards"] = 0
    e.tick()
    for _ in range(L.HINT_AFTER):
        e.note_refused("phone")
    out["phone_hint"] = _st(e)
    for _ in range(L.PAUSE_AFTER):
        e.note_refused("phone")
    out["phone_other_voices"] = _st(e)
    e.resume()
    c.t = e.ends_at - L.WARN_BEFORE_S + 1
    e.note_spoke()
    before = _st(e)
    out["phone_before_warn"] = before
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
    e4, _, _ = _engine()
    e4.start("phone")
    e4.stop("app_lock", device="phone")
    out["phone_app_lock"] = _st(e4)
    ready = dict(out["phone_on"])
    ready["camera"] = {"ready": True, "why": ""}
    out["phone_camera_ready"] = ready
    dready = dict(out["desktop_on"])
    dready["camera"] = {"ready": True, "why": ""}
    out["desktop_camera_ready"] = dready
    return out


def build() -> dict:
    S = statuses()
    signs, listens, replies, transitions, cameras = [], [], [], [], []
    for name, st in S.items():
        for me in ("phone", "desktop"):
            for stale in (False, True):
                signs.append({"name": f"{name}, on the {me}" + (", stale link" if stale else ""),
                              "status": name, "me": me, "stale": stale,
                              "want": sign(st, me, stale)})
            cameras.append({"name": f"{name}, on the {me}", "status": name, "me": me,
                            "want": camera_shown(st, me)})
    for name in ("off", "phone_on", "phone_card", "phone_other_voices", "phone_hint",
                 "desktop_on", "phone_quiet"):
        for me in ("phone", "desktop"):
            for stale in (False, True):
                for card in (False, True):
                    for answering in (False, True):
                        for locked in ((False, True) if me == "phone" else (False,)):
                            listens.append({
                                "name": (f"{name} on the {me}: stale={stale} card={card} "
                                         f"answering={answering} app_locked={locked}"),
                                "status": name, "me": me, "stale": stale,
                                "card_waiting": card, "answering": answering,
                                "app_locked": locked,
                                "want": listen(S[name], me, stale=stale, card_waiting=card,
                                               answering=answering, app_locked=locked)})
    heards = [
        ("the owner, words", {"ok": True, "owner": True, "available": True,
                              "text": "what's the weather", "live": "on"}),
        ("not the owner", {"ok": False, "owner": False, "available": True, "text": "",
                           "live": "on", "reason": "that did not sound like you"}),
        ("not the owner, the sign's hint", {"ok": False, "owner": False, "available": True,
                                            "text": "", "live": "on",
                                            "live_hint": "other_voices"}),
        ("too short, the short line", {"ok": False, "owner": False, "available": True,
                                       "too_short": True, "text": "", "live": "on",
                                       "live_say": L.SAY_SHORT}),
        ("too short again within the minute", {"ok": False, "owner": False, "available": True,
                                               "too_short": True, "text": "", "live": "on"}),
        ("paused for a card", {"ok": False, "owner": False, "available": True, "text": "",
                               "live": "paused", "live_pause": "card"}),
        ("paused: other voices", {"ok": False, "owner": False, "available": True, "text": "",
                                  "live": "paused", "live_pause": "other_voices"}),
        ("no session on this device", {"ok": False, "owner": False, "available": False,
                                       "text": "", "live": "off",
                                       "reason": L.NOT_ON}),
        ("an older PC (no live field), unavailable", {"ok": False, "available": False,
                                                      "text": ""}),
        ("that's all for now", {"ok": True, "owner": True, "available": True, "text": "",
                                "live": "ended", "live_ended": "bye", "live_say": L.SAY_BYE}),
        ("20 more minutes", {"ok": True, "owner": True, "available": True, "text": "",
                             "live": "on", "live_say": L.SAY_EXTENDED.format(n=20)}),
        ("owner, but no speech-to-text", {"ok": False, "owner": True, "available": False,
                                          "text": "", "live": "on"}),
        ("owner, empty words", {"ok": True, "owner": True, "available": True, "text": "  ",
                                "live": "on"}),
        ("no speech in it", {"ok": False, "owner": False, "available": True, "text": "",
                             "live": "", "reason": "no speech in that recording"}),
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
    ]
    for name, a, b, me in pairs:
        transitions.append({"name": name, "before": a, "after": b, "me": me,
                            "want": transition(S[a], S[b], me)})
    return {
        "_comment": ("Generated by tools/gen_live_cases.py. Do not edit by hand. Jarvis Live "
                     "(owner, 2026-09-28; docs/LIVE-DESIGN.md): what the Live sign says, when "
                     "an app may send the next clip (never while a card waits, never on a "
                     "stale link), what to do with the PC's reply, the fixed lines, and that "
                     "the camera switch shows only on the phone and only when the PC says it "
                     "is ready."),
        "title": TITLE,
        "dot": DOT,
        "link_words": LINK_WORDS,
        "lines": dict(L.LINES),
        "pause_words": dict(L.PAUSE_WORDS),
        "hint_words": dict(L.HINT_WORDS),
        "end_words": dict(L.END_WORDS),
        "app_end_reasons": list(L.APP_END_REASONS),
        "limits": {"default_minutes": L.DEFAULT_MINUTES, "max_minutes": L.MAX_MINUTES,
                   "extend_minutes": L.EXTEND_DEFAULT_MIN, "quiet_s": L.QUIET_S,
                   "warn_s": L.WARN_BEFORE_S},
        "statuses": S,
        "sign": signs,
        "listen": listens,
        "reply": replies,
        "transition": transitions,
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
