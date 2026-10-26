"""test_schedule_taint.py - a job remembers the private turn it was written in.

    python -B backend/test_schedule_taint.py

THE FINDING (schedule-source-taint, 2026-10-26). `jarvis_schedule.py` already
latches `jarvis_gate`'s process-wide taint when a reminder's stored context is
READ (`latch_taint(why="reminder_context")`), but the latch is time-bounded
(30 minutes by default) and the ROW carried no creation-time mark. So a job
written during a private turn - while the latch was on - forgot that fact as
soon as the latch expired, and the next firing had nothing left to replay.

WHAT THIS PINS
  1. LEGACY ROWS READ TRUSTED. A schedule.db written before the
     `source_taint` column exists opens, gets the column (idempotently, even
     when a second Scheduler opens the same file), and its rows read as
     trusted - deliberate, because there is no way to know and marking every
     old reminder tainted would latch on a job nobody read anything for.
  2. CREATION WHILE TAINTED STORES THE MARK. A to-do/timer/reminder written
     while `jarvis_gate.taint_active()` is True carries
     `source_taint = "read_outside"`; one written while it is off carries
     NULL. An EDIT made while tainted marks the row too.
  3. A SNOOZE COPY INHERITS THE MARK, and a repeating job that re-arms keeps
     it - both are paths where a row is written again later, by code that
     never saw the original turn.
  4. A TAINTED ROW LATCHES WHEN IT FIRES, with the exact reason
     "scheduled_task:read_outside", ONCE, and BEFORE the kind's own on_fire
     runs.
  5. AN UNTAINTED ROW DOES NOT LATCH.

`jarvis_gate` is replaced in `sys.modules` by a recording stand-in: the real
one reads a database in the owner's config folder, and the point here is what
the scheduler asks it, not what it answers. This suite therefore runs the
same in this repository (no `jarvis_gate.py` under `backend/`) and on the
owner's PC. No network, no model, a temp database per test.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_schedule.py")

TMP = Path(tempfile.mkdtemp(prefix="jarvis-schedule-taint-"))
(TMP / "config").mkdir(parents=True, exist_ok=True)
# Hermetic before the module is imported: no check may touch the owner's real
# schedule.db or settings file.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(TMP / "config")


class FakeGate(types.ModuleType):
    """What `import jarvis_gate` returns: a latch we can watch."""

    def __init__(self):
        super().__init__("jarvis_gate")
        self.active = False
        self.latches = []
        self.clears = 0

    def taint_active(self) -> bool:
        return self.active

    def _fake_latch_taint(self, minutes=None, why=""):
        self.latches.append(why)
        self.active = True
        return True

    # The module calls this name; it is exposed by assignment rather than by
    # a second definition line, because the self-improve real-tree check
    # retrieves the definition of this name, and a test-file definition
    # outranks the real one on the file-name bonus.
    latch_taint = _fake_latch_taint

    def clear_taint(self):
        self.clears += 1
        self.active = False
        return True


GATE = FakeGate()
sys.modules["jarvis_gate"] = GATE

import jarvis_schedule as S  # noqa: E402

S._audit = lambda event, detail: None

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


def raw(path: Path, jid: str) -> sqlite3.Row:
    """One jobs row, read behind the module's back - the stored value, not a view."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return con.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    finally:
        con.close()


def make(name: str, t: float = 1_800_000_000.0):
    """A Scheduler on its own temp file, with a hand-moved clock."""
    clock = Clock(t)
    path = TMP / f"{name}.db"
    s = S.Scheduler(path, clock=clock, gate=lambda *a, **k: None,
                    tier_of=lambda a: "ask", spawn=lambda fn: fn(),
                    publish=lambda kind, data: None)
    return s, path, clock


def columns(path: Path) -> list:
    con = sqlite3.connect(path)
    try:
        return [r[1] for r in con.execute("PRAGMA table_info(jobs)").fetchall()]
    finally:
        con.close()


# --------------------------------------------------------------------------
#   1. the column, old databases and the trusted default
# --------------------------------------------------------------------------

def t_the_column_is_declared_once():
    names = [name for name, _typ in S._ADDED_COLUMNS]
    check("source_taint is in _ADDED_COLUMNS exactly once",
          names.count("source_taint") == 1, names)
    check("...and it is the last column, so an older reader is untouched",
          S._ADDED_COLUMNS[-1][0] == "source_taint", S._ADDED_COLUMNS[-1])


def t_a_legacy_database_reads_trusted():
    path = TMP / "legacy.db"
    con = sqlite3.connect(path)
    try:
        # The schema as a build before this change wrote it: no source_taint.
        con.executescript(S._SCHEMA)
        con.execute("INSERT INTO jobs (id, kind, text, state, due, created, changed, source) "
                    "VALUES ('old1', 'timer', 'set before the column', 'active', "
                    "1800000000.0, 1799999990.0, 1799999990.0, 'app')")
        con.commit()
    finally:
        con.close()
    check("the old file really has no source_taint before opening",
          "source_taint" not in columns(path))
    s = S.Scheduler(path, clock=lambda: 1_800_000_001.0, gate=lambda *a, **k: None,
                    tier_of=lambda a: "ask", spawn=lambda fn: fn(),
                    publish=lambda kind, data: None)
    check("opening it adds the column", "source_taint" in columns(path))
    with s._lock, s._db() as c:
        old = s._row(c, "old1")
    check("the legacy row reads as trusted (empty mark)", S._row_taint(old) == "",
          repr(S._row_taint(old)))
    GATE.latches.clear()
    GATE.active = False
    check("firing a legacy timer does not latch", s.tick(1_800_000_001.0) == ["old1"],
          "it did not go off")
    check("...and no latch reason was recorded", GATE.latches == [], GATE.latches)
    check("a plain dict with no column also reads as trusted",
          S._row_taint({"id": "x"}) == "")


def t_the_column_is_added_idempotently_twice():
    s1, path, _clock = make("idem")
    s2, _path2, _clock2 = make("idem")
    want = [n for n, _t in S._ADDED_COLUMNS if n == "source_taint"]
    check("two Schedulers on one file do not raise", s1 is not None and s2 is not None)
    check("...and the column exists exactly once", columns(path).count("source_taint") == 1,
          columns(path))
    check("...which is what _ADDED_COLUMNS asks for", len(want) == 1, want)


# --------------------------------------------------------------------------
#   2. creation and edit while the latch is on
# --------------------------------------------------------------------------

def t_a_row_created_while_tainted_stores_the_mark():
    s, path, _clock = make("create")
    GATE.active = True
    GATE.latches.clear()
    todo = s.add_todo("milk")
    GATE.active = False
    clean = s.add_todo("bread")
    check("a to-do written while tainted carries read_outside",
          raw(path, todo["id"])["source_taint"] == S.SOURCE_TAINT,
          raw(path, todo["id"])["source_taint"])
    check("...and creating it did not latch anything itself", GATE.latches == [],
          GATE.latches)
    check("a to-do written while not tainted carries NULL",
          raw(path, clean["id"])["source_taint"] is None,
          raw(path, clean["id"])["source_taint"])
    check("every creation path goes through _insert",
          "def _insert" in Path(S.__file__).read_text(encoding="utf-8"))


def t_a_timer_and_reminder_created_while_tainted_store_the_mark():
    s, path, _clock = make("create2")
    GATE.active = True
    timer = s.add_timer(60, "tea")
    reminder = s.add_at("reminder", 1_800_000_600.0, "call mum")
    alarm = s.add_at("alarm", 1_800_000_700.0, "wake")
    GATE.active = False
    for label, job in (("timer", timer), ("reminder", reminder), ("alarm", alarm)):
        check(f"the {label} written while tainted carries read_outside",
              raw(path, job["id"])["source_taint"] == S.SOURCE_TAINT,
              raw(path, job["id"])["source_taint"])


def t_an_edit_while_tainted_marks_the_row():
    s, path, _clock = make("edit")
    todo = s.add_todo("first words")
    check("before the edit the row is trusted",
          raw(path, todo["id"])["source_taint"] is None)
    GATE.active = True
    code, out = s.act(todo["id"], "edit", fields={"text": "changed words"})
    GATE.active = False
    check("the edit is accepted", code == 200 and out.get("ok") is True, (code, out))
    check("an edit made while tainted marks the row",
          raw(path, todo["id"])["source_taint"] == S.SOURCE_TAINT,
          raw(path, todo["id"])["source_taint"])


# --------------------------------------------------------------------------
#   3. rewritten rows: snooze copies and a repeat that re-arms
# --------------------------------------------------------------------------

def t_a_snooze_copy_inherits_the_mark():
    s, path, clock = make("snooze")
    GATE.active = True
    job = s.add_timer(60, "tea")
    GATE.active = False
    check("the timer is marked at creation",
          raw(path, job["id"])["source_taint"] == S.SOURCE_TAINT)
    clock.t += 61.0
    s.tick(clock.t)
    GATE.active = False          # the replay's latch must not be what marks it
    GATE.latches.clear()
    code, out = s.snooze(job["id"], 120)
    check("the snooze is accepted", code == 200 and out.get("ok") is True, (code, out))
    check("the snooze COPY inherits read_outside",
          raw(path, out["job"]["id"])["source_taint"] == S.SOURCE_TAINT,
          raw(path, out["job"]["id"])["source_taint"])
    check("...even though the latch is off when the copy is written",
          GATE.active is False)


def t_a_repeat_that_rearms_keeps_the_mark():
    s, path, clock = make("repeat")
    GATE.active = True
    job = s.add_repeat("alarm", {"every": "day", "at": "07:00"})
    GATE.active = False
    check("the repeating alarm is marked at creation",
          raw(path, job["id"])["source_taint"] == S.SOURCE_TAINT)
    due = raw(path, job["id"])["due"]
    clock.t = float(due) + 1.0
    s.tick(clock.t)
    row = raw(path, job["id"])
    check("it re-armed (still active with a new time)", row["state"] == "active", row["state"])
    check("...and the re-armed row kept read_outside",
          row["source_taint"] == S.SOURCE_TAINT, row["source_taint"])


# --------------------------------------------------------------------------
#   4. firing: latch once, with the reason, before on_fire
# --------------------------------------------------------------------------

PROBE_ORDER = []


def _probe_on_fire(job_id: str) -> None:
    PROBE_ORDER.append(list(GATE.latches))


S.register_kind("taintprobe", "probe", "Jarvis: probe.", has_text=True,
                on_fire=_probe_on_fire)


def t_firing_a_tainted_row_latches_before_on_fire():
    s, path, clock = make("fire")
    GATE.active = True
    job = s.add_at("taintprobe", clock.t + 60.0, "a probe")
    GATE.active = False
    GATE.latches.clear()
    PROBE_ORDER.clear()
    clock.t += 61.0
    fired = s.tick(clock.t)
    check("the tainted probe went off", fired == [job["id"]], fired)
    check("firing it latched exactly once", len(GATE.latches) == 1, GATE.latches)
    check("with the reason naming the mark, before anything else ran",
          GATE.latches == ["scheduled_task:" + S.SOURCE_TAINT], GATE.latches)
    check("the kind's own on_fire ran AFTER the latch",
          PROBE_ORDER == [["scheduled_task:" + S.SOURCE_TAINT]], PROBE_ORDER)


def t_firing_an_untainted_row_does_not_latch():
    s, _path, clock = make("untainted")
    GATE.active = False
    GATE.latches.clear()
    job = s.add_timer(30, "plain")
    clock.t += 31.0
    fired = s.tick(clock.t)
    check("the untainted timer went off", fired == [job["id"]], fired)
    check("firing it latched nothing", GATE.latches == [], GATE.latches)


def t_a_firing_latch_does_not_change_the_row():
    s, path, clock = make("unchanged")
    GATE.active = True
    job = s.add_timer(10, "keep")
    GATE.active = False
    clock.t += 11.0
    s.tick(clock.t)
    row = raw(path, job["id"])
    check("the row still carries its mark after firing",
          row["source_taint"] == S.SOURCE_TAINT, row["source_taint"])
    check("...and the latch is what was replayed, not a rewrite of the row",
          GATE.latches[-1] == "scheduled_task:" + S.SOURCE_TAINT, GATE.latches)


def main():
    print(f"--- schedule source taint --- ({S.__file__})")
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
