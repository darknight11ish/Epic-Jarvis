"""Gemini work order Layer 4 (2026-10-20), Optimizations 4.1 and 4.2, proved.

    python3 backend/test_sqlite_perf.py

WHAT THIS SUITE IS FOR. Gemini's review says the owner's databases are slow
because "modules repeatedly call sqlite3.connect(path) and execute CREATE TABLE
IF NOT EXISTS + CREATE INDEX IF NOT EXISTS on every single read or write call",
and asks for (4.1) thread-local connections, one-time schema init per database
path and four pragmas, and (4.2) a traces.db retention cap plus an idle
`PRAGMA wal_checkpoint(PASSIVE)` / `PRAGMA optimize`.

The baseline was STALE, so this suite does not take it on trust: it counts what
the real modules execute, before and after the change, with a spy installed on
`sqlite3.connect`. The numbers it prints in its header line are measured on the
run's own tree, not quoted from the report.

WHAT IS PROVED HERE, one check per property:

  1. The four pragmas are really on a fresh connection, and an existing
     database is converted to WAL the first time this module opens it.
  2. `ensure_schema` runs a module's DDL callback ONCE per database path per
     process - measured with a spy - and again only after `forget_initialized`
     or `reset_initialized_for_tests`. A failing callback is not recorded, so
     the next call retries rather than leaving a schema-less database.
  3. The five adopted modules (chat_log, feedback, receipts, media_index,
     documents) execute ZERO schema statements on their repeat reads, where
     the committed code re-ran them on every call. The counts are printed.
  4. `session()` is thread-local: two threads get two connections, nested
     blocks in one thread get the same one, and the handle is CLOSED when the
     outermost block exits (a closed connection raises, and the file can be
     deleted on Windows - the bug class jarvis_sqlite.py's header records).
  5. `chat_log.search` opens ONE connection for the whole search, where the
     committed code opened two, and still finds the seeded conversation.
  6. `trim_table` keeps the newest `keep` rows: 10,001 rows in, 10,000 out,
     the oldest gone, the newest kept, idempotent on the second call.
  7. `idle_maintenance` caps a real traces.db, folds the WAL down, optimises,
     says "absent" honestly when there is no traces.db (the owner's PC today -
     F10 is BLOCKED, not fixed), and does not raise on a file that is not a
     database.
  8. The heartbeat really carries the maintenance tick: `Engine` registers it
     once, and `jarvis_initiative.sqlite_maintenance()` caps the traces table
     through the same 30-minute beat that runs the job queue.

No owner's file is read: every database is in a temporary folder, every env
var this suite sets is restored, and `JARVIS_TEST_UNSEALED_FIXTURES` is not
needed because no voice module is imported.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rebuilt"))

import jarvis_sqlite as JS  # noqa: E402
import jarvis_chat_log as CL  # noqa: E402
import jarvis_documents as DOC  # noqa: E402
import jarvis_feedback as FB  # noqa: E402
import jarvis_media_index as MI  # noqa: E402
import jarvis_receipts as RC  # noqa: E402
import jarvis_initiative as IN  # noqa: E402

PASSED, FAILED = [], []
REPORT = []            # measured line per property, printed at the end
TMP = Path(tempfile.mkdtemp(prefix="jarvis-sqlite-perf-"))
ENV_KEYS = ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR",
            "JARVIS_FEEDBACK_DB", "JARVIS_RECEIPTS_DB")
REAL_CONNECT = sqlite3.connect


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def note(line):
    REPORT.append(line)
    print(f"      {line}")


# --------------------------------------------------------------------------
#   Isolation: every database is inside this suite's own temp folder
# --------------------------------------------------------------------------

def isolate(config_dir: Path) -> dict:
    """Point every module's config resolution at `config_dir`; return the old."""
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    os.environ["OPENJARVIS_CONFIG_DIR"] = str(config_dir)
    os.environ["JARVIS_CONFIG_DIR"] = str(config_dir)
    os.environ["JARVIS_FEEDBACK_DB"] = str(config_dir / "feedback.db")
    os.environ["JARVIS_RECEIPTS_DB"] = str(config_dir / "receipts.db")
    return saved


def restore(saved: dict) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class scratch:
    """A fresh folder (and, if asked, the env pointing at it) for one test."""

    def __init__(self, name: str):
        self.name = name

    def __enter__(self) -> Path:
        self.dir = Path(tempfile.mkdtemp(prefix=f"jarvis-{self.name}-", dir=str(TMP)))
        self.saved = isolate(self.dir)
        JS.reset_initialized_for_tests()
        return self.dir

    def __exit__(self, *exc):
        restore(self.saved)
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)


# --------------------------------------------------------------------------
#   The DDL spy: what did the REAL modules execute?
# --------------------------------------------------------------------------

def _is_ddl(sql) -> bool:
    return isinstance(sql, str) and sql.lstrip().upper().startswith(
        ("CREATE ", "ALTER ", "DROP ", "CREATE VIRTUAL"))


def spy_on_sqlite():
    """Install a counting factory over `sqlite3.connect`; return (stats, undo).

    `factory=` is preserved by subclassing whatever the caller asked for, so
    jarvis_sqlite's `_ClosingConnection` keeps closing and the adopted modules'
    own `sqlite3.connect` calls keep their behaviour. Only counting changes.
    """
    stats = {"opens": 0, "ddl": 0}

    def counting_connect(*args, **kwargs):
        factory = kwargs.pop("factory", None)
        base = factory if factory is not None else sqlite3.Connection

        class _Counted(base):
            def execute(self, sql, *rest):
                if _is_ddl(sql):
                    stats["ddl"] += 1
                return super().execute(sql, *rest)

            def executescript(self, script):
                stats["ddl"] += sum(1 for line in str(script).splitlines()
                                    if _is_ddl(line))
                return super().executescript(script)

        stats["opens"] += 1
        return REAL_CONNECT(*args, factory=_Counted, **kwargs)

    sqlite3.connect = counting_connect

    def undo():
        sqlite3.connect = REAL_CONNECT
    return stats, undo


# --------------------------------------------------------------------------
#   4.1 - the pragmas
# --------------------------------------------------------------------------

def t_the_four_pragmas_are_on_every_connection():
    with scratch("pragmas") as d:
        c = JS.connect(d / "fresh.db")
        got = {
            "journal_mode": c.execute("PRAGMA journal_mode").fetchone()[0],
            "synchronous": c.execute("PRAGMA synchronous").fetchone()[0],
            "busy_timeout": c.execute("PRAGMA busy_timeout").fetchone()[0],
            "temp_store": c.execute("PRAGMA temp_store").fetchone()[0],
        }
        c.close()
        check("journal_mode is WAL", str(got["journal_mode"]).lower() == "wal", got)
        check("synchronous is NORMAL (1)", got["synchronous"] == 1, got)
        check("busy_timeout is 5000", got["busy_timeout"] == 5000, got)
        check("temp_store is MEMORY (2)", got["temp_store"] == 2, got)

        # An OLD database (created before this change) is in DELETE mode; the
        # first open through the shared helper converts it, and the next open
        # sees WAL because it is a property of the file.
        old = d / "old.db"
        raw = REAL_CONNECT(str(old))
        raw.execute("PRAGMA journal_mode = DELETE")
        raw.execute("CREATE TABLE t (id INTEGER)")
        raw.commit()
        was = str(raw.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        raw.close()
        converted = JS.connect(str(old))
        now = str(converted.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        converted.close()
        check("an existing DELETE-mode database is converted to WAL on first open",
              was == "delete" and now == "wal", (was, now))
        note(f"pragmas on a fresh connection: journal_mode={got['journal_mode']}, "
             f"synchronous={got['synchronous']}, busy_timeout={got['busy_timeout']}, "
             f"temp_store={got['temp_store']}; old DELETE db -> {now}")


# --------------------------------------------------------------------------
#   4.1 - one-time schema init
# --------------------------------------------------------------------------

def t_ensure_schema_runs_once_per_path():
    with scratch("ensure") as d:
        runs = []

        def create(conn):
            runs.append(1)
            conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)")
            conn.execute("CREATE INDEX IF NOT EXISTS t_id ON t (id)")

        for _ in range(100):
            JS.ensure_schema(d / "one.db", create)
        check("100 ensure_schema calls run the DDL callback exactly once",
              len(runs) == 1, len(runs))
        check("... and the path is in the initialized set",
              len(JS.initialized_paths()) == 1, JS.initialized_paths())

        JS.ensure_schema(d / "two.db", create)
        check("a second database path gets its own one-time init", len(runs) == 2, runs)

        JS.forget_initialized(d / "one.db")
        JS.ensure_schema(d / "one.db", create)
        check("forget_initialized makes the next call initialise again",
              len(runs) == 3, runs)

        JS.reset_initialized_for_tests()
        JS.ensure_schema(d / "one.db", create)
        check("reset_initialized_for_tests clears every path", len(runs) == 4, runs)
        note("one-time schema init: 100 calls -> 1 DDL run; forget/reset -> 1 more each")


def t_a_failed_schema_init_is_not_recorded():
    with scratch("ensure-fail") as d:
        def boom(conn):
            conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
            raise RuntimeError("the schema could not be built")

        raised = False
        try:
            JS.ensure_schema(d / "bad.db", boom)
        except RuntimeError:
            raised = True
        check("an exception from a schema callback propagates", raised)
        check("... and the path is NOT recorded as initialized",
              (d / "bad.db").resolve() not in
              {Path(p).resolve() for p in JS.initialized_paths()},
              JS.initialized_paths())

        retried = []
        JS.ensure_schema(d / "bad.db", lambda c: retried.append(1))
        check("... so the next call runs the callback again", len(retried) == 1, retried)


# --------------------------------------------------------------------------
#   4.1 - the five adopted modules
# --------------------------------------------------------------------------

def t_the_five_adopted_modules_run_their_ddl_once():
    """Per module: count schema statements on the FIRST call and on 20 later ones.

    Before this change the numbers were (measured on the committed tree with
    the same spy): chat_log 5 per call, feedback 6, receipts 2, media_index 5,
    documents 4. A check that could pass while the spy counted nothing would be
    worthless, so every module must show a non-zero first call.
    """
    with scratch("adopted") as d:
        KEY = bytes(range(32))
        stats, undo = spy_on_sqlite()
        try:
            def measure(label, warm, repeat, calls=20):
                before = dict(stats)
                warm()
                first = stats["ddl"] - before["ddl"]
                opens_before = stats["opens"]
                start_ddl = stats["ddl"]
                for _ in range(calls):
                    repeat()
                loop_ddl = stats["ddl"] - start_ddl
                loop_opens = stats["opens"] - opens_before
                check(f"{label}: the first call builds the schema ({first} DDL, not 0)",
                      first > 0, first)
                check(f"{label}: {calls} repeat calls execute 0 schema statements",
                      loop_ddl == 0, loop_ddl)
                check(f"{label}: ... and still open one connection per call "
                      f"({calls})", loop_opens == calls, loop_opens)
                note(f"{label}: first call {first} DDL, then {calls} calls "
                     f"{loop_ddl} DDL, {loop_opens} opens")

            log = CL.ChatLog(d / "chat-history.db", d / "chat-history.json",
                             lambda: KEY, crypto=True)
            log.set_enabled(True)          # History on, so list() really reads the DB
            measure("chat_log.list", lambda: log.list(), lambda: log.list())

            measure("feedback.counts", FB.counts, FB.counts)

            measure("receipts.recent", RC.recent, RC.recent)

            def mi_warm():
                with MI._INDEX_LOCK, MI._db() as c:
                    MI._ready(c)
            measure("media_index.index_stats", mi_warm, MI.index_stats)

            idx = DOC.TextIndex(DOC.index_path())
            measure("documents.TextIndex.status", idx.status, idx.status)
        finally:
            undo()


# --------------------------------------------------------------------------
#   4.1 - thread-local connection reuse
# --------------------------------------------------------------------------

def t_session_is_thread_local_and_closes_at_the_end():
    with scratch("session") as d:
        path = d / "s.db"
        JS.connect(path).close()
        seen = {}

        with JS.session(path) as outer:
            with JS.session(path) as inner:
                seen["nested_same"] = outer is inner
            seen["outer_usable_inside"] = outer.execute("SELECT 1").fetchone()[0] == 1

        after_closed = False
        try:
            outer.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            after_closed = True
        check("nested sessions in one thread share ONE connection",
              seen.get("nested_same") is True, seen)
        check("the connection is usable while the outer block is open",
              seen.get("outer_usable_inside") is True, seen)
        check("... and it is CLOSED when the outermost block exits", after_closed)

        # The Windows bug class this module's header is about: a handle left
        # open makes the file undeletable. After the block, deletion must work.
        path.unlink()
        check("... so the database file can be deleted afterwards", not path.exists())

        pair = {}

        def worker(tag, barrier):
            with JS.session(path) as c:
                pair[tag] = c
                barrier.wait()

        barrier = threading.Barrier(2)
        t1 = threading.Thread(target=worker, args=("one", barrier))
        t2 = threading.Thread(target=worker, args=("two", barrier))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        check("two threads get two DIFFERENT connections, never one shared",
              pair.get("one") is not None and pair.get("two") is not None
              and pair["one"] is not pair["two"], pair)
        note("thread-local session: nested=1 connection, two threads=2 connections, "
             "closed at the outermost exit (file deletable)")


def t_chat_log_search_reuses_one_connection():
    """The one request that reads the same database twice, counted."""
    with scratch("search") as d:
        KEY = bytes(range(32))
        log = CL.ChatLog(d / "chat-history.db", d / "chat-history.json",
                         lambda: KEY, crypto=True)

        def record(text, cid):
            return log.record_turn(
                {"messages": [{"role": "user", "content": text, "provenance": "typed"}],
                 "conversation_id": cid, "device": "phone"},
                turn={"finish_reason": "stop", "client_gone": False, "rounds": 1,
                      "answer": "Noted.", "tools_ran": []})

        record("my sister's birthday is on the ninth of March", "conv-000001")
        record("the dentist is on Tuesday", "conv-000002")

        stats, undo = spy_on_sqlite()
        try:
            before = stats["opens"]
            got = log.search("birthday")
            opens = stats["opens"] - before
        finally:
            undo()
        check("one chat_log.search opens ONE connection (was 2 before this change)",
              opens == 1, opens)
        check("... and still finds the conversation that has the word",
              [row["id"] for row in got["conversations"]] == ["conv-000001"], got)
        note(f"chat_log.search: {opens} connection for the whole request (was 2), "
             f"{len(got['conversations'])} conversation found")


# --------------------------------------------------------------------------
#   4.2 - the retention cap
# --------------------------------------------------------------------------

def t_the_cap_keeps_the_newest_ten_thousand():
    with scratch("cap") as d:
        c = JS.connect(d / "traces.db")
        c.execute("CREATE TABLE traces (id INTEGER PRIMARY KEY, kind TEXT, at REAL)")
        c.executemany("INSERT INTO traces (kind, at) VALUES (?, ?)",
                      [("t", float(i)) for i in range(1, 10002)])
        c.commit()
        check("the fixture really has 10,001 rows",
              c.execute("SELECT COUNT(*) FROM traces").fetchone()[0] == 10001)

        trimmed = JS.trim_table(c, "traces", 10000)
        c.commit()
        count = c.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        low = c.execute("SELECT MIN(id) FROM traces").fetchone()[0]
        high = c.execute("SELECT MAX(id) FROM traces").fetchone()[0]
        check("10,001 rows trim to 10,000", count == 10000, count)
        check("... exactly one row was removed", trimmed == 1, trimmed)
        check("... the OLDEST row is the one that went (id 1)", low == 2, low)
        check("... and the newest is kept (id 10,001)", high == 10001, high)
        check("a second trim does nothing", JS.trim_table(c, "traces", 10000) == 0)
        c.close()

        guard = False
        try:
            with JS.connect(d / "guard.db") as c2:
                JS.trim_table(c2, "traces; DROP TABLE traces", 10)
        except ValueError:
            guard = True
        check("a table name that is not an identifier is REFUSED, not pasted in",
              guard)
        note("retention: 10,001 rows -> 10,000, oldest id 1 removed, newest kept, "
             "second trim 0")


def _make_traces_db(path: Path, rows: int) -> None:
    c = REAL_CONNECT(str(path))
    c.execute("CREATE TABLE traces (id INTEGER PRIMARY KEY, kind TEXT)")
    c.executemany("INSERT INTO traces (kind) VALUES (?)", [("t",)] * rows)
    c.commit()
    c.close()


def t_idle_maintenance_caps_traces_and_folds_the_wal():
    with scratch("idle") as d:
        config = d / "config"
        config.mkdir()
        _make_traces_db(config / "traces.db", 10001)
        JSON_LIKE = REAL_CONNECT(str(config / "other.db"))
        JSON_LIKE.execute("PRAGMA journal_mode = WAL")
        JSON_LIKE.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY)")
        JSON_LIKE.commit()
        JSON_LIKE.close()
        (config / "not-a-database.db").write_bytes(b"this is not a sqlite file")

        out = JS.idle_maintenance(config)
        check("the traces database is found and capped",
              out["traces"] == "capped" and out["trimmed"] == 1, out)
        check("the checkpoint ran on the traces database",
              any(r["name"] == "traces.db" and r["checkpoint"] and r["optimize"]
                  for r in out["databases"]), out["databases"])
        check("the ordinary database was maintained too",
              any(r["name"] == "other.db" and r["checkpoint"] for r in out["databases"]),
              out["databases"])
        check("a file that is not a database is reported, not fatal",
              any("not-a-database.db" in e for e in out["errors"]) and bool(out["databases"]),
              out["errors"])

        c = REAL_CONNECT(str(config / "traces.db"))
        count = c.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        low = c.execute("SELECT MIN(id) FROM traces").fetchone()[0]
        c.close()
        check("after the beat the traces table holds the newest 10,000",
              count == 10000 and low == 2, (count, low))
        note(f"idle_maintenance: traces capped (trimmed {out['trimmed']}), "
             f"{len(out['databases'])} database(s) checkpointed+optimised, "
             f"{len(out['errors'])} non-database file reported")


def t_idle_maintenance_is_honest_without_a_traces_db():
    with scratch("idle-absent") as d:
        config = d / "config"
        config.mkdir()
        out = JS.idle_maintenance(config)
        check("no traces.db says so plainly instead of inventing a row",
              out["traces"] == "absent" and out["trimmed"] == 0
              and out["databases"] == [], out)
        note("idle_maintenance without traces.db: traces='absent', nothing staged "
             "(F10 stays BLOCKED; this slice does not claim a writer exists)")


# --------------------------------------------------------------------------
#   4.2 - the 30-minute heartbeat carries it
# --------------------------------------------------------------------------

def t_the_heartbeat_carries_the_maintenance_tick():
    engine = IN.Engine(heartbeat_minutes=30)
    check("a fresh engine carries no work ticks before it starts",
          engine.status()["checks"] == 0, engine.status())
    engine._attach_jobs_ticker()
    engine._attach_jobs_ticker()
    names = [name for name, _ in engine.checks]
    check("the heartbeat registers the job ticker exactly once",
          names.count(IN.JOBS_TICK) == 1, names)
    check("... and the database-maintenance ticker exactly once",
          names.count(IN.MAINTENANCE_TICK) == 1, names)

    with scratch("beat") as d:
        config = d / "config"
        config.mkdir()
        _make_traces_db(config / "traces.db", 10001)
        saved = isolate(config)
        try:
            result = IN.sqlite_maintenance()
            count = REAL_CONNECT(str(config / "traces.db")).execute(
                "SELECT COUNT(*) FROM traces").fetchone()[0]
        finally:
            restore(saved)
        check("the tick returns None, so a beat files no finding", result is None)
        check("the tick really capped the traces table", count == 10000, count)
        note("heartbeat: JOBS_TICK + sqlite-maintenance registered once each; "
             "sqlite_maintenance() capped 10,001 -> 10,000 and returned None")


# --------------------------------------------------------------------------
#   Behaviour is unchanged in the adopted modules (smoke, the suites own the rest)
# --------------------------------------------------------------------------

def t_adoption_does_not_change_what_the_modules_do():
    with scratch("behaviour") as d:
        KEY = bytes(range(32))
        log = CL.ChatLog(d / "chat-history.db", d / "chat-history.json",
                         lambda: KEY, crypto=True)
        out = log.record_turn(
            {"messages": [{"role": "user", "content": "remember the milk"}],
             "conversation_id": "conv-000001", "device": "phone"},
            turn={"finish_reason": "stop", "client_gone": False, "rounds": 1,
                  "answer": "Noted.", "tools_ran": []})
        conv = log.get("conv-000001")
        check("chat_log still records and reads a turn back",
              out.get("recorded") and conv and conv["turns"][0]["text"] == "remember the milk",
              (out, conv))

        turn_id = FB.record_turn(injected_ids=["mem:1"])
        FB.mark(turn_id, "right")
        counted = FB.counts()
        check("feedback still records a turn and counts its mark",
              count_wrong := counted["answers_marked"]["right"] == 1, counted)

        RC.record("test_tool", "did a thing")
        recent = RC.recent()
        check("receipts still record and list a receipt",
              len(recent) >= 1 and recent[0]["tool_name"] == "test_tool", recent)

        with MI._INDEX_LOCK, MI._db() as c:
            MI._ready(c)
            c.execute("INSERT OR REPLACE INTO media_files"
                      " (path, root, name, size, mtime_ns, seconds, indexed_at, lines)"
                      " VALUES ('x', 'r', 'x', 1, 1, 1.0, 1.0, 0)")
            c.commit()
        stats = MI.index_stats()
        check("media_index still counts a stored recording", stats["files"] == 1, stats)

        idx = DOC.TextIndex(d / "documents-index.db")
        with idx._db() as c:
            idx._ready(c)
        idx_status = idx.status()
        check("documents still builds and reports its index",
              isinstance(idx_status, dict) and idx_status.get("files") == 0, idx_status)


# --------------------------------------------------------------------------
#   runner
# --------------------------------------------------------------------------

def main() -> int:
    print(f"tree: {HERE}")
    for fn in (t_the_four_pragmas_are_on_every_connection,
               t_ensure_schema_runs_once_per_path,
               t_a_failed_schema_init_is_not_recorded,
               t_the_five_adopted_modules_run_their_ddl_once,
               t_session_is_thread_local_and_closes_at_the_end,
               t_chat_log_search_reuses_one_connection,
               t_the_cap_keeps_the_newest_ten_thousand,
               t_idle_maintenance_caps_traces_and_folds_the_wal,
               t_idle_maintenance_is_honest_without_a_traces_db,
               t_the_heartbeat_carries_the_maintenance_tick,
               t_adoption_does_not_change_what_the_modules_do):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print("\n=== MEASURED ===")
    for line in REPORT:
        print(f"  {line}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
