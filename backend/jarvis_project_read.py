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
    (32 hex characters, which is never a folder that exists - the same one
    field `my_files`' `map` action already uses for the same reason).
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

THE HONEST LIMITS
  * The per-file cap is `jarvis_repomap.MAX_FILE_BYTES` (512 KB), reused so the
    two readers cut at the same place. A file over it is read to the cap and
    the answer says `truncated: true` - it is not refused, and the model is
    told, so a cut file is never presented as the whole file.
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

#: What the model is told this tool gave it, in one line.
WHAT = ("the words of one file inside a folder you listed, read only - nothing was changed, "
        "moved or sent anywhere")


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


def read_folder(folder, rel, *, roots=None, clock=None) -> dict:
    """Read ONE file inside `folder`, which must be on the owner's list.

    `ok: False` and one plain sentence for every refusal; nothing is raised for
    anything a caller can cause. See the module docstring for the shape.
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
        return {"ok": False, "available": True, "error": NOT_ALLOWED}
    real = again[0]
    try:
        read = _read_bytes(real)
    except OSError as exc:
        return {"ok": False, "available": True,
                "error": f"that file could not be read ({type(exc).__name__})",
                "file": want}
    raw = read["raw"]
    if b"\x00" in raw[:8192]:
        return {"ok": False, "available": True, "error": BINARY, "file": want}
    name = os.path.basename(root.rstrip("\\/")) or root
    return {"ok": True, "available": True,
            # `path` is the REAL path this call opened, never the model's own
            # argument - the answer can say where the words came from.
            "content": raw.decode("utf-8", "replace"), "path": real,
            "file": want, "bytes": len(raw), "cap": MAX_FILE_BYTES,
            "truncated": bool(read["truncated"]),
            "folder": {"path": root, "name": name},
            "outside_text": True, "what": WHAT}


def read_project(pid, rel, *, store=None, roots=None, clock=None) -> dict:
    """Read ONE file inside a registered project's own folder (projects.db).

    Resolved exactly as `jarvis_repomap.map_project` resolves a map: the
    project's folder, then the same boundary. A project's folder must already
    be on "Folders Jarvis may look in" (`jarvis_projects.check_folder`), and it
    is asked again here, so a folder taken off the list stops being readable
    even for a project that still names it.
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
    out = read_folder(folder, rel, roots=roots, clock=clock)
    out["project"] = {"id": project.get("id"), "name": project.get("name")}
    return out


# --------------------------------------------------------------------------
#   The model's one call
# --------------------------------------------------------------------------


def run_tool(args: dict, *, roots=None, clock=None) -> dict:
    """The `project_read` tool: `{"path": ..., "file": ...}`.

    `path` takes EITHER a folder on the owner's list OR a project's id, so the
    tool's schema needs no third field - a project id is 32 hex characters and
    is never a folder that exists, which is exactly how `my_files`' `map`
    action tells the two apart, and this follows it rather than inventing a
    second convention.
    """
    if not isinstance(args, dict):
        return {"ok": False, "error": NEED_FOLDER}
    target = str(args.get("path") or "").strip()
    rel = str(args.get("file") or "").strip()
    if not target:
        return {"ok": False, "error": NEED_FOLDER}
    if not rel:
        return {"ok": False, "error": NEED_FILE}
    pid = ""
    if RM is not None and not os.path.isdir(target) and RM._PROJECT_ID.match(target):
        pid = target
    if pid:
        return read_project(pid, rel, roots=roots, clock=clock)
    return read_folder(target, rel, roots=roots, clock=clock)


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
        res = run_tool({"path": sys.argv[1],
                        "file": sys.argv[2] if len(sys.argv) > 2 else ""})
        print(json.dumps(res, indent=2)[:4000])
