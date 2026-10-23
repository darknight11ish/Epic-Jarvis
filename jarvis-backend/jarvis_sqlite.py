"""A sqlite3 connection that CLOSES when its `with` block ends.

WHY THIS MODULE EXISTS (2026-10-08: the same bug fixed by hand three times)

`sqlite3.Connection`'s own context manager COMMITS on the way out and never
closes the connection. So the shape a whole family of modules uses -

    with self._lock, self._db() as c:
        ...

- left an OPEN HANDLE on the database file behind until CPython happened to
collect the connection. That collection is immediate on a quiet line of code
and NOT immediate when a caught exception's traceback, a generator frame or a
temp-folder object still holds a reference - which is why the failure moved
from suite to suite and never happened twice in the same one.

On Windows an open handle makes the file undeletable, which is what the
runner's log said, twice, inside test_sayable.py's own group (run 2026-10-07,
PR #86):

    Exception ignored in: <finalize object at 0x23ea64114e0; dead>
      File "...\\tempfile.py", line 939, in _cleanup
        cls._rmtree(name, ignore_errors=ignore_errors)
      ...
      File "...\\tempfile.py", line 909, in onexc
        _os.unlink(path)
    PermissionError: [WinError 32] The process cannot access the file
    because it is being used by another process:
    'C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\tmpqw88ug3r\\schedule.json'

- raised by TemporaryDirectory's own cleanup, and repeated a moment later for
a second folder (tmpxh2pi8w1). It cost hours of misdiagnosis, twice, in two
different suites: the message names a temp folder, and the suite it landed on
kept changing.

THE FIX WAS WRITTEN BY HAND THREE TIMES, which is why this file is here.
jarvis_schedule.py grew its own private `_ClosingConnection` (PR #112), then
jarvis_goals.py and jarvis_projects.py each grew a second and third copy (PR
#129). A private copy in each module is how a fourth module comes to reinvent
it - or to miss it. This is the one copy they share.

`backend/test_sqlite_close_guard.py` is the repo-wide check that fails if the
raw shape comes back, and that fails if a second private copy appears.

Nothing else changes: `__exit__` still commits (or rolls back) exactly as
sqlite3 does, and a caller that keeps the connection outside a `with` still
sees it released when the object is collected, as before.
"""
from __future__ import annotations

import contextlib
import os
import re
import sqlite3
import threading
from pathlib import Path


class _ClosingConnection(sqlite3.Connection):
    """A connection the `with ... as c:` blocks CLOSE, not just commit.

    `__exit__` does exactly what sqlite3's does - commit, or roll back on an
    exception - and then closes the connection in a `finally`, so the handle
    is gone even when the block raised.
    """

    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def connect(path, timeout: float = 30) -> sqlite3.Connection:
    """`sqlite3.connect`, with a connection that closes when its `with` ends.

    Use this wherever a connection is handed back to be used as
    `with ... as c:` - never a bare `sqlite3.connect`, which commits and
    leaves the handle open. `row_factory` is left to the caller, as each of the
    three modules set it before.

    There is deliberately no way to ask for a different factory: an argument
    that could switch the closing behaviour off is the bug again, one keyword
    away. A caller that needs its own subclass wants its own module, and
    test_sqlite_close_guard.py will have something to say about that.
    """
    conn = sqlite3.connect(path, timeout=timeout, factory=_ClosingConnection)
    apply_pragmas(conn)
    return conn


# --------------------------------------------------------------------------
#   The four pragmas every connection this module hands out sets
# --------------------------------------------------------------------------

#: Gemini's work order Layer 4 Optimization 4.1 (2026-10-20). Set on EVERY
#: connection this module hands out, not just in the helpers its adopters call:
#:
#:   journal_mode = WAL     a reader never blocks a writer, and the whole
#:                          commit cost stops being an fsync of the database
#:                          file - the value is a property of the FILE, so it
#:                          is set on every connection only to make sure a
#:                          database created by an older build is converted
#:                          the first time any module touches it.
#:   synchronous = NORMAL   the companion setting for WAL: a commit is durable
#:                          against a process crash, not against the machine
#:                          losing power. That is the trade SQLite's own WAL
#:                          documentation recommends.
#:   busy_timeout = 5000    F10 (2026-10-20 audit, Area 9B): the lock-sensitive
#:                          callers expect a busy database to WAIT, not raise
#:                          "database is locked".
#:   temp_store = MEMORY    sorts and transient indexes stay off the disk; the
#:                          databases here are small (a few MB), so the memory
#:                          is cheaper than a temp file on every query.
#:
#: Each one is guarded separately: a read-only file, an unusual build of
#: SQLite or a database another program holds can refuse one pragma without the
#: connection being useless.
PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA temp_store = MEMORY",
)


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """Set the four pragmas above on `conn`, each best-effort, never raising.

    Public because a module that still opens its own `sqlite3.connect` (and
    keeps its own reason to) should not need a second copy of these four
    lines. Nothing here writes to the database beyond the journal-mode
    conversion.
    """
    for statement in PRAGMAS:
        try:
            conn.execute(statement)
        except sqlite3.Error:
            pass


# --------------------------------------------------------------------------
#   One-time schema init, per database path, per process
# --------------------------------------------------------------------------

#: Optimization 4.1's `_INITIALIZED_DB_PATHS`. A path is put in here by
#: `ensure_schema()` after its DDL callback has run successfilly once; every
#: later call in this process returns False and executes nothing.
#:
#: WHY THE PATH AND NOT THE FILE'S mtime OR A ROW IN THE DATABASE: the callers
#: are `_connect()`-shaped helpers that run on every read and every write, so
#: the thing being removed is a handful of `CREATE TABLE IF NOT EXISTS` +
#: `CREATE INDEX IF NOT EXISTS` statements per call. Anything that needed a
#: query to decide "has this run?" would give back a large part of the win.
#: The one assumption is written down for each caller: a database file this
#: process has initialised is not deleted and recreated behind its back. A
#: caller that DOES delete one (media_index's "Delete everything") calls
#: `forget_initialized(path)` when it unlinks the file.
_INITIALIZED_DB_PATHS: set = set()
_INIT_LOCK = threading.RLock()
#: The `db_key` answers, by the path string the caller passed. `realpath` on
#: Windows costs ~110 us a call (measured on this PC), which would give back a
#: large part of what this module removes from a per-read helper; a path's real
#: name does not change while the process lives, and `forget_initialized` is
#: where a caller says a FILE changed (not just its name).
_KEY_CACHE: dict = {}


def db_key(path) -> str:
    """One key per database FILE, on this machine, for the initialized set.

    `realpath` so two spellings of one file do not initialise it twice, and
    `normcase` so Windows' case-insensitive names do not either. Cached by the
    caller's own string - see _KEY_CACHE for the measurement.
    """
    text = os.fspath(path)
    with _INIT_LOCK:
        got = _KEY_CACHE.get(text)
        if got is not None:
            return got
    resolved = text
    try:
        resolved = os.path.realpath(text)
    except (OSError, ValueError):
        pass
    key = os.path.normcase(os.path.abspath(resolved))
    with _INIT_LOCK:
        _KEY_CACHE[text] = key
    return key


def ensure_schema(path, run) -> bool:
    """Run `run(connection)` once per database path in this process.

    `run` is the module's own DDL and migration callback: chat_log's tables,
    feedback's, receipts', the media index's, the documents index's. It is
    given a FRESH connection and its work is committed before that connection
    closes, so the schema is on disk by the time the caller's own connection
    looks for it.

    THE CONNECTION IS A PLAIN ONE, not this module's `_ClosingConnection`:
    migration callbacks still use `with c:` to batch their ALTER/UPDATE pair
    (jarvis_chat_log._migrate does), and a closing subclass would close the
    connection at the end of that block - before this function commits. A plain
    `sqlite3.connect` here is also not a leak: this function closes it in a
    `finally`, which is the property test_sqlite_close_guard.py is about.

    Returns True when the callback ran now, False when it had run before. Any
    exception from `run` rolls the connection back and propagates - a schema
    that could not be created must be loud, not swallowed.
    """
    key = db_key(path)
    with _INIT_LOCK:
        if key in _INITIALIZED_DB_PATHS:
            return False
        conn = sqlite3.connect(os.fspath(path), timeout=30)
        apply_pragmas(conn)
        try:
            run(conn)
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()
        _INITIALIZED_DB_PATHS.add(key)
        return True


def forget_initialized(path=None) -> None:
    """Forget one path (or every path) so the next `ensure_schema` runs again.

    For the one caller whose Delete really unlinks a database file: a new file
    at the same path is a new schema, and the initialized set cannot see that.
    """
    with _INIT_LOCK:
        if path is None:
            _INITIALIZED_DB_PATHS.clear()
        else:
            _INITIALIZED_DB_PATHS.discard(db_key(path))


def reset_initialized_for_tests() -> None:
    """`forget_initialized()` under the name a test can call on purpose."""
    forget_initialized()


def initialized_paths() -> list:
    """The paths this process has initialised, sorted - for a test to count."""
    with _INIT_LOCK:
        return sorted(_INITIALIZED_DB_PATHS)


# --------------------------------------------------------------------------
#   A thread-local connection, reused for the duration of a call
# --------------------------------------------------------------------------

#: One connection per (thread, database path), live only while a `session()`
#: block is open in that thread. SEE `session` FOR WHY IT IS NOT PERSISTENT.
_SESSIONS = threading.local()
_UNSET = object()


def _session_table() -> dict:
    table = getattr(_SESSIONS, "open", None)
    if table is None:
        table = _SESSIONS.open = {}
    return table


@contextlib.contextmanager
def session(path, *, timeout: float = 30, isolation_level=_UNSET):
    """ONE connection reused by nested blocks in this thread; closed at the end.

    Optimization 4.1's second half: "where a single request performs multiple
    reads on one DB, reuse the connection for the call". A caller wraps the
    whole request in `with session(path) as c:`, and helpers the request calls
    that open a session for the SAME path in the SAME thread get the same
    connection back - no second open, no second set of pragmas, no second
    schema check.

    THREAD-LOCAL, AND WHY IT IS CLOSED AT THE END. Each thread keeps its own
    connection (SQLite objects must not cross threads without
    `check_same_thread=False`, and this module does not hand that loaded gun
    out). Nothing outlives the OUTERMOST block: the handle is gone when the
    request ends. That is deliberate - an open handle on Windows makes the
    file undeletable, the bug jarvis_schedule/goals/projects each grew a fix
    for (see this module's header, and test_sqlite_close_guard.py) - so the
    reuse is bounded to a call and never outlives it.

    `isolation_level` is passed straight to `sqlite3.connect` when given
    (`None` = autocommit, what the modules that write single statements use);
    left alone, sqlite3's own default is used. `row_factory` is left to the
    caller, as `connect()` does.
    """
    key = db_key(path)
    table = _session_table()
    entry = table.get(key)
    if entry is None:
        kwargs = {"timeout": timeout}
        if isolation_level is not _UNSET:
            kwargs["isolation_level"] = isolation_level
        conn = sqlite3.connect(os.fspath(path), **kwargs)
        apply_pragmas(conn)
        entry = [conn, 0]
        table[key] = entry
    entry[1] += 1
    try:
        yield entry[0]
    finally:
        entry[1] -= 1
        if entry[1] <= 0:
            table.pop(key, None)
            try:
                entry[0].close()
            except sqlite3.Error:
                pass


# --------------------------------------------------------------------------
#   Retention cap + idle WAL checkpoint (Optimization 4.2)
# --------------------------------------------------------------------------

#: F10 / Q2 (2026-10-20): the retention cap Gemini's Layer 4 asks for.
TRACES_DB = "traces.db"
TRACES_TABLE = "traces"
TRACES_KEEP = 10000

#: A table/column name is pasted into SQL below, so it is never taken from an
#: untrusted place: callers pass literals from this repository, and this check
#: is what makes that a rule rather than a habit.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def trim_table(conn: sqlite3.Connection, table: str, keep: int,
               *, order_by: str = "id") -> int:
    """Delete all but the newest `keep` rows of `table`; return how many went.

    The newest are decided by `order_by` descending - for traces.db that is
    `id`, the row's own insertion order - so the cap is "the last 10,000
    things Jarvis did", not an arbitrary 10,000. Idempotent: a table already
    at or under the cap is not touched (no DELETE is even run).
    """
    if not _IDENT.match(table or "") or not _IDENT.match(order_by or ""):
        raise ValueError(f"not a table/column name: {table!r}/{order_by!r}")
    keep = int(keep)
    if keep < 1:
        raise ValueError("keep must be at least 1")
    have = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    if have <= keep:
        return 0
    before = conn.total_changes
    conn.execute(
        f"DELETE FROM {table} WHERE {order_by} NOT IN "
        f"(SELECT {order_by} FROM {table} ORDER BY {order_by} DESC LIMIT ?)",
        (keep,))
    return int(conn.total_changes - before)


def _default_config_dir() -> Path:
    """Where the owner's databases live, the way the modules resolve it."""
    for key in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        value = os.environ.get(key)
        if value:
            return Path(os.path.expanduser(value))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def idle_maintenance(config_dir=None, *, keep: int = TRACES_KEEP) -> dict:
    """The 30-minute heartbeat's housekeeping, for the databases that exist.

    ADDITIVE AND HONEST ABOUT F10. `traces.db` has NO WRITER in this
    repository or on the owner's live HUD (Gemini's Q2 finding): nothing here
    invents one, and on a PC without the file this is a directory listing and
    nothing else. The retention cap is the F10 fix's safe half and ships HERE, in
    a SHIPPED module that deploy step 1 carries - not as a live-HUD delta: the
    HUD never owned the store, so there was no anchor for a delta, and a HUD-side
    prune would delete a database this program does not own. The old
    `traces-retention` BLOCKED record in tools/reconcile_live_backend.py was
    retired on 2026-10-23 (RA-5) for exactly that reason, and the deploy dry run
    reports 0 blocked deltas. The cap and the WAL/optimize pass are wired so that
    IF a traces.db appears - from an older build or a future writer - its
    `traces` table stays at the newest 10,000 rows and its write-ahead log is
    folded down on the same beat. Nothing here claims a writer exists.

    Only files that are already on disk are opened (a missing database is
    never created by housekeeping), each one is best-effort, and the return
    value says what actually happened rather than assuming it:

        {"dir": ..., "traces": "absent"|"no traces table"|"capped",
         "trimmed": 0, "databases": [{"name", "checkpoint", "optimize"}],
         "errors": ["<file>: <what failed>"]}
    """
    directory = Path(config_dir) if config_dir is not None else _default_config_dir()
    out = {"dir": str(directory), "traces": "absent", "trimmed": 0,
           "databases": [], "errors": []}
    try:
        files = sorted(p for p in directory.glob("*.db") if p.is_file())
    except OSError as exc:
        out["errors"].append(f"{directory}: {type(exc).__name__}")
        return out
    for path in files:
        row = {"name": path.name, "checkpoint": False, "optimize": False}
        try:
            with contextlib.closing(connect(str(path))) as c:
                try:
                    # PASSIVE: never blocks a writer and never truncates a
                    # database another connection is still reading; it just
                    # moves committed WAL frames back into the main file.
                    c.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    row["checkpoint"] = True
                except sqlite3.Error as exc:
                    out["errors"].append(f"{path.name}: checkpoint {type(exc).__name__}")
                try:
                    # Re-plans the statements SQLite has watched run; safe to
                    # call on every connection (it is a no-op when it has
                    # nothing to suggest until the ANALYZE limit is reached).
                    c.execute("PRAGMA optimize")
                    row["optimize"] = True
                except sqlite3.Error as exc:
                    out["errors"].append(f"{path.name}: optimize {type(exc).__name__}")
                if path.name == TRACES_DB:
                    has = c.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (TRACES_TABLE,)).fetchone()
                    if has is None:
                        out["traces"] = "no traces table"
                    else:
                        trimmed = trim_table(c, TRACES_TABLE, keep)
                        c.commit()
                        out["traces"] = "capped"
                        out["trimmed"] = trimmed
        except sqlite3.Error as exc:
            out["errors"].append(f"{path.name}: {type(exc).__name__}")
        out["databases"].append(row)
    return out
