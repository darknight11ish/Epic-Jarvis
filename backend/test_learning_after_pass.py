"""test_learning_after_pass.py - a learning pass may not be killed by the
notes-table migration (LEARNING-ZERO-FACTS).

    python3 backend/test_learning_after_pass.py

THE LIVE SYMPTOM THIS PINS. The HUD's learning card showed learning ON,
`facts_total` 0 and `failed` 8, and `/api/memory/learning` carried
`"last_error": "after_pass: OperationalError"`. That exact string is written
by `jarvis_auto_learn.note_failure("after_pass", exc)` from anything that
escapes `after_pass`, so the one place to look is the work it does inside
its own `try:`. On the card path that work includes `_note_card()` ->
`_init_notes()`, which migrates `auto_learn_notes` with `ALTER TABLE ...
ADD COLUMN`.

WHAT IS PROVED HERE, against a real `MemoryStore` in a temporary folder:

  * a NEW notes table is created with every column the code then inserts,
    so a first install runs no ALTER at all - which is also the migration
    that the next thread can collide with;
  * an OLD notes table plus the STALE first read that two writers (the
    learner's pass and a `/api/memory/pending` read, which annotates cards
    through `card_notes()`) can produce: the pass still writes its card and
    reports it, instead of dying with
    `sqlite3.OperationalError: duplicate column name` and recording
    `after_pass: OperationalError`;
  * the guard is NARROW - a real failure (`database is locked`, a missing
    table) still raises, so a genuinely broken database cannot pass for
    "nothing to learn".

The SAVING path is not re-proved here (a fact is saved, not carded):
`backend/test_auto_learn.py` covers it end to end, and this suite's change
does not touch it.

No network, no model, no owner files: the real `after_pass` and the real
`jarvis_memory.MemoryStore` against temporary databases, the sensitive
layer's model question answered "not sensitive" the way the other suites do
it, and the learning counters pointed at this suite's own folder.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
import types
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_auto_learn.py", "jarvis_sensitive.py",
                "rebuilt/jarvis_memory.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-after-pass-"))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_TMP / "config"))

# jarvis_framework owns where the settings/stats files go; a stand-in keeps
# every write inside _TMP. The audit sink is a no-op: this suite is about the
# exception, not the log line.
fw = sys.modules.get("jarvis_framework")
if fw is None:
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = _TMP / "config"
    fw.LOG_DIR = _TMP
    fw.load_framework = lambda: {}
    fw.audit_log = lambda *a, **k: None
    fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = fw

try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M
import jarvis_auto_learn as A  # noqa: E402
import jarvis_sensitive as S  # noqa: E402

# The sensitive-topic check's optional second layer asks the learner's model.
# No model runs here; this is the stand-in the other suites use.
S.ASK_MODEL = lambda prompt: '{"sensitive": false, "category": "none"}'

PASSED, FAILED = [], []
LOCAL = "http://127.0.0.1:11434"
MODEL = "qwen3:8b"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------- a world ---

def _proposals(c):
    """The review queue as jarvis_extract leaves it."""
    c.execute("""CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY, text TEXT NOT NULL, replaces TEXT,
        confidence REAL, source TEXT, created REAL,
        state TEXT NOT NULL DEFAULT 'pending', decided REAL, fact_id INTEGER,
        replaces_id INTEGER, replaces_text TEXT)""")


_OLD_NOTES = """CREATE TABLE auto_learn_notes (
    proposal_id INTEGER PRIMARY KEY, reason TEXT, provenance TEXT, at REAL)"""


def _world(tag):
    """A scratch store, and a stats file of its own so one case's failure
    counter cannot decide another's."""
    st = M.MemoryStore(_TMP / f"memory-{tag}.db", embedder=M.HashEmbedder())
    keep_store = getattr(M, "_store", None)
    keep_stats = A.stats_path
    M._store = st
    A.stats_path = lambda: _TMP / f"stats-{tag}.json"
    with closing(st._connect()) as c:
        _proposals(c)
    return st, keep_store, keep_stats


def _done(keep_store, keep_stats):
    M._store = keep_store
    A.stats_path = keep_stats


def _queue(st, text="The owner lives in York"):
    with closing(st._connect()) as c:
        cur = c.execute("INSERT INTO proposals (text, replaces, confidence, source,"
                        " created, replaces_id, replaces_text) VALUES (?,?,?,?,?,?,?)",
                        (text, None, 0.9, "conversation", 1790000000.0, None, None))
        return {"id": cur.lastrowid, "text": text, "replaces": None,
                "replaces_id": None, "confidence": 0.9, "state": "pending"}


class _CannotSave:
    """accept_auto that saves nothing, so the proposal stays a CARD - the path
    that writes a note, which is where the live failure happened."""

    def accept_auto(self, *_a, **_k):
        return None


def _pass(st, proposal, text="I live in York", extract=None):
    """One learning pass over one pending proposal. The turn is not in a chat
    log this PC recorded, so the fact is carded (a reason is noted); nothing
    here needs a chat history, a model or the network. The model/URL are named
    only so the "is the learning model local?" check passes, exactly as the
    HUD passes it."""
    A._reset_for_tests()
    return A.after_pass([proposal], [{"role": "user", "content": text}],
                        conversation_id=None, model=MODEL, ollama=LOCAL,
                        learning_on=True, extract=extract or _CannotSave(),
                        publish=lambda ids: None)


class _Counting:
    """A connection that records every ALTER TABLE the code runs through it.

    `close()` is deliberately a no-op: after_pass borrows the store's
    connection for short reads too (`like_forgotten` does `with
    closing(store._connect())`), and closing the one real handle under it
    would make the next statement a ProgrammingError rather than exercising
    the migration."""

    def __init__(self, real):
        self._real = real
        self.alters = []

    def execute(self, sql, *args):
        if sql.lstrip().upper().startswith("ALTER TABLE"):
            self.alters.append(sql)
        return self._real.execute(sql, *args)

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._real, name)


class _Stale:
    """A connection that answers the FIRST `PRAGMA table_info(auto_learn_notes)`
    with the column list read BEFORE the other writer migrated the table, then
    passes everything else straight through.

    That is the interleaving two writers produce on an old database, made
    deterministic: both read "no sensitive"; the other one ALTERs first; this
    one ALTERs the column that now exists. It is the same race
    `jarvis_memory._init()` documents and handles for `facts.retired_at`
    ("Measured with eight processes released at the same instant: a failure
    in 2 trials of 8, only on the ONE run that migrates an old database -
    which is the owner's upgrade path")."""

    def __init__(self, real, stale_cols):
        self._real = real
        self._stale = stale_cols
        self._served = False

    def execute(self, sql, *args):
        cur = self._real.execute(sql, *args)
        if (not self._served
                and "table_info(auto_learn_notes)" in sql.replace(" ", "").lower()):
            self._served = True
            return iter(self._stale)
        return cur

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FailsOnAlter:
    """A connection over a real one whose ALTERs fail the way a REAL breakage
    would, to prove the guard is narrow."""

    def __init__(self, real, message):
        self._real = real
        self._message = message

    def execute(self, sql, *args):
        if sql.lstrip().upper().startswith("ALTER TABLE"):
            raise sqlite3.OperationalError(self._message)
        return self._real.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._real, name)


# ===================================================================== 1 ===

def t_a_new_notes_table_needs_no_migration():
    """A first install must not run an ALTER at all: the CREATE has to carry
    `topic_ask`, which `_note_card` then inserts. A table made without it
    needs a migration on the very first card - one every new install runs,
    and one a second writer can collide with (case 2)."""
    st, keep_store, keep_stats = _world("fresh")
    real_connect = st._connect
    counter = _Counting(real_connect())
    st._connect = lambda: counter
    try:
        q = _queue(st)
        res = _pass(st, q)
        st._connect = real_connect
        check("fresh database: the pass writes a card and reports no error",
              not res.get("error") and bool(res.get("cards")), res)
        check("fresh database: a first install runs NO migration on the notes "
              "table (so no concurrent first card can lose a pass to one)",
              not counter.alters, counter.alters)
        with closing(real_connect()) as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(auto_learn_notes)")]
            row = c.execute("SELECT proposal_id, reason, topic_ask, sensitive,"
                            " conversation_id FROM auto_learn_notes").fetchone()
        check("fresh database: the table has every column the INSERT fills",
              {"topic_ask", "sensitive", "conversation_id"} <= set(cols), cols)
        check("fresh database: the card's reason is stored", row is not None
              and row[1], row)
    finally:
        st._connect = real_connect
        _done(keep_store, keep_stats)


# ===================================================================== 2 ===

def t_a_stale_first_read_over_an_old_table_does_not_lose_the_card():
    """THE LIVE FAILURE. An old notes table (four columns), two writers: the
    other one finishes the migration between this pass's column read and its
    ALTERs. Before the fix that ALTER raises OperationalError, after_pass
    records `after_pass: OperationalError` and saves/cards nothing - which is
    exactly the counters the HUD showed."""
    st, keep_store, keep_stats = _world("old")
    real_connect = st._connect
    try:
        q = _queue(st)
        with closing(real_connect()) as c:
            c.execute(_OLD_NOTES)
            stale = [r[1] for r in c.execute("PRAGMA table_info(auto_learn_notes)")]
        # ... and the other writer has already migrated it.
        with closing(real_connect()) as other:
            for name, decl in (("sensitive", "TEXT"), ("conversation_id", "TEXT"),
                               ("topic_ask", "INTEGER")):
                other.execute(f"ALTER TABLE auto_learn_notes ADD COLUMN {name} {decl}")
        st._connect = lambda: _Stale(real_connect(), stale)
        res = _pass(st, q)
        st._connect = real_connect
        check("old table, stale first read: the pass still reports its card",
              not res.get("error") and bool(res.get("cards")), res)
        check("old table, stale first read: note_failure was not called",
              A.stats().get("last_error") is None, A.stats())
        with closing(real_connect()) as c:
            row = c.execute("SELECT proposal_id, reason, topic_ask, sensitive,"
                            " conversation_id FROM auto_learn_notes").fetchone()
        check("old table, stale first read: the card's reason is really stored",
              row is not None and row[1], row)
    finally:
        st._connect = real_connect
        _done(keep_store, keep_stats)


# ===================================================================== 3 ===

def t_a_real_failure_still_raises():
    """The migration's guard must not turn a genuinely broken database into
    "nothing to learn": only "already there" is swallowed."""
    st, keep_store, keep_stats = _world("locked")
    real_connect = st._connect
    try:
        with closing(real_connect()) as c:
            c.execute(_OLD_NOTES)
        for message in ("database is locked", "no such table: auto_learn_notes"):
            with closing(real_connect()) as c:
                try:
                    A._init_notes(_FailsOnAlter(c, message))
                except sqlite3.OperationalError as exc:
                    raised = str(exc)
                else:
                    raised = ""
            check(f"a real failure ({message}) is still raised",
                  raised == message, raised)
    finally:
        _done(keep_store, keep_stats)


# ===================================================================== 4 ===

def t_the_card_reason_survives_a_later_read():
    """The note is what the apps show as `auto_reason`, so the row written
    during a stale-read pass must be the one `card_notes()` reads back."""
    st, keep_store, keep_stats = _world("read")
    real_connect = st._connect
    try:
        q = _queue(st)
        with closing(real_connect()) as c:
            c.execute(_OLD_NOTES)
            stale = [r[1] for r in c.execute("PRAGMA table_info(auto_learn_notes)")]
        with closing(real_connect()) as other:
            for name, decl in (("sensitive", "TEXT"), ("conversation_id", "TEXT"),
                               ("topic_ask", "INTEGER")):
                other.execute(f"ALTER TABLE auto_learn_notes ADD COLUMN {name} {decl}")
        st._connect = lambda: _Stale(real_connect(), stale)
        res = _pass(st, q)
        st._connect = real_connect
        notes = A.card_notes([q["id"]])
        check("the card's reason is what card_notes() reads back",
              notes.get(q["id"], {}).get("auto_reason") == res.get("cards", {}).get(q["id"]),
              (notes, res))
        check("the card reason is not empty",
              bool(notes.get(q["id"], {}).get("auto_reason")), notes)
    finally:
        st._connect = real_connect
        _done(keep_store, keep_stats)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
