"""jarvis_notion_obsidian.py - bring a Notion export into an Obsidian vault.

THE OWNER'S REQUEST. Notion can export a whole workspace as Markdown & CSV or
as HTML. What it writes is not a vault: every page and folder carries a
trailing 32-character id, properties sit as loose `Key: value` lines under the
title, each database is a CSV beside its pages, links between pages point at
file names that no longer exist once the ids are stripped, and pictures and PDFs
sit wherever Notion put them. This module turns that export into a vault that
Obsidian can open, WITHOUT losing anything it cannot put back.

WHAT IT DOES, IN ORDER
  1. INGEST a `.zip`, a folder already unzipped, or either containing Notion's
     `Export-...-Part-2.zip` parts. A zip is judged by its OWN directory before
     a byte is written - the unpacked total it declares, its compression ratio,
     how many members it holds and how big the largest one is, so a zip bomb is
     refused rather than filled to - and the absolute caps are counted as bytes
     are written because a header can lie. Nothing is
     unpacked outside the staging folder, and `..` and absolute names are
     refused (the same guard `jarvis_documents.import_notion` uses - see WHY IT
     IS NOT A SECOND EXTRACTOR below).
  2. CLEAN the tree: strip Notion's 32-hex (and hyphenated 36-char) ids from
     file and folder names, replace what Windows and Obsidian forbid, and
     resolve collisions DETERMINISTICALLY - two pages called `Meeting Notes`
     under different ids become `Meeting Notes.md` and `Meeting Notes 2.md`,
     always the same way for the same export, and a generated hub note or
     `.base` that would share a name follows the same rule rather than
     replacing the page. The
     `old_relative_path_with_id -> new_vault_relative_path` map is kept because
     step 5 needs it.
  3. PROPERTIES into YAML frontmatter, including `notion_id`, so importing the
     same export twice is idempotent. Each exported CSV database has its row's
     columns merged into the matching note's frontmatter (a relation value that
     names a page of the export becomes `[[that page]]`; Notion's id is taken
     off only when the id-free value names a page, so every other value is left
     byte-for-byte), and gets a generated
     `_Database - <Name>.md` hub note - type, row count and columns in its
     frontmatter, a row table linking every child note, and a count of rows
     whose page is missing - plus a `.base` file. `X.csv` and `X_all.csv` are
     ONE database and their rows are merged.
  4. HTML into Obsidian Markdown when the export is HTML: callouts, toggles,
     `- [ ]` checklists, fenced code with its language, pipe tables.
  5. LINKS and ATTACHMENTS: `%20` is decoded, Notion's relative links become
     `[[Target Page|Display Text]]` through the map from step 2, and pictures,
     PDFs, audio and video move into the vault's attachments folder and are
     rewritten to `![[name.png]]`.
  6. PLAN -> DESCRIBE -> GATE -> RUN, like every other action here: the plan is
     a dry run with counts and a digest, `run_import(plan)` needs a person's
     yes, lands the whole tree in ONE step, and records a reversible entry in
     `jarvis_receipts` so Undo takes the import back off.

WHAT IT NEVER DOES
  * It never sends anything anywhere: standard library only, no socket, no
    child process, no network.
  * It never writes outside the vault it was pointed at, except in its own
    hidden staging folder, which is removed when the run ends - and NOTHING at
    all outside that vault once the run is over.
  * It never writes into `~/.openjarvis`, the owner's live backend folder, or
    any protected place (jarvis_documents.protected is the ONE refusal list).
  * It never overwrites a file that is already in the vault: a name already
    taken gets a number, and the plan says so before a person is asked.
  * It never reads facts, memory or chat: it is a files-in, files-out module.
  * It answers no request from another device: both routes are this PC only,
    the same rule the folder import keeps, because the export file and the
    vault are folders on this PC (2026-10-21 audit, R4).

WHY IT IS NOT A SECOND EXTRACTOR. `jarvis_documents.py` already ships
`import_notion()`, and it already refuses zip-slip, caps the size, unpacks one
level of `Part-N.zip` and moves the result into place in one step - with its
own route and its own suite. Writing that again would be the duplicate
feature this project's audits look for. What that importer does NOT do is turn
an export into a VAULT (ids, properties, links, attachments, databases), so
this module imports its guards rather than copying them:
`jarvis_documents.safe_parts` (the name check that stops `..` and absolute
paths), `jarvis_documents.protected` (the one refusal list) and
`jarvis_documents.ImportRefused` (the plain-words refusal). If that module is
not beside this one the import REFUSES rather than extracting with a guard of
its own.

Standard library only. Nothing here opens a socket.
"""
from __future__ import annotations

import html as _html
import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_documents as docs          # the guards, never a second copy
except Exception:                            # pragma: no cover - shipped beside it
    docs = None  # type: ignore

try:
    import jarvis_receipts as receipts       # one-click Undo, where it is here
except Exception:                            # pragma: no cover
    receipts = None  # type: ignore

try:
    import jarvis_framework as fw
except Exception:                            # pragma: no cover
    fw = None  # type: ignore


# --------------------------------------------------------------------------
#   What it is called, and the limits it works inside
# --------------------------------------------------------------------------

TOOL = "import_notion_export"
TITLE = "Bring a Notion export into your vault"
DETAIL = ("Notion's own export, tidied into an Obsidian vault: ids off the file names, "
          "properties as frontmatter, databases as a note and a .base, links pointing at "
          "the right pages, and pictures and documents in one attachments folder.")
CARD_ACTION = "change_own_config"            # the shape of every setting that adds files
GATE_ACTION = "import_notion_export"         # the action the gate is asked about
RECEIPT_TOOL = "import_notion_export"

PATHS = ("/api/notion/preview", "/api/notion/import")

#: The vault's attachments folder, under the vault root.
ATTACHMENTS = "attachments"
#: What is copied into it rather than left where Notion put it.
ATTACHMENT_KINDS = frozenset(
    (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".avif",
     ".pdf", ".mp3", ".m4a", ".wav", ".ogg", ".flac",
     ".mp4", ".mov", ".webm", ".mkv"))
#: The kinds a page can be written as.
NOTE_KINDS = frozenset((".md", ".markdown"))
#: The most of any one export. Counted as it is written, never as the zip
#: claims: a zip bomb lies in its own header.
MAX_FILES = 20_000
MAX_BYTES = 1024 * 1024 * 1024
MAX_ONE = 200 * 1024 * 1024
MAX_ZIP = 2 * 1024 * 1024 * 1024
#: The two numbers a zip's OWN directory is judged by, before a byte is
#: written (2026-10-20 review, rule 1): the total it declares it unpacks to,
#: and how much it claims to shrink its contents. A real Notion export is
#: pages and CSVs - text, around 2-10:1 - so 100:1 is not a working archive.
#: The absolute caps above stay as the backstop: a header can lie, and the
#: bytes actually written are what fill a disk.
#:
#: THIS module's declared-total number is 500 MB, and that is on purpose:
#: `jarvis_documents.EXPORT_UNCOMPRESSED_MAX` is 250 MB for the folder import
#: that unpacks a Notion export only to READ it, while this one WRITES a new
#: vault and copies its attachments too. The total check itself is
#: `jarvis_documents.zip_bomb_problem` (imported, not copied); the ratio is
#: the extra rule a zip bomb needs. The member COUNT and the largest single
#: member are checked from `infolist()` in `_zip_problem` as well, before any
#: member is opened (2026-10-21 audit, R2/R3).
MAX_ZIP_UNCOMPRESSED = 500 * 1024 * 1024
MAX_ZIP_RATIO = 100
MAX_NAME = 120                                # characters in one path part
#: The longest a Notion property value may be before it is cut. A runaway value
#: must not become a runaway frontmatter block.
MAX_VALUE = 400
#: How much of any one file is read as text.
MAX_TEXT = 4 * 1024 * 1024

#: Notion's trailing id: 32 hex, or the hyphenated 36-character form.
_ID = re.compile(r"[\s_-]*([0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                 r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$")
#: What Windows refuses, plus what Obsidian refuses in a file name: `#` starts a
#: heading, `^` a block id, `[` `]` and `|` are wikilink syntax, so a name
#: holding one makes a link to that page impossible to write.
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\[\]#^]')
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9]|conin\$|conout\$|clock\$)$",
                       re.IGNORECASE)
#: A property line under the title: Notion writes `Key: value`.
_PROPERTY = re.compile(r"^([A-Za-z][A-Za-z0-9 _\-/()'.]{0,48}):\s*(.*)$")


class ImportRefused(Exception):
    """Something about this export cannot be done, said in plain words."""


def _refused(why: str) -> "ImportRefused":
    return docs.ImportRefused(why) if docs is not None else ImportRefused(why)


#: What a refusal can actually BE. `_refused()` raises `jarvis_documents`' own
#: class when that module is beside this one, and this module's class when it
#: is not - so every `except`/`isinstance` asks about BOTH, or the run path
#: would catch neither and report "ImportRefused" instead of the sentence.
_REFUSALS = (ImportRefused,) + ((docs.ImportRefused,) if docs is not None else ())


# --------------------------------------------------------------------------
#   Settings folder, the gate, the clock - replaceable, so tests open nothing
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """Jarvis's settings folder.

    The SAME two variables every other module here reads - `OPENJARVIS_CONFIG_DIR`,
    then `JARVIS_CONFIG_DIR` - and not a third name of this module's own.

    THE VARIABLE IS CHECKED FIRST, BEFORE `jarvis_framework.CONFIG_DIR`, and
    that order is the whole point: `fw.CONFIG_DIR` is a module-level constant
    computed ONCE when jarvis_framework is imported, so a process that sets the
    variable afterwards (a suite, a test, a probe) cannot move it. Asking the
    environment first is what makes this module redirectable - which is how its
    own suite, and anything else that runs it, stays out of the owner's real
    `~/.openjarvis`. With nothing set the answer is `fw.CONFIG_DIR` and then
    `~/.openjarvis`, exactly as everywhere else.
    """
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    return Path(os.path.expanduser("~")) / ".openjarvis"


def state_path() -> Path:
    """Where this module keeps its own small record: the last import, by name."""
    return _config_dir() / "notion-obsidian.json"


def _protected(path) -> bool:
    if docs is not None:
        try:
            return bool(docs.protected(str(path)))
        except Exception:
            return True
    return True                                   # fail closed


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes. Never a page's name.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   2. Names: ids off, nothing forbidden, collisions decided the same way twice
# --------------------------------------------------------------------------

def split_id(name: str) -> tuple:
    """`("Meeting Notes", "1a2b...")` for a Notion name, `(name, "")` otherwise.

    The extension is kept out of the search: Notion writes the id on the STEM
    (`Meeting Notes 1a2b....md`), never after the dot. A DATABASE's CSV is the
    one shape where the id is not last - Notion writes
    `<Database Name> <id>_all.csv` - so the `_all` suffix is stepped over and
    put back, and the database's own name comes off with its id like any page.
    """
    stem, ext = os.path.splitext(name)
    tail = ""
    m_all = re.match(r"^(.*?)(_all)$", stem)
    if m_all:
        stem, tail = m_all.group(1), "_all"
    m = _ID.search(stem)
    if not m:
        return name, ""
    base = stem[:m.start()].rstrip(" -_") or stem[:m.start()]
    return base + tail + ext, m.group(1)


def clean_name(name: str, *, keep_kind: bool = True) -> str:
    """One path part, safe for Windows and for Obsidian, without Notion's id."""
    clean, _id = split_id(os.path.basename(name))
    stem, ext = os.path.splitext(clean)
    stem = _CONTROL.sub("", stem)
    stem = _FORBIDDEN.sub("-", stem)
    stem = re.sub(r"\s+", " ", stem).strip().rstrip(". ")
    if _RESERVED.match(stem):
        stem = stem + "-"
    if not stem:
        stem = "Untitled"
    if len(stem) > MAX_NAME:
        stem = stem[:MAX_NAME].rstrip(". ")
    if keep_kind and ext:
        ext = _CONTROL.sub("", ext)
        ext = _FORBIDDEN.sub("", ext)
        return stem + ext.lower()
    return stem


def _unique(want: str, taken: set) -> str:
    """`want`, or `want 2`, `want 3` ... - decided by the ORDER it was asked, so
    the same export always lands on the same names."""
    stem, ext = os.path.splitext(want)
    key = want.casefold()
    if key not in taken:
        taken.add(key)
        return want
    i = 2
    while True:
        candidate = f"{stem} {i}{ext}"
        if candidate.casefold() not in taken:
            taken.add(candidate.casefold())
            return candidate
        i += 1


# --------------------------------------------------------------------------
#   1. Ingest: a zip, a folder, and Notion's own Part-N.zip inside either
# --------------------------------------------------------------------------

def _zip_problem(zf: zipfile.ZipFile) -> str:
    """Why this archive is refused BEFORE a byte is written, or "".

    A zip bomb is refused from its own central directory rather than after
    writing the bytes it claims. Four numbers are judged here, all from
    `infolist()`: the declared unpacked TOTAL, the compression ratio, how many
    members the archive holds (the same `MAX_FILES` the folder path caps) and
    the largest single member (`MAX_ONE`). The caps in `_copy_capped` stay as
    the backstop for an archive whose header lies.
    """
    members = 0
    unpacked = packed = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        members += 1
        if members > MAX_FILES:
            return (f"the zip holds more than {MAX_FILES:,} files, which is more than "
                    f"one export can be - nothing was unpacked")
        size = int(info.file_size or 0)
        if size > MAX_ONE:
            return (f"one file inside says it is bigger than "
                    f"{MAX_ONE // (1024 * 1024)} MB once unpacked, so nothing was "
                    f"unpacked")
        unpacked += size
        packed += int(info.compress_size or 0)
    # The declared TOTAL is `jarvis_documents`' own check - the same function its
    # Notion import uses - so this module keeps importing that guard rather than
    # copying it. The numbers differ on purpose and both are stated here: that
    # import unpacks a folder to READ it (`jarvis_documents.EXPORT_UNCOMPRESSED_MAX`,
    # 250 MB); this one WRITES a new vault including the attachments
    # (`MAX_ZIP_UNCOMPRESSED`, 500 MB).
    if docs is not None:
        why = docs.zip_bomb_problem(zf, MAX_ZIP_UNCOMPRESSED)
        if why:
            return f"{why}, so nothing was unpacked"
    elif unpacked > MAX_ZIP_UNCOMPRESSED:
        return (f"the zip says it holds more than "
                f"{MAX_ZIP_UNCOMPRESSED // (1024 * 1024)} MB once unpacked, so "
                f"nothing was unpacked")
    if unpacked > 0 and packed == 0:
        return ("the zip says it holds data but no compressed bytes at all, so "
                "nothing was unpacked")
    if packed > 0 and unpacked / packed > MAX_ZIP_RATIO:
        return (f"the zip claims {unpacked:,} bytes from {packed:,} - more than "
                f"{MAX_ZIP_RATIO}:1 compressed, which is what a zip bomb looks like - "
                f"so nothing was unpacked")
    return ""


def _read_zip(zip_path: str, dest: str, counts: dict, depth: int = 0) -> None:
    """Unpack one zip into `dest`. Refuses traversal, links and the caps.

    The name check is `jarvis_documents.safe_parts` - the same function the
    Notion import in that module uses - so a `..`, an absolute path, a drive
    letter or a link is refused by the guard that already exists rather than by
    a second one written here.
    """
    if docs is None:
        raise _refused("jarvis_documents.py is not beside this module, so the safety "
                       "checks that refuse a zip's `..` names are missing - nothing "
                       "was unpacked")
    with zipfile.ZipFile(zip_path) as zf:
        why = _zip_problem(zf)
        if why:
            raise _refused(why)
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = docs.safe_parts(info.filename)
            if parts is None:
                counts["skipped"] += 1
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                counts["skipped"] += 1                 # a symlink, never followed
                continue
            ext = os.path.splitext(parts[-1])[1].lower()
            if ext == ".zip" and depth == 0:
                inner = os.path.join(dest, f".part-{uuid.uuid4().hex[:8]}.zip")
                try:
                    with zf.open(info) as src, open(inner, "wb") as out:
                        _copy_capped(src, out, counts, MAX_ZIP)
                    counts["bytes"] -= os.path.getsize(inner)
                    try:
                        _read_zip(inner, dest, counts, depth + 1)
                    except zipfile.BadZipFile:
                        counts["skipped"] += 1
                finally:
                    _remove(inner)
                continue
            counts["skipped"] += 0 if ext else 1
            target = os.path.join(dest, *parts)
            real = os.path.realpath(target)
            if not _inside(os.path.realpath(dest), real):
                counts["skipped"] += 1
                continue
            if os.path.exists(real):
                counts["skipped"] += 1
                continue
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with zf.open(info) as src, open(real, "wb") as out:
                _copy_capped(src, out, counts, MAX_ONE)
            counts["files"] += 1
            # The per-archive check above cannot see the other Part-N zips, so
            # the same cap is counted again here, as the bytes are written.
            if counts["files"] > MAX_FILES:
                raise _refused(f"the export has more than {MAX_FILES:,} files")


def _copy_capped(src, out, counts: dict, one_max: int) -> None:
    total = 0
    while True:
        chunk = src.read(1024 * 256)
        if not chunk:
            break
        total += len(chunk)
        counts["bytes"] += len(chunk)
        if total > one_max:
            raise _refused(f"one file inside is bigger than {one_max // (1024 * 1024)} MB")
        if counts["bytes"] > MAX_BYTES:
            raise _refused(f"the export is bigger than {MAX_BYTES // (1024 ** 3)} GB")
        out.write(chunk)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _inside(root: str, path: str) -> bool:
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:                            # different drives on Windows
        return False


def _copy_tree(src: str, dest: str, counts: dict) -> None:
    """A folder that was already unzipped. Nothing is followed out of it."""
    if docs is None:
        raise _refused("jarvis_documents.py is not beside this module - nothing was read")
    real_src = os.path.realpath(src)
    for dirpath, dirnames, filenames in os.walk(real_src, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames
                             if not _is_link(os.path.join(dirpath, d)))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if _is_link(full):
                counts["skipped"] += 1
                continue
            parts = docs.safe_parts(os.path.relpath(full, real_src).replace(os.sep, "/"))
            if parts is None:
                counts["skipped"] += 1
                continue
            target = os.path.realpath(os.path.join(dest, *parts))
            if not _inside(os.path.realpath(dest), target):
                counts["skipped"] += 1
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext == ".zip":
                counts["skipped"] += 1
                continue
            counts["files"] += 1
            try:
                size = os.path.getsize(full)
            except OSError:
                counts["skipped"] += 1
                continue
            counts["bytes"] += size
            if counts["bytes"] > MAX_BYTES or size > MAX_ONE:
                raise _refused("the export is bigger than this importer will take")
            if counts["files"] > MAX_FILES:
                raise _refused(f"the export has more than {MAX_FILES:,} files")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(full, target)


def _is_link(path: str) -> bool:
    try:
        return os.path.islink(path) or (
            hasattr(os.path, "isjunction") and os.path.isjunction(path))
    except OSError:
        return True


def extract(source: str, dest: str) -> dict:
    """`source` (a .zip or a folder) into `dest`. Returns the counts."""
    counts = {"files": 0, "skipped": 0, "bytes": 0}
    if os.path.isdir(source):
        _copy_tree(source, dest, counts)
    elif source.lower().endswith(".zip") and os.path.isfile(source):
        if os.path.getsize(source) > MAX_ZIP:
            raise _refused("that zip is larger than 2 GB")
        try:
            _read_zip(source, dest, counts)
        except zipfile.BadZipFile:
            raise _refused("that file is not a zip this can open")
        except _REFUSALS:
            raise
    else:
        raise _refused("point it at the .zip Notion made, or at a folder it was unzipped into")
    if counts["files"] == 0:
        raise _refused("there were no pages in it")
    return counts


# --------------------------------------------------------------------------
#   3. Properties -> YAML frontmatter
# --------------------------------------------------------------------------

#: The characters that make a plain YAML scalar ambiguous or invalid, anywhere
#: in the value: a colon, a comment hash, a flow indicator, a quote and the
#: punctuation YAML gives meaning to.
_YAML_AMBIGUOUS = re.compile(r'[:#\[\]{},"&*?|<>=!%@`\'"]')
#: YAML words that are NOT a plain string: quoted so the value stays the word
#: the owner's cell said. Lower-case true/false/null are handled above as the
#: bare values the converter has always written for them.
_YAML_WORDS = ("true", "false", "null", "~", "yes", "no", "on", "off", "y", "n")


def _yaml_scalar(value: str) -> str:
    """One frontmatter value, as a scalar that ALWAYS parses back as itself.

    RULING 8.6 (2026-10-21, accepted from the converter audit's RISK-1): a
    Notion database cell is a CSV field, and Shift+Enter puts a REAL newline
    inside one. The old version quoted such a value but escaped only a
    backslash and a quote, so the newline went in raw - and one raw line break
    inside a double-quoted scalar makes the note's whole YAML unreadable
    (Obsidian included), losing every property on the note rather than the one
    cell. So: line endings are normalized (CRLF and CR become LF, which also
    keeps a note's hash the same on every OS), and any value that is not a
    plain, unambiguous string is written with `json.dumps(..., ensure_ascii=
    False)` - a single-line double-quoted YAML 1.2 scalar, with newlines and
    tabs escaped as \\n and \\t.

    Simple values are UNCHANGED, byte for byte (the suite pins a whole simple
    frontmatter block): a plain word stays bare, a number stays bare, empty is
    "", and a value that merely needed quoting gets the same `"..."` it did
    before. Keys and ordering are untouched - this function is only ever
    given a value.
    """
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if text == "":
        return '""'
    if re.fullmatch(r"-?\d+(\.\d+)?", text) or re.fullmatch(r"true|false|null", text):
        return text
    needs = (bool(_YAML_AMBIGUOUS.search(text))
             or "\n" in text
             or any(ord(ch) < 0x20 for ch in text)
             or text[:1] in "-?[]{}&*|>'\""
             or text.lower() in _YAML_WORDS)
    if not needs:
        return text
    return json.dumps(text, ensure_ascii=False)


def yaml_block(front: dict) -> str:
    """Frontmatter, deterministically ordered: `notion_id` and `title` first."""
    order = ["notion_id", "title", "created", "updated", "tags"]
    keys = [k for k in order if k in front] + \
           sorted(k for k in front if k not in order)
    lines = ["---"]
    for key in keys:
        value = front[key]
        if isinstance(value, (list, tuple)):
            if not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            lines += [f"  - {_yaml_scalar(v)}" for v in value]
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


_MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)}


def iso_date(text: str) -> str:
    """Notion's date as ISO 8601, or "" when it is not a date at all."""
    text = str(text or "").strip()
    if not text:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?", text)
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        return f"{y}-{mo}-{d}" + (f"T{hh}:{mm}:{ss or '00'}" if hh else "")
    m = re.match(r"^([A-Z][a-z]+) (\d{1,2}), (\d{4})(?: (\d{1,2}):(\d{2}) ?([AP]M))?", text)
    if m:
        month, day, year, hh, mm, ap = m.groups()
        if month in _MONTHS:
            out = f"{year}-{_MONTHS[month]:02d}-{int(day):02d}"
            if hh:
                hour = int(hh) % 12 + (12 if (ap or "").upper() == "PM" else 0)
                out += f"T{hour:02d}:{mm}:00"
            return out
    return ""


def property_list(value: str) -> list:
    """A `tags`-shaped value as a list: `a, b` / `[a, b]` / `a` all work."""
    text = str(value or "").strip().strip("[]")
    if not text:
        return []
    parts = re.split(r"\s*,\s*", text)
    return [p.strip() for p in parts if p.strip()]


def frontmatter_of(title: str, notion_id: str, props: dict) -> dict:
    """The frontmatter block a Notion page becomes.

    Dates are ISO, `tags` is a list, and `notion_id` is what makes a SECOND
    import of the same export land on the same note instead of a copy of it.
    """
    front: dict = {}
    if notion_id:
        front["notion_id"] = notion_id
    front["title"] = title
    for key, value in props.items():
        name = re.sub(r"[^A-Za-z0-9_]+", "_", key.strip().lower()).strip("_")
        if not name or name in ("notion_id", "title"):
            continue
        text = str(value or "").strip()[:MAX_VALUE]
        if not text:
            continue
        if name in ("tags", "tag", "multi_select"):
            got = property_list(text)
            if got:
                front["tags" if name == "tag" else name] = got
            continue
        if name in ("created", "created_time", "created_at", "date", "updated",
                    "last_edited_time", "updated_at", "last_edited"):
            iso = iso_date(text)
            front[name] = iso or text
            continue
        front[name] = text
    return front


def split_properties(text: str) -> tuple:
    """`(title, frontmatter keys, body)` for one Notion Markdown page.

    Notion writes the title as the first `# ` heading and the page's properties
    as `Key: value` lines directly under it. Everything after the first blank
    line that is not a property is the page's own text.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title, start = "", 0
    for i, line in enumerate(lines[:8]):
        if line.startswith("# "):
            title, start = line[2:].strip(), i + 1
            break
    props: dict = {}
    i = start
    # Notion puts a BLANK LINE between the title and the properties, so the
    # blanks are stepped over before the property lines are read - otherwise
    # every page's properties end up in the body instead of the frontmatter.
    while i < len(lines) and not lines[i].strip():
        i += 1
    body_start = i
    while i < len(lines) and lines[i].strip():
        m = _PROPERTY.match(lines[i])
        if not m:
            break
        props[m.group(1)] = m.group(2)
        i += 1
        body_start = i
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    return title, props, "\n".join(lines[body_start:]).lstrip("\n")


# --------------------------------------------------------------------------
#   4. HTML -> Obsidian Markdown
# --------------------------------------------------------------------------

class _HtmlToMarkdown(HTMLParser):
    """One pass over Notion's HTML export, as LINES.

    A line buffer rather than a string, because a callout and a toggle are a
    BLOCK: every line of one has to come out `> `-prefixed, including the blank
    ones, or Obsidian ends the callout at the first line that is not. Notion's
    HTML is regular - headings, paragraphs, lists, `<details>` for a toggle,
    `<aside>` for a callout, `<input type=checkbox>` for a to-do, `<table>` of
    `<tr>`/`<td>`, `<pre><code class="language-x">` for code - and anything
    else falls through as its own text, so nothing is lost.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list = []
        self.cur = ""
        self.quote = 0
        self.lists: list = []
        self.in_pre = False
        self.pre_lang = ""
        self.fence = False
        self.row: Optional[list] = None
        self.cell = ""
        self.rows: list = []
        self.link = ""
        self.images: list = []

    # -- the line buffer ---------------------------------------------------
    def _end(self) -> None:
        if not self.cur:
            return                    # nothing to flush - never a stray `> `
        self.lines.append(("> " * self.quote) + self.cur.rstrip())
        self.cur = ""

    def _text(self, text: str) -> None:
        if not text:
            return
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if i:
                self._end()
            if self.row is not None:
                self.cell += (" " + part) if self.cell.strip() else part
            else:
                # A checkbox marker already ends in a space, and Notion's own
                # text starts with one: without this the to-do reads `- [x]  done`.
                if self.cur.endswith(("[x] ", "[ ] ")):
                    part = part.lstrip()
                self.cur += part

    def _blank(self) -> None:
        self._end()
        if self.lines and self.lines[-1].strip():
            # Inside a callout the separator is `>`: a bare blank line would
            # END the callout in Obsidian and spill the rest of the page.
            self.lines.append(">" if self.quote else "")

    def _line(self, text: str = "") -> None:
        self._end()
        self.cur = text

    # -- tags --------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._blank()
            self._line("#" * int(tag[1]) + " ")
        elif tag == "p":
            self._blank()
        elif tag == "br":
            self._end()
        elif tag == "hr":
            self._blank()
            self._line("---")
            self._blank()
        elif tag in ("strong", "b"):
            self._text("**")
        elif tag in ("em", "i"):
            self._text("*")
        elif tag == "del":
            self._text("~~")
        elif tag == "code" and not self.in_pre:
            self._text("`")
        elif tag == "code" and self.in_pre:
            # Notion marks the language on the <code> inside the <pre>.
            m = re.search(r"language-([A-Za-z0-9+#_.-]+)", a.get("class", ""))
            self.pre_lang = m.group(1) if m else ""
        elif tag == "pre":
            self._blank()
            self.in_pre = True
            self.pre_lang = ""
            self.fence = False
        elif tag == "a":
            self.link = a.get("href", "")
            self._text("[")
        elif tag == "img":
            src = a.get("src", "")
            if src:
                self.images.append(src)
            self._blank()
            self._line(f"![[{os.path.basename(decode_link(src))}]]")
        elif tag in ("ul", "ol"):
            self._blank()
            self.lists.append([tag, 0])
        elif tag == "li":
            self._end()
            depth = max(0, len(self.lists) - 1)
            kind = self.lists[-1][0] if self.lists else "ul"
            if kind == "ol":
                self.lists[-1][1] += 1
                self.cur = "  " * depth + f"{self.lists[-1][1]}. "
            else:
                self.cur = "  " * depth + "- "
        elif tag == "blockquote":
            self._blank()
            self.quote += 1
        elif tag == "aside":
            # The prefix is added when the line is flushed, so the title is
            # written WITHOUT it here (`_end` would otherwise double it).
            self._blank()
            self.quote = 1
            self._line("[!note]")
        elif tag == "details":
            self._blank()
            self.quote = 1
            self._line("[!note]- ")          # the <summary> finishes this line
        elif tag == "summary":
            pass
        elif tag == "input" and a.get("type", "").lower() == "checkbox":
            mark = "[x] " if "checked" in a else "[ ] "
            if self.cur.rstrip().endswith(("-", ".")) or not self.cur.strip():
                self.cur += mark            # a checkbox IS the list item
            else:
                self._blank()
                self._line("- " + mark)
        elif tag == "table":
            self._blank()
            self.rows = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = ""
        elif tag in ("div", "section", "article", "main"):
            self._blank()

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "section",
                   "article", "main"):
            self._blank()
        elif tag in ("strong", "b"):
            self._text("**")
        elif tag in ("em", "i"):
            self._text("*")
        elif tag == "del":
            self._text("~~")
        elif tag == "code" and not self.in_pre:
            self._text("`")
        elif tag == "pre":
            self.in_pre = False
            if self.fence:
                self._line("```")
            self._blank()
        elif tag == "a":
            self._text(f"]({self.link})")
            self.link = ""
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self._end()
            if not self.lists:
                self._blank()
        elif tag == "li":
            self._end()
        elif tag in ("blockquote", "aside", "details"):
            self._end()
            self.quote = max(0, self.quote - 1)
            self._blank()
        elif tag == "summary":
            self._end()
        elif tag == "table":
            self._end_table()
        elif tag == "tr":
            if self.row is not None:
                self.rows.append(self.row)
            self.row = None
        elif tag in ("td", "th"):
            if self.row is not None:
                self.row.append(self.cell.strip())
            self.cell = ""

    def handle_data(self, data):
        if self.in_pre:
            if not self.fence:
                self._line("```" + self.pre_lang)
                self._end()               # the fence is its own line
                self.fence = True
            self._text(data)
            return
        self._text(re.sub(r"[ \t\r\n]+", " ", data))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def _end_table(self) -> None:
        rows = [r for r in self.rows if any(c for c in r)]
        self.rows = []
        if not rows:
            return
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        cell = lambda c: (c or " ").replace("|", "\\|")          # noqa: E731
        self._blank()
        self._line("| " + " | ".join(cell(c) for c in rows[0]) + " |")
        self._line("|" + "|".join(" --- " for _ in range(width)) + "|")
        for r in rows[1:]:
            self._line("| " + " | ".join(cell(c) for c in r) + " |")
        self._blank()

    def result(self) -> str:
        self._end()
        text = "\n".join(self.lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def html_to_markdown(body: str) -> str:
    """Notion's HTML as Obsidian Markdown. Never raises on odd input."""
    parser = _HtmlToMarkdown()
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        return _html.unescape(re.sub(r"<[^>]+>", "", body)).strip() + "\n"
    return parser.result()


def is_html(text: str) -> bool:
    low = text[:2000].lower()
    return "<html" in low or "<article" in low or "<body" in low


def _html_title(text: str, fallback: str) -> str:
    """The page's own `<h1>`, or its file name with Notion's id off."""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", text or "", re.IGNORECASE | re.DOTALL)
    if m:
        got = _html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if got:
            return re.sub(r"[ \t\r\n]+", " ", got)
    return fallback


# --------------------------------------------------------------------------
#   5. Links, and the attachments folder
# --------------------------------------------------------------------------

def decode_link(href: str) -> str:
    """Notion's link target: `%20` decoded, fragment and query kept apart."""
    from urllib.parse import unquote, urlsplit
    try:
        parts = urlsplit(href.strip())
    except ValueError:
        return href.strip()
    path = unquote(parts.path)
    return path


def vault_link(target: str, display: str, known: dict) -> str:
    """A Notion link as an Obsidian wikilink, through the cleaned-name map.

    `known` maps a cleaned relative path (as written in the export, `.md`
    included) to its vault path. A link to something NOT in the export - a web
    address, or a page outside the export - is left as a normal Markdown link,
    because guessing a wikilink to a page that is not there is worse than
    leaving the address alone.
    """
    path = decode_link(target)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target.strip()):
        return f"[{display}]({target.strip()})" if display else f"<{target.strip()}>"
    if not path:
        return display or ""
    key = path.replace("\\", "/")
    for candidate in (key, key + ".md", os.path.splitext(key)[0] + ".md"):
        if candidate in known:
            name = os.path.splitext(known[candidate])[0]
            return f"[[{name}|{display}]]" if display and display != name else f"[[{name}]]"
    return f"[{display}]({target.strip()})" if display else ""


# --------------------------------------------------------------------------
#   6. Plan, describe, run
# --------------------------------------------------------------------------

@dataclass
class Plan:
    source: str
    vault: str
    name: str = ""
    notes: int = 0
    attachments: int = 0
    databases: int = 0
    rows: int = 0
    renamed: int = 0
    collisions: int = 0
    html_pages: int = 0
    refused: str = ""
    digest: str = ""
    said: str = ""
    staging: str = ""
    created: list = field(default_factory=list)
    _map: dict = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict:
        out = asdict(self)
        out.pop("_map", None)
        out.pop("staging", None)
        return out


def _vault_or_refuse(vault) -> Path:
    path = Path(os.path.expanduser(str(vault or ""))).resolve()
    if not str(vault or "").strip():
        raise _refused("choose the Obsidian vault folder to import into")
    if not path.is_dir():
        raise _refused(f"there is no folder at {path}")
    if _protected(str(path)):
        raise _refused("Jarvis does not write in that place")
    if not (path / ".obsidian").is_dir():
        raise _refused(f"{path} is not an Obsidian vault - it has no .obsidian folder")
    return path


def _name_for_export(source: str, today: Optional[str] = None) -> str:
    base = os.path.basename(os.path.normpath(str(source)))
    if base.lower().endswith(".zip"):
        base = base[:-4]
    clean = clean_name(base, keep_kind=False)
    clean, _id = split_id(clean)
    clean = re.sub(r"^Export\s*[-_]?\s*", "", clean, flags=re.IGNORECASE).strip(" -_")
    day = today or time.strftime("%Y-%m-%d")
    return f"{clean or 'Notion'} {day}"[:MAX_NAME].strip()


def plan_import(source: str, vault=None, *, today: Optional[str] = None,
                clock: Callable[[], float] = time.monotonic) -> Plan:
    """Work out what an import WOULD do, without writing anything into the vault.

    The source is read into a throwaway staging folder under the system temp
    folder (never the vault, never the settings folder), which is removed
    before this returns - so a dry run leaves nothing behind anywhere.
    """
    src = os.path.realpath(os.path.expanduser(str(source or "").strip()))
    if not str(source or "").strip() or not os.path.exists(src):
        raise _refused("there is nothing at that path to import")
    if _protected(src):
        raise _refused("Jarvis does not open files in that place")
    target = _vault_or_refuse(vault)
    name = _name_for_export(src, today)
    staging = tempfile.mkdtemp(prefix="jarvis-notion-plan-")
    p = Plan(source=src, vault=str(target), name=name, staging=staging)
    try:
        counts = extract(src, staging)
        p._map, stats = _survey(staging)
        p.notes = stats["notes"]
        p.attachments = stats["attachments"]
        p.databases = stats["databases"]
        p.rows = stats["rows"]
        p.renamed = stats["renamed"]
        p.collisions = stats["collisions"]
        p.html_pages = stats["html"]
        existing = target / name
        p.said = (f"{p.notes:,} note(s), {p.attachments:,} attachment(s), "
                  f"{p.databases:,} database(s) from {counts['files']:,} file(s).")
        if existing.exists():
            p.refused = (f"there is already a folder called \"{name}\" in that vault - "
                         f"move it or import into another vault")
        p.digest = _digest(p)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        p.staging = ""
    return p


def _digest(p: Plan) -> str:
    """A short, stable fingerprint of the plan: the same export twice gives the
    same digest, and any change to what would be written changes it."""
    import hashlib
    h = hashlib.sha256()
    h.update(f"{p.name}|{p.notes}|{p.attachments}|{p.databases}|{p.rows}|"
             f"{p.renamed}|{p.collisions}|{p.html_pages}".encode("utf-8"))
    for old, new in sorted(p._map.items()):
        h.update(f"{old}>{new}\n".encode("utf-8"))
    return h.hexdigest()[:16]


def _survey(staging: str) -> tuple:
    """Walk the extracted export and work out the vault's shape.

    Deterministic by construction: the export is walked in sorted order, so a
    collision is always resolved the same way for the same export.
    """
    mapping: dict = {}
    taken_dirs: dict = {}
    used_files: dict = {}
    #: database key -> the set of row identities it holds (see `_row_key`), so
    #: TWO CSV files of one database (`X.csv` and `X_all.csv`) count as one
    #: database with no row counted twice, and two rows with one title are two.
    database_rows: dict = {}
    stats = {"notes": 0, "attachments": 0, "databases": 0, "rows": 0,
             "renamed": 0, "collisions": 0, "html": 0}
    root = os.path.realpath(staging)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        clean_dir = _clean_dir(rel_dir, taken_dirs, stats)
        used_files.setdefault(clean_dir, set())
        for name in sorted(filenames):
            old = f"{rel_dir}/{name}" if rel_dir else name
            stem, ext = os.path.splitext(name)
            lower = ext.lower()
            if lower in ATTACHMENT_KINDS:
                new = _unique(clean_name(name), used_files.setdefault(ATTACHMENTS, set()))
                mapping[old] = f"{ATTACHMENTS}/{new}"
                stats["attachments"] += 1
            elif lower in NOTE_KINDS or lower == ".html":
                clean = clean_name(name)
                if lower == ".html":
                    # One page, one target: the HTML page is WRITTEN as `.md`,
                    # so its `.md` name is the one that must not collide with a
                    # Markdown page of the same title beside it.
                    clean = os.path.splitext(clean)[0] + ".md"
                new = _unique(clean, used_files[clean_dir])
                rel = f"{clean_dir}/{new}" if clean_dir else new
                mapping[old] = rel
                if lower == ".html":
                    stats["html"] += 1
                else:
                    stats["notes"] += 1
            elif lower == ".csv":
                clean = clean_name(name)
                new = _unique(clean, used_files[clean_dir])
                rel = f"{clean_dir}/{new}" if clean_dir else new
                mapping[old] = rel
                is_all = os.path.splitext(name)[0].endswith("_all")   # ORIGINAL name
                rows_before = database_rows.setdefault(_database_key(rel, is_all), set())
                seen: dict = {}
                for row in _read_csv(os.path.join(dirpath, name)):
                    key = _row_key(row, seen)
                    if key:
                        rows_before.add(key)
            else:
                continue
            if os.path.splitext(os.path.basename(mapping[old]))[0].casefold() != \
                    os.path.splitext(stem)[0].casefold():
                stats["renamed"] += 1
    stats["databases"] = len(database_rows)
    stats["rows"] = sum(len(rows) for rows in database_rows.values())
    return mapping, stats


def _title_column(row: dict) -> str:
    """Which column of this row is the page's title.

    Notion writes the database's OWN title-property name as the first CSV
    header, so the title column is `Name` usually and whatever the owner named
    it otherwise (`Task`, `Project`...) - never assume the word.
    """
    for key in ("Name", "Title"):
        if key in row:
            return key
    return next(iter(row), "")


def _row_title(row: dict) -> str:
    """The page title a database row is for: its title column's value."""
    if not isinstance(row, dict) or not row:
        return ""
    return str(row.get(_title_column(row), "") or "").strip()


def _row_key(row: dict, seen: dict) -> tuple:
    """The identity of ONE CSV row, so two rows with one title both survive.

    Notion's CSV carries no row id of its own, so a row whose TITLE ends in
    Notion's id shape is keyed by that id (unique by construction); every other
    row is keyed by its case-folded title plus the number of times that title
    has been seen in THIS file. That pairs the same occurrence across `X.csv`
    and `X_all.csv` while never merging two rows of one file.
    """
    title = _row_title(row)
    if not title:
        return ()
    m = _ID.search(title)
    if m:
        return ("id", m.group(1).casefold())
    key = title.casefold()
    n = seen.get(key, 0)
    seen[key] = n + 1
    return ("title", key, n)


def _database_key(csv_rel: str, is_all_variant: bool = False) -> tuple:
    """(folder, name) of a database - `X.csv` and `X_all.csv` are ONE database.

    `is_all_variant` comes from the ORIGINAL file name (Notion writes
    `<name> <id>_all.csv`), never from the cleaned name alone: a database
    genuinely called `Backlog_all`, whose plain export is
    `Backlog_all <id>.csv`, must keep its `_all`.
    """
    folder = os.path.dirname(csv_rel)
    stem = os.path.splitext(os.path.basename(csv_rel))[0]
    if is_all_variant and stem.endswith("_all"):
        stem = stem[:-len("_all")]
    return (folder, stem)


def _merged_database_rows(csv_rows: dict, all_variants: Optional[dict] = None) -> dict:
    """Every CSV export of one database as ONE row list.

    Rows are keyed by `_row_key`, not by title alone, so duplicates inside one
    file stay separate. Notion can export a database as `X.csv` and
    `X_all.csv`; the `_all` file is the complete one (it holds columns the
    plain export omits or truncates), so its non-empty values win while rows
    that only one of the files holds are all kept. Ordered by first sight, so
    the same export always lists the same rows in the same order.
    """
    variants = all_variants or {}
    merged: dict = {}
    for csv_rel, rows in sorted(csv_rows.items()):
        is_all = bool(variants.get(csv_rel))
        slots = merged.setdefault(_database_key(csv_rel, is_all), {})
        seen: dict = {}
        for row in rows:
            key = _row_key(row, seen)
            if not key:
                continue
            slot = slots.setdefault(key, {"title": _row_title(row), "row": {}})
            for col, value in row.items():
                if not str(value or "").strip():
                    continue
                if is_all or not str(slot["row"].get(col) or "").strip():
                    slot["row"][col] = value
    return {key: list(slots.values()) for key, slots in merged.items()}


def _known_pages(mapping: dict) -> dict:
    """casefolded page title -> the name to link to, from the Pass-1 map.

    Both the page's original title (Notion's id off, which is what a relation
    column writes) and its cleaned vault name resolve, so a link is only made
    to a page this export really holds - never to a guessed name.
    """
    out: dict = {}
    for old, new in mapping.items():
        if not str(new).lower().endswith(".md"):
            continue
        display = os.path.splitext(os.path.basename(new))[0]
        for title in (split_id(os.path.basename(old))[0],
                      clean_name(os.path.basename(old), keep_kind=False)):
            title = os.path.splitext(title)[0]
            if title:
                out.setdefault(title.casefold(), display)
        out.setdefault(display.casefold(), display)
    return out


def _relation_value(value, pages: dict) -> str:
    """One database cell, for a frontmatter property.

    Notion's id is taken off only when the id-free value names a page of THIS
    export, and that page becomes `[[that page]]`, so Obsidian's graph connects
    a database relation by itself. Every other value is returned UNCHANGED -
    byte for byte, comma and all - because ordinary cells (`1,234`, a long
    date, a reference that happens to end in 32 hex characters) must not be
    rewritten by a relation rule.
    """
    text = str(value or "").strip()
    if not text:
        return text
    # A whole cell that IS a page first: a page title may contain a comma, so
    # the comma-splitting below is only for a real multi-value relation cell.
    target = pages.get(text.casefold())
    if target:
        return f"[[{target}]]"
    clean_all, _id = split_id(text)
    target = pages.get(clean_all.strip().casefold())
    if target:
        return f"[[{target}]]"
    pieces = [p.strip() for p in re.split(r"\s*,\s*", text) if p.strip()]
    out, changed = [], False
    for piece in pieces:
        clean, _id = split_id(piece)
        target = pages.get(clean.strip().casefold()) or pages.get(piece.casefold())
        if target:
            out.append(f"[[{target}]]")
            changed = True
        else:
            out.append(piece)          # not a page: every character kept
    return ", ".join(out) if changed else text


def _table_cell(value) -> str:
    """One Markdown table cell: never a pipe inside it, never a raw newline."""
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _clean_dir(rel_dir: str, taken: dict, stats: dict) -> str:
    if not rel_dir:
        return ""
    out = []
    taken.setdefault("", set())
    for part in rel_dir.split("/"):
        parent = "/".join(out)
        taken.setdefault(parent, set())
        cleaned = _unique(clean_name(part, keep_kind=False), taken[parent])
        if cleaned != part:
            stats["renamed"] += 1
        if cleaned.casefold() != part.casefold():
            stats["collisions"] += 1
        out.append(cleaned)
    return "/".join(out)


# --------------------------------------------------------------------------
#   The run itself
# --------------------------------------------------------------------------

def describe(p: Plan) -> str:
    """What the card says, in plain words."""
    if p.refused:
        return f"Jarvis cannot bring this Notion export in: {p.refused}"
    return (f"Jarvis would like to bring your Notion export into the vault "
            f"\"{Path(p.vault).name}\" as a new folder called \"{p.name}\":\n"
            f"  {p.notes:,} note(s), {p.attachments:,} attachment(s), "
            f"{p.databases:,} database(s).\n"
            + (f"  {p.renamed:,} name(s) change (Notion's ids come off).\n"
               if p.renamed else "")
            + "Nothing already in the vault is changed or overwritten, and nothing is "
              "sent anywhere. Undo takes the new folder back off in one step.")


def run_import(p: Plan, *, approved: bool = False,
               record: bool = True) -> dict:
    """Do it. `approved` is a person's yes and has no default of True.

    Writes into a hidden staging folder inside the vault, then moves the whole
    tree into place in ONE step, so a failure leaves the vault exactly as it
    was. Records one reversible entry in jarvis_receipts first.
    """
    if p.refused:
        return {"ok": False, "reason": p.refused}
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was brought in",
                "plan": p.as_dict()}
    vault = _vault_or_refuse(p.vault)
    final = vault / p.name
    if final.exists():
        return {"ok": False, "reason": f"there is already a folder called \"{p.name}\" "
                                       f"in that vault"}
    staging = tempfile.mkdtemp(prefix=".jarvis-notion-", dir=str(vault))
    receipt_id = ""
    try:
        extracted = os.path.join(staging, "export")
        os.makedirs(extracted)
        extract(p.source, extracted)
        mapping, stats = _survey(extracted)
        built = os.path.join(staging, "built")
        os.makedirs(built)
        created, rows_without_notes = _build(extracted, built, mapping, p.name)
        if record and receipts is not None:
            receipt_id = receipts.record(
                RECEIPT_TOOL,
                f"brought a Notion export in as \"{p.name}\" ({stats['notes']} notes)",
                before={"folder": str(final), "existed": False},
                after={"folder": str(final)},
                undo=_undo_import)
        os.replace(built, final)
    except BaseException as exc:
        shutil.rmtree(staging, ignore_errors=True)
        if isinstance(exc, _REFUSALS):
            return {"ok": False, "reason": str(exc)}
        return {"ok": False, "reason": f"the import stopped: {type(exc).__name__}"}
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    p.created = created
    p.notes = stats["notes"]
    p.attachments = stats["attachments"]
    p.databases = stats["databases"]
    p.rows = stats["rows"]
    _audit("notion.import", {"notes": stats["notes"], "attachments": stats["attachments"],
                             "databases": stats["databases"], "html": stats["html"],
                             "renamed": stats["renamed"]})
    return {"ok": True, "folder": str(final), "receipt_id": receipt_id,
            "notes": stats["notes"], "attachments": stats["attachments"],
            "databases": stats["databases"], "rows": stats["rows"],
            "rows_without_notes": rows_without_notes,
            "html_pages": stats["html"],
            "said": f"Brought {stats['notes']:,} note(s) into \"{p.name}\"."}


def _undo_import(before) -> None:
    """The restorer jarvis_receipts calls after a restart: take the folder off."""
    folder = ""
    if isinstance(before, dict):
        folder = str(before.get("folder") or "")
    if folder and os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)


if receipts is not None:                      # pragma: no cover - import-time hook
    try:
        receipts.register_restorer(RECEIPT_TOOL, _undo_import)
    except Exception:
        pass


def _build(src: str, dest: str, mapping: dict, name: str) -> tuple:
    """Write the vault tree from the extracted export.

    Returns `(what was made, how many database rows had no page of their own)`.

    TWO PASSES, and the order matters: every database is read FIRST, because a
    row's columns are merged into the frontmatter of the page that row is, and
    a page whose name sorts before its database's CSV would otherwise be
    written before the columns were known.

    `taken` is the set of names already claimed in each folder of THIS new
    vault tree (pages and attachments). The generated hub note and `.base` go
    through the same `_unique` rule, so a real page (or an earlier generated
    file) is never silently replaced - the audit's F1/F2 findings.
    """
    created: list = []
    root = os.path.realpath(src)
    entries: list = []
    csv_rows: dict = {}
    csv_all: dict = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        for fname in sorted(filenames):
            old = f"{rel_dir}/{fname}" if rel_dir else fname
            new = mapping.get(old)
            if new:
                entries.append((new, os.path.join(dirpath, fname), fname))
    for new, full, fname in entries:
        if os.path.splitext(fname)[1].lower() == ".csv":
            csv_rows[new] = _read_csv(full)
            # `_all` is Notion's marker, read from the ORIGINAL name so a
            # database genuinely called `Backlog_all` keeps its name.
            csv_all[new] = os.path.splitext(fname)[0].endswith("_all")
    taken: dict = {}
    for new in mapping.values():
        if os.path.splitext(new)[1].lower() == ".csv":
            continue                        # a CSV becomes a note and a .base
        taken.setdefault(os.path.dirname(new), set()).add(
            os.path.basename(new).casefold())
    for new, full, fname in entries:
        lower = os.path.splitext(fname)[1].lower()
        target = os.path.join(dest, *new.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if lower in ATTACHMENT_KINDS:
            shutil.copyfile(full, target)
            created.append(new)
            continue
        if lower == ".csv":
            continue                        # the database becomes a note and a .base
        raw = _read_text(full)
        if raw is None:
            continue
        if lower in NOTE_KINDS:
            title, props, body = split_properties(raw)
            text = _rewrite_links(body, mapping)
        else:
            title = _html_title(raw, split_id(os.path.splitext(fname)[0])[0])
            props = {}
            text = _rewrite_links(html_to_markdown(raw), mapping)
        page_title = (title or "").strip() or split_id(os.path.splitext(fname)[0])[0]
        front = frontmatter_of(page_title, split_id(fname)[1], props)
        front = _wikilink_properties(front, mapping)
        front = _merge_database(front, page_title, csv_rows, mapping, csv_all)
        _write(target, yaml_block(front) + "\n\n" + text.rstrip() + "\n")
        created.append(new)
    db_notes, rows_without_notes = _database_notes(dest, csv_rows, mapping, name,
                                                   taken, csv_all)
    created += db_notes
    return created, rows_without_notes


def _wikilink_properties(front: dict, mapping: dict) -> dict:
    """A page's own property block: a relation value naming a page becomes a link.

    The header block carries the same relation columns a database CSV does, so
    both halves get the same rule. `title` and `notion_id` are the page's
    identity, never a link (an id on its own would be stripped to nothing).
    """
    pages = _known_pages(mapping)
    for key, value in list(front.items()):
        if key in ("notion_id", "title") or not isinstance(value, str):
            continue
        front[key] = _relation_value(value, pages)
    return front


def _merge_database(front: dict, title: str, csv_rows: dict, mapping: dict,
                       all_variants: Optional[dict] = None) -> dict:
    """A database row's columns, into the frontmatter of the page that row is.

    The row is found by its TITLE column - Notion names that column after the
    database's own title property, often `Name` and sometimes not. A relation
    value naming a page of this export becomes a `[[wikilink]]` (see
    `_relation_value`); the page's own property block wins over a CSV column
    when both carry one.
    """
    pages = _known_pages(mapping)
    wanted = (title or "").strip().casefold()
    for rows in _merged_database_rows(csv_rows, all_variants).values():
        for entry in rows:
            row = entry["row"]
            if entry["title"].casefold() != wanted:
                continue
            title_col = _title_column(row)
            for key, value in row.items():
                if key == title_col or not str(value or "").strip():
                    continue
                name = re.sub(r"[^A-Za-z0-9_]+", "_", key.strip().lower()).strip("_")
                if name and name not in front:
                    front[name] = _relation_value(value, pages)[:MAX_VALUE]
    return front


#: The prefix that marks a generated database hub note, so it sorts with the
#: rest of Jarvis's generated notes and is recognisable as one.
DATABASE_PREFIX = "_Database - "
#: The columns whose row counts become the hub note's collapsible summary.
DATABASE_GROUPS = ("Status", "Category", "Tags")


def _database_notes(dest: str, csv_rows: dict, mapping: dict,
                    export: str = "", taken: Optional[dict] = None,
                    all_variants: Optional[dict] = None) -> tuple:
    """For each exported database: a hub note and a `.base`.

    Returns `(created paths, rows that had no page of their own)`.

    The hub note is `_Database - <Name>.md`: frontmatter saying what it is
    (`type: database-index`, its row count, its columns, how many rows have no
    note), then a rendered Markdown table whose title column links every row to
    its child note. A row whose child page is missing is STILL a row in that
    table - an unresolved `[[wikilink]]`, exactly how an Obsidian vault shows a
    link to a note that is not there - and the note states the count in words
    too, so nothing a database declares is silently dropped. `X.csv` and
    `X_all.csv` are ONE database: their rows are merged before any of this.

    `taken` is the shared set of names already used in each folder of the new
    tree; both files go through `_unique`, so a page of the same name (or a
    second database whose name differs only by case, one path on NTFS) gets a
    free name here instead of being silently replaced. The hub's frontmatter
    `title` stays the DATABASE's own name, and the `.base` view too - only the
    file name gains the number when two would collide.
    """
    created: list = []
    rows_without_notes = 0
    pages = _known_pages(mapping)
    taken = {} if taken is None else taken
    for (folder, base_name), entries in sorted(
            _merged_database_rows(csv_rows, all_variants).items()):
        target = os.path.join(dest, *folder.split("/")) if folder else dest
        os.makedirs(target, exist_ok=True)
        taken_here = taken.setdefault(folder, set())
        hub_name = _unique(f"{DATABASE_PREFIX}{base_name}.md", taken_here)
        base_file = _unique(f"{base_name}.base", taken_here)
        columns: list = []
        for entry in entries:
            for key in entry["row"]:
                if key not in columns:
                    columns.append(key)
        title_col = _title_column(entries[0]["row"]) if entries else "Name"
        other = [c for c in columns if c != title_col]
        table = ["| " + " | ".join([_table_cell(title_col)]
                                   + [_table_cell(c) for c in other]) + " |",
                 "| " + " | ".join(["---"] * (1 + len(other))) + " |"]
        missing = 0
        for entry in entries:
            title = entry["title"]
            link = pages.get(title.casefold()) or clean_name(title, keep_kind=False) or title
            if title.casefold() not in pages:
                missing += 1       # a row with no page still gets its line
            table.append("| " + " | ".join(
                [f"[[{link}]]"]
                + [_table_cell(_relation_value(entry["row"].get(col, ""), pages))
                   for col in other]) + " |")
        rows_without_notes += missing
        front = {"type": "database-index", "title": base_name,
                 "rows": len(entries), "columns": [title_col] + other,
                 "rows_without_notes": missing}
        body = [yaml_block(front), "", f"# {base_name}", "", "\n".join(table)]
        if missing:
            body += ["", (f"{missing} row(s) in this database have no note in this export - "
                          f"they stay in the table above so nothing the database holds "
                          f"is lost.")]
        group_col = next((c for c in DATABASE_GROUPS
                          if c in other and any(str(e["row"].get(c, "")).strip()
                                                for e in entries)), "")
        if group_col:
            counts: dict = {}
            for entry in entries:
                label = " ".join(str(entry["row"].get(group_col, "") or "").split()) or "(empty)"
                counts[label] = counts.get(label, 0) + 1
            summary = [f"<details>", f"<summary>By {group_col}</summary>", ""]
            summary += [f"- {label}: {n}" for label, n in sorted(counts.items())]
            summary += ["", "</details>"]
            body += ["", "\n".join(summary)]
        _write(os.path.join(target, hub_name), "\n".join(body) + "\n")
        created.append(f"{folder}/{hub_name}" if folder else hub_name)
        # Obsidian's Bases file: a table of everything in this folder. The path
        # is vault-relative, so it carries the export folder's own name.
        where = "/".join(p for p in (export, folder) if p)
        base = ("filters:\n"
                "  and:\n"
                f"    - 'file.inFolder(\"{where}\")'\n"
                "views:\n"
                "  - type: table\n"
                f"    name: {base_name}\n")
        _write(os.path.join(target, base_file), base)
        created.append(f"{folder}/{base_file}" if folder else base_file)
    return created, rows_without_notes


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return f.read(MAX_TEXT).decode("utf-8", "replace")
    except OSError:
        return None


def _read_csv(path: str) -> list:
    import csv as _csv
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            return [dict(row) for row in _csv.DictReader(f)]
    except OSError:
        return []


def _rewrite_links(text: str, mapping: dict) -> str:
    """Notion's relative links as wikilinks, through the cleaned-name map.

    Two passes: Markdown links `[label](target)`, and embeds `![[name]]` that
    an earlier pass wrote from the file's ORIGINAL name (the HTML converter
    cannot know the cleaned one - it has no map).
    """
    known: dict = {}
    for old, new in mapping.items():
        known[old] = new
        known[old.replace(" ", "%20")] = new
        known[os.path.basename(old)] = new

    def embed(m):
        target = m.group(1).strip()
        got = known.get(target) or known.get(os.path.basename(target)) or ""
        if not got:
            return m.group(0)
        name = os.path.basename(got)
        alias = m.group(2) or ""
        return f"![[{name}{alias}]]"

    def one(m):
        bang, label, target = m.group(1), m.group(2), m.group(3)
        if target.startswith(("http://", "https://", "mailto:", "#", "tel:")):
            return m.group(0)
        if bang:
            # An image: the attachment's own new name, wherever it went.
            path = decode_link(target)
            got = known.get(path) or known.get(os.path.basename(path)) or ""
            return f"![[{os.path.basename(got)}]]" if got else m.group(0)
        return _one_link(label, target, known)

    text = re.sub(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)", one, text)
    return re.sub(r"!\[\[([^\]|#]+)(\|[^\]]*)?\]\]", embed, text)


def _one_link(label: str, target: str, known: dict) -> str:
    """One link. A page the export holds becomes a wikilink; a web address is
    left exactly as it was - guessing a wikilink to a page that is not there is
    worse than leaving the address alone."""
    if target.startswith(("http://", "https://", "mailto:", "#", "tel:")):
        return f"[{label}]({target})"
    got = vault_link(target, label, known)
    return got or f"[{label}]({target})"


# --------------------------------------------------------------------------
#   The routes - a plug-in folder calls install()
# --------------------------------------------------------------------------

_ARMED = False
_P_LOCK = threading.Lock()
_P_STATE: dict = {"pending": {}, "latest": {}}


def armed() -> bool:
    return _ARMED


def preview(body, *, here: Optional[bool] = None) -> tuple:
    """POST /api/notion/preview: the dry run, as counts and a digest."""
    try:
        p = plan_import(str((body or {}).get("source") or ""),
                        (body or {}).get("vault"))
    except Exception as exc:
        return 200, {"ok": False, "reason": str(exc) or type(exc).__name__}
    return 200, {"ok": not p.refused, "plan": p.as_dict(), "said": describe(p)}


def request_import(body, *, gate=None) -> tuple:
    """POST /api/notion/import: ONE approval card, then the import.

    The card is raised at the gate's own tier for `import_notion_export`; a
    denied, timed-out or refused card brings nothing in, and `run_import` is
    never reached without a person's yes.
    """
    try:
        p = plan_import(str((body or {}).get("source") or ""), (body or {}).get("vault"))
    except Exception as exc:
        return 200, {"ok": False, "reason": str(exc) or type(exc).__name__}
    if p.refused:
        return 200, {"ok": False, "reason": p.refused}
    if str((body or {}).get("digest") or "") not in ("", p.digest):
        return 200, {"ok": False,
                     "reason": "the export changed since the preview, so nothing was "
                               "brought in - look at it again"}
    check = gate or _gate
    try:
        verdict = check(GATE_ACTION, {"folder": p.name}, describe(p))
    except Exception as exc:
        return 200, {"ok": False, "reason": f"the approval could not be asked for: "
                                            f"{type(exc).__name__}"}
    if not _person_said_yes(verdict):
        return 200, {"ok": False, "reason": "not approved; nothing was brought in"}
    out = run_import(p, approved=True)
    return 200, out


def _person_said_yes(verdict) -> bool:
    if isinstance(verdict, dict):
        return bool(verdict.get("allowed")) and str(verdict.get("outcome", "")) == "approved"
    return bool(getattr(verdict, "allowed", False)) and \
        str(getattr(verdict, "outcome", "")) == "approved"


def _peer_local(handler) -> tuple:
    """The two addresses a request carries, for `_from_this_pc`."""
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def _from_this_pc(peer, local) -> bool:
    """True only when this request comes from this PC (fail closed).

    The SAME rule `jarvis_documents` uses for its folder routes: loopback is
    this PC, and a program on this PC calling its own Tailscale address arrives
    from the address it arrived at. `peer is None` is the in-process
    convention (no network request behind the call); a real socket cannot
    produce it. Anything unknown is not this PC.
    """
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False


#: What a request from another device is told. It names no path and no folder.
PC_ONLY_REASON = ("Jarvis brings a Notion export in on the PC only - the export "
                  "file and the vault are chosen here.")


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the server's GET/POST so the two routes above are answered here.

    Both POST routes are PC-only (2026-10-21 audit, R4): the export file and
    the vault are folders on this PC, and the preview works out what is in the
    export, so a paired device must not be able to ask either question - the
    same rule `/api/folders/import` already keeps.
    """
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_notion", False):
        _ARMED = True
        return "  notion     Notion export -> Obsidian vault (already on)"

    def _allowed(self) -> bool:
        try:
            return bool(origin_ok(self)) and bool(token_ok(self))
        except Exception:
            return False

    def do_GET(self):
        route = str(getattr(self, "path", "")).split("?")[0]
        if route != PATHS[0]:
            return get0(self)
        if not _allowed(self):
            return _send(self, 403, {"ok": False, "reason": "not allowed"})
        return _send(self, 200, {"ok": True, "title": TITLE, "detail": DETAIL,
                                 "armed": _ARMED})

    def do_POST(self):
        route = str(getattr(self, "path", "")).split("?")[0]
        if route not in PATHS:
            return post0(self)
        if not _allowed(self):
            return _send(self, 403, {"ok": False, "reason": "not allowed"})
        if not _from_this_pc(*_peer_local(self)):
            return _send(self, 403, {"ok": False, "pc_only": True,
                                     "reason": PC_ONLY_REASON})
        try:
            body = read_body(self)
            if isinstance(body, bytes):
                body = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            body = {}
        # ONE ROUTE, ONE ACTION (2026-10-20, field test). This line used to be
        #     code, out = request_import(body if route == PATHS[1] else body)
        # - a conditional whose two branches are the same expression, so the
        # IMPORT ran for the PREVIEW too: a documented dry run raised an
        # approval card, wrote a real folder into the vault, and only then
        # overwrote its answer with preview(). Measured on the owner's PC: two
        # preview calls raised two cards (approved) and imported twice; the
        # second preview then refused with "there is already a folder called".
        # A dry run must do only what preview() does: plan, write nothing.
        if route == PATHS[0]:
            code, out = preview(body)
        else:
            code, out = request_import(body)
        return _send(self, code, out)

    do_GET._jarvis_notion = True       # type: ignore[attr-defined]
    do_POST._jarvis_notion = True      # type: ignore[attr-defined]
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  notion     Notion export -> Obsidian vault"


def _send(self, code: int, payload: dict):
    raw = json.dumps(payload).encode("utf-8")
    try:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    except Exception:
        pass


def _reset_for_tests() -> None:
    global _ARMED
    with _P_LOCK:
        _P_STATE["pending"].clear()
        _P_STATE["latest"].clear()
    _ARMED = False


if __name__ == "__main__":
    print(f"  {TITLE}")
    print(f"  {state_path()}")
