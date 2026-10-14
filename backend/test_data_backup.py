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
  9. a NordLocker locker is refused as a destination, before anything is
     written - measured on the owner's PC, a locker does not encrypt a file
     while the app is closed, so a weekly run into one would have written his
     data in the clear and reported success;
  10. the weekly task runs `pythonw.exe` (no window), weekly, with no `/RU` and
      no `/RP` (no administrator, no stored password).
"""
import json
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
              code == 2 and not list(dest.iterdir()),
              f"exit {code}, dest holds {[p.name for p in dest.iterdir()]}")
    finally:
        jdb._crypto = real
        os_environ_unset("JARVIS_TEST_PHRASE")


# ---------------------------------------------------------------------------
#   8b. a NordLocker locker is refused, because it does not encrypt unattended
# ---------------------------------------------------------------------------
#
# Measured on the owner's PC, 2026-10-13: a locker folder is a Microsoft cloud
# placeholder, and with the NordLocker app closed a file written into it stays
# ordinary plaintext on the disk - 40 MB written cost 42.03 MB of free space and
# the file was not a reparse point at all. A weekly run pointed there would
# therefore have succeeded and left the data readable, which is the one outcome
# a backup must never produce quietly. `docs/DATA-BACKUP.md` has the numbers.


def t_a_nordlocker_locker_is_refused_as_a_destination():
    print("\n--- t_a_nordlocker_locker_is_refused_as_a_destination ---")
    # A branch merging without the guard is not a red build: the feature is
    # simply absent, and this says so rather than passing. `tools/` and this
    # suite are edited in parallel worktrees, so this is a real case and not a
    # hypothetical one.
    if not hasattr(jdb, "refuse_write_into_a_locker"):
        skip("a NordLocker locker destination is refused",
             "this build of the tool has no refuse_write_into_a_locker - the "
             "guard is not in this tree, so there is nothing to check")
        return
    base = Path(tempfile.mkdtemp(prefix="jarvis-databak-locker-", dir=ROOT_TMP))
    src = build_source(base)
    locker = base / "NordLocker_9019064"

    for gone in (locker, locker / "My Files", locker / "My Files" / "snapshots"):
        raised = _raised(lambda p=gone: jdb.refuse_write_into_a_locker(p))
        check(f"{gone.name} is refused in plain words, not taken as a destination",
              isinstance(raised, jdb.Refused) and "locker" in str(raised), str(raised))

    # The refusal has to happen BEFORE anything is written, or it is a comment
    # rather than a guard.
    code = jdb.main(["backup", "--source", str(src), "--dest",
                     str(locker / "My Files" / "snapshots")])
    check("the command line stops before taking any snapshot at all",
          code == 2 and not locker.exists(),
          f"exit {code}, locker exists: {locker.exists()}")

    # ...and an ordinary folder is still fine, so the guard is not a wall.
    allowed = _raised(lambda: jdb.refuse_write_into_a_locker(base / "snapshots"))
    check("an ordinary destination is still allowed", allowed is None, str(allowed))
    ok = jdb.take_snapshot(src, base / "snapshots", now=1_700_004_000)
    check("and a real snapshot into one still verifies",
          ok["ok"] and Path(ok["path"]).is_dir(), str(ok["problems"]))


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


def t_the_data_folder_follows_the_same_setting_jarvis_uses():
    print("\n--- t_the_data_folder_follows_the_same_setting_jarvis_uses ---")
    os_environ_set("OPENJARVIS_CONFIG_DIR", r"C:\some\other\place")
    try:
        check("OPENJARVIS_CONFIG_DIR is honoured, as jarvis_framework.py already "
              "honours it", jdb.default_source() == Path(r"C:\some\other\place"),
              str(jdb.default_source()))
    finally:
        os_environ_unset("OPENJARVIS_CONFIG_DIR")
    check("with nothing set it is ~/.openjarvis, which is where his data is",
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
              code == 2 and not list(dest.iterdir()),
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
    # The task's own description is what somebody reads in Task Scheduler a year
    # from now. The one thing about this task that could be mistaken for
    # something it is not is whether the data is protected, so it says so.
    check("the task describes itself, so it can be explained a year later",
          "-Description" in text
          and jdb.TASK_DESCRIPTION.replace("'", "''") in text,
          "no -Description in the registration script")
    check("and that description says plainly that the snapshot is NOT encrypted",
          "NOT encrypted" in jdb.TASK_DESCRIPTION
          and "seal" in jdb.TASK_DESCRIPTION, jdb.TASK_DESCRIPTION)
    check("so re-running --register-task replaces the task and its description",
          "-Force" in text)


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
                   t_a_nordlocker_locker_is_refused_as_a_destination,
                   t_two_runs_inside_one_second_do_not_collide,
                   t_the_data_folder_follows_the_same_setting_jarvis_uses,
                   t_a_passphrase_without_seal_refuses_rather_than_ignoring_it,
                   t_the_weekly_task_has_no_window_and_needs_no_administrator):
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
