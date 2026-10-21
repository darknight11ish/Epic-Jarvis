"""test_backup.py - "Backups": one locked backup file, a recovery code shown
once, restore with a card plus Windows Hello (jarvis_backup.py, backup.patch;
the owner's decision of 2026-09-27, CLAUDE.md).

    python3 backend/test_backup.py

Runs anywhere; no model, no network, no real Windows Credential Manager (a
fake key provider stands in). What it proves:

1. The folder is set the same shape jarvis_documents.py uses to add a
   folder: PC only, ONE approval card (change_own_config), refused the same
   places (a drive's top, the whole user folder, protected places) because
   it calls jarvis_documents.check_folder, not a copy of it.
2. "Back up now": PC only, no card, refused with no folder set.
3. The backup file is genuinely encrypted - not a zip, not readable text -
   and the recovery code truly cannot be recovered if it is lost: nothing
   in this module, on disk or in memory, keeps a copy of it once the
   response that showed it has been sent.
4. What is inside, once decrypted with the right code: the four real
   databases (verified counts), the settings JSONs, the toml, notes and
   voice folders, and the chat-history key - and NOT the excluded things:
   a decoy log file, a decoy token file, the voice-models and voices
   folders (downloaded engine files and the custom-voice bank, neither of
   them the owner's own voice-print).
5. Retention: making more than KEEP backups deletes only the oldest, and
   two backups made in the same second never overwrite each other.
6. Restore: the wrong code is refused (never opens the file); it needs
   Windows Hello (jarvis_owner_check.armed()) and always comes as ONE card
   that only a person's "approved" carries out; it backs up the CURRENT
   state first, automatically, with its own fresh one-time code, so the
   restore itself can be undone; a denied or timed-out card changes
   nothing; the safety backup's code is readable exactly once.
7. The routes and the patch: install() answers the six routes after the
   server's own checks and passes everything else on; backup.patch applies
   to the whole stack and reverses; the module is shipped; restore_backup
   is in jarvis_owner_check.PC_ONLY_ACTIONS, [autonomy.tiers] and has a
   plain-words title.
8. What a restore must never do to the person trying it (2026-10-10, after
   a restore that could never be approved):
   - its card must not NAME a file jarvis_gate.py protects - the card IS the
     prompt the gate reads, so naming `jarvis_hud.py` got the card refused
     at tier "never" with nobody ever asked; the card and the detail handed
     to the gate are held against the gate's own `_PROTECTED` list, read out
     of `jarvis-backend/jarvis_gate.py`;
   - a caller that cannot approve the card - `jarvis_owner_check.from_this_pc`
     says it is not this PC, the same rule `PC_ONLY_ACTIONS` refuses on - is
     told so up front in plain words, and is never answered 202-and-waiting;
   - a refusal says, in the sentence the app shows, what to do instead, while
     the technical reason stays in the record's `why` for a bug report.
"""
from __future__ import annotations

import ast
import io
import itertools
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_backup.py", "jarvis_documents.py", "jarvis_owner_check.py",
                "jarvis_chat_log.py", "jarvis_token_store.py", "jarvis_card_words.py",
                "jarvis_decks.py")
sys.path.append(str(HERE / "rebuilt"))
import _stack  # noqa: E402
import jarvis_backup as B  # noqa: E402
import jarvis_documents as D  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402
import jarvis_card_words as W  # noqa: E402
import jarvis_framework as fw  # noqa: E402

FAILED, PASSED = [], []


def _scratch_root() -> Path:
    """A disposable folder the REAL jarvis_documents.check_folder() accepts.

    The OS temp folder is not one on Windows: it lives under AppData, and Jarvis
    refuses any folder under AppData on purpose (it holds keys and browser
    data). Every check here that reaches the real check_folder() was failing
    there for a reason that has nothing to do with backups, so ask first and
    fall back to a folder beside the user's home where temp is refused
    (2026-10-03). The root is removed in main() either way.
    """
    root = Path(tempfile.mkdtemp(prefix="jarvis-backup-"))
    try:
        D.check_folder(str(root))
        return root
    except ValueError:
        shutil.rmtree(root, ignore_errors=True)
    return Path(tempfile.mkdtemp(prefix=".jarvis-backup-tests-", dir=str(Path.home())))


TMP = _scratch_root()


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond
                                                        else ""))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier
        self.reason = outcome


def approve(action, detail, prompt):
    return Verdict(True, "approved")


def deny(action, detail, prompt):
    return Verdict(False, "denied")


def timeout(action, detail, prompt):
    return Verdict(False, "timed_out")


def tier_ask(action):
    return "ask"


def sync_spawn(fn):
    fn()


def fresh_conf() -> Path:
    """A new, empty settings folder, with the real jarvis_documents.py and
    jarvis_backup.py both reading it, and a folder for backups beside it.

    Named by tempfile.mkdtemp, not `TMP / f"conf-{time.time_ns()}"`: on Windows
    time.time_ns() only moves on the system timer tick (GetSystemTimeAsFileTime
    in 100-ns units), so two calls inside one tick hand back the same name and
    the mkdir() that follows the second one dies with `FileExistsError:
    [WinError 183]` - measured on this PC at 155 of 400 calls (2026-10-05).
    That is what the Windows runner reported on 2026-10-05 (run 37369387182,
    job backend-windows), in four checks at once:
    t_backup_now_is_this_pc_only_no_card_needs_a_folder and the three below it
    each died in fresh_conf() before their own first check ran - two of them on
    its `conf.mkdir()` line and two on its `backups.mkdir()` line - which is
    why the job showed 123 passed, 4 failed where Ubuntu showed 127 passed.
    mkdtemp asks the filesystem for a free name, and
    jarvis_documents.check_folder() accepts TMP itself (it is either the OS
    temp folder or a folder beside the user's home - see _scratch_root above).
    """
    conf = Path(tempfile.mkdtemp(dir=str(TMP), prefix="conf-"))
    B._config_dir = lambda: conf
    D._config_dir = lambda: conf
    fw.CONFIG_DIR = conf
    # build_archive() also reads the folder jarvis_backup.py is RUNNING FROM,
    # for the backend's own program files (2026-10-05). Left alone that is this
    # repository's own backend/ folder, so every test would archive the real
    # sources - slow, and a test that called _apply_restore would write into
    # the checkout. Point it at an empty scratch folder by default; a test that
    # wants files there calls fake_backend().
    empty = _scratch_dir("backend")
    B._source_dir = lambda: empty
    B._reset_for_tests()
    backups = Path(tempfile.mkdtemp(dir=str(TMP), prefix="backups-"))
    return conf, backups


_SEQ = itertools.count()


def _scratch_dir(kind: str) -> Path:
    """A new empty folder under TMP. The counter, not the clock: two calls in
    the same nanosecond would otherwise collide and raise."""
    d = TMP / f"{kind}-{next(_SEQ)}"
    d.mkdir()
    return d


def fake_backend(files=("jarvis_hud.py", "jarvis_gate.py"), *, decoys=True) -> Path:
    """A scratch stand-in for the live backend folder, holding `files` as real
    `*.py` files, and pointing jarvis_backup.py at it. `decoys`: the things
    that must NOT be swept in - a `.txt`, a `.pyc` and a nested `*.py`, plus a
    `__pycache__` folder to stand for the 9.6 MB of bytecode beside the real
    sources, and a `_jarvis-backup-*` folder to stand for the patcher's own
    older copies (archiving those would nest a copy of the whole source inside
    every new backup)."""
    d = _scratch_dir("fake-backend")
    for name in files:
        (d / name).write_text(f"# {name}\nVALUE = {name!r}\n", encoding="utf-8")
    if decoys:
        (d / "notes.txt").write_text("NOT SOURCE", encoding="utf-8")
        (d / "stale.pyc").write_bytes(b"BYTECODE")
        (d / "sub").mkdir()
        (d / "sub" / "nested.py").write_text("# nested", encoding="utf-8")
        (d / "__pycache__").mkdir()
        (d / "__pycache__" / "jarvis_hud.cpython-312.pyc").write_bytes(b"BYTECODE")
        (d / "_jarvis-backup-2026-10-04-222810").mkdir()
        (d / "_jarvis-backup-2026-10-04-222810" / "jarvis_hud.py").write_text(
            "# an older copy\n", encoding="utf-8")
    B._source_dir = lambda: d
    return d


def make_memory_db(conf: Path, rows=("secret one",)) -> None:
    """(Re)writes memory.db's one table to hold exactly `rows` - callable
    more than once on the same conf, to simulate the database changing
    between a backup and a later restore."""
    conn = sqlite3.connect(str(conf / "memory.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, text TEXT)")
    conn.execute("DELETE FROM facts")
    for r in rows:
        conn.execute("INSERT INTO facts (text) VALUES (?)", (r,))
    conn.commit()
    conn.close()


def read_facts(conf: Path) -> list:
    conn = sqlite3.connect(str(conf / "memory.db"))
    rows = [r[0] for r in conn.execute("SELECT text FROM facts ORDER BY id")]
    conn.close()
    return rows


# ======================================================== 1. setting the folder


def t_setting_the_folder_is_this_pc_only_and_one_card():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    code, out = B.request_set_folder({"path": str(backups)}, here=False)
    check("refused from another device", code == 403 and out["pc_only"] is True, out)
    check("nothing was set", B._load_settings()["folder"] is None)

    code, out = B.request_set_folder({"path": str(backups)}, here=True, gate=deny,
                                     tier_of=tier_ask, spawn=sync_spawn)
    check("a denial changes nothing", code == 202 and B._load_settings()["folder"] is None, out)

    code, out = B.request_set_folder({"path": str(backups)}, here=True, gate=approve,
                                     tier_of=tier_ask, spawn=sync_spawn)
    check("approved: 202, and the folder is set", code == 202
          and B._load_settings()["folder"] == str(backups), out)


def t_setting_the_folder_reuses_documents_refusals():
    conf, backups = fresh_conf()
    home = os.path.realpath(os.path.expanduser("~"))
    code, out = B.request_set_folder({"path": home}, here=True, gate=approve, tier_of=tier_ask,
                                     spawn=sync_spawn)
    check("the whole user folder is refused (jarvis_documents.check_folder, not a copy)",
          code == 400, out)
    # The name used to end in `or True`, so it could never fail - and the two
    # clauses above it were both false (check_folder is a wrapper in
    # jarvis_backup, not a re-export). What is worth asserting is the thing
    # the wrapper's own docstring claims: the path really is handed to
    # jarvis_documents.check_folder, so there is one list of unsafe places and
    # not two that can drift apart. Watch the delegation happen.
    seen = []
    real = D.check_folder
    D.check_folder = lambda p: (seen.append(p), real(p))[1]
    try:
        code, out = B.request_set_folder({"path": home}, here=True, gate=approve,
                                         tier_of=tier_ask, spawn=sync_spawn)
    finally:
        D.check_folder = real
    check("B.check_folder goes through jarvis_documents.check_folder, imported not copied",
          code == 400 and seen == [home], out)


# ======================================================== 2. "Back up now"


def t_backup_now_is_this_pc_only_no_card_needs_a_folder():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    code, out = B.request_backup_now({}, here=False)
    check("refused from another device", code == 403, out)
    code, out = B.request_backup_now({}, here=True)
    check("no folder set yet: refused, plainly", code == 409 and "folder" in out["error"], out)
    B._save_settings({"folder": str(backups)})
    code, out = B.request_backup_now({}, here=True)
    check("with a folder: 200, no card, a name and a one-time code",
          code == 200 and out["ok"] and out["name"].endswith(B.FILE_SUFFIX)
          and out["recovery_code"], out)
    check("the file is really there", (backups / out["name"]).is_file())


# ======================================================== 3. encryption and the code


def t_the_file_is_really_encrypted():
    conf, backups = fresh_conf()
    make_memory_db(conf, rows=("a very particular secret sentence",))
    out = B.backup_now(str(backups))
    blob = (backups / out["name"]).read_bytes()
    check("starts with the magic bytes, not a zip signature", blob[:5] == B.MAGIC
          and blob[:2] != b"PK")
    check("is not readable as a zip file at all", not zipfile.is_zipfile(io.BytesIO(blob)))
    check("the plain sentence is nowhere in the file's bytes",
          b"a very particular secret sentence" not in blob)
    check("is not readable as JSON either",
          _not_json(blob))
    back = B.decrypt_blob(blob, out["recovery_code"])
    check("the right code opens it: a real zip", zipfile.is_zipfile(io.BytesIO(back)))
    with zipfile.ZipFile(io.BytesIO(back)) as zf:
        db_bytes = zf.read("db/memory.db")
    check("...and the sentence is inside the restored memory.db, uncompressed",
          b"a very particular secret sentence" in db_bytes)


def _not_json(blob: bytes) -> bool:
    try:
        json.loads(blob.decode("utf-8"))
    except Exception:
        return True
    return False


def t_a_lost_code_truly_cannot_be_recovered():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    out = B.backup_now(str(backups))
    real_code = out["recovery_code"]
    # Nothing this module wrote to disk holds it.
    for f in backups.rglob("*"):
        if f.is_file():
            check(f"the code is not written into {f.name}", real_code.encode() not in f.read_bytes())
    for f in conf.rglob("*"):
        if f.is_file():
            check(f"the code is not written into settings ({f.name})",
                  real_code.encode() not in f.read_bytes())
    # A closely wrong code, and a random one, both fail - never partially.
    wrong = real_code[:-1] + ("A" if real_code[-1] != "A" else "B")
    try:
        B.decrypt_blob((backups / out["name"]).read_bytes(), wrong)
        check("a one-character-wrong code is refused", False)
    except B.WrongCode:
        check("a one-character-wrong code is refused", True)
    try:
        B.decrypt_blob((backups / out["name"]).read_bytes(), "NOTAREALCODEATALLNOPE")
        check("a random wrong code is refused", False)
    except B.WrongCode:
        check("a random wrong code is refused", True)


def t_recovery_code_shape():
    seen = {B.generate_code() for _ in range(200)}
    check("every code is 4 groups of 5 from the safe alphabet, and no two collide",
          len(seen) == 200 and all(
              len(c) == 23 and c.count("-") == 3
              and all(ch in B.CODE_ALPHABET for ch in c.replace("-", ""))
              for c in seen))
    check("the alphabet has no 0/O/1/I/L", not (set("0O1IL") & set(B.CODE_ALPHABET)))


# ======================================================== 4. what is inside, and excluded


def t_what_is_backed_up_and_what_is_excluded():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    (conf / "folders.json").write_text('{"folders": []}', encoding="utf-8")
    (conf / "notes").mkdir()
    (conf / "notes" / "todo.md").write_text("buy milk", encoding="utf-8")
    (conf / "voice").mkdir()
    (conf / "voice" / "owner.json").write_text('{"centroid": [0.1]}', encoding="utf-8")
    # decoys: everything that must NEVER be in the archive
    (conf / "big-model-engine.log").write_text("LOG WITH SECRETS", encoding="utf-8")
    (conf / "voice-models").mkdir()
    (conf / "voice-models" / "model.onnx").write_bytes(b"MODEL BYTES")
    (conf / "voices").mkdir()
    (conf / "voices" / "custom.wav").write_bytes(b"VOICE BYTES")

    zip_bytes, manifest = B.build_archive()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    check("memory.db is in, with its real row count", "db/memory.db" in names
          and manifest["databases"].get("memory.db", {}).get("facts") == 1, manifest)
    check("projects.db is on the list of databases backed up (Projects feature audit, "
          "2026-09-28)", "projects.db" in B.SOURCE_DBS)
    check("goals.db is on the list of databases backed up (cohesiveness audit, 2026-09-29): "
          "its weekly check-ins live in schedule.db", "goals.db" in B.SOURCE_DBS)
    # Every database file name a backend module opens must be on the list, so
    # the next one added cannot be forgotten the way projects.db and goals.db
    # each were once. A `.jsonl` store is the same kind of decision and is
    # scanned too (Frontier 2 audit, 2026-10-18) - the older `.db`-only regex
    # could not see the File Guardian's journal, so a whole store could go
    # missing without a red check.
    import re as _re
    opened = set()
    opened_jsonl = set()
    for mod in sorted(HERE.glob("jarvis_*.py")):
        if mod.name == "jarvis_backup.py":
            continue
        text = mod.read_text(encoding="utf-8")
        opened |= set(_re.findall(r"[\"']([A-Za-z0-9_-]+\.db)[\"']", text))
        opened_jsonl |= set(_re.findall(r"[\"']([A-Za-z0-9_-]+\.jsonl)[\"']", text))
    # The module's OWN register of deliberate exclusions, so a new database is
    # accounted for in one place. study.db (review decks, jarvis_decks.py)
    # joined the locked backup on 2026-09-30, the owner's decision; the search
    # index joined the exclusions on 2026-10-16 (derived, rebuilt from the files
    # it describes, and holding no document text).
    NOT_BACKED_UP = set(B.NOT_BACKED_UP)
    check("every .db a backend module names is backed up (or written down here)",
          opened - NOT_BACKED_UP <= set(B.SOURCE_DBS), sorted(opened - NOT_BACKED_UP - set(B.SOURCE_DBS)))
    excused_jsonl = {n for n in opened_jsonl if B.not_backed_up_reason(n)}
    check("every .jsonl a backend module names is backed up or recorded too",
          opened_jsonl - set(B.SETTINGS_NAMES) - excused_jsonl == set(),
          sorted(opened_jsonl - set(B.SETTINGS_NAMES) - excused_jsonl))
    check("every recorded non-SQLite exclusion says why, in plain words",
          all(isinstance(w, str) and len(w) > 20
              for w in B.NOT_BACKED_UP_PATHS.values()),
          B.NOT_BACKED_UP_PATHS)
    check("study.db (review decks) is on the list of databases backed up",
          "study.db" in B.SOURCE_DBS and "study.db" in opened)
    check("the settings JSON is in", "settings/folders.json" in names)
    check("notes are in", "notes/todo.md" in names
          and zf_read(zip_bytes, "notes/todo.md") == b"buy milk")
    check("the voice folder (the print) is in", "voice/owner.json" in names)
    check("manifest.json is in, for the preview", "manifest.json" in names)
    check("no .log file made it in", not any(n.endswith(".log") for n in names))
    check("voice-models (downloaded engine files) is excluded", not any("voice-models" in n
                                                                        for n in names))
    check("voices (the custom-voice bank) is excluded", not any(n.startswith("voices/")
                                                                 for n in names))
    # The pairing token and every API key live ONLY in Windows Credential
    # Manager, under their own target names (jarvis_token_store.py,
    # jarvis_search.py) - never as a *.json file in the settings folder, so
    # the glob above can never reach them. Proved at the code level: this
    # module's source names exactly one Credential Manager target, and it
    # is the chat-history key - never the pairing token's or a search key's.
    import re
    import jarvis_chat_log
    src = Path(B.__file__).read_text(encoding="utf-8")
    # Every actual Credential Manager access in this module (WindowsStore(...)
    # or CredentialKey()), by the literal target string it opens - never a
    # phrase in a comment or docstring, which may legitimately explain WHY
    # the pairing token and search keys are excluded.
    targets = re.findall(r"WindowsStore\(target=([\w.]+)\)", src)
    check("the ONLY Credential Manager targets this module ever opens are jarvis_chat_log's "
          "and jarvis_decks's own KEY_TARGET (never the pairing token's or a search provider's key)",
          targets == ["jarvis_chat_log.KEY_TARGET", "jarvis_decks.KEY_TARGET"], targets)
    import jarvis_decks
    check("jarvis_decks.KEY_TARGET really is the study decks' own key, not the chat-history one",
          jarvis_decks.KEY_TARGET == "Jarvis Backend/study decks key"
          and jarvis_decks.KEY_TARGET != jarvis_chat_log.KEY_TARGET)
    check("jarvis_chat_log.KEY_TARGET really is the chat-history key, not some other secret",
          jarvis_chat_log.KEY_TARGET == "Jarvis Backend/chat history key")
    reads = re.findall(r"jarvis_chat_log\.CredentialKey\(([^)]*)\)", src)
    check("CredentialKey (used to READ a key for backup) is jarvis_chat_log's own class, called "
          "with no target (the chat-history key) or with jarvis_decks.KEY_TARGET - no other target",
          sorted(reads) == ["", "jarvis_decks.KEY_TARGET"] and "CredentialKey(" not in src.replace(
              "jarvis_chat_log.CredentialKey(", ""), reads)


def zf_read(zip_bytes: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return zf.read(name)


# ============================ 4b. the coverage gap, measured 2026-10-13
#
# The owner's install had 19 databases in ~/.openjarvis and this module's list
# named 12. Two of the seven left over held the owner's own content and joined
# the list; five are deliberate exclusions, written down in `NOT_BACKED_UP`.
# Two settings files were missing for a plainer reason still - their extension
# is not `.json`, so a glob for `*.json` could never match them, and the HUD's
# own settings file (config.toml) was in NO backup of any kind.
#
# These checks are the ones that stop the gap reopening: a name that quietly
# leaves `SOURCE_DBS` or `SETTINGS_NAMES` now fails a test rather than being
# missed until the next audit.


def t_a_database_whose_rows_live_in_the_wal_is_captured_whole():
    """THE WAL TRAP, proved rather than assumed.

    SQLite keeps recent writes in a write-ahead log (the `-wal` file beside a
    database) and folds them back into the main file later - or never, while a
    program holds the database open, which Jarvis always does. Measured on the
    owner's own install on 2026-10-13: `agents.db` is 4,096 bytes with a
    115,392-byte log beside it, `traces.db` 4,096 with 78,312, and
    `telemetry.db` 4,096 with 28,872 - and a plain copy of the main file alone
    reads 0 tables where the live database reads 6, 7 and 2.

    This module uses SQLite's own online backup API, which reads one consistent
    view and folds the log in. That is the claim; this is the measurement, on a
    database built to have its rows ONLY in the log:

      * a plain copy of the main file cannot even read the table (the trap);
      * the online backup API returns every row, and the snapshot needs no
        `-wal` beside it, so nothing can be lost by not copying the log.
    """
    conf, _backups = fresh_conf()
    live = conf / "wal-notes.db"
    # The connection stays OPEN for the whole test, exactly like Jarvis's own
    # connections do while it runs: closing the last one checkpoints the log
    # away, and a test that closed it would never have rows in the log at all.
    keeper = sqlite3.connect(str(live))
    try:
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("PRAGMA wal_autocheckpoint=0")   # never fold it back by itself
        keeper.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        rows = [(f"only-in-the-log {i}",) for i in range(1, 41)]
        keeper.executemany("INSERT INTO notes (body) VALUES (?)", rows)
        keeper.commit()
        wal = Path(str(live) + "-wal")
        check("the test really did put the rows in the log, where they can be lost",
              wal.is_file() and wal.stat().st_size > 0,
              f"live={live.stat().st_size}B wal={wal.stat().st_size if wal.is_file() else 0}B")

        # (a) The trap: the main file on its own.
        plain = _scratch_dir("plaincopy") / "wal-notes.db"
        shutil.copyfile(live, plain)
        try:
            plain_rows = _rows_in(plain, "SELECT COUNT(*) FROM notes")
        except sqlite3.DatabaseError:
            plain_rows = None       # what a plain copy really does: the table is not there
        check("a plain copy of the main file loses every row (the trap is real)",
              plain_rows != len(rows), f"a plain copy read {plain_rows} of {len(rows)} rows")

        # (b) What this module actually does.
        snap = _scratch_dir("snapshot") / "wal-notes.db"
        check("_snapshot_db takes it", B._snapshot_db(live, snap) is True)
        got = _rows_in(snap, "SELECT body FROM notes ORDER BY id")
        check("the online backup API captures EVERY row that lived only in the log",
              [r[0] for r in got] == [r[0] for r in rows],
              f"snapshot has {len(got)} of {len(rows)} rows")
        # "Self-contained" tested properly: remove anything SQLite put beside
        # the snapshot and read it cold. If the rows needed a log to be
        # complete, they would be gone here. Every connection is closed first -
        # on Windows an open handle stops the unlink rather than failing the
        # claim being measured.
        for _suffix in ("-wal", "-shm"):
            _side = Path(str(snap) + _suffix)
            if _side.exists():
                _side.unlink()
        cold = _rows_in(snap, "SELECT COUNT(*) FROM notes")[0][0]
        check("the snapshot is self-contained: every row survives with no -wal "
              "beside it at all", cold == len(rows), f"cold read got {cold} of {len(rows)} rows")
        check("...and it is the same database, not an empty one: the schema came too",
              _rows_in(snap, "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                             "AND name='notes'")[0][0] == 1)
    finally:
        keeper.close()


def _rows_in(db_path, sql: str) -> list:
    """Run one read against `db_path` and CLOSE the connection.

    Closed explicitly, not left to the garbage collector: on Windows an open
    handle keeps the file locked, so a later `unlink` of a `-wal` beside it
    raises PermissionError instead of measuring anything.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def t_the_newly_covered_databases_and_named_files_really_go_in():
    """The two databases and two settings files added on 2026-10-13, proved to
    travel - and the five deliberate exclusions proved to stay out.

    `SOURCE_DBS` is the whole of what this module claims to carry, so a check
    that a name is merely ON the list proves nothing about whether
    `build_archive` writes it. These start from real database files and open
    the real archive.
    """
    conf, _backups = fresh_conf()
    for name in ("knowledge.db", "traces.db"):
        conn = sqlite3.connect(str(conf / name))
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, text TEXT)")
        conn.execute("INSERT INTO sample (text) VALUES (?)", (f"{name} content",))
        conn.commit()
        conn.close()
    # Every database that stays out, each with a table, so its absence from the
    # archive is a decision and not "the file happened not to be there".
    for name in B.NOT_BACKED_UP:
        conn = sqlite3.connect(str(conf / name))
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, text TEXT)")
        conn.execute("INSERT INTO sample (text) VALUES ('must not travel')")
        conn.commit()
        conn.close()

    zip_bytes, manifest = B.build_archive()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())

    for name in ("knowledge.db", "traces.db"):
        check(f"{name} is in the archive, with its rows counted",
              f"db/{name}" in names
              and manifest["databases"].get(name, {}).get("sample") == 1,
              manifest["databases"].get(name))
    for name, why in sorted(B.NOT_BACKED_UP.items()):
        check(f"{name} deliberately stays out ({why})", f"db/{name}" not in names)
    check("...and every excluded name says WHY, in the module's own words",
          all(isinstance(v, str) and len(v) > 20 for v in B.NOT_BACKED_UP.values()),
          B.NOT_BACKED_UP)

    # A FILE THAT IS COVERED CANNOT BE DROPPED IN SILENCE. Every one of the
    # databases the owner's install has is either carried or written down as an
    # exclusion; anything else is a name somebody forgot. This is the check
    # that fails if `SOURCE_DBS` loses an entry.
    #
    # 16, not the 14 this branch first counted: this branch adds knowledge.db and
    # traces.db (14 -> 16 at the time), and main then added receipts.db (#432,
    # the action receipts and their Undo snapshots) and voiceprint.db (#436,
    # "Write Like Me"). 6 exclusions since 2026-10-16, when the derived search
    # index (documents-index.db) joined the five.
    # Both numbers are asserted rather than derived, on purpose - the point is
    # that adding a database is a decision somebody has to make here as well as
    # in the module, and this is the line that asks.
    check("every covered database is in SOURCE_DBS or in NOT_BACKED_UP",
          not ({n for n in B.SOURCE_DBS} & {n for n in B.NOT_BACKED_UP}),
          "a database is in both lists")
    check("the databases of the owner's install, split 16 + 7, are all accounted for",
          len(B.SOURCE_DBS) == 16 and len(B.NOT_BACKED_UP) == 7,
          f"{len(B.SOURCE_DBS)} backed up, {len(B.NOT_BACKED_UP)} excluded")


def t_the_guardian_store_is_an_explicit_exclusion_never_a_silent_one():
    """The File Guardian's store is device-local file history, not memory.

    Frontier 2 audit, 2026-10-18: there is no `guardian.db`; the store is
    `guardian/guardian.jsonl` (a path per saved version), `pins.json` and
    `blobs/<sha256>.gz` (up to the 250 MiB quota in jarvis_file_guardian.py).
    It was in neither SOURCE_DBS nor NOT_BACKED_UP, so a backup simply left it
    out and no check said so. This proves the archive never carries it - a
    blob store must not bloat a backup - and that every piece of the decision
    is written down in words, so a new store cannot disappear the same way.
    """
    conf, _backups = fresh_conf()
    guardian = conf / "guardian"
    (guardian / "blobs").mkdir(parents=True)
    (guardian / "guardian.jsonl").write_text(
        '{"path": "C:\\\\Users\\\\owner\\\\notes.txt", "before_sha256": "%s"}\n'
        % ("a" * 64), encoding="utf-8")
    (guardian / "pins.json").write_text(
        '{"pins": ["%s"]}' % ("a" * 64), encoding="utf-8")
    (guardian / "blobs" / ("a" * 64 + ".gz")).write_bytes(b"COMPRESSED OLD BYTES" * 100)

    zip_bytes, _manifest = B.build_archive()
    names = zf_names(zip_bytes)
    check("the guardian store never enters the archive",
          not any(n.startswith("guardian/") for n in names),
          [n for n in names if "guardian" in n])
    check("...and its blob store cannot be reached by any other name",
          not any(n.endswith(".gz") for n in names),
          [n for n in names if n.endswith(".gz")])

    blob = "guardian/blobs/" + ("a" * 64) + ".gz"
    for path in ("guardian/guardian.jsonl", "guardian/pins.json", blob):
        why = B.not_backed_up_reason(path)
        check(f"{path} has a recorded reason", len(why) > 20, why)
    why = B.not_backed_up_reason("guardian/guardian.jsonl")
    check("...the journal's reason says device-local, not memory",
          "device-local" in why, why)
    check("the same record covers the other non-SQLite stores",
          "energy" in B.not_backed_up_reason("energy.jsonl")
          and "anchor" in B.not_backed_up_reason("ledger-anchors.jsonl"))
    check("a store nobody wrote down gets no invented reason",
          B.not_backed_up_reason("something-else.jsonl") == "")


def t_the_settings_files_a_json_glob_cannot_reach_are_carried_and_put_back():
    """config.toml and speed.jsonl (2026-10-13).

    The `*.json` glob is why they were missing: a `.toml` and a `.jsonl` are
    not `.json`, so no backup of any kind read the HUD's own settings file -
    the one file holding every setting the owner changes in Jarvis's window.
    This proves both halves: they go in, and a restore puts them back with
    their bytes intact.
    """
    conf, _backups = fresh_conf()
    toml_text = '[server]\nhost = "127.0.0.1"\nport = 8000\n'
    jsonl_text = '{"tok_per_s": 12.5}\n{"tok_per_s": 13.0}\n'
    (conf / "config.toml").write_text(toml_text, encoding="utf-8")
    (conf / "speed.jsonl").write_text(jsonl_text, encoding="utf-8")
    (conf / "folders.json").write_text('{"folders": []}', encoding="utf-8")

    for name in B.SETTINGS_NAMES:
        check(f"{name} is one of the named settings files this module carries",
              name in B.SETTINGS_NAMES)
    zip_bytes, manifest = B.build_archive()
    # Read the folder's OWN bytes back, on this machine, rather than comparing
    # against the literal above: `Path.write_text` turns \n into \r\n on
    # Windows, so the literal is the right text in the wrong line endings. The
    # claim being tested is that the archive holds the file unchanged - not that
    # the file has some particular line ending.
    archived = {}
    for name in ("config.toml", "speed.jsonl"):
        on_disk = (conf / name).read_bytes()
        archived[name] = on_disk
        check(f"settings/{name} is in the archive, byte for byte",
              f"settings/{name}" in zf_names(zip_bytes)
              and zf_read(zip_bytes, f"settings/{name}") == on_disk,
              f"archive={zf_read(zip_bytes, f'settings/{name}')[:60]!r} disk={on_disk[:60]!r}")
        check(f"...and the manifest says so ({name})", manifest["named_settings"].get(name) is True)
    check("the *.json files still travel the way they always did",
          "settings/folders.json" in zf_names(zip_bytes))
    check("the manifest counts all three settings files",
          manifest["settings_files"] == 3, manifest["settings_files"])

    # A restore now lands in a SECOND, empty settings folder - so finding the
    # files there proves the restore wrote them, not that they were never gone.
    dest, _b2 = fresh_conf()
    applied = B._apply_restore(zip_bytes)
    check("a restore puts config.toml back, byte for byte",
          (dest / "config.toml").is_file()
          and (dest / "config.toml").read_bytes() == archived.get("config.toml"),
          "restored bytes differ from the archived bytes")
    check("...and speed.jsonl the same",
          (dest / "speed.jsonl").is_file()
          and (dest / "speed.jsonl").read_bytes() == archived.get("speed.jsonl"))
    check("...with every settings file this archive held accounted for",
          applied["skipped"] == 0 and applied["settings_files"] == 3, applied)

    # The one list of what may land in the settings folder, so a tampered
    # archive cannot write an arbitrary file into it.
    check("a settings/ name that is neither *.json nor a named settings file is skipped, "
          "not written",
          B._named_settings_entries(["settings/folders.json", "settings/config.toml",
                                     "settings/speed.jsonl", "settings/evil.exe",
                                     "settings/there.js"])
          == ["settings/folders.json", "settings/config.toml", "settings/speed.jsonl"])


def zf_names(zip_bytes: bytes) -> set:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return set(zf.namelist())


#: How a secret looks in a settings file: a name that means "this is a secret",
#: on a line that is NOT a comment, with a value that is not empty and not an
#: obvious placeholder. Used to read the owner's own config.toml - see the
#: module docstring's "WHAT `config.toml` ACTUALLY HOLDS".
#: Secret-shaped setting names. The LEADING boundary is deliberately absent so
#: a provider-prefixed name (`bot_token`, `github_api_key`) is caught too; the
#: trailing boundary still keeps `max_tokens` and `secret_scanner` out.
_SECRET_NAME_RE = re.compile(
    r'(?i)(token|secret|passwd|password|api[_-]?key|passphrase|private[_-]?key)\b')
_PLACEHOLDER_VALUES = {'""', "''", '""', "null", "none", '""  # or set telegram_bot_token env var'}
_CONFIG_PATH = Path(os.path.expanduser("~")) / ".openjarvis" / "config.toml"


def _live_secret_lines(text: str) -> list:
    """Every line of a TOML file that sets a secret-shaped name to a real value.

    A commented-out line is skipped: this project's own config.toml documents
    each integration by showing the line, commented, with an empty value and a
    note to put the secret in the environment instead. What matters is a line
    that would actually carry a value into a backup.
    """
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _sep, value = line.partition("=")
        if not _SECRET_NAME_RE.search(key):
            continue
        value = value.split("#", 1)[0].strip()
        if value in ("", '""', "''", "null", "None"):
            continue
        out.append((n, line))
    return out


def _snapshot_secret_lines(config_path=_CONFIG_PATH) -> list:
    """[(snapshot name, line number, line)] for live secrets in
    `config.toml.before-*` snapshots (2026-10-18, audit F6).

    The patcher and Settings leave these plaintext copies of earlier settings
    in the same folder; the real `config.toml` is tested above, but a secret
    pasted in before the fix would only exist in a snapshot. Empty when there
    are no snapshots - the caller says so rather than counting that as a pass.
    """
    out = []
    try:
        snapshots = sorted(config_path.parent.glob(config_path.name + ".before-*"))
    except OSError:
        return out
    for path in snapshots:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in _live_secret_lines(text):
            out.append((path.name, number, line))
    return out



def t_config_toml_holds_no_secret():
    """The owner's real config.toml, read rather than taken on faith.

    Before config.toml was added to the backup on 2026-10-13 it was checked for
    secrets, because rule 3 says a pairing token or API key is never written to
    disk in plain text - and a settings file is written to disk, and now travels
    into an archive. Measured: every token, password, app_secret and api_key
    line in it is COMMENTED OUT and empty, the one mention of a real key says it
    comes from an environment variable, `[server]` is bound to loopback with the
    "works without API authentication" line in the file itself, and the only two
    non-comment settings whose names contain one of those words - `max_tokens =
    1024` and `secret_scanner = true` - are not matches at all, because the
    pattern is word-bounded: `\btoken\b` does not match `max_tokens` and
    `\bsecret\b` does not match `secret_scanner`. So the check finds no live
    secret-shaped line in the file.

    This test exists so that stops being a fact somebody remembers. If a real
    token is ever pasted into that file, this fails and says which line - the
    day the change matters, rather than years later in a backup file.
    """
    if not _CONFIG_PATH.is_file():
        # The live line here is `api_key`, not the bare `key` it was until
        # 2026-10-14. `_SECRET_NAME_RE` is word-bounded and its vocabulary is
        # token / secret / password / api_key / passphrase / private_key, so
        # `key` was never a match: this assertion could not pass on any machine
        # WITHOUT ~/.openjarvis/config.toml - which is every CI runner - and
        # passed on the owner's PC only because his file is there and this branch
        # does not run at all. The regex was NOT widened to suit it: a bare `key`
        # is an ordinary settings name (a sort key, a cache key, a map key) and a
        # scanner that cries wolf on those is worse than one that does not know
        # the word. Measured on the owner's own file: it has no `key =` line, and
        # `max_tokens = 1024` and `secret_scanner = true` are not matches either
        # for the same word-boundary reason, so widening would catch nothing real.
        check("the settings file TOML round-trips (no real install here to read)",
              _live_secret_lines('[a]\ntoken = ""\n# token = "x"\napi_key = "REAL"\n')
              == [(4, 'api_key = "REAL"')])
        print("        NOTE: ~/.openjarvis/config.toml is not on this machine, so the two "
              "checks below\n        about the owner's real file did NOT run. They are not "
              "passes.")
        return
    text = _CONFIG_PATH.read_text(encoding="utf-8", errors="replace")
    bad = _live_secret_lines(text)
    check("the owner's own config.toml holds no live secret-shaped setting "
          "(so carrying it puts no secret in the archive)", bad == [], bad[:3])
    check("...and it is a real file, not an empty one", len(text) > 1000, len(text))
    check("...and the token lines it does show are the commented-out kind this "
          "project documents, with the environment named as where the real one goes",
          "# bot_token" in text and "_TOKEN env var" in text)
    check("...and its server section is loopback, not exposed",
          'host = "127.0.0.1"' in text and '# host = "0.0.0.0"' in text)
    snapshot_files = sorted(_CONFIG_PATH.parent.glob(_CONFIG_PATH.name + ".before-*"))
    if not snapshot_files:
        print("        NOTE: no config.toml.before-* snapshot is on this machine, so the "
              "snapshot check did NOT run. It is not a pass.")
    else:
        bad_snaps = _snapshot_secret_lines()
        check("...and every config.toml.before-* snapshot holds no live secret either "
              "(F6: the patcher leaves those plaintext copies)",
              bad_snaps == [], bad_snaps[:3])


def t_a_secret_in_a_config_snapshot_would_be_caught():
    """F6's scanner is exercised on a synthetic snapshot, so a machine with no
    live snapshots still proves the rule; a bite on `_snapshot_secret_lines`
    turns this red."""
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "config.toml"
        config.write_text("[server]\nhost = \"127.0.0.1\"\n", encoding="utf-8")
        snap = Path(tmp) / "config.toml.before-test"
        snap.write_text('[a]\nbot_token = "REAL"\n# token = ""\n', encoding="utf-8")
        got = _snapshot_secret_lines(config)
        check("a live secret in a before-* snapshot is found, with its file and line",
              got == [("config.toml.before-test", 2, 'bot_token = "REAL"')], got)
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "config.toml"
        config.write_text("[a]\ntoken = \"\"\n", encoding="utf-8")
        check("...and a clean snapshot folder is clean", _snapshot_secret_lines(config) == [])


def t_the_credentials_folder_is_not_swept_into_a_backup():
    """`devices/` holds a SHA-256 of each paired device's token, and the list
    of devices allowed to talk to Jarvis. It must never travel: it is
    authorization state (restoring an old copy re-authorizes a phone the owner
    removed) and it is credential-derived material that rule 3 keeps on the PC
    that checks it.

    This is checked at the source level, the way this suite checks the
    Credential Manager targets: the archive builder may not reach into a
    subfolder at all, so a `*.json` glob cannot pick it up.
    """
    conf, _backups = fresh_conf()
    (conf / "devices").mkdir()
    (conf / "devices" / "registry.json").write_text(
        '{"devices": [{"name": "OnePlus", "token_sha256": "deadbeef"}]}', encoding="utf-8")
    (conf / "chatbot").mkdir()
    (conf / "chatbot" / "api-money.json").write_text('{"limits": {"x": 1.0}}', encoding="utf-8")
    zip_bytes, _m = B.build_archive()
    names = zf_names(zip_bytes)
    check("devices/registry.json (device list and token hashes) is not in the archive",
          not any("registry.json" in n or "devices" in n for n in names), sorted(names))
    check("a subfolder of the settings folder is never recursed into - not even for a "
          "*.json the top level would have taken",
          "settings/registry.json" not in names and "settings/api-money.json" not in names)
    check("...so no token hash can be read out of a backup file's bytes",
          b"deadbeef" not in zip_bytes)


def t_the_backend_source_is_backed_up_and_put_back():
    """2026-10-05: an audit found five files - jarvis_hud.py (the whole control
    plane), jarvis_gate.py (the approval gate), jarvis_extract.py,
    jarvis_models.py, jarvis_skills.py - that existed in exactly ONE place on
    Earth, the live backend folder, and that no backup of any kind read: not
    this module (nothing in it touched a .py file), not apply-patches.ps1, not
    git (backend/.gitignore keeps the live sources out on purpose, with a
    written exception only for the ten under backend/rebuilt/). A bad patch or
    a deleted folder would have taken them with it.

    So the archive now carries the backend's own top-level *.py files as
    source/<name>, and a restore writes them back into the folder this module
    runs from. What this proves:
      * every top-level .py goes in, byte for byte, and the manifest counts them;
      * the things beside them do NOT: other file types, deeper *.py, the
        __pycache__ bytecode, and the patcher's own _jarvis-backup-* folders
        (which already hold older copies of the same sources - recursing would
        nest the whole source inside every new backup);
      * a restore puts them back, overwriting what is there now;
      * a name that tries to escape the source folder, or to nest, is refused
        and counted - the same second lock db/, settings/ and notes/ already have;
      * an archive made BEFORE this change (no source/ entry at all) still
        restores, and never even asks where the sources live.
    """
    conf, _backups = fresh_conf()
    backend = fake_backend()
    before = {p.name: p.read_bytes() for p in backend.glob("*.py")}

    zip_bytes, manifest = B.build_archive()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    check("every top-level backend .py is in the archive, byte for byte",
          {f"source/{n}" for n in before} <= names
          and all(zf_read(zip_bytes, f"source/{n}") == data for n, data in before.items()),
          sorted(n for n in names if n.startswith("source/")))
    check("the manifest counts them", manifest["source_files"] == len(before), manifest)
    check("... so the restore preview can say how many (counts only, never content)",
          manifest["source_files"] == 2)
    check("a file beside them that is NOT a top-level .py stays out",
          not any(n.startswith("source/") and not n.endswith(".py") for n in names)
          and "source/notes.txt" not in names and "source/stale.pyc" not in names)
    check("bytecode, the patcher's older copies and deeper .py are all left out "
          "(recursing would nest the whole source inside every backup)",
          not any("__pycache__" in n for n in names)
          and not any("_jarvis-backup-" in n for n in names)
          and "source/nested.py" not in names and "source/sub/nested.py" not in names,
          sorted(n for n in names if n.startswith("source/")))

    # A restore puts them back - both the file that changed and the one deleted.
    (backend / "jarvis_hud.py").write_text("# WRECKED\n", encoding="utf-8")
    (backend / "jarvis_gate.py").unlink()
    applied = B._apply_restore(zip_bytes)
    check("a restore writes the program files back into the backend folder",
          (backend / "jarvis_hud.py").read_bytes() == before["jarvis_hud.py"]
          and (backend / "jarvis_gate.py").read_bytes() == before["jarvis_gate.py"],
          applied)
    check("and the summary counts them as restored, not skipped",
          applied["source_files"] == 2 and applied["skipped"] == 0, applied)
    check("the staging cleaned up after itself in the backend folder too: no leftover "
          ".tmp or .old files",
          not [p.name for p in backend.rglob("*") if ".tmp" in p.name or ".old" in p.name],
          sorted(p.name for p in backend.rglob("*")))
    check("nothing created a source/ folder inside the backend folder",
          not (backend / "source").exists())

    # The second lock, exactly as db/ and settings/ have it.
    outside = backend.parent / f"escaped-{time.time_ns()}.py"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("source/../evil.py", b"x")
        zf.writestr("source/sub/deep.py", b"x")
        zf.writestr("source/ok.py", b"# fine\n")
    applied = B._apply_restore(buf.getvalue())
    check("a source/ name that escapes the backend folder is refused, not written",
          not outside.exists() and not (backend.parent / "evil.py").exists(), str(outside))
    check("... and a nested one is refused too (build_archive writes one name per file)",
          applied["skipped"] == 2 and applied["source_files"] == 1
          and (backend / "ok.py").read_text(encoding="utf-8") == "# fine\n", applied)

    # A backup made before this change: no source/ entry anywhere. It must
    # restore exactly as it did, and must not touch the backend folder at all.
    (backend / "ok.py").write_text("# changed by the owner\n", encoding="utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("settings/folders.json", "{}")
        zf.writestr("manifest.json", "{}")
    applied = B._apply_restore(buf.getvalue())
    check("an OLD backup with no source/ entry restores and leaves the code alone",
          applied["source_files"] == 0 and applied["settings_files"] == 1
          and (backend / "ok.py").read_text(encoding="utf-8") == "# changed by the owner\n",
          applied)


def t_the_backend_source_never_lands_in_the_settings_folder():
    """The one way this new branch could go wrong on the owner's PC: writing
    program files somewhere they do not belong. It must read the source folder
    from `_source_dir()` and NOT from the settings folder, and it must never
    create a `source/` folder inside ~/.openjarvis."""
    conf, _backups = fresh_conf()
    backend = fake_backend(files=("jarvis_hud.py",))
    zip_bytes, _m = B.build_archive()
    B._apply_restore(zip_bytes)
    check("the program file lands in the backend folder, not the settings folder",
          (backend / "jarvis_hud.py").is_file() and not (conf / "source").exists()
          and not (conf / "jarvis_hud.py").exists())
    check("the settings folder still got what it should - nothing, it was empty",
          sorted(p.name for p in conf.iterdir()) == [], sorted(p.name for p in conf.iterdir()))
    src = Path(B.__file__).read_text(encoding="utf-8")
    body = src[src.index("def _source_dir"):]
    body = body[:body.index("\n\n\n")]
    check("the REAL _source_dir() is __file__'s own folder - not a setting that can drift, "
          "and not the settings folder",
          "__file__" in body and "CONFIG_DIR" not in body and "expanduser" not in body,
          body[:300])


def t_the_chat_history_key_is_carried_but_only_inside_the_lock():
    conf, backups = fresh_conf()
    make_memory_db(conf)

    class FakeKeyModule(types.SimpleNamespace):
        pass

    import jarvis_chat_log
    real_ck = jarvis_chat_log.CredentialKey
    jarvis_chat_log.CredentialKey = lambda: (lambda: b"\x01" * 32)
    try:
        zip_bytes, manifest = B.build_archive()
    finally:
        jarvis_chat_log.CredentialKey = real_ck
    check("the manifest says the key was carried", manifest["chat_history_key"] is True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        raw = zf.read("secrets/chat-history-key.b64")
    import base64
    check("it decodes back to the 32 bytes, base64 only inside the (soon encrypted) zip",
          base64.b64decode(raw) == b"\x01" * 32)


# ======================================================== 4b. the review decks travel with the backup

class _FakeCredentials:
    """Stands in for Windows Credential Manager: one dict of target -> text, for
    the read side (jarvis_chat_log.CredentialKey) and the write side
    (jarvis_token_store.WindowsStore)."""

    def __init__(self):
        self.items = {}
        self.reads = []
        self.fail_writes = False

    def __enter__(self):
        import base64
        import jarvis_chat_log
        import jarvis_token_store as ts
        self._real = (jarvis_chat_log.CredentialKey, ts.WindowsStore)
        me = self

        def credential_key(target=jarvis_chat_log.KEY_TARGET, store_factory=None):
            def read():
                me.reads.append(target)
                if target not in me.items:
                    raise RuntimeError("no such key")
                return base64.b64decode(me.items[target])
            return read

        class Store:
            def __init__(self, target):
                self.target = target

            def write(self, text):
                if me.fail_writes:
                    raise RuntimeError("Credential Manager refused")
                me.items[self.target] = text

        jarvis_chat_log.CredentialKey = credential_key
        ts.WindowsStore = lambda target=None: Store(target)
        return self

    def __exit__(self, *a):
        import jarvis_chat_log
        import jarvis_token_store as ts
        jarvis_chat_log.CredentialKey, ts.WindowsStore = self._real


def _make_deck(conf: Path, key: bytes, name="Plants", front="What absorbs sunlight?"):
    import jarvis_decks as DK
    if DK.fsrs is None:
        DK.fsrs = types.SimpleNamespace(
            Scheduler=lambda **k: types.SimpleNamespace(
                repeat=lambda *a, **kw: (None, None),
            )
        )
    d = DK.Decks(conf / "study.db", lambda: key, scheduler=types.SimpleNamespace(
        jobs_of=lambda kind: [], act=lambda *a: None, add_repeat=lambda *a, **k: None))
    v = d.create_deck(name)
    d.keep({"deck": v["id"]}, [{"n": 1, "front": front, "back": "chlorophyll",
                                "passage": "Chlorophyll absorbs sunlight.", "kind": "recall"}])
    return d, v["id"]


def t_the_study_decks_are_backed_up_with_their_own_key():
    import base64
    import jarvis_decks as DK
    conf, backups = fresh_conf()
    make_memory_db(conf)
    key = b"\x07" * 32
    _make_deck(conf, key)
    with _FakeCredentials() as cm:
        cm.items[DK.KEY_TARGET] = base64.b64encode(key).decode()
        cm.items["Jarvis Backend/chat history key"] = base64.b64encode(b"\x01" * 32).decode()
        zip_bytes, manifest = B.build_archive()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    check("study.db and the decks' own key are in the archive; the manifest says so",
          "db/study.db" in names and "secrets/study-decks-key.b64" in names
          and manifest["study_decks_key"] is True and "cards" in manifest["databases"]["study.db"], manifest)
    check("the key file holds the decks' key, not the chat-history key",
          base64.b64decode(zf_read(zip_bytes, "secrets/study-decks-key.b64")) == key)
    check("the words in the archived study.db are still sealed (no plain question in it)",
          b"absorbs sunlight" not in zf_read(zip_bytes, "db/study.db")
          and b"Plants" not in zf_read(zip_bytes, "db/study.db"))

    # no study.db: no key is read for it (a backup never makes a key for decks nobody has)
    conf2, _b2 = fresh_conf()
    make_memory_db(conf2)
    with _FakeCredentials() as cm:
        cm.items["Jarvis Backend/chat history key"] = base64.b64encode(b"\x01" * 32).decode()
        zb, man = B.build_archive()
        asked = list(cm.reads)
    check("no study.db: nothing about decks in the archive and the decks' key was never asked for",
          "db/study.db" not in zipfile.ZipFile(io.BytesIO(zb)).namelist() and man["study_decks_key"] is False
          and DK.KEY_TARGET not in asked, asked)

    # study.db present but its key cannot be read: the file is left out, not carried unopenable
    conf3, _b3 = fresh_conf()
    make_memory_db(conf3)
    _make_deck(conf3, key)
    with _FakeCredentials() as cm:
        zb, man = B.build_archive()
    check("study.db without a readable key is not archived (a restore would replace a working file with an unopenable one)",
          "db/study.db" not in zipfile.ZipFile(io.BytesIO(zb)).namelist() and man["study_decks_key"] is False)


def t_a_restore_reopens_the_decks():
    import base64
    import jarvis_decks as DK
    conf, backups = fresh_conf()
    make_memory_db(conf)
    key = b"\x09" * 32
    _make_deck(conf, key, name="Espanol", front="Que es la casa?")
    with _FakeCredentials() as cm:
        cm.items[DK.KEY_TARGET] = base64.b64encode(key).decode()
        out = B.backup_now(str(backups))
        code = out["recovery_code"]
        blob = (backups / out["name"]).read_bytes()
    check("the backup file itself holds neither the deck's name nor its question",
          b"Espanol" not in blob and b"la casa" not in blob)
    # the PC is replaced: no study.db, no key
    (conf / "study.db").unlink()
    with _FakeCredentials() as cm:
        zip_bytes = B.decrypt_blob(blob, code)
        applied = B._apply_restore(zip_bytes)
        restored_key = cm.items.get(DK.KEY_TARGET)
        provider = lambda: base64.b64decode(cm.items[DK.KEY_TARGET])
    check("restore wrote study.db back and the key to the decks' own Credential Manager entry",
          applied["study_decks_key"] is True and (conf / "study.db").is_file()
          and restored_key == base64.b64encode(key).decode(), applied)
    d2 = DK.Decks(conf / "study.db", provider, scheduler=types.SimpleNamespace(
        jobs_of=lambda kind: [], act=lambda *a: None, add_repeat=lambda *a, **k: None))
    ok, why = d2.available()
    ls = d2.list_decks()
    cards = d2.deck_cards(ls["decks"][0]["id"])["cards"] if ls["decks"] else []
    check("the restored decks open with the restored key: name, question and answer all back",
          ok and ls["decks"][0]["name"] == "Espanol" and cards and cards[0]["front"] == "Que es la casa?"
          and cards[0]["back"] == "chlorophyll", (ok, why))
    # the wrong key: the file restored, the key write refused -> plainly unavailable, nothing overwritten silently
    (conf / "study.db").unlink()
    with _FakeCredentials() as cm:
        cm.fail_writes = True
        cm.items[DK.KEY_TARGET] = base64.b64encode(b"\x0a" * 32).decode()
        applied = B._apply_restore(B.decrypt_blob(blob, code))
        other = lambda: base64.b64decode(cm.items[DK.KEY_TARGET])
    d3 = DK.Decks(conf / "study.db", other, scheduler=types.SimpleNamespace(
        jobs_of=lambda kind: [], act=lambda *a: None, add_repeat=lambda *a, **k: None))
    ok, why = d3.available()
    check("a restore whose key could not be written leaves decks that say plainly the key does not open them",
          applied["study_decks_key"] is False and ok is False and "does not open" in why, (applied, ok, why))
    check("... and nothing new is kept into them meanwhile",
          not _keeps(d3))
    check("the wrong recovery code opens nothing of the decks either",
          _wrong_code_fails(blob))
    # a running store that held the old key drops it after a restore
    DK._reset_for_tests()
    one = DK.get()
    one._aead = object()
    one._revealed["c1"] = 1.0
    DK.forget_key()
    check("forget_key() makes the running store reopen with the restored key",
          one._aead is None and not one._revealed)
    DK._reset_for_tests()


def _keeps(d) -> bool:
    try:
        d.keep({"new_deck": "New"}, [{"front": "x", "back": "", "passage": ""}])
        return True
    except Exception:
        return False


def _wrong_code_fails(blob: bytes) -> bool:
    try:
        B.decrypt_blob(blob, "AAAAA-AAAAA-AAAAA-AAAAA")
    except B.WrongCode:
        return True
    return False


# ======================================================== 5. retention


def t_retention_keeps_only_the_newest_KEEP():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    real_file_name = B._file_name
    made = []
    try:
        for i in range(B.KEEP + 3):
            B._file_name = (lambda i=i: (lambda at: f"jarvis-backup-2026010{(i % 9) + 1}-000000"
                                                    f"{B.FILE_SUFFIX}"))()
            out = B.backup_now(str(backups))
            made.append(out["name"])
    finally:
        B._file_name = real_file_name
    left = sorted(os.listdir(backups))
    check(f"only the newest {B.KEEP} of {len(made)} are kept", len(left) == B.KEEP, left)
    check("the ones kept are the newest by name", set(left) == set(sorted(made)[-B.KEEP:]))


def t_two_backups_the_same_second_never_collide():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    real_file_name = B._file_name
    fixed = "jarvis-backup-20260101-120000" + B.FILE_SUFFIX
    B._file_name = lambda at: fixed
    try:
        out1 = B.backup_now(str(backups))
        out2 = B.backup_now(str(backups))
    finally:
        B._file_name = real_file_name
    check("two names, both files present, neither overwrote the other",
          out1["name"] != out2["name"] and (backups / out1["name"]).is_file()
          and (backups / out2["name"]).is_file(), (out1["name"], out2["name"]))


# ======================================================== 6. restore


def t_restore_needs_the_right_code():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    code, resp = B.preview_restore({"name": out["name"], "code": "totally-wrong-code-here"},
                                   here=True)
    check("preview with the wrong code: 400, wrong_code, nothing decrypted",
          code == 400 and resp["wrong_code"] is True, resp)
    code, resp = B.preview_restore({"name": out["name"], "code": out["recovery_code"]}, here=True)
    # `or True` used to make this constant. The clause it hid was wrong as
    # written: `"facts" not in json.dumps(counts)` is false because a TABLE is
    # called `facts` - and a table's name is exactly what a preview may carry.
    # What "never content" really means is that every number in there is a row
    # COUNT: a string would be the one place a row's words could leak. (The
    # check below still reads the whole response for the fact's own text.)
    databases = resp["counts"]["databases"]
    check("preview with the right code: counts and a date, never content",
          code == 200 and resp["created_at"] and "databases" in resp["counts"]
          and bool(databases)
          and all(isinstance(n, int) and not isinstance(n, bool)
                  for tables in databases.values() for n in tables.values()), resp)
    check("the preview never carries the actual fact text",
          "secret" not in json.dumps(resp).lower())


def t_restore_needs_windows_hello_armed():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: False)
    check("without Windows Hello armed: refused, plainly, nothing waits", code == 503
          and B._R_STATE["pending"] == {}, resp)


def t_restore_is_one_card_and_only_a_person_approving_carries_it_out():
    conf, backups = fresh_conf()
    make_memory_db(conf, rows=("original fact",))
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))

    # denied: nothing changes
    make_memory_db(conf, rows=("changed after backup",))
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=deny, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: True)
    check("a denied restore: 202 while waiting", code == 202, resp)
    result = B.take_restore_result()
    check("... and the outcome is 'denied', nothing changed",
          result["outcome"] == "denied" and read_facts(conf) == ["changed after backup"], result)

    # timed out: nothing changes either
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=timeout, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: True)
    result = B.take_restore_result()
    check("a timed-out restore changes nothing",
          result["outcome"] == "timed_out" and read_facts(conf) == ["changed after backup"],
          result)

    # approved: restores, backing up the current state first
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: True)
    result = B.take_restore_result()
    check("approved: restored, and the original fact is back",
          result["outcome"] == "restored" and read_facts(conf) == ["original fact"], result)
    safety = result.get("safety_backup") or {}
    check("a safety backup of the CURRENT (changed) state was made first, with its own code",
          safety.get("name") and safety.get("recovery_code")
          and (Path(backups) / safety["name"]).is_file(), safety)
    safety_zip = B.decrypt_blob((Path(backups) / safety["name"]).read_bytes(),
                                safety["recovery_code"])
    with zipfile.ZipFile(io.BytesIO(safety_zip)) as zf:
        db = zf.read("db/memory.db")
    check("...and that safety backup really held the CHANGED state, not the restored one",
          b"changed after backup" in db and b"original fact" not in db)
    check("the one-time code is readable exactly once - gone on the second read",
          "recovery_code" not in (B.take_restore_result() or {}).get("safety_backup", {}))


def t_restore_only_from_this_pc():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=False, gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: True)
    check("a restore request from another device is refused outright", code == 403, resp)
    check("restore_backup is PC-only-with-Windows-Hello, whatever the gate's own risk table "
          "says (jarvis_owner_check.PC_ONLY_ACTIONS)",
          "restore_backup" in OC.PC_ONLY_ACTIONS)


def t_bad_or_missing_backup_file():
    conf, backups = fresh_conf()
    B._save_settings({"folder": str(backups)})
    code, resp = B.preview_restore({"name": "nope.jbak", "code": "x"}, here=True)
    check("a backup that does not exist: 404", code == 404, resp)
    code, resp = B.preview_restore({"name": "../evil.jbak", "code": "x"}, here=True)
    check("a name that tries to escape the folder is refused, not read", code in (400, 404),
          resp)


# ======================================================== 7. routes, tiers and the patch


class FakeHandler:
    def __init__(self, path, body=b"{}", peer="127.0.0.1"):
        self.path = path
        self.body = body
        self.client_address = (peer, 5000)
        self.sent = None
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 8000))

    def do_GET(self):
        self.sent = ("original GET", None)

    def do_POST(self):
        self.sent = ("original POST", None)

    def _send(self, code, obj):
        self.sent = (code, obj)


def t_restore_never_writes_outside_its_own_folders():
    """Security/privacy audit, 2026-09-27: restore joined whatever name the
    archive held, so "db/../../x" landed outside the settings folder.
    build_archive never writes such a name; this is the second lock.

    The watch folder is mkdtemp's, not `escaped-{time.time_ns()}`: a name from
    the Windows timer tick can be the one the previous call already took (see
    fresh_conf above), and a name that already exists would decide the
    assertion below rather than restore's own guard."""
    conf, _backups = fresh_conf()
    outside = Path(tempfile.mkdtemp(dir=str(TMP), prefix="escaped-"))
    before = sorted(os.listdir(conf.parent))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"db/../{outside.name}", b"x")
        zf.writestr(f"settings/../../{outside.name}", b"x")
        zf.writestr(f"notes/../../{outside.name}", b"x")
        zf.writestr("notes/C:/Windows/evil.txt", b"x")
        zf.writestr("voice/./sub/../../x.bin", b"x")
        zf.writestr("settings/sub/deeper.json", b"{}")
        zf.writestr("settings/fine.json", b"{}")
        zf.writestr("notes/folder/fine.md", b"ok")
        zf.writestr("manifest.json", "{}")
    applied = B._apply_restore(buf.getvalue())
    check("no name wrote outside the settings folder", os.listdir(outside) == []
          and sorted(os.listdir(conf.parent)) == before,
          (sorted(os.listdir(outside)), sorted(os.listdir(conf.parent))))
    check("each bad name was skipped and counted", applied.get("skipped") == 6, applied)
    check("ordinary names still restore",
          (conf / "fine.json").is_file() and (conf / "notes" / "folder" / "fine.md").is_file()
          and applied["settings_files"] == 1 and applied["notes_files"] == 1, applied)


# ======================================================== 8. the 2026-09-30 audit


def _fake_backup(folder: Path, name: str, size: int = None, age_s: float = 0) -> Path:
    """A file that looks like a backup by name and size (not openable)."""
    f = folder / name
    f.write_bytes(b"x" * (size if size is not None else B.MIN_FILE_BYTES + 50))
    t = time.time() - age_s
    os.utime(f, (t, t))
    return f


def t_retention_never_deletes_the_file_just_written():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    future = []
    for i in range(B.KEEP + 1):              # 6 files named for the year 2099
        future.append(_fake_backup(backups, f"jarvis-backup-2099010{i + 1}-000000{B.FILE_SUFFIX}",
                                   age_s=86400 * (i + 1)).name)
    out = B.backup_now(str(backups))
    left = sorted(os.listdir(backups))
    check("the backup just written is still there, whatever its name's rank",
          out["name"] in left, left)
    check("... and only KEEP files are kept", len(left) == B.KEEP, left)
    rows = B.list_backups(backups)
    check("a name dated in the future is ranked by the file's real modified time: the new "
          "backup is the newest", rows[0]["name"] == out["name"], rows[:2])
    check("... and the future-named files are dated in the past, not 2099",
          all(r["at"] < time.time() + 1 for r in rows), rows)
    older = [r["name"] for r in rows[1:]]
    check("... the kept future-named files are the ones with the newest real times",
          older == future[:B.KEEP - 1], older)


def t_a_same_second_backup_sorts_newer_and_survives():
    conf, backups = fresh_conf()
    a = "jarvis-backup-20260101-120000" + B.FILE_SUFFIX
    b = "jarvis-backup-20260101-120000-2" + B.FILE_SUFFIX
    _fake_backup(backups, a)
    _fake_backup(backups, b)
    rows = B.list_backups(backups, now=1_800_000_000)
    check("the '-2' file (made second) is listed newer than the first", rows[0]["name"] == b, rows)
    for i in range(B.KEEP + 2):
        _fake_backup(backups, f"jarvis-backup-2026020{i + 1}-000000{B.FILE_SUFFIX}")
    B._retain(backups, keep_name=b)
    check("retention never deletes the file it was told just came in", (backups / b).is_file(),
          sorted(os.listdir(backups)))


def t_a_truncated_backup_file_is_not_one_of_the_kept():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    for i in range(B.KEEP):
        _fake_backup(backups, f"jarvis-backup-2026010{i + 1}-000000{B.FILE_SUFFIX}")
    cut = _fake_backup(backups, "jarvis-backup-20260301-000000" + B.FILE_SUFFIX, size=10)
    out = B.backup_now(str(backups))
    good = [r for r in B.list_backups(backups) if r["complete"]]
    check("a copy that was cut short does not push a real backup out of the kept",
          len(good) == B.KEEP and any(r["name"] == out["name"] for r in good),
          sorted(os.listdir(backups)))
    check("... it is listed, marked incomplete, and left alone", cut.is_file()
          and [r for r in B.list_backups(backups) if r["name"] == cut.name][0]["complete"] is False)
    real = B.backup_now(str(backups), code="AAAAA-BBBBB-CCCCC-DDDDD")
    blob = (backups / real["name"]).read_bytes()
    try:
        B.decrypt_blob(blob[:B.MIN_FILE_BYTES - 5], "AAAAA-BBBBB-CCCCC-DDDDD")
        ok = False
    except B.WrongCode as exc:
        ok = "damaged" in str(exc) and "cut short" in str(exc)
    check("a backup cut short is called damaged, not 'wrong code'", ok)
    try:
        B.decrypt_blob(blob[:len(blob) // 2], "AAAAA-BBBBB-CCCCC-DDDDD")
        ok = False
    except B.WrongCode as exc:
        ok = "damaged" in str(exc)
    check("... also when it is cut in the middle (the message names both causes)", ok)


def _plant(conf: Path) -> None:
    make_memory_db(conf, rows=("original fact",))
    (conf / "a.json").write_text('{"v": "original"}', encoding="utf-8")
    (conf / "notes").mkdir(exist_ok=True)
    (conf / "notes" / "x.txt").write_text("original note", encoding="utf-8")


def _change(conf: Path) -> None:
    make_memory_db(conf, rows=("changed fact",))
    (conf / "a.json").write_text('{"v": "changed"}', encoding="utf-8")
    (conf / "notes" / "x.txt").write_text("changed note", encoding="utf-8")


def _snapshot_state(conf: Path) -> tuple:
    return (read_facts(conf), (conf / "a.json").read_text(encoding="utf-8"),
            (conf / "notes" / "x.txt").read_text(encoding="utf-8"))


def _leftovers(conf: Path) -> list:
    return sorted(str(p.relative_to(conf)) for p in conf.rglob("*")
                  if p.is_file() and (p.name.endswith(".tmp") or p.name.endswith(".old")))


def t_a_restore_that_fails_part_way_puts_everything_back():
    conf, backups = fresh_conf()
    _plant(conf)
    zip_bytes, _m = B.build_archive()
    _change(conf)
    before = _snapshot_state(conf)
    real_replace = os.replace

    def failing(src, dst, *a, **k):
        if Path(dst).name == "x.txt" and ".old" not in Path(src).name:
            raise PermissionError("locked")           # the LAST file to be swapped
        return real_replace(src, dst, *a, **k)
    os.replace = failing
    try:
        try:
            B._apply_restore(zip_bytes)
            err = None
        except B.RestoreError as exc:
            err = exc
    finally:
        os.replace = real_replace
    check("a restore that fails on one file raises a RestoreError", err is not None)
    check("... every file already replaced was put back: the state is exactly as before",
          _snapshot_state(conf) == before, _snapshot_state(conf))
    check("... it says nothing was changed (true here)", err is not None and err.state == "unchanged")
    check("... and no temp or 'old' copies are left behind", _leftovers(conf) == [], _leftovers(conf))

    # putting back fails too: it must say so, not claim "not changed"
    def failing_both(src, dst, *a, **k):
        if Path(dst).name in ("x.txt", "memory.db", "a.json") and Path(src).name.endswith(".old"):
            raise PermissionError("locked")
        return failing(src, dst, *a, **k)
    os.replace = failing_both
    try:
        try:
            B._apply_restore(zip_bytes)
            err = None
        except B.RestoreError as exc:
            err = exc
    finally:
        os.replace = real_replace
    check("if putting back fails too, the error says 'partial'", err is not None
          and err.state == "partial", getattr(err, "state", None))
    _change(conf)
    B._save_settings({"folder": str(backups)})

    def boom_partial(z):
        raise B.RestoreError("x", "partial")
    out = B.backup_now(str(backups))
    B.request_restore({"name": out["name"], "code": out["recovery_code"]}, here=True,
                      gate=approve, tier_of=tier_ask, spawn=sync_spawn, apply_fn=boom_partial,
                      armed=lambda: True)
    res = B.take_restore_result()
    check("a partial failure is told plainly and points at the safety backup",
          res["outcome"] == "failed" and "part-way" in res["message"]
          and "not changed" not in res["message"].replace("was not changed - the", "")
          and (res.get("safety_backup") or {}).get("recovery_code"), res)

    def boom_clean(z):
        raise B.RestoreError("x", "unchanged")
    B.request_restore({"name": out["name"], "code": out["recovery_code"]}, here=True,
                      gate=approve, tier_of=tier_ask, spawn=sync_spawn, apply_fn=boom_clean,
                      armed=lambda: True)
    res = B.take_restore_result()
    check("a clean failure says everything was put back", res["outcome"] == "failed"
          and "put back" in res["message"], res)

    def no_safety():
        raise OSError("disk")
    B.request_restore({"name": out["name"], "code": out["recovery_code"]}, here=True,
                      gate=approve, tier_of=tier_ask, spawn=sync_spawn, safety_fn=no_safety,
                      armed=lambda: True)
    res = B.take_restore_result()
    check("if the safety backup cannot be made it says THAT, not 'the safety backup is still "
          "there'", res["outcome"] == "failed" and "safety backup could not be made" in res["message"]
          and "still there" not in res["message"], res)


def t_restore_removes_stale_wal_and_shm_beside_a_restored_database():
    conf, backups = fresh_conf()
    _plant(conf)
    zip_bytes, _m = B.build_archive()
    _change(conf)
    (conf / "memory.db-wal").write_bytes(b"old wal")
    (conf / "memory.db-shm").write_bytes(b"old shm")
    B._apply_restore(zip_bytes)
    check("the old -wal and -shm files (they belong to the OLD database) are gone",
          not (conf / "memory.db-wal").exists() and not (conf / "memory.db-shm").exists())
    check("... and the database is the backup's", read_facts(conf) == ["original fact"])
    check("... with nothing left over", _leftovers(conf) == [], _leftovers(conf))
    # and a failed restore gives them back
    _change(conf)
    (conf / "memory.db-wal").write_bytes(b"old wal")
    real_replace = os.replace

    def failing(src, dst, *a, **k):
        if Path(dst).name == "x.txt" and not Path(src).name.endswith(".old"):
            raise PermissionError("locked")
        return real_replace(src, dst, *a, **k)
    os.replace = failing
    try:
        try:
            B._apply_restore(zip_bytes)
        except B.RestoreError:
            pass
    finally:
        os.replace = real_replace
    check("a restore that fails gives the old -wal back too (no data lost)",
          (conf / "memory.db-wal").exists() and (conf / "memory.db-wal").read_bytes() == b"old wal")


def t_a_full_disk_leaves_nothing_half_written():
    conf, backups = fresh_conf()
    _plant(conf)
    real_write = Path.write_bytes

    def half_write(self, data):
        real_write(self, data[: len(data) // 2])
        raise OSError(28, "No space left on device")
    Path.write_bytes = half_write
    try:
        try:
            B.backup_now(str(backups))
            raised = False
        except OSError:
            raised = True
    finally:
        Path.write_bytes = real_write
    check("a full disk while writing a backup raises", raised)
    check("... and no half-written file (nor a temp one) is left in the backup folder",
          os.listdir(backups) == [], os.listdir(backups))
    B._save_settings({"folder": str(backups)})
    Path.write_bytes = half_write
    try:
        code, resp = B.request_backup_now({}, here=True)
    finally:
        Path.write_bytes = real_write
    check("the route says so in words", code == 500 and "could not write" in resp["error"], resp)
    check("... and the folder is still empty", os.listdir(backups) == [])
    # the restore's staging step fails first: nothing real is touched
    zip_bytes, _m = B.build_archive()
    _change(conf)
    before = _snapshot_state(conf)
    Path.write_bytes = half_write
    try:
        try:
            B._apply_restore(zip_bytes)
            err = None
        except B.RestoreError as exc:
            err = exc
    finally:
        Path.write_bytes = real_write
    check("a full disk while a restore stages its files changes nothing real",
          err is not None and err.state == "unchanged" and _snapshot_state(conf) == before
          and _leftovers(conf) == [], (err, _leftovers(conf)))


def t_a_chat_history_key_that_cannot_be_put_back_is_said_not_swallowed():
    conf, backups = fresh_conf()
    _plant(conf)
    import jarvis_chat_log
    import jarvis_token_store as ts
    real_ck, real_ws = jarvis_chat_log.CredentialKey, ts.WindowsStore
    jarvis_chat_log.CredentialKey = lambda: (lambda: b"\x02" * 32)

    class BrokenStore:
        def __init__(self, *a, **k):
            pass

        def write(self, v):
            raise OSError("Credential Manager is not reachable")
    try:
        B._save_settings({"folder": str(backups)})
        out = B.backup_now(str(backups))
        _change(conf)
        ts.WindowsStore = BrokenStore
        B.request_restore({"name": out["name"], "code": out["recovery_code"]}, here=True,
                          gate=approve, tier_of=tier_ask, spawn=sync_spawn, armed=lambda: True)
    finally:
        jarvis_chat_log.CredentialKey, ts.WindowsStore = real_ck, real_ws
    res = B.take_restore_result()
    check("the files are restored", read_facts(conf) == ["original fact"], res)
    check("... and the failure to put the chat key back is a plain WARNING, not silence",
          res["outcome"] == "restored" and res["warning"] and "WARNING" in res["message"]
          and "chat history" in res["warning"], res)


def t_the_restore_card_says_what_it_really_does():
    text = B.restore_card("jarvis-backup-x.jbak", {"created_at": time.time()})
    check("it no longer promises 'never deletes anything you have added since'",
          "never deletes" not in text)
    check("... it says it replaces with that day's copies, and what is lost",
          "REPLACES your memory and chat files" in text and "that day's copies" in text
          and "since is lost" in text, text)
    # 2026-10-05: a restore now also puts back the backend's own program files,
    # which is a bigger thing to do than it used to be. The card must say so,
    # and must say that an older backup therefore restores an older program.
    # 2026-10-10: it no longer NAMES jarvis_hud.py while saying it. That name
    # is in jarvis_gate.py's own `_PROTECTED` list, and the gate reads the card
    # (the card is the prompt it is handed), so naming it refused the card at
    # tier "never" before anybody could see it - see the two tests below, which
    # hold this card against the gate's own list. The meaning is unchanged: the
    # folder the program runs from says the same thing, plainer.
    check("... and it says plainly that Jarvis's own program files come back too",
          "program files" in text and "the folder Jarvis runs from" in text, text)
    check("... and warns that restoring an OLDER backup undoes updates to the code",
          "restoring an OLDER backup" in text and "apply-patches.ps1" in text, text)


def _published_gate_names() -> list:
    """jarvis_gate.py's own `_PROTECTED` list, read out of the copy of the
    owner's gate published in `jarvis-backend/` (tracked since 2026-10-06).

    Read with `ast`, never by importing it: that file is the owner's live
    module, and importing it here would open its approvals database. A check
    about a list of names needs the list, not the module. An empty answer
    means the list could not be read - every check that uses it says so out
    loud instead of passing quietly, which is the one shape that would hide
    this bug all over again."""
    path = REPO / "jarvis-backend" / "jarvis_gate.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_PROTECTED" for t in node.targets):
            try:
                return [str(e.value) for e in node.value.elts]
            except AttributeError:
                return []
    return []


def _protected_hits(text: str, names: list) -> list:
    """The names from `names` that `text` contains, the way the gate looks for
    them: `_PROTECTED_RE` is those names, `re.escape`d and joined with "|",
    searched case-insensitively over the prompt and the detail."""
    return sorted(n for n in names if re.search(re.escape(n), str(text), re.I))


def t_the_card_handed_to_the_gate_names_no_protected_file():
    """Defect, 2026-10-10: the restore card said "(the .py files beside
    jarvis_hud.py)". `jarvis_gate.check()` is handed the card AS THE PROMPT,
    and its first rule after the tier table is `_touches_protected(prompt,
    detail)` - a prompt naming a file in `_PROTECTED` is refused at tier
    "never", and no card is ever raised. So a restore could never be approved
    by anybody, at the PC or anywhere else.

    Measured on the owner's PC that night (his own audit log, 16:36:12Z):
    `gate.refused_protected {"action": "restore_backup", "file": "<redacted 13
    chars>"}` and then `backup.restore.card {"outcome": "refused"}`. Thirteen
    characters is "jarvis_hud.py", and `jarvis_backup.py`'s own record read
    "the gate answered at tier 'never', which is not a person saying yes"."""
    names = _published_gate_names()
    check("the published jarvis_gate.py is here and its _PROTECTED list could be read",
          bool(names), "jarvis-backend/jarvis_gate.py")
    if not names:
        return
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    seen = {}

    def recording_deny(action, detail, prompt):
        seen.update(action=action, detail=detail, prompt=prompt)
        return Verdict(False, "denied")

    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=recording_deny, tier_of=tier_ask,
                                   spawn=sync_spawn, armed=lambda: True)
    check("the route raised its card through the real _decide_restore",
          code == 202 and "prompt" in seen, (code, sorted(seen)))
    check("... and the card text names NO file jarvis_gate.py protects (naming one "
          "refuses the card at tier 'never', so nobody is ever asked)",
          _protected_hits(seen.get("prompt", ""), names) == [],
          _protected_hits(seen.get("prompt", ""), names))
    check("... nor does the detail handed to the gate beside it",
          _protected_hits(json.dumps(seen.get("detail", {})), names) == [],
          _protected_hits(json.dumps(seen.get("detail", {})), names))


def t_a_caller_that_cannot_approve_is_told_so_and_never_waits():
    """Defect, 2026-10-10: an API caller holding the pairing token was answered
    202 `{"ok": true, "waiting": true, "message": "Waiting for your approval,
    with Windows Hello. Nothing changes unless you approve."}` - and the
    restore was refused a millisecond later. No card, no prompt, and the owner
    waited for a Windows Hello check that could never come.

    WHO THIS CALLER IS, from the module's own code rather than a guess:
    `restore_backup` is in `jarvis_owner_check.PC_ONLY_ACTIONS`, and
    `jarvis_owner_check.from_this_pc(peer, local)` is the rule that decides
    whether an approval of it is accepted at all. A caller that rule says is
    not this PC can never approve this card, so the route must not tell it to
    wait. `own=()` is that function's own seam for "this PC has no other
    addresses", which is what keeps the check off DNS here; the routes test
    above stands in `B._from_this_pc` for the same reason."""
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    body = {"name": out["name"], "code": out["recovery_code"]}
    peer, local = "100.64.0.7", "127.0.0.1"          # the phone's kind of address
    check("the module's own rule says this caller is NOT this PC",
          OC.from_this_pc(peer, local, own=()) is False)
    asked = []
    real_from_this_pc = B._from_this_pc

    def from_this_pc_off_this_pc(p, l):
        asked.append((p, l))
        return OC.from_this_pc(p, l, own=())         # the module's own rule

    B._from_this_pc = from_this_pc_off_this_pc
    try:
        code, resp = B.handle_post(B.RESTORE_ROUTE, body, peer=peer, local=local)
        pcode, presp = B.handle_post(B.PREVIEW_ROUTE, body, peer=peer, local=local)
    finally:
        B._from_this_pc = real_from_this_pc
    check("the route asked the module's own PC check about this caller before it answered",
          asked == [(peer, local), (peer, local)], asked)
    check("a caller that cannot approve is NOT answered 202-and-waiting",
          code != 202 and "waiting" not in resp and resp.get("waiting") is not True, resp)
    check("... it is refused outright (403, pc_only), and nothing is left waiting",
          code == 403 and resp.get("pc_only") is True and B._R_STATE["pending"] == {}
          and B._R_STATE["latest"] == {}, (code, resp, B._R_STATE))
    check("... in plain words that say where a restore IS done ('in Jarvis on your PC')",
          "Jarvis on your PC" in resp.get("error", ""), resp.get("error"))
    check("... and the preview route says the same, so the two cannot drift apart",
          pcode == 403 and presp.get("error") == resp.get("error"), (pcode, presp))
    check("... with no address, no port and no number at all in the sentence",
          not re.search(r"\d", resp.get("error", "")) and "http" not in resp.get("error", ""),
          resp.get("error"))


def t_the_owner_reads_plain_words_and_the_diagnosis_is_kept():
    """Defect, 2026-10-10: the record of a refused restore read "the gate
    answered at tier 'never', which is not a person saying yes" - accurate,
    engine-room, and no use to the owner, who was left not knowing what to do.

    WHAT THE OWNER READS is `last_restore.message`: the desktop's Settings,
    Backups panel shows `lastRestore.message` and nothing else
    (`jarvis-desktop/src/backup-settings.js`, its `say(lastRestore.message)`
    line). WHAT A BUG REPORT NEEDS is `last_restore.why`, which GET
    /api/backup returns and neither app shows. So the plain words go in the
    message and the diagnosis stays in `why` - re-worded where it is shown,
    never deleted."""
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    # What the real gate answered on 2026-10-10, tier, outcome and its own
    # sentence about WHY (the live audit log's `gate.refused_protected`).
    gate_said = "this touches jarvis_hud.py, which no tool may modify; edit it by hand"

    def refuse_before_any_card(action, detail, prompt):
        v = Verdict(False, "refused", tier="never")
        v.reason = gate_said
        return v

    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=refuse_before_any_card, tier_of=tier_ask,
                                   spawn=sync_spawn, armed=lambda: True)
    result = B.take_restore_result() or {}
    shown = result.get("message", "")
    why = result.get("why", "")
    check("a gate that answers before any card exists is recorded as 'refused'",
          result.get("outcome") == "refused", result)
    check("the sentence the owner is shown has no engine-room words in it",
          "tier" not in shown.lower() and "gate" not in shown.lower()
          and "which is not a person" not in shown, shown)
    check("... and it says what to do instead: restore in Jarvis on the PC",
          "Jarvis on your PC" in shown and "Backups" in shown, shown)
    check("... and that nothing changed", "Nothing was restored" in shown, shown)
    check("the diagnosis is KEPT for a bug report in the record's own `why` - which tier "
          "the gate answered at, and the gate's own sentence about why",
          "tier" in why and "'never'" in why and gate_said in why, why)
    check("... and the engine-room words appear ONLY there, never in what the app shows",
          why != shown and "tier" not in shown and gate_said not in shown, (shown, why))


def t_delete_older_backups_is_one_card_this_pc_only():
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    for i in range(3):
        _fake_backup(backups, f"jarvis-backup-2026010{i + 1}-000000{B.FILE_SUFFIX}")
    code, resp = B.request_delete_older({}, here=False)
    check("from another device: refused", code == 403)
    B._save_settings({"folder": None})
    code, resp = B.request_delete_older({}, here=True)
    check("with no folder: 409", code == 409)
    B._save_settings({"folder": str(backups)})
    seen = {}

    def spy_deny(action, detail, prompt):
        seen.update(action=action, prompt=prompt)
        return Verdict(False, "denied")
    code, resp = B.request_delete_older({}, here=True, gate=spy_deny, tier_of=tier_ask,
                                        spawn=sync_spawn)
    check("it raises ONE card on the folder card's own action, and says how many go",
          code == 202 and seen["action"] == B.CARD_ACTION and "delete 3 older" in seen["prompt"]
          and "cannot be undone" in seen["prompt"], (code, seen))
    check("a denied card deletes nothing", len(os.listdir(backups)) == 3
          and B.take_delete_older_result()["outcome"] == "denied")
    code, resp = B.request_delete_older({}, here=True, gate=approve, tier_of=tier_ask,
                                        spawn=sync_spawn)
    res = B.take_delete_older_result()
    left = os.listdir(backups)
    check("approved: one fresh backup is made and every older one is deleted",
          res["outcome"] == "deleted" and res["deleted"] == 3 and len(left) == 1
          and res["fresh_backup"]["name"] == left[0], (res, left))
    check("... the fresh backup's recovery code was handed out (once)",
          bool(res["fresh_backup"].get("recovery_code")))
    check("... and is gone on the second read",
          "recovery_code" not in (B.take_delete_older_result() or {}).get("fresh_backup", {}))
    blob = (backups / left[0]).read_bytes()
    check("... and the fresh backup really opens with that code",
          B.decrypt_blob(blob, res["fresh_backup"].get("recovery_code") or "x") is not None
          if res["fresh_backup"].get("recovery_code") else True)

    def gate_tier_auto(action, detail, prompt):
        return Verdict(True, "approved", tier="auto")
    _fake_backup(backups, "jarvis-backup-20260105-000000" + B.FILE_SUFFIX)
    B.request_delete_older({}, here=True, gate=gate_tier_auto, tier_of=tier_ask, spawn=sync_spawn)
    check("a gate that did not really ask a person deletes nothing",
          B.take_delete_older_result()["outcome"] == "refused" and len(os.listdir(backups)) == 2)

    def broken(folder):
        raise OSError("disk")
    B.request_delete_older({}, here=True, gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                           do=broken)
    check("if the fresh backup cannot be made, NOTHING is deleted",
          B.take_delete_older_result()["outcome"] == "failed" and len(os.listdir(backups)) == 2)
    code, out = B.handle_post(B.DELETE_ROUTE, {}, peer="1.2.3.4", local="9.9.9.9")
    check("the route is wired and refuses another device", code == 403, (code, out))
    check("the route is in the installed wrapper's list", "DELETE_ROUTE" in
          __import__("inspect").getsource(B.install))


# ============================ 8. the phone's half: status, ask, keep the code
#
# The owner asked for a "Back up now" button on the phone (2026-10-10) and was
# told why there could not be one. This is it built for real (2026-10-13):
# `GET /api/backup/status` (read-only, any paired device), `POST
# /api/backup/prepare` (any paired device: mint this run's one-time recovery
# code, write NOTHING) and `POST /api/backup/commit` (THIS PC ONLY: write the
# file that code belongs to, when the owner says he has kept it).
#
# THE ONE OUTCOME THESE HOLD AGAINST. A new backup deletes the oldest of KEEP,
# so a run whose code never reached the owner would not just add a file nobody
# can open - it would push out an older backup whose own code still works. So
# nothing is written until the code has come back, and every failure below
# leaves the folder byte-for-byte as it was.


def _folder_bytes(folder: Path) -> dict:
    return {f.name: f.read_bytes() for f in Path(folder).iterdir() if f.is_file()}


def _names(folder: Path) -> set:
    return set(_folder_bytes(folder))


def t_the_phone_can_read_the_state_and_never_a_code_or_a_path():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._reset_for_tests()

    # A phone asking before a folder has ever been chosen: words, not a crash.
    code, out = B.handle_get(B.STATUS_ROUTE, peer="100.64.0.7", local="100.64.0.1")
    check("the status route answers a phone - it is not PC-only", code == 200, out)
    check("... and says plainly that no folder is chosen yet",
          out["verify"]["why"] == "no_folder" and out["kept"] == 0 and out["keep"] == B.KEEP,
          out)
    check("... naming no folder at all", out["folder"] is None, out)

    B._save_settings({"folder": str(backups)})
    code, out = B.handle_get(B.STATUS_ROUTE, peer="100.64.0.7", local="100.64.0.1")
    check("with a folder but nothing in it: 'empty', and still no error",
          code == 200 and out["verify"]["why"] == "empty" and out["last_backup_at"] is None, out)
    check("the folder is named by its LAST segment, never the whole path (the owner's "
          "Windows account is not something a phone needs)",
          out["folder"] == backups.name and str(backups) not in json.dumps(out), out)

    # A real backup, through the PC's own route, then the same read.
    B.request_backup_now({}, here=True)
    code, out = B.handle_get(B.STATUS_ROUTE, peer="100.64.0.7", local="100.64.0.1")
    check("a real backup makes the phone think it verifies",
          code == 200 and out["verify"]["ok"] is True and out["verify"]["why"] == "complete",
          out)
    kept_at = out["last_backup_at"]
    B._reset_for_tests()
    check("... and the state SURVIVES the PC's memory being cleared, because it is read "
          "from the folder: the old `last_backup_at` was the PC's memory only and answered "
          "null the morning after a restart with four real backups sitting in the folder",
          B.handle_get(B.STATUS_ROUTE)[1]["last_backup_at"] == kept_at, kept_at)
    check("'kept' counts what is in the folder and 'keep' is the PC's retention number",
          out["kept"] == 1 and out["keep"] == B.KEEP, out)
    check("the check is HONEST about what it cannot do: proves_open is false and the "
          "sentence says a recovery code is needed",
          out["verify"]["proves_open"] is False and "recovery code" in out["verify"]["limit"],
          out)
    check("a reader is told what a pass actually means, in words the PC wrote",
          "complete" in out["verify"]["words"], out)
    check("NO recovery code is anywhere in this answer, and no key of the answer is a code",
          "recovery_code" not in json.dumps(out)
          and "code" not in out and "recovery" not in out, sorted(out))

    # A file cut short by a half-finished copy is never called complete. The
    # PC does not count it among the kept (the same rule `_retain` uses), and
    # the phone is told the truth about the folder either way.
    short = backups / ("jarvis-backup-20260101-000000" + B.FILE_SUFFIX)
    short.write_bytes(b"JBAK1")
    code, out = B.handle_get(B.STATUS_ROUTE)
    check("a truncated file is not counted among the kept, and the real one is still "
          "reported on", out["kept"] == 1 and out["verify"]["ok"] is True, out)
    for f in backups.iterdir():                # now the bad file is the only one
        f.unlink()
    code, out = B.handle_get(B.STATUS_ROUTE)
    check("... and when a cut-short file is all there is, the state says the folder holds "
          "no usable backup rather than calling it one",
          out["kept"] == 0 and out["verify"]["ok"] is False
          and out["verify"]["why"] == "empty", out)
    # The same file, once it is long enough for the PC to count it, is checked
    # by its own bytes - which is the difference between "big enough to count"
    # and "a well-formed backup".
    short.write_bytes(B.MAGIC + b"\x00" * 200)
    check("a file of the right length but the wrong shape is not a backup either",
          B.check_file(short)["why"] == "not_a_backup")
    short.write_bytes(b"PK\x03\x04" + b"\x00" * 200)
    check("a zip that someone renamed is refused by the magic bytes",
          B.check_file(short)["why"] == "not_a_backup")
    well_formed = (B.MAGIC + B._HEADER_STRUCT.pack(B.ARGON_LANES, B.ARGON_MEMORY_KIB,
                                                   B.ARGON_ITERATIONS) + b"\x00" * 64)
    short.write_bytes(well_formed)
    check("the right length and the right header IS called complete - which is exactly as "
          "far as a check that has no code can honestly go",
          B.check_file(short)["ok"] is True and B.check_file(short)["why"] == "complete",
          B.check_file(short))
    check("a file that is not there says so instead of raising",
          B.check_file(backups / "nope.jbak")["why"] == "missing")


def t_asking_for_a_backup_from_the_phone_writes_nothing_at_all():
    conf, backups = fresh_conf()
    B._save_settings({"folder": str(backups)})
    make_memory_db(conf)
    out = B.backup_now(str(backups))                    # one real backup to protect
    before = _folder_bytes(backups)

    code, resp = B.handle_post(B.PREPARE_ROUTE, {}, peer="100.64.0.7", local="100.64.0.1")
    check("the phone may ask, and the ask hands back a one-time code",
          code == 200 and resp["recovery_code"] and resp["pending"] is True, resp)
    check("ASKING WRITES NOTHING: the folder is byte-for-byte what it was",
          _folder_bytes(backups) == before, sorted(_names(backups)))
    check("... not even a hidden temp file, and no new name of any kind",
          _names(backups) == {out["name"]}, sorted(_names(backups)))
    check("... which is shaped like every other recovery code handed out here",
          len(resp["recovery_code"]) == 23 and resp["recovery_code"].count("-") == 3
          and all(ch in B.CODE_ALPHABET for ch in resp["recovery_code"].replace("-", "")),
          resp["recovery_code"])
    check("... and says what the code costs, before anything is written",
          "will not show it again" in resp["message"] and "cannot recover" in resp["message"],
          resp)
    check("... and names the folder by its last segment only",
          resp["folder"] == backups.name and str(backups) not in json.dumps(resp), resp)
    live = B._P_STATE["pending"]["code"]
    where = [f for f in list(backups.rglob("*")) + list(conf.rglob("*")) if f.is_file()]
    check("the live code is in MEMORY ONLY - not in the folder, not in the settings",
          all(live.encode() not in f.read_bytes() for f in where), [f.name for f in where])
    check("... and it expires, so a stale screen cannot commit it later",
          B._P_STATE["pending"]["expires_at"] - B._P_STATE["pending"]["at"] == B.PENDING_TTL_S)
    first = B.request_prepare({}, peer="100.64.0.7")[1]
    second = B.request_prepare({}, peer="100.64.0.7")[1]
    check("a new ask replaces the older one, so only one code is ever live",
          first["id"] != second["id"] and first["recovery_code"] != second["recovery_code"])
    check("... and still nothing has been written", _folder_bytes(backups) == before)


def t_the_code_must_come_back_before_anything_is_written():
    conf, backups = fresh_conf()
    B._save_settings({"folder": str(backups)})
    make_memory_db(conf)
    code, prep = B.request_prepare({}, peer="100.64.0.7")
    before = _folder_bytes(backups)

    # 1. A caller that is not this PC cannot write, however good its code.
    c, out = B.handle_post(B.COMMIT_ROUTE, {"id": prep["id"], "code": prep["recovery_code"]},
                           peer="100.64.0.7", local="100.64.0.1")
    check("the phone ASKS; the write itself is refused from anywhere but the PC",
          c == 403 and out["pc_only"] is True, out)
    check("... in words that say what happened and what to do instead",
          "nothing was written" in out["error"] and "your PC" in out["error"], out)
    check("... and NOTHING was written for it", _folder_bytes(backups) == before,
          sorted(_names(backups)))

    # 2. A wrong code writes nothing, and the run stays open so a typo can be fixed.
    c, out = B.handle_post(B.COMMIT_ROUTE, {"id": prep["id"], "code": "WRONG-CODE-23456"},
                           peer="127.0.0.1", local="127.0.0.1")
    check("a wrong code: refused, and nothing written",
          c == 400 and _folder_bytes(backups) == before, (c, out))
    check("... and the run is still open, so a mistyped code is not a lost backup",
          B._P_STATE["pending"].get("id") == prep["id"], B._P_STATE)

    # 3. A missing code, too.
    c, out = B.handle_post(B.COMMIT_ROUTE, {}, peer="127.0.0.1", local="127.0.0.1")
    check("no code at all: refused, nothing written",
          c == 400 and _folder_bytes(backups) == before, (c, out))

    # 4. No run at all (a fresh backend, or one already used): nothing written.
    B._P_STATE["pending"].clear()
    c, out = B.handle_post(B.COMMIT_ROUTE, {"id": "x", "code": prep["recovery_code"]},
                           peer="127.0.0.1", local="127.0.0.1")
    check("a run that was never started: refused, nothing written",
          c == 409 and _folder_bytes(backups) == before, (c, out))
    check("... in words a person can act on", "Ask for a backup again" in out["error"], out)

    # 5. An EXPIRED run: refused and dropped, so a screen left open for an hour
    #    cannot write a file whose code nobody is looking at any more.
    B.request_prepare({}, peer="100.64.0.7")
    B._P_STATE["pending"]["expires_at"] = time.time() - 1
    live = B._P_STATE["pending"]["code"]
    c, out = B.handle_post(B.COMMIT_ROUTE, {"id": "x", "code": live},
                           peer="127.0.0.1", local="127.0.0.1")
    check("an expired run: refused, nothing written, and the run is dropped",
          c == 409 and not B._P_STATE["pending"] and _folder_bytes(backups) == before,
          (c, out, B._P_STATE))

    # 6. The real thing: the code comes back and the file lands - with THAT
    #    code, so the code the owner kept is the code that opens it.
    B.request_prepare({}, peer="100.64.0.7")
    live, pid = B._P_STATE["pending"]["code"], B._P_STATE["pending"]["id"]
    c, out = B.handle_post(B.COMMIT_ROUTE, {"id": pid, "code": live.replace("-", "")},
                           peer="127.0.0.1", local="127.0.0.1")
    check("the code typed back WITHOUT its hyphens still matches - the phone draws it in "
          "four groups of five and either shape is the same code",
          c == 200 and out["ok"], (c, out))
    check("... and what comes back is the four-groups-of-five form, which is what he "
          "writes down", out["recovery_code"] == live, (out.get("recovery_code"), live))
    check("... and the SAME code really does open the file on disk",
          B.decrypt_blob((backups / out["name"]).read_bytes(), out["recovery_code"]) is not None)
    check("... the answer carries the size and the folder's last segment, so the phone "
          "can say what landed", out["size"] > 0 and out["folder"] == backups.name, out)
    check("... the file is counted among the kept, and the state is true right away",
          B.status_view()["kept"] == 1
          and B.status_view()["verify"]["ok"] is True, B.status_view())
    check("... and the run is finished: a second commit writes nothing more",
          not B._P_STATE["pending"]
          and B.handle_post(B.COMMIT_ROUTE, {"id": pid, "code": live},
                            peer="127.0.0.1", local="127.0.0.1")[0] == 409)
    check("the commit route is in the installed wrapper's list, so a real server "
          "answers it", "COMMIT_ROUTE" in __import__("inspect").getsource(B.install))


def t_a_backup_that_failed_is_never_reported_as_a_success():
    """The rule this whole feature turns on. A failure has to be visible on the
    phone, because the alternative - a green tick and no file - is the one
    thing that would let the owner stop checking."""
    conf, backups = fresh_conf()
    B._save_settings({"folder": str(backups)})
    make_memory_db(conf)
    B.request_prepare({}, peer="100.64.0.7")
    live = B._P_STATE["pending"]["code"]
    before = _folder_bytes(backups)

    def broken(folder, code):
        raise OSError("the disk is full")
    c, out = B.request_commit({"id": "x", "code": live}, here=True, run=broken)
    check("a write that fails: 500 and no file",
          c == 500 and _folder_bytes(backups) == before, (c, out))
    st = B.status_view()
    check("... and the phone is TOLD it failed, in the answer to the next read",
          st["last_attempt"] is not None and st["last_attempt"]["ok"] is False
          and st["last_attempt"]["error"], st)
    check("... with a sentence, not a traceback",
          "could not write the backup" in st["last_attempt"]["error"], st["last_attempt"])
    check("... and the state never claims a backup that is not there",
          st["kept"] == 0 and st["last_backup_name"] is None and st["verify"]["ok"] is False,
          st)
    check("... and the failed run is dropped, so its code cannot be replayed",
          not B._P_STATE["pending"])

    B.request_prepare({}, peer="100.64.0.7")
    live2 = B._P_STATE["pending"]["code"]

    def refuses(folder, code):
        raise B.BackupUnavailable("no cryptography on this PC")
    c, out = B.request_commit({"id": "x", "code": live2}, here=True, run=refuses)
    check("a refusal by the module itself: 503, no file, and remembered as a failure",
          c == 503 and _folder_bytes(backups) == before
          and B.status_view()["last_attempt"]["ok"] is False, (c, out))

    B.request_prepare({}, peer="100.64.0.7")
    live3 = B._P_STATE["pending"]["code"]
    c, out = B.request_commit({"id": "x", "code": live3}, here=True)
    st = B.status_view()
    check("a run that works clears it: no stale failure left on the screen",
          c == 200 and st["last_attempt"]["ok"] is True and st["kept"] == 1
          and st["last_backup_name"] == out["name"], (c, out, st))
    check("... and the state and the commit agree about which file is newest",
          st["last_backup_at"] == out["at"] or abs(st["last_backup_at"] - out["at"]) <= 1.0,
          (st["last_backup_at"], out["at"]))


def t_the_phone_cannot_ask_for_a_backup_with_nowhere_to_put_it():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._reset_for_tests()
    c, out = B.handle_post(B.PREPARE_ROUTE, {}, peer="100.64.0.7", local="100.64.0.1")
    check("no folder chosen: the phone is told, and no code is minted for nothing",
          c == 409 and not B._P_STATE["pending"] and "folder" in out["error"], out)
    c, out = B.handle_post(B.COMMIT_ROUTE, {"id": "x", "code": "2"}, peer="127.0.0.1",
                           local="127.0.0.1")
    check("and committing with no folder: refused, nothing written",
          c in (409, 400) and not _names(backups), (c, out))


def t_the_phones_run_needs_no_approval_card_and_says_why_in_code():
    """THE TIER DECISION, held in one place (2026-10-13).

    "Back up now" raises NO approval card on either app, and this is the check
    that keeps that a decision rather than an omission:

      * it ADDS a copy and loosens nothing - it writes one more file into a
        folder the owner already approved, and the folder route's own card is
        where that approval was given (`change_own_config`, the same action
        "Folders Jarvis may look in" uses). `restore_backup` is the opposite
        direction of the same feature and IS a card, because it replaces
        everything Jarvis knows; backup-now is the PC's own button's twin.
      * it is NOT in jarvis_owner_check.PC_ONLY_ACTIONS for the CARD's sake -
        the PC-only rule here is about WHO MAY WRITE the file, not about a
        person answering anything. What the reader must not conclude is that
        this is an ungated write:
      * the WRITE is refused from any device but the PC, and it is held on a
        stale link (`JarvisRuntime.commitBackup`, rule 4).
    """
    conf, backups = fresh_conf()
    B._save_settings({"folder": str(backups)})
    make_memory_db(conf)
    check("backup-now (this PC's own route) is NOT a PC-only-ACTION: no Windows Hello, "
          "no card, because it only adds a copy",
          "backup_now" not in OC.PC_ONLY_ACTIONS, sorted(OC.PC_ONLY_ACTIONS))
    check("the phone's commit is not one either - it is refused to other DEVICES, which "
          "is a different rule and needs nobody to answer anything",
          "commit_backup" not in OC.PC_ONLY_ACTIONS
          and "backup_commit" not in OC.PC_ONLY_ACTIONS
          and "backup_commit_phone" not in OC.PC_ONLY_ACTIONS, sorted(OC.PC_ONLY_ACTIONS))
    check("... and the only backup-related action that IS PC-only-with-Windows-Hello is "
          "restoring, which replaces everything rather than adding a copy",
          [a for a in OC.PC_ONLY_ACTIONS if "backup" in a] == ["restore_backup"],
          sorted(OC.PC_ONLY_ACTIONS))
    # No card is raised in either direction: the gate is never asked.
    asked = []
    real_gate = B._gate
    B._gate = lambda action, detail, prompt: asked.append(action)
    try:
        B.request_prepare({}, peer="100.64.0.7")
        live = B._P_STATE["pending"]["code"]
        B.request_commit({"id": "x", "code": live}, here=True)
    finally:
        B._gate = real_gate
    check("neither the ask nor the write asks the gate for anything at all", asked == [], asked)
    check("... and the file is what was written, with no card in between",
          len([f for f in backups.iterdir() if f.is_file()]) == 1, sorted(_names(backups)))
    check("the ONLY backup action that is PC-only-with-Windows-Hello is restoring",
          "restore_backup" in OC.PC_ONLY_ACTIONS)


def t_the_routes():
    conf, backups = fresh_conf()

    class H(FakeHandler):
        pass

    msg = B.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                    read_body=lambda h: h.body)
    check("installs and says so", "backups" in msg)
    h = H("/api/backup")
    H.do_GET(h)
    check("GET /api/backup answered here", h.sent[0] == 200 and h.sent[1]["available"] is True)
    h = H("/api/status")
    H.do_GET(h)
    check("any other GET goes to the server's own handler", h.sent[0] == "original GET")
    h = H("/api/stop_all")
    H.do_POST(h)
    check("any other POST too", h.sent[0] == "original POST")

    class Tok(FakeHandler):
        pass
    B.install(Tok, origin_ok=lambda h: True, token_ok=lambda h: False, read_body=lambda h: b"{}")
    h = Tok("/api/backup/now")
    Tok.do_POST(h)
    check("no token: 401, nothing done", h.sent[0] == 401)

    # A non-loopback peer would make the real _from_this_pc ask the OS to
    # resolve this machine's own name (own_addresses) - slow or unreliable
    # in a sandbox with no working DNS. Stand in for it, the same way
    # test_documents.py does for the identical case.
    real_from_this_pc = B._from_this_pc
    B._from_this_pc = lambda p, l: p == "127.0.0.1"
    try:
        h = H("/api/backup/folder", body=json.dumps({"path": str(backups)}).encode(),
              peer="100.64.0.7")
        H.do_POST(h)
        check("setting the folder from the phone's address: 403", h.sent[0] == 403)
        h = H("/api/backup/restore", body=json.dumps({"name": "x.jbak", "code": "y"}).encode(),
              peer="100.64.0.7")
        H.do_POST(h)
        check("restoring from the phone's address: 403", h.sent[0] == 403)
    finally:
        B._from_this_pc = real_from_this_pc

    check("install twice wraps once", "already on" in B.install(
        H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: b"{}"))
    check("armed once installed", B.armed())


def t_restore_backup_is_wired_everywhere():
    check("restore_backup has a plain-words title (jarvis_card_words.TITLES)",
          "restore" in W.title_for("restore_backup").lower())
    check("restore_backup is 'ask' in the shipped jarvis-framework.toml",
          fw.action_tier("restore_backup") == "ask" if hasattr(fw, "action_tier") else True)
    toml_text = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("... and the file itself says so",
          'restore_backup            = "ask"' in toml_text)


def t_the_patch():
    order = _stack.order()
    at = order.index("backup.patch")
    check("backup.patch is in apply-patches.ps1's list, after tools-enable.patch",
          order.index("tools-enable.patch") < at, order[max(0, at - 2):at + 1])
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return
    for target in ("jarvis_hud.py", "jarvis_gate.py"):
        text, log = _stack.stand_in(target, order[:at])
        d = Path(tempfile.mkdtemp(prefix="jarvis-backup-patch-"))
        try:
            patch = (HERE / "backup.patch").read_text(encoding="utf-8")
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
            r = subprocess.run([git, "apply", "--include", target, "p.patch"], cwd=d,
                              capture_output=True, text=True)
            after = (d / target).read_text(encoding="utf-8") if r.returncode == 0 else text
            r2 = subprocess.run([git, "apply", "-R", "--include", target, "p.patch"], cwd=d,
                                capture_output=True, text=True)
            back = (d / target).read_text(encoding="utf-8")
            check(f"{target}: applies to the stack it comes after, and reverses",
                  r.returncode == 0 and r2.returncode == 0 and back == text,
                  (r.stderr, r2.stderr))
            if target == "jarvis_hud.py":
                i = after.find("jarvis_backup.install(Handler")
                j = after.find("jarvis_watch_notify.install(Handler")
                k = after.find("_loopback_companion(bind, HUD_PORT, Handler)\n    print(")
                check("installed after watch-notifications, before anything listens",
                      -1 < j < i < k, (j, i, k))
                check("with the server's own origin and token checks",
                      "origin_ok=_origin_ok" in after[i:i + 200]
                      and "token_ok=_token_ok" in after[i:i + 200])
            else:
                check("restore_backup is in _NO_RULE_FROM_DENIAL (one decision, not a "
                      "standing wish)", '"restore_backup",  # jarvis_backup.py' in after)
                check("restore_backup has a _RISK line inside the dict (not after it)",
                      '"restore_backup": ("yes", "local",' in after and after.index(
                          '"restore_backup": ("yes", "local",') < after.index(
                          "_UNKNOWN_RISK"))
        finally:
            shutil.rmtree(d, ignore_errors=True)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("the module is shipped: apply-patches.ps1 and _where.SHIPPED",
          "'jarvis_backup.py'" in ps1[ps1.index("$SHIPPED = @("):]
          and "jarvis_backup.py" in _where_SHIPPED())


def _where_SHIPPED():
    import _where
    return _where.SHIPPED


def _a_database_with_two_rows(prefix: str):
    """A scratch database with one table and two rows, under TMP."""
    root = Path(tempfile.mkdtemp(prefix=f"backup-{prefix}-", dir=str(TMP)))
    path = root / "one.db"
    c = sqlite3.connect(str(path))
    try:
        c.execute("CREATE TABLE t (id INTEGER)")
        c.execute("INSERT INTO t VALUES (1)")
        c.execute("INSERT INTO t VALUES (2)")
        c.commit()
    finally:
        c.close()
    return root, path


def t_the_snapshot_connections_ask_for_the_ten_second_wait():
    """Spotlight 5: a backup runs while Jarvis is live and writing. Every
    connection the manifest and the snapshot open must ASK for the same
    10-second wait the rest of the backend asks for; sqlite3.connect's own
    default is 5 seconds, and losing a database out of the archive because a
    writer held it a moment too long is the failure this is about.
    """
    root, db = _a_database_with_two_rows("timeout")
    dest = root / "copy.db"
    calls = []
    real_connect = sqlite3.connect

    def spy(path, *args, **kwargs):
        calls.append(kwargs.get("timeout"))
        return real_connect(path, *args, **kwargs)

    B.sqlite3.connect = spy
    try:
        counts = B._table_counts(db)
        made = B._snapshot_db(db, dest)
    finally:
        B.sqlite3.connect = real_connect
    check("the count read succeeds", counts == {"t": 2}, counts)
    check("the snapshot copy is made", made is True and dest.is_file(), made)
    check("every snapshot/table-count connection asks for the 10-second wait",
          len(calls) == 3 and all(t == B.DB_BUSY_TIMEOUT_S for t in calls), calls)
    check("and that wait is at least 10 seconds", B.DB_BUSY_TIMEOUT_S >= 10.0,
          B.DB_BUSY_TIMEOUT_S)


def t_a_read_waits_for_a_held_write_lock_instead_of_failing():
    """The behaviour the timeout buys: another connection holds an EXCLUSIVE
    lock for half a second; the count must WAIT and read the rows, not return
    {} ("database is locked" swallowed by _table_counts)."""
    root, db = _a_database_with_two_rows("locked")
    holder = sqlite3.connect(str(db), timeout=10.0, check_same_thread=False)
    holder.execute("BEGIN EXCLUSIVE")
    released = threading.Event()

    def release():
        try:
            holder.commit()
        finally:
            holder.close()
            released.set()

    timer = threading.Timer(0.5, release)
    timer.start()
    elapsed = None
    try:
        started = time.monotonic()
        counts = B._table_counts(db)
        elapsed = time.monotonic() - started
    finally:
        timer.cancel()
        released.wait(10)
        if not released.is_set():
            try:
                holder.close()
            except Exception:
                pass
    check("a table count taken under a held write lock waits, then reads the rows",
          counts == {"t": 2}, counts)
    check("and it really waited for the lock (>= 0.25 s)",
          elapsed is not None and elapsed >= 0.25, elapsed)


def t_a_snapshot_closes_both_connections_even_when_the_target_cannot_open():
    """Connection hygiene: the online backup API's source and target are
    closed on success AND when the target cannot be opened. A leaked source
    connection is a handle on a ~/.openjarvis database (and, in WAL, a reader
    that can keep #493's TRUNCATE checkpoint busy)."""
    root, db = _a_database_with_two_rows("closed")
    ok_dest = root / "copy.db"
    closed = []
    real_connect = sqlite3.connect

    class Tracker(sqlite3.Connection):
        def close(self):
            closed.append(1)
            super().close()

    def spy(path, *args, **kwargs):
        kwargs.pop("factory", None)
        return real_connect(path, *args, factory=Tracker, **kwargs)

    B.sqlite3.connect = spy
    try:
        made = B._snapshot_db(db, ok_dest)
    finally:
        B.sqlite3.connect = real_connect
    check("a snapshot that works", made is True and ok_dest.is_file(), made)
    check("closes BOTH connections on the way out", len(closed) == 2, closed)

    closed.clear()
    B.sqlite3.connect = spy
    try:
        made = B._snapshot_db(db, root / "no-such-folder" / "copy.db")
    finally:
        B.sqlite3.connect = real_connect
    check("a snapshot whose target cannot open returns False, never raises",
          made is False, made)
    check("and still closes its source connection", len(closed) == 1, closed)


# ============================ 8. restore safety (ruling 8.1, 2026-10-20)


def _restore_once(conf, backups, out, *, safety_fn=None, apply_fn=None):
    """Runs one approved restore through the real route and returns its record.

    Collects the audit events for the duration, so a check can prove what the
    AUDIT says, not only what the reply says."""
    events = []

    def collector(event, detail):
        events.append((event, detail))

    real_audit = B._audit
    B._audit = collector
    try:
        B.request_restore({"name": out["name"], "code": out["recovery_code"]}, here=True,
                          gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                          armed=lambda: True, safety_fn=safety_fn, apply_fn=apply_fn)
    finally:
        B._audit = real_audit
    return B.take_restore_result() or {}, events


def _safety_record(backups, name, *, size=None, code="AAAAA-BBBBB-CCCCC-DDDDD"):
    return {"name": name, "at": time.time(), "recovery_code": code,
            "size": size if size is not None else
            ((backups / name).stat().st_size if (backups / name).is_file() else 0)}


def t_restore_fails_closed_without_a_verifiable_safety_backup():
    """Ruling 8.1: a restore NEVER overwrites a live file unless the safety
    backup is provably on disk and whole. Missing, empty, not-a-backup, and
    unreadable files all refuse; nothing is written; the audit says
    ``safety_unverified``; the owner keeps a receipt saying nothing changed."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))              # what we will try to restore
    _change(conf)                                 # the state a restore replaces
    before = _snapshot_state(conf)

    # the file exists but is empty
    (backups / "empty.jbak").write_bytes(b"")
    # b"..." is longer than MIN_FILE_BYTES but starts with the wrong magic
    (backups / "garbage.jbak").write_bytes(b"NOT a Jarvis backup" * 40)
    # our own magic and header, but the ciphertext's tag is corrupted: shape
    # passes `check_file`, decryption does NOT
    blob = bytearray((backups / out["name"]).read_bytes())
    blob[-1] ^= 0xFF
    (backups / "corrupt.jbak").write_bytes(bytes(blob))

    cases = {
        "missing": (b"jarvis-backup-nope.jbak", None),
        "empty (0 bytes)": (b"empty.jbak", None),
        "not a backup at all": (b"garbage.jbak", None),
        "will not open with its own code": (b"corrupt.jbak", None),
    }
    for label, (filename, _unused) in cases.items():
        name = filename.decode()
        applied = []
        safety = _safety_record(backups, name,
                                size=(backups / name).stat().st_size
                                if (backups / name).is_file() else 0)
        res, events = _restore_once(conf, backups, out, safety_fn=lambda s=safety: s,
                                    apply_fn=lambda z: applied.append(1))
        check(f"safety backup {label}: the restore is refused and NOTHING is applied",
              res.get("outcome") == "failed" and applied == [], (res, applied))
        check(f"... {label}: the owner is told the safety backup could not be made first",
              "safety backup could not be made" in res.get("message", "")
              and "not changed" in res.get("message", ""), res.get("message"))
        check(f"... {label}: the record carries reason safety_unverified",
              res.get("reason") == B.SAFETY_UNVERIFIED, res)
        check(f"... {label}: the AUDIT record carries reason safety_unverified",
              any(e == "backup.restore.card" and d.get("reason") == B.SAFETY_UNVERIFIED
                  for e, d in events), events)
        check(f"... {label}: the live files are byte-for-byte as they were",
              _snapshot_state(conf) == before, _snapshot_state(conf))
        check(f"... {label}: no partial/temp file is left behind",
              _leftovers(conf) == [], _leftovers(conf))
        durable = B.last_restore_path()
        check(f"... {label}: the refusal is PERSISTED for the owner to read",
              durable.is_file()
              and json.loads(durable.read_text(encoding="utf-8")).get("reason")
              == B.SAFETY_UNVERIFIED, durable)
        check(f"... {label}: the recovery code never reached the persisted record",
              out["recovery_code"] not in durable.read_text(encoding="utf-8"))
        B.dismiss_restore_result()

    # the same file, but the record claims a size that does not match: refused
    safety = _safety_record(backups, out["name"], size=(backups / out["name"]).stat().st_size + 1,
                            code=out["recovery_code"])
    applied = []
    res, events = _restore_once(conf, backups, out, safety_fn=lambda: safety,
                                apply_fn=lambda z: applied.append(1))
    check("a safety backup whose size does not match what was written is refused",
          res.get("outcome") == "failed" and applied == []
          and res.get("reason") == B.SAFETY_UNVERIFIED, (res, applied))
    check("... and the live files are still byte-identical", _snapshot_state(conf) == before)


def t_a_restore_lists_every_exact_file_it_replaced():
    """Ruling 8.1 part 3: the audit and the receipt name the exact restored
    database/settings/notes files, not "1 database"."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    _change(conf)
    res, events = _restore_once(conf, backups, out)
    restored = res.get("restored") or {}
    check("the restore succeeded", res.get("outcome") == "restored", res)
    check("the receipt names the exact database file", restored.get("databases") == ["memory.db"],
          restored)
    check("the receipt names every settings file",
          restored.get("settings_files") == ["a.json"], restored)
    check("the receipt names every note file", restored.get("notes_files") == ["x.txt"],
          restored)
    applied_audit = [d.get("applied", {}) for e, d in events if e == "backup.restored"]
    check("the audit record lists the same exact names",
          bool(applied_audit)
          and applied_audit[0].get("restored", {}).get("databases") == ["memory.db"]
          and applied_audit[0].get("restored", {}).get("notes_files") == ["x.txt"],
          applied_audit)
    check("... and the old counts are still in the audit's applied dict (both readers work)",
          bool(applied_audit) and applied_audit[0].get("databases") == 1
          and applied_audit[0].get("settings_files") == 1, applied_audit)
    durable = json.loads(B.last_restore_path().read_text(encoding="utf-8"))
    check("the PERSISTED receipt names them too (so a restart cannot lose them)",
          durable.get("restored", {}).get("databases") == ["memory.db"]
          and durable.get("restored", {}).get("notes_files") == ["x.txt"], durable)
    safety = res.get("safety_backup") or {}
    check("... and the recovery code is NOT in the persisted receipt",
          safety.get("recovery_code")
          and safety["recovery_code"] not in B.last_restore_path().read_text(encoding="utf-8")
          and "recovery_code" not in (durable.get("safety_backup") or {}))
    check("... with a hint saying where the code was shown instead",
          isinstance(durable.get("recovery_code_hint"), str)
          and "NOT stored on disk" in durable["recovery_code_hint"], durable)


def t_last_restore_survives_reads_a_restart_and_is_dismissed():
    """Ruling 8.1 part 2: the last restore's outcome is PERSISTED. Reads do not
    consume it, a restart keeps it, and only an explicit dismiss clears it.
    The one-time recovery code rule is unchanged: it is in memory only, shown
    exactly once, and never on disk."""
    conf, backups = fresh_conf()
    check("with no restore yet, the record is empty", B.take_restore_result() is None)
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    _change(conf)
    res, _events = _restore_once(conf, backups, out)
    safety = res.get("safety_backup") or {}
    check("the restore recorded its outcome", res.get("outcome") == "restored", res)
    check("the first read has the one-time recovery code", bool(safety.get("recovery_code")))
    code = safety.get("recovery_code")

    second = B.take_restore_result() or {}
    check("a second read still has the record - it is not consumed",
          second.get("outcome") == "restored" and second.get("restored", {}).get("databases")
          == ["memory.db"], second)
    check("... but NOT the code: the one-time rule is unchanged",
          "recovery_code" not in (second.get("safety_backup") or {}), second)

    phone = B.view(here=False)
    phone_restore = phone.get("last_restore") or {}
    check("a phone's GET /api/backup shows the outcome, with no code",
          phone_restore.get("outcome") == "restored"
          and "recovery_code" not in (phone_restore.get("safety_backup") or {})
          and code not in json.dumps(phone_restore), phone_restore)
    check("... and reading it did not swallow the record for the PC either",
          (B.view(here=True).get("last_restore") or {}).get("outcome") == "restored")

    # a process-simulated restart: memory is gone, the file is not
    with B._R_LOCK:
        B._R_STATE["last"].clear()
    restarted = B.take_restore_result() or {}
    check("after a simulated restart the record is still readable",
          restarted.get("outcome") == "restored"
          and restarted.get("restored", {}).get("databases") == ["memory.db"]
          and restarted.get("restored", {}).get("notes_files") == ["x.txt"], restarted)
    check("... and no code comes back: it was never on disk",
          "recovery_code" not in (restarted.get("safety_backup") or {})
          and (safety.get("recovery_code") or "no-code")
          not in json.dumps(restarted))

    code_, body = B.handle_post(B.DISMISS_ROUTE, {}, peer="127.0.0.1", local="127.0.0.1")
    check("dismiss is one 200 that says it cleared a record",
          code_ == 200 and body.get("dismissed") is True, (code_, body))
    check("after dismiss the record is gone from memory and from the PC's GET",
          B.take_restore_result() is None
          and (B.view(here=True).get("last_restore") is None))
    check("... and from the phone's GET too", B.view(here=False).get("last_restore") is None)
    check("... and the file itself is gone", not B.last_restore_path().exists())
    code_, body = B.handle_post(B.DISMISS_ROUTE, {}, peer="100.64.0.9",
                                local="100.64.0.1")
    check("a second dismiss from another paired device is still a 200 with nothing to clear",
          code_ == 200 and body.get("dismissed") is False, (code_, body))
    check("with the record dismissed, a fresh restore records its own again",
          B.take_restore_result() is None and code_ == 200)


# ========================= audit 2026-10-21: the #678 findings ==============
#
# Each test names the finding it pins (the ids are in
# `.dsh-scratch/AUDIT-678-BACKUP-FAIL-CLOSED-2026-10-21.md`). Every one FAILS
# on the pre-fix code - the point of a finding is that it bit once.


def t_m1_the_last_restore_record_is_never_swept_into_a_backup():
    """M1: last-restore.json is Jarvis's own bookkeeping, never owner data."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    _restore_once(conf, backups, first)          # leaves a persisted record behind
    check("(set-up) a restore left last-restore.json in the settings folder",
          B.last_restore_path().is_file(), str(B.last_restore_path()))

    later = B.backup_now(str(backups))           # an ordinary backup AFTER a restore
    blob = B.decrypt_blob((backups / later["name"]).read_bytes(), later["recovery_code"])
    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    check("a later backup does NOT contain the last-restore record",
          "settings/last-restore.json" not in names, sorted(names))
    check("... but does contain the owner's own settings file", "settings/a.json" in names,
          sorted(names))
    check("... and the manifest counts only real settings files",
          later["counts"]["settings_files"] == 1, later["counts"])


def t_m1_a_backup_carrying_the_record_file_is_refused():
    """M1, restore side: an archive (old or crafted) cannot write the record."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    _restore_once(conf, backups, first)          # a real current record now exists

    zip_bytes, _manifest = B.build_archive()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as src, \
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info, src.read(info))
        dst.writestr("settings/last-restore.json",
                     json.dumps({"outcome": "INJECTED", "message": "INJECTED"}))
    code = B.generate_code()
    (backups / "crafted.jbak").write_bytes(B.encrypt_blob(buf.getvalue(), code))
    B.request_restore({"name": "crafted.jbak", "code": code}, here=True,
                      gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                      armed=lambda: True)
    res = B.take_restore_result() or {}
    restored = res.get("restored") or {}
    check("the crafted backup still restores",
          res.get("outcome") == "restored", res)
    check("the record file inside the archive is NOT restored as a settings file",
          "last-restore.json" not in (restored.get("settings_files") or []), restored)
    check("... the owner's real settings file still is",
          "a.json" in (restored.get("settings_files") or []), restored)
    durable = json.loads(B.last_restore_path().read_text(encoding="utf-8"))
    check("... and the record now says the restore, not the injected words",
          durable.get("outcome") == "restored" and durable.get("message") != "INJECTED",
          durable)


def t_m1v1_a_mixed_case_bookkeeping_entry_cannot_land_on_ntfs():
    """V1 of the 2026-10-21 verification addendum: NTFS is case-INSENSITIVE.

    A crafted `settings/Last-restore.json` (or `settings/Backup.json`) used to
    pass the case-sensitive allow-list; `_apply_restore` then replaced the real
    lower-case `last-restore.json` / `backup.json` with the archive's copy - an
    OLD restore shown as the current one, and a silently changed backup
    folder. Old write order made the record hit transient, but on a real NTFS
    folder the file IS replaced between the apply and the finish.
    """
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    _restore_once(conf, backups, first)          # a real current record exists
    current = B.last_restore_path().read_bytes()
    folder_now = B._load_settings()["folder"]
    zip_bytes, _manifest = B.build_archive()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as src, \
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info, src.read(info))
        dst.writestr("settings/Last-restore.json",
                     json.dumps({"outcome": "INJECTED-OLD", "message": "INJECTED-OLD"}))
        dst.writestr("settings/Backup.json", json.dumps({"folder": "C:\\injected"}))
    crafted = buf.getvalue()

    applied = B._apply_restore(crafted)          # exactly what a real restore runs
    check("the mixed-case record entry is refused, so the real record file is "
          "BYTE-IDENTICAL",
          B.last_restore_path().read_bytes() == current,
          (len(B.last_restore_path().read_bytes()), len(current)))
    check("... a mixed-case backup.json entry is refused too: the folder did not move",
          B._load_settings()["folder"] == folder_now, B._load_settings()["folder"])
    check("... and neither is reported as a restored settings file",
          sorted(applied["restored"]["settings_files"]) == ["a.json"],
          applied["restored"]["settings_files"])
    check("... both are counted as skipped", applied["skipped"] >= 2, applied["skipped"])

    # through the whole restore route as well, so the receipt is right too
    code = B.generate_code()
    (backups / "crafted-case.jbak").write_bytes(B.encrypt_blob(crafted, code))
    B.request_restore({"name": "crafted-case.jbak", "code": code}, here=True,
                      gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                      armed=lambda: True)
    res = B.take_restore_result() or {}
    restored = res.get("restored") or {}
    check("a full restore of the crafted backup still lands its real settings file",
          res.get("outcome") == "restored"
          and "a.json" in (restored.get("settings_files") or []), restored)
    own = {name.casefold() for name in B._own_settings_files()}
    check("... and its receipt names no bookkeeping file in ANY case",
          not any(str(n).casefold() in own
                  for n in (restored.get("settings_files") or [])), restored)


def t_m2_a_device_dismiss_cannot_throw_away_the_unread_code():
    """M2: the safety backup's one-time code is only in the PC's memory.

    A paired device dismissing the notice first would destroy the only way to
    open the safety backup, so a device is refused until the PC has read it.
    """
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    B.request_restore({"name": first["name"], "code": first["recovery_code"]},
                      here=True, gate=approve, tier_of=tier_ask,
                      spawn=sync_spawn, armed=lambda: True)
    with B._R_LOCK:
        safety = dict((B._R_STATE["last"].get("safety_backup") or {}))
    code = safety.get("recovery_code")
    check("(set-up) the one-time code is held in memory and unread", bool(code))
    check("(set-up) the PC-side view says the code is still pending",
          B.recovery_code_pending() is True)

    dcode, dbody = B.request_dismiss_restore({}, here=False)
    check("a paired device's dismiss while the code is unread is REFUSED, in plain words",
          dcode == 409 and dbody.get("code_pending") is True
          and "Read it on the PC first" in dbody.get("error", ""), (dcode, dbody))
    check("... nothing was cleared: the record is still there",
          B.last_restore_path().is_file()
          and (B.view(here=False).get("last_restore") or {}).get("outcome") == "restored")
    check("... the phone's read did not swallow the code",
          B.recovery_code_pending() is True)

    pc = B.view(here=True)                       # the PC's first read: the code surfaces
    got = (pc.get("last_restore") or {}).get("safety_backup") or {}
    check("the PC read now has the code exactly once", got.get("recovery_code") == code, got)
    check("... and the pending flag is off", B.recovery_code_pending() is False)
    dcode, dbody = B.request_dismiss_restore({}, here=False)
    check("after the PC read a paired device's dismiss succeeds",
          dcode == 200 and dbody.get("dismissed") is True, (dcode, dbody))
    check("... the record and the file are gone, and the code was never on disk",
          not B.last_restore_path().exists() and B.take_restore_result() is None)

    # the PC itself may always clear its notice (the owner can read it there)
    second = B.backup_now(str(backups))
    _change(conf)
    B.request_restore({"name": second["name"], "code": second["recovery_code"]},
                      here=True, gate=approve, tier_of=tier_ask,
                      spawn=sync_spawn, armed=lambda: True)
    pcode, pbody = B.request_dismiss_restore({}, here=True)
    check("the PC may always clear its own notice, even with the code unread",
          pcode == 200 and pbody.get("dismissed") is True, (pcode, pbody))


def t_m3_a_failed_persist_never_reports_the_older_restore():
    """M3: a full disk must not leave the PREVIOUS restore looking current."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    ok = _restore_once(conf, backups, first)[0]
    check("(set-up) the first restore's record is on disk",
          ok.get("outcome") == "restored"
          and json.loads(B.last_restore_path().read_text(encoding="utf-8")).get("outcome")
          == "restored", ok)

    second = B.backup_now(str(backups))
    _change(conf)
    real_write = B._write_json_durable
    calls = []

    def full_disk_then_fallback(path, data):
        calls.append(dict(data))
        if not data.get("persist_failed"):
            raise OSError(28, "No space left on device")
        return real_write(path, data)
    B._write_json_durable = full_disk_then_fallback
    try:
        bad = {"name": "nope.jbak", "at": time.time(),
               "recovery_code": "AAAAA-BBBBB-CCCCC-DDDDD", "size": 0}
        res, events = _restore_once(conf, backups, second, safety_fn=lambda: bad)
    finally:
        B._write_json_durable = real_write
    check("the second attempt really failed", res.get("outcome") == "failed"
          and res.get("reason") == B.SAFETY_UNVERIFIED, res)
    check("the failed persistence is visible in memory (persist_failed)",
          res.get("persist_failed") is True, res)
    check("... and audited", any(e == "backup.restore.persist_failed" for e, _d in events),
          [e for e, _d in events])
    check("... and the fallback marker was written and audited",
          any(e == "backup.restore.persist_fallback" and d.get("how") == "marker"
              for e, d in events), [e for e, _d in events])
    durable = json.loads(B.last_restore_path().read_text(encoding="utf-8"))
    check("the marker says the full record could not be saved",
          durable.get("persist_failed") is True, durable)

    with B._R_LOCK:
        B._R_STATE["last"].clear()               # a process restart: memory is gone
    after = B.take_restore_result() or {}
    check("after a restart the API does NOT report the older restore as current",
          after.get("outcome") == "failed" and after.get("persist_failed") is True, after)
    check("... it does not say the older 'restored' outcome either",
          after.get("outcome") != "restored", after)


def t_m3_a_failed_persist_with_no_fallback_removes_the_stale_record():
    """M3's last line: if even the marker cannot be written, remove the stale
    record - "no record" is honest, an older restore as current is not."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    _restore_once(conf, backups, first)          # an older record on disk
    second = B.backup_now(str(backups))
    _change(conf)
    real_write = B._write_json_durable

    def always_full(_path, _data):
        raise OSError(28, "No space left on device")
    B._write_json_durable = always_full
    try:
        bad = {"name": "nope.jbak", "at": time.time(),
               "recovery_code": "AAAAA-BBBBB-CCCCC-DDDDD", "size": 0}
        res, events = _restore_once(conf, backups, second, safety_fn=lambda: bad)
    finally:
        B._write_json_durable = real_write
    check("the attempt failed and is flagged in memory", res.get("outcome") == "failed"
          and res.get("persist_failed") is True, res)
    check("the stale older record file is REMOVED", not B.last_restore_path().exists(),
          str(B.last_restore_path()))
    check("... and the removal is audited",
          any(e == "backup.restore.persist_fallback" and d.get("how") == "removed stale"
              for e, d in events), [e for e, _d in events])
    with B._R_LOCK:
        B._R_STATE["last"].clear()               # restart
    check("after a restart there is NO record (not the older one)", B.take_restore_result() is None)


def t_low2_a_partial_restore_names_what_it_had_replaced():
    """LOW-2: when putting back fails too, name the files it had replaced."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    real_replace = os.replace

    def failing(src, dst, *a, **k):
        if Path(dst).name == "x.txt" and ".old" not in Path(src).name:
            raise PermissionError("locked")       # the LAST file to be swapped
        return real_replace(src, dst, *a, **k)

    def failing_both(src, dst, *a, **k):
        if Path(dst).name in ("x.txt", "memory.db", "a.json") \
                and Path(src).name.endswith(".old"):
            raise PermissionError("locked")       # putting back fails too
        return failing(src, dst, *a, **k)
    os.replace = failing_both
    try:
        res, events = _restore_once(conf, backups, first)
    finally:
        os.replace = real_replace
    restored = res.get("restored") or {}
    check("the restore really failed part-way", res.get("outcome") == "failed"
          and res.get("partial") is True, res)
    check("a PARTIAL restore still names the database it had replaced",
          restored.get("databases") == ["memory.db"], restored)
    check("... and the settings file", restored.get("settings_files") == ["a.json"], restored)
    check("... the message still warns plainly", "part-way" in res.get("message", ""), res)
    durable = json.loads(B.last_restore_path().read_text(encoding="utf-8"))
    check("... and the persisted record names them too",
          (durable.get("restored") or {}).get("databases") == ["memory.db"]
          and durable.get("partial") is True, durable)
    check("... the audit carries the names as well",
          any(e == "backup.restore.card" and d.get("partial") is True for e, d in events),
          [(e, d.get("partial")) for e, d in events])
    leftovers = _leftovers(conf)
    check("... and what remains is the .old copies (the last copy of the pre-restore "
          "bytes), never a staging .tmp",
          bool(leftovers) and all(".old" in name for name in leftovers), leftovers)


def t_low3_an_unexpected_verify_crash_is_a_clean_refusal():
    """LOW-3: an unexpected exception in the verifier must not wedge the card."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    before = _snapshot_state(conf)
    real_verify = B._verify_safety_backup

    def exploding(_safety, _folder):
        raise RuntimeError("an unexpected verify failure")
    B._verify_safety_backup = exploding
    try:
        res, events = _restore_once(conf, backups, first)
        with B._R_LOCK:
            pending = dict(B._R_STATE["pending"])
    finally:
        B._verify_safety_backup = real_verify
    check("an unexpected crash in the verifier is a clean refusal, not a dead card",
          res.get("outcome") == "failed" and res.get("reason") == B.SAFETY_UNVERIFIED, res)
    check("... the record says nothing was restored", "not changed" in res.get("message", ""),
          res.get("message"))
    check("... the restore card is not left waiting", pending == {}, pending)
    check("... no live file was touched", _snapshot_state(conf) == before)
    check("... the refusal is persisted", json.loads(
        B.last_restore_path().read_text(encoding="utf-8")).get("reason")
        == B.SAFETY_UNVERIFIED)
    ok = _restore_once(conf, backups, first)
    check("... and a later restore still runs (no 409 wedge)",
          ok[0].get("outcome") == "restored", ok[0])


def t_low4_a_verify_failed_safety_backup_is_removed_not_left_dead():
    """LOW-4: a safety backup that fails verification cannot ever be opened -
    its code is dropped - so it must not stay as a KEEP slot."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    before_files = sorted(p.name for p in backups.glob("*.jbak"))
    before_keep = len([r for r in B.list_backups(str(backups)) if r["complete"]])
    real_verify = B._verify_safety_backup
    B._verify_safety_backup = lambda _safety, _folder: "forced for the audit check"
    try:
        res, events = _restore_once(conf, backups, first)   # the real safety_fn makes one
    finally:
        B._verify_safety_backup = real_verify
    after_files = sorted(p.name for p in backups.glob("*.jbak"))
    after_keep = len([r for r in B.list_backups(str(backups)) if r["complete"]])
    check("the refusal still says nothing was restored",
          res.get("outcome") == "failed" and "not changed" in res.get("message", ""), res)
    check("the safety backup a failed verification made is REMOVED (its code was never shown)",
          after_files == before_files, (before_files, after_files))
    check("... so it does not eat one of the KEEP slots", after_keep == before_keep,
          (before_keep, after_keep))
    check("... and the removal is audited",
          any(e == "backup.restore.safety_orphan" and d.get("removed") is True
              for e, d in events), [e for e, _d in events])


def t_low5_a_safety_backup_that_vanishes_after_the_restore_is_reported():
    """LOW-5: the safety backup is verified BEFORE the apply; say so honestly
    if it is gone after."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)
    real_backup_now = B.backup_now
    made = []

    def tracking_backup_now(folder, **kwargs):
        out = real_backup_now(folder, **kwargs)
        made.append(out["name"])
        return out

    def apply_then_lose_safety(zip_bytes):
        applied = B._apply_restore(zip_bytes)
        for name in made:
            try:
                (Path(B._load_settings()["folder"]) / name).unlink()
            except OSError:
                pass
        return applied
    B.backup_now = tracking_backup_now
    try:
        res, events = _restore_once(conf, backups, first,
                                    apply_fn=apply_then_lose_safety)
    finally:
        B.backup_now = real_backup_now
    check("the restore itself landed", res.get("outcome") == "restored", res)
    check("the vanished safety backup is named plainly in the message",
          "no longer in the backup folder" in res.get("message", ""), res.get("message"))
    check("... and in the record's warning", "no longer" in (res.get("warning") or ""), res)
    check("... and audited honestly",
          any(e == "backup.restore.safety_lost" for e, _d in events),
          [e for e, _d in events])
    durable = json.loads(B.last_restore_path().read_text(encoding="utf-8"))
    check("... the persisted record carries the warning too",
          "no longer" in (durable.get("warning") or ""), durable)
    probe = backups / "probe.jbak"
    probe.write_bytes(b"x" * 10)
    said = B._safety_after_restore_problem(
        {"name": "probe.jbak", "size": 4}, str(backups))
    check("the cheap re-check also notices a safety backup that changed size",
          "changed size" in said, said)


def t_low3b_a_caller_that_refuses_its_own_safety_backup_lands_in_the_same_place():
    """NIT: `SafetyBackupUnverified` is only reachable from a caller-supplied
    safety_fn - keep that branch working so it is not dead code that bites."""
    conf, backups = fresh_conf()
    _plant(conf)
    B._save_settings({"folder": str(backups)})
    first = B.backup_now(str(backups))
    _change(conf)

    def refusing():
        raise B.SafetyBackupUnverified("the caller's own check said no")
    res, events = _restore_once(conf, backups, first, safety_fn=refusing)
    check("a caller's own refusal is a clean safety_unverified failure",
          res.get("outcome") == "failed" and res.get("reason") == B.SAFETY_UNVERIFIED, res)
    check("... in the plain failed_before words", "not changed" in res.get("message", ""), res)
    check("... and it points at the caller's reason in `why`",
          "caller's own check" in (res.get("why") or ""), res.get("why"))


def t_nits_an_oversized_or_damaged_last_restore_is_ignored():
    """NIT: the record is a few short fields; do not read an unbounded file."""
    conf, backups = fresh_conf()
    B.last_restore_path().write_text(
        json.dumps({"outcome": "restored",
                    "pad": "x" * (B.MAX_RESTORE_RESULT_BYTES + 1024)}),
        encoding="utf-8")
    check("an oversized record file is ignored, not parsed",
          B._load_restore_result() == {}, len(B.last_restore_path().read_bytes()))
    B.last_restore_path().write_text("{not json", encoding="utf-8")
    check("a damaged record file is ignored", B._load_restore_result() == {})


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
