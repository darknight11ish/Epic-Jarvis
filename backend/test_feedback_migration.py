"""test_feedback_migration.py - the pre-v2 fixture migration smoke test (Q2/Q9).

    python3 backend/test_feedback_migration.py

WHY THIS EXISTS. The Wave-10 "Mark + why + save my correction" work adds two
columns to `feedback.db`'s `marks` table (`reason`, `correction`) and a new
`notes` table. The owner's live PC already has a `feedback.db` written by the
OLD backend, so the migration has to be proved against a real pre-v2 file -
one written by the old schema - and the real file must not be touched at all.
Owner ruling Q2 (2026-11-08, 15:45 PT) asked for that proof against a copy of
the live `feedback.db`; Q9 (2026-11-09) replaced the live copy with the fixture
described below, because the owner's file has since migrated to v2.

WHY A FIXTURE, AND NOT THE LIVE FILE (owner ruling Q9, 2026-11-09). This suite
used to copy the owner's live `feedback.db`
(`C:\\Users\\pcadmin\\.openjarvis\\feedback.db`) and assert the copy was still
pre-v2. On the owner's PC that file has since migrated to v2, so the copy half
failed at the desk every time, while CI - which has no live file - skipped it.
Q9's ruling: run the migration against an EXPLICIT pre-v2 FIXTURE COPY in
scratch instead of probing the live file.

THE FIXTURE (no binary blob in the repository). `_make_old_db` writes the OLD
schema in code - turns, turn_items, marks with four columns, retire_cards, no
notes table - and fills it with a fixed set of turns, fact ids, skill-note ids,
marks and one retire card. The same schema and the same rows on every machine
and every run, so the proof is deterministic and needs no owner file.

THE TWO HALVES, both always run:
  * synthetic - build the pre-v2 fixture, migrate it IN PLACE;
  * fixture copy - build the same pre-v2 fixture, take a byte copy with
    `shutil.copy2`, migrate the COPY, and prove the fixture itself is
    byte-for-byte untouched (sha256, size, mtime, no new file beside it). The
    fixture is only hashed, stat'd and copied - never opened with sqlite3.

WHAT THE PROOF IS, per database (both halves alike):
  1. BEFORE: record the schema, every table's row count, every old mark row,
     every turn/turn_item/retire_cards row, and the OLD-BODY counts derived
     independently from those rows (current mark = newest mark row per answer;
     helpful/harmful per memory fact and per skill note).
  2. OPEN with `jarvis_feedback` (setting `JARVIS_FEEDBACK_DB` at the copy) -
     `_connect()` runs `_create_schema`/`_migrate`, which is the thing under
     test. Then: `reason` and `correction` columns exist, the `notes` table
     exists, and EVERY row of every old table is still there, unchanged - no
     row lost, no value rewritten; old marks simply carry NULL for the two new
     columns.
  3. READ: `counts()` equals the independently derived old-body counts; the
     current mark of old answers still reads exactly (`mark_of`/`state_of`:
     mark unchanged, reason and correction empty).
  4. WRITE A NEW v2 MARK: a new answer, `wrong` + reason `misunderstood` + a
     correction - stored in the mark row, read back by `state_of`, kept as a
     manner note by `local_notes()`, and reflected in `counts()`.
  5. BOUNDS: a 500-character correction is accepted and round-trips exactly
     (no trimming inside the words, no reformatting); a 501-character one is
     REFUSED with the module's own 400 (never silently cut) and writes no mark
     and no note.
  6. A new mark written the OLD way (no reason, no correction) still works and
     stores NULL in both new columns.

NO LIVE FILE, NO LIVE INSTALL. `JARVIS_FEEDBACK_DB` is pointed at the scratch
database before any `jarvis_feedback` call, so the module's own fallback
(`~/.openjarvis/feedback.db`) cannot be reached; the guard below points it at a
non-existent scratch path even before the first proof. The suite never reads,
copies or writes the owner's real `feedback.db`, and does not need
`JARVIS_BACKEND` - it imports `jarvis_feedback` from this checkout's own
`backend/` folder. No network, no model: real sqlite files in a temp dir.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
import types
from contextlib import closing, contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-feedback-migration-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP / "config"
fw.LOG_DIR = _TMP / "logs"
fw.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
fw.LOG_DIR.mkdir(parents=True, exist_ok=True)
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)
os.environ.setdefault("JARVIS_NO_EMBED", "1")
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(fw.CONFIG_DIR))

import jarvis_feedback as F  # noqa: E402

PASSED, FAILED = [], []

#: A scratch path, set BEFORE any `jarvis_feedback` call, so the module's own
#: fallback (`~/.openjarvis/feedback.db`) is never reached even if a future
#: edit calls it early. `_prove` repoints it at the database under test.
os.environ["JARVIS_FEEDBACK_DB"] = str(_TMP / "never-the-live-file.db")


def check(name: str, cond, detail="") -> None:
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    """Fail the case if anything opens a socket."""

    def __enter__(self):
        import socket
        self.real = socket.socket.connect

        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        import socket
        socket.socket.connect = self.real
        return False


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def _raw(db: Path):
    """A plain read connection to a TEMP COPY (never the live file)."""
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


#: The pre-v2 schema the old backend writes (from jarvis_feedback's own
#: history: turns, turn_items, marks - four columns, retire_cards - and no
#: notes table).
_OLD_SCHEMA = (
    """CREATE TABLE turns (
        turn_id  TEXT PRIMARY KEY,
        created  REAL NOT NULL)""",
    """CREATE TABLE turn_items (
        turn_id  TEXT NOT NULL REFERENCES turns(turn_id),
        item     TEXT NOT NULL,
        PRIMARY KEY (turn_id, item))""",
    "CREATE INDEX turn_items_item ON turn_items(item)",
    """CREATE TABLE marks (
        id       INTEGER PRIMARY KEY,
        turn_id  TEXT NOT NULL REFERENCES turns(turn_id),
        mark     TEXT NOT NULL CHECK (mark IN ('right','wrong','none')),
        marked   REAL NOT NULL)""",
    "CREATE INDEX marks_turn ON marks(turn_id, id)",
    """CREATE TABLE retire_cards (
        id           INTEGER PRIMARY KEY,
        fact_id      INTEGER NOT NULL,
        proposal_id  INTEGER NOT NULL,
        helpful      INTEGER NOT NULL,
        harmful      INTEGER NOT NULL,
        raised       REAL NOT NULL)""",
)

USER_TABLES = ("turns", "turn_items", "marks", "retire_cards")


def _derive_old_counts(db: Path) -> dict:
    """The OLD-BODY counters, derived here from rows only (no module code).

    The same rule jarvis_feedback documents: the current mark is the newest
    mark row per answer; counts are per item ("mem:<id>" a fact, anything else
    a skill note) over answers whose current mark is right/wrong.
    """
    with _raw(db) as c:
        current = {r["turn_id"]: r["mark"] for r in c.execute(
            "SELECT turn_id, mark FROM marks"
            " WHERE id IN (SELECT MAX(id) FROM marks GROUP BY turn_id)")}
        facts, notes = {}, {}
        for r in c.execute("SELECT turn_id, item FROM turn_items"):
            mark = current.get(r["turn_id"])
            if mark not in ("right", "wrong"):
                continue
            item = r["item"]
            bucket = facts if item.startswith("mem:") else notes
            key = item[4:] if item.startswith("mem:") else item
            got = bucket.setdefault(key, {"helpful": 0, "harmful": 0})
            got["helpful" if mark == "right" else "harmful"] += 1
        cards = c.execute("SELECT COUNT(*) FROM retire_cards").fetchone()[0]
    facts = {k: v for k, v in facts.items() if v["helpful"] or v["harmful"]}
    notes = {k: v for k, v in notes.items() if v["helpful"] or v["harmful"]}
    return {
        "facts": facts,
        "skill_notes": notes,
        "answers_marked": {
            "right": sum(1 for m in current.values() if m == "right"),
            "wrong": sum(1 for m in current.values() if m == "wrong")},
        "retire_cards_raised": int(cards),
    }


def _snapshot(db: Path) -> dict:
    """Everything about the file that the migration must not disturb."""
    with _raw(db) as c:
        tables = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        cols = {t: [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
                for t in tables}
        counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in tables}
        marks = [tuple(r) for r in c.execute(
            "SELECT id, turn_id, mark, marked FROM marks ORDER BY id")]
        turns = [tuple(r) for r in c.execute(
            "SELECT turn_id, created FROM turns ORDER BY turn_id")]
        items = [tuple(r) for r in c.execute(
            "SELECT turn_id, item FROM turn_items ORDER BY turn_id, item")]
        cards = [tuple(r) for r in c.execute(
            "SELECT * FROM retire_cards ORDER BY id")]
    return {"tables": tables, "cols": cols, "counts": counts, "marks": marks,
            "turns": turns, "items": items, "cards": cards,
            "derived": _derive_old_counts(db)}


def _old_marks(db: Path) -> list:
    with _raw(db) as c:
        return [tuple(r) for r in c.execute(
            "SELECT id, turn_id, mark, marked FROM marks ORDER BY id")]


def _new_marks(db: Path) -> list:
    with _raw(db) as c:
        return [dict(r) for r in c.execute(
            "SELECT turn_id, mark, reason, correction FROM marks"
            " ORDER BY id")]


def _notes(db: Path) -> list:
    with _raw(db) as c:
        return [dict(r) for r in c.execute(
            "SELECT turn_id, kind, reason, text FROM notes ORDER BY id")]


def _make_old_db(path: Path) -> dict:
    """A synthetic pre-v2 database with real marks, facts and skill notes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    try:
        for statement in _OLD_SCHEMA:
            c.execute(statement)
        turn = lambda n: f"{n:032x}"          # a valid 32-char turn id
        turns = [turn(1), turn(2), turn(3), turn(4), turn(5), turn(6)]
        for i, tid in enumerate(turns):
            c.execute("INSERT INTO turns (turn_id, created) VALUES (?,?)",
                      (tid, 1700000000.0 + i))
        note_a = F.note_id("email", "keep replies short")
        note_b = F.note_id("calendar", "no meetings before 9")
        items = {
            turn(1): ["mem:11", note_a],
            turn(2): ["mem:11", "mem:22"],
            turn(3): ["mem:11", "mem:22"],
            turn(4): ["mem:22", note_a],
            turn(5): [note_b],
            turn(6): ["mem:11", note_b],
        }
        for tid, its in items.items():
            for item in its:
                c.execute("INSERT INTO turn_items (turn_id, item) VALUES (?,?)",
                          (tid, item))
        marks = [
            (turn(1), "right", 1700000100.0),
            (turn(2), "wrong", 1700000200.0),
            (turn(3), "right", 1700000300.0),   # then taken back below
            (turn(3), "none", 1700000301.0),
            (turn(4), "wrong", 1700000400.0),
            (turn(5), "right", 1700000500.0),
        ]
        c.executemany("INSERT INTO marks (turn_id, mark, marked) VALUES (?,?,?)",
                      marks)
        c.execute("INSERT INTO retire_cards (fact_id, proposal_id, helpful,"
                  " harmful, raised) VALUES (?,?,?,?,?)", (22, 7, 0, 5, 1.0))
        c.commit()
    finally:
        c.close()
    return {"turns": turns, "note_a": note_a, "note_b": note_b,
            "expected_counts": {
                "turns": len(turns),
                "turn_items": sum(len(v) for v in items.values()),
                "marks": len(marks),
                "retire_cards": 1}}


def _prove(db: Path, label: str, *, old_turn: str = "") -> dict:
    """The whole migration proof on ONE database copy. Returns facts for print."""
    pre = _snapshot(db)
    had_v2 = ("reason" in pre["cols"].get("marks", ())
              and "notes" in pre["counts"])
    report = {"label": label, "had_v2": had_v2, "pre": pre}

    os.environ["JARVIS_FEEDBACK_DB"] = str(db)
    with NoNetwork():
        counts = F.counts()                     # <- triggers the migration
        post = _snapshot(db)

        # ---- 2. the schema grew, and nothing was lost ---------------------
        check(f"{label}: the marks table gained reason + correction",
              "reason" in post["cols"].get("marks", ())
              and "correction" in post["cols"].get("marks", ()),
              post["cols"].get("marks"))
        check(f"{label}: the notes table exists", "notes" in post["counts"],
              sorted(post["counts"]))
        for table in USER_TABLES:
            check(f"{label}: no {table} row was lost",
                  post["counts"].get(table) == pre["counts"].get(table),
                  f"{pre['counts'].get(table)} -> {post['counts'].get(table)}")
        check(f"{label}: every old mark row is unchanged",
              _old_marks(db) == pre["marks"],
              f"{len(pre['marks'])} rows")
        with _raw(db) as c:
            untouched = c.execute(
                "SELECT COUNT(*) FROM marks WHERE reason IS NOT NULL"
                " OR correction IS NOT NULL").fetchone()[0]
        check(f"{label}: old marks carry NULL in both new columns",
              untouched == 0, untouched)
        if not had_v2:
            check(f"{label}: the old file had no v2 columns before opening",
                  "reason" not in pre["cols"].get("marks", ())
                  and "notes" not in pre["counts"],
                  pre["cols"].get("marks"))

        # ---- 3. the old readings are exactly the same ---------------------
        check(f"{label}: counts() equals the independently derived old counts",
              counts["facts"] == pre["derived"]["facts"]
              and counts["skill_notes"] == pre["derived"]["skill_notes"]
              and counts["answers_marked"] == pre["derived"]["answers_marked"]
              and counts["retire_cards_raised"]
              == pre["derived"]["retire_cards_raised"],
              (counts, pre["derived"]))
        if old_turn:
            want = next(m for m in pre["marks"] if m[1] == old_turn)
            check(f"{label}: the current mark of an old answer still reads",
                  F.mark_of(old_turn) == want[2], F.mark_of(old_turn))
            check(f"{label}: ... with no reason or correction invented",
                  F.state_of(old_turn) == {"mark": want[2], "reason": "",
                                           "correction": ""},
                  F.state_of(old_turn))

        # ---- 4. a NEW v2 mark writes, reads back, and notes locally -------
        text = "I meant the other Mario, the plumber on level 2."
        tid = F.record_turn(["mem:901"])
        out = F.mark(tid, "wrong", reason="misunderstood", correction=text)
        check(f"{label}: a new v2 mark is accepted",
              out.get("ok") is True and out.get("changed") is True, out)
        check(f"{label}: ... it echoes the reason and saves the correction",
              out.get("reason") == "misunderstood"
              and out.get("correction_saved") is True, out)
        check(f"{label}: ... state_of reads the mark, why and correction back",
              F.state_of(tid) == {"mark": "wrong",
                                  "reason": "misunderstood",
                                  "correction": text},
              F.state_of(tid))
        check(f"{label}: ... the correction lives in the mark row",
              any(m["turn_id"] == tid and m["reason"] == "misunderstood"
                  and m["correction"] == text for m in _new_marks(db)),
              _new_marks(db)[-3:])
        check(f"{label}: ... and the manner note is kept locally",
              any(n["turn_id"] == tid and n["kind"] == "manner"
                  and n["reason"] == "misunderstood" and n["text"] == text
                  for n in F.local_notes()),
              F.local_notes()[-2:])
        check(f"{label}: ... the note is not counted as a remembered fact",
              all(tid not in k for k in counts.get("facts", {})))

        # ---- 5. 500 round-trips; 501 is refused, never cut ----------------
        longest = ("the quick brown fox jumps over the lazy dog. " * 12)[:500]
        check(f"{label}: the fixture correction is exactly 500", len(longest) == 500)
        tid2 = F.record_turn(["mem:902"])
        out2 = F.mark(tid2, "wrong", reason="misunderstood", correction=longest)
        check(f"{label}: a 500-character correction is accepted",
              out2.get("ok") is True and out2.get("correction_saved") is True, out2)
        check(f"{label}: ... and round-trips exactly",
              F.state_of(tid2) == {"mark": "wrong",
                                   "reason": "misunderstood",
                                   "correction": longest},
              F.state_of(tid2))
        too_long = "x" * 501
        tid3 = F.record_turn(["mem:903"])
        marks_before = len(_new_marks(db))
        notes_before = len(_notes(db))
        out3 = F.mark(tid3, "wrong", reason="misunderstood", correction=too_long)
        check(f"{label}: a 501-character correction is refused",
              out3.get("ok") is False and out3.get("status") == 400
              and "500 characters or fewer" in str(out3.get("reason")),
              out3)
        check(f"{label}: ... the refusal writes no mark and no note",
              len(_new_marks(db)) == marks_before
              and len(_notes(db)) == notes_before,
              (marks_before, len(_new_marks(db)), notes_before, len(_notes(db))))
        check(f"{label}: ... and the answer is still unmarked",
              F.state_of(tid3) == {"mark": "none", "reason": "",
                                   "correction": ""},
              F.state_of(tid3))

        # ---- 6. the old body still works on the new file ------------------
        tid4 = F.record_turn(["mem:904"])
        out4 = F.mark(tid4, "right")
        check(f"{label}: an old-body mark still works after migration",
              out4.get("ok") is True and out4.get("mark") == "right", out4)
        check(f"{label}: ... and stores no reason or correction",
              F.state_of(tid4) == {"mark": "right", "reason": "",
                                   "correction": ""},
              F.state_of(tid4))

    report["final_counts"] = {t: _snapshot(db)["counts"].get(t)
                              for t in USER_TABLES}
    report["final_notes"] = len(_notes(db))
    report["counts"] = counts
    return report


# --------------------------------------------------------------------------
#   The synthetic half - always runs, including on a CI runner
# --------------------------------------------------------------------------
def t_the_synthetic_pre_v2_fixture_migrates():
    d = Path(tempfile.mkdtemp(prefix="synthetic-", dir=_TMP))
    db = d / "feedback.db"
    made = _make_old_db(db)
    pre_counts = _snapshot(db)["counts"]
    check("synthetic: it starts from the old 4-column marks table and no notes",
          "reason" not in _snapshot(db)["cols"]["marks"]
          and "notes" not in _snapshot(db)["counts"],
          _snapshot(db)["cols"]["marks"])
    report = _prove(db, "synthetic", old_turn=made["turns"][1])
    counts = report["counts"]
    check("synthetic: the fact counters are the expected ones",
          counts["facts"].get("11") is not None
          and counts["facts"]["11"]["helpful"] >= 1,
          counts["facts"])
    check("synthetic: the skill-note counters are the expected ones",
          bool(counts["skill_notes"]), counts["skill_notes"])
    check("synthetic: the old retire-card count survives",
          counts["retire_cards_raised"] == 1, counts["retire_cards_raised"])
    check("synthetic: no old table row was lost end-to-end",
          all(report["final_counts"][t] >= pre_counts[t] for t in USER_TABLES),
          report["final_counts"])


# --------------------------------------------------------------------------
#   The fixture-copy half - an explicit pre-v2 fixture, copied, then migrated
# --------------------------------------------------------------------------
def t_the_pre_v2_fixture_copy_migrates():
    """A byte copy of the explicit pre-v2 fixture migrates; the fixture does not.

    Q9's replacement for the old live-copy half: the same proof and the same
    copy shape, but the source is the deterministic fixture `_make_old_db`
    writes in scratch. The fixture is only hashed, stat'd and copied - never
    opened with sqlite3 - so "the source was not touched" is proved by bytes,
    not by a read-only connection.
    """
    fixture_dir = Path(tempfile.mkdtemp(prefix="fixture-", dir=_TMP))
    fixture = fixture_dir / "pre-v2-feedback.db"
    made = _make_old_db(fixture)
    before_hash = sha256(fixture)
    before_size = fixture.stat().st_size
    before_mtime = fixture.stat().st_mtime
    before_names = sorted(p.name for p in fixture_dir.iterdir())

    copy_dir = Path(tempfile.mkdtemp(prefix="fixture-copy-", dir=_TMP))
    copy = copy_dir / "feedback.db"
    shutil.copy2(fixture, copy)
    copy_hash = sha256(copy)
    check("fixture copy: the copy is byte-identical to the fixture",
          copy_hash == before_hash, (copy_hash, before_hash))

    report = _prove(copy, "fixture copy", old_turn=made["turns"][1])
    check("fixture copy: it started from the old 4-column marks table and no notes",
          "reason" not in report["pre"]["cols"].get("marks", ())
          and "notes" not in report["pre"]["counts"],
          report["pre"]["cols"].get("marks"))
    check("fixture copy: the copy's pre-migration rows are the fixture's rows",
          {t: report["pre"]["counts"].get(t) for t in USER_TABLES}
          == made["expected_counts"],
          (report["pre"]["counts"], made["expected_counts"]))
    # The old live-copy half could only assert this on a machine with a pre-v2
    # live file, and the owner's already-migrated file made it fail forever.
    # On the fixture it is deterministic.
    check("fixture copy: the copy started as a pre-v2 file",
          report["had_v2"] is False, report["had_v2"])

    # The fixture must be untouched: same bytes, same size, same mtime, and no
    # sidecar file created beside it.
    after_hash = sha256(fixture)
    after_names = sorted(p.name for p in fixture_dir.iterdir())
    check("fixture: the fixture's sha256 is unchanged",
          after_hash == before_hash, (before_hash, after_hash))
    check("fixture: the fixture's size and mtime are unchanged",
          fixture.stat().st_size == before_size
          and fixture.stat().st_mtime == before_mtime,
          (before_size, fixture.stat().st_size))
    check("fixture: this run created no new file beside the fixture",
          after_names == before_names, (before_names, after_names))
    check("fixture: jarvis_feedback ran against the copy, not the fixture",
          F.db_path().resolve() == copy.resolve(), F.db_path())

    # The numbers the Lead asked for, printed so they are in the log:
    print("\n--- pre-v2 fixture copy: measured ---")
    print(f"    fixture sha256 (before == after): {before_hash}")
    print(f"    copy sha256:                      {copy_hash}")
    print(f"    pre-migration schema: marks columns "
          f"{report['pre']['cols'].get('marks')}, tables {report['pre']['tables']}")
    print(f"    pre-migration row counts: {report['pre']['counts']}")
    print(f"    post-migration row counts: {report['final_counts']}")
    print(f"    old-body counts read back: facts={len(report['counts']['facts'])}, "
          f"skill_notes={len(report['counts']['skill_notes'])}, "
          f"answers_marked={report['counts']['answers_marked']}, "
          f"retire_cards={report['counts']['retire_cards_raised']}")
    print(f"    v2 notes after the new marks: {report['final_notes']}")


def main():
    try:
        for fn in (t_the_synthetic_pre_v2_fixture_migrates,
                   t_the_pre_v2_fixture_copy_migrates):
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
        print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
        if FAILED:
            print("failed: " + ", ".join(FAILED))
        return 1 if FAILED else 0
    finally:
        # Everything this suite writes lives under this one scratch root.
        # Remove it so a second run starts from nothing - and so no scratch
        # file is left anywhere for a later reader to mistake for a live one.
        shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
