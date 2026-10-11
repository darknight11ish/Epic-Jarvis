#!/usr/bin/env python3
"""Writes the shared table for "Look at this" and "Watch with me", for both
apps, and checks it.

    python3 tools/gen_screen_cases.py            # write both copies
    python3 tools/gen_screen_cases.py --check    # compare only

Looking at the screen (the owner's decision of 2026-09-28, docs/SCREEN-DESIGN.md)
runs on the PC and on the phone. The session and the rules are the PC's
(backend/jarvis_screen.py); what each app decides on its own is small and must
be the SAME on both:

  words       the fixed words the sign and the notes say, the dot between
              them, how long an ended sign stays, what "more time" adds, the
              pause and end reasons (a FIXED list - never a program, a site,
              a title or a word from the screen), the marks a question
              carries, and the limits
  sign        what the sign says (the desktop's badge and strip; the phone's
              notification and Home line): the title, one line of detail and
              which buttons it offers (Stop watching, 20 more minutes)
  look_line   the one line after ONE look: the note, or the PC's own reason
              there was no look
  mark        the mark a question carries so the PC adds the held look's
              words to THAT question - only while a look is held

The words come from jarvis_screen.py itself, so an app cannot word them
differently. This writes the SAME file into

    jarvis-desktop/tests/fixtures/screen-cases.json
    jarvis-client/app/src/test/resources/contract/screen-cases.json

(byte-identical). The desktop's tests/look-rules.mjs runs every case through
src/look-rules.js, the phone's ScreenRulesTest through net/ScreenRules.kt, and
backend/test_screen.py checks both copies are current.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_screen as S  # noqa: E402
import jarvis_screen_picture as SP  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "screen-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "screen-cases.json")
COPIES = (DESKTOP, PHONE)

#: Named statuses: the same fixed keys GET /api/screen and the `screen_watch`
#: event carry (S.STATUS_KEYS).
STATUSES = {
    "off": {"state": "off", "on": False, "paused": None, "pause_words": None, "left_s": None,
            "ending_soon": False, "ended": None, "ended_words": None, "look_held": False,
            "look_left_s": None, "built": True},
    "watching": {"state": "watching", "on": True, "paused": None, "pause_words": None,
                 "left_s": 1440, "ending_soon": False, "ended": None, "ended_words": None,
                 "look_held": False, "look_left_s": None, "built": True},
    "watching_short": {"state": "watching", "on": True, "paused": None, "pause_words": None,
                       "left_s": 45, "ending_soon": True, "ended": None, "ended_words": None,
                       "look_held": False, "look_left_s": None, "built": True},
    "watching_one_min": {"state": "watching", "on": True, "paused": None, "pause_words": None,
                         "left_s": 60, "ending_soon": True, "ended": None, "ended_words": None,
                         "look_held": False, "look_left_s": None, "built": True},
    "paused_password": {"state": "paused", "on": True, "paused": "password_box",
                        "pause_words": S.PAUSE_WORDS["password_box"], "left_s": 1200,
                        "ending_soon": False, "ended": None, "ended_words": None,
                        "look_held": False, "look_left_s": None, "built": True},
    "paused_no_words": {"state": "paused", "on": True, "paused": "cannot_read",
                        "pause_words": None, "left_s": 300, "ending_soon": False,
                        "ended": None, "ended_words": None, "look_held": False,
                        "look_left_s": None, "built": True},
    "ended_time": {"state": "ended", "on": False, "paused": None, "pause_words": None,
                   "left_s": None, "ending_soon": False, "ended": "time",
                   "ended_words": S.END_WORDS["time"], "look_held": False,
                   "look_left_s": None, "built": True},
    "ended_no_words": {"state": "ended", "on": False, "paused": None, "pause_words": None,
                       "left_s": None, "ending_soon": False, "ended": None,
                       "ended_words": None, "look_held": False, "look_left_s": None,
                       "built": True},
    "look_held": {"state": "off", "on": False, "paused": None, "pause_words": None,
                  "left_s": None, "ending_soon": False, "ended": None, "ended_words": None,
                  "look_held": True, "look_left_s": 90, "built": True},
    "watching_and_held": {"state": "watching", "on": True, "paused": None, "pause_words": None,
                          "left_s": 600, "ending_soon": False, "ended": None,
                          "ended_words": None, "look_held": True, "look_left_s": 100,
                          "built": True},
}

SIGN_CASES = [
    ("off: nothing to show", "off", False, None),
    ("watching: the title and the minutes, Stop", "watching", False, None),
    ("watching, ending soon: 20 more minutes is offered", "watching_short", False, None),
    ("watching, exactly a minute left", "watching_one_min", False, None),
    ("paused on a password box: why, in the fixed words", "paused_password", False, None),
    ("paused, the PC gave no words", "paused_no_words", False, None),
    ("the link is catching up: Stop still works", "watching", True, None),
    ("paused and the link is catching up", "paused_password", True, None),
    ("just ended: why, for a few seconds", "ended_time", False, 3),
    ("ended, no reason given", "ended_no_words", False, 0),
    ("ended a while ago: gone", "ended_time", False, S.ENDED_SHOW_S),
    ("ended long ago: gone", "ended_time", False, 600),
    ("a look is held but no session: no sign (the strip says the look)", "look_held", False, None),
    ("watching with a held look: the sign is the session's", "watching_and_held", False, None),
    ("nothing at all (no status yet)", None, False, None),
]

LOOK_PAYLOADS = [
    ("a look: the note", {"ok": True, "note": "Looked at: Chrome window · words only"}),
    ("a look with no note", {"ok": True}),
    ("no look: the PC's reason",
     {"ok": False, "said": "There's a password box in front, so I'm not looking."}),
    ("no look, no reason", {"ok": False}),
    ("a wrong answer with the screen's words in it never shows them",
     {"ok": False, "part": "Snorvelquist balance owed"}),
    ("not an object", None),
]


#: Picture mode's settings block (backend/jarvis_screen_picture.py, the owner's
#: decision of 2026-09-29): what each app shows for one GET /api/screen/picture
#: answer. The payloads are shaped like the PC's real answer (only the keys the
#: apps read).
_LOOK = {"seconds": 41.0}
_MEASURED_NONE = ("Not measured yet: nobody knows how slow this is on your PC. Run the line below "
                  "before you rely on it.")
_MEASURED_SOME = ("Measured on 29 Sep 2026: about 41 seconds for one look (a made-up test picture "
                  "- a busy real screen may take longer).")
#: Read from the module, never spelled out here: this line used to hard-code
#: "minicpm-v:4.6", and when that tag turned out not to exist the generated
#: fixture and the app kept telling the owner to pull a model that 404s. The
#: tag has one home (jarvis_screen_picture.DEFAULT_MODEL) and this is a reader
#: of it (2026-10-07 bug audit, finding F1).
_LINE = (f"ollama pull '{SP.DEFAULT_MODEL}'; Push-Location -LiteralPath 'C:\\Jarvis'; "
         "py -3 .\\jarvis_screen_picture.py --measure; Pop-Location")
PICTURE_PAYLOADS = [
    ("off, never measured", {
        "enabled": False, "waiting": False,
        "line": SP.state_line(enabled=False, waiting=False, not_ready="", last_look=None),
        "measured_words": _MEASURED_NONE, "install_line": _LINE}),
    ("its card is waiting", {
        "enabled": False, "waiting": True,
        "line": SP.state_line(enabled=False, waiting=True, not_ready="", last_look=None),
        "measured_words": _MEASURED_NONE, "install_line": _LINE}),
    ("on but the model is not installed", {
        "enabled": True, "waiting": False,
        "line": SP.state_line(enabled=True, waiting=False, last_look=None,
                              not_ready=SP.WHY_WORDS["not_installed"].format(model=SP.DEFAULT_MODEL)),
        "measured_words": _MEASURED_NONE, "install_line": _LINE}),
    ("on, working, not measured yet", {
        "enabled": True, "waiting": False,
        "line": SP.state_line(enabled=True, waiting=False, not_ready="", last_look=None),
        "measured_words": _MEASURED_NONE, "install_line": _LINE}),
    ("on, measured, and a real look took 41 seconds", {
        "enabled": True, "waiting": False,
        "line": SP.state_line(enabled=True, waiting=False, not_ready="", last_look=_LOOK),
        "measured_words": _MEASURED_SOME, "install_line": _LINE}),
    ("a card is waiting while it is somehow already on", {
        "enabled": True, "waiting": True, "line": "", "measured_words": "", "install_line": ""}),
    ("off and the PC sent no words", {"enabled": False}),
    ("an answer that is not a status", {"waiting": True}),
    ("not an object", None),
]


def document() -> str:
    doc = {
        "_comment": ("Generated by tools/gen_screen_cases.py from backend/jarvis_screen.py. "
                     "Do not edit by hand. The owner's decision of 2026-09-28: Jarvis may "
                     "look at the screen, two ways. The sign says only fixed words and "
                     "minutes - never a program, a site, a title or a word from the screen."),
        "words": {
            "seen": S.SEEN,
            "dot": S.SIGN_DOT,
            "ended_show_s": S.ENDED_SHOW_S,
            "more_minutes": S.MORE_MINUTES,
            "pause_words": S.PAUSE_WORDS,
            "end_words": S.END_WORDS,
            "marks": list(S.MARKS),
            "status_keys": list(S.STATUS_KEYS),
        },
        "limits": {
            "default_minutes": S.DEFAULT_MINUTES,
            "max_minutes": S.MAX_MINUTES,
            "follow_up_s": S.FOLLOW_UP_S,
            "warn_before_s": S.WARN_BEFORE_S,
        },
        "picture": {
            "words": SP.WORDS,
            "why_words": SP.WHY_WORDS,
            "short_words": SP.SHORT_WORDS,
            "panels": [{"name": name, "payload": payload, "want": SP.panel(payload)}
                       for name, payload in PICTURE_PAYLOADS],
        },
        "statuses": STATUSES,
        "sign": [
            {"name": name, "status": key, "stale": stale, "ended_ago": ago,
             "want": S.sign(STATUSES.get(key) if key else None, stale=stale, ended_ago=ago)}
            for name, key, stale, ago in SIGN_CASES
        ],
        "look_line": [
            {"name": name, "payload": payload, "want": S.look_line(payload)}
            for name, payload in LOOK_PAYLOADS
        ],
        "mark": [
            {"name": key, "status": key, "want": S.screen_mark(STATUSES[key])}
            for key in STATUSES
        ] + [{"name": "no status", "status": None, "want": S.screen_mark(None)}],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    doc = document()
    if "--check" in sys.argv:
        bad = [p for p in COPIES if not p.exists() or p.read_text(encoding="utf-8") != doc]
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_screen_cases.py")
        if not bad:
            print("screen-cases.json: both copies match")
        return 1 if bad else 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
