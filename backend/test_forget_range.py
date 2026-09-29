"""test_forget_range.py - "Forget a time frame": a checked list, ONE card,
ten minutes to undo.

    python3 backend/test_forget_range.py

The owner's decision of 2026-09-28 (CLAUDE.md): the owner may ask, by voice
or typing, to forget what Jarvis learned or said in a time frame. Nothing is
removed at once: both apps show the exact facts and chats, each ticked; ONE
approval card listing every item is decided by tapping only; approved, the
facts are forgotten (retired, as Forget does) and the chats deleted, with
10 minutes to Undo. backend/jarvis_forget_range.py does the work,
forget-range.patch installs its routes (docs/JARVIS-API.md section 64).

What is proved here, against a real memory store and a real, encrypted
chat history in a temp folder, with the clock and the time zone fixed:

  * time frames: the choices, typed dates, times of day, what is refused;
  * the list: facts by when they were SAVED (never their "true from"
    date), only facts still in use, chats that overlap the days - and the
    ones that spill outside them marked; more than 200 is counts only;
  * the card: tier "ask" only, every fact word for word and every chat's
    title on it, nothing changed before a person's yes, one at a time, a
    list that changed since it was read refused;
  * approved: each fact retired with Forget's own "forgotten" mark, each
    chat gone from the file; denied or timed out: nothing changed;
  * Undo: everything back as it was (a lease's end date too), once; a fact
    erased meanwhile stays erased; a chat continued meanwhile is joined
    back together; after ten minutes (or a restart) there is nothing to
    undo, and the held chats are dropped;
  * by voice or typing: jarvis_quick fills in the list and opens Brain,
    NEVER removes anything, asks about a date it cannot be sure of, and a
    spoken "yes" approves nothing;
  * the routes, token and origin like every other, and the words both apps
    share (tools/gen_forget_range_cases.py) are current.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import types
from contextlib import closing
from datetime import datetime
from pathlib import Path

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_forget_range.py", "rebuilt/jarvis_memory.py", "jarvis_chat_log.py",
                "jarvis_quick.py", "jarvis_card_words.py", "jarvis_asks_first.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-forget-range-"))
_AUDIT = []
_TIERS = {"memory_forget_range": "ask"}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: _AUDIT.append((event, detail))
fw.action_tier = lambda action: _TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

_NET = []
_real_connect = socket.socket.connect


def _no_connect(self, *a, **k):
    _NET.append(a)
    raise OSError("test_forget_range.py: no network")


socket.socket.connect = _no_connect

try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M
import jarvis_chat_log as CH  # noqa: E402
import jarvis_forget_range as FR  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []
KEY = bytes(range(32))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def at(y, mo, d, h=12, mi=0) -> float:
    return datetime(y, mo, d, h, mi).timestamp()


#: Monday 28 September 2026, 15:30, in UTC.
NOW = at(2026, 9, 28, 15, 30)
FR._now = lambda: NOW


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, outcome, tier="ask", reason=""):
        self.allowed, self.outcome, self.tier, self.reason = allowed, outcome, tier, reason


class Gate:
    """The approval gate, answering as told; it remembers what it was asked."""

    def __init__(self, answer="approved"):
        self.answer = answer
        self.asked = []

    def __call__(self, action, detail, prompt):
        self.asked.append((action, detail, prompt))
        if self.answer == "approved":
            return Verdict(True, "approved")
        if self.answer == "auto":
            return Verdict(True, "auto", tier="auto")
        return Verdict(False, self.answer)


class Held:
    """spawn() that keeps the job, so the test decides when the card is answered."""

    def __init__(self):
        self.jobs = []

    def __call__(self, fn):
        self.jobs.append(fn)

    def run(self):
        while self.jobs:
            self.jobs.pop(0)()


class Timers:
    def __init__(self):
        self.set = []

    def __call__(self, seconds, fn):
        self.set.append((seconds, fn))


class Emb(M.Embedder):
    name, dim, semantic = "forget-range-test-v1", 8, False

    def embed(self, texts):
        return [[1.0 + ((hash(t) >> i) & 1) for i in range(self.dim)] for t in texts]


_N = [0]


class World:
    """One memory store and one chat history, in their own folder."""

    def __init__(self):
        _N[0] += 1
        FR._reset_for_tests()
        self.dir = _TMP / f"w{_N[0]}"
        self.dir.mkdir()
        self.mem = M.MemoryStore(path=self.dir / "memory.db", embedder=Emb())
        self.clock = Clock()
        self.log = CH.ChatLog(self.dir / "chat-history.db", self.dir / "chat-history.json",
                              lambda: KEY, clock=self.clock)
        CH.use(self.log)
        self.gate = Gate()
        self.spawn = Held()
        self.timers = Timers()

    def fact(self, text, saved, **meta) -> int:
        fid = self.mem.add(text, source="test", meta=meta or None)
        with closing(sqlite3.connect(self.mem.path)) as c:
            c.execute("UPDATE facts SET created=? WHERE id=?", (saved, fid))
            c.commit()
        return fid

    def chat(self, cid, words, when, answer=None):
        self.clock.t = when
        turn = {"answer": answer, "finish_reason": "stop"} if answer else None
        out = self.log.record_turn({"conversation_id": cid, "device": "desktop",
                                    "messages": [{"role": "user", "content": words}]},
                                   lane="test", turn=turn, at=when)
        assert out.get("recorded"), out
        return cid

    def preview(self, frm, to, kinds=FR.KINDS):
        return FR.preview(FR.frame_of(frm, to, NOW), kinds, mem=self.mem, chats=self.log)

    def ask(self, body, now=NOW):
        return FR.request(body, now=now, mem=self.mem, chats=self.log, gate=self.gate,
                          spawn=self.spawn)

    def approve(self):
        """Answer the waiting card as the gate says, then run apply with a
        timer this test holds."""
        real = FR._timer
        FR._timer = self.timers
        try:
            self.spawn.run()
        finally:
            FR._timer = real

    def row(self, fid):
        return self.mem.get(fid)


# --------------------------------------------------------------------------
#   Time frames
# --------------------------------------------------------------------------


def t_frames():
    f = FR.frame_of("2026-09-01", "2026-09-15", NOW)
    check("two dates: from the start of the first to the end of the last",
          f.start == at(2026, 9, 1, 0) and f.end == at(2026, 9, 16, 0), (f.start, f.end))
    check("... written back the way the apps send it", (f.frm, f.to) == ("2026-09-01", "2026-09-15"))
    check("... and said in words", f.said == "1 to 15 September 2026", f.said)
    check("one day", FR.frame_of("2026-09-28", "2026-09-28", NOW).said == "28 September 2026")
    check("across months", FR.frame_of("2026-08-30", "2026-09-05", NOW).said
          == "30 August to 5 September 2026")
    check("across years", FR.frame_of("2025-12-28", "2026-01-03", NOW).said
          == "28 December 2025 to 3 January 2026")
    t = FR.frame_of("2026-09-28T00:00", "2026-09-28T11:59", NOW)
    check("a time of day: to the end of that minute",
          t.start == at(2026, 9, 28, 0) and t.end == at(2026, 9, 28, 12), (t.start, t.end))
    check("... said with the clock", t.said == "28 September 2026, midnight to 11:59 am", t.said)
    for frm, to, why in (("2026-09-15", "2026-09-01", "after"), ("1 Sept", "2026-09-02", "like"),
                         ("2026-02-30", "2026-03-01", "like"), ("2026-10-01", "2026-10-02", "not happened"),
                         (None, "2026-09-02", "like"), ("1999-01-01", "1999-01-02", "like")):
        try:
            FR.frame_of(frm, to, NOW)
            check(f"refused: {frm!r} to {to!r}", False)
        except ValueError as exc:
            check(f"refused: {frm!r} to {to!r}, in words", why in str(exc), str(exc))
    got = {k: (FR.preset_frame(k, NOW).frm, FR.preset_frame(k, NOW).to) for k, _ in FR.PRESETS}
    check("the choices, in the PC's own time (Monday 28 September)", got == {
        "today": ("2026-09-28", "2026-09-28"), "yesterday": ("2026-09-27", "2026-09-27"),
        "this_week": ("2026-09-28", "2026-09-28"), "last_week": ("2026-09-21", "2026-09-27"),
        "last_7_days": ("2026-09-22", "2026-09-28"), "this_month": ("2026-09-01", "2026-09-28"),
        "last_month": ("2026-08-01", "2026-08-31")}, got)
    check("kinds: both by default, one, or refused",
          FR.kinds_of(None) == ("facts", "chats") and FR.kinds_of("chats") == ("chats",)
          and FR.kinds_of(["chats", "facts"]) == ("facts", "chats"))
    try:
        FR.kinds_of("emails")
        check("kinds: anything else refused", False)
    except ValueError:
        check("kinds: anything else refused", True)


# --------------------------------------------------------------------------
#   The list
# --------------------------------------------------------------------------


def t_the_list():
    w = World()
    a = w.fact("The owner moved to Leeds in 2019", at(2026, 9, 3))
    b = w.fact("The owner's sister likes jazz", at(2026, 9, 10), kind="shared")
    w.fact("The owner drinks tea", at(2026, 8, 20))             # before
    w.fact("The owner runs on Sundays", at(2026, 9, 20))        # after
    gone = w.fact("The owner has a red bike", at(2026, 9, 5))
    w.mem.retire(gone)                                          # already forgotten
    w.mem.pin(b)
    w.chat("conv-inside-0001", "Plan the trip to Rome", at(2026, 9, 4, 9))
    w.chat("conv-inside-0001", "and book a hotel", at(2026, 9, 4, 10))
    w.chat("conv-spills-0002", "Help me write a poem", at(2026, 8, 31, 22))
    w.chat("conv-spills-0002", "make it rhyme", at(2026, 9, 1, 8))
    w.chat("conv-outside-003", "What is the weather", at(2026, 9, 20))
    p = w.preview("2026-09-01", "2026-09-15")
    ids = [f["id"] for f in p["facts"]]
    check("facts saved in those days, oldest first; not before, not after, not already forgotten",
          ids == [a, b], ids)
    check("by when they were SAVED - a 2019 'true from' date does not move it",
          p["facts"][0]["text"] == "The owner moved to Leeds in 2019")
    check("each fact labelled with the day it was saved", p["facts"][0]["label"] == "Saved 3 September",
          p["facts"][0]["label"])
    check("a pinned fact and a Between us fact say so",
          p["facts"][1]["pinned"] is True and p["facts"][1]["between_us"] is True
          and p["facts"][0]["pinned"] is False)
    cids = [c["id"] for c in p["chats"]]
    check("chats that overlap the days, oldest first", cids == ["conv-spills-0002", "conv-inside-0001"],
          cids)
    spills = {c["id"]: c["spills"] for c in p["chats"]}
    check("the one that started the day before is marked: the whole chat goes",
          spills == {"conv-spills-0002": True, "conv-inside-0001": False}, spills)
    ticks = {c["id"]: c["ticked"] for c in p["chats"]}
    check("a chat with messages from outside the days starts UNticked (finding 10, "
          "2026-09-28); one wholly inside starts ticked",
          ticks == {"conv-spills-0002": False, "conv-inside-0001": True}, ticks)
    check("its warning says to tick it only if the whole chat should go",
          "Tick it only if the whole chat should go" in FR.WORDS["spills"])
    first = p["chats"][1]
    check("a chat's title, days and messages", first["title"] == "Plan the trip to Rome"
          and first["label"] == "4 September · 2 messages" and first["turns"] == 2, first)
    check("the counts, and the summary in words",
          p["counts"] == {"facts": 2, "chats": 2}
          and p["said"] == "2 facts and 2 chats from 1 to 15 September 2026.", p)
    only = w.preview("2026-09-01", "2026-09-15", ("chats",))
    check("chats only: no facts read", only["facts"] == [] and "facts" not in only["counts"]
          and only["said"] == "2 chats from 1 to 15 September 2026.", only)
    empty = w.preview("2026-07-01", "2026-07-02")
    check("nothing then: empty, and said so", empty["empty"] is True
          and empty["said"] == "0 facts and 0 chats from 1 to 2 July 2026.", empty["said"])
    m = w.preview("2026-09-01", "2026-09-15")
    check("nothing was changed by reading the list",
          w.row(a)["valid_to"] is None and len(w.log.list()["conversations"]) == 3)


def t_too_many():
    w = World()
    with closing(sqlite3.connect(w.mem.path)) as c:
        for i in range(FR.MAX_ITEMS + 1):
            c.execute("INSERT INTO facts (text, source, created, valid_from) VALUES (?,?,?,?)",
                      (f"The owner said thing number {i}", "test", at(2026, 9, 2) + i,
                       at(2026, 9, 2)))
        c.commit()
    p = w.preview("2026-09-01", "2026-09-15")
    check(f"more than {FR.MAX_ITEMS}: counts only, no list", p["too_many"] is True
          and p["facts"] == [] and p["chats"] == [] and p["counts"]["facts"] == FR.MAX_ITEMS + 1)
    check("... and asks for fewer days", p["said"].endswith("more than 200 at once. Choose fewer days."),
          p["said"])
    out = w.ask({"from": "2026-09-01", "to": "2026-09-15",
                 "facts": list(range(1, FR.MAX_ITEMS + 2))})
    check(f"a request for more than {FR.MAX_ITEMS} is refused", out[0] == 400, out)


# --------------------------------------------------------------------------
#   The card
# --------------------------------------------------------------------------


def _body(w, **kw):
    p = w.preview("2026-09-01", "2026-09-15")
    body = {"from": "2026-09-01", "to": "2026-09-15", "facts": [f["id"] for f in p["facts"]],
            "chats": [c["id"] for c in p["chats"]]}
    body.update(kw)
    return body


def _world_with_things():
    w = World()
    w.a = w.fact("The owner moved to Leeds", at(2026, 9, 3))
    w.b = w.fact("The owner's lease ends in December", at(2026, 9, 6))
    with closing(sqlite3.connect(w.mem.path)) as c:
        c.execute("UPDATE facts SET valid_to=? WHERE id=?", (at(2026, 12, 31), w.b))
        c.commit()
    w.keep = w.fact("The owner likes pears", at(2026, 9, 8))
    w.chat("conv-trip-00001", "Plan the trip to Rome", at(2026, 9, 4, 9), answer="Sure - when?")
    w.chat("conv-poem-00002", "Help me write a poem", at(2026, 9, 7, 9))
    return w


def t_the_card():
    w = _world_with_things()
    for bad, why in (({"from": "2026-09-01", "to": "2026-09-15"}, "Tick at least one"),
                     ({"from": "2026-09-01", "to": "2026-09-15", "facts": ["1"]}, "whole-number"),
                     ({"from": "2026-09-01", "to": "2026-09-15", "chats": ["x"]}, "conversation ids"),
                     ({"from": "2026-09-01", "to": "2026-09-15", "facts": [w.a, w.a]}, "twice"),
                     ({"from": "bad", "to": "2026-09-15", "facts": [w.a]}, "like 2026-09-01"),
                     ("not an object", "JSON object")):
        code, out = w.ask(bad)
        check(f"refused, in words: {why}", code == 400 and why in out.get("error", ""), out)
    _TIERS["memory_forget_range"] = "auto"
    try:
        code, out = w.ask(_body(w))
        check("a tier other than 'ask' refuses - a settings line is never the owner's yes",
              code == 503 and "must be 'ask'" in out["error"] and not w.spawn.jobs, out)
    finally:
        _TIERS["memory_forget_range"] = "ask"
    body = _body(w, facts=[w.a, w.b])          # the owner unticked the pears
    code, out = w.ask(body)
    check("202: one card is raised", code == 202 and out["waiting"] is True
          and out["counts"] == {"facts": 2, "chats": 2}, out)
    check("... and nothing changed yet", w.row(w.a)["valid_to"] is None
          and len(w.log.list()["conversations"]) == 2)
    check("status: waiting", FR.status(NOW)["waiting"] is True)
    code2, out2 = w.ask(body)
    check("a second request while the card waits: 409", code2 == 409, out2)
    w.gate.answer = "approved"
    FR._timer, real = w.timers, FR._timer
    try:
        w.spawn.run()
    finally:
        FR._timer = real
    action, detail, prompt = w.gate.asked[0]
    check("ONE card, action memory_forget_range", len(w.gate.asked) == 1
          and action == "memory_forget_range", action)
    for words in ("The owner moved to Leeds", "The owner's lease ends in December",
                  "Plan the trip to Rome", "Help me write a poem", "1 to 15 September 2026",
                  "saved 3 September", "4 September · 2 messages", "Undo",
                  "Saying yes out loud does not approve it"):
        check(f"the card says {words!r}", words in prompt, prompt)
    check("the card says what stays (the second chat audit): unticked facts and older backups",
          "Facts you did not tick stay. Copies in older backups stay until they age out." in prompt, prompt)
    check("the unticked fact is not on the card", "pears" not in prompt)
    check("the card's detail says it stays on this PC", detail["leaves_this_pc"] is False
          and detail["text"] == prompt and detail["facts"] == 2 and detail["chats"] == 2)


def t_support_records_ask_first():
    """The owner, 2026-09-28: "Forget a time frame" asks before removing a
    customer-support chat's record. It is listed, NOT ticked to start with,
    with a line saying so; ticked, the card names it."""
    w = _world_with_things()
    w.clock.t = at(2026, 9, 5, 10)
    got = w.log.record_support("sup-groupon-001", "Groupon: refund",
                               [{"provenance": "support_company", "text": "We can refund",
                                 "at": at(2026, 9, 5, 10)}])
    check("a support record is kept", got.get("recorded"), got)
    out = w.preview("2026-09-01", "2026-09-15")
    items = {c["id"]: c for c in out["chats"]}
    sup = items.get("sup-groupon-001") or {}
    check("the support record is listed, with its kind", sup.get("kind") == "support", sup)
    check("...and starts UNticked; an ordinary chat starts ticked",
          sup.get("ticked") is False and items["conv-trip-00001"]["ticked"] is True, items)
    check("the words say it is kept unless ticked",
          "kept unless you tick it" in FR.WORDS["support"])
    w.gate.answer = "approved"
    code, _ = w.ask(_body(w, facts=[], chats=["sup-groupon-001"]))
    check("ticked by the owner: one card", code == 202)
    FR._timer, real = w.timers, FR._timer
    try:
        w.spawn.run()
    finally:
        FR._timer = real
    prompt = w.gate.asked[-1][2]
    check("the card names it a customer-support record",
          "customer-support chat's record" in prompt, prompt)


def t_denied_changes_nothing():
    for answer in ("denied", "timed_out"):
        w = _world_with_things()
        w.gate.answer = answer
        w.ask(_body(w))
        w.approve()
        st = FR.status(NOW)
        check(f"{answer}: nothing forgotten, nothing deleted",
              w.row(w.a)["valid_to"] is None and len(w.log.list()["conversations"]) == 2)
        check(f"{answer}: said, and no Undo", st["last"]["outcome"] == answer
              and st["undo"] is None and st["waiting"] is False, st)
    w = _world_with_things()
    w.gate.answer = "auto"
    w.ask(_body(w))
    w.approve()
    check("a gate that answered without a person: refused, nothing changed",
          FR.status(NOW)["last"]["outcome"] == "refused" and w.row(w.a)["valid_to"] is None)


def t_the_list_changed():
    w = _world_with_things()
    body = _body(w)
    w.mem.retire(w.a)
    code, out = w.ask(body)
    check("a fact forgotten since the list was read: 409, read it again",
          code == 409 and out.get("changed") is True, out)
    w = _world_with_things()
    body = _body(w)
    w.log.delete("conv-poem-00002")
    code, out = w.ask(body)
    check("a chat deleted since: 409", code == 409, out)
    w = _world_with_things()
    other = w.fact("The owner has a cat", at(2026, 9, 25))
    code, out = w.ask(_body(w, facts=[w.a, other]))
    check("a fact from other days: 409, never forgotten through this card", code == 409
          and w.row(other)["valid_to"] is None, out)


def t_approved_then_undo():
    w = _world_with_things()
    before_b = w.row(w.b)["valid_to"]
    files_before = sorted(p.name for p in w.dir.iterdir())
    w.ask(_body(w, facts=[w.a, w.b]))
    w.approve()
    a = w.row(w.a)
    meta = json.loads(a["meta"] or "{}")
    check("approved: the fact is forgotten, as Forget does - retired, not erased",
          a["retired_at"] is not None and a["erased_at"] is None
          and a["text"] == "The owner moved to Leeds")
    check("... with Forget's own 'forgotten' mark (what keeps it from coming back)",
          bool(meta.get("forgotten_at")))
    try:
        import jarvis_past
        check("jarvis_past reads it as forgotten", jarvis_past.forgotten(a) is True)
    except ImportError:
        pass
    check("the lease that ends in December is forgotten too", w.row(w.b)["retired_at"] is not None)
    check("the unticked fact is untouched", w.row(w.keep)["valid_to"] is None)
    check("the chats are gone from the history file", w.log.list()["conversations"] == []
          and w.log.get("conv-trip-00001") is None)
    files_after = sorted(p.name for p in w.dir.iterdir()
                         if not p.name.endswith(("-wal", "-shm", "-journal")))
    check("... and no new file was written to hold them: the Undo is in memory only",
          files_after == [n for n in files_before
                          if not n.endswith(("-wal", "-shm", "-journal"))], (files_before, files_after))
    with closing(sqlite3.connect(w.dir / "chat-history.db")) as c:
        left = c.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
    check("... and not a row of them is left in the history file", left == 0, left)
    st = FR.status(NOW)
    check("status: Undo for ten minutes", st["undo"] is not None and st["undo"]["facts"] == 2
          and st["undo"]["chats"] == 2 and st["undo"]["seconds_left"] == 600
          and st["undo"]["said"] == "Forgot 2 facts and deleted 2 chats from 1 to 15 September 2026.",
          st["undo"])
    check("a timer was set for ten minutes", w.timers.set and w.timers.set[0][0] == 600)
    code, out = w.ask(_body(w, facts=[w.keep], chats=None), now=NOW + 60)
    check("while an Undo is open, another time frame waits", code == 409
          and "undo" in out["error"].lower(), out)
    code, out = FR.undo(now=NOW + 120, mem=w.mem, chats=w.log)
    check("Undo: 200, everything put back", code == 200
          and out["restored"] == {"facts": 2, "chats": 2}, out)
    a2, b2 = w.row(w.a), w.row(w.b)
    check("the fact is in use again, without the forgotten mark",
          a2["valid_to"] is None and a2["retired_at"] is None
          and not json.loads(a2["meta"] or "{}").get("forgotten_at"))
    check("the lease's own end date came back, not 'still true forever'", b2["valid_to"] == before_b)
    check("recall has them again", {f["id"] for f in w.mem.current_facts()} >= {w.a, w.b})
    conv = w.log.get("conv-trip-00001")
    check("the chat is back, word for word, answer included",
          conv and [t["text"] for t in conv["turns"]] == ["Plan the trip to Rome", "Sure - when?"]
          and conv["title"] == "Plan the trip to Rome", conv)
    code, out = FR.undo(now=NOW + 130, mem=w.mem, chats=w.log)
    check("Undo twice: nothing left to undo", code == 409, out)
    check("... and the status says it was put back", FR.status(NOW + 130)["last"]["outcome"] == "undone")


def t_undo_edge_cases():
    w = _world_with_things()
    w.ask(_body(w, facts=[w.a, w.b]))
    w.approve()
    w.mem.erase(w.a)
    w.chat("conv-trip-00001", "and a hotel near the station", NOW + 30)
    code, out = FR.undo(now=NOW + 60, mem=w.mem, chats=w.log)
    check("a fact erased during the ten minutes stays erased", w.row(w.a)["erased_at"] is not None
          and w.row(w.a)["retired_at"] is not None, w.row(w.a))
    check("... and the answer says one stayed", out["not_restored"]["facts"] == 1
          and "1 fact stayed forgotten" in out["message"], out)
    conv = w.log.get("conv-trip-00001")
    words = [t["text"] for t in conv["turns"]]
    check("a chat the owner went on with is joined back together, old messages first",
          words == ["Plan the trip to Rome", "Sure - when?", "and a hotel near the station"], words)
    check("... under its first title", conv["title"] == "Plan the trip to Rome")

    w = _world_with_things()
    w.ask(_body(w))
    w.approve()
    import copy
    w.log.put_back(copy.deepcopy(FR._STATE["undo"]["chats"]))   # e.g. a backup restored meanwhile
    w.chat("conv-trip-00001", "and a table for two", NOW + 40)
    FR.undo(now=NOW + 60, mem=w.mem, chats=w.log)
    words = [t["text"] for t in w.log.get("conv-trip-00001")["turns"]]
    check("a chat already put back by other means is not doubled by Undo; newer words still join",
          words == ["Plan the trip to Rome", "Sure - when?", "and a table for two"], words)

    w = _world_with_things()
    w.ask(_body(w))
    w.approve()
    st = FR.status(NOW + 601)
    check("after ten minutes: no Undo, and the status says why", st["undo"] is None
          and st["last"]["outcome"] == "kept", st)
    code, out = FR.undo(now=NOW + 602, mem=w.mem, chats=w.log)
    check("... Undo answers 409", code == 409, out)
    check("... the chats stay deleted, the facts forgotten", w.log.get("conv-trip-00001") is None
          and w.row(w.a)["retired_at"] is not None)

    w = _world_with_things()
    w.ask(_body(w))
    w.approve()
    seconds, fn = w.timers.set[0]
    fn()
    check("the ten-minute timer drops what was held", FR.status(NOW)["undo"] is None
          and FR._STATE["undo"] is None)

    w = _world_with_things()
    w.ask(_body(w))
    w.approve()
    FR._reset_for_tests()               # what a restart leaves: nothing in memory
    code, out = FR.undo(now=NOW + 30, mem=w.mem, chats=w.log)
    check("after a restart there is nothing to undo - it was never on disk", code == 409
          and w.log.get("conv-trip-00001") is None)


# --------------------------------------------------------------------------
#   By voice or typing
# --------------------------------------------------------------------------


class _Sched:
    def mark_command(self, text):
        pass

    def forget_set(self, conversation):
        pass

    def note_set(self, *a, **k):
        pass


def t_phrases():
    cases = {
        "forget what you learned last week": ("2026-09-21", "2026-09-27", ("facts",)),
        "delete my chats from 1 to 15 September": ("2026-09-01", "2026-09-15", ("chats",)),
        "Jarvis, forget everything from yesterday": ("2026-09-27", "2026-09-27", ("facts", "chats")),
        "forget what I said this morning": ("2026-09-28T00:00", "2026-09-28T11:59", ("facts", "chats")),
        "forget what I told you on Tuesday": ("2026-09-22", "2026-09-22", ("facts", "chats")),
        "delete my conversations from September 1 to 15": ("2026-09-01", "2026-09-15", ("chats",)),
        "forget what you learned and delete my chats from last week":
            ("2026-09-21", "2026-09-27", ("facts", "chats")),
        "delete my chats between 30 August and 5 September": ("2026-08-30", "2026-09-05", ("chats",)),
        "delete my chats from the last 3 days": ("2026-09-26", "2026-09-28", ("chats",)),
        "forget everything since Friday": ("2026-09-25", "2026-09-28", ("facts", "chats")),
        "delete my chats from 28 December to 3 January": ("2025-12-28", "2026-01-03", ("chats",)),
        "forget what I said on the twenty first of September": ("2026-09-21", "2026-09-21",
                                                                ("facts", "chats")),
    }
    for s, (frm, to, kinds) in cases.items():
        got = FR.parse_phrase(Q.normalise(s), NOW)
        ok = bool(got) and "frame" in got and (got["frame"].frm, got["frame"].to, got["kinds"]) \
            == (frm, to, kinds)
        check(f"understood: {s!r}", ok, got and ("frame" in got and (got["frame"].frm, got["frame"].to,
                                                                      got["kinds"]) or got))
    for s, bit in (("forget what you learned on Monday", "Today is Monday"),
                   ("forget everything from 3/9", "two ways"),
                   ("forget what you learned in October", "not happened yet this year"),
                   ("forget what you learned on the 3rd", "Which month"),
                   ("forget what you learned last night", "yesterday evening"),
                   ("forget what you learned on 31 February", "no 31 February")):
        got = FR.parse_phrase(Q.normalise(s), NOW)
        check(f"asked, not guessed: {s!r}", bool(got) and bit in got.get("ask", ""), got)
    for s in ("delete the reminder for tomorrow", "forget it", "delete everything on my todo list",
              "yes", "approve", "approve it", "yes forget them", "forget about the dentist",
              "delete my messages from John", "clear my history"):
        check(f"not ours: {s!r}", FR.parse_phrase(Q.normalise(s), NOW) is None)


def t_quick_never_removes():
    w = _world_with_things()
    CH.use(w.log)
    real_mem = FR._memory
    FR._memory = lambda: w.mem
    try:
        res = Q.answer("forget what you learned from 1 to 15 September", sched=_Sched(), now=NOW)
        check("typed or said: answered without the model", res is not None
              and res.intent == "forget_range", res and res.reply)
        check("... it says where the list is, and that saying yes does nothing",
              "in Brain, under Forget a time frame: 3 facts from 1 to 15 September 2026" in res.reply
              and "saying yes out loud does not approve it" in res.reply, res.reply)
        check("... and opens that place in the app", res.open_brain == "forget-range"
              and Q.route_fields(res).get("open_brain") == "forget-range")
        check("... NOTHING was removed", w.row(w.a)["valid_to"] is None
              and len(w.log.list()["conversations"]) == 2)
        asked = FR.status(NOW)["asked"]
        check("... the apps' list is filled in with those days", asked is not None
              and (asked["from"], asked["to"], asked["kinds"]) == ("2026-09-01", "2026-09-15", ["facts"]),
              asked)
        check("no card was raised by the sentence", FR.status(NOW)["waiting"] is False)
        w.ask(_body(w))
        for said in ("yes", "approve", "approve it", "yes, forget them", "OK go ahead"):
            got = Q.answer(said, sched=_Sched(), now=NOW)
            check(f"a spoken {said!r} approves nothing", (got is None or got.intent != "forget_range")
                  and FR.status(NOW)["waiting"] is True and not w.gate.asked)
        w.spawn.jobs.clear()
        FR._reset_for_tests()
        res = Q.answer("forget what you learned on Monday", sched=_Sched(), now=NOW)
        check("a date it cannot be sure of: a question, and nothing opened", res is not None
              and "Today is Monday" in res.reply and res.open_brain is None
              and FR.status(NOW)["asked"] is None, res and res.reply)
        res = Q.answer("forget what you learned in July", sched=_Sched(), now=NOW)
        check("nothing from then: said, nothing opened",
              res.reply == "There is nothing to forget: Jarvis learned nothing from 1 to 31 July 2026."
              and res.open_brain is None, res.reply)
        res = Q.answer("erase what I said from 1 to 15 September", sched=_Sched(), now=NOW)
        check("'erase' is told plainly this forgets, and Erase the words is per fact",
              res.reply.startswith("I can forget them, but not erase their words"), res.reply)
    finally:
        FR._memory = real_mem


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------


class FakeHandler:
    def __init__(self, path, body=b"{}", token=True, origin=True):
        self.path = path
        self.body = body
        self.token = token
        self.origin = origin
        self.sent = None

    def do_GET(self):
        self.sent = ("original GET",)

    def do_POST(self):
        self.sent = ("original POST",)

    def _send(self, code, out):
        self.sent = (code, out)


def t_routes():
    w = _world_with_things()
    real_mem, real_spawn, real_gate = FR._memory, FR._spawn, FR._gate
    FR._memory, FR._spawn, FR._gate = (lambda: w.mem), w.spawn, w.gate

    class H(FakeHandler):
        pass

    banner = FR.install(H, origin_ok=lambda s: s.origin, token_ok=lambda s: s.token,
                        read_body=lambda s: s.body)
    try:
        check("install() gives a banner line", "Forget a time frame" in banner)
        check("installing twice is harmless", "already on" in FR.install(
            H, origin_ok=lambda s: True, token_ok=lambda s: True, read_body=lambda s: b""))
        h = H("/api/memory/forget_range")
        H.do_GET(h)
        check("GET status", h.sent[0] == 200 and h.sent[1]["available"] is True
              and h.sent[1]["max_items"] == 200 and h.sent[1]["undo_minutes"] == 10
              and [p["id"] for p in h.sent[1]["presets"]][:2] == ["today", "yesterday"], h.sent)
        h = H("/api/memory/forget_range/preview?from=2026-09-01&to=2026-09-15&kinds=facts")
        H.do_GET(h)
        check("GET preview", h.sent[0] == 200 and len(h.sent[1]["facts"]) == 3, h.sent)
        h = H("/api/memory/forget_range/preview?preset=someday")
        H.do_GET(h)
        check("GET preview: a bad choice is a 400 in words", h.sent[0] == 400, h.sent)
        h = H("/api/memory/forget_range", token=False)
        H.do_GET(h)
        check("no token: 401", h.sent[0] == 401)
        h = H("/api/memory/forget_range/undo", origin=False)
        H.do_POST(h)
        check("another origin: 403", h.sent[0] == 403)
        h = H("/api/memory/forget_range/undo", body=b"{}")
        H.do_POST(h)
        check("POST undo with nothing to undo: 409", h.sent[0] == 409, h.sent)
        h = H("/api/memory/forget", body=b"{}")
        H.do_POST(h)
        check("any other route goes to the original handler", h.sent == ("original POST",))
        h = H("/api/memory/forget_range", body=b"not json")
        H.do_POST(h)
        check("POST with a body that is not JSON: 400", h.sent[0] == 400)
        body = json.dumps({"from": "2026-09-01", "to": "2026-09-15", "facts": [w.a]}).encode()
        h = H("/api/memory/forget_range", body=body)
        H.do_POST(h)
        check("POST forget: 202 and one card waiting", h.sent[0] == 202 and len(w.spawn.jobs) == 1,
              h.sent)
    finally:
        FR._memory, FR._spawn, FR._gate = real_mem, real_spawn, real_gate
        w.spawn.jobs.clear()
        FR._reset_for_tests()


# --------------------------------------------------------------------------
#   Fit: card words, What asks first, the settings file, the patch
# --------------------------------------------------------------------------


def t_fit():
    import jarvis_card_words as W
    import jarvis_asks_first as A
    check("the card has a plain title", W.title_for("memory_forget_range").startswith(
        "Jarvis wants to forget what it learned"))
    check("What asks first: it always asks and cannot be loosened",
          "memory_forget_range" in A.MUST_ASK and "memory_forget_range" in A.HARD_LIMITS
          and "memory_forget_range" not in A.LOOSE)
    rows = [r for g in A.GROUPS for r in g[1]]
    check("... and it has a row on the page", "memory_forget_range" in rows)
    toml = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("the shipped settings file says ask", 'memory_forget_range       = "ask"' in toml)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    try:
        import _stack as _st
        rewritten = _st.later_rewriting("forget-range.patch", "forget_range", names)
    except Exception as exc:  # noqa: BLE001 - reported as the check's detail
        rewritten = [repr(exc)]
    check("forget-range.patch is in apply-patches.ps1, and no later patch rewrites its lines",
          "forget-range.patch" in names and not rewritten, rewritten or names[-3:])
    check("jarvis_forget_range.py is shipped", "'jarvis_forget_range.py'" in ps1)
    try:
        import _stack
        for target, needle in (("jarvis_gate.py", '"memory_forget_range": ("no", "local"'),
                               ("jarvis_hud.py", "jarvis_forget_range.install(Handler")):
            text, log = _stack.stand_in(target)
            mine = [l for l in log if l.startswith("forget-range")]
            check(f"forget-range.patch applies to {target} on the whole stack, on its own context",
                  text is not None and needle in text and not mine, (log[-3:], mine))
    except Exception as exc:
        check("the stack could be rehearsed", False, repr(exc))
    gen = REPO / "tools" / "gen_forget_range_cases.py"
    r = subprocess.run([sys.executable, str(gen), "--check"], capture_output=True, text=True)
    check("both apps' copy of the words and answers is current "
          "(python3 tools/gen_forget_range_cases.py)", r.returncode == 0, r.stdout + r.stderr)


def t_no_network_no_words_in_the_audit():
    check("nothing tried the network", _NET == [], _NET)
    text = json.dumps(_AUDIT)
    check("the audit log has counts and outcomes, never a fact's words or a chat's title",
          "Leeds" not in text and "Rome" not in text and any(
              e == "memory.forget_range.done" for e, _ in _AUDIT), text[:300])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
