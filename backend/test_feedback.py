"""A right/wrong mark per answer, and the helpful/harmful counts it feeds.

    python3 test_feedback.py

No pytest, no network, no model. Real sqlite files in a temp dir.

Items 1 and 8 of docs/LEARNING-RESEARCH-2026-09-23.md. What is being pinned,
in the order the owner's rules put it:

1. ONLY IDS ARE KEPT. An answer is recorded as a random id, a time, and the
   ids of the facts that went into it. No text column exists to hold a
   question or an answer, and ids that are not a stored fact are dropped.
2. ONE ANSWER, ONE MARK. mark() takes one turn id. A list is refused, not
   iterated. Marking again replaces the mark (the old row is kept as
   history), and only the newest mark counts.
3. THE COUNTERS MOVE ONLY ON THE OWNER'S MARKS - they are counted from the
   marks table, with nowhere else to write them.
4. NOTHING RETIRES ITSELF. Crossing the (high) line raises ONE card in the
   ordinary review queue, never a second for the same evidence, and the fact
   stays current until the owner accepts that card. Discarding it keeps the
   fact exactly as it was.
5. NOTHING LEAVES THE MACHINE, AND THE MODEL CANNOT MARK. No socket opens;
   jarvis_agent.py's tool loop never names this module.

Parts 1-5 run anywhere: jarvis_feedback.py ships in this repository. The
review-queue half needs jarvis_extract.py WITH feedback.patch applied, and
the route half needs jarvis_hud.py with it applied; each skips honestly when
the file is absent and FAILS when the file is there without the patch.
"""
import json, os, socket, sys, tempfile, textwrap, time, traceback, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, explain

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-feedback-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)
os.environ.setdefault("JARVIS_NO_EMBED", "1")

# jarvis_memory: the backend's own if there is one, otherwise the rebuilt copy
# in this repository - it is only used here as a real store to hold facts.
if missing("jarvis_memory.py"):
    sys.path.append(str(HERE / "rebuilt"))
import jarvis_memory as M

# jarvis_feedback is OURS: this directory first, so a stale copy in a backend
# folder cannot shadow the one being tested.
sys.path.insert(0, str(HERE))
# On a real install (JARVIS_BACKEND set), the backend's own copy must be
# there and be this one - see _where.require_shipped.
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_feedback.py")
import jarvis_feedback as F

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    """Any socket at all, in this block, is a failure."""

    def __enter__(self):
        self.real = socket.socket.connect
        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


def fresh():
    """A new feedback file and a new memory store for each test."""
    d = Path(tempfile.mkdtemp(prefix="jarvis-feedback-case-", dir=_TMP))
    os.environ["JARVIS_FEEDBACK_DB"] = str(d / "feedback.db")
    s = M.MemoryStore(path=d / "memory.db")
    M._store = s
    return s


class FakeExtract:
    """Stands in for jarvis_extract where only the CALL matters."""

    def __init__(self, answer=None):
        self.calls = []
        self.answer = answer
        self._next = 100

    def propose_retire(self, fact_id, *, helpful, harmful):
        self.calls.append((fact_id, helpful, harmful))
        if self.answer is not None:
            return self.answer
        self._next += 1
        return self._next


def answers(n, facts, mark):
    """n answers that each used `facts`, each marked `mark`."""
    for _ in range(n):
        tid = F.record_turn([f"mem:{f}" for f in facts])
        out = F.mark(tid, mark)
        assert out["ok"], out


# ---- 1. only ids ------------------------------------------------------------

def t_only_ids_are_kept():
    fresh()
    with NoNetwork():
        tid = F.record_turn(["mem:12", "mem:12", "fact:3", "mem:7",
                             "Mario is allergic to penicillin", "mem:1; DROP TABLE x",
                             42, None])
    check("a turn id is 32 hex characters", len(tid) == 32 and int(tid, 16) >= 0, tid)
    import sqlite3
    c = sqlite3.connect(os.environ["JARVIS_FEEDBACK_DB"])
    try:
        items = sorted(r[0] for r in c.execute("SELECT item FROM turn_items"))
        cols = {t: [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
                for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        dump = "\n".join(c.iterdump())
    finally:
        c.close()
    check("only stored-fact ids are kept, each once", items == ["mem:12", "mem:7"], repr(items))
    check("a list-position id (fact:N) is dropped - it points at a different "
          "fact once the list changes", "fact:3" not in items)
    check("free text handed in as an id is not stored",
          "penicillin" not in dump and "DROP TABLE" not in dump)
    allowed = {"turn_id", "created", "item", "id", "mark", "marked", "fact_id",
               "proposal_id", "helpful", "harmful", "raised"}
    extra = {t: [x for x in v if x not in allowed] for t, v in cols.items()}
    check("no table has a column that could hold a question or an answer",
          not any(extra.values()), repr(extra))
    many = F.record_turn([f"mem:{i}" for i in range(500)])
    c = sqlite3.connect(os.environ["JARVIS_FEEDBACK_DB"])
    try:
        n = c.execute("SELECT COUNT(*) FROM turn_items WHERE turn_id=?", (many,)).fetchone()[0]
    finally:
        c.close()
    check("a malformed header cannot write hundreds of rows",
          n == F.MAX_ITEMS_PER_TURN, f"{n} rows")


# ---- 2. one answer, one mark -----------------------------------------------

def t_one_answer_one_mark():
    fresh()
    tid = F.record_turn(["mem:1"])
    out = F.mark(tid, "wrong")
    check("a mark on a known answer is accepted", out["ok"] and out["mark"] == "wrong", repr(out))
    check("the mark says how many facts that answer used", out["facts"] == 1, repr(out))
    out = F.mark(tid, "wrong")
    check("marking the same way twice changes nothing", out["ok"] and out["changed"] is False)
    check("and counts once, not twice", F.counts()["facts"]["1"]["harmful"] == 1,
          repr(F.counts()["facts"]))
    F.mark(tid, "right")
    n = F.counts()["facts"]["1"]
    check("changing the mark moves BOTH counts - only the newest mark counts",
          n == {"helpful": 1, "harmful": 0}, repr(n))
    F.mark(tid, None)
    check("a mark can be taken back", "1" not in F.counts()["facts"]
          and F.mark_of(tid) == "none", repr(F.counts()["facts"]))
    import sqlite3
    c = sqlite3.connect(os.environ["JARVIS_FEEDBACK_DB"])
    try:
        hist = [r[0] for r in c.execute("SELECT mark FROM marks WHERE turn_id=? ORDER BY id", (tid,))]
    finally:
        c.close()
    check("the history of the mark is kept, not overwritten",
          hist == ["wrong", "right", "none"], repr(hist))

    lst = F.mark([tid, tid], "wrong")
    check("a LIST of answers is refused, not iterated - there is no mark-all",
          lst["ok"] is False and lst["status"] == 400, repr(lst))
    check("an unknown answer is a 404, not a silent success",
          F.mark("0" * 32, "wrong")["status"] == 404)
    check("an unknown mark is refused", F.mark(tid, "meh")["status"] == 400)
    check("a malformed id is refused", F.mark("../../etc", "wrong")["status"] == 400)
    check("mark_of an unknown answer is None", F.mark_of("f" * 32) is None)


# ---- 3. the counters -------------------------------------------------------

def t_counters_are_counted_from_marks():
    fresh()
    answers(2, [1, 2], "right")
    answers(3, [2], "wrong")
    F.record_turn(["mem:3"])               # used, never marked
    c = F.counts()
    check("helpful/harmful per fact", c["facts"] == {
        "1": {"helpful": 2, "harmful": 0}, "2": {"helpful": 2, "harmful": 3}},
        repr(c["facts"]))
    check("an answer nobody marked moves no counter", "3" not in c["facts"])
    check("the tally of marked answers", c["answers_marked"] == {"right": 2, "wrong": 3},
          repr(c["answers_marked"]))
    nid = F.note_id("email-triage", "  Always   check the sender first ")
    check("a skill note gets a stable id from its words",
          nid == F.note_id("email-triage", "Always check the sender first")
          and nid.startswith("note:email-triage:"), nid)
    tid = F.record_turn(["mem:1"], notes=[nid])
    F.mark(tid, "wrong")
    check("skill notes are counted too, apart from facts",
          F.counts()["skill_notes"] == {nid: {"helpful": 0, "harmful": 1}},
          repr(F.counts()["skill_notes"]))
    check("no counter column exists for anything else to write to",
          "UPDATE" not in Path(F.__file__).read_text(encoding="utf-8"),
          "an UPDATE in jarvis_feedback.py would be a second way to move a count")


# ---- 4. the "retire this?" card --------------------------------------------

def t_the_threshold_is_high():
    s = F.should_raise
    check("4 wrong answers is not enough", s(0, 4) is False)
    check("5 wrong, 0 right crosses it", s(0, 5) is True)
    check("5 wrong against 2 right does not - wrong must be 3x right", s(2, 5) is False)
    check("6 wrong against 2 right does", s(2, 6) is True)
    check("the numbers are the documented ones",
          (F.RETIRE_MIN_WRONG, F.RETIRE_RATIO) == (5, 3))


def t_one_card_never_a_retirement():
    s = fresh()
    fid = s.add_fact("Mario's main editor is Vim")
    other = s.add_fact("Mario drives a 1998 Volvo")
    x = FakeExtract()
    real = F._maybe_raise
    F._maybe_raise = lambda f: real(f, extract=x)
    try:
        answers(4, [fid, other], "wrong")
        check("four wrong answers ask nothing", x.calls == [], repr(x.calls))
        answers(2, [other], "right")
        answers(1, [fid, other], "wrong")
        check("the fifth wrong answer raises exactly one card, for the fact "
              "that crossed", [c[0] for c in x.calls] == [fid], repr(x.calls))
        check("the card carries the counts", x.calls[0][1:] == (0, 5), repr(x.calls))
        answers(1, [fid], "wrong")
        check("the next wrong answer does not raise a second card",
              len(x.calls) == 1, repr(x.calls))
        answers(1, [fid], "right")
        check("a right mark never raises anything", len(x.calls) == 1)
        check("the fact is still current - a mark never retires anything",
              s.get(fid)["valid_to"] is None)
        answers(4, [fid], "wrong")
        check("only after five MORE wrong answers is it asked again",
              [c[0] for c in x.calls] == [fid, fid] and x.calls[1][2] == 10,
              repr(x.calls))
    finally:
        F._maybe_raise = real


def t_no_card_when_it_cannot_be_asked():
    s = fresh()
    fid = s.add_fact("Mario's main editor is Vim")
    real = F._maybe_raise
    x = FakeExtract(answer=None)
    x.answer = 0                                 # queue full / already waiting
    F._maybe_raise = lambda f: real(f, extract=x)
    try:
        answers(5, [fid], "wrong")
        check("a refused card is asked for", len(x.calls) == 1, repr(x.calls))
        x.answer = None
        answers(1, [fid], "wrong")
        check("...and asked for AGAIN next time, because it was never raised",
              len(x.calls) == 2, repr(x.calls))
    finally:
        F._maybe_raise = real

    s = fresh()
    fid = s.add_fact("Mario's main editor is Vim")
    s.retire(fid)
    x = FakeExtract()
    F._maybe_raise = lambda f: real(f, extract=x)
    try:
        answers(5, [fid], "wrong")
        check("a fact already retired gets no card", x.calls == [], repr(x.calls))
    finally:
        F._maybe_raise = real

    s = fresh()
    fid = s.add_fact("Mario's main editor is Vim")
    old = types.SimpleNamespace()                # jarvis_extract WITHOUT the patch
    F._maybe_raise = lambda f: real(f, extract=old)
    try:
        answers(5, [fid], "wrong")
        check("an unpatched jarvis_extract means no card, and no error", True)
    except Exception as exc:
        check("an unpatched jarvis_extract means no card, and no error", False, repr(exc))
    finally:
        F._maybe_raise = real


# ---- 5. local only, and out of the model's reach ---------------------------

def t_nothing_leaves_and_the_model_cannot_mark():
    s = fresh()
    fid = s.add_fact("Mario's main editor is Vim")
    real = F._maybe_raise
    x = FakeExtract()
    F._maybe_raise = lambda f: real(f, extract=x)
    try:
        with NoNetwork():
            answers(6, [fid], "wrong")
            F.counts()
        check("recording, marking, counting and raising a card open no socket", True)
    except AssertionError as exc:
        check("recording, marking, counting and raising a card open no socket", False, str(exc))
    finally:
        F._maybe_raise = real
    agent = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("the model's tool loop never names this module",
          "jarvis_feedback" not in agent and "/api/feedback" not in agent)
    src = Path(F.__file__).read_text(encoding="utf-8")
    import ast
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    check("the module imports no network code at all",
          not mods & {"urllib", "requests", "http", "socket", "ssl", "urllib3"},
          repr(sorted(mods)))
    check("and never retires or deletes anything itself",
          ".retire(" not in src and "DELETE" not in src)


# ---- the review-queue half: jarvis_extract with feedback.patch --------------

def t_the_card_goes_through_the_review_queue():
    if missing("jarvis_extract.py"):
        return check("SKIP review-queue half - " + explain(), True)
    import jarvis_extract as X
    if not hasattr(X, "propose_retire"):
        return check("jarvis_extract has propose_retire - feedback.patch is applied",
                     False, "the file is there without the patch")
    s = fresh()
    fid = s.add_fact("Mario's main editor is Vim")
    before = s.status()["facts"]
    answers(5, [fid], "wrong")
    cards = [p for p in X.pending() if p.get("source") == X.RETIRE_SOURCE]
    check("five wrong answers put ONE card in the ordinary review queue",
          len(cards) == 1, repr(X.pending()))
    if not cards:
        return
    card = cards[0]
    check("the card names the fact, where every card names what it would retire",
          card["replaces_id"] == fid and card["replaces_text"] == "Mario's main editor is Vim",
          repr(card))
    check("the card says what accepting does, and that nothing is deleted",
          "retires" in card["text"] and "history" in card["text"], card["text"])
    check("the fact is still current while the card waits", s.get(fid)["valid_to"] is None)
    check("a second card for the same fact is not queued while one waits",
          X.propose_retire(fid, helpful=0, harmful=9) is None)

    check("discarding the card is a normal reject", X.decide(card["id"], False) == 0)
    check("...and the fact is untouched", s.get(fid)["valid_to"] is None)

    answers(5, [fid], "wrong")
    card2 = [p for p in X.pending() if p.get("source") == X.RETIRE_SOURCE]
    check("five MORE wrong answers ask again", len(card2) == 1, repr(X.pending()))
    got = X.decide(card2[0]["id"], True)
    check("accepting returns the retired fact's id", got == fid, repr(got))
    f = s.get(fid)
    check("accepting RETIRES the fact - an end date, the row is still there",
          f is not None and f["valid_to"] is not None)
    check("and adds nothing: the card's sentence did not become a fact",
          s.status()["facts"] == before
          and not any("Stop using" in (r.get("text") or "") for r in s.current_facts()),
          f"{s.status()['facts']} facts, was {before}")
    check("a decided card cannot be decided again", X.decide(card2[0]["id"], True) is None)

    # CONTROL: an ordinary correction still works exactly as before.
    reply = json.dumps({"facts": [{"text": "Mario's main editor is VS Code now",
                                   "confidence": 0.9}]})
    rows = X.propose([{"role": "user", "content": "hi"}], llm=lambda _p: reply)
    if rows:
        new = X.decide(rows[0]["id"], True)
        check("CONTROL an ordinary proposal still becomes a fact",
              bool(new) and s.get(new)["text"] == "Mario's main editor is VS Code now")
    else:
        check("CONTROL an ordinary proposal still becomes a fact", False, "nothing proposed")

    s = fresh()
    fid = s.add_fact("Mario prefers tabs over spaces in Go")
    keep = X._cfg
    X._cfg = lambda k, d=None: {"review_queue_max": 0}.get(k, d)
    try:
        dropped = X._dropped_full
        check("a full queue queues no card", X.propose_retire(fid, helpful=0, harmful=5) is None)
        check("...and counts it like any dropped proposal", X._dropped_full == dropped + 1)
    finally:
        X._cfg = keep


# ---- the route half: jarvis_hud.py with feedback.patch ---------------------

def _lift(src, start, end, params):
    """One block of the handler, as a callable. Indented one level deeper
    than it sits in do_GET/do_POST, so `return` works."""
    i = src.rindex("\n", 0, src.index(start)) + 1     # from the line's start
    j = src.rindex("\n", 0, src.index(end, i)) + 1
    body = textwrap.dedent(src[i:j])
    code = f"def _h({params}):\n" + textwrap.indent(body, "    ") + "\n    return None\n"
    ns = {}
    exec(compile(code, "<lifted>", "exec"), ns)
    return ns


class _Handler:
    def __init__(self, path="/"):
        self.path = path
        self.sent = None

    def _send(self, code, payload):
        self.sent = (code, payload)
        return self.sent


def t_the_routes():
    if missing("jarvis_hud.py"):
        return check("SKIP route half - " + explain(), True)
    src = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    if 'route == "/api/feedback/mark"' not in src:
        return check("jarvis_hud.py carries /api/feedback/mark - feedback.patch is applied",
                     False, "the file is there without the patch")
    fresh()
    post = _lift(src, 'if route == "/api/feedback/mark":',
                 'if route in ("/api/memory/forget"', "self, route")
    body = {}
    post.update(_origin_ok=lambda h: True, _token_ok=lambda h: body.get("token", True),
                _read_body=lambda h: json.dumps(body.get("json")).encode(), json=json)

    def call(payload, token=True):
        body.clear(); body.update(json=payload, token=token)
        h = _Handler()
        post["_h"](h, "/api/feedback/mark")
        return h.sent

    tid = F.record_turn(["mem:4"])
    check("no token, no mark", call({"turn_id": tid, "mark": "wrong"}, token=False)[0] == 401)
    code, out = call({"turn_id": tid, "mark": "wrong"})
    check("POST /api/feedback/mark marks one answer", code == 200 and out["mark"] == "wrong",
          repr((code, out)))
    code, out = call({"turn_id": [tid], "mark": "wrong"})
    check("a list of turn ids is a 400 at the route too", code == 400, repr((code, out)))
    check("an unknown answer is a 404 at the route", call({"turn_id": "a" * 32,
                                                          "mark": "right"})[0] == 404)
    check("a non-object body is refused", call(["x"])[0] == 400)
    block = src[src.index('if route == "/api/feedback/mark":'):
                src.index('if route in ("/api/memory/forget"')]
    check("the route has no list form", '"ids"' not in block and "turn_ids" not in block)

    get = _lift(src, 'if path in ("/api/feedback/counts"',
                'if path in ("/api/memory/pending"', "self, path")
    get.update(_origin_ok=lambda h: True, _token_ok=lambda h: True)
    h = _Handler("/api/feedback/counts")
    get["_h"](h, "/api/feedback/counts")
    check("GET /api/feedback/counts serves the counters",
          h.sent[0] == 200 and h.sent[1]["facts"] == {"4": {"helpful": 0, "harmful": 1}},
          repr(h.sent))
    h = _Handler(f"/api/feedback/mark?turn_id={tid}")
    get["_h"](h, "/api/feedback/mark")
    check("GET /api/feedback/mark?turn_id= reads one answer's mark",
          h.sent == (200, {"turn_id": tid, "mark": "wrong"}), repr(h.sent))
    get["_token_ok"] = lambda h: False
    h = _Handler("/api/feedback/counts")
    get["_h"](h, "/api/feedback/counts")
    check("the counts are behind the token", h.sent[0] == 401)

    hook = _lift(src, "# feedback.patch: give this answer", "if use_tools:", "route_header")
    rh = {"injected_ids": ["mem:9", "fact:2"], "lane": "local"}
    hook["_h"](rh)
    check("every answered chat turn gets a turn_id in X-Jarvis-Route",
          isinstance(rh.get("turn_id"), str) and len(rh["turn_id"]) == 32, repr(rh))
    check("...recorded against the facts that answer used",
          F.mark(rh["turn_id"], "right")["facts"] == 1)
    broken = types.ModuleType("jarvis_feedback")
    def boom(*a, **k):
        raise RuntimeError("disk full")
    broken.record_turn = boom
    sys.modules["jarvis_feedback"] = broken
    try:
        rh = {"injected_ids": ["mem:9"]}
        hook["_h"](rh)
        check("a failure to record never breaks the answer", "turn_id" not in rh)
    except Exception as exc:
        check("a failure to record never breaks the answer", False, repr(exc))
    finally:
        sys.modules["jarvis_feedback"] = F
    i = src.index("# feedback.patch: give this answer")
    check("the id is recorded AFTER the degrade loop, so a turn that left the "
          "local lane records no facts",
          src.rfind("for _hop in", 0, i) != -1 or "_degrade_hops" not in src)


def _pending_route_from_patch():
    """The GET /api/memory/pending block as feedback.patch leaves it - the
    new side of the hunk that starts on that route's `if path ==` line.
    Every line of that hunk's context is memory-pane.patch's own output, so
    this is the real text, not a copy of it."""
    lines = (REPO / "backend" / "feedback.patch").read_text(encoding="utf-8").splitlines()
    out, on = [], False
    for l in lines:
        if l.startswith("@@"):
            if on:
                break
            continue
        if not on and l == '                 if path == "/api/memory/pending":':
            on = True
        if on and not l.startswith("-"):
            out.append(l[1:])
    # A newline first: _lift() finds the start of the line by looking back
    # for one.
    return "\n" + "\n".join(out) + "\n"


def _check_pending_route(src, where):
    """A "retire this?" card only reaches a client that asks for it."""
    get = _lift(src, 'if path == "/api/memory/pending":',
                'if path == "/api/memory/facts":', "self, path")
    rows = [{"id": 1, "text": "I like oat milk", "source": "conversation"},
            {"id": 2, "text": "Stop using this fact? ...", "source": "feedback_retire",
             "replaces_id": 7}]
    get["jarvis_extract"] = types.SimpleNamespace(
        pending=lambda: [dict(r) for r in rows], setup_status=lambda: {},
        RETIRE_SOURCE="feedback_retire")
    get["jarvis_sleep"] = types.SimpleNamespace(reminder_card=lambda: None)

    def ids(url):
        h = _Handler(url)
        get["_h"](h, "/api/memory/pending")
        return [r["id"] for r in h.sent[1]["pending"]] if h.sent else None

    check(f"{where}: a client that does not ask never sees a retire card "
          "(its 'Keep' button would retire the fact)",
          ids("/api/memory/pending") == [1], repr(ids("/api/memory/pending")))
    check(f"{where}: ?retire_cards=0 or anything but 1 is the same as not asking",
          ids("/api/memory/pending?retire_cards=0") == [1]
          and ids("/api/memory/pending?retire_cards=yes") == [1])
    check(f"{where}: ?retire_cards=1 shows it, beside the ordinary cards",
          ids("/api/memory/pending?retire_cards=1") == [1, 2],
          repr(ids("/api/memory/pending?retire_cards=1")))


def t_retire_cards_only_for_a_client_that_asks():
    _check_pending_route(_pending_route_from_patch(), "the patch")
    if missing("jarvis_hud.py"):
        return check("SKIP the same on jarvis_hud.py - " + explain(), True)
    src = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    if 'if path == "/api/memory/pending":' not in src:
        return check("SKIP the same on jarvis_hud.py - it has no memory pane route "
                     "(memory-pane.patch is not applied)", True)
    if "retire_cards" not in src:
        return check("jarvis_hud.py hides retire cards - feedback.patch is applied",
                     False, "the file is there without this part of the patch")
    _check_pending_route(src, "jarvis_hud.py")


def t_the_stack_lists_the_patch():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 applies feedback.patch", "'feedback.patch'" in ps1)
    check("and after decide-once and tool-calling-wiring, whose output it "
          "anchors on",
          ps1.index("'feedback.patch'") > ps1.index("'decide-once.patch'")
          and ps1.index("'feedback.patch'") > ps1.index("'tool-calling-wiring.patch'"))


if __name__ == "__main__":
    for fn in (t_only_ids_are_kept, t_one_answer_one_mark, t_counters_are_counted_from_marks,
               t_the_threshold_is_high, t_one_card_never_a_retirement,
               t_no_card_when_it_cannot_be_asked, t_nothing_leaves_and_the_model_cannot_mark,
               t_the_card_goes_through_the_review_queue, t_the_routes,
               t_retire_cards_only_for_a_client_that_asks,
               t_the_stack_lists_the_patch):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
