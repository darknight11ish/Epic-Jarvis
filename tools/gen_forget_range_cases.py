#!/usr/bin/env python3
"""Writes the "Forget a time frame" contract file for both apps, and checks it.

    python3 tools/gen_forget_range_cases.py            # write both copies
    python3 tools/gen_forget_range_cases.py --check    # compare only

What /api/memory/forget_range, /preview and /undo really answer
(backend/jarvis_forget_range.py, forget-range.patch; docs/JARVIS-API.md
section 64), in named situations - made by the real code against a real
memory store and a real, encrypted chat history in a temporary folder,
nothing written by hand:

    jarvis-desktop/tests/fixtures/forget-range-cases.json
    jarvis-client/app/src/test/resources/contract/forget-range-cases.json

(byte-identical). The desktop's Rust and JavaScript tests and the phone's
ForgetRangeTest build against it.

It also carries what both apps must say the same way: `words` (the
backend's own WORDS - the screens' buttons and sentences), the quick
choices (`presets`) and the limits. The clock and the time zone are fixed
(UTC, Monday 28 September 2026, 15:30), so the file only changes when the
backend's answer does.
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
import types
from contextlib import closing
from datetime import datetime
from pathlib import Path

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_CONF = Path(tempfile.mkdtemp(prefix="jarvis-forget-range-cases-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_CONF)
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _CONF
fw.LOG_DIR = _CONF
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: None
fw.action_tier = lambda action: "ask"
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_chat_log as CH  # noqa: E402
import jarvis_forget_range as FR  # noqa: E402
import jarvis_memory as M  # noqa: E402
import jarvis_card_words as W  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "forget-range-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "forget-range-cases.json")
COPIES = (DESKTOP, PHONE)


def _at(y, mo, d, h=12, mi=0) -> float:
    return datetime(y, mo, d, h, mi).timestamp()


NOW = _at(2026, 9, 28, 15, 30)
FR._now = lambda: NOW
KEY = bytes(range(32))


class _Emb(M.Embedder):
    name, dim, semantic = "forget-range-cases-v1", 8, False

    def embed(self, texts):
        return [[1.0 + (len(t) % (i + 2)) for i in range(self.dim)] for t in texts]


class _V:
    def __init__(self, allowed, outcome):
        self.allowed, self.outcome, self.tier, self.reason = allowed, outcome, "ask", ""


class _World:
    def __init__(self, name):
        FR._reset_for_tests()
        self.dir = _CONF / name
        self.dir.mkdir()
        self.mem = M.MemoryStore(path=self.dir / "memory.db", embedder=_Emb())
        self.t = NOW
        self.log = CH.ChatLog(self.dir / "chat-history.db", self.dir / "chat-history.json",
                              lambda: KEY, clock=lambda: self.t)
        CH.use(self.log)
        self.jobs = []

    def fact(self, text, saved, **meta):
        fid = self.mem.add(text, source="cases", meta=meta or None)
        with closing(sqlite3.connect(self.mem.path)) as c:
            c.execute("UPDATE facts SET created=? WHERE id=?", (saved, fid))
            c.commit()
        return fid

    def chat(self, cid, words, when):
        self.t = when
        self.log.record_turn({"conversation_id": cid, "device": "phone",
                              "messages": [{"role": "user", "content": words}]},
                             lane="cases", at=when)

    def get(self, route, query=""):
        code, body = FR.handle_get(route, query, now=NOW, mem=self.mem, chats=self.log)
        return {"status": code, "body": _steady(body)}

    def post(self, route, body, gate="approved", now=NOW):
        code, out = FR.handle_post(route, body, now=now, mem=self.mem, chats=self.log,
                                   gate=lambda a, d, p: _V(gate == "approved", gate),
                                   spawn=self.jobs.append)
        return {"status": code, "body": _steady(out)}

    def answer_card(self):
        real = FR._timer
        FR._timer = lambda s, fn: None
        try:
            while self.jobs:
                self.jobs.pop(0)()
        finally:
            FR._timer = real


def _steady(v):
    """The answer with what changes from run to run taken out: when a card
    was answered (`at`) and the spoken request's own id."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k == "at":
                out[k] = 0
            elif k == "id" and isinstance(x, str) and len(x) == 12:
                out[k] = "asked-id"
            else:
                out[k] = _steady(x)
        return out
    if isinstance(v, list):
        return [_steady(x) for x in v]
    return v


def _things(w):
    a = w.fact("The owner moved to Leeds in 2019", _at(2026, 9, 3))
    b = w.fact("The owner's sister likes jazz", _at(2026, 9, 10), kind="shared")
    w.mem.pin(b)
    w.chat("conv-poem-00002", "Help me write a poem", _at(2026, 8, 31, 22))
    w.chat("conv-poem-00002", "make it rhyme", _at(2026, 9, 1, 8))
    w.chat("conv-trip-00001", "Plan the trip to Rome", _at(2026, 9, 4, 9))
    return a, b


def cases() -> dict:
    out = {}
    q = "from=2026-09-01&to=2026-09-15"

    w = _World("fresh")
    out["status_fresh"] = w.get(FR.ROUTE)
    out["preview_empty"] = w.get(FR.PREVIEW, q)
    out["preview_bad_date"] = w.get(FR.PREVIEW, "from=1 Sept&to=2026-09-15")
    out["preview_bad_preset"] = w.get(FR.PREVIEW, "preset=someday")
    out["preview_preset_last_week"] = w.get(FR.PREVIEW, "preset=last_week&kinds=facts")

    w = _World("list")
    a, b = _things(w)
    out["preview"] = w.get(FR.PREVIEW, q)
    out["preview_chats_only"] = w.get(FR.PREVIEW, q + "&kinds=chats")
    out["preview_morning"] = w.get(FR.PREVIEW, "from=2026-09-28T00:00&to=2026-09-28T11:59")
    body = {"from": "2026-09-01", "to": "2026-09-15", "facts": [a, b],
            "chats": ["conv-poem-00002", "conv-trip-00001"]}
    out["forget_none_ticked"] = w.post(FR.ROUTE, {"from": "2026-09-01", "to": "2026-09-15",
                                                  "facts": [], "chats": []})
    out["forget_waiting"] = w.post(FR.ROUTE, body)
    out["status_waiting"] = w.get(FR.ROUTE)
    out["forget_second_card"] = w.post(FR.ROUTE, body)
    w.answer_card()
    out["status_undo"] = w.get(FR.ROUTE)
    out["forget_while_undo"] = w.post(FR.ROUTE, {"from": "2026-09-01", "to": "2026-09-15",
                                                 "facts": [a]}, now=NOW + 60)
    out["undo"] = w.post(FR.UNDO, {}, now=NOW + 120)
    out["undo_nothing"] = w.post(FR.UNDO, {}, now=NOW + 130)
    out["status_after_undo"] = w.get(FR.ROUTE)

    w = _World("denied")
    a, b = _things(w)
    w.post(FR.ROUTE, {"from": "2026-09-01", "to": "2026-09-15", "facts": [a]}, gate="denied")
    w.answer_card()
    out["status_denied"] = w.get(FR.ROUTE)

    w = _World("changed")
    a, b = _things(w)
    w.mem.retire(a)
    out["forget_list_changed"] = w.post(FR.ROUTE, {"from": "2026-09-01", "to": "2026-09-15",
                                                   "facts": [a]})

    w = _World("asked")
    _things(w)
    said, opens = FR.quick_answer(FR.parse_phrase("forget what you learned from 1 to 15 "
                                                  "september", NOW), NOW,
                                  mem=w.mem, chats=w.log)
    out["asked_said"] = {"said": said, "opens": opens}
    out["status_asked"] = w.get(FR.ROUTE)

    w = _World("many")
    with closing(sqlite3.connect(w.mem.path)) as c:
        for i in range(FR.MAX_ITEMS + 1):
            c.execute("INSERT INTO facts (text, source, created, valid_from) VALUES (?,?,?,?)",
                      (f"Fact number {i}", "cases", _at(2026, 9, 2) + i, _at(2026, 9, 2)))
        c.commit()
    out["preview_too_many"] = w.get(FR.PREVIEW, q)
    FR._reset_for_tests()
    return {
        "routes": {"status": FR.ROUTE, "preview": FR.PREVIEW, "undo": FR.UNDO},
        "words": FR.WORDS,
        "presets": [{"id": k, "label": v} for k, v in FR.PRESETS],
        "limits": {"max_items": FR.MAX_ITEMS, "undo_minutes": FR.UNDO_MINUTES},
        "card_title": W.title_for(FR.ACTION),
        "cases": out,
        # A PC without jarvis_forget_range.py / forget-range.patch.
        "missing": {"status": 404, "body": {"error": "not found"}},
    }


def render() -> str:
    return json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_forget_range_cases.py")
        if stale:
            return 1
        print("forget-range-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
