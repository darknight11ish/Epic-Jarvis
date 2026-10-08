"""jarvis_tasks.py - the job list: work that outlives one chat turn.

WHY THIS EXISTS

Until now every turn Jarvis takes is a single-turn, tool-using chat turn with
a hard 7-request ceiling (6 rounds, `jarvis_agent.py`), and nothing about it
survives the turn ending. The project's own capability audit of 2026-10-06
says the cost of that plainly: *"No persistent queue, no retries, no
self-verification, no self-critique, no multi-agent work."* The plan card
(`jarvis_plan.py`, "one card, several steps") is built and switched off
because it has no durable place to sit, Projects cannot run a test suite,
and the overnight tidy runs nothing.

This module is that durable place. It is a small job list on the PC's own
disk: a task is a named job with a list of steps, each step is still a tool
call that goes through the ONE approval gate exactly as it does today, and
the list remembers where it got to - through a restart, a crash, a pause, a
stop, or an action whose outcome nobody knows.

WHAT THIS IS NOT

- **Not a second gate, and not a way around the gate.** Every step that acts
  is asked about on its own card, by the caller's own `ask` (normally
  `jarvis_gate.check`). This module decides only the ORDER of steps and what
  is remembered between them. It never imports `jarvis_gate`, never guesses
  a route, and never treats "the task was approved" as approval of a step.
- **Not a second scheduler.** Timed things - the briefing, "tell me when",
  the overnight tidy, the standby window - stay kinds on the one clock
  (`jarvis_schedule.register_kind`). This module is not a clock: the caller
  ticks it, and a job that must happen at a time is enqueued BY the
  scheduler's `on_fire`, never by a timer of its own here.
- **Not a way for anything to leave the PC.** This file makes no network
  call and no tool call of its own. A step that leaves the machine runs
  through the caller's `run_step`, which is the same gate every ordinary
  tool call already goes through. This module adds no new lane, no key and
  no address.
- **Not a queue for the owner's private words.** A task's title, its step
  words and its results are the owner's own material and stay in the same
  local store as everything else (config folder, owner-only). Nothing here
  is published to a client except the counted, titled summary `status()`
  returns - the same rule `jarvis_task_control` already follows.

THE FOUR HABITS BORROWED FROM OPENMUSE (docs/COMPETITORS-OPENMUSE-2026-10-08.md)

1. **A lease, so a crashed job is picked up again and never run twice at
   once.** A claim writes a `lease_id` and a `lease_until` through a
   compare-and-set on the row's own version, so two claimers cannot both
   win. A `running` task whose lease has run out is the signature of a
   backend that died mid-step; `tick()` handles it below, honestly.
2. **A checkpoint after every step.** A step that finished is a fact on
   disk before the next step is considered, so a restart resumes rather
   than starts over.
3. **An action, not a step, is what leaves the machine - and an action that
   MIGHT have gone out is never retried.** `outcome_unknown` is its own
   state, separate from `failed`, and `recover_interrupted()` turns every
   action left mid-flight by a restart into one, in words that tell the
   owner to check the other side first. A silent second send is the exact
   failure one-card-per-email exists to prevent.
4. **A decision is bound to what was shown.** An approval carries the hash
   of the words on the card; deciding with any other hash is refused. That
   is the half Jarvis did not have - `owner-check.patch` proves WHO
   approved, this proves WHAT they approved, and together they are stronger
   than either project has alone.

ONE STEP PER TICK, ON PURPOSE

The backend is one process on the owner's PC and it also answers the apps
and the voice path. A job must never hold the turn that started it, so
`tick()` runs at most one step of each of at most `MAX_IN_FLIGHT` tasks and
returns. A card that needs the owner is not waited on inside a tick either:
`ask(step)` returns a verdict, or `None` for "not decided yet", the task
sits in `waiting_approval`, and a later tick asks again. That is why a job
can take an hour without the Jarvis bar freezing for an hour.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

#: How many tasks may be mid-run at once. Three, the same number OpenMuse's
#: worker uses, and small on purpose: this is a PC that is also answering the
#: owner, running the model on its card, and listening for "Hey Jarvis".
MAX_IN_FLIGHT = 3

#: Steps in one task. Matches `jarvis_plan.MAX_STEPS` so a plan that was
#: allowed on its own card cannot become a longer job by being enqueued.
MAX_STEPS = 8

#: Jobs waiting that have not started. Past this, `enqueue()` refuses in
#: words. A refusal, never a grant, and never a silent drop.
MAX_WAITING = 20

#: How long a claim is good for. Long enough for one slow step (a model
#: answer, a page read), short enough that a dead backend's job comes back
#: within a minute.
LEASE_SECONDS = 60

#: How long a card waits before it expires. The same 30 minutes OpenMuse
#: uses, and the same figure `approval-expiry.patch` already counts down.
ACTION_TTL_SECONDS = 30 * 60

#: Text kept per field, so one runaway step cannot fill the disk.
MAX_TEXT = 400        # a task title, a step's `why`
MAX_RESULT = 4000     # one step's result, as text
MAX_FEED = 400        # one run-event line

#: Task states. `blocked` is the honest one: something was interrupted and
#: only the owner can say what happens next (see `tick()`).
STATES = ("queued", "running", "waiting_approval", "waiting_input",
          "paused", "scheduled", "blocked", "succeeded", "failed", "cancelled")

#: Action states. `outcome_unknown` is deliberately NOT `failed`.
ACTION_STATES = ("awaiting_review", "executing", "succeeded", "failed",
                 "outcome_unknown", "denied", "expired")

#: The sentence the owner sees for an action nobody can vouch for. Copying
#: this wording matters: it is the only thing standing between a crash and a
#: silent second send.
UNKNOWN_WORDS = ("The PC restarted while this was going out. Check the other "
                 "side before doing it again - Jarvis will not repeat it.")


class Refused(ValueError):
    """The job list refused: too many waiting, a malformed task, a bad hash."""


class LostLease(RuntimeError):
    """This run no longer owns its task - paused, stopped, cancelled, or
    taken over after the lease ran out. Raised by `guard()`."""


class StopRequested(RuntimeError):
    """The owner pressed Stop (or "stop everything"). Never gated: stopping
    is always allowed, and always immediate."""


# --------------------------------------------------------------------------
#   Where it lives
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The owner's settings and data folder - the same rule every other
    module here uses. `jarvis_framework`'s own CONFIG_DIR wins when it is
    importable, because that is what the running backend uses."""
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    try:
        import jarvis_framework as fw  # type: ignore
        return Path(fw.CONFIG_DIR)
    except Exception:
        return Path(os.path.expanduser("~")) / ".openjarvis"


DB_ENV = "JARVIS_TASKS_DB"


def db_path() -> Path:
    """The job list's own file. One name, so the module, the patch and the
    tests cannot disagree about it - and a one-line override so a test (or a
    second install) never touches the owner's real list."""
    env = (os.environ.get(DB_ENV) or "").strip()
    if env:
        return Path(os.path.expanduser(env))
    return _config_dir() / "tasks.db"


# --------------------------------------------------------------------------
#   Small helpers
# --------------------------------------------------------------------------

def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts if ts is not None else _now()))


def _cut(text, limit: int) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit] + " ..."


def canonical(value) -> str:
    """The one way anything here is turned into text for hashing. Sorted
    keys and no incidental spaces, so the same content always hashes the
    same - a card re-drawn tomorrow must produce yesterday's hash."""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)
    except Exception:
        return str(value)


def content_hash(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def idempotent_id(key: str) -> str:
    """An action's id, when the caller gave an idempotency key. The same key
    always produces the same id, so asking twice returns the first action
    instead of making a second one."""
    return hashlib.sha256(("jarvis-action:" + str(key)).encode("utf-8")).hexdigest()


def memo_key(tool: str, args) -> str:
    """A step's identity for the memo: the tool's name and its arguments,
    nothing else - not the task, not the time."""
    return hashlib.sha256(canonical({"tool": tool, "args": args}).encode("utf-8")).hexdigest()


#: The placeholder an earlier step's result goes into, exactly the syntax
#: `jarvis_plan.py` uses, so a plan that was already written for the plan
#: card does not have to be rewritten to run as a job.
SLOT = re.compile(r"\{\{\s*step\s+(\d+)\s*\}\}", re.I)


def _subst(value, text: str):
    if isinstance(value, str):
        return SLOT.sub(lambda _m: text, value)
    if isinstance(value, dict):
        return {k: _subst(v, text) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_subst(v, text) for v in value]
    return value


def fill_from_done(step: dict, done: list) -> dict:
    """A copy of a step with every `{{step N}}` replaced by step N's REAL
    recorded result - never the proposal-time guess.

    `jarvis_plan.py` proves why this matters (its condition 2, bug audit
    2026-09-28 F3): a step whose arguments came from an earlier step's
    result could not be shown truthfully on the card that was approved, so
    it is asked about again, on its own card, with the value it will
    actually use. This function is what produces that value.
    """
    out = dict(step)
    earlier = step.get("from_step")
    if earlier is None:
        return out
    text = ""
    for d in done or []:
        if d.get("index") == earlier:
            text = str(d.get("result") or "")
    out["args"] = _subst(dict(step.get("args") or {}), text)
    out["filled"] = True
    return out


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

@dataclass
class Verdict:
    """What `ask()` gives back. `allowed` is the only thing that permits a
    step, it always defaults to False, and `outcome` carries the gate's own
    word (`approved`, `denied`, `timed_out`, `refused`) so a timeout is
    never mistaken for a refusal (see `backend/gate-outcome.patch`)."""
    allowed: bool = False
    outcome: str = "refused"
    reason: str = ""
    request_id: Optional[str] = None


@dataclass
class Task:
    id: str
    title: str
    goal: str
    steps: list = field(default_factory=list)     # [{tool, args, why, risky, retry_safe}]
    kind: str = "job"
    status: str = "queued"
    at: int = 0                                    # next step, 0-based
    done: list = field(default_factory=list)       # completed steps, with results
    asked: Optional[dict] = None                   # the step waiting on a card
    question: str = ""
    answer: str = ""
    attempts: int = 0
    lease_id: Optional[str] = None
    lease_until: float = 0.0
    updated_at: float = 0.0
    error: str = ""
    created: float = 0.0
    #: The step this task was in the middle of when its lease was last held:
    #: `{"index": n, "tool": "...", "acts": bool}`. Cleared the moment the
    #: step is checkpointed. A lease that runs out with this set is how
    #: `tick()` knows a step was interrupted rather than never started.
    inflight: Optional[dict] = None
    #: The run row this execution belongs to. One tick is one run: it starts
    #: at the claim and is finished at every way out, so a run left
    #: `running` is always the signature of a process that died.
    run_id: Optional[str] = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL,
  lease_id TEXT, lease_until REAL NOT NULL DEFAULT 0,
  at INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status, updated_at);
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL, started_at REAL NOT NULL,
  finished_at REAL, status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS runs_task ON runs(task_id, started_at);
CREATE TABLE IF NOT EXISTS run_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, date REAL NOT NULL,
  kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS run_events_task ON run_events(task_id, id);
CREATE TABLE IF NOT EXISTS actions(
  id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL,
  idem TEXT, expires_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS actions_status ON actions(status, updated_at);
CREATE INDEX IF NOT EXISTS actions_idem ON actions(idem);
CREATE TABLE IF NOT EXISTS memo(
  key TEXT PRIMARY KEY, result TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS control(
  key TEXT PRIMARY KEY, value TEXT NOT NULL, at REAL NOT NULL);
"""

#: A task's own fields, so a row written by an older or newer version of
#: this module still loads instead of refusing to be read. A store that
#: cannot read its own rows is worse than one that ignores a new field.
TASK_FIELDS = tuple(Task.__dataclass_fields__.keys())


def _task_from(doc) -> Optional[Task]:
    if not isinstance(doc, dict):
        return None
    try:
        return Task(**{k: v for k, v in doc.items() if k in TASK_FIELDS})
    except Exception:
        return None


class Store:
    """The job list on disk. One file, plain SQLite, no schema migration
    machinery beyond `CREATE TABLE IF NOT EXISTS` - this is one owner on one
    PC, and a store that needs a migration tool is a store that breaks.

    Every state change that another tick, another thread or a restart could
    race with is a compare-and-set: a single UPDATE with the old value in
    its WHERE clause, and the code checks whether it actually changed a row.
    That is the whole concurrency story, and it is enough for a single
    process because SQLite serialises the writes themselves."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else db_path()
        if self.path.parent and str(self.path.parent) not in ("", "."):
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        with closing(self._connect()) as c:
            c.executescript(SCHEMA)
            c.commit()

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        return c

    # -- tasks -------------------------------------------------------------

    def _put_task(self, c: sqlite3.Connection, t: Task, *, expect=None) -> bool:
        """Write a task back. `expect` is the version this write claims to be
        based on (a status, or a (status, lease_id) pair); the write only
        lands if the row still says that. Returns whether it landed."""
        t.updated_at = _now()
        if expect is None:
            c.execute("UPDATE tasks SET data=?, status=?, lease_id=?, lease_until=?, "
                      "at=?, updated_at=? WHERE id=?",
                      (canonical(t.as_dict()), t.status, t.lease_id, t.lease_until,
                       t.at, t.updated_at, t.id))
            return True
        want_status, want_lease = expect if isinstance(expect, tuple) else (expect, None)
        cur = c.execute(
            "UPDATE tasks SET data=?, status=?, lease_id=?, lease_until=?, at=?, updated_at=? "
            "WHERE id=? AND status=? AND COALESCE(lease_id,'')=?",
            (canonical(t.as_dict()), t.status, t.lease_id, t.lease_until, t.at,
             t.updated_at, t.id, want_status, want_lease or ""))
        return cur.rowcount == 1

    def get_task(self, task_id: str) -> Optional[Task]:
        with closing(self._connect()) as c:
            row = c.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        try:
            return _task_from(json.loads(row["data"]))
        except Exception:
            return None

    def list_tasks(self, status: Optional[str] = None) -> list:
        sql = "SELECT data FROM tasks"
        args: tuple = ()
        if status:
            sql += " WHERE status=?"
            args = (status,)
        sql += " ORDER BY updated_at DESC"
        with closing(self._connect()) as c:
            rows = c.execute(sql, args).fetchall()
        out = []
        for r in rows:
            try:
                t = _task_from(json.loads(r["data"]))
            except Exception:
                t = None
            if t is not None:
                out.append(t)
        return out

    def add_task(self, t: Task) -> None:
        with closing(self._connect()) as c:
            t.created = t.created or _now()
            t.updated_at = t.created
            c.execute("INSERT INTO tasks(id,data,status,lease_id,lease_until,at,updated_at) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (t.id, canonical(t.as_dict()), t.status, t.lease_id or None,
                       t.lease_until, t.at, t.updated_at))
            c.commit()

    # -- runs and the feed -------------------------------------------------

    def add_run(self, task_id: str, status: str, detail: str = "") -> str:
        rid = uuid.uuid4().hex
        with closing(self._connect()) as c:
            c.execute("INSERT INTO runs(id,task_id,started_at,status,detail) VALUES(?,?,?,?,?)",
                      (rid, task_id, _now(), status, _cut(detail, MAX_FEED)))
            c.commit()
        return rid

    def finish_run(self, run_id: str, status: str, detail: str = "") -> None:
        with closing(self._connect()) as c:
            c.execute("UPDATE runs SET finished_at=?, status=?, detail=? WHERE id=? AND status=?",
                      (_now(), status, _cut(detail, MAX_FEED), run_id, "running"))
            c.commit()

    def reconcile_runs(self) -> int:
        """Any run left `running` belongs to a process that is gone. Said
        once, at startup, rather than pretending it finished."""
        with closing(self._connect()) as c:
            cur = c.execute("UPDATE runs SET status='interrupted', finished_at=? "
                            "WHERE status='running'", (_now(),))
            c.commit()
            return cur.rowcount

    def add_event(self, task_id: str, kind: str, title: str, detail: str = "") -> None:
        with closing(self._connect()) as c:
            c.execute("INSERT INTO run_events(task_id,date,kind,title,detail) VALUES(?,?,?,?,?)",
                      (task_id, _now(), _cut(kind, 40), _cut(title, MAX_FEED),
                       _cut(detail, MAX_FEED)))
            c.commit()

    def events(self, task_id: Optional[str] = None, limit: int = 50) -> list:
        with closing(self._connect()) as c:
            if task_id:
                rows = c.execute("SELECT * FROM run_events WHERE task_id=? ORDER BY id DESC "
                                 "LIMIT ?", (task_id, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM run_events ORDER BY id DESC LIMIT ?",
                                 (limit,)).fetchall()
        return [dict(r) for r in rows]

    def runs(self, task_id: Optional[str] = None, limit: int = 50) -> list:
        with closing(self._connect()) as c:
            if task_id:
                rows = c.execute("SELECT * FROM runs WHERE task_id=? ORDER BY started_at DESC "
                                 "LIMIT ?", (task_id, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                                 (limit,)).fetchall()
        return [dict(r) for r in rows]

    # -- the memo ----------------------------------------------------------

    def memo_get(self, key: str) -> Optional[str]:
        with closing(self._connect()) as c:
            row = c.execute("SELECT result FROM memo WHERE key=?", (key,)).fetchone()
        return row["result"] if row else None

    def memo_put(self, key: str, result: str) -> None:
        with closing(self._connect()) as c:
            c.execute("INSERT INTO memo(key,result,at) VALUES(?,?,?) "
                      "ON CONFLICT(key) DO UPDATE SET result=excluded.result, at=excluded.at",
                      (key, _cut(result, MAX_RESULT), _now()))
            c.commit()

    def save(self, t: Task, expect=None) -> bool:
        """Write one task back. False means the row moved under us - someone
        else claimed it, paused it or cancelled it - and the caller must not
        pretend otherwise."""
        with closing(self._connect()) as c:
            ok = self._put_task(c, t, expect=expect)
            c.commit()
            return ok

    # -- the control switches ---------------------------------------------

    def set_flag(self, key: str, value: str = "1") -> None:
        with closing(self._connect()) as c:
            c.execute("INSERT INTO control(key,value,at) VALUES(?,?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value, at=excluded.at",
                      (key, str(value), _now()))
            c.commit()

    def get_flag(self, key: str) -> Optional[str]:
        with closing(self._connect()) as c:
            row = c.execute("SELECT value FROM control WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def clear_flag(self, key: str) -> None:
        with closing(self._connect()) as c:
            c.execute("DELETE FROM control WHERE key=?", (key,))
            c.commit()


# --------------------------------------------------------------------------
#   Actions: the only thing here that leaves the machine
# --------------------------------------------------------------------------

@dataclass
class Action:
    id: str
    kind: str
    title: str
    shown: str                       # the exact words that were on the card
    payload: dict = field(default_factory=dict)
    hash: str = ""
    status: str = "awaiting_review"
    idem: Optional[str] = None
    task_id: Optional[str] = None
    created: float = 0.0
    expires_at: float = 0.0
    decided: str = ""
    decided_by: str = ""
    decided_at: float = 0.0
    result: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


ACTION_FIELDS = tuple(Action.__dataclass_fields__.keys())


class OutcomeUnknown(RuntimeError):
    """Raised by an `execute` that cannot say whether the other side got it -
    a timeout, a connection reset mid-request, an answer that never came.
    This is the ONE error that must never be retried quietly."""


def _action_from(doc) -> Optional[Action]:
    if not isinstance(doc, dict):
        return None
    try:
        return Action(**{k: v for k, v in doc.items() if k in ACTION_FIELDS})
    except Exception:
        return None


def _action_claim(store: Store, action_id: str, want_status: str, new_status: str,
                  *, expires_at: Optional[float] = None,
                  require_unexpired: bool = False, now: Optional[float] = None) -> bool:
    """One SQL statement that moves an action on, and only if it is still
    where the caller thinks it is. A single UPDATE is the whole reason two
    devices approving the same card at the same moment cannot both win: the
    loser's statement changes no rows."""
    now = now if now is not None else _now()
    sql = ("UPDATE actions SET status=?, updated_at=? WHERE id=? AND status=?")
    args: list = [new_status, now, action_id, want_status]
    if require_unexpired:
        sql += " AND expires_at > ?"
        args.append(now)
    with closing(store._connect()) as c:
        cur = c.execute(sql, tuple(args))
        c.commit()
        return cur.rowcount == 1


def get_action(store: Store, action_id: str) -> Optional[Action]:
    with closing(store._connect()) as c:
        row = c.execute("SELECT data FROM actions WHERE id=?", (action_id,)).fetchone()
    if not row:
        return None
    try:
        return _action_from(json.loads(row["data"]))
    except Exception:
        return None


def list_actions(store: Store, status: Optional[str] = None) -> list:
    sql = "SELECT data FROM actions"
    args: tuple = ()
    if status:
        sql += " WHERE status=?"
        args = (status,)
    sql += " ORDER BY updated_at DESC"
    with closing(store._connect()) as c:
        rows = c.execute(sql, args).fetchall()
    out = []
    for r in rows:
        try:
            a = _action_from(json.loads(r["data"]))
        except Exception:
            a = None
        if a is not None:
            out.append(a)
    return out


def propose_action(store: Store, *, kind: str, title: str, shown: str,
                   payload: Optional[dict] = None, idem: Optional[str] = None,
                   task_id: Optional[str] = None, now: Optional[float] = None) -> Action:
    """Put one acting thing in front of the owner.

    `shown` is the card's own words, word for word. The action's hash is
    taken over `kind`, the payload AND those words, so re-wording a card
    without re-asking is impossible: the decision has to carry the same
    hash, and a stale one is refused.

    An `idem` key makes this idempotent - the id is derived from it, so the
    same request twice returns the first action and never makes a second.
    This is the half Jarvis was missing: `decide-once.patch` stops a double
    DECISION, this stops a double REQUEST.
    """
    now = now if now is not None else _now()
    if not str(kind or "").strip():
        raise Refused("an action needs a kind")
    body = {"kind": str(kind), "payload": payload or {}, "shown": _cut(shown, 4000)}
    aid = idempotent_id(idem) if idem else uuid.uuid4().hex
    if idem:
        existing = get_action(store, aid)
        if existing is not None:
            return existing
    action = Action(id=aid, kind=str(kind), title=_cut(title, MAX_TEXT),
                    shown=body["shown"], payload=body["payload"],
                    hash=content_hash(body), idem=str(idem) if idem else None,
                    task_id=task_id, created=now, expires_at=now + ACTION_TTL_SECONDS)
    with closing(store._connect()) as c:
        if idem:
            # INSERT ... DO NOTHING, so two callers racing on one key still
            # produce one action rather than an error or a duplicate.
            cur = c.execute(
                "INSERT INTO actions(id,data,status,idem,expires_at,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (action.id, canonical(action.as_dict()), action.status, action.idem,
                 action.expires_at, now))
            landed = cur.rowcount == 1
        else:
            c.execute("INSERT INTO actions(id,data,status,idem,expires_at,updated_at) "
                      "VALUES(?,?,?,?,?,?)",
                      (action.id, canonical(action.as_dict()), action.status, None,
                       action.expires_at, now))
            landed = True
        c.commit()
    if not landed:
        return get_action(store, aid) or action
    if action.task_id:
        store.add_event(action.task_id, "approval",
                        f"Waiting for you: {action.title}", action.shown)
    return action


def decide_action(store: Store, action_id: str, shown_hash: str, decision: str, *,
                  authorized: bool = False, by: str = "this PC",
                  now: Optional[float] = None) -> Action:
    """Record the owner's answer, and only for the card they were shown.

    Four refusals, each of which is a real failure this project has been
    bitten by or has written down as a risk:

    - **the hash does not match** - "this changed since you looked at it".
      Approving something other than what was read is the one thing a card
      cannot allow.
    - **nobody is there** - `authorized=False` (the default) means the
      Windows Hello / screen-lock check did not pass. Same shape as
      `jarvis_plan.run(approved=False)`: a module that can act on the world
      must not be one call away from doing it by accident.
    - **it expired** - 30 minutes, moved to `expired` by a compare-and-set,
      so a card cannot be answered a day later.
    - **it was already decided** - the state is returned rather than an
      error, because a double tap is not a mistake worth a red message.
    """
    now = now if now is not None else _now()
    if decision not in ("approve", "deny"):
        raise Refused("a decision is approve or deny")
    action = get_action(store, action_id)
    if action is None:
        raise Refused("that card is not in the job list any more")
    if action.status != "awaiting_review":
        return action
    if str(shown_hash or "") != action.hash:
        raise Refused("This changed since it was shown to you. Open the card "
                      "again and decide on the current words.")
    if not authorized:
        raise Refused("nothing was decided: this needs your fingerprint or PIN "
                      "on the PC, and that check did not pass.")
    if action.expires_at <= now:
        # Claim it on the status column first (so two ticks racing on the
        # same expired card do not both write), then record the words. The
        # blob and the column are updated together by `_write_action`.
        if _action_claim(store, action_id, "awaiting_review", "expired", now=now):
            action.status = "expired"
            _write_action(store, action, now)
        raise Refused("That card expired - nothing was done. Ask again and a "
                      "fresh one will be raised.")
    if decision == "deny":
        if not _action_claim(store, action_id, "awaiting_review", "denied", now=now):
            return get_action(store, action_id) or action
        action.status, action.decided, action.decided_by = "denied", "deny", by
        action.decided_at = now
        _write_action(store, action, now)
        if action.task_id:
            store.add_event(action.task_id, "approval",
                            f"You said no: {action.title}", "")
        return action
    # approve: the claim IS the approval. Only the caller whose UPDATE
    # changed a row goes on to execute.
    if not _action_claim(store, action_id, "awaiting_review", "executing",
                         require_unexpired=True, now=now):
        return get_action(store, action_id) or action
    action.status, action.decided, action.decided_by = "executing", "approve", by
    action.decided_at = now
    _write_action(store, action, now)
    if action.task_id:
        store.add_event(action.task_id, "approval", f"You approved: {action.title}", "")
    return action


def _write_action(store: Store, action: Action, now: Optional[float] = None) -> None:
    with closing(store._connect()) as c:
        c.execute("UPDATE actions SET data=?, status=?, updated_at=? WHERE id=?",
                  (canonical(action.as_dict()), action.status,
                   now if now is not None else _now(), action.id))
        c.commit()


def run_action(store: Store, action_id: str, execute: Callable[[Action], object], *,
               approved: bool = False) -> Action:
    """Do the thing. `execute` is supplied by the caller and is where the
    address, the key and the provider's own call live - this module has none
    of those and never will.

    `approved=False` by default. The action must already be `executing`
    (which only a real decision produces), and `approved=True` must be
    passed explicitly, so there are two independent reasons this cannot run
    by accident.

    The outcome is recorded honestly: a call that merely failed is `failed`;
    a call that might have reached the other side is `outcome_unknown`, and
    nothing in this module will ever retry it.
    """
    now = _now()
    action = get_action(store, action_id)
    if action is None:
        raise Refused("that action is not in the job list any more")
    if not approved:
        return action
    if action.status != "executing":
        return action
    try:
        out = execute(action)
        text = out if isinstance(out, str) else canonical(out)
        action.status, action.result = "succeeded", _cut(text, MAX_RESULT)
    except OutcomeUnknown as exc:
        action.status = "outcome_unknown"
        action.error = _cut(str(exc) or UNKNOWN_WORDS, MAX_RESULT)
    except Exception as exc:
        action.status = "failed"
        action.error = _cut(f"{type(exc).__name__}: {exc}", MAX_RESULT)
    _write_action(store, action, now)
    if action.task_id:
        store.add_event(action.task_id,
                        "result" if action.status == "succeeded" else "error",
                        f"{action.title}: {action.status}",
                        action.result or action.error)
    return action


def recover_interrupted(store: Store) -> int:
    """Startup: any action this process left `executing` belongs to a PC
    that stopped mid-send. It becomes `outcome_unknown` - never `failed`,
    which would invite a retry, and never `succeeded`, which would be a
    guess. Called once, when the backend starts."""
    now = _now()
    with closing(store._connect()) as c:
        rows = c.execute("SELECT data FROM actions WHERE status='executing'").fetchall()
        n = 0
        for r in rows:
            try:
                a = _action_from(json.loads(r["data"]))
            except Exception:
                a = None
            if a is None:
                continue
            a.status, a.error = "outcome_unknown", UNKNOWN_WORDS
            c.execute("UPDATE actions SET data=?, status=?, updated_at=? WHERE id=?",
                      (canonical(a.as_dict()), a.status, now, a.id))
            n += 1
        c.commit()
    return n


# --------------------------------------------------------------------------
#   The job list
# --------------------------------------------------------------------------

class JobList:
    """The whole public face: add a job, tick it, steer it, read it.

    Every method that can act takes its ability to act from the caller, so
    this class owns no tool, no key and no address. Every method that can
    refuse does, in words the owner can read."""

    def __init__(self, store: Optional[Store] = None):
        self.store = store or Store()

    # -- adding ------------------------------------------------------------

    def enqueue(self, title: str, goal: str, steps: list, *, kind: str = "job",
                task_id: Optional[str] = None) -> Task:
        """Add one job. Refuses in words rather than accepting anything it
        cannot honestly run: no steps, too many steps, a step with no tool
        or no reason, a queue already full.

        A step is `{"tool": ..., "args": {...}, "why": ..., "risky": bool,
        "acts": bool, "retry_safe": bool}`. **`acts` defaults to True** -
        assume a step changes something until the caller says otherwise, so
        an interrupted step blocks and asks rather than being retried
        behind the owner's back. `retry_safe` says a step may be served from
        the memo and re-run after an interruption; a step that leaves the
        machine must never set it.
        """
        title = _cut(title, MAX_TEXT)
        goal = _cut(goal, MAX_TEXT)
        if not title:
            raise Refused("a job needs a name")
        if not isinstance(steps, list) or not steps:
            raise Refused("a job needs at least one step")
        if len(steps) > MAX_STEPS:
            raise Refused(f"a job can have at most {MAX_STEPS} steps - split it into "
                          "smaller jobs")
        waiting = self.store.list_tasks("queued") + self.store.list_tasks("waiting_approval")
        if len(waiting) >= MAX_WAITING:
            raise Refused(f"there are already {len(waiting)} jobs waiting. Finish or "
                          "cancel one first - nothing was added.")
        clean = []
        for i, s in enumerate(steps, 1):
            if not isinstance(s, dict):
                raise Refused(f"step {i} is not a step")
            tool = _cut(s.get("tool"), 80)
            why = _cut(s.get("why"), MAX_TEXT)
            if not tool:
                raise Refused(f"step {i} does not name a tool")
            if not why:
                raise Refused(f"step {i} does not say why")
            args = s.get("args") if isinstance(s.get("args"), dict) else {}
            from_step = s.get("from_step")
            slots = [int(m) for m in SLOT.findall(canonical(args))]
            if from_step is not None:
                if (not isinstance(from_step, int) or isinstance(from_step, bool)
                        or not 0 <= from_step < i - 1):
                    raise Refused(f"step {i} names an earlier step that does not exist")
                if not slots:
                    raise Refused(f"step {i} says it uses step {from_step + 1}'s result, "
                                  f"but none of its arguments says where - put "
                                  f"{{{{step {from_step + 1}}}}} in the argument that "
                                  "uses it")
                if any(n != from_step + 1 for n in slots):
                    raise Refused(f"step {i} can only use the result of step "
                                  f"{from_step + 1}, the one its from_step names")
            elif slots:
                # A stray placeholder would run with the braces still in it -
                # a step acting on the literal text "{{step 1}}" instead of
                # the value. Refused, never guessed at (jarvis_plan.py makes
                # the same refusal for the same reason).
                raise Refused(f"step {i} uses an earlier step's result ({{{{step "
                              f"{slots[0]}}}}}) but does not say which step in from_step")
            clean.append({"tool": tool, "args": args, "why": why,
                          "risky": bool(s.get("risky")),
                          "from_step": from_step,
                          "acts": bool(s.get("acts", True)),
                          "retry_safe": bool(s.get("retry_safe"))})
        t = Task(id=task_id or uuid.uuid4().hex, title=title, goal=goal, steps=clean,
                 kind=_cut(kind, 40) or "job", status="queued")
        self.store.add_task(t)
        self.store.add_event(t.id, "plan", f"Added: {title}", f"{len(clean)} step(s)")
        return t

    # -- steering (never gated: stopping is always allowed) ----------------

    def _move(self, task_id: str, to: str, *, states=("queued", "running",
                                                     "waiting_approval",
                                                     "waiting_input", "blocked",
                                                     "paused")) -> Task:
        t = self.store.get_task(task_id)
        if t is None:
            raise Refused("that job is not in the list any more")
        if t.status not in states:
            return t
        old_status, old_lease = t.status, t.lease_id or ""
        t.status, t.lease_id, t.lease_until = to, None, 0.0
        if not self.store.save(t, expect=(old_status, old_lease)):
            return self.store.get_task(task_id) or t
        self.store.add_event(t.id, "status", f"{to}", "")
        return t

    def pause(self, task_id: str) -> Task:
        return self._move(task_id, "paused", states=("queued", "running",
                                                    "waiting_approval", "blocked"))

    def resume(self, task_id: str) -> Task:
        t = self.store.get_task(task_id)
        if t is None:
            raise Refused("that job is not in the list any more")
        if t.status != "paused":
            raise Refused("only a paused job can be resumed")
        return self._move(task_id, "queued", states=("paused",))

    def cancel(self, task_id: str) -> Task:
        return self._move(task_id, "cancelled")

    def retry(self, task_id: str) -> Task:
        """Try the interrupted step again - a deliberate act by the owner,
        never something this module does on its own."""
        t = self.store.get_task(task_id)
        if t is None:
            raise Refused("that job is not in the list any more")
        if t.status not in ("failed", "blocked", "cancelled"):
            raise Refused("only a job that stopped can be retried")
        old_status, old_lease = t.status, t.lease_id or ""
        t.status, t.lease_id, t.lease_until = "queued", None, 0.0
        t.error, t.question, t.inflight = "", "", None
        if not self.store.save(t, expect=(old_status, old_lease)):
            return self.store.get_task(task_id) or t
        self.store.add_event(t.id, "status", "retry", f"step {t.at + 1} again")
        return t

    def answer(self, task_id: str, text: str) -> Task:
        """Answer a job that stopped to ask something (`waiting_input`)."""
        t = self.store.get_task(task_id)
        if t is None:
            raise Refused("that job is not in the list any more")
        if t.status != "waiting_input":
            raise Refused("that job is not waiting on a question")
        t.answer = _cut(text, MAX_TEXT)
        t.status = "queued"
        t.lease_id = None
        self.store.save(t)
        self.store.add_event(t.id, "observation", "You answered", t.answer)
        return t

    def request_stop(self) -> None:
        """Stop everything. Ungated and immediate, the same as the existing
        Stop-everything hotkey: a stop that had to be approved would not be
        a stop."""
        self.store.set_flag("stop", "1")
        self.store.add_event("", "status", "stop", "everything was asked to stop")

    def clear_stop(self) -> None:
        self.store.clear_flag("stop")

    def stop_requested(self) -> bool:
        return (self.store.get_flag("stop") or "") == "1"

    # -- reading -----------------------------------------------------------

    def status(self) -> dict:
        """The counted summary the apps may show. Deliberately NOT the
        owner's own words: ids, tool names, counts and states only - the
        same rule `jarvis_task_control.status()` already follows, so a job
        list cannot become a new way for private text to reach a lock
        screen. The readable feed is `feed()`, for the PC's own window.
        """
        tasks = self.store.list_tasks()
        by = {}
        for t in tasks:
            by[t.status] = by.get(t.status, 0) + 1
        return {
            "counts": by,
            "waiting": by.get("queued", 0) + by.get("waiting_approval", 0),
            "running": by.get("running", 0),
            "blocked": by.get("blocked", 0),
            "stop": self.stop_requested(),
            "tasks": [{"id": t.id, "state": t.status, "kind": t.kind,
                       "step": t.at + 1, "steps": len(t.steps),
                       "attempts": t.attempts,
                       "tools": [s.get("tool") for s in t.steps],
                       # A job that cannot go on without the owner: one blocked
                       # by an interrupted step, or one that stopped to ask a
                       # question. Both carry the caller's own sentence, and
                       # both are what a screen offers an answer or a Retry
                       # for. `question` must be the CALLER's words about what
                       # is missing - never the text of a note, an email or a
                       # message - the same rule jarvis_task_control.status()
                       # follows, for the same reason: a phone reads this.
                       "needs_attention": t.status in ("blocked", "waiting_input"),
                       "question": (t.question if t.status in ("blocked", "waiting_input")
                                    else "")}
                      for t in tasks],
        }

    def feed(self, task_id: Optional[str] = None, limit: int = 50) -> list:
        """The readable record - what ran, when, and how it ended - with the
        step results. **For the PC's own window only**, the same as
        `jarvis_task_control`'s notes: it carries the owner's own material,
        so it must never be sent to a phone's lock screen."""
        return self.store.events(task_id, limit)

    # -- the tick ----------------------------------------------------------

    def _due(self, now: float) -> list:
        """Jobs a tick may work on. `scheduled` is deliberately absent: this
        module is not a clock. A caller that wanted a job to start at a time
        flips it to `queued` when its own scheduler says so."""
        due = []
        for t in self.store.list_tasks():
            if t.status in ("queued", "waiting_approval"):
                due.append(t)
        due.sort(key=lambda t: t.created)
        return due

    def _recover_leases(self, now: float) -> list:
        """A `running` job whose lease has run out is a backend that died
        mid-step. What happens next depends on the step, and this is the
        honest part:

        - **a step that acts** (the default) - nobody knows whether it
          happened. The job goes to `blocked`, with the module's own words
          asking the owner to check and then Retry or Cancel. Any action of
          that job left `executing` becomes `outcome_unknown` too.
        - **a step that only reads** (`acts: False`) - safe to do again, so
          the job simply goes back to `queued`.
        """
        out = []
        for t in self.store.list_tasks("running"):
            # A live lease means someone is working on it - leave it alone.
            # A MISSING or past lease with `running` is a backend that died.
            if t.lease_until and t.lease_until > now:
                continue
            old_lease = t.lease_id or ""
            flight = t.inflight or {}
            if flight and flight.get("acts", True):
                t.status, t.error = "blocked", UNKNOWN_WORDS
                t.question = (f"Step {int(flight.get('index', 0)) + 1} "
                              f"({flight.get('tool', 'a step')}) was part-way through when "
                              "the PC stopped. It may already have happened. Check, then "
                              "choose Retry or Cancel.")
                self._orphan_actions(t.id)
                kind = "error"
            else:
                t.status = "queued"
                kind = "status"
            t.lease_id, t.lease_until, t.inflight = None, 0.0, None
            self._end_run(t, "interrupted", "the process stopped mid-run")
            if self.store.save(t, expect=("running", old_lease)):
                self.store.add_event(t.id, kind, "Picked up again after a restart",
                                     t.error)
                out.append({"id": t.id, "state": t.status})
        return out

    def _end_run(self, t: Task, status: str, detail: str = "") -> None:
        """Close this attempt's receipt. A run row is per tick, so it is
        closed on every way out of one - finished, checkpointed, waiting,
        failed, or found dead at startup."""
        if t.run_id:
            self.store.finish_run(t.run_id, status, detail)
            t.run_id = None

    def _orphan_actions(self, task_id: str) -> int:
        """Any action of this job that was mid-flight becomes unknown. Never
        retried by this module, whatever the owner chooses later."""
        n = 0
        for a in list_actions(self.store, "executing"):
            if a.task_id != task_id:
                continue
            if _action_claim(self.store, a.id, "executing", "outcome_unknown"):
                a.status, a.error = "outcome_unknown", UNKNOWN_WORDS
                _write_action(self.store, a)
                n += 1
        return n

    def _claim(self, t: Task, now: float) -> Optional[Task]:
        old_status, old_lease = t.status, t.lease_id or ""
        t.lease_id = uuid.uuid4().hex
        t.lease_until = now + LEASE_SECONDS
        # An attempt is a step actually being tried. A job that is only
        # WAITING on a card is re-claimed every tick, and counting those
        # would make a job that asked once look like it had tried five times.
        if old_status == "queued":
            t.attempts += 1
        t.status = "running"
        if not self.store.save(t, expect=(old_status, old_lease)):
            return None
        t.run_id = self.store.add_run(t.id, "running", f"attempt {t.attempts}")
        self.store.save(t, expect=("running", t.lease_id or ""))
        return t

    def tick(self, run_step: Callable[[dict], object], *, ask=None,
             ledger: Optional[Callable[[dict], None]] = None,
             now: Optional[float] = None, max_in_flight: int = MAX_IN_FLIGHT) -> dict:
        """Work the list a little, then return. At most ONE step per job, at
        most `max_in_flight` jobs, never a wait for the owner inside the
        tick - so the Jarvis bar, the voice path and the apps keep working
        while a job runs.

        `run_step(step)` does the step and returns its result; it may raise
        `StopRequested` (the owner stopped) or `LostLease` (the claim went
        away). `ask(step)` raises that step's own approval card if it needs
        one, and returns a `Verdict`, or `None` for "not decided yet" - in
        which case the job waits and a later tick asks again. `ledger`, if
        given, is handed one small record per finished step, for the
        existing read-only activity list.
        """
        now = now if now is not None else _now()
        report: dict = {"now": _iso(now), "stop": self.stop_requested(),
                        "reconciled": self.store.reconcile_runs(),
                        "recovered": [], "claimed": [], "steps": [],
                        "waiting": [], "finished": [], "blocked": [], "deferred": []}
        if report["stop"]:
            return report
        report["recovered"] = self._recover_leases(now)
        for t in self._due(now)[:max(0, max_in_flight)]:
            claimed = self._claim(t, now)
            if claimed is None:
                report["deferred"].append({"id": t.id, "why": "someone else took it"})
                continue
            report["claimed"].append(claimed.id)
            self._one_step(claimed, run_step=run_step, ask=ask, report=report,
                           ledger=ledger, now=now)
        return report

    def _one_step(self, t: Task, *, run_step, ask, report, ledger, now) -> None:
        lease = t.lease_id or ""
        n = len(t.steps)
        if t.at >= n:
            self._finish(t, "succeeded", "every step finished", report)
            return
        step = t.steps[t.at]
        index = t.at
        # A step that uses an earlier step's result is asked about and run
        # with the REAL value, never the placeholder (see `fill_from_done`).
        if step.get("from_step") is not None:
            step = fill_from_done(step, t.done)

        # -- a step that needs its own card --------------------------------
        if step.get("risky") or step.get("from_step") is not None:
            verdict = None
            if ask is not None:
                try:
                    verdict = ask(step)
                except Exception as exc:
                    report["blocked"].append({"id": t.id, "why": f"ask failed: {exc}"})
                    t.status, t.lease_id, t.inflight = "blocked", None, None
                    t.error = f"could not raise the card for step {index + 1}: {exc}"
                    self._end_run(t, "failed", t.error)
                    self.store.save(t, expect=("running", lease))
                    return
            if verdict is None:
                t.status, t.lease_id, t.lease_until, t.asked = "waiting_approval", None, 0.0, {
                    "index": index, "tool": step.get("tool")}
                t.inflight = None
                self._end_run(t, "waiting", f"waiting on step {index + 1}")
                if self.store.save(t, expect=("running", lease)):
                    self.store.add_event(t.id, "approval",
                                         f"Waiting for your answer on step {index + 1}",
                                         str(step.get("tool")))
                    report["waiting"].append({"id": t.id, "step": index + 1})
                return
            outcome = getattr(verdict, "outcome", "denied")
            if getattr(verdict, "allowed", False) is not True:
                if outcome == "timed_out":
                    # NOT a refusal. Nobody answered, so nothing was done and
                    # the job waits rather than dying - the whole point of
                    # gate-outcome.patch's separate `timed_out`.
                    t.status, t.lease_id, t.lease_until, t.inflight = "queued", None, 0.0, None
                    self._end_run(t, "waiting", "the card timed out")
                    if self.store.save(t, expect=("running", lease)):
                        self.store.add_event(
                            t.id, "status", "The card timed out",
                            "nobody answered, so nothing was done - it will ask again")
                        report["deferred"].append({"id": t.id, "why": "card timed out"})
                    return
                t.status, t.lease_id, t.inflight = "failed", None, None
                t.error = (f"you said no at step {index + 1} "
                           f"({step.get('tool')}) - nothing after it ran")
                self._end_run(t, "failed", t.error)
                if self.store.save(t, expect=("running", lease)):
                    self.store.add_event(t.id, "error", f"Stopped at step {index + 1}",
                                         t.error)
                    report["finished"].append({"id": t.id, "state": "failed"})
                return

        # -- the memo: a step already done is not done twice ----------------
        key = memo_key(step.get("tool", ""), step.get("args", {}))
        reused = None
        if step.get("retry_safe"):
            reused = self.store.memo_get(key)
        if reused is not None:
            self._record_step(t, index, step, reused, report, ledger, lease,
                              kind="observation",
                              title=f"Step {index + 1} already done - used the recorded "
                                    "result")
            return

        # -- run it ---------------------------------------------------------
        t.inflight = {"index": index, "tool": step.get("tool"),
                      "acts": bool(step.get("acts", True))}
        if not self.store.save(t, expect=("running", lease)):
            report["deferred"].append({"id": t.id, "why": "lost the lease"})
            return
        if self.stop_requested():
            t.status, t.lease_id, t.lease_until, t.inflight = "queued", None, 0.0, None
            self._end_run(t, "stopped", "stopped before the step")
            self.store.save(t, expect=("running", lease))
            report["deferred"].append({"id": t.id, "why": "stopped before the step"})
            return
        try:
            out = run_step(step)
        except StopRequested:
            t.status, t.lease_id, t.lease_until, t.inflight = "queued", None, 0.0, None
            self._end_run(t, "stopped", f"stopped during step {index + 1}")
            if self.store.save(t, expect=("running", lease)):
                self.store.add_event(t.id, "status", "Stopped by you",
                                     f"before step {index + 1} finished")
                report["deferred"].append({"id": t.id, "why": "stopped"})
            return
        except LostLease:
            t.lease_id, t.lease_until, t.inflight = None, 0.0, None
            t.status = "queued"
            self._end_run(t, "interrupted", "the lease was taken away")
            self.store.save(t, expect=("running", lease))
            report["deferred"].append({"id": t.id, "why": "lost the lease"})
            return
        except Exception as exc:
            t.status, t.lease_id, t.inflight = "failed", None, None
            t.error = f"step {index + 1} ({step.get('tool')}) failed: {type(exc).__name__}: {exc}"
            self._end_run(t, "failed", t.error)
            if self.store.save(t, expect=("running", lease)):
                self.store.add_event(t.id, "error", f"Step {index + 1} failed", t.error)
                report["finished"].append({"id": t.id, "state": "failed"})
            return

        text = out if isinstance(out, str) else canonical(out)
        if step.get("retry_safe"):
            self.store.memo_put(key, text)
        self._record_step(t, index, step, text, report, ledger, lease, kind="step",
                          title=f"Step {index + 1}/{n}: {step.get('tool')}")

    def _record_step(self, t: Task, index: int, step: dict, text: str, report,
                     ledger, lease: str, *, kind: str, title: str) -> None:
        """A finished step becomes a fact on disk before anything else is
        considered - the checkpoint.

        The lease is GIVEN BACK here rather than held. One tick is one step:
        holding the lease for the rest of the job would block the next step
        until it expired, which on a 60-second lease turns a three-step job
        into a three-minute one. The compare-and-set is what makes giving it
        back safe - if the row moved while the step ran, the checkpoint is
        discarded rather than written over someone else's work.
        """
        t.done.append({"index": index, "tool": step.get("tool"),
                       "why": step.get("why"), "result": _cut(text, MAX_RESULT),
                       "at": _iso()})
        t.at = index + 1
        t.inflight = None
        t.asked = None
        finished = t.at >= len(t.steps)
        t.lease_id, t.lease_until = None, 0.0
        t.status = "succeeded" if finished else "queued"
        self._end_run(t, "succeeded" if finished else "checkpoint",
                      f"step {index + 1} of {len(t.steps)}")
        if not self.store.save(t, expect=("running", lease)):
            report["deferred"].append({"id": t.id, "why": "lost the lease at the checkpoint"})
            return
        self.store.add_event(t.id, kind, title, _cut(text, MAX_FEED))
        if ledger is not None:
            try:
                ledger({"task": t.id, "step": index + 1, "tool": step.get("tool"),
                        "state": "succeeded", "at": _iso()})
            except Exception:
                pass
        report["steps"].append({"id": t.id, "step": index + 1, "tool": step.get("tool")})
        if finished:
            self._finish(t, "succeeded", "every step finished", report, already_saved=True)

    def _finish(self, t: Task, state: str, detail: str, report, *,
                already_saved: bool = False) -> None:
        t.status, t.lease_id, t.lease_until, t.inflight = state, None, 0.0, None
        self._end_run(t, state, detail)
        if not already_saved:
            self.store.save(t)
        self.store.add_event(t.id, "result", f"{state}: {detail}", "")
        report["finished"].append({"id": t.id, "state": state})


# --------------------------------------------------------------------------
#   The split: a chat turn hands the work to a job
# --------------------------------------------------------------------------

def _field(source, name, default=None):
    """Read a value from either a dict or an object. The plan card's own
    `PlanStep` is a dataclass, and a caller may equally hand over plain
    dicts; accepting both keeps `jarvis_plan` an optional neighbour rather
    than a hard dependency of this module."""
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def plan_steps(plan) -> list:
    """A `jarvis_plan.Plan`'s steps as this module's step dicts, with nothing
    softened:

    - **`risky` is carried over exactly.** A step the plan called risky is
      still asked about on its own card when its turn comes, so approving the
      job never approves it (`jarvis_plan.py`'s condition 1).
    - **`from_step` is carried over exactly**, so a step whose arguments come
      from an earlier step's real result is asked again, individually, with
      the value it will actually use (condition 2).
    - **`acts` is True for every step of a plan, and `retry_safe` is False.**
      A plan's own `PlanStep` says nothing about either, so the safe reading
      is chosen: assume a step changes something until a caller says
      otherwise, and never reuse a recorded result in place of running it.
      A read-only step may be marked `acts: False` by whoever built the plan.
    """
    out = []
    for s in (_field(plan, "steps", []) or []):
        out.append({
            "tool": _field(s, "tool", ""),
            "args": dict(_field(s, "args", {}) or {}),
            "why": _field(s, "why", ""),
            "risky": bool(_field(s, "risky", False)),
            "from_step": _field(s, "from_step", None),
            "acts": bool(_field(s, "acts", True)),
            "retry_safe": bool(_field(s, "retry_safe", False)),
        })
    return out


def job_id_for_plan(plan_key: str) -> str:
    """The id a given plan gets, so the SAME plan approved twice makes one
    job rather than two. Same idea as an action's idempotency key, one layer
    up: that stops a double send, this stops a double job."""
    return hashlib.sha256(("jarvis-job:" + str(plan_key)).encode("utf-8")).hexdigest()


def from_plan(job_list: "JobList", plan, *, approved: bool = False,
              plan_key: Optional[str] = None, kind: str = "plan") -> Task:
    """Hand an APPROVED plan to the job list, and nothing else.

    This is the whole of the chat/jobs split in one function: the turn that
    talked to the owner stops being the thing that runs the steps. The job
    runs them, one per tick, each through the same gate as always - so a
    job can outlive the turn, survive a restart, be paused or stopped, and
    still never act without its own card.

    `approved=False` by default, and a plan that is not approved adds
    NOTHING - the same shape as `jarvis_plan.run(approved=False)` and
    `run_action(approved=False)`. A module that can put work in motion must
    not be one call away from doing it by accident.

    `plan_key` makes it idempotent: the same key returns the job that
    already exists instead of making a second one.

    Nothing here approves a step, and nothing here can: `plan_steps` keeps
    every `risky` and `from_step` flag intact, and the job asks about those
    on their own cards when their turn comes.
    """
    if not approved:
        raise Refused("nothing was added: the plan was not approved")
    goal = str(_field(plan, "goal", "") or "")
    steps = plan_steps(plan)
    if not steps:
        raise Refused("nothing was added: that plan has no steps")
    tid = job_id_for_plan(plan_key) if plan_key else None
    if tid:
        existing = job_list.store.get_task(tid)
        if existing is not None:
            return existing
    title = goal or "A job"
    return job_list.enqueue(title, goal, steps, kind=kind, task_id=tid)


def gate_ask(gate_check: Callable[[dict], object], *, undecided=None):
    """Adapt the ONE approval gate into the `ask` the worker's `tick()` calls.

    The worker never imports `jarvis_gate` and cannot approve anything; this
    is the only place the two meet, and everything it does is in one
    direction - it hands the step to the gate that already exists and reports
    what came back:

    - the gate says `allowed is True` -> the step may run (and only then);
    - the gate says anything else -> the step does not run. A `timed_out`
      still waits (the worker's own rule: an unanswered card is not a
      refusal), a `denied` or `refused` stops the job at that step, and the
      steps already done stay done;
    - the gate answers `None` -> **not decided yet**; the job waits and a
      later tick asks again, so a card is never waited on inside a tick;
    - the gate RAISES -> `None`, the same as "not decided". A gate that
      cannot answer has not answered, and the one wrong answer here would be
      to treat its silence as permission.
    """
    def ask(step: dict):
        try:
            verdict = gate_check(step)
        except Exception:
            return None
        if verdict is None:
            return undecided
        allowed = getattr(verdict, "allowed", False) is True
        outcome = str(getattr(verdict, "outcome", "") or "")
        # `allowed` outranks the word. The real gate cannot produce the pair
        # "not allowed, but the outcome says approved" - gate-outcome.patch's
        # `Verdict.__post_init__` enforces the other direction, that only
        # auto/notify/approved may carry allowed=True. This is the seam where
        # the opposite slip would become a lie in the run feed and on the
        # screen, and one word is all it costs to make that impossible.
        if not allowed and outcome in ("approved", "auto", "notify"):
            outcome = "denied"
        if not outcome:
            outcome = "approved" if allowed else "denied"
        return Verdict(allowed=allowed, outcome=outcome,
                       reason=str(getattr(verdict, "reason", "") or ""),
                       request_id=getattr(verdict, "request_id", None))
    return ask


# --------------------------------------------------------------------------
#   Startup, and the one call the patch makes
# --------------------------------------------------------------------------

def startup(store: Optional[Store] = None) -> dict:
    """Everything that must happen once, when the backend starts:

    - runs a dead process left `running` are marked `interrupted`, so the
      activity list does not show a job that "finished" by dying;
    - any ACTION left `executing` becomes `outcome_unknown`. This is the
      important one: a restart in the middle of a send must never look like
      a failure to retry or a success to believe.
    - a Stop left on from a previous run is cleared, because Stop means
      "stop what is happening now", not "stay stopped for ever".
    """
    st = store or Store()
    unknown = recover_interrupted(st)
    interrupted = st.reconcile_runs()
    st.clear_flag("stop")
    if unknown:
        st.add_event("", "error", "A step was interrupted while it was going out",
                     UNKNOWN_WORDS)
    return {"interrupted_runs": interrupted, "outcome_unknown": unknown}


def boot_once(store: Optional[Store] = None) -> dict:
    """`startup()`, once per process. The patch calls this from the first
    route that touches the job list, so recovery happens whether or not the
    backend has a convenient startup hook to hang it on - and a second call
    in the same process costs nothing."""
    global _BOOTED
    if _BOOTED is not None:
        return _BOOTED
    _BOOTED = startup(store)
    return _BOOTED


_BOOTED: Optional[dict] = None


def guard(store: Optional[Store] = None) -> None:
    """Raise unless it is still right to keep going. The caller's `run_step`
    calls this before doing anything that matters: it is how a Stop pressed
    while a step was running takes effect at the step AFTER it, and how a
    job whose lease was taken away stops writing."""
    if (store or Store()).get_flag("stop") == "1":
        raise StopRequested("the owner asked everything to stop")


