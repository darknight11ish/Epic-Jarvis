"""jarvis_project_read.py - read ONE file inside a folder the owner has already
put on "Folders Jarvis may look in".

NEW MODULE, shipped whole. It is the READ half of "Jarvis takes over dev work"
(the owner's approved plan; the 2026-11-05 project decision said each
previously-unbuilt item needs its own owner decision, and this is the read
half's, recorded in `decisions.d/2026-11-09-project-read.md`). One model tool:
`project_read`.

THE GAP IT CLOSES, IN PLAIN WORDS
  Two read paths exist and neither one does this job:
    * `file_read` (jarvis_agent.py) opens any text file, but it has NO check
      against the owner's folder list at all - it is the unbounded read.
    * `my_files`' `read` action IS bounded (jarvis_documents.read ->
      `allowed_path`), but it refuses code: `TEXT_KINDS` is md/txt/csv, so a
      .py, .js, .json or .toml file is answered with "Jarvis reads PDF, Word,
      Excel, PowerPoint, Markdown, text and CSV files only."
  So "read this Python file in my project" had no bounded door. This module is
  that door - a COMPOSITION of two things that already exist, not a third
  boundary:
    * `jarvis_documents.allowed_path()` - the ONE folder boundary the files
      tool uses, asked for the folder and then again for every file;
    * `jarvis_repomap._walk()` - the only `.gitignore`-aware walk in this tree,
      with the project map's own per-file cap (`MAX_FILE_BYTES`) beside it.

WHAT IT MAY LOOK AT, AND WHY THAT LIST IS NOT A SECOND LIST
  * The folder must be on "Folders Jarvis may look in", or be a registered
    project's own folder (which `jarvis_projects.check_folder` already requires
    to be on that same list). Both are asked through `allowed_path()`, so
    hidden folders, "never looks in" places, "Protected from Jarvis" items,
    reserved Windows names and links that lead outside are refused by the
    EXISTING code rather than by a new rule here.
  * The file is then asked for by `allowed_path()` again, resolved: a link that
    leads out of the folder is refused, and the check that passes is the same
    path that is opened (the lesson `file_read` records - checking one path and
    opening another lets a link swapped in between point elsewhere).
  * `.gitignore` is honoured by the SAME walk the repository map uses: a file
    the map would not list - ignored by the folder's own `.gitignore`, inside a
    build/vendor/dependency folder, or hidden - is refused here too, in one
    plain sentence. So the two readers cannot disagree about the same file.
  * `.gitignore`-aware is NOT "tracked files only", and this module says so
    rather than borrowing the phrase: `_walk` never asks git. An IGNORED file
    is skipped; an untracked file that is not ignored is read, exactly as the
    map lists it.

WHAT IT DOES AND DOES NOT DO
  * It WRITES NOTHING. No index, no cache, no temporary file: the walk is
    read-only and the text is held in memory.
  * It runs no program, starts no child process, opens no socket and calls no
    model. Standard library only.
  * It raises NO approval card and adds NO gate action. Reading is decided
    under `file_read`'s own action, `read_files_readonly` (tier "auto" in the
    shipped `[autonomy.tiers]`), which is the same line `file_read` and
    `my_files` already use - see `gate_lookup_name` at its one tool
    declaration in jarvis_agent.py. There is no loosening here: nothing is
    approved, moved or written, so there is nothing to approve.
  * It is a READ, so `jarvis_agent._PROTECTION_READ_ONLY_TOOLS` names it: a
    folder the owner marked read-only may be read, and one marked blocked is
    refused by `allowed_path()` before this module ever opens anything.
  * Its result carries `outside_text: True`, like `my_files` and the map, and
    the agent's own boundary (`_TurnWatch.took_in`) labels and scans every
    tool result before the model reads it. The text itself is NOT wrapped in a
    label inside `content`: a sentence put into the middle of the code would
    be a sentence the model might quote as if the file said it, and
    `file_read` - this module's unbounded twin - does not do it either.

THE TWO WAYS IN
  * `path` is a folder on the owner's list, OR a registered project's id
    (32 hex characters in practice - `uuid4().hex`; the map's own matcher
    accepts 16 to 64, and a name is only taken as an id when it is not an
    existing folder - the same one field `my_files`' `map` action already uses
    for the same reason).
  * `file` is the file's path INSIDE that folder, with forward or back
    slashes: `app/server.py`. A whole path, a `..` step, a drive letter or a
    leading slash is refused before anything is joined.

THE SHAPE OF AN ANSWER
  {"ok": true, "content": "<the file's text>", "path": "<the resolved file>",
   "file": "app/server.py", "folder": {"path", "name"}, "bytes": int,
   "cap": int, "truncated": bool, "outside_text": true, "what": "..."}
  A project read adds {"project": {"id", "name"}}. A refusal is
  {"ok": false, "error": "<ONE plain sentence>"} and never a stack trace,
  which is the rule every refusal in this module follows - `read_folder` and
  `run_tool` return, they do not raise, for anything a caller can cause.

A LINE RANGE, AND THE ONE FOOTER
  `start_line` and `lines` are optional whole numbers: the first line to show
  (1-based, default 1) and how many lines to show (default 400, hard cap
  2,000). Asking for either turns the read into a range: `content` is numbered
  lines - "12: the line's own words" - and the answer also carries
  `start_line`, `end_line`, `total_lines` and `line_cap`. A range is capped at
  96 KiB of text as well as 2,000 lines, so one answer can never overflow the
  model's context.
  The footer lives in `more`, NEVER in `content`: the model reads `content` as
  source code, and a sentence put inside it is a sentence the model might quote
  as if the file said it. `more` says, word for word, what to ask for next:
  "Showing lines A\u2013B of N; request the next line range to read more". A file
  over 64 MiB is not counted line by line - counting it would mean reading the
  whole file - so that footer says the exact total is unknown instead, and a
  range can still be asked for. When nothing follows, `more` is absent.
  With neither argument the read is the whole file, exactly as it was before a
  range existed: the same keys, the same `truncated` flag. If that whole read
  is cut at the byte cap, `more` carries the same "request the next line range"
  sentence, using the counted total where the file is small enough to count.
  The first line is line 1, a line ends at a newline (so a Windows CRLF counts
  once), and a last piece with no newline is still a line - the same rule
  numbers, counts and reports, so A, B and N can never disagree. A range read
  drops the `\r` of a CRLF from the text it shows, never from the count.

CREDENTIAL FILES ARE REFUSED BY NAME
  A file whose NAME says it holds a key, a password or a token is refused with
  one plain sentence, even inside a folder the owner listed: `.env` and
  `.env.*`, `.netrc`, `.git-credentials`, `.npmrc`, `credentials`,
  `credentials.json`, a private key (`id_rsa`, `id_ed25519`, `id_ecdsa`,
  `id_dsa`, with or without a suffix), the `.pem`, `.key`, `.pfx`, `.p12`,
  `.kdbx` and `.jks` extensions, and any path with a `.git` folder in it. The
  check is the NAME only: it never opens the file, never asks whether it
  exists, and never lists anything. Ordinary source files that merely contain
  one of those words - `key.py`, `keys.py`, `env.py`, `credentials_migration.py`
  - are read exactly as before. It runs when the folder/file boundary has
  already refused the path (so the sentence says WHY, instead of the broad
  "only folders on the list" answer that is untrue for a file inside a listed
  folder) and again after the walk, before the file is opened, so a name the
  boundary does not know about (`id_dsa`, `credentials.json`) is refused too.

THE HONEST LIMITS
  * The whole-file cap is `jarvis_repomap.MAX_FILE_BYTES` (512 KB), reused so
    the two readers cut at the same place. A file over it is read to the cap
    and the answer says `truncated: true` - it is not refused, and the model is
    told, so a cut file is never presented as the whole file. A file over the
    cap can be read in full a line range at a time, and the `more` footer says
    which range to ask for next.
  * A binary file (a NUL byte in its first 8,192 bytes) is refused in words
    rather than returned as mojibake.
  * Bytes that are not valid UTF-8 are decoded with replacement characters,
    exactly as `file_read` and the map do; nothing else happens.
  * The walk is the map's, so it carries the map's bounds: at most
    `MAX_FILES_SEEN` files and `MAX_SECONDS` seconds. When it stops early the
    answer says so, and a file that was not reached is refused with the bound
    that stopped it named - never reported as "no such file".
  * `jarvis_sources.KNOWN_TOOLS` does not name this tool yet, so an answer
    built on this read carries no "where this came from" chip. Adding one line
    there is a separate, tiny change; it is said here rather than left to be
    discovered.
"""
from __future__ import annotations

import os
import re

try:
    import jarvis_repomap as RM
except Exception:                                            # noqa: BLE001
    RM = None

#: The per-file cap, taken from the project map's own constant - never a second
#: number that could drift from it. 0 when the map module is missing, and then
#: every read is refused with MISSING below (a cap of zero would otherwise
#: return an empty file and call it a success).
MAX_FILE_BYTES = RM.MAX_FILE_BYTES if RM is not None else 0

#: What a caller is told when the map module - the bounded walk this module
#: reuses - is not on this backend at all.
MISSING = ("The project map is not installed on this backend, so there is nothing that can "
           "walk one of your folders for a code file.")

#: One plain sentence for a refused path shape, kept here because they are the
#: words the model reads back.
NEED_FOLDER = ("Say which folder on your list - or which project - the file is in, and its "
               "path inside that folder.")
NEED_FILE = ("Say which file to read: its path inside the folder, for example app/server.py.")
WHOLE_PATH = ("That is a whole path, not a path inside the folder. Give the file's place "
              "inside the folder - for example app/server.py.")
CLIMBS_OUT = ("That path climbs out of the folder with \"..\", so it is refused: Jarvis reads "
              "only files inside the folder you listed.")
NOT_ALLOWED = ("Jarvis may read only files inside the folders on the owner's list (Settings, "
               "Folders Jarvis may look in), and never keys, saved passwords, browser data, "
               "hidden folders or an item on the \"Protected from Jarvis\" list.")
GONE = "That folder is not on this PC any more, so there is nothing to read."
IS_FOLDER = "That is a folder, not a file, so there are no words in it to read."
NO_FILE = "There is no file at {file} in that folder."
SKIPPED = ("That file is not one Jarvis reads from this folder: the folder's own .gitignore "
           "skips it, or it sits in a build, vendor or dependency folder - the same rule the "
           "project map follows. Nothing was read.")
BINARY = ("That is a binary file - a picture, a program or an archive - not text, so there are "
          "no words in it to read.")
CREDENTIAL = ("That is a credential file (its name says it holds a key, a password or a "
              "token), so Jarvis will not read it even inside a folder you listed.")
BAD_RANGE = ("A line range needs two whole numbers of 1 or more: start_line, the first line "
             "to show, and lines, how many lines to show (at most {cap:,}) - so nothing was "
             "read.")

#: A range read returns this many lines when the caller does not say, and never
#: more than MAX_LINES however large a number it sends. MAX_SLICE_BYTES is the
#: third bound: 2,000 normal lines fit easily, and 2,000 enormous ones still
#: cannot overflow the model's context.
DEFAULT_LINES = 400
MAX_LINES = 2000
MAX_SLICE_BYTES = 96 * 1024
#: A file bigger than this is not counted line by line. Counting means reading
#: every byte, and the answer says the exact total is unknown rather than
#: spending a read of the whole file on a number.
MAX_COUNT_BYTES = 64 * 1024 * 1024

#: The ONE footer a cut read carries, in `more` - never in `content`. This is
#: the exact sentence the 2026-11-09 architecture ruling asked for, so the
#: model is told which range to ask for next instead of silently losing text.
MORE = ("Showing lines {first}\u2013{last} of {total}; request the next line range to read "
        "more")
#: The same footer when the slice stopped at the answer-size limit before the
#: range asked for was complete, not at the end of the file.
MORE_BYTES = ("Showing lines {first}\u2013{last} of {total}; the {kib} KiB limit for one "
              "answer was reached first, so request the next line range to read more")
#: The footer when the file is over MAX_COUNT_BYTES: the exact total is not
#: known, and it says so instead of guessing one.
MORE_UNKNOWN = ("Showing lines {first}\u2013{last}; the exact total is unknown because this "
                "file is too big to count every line (over {mib} MiB) - ask for a line range "
                "to read on.")
MORE_BYTES_UNKNOWN = ("Showing lines {first}\u2013{last}; the exact total is unknown because "
                      "this file is too big to count every line (over {mib} MiB), and the "
                      "{kib} KiB limit for one answer was reached first - ask for a line "
                      "range to read on.")
#: One line longer than a whole answer may be. A line range cannot split a line,
#: so the start of it is shown and the footer says exactly that.
TOO_LONG = ("Line {line} alone is longer than the {kib} KiB limit for one answer, so only "
            "its start is shown - a line range cannot read the rest of that line.")

#: What the model is told this tool gave it, in one line.
WHAT = ("the words of one file - or one line range of it - inside a folder you listed, read "
        "only - nothing was changed, moved or sent anywhere")


def _documents():
    """jarvis_documents, or None when this backend does not ship it.

    A missing copy means there is no "Folders Jarvis may look in" list at all,
    so there is nothing this module may read: the caller refuses in words.
    """
    try:
        import jarvis_documents
        return jarvis_documents
    except Exception:                                       # noqa: BLE001
        return None


def _projects():
    try:
        import jarvis_projects
        return jarvis_projects
    except Exception:                                       # noqa: BLE001
        return None


# --------------------------------------------------------------------------
#   The file's path INSIDE the folder - checked before anything is joined
# --------------------------------------------------------------------------

_DRIVE = re.compile(r"^[A-Za-z]:")


def _parts_of(rel):
    """(parts, "") for a path inside the folder, or (None, why) in one sentence.

    Refused here, before a single path is built: a whole path (drive letter,
    UNC, leading slash), a `..` step, an empty or whitespace-only name, and a
    NUL byte. Everything else - hidden names, links, protected places - is
    `allowed_path()`'s own refusal, not a second list here.
    """
    if not isinstance(rel, str) or not rel.strip() or "\x00" in rel:
        return None, NEED_FILE
    text = rel.strip()
    if os.path.isabs(text) or _DRIVE.match(text) or text[:1] in ("\\", "/"):
        return None, WHOLE_PATH
    parts = [p for p in text.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts:
        return None, NEED_FILE
    if ".." in parts:
        return None, CLIMBS_OUT
    return parts, ""


def _want(parts) -> str:
    """The requested path as the map prints one: forward slashes."""
    return "/".join(parts)


def _same(a: str, b: str) -> bool:
    """Two relative paths, compared the way this filesystem compares names.

    `normcase` folds case on Windows and leaves it alone elsewhere, which is
    exactly the question being asked: does this name on THIS disk still name
    the same file. It can never widen the walk: the comparison is against a
    file the walk itself listed and `allowed_path()` already accepted.
    """
    return os.path.normcase(a) == os.path.normcase(b)


#: The names that say "this holds a key, a password or a token". Asked of the
#: NAME only - `_credential` never opens, stats or lists anything.
_CRED_NAMES = (".env", ".netrc", ".git-credentials", ".npmrc", "credentials",
               "credentials.json")
_CRED_STEMS = ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")
_CRED_EXTS = (".pem", ".key", ".pfx", ".p12", ".kdbx", ".jks")


def _credential(rel, real="") -> bool:
    """True when this NAME says the file holds a key, a password or a token.

    Asked of the path inside the folder, of the file's own name, and - when a
    resolved `real` path is given - of the name it leads to, so a link called
    `notes.py` that points at a private key is still refused. It is the name
    and nothing else: no `open`, no `stat`, no `listdir`, so the answer cannot
    depend on the file existing or on being able to read it.

    Deliberately narrow: `key.py`, `keys.py`, `env.py` and
    `credentials_migration.py` are ordinary source files and are NOT refused.
    A `.git` FOLDER anywhere in the path is refused (a git store holds
    credentials); a file merely called `my.git` is not.
    """
    parts = [p for p in str(rel or "").replace("\\", "/").split("/")
             if p not in ("", ".")]
    if any(p.lower() == ".git" for p in parts[:-1]):
        return True
    names = [parts[-1]] if parts else []
    if real:
        try:
            names.append(os.path.basename(os.path.realpath(real)))
        except OSError:
            pass
    for name in names:
        low = str(name or "").strip().lower()
        if not low:
            continue
        if low in _CRED_NAMES or low.startswith(".env."):
            return True
        if any(low.startswith(stem) for stem in _CRED_STEMS):
            return True
        if os.path.splitext(low)[1] in _CRED_EXTS:
            return True
    return False


# --------------------------------------------------------------------------
#   Reading one file, behind the boundary and behind the walk
# --------------------------------------------------------------------------


def _read_bytes(real: str) -> dict:
    """{"raw": the bytes read, "truncated": whether more followed} for one
    already-approved real path - one byte past the cap, to tell a file that
    fits from one that does not."""
    cap = MAX_FILE_BYTES
    with open(real, "rb") as fh:
        raw = fh.read(cap + 1)
    return {"raw": raw[:cap], "truncated": len(raw) > cap}


# --------------------------------------------------------------------------
#   A line range: numbered lines, the real total, and ONE honest footer
# --------------------------------------------------------------------------


def _line_range(start_line, lines):
    """(first, count, why) for the two optional arguments; why "" is fine.

    `(None, None, "")` means the caller asked no line question at all, and the
    read stays a whole-file read. `start_line` is 1-based and `lines` is capped
    at MAX_LINES rather than refused, so a model asking for more simply gets
    the most one answer may carry. A value that is not a whole number of 1 or
    more is refused in one sentence - never an exception.
    """
    if start_line is None and lines is None:
        return None, None, ""
    if start_line is None:
        first = 1
    else:
        if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1:
            return None, None, BAD_RANGE.format(cap=MAX_LINES)
        first = start_line
    if lines is None:
        return first, DEFAULT_LINES, ""
    if isinstance(lines, bool) or not isinstance(lines, int) or lines < 1:
        return None, None, BAD_RANGE.format(cap=MAX_LINES)
    return first, min(lines, MAX_LINES), ""


def _count_lines(real: str):
    """(total, known): the real number of lines, counted by streaming the file.

    A line ends at a newline byte (a Windows CRLF counts once), and a last
    piece with no newline is still a line - the same rule the range read uses,
    so the numbered lines, `end_line` and `total_lines` can never disagree.
    A file over MAX_COUNT_BYTES is NOT counted: counting means reading every
    byte, so `known` is False and the footer says the exact total is unknown
    rather than guessing one.
    """
    try:
        if os.path.getsize(real) > MAX_COUNT_BYTES:
            return None, False
    except OSError:
        return None, False
    total = 0
    last = b"\n"
    try:
        with open(real, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                total += chunk.count(b"\n")
                last = chunk[-1:]
    except OSError:
        return None, False
    if last not in (b"", b"\n"):
        total += 1
    return total, True


def _line_text(raw: bytes) -> str:
    """One line's bytes as text: UTF-8 with replacement, and the `\\r` of a
    Windows CRLF dropped from what is SHOWN (never from the count)."""
    text = raw.decode("utf-8", "replace")
    return text[:-1] if text.endswith("\r") else text


def _each_line(real: str):
    """(line number, text, the file bytes it took) for every line, in order.

    Read in binary chunks, so a memory-mapped or very long file is never
    loaded whole; only the piece still being assembled is held. Line 1 is the
    first line.
    """
    line_no = 0
    pending = b""
    with open(real, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            pending += chunk
            start = 0
            while True:
                cut = pending.find(b"\n", start)
                if cut < 0:
                    break
                raw = pending[start:cut]
                line_no += 1
                yield line_no, _line_text(raw), len(raw) + 1
                start = cut + 1
            pending = pending[start:]
    if pending:
        line_no += 1
        yield line_no, _line_text(pending), len(pending)


def _slice_lines(real: str, first: int, count: int) -> dict:
    """The numbered lines a range read returns, and why it stopped.

    {"lines": ["12: the words", ...], "end_line": int, "bytes": int,
     "more": bool, "stopped_bytes": bool, "cut_one": bool}

    `end_line` is the real file line number of the last line shown, or
    `first - 1` when nothing was shown because the file ends before `first`.
    At most `count` lines, and at most MAX_SLICE_BYTES of text: when the next
    line would not fit, the read stops there and the footer says so. A single
    line longer than that whole budget is the one case where a piece of one
    line is shown (`cut_one`), because a line range cannot split a line.
    """
    lines, used, size, last = [], 0, 0, first - 1
    stopped_bytes = cut_one = False
    it = _each_line(real)
    for line_no, text, raw in it:
        if line_no < first:
            continue
        piece = f"{line_no}: {text}"
        if used + len(piece) + 1 > MAX_SLICE_BYTES:
            stopped_bytes = True
            if not lines:
                room = max(0, MAX_SLICE_BYTES - len(f"{line_no}: "))
                piece = f"{line_no}: {text[:room]}"
                lines.append(piece)
                size += len(piece.encode("utf-8", "replace"))
                last = line_no
                cut_one = True
            break
        lines.append(piece)
        used += len(piece) + 1
        size += raw
        last = line_no
        if len(lines) >= count:
            break
    more = stopped_bytes or next(it, None) is not None
    return {"lines": lines, "end_line": last, "bytes": size,
            "more": more, "stopped_bytes": stopped_bytes, "cut_one": cut_one}


def _footer(first: int, last: int, total, known: bool,
            stopped_bytes: bool, cut_one: bool) -> str:
    """The ONE `more` sentence, chosen by exactly why the read stopped."""
    kib = MAX_SLICE_BYTES // 1024
    mib = MAX_COUNT_BYTES // (1024 * 1024)
    if cut_one:
        return TOO_LONG.format(line=last, kib=kib)
    if known and stopped_bytes:
        return MORE_BYTES.format(first=first, last=last, total=total, kib=kib)
    if known:
        return MORE.format(first=first, last=last, total=total)
    if stopped_bytes:
        return MORE_BYTES_UNKNOWN.format(first=first, last=last, mib=mib, kib=kib)
    return MORE_UNKNOWN.format(first=first, last=last, mib=mib)


def read_folder(folder, rel, *, roots=None, clock=None,
                start_line=None, lines=None) -> dict:
    """Read ONE file inside `folder`, which must be on the owner's list.

    `start_line` and `lines` are the optional line range: both None is the
    whole-file read this call has always done. `ok: False` and one plain
    sentence for every refusal; nothing is raised for anything a caller can
    cause. See the module docstring for the shape.
    """
    import time as _time
    clock = clock or _time.monotonic
    if RM is None:
        return {"ok": False, "available": False, "error": MISSING}
    docs = _documents()
    if docs is None:
        return {"ok": False, "available": False,
                "error": "Looking in folders is not installed on this backend, so there is "
                         "nothing to read."}
    parts, why = _parts_of(rel)
    if parts is None:
        return {"ok": False, "available": True, "error": why}
    first, count, why = _line_range(start_line, lines)
    if why:
        return {"ok": False, "available": True, "error": why}
    want = _want(parts)
    listed = docs.folders() if roots is None else list(roots)
    got = docs.allowed_path(folder, listed)
    if got is None:
        # The WHOLE refusal, in the same words the project map uses: the folder
        # itself is not on the list, so no walk starts and nothing is guessed.
        return {"ok": False, "available": True, "error": RM.REFUSED}
    root = got[0]
    if not os.path.isdir(root):
        return {"ok": False, "available": True, "error": GONE}

    # The boundary, asked for the file itself BEFORE it is opened: a link that
    # leads out of the folder resolves outside it and is refused here. `..` was
    # refused above, so this join cannot climb out on its own.
    candidate = os.path.join(root, *parts)
    got = docs.allowed_path(candidate, [root])
    if got is None:
        # The boundary says no. Ask the credential checker WHY, because a
        # `.env`, a private key or `.git/config` inside a LISTED folder is not
        # refused for being outside the list - it is refused for its name, and
        # the owner should read that reason. The checker has still run after
        # the boundary and before anything is opened; it never touches the file.
        if _credential(want, candidate):
            return {"ok": False, "available": True, "error": CREDENTIAL}
        return {"ok": False, "available": True, "error": NOT_ALLOWED}
    real = got[0]
    if os.path.isdir(real):
        return {"ok": False, "available": True, "error": IS_FOLDER}
    if not os.path.isfile(real):
        return {"ok": False, "available": True, "error": NO_FILE.format(file=want)}

    # The walk, so `.gitignore` and the build/vendor folders decide the same
    # way they do for the project map. A file the walk lists has ALREADY passed
    # `allowed_path(full, [root])` one moment before it was added.
    found, stopped = RM._walk(root, clock=clock)
    match = None
    for full, shown in found:
        if _same(shown.replace("\\", "/"), want):
            match = full
            break
    if match is None:
        if stopped:
            return {"ok": False, "available": True,
                    "error": f"Jarvis could not reach that file: the folder is too big to "
                             f"look through in one pass ({stopped}), so nothing was read. "
                             f"Ask about a folder nearer the file."}
        return {"ok": False, "available": True, "error": SKIPPED}
    # The path that passed the check is the path that is opened (the same rule
    # `file_read` records): asked again, and the resolved answer is used.
    again = docs.allowed_path(match, [root])
    if again is None:
        if _credential(want, match):
            return {"ok": False, "available": True, "error": CREDENTIAL}
        return {"ok": False, "available": True, "error": NOT_ALLOWED}
    real = again[0]
    # AFTER the walk and the boundary, BEFORE the file is opened: the file the
    # walk found must not be a credential file even when the boundary let its
    # path through. `real` is the resolved target, so a link with an ordinary
    # name that points at a private key is caught here. Nothing is read first.
    if _credential(want, real):
        return {"ok": False, "available": True, "error": CREDENTIAL}
    name = os.path.basename(root.rstrip("\\/")) or root
    # A binary file is refused before EITHER read: a picture or a program must
    # never come back as mojibake, and a line range would otherwise number a
    # binary's bytes as if they were words.
    try:
        with open(real, "rb") as fh:
            head = fh.read(8192)
    except OSError as exc:
        return {"ok": False, "available": True,
                "error": f"that file could not be read ({type(exc).__name__})",
                "file": want}
    if b"\x00" in head:
        return {"ok": False, "available": True, "error": BINARY, "file": want}

    if first is not None:
        # A LINE RANGE: numbered lines in `content`, and the one footer in
        # `more` (never inside `content` - the model reads that as source).
        try:
            total, known = _count_lines(real)
            part = _slice_lines(real, first, count)
        except OSError as exc:
            return {"ok": False, "available": True,
                    "error": f"that file could not be read ({type(exc).__name__})",
                    "file": want}
        out = {"ok": True, "available": True,
               "content": "\n".join(part["lines"]),
               # `path` is the REAL path this call opened, never the model's
               # own argument - the answer can say where the words came from.
               "path": real, "file": want,
               "bytes": part["bytes"], "cap": MAX_FILE_BYTES,
               "line_cap": MAX_LINES,
               "start_line": first, "end_line": part["end_line"],
               "total_lines": total if known else None,
               "truncated": bool(part["more"]),
               "folder": {"path": root, "name": name},
               "outside_text": True, "what": WHAT}
        if part["more"]:
            out["more"] = _footer(first, part["end_line"], total, known,
                                  part["stopped_bytes"], part["cut_one"])
        return out

    try:
        read = _read_bytes(real)
    except OSError as exc:
        return {"ok": False, "available": True,
                "error": f"that file could not be read ({type(exc).__name__})",
                "file": want}
    raw = read["raw"]
    content = raw.decode("utf-8", "replace")
    out = {"ok": True, "available": True,
           # `path` is the REAL path this call opened, never the model's own
           # argument - the answer can say where the words came from.
           "content": content, "path": real,
           "file": want, "bytes": len(raw), "cap": MAX_FILE_BYTES,
           "truncated": bool(read["truncated"]),
           "folder": {"path": root, "name": name},
           "outside_text": True, "what": WHAT}
    if read["truncated"]:
        # The whole-file read was cut at the byte cap. Say which line range to
        # ask for next, with the counted total where the file is cheap enough
        # to count - the same footer a range read carries. `complete` counts
        # whole lines only, so the next range starts at the line whose start
        # the cut left half-shown.
        complete = content.count("\n")
        total, known = _count_lines(real)
        if not complete and content:
            # One line longer than the whole-file cap: a range cannot hold it
            # whole either, and the honest sentence is the one-line one.
            out["more"] = TOO_LONG.format(line=1, kib=MAX_FILE_BYTES // 1024)
        else:
            out["more"] = _footer(1, complete or 1, total, known, False, False)
    return out


def read_project(pid, rel, *, store=None, roots=None, clock=None,
                 start_line=None, lines=None) -> dict:
    """Read ONE file inside a registered project's own folder (projects.db).

    Resolved exactly as `jarvis_repomap.map_project` resolves a map: the
    project's folder, then the same boundary. A project's folder must already
    be on "Folders Jarvis may look in" (`jarvis_projects.check_folder`), and it
    is asked again here, so a folder taken off the list stops being readable
    even for a project that still names it. `start_line` and `lines` are the
    same optional line range `read_folder` takes.
    """
    if store is None:
        projects = _projects()
        if projects is None:
            return {"ok": False, "available": False,
                    "error": "Projects are not installed on this backend, so there is no "
                             "project folder to read from."}
        store = projects.get()
    try:
        project = store.get(pid)
    except KeyError:
        return {"ok": False, "available": True, "error": "There is no project with that id."}
    folder = ((project.get("folder") or {}).get("path") or "").strip()
    if not folder:
        return {"ok": False, "available": True,
                "error": "That project has no folder, so there is nothing to read. A coding "
                         "project's folder is chosen on the PC."}
    out = read_folder(folder, rel, roots=roots, clock=clock,
                      start_line=start_line, lines=lines)
    out["project"] = {"id": project.get("id"), "name": project.get("name")}
    return out


# --------------------------------------------------------------------------
#   The model's one call
# --------------------------------------------------------------------------


def run_tool(args: dict, *, roots=None, clock=None) -> dict:
    """The `project_read` tool: `{"path": ..., "file": ...}`, plus the optional
    line range `{"start_line": ..., "lines": ...}`.

    `path` takes EITHER a folder on the owner's list OR a project's id, so the
    tool's schema needs no third field - a project id is a `uuid4().hex`, so 32
    hex characters (the map's own matcher accepts 16 to 64), and a name is only
    taken as an id when it is not an existing folder, which is exactly how
    `my_files`' `map` action tells the two apart, and this follows it rather
    than inventing a second convention. The two range arguments are validated
    in `read_folder`, so every door (a folder or a project id) refuses a bad
    value the same way.
    """
    if not isinstance(args, dict):
        return {"ok": False, "error": NEED_FOLDER}
    target = str(args.get("path") or "").strip()
    rel = str(args.get("file") or "").strip()
    if not target:
        return {"ok": False, "error": NEED_FOLDER}
    if not rel:
        return {"ok": False, "error": NEED_FILE}
    start_line = args.get("start_line")
    lines = args.get("lines")
    pid = ""
    if RM is not None and not os.path.isdir(target) and RM._PROJECT_ID.match(target):
        pid = target
    if pid:
        return read_project(pid, rel, roots=roots, clock=clock,
                            start_line=start_line, lines=lines)
    return read_folder(target, rel, roots=roots, clock=clock,
                       start_line=start_line, lines=lines)


def _reset_for_tests() -> None:
    """Nothing is cached, so there is nothing to reset - kept so a suite that
    resets its siblings can call it without a special case."""
    return None


if __name__ == "__main__":                                  # pragma: no cover
    import json
    import sys
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": NEED_FOLDER}, indent=2))
    else:
        asked = {"path": sys.argv[1],
                 "file": sys.argv[2] if len(sys.argv) > 2 else ""}
        if len(sys.argv) > 3:
            asked["start_line"] = int(sys.argv[3])
        if len(sys.argv) > 4:
            asked["lines"] = int(sys.argv[4])
        print(json.dumps(run_tool(asked), indent=2)[:4000])
