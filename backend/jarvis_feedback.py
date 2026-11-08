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

RIGHT/WRONG v2 - MARK + WHY + SAVE MY CORRECTION (2026-11-08)
The owner chose this shape on 2026-11-07: tapping Wrong may say WHY, and may
carry the owner's own correction words. It is the SAME route, and an old body
is still fully valid:

    POST /api/feedback/mark
    {"turn_id": "<32 hex>", "mark": "right"|"wrong"|"none",
     "reason": "wrong_fact"|"outdated"|"misunderstood"|"too_long"|
               "too_sensitive",                 # optional; absent/"" = old body
     "correction": "<the owner's own words>"}   # optional; trimmed, max 500

WHAT IS KEPT, AND WHERE. The mark row grows two columns - `reason` and
`correction` - so the correction is stored LOCALLY with the mark it belongs to,
in this same `feedback.db`, beside memory.db. Nothing else gains text: no
question, no answer, no model output. The `notes` table holds the two note
kinds below the same way.

WHAT A REASON DOES
    wrong_fact / outdated   ONE card in the EXISTING memory review queue for
                            the FIRST current remembered fact recorded for
                            that answer:
                              * with the owner's own correction words - an
                                ordinary review card (`source`
                                "feedback_correction", the words in `text`,
                                the fact in `replaces_id`/`replaces_text`).
                                Accepting it is the queue's own `_accept`: it
                                stores the correction as the new fact and
                                retires the old row (history kept) = the fact
                                updated with the correction;
                              * with no correction typed - the queue's
                                existing "retire this?" card
                                (`jarvis_extract.propose_retire`, `source`
                                "feedback_retire"). Accepting it FORGETS the
                                fact (an end date; nothing is deleted).
                            Discarding either card changes nothing. A card
                            that cannot be asked (no recorded fact, the fact
                            already ended, the queue full, no jarvis_extract on
                            this PC) raises nothing and the answer says so.
    misunderstood / too_long a "manner" note in this file's own `notes` table
                            (what the owner would prefer next time), no memory
                            change at all.
    too_sensitive           a "privacy" note in the same table; the existing
                            sensitive-topic blocks and held cards are untouched.
    no reason               the old body: the counters and the old "retire
                            this?" counter card, exactly as before.

Only an UNREASONED wrong mark can raise the old counter card: the correction is
primary, so a reasoned mark never raises two cards. The counters themselves
still move for every mark - they are derived from the marks table - so a reason
cannot hide a wrong answer from them. The card's accept rule is NOT copied
here: it lives in jarvis_extract's own queue (`_accept` / `_accept_retire`), so
a mark can queue a card but can never change memory by itself.

THE RESPONSE is the old one plus what the apps show (all additive; ok, turn_id,
mark, was, changed, facts and retire_cards_raised keep their old meaning):

    {"ok": true, "turn_id": ..., "mark": "wrong", "was": "none",
     "changed": true, "facts": 1, "retire_cards_raised": 0,
     "reason": "wrong_fact"|""|...,       # the tag, echoed
     "correction_saved": true|false,     # a non-empty correction was stored
     "said": "one plain sentence for the app to show",
     "card_raised": true|false,          # ONE card in the review queue was queued
     "card_action": "feedback_correction"|"feedback_retire"|"",
                                         # which card: an update (the owner's own
                                         # words are the proposed replacement fact)
                                         # or a FORGET (the queue's retire card)
     "card_id": <the review-queue card id, or null>}

Errors keep their old shape: 400 {"error": "..."} for a bad turn id, mark,
reason or an over-long correction; 404 {"error": "no answer with that id on
this machine"}. GET /api/feedback/mark?turn_id=... answers the current mark
plus the reason and correction now (mark itself is unchanged).

ONE CARD, ONE DECISION, AND THE HONEST LIMIT. The review queue has one
accept/discard decision, so one card cannot offer BOTH "Forget that fact" and
"Update the fact with the correction" as two live buttons. What it offers is
the right one for this mark: Update when the owner typed a correction, Forget
when they did not; discarding means keep it as it is. A true two-button choice
would need a new decision verb in the queue, the route and both apps.

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
import jarvis_sqlite
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

#: Right/Wrong v2 (2026-11-08): the "why" tags a mark may carry.
REASONS = ("wrong_fact", "outdated", "misunderstood", "too_long", "too_sensitive")
#: A reason that corrects a REMEMBERED FACT: one card in the review queue.
FACT_REASONS = ("wrong_fact", "outdated")
#: The reasons that become a local note instead, and the note's kind.
NOTE_FOR_REASON = {"misunderstood": "manner", "too_long": "manner",
                   "too_sensitive": "privacy"}
#: The note kinds this module keeps (its own table, never memory.db).
NOTE_KINDS = ("manner", "privacy")
#: The `source`/action name of the two cards a wrong_fact / outdated mark may
#: raise, in the ordinary memory review queue. "feedback_correction" is an
#: ordinary proposal (the owner's words are the proposed replacement fact, so
#: accepting it updates the fact); "feedback_retire" is the queue's existing
#: "retire this?" card (accepting it forgets the fact).
CARD_ACTION_CORRECTION = "feedback_correction"
CARD_ACTION_RETIRE = "feedback_retire"
#: The longest correction this backend stores. Longer is refused, never cut:
#: silently cutting the owner's own words is the one thing a correction path
#: must not do.
MAX_CORRECTION = 500

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


def _create_schema(c: sqlite3.Connection) -> None:
    """The tables a feedback database needs, run ONCE per file (Optimization
    4.1). Called through `jarvis_sqlite.ensure_schema`; before this every
    `_connect()` re-ran six CREATE statements, on every turn's feedback read."""
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
        marked   REAL NOT NULL,
        reason     TEXT,
        correction TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS marks_turn ON marks(turn_id, id)")
    c.execute("""CREATE TABLE IF NOT EXISTS retire_cards (
        id           INTEGER PRIMARY KEY,
        fact_id      INTEGER NOT NULL,
        proposal_id  INTEGER NOT NULL,
        helpful      INTEGER NOT NULL,
        harmful      INTEGER NOT NULL,
        raised       REAL NOT NULL)""")
    # Right/Wrong v2 (2026-11-08): the owner's own "what should I have said?"
    # words, kept for a misunderstood / too-long mark as a manner note, and
    # for a too-sensitive mark as a privacy note. Its OWN table in this file -
    # never memory.db, so a note cannot become a remembered fact, and the
    # sensitive-topic blocks are not touched by it.
    c.execute("""CREATE TABLE IF NOT EXISTS notes (
        id       INTEGER PRIMARY KEY,
        turn_id  TEXT NOT NULL,
        kind     TEXT NOT NULL CHECK (kind IN ('manner','privacy')),
        reason   TEXT NOT NULL,
        text     TEXT,
        created  REAL NOT NULL)""")
    _migrate(c)


def _migrate(c: sqlite3.Connection) -> None:
    """Bring a feedback.db written before Right/Wrong v2 up to date.

    `jarvis_sqlite.ensure_schema` runs `_create_schema` once per file per
    process, and `CREATE TABLE IF NOT EXISTS` does NOT add columns to an
    existing table - so the owner's existing feedback.db keeps its old marks
    table unless this runs. Additive only: nothing is dropped, rewritten or
    deleted, and every old row simply has NULL reason/correction (the same
    "old body, old meaning" they had when they were written).
    """
    cols = {r[1] for r in c.execute("PRAGMA table_info(marks)")}
    for name in ("reason", "correction"):
        if name not in cols:
            c.execute(f"ALTER TABLE marks ADD COLUMN {name} TEXT")
    c.execute("""CREATE TABLE IF NOT EXISTS notes (
        id       INTEGER PRIMARY KEY,
        turn_id  TEXT NOT NULL,
        kind     TEXT NOT NULL CHECK (kind IN ('manner','privacy')),
        reason   TEXT NOT NULL,
        text     TEXT,
        created  REAL NOT NULL)""")


def _connect() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit, like jarvis_memory's store: every write here is one
    # statement or is wrapped in an explicit BEGIN below.
    c = sqlite3.connect(p, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    jarvis_sqlite.apply_pragmas(c)
    jarvis_sqlite.ensure_schema(p, _create_schema)
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


# --------------------------------------------------------------------------
#   Right/Wrong v2 - the why tag, the owner's correction and the notes
# --------------------------------------------------------------------------

def _clean_reason(value) -> tuple:
    """(the whole tag, or "", (error words, or None)).

    A tag is one of REASONS exactly (case/space tolerant); anything else is
    refused rather than guessed at, because the tag decides what a mark does
    to memory and a near miss must not pick the wrong behaviour."""
    if value is None:
        return "", None
    if not isinstance(value, str):
        return "", "reason must be one of " + ", ".join(REASONS)
    got = value.strip().lower()
    if not got:
        return "", None
    if got not in REASONS:
        return "", "reason must be one of " + ", ".join(REASONS)
    return got, None


def _clean_correction(value) -> tuple:
    """(the trimmed owner text, or "", (error words, or None)).

    Trimmed only at the ends: the owner's own words are never reworded. Over
    MAX_CORRECTION is a refusal, never a silent cut."""
    if value is None:
        return "", None
    if not isinstance(value, str):
        return "", "correction must be text"
    text = value.strip()
    if len(text) > MAX_CORRECTION:
        return "", f"correction must be {MAX_CORRECTION} characters or fewer"
    return text, None


def _now_marks(c, turn_id: str) -> tuple:
    """(state_of row or None) - the newest mark row for this answer."""
    return c.execute("SELECT mark, reason, correction FROM marks"
                     " WHERE turn_id=? ORDER BY id DESC LIMIT 1",
                     (turn_id,)).fetchone()


def _queue_card(fact_id, correction: str, *, extract=None, memory=None) -> tuple:
    """Queue ONE review-queue card about one remembered fact. Changes nothing.

    (card_action, card_id) - ("", None) when there is nothing to ask.

    With the owner's own correction words, the card is an ORDINARY review card:
    a proposed replacement fact (`text` = the correction) naming the fact it
    would replace (`replaces_id`/`replaces_text`), under `source`
    "feedback_correction". The queue's OWN `_accept` is what applies it - it
    stores the correction, retires the old row (history kept) and adds nothing
    else - so there is no second writer of the accept rule here.

    With no correction typed, the card is the queue's existing "retire this?"
    card for that fact, raised by `jarvis_extract.propose_retire` with the
    counts from this file: accepting it FORGETS the fact (an end date, never a
    delete) and adds nothing.

    The same safe shape as `_maybe_raise`: every way this cannot be asked ends
    in "no card", because the fact must keep working exactly as it is until a
    person answers the card.
    """
    try:
        if extract is None:
            import jarvis_extract as extract  # noqa: F811
        if memory is None:
            import jarvis_memory as memory  # noqa: F811
        store = memory.store()
        fact = store.get(int(fact_id))
        if not _is_current(fact):
            return "", None
        words = " ".join(str(correction or "").split())
        if words:
            # An ordinary proposal: the owner's words are the proposed new
            # fact, and accepting updates the fact it names (see _accept).
            with closing(store._connect()) as c:
                init = getattr(extract, "_init", None)
                if callable(init):
                    init(c)
                if c.execute(
                        "SELECT 1 FROM proposals WHERE state='pending' AND source=?"
                        " AND replaces_id=?", (CARD_ACTION_CORRECTION,
                                               int(fact_id))).fetchone():
                    return "", None
                cfg = getattr(extract, "_cfg", None)
                cap = int(cfg("review_queue_max", 200)) if callable(cfg) else 200
                pend = c.execute("SELECT COUNT(*) FROM proposals"
                                 " WHERE state='pending'").fetchone()[0]
                if pend >= cap:
                    if hasattr(extract, "_dropped_full"):
                        extract._dropped_full += 1
                    return "", None
                cur = c.execute(
                    "INSERT INTO proposals (text, replaces, confidence, source,"
                    " created, replaces_id, replaces_text)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (words, fact.get("text"), None, CARD_ACTION_CORRECTION,
                     time.time(), int(fact_id), fact.get("text")))
                try:
                    c.commit()
                except Exception:
                    pass
                return (CARD_ACTION_CORRECTION,
                        int(cur.lastrowid or 0) or None)
        # No correction typed: the queue's existing "retire this?" card, so
        # accepting it is a FORGET with the same one-decision rule.
        propose = getattr(extract, "propose_retire", None)
        if propose is None:
            return "", None
        with closing(_connect()) as c:
            n = _counts_for(c, [f"mem:{int(fact_id)}"]).get(
                f"mem:{int(fact_id)}", {"helpful": 0, "harmful": 0})
        pid = propose(int(fact_id), helpful=int(n["helpful"]),
                      harmful=int(n["harmful"]))
        return (CARD_ACTION_RETIRE, int(pid) if pid else None) if pid else ("", None)
    except Exception:
        return "", None


def _save_note(turn_id: str, kind: str, reason: str, text: str) -> bool:
    """Keep ONE manner or privacy note locally. Never touches memory."""
    try:
        with _LOCK, closing(_connect()) as c:
            c.execute("INSERT INTO notes (turn_id, kind, reason, text, created)"
                      " VALUES (?,?,?,?,?)",
                      (turn_id, kind, reason, str(text or ""), time.time()))
        return True
    except Exception:
        return False


def _said(value: str, tag: str, facts_used: int, card_id, correction: str) -> str:
    """ONE plain sentence for an app to show about this mark (live, not stored).

    It never claims a memory change happened: a correction waits on its card,
    and the notes are notes."""
    if value == "none":
        return "Mark taken back - that answer is unmarked again."
    if value == "right":
        return "Thanks - marked right."
    if tag in FACT_REASONS:
        if card_id:
            if correction:
                return ("Thanks - I saved your correction. One card is waiting: "
                        "accept it to update the remembered fact with your words, "
                        "or discard it to keep the fact as it is.")
            return ("Thanks - I saved that. One card is waiting: accept it to stop "
                    "using the remembered fact, or discard it to keep it as it is.")
        if facts_used:
            saved = "your correction" if correction else "that"
            return (f"Thanks - I saved {saved}, but no card was raised: there "
                    f"was no current remembered fact to ask about.")
        return ("Thanks - I saved that. No remembered fact went into that answer, "
                "so nothing else was changed.")
    if tag in NOTE_FOR_REASON:
        if tag == "too_sensitive":
            return ("Thanks - I saved that as a privacy note. Your sensitive-topic "
                    "blocks are exactly as they were.")
        return ("Thanks - I saved that as a note about how I should answer, not "
                "about what I remember.")
    return ("Thanks - marked wrong. Your marks are counted; nothing was changed "
            "in memory.")


def mark(turn_id, value, reason=None, correction=None) -> dict:
    """The owner's mark on ONE answer, with an optional why and correction.

    `value` is "right", "wrong", or "none" / None to take a mark back.
    `reason` is one of REASONS, or None/"" for the old body's behaviour (see
    the module docstring for what each tag does). `correction` is the owner's
    own words, trimmed, at most MAX_CORRECTION characters. Both only change
    anything on a "wrong" mark.

    Marking the same answer again keeps the old row as history and only the
    newest counts; a NEW why or correction is recorded as a new row. A list of
    turn ids is refused, not iterated: one answer, one mark. `changed` means a
    new mark row was written (the mark, or the why/correction on it, changed).

    Returns the old response keys plus `reason`, `correction_saved`, `said`,
    `card_raised`, `card_action` and `card_id` - see the module docstring.
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
    tag, why = _clean_reason(reason)
    if why:
        return {"ok": False, "status": 400, "reason": why}
    text, why = _clean_correction(correction)
    if why:
        return {"ok": False, "status": 400, "reason": why}

    write = False
    with _LOCK, closing(_connect()) as c:
        if not c.execute("SELECT 1 FROM turns WHERE turn_id=?", (turn_id,)).fetchone():
            return {"ok": False, "status": 404,
                    "reason": "no answer with that id on this machine"}
        row = _now_marks(c, turn_id)
        before = row["mark"] if row else "none"
        was_reason = (row["reason"] or "") if row else ""
        was_text = (row["correction"] or "") if row else ""
        # Only a wrong mark carries a why and a correction: "right" and "none"
        # keep their old meaning, and a tag sent with them is not stored.
        store_tag = tag if value == "wrong" else ""
        store_text = text if value == "wrong" else ""
        if value == "wrong":
            write = (before != value or store_tag != was_reason
                     or store_text != was_text)
        else:
            write = before != value
        if write:
            c.execute("INSERT INTO marks (turn_id, mark, reason, correction, marked)"
                      " VALUES (?,?,?,?,?)",
                      (turn_id, value, store_tag or None,
                       store_text or None, time.time()))
        items = [r["item"] for r in c.execute(
            "SELECT item FROM turn_items WHERE turn_id=? ORDER BY rowid", (turn_id,))]

    raised = 0
    card_id = None
    card_action = ""
    if value == "wrong" and store_tag in FACT_REASONS:
        # THE CORRECTION IS PRIMARY (2026-11-08): one card for the FIRST
        # current remembered fact recorded for this answer. One card, one
        # decision; the older counter card is not raised for a reasoned mark.
        # ONE card, for the FIRST remembered fact recorded for this answer (in
        # the order the answer used them). If that fact cannot be asked about
        # (already ended, a card already waiting, no jarvis_extract here) the
        # mark raises nothing - it never moves on to a fact the owner did not
        # just point at, and a second mark can never queue a second card.
        first_fid = None
        for item in items:
            if not item.startswith("mem:"):
                continue
            try:
                first_fid = int(item[4:])
            except (TypeError, ValueError):
                first_fid = None
            break
        if first_fid is not None:
            card_action, card_id = _queue_card(first_fid, store_text)
    elif value == "wrong" and store_tag in NOTE_FOR_REASON:
        _save_note(turn_id, NOTE_FOR_REASON[store_tag], store_tag, store_text)
    elif value == "wrong" and before != "wrong":
        # The old body's backstop: only a WRONG mark can push a fact over the
        # line, so only a wrong mark goes looking. Unchanged.
        for item in items:
            if item.startswith("mem:") and _maybe_raise(int(item[4:])):
                raised += 1
    facts_used = sum(1 for i in items if i.startswith("mem:"))
    return {"ok": True, "status": 200, "turn_id": turn_id, "mark": value,
            "was": before, "changed": write,
            "facts": facts_used,
            "retire_cards_raised": raised,
            "reason": store_tag,
            "correction_saved": bool(store_text),
            "said": _said(value, store_tag, facts_used, card_id, store_text),
            "card_raised": bool(card_id),
            "card_action": card_action if card_id else "",
            "card_id": card_id}


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


def state_of(turn_id) -> Optional[dict]:
    """The current mark AND the reason/correction stored with it, or None.

    What GET /api/feedback/mark now answers: `mark` keeps its old meaning, so
    an app that only reads `mark` is unchanged, and a newer app can show the
    why and the owner's own correction again when it re-opens the answer.
    Unknown id -> None (the route's 404), exactly like mark_of."""
    if not isinstance(turn_id, str) or not _TURN.match(turn_id):
        return None
    with _LOCK, closing(_connect()) as c:
        if not c.execute("SELECT 1 FROM turns WHERE turn_id=?", (turn_id,)).fetchone():
            return None
        row = _now_marks(c, turn_id)
    if row is None:
        return {"mark": "none", "reason": "", "correction": ""}
    return {"mark": str(row["mark"]),
            "reason": str(row["reason"] or ""),
            "correction": str(row["correction"] or "")}


def local_notes() -> list:
    """Every manner/privacy note kept locally, oldest first.

    This is a READER for this PC's own record (tests, and a future app screen);
    there is no route to it today and no model tool can reach this module, so
    the words stay on this machine. What a note is: the owner's own words about
    how Jarvis should answer (manner) or about something too private to keep
    (privacy) - never a change to remembered facts."""
    with _LOCK, closing(_connect()) as c:
        rows = c.execute("SELECT turn_id, kind, reason, text, created"
                         " FROM notes ORDER BY id").fetchall()
    return [{"turn_id": r["turn_id"], "kind": r["kind"], "reason": r["reason"],
             "text": r["text"] or "", "created": float(r["created"])} for r in rows]
