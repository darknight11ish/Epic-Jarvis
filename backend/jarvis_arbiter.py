"""
jarvis_arbiter.py - the one place that decides whether to interrupt you.

Every feature in this project spends the owner's attention and, until this
module existed, every feature decided for itself how much. The initiative
engine speaks a finding. A Long Fuse job finishes and announces it. The model
steward finds a newer model. The gate raises a card. Each of those is
reasonable on its own; together they are a machine for interrupting somebody
all day, and the usual outcome is that the owner turns the lot off - which
costs them the one notification that mattered along with the forty that did
not.

So: nothing unsolicited reaches a client directly any more. It is handed to
this module, which holds a budget, and what does not fit the budget drains
into one daily digest.

Three things it is NOT, each for a reason:

  * It is not in the event bus. The bus fans out to three clients with three
    different ideas of what an interruption is - a tray balloon, a phone
    notification, a spoken sentence. The decision has to be made once, before
    that, or each client re-decides it differently.

  * It is not in the initiative engine. That engine is one producer among
    several, and a budget that only one producer respects is not a budget.

  * It does not touch anything you ASKED for. A gate card for an action you
    just requested is foreground: you are already here, waiting, and making
    that wait on a token bucket would be absurd. `solicited=True` bypasses
    everything. The budget governs things that arrive when nobody asked.

The digest deliberately has no bulk action and no way to approve anything.
A ranked list of pending approvals with one tap each was the first design and
it is exactly the "just approve these" pattern that jarvis_content_risk exists
to flag when an attacker uses it; building it in-house does not make it
better. The digest LISTS an approval and says which card to open. Approving
still happens one card at a time, in the gate, where the consequence and the
reason are shown.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

DB_PATH = Path(os.environ.get("JARVIS_ARBITER_DB", str(_CFG_DIR / "arbiter.db")))

_LOCK = threading.RLock()
_inited = False


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("arbiter", {}).get(key, default)
    except Exception:
        return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Channels, priorities, and what they actually mean
# --------------------------------------------------------------------------
# SPEAK is the expensive one: audio, unprompted, in the room. It is what the
# budget counts. NOTIFY is a badge or a tray count - visible when the owner
# next looks, costing nothing until then. DIGEST is the overflow: it waits for
# the once-a-day brief.
SPEAK, NOTIFY, DIGEST, DROPPED = "speak", "notify", "digest", "dropped"

# Priority decides ORDER inside the digest and nothing else. It deliberately
# does not buy a bigger budget: a producer that wants to be heard more would
# simply always say "high", and a scale everyone tops out on is not a scale.
# The one exception is `critical`, which is for a fact about the machine the
# owner cannot act on later - the disk is full, the model will not load - and
# which the config can cap.
PRIORITIES = ("critical", "high", "normal", "low")
_PRI_RANK = {p: i for i, p in enumerate(PRIORITIES)}

# What kind of thing it is. Used for ranking the digest by CONSEQUENCE rather
# than by how loudly the item asks. See _rank().
KINDS = ("approval", "job", "finding", "steward", "reminder", "other")
_KIND_RANK = {"approval": 0, "job": 1, "steward": 2, "finding": 3,
              "reminder": 4, "other": 5}


def _connect() -> sqlite3.Connection:
    """Always inside `with closing(_connect()) as c:`.

    `isolation_level=None` for the same reason jarvis_gate.py uses it: without
    it, sqlite3 opens an implicit transaction on the first INSERT and nothing
    is written until somebody calls commit(). Every write in this module is a
    single statement, so autocommit is both correct and one fewer thing to get
    wrong on a path that decides whether the owner is interrupted.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=10.0, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c


def _init() -> None:
    global _inited
    with _LOCK:
        if _inited:
            return
        with closing(_connect()) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS intents (
                    id        TEXT PRIMARY KEY,
                    source    TEXT NOT NULL,
                    kind      TEXT NOT NULL,
                    title     TEXT NOT NULL,
                    body      TEXT,
                    priority  TEXT NOT NULL,
                    ref       TEXT,           -- an id in another module
                    created   REAL NOT NULL,
                    expires   REAL,
                    channel   TEXT NOT NULL,  -- speak|notify|digest|dropped
                    state     TEXT NOT NULL,  -- queued|delivered|expired
                    delivered REAL
                )""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_intent_state"
                      " ON intents(state, created)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS spend (
                    day   TEXT PRIMARY KEY,
                    spent INTEGER NOT NULL,
                    muted INTEGER NOT NULL DEFAULT 0
                )""")
        _inited = True


def _today(now: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now or time.time()))


# --------------------------------------------------------------------------
#   The budget
# --------------------------------------------------------------------------

def _limit() -> int:
    try:
        return max(0, int(_cfg("spoken_per_day", 3)))
    except (TypeError, ValueError):
        return 3


def _blocked_reason() -> Optional[str]:
    """Why the budget is zero right now regardless of what is left in it.

    Quiet and Standby are the owner saying "not now" in the plainest terms
    this system has, and a session lock says they are not at the desk. Speaking
    into an empty room is not free: it is either heard by somebody else or not
    heard at all, and both are worse than waiting.
    """
    try:
        import jarvis_power
        mode = jarvis_power.current()
        if mode in ("quiet", "standby"):
            return f"power mode is {mode}"
    except Exception:
        pass
    if _session_locked():
        return "the session is locked"
    return None


def _session_locked() -> bool:
    """Is the owner away from the machine?

    This replaces a webcam. An earlier design used face detection to decide
    whether to speak; it was killed because the operating system already knows
    the answer, and asking it costs no camera handle for a compromise to
    inherit and creates no record of who else was in the room.

    On Windows the real implementation is GetLastInputInfo plus the session
    lock/unlock notifications. There is no portable stdlib call for either, so
    this reads a small file that the desktop shell writes and returns False
    when it is absent - an unknown answer must not silence Jarvis, because a
    rule that fails to "never speak" is a rule that looks broken.
    """
    try:
        p = Path(os.environ.get("JARVIS_PRESENCE_FILE",
                                str(_CFG_DIR / "presence.json")))
        d = json.loads(p.read_text("utf-8"))
        if bool(d.get("locked")):
            return True
        idle = float(d.get("idle_seconds", 0) or 0)
        away_after = float(_cfg("away_after_idle_minutes", 15) or 15) * 60.0
        return away_after > 0 and idle >= away_after
    except Exception:
        return False


def budget(now: Optional[float] = None) -> dict:
    """What is left today, and why it might be zero anyway."""
    _init()
    day = _today(now)
    with closing(_connect()) as c:
        row = c.execute("SELECT spent, muted FROM spend WHERE day=?", (day,)).fetchone()
    spent = int(row["spent"]) if row else 0
    muted = bool(row["muted"]) if row else False
    limit = _limit()
    blocked = "muted until tomorrow" if muted else _blocked_reason()
    remaining = 0 if blocked else max(0, limit - spent)
    return {"limit": limit, "spent": spent, "remaining": remaining,
            "muted": muted, "blocked_by": blocked,
            "resets": "the start of tomorrow", "day": day}


def mute_until_tomorrow(now: Optional[float] = None) -> dict:
    """The owner's "not now" for the rest of the day. Deliberately not
    "mute forever": a mute with no end is how a feature gets switched off
    once and never reconsidered, and this one has a natural end."""
    _init()
    day = _today(now)
    with closing(_connect()) as c:
        c.execute("INSERT INTO spend (day, spent, muted) VALUES (?,0,1) "
                  "ON CONFLICT(day) DO UPDATE SET muted=1", (day,))
    _audit("arbiter.muted", {"day": day})
    return budget(now)


def unmute(now: Optional[float] = None) -> dict:
    _init()
    with closing(_connect()) as c:
        c.execute("UPDATE spend SET muted=0 WHERE day=?", (_today(now),))
    return budget(now)


def _spend(now: Optional[float] = None) -> bool:
    """Take one token. Returns False if there was none, without spending.

    The read and the write are one statement guarded on the count, so two
    producers firing at the same moment cannot both be told yes when only one
    token was left.

    The blocked check has to be HERE and not only in budget(): budget() is a
    report and this is the decision, and an earlier version had the reason
    computed in the report while the decision consulted nothing but the
    counter - so Quiet, Standby and a locked session all read as "blocked" on
    every screen while Jarvis carried on speaking. A number shown to the owner
    and a number the code acts on have to be the same number.
    """
    _init()
    if _blocked_reason():
        return False
    day = _today(now)
    limit = _limit()
    with closing(_connect()) as c:
        c.execute("INSERT OR IGNORE INTO spend (day, spent, muted) VALUES (?,0,0)", (day,))
        cur = c.execute("UPDATE spend SET spent = spent + 1 "
                        "WHERE day=? AND muted=0 AND spent < ?", (day, limit))
        return cur.rowcount > 0


# --------------------------------------------------------------------------
#   Delivering
# --------------------------------------------------------------------------

@dataclass
class Decision:
    id: str
    channel: str
    reason: str
    spoken: bool
    budget: dict

    def as_dict(self) -> dict:
        return asdict(self)


def deliver(source: str, title: str, body: str = "", *,
            kind: str = "finding", priority: str = "normal",
            can_defer: bool = True, expires: Optional[float] = None,
            ref: str = "", solicited: bool = False,
            want: str = SPEAK, now: Optional[float] = None) -> Decision:
    """Ask to reach the owner. The answer is one of four channels.

    `solicited=True` is for anything the owner is currently waiting on - a
    gate card for the action they just requested, an answer to a question they
    just asked. It skips the budget entirely, is never queued, and is never
    counted. Producers must not set it to get around the budget; there is a
    test asserting the initiative engine's own findings never do.

    `can_defer=False` says this stops being useful if it waits. It does NOT
    buy a token - it means that when there is no token, the item is dropped
    rather than put in a digest that will show it tomorrow when it is no
    longer true. A stale "your build is failing" from yesterday is worse than
    nothing, because acting on it wastes a real minute.
    """
    _init()
    now = time.time() if now is None else now
    kind = kind if kind in KINDS else "other"
    priority = priority if priority in PRIORITIES else "normal"
    iid = "i-" + uuid.uuid4().hex[:12]

    if solicited:
        # Not recorded, not counted, not queueable. The owner is here.
        _audit("arbiter.foreground", {"source": source, "kind": kind})
        return Decision(iid, want, "you asked for this", want == SPEAK,
                        budget(now))

    row = (iid, str(source)[:120], kind, str(title)[:300], str(body)[:4000],
           priority, str(ref)[:120], now, expires)

    def record(channel: str, state: str) -> None:
        with closing(_connect()) as c:
            c.execute("INSERT INTO intents (id,source,kind,title,body,priority,"
                      "ref,created,expires,channel,state,delivered)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      row + (channel, state, now if state != "queued" else None))

    if want != SPEAK:
        record(NOTIFY, "delivered")
        return Decision(iid, NOTIFY, "a badge costs nothing until you look",
                        False, budget(now))

    if _spend(now):
        record(SPEAK, "delivered")
        b = budget(now)
        _audit("arbiter.spoke", {"source": source, "kind": kind,
                                 "remaining": b["remaining"]})
        _publish_state(b)
        return Decision(iid, SPEAK, "within today's budget", True, b)

    b = budget(now)
    if not can_defer:
        record(DROPPED, "expired")
        _audit("arbiter.dropped", {"source": source, "kind": kind,
                                   "why": b["blocked_by"] or "budget spent"})
        return Decision(iid, DROPPED,
                        "this stops being true if it waits, and there was no "
                        "interruption left to spend on it", False, b)

    record(DIGEST, "queued")
    _publish_state(b)
    return Decision(iid, DIGEST,
                    (b["blocked_by"] or "today's interruptions are spent")
                    + "; it is in the digest", False, b)


# --------------------------------------------------------------------------
#   The digest
# --------------------------------------------------------------------------

def _rank(row: dict) -> tuple:
    """Order by CONSEQUENCE, never by urgency.

    An item does not move up the list because its own text says it is urgent.
    That is the whole attack jarvis_content_risk watches for, and a ranking
    function that rewards urgency would implement it for the attacker. So the
    key is: what kind of thing it is, then the priority a PRODUCER set (which
    is code, not content), then age.
    """
    return (_KIND_RANK.get(row["kind"], 9),
            _PRI_RANK.get(row["priority"], 9),
            row["created"])


def digest(limit: int = 50, now: Optional[float] = None) -> dict:
    """Everything waiting, ranked, with nothing resolvable from here.

    Note what this returns for an approval: an id, a title, and
    `opens_card: True`. It does not return the approval's detail and there is
    no function in this module that decides one. If a decision is worth a
    gate, it is worth one tap each - batching is how a gesture stops being a
    decision.
    """
    _init()
    now = time.time() if now is None else now
    expire(now)
    with closing(_connect()) as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM intents WHERE state='queued' ORDER BY created").fetchall()]
    rows.sort(key=_rank)
    items = []
    for r in rows[:limit]:
        item = {"id": r["id"], "kind": r["kind"], "source": r["source"],
                "title": r["title"], "priority": r["priority"],
                "created": r["created"], "ref": r["ref"] or ""}
        if r["kind"] == "approval":
            item["opens_card"] = True
            item["body"] = ""            # the card shows it, in the gate
        else:
            item["opens_card"] = False
            item["body"] = r["body"] or ""
        items.append(item)
    return {"items": items, "count": len(rows), "shown": len(items),
            "budget": budget(now), "hour": _digest_hour(),
            "note": ("Approvals open their own card. There is no approve-all, "
                     "here or anywhere else.")}


def _digest_hour() -> int:
    try:
        return max(0, min(23, int(_cfg("digest_hour", 18))))
    except (TypeError, ValueError):
        return 18


def digest_due(now: Optional[float] = None) -> bool:
    """True once a day, at the chosen hour, and only if there is something in
    it. A digest that arrives empty teaches the owner it is not worth opening.
    """
    _init()
    now = time.time() if now is None else now
    lt = time.localtime(now)
    if lt.tm_hour < _digest_hour():
        return False
    with closing(_connect()) as c:
        row = c.execute("SELECT COUNT(*) n FROM intents WHERE state='queued'").fetchone()
        if not row or not row["n"]:
            return False
        last = c.execute("SELECT MAX(delivered) d FROM intents "
                         "WHERE state='delivered' AND channel=?", (DIGEST,)).fetchone()
    if last and last["d"] and _today(last["d"]) == _today(now):
        return False
    return True


def mark_digest_delivered(ids: Optional[list] = None,
                          now: Optional[float] = None) -> int:
    """The owner has seen these. Called after the digest is actually shown,
    not when it is generated - a digest generated and never displayed (the
    phone was off, the tray never opened) must show up again."""
    _init()
    now = time.time() if now is None else now
    with closing(_connect()) as c:
        if ids is None:
            cur = c.execute("UPDATE intents SET state='delivered', channel=?, "
                            "delivered=? WHERE state='queued'", (DIGEST, now))
        else:
            qs = ",".join("?" * len(ids))
            cur = c.execute(f"UPDATE intents SET state='delivered', channel=?, "
                            f"delivered=? WHERE state='queued' AND id IN ({qs})",
                            [DIGEST, now, *ids])
        return cur.rowcount


def expire(now: Optional[float] = None) -> int:
    """Drop queued items whose moment has passed. Called on every read, so a
    digest never shows something that stopped being true while it waited."""
    _init()
    now = time.time() if now is None else now
    with closing(_connect()) as c:
        cur = c.execute("UPDATE intents SET state='expired' "
                        "WHERE state='queued' AND expires IS NOT NULL AND expires < ?",
                        (now,))
        keep = float(_cfg("keep_delivered_days", 14) or 14) * 86400.0
        c.execute("DELETE FROM intents WHERE state<>'queued' AND created < ?",
                  (now - keep,))
        return cur.rowcount


def pending_count(now: Optional[float] = None) -> int:
    """How many notches the reactor's rim ring draws."""
    _init()
    expire(now)
    with closing(_connect()) as c:
        row = c.execute("SELECT COUNT(*) n FROM intents WHERE state='queued'").fetchone()
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------
#   What the reactor shows
# --------------------------------------------------------------------------
# BANKED is a new face state and it is not a mood, it is a fact: there are
# things waiting and Jarvis is not going to say them out loud. Dimmed idle, no
# animation, the rim ring fully drawn, silent until tapped.
#
# The important half is the rule underneath it: a job finishing while banked
# does NOT move the face to "speaking" and does not make a sound. It adds a
# notch. Getting this wrong - letting a completion produce audio because the
# code path that finishes a job is not the code path that checks the budget -
# is exactly how an interruption budget becomes decorative.

def banked(now: Optional[float] = None) -> bool:
    b = budget(now)
    return bool(b["remaining"] == 0 and pending_count(now) > 0)


def face_state(activity: str = "idle", now: Optional[float] = None) -> str:
    """What the reactor should show, given what Jarvis is doing.

    Banked only replaces a resting face. If Jarvis is mid-sentence to somebody
    who asked it something, that is foreground and it keeps its own state -
    the budget governs what Jarvis STARTS, not what it is in the middle of.
    """
    if activity in ("idle",) and banked(now):
        return "banked"
    return activity


_last_published: dict = {}


def _publish_state(b: Optional[dict] = None, now: Optional[float] = None) -> None:
    """Tell the clients, but only when something actually changed. A budget
    event per finding would be its own kind of noise."""
    try:
        import jarvis_events
    except Exception:
        return
    b = b or budget(now)
    state = {"remaining": b["remaining"], "limit": b["limit"],
             "blocked_by": b["blocked_by"], "pending": pending_count(now),
             "banked": banked(now)}
    if state == _last_published:
        return
    _last_published.update(state)
    try:
        jarvis_events.BUS.publish("attention", state)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The tick
# --------------------------------------------------------------------------

def tick(now: Optional[float] = None) -> dict:
    """One pass, for whatever loop is already running.

    Pulls finished Long Fuse jobs in here rather than letting them announce
    themselves. That is the contract jarvis_jobs.collect() was written for:
    "tell me tomorrow" has no tomorrow if the answer arrives as a voice
    interruption at two in the afternoon.
    """
    now = time.time() if now is None else now
    out = {"expired": expire(now), "jobs": 0, "digest_due": False}
    try:
        import jarvis_jobs
        for job in jarvis_jobs.collect(limit=20):
            state = job.get("state", "done")
            deliver(source="long-fuse",
                    title=(job.get("label") or job.get("handler") or "job")
                          + (" finished" if state == "done" else f" {state}"),
                    body=str(job.get("result_summary") or job.get("error") or "")[:1000],
                    kind="job",
                    priority="normal" if state == "done" else "high",
                    ref=str(job.get("id", "")), now=now)
            out["jobs"] += 1
    except Exception:
        pass
    out["digest_due"] = digest_due(now)
    out["pending"] = pending_count(now)
    _publish_state(now=now)
    return out


def status(now: Optional[float] = None) -> dict:
    return {"available": True, "budget": budget(now),
            "pending": pending_count(now), "banked": banked(now),
            "digest_hour": _digest_hour(), "digest_due": digest_due(now)}


if __name__ == "__main__":                                # pragma: no cover
    import pprint
    pprint.pprint(status())
