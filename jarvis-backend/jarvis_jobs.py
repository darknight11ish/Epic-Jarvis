"""jarvis_jobs.py - Long Fuse: work that outlives the conversation.

"Research this and tell me tomorrow." "Watch that repo and say something if
it moves." Those are not tool calls. A tool call starts and finishes inside
one turn, with a human sitting there; a job starts in one conversation,
finishes in another, and usually finishes while nobody is looking. Everything
awkward about this module follows from that one sentence.

NOBODY IS LOOKING, SO APPROVAL CANNOT BE LIVE
The gate asks a human and blocks until they answer. A job cannot do that -
there is no human, and there will not be one for hours. So the permission
question is moved forward in time: when the job is created, the capabilities
it may use are written onto its row and frozen there. Execution may use that
set and may never exceed it. There is no widening path, deliberately; a job
that turns out to need something else queues a one-shot grant and parks,
and if nobody ever answers it parks for ever rather than proceeding.

NOBODY IS LOOKING, SO TAINT CANNOT BE AMBIENT
The gate's taint latch is a timer on a global conversation. A job created on
Tuesday inside a tainted conversation may not run on Wednesday, after the
latch has long expired, and quietly hand personal context to a cloud lane.
So taint is copied onto the row at creation and carried for the job's whole
life. It is one-directional: a caller can add taint, never remove it.

NOBODY IS LOOKING, SO THE RESULT MUST NOT SPEAK
A job that finishes at 03:00 must not say so at 03:00. Results sit on the
row until something collects them (see `collect`). This module has no voice
path and no push path at all, which is the enforcement.

THE DATABASE IS THE INTERESTING PART
Jobs are rows, so a restart loses nothing. But this database's neighbours -
the approval queue, the memory extractor, the heartbeat - are already
writing to SQLite from several threads in this process, and the obvious
implementation (a connection per thread, each one writing when it likes)
produces `database is locked` under exactly the load a job scheduler
creates. See `_writer_loop` for why one queue and one thread was the answer
instead.
"""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

DB_PATH = Path(os.environ.get("JARVIS_JOBS_DB", _CFG_DIR / "jobs.db"))

STATES = ("queued", "running", "waiting_approval", "done", "failed", "cancelled")
TERMINAL = ("done", "failed", "cancelled")


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("jobs", {}).get(key, default)
    except Exception:
        return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


class JobsUnavailable(RuntimeError):
    """The job store could not be reached or trusted. Raised rather than
    returned, because every caller of this module is deciding whether work
    happens, and a function that returns None on failure gets its None
    ignored."""


class Cancelled(Exception):
    """Raised inside a handler when the owner cancelled the job."""


class NeedsApproval(Exception):
    """Raised inside a handler when it asked for a capability the frozen set
    does not carry. Not an error: the job parks, it does not fail."""

    def __init__(self, action: str, reason: str = "", denied: bool = False):
        super().__init__(reason or f"needs approval for {action}")
        self.action, self.reason, self.denied = action, reason, denied


# --------------------------------------------------------------------------
#   Storage: one writer, and why
# --------------------------------------------------------------------------

_QUEUE: "queue.Queue" = queue.Queue()
_WRITER: Optional[threading.Thread] = None
_WRITER_READY = threading.Event()
_WRITER_ERROR: Optional[str] = None
_WRITER_LOCK = threading.Lock()
_INIT_LOCK = threading.RLock()
_inited = False


@dataclass
class _Write:
    fn: Callable[[sqlite3.Connection], Any]
    done: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Optional[BaseException] = None


def _busy_timeout() -> float:
    try:
        return max(1.0, float(_cfg("busy_timeout_seconds", 10)))
    except (TypeError, ValueError):
        return 10.0


def _connect_read() -> sqlite3.Connection:
    """A short-lived read connection. Under WAL a reader never blocks a
    writer and never holds a lock a writer has to wait for, so reads are
    allowed to be casual in a way writes are not."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=_busy_timeout(),
                           isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _writer_loop() -> None:
    """The only thread that writes to jobs.db.

    WHY NOT A CONNECTION PER THREAD, which is what every SQLite tutorial
    shows and what the rest of this codebase does for its small tables:
    SQLite allows exactly one writer at a time per database. With a
    connection per thread, "one at a time" is enforced by every other thread
    sitting in a busy handler, and when the handler's timeout elapses the
    caller gets `database is locked` - an exception, not a delay. The job
    scheduler is the worst possible shape for that: a tick claims several
    jobs at once, each running job writes progress, the HUD cancels one, the
    memory extractor and the approval queue are writing to neighbouring
    files on the same disk, and WAL's single-writer rule turns all of it into
    a lock convoy. Raising the busy timeout does not fix it; it only decides
    how long you wait before the same exception.

    So the contention is moved somewhere it can be handled honestly: a queue.
    Writers hand over a function and block on an Event; this thread applies
    them one at a time on ONE connection. Serialisation happens in Python,
    where waiting is cheap and ordered, instead of in SQLite's busy handler,
    where waiting is a spin and the loser gets an error. It also means the
    connection never crosses a thread boundary, so sqlite3's
    check_same_thread default stays on rather than being switched off to
    make the tutorial shape work.

    What this does NOT solve is a second PROCESS writing (the HUD proxy and
    OpenJarvis are separate). That is what WAL plus busy_timeout is for, and
    cross-process write volume here is a handful of rows a minute.
    """
    global _WRITER_ERROR
    conn: Optional[sqlite3.Connection] = None
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), timeout=_busy_timeout(),
                               isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={int(_busy_timeout() * 1000)}")
        # FULL, not NORMAL. NORMAL can lose the last few transactions when
        # the machine loses power, and the whole promise of this module is
        # that a job you scheduled is still there tomorrow. The write volume
        # is a few rows a minute, so the fsync costs nothing that matters.
        conn.execute("PRAGMA synchronous=FULL")
    except Exception as exc:
        _WRITER_ERROR = f"{type(exc).__name__}: {exc}"
        conn = None
    finally:
        _WRITER_READY.set()

    while True:
        item = _QUEUE.get()
        if item is None:                       # shutdown sentinel
            break
        if conn is None:
            item.error = JobsUnavailable(
                f"the jobs database could not be opened ({_WRITER_ERROR})")
            item.done.set()
            continue
        try:
            item.result = item.fn(conn)
        except BaseException as exc:           # noqa: BLE001 - handed to the caller
            item.error = exc
        finally:
            item.done.set()
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def _start_writer() -> None:
    global _WRITER
    with _WRITER_LOCK:
        if _WRITER is not None and _WRITER.is_alive():
            return
        _WRITER_READY.clear()
        _WRITER = threading.Thread(target=_writer_loop, daemon=True,
                                   name="jarvis-jobs-writer")
        _WRITER.start()
    _WRITER_READY.wait(timeout=_busy_timeout() + 5.0)


def _write(fn: Callable[[sqlite3.Connection], Any],
           timeout: Optional[float] = None) -> Any:
    """Apply `fn` on the writer thread and return what it returned.

    Blocks. A timeout raises rather than returning, because a caller that
    thinks it wrote a job row and did not would schedule work that never
    runs and report success to the owner.
    """
    _start_writer()
    if _WRITER_ERROR:
        raise JobsUnavailable(_WRITER_ERROR)
    if timeout is None:
        try:
            timeout = float(_cfg("write_timeout_seconds", 15))
        except (TypeError, ValueError):
            timeout = 15.0
    item = _Write(fn=fn)
    _QUEUE.put(item)
    if not item.done.wait(timeout):
        raise JobsUnavailable("the jobs writer did not answer within "
                              f"{timeout}s; the job was NOT recorded")
    if item.error is not None:
        raise item.error
    return item.result


def _read(sql: str, params: tuple = ()) -> list:
    _init()
    with closing(_connect_read()) as c:
        return c.execute(sql, params).fetchall()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id         TEXT PRIMARY KEY,
    handler    TEXT NOT NULL,
    params     TEXT NOT NULL,          -- JSON object, never code
    label      TEXT NOT NULL,
    caps       TEXT NOT NULL,          -- JSON list, frozen at creation
    tainted    INTEGER NOT NULL,       -- copied from the gate at creation
    state      TEXT NOT NULL,
    progress   REAL NOT NULL DEFAULT 0,
    note       TEXT,
    due        REAL NOT NULL,
    created    REAL NOT NULL,
    started    REAL,
    finished   REAL,
    heartbeat  REAL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    cancel     INTEGER NOT NULL DEFAULT 0,
    result     TEXT,
    error      TEXT,
    delivered  REAL                    -- NULL until collect() takes it
);
CREATE INDEX IF NOT EXISTS ix_jobs_due ON jobs(state, due);
CREATE INDEX IF NOT EXISTS ix_jobs_undelivered ON jobs(delivered, finished);

CREATE TABLE IF NOT EXISTS job_grants (
    id      TEXT PRIMARY KEY,
    job_id  TEXT NOT NULL,
    action  TEXT NOT NULL,
    state   TEXT NOT NULL,             -- pending|granted|denied
    created REAL NOT NULL,
    decided REAL,
    decided_by TEXT,
    used    REAL                       -- a grant is one shot; this spends it
);
CREATE INDEX IF NOT EXISTS ix_grants ON job_grants(job_id, action, state);
"""


def _init() -> None:
    global _inited
    with _INIT_LOCK:
        if _inited:
            return
        _write(lambda c: c.executescript(_SCHEMA))
        _write(_reclaim)
        _inited = True


def _reclaim(c: sqlite3.Connection) -> dict:
    """A process that died mid-run leaves a row saying `running` with nobody
    running it, exactly as jarvis_gate.py's approvals table ends up with a
    `pending` row nobody is waiting on. Same treatment: anything whose
    heartbeat is older than it could plausibly be while alive did not
    survive, and is taken back on the next init.

    Taken back to `queued`, not to `failed`, because most job bodies are a
    search or a fetch and re-running one costs a request. The attempt counter
    is what stops that being a loop: a job that has died `max_attempts` times
    is failing in a way a retry will not fix, so it is failed with that said
    out loud. HANDLERS MUST THEREFORE BE IDEMPOTENT UP TO THEIR FIRST
    SIDE EFFECT - a job that half-sent something before the crash will start
    again from the top.
    """
    now = time.time()
    stale = now - _stale_seconds()
    tries = _max_attempts()
    # A job cancelled while it was running, whose runner then died, is
    # cancelled - not requeued. The owner already said no.
    c.execute("UPDATE jobs SET state='cancelled', finished=? "
              "WHERE state='running' AND cancel=1 AND heartbeat < ?", (now, stale))
    dead = c.execute(
        "UPDATE jobs SET state='failed', finished=?, error=? "
        "WHERE state='running' AND cancel=0 AND heartbeat < ? AND attempts >= ?",
        (now, f"the process running this died {tries} times without finishing",
         stale, tries)).rowcount
    back = c.execute(
        "UPDATE jobs SET state='queued', started=NULL, heartbeat=NULL, due=? "
        "WHERE state='running' AND cancel=0 AND heartbeat < ?",
        (now, stale)).rowcount
    if dead or back:
        _audit("jobs.reclaimed", {"requeued": back, "failed": dead})
    return {"requeued": back, "failed": dead}


def _stale_seconds() -> float:
    try:
        return max(30.0, float(_cfg("stale_running_seconds", 900)))
    except (TypeError, ValueError):
        return 900.0


def _max_attempts() -> int:
    try:
        return max(1, int(_cfg("max_attempts", 3)))
    except (TypeError, ValueError):
        return 3


def shutdown(timeout: float = 5.0) -> None:
    """Stop the writer thread. For a clean process exit and for tests, which
    need to point DB_PATH somewhere else between cases."""
    global _WRITER, _inited, _WRITER_ERROR
    with _WRITER_LOCK:
        t, _WRITER = _WRITER, None
    if t is not None and t.is_alive():
        _QUEUE.put(None)
        t.join(timeout)
    with _INIT_LOCK:
        _inited = False
    _WRITER_ERROR = None
    _WRITER_READY.clear()


# --------------------------------------------------------------------------
#   Handlers: registered callables, never stored code
# --------------------------------------------------------------------------
# A job row holds a NAME and a JSON params dict. It does not hold a pickle,
# a marshalled function, a source string for eval, or a module path to
# import. Those are all the same design and it is the wrong one here: the
# jobs table would become an arbitrary-code-execution channel, so anything
# that can write a row - a bug, an injected tool call, a synced file, a
# restored backup from before a fix - gets to run code as this process. It
# would also make the frozen capability set meaningless, because the code
# deciding what to do would be the part that was not frozen. A module path
# is no better: "import whatever the row says" is eval with extra steps, and
# a row naming a module that exists for other reasons executes it at import
# time before anyone checks anything.
#
# Registration by name means the set of things a job can possibly do is
# fixed when this process starts, by code that shipped in this repo. An
# unknown name is a failed job with the name printed, never a lookup.

_HANDLERS: dict[str, Callable] = {}
_HANDLER_LOCK = threading.Lock()


def register(name: str, fn: Callable) -> Callable:
    """Make `fn` runnable as a job body under `name`.

    The handler is called as fn(ctx, params): `ctx` is the JobContext below,
    `params` is the JSON dict from the row. Whatever it returns is stored as
    the result and must be JSON-serialisable; raising Cancelled or
    NeedsApproval is normal control flow, any other exception fails the job.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("a handler needs a name")
    if not callable(fn):
        raise TypeError(f"handler {name!r} is not callable")
    with _HANDLER_LOCK:
        _HANDLERS[name] = fn
    return fn


def handlers() -> list[str]:
    with _HANDLER_LOCK:
        return sorted(_HANDLERS)


# --------------------------------------------------------------------------
#   The event stream
# --------------------------------------------------------------------------

_LAST_EMIT: dict[str, float] = {}
_EMIT_LOCK = threading.Lock()


def _emit(row: dict, note: str = "", force: bool = True) -> None:
    """Publish a `job` event. Every client already subscribes to the bus, so
    this is how progress reaches the HUD, the desktop shell and the phone
    without any of them polling the jobs table.

    Swallowing failures is right here and only here: the bus is a view of the
    truth, not the truth, and a job must not fail because a notification
    could not be published. Nothing about permission, taint or state is
    decided in this function.
    """
    jid = row.get("id", "")
    if not force:
        try:
            gap = float(_cfg("progress_event_seconds", 1.0))
        except (TypeError, ValueError):
            gap = 1.0
        with _EMIT_LOCK:
            if time.time() - _LAST_EMIT.get(jid, 0.0) < gap:
                return
            _LAST_EMIT[jid] = time.time()
    else:
        with _EMIT_LOCK:
            _LAST_EMIT[jid] = time.time()
    try:
        import jarvis_events
        jarvis_events.BUS.publish("job", {
            "id": jid,
            "state": row.get("state"),
            "progress": round(float(row.get("progress") or 0.0), 3),
            "label": (row.get("label") or "")[:80],
            "note": (note or row.get("note") or "")[:120],
            "tainted": bool(row.get("tainted")),
        })
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Rows
# --------------------------------------------------------------------------

def _loads(raw, default):
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _row(r) -> dict:
    d = dict(r)
    d["params"] = _loads(d.get("params"), {})
    d["caps"] = _loads(d.get("caps"), [])
    d["result"] = _loads(d.get("result"), None)
    d["tainted"] = bool(d.get("tainted"))
    d["cancel"] = bool(d.get("cancel"))
    return d


def _fetch(c: sqlite3.Connection, job_id: str) -> Optional[dict]:
    r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _row(r) if r else None


# --------------------------------------------------------------------------
#   Creating a job: the moment the capability set is frozen
# --------------------------------------------------------------------------

def _when_to_epoch(when: Any) -> float:
    """None or nothing means now. Accepts an epoch number, a datetime, or an
    ISO-8601 string, because the three callers that exist write it three
    different ways."""
    if when is None:
        return time.time()
    if isinstance(when, (int, float)):
        # A small number is a delay in seconds, not an epoch in 1970.
        return time.time() + float(when) if when < 10_000_000 else float(when)
    try:
        import datetime as _dt
        if isinstance(when, _dt.datetime):
            return when.timestamp()
        if isinstance(when, str):
            return _dt.datetime.fromisoformat(when.strip()).timestamp()
    except Exception as exc:
        raise ValueError(f"cannot read a time out of {when!r}: {exc}") from exc
    raise ValueError(f"cannot read a time out of {when!r}")


def _tier_of(action: str) -> str:
    """The framework's tier for an action. A policy that cannot be read is an
    exception, not a default: a capability set frozen against an unknown
    policy is a promise nobody checked."""
    if fw is None:
        raise JobsUnavailable("jarvis_framework is not importable, so the "
                              "autonomy policy cannot be checked")
    try:
        return fw.action_tier(action)
    except Exception as exc:
        raise JobsUnavailable(
            f"the autonomy policy could not be read ({exc}), so no capability "
            f"set can be frozen against it") from exc


def _freeze_caps(caps) -> list[str]:
    """Normalise the requested capabilities, and refuse to freeze one the
    framework says is `never`.

    A `never` action is not refusable later by this module in any useful way:
    the whole point of the frozen set is that execution trusts it, so a
    forbidden action must not be inside it in the first place. Catching it
    here also means the refusal lands on the person scheduling the job, while
    they are still present to hear it.
    """
    if isinstance(caps, str):
        caps = [caps]
    out = sorted({str(c).strip() for c in (caps or []) if str(c).strip()})
    forbidden = [c for c in out if _tier_of(c) == "never"]
    if forbidden:
        raise ValueError(
            "these actions are set to 'never' in jarvis-framework.toml and "
            f"cannot be frozen onto a job: {', '.join(forbidden)}")
    return out


def create(handler: str, params: Optional[dict] = None, label: str = "",
           caps=(), when: Any = None, tainted: Optional[bool] = None) -> str:
    """Schedule a job and return its id.

    `caps` is the complete set of actions this job may ever take. It is
    written onto the row now and read back at execution; nothing widens it.
    `when` is None for "as soon as a tick comes round", a delay in seconds, an
    epoch, a datetime or an ISO string.

    `tainted` may force taint ON. It cannot force it off: the gate is asked
    as well, and the two are OR-ed. A caller who could untaint a job by
    passing a flag would be a laundering path, which is the exact thing the
    persisted taint exists to close.
    """
    _init()
    handler = (handler or "").strip()
    if not handler:
        raise ValueError("a job needs a handler name")
    params = params or {}
    if not isinstance(params, dict):
        raise TypeError("job params must be a dict, so they can be JSON")
    try:
        blob = json.dumps(params)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"job params must be JSON-serialisable: {exc}") from exc

    frozen = _freeze_caps(caps)

    # The gate is imported lazily: it opens its own database on first use and
    # this module is imported by things (the HUD's status page) that never
    # schedule anything.
    latched = False
    try:
        import jarvis_gate
        latched = bool(jarvis_gate.taint_active())
    except Exception:
        # taint_active() already answers True when it cannot tell. Reaching
        # here means the import itself failed, and "is this private?" with no
        # way to check has exactly one safe answer.
        latched = True
    is_tainted = bool(latched or bool(tainted))

    jid = uuid.uuid4().hex[:12]
    now = time.time()
    due = _when_to_epoch(when)
    row = {"id": jid, "handler": handler, "params": blob,
           "label": (label or handler)[:200], "caps": json.dumps(frozen),
           "tainted": 1 if is_tainted else 0, "state": "queued",
           "due": due, "created": now}

    def _insert(c: sqlite3.Connection):
        c.execute(
            "INSERT INTO jobs (id,handler,params,label,caps,tainted,state,"
            " progress,due,created) VALUES (?,?,?,?,?,?,?,0,?,?)",
            (row["id"], row["handler"], row["params"], row["label"],
             row["caps"], row["tainted"], row["state"], row["due"],
             row["created"]))
    _write(_insert)

    # The label is the owner's own words and the params can carry a path or a
    # search term, so neither goes to the audit log; the shape does.
    _audit("jobs.created", {"id": jid, "handler": handler, "caps": frozen,
                            "tainted": is_tainted, "due": due,
                            "param_keys": sorted(params.keys())[:12]})
    _emit({"id": jid, "state": "queued", "progress": 0.0,
           "label": row["label"], "tainted": is_tainted}, note="scheduled")
    return jid


# --------------------------------------------------------------------------
#   The context a handler is given
# --------------------------------------------------------------------------

class JobContext:
    """What a job body is allowed to know and do.

    Handlers get one of these instead of module-level access, so the frozen
    capability set, the taint flag and the cancel check are all in front of
    them rather than somewhere they have to remember to look.
    """

    def __init__(self, row: dict):
        self.job_id: str = row["id"]
        self.label: str = row.get("label") or ""
        self.params: dict = row.get("params") or {}
        self.handler: str = row.get("handler") or ""
        # A frozenset, not a list, and not a reference to anything mutable on
        # the row. A handler that appends to its own capabilities should have
        # nothing to append to.
        self._caps: frozenset = frozenset(row.get("caps") or [])
        self.tainted: bool = bool(row.get("tainted"))
        self.attempts: int = int(row.get("attempts") or 0)
        self._progress: float = float(row.get("progress") or 0.0)

    # ---- what it may do ------------------------------------------------
    @property
    def caps(self) -> frozenset:
        return self._caps

    @property
    def local_only(self) -> bool:
        """True when this job may only use the local model. The router and
        any model call inside a handler must consult this instead of asking
        the gate, whose latch is a timer that expired hours ago."""
        return self.tainted

    def may(self, action: str) -> bool:
        """Pure predicate. No side effects, no queueing, so a handler can
        plan around a missing capability instead of tripping over it."""
        return action in self._caps

    def require(self, action: str, detail: Optional[dict] = None) -> bool:
        """Insist on a capability, or park the job.

        In the frozen set: yes, immediately. Outside it: this does NOT
        escalate and does NOT consult the tier table for a pass. It records a
        one-shot grant request, parks the job in `waiting_approval` and
        raises. The next tick re-runs the handler; if a human answered yes in
        the meantime the grant is spent here and the job continues, and if
        nobody answered it parks again. Nothing about this path writes to the
        `caps` column.

        WHY NOT jarvis_gate.check(): because the gate answers from the tier
        table, and an action at tier `auto` would come back allowed without
        any human involved. That is the correct answer to "may Jarvis do this
        in a conversation" and the wrong answer to "may THIS job, whose
        permissions were fixed on Tuesday, do this". The frozen set is a
        ceiling under the tier table, not a second copy of it. The tier table
        is still consulted for one thing - `never` - because an action the
        framework forbids outright must not generate a card that invites
        someone to allow it.
        """
        self.checkpoint()
        if action in self._caps:
            return True
        if _tier_of(action) == "never":
            _audit("jobs.capability_forbidden", {"id": self.job_id,
                                                 "action": action})
            raise NeedsApproval(
                action, f"{action} is set to 'never' in jarvis-framework.toml; "
                        f"no grant can authorise it", denied=True)

        state = _write(lambda c: _grant_step(c, self.job_id, action))
        if state == "granted":
            _audit("jobs.capability_granted", {"id": self.job_id,
                                               "action": action})
            return True
        if state == "denied":
            raise NeedsApproval(action, f"the owner denied {action}", denied=True)
        raise NeedsApproval(action, f"waiting for someone to allow {action}")

    # ---- staying alive, and stopping -----------------------------------
    def checkpoint(self) -> None:
        """Raise if the job has been cancelled. Called by progress() and
        require(), so a handler that reports progress gets cancellation for
        free and a handler that reports nothing can still ask."""
        if self.cancelled:
            raise Cancelled(f"job {self.job_id} was cancelled")

    @property
    def cancelled(self) -> bool:
        rows = _read("SELECT cancel,state FROM jobs WHERE id=?", (self.job_id,))
        if not rows:
            return True                # a row that vanished is not still running
        return bool(rows[0]["cancel"]) or rows[0]["state"] == "cancelled"

    def progress(self, fraction: Optional[float] = None, note: str = "") -> None:
        """Report how far along this is, and check for cancellation.

        The two are deliberately the same call. A handler that reports
        progress is a handler that can be stopped mid-step, and making the
        author write two calls to get that is how you end up with jobs that
        ignore cancel for twenty minutes. It is also the liveness signal: a
        job that goes longer than [jobs].stale_running_seconds without one is
        treated as dead by the next reclaim.
        """
        if fraction is not None:
            try:
                self._progress = min(1.0, max(0.0, float(fraction)))
            except (TypeError, ValueError):
                pass
        now = time.time()
        _write(lambda c: c.execute(
            "UPDATE jobs SET progress=?, note=?, heartbeat=? "
            "WHERE id=? AND state='running'",
            (self._progress, note[:200], now, self.job_id)))
        _emit({"id": self.job_id, "state": "running", "progress": self._progress,
               "label": self.label, "tainted": self.tainted},
              note=note, force=False)
        self.checkpoint()


def _grant_step(c: sqlite3.Connection, job_id: str, action: str) -> str:
    """One transition of the grant state machine, on the writer thread so it
    cannot interleave with another one. Returns the state the caller should
    act on: granted (and spent here), denied, or pending."""
    now = time.time()
    c.execute("BEGIN IMMEDIATE")
    try:
        row = c.execute(
            "SELECT id,state FROM job_grants WHERE job_id=? AND action=? "
            "AND used IS NULL ORDER BY created DESC LIMIT 1",
            (job_id, action)).fetchone()
        if row is None:
            c.execute("INSERT INTO job_grants (id,job_id,action,state,created) "
                      "VALUES (?,?,?,'pending',?)",
                      (uuid.uuid4().hex[:12], job_id, action, now))
            c.execute("COMMIT")
            return "pending"
        if row["state"] == "granted":
            # Spent on the way out. A grant authorises one use; the next time
            # the handler asks, it asks again.
            c.execute("UPDATE job_grants SET used=? WHERE id=?", (now, row["id"]))
            c.execute("COMMIT")
            return "granted"
        if row["state"] == "denied":
            c.execute("UPDATE job_grants SET used=? WHERE id=?", (now, row["id"]))
            c.execute("COMMIT")
            return "denied"
        c.execute("COMMIT")
        return "pending"
    except Exception:
        try:
            c.execute("ROLLBACK")
        except Exception:
            pass
        raise


def pending_grants(job_id: Optional[str] = None) -> list[dict]:
    """Capabilities jobs have asked for and nobody has answered. The HUD
    renders these next to the gate's own approvals."""
    if job_id:
        rows = _read("SELECT g.*, j.label, j.handler FROM job_grants g "
                     "JOIN jobs j ON j.id=g.job_id "
                     "WHERE g.state='pending' AND g.used IS NULL AND g.job_id=? "
                     "ORDER BY g.created", (job_id,))
    else:
        rows = _read("SELECT g.*, j.label, j.handler FROM job_grants g "
                     "JOIN jobs j ON j.id=g.job_id "
                     "WHERE g.state='pending' AND g.used IS NULL "
                     "ORDER BY g.created")
    return [dict(r) for r in rows]


def decide_grant(grant_id: str, approved: bool, by: str = "hud") -> bool:
    """Answer one capability request. False if it is unknown or already
    answered, so a second tap cannot revive a spent grant."""
    _init()

    def _go(c: sqlite3.Connection) -> bool:
        cur = c.execute(
            "UPDATE job_grants SET state=?, decided=?, decided_by=? "
            "WHERE id=? AND state='pending' AND used IS NULL",
            ("granted" if approved else "denied", time.time(),
             str(by or "hud")[:64], grant_id))
        return cur.rowcount > 0
    ok = _write(_go)
    if ok:
        _audit("jobs.grant_decided", {"grant": grant_id,
                                      "approved": bool(approved), "by": by})
    return ok


# --------------------------------------------------------------------------
#   Running
# --------------------------------------------------------------------------

def _claim(c: sqlite3.Connection, job_id: str, now: float) -> Optional[dict]:
    """Take ownership of one job, or return None because somebody else did.

    The guard is the whole point: `cancel=0` means a cancelled job can never
    be started, and the state list means a finished one can never be
    restarted. Both are enforced in the WHERE clause rather than by reading
    the row first and deciding, which is a race with every other tick.

    `now` is the tick's clock and is only compared against `due`; the stamps
    written on the row are the real time, so a tick run with a shifted clock
    cannot leave a row claiming it started in the future.
    """
    real = time.time()
    cur = c.execute(
        "UPDATE jobs SET state='running', started=COALESCE(started,?), "
        " heartbeat=?, attempts=attempts+1 "
        "WHERE id=? AND cancel=0 AND due<=? "
        " AND state IN ('queued','waiting_approval')",
        (real, real, job_id, now))
    if cur.rowcount == 0:
        return None
    return _fetch(c, job_id)


def _finish(job_id: str, state: str, result: Any = None,
            error: str = "") -> Optional[dict]:
    """Write a terminal state, unless the job was cancelled underneath us.

    `cancel=0` in the guard is what makes cancellation final. A handler that
    ignores its context and runs to completion after the owner cancelled does
    not get to mark the job done, and its result is dropped rather than
    delivered - a result nobody wanted is not an outcome, and putting it in
    the digest would make cancel a suggestion.
    """
    try:
        blob = json.dumps(result) if result is not None else None
    except (TypeError, ValueError):
        blob = json.dumps({"unserialisable": str(type(result).__name__)})
        error = error or "the handler returned something that is not JSON"
        state = "failed"

    def _go(c: sqlite3.Connection):
        # progress only moves to 1.0 on success. A job that failed at 40% is
        # more honest about itself than one the writer rounded up.
        cur = c.execute(
            "UPDATE jobs SET state=?, finished=?, result=?, error=?, "
            " progress=CASE WHEN ?='done' THEN 1.0 ELSE progress END "
            "WHERE id=? AND state='running' AND cancel=0",
            (state, time.time(), blob, error[:2000] or None, state, job_id))
        if cur.rowcount == 0:
            # Cancelled mid-flight. Settle the row as cancelled and keep no
            # result.
            c.execute("UPDATE jobs SET state='cancelled', finished=? "
                      "WHERE id=? AND state='running'", (time.time(), job_id))
        return _fetch(c, job_id)
    row = _write(_go)
    if row:
        _audit("jobs.finished", {"id": job_id, "state": row["state"],
                                 "handler": row.get("handler"),
                                 "attempts": row.get("attempts")})
        _emit(row, note=error[:120] if error else "")
    return row


def _park(job_id: str, action: str, reason: str) -> Optional[dict]:
    """Move a running job back to waiting_approval and set when to retry."""
    try:
        retry = max(1.0, float(_cfg("approval_retry_seconds", 30)))
    except (TypeError, ValueError):
        retry = 30.0

    def _go(c: sqlite3.Connection):
        c.execute("UPDATE jobs SET state='waiting_approval', due=?, note=? "
                  "WHERE id=? AND state='running' AND cancel=0",
                  (time.time() + retry, f"needs {action}"[:200], job_id))
        return _fetch(c, job_id)
    row = _write(_go)
    if row:
        _audit("jobs.waiting", {"id": job_id, "action": action})
        _emit(row, note=reason[:120] or f"needs {action}")
    return row


def run_due(now: Optional[float] = None, limit: Optional[int] = None) -> dict:
    """One tick. Runs every job that is due, in this thread, and returns what
    happened.

    Synchronous on purpose. The caller is jarvis_initiative's engine thread
    (or a test), which exists to spend time; handing each job to a pool would
    buy concurrency nobody asked for and cost the one property that makes
    this testable - that when run_due returns, the tick is over. Cancellation
    still works mid-step, because cancel is a row the handler's context reads
    from another thread, not a flag in this one.
    """
    _init()
    now = time.time() if now is None else now
    if limit is None:
        try:
            limit = max(1, int(_cfg("max_jobs_per_tick", 4)))
        except (TypeError, ValueError):
            limit = 4
    due = _read("SELECT id FROM jobs WHERE cancel=0 AND due<=? "
                " AND state IN ('queued','waiting_approval') "
                "ORDER BY due LIMIT ?", (now, limit))
    out = {"ran": 0, "done": [], "failed": [], "waiting": [], "cancelled": [],
           "skipped": []}
    for r in due:
        jid = r["id"]
        row = _write(lambda c, j=jid: _claim(c, j, now))
        if row is None:
            out["skipped"].append(jid)
            continue
        out["ran"] += 1
        _emit(row, note="started")
        with _HANDLER_LOCK:
            fn = _HANDLERS.get(row["handler"])
        if fn is None:
            # Never an import, never a lookup by path. The name is wrong or
            # the module that registers it did not load; say which name, so
            # the answer is one grep rather than a mystery.
            _finish(jid, "failed",
                    error=f"no handler named {row['handler']!r} is registered "
                          f"(known: {', '.join(handlers()) or 'none'})")
            out["failed"].append(jid)
            continue
        ctx = JobContext(row)
        try:
            result = fn(ctx, dict(row["params"]))
        except Cancelled:
            _finish(jid, "cancelled")
            out["cancelled"].append(jid)
            continue
        except NeedsApproval as need:
            if need.denied:
                _finish(jid, "failed", error=need.reason or str(need))
                out["failed"].append(jid)
            else:
                _park(jid, need.action, need.reason or str(need))
                out["waiting"].append(jid)
            continue
        except Exception as exc:                       # noqa: BLE001
            # No blind retry. A job body that threw will throw again next
            # tick, and a retried job that already sent half of something
            # sends it twice. The reclaim path retries; this one does not.
            _finish(jid, "failed", error=f"{type(exc).__name__}: {exc}")
            out["failed"].append(jid)
            continue
        final = _finish(jid, "done", result=result)
        (out["cancelled"] if final and final["state"] == "cancelled"
         else out["done"]).append(jid)
    return out


# --------------------------------------------------------------------------
#   Cancel
# --------------------------------------------------------------------------

def cancel(job_id: str, by: str = "hud") -> bool:
    """Stop a job. Works from any client, at any point, and does not undo.

    Two writes in one statement's worth of intent: the flag, which a running
    handler's next progress() or require() sees and raises on, and the state,
    which is set straight away for a job that is not running so a tick cannot
    pick it up in the gap. There is no resume - the guards on every other
    write exclude a cancelled row, so "cancel then uncancel" is not something
    a caller can express.
    """
    _init()

    def _go(c: sqlite3.Connection):
        cur = c.execute(
            "UPDATE jobs SET cancel=1 WHERE id=? AND state NOT IN "
            "('done','failed','cancelled')", (job_id,))
        if cur.rowcount == 0:
            return None
        c.execute("UPDATE jobs SET state='cancelled', finished=? "
                  "WHERE id=? AND state IN ('queued','waiting_approval')",
                  (time.time(), job_id))
        c.execute("UPDATE job_grants SET state='denied', decided=?, "
                  "decided_by=? WHERE job_id=? AND state='pending'",
                  (time.time(), f"cancel:{by}"[:64], job_id))
        return _fetch(c, job_id)
    row = _write(_go)
    if row is None:
        return False
    _audit("jobs.cancelled", {"id": job_id, "by": by, "state": row["state"]})
    _emit(row, note="cancelled")
    return True


# --------------------------------------------------------------------------
#   Reading, and handing results on
# --------------------------------------------------------------------------

def get(job_id: str) -> Optional[dict]:
    rows = _read("SELECT * FROM jobs WHERE id=?", (job_id,))
    return _row(rows[0]) if rows else None


def jobs(state: Optional[str] = None, limit: int = 200) -> list[dict]:
    """Every job, newest first, or only those in one state."""
    if state:
        if state not in STATES:
            raise ValueError(f"{state!r} is not a job state; try one of "
                             f"{', '.join(STATES)}")
        rows = _read("SELECT * FROM jobs WHERE state=? ORDER BY created DESC "
                     "LIMIT ?", (state, limit))
    else:
        rows = _read("SELECT * FROM jobs ORDER BY created DESC LIMIT ?", (limit,))
    return [_row(r) for r in rows]


def collect(limit: int = 20) -> list[dict]:
    """Finished jobs nobody has been told about yet, marked as told.

    THE CONTRACT, for jarvis_arbiter, which is being written in parallel and
    is deliberately not imported here: the arbiter owns the interruption
    budget and the daily digest, and it calls this. Nothing in this module
    speaks, pushes or interrupts - a job that finishes at 03:00 puts a row
    here and goes quiet, and the arbiter decides at breakfast whether it is
    worth a line. Reversing that dependency (jobs calling the arbiter) would
    put the decision to interrupt inside the code that has a reason to.

    Exactly once, by construction: the select and the update happen inside
    one function on the single writer thread, inside BEGIN IMMEDIATE, so two
    collectors cannot both see the same row. `tainted` is returned with every
    item because the arbiter must know whether a summary may be written by a
    cloud model - the taint outlives the conversation that caused it.

    `cancelled` jobs are not included. The owner cancelled it; telling them
    about it later is the interruption they were avoiding.
    """
    _init()
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 20

    def _go(c: sqlite3.Connection):
        c.execute("BEGIN IMMEDIATE")
        try:
            rows = c.execute(
                "SELECT * FROM jobs WHERE delivered IS NULL "
                " AND state IN ('done','failed') ORDER BY finished LIMIT ?",
                (limit,)).fetchall()
            picked = [_row(r) for r in rows]
            now = time.time()
            for p in picked:
                c.execute("UPDATE jobs SET delivered=? WHERE id=? "
                          "AND delivered IS NULL", (now, p["id"]))
            c.execute("COMMIT")
            return picked
        except Exception:
            try:
                c.execute("ROLLBACK")
            except Exception:
                pass
            raise
    picked = _write(_go)
    if picked:
        _audit("jobs.collected", {"n": len(picked),
                                  "ids": [p["id"] for p in picked]})
    return [{"id": p["id"], "handler": p["handler"], "label": p["label"],
             "state": p["state"], "result": p["result"], "error": p["error"],
             "tainted": p["tainted"], "finished": p["finished"],
             "created": p["created"]} for p in picked]


def status() -> dict:
    """What the HUD shows and what a boot banner checks."""
    _init()
    counts = {s: 0 for s in STATES}
    with closing(_connect_read()) as c:
        for r in c.execute("SELECT state, COUNT(*) n FROM jobs GROUP BY state"):
            counts[r["state"]] = r["n"]
        journal = c.execute("PRAGMA journal_mode").fetchone()[0]
        undelivered = c.execute(
            "SELECT COUNT(*) n FROM jobs WHERE delivered IS NULL AND "
            "state IN ('done','failed')").fetchone()["n"]
        waiting = c.execute(
            "SELECT COUNT(*) n FROM job_grants WHERE state='pending' "
            "AND used IS NULL").fetchone()["n"]
    return {"enabled": bool(_cfg("enabled", True)),
            "db": str(DB_PATH),
            "journal_mode": journal,
            "writer_alive": bool(_WRITER and _WRITER.is_alive()),
            "handlers": handlers(),
            "counts": counts,
            "undelivered": undelivered,
            "pending_grants": waiting,
            "config": {"max_jobs_per_tick": _cfg("max_jobs_per_tick", 4),
                       "stale_running_seconds": _stale_seconds(),
                       "max_attempts": _max_attempts(),
                       "approval_retry_seconds": _cfg("approval_retry_seconds", 30)}}


# --------------------------------------------------------------------------
#   python jarvis_jobs.py
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Long Fuse: jobs that outlive "
                                             "the conversation.")
    ap.add_argument("--list", action="store_true", help="every job on file")
    ap.add_argument("--cancel", metavar="ID", help="stop one job")
    ap.add_argument("--tick", action="store_true", help="run whatever is due")
    a = ap.parse_args()
    if a.cancel:
        print("cancelled" if cancel(a.cancel, by="cli") else "no such job, or "
              "it had already finished")
    elif a.tick:
        print(json.dumps(run_due(), indent=1))
    elif a.list:
        for j in jobs():
            flag = " [local only]" if j["tainted"] else ""
            print(f"  {j['id']}  {j['state']:16} {j['progress']:4.0%}  "
                  f"{j['label'][:48]}{flag}")
    else:
        print(json.dumps(status(), indent=1))
