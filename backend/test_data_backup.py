"""tools/jarvis_data_backup.py takes one consistent, verified snapshot of the
owner's Jarvis data, keeps only the newest few, and can put one back.

    python3 test_data_backup.py

WHY

The owner's personal data - 19 SQLite databases, his settings file, his
voice-print - lives in `~/.openjarvis`, and on 2026-10-13 the only copy of
several of those databases was the one Jarvis itself keeps open. The attempt at
a copy that existed was a plain file copy, and it was measurably not a
snapshot: **16 tables and 10 rows were lost**, three databases were missing
outright, and its `agents.db` was an empty shell (0 tables where the live
database reads 6) because the database was still in a 115 KB `-wal` that the
copy left behind.

That is the failure this suite is built around. Everything here is a fixture
made in a temp folder: **nothing in this file reads or writes the owner's real
`~/.openjarvis`**, so it runs in CI where no such folder exists. What it proves:

  1. the tool contains no network call at all - checked by reading the module's
     own source, because the claim is about the file, not about a run;
  2. a database whose newest rows are still only in the `-wal` is snapshotted
     whole, and the `-wal` itself is never copied - the exact failure above,
     reproduced in a fixture and then shown to be fixed;
  3. every database in a snapshot opens, passes `PRAGMA integrity_check`, and
     holds the tables and rows the live database had;
  4. a snapshot that lost a table, or was truncated, is CAUGHT - this is the
     check a plain copy cannot pass;
  5. the tool never writes into the folder it is reading, and a restore refuses
     to write there either - asked for and refused, with the folder shown to be
     untouched afterwards;
  6. a restore to a spare folder really puts the data back, rows and all;
  7. keeping the newest few deletes only snapshots of this tool's own making -
     the owner's `.jbak` files and the older plain copy are left alone;
  8. a sealed snapshot round-trips, a wrong passphrase is refused in plain
     words, and a missing `cryptography` refuses BEFORE anything is written;
  9. the weekly task runs `pythonw.exe` (no window), weekly, with no `/RU` and
     no `/RP` (no administrator, no stored password).
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
import jarvis_data_backup as jdb  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []
ROOT_TMP = None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """A check this machine cannot run. Printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


# ---------------------------------------------------------------------------
#   Fixtures - a small stand-in for ~/.openjarvis, in a temp folder
# ---------------------------------------------------------------------------


def make_wal_db(path: Path, rows: int = 5):
    """A database whose newest rows are STILL ONLY IN THE -wal.

    The connection is returned open and must stay open: closing it checkpoints
    the log away and the fixture would stop reproducing the real failure
    (`agents.db`, 4,096 bytes of file beside a 115,392-byte log).
    """
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
    conn.executemany("INSERT INTO notes (body) VALUES (?)",
                     [(f"row {i}",) for i in range(rows)])
    conn.commit()
    return conn


def make_plain_db(path: Path, rows: int = 3):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, word TEXT)")
    conn.executemany("INSERT INTO facts (word) VALUES (?)",
                     [(f"fact {i}",) for i in range(rows)])
    conn.commit()
    conn.close()


def build_source(base: Path) -> Path:
    """A source folder shaped like the real one, and small."""
    src = base / "source"
    (src / "voice").mkdir(parents=True)
    (src / "devices").mkdir(parents=True)
    (src / "voice-models").mkdir(parents=True)
    src.joinpath("config.toml").write_text("[server]\nport = 8765\n", encoding="utf-8")
    src.joinpath("speed.jsonl").write_text('{"t": 1}\n', encoding="utf-8")
    src.joinpath("voice", "owner-phone.json").write_text('{"print": "his"}', encoding="utf-8")
    src.joinpath("devices", "registry.json").write_text('{"phones": 1}', encoding="utf-8")
    # 1.14 GB on the real PC; here, enough to prove the exclusion is by name
    src.joinpath("voice-models", "big.bin").write_bytes(b"x" * 4096)
    make_plain_db(src / "memory.db", rows=3)
    return src


def manifest_of(snapshot) -> dict:
    return json.loads((Path(snapshot) / jdb.MANIFEST).read_text(encoding="utf-8"))


def rows_of(db: Path, table: str) -> int:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        conn.close()


def _can_still_write(conn) -> bool:
    """Proves the snapshot did not lock or damage the live database: the
    process that owns it can still commit a row afterwards."""
    try:
        conn.execute("INSERT INTO notes (body) VALUES ('written after the snapshot')")
        conn.commit()
        return True
    except sqlite3.DatabaseError:
        return False


def _raised(fn):
    """Run it and hand back the exception, so a check can look at it."""
    try:
        fn()
    except Exception as exc:      # noqa: BLE001 - the point is to inspect it
        return exc
    return None


# ---------------------------------------------------------------------------
#   1. no network call, read out of the module's own source
# ---------------------------------------------------------------------------

#: Every way this could reach off the machine, by the name it would be imported
#: or called under. A backup on a timer is exactly what grows a "send it to the
#: cloud" option later, so the door is checked shut rather than described as shut.
FORBIDDEN = ("socket", "urllib", "http.client", "httplib", "requests", "ftplib",
             "smtplib", "telnetlib", "xmlrpc", "paramiko", "pycurl", "webbrowser",
             "urlopen", "webhook", "boto3", "azure", "google.cloud")


def t_no_network_call_anywhere_in_the_tool():
    print("\n--- t_no_network_call_anywhere_in_the_tool ---")
    source = (ROOT / "tools" / jdb.TOOL).read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    # The module's own docstring NAMES these modules to say it does not use
    # them, so the prose is dropped and only real code is searched.
    code = code.split('"""', 2)[-1]
    found = [word for word in FORBIDDEN if word in code]
    check("the tool's own source names no way off this machine "
          f"({len(FORBIDDEN)} checked)", not found,
          "found: " + ", ".join(found))
    for module in ("socket", "urllib", "http"):
        check(f"`import {module}` appears nowhere in the tool",
              f"import {module}" not in code)
    check("and it really is the file the command line runs",
          "if __name__" in source and "main()" in source)


# ---------------------------------------------------------------------------
#   2 + 3. the -wal rows are in the snapshot, and the -wal itself is not
# ---------------------------------------------------------------------------


def t_a_database_living_in_its_wal_is_snapshotted_whole():
    print("\n--- t_a_database_living_in_its_wal_is_snapshotted_whole ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-wal-", dir=ROOT_TMP))
    src = build_source(base)
    dest = base / "snapshots"
    conn = make_wal_db(src / "agents.db", rows=7)
    try:
        wal = src / "agents.db-wal"
        check("the fixture really has its rows in a -wal, as the live PC did",
              wal.is_file() and wal.stat().st_size > 0,
              f"wal exists={wal.is_file()}")

        # What a plain file copy does: take the .db, leave the log. This is the
        # measured failure (agents.db: 0 tables where the live one had 6), and
        # reproducing it here is what makes the next check mean something.
        plain = base / "plain-copy"
        plain.mkdir()
        shutil.copy2(src / "agents.db", plain / "agents.db")
        alone = sqlite3.connect(f"file:{(plain / 'agents.db').as_posix()}?mode=ro", uri=True)
        try:
            tables_alone = [r[0] for r in alone.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
        finally:
            alone.close()
        check("a plain copy of that .db alone loses the whole database "
              "(the failure being fixed)", tables_alone == [],
              f"the plain copy still had {tables_alone}")

        result = jdb.take_snapshot(src, dest, now=1_700_000_000)
        snap = Path(result["path"])
        check("the snapshot was taken and verified", result["ok"],
              "; ".join(result["problems"]))
        check("the whole database came across, tables and rows",
              rows_of(snap / "agents.db", "notes") == 7,
              f"{rows_of(snap / 'agents.db', 'notes')} rows, expected 7")
        check("no -wal, -shm or -journal file was copied into the snapshot",
              not [p.name for p in snap.iterdir()
                   if p.name.endswith(("-wal", "-shm", "-journal"))],
              str([p.name for p in snap.iterdir()]))
        entry = manifest_of(snap)["databases"]["agents.db"]
        check("the manifest says which SQLite method made it",
              entry["method"] in ("vacuum_into", "online_backup"), str(entry["method"]))
        check("and the manifest's own row count matches the file",
              entry["rows"] == 7, str(entry["rows"]))
        check("the source database is untouched and still writable afterwards",
              _can_still_write(conn),
              "writing to the live database failed after the snapshot")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
#   4. a snapshot that lost something is caught
# ---------------------------------------------------------------------------


def t_a_broken_snapshot_is_caught_and_not_counted():
    print("\n--- t_a_broken_snapshot_is_caught_and_not_counted ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-bad-", dir=ROOT_TMP))
    src = build_source(base)
    dest = base / "snapshots"
    result = jdb.take_snapshot(src, dest, now=1_700_000_100)
    snap = Path(result["path"])
    check("the good snapshot verifies with no problems",
          jdb.verify_snapshot(snap)["problems"] == [],
          str(jdb.verify_snapshot(snap)["problems"]))

    # (a) the empty shell: exactly what a plain copy of a WAL database leaves.
    shell = base / "shell.db"
    sqlite3.connect(str(shell)).close()
    shutil.copy2(shell, snap / "memory.db")
    problems = jdb.verify_snapshot(snap)["problems"]
    check("a database replaced by an empty shell IS caught",
          problems and any("sha256" in p or "tables" in p for p in problems),
          str(problems))

    # (b) a file cut short - the "copy that did not finish" case.
    shutil.copy2(src / "memory.db", snap / "memory.db")
    with open(snap / "memory.db", "r+b") as fh:
        fh.truncate(64)
    problems = jdb.verify_snapshot(snap)["problems"]
    check("a truncated database IS caught", bool(problems), str(problems))

    # (c) a changed settings file - not a database, and still caught.
    result2 = jdb.take_snapshot(src, dest, now=1_700_000_200)
    snap2 = Path(result2["path"])
    (snap2 / "config.toml").write_text("tampered\n", encoding="utf-8")
    problems = jdb.verify_snapshot(snap2)["problems"]
    check("a changed non-database file IS caught",
          any("config.toml" in p for p in problems), str(problems))


def t_a_failed_snapshot_is_kept_but_never_counted():
    print("\n--- t_a_failed_snapshot_is_kept_but_never_counted ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-inc-", dir=ROOT_TMP))
    src = build_source(base)
    # A file called .db that is not a database at all: the one thing that makes
    # a snapshot fail its own checks on a healthy machine.
    (src / "broken.db").write_bytes(b"this is not a sqlite database at all")
    dest = base / "snapshots"
    result = jdb.take_snapshot(src, dest, now=1_700_000_300)
    check("the run reports FAILED rather than pretending", result["ok"] is False)
    check("the failure names the database that would not open",
          any("broken.db" in p for p in result["problems"]), str(result["problems"]))
    check("the bad snapshot is kept for inspection, plainly named",
          result["name"].endswith(jdb.INCOMPLETE), result["name"])
    check("and it is never counted as one of the kept backups",
          [r["name"] for r in jdb.list_snapshots(dest) if not r["incomplete"]] == [],
          str([r["name"] for r in jdb.list_snapshots(dest)]))


# ---------------------------------------------------------------------------
#   5. it never writes into the folder it is reading
# ---------------------------------------------------------------------------


def t_it_never_writes_into_the_folder_it_reads():
    print("\n--- t_it_never_writes_into_the_folder_it_reads ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-guard-", dir=ROOT_TMP))
    src = build_source(base)
    before = sorted(p.name for p in src.iterdir())

    refused_dest = False
    try:
        jdb.take_snapshot(src, src / "snapshots", now=1_700_000_400)
    except jdb.Refused as exc:
        refused_dest = "inside" in str(exc)
    check("a destination inside the live folder is refused", refused_dest)
    check("...and nothing at all was created there",
          sorted(p.name for p in src.iterdir()) == before,
          f"{before} -> {sorted(p.name for p in src.iterdir())}")

    dest = base / "snapshots"
    snap = jdb.take_snapshot(src, dest, now=1_700_000_500)["path"]
    refused_restore = False
    try:
        jdb.restore_snapshot(snap, src, source=src)
    except jdb.Refused as exc:
        refused_restore = "inside" in str(exc)
    check("a restore INTO the live folder is refused too", refused_restore)
    check("...and the live folder is still exactly as it was",
          sorted(p.name for p in src.iterdir()) == before,
          f"{before} -> {sorted(p.name for p in src.iterdir())}")
    check("so a typo cannot turn a backup into a write over the live data",
          refused_dest and refused_restore)


# ---------------------------------------------------------------------------
#   6. a restore really puts it back, into a spare folder
# ---------------------------------------------------------------------------


def t_a_restore_really_puts_the_data_back():
    print("\n--- t_a_restore_really_puts_the_data_back ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-restore-", dir=ROOT_TMP))
    src = build_source(base)
    conn = make_wal_db(src / "agents.db", rows=9)
    try:
        dest = base / "snapshots"
        snap = jdb.take_snapshot(src, dest, now=1_700_000_600)["path"]
        manifest = manifest_of(snap)
        target = base / "restored"
        out = jdb.restore_snapshot(snap, target)

        check("the restore reports no problems", out["problems"] == [],
              str(out["problems"]))
        check("the restored folder holds every database the snapshot had",
              sorted(out["counts"]) == sorted(manifest["databases"]),
              f"{sorted(out['counts'])} vs {sorted(manifest['databases'])}")
        check("the row counts read back out of the RESTORE match the manifest",
              all(out["counts"][name] == manifest["databases"][name]["rows"]
                  for name in out["counts"]),
              f"{out['counts']} vs "
              f"{ {k: v['rows'] for k, v in manifest['databases'].items()} }")
        check("the rows that lived only in the -wal arrived with it",
              rows_of(target / "agents.db", "notes") == 9,
              f"{rows_of(target / 'agents.db', 'notes')} rows, expected 9")
        check("the plain files came back too",
              (target / "config.toml").is_file() and (target / "speed.jsonl").is_file()
              and (target / "voice" / "owner-phone.json").is_file())
        check("a note saying how to restore is written beside the data",
              (target / jdb.README).is_file()
              and "restore" in (target / jdb.README).read_text(encoding="utf-8").lower())
        spare = jdb.restore_snapshot(snap, to_temp=True)["target"]
        check("--to-temp lands in a fresh folder of its own, not in the live one",
              "jarvis-restore-" in spare)
        shutil.rmtree(spare, ignore_errors=True)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
#   7. retention: the newest few, and only its own
# ---------------------------------------------------------------------------


def t_keeping_the_newest_few_touches_nothing_else():
    print("\n--- t_keeping_the_newest_few_touches_nothing_else ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-keep-", dir=ROOT_TMP))
    src = build_source(base)
    dest = base / "snapshots"
    dest.mkdir()

    # Things that are NOT this tool's: the owner's encrypted backups and the
    # older plain copy. Retention must not know they exist.
    (dest / "jarvis-backup-20261010-164905.jbak").write_bytes(b"JBAK1" + b"x" * 100)
    (dest / "jarvis-data-2026-10-13-223631").mkdir()
    (dest / "jarvis-data-2026-10-13-223631" / "memory.db").write_bytes(b"old copy")

    made = []
    for i in range(6):
        made.append(jdb.take_snapshot(src, dest, keep=4, now=1_700_001_000 + i)["name"])
    rows = jdb.list_snapshots(dest)
    good = [r for r in rows if not r["incomplete"]]
    check("only 4 of the 6 are kept", len(good) == 4, str([r["name"] for r in good]))
    check("the newest one is kept, not deleted by its own retention",
          made[-1] in [r["name"] for r in good], str(made))
    check("the oldest two are the ones removed",
          made[0] not in [r["name"] for r in good] and
          made[1] not in [r["name"] for r in good], str(sorted(r["name"] for r in good)))
    check("the owner's .jbak file is untouched",
          (dest / "jarvis-backup-20261010-164905.jbak").is_file())
    check("the older plain copy is untouched",
          (dest / "jarvis-data-2026-10-13-223631" / "memory.db").is_file())
    check("so a weekly timer cannot pile up the way the code backups did",
          len(good) == jdb.KEEP == 4)
    check("list_snapshots is newest first", 
          [r["name"] for r in rows] == sorted([r["name"] for r in rows], reverse=True),
          str([r["name"] for r in rows]))


# ---------------------------------------------------------------------------
#   8. sealing: the half that is safe to decide, and its refusals
# ---------------------------------------------------------------------------


def t_a_sealed_snapshot_round_trips():
    print("\n--- t_a_sealed_snapshot_round_trips ---")
    if jdb._crypto()[0] is None:
        skip("a sealed snapshot round trips", "the `cryptography` package is not installed")
        return
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-seal-", dir=ROOT_TMP))
    src = build_source(base)
    conn = make_wal_db(src / "agents.db", rows=4)
    try:
        dest = base / "snapshots"
        phrase = "correct horse battery staple"
        result = jdb.take_snapshot(src, dest, passphrase=phrase, now=1_700_002_000)
        sealed = Path(result["path"])
        check("a sealed snapshot is ONE file, not a folder",
              sealed.is_file() and sealed.suffix == jdb.SEAL_SUFFIX and not sealed.is_dir(),
              str(sealed))
        check("and no plainly readable folder was left beside it",
              not [p.name for p in dest.iterdir() if p.is_dir()], 
              str([p.name for p in dest.iterdir()]))
        check("it does not open without the passphrase - in plain words",
              isinstance(_raised(lambda: jdb.verify_snapshot(sealed)), jdb.Refused)
              and "passphrase" in str(_raised(lambda: jdb.verify_snapshot(sealed))),
              str(_raised(lambda: jdb.verify_snapshot(sealed))))
        opened = jdb.verify_snapshot(sealed, phrase)
        check("with the passphrase it opens and verifies clean",
              opened["problems"] == [], str(opened["problems"]))
        check("the rows that lived only in the -wal are in the sealed copy",
              opened["counts"].get("agents.db") == 4, str(opened["counts"]))
        wrong = _raised(lambda: jdb.verify_snapshot(sealed, "not the passphrase"))
        check("a wrong passphrase is refused in plain words, not a library error",
              isinstance(wrong, jdb.Refused) and "does not open" in str(wrong), str(wrong))
        restored = jdb.restore_snapshot(sealed, base / "out", passphrase=phrase)
        check("and it restores, with the real row counts",
              restored["problems"] == [] and rows_of(Path(restored["target"]) /
                                                     "agents.db", "notes") == 4,
              str(restored))
    finally:
        conn.close()


def t_sealing_without_the_library_writes_nothing():
    print("\n--- t_sealing_without_the_library_writes_nothing ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-nocrypto-", dir=ROOT_TMP))
    src = build_source(base)
    dest = base / "snapshots"
    dest.mkdir()
    real = jdb._crypto
    jdb._crypto = lambda: (None, None)          # stand in for a PC without it
    try:
        folder = base / "made-up-snapshot"
        folder.mkdir()
        (folder / "memory.db").write_bytes(b"pretend")
        raised = _raised(lambda: jdb._seal_folder(folder, base / "sealed.jba", "phrase"))
        check("sealing without `cryptography` refuses in plain words",
              isinstance(raised, jdb.Refused) and "cryptography" in str(raised), str(raised))
        check("and it wrote no sealed file, and no unsealed copy either",
              not (base / "sealed.jba").exists()
              and not [p.name for p in base.iterdir() if p.name.endswith(jdb.SEAL_SUFFIX)],
              str([p.name for p in base.iterdir()]))
        os_environ_set("JARVIS_TEST_PHRASE", "phrase")
        code = jdb.main(["backup", "--source", str(src), "--dest", str(dest),
                         "--seal", "--passphrase-env", "JARVIS_TEST_PHRASE"])
        check("the command line refuses before taking any snapshot at all",
              code == 2 and jdb.list_snapshots(dest) == []
              and not [p.name for p in dest.iterdir() if p.is_dir()],
              f"exit {code}, dest holds {[p.name for p in dest.iterdir()]}")
    finally:
        jdb._crypto = real
        os_environ_unset("JARVIS_TEST_PHRASE")


# ---------------------------------------------------------------------------
#   9. the weekly timer: no window, no administrator
# ---------------------------------------------------------------------------


def t_two_runs_inside_one_second_do_not_collide():
    print("\n--- t_two_runs_inside_one_second_do_not_collide ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-tick-", dir=ROOT_TMP))
    src = build_source(base)
    dest = base / "snapshots"
    # The SAME `now` for both: on Windows the clock only moves on the system
    # timer tick, so a hand-run and the weekly task really do ask for the same
    # name - and `mkdir` without asking the filesystem first dies with
    # FileExistsError [WinError 183]. tools/check_same_tick_paths.py exists for
    # the three Windows CI suites that shape broke.
    first = jdb.take_snapshot(src, dest, now=1_700_003_000)
    second = jdb.take_snapshot(src, dest, now=1_700_003_000)
    check("two snapshots taken in the same second are two folders, not one",
          first["name"] != second["name"] and Path(first["path"]).is_dir()
          and Path(second["path"]).is_dir(),
          f"{first['name']} / {second['name']}")
    check("both of them verify",
          jdb.verify_snapshot(first["path"])["problems"] == []
          and jdb.verify_snapshot(second["path"])["problems"] == [],
          f"{jdb.verify_snapshot(first['path'])['problems']} "
          f"{jdb.verify_snapshot(second['path'])['problems']}")
    check("and the second did not delete the first",
          len([r for r in jdb.list_snapshots(dest) if not r["incomplete"]]) == 2,
          str([r["name"] for r in jdb.list_snapshots(dest)]))
    check("no half-built folder is left behind",
          not [p.name for p in dest.iterdir() if p.name.endswith(".partial")],
          str([p.name for p in dest.iterdir()]))


def t_a_refused_run_still_leaves_a_trace():
    print("\n--- t_a_refused_run_still_leaves_a_trace ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-trace-", dir=ROOT_TMP))
    src = build_source(base)
    dest = base / "snapshots"
    dest.mkdir()
    # The weekly task never passes --seal, so this refusal is not the task's
    # own path - but it is the shape of every early refusal, and the point is
    # that `pythonw.exe` has no console: a refusal printed to stdout goes
    # nowhere, and a task that FAILED must not look like one that has not run.
    real = jdb._crypto
    jdb._crypto = lambda: (None, None)
    os_environ_set("JARVIS_TEST_PHRASE", "phrase")
    try:
        with isolated_env(JARVIS_DATA_BACKUP_STATE_DIR=str(base / "state")):
            code = jdb.main(["backup", "--source", str(src), "--dest", str(dest),
                             "--seal", "--passphrase-env", "JARVIS_TEST_PHRASE"])
        note = dest / "last-run.txt"
        check("a run that refused before writing anything is recorded as FAILED",
              code == 2 and note.is_file() and "FAILED" in note.read_text(encoding="utf-8"),
              f"exit {code}, note: {note.read_text(encoding='utf-8') if note.is_file() else 'ABSENT'}")
        check("and the reason is in it, so the owner can act on it",
              note.is_file() and "cryptography" in note.read_text(encoding="utf-8"),
              note.read_text(encoding="utf-8") if note.is_file() else "ABSENT")
        check("...and nothing that looks like a backup was left behind",
              jdb.list_snapshots(dest) == [], str(jdb.list_snapshots(dest)))
    finally:
        jdb._crypto = real
        os_environ_unset("JARVIS_TEST_PHRASE")

    # And the note must never be the thing that writes into the live folder.
    refusals = src / "would-be-dest"
    with isolated_env(JARVIS_DATA_BACKUP_STATE_DIR=str(base / "state2")):
        jdb.main(["backup", "--source", str(src), "--dest", str(refusals)])
    check("a run refused because the destination is inside the live folder writes "
          "NO note there", not refusals.exists(),
          str(sorted(p.name for p in src.iterdir())))
    check("...and the record of it is written where it can still be found",
          (base / "state2" / "last-run.txt").is_file()
          and "FAILED" in (base / "state2" / "last-run.txt").read_text(encoding="utf-8"),
          (base / "state2" / "last-run.txt").read_text(encoding="utf-8")
          if (base / "state2" / "last-run.txt").is_file() else "ABSENT")


def t_the_data_folder_follows_the_same_setting_jarvis_uses():
    print("\n--- t_the_data_folder_follows_the_same_setting_jarvis_uses ---")
    # "Nothing set" has to be MADE true, not assumed: backend/run_suites.py sets
    # OPENJARVIS_CONFIG_DIR to its own state folder for every suite it runs, so
    # a check that read the environment as it found it passed here on the
    # owner's PC and failed in CI - measured, 67 passed / 1 failed in job
    # 115712066771. Both names are cleared, and put back afterwards.
    saved = {name: os.environ.pop(name)
             for name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR")
             if name in os.environ}
    try:
        check("with neither variable set it is ~/.openjarvis, which is where his "
              "data really is", jdb.default_source() == Path.home() / ".openjarvis",
              str(jdb.default_source()))
    finally:
        os.environ.update(saved)

    for name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        os_environ_set(name, r"C:\some\other\place")
        try:
            check(f"{name} is honoured, as jarvis_framework.py already honours it",
                  jdb.default_source() == Path(r"C:\some\other\place"),
                  str(jdb.default_source()))
        finally:
            os_environ_unset(name)
    check("and with both cleared again it is back to ~/.openjarvis",
          jdb.default_source() == Path.home() / ".openjarvis",
          str(jdb.default_source()))


def t_a_passphrase_without_seal_refuses_rather_than_ignoring_it():
    print("\n--- t_a_passphrase_without_seal_refuses_rather_than_ignoring_it ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-noseal-", dir=ROOT_TMP))
    src = build_source(base)
    dest = base / "snapshots"
    dest.mkdir()
    os_environ_set("JARVIS_TEST_PHRASE", "phrase")
    try:
        code = jdb.main(["backup", "--source", str(src), "--dest", str(dest),
                         "--passphrase-env", "JARVIS_TEST_PHRASE"])
        check("a passphrase given without --seal stops, instead of quietly writing "
              "the data out readable",
              code == 2 and jdb.list_snapshots(dest) == []
              and not [p.name for p in dest.iterdir() if p.is_dir()],
              f"exit {code}, dest holds {[p.name for p in dest.iterdir()]}")
    finally:
        os_environ_unset("JARVIS_TEST_PHRASE")


def t_the_weekly_task_has_no_window_and_needs_no_administrator():
    print("\n--- t_the_weekly_task_has_no_window_and_needs_no_administrator ---")
    import os as _os
    exe = str(Path(_os.environ.get("SYSTEMROOT", "C:/Windows")) / "pythonw.exe")
    script = r"C:\somewhere with a space\jarvis_data_backup.py"
    text = jdb.task_script(exe, script)
    check("the task is named in plain words",
          jdb.TASK_NAME == "Jarvis Personal Data Backup", jdb.TASK_NAME)
    check("it is registered weekly", "-Weekly" in text and jdb.TASK_DAY in text, text)
    check("at a fixed time, so Windows can show a next run time",
          jdb.TASK_AT in text, text)
    check("the windowless interpreter runs it - no window ever flashes",
          f"-Execute '{exe}'" in text and "pythonw.exe" in exe, text)
    check("the script's path is quoted, because his paths have spaces in them",
          f"'{chr(34)}{script}{chr(34)}'" in text, text)
    check("StartWhenAvailable is set, so a run missed while the PC was asleep "
          "happens late rather than never", "-StartWhenAvailable" in text, text)
    check("no -RunLevel Highest: it does not ask for administrator",
          "-RunLevel" not in text, text)
    check("no -User and no -Password: it runs as this user and stores no password",
          "-User" not in text and "-Password" not in text, text)
    check("-Force is there, so re-registering replaces the old task",
          "-Force" in text, text)
    check("pythonw_for picks the windowless interpreter when it is beside this one",
          jdb.pythonw_for(exe).endswith(("pythonw.exe", "pyw.exe", "python.exe")),
          jdb.pythonw_for(exe))
    check("registering is refused in plain words where there is no Task Scheduler",
          _os.name == "nt" or
          isinstance(_raised(lambda: jdb.register_task("x")), jdb.Refused))


def _raised(fn):
    """Run it and hand back the exception, so a check can look at it."""
    try:
        fn()
    except Exception as exc:      # noqa: BLE001 - the point is to inspect it
        return exc
    return None


def os_environ_set(name, value):
    import os
    os.environ[name] = value


def os_environ_unset(name):
    import os
    os.environ.pop(name, None)


class isolated_env:
    """Set environment variables for one check, and put every one of them back
    afterwards whatever it was.

    This matters more than it looks: `run_suites.py` sets `OPENJARVIS_CONFIG_DIR`
    AND `JARVIS_CONFIG_DIR` at a private folder before this file starts, so a
    check that unsets one of them and does not restore it changes the
    environment every check after it runs in - which is exactly how the
    "with nothing set it is ~/.openjarvis" check above came to fail under the
    runner while passing when this file was run on its own."""

    def __init__(self, **values):
        self.values = values
        self.kept = {}

    def __enter__(self):
        import os
        for name, value in self.values.items():
            self.kept[name] = os.environ.get(name)
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        return self

    def __exit__(self, *exc):
        import os
        for name, value in self.kept.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        return False


class default_folder:
    """Point the tool's built-in default folder at a temp folder for one check,
    so a test never reads or writes the real `~/jarvis-data-snapshots`."""

    def __init__(self, path):
        self.path = Path(path)
        self.real = None

    def __enter__(self):
        self.real = jdb.DEFAULT_DEST
        jdb.DEFAULT_DEST = self.path
        return self.path

    def __exit__(self, *exc):
        jdb.DEFAULT_DEST = self.real
        return False


# ---------------------------------------------------------------------------
#   10. ONE destination, chosen by the owner - backup.json's `folder` key
# ---------------------------------------------------------------------------


def t_the_destination_is_the_folder_the_owner_chose_in_the_app():
    """The `folder` key of `backup.json` - the file the app's own `.jbak`
    backups keep their destination in, and the window in Settings, Backups sets
    through `/api/backup/folder` - is what this tool reads, at run time."""
    print("\n--- t_the_destination_is_the_folder_the_owner_chose_in_the_app ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-choice-", dir=ROOT_TMP))
    src = build_source(base)
    config, chosen, previous = base / "config", base / "chosen by the owner", base / "default"
    for folder in (config, chosen, previous):
        folder.mkdir()
    (config / jdb.SETTINGS_NAME).write_text(json.dumps({jdb.SETTINGS_KEY: str(chosen)}),
                                            encoding="utf-8")
    # A snapshot from before the folder changed, in the built-in default.
    old = Path(jdb.take_snapshot(src, previous, now=1_700_004_000)["path"])

    with default_folder(previous), isolated_env(
            OPENJARVIS_CONFIG_DIR=str(config), JARVIS_CONFIG_DIR=None,
            JARVIS_DATA_BACKUP_STATE_DIR=str(base / "state")):
        check("the destination is read from the app's own settings file, not invented "
              "as a second setting here",
              jdb.settings_file() == config / jdb.SETTINGS_NAME
              and jdb.SETTINGS_KEY == "folder" and jdb.chosen_destination() == chosen,
              f"{jdb.settings_file()} -> {jdb.chosen_destination()}")
        where, note = jdb.destination(None, src)
        check("so the run's destination is the folder he chose, not the built-in default",
              where == chosen and note == "", f"{where} ({note!r})")

        code = jdb.main(["backup", "--source", str(src)])
        made = [r["name"] for r in jdb.list_snapshots(chosen) if not r["incomplete"]]
        check("the command line wrote the snapshot into the chosen folder",
              code == 0 and len(made) == 1, f"exit {code}, {made}")
        check("and nothing new was written into the built-in default folder",
              [r["name"] for r in jdb.list_snapshots(previous)] == [old.name],
              str([r["name"] for r in jdb.list_snapshots(previous)]))

        check("older snapshots left in the old folder are reported, not ignored",
              [r["count"] for r in jdb.older_snapshots_elsewhere(chosen)] == [1],
              str(jdb.older_snapshots_elsewhere(chosen)))
        check("...and the old folder still holds its snapshot, untouched",
              old.is_dir() and old.parent == previous)
        check("a hand-run --dest still overrides the setting for one run",
              jdb.destination(str(base / "elsewhere"), src)[0] == base / "elsewhere")

    # A PC where he has never chosen: nothing in backup.json, so the default.
    empty = base / "config with nothing in it"
    empty.mkdir()
    with default_folder(previous), isolated_env(OPENJARVIS_CONFIG_DIR=str(empty),
                                                JARVIS_CONFIG_DIR=None):
        check("with nothing chosen at all the built-in default is still used",
              jdb.destination(None, src)[0] == previous)


def t_the_weekly_tasks_own_command_line_follows_the_setting():
    """The task runs the script with NO arguments at all. That is the shape
    that has to follow the folder, not a hand-run that happens to pass one."""
    print("\n--- t_the_weekly_tasks_own_command_line_follows_the_setting ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-task-", dir=ROOT_TMP))
    live = build_source(base)                     # stands in for ~/.openjarvis
    chosen = base / "where he sends them"
    chosen.mkdir()
    settings = live / jdb.SETTINGS_NAME
    settings.write_text(json.dumps({jdb.SETTINGS_KEY: str(chosen)}, indent=2), encoding="utf-8")
    before = settings.read_text(encoding="utf-8")

    with default_folder(base / "unused default"), isolated_env(
            OPENJARVIS_CONFIG_DIR=str(live), JARVIS_CONFIG_DIR=None,
            JARVIS_DATA_BACKUP_STATE_DIR=str(base / "state")):
        code = jdb.main([])                       # the task's own command line
        made = [r for r in jdb.list_snapshots(chosen) if not r["incomplete"]]
        check("the weekly run, with no arguments, lands in the folder backup.json names",
              code == 0 and len(made) == 1, f"exit {code}, {[r['name'] for r in made]}")
        check("it read that folder from backup.json rather than the default",
              not list(jdb.list_snapshots(base / "unused default")))
        check("the setting file is left exactly as the app wrote it",
              settings.read_text(encoding="utf-8") == before)
        check("and the run's own record says where it landed",
              (chosen / "last-run.txt").is_file()
              and str(chosen) in (chosen / "last-run.txt").read_text(encoding="utf-8"),
              (chosen / "last-run.txt").read_text(encoding="utf-8")
              if (chosen / "last-run.txt").is_file() else "no last-run.txt")


def t_a_folder_inside_the_live_data_folder_is_refused_and_nothing_is_written():
    print("\n--- t_a_folder_inside_the_live_data_folder_is_refused_and_nothing_is_written ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-inside-", dir=ROOT_TMP))
    live = build_source(base)
    config = base / "config"
    config.mkdir()
    state = base / "state"
    (config / jdb.SETTINGS_NAME).write_text(json.dumps({jdb.SETTINGS_KEY: str(live)}),
                                            encoding="utf-8")

    with default_folder(base / "unused default"), isolated_env(
            OPENJARVIS_CONFIG_DIR=str(config), JARVIS_CONFIG_DIR=None,
            JARVIS_DATA_BACKUP_STATE_DIR=str(state)):
        before = sorted(p.name for p in live.iterdir())
        why = _raised(lambda: jdb.destination(None, live))
        check("a chosen folder inside the live data folder is refused",
              isinstance(why, jdb.Refused), str(why))
        check("...in plain words, naming the folder and the reason",
              isinstance(why, jdb.Refused) and str(live) in str(why)
              and "inside" in str(why), str(why))

        code = jdb.main(["backup", "--source", str(live)])
        after = sorted(p.name for p in live.iterdir())
        check("the run stops instead of backing up into the thing being backed up",
              code == 2, str(code))
        check("nothing at all was created in the live data folder",
              after == before, f"{before} -> {after}")
        check("not even the failure note - the guard is not routed round by the "
              "note about the failure", not (live / "last-run.txt").exists())
        note = state / "last-run.txt"
        check("the failure is written where it can still be seen, saying FAILED",
              note.is_file() and "FAILED" in note.read_text(encoding="utf-8"),
              note.read_text(encoding="utf-8") if note.is_file() else "no note")


def t_a_chosen_folder_that_is_gone_fails_loudly():
    print("\n--- t_a_chosen_folder_that_is_gone_fails_loudly ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-gone-", dir=ROOT_TMP))
    src = build_source(base)
    config, chosen, state = base / "config", base / "chosen", base / "state"
    for folder in (config, chosen):
        folder.mkdir()
    (config / jdb.SETTINGS_NAME).write_text(json.dumps({jdb.SETTINGS_KEY: str(chosen)}),
                                            encoding="utf-8")

    with default_folder(base / "unused default"), isolated_env(
            OPENJARVIS_CONFIG_DIR=str(config), JARVIS_CONFIG_DIR=None,
            JARVIS_DATA_BACKUP_STATE_DIR=str(state)):
        jdb.main(["backup", "--source", str(src)])
        good = (chosen / "last-run.txt").read_text(encoding="utf-8")
        check("a good run leaves an OK record in the folder", good.startswith("20")
              and "OK" in good, good)

        # The drive was unplugged, or the folder was deleted.
        shutil.rmtree(chosen)
        code = jdb.main(["backup", "--source", str(src)])
        check("the next run stops instead of quietly re-making the folder",
              code == 2, str(code))
        check("...and does not re-create a folder he did not choose this time",
              not chosen.exists())
        note = state / "last-run.txt"
        check("the failure is written where it can still be seen, saying FAILED",
              note.is_file() and "FAILED" in note.read_text(encoding="utf-8"),
              note.read_text(encoding="utf-8") if note.is_file() else "no note")
        check("status says the same rather than reporting an empty backup folder",
              jdb.main(["status"]) == 2)


def t_an_unwritable_folder_fails_loudly():
    print("\n--- t_an_unwritable_folder_fails_loudly ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-nowrite-", dir=ROOT_TMP))
    src = build_source(base)
    config, chosen, state = base / "config", base / "chosen", base / "state"
    for folder in (config, chosen):
        folder.mkdir()
    (config / jdb.SETTINGS_NAME).write_text(json.dumps({jdb.SETTINGS_KEY: str(chosen)}),
                                            encoding="utf-8")
    a_file = base / "not a folder"
    a_file.write_text("x", encoding="utf-8")

    check("a place that is not a folder at all cannot be written into",
          jdb.can_write(a_file) is False)
    real = jdb.can_write
    jdb.can_write = lambda folder: False          # stand in for a full or locked disk
    try:
        with default_folder(base / "unused default"), isolated_env(
                OPENJARVIS_CONFIG_DIR=str(config), JARVIS_CONFIG_DIR=None,
                JARVIS_DATA_BACKUP_STATE_DIR=str(state)):
            why = _raised(lambda: jdb.destination(None, src))
            check("a folder Jarvis cannot write into is refused, naming the folder",
                  isinstance(why, jdb.Refused) and str(chosen) in str(why)
                  and "cannot write" in str(why), str(why))
            code = jdb.main(["backup", "--source", str(src)])
            check("the run stops rather than reporting a backup it did not make",
                  code == 2, str(code))
            check("and no snapshot was left in the folder",
                  list(jdb.list_snapshots(chosen)) == [],
                  str(jdb.list_snapshots(chosen)))
            note = state / "last-run.txt"
            check("the failure is written where it can still be seen, saying FAILED",
                  note.is_file() and "FAILED" in note.read_text(encoding="utf-8"),
                  note.read_text(encoding="utf-8") if note.is_file() else "no note")
    finally:
        jdb.can_write = real
    skip("a directory whose Windows permissions really refuse a write",
         "making one needs icacls and this account's own name; the refusal above is "
         "driven through the same door the real probe goes through (can_write), and "
         "the probe itself is checked on a place that genuinely refuses one")


def t_the_other_drive_is_a_note_and_the_program_folder_is_a_refusal():
    print("\n--- t_the_other_drive_is_a_note_and_the_program_folder_is_a_refusal ---")
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-drive-", dir=ROOT_TMP))
    src = build_source(base)
    note = jdb.drive_note(Path("D:/backups"))
    if os.name == "nt":
        check("a folder on another drive comes back as a note naming that drive",
              "D:" in note and "Windows" in note, note)
        check("a folder on the drive Windows is on has no note",
              jdb.drive_note(Path(os.environ.get("SystemDrive", "C:") + "/backups")) == "")
    else:
        skip("the other-drive note", "it is a Windows question; os.name is not nt")

    program = jdb.program_folder()
    refused = _raised(lambda: jdb.take_snapshot(src, program / "snapshots"))
    check("a destination inside this tool's own program folder is refused",
          isinstance(refused, jdb.Refused), str(refused))
    check("...in plain words, naming that folder",
          isinstance(refused, jdb.Refused) and str(program) in str(refused), str(refused))
    check("...and nothing was created there", not (program / "snapshots").exists())

    root = Path(Path.home().anchor)
    why = _raised(lambda: jdb.check_chosen_folder(root, src))
    check("the top of a whole drive is refused as a backup folder",
          isinstance(why, jdb.Refused) and "top of a whole drive" in str(why), str(why))

    # The note is RECORDED, not just printed: an unattended run has no console,
    # so a printed warning about the drive would never be read. (The note is
    # passed in rather than produced by a real second drive - this PC has one.)
    dest = base / "snapshots"
    jdb.take_snapshot(src, dest, now=1_700_004_500,
                      dest_note="this folder is on drive D:, not the drive Windows is on (C:)")
    text = (dest / "last-run.txt").read_text(encoding="utf-8")
    check("a note about the destination is written into last-run.txt, where an "
          "unattended run can be read later",
          "NOTE:" in text and "drive D:" in text, text)


# ---------------------------------------------------------------------------


def main() -> int:
    global ROOT_TMP
    ROOT_TMP = tempfile.mkdtemp(prefix="jarvis-databak-")
    try:
        for fn in (t_no_network_call_anywhere_in_the_tool,
                   t_a_database_living_in_its_wal_is_snapshotted_whole,
                   t_a_broken_snapshot_is_caught_and_not_counted,
                   t_a_failed_snapshot_is_kept_but_never_counted,
                   t_it_never_writes_into_the_folder_it_reads,
                   t_a_restore_really_puts_the_data_back,
                   t_keeping_the_newest_few_touches_nothing_else,
                   t_a_sealed_snapshot_round_trips,
                   t_sealing_without_the_library_writes_nothing,
                   t_two_runs_inside_one_second_do_not_collide,
                   t_a_refused_run_still_leaves_a_trace,
                   t_the_data_folder_follows_the_same_setting_jarvis_uses,
                   t_a_passphrase_without_seal_refuses_rather_than_ignoring_it,
                   t_the_weekly_task_has_no_window_and_needs_no_administrator,
                   t_the_destination_is_the_folder_the_owner_chose_in_the_app,
                   t_the_weekly_tasks_own_command_line_follows_the_setting,
                   t_a_folder_inside_the_live_data_folder_is_refused_and_nothing_is_written,
                   t_a_chosen_folder_that_is_gone_fails_loudly,
                   t_an_unwritable_folder_fails_loudly,
                   t_the_other_drive_is_a_note_and_the_program_folder_is_a_refusal):
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    finally:
        shutil.rmtree(ROOT_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
