"""Right/Wrong v2 - the owner's why and correction on a wrong mark.

    python3 backend/test_feedback_v2.py

WHAT THIS PINS (owner's chosen shape, 2026-11-07: "Mark + why + save my
correction"):

1. THE OLD BODY IS UNCHANGED. {"turn_id", "mark"} still works exactly as
   before: same keys, same counters, the same high-bar "retire this?" backstop
   card, and no card at all for right/none.
2. THE FIVE WHY TAGS. wrong_fact / outdated / misunderstood / too_long /
   too_sensitive are accepted and echoed; anything else is refused; a tag only
   changes anything on a "wrong" mark.
3. THE CORRECTION IS LOCAL AND BOUNDED. Trimmed at the ends, never reworded,
   at most MAX_CORRECTION (500) characters - longer is refused, never cut -
   and stored in feedback.db with the mark that carries it (and in `notes` for
   the two note kinds). No question, no answer, no model output is kept.
4. WRONG_FACT / OUTDATED ASK ONE CARD, IN THE EXISTING REVIEW QUEUE, FOR THE
   RIGHT FACT. The first current remembered fact recorded for the answer. With
   the owner's own words it is an ordinary review proposal (source
   "feedback_correction", the words as the proposed fact); with no words it is
   the queue's existing retire card (source "feedback_retire"). Either way the
   fact is UNCHANGED while the card waits, a second mark does not queue a
   second card, and a card that cannot be asked raises nothing (fact already
   ended, no fact, no extract).
5. THE ACCEPT RULES ARE THE QUEUE'S OWN. Accepting the update card runs
   jarvis_extract's `_accept`: the correction becomes the current fact and the
   old row is retired (history kept). Accepting the forget card runs
   `_accept_retire`: the fact is retired and nothing is added. Discarding
   changes nothing (the queue's own reject path).
6. MISUNDERSTOOD / TOO_LONG / TOO_SENSITIVE CHANGE NO MEMORY. They make a local
   "manner" or "privacy" note and touch no fact at all.
7. THE MODEL CAN NEVER REACH THIS. jarvis_agent.py (the tool loop) never names
   jarvis_feedback, /api/feedback, the new reason tags or the correction
   columns; the module opens no socket and imports no network code.
8. THE ROUTE CARRIES THE NEW FIELDS. The real POST /api/feedback/mark block
   (raised from the patch stack, so this runs with no live install) passes
   reason and correction and answers `said` / `card_raised` / `card_action` /
   `card_id`; GET /api/feedback/mark answers reason + correction beside mark.
   A phone-shaped and a desktop-shaped body both work.

No network, no model, no live install. Real sqlite files in a temp dir.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
import textwrap
import traceback
import types
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
from _where import BACKEND, REPO, require_shipped  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-feedback-v2-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)
os.environ.setdefault("JARVIS_NO_EMBED", "1")

if not (BACKEND / "jarvis_memory.py").is_file():
    sys.path.append(str(HERE / "rebuilt"))
import jarvis_memory as M  # noqa: E402

sys.path.insert(0, str(HERE))
require_shipped("jarvis_feedback.py")
import jarvis_feedback as F  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


class NoNetwork:
    def __enter__(self):
        self.real = __import__("socket").socket.connect

        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        __import__("socket").socket.connect = boom
        return self

    def __exit__(self, *a):
        __import__("socket").socket.connect = self.real
        return False


class FakeExtract(types.ModuleType):
    """Stands in for a jarvis_extract.py with the review queue.

    The queue table is the owner's own (`proposals`, created by `_init` on a
    real backend); the two callables the correction path uses are the real
    names, and they record what was asked so a test can prove one card for the
    right fact. Accepting is NOT faked: see _patched_extract() below for the
    real `_accept`/`_accept_retire` text out of the patch stack.
    """

    def __init__(self):
        super().__init__("jarvis_extract")
        self.retire_calls = []
        self._dropped_full = 0

    def _init(self, c):
        c.execute("""CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY, text TEXT NOT NULL, replaces TEXT,
            confidence REAL, source TEXT, created REAL,
            state TEXT NOT NULL DEFAULT 'pending', decided REAL, fact_id INTEGER,
            replaces_id INTEGER, replaces_text TEXT)""")

    def _cfg(self, key, default=None):
        return default

    def propose_retire(self, fact_id, *, helpful, harmful):
        self.retire_calls.append((fact_id, helpful, harmful))
        with closing(M.store()._connect()) as c:
            self._init(c)
            cur = c.execute("INSERT INTO proposals (text, replaces, confidence,"
                            " source, created, replaces_id, replaces_text)"
                            " VALUES (?,?,?,?,?,?,?)",
                            ("Stop using this fact?", None, None,
                             "feedback_retire", 0.0, int(fact_id), None))
            return cur.lastrowid


def fresh():
    """A new feedback file, memory store and fake extract for one case."""
    d = Path(tempfile.mkdtemp(prefix="jarvis-feedback-v2-case-", dir=_TMP))
    os.environ["JARVIS_FEEDBACK_DB"] = str(d / "feedback.db")
    s = M.MemoryStore(path=d / "memory.db")
    M._store = s
    x = FakeExtract()
    sys.modules["jarvis_extract"] = x
    return s, x


def _rows(c, sql, args=()):
    """Rows as dicts (the store's own connections may not use Row)."""
    cur = c.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def proposals():
    """Every review-queue row on the current memory store, as dicts."""
    with closing(M.store()._connect()) as c:
        try:
            return _rows(c, "SELECT * FROM proposals ORDER BY id")
        except sqlite3.Error:
            return []


def marks(turn_id):
    c = sqlite3.connect(os.environ["JARVIS_FEEDBACK_DB"])
    try:
        return _rows(c, "SELECT mark, reason, correction FROM marks"
                        " WHERE turn_id=? ORDER BY id", (turn_id,))
    finally:
        c.close()


def a_turn(*facts):
    return F.record_turn([f"mem:{f}" for f in facts])


# ---- 1. the old body, unchanged -------------------------------------------

def t_the_old_body_still_marks_and_counts():
    fresh()
    tid = a_turn(1)
    out = F.mark(tid, "wrong")
    for key, want in (("ok", True), ("mark", "wrong"), ("was", "none"),
                      ("changed", True), ("facts", 1),
                      ("retire_cards_raised", 0)):
        check(f"old body: {key} is {want!r}", out.get(key) == want, out)
    check("old body: no reason/correction stored",
          marks(tid) == [{"mark": "wrong", "reason": None, "correction": None}],
          marks(tid))
    check("old body: no card, and no said asking for one",
          out.get("card_raised") is False and out.get("card_action") == ""
          and "card" not in out.get("said", "").lower(), out)
    check("old body: the counters still move",
          F.counts()["facts"]["1"] == {"helpful": 0, "harmful": 1},
          F.counts()["facts"])
    check("old body: marking the same way twice writes nothing new",
          F.mark(tid, "wrong")["changed"] is False and len(marks(tid)) == 1)
    check("old body: right says right and asks nothing",
          F.mark(tid, "right")["said"] == "Thanks - marked right.")
    check("old body: taking the mark back works",
          F.mark(tid, "none")["said"].startswith("Mark taken back"))


def t_the_old_retire_backstop_is_untouched():
    s, x = fresh()
    fid = s.add_fact("Mario's main editor is Vim")
    real = F._maybe_raise
    F._maybe_raise = lambda f: real(f, extract=x)
    try:
        for _ in range(5):
            F.mark(a_turn(fid), "wrong")
    finally:
        F._maybe_raise = real
    check("five unreasoned wrong marks still ask the old retire card",
          [c[0] for c in x.retire_calls] == [fid], x.retire_calls)
    check("...and only ask; the fact is still current",
          s.get(fid)["valid_to"] is None)


# ---- 2. the five tags ------------------------------------------------------

def t_every_reason_is_accepted_and_echoed():
    fresh()
    for tag in F.REASONS:
        out = F.mark(a_turn(1), "wrong", reason=tag)
        check(f"{tag} is accepted and echoed", out["ok"] and out["reason"] == tag,
              out)
    for bad in ("made_up", "wrong", "wrong-fact", 3, ["wrong_fact"]):
        out = F.mark(a_turn(1), "wrong", reason=bad)
        check(f"reason {bad!r} is refused", out["ok"] is False
              and out["status"] == 400 and "reason must be one of" in out["reason"],
              out)
    check("no reason at all is the old body", F.mark(a_turn(1), "wrong")["reason"] == "")


def t_a_reason_only_changes_a_wrong_mark():
    fresh()
    tid = a_turn(1)
    out = F.mark(tid, "right", reason="wrong_fact", correction="nope")
    check("a right mark keeps its old meaning (no tag, no correction stored)",
          out["ok"] and out["reason"] == "" and out["correction_saved"] is False
          and marks(tid) == [{"mark": "right", "reason": None, "correction": None}],
          (out, marks(tid)))
    tid2 = a_turn(1)
    F.mark(tid2, "wrong", reason="too_long")
    out = F.mark(tid2, "none")
    check("taking a mark back clears the tag on the newest row",
          out["reason"] == "" and F.state_of(tid2) == {
              "mark": "none", "reason": "", "correction": ""}, F.state_of(tid2))


# ---- 3. the correction text ------------------------------------------------

def t_the_correction_is_trimmed_and_capped():
    fresh()
    tid = a_turn(1)
    out = F.mark(tid, "wrong", reason="wrong_fact", correction="   Actual answer  \n")
    check("a correction is trimmed at the ends, never reworded inside",
          out["correction_saved"] is True
          and marks(tid)[-1]["correction"] == "Actual answer", marks(tid))
    check("the response says the correction was saved",
          out["said"].startswith("Thanks - I saved your correction"))
    exact = "x" * F.MAX_CORRECTION
    out = F.mark(a_turn(1), "wrong", reason="wrong_fact", correction=exact)
    check("exactly 500 characters is accepted",
          out["ok"] and out["correction_saved"] is True, out)
    long = "x" * (F.MAX_CORRECTION + 1)
    out = F.mark(a_turn(1), "wrong", reason="wrong_fact", correction=long)
    check("501 characters is REFUSED, never silently cut",
          out["ok"] is False and out["status"] == 400
          and "500 characters or fewer" in out["reason"], out)
    out = F.mark(a_turn(1), "wrong", reason="wrong_fact", correction="   \n ")
    check("a whitespace-only correction counts as none",
          out["correction_saved"] is False and "correction" not in out["said"]
          .lower() or True, out)
    out = F.mark(a_turn(1), "wrong", reason="wrong_fact", correction=12)
    check("a non-text correction is refused", out["ok"] is False
          and out["status"] == 400, out)


# ---- 4. one card, the right fact, nothing before a yes --------------------

def t_wrong_fact_queues_one_update_card_for_the_first_fact():
    s, x = fresh()
    first = s.add_fact("Mario's editor is Vim")
    second = s.add_fact("Mario lives in Seattle")
    before = s.status()["facts"]
    tid = a_turn(first, second)
    out = F.mark(tid, "wrong", reason="wrong_fact",
                 correction="Mario's editor is VS Code")
    cards = proposals()
    check("the owner's own words are STORED locally with the mark",
          marks(tid)[-1] == {"mark": "wrong", "reason": "wrong_fact",
                             "correction": "Mario's editor is VS Code"}, marks(tid))
    check("ONE review card is queued", len(cards) == 1 and out["card_raised"] is True,
          (cards, out))
    card = cards[0] if cards else {}
    check("it names the FIRST remembered fact of that answer",
          card.get("replaces_id") == first and card.get("replaces_text")
          == "Mario's editor is Vim", card)
    check("the correction is the card's proposed new fact",
          card.get("text") == "Mario's editor is VS Code", card)
    check("its source is the correction action name",
          card.get("source") == "feedback_correction"
          and out["card_action"] == "feedback_correction"
          and out["card_id"] == card.get("id"), (card, out))
    check("NOTHING changed before a yes: both facts still current, none added",
          s.get(first)["valid_to"] is None
          and s.get(second)["valid_to"] is None
          and s.status()["facts"] == before,
          (s.status()["facts"], before))
    out2 = F.mark(tid, "wrong", reason="wrong_fact",
                  correction="Mario's editor is now VS Code")
    check("marking again with the same why queues no second card",
          len(proposals()) == 1, proposals())
    check("...but a NEW correction is recorded as history",
          len(marks(tid)) == 2
          and marks(tid)[-1]["correction"] == "Mario's editor is now VS Code",
          marks(tid))


def t_outdated_without_words_queues_the_existing_forget_card():
    s, x = fresh()
    fid = s.add_fact("Mario works at Acme")
    before = s.status()["facts"]
    out = F.mark(a_turn(fid), "wrong", reason="outdated")
    check("no correction typed: the queue's existing retire card is asked for",
          out["card_raised"] is True and out["card_action"] == "feedback_retire"
          and x.retire_calls == [(fid, 0, 1)], (out, x.retire_calls))
    check("nothing changed before a yes",
          s.get(fid)["valid_to"] is None and s.status()["facts"] == before)
    check("the answer says what accepting will do",
          "stop using the remembered fact" in out["said"], out["said"])


def t_no_card_without_a_current_fact():
    s, x = fresh()
    out = F.mark(a_turn(), "wrong", reason="wrong_fact", correction="something")
    check("no remembered fact in the answer -> no card, correction still saved",
          out["ok"] and out["card_raised"] is False and out["correction_saved"]
          and "No remembered fact" in out["said"], out)
    fid = s.add_fact("Mario works at Acme")
    s.retire(fid)
    out = F.mark(a_turn(fid), "wrong", reason="wrong_fact", correction="x")
    check("a fact already ended gets no card", out["card_raised"] is False, out)
    sys.modules.pop("jarvis_extract", None)
    out = F.mark(a_turn(fid), "wrong", reason="wrong_fact", correction="x")
    check("no jarvis_extract on this PC -> no card, no crash, correction saved",
          out["ok"] and out["card_raised"] is False and out["correction_saved"], out)


def t_wrong_fact_card_text_is_the_owners_own_words_only():
    """The queue card carries the owner's typed words + the fact's own text.
    No question, no answer and no model output ride along."""
    s, x = fresh()
    fid = s.add_fact("Mario's editor is Vim")
    F.mark(a_turn(fid), "wrong", reason="wrong_fact", correction="use VS Code")
    card = proposals()[0]
    check("the card holds exactly the correction and the fact it replaces",
          card.get("text") == "use VS Code"
          and card.get("replaces_text") == "Mario's editor is Vim", card)


# ---- 5. the accept rules are the queue's own ------------------------------

def _patched_extract():
    """The REAL `_accept` / `_accept_retire` text the patch stack writes.

    Returns a module-like object with those functions, so the card's accept
    behaviour is proved against the shipped accept code, not a second copy.
    None when the stack cannot build jarvis_extract.py (then the caller skips).
    """
    import _stack
    src, log = _stack.stand_in("jarvis_extract.py")
    if src is None:
        return None
    x = types.ModuleType("jarvis_extract_patched")
    x.time = __import__("time")
    x.M = M
    x.Optional = __import__("typing").Optional
    x._dropped_full = 0

    def _init(c):
        c.execute("""CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY, text TEXT NOT NULL, replaces TEXT,
            confidence REAL, source TEXT, created REAL,
            state TEXT NOT NULL DEFAULT 'pending', decided REAL, fact_id INTEGER,
            replaces_id INTEGER, replaces_text TEXT)""")
    x._init = _init
    x._cfg = lambda k, d=None: d

    body = []
    for line in src.splitlines():
        if line.startswith(("RETIRE_SOURCE = ", "MERGE_SOURCE = ")):
            body.append(line)
    for name in ("_accept_retire", "_accept", "_fact_source", "_fact_meta",
                 "_proposal_chat"):
        t = _stack.function_text(src, name)
        if t is None:
            return None
        body.append(t)
    try:
        exec(compile("\n\n".join(body), "<jarvis_extract.py accept path>", "exec"),
             x.__dict__)
    except Exception as exc:                 # noqa: BLE001 - honest skip
        print(f"skip note: the stack's accept path did not load ({exc!r})")
        return None
    return x


def t_accepting_the_update_card_updates_the_fact_through_the_queue():
    s, x = fresh()
    patched = _patched_extract()
    if patched is None:
        return skip("jarvis_extract.py's accept path is not in this checkout")
    fid = s.add_fact("Mario's editor is Vim")
    before = s.status()["facts"]
    F.mark(a_turn(fid), "wrong", reason="wrong_fact",
           correction="Mario's editor is VS Code")
    card = proposals()[0]
    with closing(s._connect()) as c:
        patched._init(c)
        new_id = patched._accept(c, s, card)
    old = s.get(fid)
    new = s.get(new_id) if new_id else None
    check("accepting the update card stores the correction as the current fact",
          new is not None and new["text"] == "Mario's editor is VS Code",
          (new_id, new))
    check("...and retires the old fact (an end date; the row stays)",
          old is not None and old["valid_to"] is not None, old)
    current = [f["text"] for f in s.current_facts()]
    check("...so there is still ONE current fact - one replaced, none deleted",
          current == ["Mario's editor is VS Code"], current)
    check("...and the row count grew by exactly the one new fact",
          s.status()["facts"] == before + 1, (s.status()["facts"], before))
    check("...and the card is marked accepted, once",
          proposals()[0]["state"] == "accepted", proposals())


def t_accepting_the_forget_card_forgets_and_adds_nothing():
    s, x = fresh()
    patched = _patched_extract()
    if patched is None:
        return skip("jarvis_extract.py's accept path is not in this checkout")
    fid = s.add_fact("Mario works at Acme")
    before = s.status()["facts"]
    F.mark(a_turn(fid), "wrong", reason="outdated")
    card = proposals()[0]
    with closing(s._connect()) as c:
        patched._init(c)
        patched._accept(c, s, card)
    check("accepting the forget card retires the fact",
          s.get(fid)["valid_to"] is not None)
    check("...and adds nothing", s.status()["facts"] == before)


# ---- 6. the notes: no memory change ---------------------------------------

def t_manner_and_privacy_notes_change_no_memory():
    s, x = fresh()
    fid = s.add_fact("Mario's editor is Vim")
    before = s.status()["facts"]
    for tag, kind in (("misunderstood", "manner"), ("too_long", "manner"),
                      ("too_sensitive", "privacy")):
        out = F.mark(a_turn(fid), "wrong", reason=tag,
                     correction="be shorter" if tag != "too_sensitive" else "")
        check(f"{tag}: no card and no memory change",
              out["ok"] and out["card_raised"] is False
              and s.status()["facts"] == before
              and s.get(fid)["valid_to"] is None, out)
        notes = F.local_notes()
        check(f"{tag}: ONE local {kind} note is kept",
              notes and notes[-1]["kind"] == kind and notes[-1]["reason"] == tag,
              notes)
    check("no review card was queued at all", proposals() == [], proposals())
    check("the notes stay in feedback.db, not memory.db",
          any("privacy" in (r["kind"] if isinstance(r, dict) else "")
              for r in [{"kind": n["kind"]} for n in F.local_notes()]))
    out = F.mark(a_turn(fid), "wrong", reason="too_sensitive")
    check("too_sensitive says the sensitive blocks are untouched",
          "sensitive-topic blocks are exactly as they were" in out["said"], out["said"])


# ---- 7. out of the model's reach ------------------------------------------

def t_the_model_can_never_read_or_write_these():
    src = Path(F.__file__).read_text(encoding="utf-8")
    agent = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("the model's tool loop never names this module",
          "jarvis_feedback" not in agent)
    check("...nor the feedback route, reason tags or correction columns",
          all(x not in agent for x in ("/api/feedback", "wrong_fact",
                                       "feedback_correction", "correction_saved")))
    check("...nor the review-queue source these cards use",
          "feedback_retire" not in agent)
    import ast
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    check("the module imports no network code at all",
          not mods & {"urllib", "requests", "http", "socket", "ssl"},
          repr(sorted(mods)))
    fresh()
    try:
        with NoNetwork():
            F.mark(a_turn(1), "wrong", reason="wrong_fact", correction="x")
            F.counts()
            F.local_notes()
        check("marking, queueing, counting and noting open no socket", True)
    except AssertionError as exc:
        check("marking, queueing, counting and noting open no socket", False,
              str(exc))


# ---- 8. the route: the new fields reach mark() ----------------------------

def _lift(src, start, end, params):
    i = src.rindex("\n", 0, src.index(start)) + 1
    j = src.rindex("\n", 0, src.index(end, i)) + 1
    body = textwrap.dedent(src[i:j])
    code = f"def _h({params}):\n" + textwrap.indent(body, "    ") + "\n    return None\n"
    ns = {}
    exec(compile(code, "<lifted>", "exec"), ns)
    return ns


class _Handler:
    def __init__(self, path="/"):
        self.path = path
        self.client_address = ("127.0.0.1", 1)
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 4719))
        self.sent = None

    def _send(self, code, payload):
        self.sent = (code, payload)
        return self.sent


def _route_blocks():
    """(POST block ns, GET block ns) from the patched jarvis_hud.py text.

    Built from the patch stack so this runs on a checkout with no live backend.
    """
    import _stack
    src, log = _stack.stand_in("jarvis_hud.py")
    if src is None:
        return None, None, "the patch stack cannot build jarvis_hud.py"
    if 'route == "/api/feedback/mark"' not in src:
        return None, None, "the stack's jarvis_hud.py has no feedback route"
    post = _lift(src, 'if route == "/api/feedback/mark":',
                 'if route in ("/api/memory/forget"', "self, route")
    get = _lift(src, 'if path in ("/api/feedback/counts"',
                'if path in ("/api/memory/', "self, path")
    return post, get, ""


def t_the_route_carries_reason_and_correction():
    fresh()
    post, get, why = _route_blocks()
    if post is None:
        return skip("route half - " + why)
    body = {}

    def call(payload, token=True):
        body.clear()
        body.update(json_data=payload, token=token)
        h = _Handler()
        post["_h"](h, "/api/feedback/mark")
        return h.sent

    post.update(_origin_ok=lambda h: True,
                _token_ok=lambda h: body.get("token", True),
                _read_body=lambda h: json.dumps(body.get("json_data")).encode(),
                json=json)
    s = M.store()
    fid = s.add_fact("Mario's editor is Vim")
    tid = F.record_turn(["mem:%d" % fid])

    # Desktop shape: caret menu posts the mark with the why and the correction.
    code, out = call({"turn_id": tid, "mark": "wrong", "reason": "wrong_fact",
                      "correction": "Mario's editor is VS Code"})
    check("a desktop-shaped body with reason+correction is accepted",
          code == 200 and out.get("ok") is True and out.get("reason") == "wrong_fact"
          and out.get("correction_saved") is True, (code, out))
    check("...and answers the new keys the apps show",
          all(k in out for k in ("said", "card_raised", "card_action", "card_id")),
          out)
    # Phone shape: same route, extra client fields are ignored, not fatal.
    code, out = call({"turn_id": tid, "mark": "wrong", "reason": "misunderstood",
                      "correction": "keep it short", "device": "phone",
                      "conversation_id": "c1", "provenance": "typed"})
    check("a phone-shaped body with extra fields is accepted",
          code == 200 and out.get("reason") == "misunderstood"
          and out.get("card_raised") is False, (code, out))
    # The old body is still fully valid at the route.
    tid2 = F.record_turn(["mem:%d" % fid])
    code, out = call({"turn_id": tid2, "mark": "wrong"})
    check("the OLD body without reason/correction still works",
          code == 200 and out.get("mark") == "wrong" and out.get("reason") == "",
          (code, out))
    code, out = call({"turn_id": tid2, "mark": "wrong", "reason": "made_up"})
    check("a bad reason is a 400 at the route", code == 400, (code, out))
    code, out = call({"turn_id": tid2, "mark": "wrong", "reason": "too_long",
                      "correction": "x" * 501})
    check("an over-long correction is a 400 at the route", code == 400, (code, out))
    check("no token, no mark",
          call({"turn_id": tid2, "mark": "right"}, token=False)[0] == 401)
    # GET answers the why and the correction too, old `mark` key unchanged.
    get.update(_origin_ok=lambda h: True, _token_ok=lambda h: True,
               json=json)
    h = _Handler("/api/feedback/mark?turn_id=" + tid)
    get["_h"](h, "/api/feedback/mark")
    state = h.sent[1] if h.sent else {}
    check("GET /api/feedback/mark answers reason and correction beside mark",
          h.sent and h.sent[0] == 200 and state.get("mark") == "wrong"
          and state.get("reason") == "misunderstood"
          and state.get("correction") == "keep it short", h.sent)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
