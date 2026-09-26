#!/usr/bin/env python3
"""Writes the focus-session contract file for both apps, and checks it.

    python3 tools/gen_focus_cases.py            # write both copies
    python3 tools/gen_focus_cases.py --check    # compare only

What GET /api/focus and POST /api/focus/start and /act really answer
(backend/jarvis_focus.py), in named situations, made by the real engine with a
clock moved by hand and a stand-in for what is in front - nothing is written
by hand:

    jarvis-desktop/tests/fixtures/focus-cases.json
    jarvis-client/app/src/test/resources/contract/focus-cases.json

(byte-identical). The desktop's tests/focus.mjs and the phone's FocusTest
build against it.

The stand-in's program and site names are made up, and render() refuses to
write a file that holds any of them: the apps are only ever sent counts.
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-focus-cases-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP)
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.load_framework = lambda: {}
_fw.audit_log = lambda *a, **k: None
_fw.action_tier = lambda a: "auto"
sys.modules["jarvis_framework"] = _fw

import jarvis_schedule as S  # noqa: E402
import jarvis_focus as F  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "focus-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "focus-cases.json")
COPIES = (DESKTOP, PHONE)

T0 = 1_800_000_000.0
WORK = {"exe": r"C:\Apps\Qwertwork.exe", "title": "Qwertwork secret doc", "cls": "x"}
AWAY = {"exe": r"C:\Apps\chrome.exe", "title": "Zorbleflix", "cls": "x",
        "host": "https://www.zorbleflix.example/watch?v=1"}
JARVIS = {"exe": r"C:\Apps\jarvis-desktop.exe", "title": "Jarvis", "cls": "x"}
MADE_UP = ("qwertwork", "zorbleflix")


class _World:
    def __init__(self, name):
        self.t = T0
        self.front = None
        self.s = S.Scheduler(_TMP / f"{name}.db", clock=lambda: self.t, spawn=lambda fn: fn(),
                             publish=lambda k, d: None)
        none = lambda: (_ for _ in ()).throw(RuntimeError("none"))  # noqa: E731
        self.e = F.Engine(clock=lambda: self.t, probe=lambda: self.front,
                          sched=lambda: self.s, power=none, switch=none,
                          publish=lambda k, d: None, audit=lambda e, d: None,
                          ledger=_TMP / f"{name}.json", threads=False)

    def at(self, front, ticks=1):
        self.front = front
        for _ in range(ticks):
            self.t += 1
            self.e.tick()
        self.e._mail = None


def cases() -> dict:
    out = {"words": {"title": F.TITLE, "detail": F.DETAIL, "phone_note": F.PHONE_NOTE,
                     "missing": F.MISSING, "default_minutes": F.DEFAULT_MINUTES,
                     "min_minutes": F.MIN_MINUTES, "max_minutes": F.MAX_MINUTES,
                     "extend_minutes": F.EXTEND_DEFAULT_MIN}}
    w = _World("off")
    out["off_never"] = w.e.status()

    w = _World("run")
    code, started = w.e.start(30, "the essay", by="this PC")
    out["start_answer"] = {"code": code, "body": started}
    out["settling"] = w.e.status()
    w.at(JARVIS)
    w.at(WORK, ticks=2)
    w.at(WORK, ticks=120)
    out["locked_on_target"] = w.e.status()
    w.at(AWAY, ticks=30)
    out["drifting"] = w.e.status()
    code, body = w.e.act("research")
    out["research_answer"] = {"code": code, "body": body}
    out["excused"] = w.e.status()
    w.at(WORK, ticks=60)
    code, body = w.e.act("snooze", 5)
    out["snoozed"] = w.e.status()
    code, body = w.e.act("pause")
    out["pause_answer"] = {"code": code, "body": body}
    out["paused"] = w.e.status()
    w.e.act("resume")
    w.at(WORK, ticks=60)
    code, body = w.e.act("stop")
    out["stop_answer"] = {"code": code, "body": body}
    out["off_with_report"] = w.e.status()
    code, body = w.e.act("pause")
    out["act_without_session"] = {"code": code, "body": body}

    w = _World("done")
    w.e.start(5, "", by="this PC")
    w.at(WORK, ticks=2)
    w.at(WORK, ticks=300)
    w.e.finish(completed=True)
    out["done_clean"] = w.e.status()
    return out


def render() -> str:
    text = json.dumps(cases(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    low = text.lower()
    leaked = [m for m in MADE_UP if m in low]
    if leaked:
        raise SystemExit(f"refusing to write: what was in front leaked into the answers: {leaked}")
    return text


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        bad = [str(p.relative_to(ROOT)) for p in COPIES
               if not p.is_file() or p.read_text(encoding="utf-8") != text]
        if bad:
            print("out of date (run python3 tools/gen_focus_cases.py): " + ", ".join(bad))
            return 1
        print("focus cases: both copies up to date")
        return 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
