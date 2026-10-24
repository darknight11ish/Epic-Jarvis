"""Walk a project folder without following shortcuts out of it.

WHY THIS FILE EXISTS

P-GH-1 stages the files of a coding project and can send them to GitHub. A
Windows folder can hold a shortcut to another place on the PC: a symbolic link
or a directory junction (a link that looks like an ordinary folder). If the
walker follows one, a project that looks small can stage ``~/.ssh`` or Jarvis's
own settings folder, and those files can end up in a repository. Windows also
marks one attribute, ``FILE_ATTRIBUTE_REPARSE_POINT`` (0x400), on both kinds of
shortcut, and not every Python version reports a junction as a symlink, so both
signs are checked.

WHAT THIS MODULE DOES

``walk_project_files(root)`` walks a folder top-down and returns every ordinary
file's path relative to the root, using ``/`` on every platform. It refuses -
with :class:`GuardRefusal` and a sentence for the owner - the moment it meets:

* a link or reparse point as the project folder itself, as any folder it would
  enter, or as any file it would stage;
* a path whose resolved form (links followed) is outside the project folder;
* something that is neither an ordinary file nor a folder (a device, pipe or
  socket);
* a folder that cannot be read, changed while it was being read, nested deeper
  than the cap, or a project holding more than the file cap.

Every folder on the way down is checked with ``os.lstat`` before it is entered,
so a parent cannot be swapped for a shortcut and quietly followed. A shortcut is
refused rather than skipped: a project with one in it is not the project the
owner thinks it is, and silently staging the rest would hide that.

WHAT THIS DOES NOT DO

* It does not read file contents and does not write anything.
* It does not decide which files are worth staging; P-GH-1's own list does that
  after this walk.
* It is not a sandbox. A program already on the PC can still move a folder after
  the walk and before a read; the caller must open the file it staged and check
  it is the same file, the way ``jarvis_file_guardian`` does for writes.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

#: ``winnt.h``'s name for the attribute Windows puts on both symlinks and
#: junctions. A junction is not always ``os.path.islink`` on older Pythons.
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

#: Caps so a hostile or vast folder cannot run forever. A real project is far
#: below both.
MAX_WALK_FILES = 100_000
MAX_WALK_SECONDS = 30.0
MAX_WALK_DEPTH = 64


class GuardRefusal(Exception):
    """A plain-English reason this project folder will not be walked.

    ``str(exc)`` says what was found and that nothing was read. The walk stops
    at the first refusal; it never returns a partial list.
    """


def _refuse(why: str) -> None:
    raise GuardRefusal(why)


def _link_like(info) -> bool:
    """True for a symlink or a Windows reparse point (junction), by either sign."""
    mode = int(getattr(info, "st_mode", 0) or 0)
    if stat.S_ISLNK(mode):
        return True
    attrs = int(getattr(info, "st_file_attributes", 0) or 0)
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def _shown(rel_parts) -> str:
    return "/".join(rel_parts) if rel_parts else "the project folder"


def _shortcut_refusal(rel_parts) -> None:
    if rel_parts:
        _refuse(f"Jarvis will not read this project folder: it contains a "
                f"shortcut (a link to another place on the PC) at "
                f"{_shown(rel_parts)!r}. A shortcut like that can make Jarvis "
                f"read private files outside the project, so nothing was read.")
    _refuse("Jarvis will not read this project folder: the folder itself is a "
            "shortcut (a link to another place on the PC). A shortcut like that "
            "can make Jarvis read private files outside the project, so nothing "
            "was read.")


def _seconds_words(value: float) -> str:
    return f"{value:g} second" if value == 1 else f"{value:g} seconds"


def walk_project_files(root, *, max_files: int = MAX_WALK_FILES,
                       max_seconds: float = MAX_WALK_SECONDS,
                       clock=time.monotonic) -> list[str]:
    """Return the ordinary files under ``root`` as sorted relative paths.

    Raises :class:`GuardRefusal` (and returns nothing) when a shortcut, a path
    that resolves outside the root, a special file, an unreadable folder, a
    folder that changes mid-walk, or a cap is met. ``clock`` is injectable so a
    test can prove the time cap without waiting.
    """
    raw_root = Path(os.path.expanduser(str(root)))
    try:
        root_info = os.lstat(raw_root)
    except OSError:
        _refuse("Jarvis will not read this project folder: it is not there, or "
                "Windows refused access to it. Nothing was read.")
    if _link_like(root_info):
        _shortcut_refusal([])
    try:
        root_path = raw_root.resolve()
    except (OSError, ValueError):
        _refuse("Jarvis will not read this project folder: its real place on "
                "the PC cannot be found. Nothing was read.")
    if not root_path.is_dir():
        _refuse("Jarvis will not read this project folder: it is not a folder. "
                "Nothing was read.")
    started = clock()
    out: list[str] = []

    def over_time() -> None:
        if max_seconds and clock() - started > max_seconds:
            _refuse(f"Jarvis will not read this project folder: looking through "
                    f"it took longer than {_seconds_words(max_seconds)}, which is "
                    f"more than a project folder should. Nothing was read.")

    def visit(folder: Path, rel_parts: list, depth: int) -> None:
        if depth > MAX_WALK_DEPTH:
            _refuse(f"Jarvis will not read this project folder: its folders are "
                    f"nested more than {MAX_WALK_DEPTH} levels deep. Nothing was read.")
        over_time()
        try:
            info = os.lstat(folder)
        except OSError:
            _refuse(f"Jarvis will not read this project folder: "
                    f"{_shown(rel_parts)!r} changed while Jarvis was looking at "
                    f"it. Nothing was read.")
        if _link_like(info):
            _shortcut_refusal(rel_parts)
        try:
            resolved = folder.resolve()
        except (OSError, ValueError):
            _refuse(f"Jarvis will not read this project folder: the real place "
                    f"of {_shown(rel_parts)!r} cannot be found. Nothing was read.")
        if not resolved.is_relative_to(root_path):
            _refuse(f"Jarvis will not read this project folder: "
                    f"{_shown(rel_parts)!r} really lives outside the project. "
                    f"Nothing was read.")
        try:
            with os.scandir(folder) as listing:
                entries = sorted(listing, key=lambda e: e.name)
        except OSError:
            _refuse(f"Jarvis will not read this project folder: Windows refused "
                    f"access to {_shown(rel_parts)!r}. Nothing was read.")
        for entry in entries:
            over_time()
            child = Path(entry.path)
            child_rel = rel_parts + [entry.name]
            try:
                child_info = os.lstat(child)
            except OSError:
                _refuse(f"Jarvis will not read this project folder: "
                        f"{_shown(child_rel)!r} changed while Jarvis was looking "
                        f"at it. Nothing was read.")
            if _link_like(child_info):
                _shortcut_refusal(child_rel)
            if stat.S_ISDIR(child_info.st_mode):
                visit(child, child_rel, depth + 1)
                continue
            if not stat.S_ISREG(child_info.st_mode):
                _refuse(f"Jarvis will not read this project folder: "
                        f"{_shown(child_rel)!r} is not an ordinary file or folder "
                        f"(it may be a device or a pipe). Nothing was read.")
            try:
                real = child.resolve()
            except (OSError, ValueError):
                _refuse(f"Jarvis will not read this project folder: the real "
                        f"place of {_shown(child_rel)!r} cannot be found. Nothing "
                        f"was read.")
            if not real.is_relative_to(root_path):
                _refuse(f"Jarvis will not read this project folder: "
                        f"{_shown(child_rel)!r} really lives outside the project. "
                        f"Nothing was read.")
            out.append("/".join(child_rel))
            if max_files and len(out) > max_files:
                _refuse(f"Jarvis will not read this project folder: it holds more "
                        f"than {max_files:,} files, which is more than one project "
                        f"should have. Nothing was read.")

    visit(root_path, [], 0)
    return sorted(out)


__all__ = [
    "FILE_ATTRIBUTE_REPARSE_POINT",
    "GuardRefusal",
    "MAX_WALK_FILES",
    "MAX_WALK_DEPTH",
    "MAX_WALK_SECONDS",
    "walk_project_files",
]
