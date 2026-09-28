#!/usr/bin/env python3
"""Writes "Widgets you describe"'s golden files, and checks them.

    python3 tools/gen_widget_cases.py            # write both files
    python3 tools/gen_widget_cases.py --check    # compare only

jarvis-desktop/tests/fixtures/widget-cases.json and the phone's
byte-identical copy, contract/widget-cases.json (docs/JARVIS-API.md
section 86).

WHAT IS IN THEM
- `actions`: the five safe buttons, their wire names and fixed words - the
  PC's (jarvis_widgets.ACTIONS). Both apps' own lists must equal it (the
  phone's is TileAction, the Quick Settings tiles' list).
- `private_sources`: the sources whose words are hidden under App lock and
  "Hide memory lists and chat history".
- `cases`: what GET /api/widgets/show answers - real answers made by
  jarvis_widgets.show() with made-up readings, and HOSTILE answers written
  by hand (a script type, an "approve" button, a huge list, a missing
  private flag, control characters, a fraction of 7) - each with the
  `view` BOTH apps must draw from it and the `hidden` view they draw while
  private words are hidden. `app_view()` and `hide()` below are the rule,
  written once here; the desktop's widget-board.js and the phone's
  net/JarvisWidgets.kt must give exactly these.

WHY THE APPS CHECK AGAIN: the PC already sends only checked blocks. The apps
still draw nothing that is not on their own menu - an unknown block type or
button is left out, a source they do not know is treated as private - so a
PC answer that is wrong, or from a newer PC, can never put a button on the
home screen that the app does not already know is safe.

The readings are MADE UP. The clock is fixed and the time zone is UTC.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_widgets as W  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "widget-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "widget-cases.json")

NOW = 1790589600.0     # Monday 28 September 2026, 10:00 UTC

# --------------------------------------------------------------------------
#   The rule both apps follow, written once
# --------------------------------------------------------------------------

MAX_BLOCKS = W.MAX_BLOCKS
MAX_ITEMS = W.MAX_LIST
PRIVATE = sorted(k for k, s in W.SOURCES.items() if s.private)
HIDDEN = W.PRIVATE_HIDDEN
_WS = re.compile(r"[ \t\n\r\f\v]+")


def text(v, cap: int) -> str:
    """Text as both apps draw it: a string only; control (Cc) and format
    (Cf) characters removed; ASCII white space collapsed; at most `cap`
    characters (code points)."""
    if not isinstance(v, str):
        return ""
    import unicodedata
    s = "".join(c for c in v if unicodedata.category(c) not in ("Cc", "Cf")
                or c in " \t\n\r\f\v")
    s = _WS.sub(" ", s).strip(" ")
    return s[:cap].rstrip(" ")


def _int(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


def app_view(ans):
    """The blocks an app draws from one show answer, or None."""
    if not isinstance(ans, dict) or ans.get("ok") is not True:
        return None
    blocks = ans.get("blocks") if isinstance(ans.get("blocks"), list) else []
    out = []
    for b in blocks[:MAX_BLOCKS]:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "title":
            s = text(b.get("text"), W.MAX_TEXT)
            if s:
                out.append({"type": "title", "text": s})
        elif t == "button":
            a = b.get("action")
            if isinstance(a, str) and a in W.ACTIONS:
                out.append({"type": "button", "action": a, "label": W.ACTIONS[a]})
        elif t in ("number", "list", "progress"):
            src = b.get("source") if isinstance(b.get("source"), str) else ""
            private = b.get("private") is not False or src not in W.SOURCES or src in PRIVATE
            v = {"type": t, "label": text(b.get("label"), W.MAX_LABEL),
                 "note": text(b.get("note"), 120), "private": private, "hidden": False}
            if t == "number":
                v["value"] = text(b.get("value"), 20)
            elif t == "list":
                items = b.get("items") if isinstance(b.get("items"), list) else []
                items = [i for i in items if isinstance(i, dict)]
                v["items"] = [{"text": text(i.get("text"), 120), "when": text(i.get("when"), 40)}
                              for i in items[:MAX_ITEMS]]
                v["more"] = _int(b.get("more")) + max(0, len(items) - MAX_ITEMS)
                v["empty"] = text(b.get("empty"), 60)
            else:
                f = b.get("fraction")
                f = float(f) if isinstance(f, (int, float)) and not isinstance(f, bool) else 0.0
                v["fraction"] = min(1.0, max(0.0, f))
                v["value"] = text(b.get("value"), 60)
            out.append(v)
    return {"name": text(ans.get("name"), W.MAX_NAME), "blocks": out}


def hide(view):
    """The same view while App lock or "Hide memory lists and chat history"
    hides private words: a private block keeps its label, loses its words."""
    if view is None:
        return None
    out = []
    for b in view["blocks"]:
        b = dict(b)
        if b.get("private"):
            b["hidden"] = True
            b["note"] = HIDDEN
            if b["type"] == "number":
                b["value"] = ""
            elif b["type"] == "list":
                b["items"], b["more"] = [], 0
            elif b["type"] == "progress":
                b["fraction"], b["value"] = 0.0, ""
        out.append(b)
    return {"name": view["name"], "blocks": out}


# --------------------------------------------------------------------------
#   The cases
# --------------------------------------------------------------------------

class _Sched:
    def listed(self):
        return [
            {"kind": "reminder", "state": "active", "due": NOW + 7200, "text": "Call mum",
             "when": "12:00"},
            {"kind": "alarm", "state": "active", "due": NOW + 600, "text": "", "when": "10:10"},
            {"kind": "timer", "state": "active", "due": NOW + 272, "left": 272.0, "text": "Pasta"},
            {"kind": "today", "state": "active", "due": NOW + 3600, "text": "Gym bag",
             "today": "showing"},
        ]

    def todos(self):
        return [{"text": "Milk", "list": ""}, {"text": "Tax form", "list": ""}]


def _readers():
    return W.Readers(
        sched=_Sched, now=lambda: NOW,
        briefing=lambda: {"made": NOW - 3600, "sections": [
            {"key": "email", "state": "ok", "summary": "4 unread emails.", "items": []}]},
        disk=lambda: (412 * 1024 ** 3, 931 * 1024 ** 3),
        focus=lambda: {"on": True, "minutes": 25, "left_s": 600},
        playing=lambda: {"ok": True, "said": "Playing: “Song” by Band."})


def _real(spec) -> dict:
    w = W.validate(spec)
    w = {"id": "w0123456789", **w}
    return {"ok": True, "id": w["id"], "name": w["name"], "at": NOW,
            "blocks": [W.fill(b, _readers()) for b in w["blocks"]]}


def cases() -> dict:
    out = {}
    out["morning"] = _real({"name": "Morning", "blocks": [
        {"type": "title", "text": "Good morning"},
        {"type": "list", "source": "reminders", "max": 3, "label": "Next up"},
        {"type": "number", "source": "email_count"},
        {"type": "progress", "source": "disk_free"},
        {"type": "button", "action": "timer"},
        {"type": "button", "action": "stop_everything"}]})
    out["focus_and_music"] = _real({"name": "Desk", "blocks": [
        {"type": "progress", "source": "focus"},
        {"type": "list", "source": "now_playing", "max": 1},
        {"type": "list", "source": "todo", "max": 1},
        {"type": "number", "source": "todo_count"},
        {"type": "button", "action": "focus"},
        {"type": "button", "action": "pc_play_pause"},
        {"type": "button", "action": "brief_me"}]})
    out["hostile"] = {"ok": True, "id": "w0123456789", "name": "Evil‮​ name" + "x" * 80,
                      "at": NOW, "blocks": [
        {"type": "script", "text": "alert(1)"},
        {"type": "html", "html": "<img src=x onerror=alert(1)>"},
        {"type": "button", "action": "approve", "label": "Approve"},
        {"type": "button", "action": "deny_all"},
        {"type": "button", "action": "timer", "label": "Approve everything"},
        {"type": "title", "text": "\u0007Hi\tthere\n\n  you⁦"},
        {"type": "list", "source": "reminders", "label": "L", "private": False,
         "items": [{"text": f"item {i}", "when": "now"} for i in range(40)] + ["junk", 7],
         "more": -3, "empty": "none"},
        {"type": "number", "source": "brand_new_source", "label": "New", "value": "12"},
        {"type": "progress", "source": "disk_free", "private": False, "fraction": 7,
         "value": "x"},
        {"type": "number", "source": "todo_count", "value": 5, "label": ["no"]},
        "not a block", None, 3]}
    out["too_many_blocks"] = {"ok": True, "name": "Many", "blocks":
                              [{"type": "title", "text": f"T{i}"} for i in range(20)]}
    out["not_ok"] = {"ok": False, "error": W.NO_SUCH}
    out["odd_values"] = {"ok": True, "name": 42, "blocks": [
        {"type": "progress", "source": "disk_free", "private": False, "fraction": 7, "value": "x"},
        {"type": "progress", "source": "disk_free", "private": False, "fraction": -1},
        {"type": "progress", "source": "disk_free", "private": False, "fraction": True},
        {"type": "number", "source": "todo_count", "private": False, "value": 5, "label": ["no"]},
        {"type": "list", "source": "todo", "items": "not a list", "more": True}]}
    out["missing_private_flag"] = {"ok": True, "name": "M", "blocks": [
        {"type": "progress", "source": "focus", "fraction": 0.5, "value": "5:00 left"}]}
    return {name: {"answer": ans, "view": app_view(ans), "hidden": hide(app_view(ans))}
            for name, ans in out.items()}


def render() -> str:
    data = {
        "comment": "Made by tools/gen_widget_cases.py - do not edit by hand. "
                   "docs/JARVIS-API.md section 86.",
        "actions": [{"id": k, "label": v} for k, v in W.ACTIONS.items()],
        "private_sources": PRIVATE,
        "hidden_words": HIDDEN,
        "limits": {"blocks": MAX_BLOCKS, "items": MAX_ITEMS, "name": W.MAX_NAME,
                   "text": W.MAX_TEXT, "label": W.MAX_LABEL},
        "cases": cases(),
    }
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    want = render()
    if "--check" in sys.argv:
        bad = [str(p) for p in (DESKTOP, PHONE)
               if not p.exists() or p.read_text(encoding="utf-8") != want]
        if bad:
            print("out of date (run tools/gen_widget_cases.py): " + ", ".join(bad))
            return 1
        print("widget cases up to date")
        return 0
    for p in (DESKTOP, PHONE):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(want, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
