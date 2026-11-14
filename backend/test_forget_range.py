"""test_forget_range.py - "Forget a time frame": a checked list, ONE card,
ten minutes to undo.

    python3 backend/test_forget_range.py

The owner's decision of 2026-09-28 (CLAUDE.md): the owner may ask, by voice
or typing, to forget what Jarvis learned or said in a time frame. Nothing is
removed at once: both apps show the exact facts and chats, each ticked; ONE
approval card carrying the count of facts and chats and the days is decided by
tapping only; approved, the facts are forgotten (retired, as Forget does) and
the chats deleted, with 10 minutes to Undo. The full list stays on the screen
that was ticked. backend/jarvis_forget_range.py does the work,
forget-range.patch installs its routes (docs/JARVIS-API.md section 64).

What is proved here, against a real memory store and a real, encrypted
chat history in a temp folder, with the clock and the time zone fixed:

  * time frames: the choices, typed dates, times of day, what is refused;
  * the list: facts by when they were SAVED (never their "true from"
    date), only facts still in use, chats that overlap the days - and the
    ones that spill outside them marked; PINNED chats are never on the
    tickable list and are counted as kept; an estimate measured from the
     counts, with a human sentence; NO ITEM CAP (the owner's 2026-11-08
     ruling): any number is listed in full and offered, and a selection past
     LARGE_WIPE_ITEMS (200) is called a LARGE WIPE in words - never refused;
  * the card: tier "ask" only, the COUNT of facts and chats with the date
    range, the facts' own words while they fit, the pinned-kept count and the
    estimate on it; one at a time; a list that changed since it was read
    refused; a card that would be cut by the gate's 4,000-character limit
    (the owner's ruling of 2026-11-13) is REFUSED before it is raised - and
    the checked list still carries every item in full;
   * NO BACKUP IS TOUCHED: a backup folder present on disk is byte-unchanged
     through a preview and a full forget, and the module names no backup at
     all (walked as AST nodes, not pinned as source text);
   * the DOUBLE-CONFIRM guard BITES (mutation-proved): removing the literal-yes
     refusal makes a test go red, and the original refuses;
   * TWO yesses: approving the card changes NOTHING and holds the items;
    only POST /confirm with a literal `yes: true` retires the facts (with
    Forget's own "forgotten" mark) and deletes the chats; denied or timed
    out: nothing changed; a non-literal yes is a 400 and the hold stays;
    409 with no hold, an expired hold, a changed list, a card still
    waiting or an Undo already open;
  * Undo: everything back as it was (a lease's end date too), once; a fact
    erased meanwhile stays erased; a chat continued meanwhile is joined
    back together; after ten minutes (or a restart) there is nothing to
    undo, and the held chats are dropped;
  * by voice or typing: jarvis_quick fills in the list and opens Brain,
    NEVER removes anything, asks about a date it cannot be sure of, answers
    "how long would that take" from the measured estimate, asks which days
    for a date-less "clear old chats" instead of denying the capability,
    and a spoken "yes" approves nothing;
  * the routes, token and origin like every other, and the words both apps
    share (tools/gen_forget_range_cases.py) are current.

No pytest, no network, no model.
"""
from __future__ import annotations

import ast
import importlib.util
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

#: forget-range.patch's OWN risk-table line for the action, used by the
#: later_rewriting() question below. The question is "does a later patch
#: REWRITE one of the lines forget-range.patch wrote", so the needle is the
#: LINE, not the bare `forget_range`: gate-touches.patch (2026-10-20) names
#: `memory_forget_range` again, in its own `_REPLACES_ACTIONS` table for the
#: blind-approval guards, without touching this line. A bare name flagged that
#: new table and proved nothing about the line that matters.
FORGET_RANGE_RISK_LINE = '"memory_forget_range": ("no", "local",'
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

# A MEASURED accommodation of a PRE-EXISTING path, not part of this feature:
# `jarvis_quick.answer()` calls `_awareness_note()` after any answer whose
# intent is not in READ_ONLY_INTENTS, and "forget_range" is not in that set
# (jarvis_quick.py:25990 here). That note reads this PC's real model records -
# which on this PC opens a connection to Ollama - and writes the change journal
# under OPENJARVIS_HOME (~/.openjarvis by default). Measured 2026-11-09 with
# the stub removed and OPENJARVIS_HOME pointed at a temp folder: 257 passed,
# 1 failed ("nothing tried the network"), and self-awareness/snapshot.json was
# written. A test must not touch the owner's live folder or the network, so
# only that one post-answer writer is stubbed; the forget-range path under test
# never calls it. (The real fix - adding "forget_range" to READ_ONLY_INTENTS -
# touches a Wave-11 module and belongs to the Lead, not this lane.)
Q._awareness_note = lambda *a, **k: ""

PASSED, FAILED = [], []
KEY = bytes(range(32))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def at(y, mo, d, h=12, mi=0) -> float:
    return datetime(y, mo, d, h, mi).timestamp()


#: Monday 28 September 2026, 15:30, in UTC. The zone is set HERE, not left to the
#: machine: the frames ("last week", "yesterday") are the PC's local days, so
#: the same test gave different answers on a PC in another zone (2026-09-30).
os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()
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
        """Answer the waiting card as the gate says (the FIRST yes). Since
        the owner's decision of 2026-11-04 this changes nothing: it holds the
        items for the second yes, with a timer this test holds."""
        real = FR._timer
        FR._timer = self.timers
        try:
            self.spawn.run()
        finally:
            FR._timer = real

    def hold_id(self):
        with FR._LOCK:
            return (FR._STATE["hold"] or {}).get("token")

    def confirm(self, yes=True, now=NOW, hold_id=None):
        """The SECOND yes, through the real route's own function. With no hold
        at all it still sends a well-shaped id, so the answer is the route's
        own 409 and not a 400 about the body."""
        hid = hold_id if hold_id is not None else self.hold_id()
        body = {"id": hid if isinstance(hid, str) else "0" * 32, "yes": yes}
        return FR.confirm(body, now=now, mem=self.mem, chats=self.log, timer=self.timers)

    def forget(self, body, now=NOW):
        """The whole two-step flow: card, first yes, second yes."""
        code, out = self.ask(body, now=now)
        if code != 202:
            return code, out
        self.approve()
        return self.confirm(now=now)

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
    w.chat("conv-pinned-0004", "Pinned planning", at(2026, 9, 5, 9))
    w.log.set_pin("conv-pinned-0004", True)
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
    # The owner's decision of 2026-11-04: a pinned chat is kept.
    check("a pinned chat is NEVER on the tickable list",
          "conv-pinned-0004" not in cids, cids)
    check("... and the list says which pinned chats it is keeping, and how many",
          p["pinned_kept"] == [{"id": "conv-pinned-0004", "title": "Pinned planning",
                                "messages": 1}]
          and p["pinned_kept_count"] == 1, p.get("pinned_kept"))
    check("... a pinned chat is not in the count that Forget these sends",
          p["counts"]["chats"] == 2)
    # The measured "how long would that take" (owner, 2026-11-04).
    est = p["estimate"]
    check("the estimate is made of the counts just measured",
          est["facts"] == 2 and est["chats"] == 2 and est["messages"] == 4
          and isinstance(est["seconds"], int) and est["seconds"] >= 1, est)
    check("... and says it in a plain sentence",
          est["text"] == "About 1 second to forget 2 facts and delete 2 chats (4 messages).",
          est["text"])
    only = w.preview("2026-09-01", "2026-09-15", ("chats",))
    check("chats only: no facts read", only["facts"] == [] and "facts" not in only["counts"]
          and only["said"] == "2 chats from 1 to 15 September 2026.", only)
    check("... and the estimate leaves the facts out", only["estimate"]["facts"] == 0
          and "forget 0 facts" not in only["estimate"]["text"], only["estimate"])
    empty = w.preview("2026-07-01", "2026-07-02")
    check("nothing then: empty, and said so", empty["empty"] is True
          and empty["said"] == "0 facts and 0 chats from 1 to 2 July 2026.", empty["said"])
    check("... with a one-second floor rather than a pretend zero",
          empty["estimate"]["seconds"] == 1 and empty["pinned_kept_count"] == 0,
          empty["estimate"])
    m = w.preview("2026-09-01", "2026-09-15")
    check("nothing was changed by reading the list",
          w.row(a)["valid_to"] is None and len(w.log.list()["conversations"]) == 4)


def t_no_cap_and_large_wipe():
    """The owner's ruling, 2026-11-08, verbatim: "why is there a cap at 200? I
    say i should be able to wipe as many as i want as long as there is a double
    confirmation and it doesn't touch any backups."

    So: 241 items preview in FULL and are offered in one action; the words say
    LARGE WIPE (the old 200 is now only the threshold for saying so, named in
    the body); and the double confirmation is unchanged - the card holds them
    and only the second yes removes anything."""
    w = World()
    n = 241                                   # 241, not 200: clearly past it
    with closing(sqlite3.connect(w.mem.path)) as c:
        for i in range(n):
            c.execute("INSERT INTO facts (text, source, created, valid_from) VALUES (?,?,?,?)",
                      (f"The owner said thing number {i}", "test", at(2026, 9, 2) + i,
                       at(2026, 9, 2)))
        c.commit()
    p = w.preview("2026-09-01", "2026-09-15")
    check("241 items preview IN FULL - there is no cap", len(p["facts"]) == n
          and p["counts"]["facts"] == n and "too_many" not in p, p["counts"])
    check("... the counts sentence is exact",
          p["said"] == f"{n} facts and 0 chats from 1 to 15 September 2026.",
          p["said"])
    check("... and it is called a large wipe, with the threshold named, never a limit",
          p["large_wipe"] is True and p["large_wipe_items"] == FR.LARGE_WIPE_ITEMS
          and str(n) in p["large_wipe_words"] and "large wipe" in p["large_wipe_words"]
          and "say yes a second time" in p["large_wipe_words"], p["large_wipe_words"])
    check("... the estimate is the whole batch, with no 'at least' or cap note",
          p["estimate"]["facts"] == n and "At least" not in p["estimate"]["text"]
          and "more than" not in p["estimate"]["text"]
          and "repeating it" not in p["estimate"]["text"], p["estimate"])
    body = {"from": "2026-09-01", "to": "2026-09-15",
            "facts": [f["id"] for f in p["facts"]]}
    code, out = w.ask(body)
    check("a 241-item request is offered (202, ONE card), not refused",
          code == 202 and out.get("waiting") is True and not w.gate.asked, out)
    check("... and the 202 body says it is large",
          out.get("large_wipe") is True and "large wipe" in out.get("message", "")
          and "large wipe" in str(out.get("large_wipe_words") or ""), out)
    w.clock.t = NOW + 1
    w.approve()                                # the FIRST yes: nothing changes
    prompt = w.gate.asked[-1][2]
    check("the card lists the big selection and calls it a large wipe",
          f"these {n} facts" in prompt and "large wipe" in prompt, prompt[:400])
    check("... approving the card changes NOTHING: all 241 are still in use",
          all(w.row(f["id"])["valid_to"] is None for f in p["facts"]))
    st = FR.status(NOW + 2)
    check("... the status offers the SECOND yes, with the large-wipe words",
          st["confirm"] is not None and st["large_wipe"] is True
          and st["confirm"]["large_wipe"] is True
          and "large wipe" in st["confirm"]["text"], st.get("confirm"))
    code, out = w.confirm(now=NOW + 3)
    check("... and only the second yes forgets all 241", code == 200
          and out["facts_forgotten"] == n, out)
    check("... every one really is forgotten",
          all(w.row(f["id"])["retired_at"] is not None for f in p["facts"]))
    code, out = FR.undo(now=NOW + 60, mem=w.mem, chats=w.log)
    check("... and Undo puts all 241 back", code == 200 and out["restored"]["facts"] == n, out)
    check("... every one is in use again",
          all(w.row(f["id"])["valid_to"] is None for f in p["facts"]))


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
    # A pinned chat in the same days, created after the list was read, so the
    # card must say it is being kept (owner, 2026-11-04).
    w.chat("conv-pinned-00003", "Pinned planning", at(2026, 9, 5, 9))
    w.log.set_pin("conv-pinned-00003", True)
    body = _body(w, facts=[w.a, w.b])          # the owner unticked the pears
    code, out = w.ask(body)
    check("202: one card is raised", code == 202 and out["waiting"] is True
          and out["counts"] == {"facts": 2, "chats": 2}, out)
    check("... and nothing changed yet", w.row(w.a)["valid_to"] is None
          and len(w.log.list()["conversations"]) == 3)
    check("... the pinned chat is counted as kept, not as deleted",
          out["pinned_kept_count"] == 1, out)
    check("... and the SECOND yes is offered with its own route, id and 2 minutes",
          out["confirm"]["route"] == FR.CONFIRM and out["confirm"]["expires_in"] == 120
          and isinstance(out["confirm"]["id"], str) and len(out["confirm"]["id"]) == 32
          and "Say yes again" in out["confirm"]["text"], out.get("confirm"))
    st = FR.status(NOW)
    check("status: waiting, with the pinned count, and no second yes yet",
          st["waiting"] is True and st["pinned_kept_count"] == 1 and st["confirm"] is None, st)
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
                  "Saying yes out loud does not approve it",
                  "1 pinned chat is kept", "About 1 second to forget 2 facts",
                  "say yes a second time"):
        check(f"the card says {words!r}", words in prompt, prompt)
    check("the card says what stays (the second chat audit): unticked facts and older backups",
          "Facts you did not tick stay. Copies in older backups stay until they age out." in prompt, prompt)
    check("the unticked fact is not on the card", "pears" not in prompt)
    check("the card's detail says it stays on this PC, and how many pins are kept",
          detail["leaves_this_pc"] is False
          and detail["text"] == prompt and detail["facts"] == 2 and detail["chats"] == 2
          and detail["pinned_kept"] == 1, detail)


# --------------------------------------------------------------------------
#   A big range must still FIT on one card (the owner's ruling, 2026-11-13)
# --------------------------------------------------------------------------

#: Monday 9 November 2026, 15:30 UTC: the day after the range the owner used,
#: so his own "2 to 8 November" frame is in the past and frame_of accepts it.
NOV_AFTER = at(2026, 11, 9, 15, 30)

#: The facts the range holds. The owner's own chat titles are longer (his card
#: measured 14,546 characters on 2026-11-13); these are short on purpose, so
#: the number this suite prints is THIS test's, not his.
_NOV_FACTS = ("The owner moved to Leeds", "The owner's lease ends in December",
              "The owner likes pears")


def _november_world(chats=125):
    """The owner's own shape: 3 facts and `chats` chats from 2 to 8 November
    2026, with the preview of that range already taken."""
    w = World()
    for i, text in enumerate(_NOV_FACTS):
        w.fact(text, at(2026, 11, 3 + i))
    for i in range(chats):
        w.chat(f"conv-{i:05d}", f"Chat number {i} about the kitchen plan",
               at(2026, 11, 2) + i * 3600)
    w.frame = FR.frame_of("2026-11-02", "2026-11-08", NOV_AFTER)
    w.preview_nov = FR.preview(w.frame, FR.KINDS, mem=w.mem, chats=w.log)
    w.body = {"from": "2026-11-02", "to": "2026-11-08",
              "facts": [f["id"] for f in w.preview_nov["facts"]],
              "chats": [c["id"] for c in w.preview_nov["chats"]]}
    return w


def t_a_125_chat_range_fits_on_one_card():
    """THE OWNER'S RULING (2026-11-13, verbatim: "Show the count, allow it").

    jarvis_gate stores a card's detail as `json.dumps(detail)[:4000]`, and the
    HUD disables Approve when a detail that long no longer parses ("This
    request was cut off before it reached this card"). A card that listed
    every chat was 14,546 characters for the owner's own 125 chats: it reached
    the HUD cut off mid-JSON and expired un-approvable. So the CARD now
    carries the count and the dates, and the PREVIEW screen keeps every item -
    this proves both halves at once."""
    w = _november_world()
    p = w.preview_nov
    check("CONTROL: the range holds 3 facts and 125 chats",
          p["counts"] == {"facts": 3, "chats": 125} and len(p["chats"]) == 125,
          p["counts"])
    code, out = w.ask(w.body, now=NOV_AFTER)
    check("CONTROL: the range is offered - 202 and one card", code == 202, out)
    w.approve()                     # the card is raised, so the gate saw its detail
    action, detail, prompt = w.gate.asked[-1]
    stored = json.dumps(detail)
    try:
        json.loads(stored[:4000])
        parses = True
    except ValueError:
        parses = False
    check("PIN 1: the 125-chat card is well under the gate's 4,000 characters",
          len(prompt) < 2000, len(prompt))
    check("PIN 1b: the detail the gate keeps - json.dumps(detail)[:4000] - is VALID "
          "JSON, so the HUD can never call it cut off",
          len(stored) < 4000 and parses, f"{len(stored)} characters, parses={parses}")
    check("PIN 2: the card says the count of facts and chats and the date range",
          "3 facts and 125 chats from 2 to 8 November 2026." in prompt, prompt[:300])
    check("... word for word the sentence the checked list itself carries",
          p["said"] in prompt, p["said"])
    check("... and the facts' own words are still on it, so the owner sees what he loses",
          all(t in prompt for t in _NOV_FACTS), prompt[:600])
    check("... with the risk sentence and the undo promise unchanged",
          "For 10 minutes after the second yes, one tap on Undo" in prompt
          and "the chats are gone for good" in prompt
          and "Saying yes out loud does not approve it" in prompt, prompt[-500:])
    check("... and it says where the full list is",
          "The full list, every title and date, is on the Forget a time frame screen, "
          "where you ticked them." in prompt, prompt[-500:])
    check("... not one line per chat: a card of a few dozen lines, not 144",
          prompt.count("\n") < 30, prompt.count("\n"))
    check("PIN 4: the PREVIEW still lists every item in full - nothing was removed there",
          [c["title"] for c in p["chats"]] == [f"Chat number {i} about the kitchen plan"
                                               for i in range(125)]
          and all(c["label"] for c in p["chats"])
          and [f["text"] for f in p["facts"]] == list(_NOV_FACTS), p["counts"])
    check("... so the card counts them while the screen still shows every title",
          "Chat number 0" not in prompt
          and p["chats"][0]["title"] == "Chat number 0 about the kitchen plan",
          prompt[:200])
    check("... and the card's detail carries the same counts, on this PC",
          detail["facts"] == 3 and detail["chats"] == 125
          and detail["leaves_this_pc"] is False, detail)


def t_a_big_list_of_facts_fits_too():
    """The other half of the fit: the facts are kept while they fit, and when
    they cannot, the card says so and names where their words are - rather
    than being cut. 300 facts of ordinary length cannot fit (each line is over
    100 characters), so the card falls back to the count and the pointer."""
    w = World()
    with closing(sqlite3.connect(w.mem.path)) as c:
        for i in range(300):
            c.execute("INSERT INTO facts (text, source, created, valid_from) VALUES (?,?,?,?)",
                      (f"The owner said thing number {i}, which is a long enough fact to take "
                       "a line of its own on any card that tried to list it", "test",
                       at(2026, 11, 2) + i, at(2026, 11, 2)))
        c.commit()
    w.frame = FR.frame_of("2026-11-02", "2026-11-08", NOV_AFTER)
    p = FR.preview(w.frame, FR.KINDS, mem=w.mem, chats=w.log)
    body = {"from": "2026-11-02", "to": "2026-11-08",
            "facts": [f["id"] for f in p["facts"]]}
    code, out = w.ask(body, now=NOV_AFTER)
    check("CONTROL: 300 facts are offered - 202 and one card", code == 202, out)
    w.approve()
    prompt = w.gate.asked[-1][2]
    check("a 300-fact card fits by carrying the count, not 300 lines",
          len(prompt) < 2000 and prompt.count("\n") < 20, f"{len(prompt)} characters")
    check("... the count and the days are on it",
          "300 facts from 2 to 8 November 2026." in prompt, prompt[:300])
    check("... and it says, grammatically, where the facts' own words are",
          "Their words are on the Forget a time frame screen, where you ticked them." in prompt,
          prompt[:600])
    check("... no fact is quoted on it", "thing number 0" not in prompt, prompt[:300])
    check("... and the preview still carries all 300, each with its words",
          len(p["facts"]) == 300 and p["counts"] == {"facts": 300, "chats": 0}
          and p["facts"][0]["label"], p["counts"])


def t_a_card_that_would_be_cut_is_refused_before_it_exists():
    """Fail closed on THIS path too - the half that was missing.

    The model tool path refuses a too-long card before it is raised
    (jarvis_agent.py's `_card_would_be_cut`, the rule its comment at
    :7672-7676 describes). jarvis_forget_range raised its card straight
    through `jarvis_gate.check` and never asked, so the owner's own card sat at
    exactly 4,000 characters, invalid JSON, un-approvable, until it expired
    (measured 2026-11-13). Now the route asks the same rule, imported from its
    owner."""
    import jarvis_agent
    w = _november_world(chats=2)
    body = w.body
    asked = len(w.gate.asked)

    # (a) The rule is IMPORTED, not copied: patching the owner's function must
    # change this route's answer.
    real = jarvis_agent._card_would_be_cut
    calls = []
    jarvis_agent._card_would_be_cut = lambda *a, **k: (calls.append(a), True)[1]
    try:
        code, out = w.ask(body, now=NOV_AFTER)
    finally:
        jarvis_agent._card_would_be_cut = real
    check("PIN 3: a card the gate would cut is REFUSED before it is raised - "
          "no approvals row, no card job",
          code == 400 and "nothing was asked" in out.get("error", "")
          and len(w.gate.asked) == asked and not w.spawn.jobs, out)
    check("... the refusal comes from jarvis_agent's own rule - imported from the "
          "module that owns it, never copied",
          len(calls) == 1, calls)
    check("... and nothing is left holding anything: no card waiting, no second yes",
          FR._STATE["pending"] is None and FR._STATE["hold"] is None, FR._STATE)

    # (b) The real rule, on a card that genuinely would be cut: 9,000 characters.
    real_card = FR.card_text
    FR.card_text = lambda *a, **k: "x" * 9000
    try:
        code2, out2 = w.ask(body, now=NOV_AFTER)
    finally:
        FR.card_text = real_card
    check("... and a card forced past 4,000 characters is refused the same way, "
          "not shown un-approvable",
          code2 == 400 and "nothing was asked" in out2.get("error", "")
          and len(w.gate.asked) == asked and not w.spawn.jobs, out2)


def t_two_yeses():
    """The owner, 2026-11-04: "give me a card with all the details, with a
    double confirmation of yes if i want to". The card is the FIRST yes and
    changes nothing; only POST /confirm with a literal `yes: true` acts, and
    every other answer changes nothing."""
    w = _world_with_things()
    w.chat("conv-pinned-00003", "Pinned planning", at(2026, 9, 5, 9))
    w.log.set_pin("conv-pinned-00003", True)
    code, out = w.ask(_body(w, facts=[w.a, w.b]))
    check("CONTROL: 202 and the card", code == 202, out)
    w.approve()                                  # the FIRST yes
    st = FR.status(NOW)
    check("after the card: nothing forgotten, nothing deleted",
          w.row(w.a)["valid_to"] is None and w.row(w.b)["retired_at"] is None
          and len(w.log.list()["conversations"]) == 3)
    check("... status offers the second yes and says the card is approved",
          st["waiting"] is False and st["confirm"] is not None
          and st["confirm"]["expires_in"] == 120 and st["last"]["outcome"] == "confirm", st)
    held = st["confirm"]["id"]
    code, out = w.confirm(yes="yes", hold_id=held)
    check("a yes that is not the literal true: 400, and the hold STAYS",
          code == 400 and "literal yes" in out["error"]
          and w.hold_id() == held and w.row(w.a)["valid_to"] is None, out)
    code, out = w.confirm(yes=1, hold_id=held)
    check("... a 1 is not true either", code == 400 and w.hold_id() == held, out)
    code, out = w.confirm(hold_id="f" * 32)
    check("the wrong id: 409, nothing changed", code == 409 and w.hold_id() == held
          and w.row(w.a)["valid_to"] is None, out)
    code, out = w.confirm()
    check("the second yes: 200 and only now do the facts and chats go",
          code == 200 and out["ok"] is True and out["facts_forgotten"] == 2
          and out["chats_deleted"] == 2 and out["pinned_kept"] == 1, out)
    check("... the fact is retired, not erased",
          w.row(w.a)["retired_at"] is not None and w.row(w.a)["erased_at"] is None
          and w.row(w.a)["text"] == "The owner moved to Leeds")
    check("... the pinned chat is still there", w.log.get("conv-pinned-00003") is not None)
    check("... and the two ticked chats are gone", w.log.get("conv-trip-00001") is None
          and w.log.get("conv-poem-00002") is None)
    check("... with the Undo's own 10 minutes in the answer",
          out["undo"]["seconds"] == 600 and out["undo"]["until"] == "2026-09-28T15:40:00", out)
    check("... and the status has no second yes left to give",
          FR.status(NOW)["confirm"] is None and FR.status(NOW)["undo"] is not None)
    code, out = w.confirm()
    check("a second confirm after it: 409, nothing changed twice", code == 409, out)
    check("Undo after the second yes still puts everything back",
          FR.undo(now=NOW + 60, mem=w.mem, chats=w.log)[0] == 200
          and w.log.get("conv-trip-00001") is not None
          and w.row(w.a)["valid_to"] is None)


def t_the_second_yes_409s():
    """Every refusal the frozen contract names, each with nothing changed."""
    w = _world_with_things()
    code, out = w.confirm()                       # no hold at all
    check("no hold: 409", code == 409 and "no second yes waiting" in out["error"], out)
    code, out = w.ask(_body(w, facts=[w.a]))
    check("CONTROL: the card is waiting", code == 202, out)
    code, out = w.confirm()                       # a card is still waiting
    check("a card still waiting: 409, and the card is still waiting",
          code == 409 and "still waiting" in out["error"]
          and FR.status(NOW)["waiting"] is True, out)
    w.approve()
    held = w.hold_id()
    code, out = w.confirm(now=NOW + FR.HOLD_SECONDS + 1)   # the hold expired
    check("the hold expired: 409, nothing forgotten",
          code == 409 and "2 minutes are up" in out["error"] and w.row(w.a)["valid_to"] is None,
          out)
    check("... and expiry is not an error state: the status just stops offering it",
          FR.status(now=NOW + FR.HOLD_SECONDS + 1)["confirm"] is None
          and FR.status(now=NOW + FR.HOLD_SECONDS + 1)["last"]["outcome"] == "confirm_expired")
    w = _world_with_things()
    w.ask(_body(w, facts=[w.a]))
    w.approve()
    w.mem.retire(w.a)                             # the list changed while held
    code, out = w.confirm()
    check("the items changed: 409 with changed: true, nothing forgotten",
          code == 409 and out.get("changed") is True, out)
    # A hold and an open Undo are never both real (a card is refused while an
    # Undo is open, and the second yes clears the hold), so the guard is shown
    # by putting the two states there by hand: it must still refuse.
    w = _world_with_things()
    w.ask(_body(w, facts=[w.a]))
    w.approve()
    with FR._LOCK:
        FR._STATE["undo"] = {"token": "made-up", "until": NOW + 300,
                             "mono_until": time.monotonic() + 300,
                             "facts": [], "chats": {}, "frame": "1 to 15 September 2026"}
    code, out = w.confirm()
    check("an Undo already open: 409, nothing else forgotten",
          code == 409 and "undo" in out["error"].lower()
          and w.row(w.a)["valid_to"] is None, out)
    with FR._LOCK:
        FR._STATE["undo"] = None
    w.confirm()
    check("... and once it is out of the way the held second yes still works",
          w.row(w.a)["retired_at"] is not None)


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
    w.approve()                                  # FIRST yes: nothing changes yet
    check("the first yes alone left every fact and chat alone",
          w.row(w.a)["valid_to"] is None and w.log.get("conv-trip-00001") is not None)
    check("... and the second yes is what acts", w.confirm()[0] == 200)
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
    check("timers: 2 minutes for the second yes, 10 minutes for the Undo",
          [s for s, _ in w.timers.set] == [FR.HOLD_SECONDS, 600])
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


def t_the_undo_expiring_scrubs_the_receipts_too():
    """F2 (data-integrity audit, 2026-10-28): when the ten minutes are up the
    held chats are dropped for good - and their words must leave the receipts
    store with them.

    `delete()` has always scrubbed receipts; this path never did, so "Forget a
    time frame" left what was said in receipts.db. It cannot be done when the
    chats are taken out (a scrub cannot be undone, and the Undo is real), so it
    runs at the expiry, on the rows still sealed as they were on disk."""
    import jarvis_receipts as R2
    w = _world_with_things()
    words = "Plan the trip to Rome"

    def receipt_row(rid):
        with closing(sqlite3.connect(str(R2.db_path()))) as c:
            return c.execute("SELECT summary FROM action_receipts WHERE receipt_id=?",
                             (rid,)).fetchone()

    rid = R2.record("note_write", "saved: " + words, before={"text": words})
    w.ask(_body(w, facts=[w.a, w.b]))
    w.approve()
    w.confirm()
    check("the chat is gone from the history", w.log.get("conv-trip-00001") is None)
    check("... while the Undo is open its words are STILL in the receipt "
          "(a scrub could not be undone)",
          words in (receipt_row(rid)[0] or ""), receipt_row(rid))
    st = FR.status(NOW + 601)                     # ten minutes and a second
    row = receipt_row(rid)
    check("when the ten minutes are up the held chats are dropped for good",
          st["undo"] is None and st["last"]["outcome"] == "kept", st)
    check("F2: ... and their words are scrubbed out of the receipts",
          row is not None and words not in (row[0] or ""), row)
    check("F2: ... replaced by the fixed marker, never a hash",
          row is not None and R2.FORGOTTEN in (row[0] or ""), row)


def t_the_undo_window_cannot_be_stretched_by_setting_the_clock_back():
    w = _world_with_things()
    w.ask(_body(w, facts=[w.a, w.b]))
    w.approve()
    w.confirm()
    check("CONTROL: the Undo is open", FR.status(NOW)["undo"] is not None)
    real = time.monotonic
    time.monotonic = lambda: real() + 700            # ten real minutes have passed ...
    try:
        st = FR.status(NOW - 3600)                   # ... and the PC's clock was set back an hour
        code, out = FR.undo(now=NOW - 3600, mem=w.mem, chats=w.log)
    finally:
        time.monotonic = real
    check("on the wall clock alone it would still look open; the monotonic clock ends it",
          st["undo"] is None, st["undo"])
    check("... and Undo says the ten minutes are up", code == 409
          and "10 minutes are up" in out["error"], (code, out))


def t_undo_edge_cases():
    w = _world_with_things()
    w.ask(_body(w, facts=[w.a, w.b]))
    w.approve()
    w.confirm()
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
    w.confirm()
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
    w.confirm()
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
    w.confirm()
    seconds, fn = w.timers.set[-1]
    fn()
    check("the ten-minute timer drops what was held", FR.status(NOW)["undo"] is None
          and FR._STATE["undo"] is None)

    w = _world_with_things()
    w.ask(_body(w))
    w.approve()
    w.confirm()
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
        # The owner's own words, 2026-11-04: "clear old chats", "clear the
        # chats from <date>", "delete the conversations from last week".
        "clear the chats from 3 September": ("2026-09-03", "2026-09-03", ("chats",)),
        "clear conversations from 3 September": ("2026-09-03", "2026-09-03", ("chats",)),
        "delete the conversations from last week": ("2026-09-21", "2026-09-27", ("chats",)),
        "forget chats from yesterday": ("2026-09-27", "2026-09-27", ("chats",)),
        "clear old chats and everything you learned": None,       # date-less: asks
        "clear old chats": None,
        "delete old conversations": None,
    }
    for s, want in cases.items():
        got = FR.parse_phrase(Q.normalise(s), NOW)
        if want is None:
            # Date-less: it must ASK which days, naming the capability and the
            # pinned chats - never deny it (owner, 2026-11-04).
            check(f"understood, and asks which days: {s!r}",
                  bool(got) and got.get("ask") == FR.WHICH_DAYS
                  and "which days" in got["ask"] and "Pinned chats are always kept" in got["ask"],
                  got)
            continue
        frm, to, kinds = want
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
              "delete my messages from John", "delete everything",
              "how long does it take to boil an egg"):
        check(f"not ours: {s!r}", FR.parse_phrase(Q.normalise(s), NOW) is None)
    # "how long would that take" is answered, not owned by the model: without a
    # range yet it asks which days (owner, 2026-11-04: never "I don't track that").
    for s in ("how long would that take", "how long will that take?",
              "how long would it take to clear old chats",
              "clear old chats and how long would that take"):
        got = FR.parse_phrase(Q.normalise(s), NOW)
        check(f"a 'how long' question is ours, not the model's: {s!r}",
              bool(got) and (got.get("estimate") is True or "ask" in got), got)


def t_a_leap_day_range_asks_instead_of_crashing():
    leap_now = at(2028, 6, 1, 12, 0)
    for s in ("delete my chats from 29 february to 15 january",
              "forget what you learned from 29 february to 10 january"):
        try:
            got = FR.parse_phrase(Q.normalise(s), leap_now)
            crashed = None
        except Exception as exc:                # noqa: BLE001 - the bug was a ValueError
            got, crashed = None, exc
        check(f"{s!r}: no crash", crashed is None, repr(crashed))
        check(f"{s!r}: a plain question to ask again, not a guess",
              bool(got) and "ask" in got and "Say the two dates with their years" in got["ask"], got)
    got = FR.parse_phrase(Q.normalise("delete my chats from 29 february to 3 march"), leap_now)
    check("CONTROL: a leap-day range that IS in order still works",
          bool(got) and "frame" in got and got["frame"].frm == "2028-02-29", got)


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
        # "how long would that take" (owner, 2026-11-04): answered from the
        # measured estimate, never "I don't track that".
        res = Q.answer("how long would that take", sched=_Sched(), now=NOW)
        check("'how long would that take' answers from the estimate, with no model",
              res is not None and res.intent == "forget_range"
              and res.reply.startswith("For 1 to 15 September 2026: About ")
              and "1 second" in res.reply
              and "say yes a second time" in res.reply, res and res.reply)
        check("... and opens that list in the app, since that is what it is about",
              res.open_brain == "forget-range", res and res.open_brain)
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
        # The owner's own words, 2026-11-04: "clear old chats" must ask for the
        # range, and a "how long" with no range must ask too - never deny.
        res = Q.answer("clear old chats", sched=_Sched(), now=NOW)
        check("'clear old chats' asks which days, naming what it can do and the pinned chats",
              res is not None and res.intent == "forget_range"
              and res.reply == FR.WHICH_DAYS and res.open_brain is None, res and res.reply)
        res = Q.answer("how long would that take", sched=_Sched(), now=NOW)
        check("'how long would that take' with no range asks which days, never "
              "'I don't track that'",
              res is not None and res.intent == "forget_range" and res.reply == FR.WHICH_DAYS
              and res.open_brain is None, res and res.reply)
        res = Q.answer("forget what you learned in July", sched=_Sched(), now=NOW)
        check("nothing from then: said, nothing opened",
              res.reply == "There is nothing to forget: Jarvis learned nothing from 1 to 31 July 2026."
              and res.open_brain is None, res.reply)
        res = Q.answer("erase what I said from 1 to 15 September", sched=_Sched(), now=NOW)
        check("'erase' is told plainly this forgets, and Erase the words is per fact",
              res.reply.startswith("I can forget them, but not erase their words"), res.reply)
        # The owner's own clear-chats words (2026-11-04) bind to this intent.
        res = Q.answer("delete the conversations from last week", sched=_Sched(), now=NOW)
        check("'delete the conversations from last week' is this intent, without the model",
              res is not None and res.intent == "forget_range"
              and "There is nothing to forget: there are no chats from 21 to 27 September 2026."
              in res.reply, res and res.reply)
        res = Q.answer("clear the chats from 4 September", sched=_Sched(), now=NOW)
        check("'clear the chats from 4 September' lists that day's chat",
              res is not None and res.intent == "forget_range"
              and "1 chat from 4 September 2026" in res.reply, res and res.reply)
        # The only chat from that day is pinned: say it is kept, never "there
        # are no chats" (which would be a lie).
        w.log.set_pin("conv-trip-00001", True)
        res = Q.answer("clear the chats from 4 September", sched=_Sched(), now=NOW)
        check("a pinned-only day says the chat is kept, not that there are none",
              res is not None and res.intent == "forget_range"
              and "1 chat from then is pinned" in res.reply
              and "there are no chats" not in res.reply, res and res.reply)
    finally:
        FR._memory = real_mem



def t_backups_are_never_touched():
    """The owner's 2026-11-08 ruling: wipe as many as he wants "as long as ...
    it doesn't touch any backups".

    A real backup folder on disk is byte-unchanged through a preview, the ONE
    card, and the second yes; and the module's own code never names, imports,
    copies, prunes or rotates a backup - only its card sentence mentions that
    copies in older backups stay."""
    w = _world_with_things()
    backups = w.dir / "backups"
    backups.mkdir()
    (backups / "2026-09-01.db").write_bytes(b"an older backup, still sealed")
    (backups / "2026-09-02.db").write_bytes(b"a second older backup")
    older = backups / "2025"
    older.mkdir()
    (older / "2025-12-31.db").write_bytes(b"the oldest backup")

    def snapshot():
        return sorted((str(p.relative_to(backups)), p.read_bytes(), p.stat().st_mtime_ns)
                      for p in backups.rglob("*") if p.is_file())

    before = snapshot()
    p = w.preview("2026-09-01", "2026-09-15")
    code, _out = w.ask(_body(w))
    check("the backup folder is untouched by the preview and the card request",
          code == 202 and snapshot() == before, code)
    w.approve()
    code, _out = w.confirm()
    check("... and by the second yes that actually forgets and deletes", code == 200)
    check("... the backups are byte-for-byte unchanged, same names and mtimes",
          snapshot() == before, [x[0] for x in snapshot()])
    check("... no file was added to or removed from the backup folder",
          [x[0] for x in snapshot()] == [x[0] for x in before])

    # And the module's own CODE never names a backup: only the card sentence
    # does (a string constant, not an import, a call or a path).
    tree = ast.parse(Path(FR.__file__).read_text(encoding="utf-8"))
    tree_imports = _imported_modules(tree)
    named = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and "backup" in node.id.lower():
            named.append(node.id)
        elif isinstance(node, ast.Attribute) and "backup" in node.attr.lower():
            named.append(node.attr)
        elif isinstance(node, ast.Import):
            named += [a.name for a in node.names if "backup" in a.name.lower()]
        elif isinstance(node, ast.ImportFrom) and "backup" in (node.module or "").lower():
            named.append(node.module)
    check("the module's own code never names or imports a backup mechanism", named == [], named)
    check("... and it imported no module that copies or prunes a file",
          all(m not in tree_imports for m in ("shutil", "glob", "zipfile")),
          sorted(tree_imports & {"shutil", "glob", "zipfile"}))
    # The two stores this path owns ARE touched by the same run - so the test
    # above cannot pass for the wrong reason (nothing happening at all).
    check("... while the two stores it does own really were used",
          w.row(w.a)["retired_at"] is not None
          and len(w.log.list()["conversations"]) < 2)


def t_the_double_confirm_guard_bites():
    """MUTATION PROOF of the second yes: take the literal-yes refusal out of a
    COPY of the module and a non-literal `yes: false` DELETES the items; the
    real module refuses the same call in the PC's own words. So the guard is
    load-bearing, and the suites that assert the refusal would go red if it
    were removed."""
    src = Path(FR.__file__).read_text(encoding="utf-8")
    mutant_src = src.replace('if body.get("yes") is not True:', "if False:")
    check("the mutation changes the module (the guard is really in the source)",
          mutant_src != src)
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-forget-mutant-"))
    mp = tmp / "jarvis_forget_range_mutant.py"
    mp.write_text(mutant_src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("jarvis_forget_range_mutant", mp)
    MUT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MUT)
    MUT._timer = Timers()
    w = _world_with_things()
    MUT._reset_for_tests()
    spawn = Held()
    code, _out = MUT.request(_body(w), now=NOW, mem=w.mem, chats=w.log,
                             gate=Gate(), spawn=spawn)
    check("the mutant flow still raises its card", code == 202, code)
    while spawn.jobs:
        spawn.jobs.pop(0)()
    hid = (MUT.status(NOW).get("confirm") or {}).get("id")
    code, _out = MUT.confirm({"id": hid, "yes": False}, now=NOW, mem=w.mem,
                             chats=w.log, timer=Timers())
    check("MUTANT: with that one guard removed, a `yes: false` deletes (so the "
          "guard is what stops it)", code == 200 and w.row(w.a)["retired_at"] is not None,
          (code, w.row(w.a).get("retired_at")))
    w2 = _world_with_things()
    code, _out = w2.ask(_body(w2))
    check("the real module still offers the card", code == 202, code)
    w2.approve()
    code, out = w2.confirm(yes=False)
    check("the real module REFUSES a non-literal yes, and the list stays held",
          code == 400 and "literal yes" in out.get("error", "")
          and w2.row(w2.a)["retired_at"] is None, out)
    code, _out = w2.confirm(yes=True)
    check("... and its real second yes still acts", code == 200
          and w2.row(w2.a)["retired_at"] is not None)


def _imported_modules(tree) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


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
               and h.sent[1]["large_wipe_items"] == 200
               and h.sent[1]["large_wipe"] is False and h.sent[1]["undo_minutes"] == 10
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
        h = H("/api/memory/forget_range/confirm")
        H.do_GET(h)
        check("GET confirm: 405, use POST", h.sent[0] == 405, h.sent)
        h = H("/api/memory/forget_range/confirm", body=b"{}")
        H.do_POST(h)
        check("POST confirm with no id: 400, and no hold to answer",
              h.sent[0] == 400 and FR.status(NOW)["confirm"] is None, h.sent)
        h = H("/api/memory/forget_range/confirm", body=b"{}", token=False)
        H.do_POST(h)
        check("confirm needs the token like every other POST", h.sent[0] == 401)
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
        FR._timer, real_t = w.timers, FR._timer
        try:
            w.spawn.run()
        finally:
            FR._timer = real_t
        held = (FR.status(NOW)["confirm"] or {}).get("id") or "x"
        h = H("/api/memory/forget_range/confirm",
              body=json.dumps({"id": held, "yes": True}).encode())
        H.do_POST(h)
        check("POST confirm through the route: 200, and only now the fact is retired",
              h.sent[0] == 200 and h.sent[1]["facts_forgotten"] == 1
              and w.row(w.a)["retired_at"] is not None, h.sent)
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
        rewritten = _st.later_rewriting("forget-range.patch", FORGET_RANGE_RISK_LINE, names)
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
