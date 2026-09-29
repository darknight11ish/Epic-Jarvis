"""jarvis_backup.py - one locked backup file, a recovery code, restore with a
card (the owner's decision of 2026-09-27, CLAUDE.md; the design in
docs/CUTTING-EDGE-2026-09-26-round2-trust.md, "2. Encrypted backup and plain
restore"). docs/JARVIS-API.md section 45.

NEW MODULE, shipped whole. backup.patch adds one call at start-up,
`install(Handler, ...)`, which answers the six routes below (the same shape
as jarvis_documents.py).

THE OWNER'S DECISION (CLAUDE.md, 2026-09-27, answering
docs/OWNER-QUESTIONS-2026-09-27.md): "one locked backup file into a folder
the owner picks, a NordLocker (or other cloud-synced) folder included.
Locked with a recovery code only the owner has (shown once); Jarvis keeps
only the last few. This bends rule 1 for that one locked file only, and the
app must say plainly that a lost code means a useless backup and that
erased facts stay in older backups until they age out."

THIS BENDS RULE 1 (docs/ARCHITECTURE.md invariant 1), on purpose, for this
one file only: a folder the owner picks can be one a cloud-sync program
(NordLocker, OneDrive, ...) uploads. Jarvis itself sends nothing anywhere -
it only writes one encrypted file to a folder on this PC, exactly as
"Folders Jarvis may look in" does - but if that folder is synced, the sync
program uploads it, the same as anything else the owner puts there. That is
the whole exception: one named file, encrypted before it is written, never
readable without a recovery code only the owner ever holds.

THE FOLDER - reused exactly, "Folders Jarvis may look in"'s own picker
  * Setting it: only from this PC (jarvis_owner_check.from_this_pc), ONE
    approval card (action `change_own_config`, tier "ask" only - the same
    action jarvis_documents.py uses for adding a folder). Refused for the
    same places `jarvis_documents.check_folder` refuses (a drive's top, the
    whole user folder, Windows' folders, protected places): imported from
    there, not copied, so the two lists of refusals can never drift apart.
    A NordLocker-synced folder is an ordinary folder to Windows, so nothing
    special is needed for it.
  * "Back up now": no card. The owner already approved the folder, and
    pressing the button on the PC is the same shape as the Notion import
    (jarvis_documents.py) - an explicit action the owner started, writing
    only into a folder already on the list.

WHAT IS BACKED UP - verified against this repository's real file names,
2026-09-27 (the design doc's names had drifted: it said "history.db"; the
real file, made by jarvis_chat_log.py, is "chat-history.db")
  * Four SQLite databases, snapshotted with the online backup API
    (`sqlite3.Connection.backup`, safe while Jarvis keeps them open):
    memory.db, chat-history.db, schedule.db, feedback.db.
  * Every `*.json` file directly in the Jarvis settings folder (folders.
    json, asks_first.json, manner.json, and so on) - never a subfolder, so
    this glob can never reach into "voice" or "notes" by accident.
  * jarvis-framework.toml, wherever `jarvis_framework.config_path()` finds
    the owner's real copy.
  * The notes folder (`notes/`) and the voice enrolment folder (`voice/` -
    the owner's own voice-print, NOT `voice-models/`, which holds
    downloaded engine files, or `voices/`, the custom-voice bank), both
    copied whole, recursively.
  * The chat-history encryption key, read from Windows Credential Manager
    (jarvis_chat_log.CredentialKey, KEY_TARGET) and kept, base64, as ONE
    small file INSIDE the archive - which is encrypted before it ever
    touches a disk, so the key is never written out in the clear.

EXPLICITLY NOT BACKED UP (CLAUDE.md rule 3; the owner's own words)
  * The pairing token and every API key (Exa, Tavily, Brave, GitHub, ...):
    all of them live in Windows Credential Manager under their OWN target
    names (jarvis_token_store.py, jarvis_search.py) - never in a `*.json`
    settings file - and this module reads exactly one Credential Manager
    entry, the chat-history key, and no other. A key that is re-entered
    once, on the PC that needs it, is safer than one that can be dug out of
    a backup file years later.
  * Model files (large, and Ollama already keeps its own copy) and logs
    (`*.log` in the settings folder - the `*.json` glob above never matches
    them).
  * approvals.db and holds.db (pending-approval state, not memory - restoring
    a stale "waiting" row would be misleading, never a security hole: the
    in-memory approval stamp, jarvis_owner_check.stamp, is gone the moment
    the backend restarts, so nothing written into approvals.db by a restore
    can forge an approval).

THE LOCK - AES-256-GCM with a key stretched from the recovery code by
Argon2id (`cryptography`, already a dependency here for chat history and
already pinned in requirements.lock at 50.0.1, which has had Argon2id since
44.0.0). NOT the `pyrage`/age route the design doc offered as its other
option: this repository pins every dependency with hashes
(requirements.lock, tools/check_python_advisories.py) and a brand-new
package needs that lock remade and re-checked before it can ship. (Said
plainly, security/privacy audit 2026-09-27: apply-patches.ps1 still
installs from requirements.txt, not the lock, and leaves an installed
package alone - so the PC's `cryptography` is whatever was there first. One
older than 44.0.0 has no Argon2id; the import below then fails and backing
up refuses in words, never writing anything unencrypted.) A package
already here, already reviewed and already the exact tool this job needs,
is the lower-friction and no less honest choice. The cost, said plainly:
`age -d` cannot open this file - only Jarvis, or someone who reads this
docstring and reimplements the format below, can.

    b"JBAK1" | argon2 lanes (1 byte) | argon2 memory KiB (4 bytes) |
    argon2 iterations (4 bytes) | salt (16 bytes) | nonce (12 bytes) |
    AES-256-GCM(zip bytes), AAD = every byte before the ciphertext

The recovery code (`generate_code`) is 20 characters from a 32-symbol
alphabet with no 0/O/1/I/L (about 100 bits) - typed once, shown once, in
four groups of five. It is NEVER written to a file, a log, or the audit
trail, and this module has no code path that could recover it: the only
way to open a backup is to have kept the code that made it. Said plainly,
in every place the code is shown and on the restore card: A LOST CODE MEANS
A USELESS BACKUP - there is no way in without it. And: "Erase the words"
cannot reach into an OLDER backup that still holds an erased fact's
original text; it only stops mattering once every backup kept from before
the erase has aged out (KEEP, below).

RETENTION - the newest KEEP (5) backup files in the folder are kept; making
a new one deletes the rest. Five, not three, because a card is shown for
each restore anyway (so keeping more costs disk, not safety), and not more
than five because a folder that is also synced to the cloud should not grow
without bound. Named `jarvis-backup-<UTC time>.jbak`, sorted by that name.

RESTORE - pick a file, type its code, see COUNTS and a DATE only (read from
the archive's own manifest.json, never any content) as a preview
(`preview_restore`); then ONE approval card that ALWAYS needs Windows Hello
and ALWAYS comes from this PC (action `restore_backup`, in
jarvis_owner_check.PC_ONLY_ACTIONS - the same mechanism
`loosen_what_asks_first` and `enable_reading_tool` already use), whatever
the gate's own risk table would say on its own: replacing everything Jarvis
knows is exactly the kind of action that must never go through on a stolen
token from another device. Before the restore itself, Jarvis backs up the
CURRENT state first, automatically, with a FRESH recovery code shown once
in the same response - so the restore itself can be undone, and the owner
is told the one code they need to undo it.

Restore only ADDS AND OVERWRITES; it never deletes a file that is not in
the backup. Said plainly on the restore card: this can bring back an erased
fact's original words, if an older backup still has them - the same limit
CLAUDE.md itself states.

Standard library plus `cryptography` (already required by chat history;
without it, backing up and restoring both refuse, in words, rather than
ever writing anything unencrypted).
"""
from __future__ import annotations

import base64
import calendar
import io
import json
import os
import secrets
import sqlite3
import struct
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
except Exception:  # pragma: no cover - cryptography not installed
    AESGCM = None  # type: ignore
    Argon2id = None  # type: ignore
    InvalidTag = Exception  # type: ignore

PATH = "/api/backup"
FOLDER_ROUTE = "/api/backup/folder"
NOW_ROUTE = "/api/backup/now"
LIST_ROUTE = "/api/backup/list"
PREVIEW_ROUTE = "/api/backup/restore/preview"
RESTORE_ROUTE = "/api/backup/restore"

#: Setting the folder - jarvis_documents.py's own action for "let Jarvis see
#: (or write into) one more place".
CARD_ACTION = "change_own_config"

#: Restoring from a backup. jarvis_owner_check.PC_ONLY_ACTIONS holds the
#: same name.
RESTORE_ACTION = "restore_backup"

#: How many backup files are kept in the folder. Chosen, not measured: a
#: card is shown per restore either way, so more costs disk, not safety; a
#: synced folder should not grow without bound. See the module docstring.
KEEP = 5

FILE_SUFFIX = ".jbak"
MAGIC = b"JBAK1"

#: Argon2id, OWASP's 2026 minimum for a low-value key doubled: about
#: 0.5-1.5s on an ordinary PC, cheap once, expensive at scale for an
#: attacker who has already stolen the file.
ARGON_LANES = 4
ARGON_MEMORY_KIB = 64 * 1024      # 64 MiB
ARGON_ITERATIONS = 3
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12
_HEADER_STRUCT = struct.Struct(">B I I")   # lanes, memory_kib, iterations

#: No 0/O, 1/I/L: nothing that can be misread out loud or by eye.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_GROUPS, CODE_GROUP_LEN = 4, 5

#: The real databases this backend has today (verified against the modules
#: that make them, 2026-09-27 - see the module docstring). projects.db
#: (jarvis_projects.py: projects, their benchmarks and every number the
#: owner logged) joined on 2026-09-28, found by the Projects feature audit.
#: goals.db (jarvis_goals.py) joined on 2026-09-29, found by the cohesiveness
#: audit: schedule.db WAS backed up, and it holds each goal's weekly check-in
#: job, so a restore brought back check-ins whose goals were gone - and Stop
#: tracking (the only way to remove one) needs the goal.
SOURCE_DBS = ("memory.db", "chat-history.db", "schedule.db", "feedback.db", "projects.db",
              "goals.db")

MISSING = "backup.py could not be reached - run apply-patches.ps1 on this PC"
NO_CRYPTO = ("Backing up needs the `cryptography` package, which is not installed on this "
             "PC - without it nothing is ever written unencrypted, so backups are off "
             "until it is installed")
NO_FOLDER = "Choose a folder for backups first (Settings, Backups)."
PC_ONLY = "Backups are set up on the PC only (Settings, Backups)."
LOST_CODE = ("Write this down or save it somewhere safe now - Jarvis will not show it "
             "again, and cannot recover it. If it is lost, this backup can never be "
             "opened again; there is no other way in.")
ERASE_LIMIT = ("\"Erase the words\" cannot reach into an older backup: an erased fact's "
               "original words may still be readable in a backup kept from before it was "
               "erased, until that backup ages out of the last {keep} kept. A chat you "
               "delete is the same: it can still be in an older backup until that backup "
               "ages out.").format(keep=KEEP)


class WrongCode(Exception):
    """The recovery code does not open this file (or it is not one of ours)."""


class BackupUnavailable(Exception):
    """Backing up or restoring cannot go ahead; the message is plain words."""


# ---------------------------------------------------------------------------
#   Settings, the gate, the clock - replaceable, so the tests open nothing
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    """backup.json in the Jarvis settings folder: {"folder": str|None}. The
    LAST backup's own outcome is kept in memory only (_B_STATE), never here -
    it can carry a one-time recovery code, which must never touch disk."""
    return _config_dir() / "backup.json"


def _load_settings() -> dict:
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"folder": None}
    except (OSError, ValueError):
        return {"folder": None}
    if not isinstance(raw, dict):
        return {"folder": None}
    folder = raw.get("folder")
    return {"folder": folder if isinstance(folder, str) and folder else None}


def _save_settings(data: dict) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-backup-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes only. Never a folder's path, a file name that
    # could hint at its date, or (obviously) a recovery code.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False  # cannot tell: fail closed, nothing runs


def _owner_check_armed() -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.armed())
    except Exception:
        return False


def check_folder(path) -> str:
    """The folder, as it would be kept, or ValueError with a sentence.

    Reused from jarvis_documents.py - not copied - so backups are refused
    the same places "Folders Jarvis may look in" is (a drive's top, the
    whole user folder, Windows' own folders, anywhere file_read refuses):
    one list of unsafe places, never two that can drift apart.
    """
    import jarvis_documents
    return jarvis_documents.check_folder(path)


# ---------------------------------------------------------------------------
#   The lock: AES-256-GCM, a key stretched from the code by Argon2id
# ---------------------------------------------------------------------------


def generate_code() -> str:
    """A fresh recovery code: 20 characters, 4 groups of 5, from an
    alphabet with no 0/O/1/I/L. Never logged, never written to a file,
    never kept by this module past the response that shows it once."""
    chars = [secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUPS * CODE_GROUP_LEN)]
    groups = ["".join(chars[i:i + CODE_GROUP_LEN])
              for i in range(0, len(chars), CODE_GROUP_LEN)]
    return "-".join(groups)


def _clean_code(code) -> str:
    """As the owner would type it back: upper-cased, hyphens and spaces
    dropped, so "abcd-efghj" and "ABCDEFGHJ" and "abcd efgh j" all match."""
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def _require_crypto() -> None:
    if AESGCM is None or Argon2id is None:
        raise BackupUnavailable(NO_CRYPTO)


def _derive_key(salt: bytes, code: str) -> bytes:
    kdf = Argon2id(salt=salt, length=KEY_LEN, iterations=ARGON_ITERATIONS,
                   lanes=ARGON_LANES, memory_cost=ARGON_MEMORY_KIB)
    return kdf.derive(_clean_code(code).encode("utf-8"))


def encrypt_blob(data: bytes, code: str) -> bytes:
    """The on-disk format - see the module docstring's diagram. `data` is
    the whole zip archive's bytes, held in memory only until this returns."""
    _require_crypto()
    salt = secrets.token_bytes(SALT_LEN)
    nonce = secrets.token_bytes(NONCE_LEN)
    header = MAGIC + _HEADER_STRUCT.pack(ARGON_LANES, ARGON_MEMORY_KIB, ARGON_ITERATIONS)
    header += salt + nonce
    key = _derive_key(salt, code)
    aes = AESGCM(key)
    return header + aes.encrypt(nonce, data, header)


def decrypt_blob(blob: bytes, code: str) -> bytes:
    """The zip bytes back, or WrongCode - never AESGCM's own exception, so a
    caller never has to know cryptography's exception types to handle it."""
    _require_crypto()
    head_len = len(MAGIC) + _HEADER_STRUCT.size + SALT_LEN + NONCE_LEN
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < head_len or \
            bytes(blob[:len(MAGIC)]) != MAGIC:
        raise WrongCode("that is not a Jarvis backup file")
    header = bytes(blob[:head_len])
    lanes, memory_kib, iterations = _HEADER_STRUCT.unpack(
        header[len(MAGIC):len(MAGIC) + _HEADER_STRUCT.size])
    salt = header[len(MAGIC) + _HEADER_STRUCT.size: len(MAGIC) + _HEADER_STRUCT.size + SALT_LEN]
    nonce = header[len(MAGIC) + _HEADER_STRUCT.size + SALT_LEN:head_len]
    ciphertext = bytes(blob[head_len:])
    try:
        kdf = Argon2id(salt=salt, length=KEY_LEN, iterations=iterations,
                       lanes=lanes, memory_cost=memory_kib)
        key = kdf.derive(_clean_code(code).encode("utf-8"))
        aes = AESGCM(key)
        return aes.decrypt(nonce, ciphertext, header)
    except InvalidTag:
        raise WrongCode("that recovery code does not open this backup") from None
    except (ValueError, TypeError) as exc:
        raise WrongCode(f"that backup file is damaged ({type(exc).__name__})") from None


# ---------------------------------------------------------------------------
#   Gathering what gets backed up
# ---------------------------------------------------------------------------


def _table_counts(db_path: Path) -> dict:
    """{table: row count} for every real table in `db_path` - a manifest
    number, never a row's content. {} for a missing or unreadable file."""
    if not db_path.is_file():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.DatabaseError:
        return {}
    try:
        conn.execute("PRAGMA query_only = 1")
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        out = {}
        for name in names:
            try:
                out[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except sqlite3.DatabaseError:
                continue
        return out
    except sqlite3.DatabaseError:
        return {}
    finally:
        conn.close()


def _snapshot_db(src: Path, dest: Path) -> bool:
    """A safe-while-running copy of `src` at `dest`, via SQLite's own online
    backup API. False (never raises) when `src` does not exist or cannot be
    read - that database is simply left out of the archive."""
    if not src.is_file():
        return False
    try:
        source = sqlite3.connect(str(src))
    except sqlite3.DatabaseError:
        return False
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    except sqlite3.DatabaseError:
        return False
    finally:
        source.close()
    return dest.is_file()


def _chat_history_key_b64() -> Optional[str]:
    """The chat-history encryption key, base64, or None if it is not there
    or Credential Manager cannot be reached. Read the SAME way
    jarvis_chat_log.py reads it - not copied."""
    try:
        import jarvis_chat_log
        key = jarvis_chat_log.CredentialKey()()
        return base64.b64encode(key).decode("ascii")
    except Exception:
        return None


def _toml_source() -> Optional[Path]:
    try:
        if fw is not None:
            p = fw.config_path()
            return Path(p) if p else None
    except Exception:
        pass
    return None


def _walk_files(root: Path):
    if not root.is_dir():
        return
    for p in sorted(root.rglob("*")):
        if p.is_file():
            yield p


def build_archive() -> tuple:
    """(zip_bytes, manifest). The manifest is also written INSIDE the zip
    as manifest.json, so a restore preview can read counts and a date
    without touching anything else in the archive."""
    conf = _config_dir()
    manifest = {"created_at": time.time(), "databases": {}, "settings_files": 0,
                "notes_files": 0, "voice_files": 0, "chat_history_key": False,
                "framework_toml": False}
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="jarvis-backup-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in SOURCE_DBS:
                src = conf / name
                dest = tmp_path / name
                if _snapshot_db(src, dest):
                    manifest["databases"][name] = _table_counts(dest)
                    zf.write(dest, arcname=f"db/{name}")
            for jf in sorted(conf.glob("*.json")):
                if jf.name == settings_path().name:
                    continue  # backup.json names only a folder - never useful inside itself
                try:
                    zf.write(jf, arcname=f"settings/{jf.name}")
                    manifest["settings_files"] += 1
                except OSError:
                    continue
            toml_src = _toml_source()
            if toml_src is not None and toml_src.is_file():
                try:
                    zf.write(toml_src, arcname="jarvis-framework.toml")
                    manifest["framework_toml"] = True
                except OSError:
                    pass
            notes_root = conf / "notes"
            for f in _walk_files(notes_root):
                zf.write(f, arcname=f"notes/{f.relative_to(notes_root)}")
                manifest["notes_files"] += 1
            voice_root = conf / "voice"
            for f in _walk_files(voice_root):
                zf.write(f, arcname=f"voice/{f.relative_to(voice_root)}")
                manifest["voice_files"] += 1
            key_b64 = _chat_history_key_b64()
            if key_b64:
                zf.writestr("secrets/chat-history-key.b64", key_b64)
                manifest["chat_history_key"] = True
            zf.writestr("manifest.json", json.dumps(manifest))
    return buf.getvalue(), manifest


# ---------------------------------------------------------------------------
#   Making one backup file, and keeping only the last few
# ---------------------------------------------------------------------------


def _file_name(at: float) -> str:
    return time.strftime("jarvis-backup-%Y%m%d-%H%M%S", time.gmtime(at)) + FILE_SUFFIX


def _stamp_of(name: str) -> Optional[str]:
    """The "jarvis-backup-YYYYmmdd-HHMMSS" part of a name that may carry a
    "-N" disambiguator before the extension (two backups made in the same
    second), or None if `name` is not shaped like one of ours."""
    if not (name.startswith("jarvis-backup-") and name.endswith(FILE_SUFFIX)):
        return None
    body = name[:-len(FILE_SUFFIX)]
    parts = body.split("-")
    # "jarvis-backup-YYYYmmdd-HHMMSS" is 4 parts; a 5th, all-digit part is
    # the disambiguator added below for two backups made in the same second.
    if len(parts) == 5 and parts[-1].isdigit():
        return "-".join(parts[:-1])
    return body


def list_backups(folder) -> list:
    """[{"name", "at", "size"}], newest first. `at` is read from the file's
    own name (UTC), which sorting by name already matches; a file that does
    not parse is skipped, never guessed at from mtime (a copy or a sync
    program can change that)."""
    p = Path(folder)
    if not p.is_dir():
        return []
    out = []
    for f in p.iterdir():
        if not f.is_file():
            continue
        stamp = _stamp_of(f.name)
        if stamp is None:
            continue
        try:
            at = calendar.timegm(time.strptime(stamp, "jarvis-backup-%Y%m%d-%H%M%S"))
        except ValueError:
            continue
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        out.append({"name": f.name, "at": at, "size": size})
    out.sort(key=lambda r: r["name"], reverse=True)
    return out


def _retain(folder) -> None:
    rows = list_backups(folder)
    for row in rows[KEEP:]:
        try:
            (Path(folder) / row["name"]).unlink()
        except OSError:
            pass


def backup_now(folder, *, code: Optional[str] = None) -> dict:
    """Makes one encrypted backup file in `folder`. `code` lets a caller
    (the restore flow's safety backup) supply its own fresh code; a plain
    "Back up now" leaves it None and gets one made here. Returns
    {"name", "at", "counts", "recovery_code"} - the code is in the return
    value ONLY, never written anywhere by this function."""
    real = check_folder(folder)
    made_code = code or generate_code()
    zip_bytes, manifest = build_archive()
    blob = encrypt_blob(zip_bytes, made_code)
    at = time.time()
    base = _file_name(at)
    name, dest, n = base, Path(real) / base, 1
    # Two backups in the same second (e.g. "Back up now" right before a
    # restore's automatic safety backup) must never share a name - that
    # would silently overwrite the first with the second's content.
    while dest.exists():
        n += 1
        name = base[:-len(FILE_SUFFIX)] + f"-{n}" + FILE_SUFFIX
        dest = Path(real) / name
    tmp = Path(real) / f".{name}.{uuid.uuid4().hex[:8]}.tmp"
    tmp.write_bytes(blob)
    os.replace(tmp, dest)
    _retain(real)
    return {"name": name, "at": at, "counts": manifest, "recovery_code": made_code,
            "size": dest.stat().st_size}


# ---------------------------------------------------------------------------
#   Setting the folder - the folder-add card, jarvis_documents.py's own shape
# ---------------------------------------------------------------------------

_F_LOCK = threading.Lock()
_F_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}
_F_SWITCH = threading.Lock()

LAST_WORDS = {
    "set": "Set. Jarvis will back up into that folder.",
    "denied": "You said no, so the folder was not changed.",
    "timed_out": "Nobody answered the card in time, so the folder was not changed.",
    "withdrawn": "You changed your mind before the card was answered, so nothing changed.",
    "refused": "The card could not be answered, so the folder was not changed.",
    "failed": "It was approved, but the setting could not be saved, so the folder was not "
              "changed.",
}


def folder_card(path: str) -> str:
    return "\n".join([
        "Back up into this folder?",
        "",
        f"Folder: {path}",
        "",
        "From now on, \"Back up now\" writes one locked file here - your memory, chat "
        "history, settings and notes, encrypted, with a recovery code shown once that "
        "only you will have. Jarvis keeps the newest "
        f"{KEEP} backups here and deletes older ones.",
        "",
        "If this folder is synced by NordLocker, OneDrive or a similar program, that "
        "program uploads the file, as it does anything else you put there - the file "
        "itself stays locked either way.",
        "",
        f"A lost recovery code means a useless backup: {LOST_CODE}",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _folder_finish(pid: str, outcome: str, why: str = "") -> None:
    with _F_LOCK:
        if _F_STATE["pending"].get("id") == pid:
            _F_STATE["pending"].clear()
        _F_STATE["withdrawn"].discard(pid)
        if _F_STATE["latest"].get("id") not in (None, pid):
            return
        _F_STATE["last"].clear()
        _F_STATE["last"].update(outcome=outcome, why=why, at=time.time(),
                                message=LAST_WORDS.get(outcome, ""))
    _audit("backup.folder.card", {"outcome": outcome})


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _decide_folder(pid: str, path: str, gate: Callable, tier_of: Callable,
                   write: Callable[[str], None]) -> None:
    text = folder_card(path)
    detail = {"text": text, "what": "back up into one more folder",
              "setting": "backup folder", "to": path, "leaves_this_pc": False}
    try:
        v = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _folder_finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _folder_finish(pid, "refused",
                              f"the gate answered at tier {vtier!r}, which is not a person "
                              f"saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _folder_finish(pid, outcome)
        return _folder_finish(pid, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _F_SWITCH:
        with _F_LOCK:
            withdrawn = pid in _F_STATE["withdrawn"]
        if withdrawn:
            return _folder_finish(pid, "withdrawn")
        try:
            write(path)
        except Exception as exc:
            return _folder_finish(pid, "failed", type(exc).__name__)
    _audit("backup.folder.set", {})
    _folder_finish(pid, "set")


def _set_folder_now(path: str) -> None:
    _save_settings({"folder": path})


def request_set_folder(body, *, peer=None, local=None, here: Optional[bool] = None,
                       gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                       spawn: Optional[Callable] = None,
                       write: Optional[Callable[[str], None]] = None) -> tuple:
    """POST /api/backup/folder {"path"}. (code, body). 202 and ONE card."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    write = write or _set_folder_now
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"path": "<a folder on this PC>"}'}
    try:
        real = check_folder(body.get("path"))
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except BackupUnavailable as exc:
        return 503, {"ok": False, "error": str(exc)}
    t = tier_of(CARD_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{CARD_ACTION} is tier {t!r} in jarvis-framework.toml; setting the backup "
            f"folder needs a person to say yes, so it must be 'ask'")}
    with _F_LOCK:
        if _F_STATE["pending"]:
            return 409, {"ok": False, "error": "A card to set the backup folder is already "
                                               "waiting - answer it first."}
        pid = uuid.uuid4().hex
        _F_STATE["pending"].update(id=pid, path=real, since=time.time())
        _F_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide_folder(pid, real, gate, tier_of, write))
    except Exception:
        with _F_LOCK:
            _F_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "message": "Waiting for your approval. Nothing "
                                                          "changes unless you approve the "
                                                          "card."}


# ---------------------------------------------------------------------------
#   "Back up now" - no card
# ---------------------------------------------------------------------------

_B_LOCK = threading.Lock()
_B_STATE: dict = {"last": {}}   # {"name","at","counts","ok","error"} - never the code


def _record_backup_outcome(ok: bool, *, name: str = "", at: float = 0.0, counts=None,
                           error: str = "") -> None:
    with _B_LOCK:
        _B_STATE["last"] = {"ok": ok, "name": name, "at": at or time.time(),
                            "counts": counts or {}, "error": error}


def request_backup_now(body=None, *, peer=None, local=None, here: Optional[bool] = None,
                       run: Optional[Callable[[str], dict]] = None) -> tuple:
    """POST /api/backup/now {}. PC only, no card - the folder was already
    approved. Runs synchronously: a backup is small enough (settings,
    notes, a few SQLite files) that there is nothing to poll for."""
    run = run or backup_now
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    st = _load_settings()
    if not st["folder"]:
        return 409, {"ok": False, "error": NO_FOLDER}
    try:
        out = run(st["folder"])
    except (BackupUnavailable, ValueError) as exc:
        _record_backup_outcome(False, error=str(exc))
        return 503, {"ok": False, "error": str(exc)}
    except OSError as exc:
        _record_backup_outcome(False, error=f"could not write the backup ({type(exc).__name__})")
        return 500, {"ok": False, "error": f"could not write the backup file "
                                           f"({type(exc).__name__})"}
    _record_backup_outcome(True, name=out["name"], at=out["at"], counts=out["counts"])
    _audit("backup.made", {"ok": True})
    return 200, {"ok": True, "name": out["name"], "at": out["at"], "counts": out["counts"],
                "recovery_code": out["recovery_code"],
                "message": f"Backed up. {LOST_CODE}"}


def request_list(*, peer=None, local=None, here: Optional[bool] = None) -> tuple:
    """GET /api/backup/list. PC only."""
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    st = _load_settings()
    if not st["folder"]:
        return 200, {"ok": True, "backups": []}
    return 200, {"ok": True, "backups": list_backups(st["folder"])}


# ---------------------------------------------------------------------------
#   Restore preview - counts and a date only, never content
# ---------------------------------------------------------------------------


def _read_manifest(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        try:
            return json.loads(zf.read("manifest.json"))
        except (KeyError, ValueError):
            return {}


def preview_restore(body, *, peer=None, local=None, here: Optional[bool] = None) -> tuple:
    """POST /api/backup/restore/preview {"name","code"}. PC only. Decrypts
    to read manifest.json ONLY - counts and the backup's own date - never
    any other file inside. Nothing is changed."""
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if not isinstance(body, dict) or not isinstance(body.get("name"), str) or \
            not isinstance(body.get("code"), str):
        return 400, {"ok": False, "error": 'need {"name": "<backup file>", "code": '
                                           '"<recovery code>"}'}
    st = _load_settings()
    if not st["folder"]:
        return 409, {"ok": False, "error": NO_FOLDER}
    path = Path(st["folder"]) / body["name"]
    if ".." in body["name"] or "/" in body["name"] or "\\" in body["name"] or not path.is_file():
        return 404, {"ok": False, "error": "That backup file could not be found."}
    try:
        blob = path.read_bytes()
        zip_bytes = decrypt_blob(blob, body["code"])
        manifest = _read_manifest(zip_bytes)
    except WrongCode as exc:
        return 400, {"ok": False, "error": str(exc), "wrong_code": True}
    except (OSError, zipfile.BadZipFile, BackupUnavailable) as exc:
        return 500, {"ok": False, "error": f"that backup could not be read ({type(exc).__name__})"}
    return 200, {"ok": True, "name": body["name"], "created_at": manifest.get("created_at"),
                "counts": manifest, "erase_limit": ERASE_LIMIT}


# ---------------------------------------------------------------------------
#   Restore - one card, always Windows Hello, always this PC
# ---------------------------------------------------------------------------

_R_LOCK = threading.Lock()
_R_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}
_R_SWITCH = threading.Lock()

RESTORE_LAST_WORDS = {
    # The tray has no "Restart" row, and closing a window only hides it
    # (setup/recovery audit, 2026-09-27): these are the real steps. The
    # safety backup's code is shown once, in this same panel, and lives only
    # in this process's memory - so it comes before the restart.
    "restored": "Restored. First write down the safety backup's recovery code (\"Your data "
               "just before the restore\", in Settings, Backups). Then restart Jarvis so every part of it uses the restored data - "
               "some of it was already open while the files underneath it changed: tray "
               "icon, Stop the backend, then Start the backend (or, if you started Jarvis "
               "yourself in PowerShell, close that window and start it again).",
    "denied": "You said no, so nothing was restored.",
    "timed_out": "Nobody answered the card in time, so nothing was restored.",
    "withdrawn": "You changed your mind before the card was answered, so nothing was "
                "restored.",
    "refused": "The card could not be answered, so nothing was restored.",
    "failed": "It was approved, but the restore itself failed, so your data was not "
              "changed - the safety backup made just before it is still there.",
}


def restore_card(name: str, manifest: dict) -> str:
    when = manifest.get("created_at")
    when_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(when)) if when else "an unknown time"
    return "\n".join([
        "Restore Jarvis from this backup?",
        "",
        f"Backup: {name}",
        f"Made: {when_text}",
        "",
        "This REPLACES your memory, chat history, settings and notes with what was saved "
        "then. It only adds and overwrites - it never deletes anything you have added "
        "since.",
        "",
        "Before doing this, Jarvis will back up your CURRENT data first, with a fresh "
        "recovery code shown once, so this restore itself can be undone.",
        "",
        ERASE_LIMIT,
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes.",
    ])


def _restore_finish(pid: str, outcome: str, *, why: str = "", safety=None) -> None:
    with _R_LOCK:
        if _R_STATE["pending"].get("id") == pid:
            _R_STATE["pending"].clear()
        _R_STATE["withdrawn"].discard(pid)
        if _R_STATE["latest"].get("id") not in (None, pid):
            return
        _R_STATE["last"].clear()
        _R_STATE["last"].update(outcome=outcome, why=why, at=time.time(),
                                message=RESTORE_LAST_WORDS.get(outcome, ""),
                                safety_backup=safety)
    _audit("backup.restore.card", {"outcome": outcome})


def take_restore_result() -> Optional[dict]:
    """The last restore's outcome, INCLUDING the safety backup's one-time
    recovery code if there is one - read ONCE. A second call never sees the
    code again, so it can never be re-read off a stale poll, logged by a
    later request, or left sitting in memory for longer than one answer
    needs it."""
    with _R_LOCK:
        last = dict(_R_STATE["last"])
        if last:
            safety = last.get("safety_backup")
            if isinstance(safety, dict) and "recovery_code" in safety:
                _R_STATE["last"]["safety_backup"] = {k: v for k, v in safety.items()
                                                     if k != "recovery_code"}
    return last or None


def _inside(root: Path, rel: str, *, flat: bool = False) -> Optional[Path]:
    """`root` joined with the archive path `rel`, or None when `rel` could
    land anywhere but inside `root`: a "..", an empty or "." part, a
    leading "/", a backslash, or a drive letter (on Windows, `root /
    "C:/x"` IS "C:/x"). `flat`: one name only, no folder (db/ and
    settings/ hold top-level files only - build_archive never writes
    deeper). Security/privacy audit, 2026-09-27: restore used to join
    whatever name the archive held, so "db/../../x" wrote outside the
    settings folder. build_archive never writes such a name, and a file
    needs its recovery code to open, so this is a second lock, not a
    reported attack."""
    if not rel or "\\" in rel or rel.startswith("/") or ":" in rel:
        return None
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts) or (flat and len(parts) != 1):
        return None
    return root.joinpath(*parts)


def _apply_restore(zip_bytes: bytes) -> dict:
    """Writes the archive's files back. Additive/overwrite only - nothing
    present now but absent from the backup is deleted. Returns a short
    summary for the audit log (counts only). A name that would land
    outside its own folder is skipped and counted (`_inside`)."""
    conf = _config_dir()
    conf.mkdir(parents=True, exist_ok=True)
    applied = {"databases": 0, "settings_files": 0, "notes_files": 0, "voice_files": 0,
              "framework_toml": False, "chat_history_key": False, "skipped": 0}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/") or name == "manifest.json":
                continue
            where = None
            if name.startswith("db/"):
                where = ("databases", _inside(conf, name[len("db/"):], flat=True))
            elif name.startswith("settings/"):
                where = ("settings_files", _inside(conf, name[len("settings/"):], flat=True))
            elif name.startswith("notes/"):
                where = ("notes_files", _inside(conf / "notes", name[len("notes/"):]))
            elif name.startswith("voice/"):
                where = ("voice_files", _inside(conf / "voice", name[len("voice/"):]))
            if where is not None and where[1] is None:
                applied["skipped"] += 1
                continue
            data = zf.read(info)
            if where is not None:
                dest = where[1]
                applied[where[0]] += 1
            elif name == "jarvis-framework.toml":
                toml_dest = _toml_source()
                dest = toml_dest if toml_dest is not None else (conf / name)
                applied["framework_toml"] = True
            elif name == "secrets/chat-history-key.b64":
                try:
                    import jarvis_token_store as ts
                    import jarvis_chat_log
                    ts.WindowsStore(target=jarvis_chat_log.KEY_TARGET).write(
                        data.decode("ascii"))
                    applied["chat_history_key"] = True
                except Exception:
                    pass
                continue
            else:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.parent / f".{dest.name}.{uuid.uuid4().hex[:8]}.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, dest)
    return applied


def _decide_restore(pid: str, name: str, code: str, manifest: dict, zip_bytes: bytes,
                    gate: Callable, tier_of: Callable, apply_fn: Callable,
                    safety_fn: Callable) -> None:
    text = restore_card(name, manifest)
    detail = {"text": text, "what": "replace memory, chat history, settings and notes with "
                                    f"the backup {name}", "setting": "restore from backup",
              "to": name, "leaves_this_pc": False}
    try:
        v = gate(RESTORE_ACTION, detail, text)
    except Exception as exc:
        return _restore_finish(pid, "refused", why=f"the approval gate failed "
                                                   f"({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(RESTORE_ACTION) != "ask":
        return _restore_finish(pid, "refused",
                               why=f"the gate answered at tier {vtier!r}, which is not a "
                                   f"person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _restore_finish(pid, outcome)
        return _restore_finish(pid, "refused", why=str(getattr(v, "reason", "refused"))[:200])
    with _R_SWITCH:
        with _R_LOCK:
            withdrawn = pid in _R_STATE["withdrawn"]
        if withdrawn:
            return _restore_finish(pid, "withdrawn")
        try:
            safety = safety_fn()
        except Exception as exc:
            return _restore_finish(pid, "failed", why=f"the safety backup failed "
                                                       f"({type(exc).__name__})")
        try:
            applied = apply_fn(zip_bytes)
        except Exception as exc:
            return _restore_finish(pid, "failed", why=type(exc).__name__,
                                   safety={"name": safety["name"], "at": safety["at"],
                                           "recovery_code": safety["recovery_code"]})
    _audit("backup.restored", {"applied": applied})
    _restore_finish(pid, "restored",
                    safety={"name": safety["name"], "at": safety["at"],
                            "recovery_code": safety["recovery_code"]})


def request_restore(body, *, peer=None, local=None, here: Optional[bool] = None,
                    gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
                    spawn: Optional[Callable] = None, apply_fn: Optional[Callable] = None,
                    safety_fn: Optional[Callable] = None,
                    armed: Optional[Callable[[], bool]] = None) -> tuple:
    """POST /api/backup/restore {"name","code"}. (code, body). 202 and ONE
    card that always needs Windows Hello and always comes from this PC -
    jarvis_owner_check.PC_ONLY_ACTIONS refuses its approval from anywhere
    else, whatever the gate's own risk table says about `restore_backup`."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    apply_fn = apply_fn or _apply_restore
    armed = armed or _owner_check_armed
    is_here = bool(here) if here is not None else _from_this_pc(peer, local)
    if not is_here:
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if not isinstance(body, dict) or not isinstance(body.get("name"), str) or \
            not isinstance(body.get("code"), str):
        return 400, {"ok": False, "error": 'need {"name": "<backup file>", "code": '
                                           '"<recovery code>"}'}
    st = _load_settings()
    if not st["folder"]:
        return 409, {"ok": False, "error": NO_FOLDER}
    if not armed():
        return 503, {"ok": False, "error": "Jarvis cannot check it is you on this PC yet "
                                           "(Windows Hello), so a restore is refused until "
                                           "it can - restart Jarvis after setting up Windows "
                                           "Hello."}
    path = Path(st["folder"]) / body["name"]
    if ".." in body["name"] or "/" in body["name"] or "\\" in body["name"] or not path.is_file():
        return 404, {"ok": False, "error": "That backup file could not be found."}
    try:
        blob = path.read_bytes()
        zip_bytes = decrypt_blob(blob, body["code"])
        manifest = _read_manifest(zip_bytes)
    except WrongCode as exc:
        return 400, {"ok": False, "error": str(exc), "wrong_code": True}
    except (OSError, zipfile.BadZipFile, BackupUnavailable) as exc:
        return 500, {"ok": False, "error": f"that backup could not be read ({type(exc).__name__})"}
    t = tier_of(RESTORE_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{RESTORE_ACTION} is tier {t!r} in jarvis-framework.toml; restoring needs a "
            f"person to say yes, so it must be 'ask'")}
    safety_fn = safety_fn or (lambda: backup_now(st["folder"]))
    with _R_LOCK:
        if _R_STATE["pending"]:
            return 409, {"ok": False, "error": "A restore card is already waiting - answer "
                                               "it first."}
        pid = uuid.uuid4().hex
        _R_STATE["pending"].update(id=pid, name=body["name"], since=time.time())
        _R_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide_restore(pid, body["name"], body["code"], manifest, zip_bytes,
                                      gate, tier_of, apply_fn, safety_fn))
    except Exception:
        with _R_LOCK:
            _R_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "message": "Waiting for your approval, with "
                                                          "Windows Hello. Nothing changes "
                                                          "unless you approve."}


# ---------------------------------------------------------------------------
#   GET /api/backup
# ---------------------------------------------------------------------------


def view(*, here: bool = False) -> dict:
    """GET /api/backup. From this PC: the folder, whether a card is
    waiting, how the last folder-card and the last backup/restore went, and
    the retention count. From anywhere else (the phone): only whether a
    backup has ever been made and when the last one was - "last backup: 3
    days ago" and nothing more (the design's own words; the full flow is
    desktop-only, docs/ARCHITECTURE.md section 8)."""
    with _B_LOCK:
        last_backup = dict(_B_STATE["last"]) if _B_STATE["last"] else None
    if not here:
        return {"available": True,
                "last_backup_at": last_backup["at"] if last_backup else None}
    st = _load_settings()
    with _F_LOCK:
        pending = dict(_F_STATE["pending"]) if _F_STATE["pending"] else None
        last_folder_card = dict(_F_STATE["last"]) if _F_STATE["last"] else None
    with _R_LOCK:
        restore_pending = dict(_R_STATE["pending"]) if _R_STATE["pending"] else None
    # take_restore_result() takes _R_LOCK itself - called after releasing it
    # above, never from inside it (that would deadlock: _R_LOCK is a plain
    # Lock, not reentrant).
    last_restore = take_restore_result()
    return {"available": True, "folder": st["folder"], "keep": KEEP,
           "last_backup": last_backup, "pending_folder_card": pending,
           "last_folder_card": last_folder_card, "pending_restore_card": restore_pending,
           "last_restore": last_restore, "erase_limit": ERASE_LIMIT}


# ---------------------------------------------------------------------------
#   Wiring into jarvis_hud.py's server (backup.patch)
# ---------------------------------------------------------------------------

_ARMED = False


def armed() -> bool:
    return _ARMED


def _peer_local(handler) -> tuple:
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def handle_get(route: str, *, peer=None, local=None) -> tuple:
    here = _from_this_pc(peer, local)
    if route == PATH:
        return 200, view(here=here)
    if route == LIST_ROUTE:
        return request_list(peer=peer, local=local, here=here)
    return 404, {"ok": False, "error": "not found"}


def handle_post(route: str, body, *, peer=None, local=None) -> tuple:
    here = _from_this_pc(peer, local)
    if route == FOLDER_ROUTE:
        return request_set_folder(body, peer=peer, local=local, here=here)
    if route == NOW_ROUTE:
        return request_backup_now(body, peer=peer, local=local, here=here)
    if route == PREVIEW_ROUTE:
        return preview_restore(body, peer=peer, local=local, here=here)
    if route == RESTORE_ROUTE:
        return request_restore(body, peer=peer, local=local, here=here)
    return 404, {"ok": False, "error": "not found"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so the six routes above are
    answered here, after the server's own origin and token checks; every
    other request goes straight to the original - the same shape as
    jarvis_documents.py's `install`."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_backup", False):
        _ARMED = True
        return "  backups    /api/backup, folder, now, list, restore (already on)"

    from urllib.parse import urlsplit

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/") or "/"
        if route not in (PATH, LIST_ROUTE):
            return get0(self)
        if not _allowed(self):
            return None
        peer, local = _peer_local(self)
        try:
            code, out = handle_get(route, peer=peer, local=local)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in (FOLDER_ROUTE, NOW_ROUTE, PREVIEW_ROUTE, RESTORE_ROUTE):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            return self._send(400, {"ok": False, "error": "bad JSON"})
        peer, local = _peer_local(self)
        try:
            code, out = handle_post(route, body, peer=peer, local=local)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_backup = True
    do_POST._jarvis_backup = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  backups    /api/backup, folder, now, list, restore"


def _reset_for_tests() -> None:
    global _ARMED
    _ARMED = False
    with _F_LOCK:
        _F_STATE.update(pending={}, withdrawn=set(), last={}, latest={})
    with _R_LOCK:
        _R_STATE.update(pending={}, withdrawn=set(), last={}, latest={})
    with _B_LOCK:
        _B_STATE["last"] = {}


if __name__ == "__main__":
    print(f"  config dir  {_config_dir()}")
    print(f"  settings    {_load_settings()}")
    print(f"  crypto      {'ready' if AESGCM is not None and Argon2id is not None else NO_CRYPTO}")
