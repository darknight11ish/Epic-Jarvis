#!/usr/bin/env python3
"""jarvis_data_backup.py - one consistent, verified, local snapshot of the
owner's personal Jarvis data, and a weekly timer that takes it.

WHY THIS EXISTS (measured on the owner's PC, 2026-10-13)

His personal data lives in `C:\\Users\\pcadmin\\.openjarvis\\`: 19 SQLite
databases plus a settings file and a few small folders - **1.26 MB of
irreplaceable data** beside 1.14 GB of re-downloadable `voice-models`. Until
now the only copy of several of those databases was the one Jarvis itself
keeps open, and the only attempt at a copy was a plain `Copy-Item` of the
folder (`C:\\Users\\pcadmin\\jarvis-data-backups\\jarvis-data-2026-10-13-223631`).
A plain copy is not a snapshot, and this was measured rather than assumed -
comparing that copy with a real SQLite snapshot of the same minute:

  * it holds 16 of the 19 databases: `digest.db`, `telemetry.db` and
    `traces.db` are **absent**;
  * its `agents.db` is an **empty shell - 0 tables where the live database
    reads 6** - because `agents.db` is 4,096 bytes while `agents.db-wal` is
    115,392 bytes: the database IS the write-ahead log, and a plain copy takes
    the empty file and leaves the log behind;
  * `traces.db` (9 rows) and `telemetry.db` (1 row) are the same shape, with
    78,312-byte and 28,872-byte logs;
  * **16 tables and 10 rows of real data were lost**, and the copy cannot be
    verified at all - nothing checks that what it wrote opens.

The rest of the brief's picture was confirmed too: Windows' File History has
no backup target, the `Backup` scheduled tasks are empty Windows placeholders
(`\\Microsoft\\Windows\\AppListBackup\\Backup`, `\\Microsoft\\Windows\\CloudRestore\\Backup`),
and no task has ever copied this folder.

WHAT ALREADY EXISTS, AND WHY THIS IS NOT A SECOND COPY OF IT

`backend/jarvis_backup.py` (the live copy is byte-identical to this
repository's base, sha256 4DA65FBC...) already takes a consistent snapshot with
SQLite's online backup API and seals it with Argon2id + AES-256-GCM. The owner
has used it: four real `.jbak` files sit in
`C:\\Users\\pcadmin\\Documents\\Jarvis Backups`, newest 2026-10-10 09:49. That
is not nothing, and this tool does not replace it.

It cannot, however, be put on a timer, and that is the whole reason this tool
exists. `generate_code()` makes a **fresh recovery code for every backup**,
returns it once in the response, and never writes it anywhere - its own
docstring says "NEVER written to a file, a log, or the audit trail". An
unattended run would therefore produce a locked file **nobody could ever
open**, which is worse than no backup because it looks like one. (Three of the
owner's four `.jbak` files were made within twenty seconds of each other on
2026-10-10 and nothing has run since, which is what "there is no timer" looks
like from the outside.)

It also does not cover everything: its `SOURCE_DBS` names 12 databases, and
`knowledge.db`, `agents.db`, `audit.db`, `sync_state.db`, `telemetry.db`,
`traces.db` and `digest.db` are not among them; `approvals.db` (51 rows) is
excluded on purpose; its `*.json` glob does not match `speed.jsonl`; and its
only `.toml` is `jarvis-framework.toml`, which lives in the program folder - so
`~/.openjarvis/config.toml`, the HUD's own settings file (`jarvis_hud.py:89`,
10,923 characters), is in no backup of any kind.

So the division of labour is deliberate and worth saying plainly:

  * `jarvis_backup.py` - the owner's encrypted, code-plus-data, shown-once-code
    archive, made when he presses the button, kept 5.
  * this tool - an **unattended, verified, local** snapshot of the personal
    data alone, on a weekly timer, kept 4. No code (rule 5 of the brief: this
    is about personal data, not the program), no recovery code to lose, and
    every file proved to open before the snapshot counts as one.

HOW A SNAPSHOT IS TAKEN, AND WHY THAT IS SAFE WHILE JARVIS RUNS

Never `Copy-Item`. SQLite is asked to copy itself:

  * each database is opened **read-only** (`file:...?mode=ro`) with a 30-second
    `busy_timeout`, and **`VACUUM INTO`** writes a fresh, compacted,
    single-file copy of it. SQLite reads one consistent view of the database
    and folds the write-ahead log into the result, so a database mid-write
    still produces a file that opens. This was measured on his PC with Jarvis
    running: **all 19 databases** snapshotted, `PRAGMA integrity_check` "ok"
    for every one, row counts identical to the live source;
  * if `VACUUM INTO` refuses for any reason (an old SQLite, a lock that will
    not clear), the same connection falls back to the **online backup API**
    (`Connection.backup`) - the equivalent primitive, and the one
    `jarvis_backup.py` uses. Which method produced each database is written
    into the manifest, so the claim is checkable rather than asserted;
  * `-wal`, `-shm` and `-journal` companions are **never copied**. They are
    already inside the snapshot, and a stale `-wal` landing beside a fresh
    `-db` is a way to corrupt a restore, not a way to complete one;
  * the non-database files are copied plainly (`config.toml`, `speed.jsonl`,
    every other top-level file, and the small data folders - `voice/` holds his
    voice-print enrolments and is as irreplaceable as anything here).

NOTHING IS TRUSTED. Every database in the snapshot is then opened again and
checked: `PRAGMA integrity_check` must say `ok`, its set of tables must be the
same set the live database had, and it must not hold fewer rows than the live
one did. A snapshot that fails any of that is retried once against a fresh read
of the live database and, if it still fails, is kept as
`<name>-INCOMPLETE` for inspection, never counted as a backup, and reported as
a failure. This is the check that a plain copy cannot pass and that this
repository's own habit - "BLOCKED is never a pass" - demands.

WHAT IS KEPT, AND FOR HOW LONG

The newest **4** good snapshots, `KEEP = 4`. Weekly, so that is about a month:
enough that a bad write noticed a fortnight later can still be walked back,
few enough that it cannot pile up the way the code backups did (23 of them,
pruned by hand on 2026-10-13). Making a new one deletes the ones past that.
Nothing but this tool's own `jarvis-snap-*` entries is ever deleted - the
owner's `.jbak` files, and the older plain copy, are not this tool's business.

WHERE IT LANDS, AND WHY NOT IN THE FOLDER HE ALREADY HAS

Default destination: `C:\\Users\\pcadmin\\jarvis-data-snapshots`.

**Deliberately not** `C:\\Users\\pcadmin\\Documents\\Jarvis Backups`, the
folder the app writes `.jbak` files into. That folder is one the app is
allowed to point at a cloud-synced place - its own docstring says a NordLocker
or OneDrive folder is fine because rule 1 is bent "for that one locked file
only", the file being encrypted before it is written. These snapshots are
plain files. OneDrive is installed on this PC, so putting unencrypted memory
facts in a folder that may become a synced one would bend rule 1 without the
owner ever deciding to.

RULE 1 AND THE ONE THING THIS TOOL WILL NOT DO

**This tool contains no network call at all** - no `socket`, no `urllib`, no
`http`, no `requests`, and no import of any of them. It reads
`~/.openjarvis`, writes to the destination folder, and that is the whole of it.
Nothing is uploaded, and there is nothing in the file that could upload
anything: the claim is machine-checked by `backend/test_data_backup.py`, which
reads this module's own source and refuses the list of network modules by name.
A backup on a timer is exactly the kind of thing that quietly grows a "send it
to the cloud" option later, so the door is nailed shut here and the test is the
nail.

**It never writes into `~/.openjarvis`.** The source is opened read-only, and
both the destination and any restore target are refused if they resolve inside
the source folder (`refuse_write_inside`), so a typo cannot turn a backup into
a write over the live data. Restoring is a separate, explicit act with its own
target folder - and the target is never the live folder.

ENCRYPTION - THE HALF THAT IS SAFE TO DECIDE, DECIDED

The decision about encrypting the **live** files is the owner's and has not
been made, so this tool does not touch, encrypt or move them. The archive
itself is a supported, documented option:

  * `--seal` with a passphrase (`--passphrase-env VAR` or
    `--passphrase-file FILE`) writes **one** `jarvis-snap-<stamp>.jba` file
    instead of a folder: the zip of the snapshot, sealed AES-256-GCM under a
    key stretched from the passphrase by Argon2id. The construction is
    deliberately the same as `jarvis_backup.py`'s `JBAK1` - one format for this
    project to reason about rather than two - with a different magic (`JDBA1`)
    so the two can never be mistaken for each other;
  * it needs only `cryptography`, which is **already installed** on his PC
    (50.0.2, and its `Argon2id` imports) and is already a pinned dependency for
    chat history. Nothing is downloaded. Checked rather than assumed: there is
    no 7-Zip, no GnuPG, no OpenSSL, no `age` and no WinRAR on that machine,
    NordLocker is installed but has no command line (GUI only), and
    `Compress-Archive` cannot password a file at all - so `cryptography` is the
    only safe option already present, and it is the one used;
  * if `cryptography` is missing, `--seal` **refuses in plain words** and writes
    nothing. It never quietly writes the data unsealed instead;
  * the default is unsealed, on purpose: the weekly timer has no passphrase to
    use, because the only place an unattended run could keep one is on the same
    disk as the backup - which is the trade `jarvis_backup.py` deliberately
    refuses to make. Sealing is for the runs the owner starts by hand, and for
    a folder he later decides to sync.

THE ONE LINE, AND THE TIMER

Back up now, one line, pasted into a terminal:

    python "$env:LOCALAPPDATA\\JarvisDataBackup\\jarvis_data_backup.py"

It prints where the snapshot landed in plain words. Set it up once with:

    python "<a checkout>\\tools\\jarvis_data_backup.py" --install --register-task

`--install` copies this file to `%LOCALAPPDATA%\\JarvisDataBackup\\` and
`--register-task` registers the Windows task **`Jarvis Personal Data Backup`**
- weekly, Sunday 03:00, per-user, no administrator, running `pythonw.exe` so
**no window ever flashes on his screen**, and with `StartWhenAvailable` so a run
missed because the PC was asleep happens at the next opportunity instead of
never. It runs while he is signed in: that is what "per-user and no
administrator" costs, and it is the same shape as the two `Jarvis Ollama` tasks
already on that PC (measured: both are `InteractiveToken` with
`StartWhenAvailable` true), not a new invention. That is why both the line above
and the task point at the installed copy rather than at a checkout: this repository
is worked in parallel `git worktree`s, the owner's own checkout sits on
whatever branch is current, and a backup that stops happening because a branch
changed is not a backup. The installed copy is a deployment artifact, not a
second source: every manifest records the tool's own version and sha256, so a
snapshot says which build made it.

Restore is a real, testable path - to a spare folder, never over the live data:

    python "$env:LOCALAPPDATA\\JarvisDataBackup\\jarvis_data_backup.py" restore --to-temp

    python tools/jarvis_data_backup.py                      # back up now
    python tools/jarvis_data_backup.py status               # what exists, next run
    python tools/jarvis_data_backup.py verify <snapshot>    # is this one good?
    python tools/jarvis_data_backup.py restore <snapshot> --to <folder>
    python tools/jarvis_data_backup.py --install --register-task

Standard library only, plus `cryptography` when `--seal` is asked for.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

TOOL = "jarvis_data_backup.py"
#: Bumped by hand when the on-disk shape of a snapshot changes. Every manifest
#: carries it, so a snapshot always says which build made it.
VERSION = "1"

DEFAULT_DEST = Path(os.path.expanduser("~")) / "jarvis-data-snapshots"


def default_source() -> Path:
    """Where Jarvis keeps its data: `OPENJARVIS_CONFIG_DIR`, then
    `JARVIS_CONFIG_DIR`, then `~/.openjarvis`.

    The same two variables, in the same order, that `jarvis_backup.py` and
    `jarvis_framework.py` already use - so this backs up the folder Jarvis is
    actually using rather than a guess that happens to be right today. Under
    the scheduled task neither variable is set and it is `~/.openjarvis`."""
    for name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        value = os.environ.get(name)
        if value:
            return Path(os.path.expanduser(value))
    return Path(os.path.expanduser("~")) / ".openjarvis"

SNAP_PREFIX = "jarvis-snap-"
INCOMPLETE = "-INCOMPLETE"
MANIFEST = "manifest.json"
README = "README.txt"
SEAL_SUFFIX = ".jba"
#: `jarvis-snap-YYYYmmdd-HHMMSS`, an optional `-N` for two snapshots made in the
#: same second, an optional `-INCOMPLETE`, and an optional `.jba` when sealed.
SNAP_RE = re.compile(r"^jarvis-snap-(\d{8}-\d{6})(?:-(\d+))?(-INCOMPLETE)?(\.jba)?$")
STAMP_FMT = "%Y%m%d-%H%M%S"

#: The newest snapshots kept. Weekly, so about a month - see the docstring.
KEEP = 4
#: A crashed run's leftovers, and failed snapshots, are cleared after this long:
#: long enough to look at a failure, short enough not to pile up.
STALE_DAYS = 7
#: A folder bigger than this is not copied; it is named in the manifest instead
#: so nothing is dropped in silence. No folder here is near it today (the
#: largest kept one is voice/ at 0.2 MB).
MAX_DIR_BYTES = 256 * 1024 * 1024

#: Folders deliberately not copied, with the reason that goes into the manifest.
#: `voice-models` is 1.14 GB of downloadable engine files, `models` is a 64 MB
#: Hugging Face cache for the embedding model, and `logs` is 13 MB of daily
#: diagnostics - one day of it alone is 10.8 MB. None is the owner's data;
#: `audit.db` is where the audit trail proper lives and it IS backed up.
EXCLUDED_DIRS = {
    "voice-models": "downloaded voice engines, re-downloadable (1.14 GB)",
    "models": "a downloaded embedding-model cache, re-downloadable (64 MB)",
    "logs": "daily diagnostic logs, not data (13 MB)",
    "__pycache__": "compiled bytecode, rebuilt from source",
}

SEAL_MAGIC = b"JDBA1"
ARGON_LANES = 4
ARGON_MEMORY_KIB = 64 * 1024
ARGON_ITERATIONS = 3
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12
SEAL_HEADER = 1 + 4 + 4  # lanes, memory KiB, iterations (the rest is salt+nonce)

TASK_NAME = "Jarvis Personal Data Backup"
TASK_DAY = "SUN"
TASK_AT = "03:00"


class Refused(Exception):
    """This cannot go ahead; the message is plain words for the owner."""


# ---------------------------------------------------------------------------
#   Small helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """The file's sha256, read in 1 MiB blocks - a snapshot of these sizes is
    a fraction of a second, and nothing is ever held in memory whole."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _resolve(path) -> Path:
    """A real, comparable absolute path. `resolve()` alone would follow a
    symlink into the live folder and let a destination outside it pass a check
    that meant to stop it, so the resolved form is what every guard uses."""
    return Path(os.path.abspath(str(Path(path).expanduser())))


def is_inside(child, parent) -> bool:
    """Is `child` the same as `parent`, or inside it? Windows paths are
    case-insensitive, so the comparison is too."""
    c, p = _resolve(child), _resolve(parent)
    if c == p:
        return True
    try:
        c.relative_to(p)
        return True
    except ValueError:
        return False


def refuse_write_inside(target, source) -> Path:
    """`target` as a Path, or Refused when writing there would write into the
    live data. THE guard the brief asks for: this tool never writes into
    `~/.openjarvis`, and this is what makes that true rather than intended."""
    t = _resolve(target)
    if is_inside(t, source):
        raise Refused(
            f"{t} is inside {_resolve(source)} - the folder Jarvis is using right now. "
            f"Nothing was written there and nothing will be: choose a folder outside it, "
            f"such as {DEFAULT_DEST}")
    return t


def _connect_ro(path, timeout=30.0) -> sqlite3.Connection:
    """A read-only connection with a long busy timeout. Read-only means a bug
    here cannot write to the live database; the timeout is what makes a
    database another process is writing to settle instead of failing."""
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True,
                           timeout=timeout)
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    return conn


def read_shape(conn: sqlite3.Connection) -> dict:
    """{table: row count} for every real table, read through SQLite - which
    folds in the write-ahead log, so this is the LIVE shape and not the shape
    of the .db file on its own. A table whose count cannot be read is None
    (a virtual table, say), and None is compared as "cannot tell", never as 0.
    """
    shape: dict = {}
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]
    for name in names:
        try:
            shape[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        except sqlite3.DatabaseError:
            shape[name] = None
    return shape


def total_rows(shape: dict) -> int:
    return sum(v for v in shape.values() if isinstance(v, int))


# ---------------------------------------------------------------------------
#   The snapshot itself
# ---------------------------------------------------------------------------


def snapshot_db(src: Path, dest: Path, timeout: float = 30.0) -> dict:
    """One consistent copy of `src` at `dest`. Returns
    {"method", "source_shape", "shape", "integrity", "problems", "notes"}.

    `VACUUM INTO` first - SQLite's own "write me a fresh single-file copy",
    safe while Jarvis keeps writing, with the write-ahead log folded in. The
    online backup API is the fallback, for the case where VACUUM INTO refuses
    (it needs a moment of quiet and its own SQLite floor of 3.27).

    `notes` and `problems` are kept apart on purpose: falling back to the other
    method and succeeding anyway is a note, and a note must not mark a
    perfectly good snapshot incomplete.
    """
    out = {"method": "", "source_shape": {}, "shape": {}, "integrity": "",
           "problems": [], "notes": [], "bytes": 0, "sha256": ""}
    if dest.exists():
        dest.unlink()
    try:
        conn = _connect_ro(src, timeout)
    except sqlite3.DatabaseError as exc:
        out["problems"].append(f"the live database cannot be opened ({exc})")
        return out
    try:
        try:
            out["source_shape"] = read_shape(conn)
        except sqlite3.DatabaseError as exc:
            # One unreadable file must never abort the whole backup: it is
            # named, reported, and the rest of the databases are still taken.
            out["problems"].append(f"the live database cannot be read ({exc})")
            return out
        try:
            conn.execute("VACUUM INTO ?", (str(dest),))
            out["method"] = "vacuum_into"
        except sqlite3.DatabaseError as exc:
            out["notes"].append(f"VACUUM INTO refused ({exc}); used the online backup API")
            if dest.exists():
                dest.unlink()
            try:
                target = sqlite3.connect(str(dest))
                try:
                    conn.backup(target)
                finally:
                    target.close()
                out["method"] = "online_backup"
            except sqlite3.DatabaseError as exc2:
                out["problems"].append(f"the online backup API refused too ({exc2})")
                return out
    finally:
        conn.close()

    # Everything below is read back OUT of the snapshot, never trusted from
    # the copy above: an unwritten or half-written file is a file that does not
    # open, and this is where that is found.
    check = verify_db_file(dest, out["source_shape"])
    out["problems"].extend(check["problems"])
    out["shape"] = check["shape"]
    out["integrity"] = check["integrity"]
    if dest.is_file():
        out["bytes"] = dest.stat().st_size
        out["sha256"] = sha256_file(dest)
    return out


def verify_db_file(path: Path, expect_shape=None) -> dict:
    """Open `path` and check it is a working database. Returns
    {"shape", "integrity", "problems"}.

    Three things are demanded of it, and each is a real failure this project
    has already seen a copy commit:
      * it opens at all, and `PRAGMA integrity_check` says `ok`;
      * it has the same SET of tables the live database had - the empty-shell
        case, `agents.db` with 0 tables where the live one had 6, is caught
        here and nowhere else;
      * no table holds fewer rows than the live one did. `>=` and not `==`
        because Jarvis may write during the second this takes, and a snapshot
        that is NEWER than the reading is not a broken snapshot.
    """
    out = {"shape": {}, "integrity": "", "problems": []}
    try:
        conn = _connect_ro(path)
    except sqlite3.DatabaseError as exc:
        out["problems"].append(f"the snapshot cannot be opened at all ({exc})")
        return out
    try:
        try:
            out["integrity"] = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            if out["integrity"] != "ok":
                out["problems"].append(f"integrity_check said {out['integrity']!r}, not 'ok'")
        except sqlite3.DatabaseError as exc:
            out["problems"].append(f"integrity_check could not run ({exc})")
        try:
            out["shape"] = read_shape(conn)
        except sqlite3.DatabaseError as exc:
            out["problems"].append(f"the snapshot's tables cannot be read ({exc})")
    finally:
        conn.close()

    if expect_shape is not None:
        was, now = set(expect_shape), set(out["shape"])
        if was != now:
            missing = sorted(was - now)
            extra = sorted(now - was)
            detail = []
            if missing:
                detail.append("missing " + ", ".join(missing))
            if extra:
                detail.append("unexpected " + ", ".join(extra))
            out["problems"].append(
                f"the snapshot's tables do not match the live database's "
                f"({len(now)} vs {len(was)}; {'; '.join(detail)})")
        for name, count in expect_shape.items():
            if count is None:
                continue
            got = out["shape"].get(name)
            if isinstance(got, int) and got < count:
                out["problems"].append(
                    f"{name} holds {got} rows where the live database held {count}")
    return out


def _copy_file(src: Path, dest: Path, manifest: dict, arcname: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    manifest["files"][arcname] = {"bytes": dest.stat().st_size,
                                  "sha256": sha256_file(dest)}


def _copy_dir(src: Path, dest: Path, manifest: dict, arcname: str) -> None:
    size = sum(f.stat().st_size for f in src.rglob("*") if f.is_file())
    if size > MAX_DIR_BYTES:
        manifest["excluded"].append(
            {"path": arcname, "bytes": size,
             "why": f"larger than {MAX_DIR_BYTES // (1024 * 1024)} MB"})
        return
    for f in sorted(src.rglob("*")):
        if f.is_file():
            rel = f.relative_to(src)
            _copy_file(f, dest / rel, manifest, f"{arcname}/{rel.as_posix()}")


def take_snapshot(source=None, dest=None, *, keep: int = KEEP, passphrase=None,
                  timeout: float = 30.0, now: float | None = None) -> dict:
    """Take, verify, keep. Returns a result dict - {"name", "path", "manifest",
    "problems", "removed", "sealed", "ok"} - and never raises for a database
    that merely failed its checks; that is reported in `problems` with `ok`
    False, and the snapshot is kept as `-INCOMPLETE` so it can be looked at.
    """
    source = _resolve(source or default_source())
    dest = _resolve(dest or DEFAULT_DEST)
    if not source.is_dir():
        raise Refused(f"{source} is not a folder, so there is nothing to back up")
    refuse_write_inside(dest, source)          # never write into the live folder
    dest.mkdir(parents=True, exist_ok=True)

    at = time.time() if now is None else now
    stamp = time.strftime(STAMP_FMT, time.localtime(at))
    # The folder the snapshot is BUILT in asks the filesystem for its name
    # (`tempfile.mkdtemp`), never the clock. This is not fussiness: on Windows
    # the clock only moves on the system timer tick, about 15.6 ms, and
    # `time.strftime("%Y%m%d-%H%M%S")` is good for a whole second - so a
    # hand-run and the weekly task landing together would ask for the same
    # folder, and `mkdir` would raise `FileExistsError [WinError 183]` (or,
    # with `exist_ok=True`, quietly build two half-snapshots in one folder).
    # `tools/check_same_tick_paths.py` is the check, and its own docstring has
    # the three Windows CI suites this shape really broke.
    partial = Path(tempfile.mkdtemp(prefix=".partial-", suffix=".partial", dir=dest))

    manifest: dict = {
        "tool": TOOL, "tool_version": VERSION,
        "tool_sha256": sha256_file(Path(__file__)) if Path(__file__).is_file() else "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(at)),
        "created_epoch": at, "stamp": stamp, "source": str(source),
        "sealed": bool(passphrase), "databases": {}, "files": {},
        "excluded": [{"path": d, "why": why} for d, why in sorted(EXCLUDED_DIRS.items())
                     if (source / d).is_dir()],
        "problems": [], "notes": [], "verified": False,
    }

    # --- the databases: one consistent copy each, checked by opening it again
    for src in sorted(source.glob("*.db")):
        attempt, result = 0, None
        while attempt < 2:
            attempt += 1
            result = snapshot_db(src, partial / src.name, timeout)
            if not result["problems"]:
                break
            # One retry, against a FRESH reading of the live database: the
            # usual cause is Jarvis deleting a row between the reading and the
            # copy, which a second try settles.
            time.sleep(0.2)
        manifest["databases"][src.name] = {
            "method": result["method"], "integrity": result["integrity"],
            "rows": total_rows(result["shape"]), "tables": result["shape"],
            "source_rows": total_rows(result["source_shape"]),
            "bytes": result["bytes"], "sha256": result["sha256"],
            "attempts": attempt,
        }
        for note in result["notes"]:
            manifest["notes"].append(f"{src.name}: {note}")
        for problem in result["problems"]:
            manifest["problems"].append(f"{src.name}: {problem}")

    # --- everything else at the top level, and the small data folders. The
    # `-wal`, `-shm` and `-journal` companions are already inside the snapshots
    # above; copying one would leave a stale log beside a fresh database.
    for entry in sorted(source.iterdir()):
        if entry.is_file():
            if entry.suffix in (".db",) or entry.name.endswith(("-wal", "-shm", "-journal")):
                continue
            if entry.name in (MANIFEST, README):
                continue
            _copy_file(entry, partial / entry.name, manifest, entry.name)
        elif entry.is_dir():
            if entry.name in EXCLUDED_DIRS:
                continue
            _copy_dir(entry, partial / entry.name, manifest, entry.name)

    manifest["totals"] = {
        "databases": len(manifest["databases"]),
        "database_rows": sum(d["rows"] for d in manifest["databases"].values()),
        "files": len(manifest["files"]),
        "bytes": (sum(d["bytes"] for d in manifest["databases"].values())
                  + sum(f["bytes"] for f in manifest["files"].values())),
    }
    manifest["verified"] = not manifest["problems"]

    _write_text(partial / MANIFEST, json.dumps(manifest, indent=2) + "\n")
    _write_text(partial / README, _readme(manifest))

    final_name = _place_snapshot(partial, dest, stamp, manifest["verified"])
    final = dest / final_name

    result = {"name": final_name, "path": str(final), "manifest": manifest,
              "problems": list(manifest["problems"]), "removed": [],
              "sealed": False, "ok": manifest["verified"], "keep": keep}

    if passphrase:
        sealed_path = dest / f"{final_name}{SEAL_SUFFIX}"
        try:
            _seal_folder(final, sealed_path, passphrase)
        except Refused:
            # Sealing was asked for and could not be done. A plaintext folder
            # left behind would quietly defeat the request, so it is removed:
            # nothing unsealed is ever kept in the place of a sealed backup.
            shutil.rmtree(final, ignore_errors=True)
            _remove(sealed_path)
            raise Refused(
                "the snapshot could not be sealed, so it was NOT kept - a backup you "
                "asked to be protected must not be left readable instead") from None
        shutil.rmtree(final)
        # The `.jba` is what retention must protect: the folder is gone.
        final_name = f"{final_name}{SEAL_SUFFIX}"
        result.update(name=final_name, path=str(sealed_path), sealed=True)

    result["removed"] = retain(dest, keep, protect=final_name, now=at)
    _write_last_run(dest, result)
    return result


def _place_snapshot(partial: Path, dest: Path, stamp: str, verified: bool) -> str:
    """Give the finished snapshot its dated name, and return that name.

    The dated name is what a person reads, so it is kept - but the clock is
    only good for ONE SECOND, so a name another run already holds is skipped
    rather than written over. That is the same same-tick race the partial
    folder above avoids, one step later, and this is where it would otherwise
    delete a snapshot that had just been made. Nothing is ever removed here.

    The `-N` goes BEFORE the `-INCOMPLETE` marker, so the name still reads as
    one of ours (`SNAP_RE`) whatever happened to the run.
    """
    for n in range(1, 1000):
        name = (f"{SNAP_PREFIX}{stamp}" + ("" if n == 1 else f"-{n}")
                + ("" if verified else INCOMPLETE))
        try:
            partial.rename(dest / name)
            return name
        except OSError:
            continue
    # A thousand snapshots inside one second is not a real state; it means the
    # destination is not writable or is full. Say so instead of losing the work.
    raise Refused(f"could not give the snapshot a name in {dest} - is the folder "
                  f"writable and is there room on the disk?")


def _readme(manifest: dict) -> str:
    """A plain-words note inside every snapshot, because the person who needs
    it will be reading it at the worst possible moment."""
    return (
        f"One backup of your Jarvis data, made {manifest['created_at']}.\n"
        f"\n"
        f"{manifest['totals']['databases']} databases "
        f"({manifest['totals']['database_rows']} rows) and "
        f"{manifest['totals']['files']} other files, copied with SQLite itself "
        f"so every one is consistent even while Jarvis was running.\n"
        f"\n"
        f"Every database in here was opened and checked when this was made, and "
        f"the check result is in {MANIFEST}.\n"
        f"\n"
        f"TO PUT IT BACK: do not copy these files over your live data by hand. "
        f"Run this instead, which restores into a spare folder and checks every "
        f"database opens, so nothing you are using is touched:\n"
        f"\n"
        f'  python "$env:LOCALAPPDATA\\JarvisDataBackup\\{TOOL}" restore '
        f'--to-temp\n'
        f"\n"
        f"It will print the folder it used and how many rows are in each "
        f"database.\n")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_last_run(dest: Path, result: dict) -> None:
    """`last-run.txt` in the destination folder: what the timer did, and when.
    An unattended run has no console to print to, so without this file there
    would be no way to tell a working timer from a dead one. Counts and names
    only - never a row of anybody's data."""
    lines = [
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}  "
        f"{'OK' if result['ok'] else 'FAILED'}",
        f"  snapshot: {result['name']}",
        f"  sealed: {result['sealed']}",
        f"  databases: {result['manifest']['totals']['databases']}, "
        f"rows: {result['manifest']['totals']['database_rows']}, "
        f"other files: {result['manifest']['totals']['files']}",
        f"  removed older: {', '.join(result['removed']) or 'none'}",
        f"  landed in: {Path(result['path']).parent}",
    ]
    for problem in result["problems"]:
        lines.append(f"  PROBLEM: {problem}")
    _write_text(dest / "last-run.txt", "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
#   Finding what is there, and keeping only the newest few
# ---------------------------------------------------------------------------


def list_snapshots(dest) -> list:
    """Every `jarvis-snap-*` entry in `dest`, newest first, each as
    {"name", "path", "sealed", "incomplete", "at"}. Anything that is not one of
    ours - the owner's `.jbak` files above all - is not listed and not touched.
    """
    out = []
    folder = Path(dest)
    if not folder.is_dir():
        return out
    for entry in folder.iterdir():
        m = SNAP_RE.match(entry.name)
        if not m:
            continue
        if not (entry.is_dir() or entry.is_file()):
            continue
        stamp, tie, incomplete, sealed = m.groups()
        try:
            at = time.mktime(time.strptime(stamp, STAMP_FMT))
        except ValueError:
            continue
        out.append({"name": entry.name, "path": entry, "sealed": bool(sealed),
                    "incomplete": bool(incomplete), "at": at, "tie": int(tie or 1)})
    out.sort(key=lambda r: (r["at"], r["tie"], r["name"]), reverse=True)
    return out


def retain(dest, keep: int = KEEP, *, protect=None, now: float | None = None) -> list:
    """Keep the newest `keep` verified snapshots; remove the rest. Returns the
    names removed. `protect` is the snapshot just made - never removed, and it
    counts as one of the `keep`. Leftover `.partial` folders and failed
    `-INCOMPLETE` ones older than STALE_DAYS are cleared too, so a crash cannot
    pile up either.
    """
    now = time.time() if now is None else now
    rows = [r for r in list_snapshots(dest) if not r["incomplete"]]
    keeping = {r["name"] for r in rows[:keep]}
    if protect:
        keeping.add(protect)
    removed = []
    for row in rows:
        if row["name"] in keeping:
            continue
        _remove(row["path"])
        removed.append(row["name"])

    cut = now - STALE_DAYS * 86400
    for entry in Path(dest).iterdir():
        stale = (entry.name.startswith(".") and entry.name.endswith(".partial")) or \
                (SNAP_RE.match(entry.name) and entry.name.endswith(INCOMPLETE))
        if not stale:
            continue
        try:
            if entry.stat().st_mtime < cut:
                _remove(entry)
                removed.append(entry.name)
        except OSError:
            continue
    return removed


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
#   Verifying, and putting it back
# ---------------------------------------------------------------------------


def verify_snapshot(path, passphrase=None) -> dict:
    """Check a snapshot against its own manifest, file by file. Returns
    {"manifest", "problems", "counts"} - `counts` is {database: rows} read back
    out of the snapshot, so a caller can report real numbers rather than a
    promise."""
    path = Path(path)
    workdir = None
    try:
        folder = path
        if path.suffix == SEAL_SUFFIX:
            if not passphrase:
                raise Refused(
                    f"{path.name} is a sealed snapshot: give its passphrase with "
                    f"--passphrase-env or --passphrase-file to open it")
            workdir = Path(_temp_dir("jarvis-verify-"))
            _open_seal(path, workdir, passphrase)
            folder = workdir
        manifest_file = folder / MANIFEST
        if not manifest_file.is_file():
            raise Refused(f"{folder} is not a snapshot of mine - there is no {MANIFEST} in it")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        problems, counts = [], {}
        for name, entry in sorted(manifest.get("databases", {}).items()):
            db = folder / name
            if not db.is_file():
                problems.append(f"{name} is missing from the snapshot")
                continue
            if entry.get("sha256") and sha256_file(db) != entry["sha256"]:
                problems.append(f"{name} is not the file this manifest describes "
                                f"(its sha256 changed)")
                continue
            check = verify_db_file(db, entry.get("tables"))
            counts[name] = total_rows(check["shape"])
            problems.extend(f"{name}: {p}" for p in check["problems"])
            if entry.get("tables") is not None and check["shape"] != entry["tables"]:
                problems.append(f"{name}: the row counts no longer match the manifest")
        for name, entry in sorted(manifest.get("files", {}).items()):
            f = folder / name
            if not f.is_file():
                problems.append(f"{name} is missing from the snapshot")
            elif entry.get("sha256") and sha256_file(f) != entry["sha256"]:
                problems.append(f"{name} is not the file this manifest describes")
        return {"manifest": manifest, "problems": problems, "counts": counts}
    finally:
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)


def restore_snapshot(snapshot, target=None, *, passphrase=None, to_temp=False,
                     source=None) -> dict:
    """Put a snapshot back, into `target` - which is refused if it is inside the
    live data, so this can never be the thing that overwrites it. Returns
    {"target", "counts", "problems"}: the databases really open and the real
    row counts, checked after the copy rather than inferred from it.
    """
    source = _resolve(source or default_source())
    snapshot = Path(snapshot)
    if to_temp and target:
        raise Refused("give --to or --to-temp, not both")
    if to_temp:
        target = Path(_temp_dir("jarvis-restore-"))
    elif target:
        target = refuse_write_inside(target, source)
    else:
        raise Refused(f"say where to put it: --to <a folder> or --to-temp "
                      f"(nothing is ever written into {source})")
    target.mkdir(parents=True, exist_ok=True)

    workdir = None
    try:
        folder = snapshot
        if snapshot.suffix == SEAL_SUFFIX:
            if not passphrase:
                raise Refused(f"{snapshot.name} is sealed: give its passphrase")
            workdir = Path(_temp_dir("jarvis-open-"))
            _open_seal(snapshot, workdir, passphrase)
            folder = workdir
        manifest_file = folder / MANIFEST
        if not manifest_file.is_file():
            raise Refused(f"{folder} is not a snapshot of mine - there is no {MANIFEST} in it")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        for entry in sorted(folder.iterdir()):
            if entry.name in (MANIFEST, README):
                continue
            into = target / entry.name
            if entry.is_dir():
                shutil.copytree(entry, into, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, into)
        _write_text(target / README, _readme(manifest))
    finally:
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)

    # Check what actually landed, by opening it. These are the numbers a
    # restore test reports.
    problems, counts, tables = [], {}, {}
    for name, entry in sorted(manifest.get("databases", {}).items()):
        db = target / name
        if not db.is_file():
            problems.append(f"{name} did not arrive")
            continue
        check = verify_db_file(db, entry.get("tables"))
        counts[name] = total_rows(check["shape"])
        tables[name] = len(check["shape"])
        problems.extend(f"{name}: {p}" for p in check["problems"])
    return {"target": str(target), "counts": counts, "tables": tables,
            "problems": problems, "manifest": manifest}


def _temp_dir(prefix: str) -> str:
    return tempfile.mkdtemp(prefix=prefix)


# ---------------------------------------------------------------------------
#   Sealing, for the runs the owner starts by hand
# ---------------------------------------------------------------------------
#
#   b"JDBA1" | lanes (1) | memory KiB (4, big endian) | iterations (4) |
#   salt (16) | nonce (12) | AES-256-GCM(zip bytes), AAD = every byte before it
#
# Deliberately the same construction as jarvis_backup.py's JBAK1 - one format
# for this project to reason about instead of two - with a different magic so
# the two can never be confused. See the module docstring for why the default
# is unsealed and why no passphrase is ever stored.


def _crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    except Exception:
        return None, None
    return AESGCM, Argon2id


def _seal_folder(folder: Path, out_path: Path, passphrase: str) -> None:
    """One sealed `.jba` file holding the whole snapshot folder."""
    import io
    import secrets
    import struct

    aesgcm, argon2 = _crypto()
    if aesgcm is None:
        raise Refused(
            "sealing a backup needs the `cryptography` package, which is not installed "
            "here. Nothing was written unsealed instead - either install it, or take "
            "the backup without --seal.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                zf.write(f, arcname=f.relative_to(folder).as_posix())
    salt, nonce = secrets.token_bytes(SALT_LEN), secrets.token_bytes(NONCE_LEN)
    header = (SEAL_MAGIC
              + struct.pack(">BII", ARGON_LANES, ARGON_MEMORY_KIB, ARGON_ITERATIONS)
              + salt + nonce)
    key = argon2(salt=salt, length=KEY_LEN, iterations=ARGON_ITERATIONS,
                 lanes=ARGON_LANES, memory_cost=ARGON_MEMORY_KIB).derive(
        passphrase.encode("utf-8"))
    blob = header + aesgcm(key).encrypt(nonce, buf.getvalue(), header)
    tmp = out_path.with_name("." + out_path.name + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, out_path)


def _open_seal(path: Path, into: Path, passphrase: str) -> None:
    """Unseal `path` into the folder `into`. A wrong passphrase is refused in
    plain words, never as a library exception."""
    import io
    import struct

    aesgcm, argon2 = _crypto()
    if aesgcm is None:
        raise Refused("opening a sealed backup needs the `cryptography` package, which "
                      "is not installed here")
    head_len = len(SEAL_MAGIC) + SEAL_HEADER + SALT_LEN + NONCE_LEN
    blob = path.read_bytes()
    if len(blob) < head_len or blob[:len(SEAL_MAGIC)] != SEAL_MAGIC:
        raise Refused(f"{path.name} is not a sealed backup of mine")
    body = blob[len(SEAL_MAGIC):len(SEAL_MAGIC) + SEAL_HEADER]
    lanes, memory_kib, iterations = struct.unpack(">BII", body)
    salt = blob[len(SEAL_MAGIC) + SEAL_HEADER:len(SEAL_MAGIC) + SEAL_HEADER + SALT_LEN]
    nonce = blob[len(SEAL_MAGIC) + SEAL_HEADER + SALT_LEN:head_len]
    key = argon2(salt=salt, length=KEY_LEN, iterations=iterations, lanes=lanes,
                 memory_cost=memory_kib).derive(passphrase.encode("utf-8"))
    try:
        plain = aesgcm(key).decrypt(nonce, blob[head_len:], blob[:head_len])
    except Exception:
        raise Refused(f"that passphrase does not open {path.name} (or the file is "
                      f"damaged)") from None
    with zipfile.ZipFile(io.BytesIO(plain)) as zf:
        for info in zf.infolist():
            # A zip entry may name a path; refuse anything that would climb out
            # of the folder it is being unpacked into.
            target = (into / info.filename).resolve()
            if not str(target).startswith(str(into.resolve())):
                raise Refused(f"{path.name} holds an entry that points outside the "
                              f"folder it is unpacked into ({info.filename})")
        zf.extractall(into)


def passphrase_from(args, *, required: bool = False) -> str:
    """The passphrase, from the file or the environment variable the caller
    named. Never from the command line itself: a passphrase typed as an
    argument lands in PowerShell's history and in the process list.

    Read for `verify` and `restore` too, so an already-sealed snapshot opens
    without having to say `--seal` again; `required` is what makes it an error
    rather than an empty string.
    """
    phrase = ""
    if args.passphrase_file:
        text = Path(args.passphrase_file).expanduser().read_text(encoding="utf-8")
        phrase = text.splitlines()[0].strip() if text.strip() else ""
    else:
        phrase = os.environ.get(args.passphrase_env, "")
    if required and not phrase:
        raise Refused(
            f"--seal needs a passphrase: set {args.passphrase_env} first, or use "
            f"--passphrase-file <a file only you can read>. Nothing was written.")
    return phrase


# ---------------------------------------------------------------------------
#   Installing it somewhere stable, and the weekly timer
# ---------------------------------------------------------------------------


def install_dir() -> Path:
    """Where the installed copy lives: `%LOCALAPPDATA%\\JarvisDataBackup` on
    Windows. Stable on purpose - see the docstring on why the timer does not
    point at a git checkout."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"),
                                                          ".local", "share")
    return Path(base) / "JarvisDataBackup"


def install(into=None) -> Path:
    """Copy this file to the stable folder, atomically. Returns the path."""
    into = Path(into) if into else install_dir()
    into.mkdir(parents=True, exist_ok=True)
    dest = into / TOOL
    tmp = into / f".{TOOL}.tmp"
    shutil.copy2(Path(__file__), tmp)
    os.replace(tmp, dest)
    return dest


def pythonw_for(exe=None) -> str:
    """`pythonw.exe` beside the interpreter if it is there, so the timer runs
    with no console window at all; otherwise the interpreter itself."""
    exe = Path(exe or sys.executable)
    quiet = exe.with_name("pythonw.exe")
    return str(quiet if quiet.is_file() else exe)


def powershell_exe() -> str:
    """Windows PowerShell 5.1, by its full path - the one interpreter that is
    on every Windows machine. It is what the owner's two existing Jarvis tasks
    run, and it is here for the same reason: a task that cannot find its shell
    is a task that silently does nothing."""
    system = os.environ.get("SYSTEMROOT", r"C:\Windows")
    exe = Path(system) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(exe) if exe.is_file() else "powershell"


def task_script(exe, script, *, name: str = TASK_NAME, day: str = TASK_DAY,
                at: str = TASK_AT) -> str:
    """The PowerShell that registers the weekly run. Pure - `register_task`
    runs it, and a test can read it without touching the Task Scheduler.

    `pythonw.exe` is what makes no window appear. No `-User` and no
    `-Password`: the task runs as this user, when this user is signed in, so
    registering it needs no administrator and no password is stored anywhere.
    `-StartWhenAvailable` is what makes a run that was MISSED happen - at 03:00
    his PC may well be asleep, and without it the weekly backup would simply
    never happen, which is the one failure worse than a late backup.
    """
    parent = Path(script).parent
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$action = New-ScheduledTaskAction -Execute '{exe}' "
        f"-Argument '\"{script}\"' -WorkingDirectory '{parent}'",
        f"$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek {day} -At '{at}'",
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable "
        "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)",
        f"Register-ScheduledTask -TaskName '{name}' -Action $action "
        f"-Trigger $trigger -Settings $settings -Force | Out-Null",
        "Write-Output 'registered'",
    ])


def register_task(script=None, *, name: str = TASK_NAME, day: str = TASK_DAY,
                  at: str = TASK_AT, exe=None) -> dict:
    """Register (or replace) the weekly task. Returns {"script", "output", "ok",
    "next_run"}. The PowerShell is handed over base64-encoded
    (`-EncodedCommand`), so no quote in any path can be mangled on the way - a
    path with a space in it is the normal case on this PC."""
    import base64

    script = str(Path(script) if script else install())
    if os.name != "nt":
        raise Refused("the weekly timer is a Windows scheduled task; this is not Windows")
    text = task_script(pythonw_for(exe), script, name=name, day=day, at=at)
    encoded = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
    command = [powershell_exe(), "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]
    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused(f"could not register the task ({type(exc).__name__}: {exc})") from None
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0 or "registered" not in out:
        raise Refused(f"the task was not registered: {out or proc.returncode}")
    return {"script": text, "output": out, "ok": True, "next_run": task_next_run(name)}


def task_next_run(name: str = TASK_NAME) -> str:
    """The task's own next run time, as Windows reports it, or "" if it cannot
    be read. Shown to the owner and kept for the record: a timer nobody has
    seen the next run time of is a timer nobody knows is working."""
    if os.name != "nt":
        return ""
    try:
        proc = subprocess.run(["schtasks", "/Query", "/TN", name, "/V", "/FO", "LIST"],
                              capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in (proc.stdout or "").splitlines():
        if line.lower().startswith("next run time"):
            return line.split(":", 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
#   The command line
# ---------------------------------------------------------------------------


def _print_snapshot(result: dict) -> None:
    m = result["manifest"]
    print(f"Jarvis personal data backup - {'OK' if result['ok'] else 'FAILED'}")
    print(f"  snapshot:   {result['name']}{'  (sealed)' if result['sealed'] else ''}")
    print(f"  databases:  {m['totals']['databases']} "
          f"({m['totals']['database_rows']} rows), "
          f"{m['totals']['files']} other files")
    print(f"  verified:   every database was opened again and checked"
          f"{'' if result['ok'] else ' -- SEE PROBLEMS BELOW'}")
    print(f"  kept:       newest {result['keep']}; removed {len(result['removed'])} older")
    for note in result["manifest"].get("notes", []):
        print(f"  note:       {note}")
    for problem in result["problems"]:
        print(f"  PROBLEM:    {problem}")
    print(f"  Backed up to {Path(result['path']).parent}")


def cmd_backup(args) -> int:
    try:
        phrase = passphrase_from(args, required=args.seal)
    except Refused as exc:
        print(f"Nothing was backed up: {exc}")
        return 2
    if phrase and not args.seal:
        # A passphrase was given but sealing was not asked for. Writing the
        # data out readable would quietly ignore the one thing the caller
        # clearly meant, so this stops instead.
        print("Nothing was backed up: a passphrase was given but --seal was not, so "
              "the snapshot would have been written readable. Add --seal, or leave "
              "the passphrase out.")
        return 2
    if args.seal:
        # Asked to seal: check the tool is here BEFORE a snapshot is taken, so
        # a missing `cryptography` cannot leave a plainly readable copy behind.
        aesgcm, _argon2 = _crypto()
        if aesgcm is None:
            print("Nothing was backed up: sealing needs the `cryptography` package, "
                  "which is not installed here. Take the backup without --seal, or "
                  "install it - nothing was written unsealed instead.")
            return 2
    try:
        result = take_snapshot(args.source, args.dest, keep=args.keep,
                               passphrase=phrase if args.seal else None)
    except Refused as exc:
        print(f"Nothing was backed up: {exc}")
        return 2
    _print_snapshot(result)
    return 0 if result["ok"] else 1


def cmd_verify(args) -> int:
    snapshot = args.snapshot or _newest(args.dest)
    try:
        phrase = passphrase_from(args)
    except Refused as exc:
        print(f"Nothing was verified: {exc}")
        return 2
    try:
        out = verify_snapshot(snapshot, phrase or None)
    except Refused as exc:
        print(str(exc))
        return 2
    print(f"Snapshot {Path(snapshot).name} - "
          f"{len(out['counts'])} databases, {sum(out['counts'].values())} rows")
    for name, rows in sorted(out["counts"].items()):
        print(f"  {name:<20} {rows:>7} rows")
    if out["problems"]:
        print(f"  {len(out['problems'])} problem(s):")
        for problem in out["problems"]:
            print(f"    {problem}")
        return 1
    print("  every database opens and matches its manifest.")
    return 0


def cmd_restore(args) -> int:
    snapshot = args.snapshot or _newest(args.dest)
    try:
        phrase = passphrase_from(args)
    except Refused as exc:
        print(f"Nothing was restored: {exc}")
        return 2
    try:
        out = restore_snapshot(snapshot, args.to, passphrase=phrase or None,
                              to_temp=args.to_temp, source=args.source)
    except Refused as exc:
        print(f"Nothing was restored: {exc}")
        return 2
    print(f"Restored into {out['target']}")
    for name, rows in sorted(out["counts"].items()):
        print(f"  {name:<20} {rows:>7} rows in {out['tables'][name]} tables")
    print(f"  {sum(out['counts'].values())} rows in total")
    if out["problems"]:
        print(f"  {len(out['problems'])} problem(s) - this restore is NOT good:")
        for problem in out["problems"]:
            print(f"    {problem}")
        return 1
    print("  Your live data was not touched: this is a copy in the folder above.")
    return 0


def cmd_status(args) -> int:
    dest = _resolve(args.dest)
    rows = list_snapshots(dest)
    good = [r for r in rows if not r["incomplete"]]
    print(f"Snapshots in {dest}: {len(good)} good"
          f"{', ' + str(len(rows) - len(good)) + ' incomplete' if len(rows) > len(good) else ''}")
    print(f"  keeping the newest {KEEP}; the older ones are deleted as new ones arrive")
    for row in rows[:8]:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(row["at"]))
        note = "  (sealed)" if row["sealed"] else ""
        if row["incomplete"]:
            note += "  (INCOMPLETE - do not rely on this one)"
        size = 0
        if row["path"].is_dir():
            size = sum(f.stat().st_size for f in row["path"].rglob("*") if f.is_file())
        elif row["path"].is_file():
            size = row["path"].stat().st_size
        print(f"  {when}  {size / 1024:8.0f} KB  {row['name']}{note}")
    last = dest / "last-run.txt"
    if last.is_file():
        print("\nLast run (last-run.txt):")
        print("  " + last.read_text(encoding="utf-8").strip().replace("\n", "\n  "))
    if os.name == "nt":
        print(f"\nWeekly task '{TASK_NAME}': next run {task_next_run() or 'not found'}")
    return 0


def cmd_install(args) -> int:
    into = Path(args.install_to) if args.install_to else install_dir()
    dest = install(into)
    print(f"Installed to {dest}")
    print(f"  Back up now, one line:")
    print(f'    python "{dest}"')
    if args.register_task:
        out = register_task(dest, day=args.task_day, at=args.task_at)
        print(f"  Weekly task '{TASK_NAME}' registered: every {args.task_day} "
              f"at {args.task_at}")
        print(f"  Its next run: {out['next_run'] or 'not reported by Windows'}")
        print(f"  It runs with no window (pythonw.exe), as this user, and needs no "
              f"administrator.")
    return 0


def _newest(dest):
    rows = [r for r in list_snapshots(_resolve(dest or DEFAULT_DEST)) if not r["incomplete"]]
    if not rows:
        raise Refused(f"there are no snapshots in {_resolve(dest or DEFAULT_DEST)} yet - "
                      f"make one first")
    return str(rows[0]["path"])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL,
        description="One consistent, verified, local snapshot of the owner's Jarvis "
                    "data. Nothing leaves this PC.")
    p.add_argument("action", nargs="?", default="backup",
                   choices=["backup", "verify", "restore", "status", "install"],
                   help="backup (default), verify, restore, status or install")
    p.add_argument("snapshot", nargs="?", default=None,
                   help="the snapshot folder (or .jba file) to verify or restore; "
                        "the newest is used when this is left out")
    p.add_argument("--source", default=None,
                   help=f"the folder holding Jarvis's data (default {default_source()})")
    p.add_argument("--dest", default=str(DEFAULT_DEST),
                   help=f"where snapshots are written (default {DEFAULT_DEST})")
    p.add_argument("--keep", type=int, default=KEEP,
                   help=f"how many snapshots to keep (default {KEEP})")
    p.add_argument("--to", default=None, help="restore into this folder")
    p.add_argument("--to-temp", action="store_true",
                   help="restore into a fresh folder under the system temp folder")
    p.add_argument("--seal", action="store_true",
                   help="write one passphrase-protected .jba file instead of a folder")
    p.add_argument("--passphrase-env", default="JARVIS_BACKUP_PASSPHRASE",
                   help="the environment variable holding the passphrase for --seal")
    p.add_argument("--passphrase-file", default=None,
                   help="a file whose first line is the passphrase (for --seal)")
    p.add_argument("--register-task", dest="register_task", action="store_true",
                   help="with the install action: also register the weekly task")
    p.add_argument("--install-to", default=None,
                   help="install into this folder instead of the default")
    p.add_argument("--task-day", default=TASK_DAY, help=f"task day (default {TASK_DAY})")
    p.add_argument("--task-at", default=TASK_AT, help=f"task time (default {TASK_AT})")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "verify":
            return cmd_verify(args)
        if args.action == "restore":
            return cmd_restore(args)
        if args.action == "status":
            return cmd_status(args)
        if args.action == "install":
            return cmd_install(args)
        return cmd_backup(args)
    except Refused as exc:
        print(f"{exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
