"""jarvis_feedback.py - a right/wrong mark on each answer, and what the marks
say about the facts that went into it.

Items 1 and 8 of docs/LEARNING-RESEARCH-2026-09-23.md.

WHAT WAS MISSING
Jarvis learns what the owner says, but never finds out whether its own
answers were any good. There was no way to say "that was wrong". This module
is the backend half of that button, and of the counters that grow out of it.

WHAT IT KEEPS - AND WHAT IT NEVER KEEPS
    turns        one row per answered /api/chat turn: a random id and a time.
    turn_items   which remembered facts (and, later, skill notes) went into
                 that answer, as ids like "mem:12". Nothing else.
    marks        the owner's mark on an answer: "right", "wrong" or "none"
                 (taken back). Added to, never edited or deleted, so a change
                 of mind is history rather than a lost row. The CURRENT mark
                 is the newest row for that answer.
    retire_cards which facts have had a "retire this?" card raised, and at
                 what count, so the same card is not raised twice.

No question, no answer, no prompt, no fact text is written here - only ids,
times and marks. The fact ids are the ones the HUD already puts in the
X-Jarvis-Route header as `injected_ids` (memory-noise.patch builds them;
degrade-filter.patch empties them when a turn leaves the local lane). The
file is `feedback.db` in the same config folder as memory.db, and nothing in
this module opens a socket.

It is its own file on purpose. memory.db belongs to jarvis_memory and the
review queue; a second writer migrating tables in there is how two pieces of
work collide. The one thing this module does to memory is ask - see below.

ONE ANSWER, ONE MARK
`mark()` takes ONE turn id. There is no list form, no "mark all", and no
route that accepts one: a bulk mark would move every counter at once on one
tap, which is the approve-all shape docs/ARCHITECTURE.md forbids, arriving
through the side door of a statistic.

THE COUNTERS (item 8)
Per fact, and per skill note: how many answers it was used in that the owner
marked right ("helpful") and marked wrong ("harmful"). The format - an id with
helpful/harmful counts - is the idea from the ACE project's playbook
(ace-agent/ace, playbook_utils.py, Apache-2.0). Only the idea: no ACE code is
here, and nothing of the engine OpenJarvis wraps around it (which asks a cloud
model, and treats Jarvis's own old answer as the right one).

The counters are DERIVED - counted from the marks every time - rather than
stored numbers that get incremented. That is what makes "only the owner's own
marks move them" true by construction: there is no counter column for
anything else to write to, and a mark changed from wrong to right changes
both counts without any bookkeeping that could drift.

WHAT A HIGH "HARMFUL" COUNT DOES - AND DOES NOT DO
It never retires anything. When a CURRENT fact has been in at least
RETIRE_MIN_WRONG answers marked wrong, AND those outnumber the ones marked
right by at least RETIRE_RATIO to one, this asks jarvis_extract to queue ONE
"retire this?" card in the ordinary memory review queue - the same queue,
the same one-at-a-time Keep/Discard decision, the same /api/memory/decide.
Nothing changes until the owner accepts that card, and accepting RETIRES
(an end date; the fact stays in the history), it does not delete.

The bar is high on purpose. With one user the counts are sparse, and a fact
appearing in a wrong answer does not prove the fact caused the mistake. Five
wrong answers, outnumbering the right ones three to one, is "this keeps
showing up when things go wrong", not proof. The card says the numbers and
lets the owner judge.

A fact the owner pinned ("Always keep in mind", memory-profile.patch) never
gets the card: it is in every answer, so its counts only say how answers go
in general.

If the owner discards the card, it is not raised again for that fact until
RETIRE_MIN_WRONG MORE wrong marks have arrived - "you already said keep it"
is respected, but it is not a permanent mute on new evidence.

WHAT THE MODEL CAN DO HERE: NOTHING
No tool reaches this module (test_feedback.py checks jarvis_agent.py never
names it). A mark arrives only through POST /api/feedback/mark, behind the
pairing token, from a person pressing a button on one answer.

SKILL NOTES - HONEST STATUS
The counters take skill-note ids ("note:<skill>:<hash>", see note_id()), but
nothing records which skill notes went into an answer yet. That happens
inside jarvis_skills.load(), which lives on the owner's machine and not in
this repository. Until a caller passes `notes=` to record_turn(), skill-note
counters stay empty. They never raise a card: retiring a note would mean
removing text from the skill's index, which is a different, gated change
(skill-notes.patch).
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Iterable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - works standalone
    fw = None  # type: ignore


#: The marks a person can give an answer. "none" takes a mark back.
MARKS = ("right", "wrong", "none")

#: A fact must have been in at least this many answers marked wrong...
RETIRE_MIN_WRONG = 5
#: ...and those must outnumber the answers marked right by this ratio, before
#: a "retire this?" card is raised. See the module docstring for why it is high.
RETIRE_RATIO = 3

#: An answer recalls MEMORY_K facts (5 by default). This cap is far above that
#: and exists only so a malformed header cannot write a thousand rows.
MAX_ITEMS_PER_TURN = 64

_ITEM = re.compile(r"^(mem:[0-9]{1,12}|note:[^\s:]{1,80}:[0-9a-f]{12})$")
_TURN = re.compile(r"^[0-9a-f]{32}$")

_LOCK = threading.RLock()


# --------------------------------------------------------------------------
#   Where
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    # The same three places jarvis_memory looks, in the same order, so this
    # file sits beside memory.db rather than somewhere of its own choosing.
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def db_path() -> Path:
    """JARVIS_FEEDBACK_DB overrides it; the tests give each case its own."""
    env = os.environ.get("JARVIS_FEEDBACK_DB")
    return Path(env) if env else _config_dir() / "feedback.db"


def _connect() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit, like jarvis_memory's store: every write here is one
    # statement or is wrapped in an explicit BEGIN below.
    c = sqlite3.connect(p, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS turns (
        turn_id  TEXT PRIMARY KEY,
        created  REAL NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS turn_items (
        turn_id  TEXT NOT NULL REFERENCES turns(turn_id),
        item     TEXT NOT NULL,
        PRIMARY KEY (turn_id, item))""")
    c.execute("CREATE INDEX IF NOT EXISTS turn_items_item ON turn_items(item)")
    c.execute("""CREATE TABLE IF NOT EXISTS marks (
        id       INTEGER PRIMARY KEY,
        turn_id  TEXT NOT NULL REFERENCES turns(turn_id),
        mark     TEXT NOT NULL CHECK (mark IN ('right','wrong','none')),
        marked   REAL NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS marks_turn ON marks(turn_id, id)")
    c.execute("""CREATE TABLE IF NOT EXISTS retire_cards (
        id           INTEGER PRIMARY KEY,
        fact_id      INTEGER NOT NULL,
        proposal_id  INTEGER NOT NULL,
        helpful      INTEGER NOT NULL,
        harmful      INTEGER NOT NULL,
        raised       REAL NOT NULL)""")
    return c


# --------------------------------------------------------------------------
#   Ids
# --------------------------------------------------------------------------

def note_id(skill: str, note: str) -> str:
    """The id a skill note is counted under.

    A note is a line of free text in a list, with no id of its own, and its
    position moves when another note is added. So: the skill's name plus a
    short hash of the note's words, which stays the same for the same note.
    The note's text itself is never stored here.
    """
    name = re.sub(r"[\s:]+", "_", str(skill or "").strip())[:80] or "_"
    words = " ".join(str(note or "").split())
    return f"note:{name}:{hashlib.sha256(words.encode('utf-8')).hexdigest()[:12]}"


def _clean_items(ids: Iterable) -> list[str]:
    """Keep only ids that name a stored fact or a skill note.

    `fact:<n>` - the HUD's fallback when recall came from the old jsonl file
    rather than the store - is dropped: it is a position in a list that
    changes, so counting against it would count against the wrong fact later.
    """
    out: list[str] = []
    for i in ids or ():
        if isinstance(i, str) and _ITEM.match(i) and i not in out:
            out.append(i)
        if len(out) >= MAX_ITEMS_PER_TURN:
            break
    return out


# --------------------------------------------------------------------------
#   Recording an answer
# --------------------------------------------------------------------------

def record_turn(injected_ids: Iterable = (), notes: Iterable = ()) -> str:
    """Note that an answer is about to be sent, and what memory went into it.

    Returns the new turn id, which the HUD puts in X-Jarvis-Route as
    `turn_id` so a client can mark this answer later. Called once per
    answered /api/chat turn, on the request thread, before the first byte of
    the answer - so it has to be cheap, and it is: one insert per id.

    Takes ids only. There is no parameter here that could carry the
    conversation, which is the simplest way to keep it out.
    """
    tid = uuid.uuid4().hex
    items = _clean_items(list(injected_ids or ()) + list(notes or ()))
    with _LOCK, closing(_connect()) as c:
        c.execute("BEGIN")
        try:
            c.execute("INSERT INTO turns (turn_id, created) VALUES (?,?)",
                      (tid, time.time()))
            c.executemany("INSERT OR IGNORE INTO turn_items (turn_id, item) VALUES (?,?)",
                          [(tid, i) for i in items])
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    return tid


# --------------------------------------------------------------------------
#   Marking an answer
# --------------------------------------------------------------------------

_CURRENT = """
    SELECT m.turn_id, m.mark FROM marks m
    WHERE m.id = (SELECT MAX(id) FROM marks WHERE turn_id = m.turn_id)
"""


def _current_mark(c, tid: str) -> str:
    row = c.execute("SELECT mark FROM marks WHERE turn_id=? ORDER BY id DESC LIMIT 1",
                    (tid,)).fetchone()
    return row["mark"] if row else "none"


def _counts_for(c, items: Iterable[str]) -> dict:
    items = list(items)
    if not items:
        return {}
    q = ",".join("?" * len(items))
    rows = c.execute(f"""
        WITH cur AS ({_CURRENT})
        SELECT ti.item,
               SUM(CASE WHEN cur.mark='right' THEN 1 ELSE 0 END) AS helpful,
               SUM(CASE WHEN cur.mark='wrong' THEN 1 ELSE 0 END) AS harmful
        FROM turn_items ti JOIN cur ON cur.turn_id = ti.turn_id
        WHERE ti.item IN ({q})
        GROUP BY ti.item""", items).fetchall()
    out = {i: {"helpful": 0, "harmful": 0} for i in items}
    for r in rows:
        out[r["item"]] = {"helpful": int(r["helpful"] or 0),
                          "harmful": int(r["harmful"] or 0)}
    return out


def mark(turn_id, value) -> dict:
    """The owner's mark on ONE answer. Returns what happened, never raises
    for bad input.

    `value` is "right", "wrong", or "none" / None to take a mark back.
    Marking the same answer again replaces its mark - the old one is kept as
    history, and only the newest counts. A list of turn ids is refused,
    not iterated: one answer, one mark.
    """
    if not isinstance(turn_id, str) or not _TURN.match(turn_id):
        return {"ok": False, "status": 400,
                "reason": "need one turn_id - the 32-character id from the "
                          "X-Jarvis-Route header of that answer"}
    if value is None:
        value = "none"
    if value not in MARKS:
        return {"ok": False, "status": 400,
                "reason": 'mark must be "right", "wrong" or "none"'}

    with _LOCK, closing(_connect()) as c:
        if not c.execute("SELECT 1 FROM turns WHERE turn_id=?", (turn_id,)).fetchone():
            return {"ok": False, "status": 404,
                    "reason": "no answer with that id on this machine"}
        before = _current_mark(c, turn_id)
        if before != value:
            c.execute("INSERT INTO marks (turn_id, mark, marked) VALUES (?,?,?)",
                      (turn_id, value, time.time()))
        items = [r["item"] for r in c.execute(
            "SELECT item FROM turn_items WHERE turn_id=? ORDER BY item", (turn_id,))]

    raised = 0
    # Only a WRONG mark can push a fact over the line, so only a wrong mark
    # goes looking. Taking a mark back, or marking right, never raises a card.
    if value == "wrong" and before != "wrong":
        for item in items:
            if item.startswith("mem:") and _maybe_raise(int(item[4:])):
                raised += 1
    return {"ok": True, "status": 200, "turn_id": turn_id, "mark": value,
            "was": before, "changed": before != value,
            "facts": sum(1 for i in items if i.startswith("mem:")),
            "retire_cards_raised": raised}


# --------------------------------------------------------------------------
#   The "retire this?" card
# --------------------------------------------------------------------------

def should_raise(helpful: int, harmful: int) -> bool:
    """The threshold, as one function so the test pins it exactly."""
    return harmful >= RETIRE_MIN_WRONG and harmful >= RETIRE_RATIO * helpful


def _is_current(fact: Optional[dict]) -> bool:
    if not fact:
        return False
    vt = fact.get("valid_to")
    return vt is None or float(vt) > time.time()


def _maybe_raise(fact_id: int, *, extract=None, memory=None) -> bool:
    """Ask for ONE "retire this?" card if this fact has crossed the line.

    Never retires. Everything that could go wrong here - the memory module
    missing, the queue full, jarvis_extract not patched - ends in "no card",
    which is the safe direction: the fact keeps working exactly as before.
    """
    with _LOCK:
        with closing(_connect()) as c:
            n = _counts_for(c, [f"mem:{fact_id}"])[f"mem:{fact_id}"]
            if not should_raise(n["helpful"], n["harmful"]):
                return False
            last = c.execute(
                "SELECT harmful FROM retire_cards WHERE fact_id=? ORDER BY id DESC LIMIT 1",
                (fact_id,)).fetchone()
            # One card per level of evidence. Once a card has been raised at
            # some count, the next one needs RETIRE_MIN_WRONG more wrong marks
            # on top - whether the first was accepted, discarded or is still
            # waiting.
            if last is not None and n["harmful"] < int(last["harmful"]) + RETIRE_MIN_WRONG:
                return False
        try:
            if memory is None:
                import jarvis_memory as memory  # noqa: F811
            if not _is_current(memory.store().get(int(fact_id))):
                return False
            # "Always keep in mind" (memory-profile.patch): a pinned fact is
            # in EVERY answer, so its marks only count how the answers went
            # overall - they say nothing about the fact. The owner pinned it
            # on purpose; Unpin, Forget and Erase are all one tap away.
            pinned = getattr(memory.store(), "is_pinned", None)
            if pinned is not None and pinned(int(fact_id)):
                return False
            if extract is None:
                import jarvis_extract as extract  # noqa: F811
            propose = getattr(extract, "propose_retire", None)
            if propose is None:
                # jarvis_extract without feedback.patch applied: there is no
                # safe way to ask, so do not ask.
                return False
            pid = propose(int(fact_id), helpful=n["helpful"], harmful=n["harmful"])
        except Exception:
            return False
        if not pid:
            # Queue full, a card already waiting, or the fact went away. Not
            # recorded, so the next wrong mark tries again.
            return False
        with closing(_connect()) as c:
            c.execute("INSERT INTO retire_cards (fact_id, proposal_id, helpful, harmful, raised)"
                      " VALUES (?,?,?,?,?)",
                      (int(fact_id), int(pid), n["helpful"], n["harmful"], time.time()))
        return True


# --------------------------------------------------------------------------
#   Reading
# --------------------------------------------------------------------------

def counts() -> dict:
    """Every fact and skill note that has been in a marked answer, with its
    helpful/harmful counts. What GET /api/feedback/counts serves.

    Ids and numbers only. A screen that wants the fact's words already has
    them from /api/memory/facts, behind the same token.
    """
    with _LOCK, closing(_connect()) as c:
        rows = c.execute(f"""
            WITH cur AS ({_CURRENT})
            SELECT ti.item,
                   SUM(CASE WHEN cur.mark='right' THEN 1 ELSE 0 END) AS helpful,
                   SUM(CASE WHEN cur.mark='wrong' THEN 1 ELSE 0 END) AS harmful
            FROM turn_items ti JOIN cur ON cur.turn_id = ti.turn_id
            GROUP BY ti.item""").fetchall()
        tally = c.execute(f"""
            WITH cur AS ({_CURRENT})
            SELECT SUM(CASE WHEN mark='right' THEN 1 ELSE 0 END) AS r,
                   SUM(CASE WHEN mark='wrong' THEN 1 ELSE 0 END) AS w
            FROM cur""").fetchone()
        cards = c.execute("SELECT COUNT(*) FROM retire_cards").fetchone()[0]
    facts, notes = {}, {}
    for r in rows:
        h, x = int(r["helpful"] or 0), int(r["harmful"] or 0)
        if not (h or x):
            continue
        if r["item"].startswith("mem:"):
            facts[r["item"][4:]] = {"helpful": h, "harmful": x}
        else:
            notes[r["item"]] = {"helpful": h, "harmful": x}
    return {
        "available": True,
        "facts": facts,
        "skill_notes": notes,
        "answers_marked": {"right": int(tally["r"] or 0), "wrong": int(tally["w"] or 0)},
        "retire_cards_raised": int(cards),
        "threshold": {"min_wrong": RETIRE_MIN_WRONG, "ratio": RETIRE_RATIO},
        "note": "counts come only from your own marks. A fact that was in a "
                "wrong answer did not necessarily cause it.",
    }


def mark_of(turn_id) -> Optional[str]:
    """The current mark on one answer, or None if the id is unknown."""
    if not isinstance(turn_id, str) or not _TURN.match(turn_id):
        return None
    with _LOCK, closing(_connect()) as c:
        if not c.execute("SELECT 1 FROM turns WHERE turn_id=?", (turn_id,)).fetchone():
            return None
        return _current_mark(c, turn_id)
