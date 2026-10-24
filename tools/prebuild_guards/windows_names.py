"""Turn a name sent by the phone into a name Windows can really save.

WHY THIS FILE EXISTS

P-Doc lets the owner send a document from the phone into a project. The phone
sends a file name, and that name is written onto this Windows PC's NTFS disk.
Windows has names it does not treat as files at all (``CON``, ``NUL``, ``COM1``
and friends open devices instead), a colon that opens a hidden second stream,
and it quietly removes a trailing dot or space - so the file saved is not the
file named. A name can also carry ``..`` or a slash and point outside the
project folder. A phone is a separate device with its own ideas about names, so
none of this may be taken on trust.

WHAT THIS MODULE DOES

``sanitize_upload_name`` returns a name that is safe to create, or raises
:class:`GuardRefusal` with a sentence the owner can read. It refuses:

* the Windows device names, case-insensitively, with or without an extension;
* any colon (an NTFS alternate data stream, and also how a drive is written);
* a trailing dot or space (Windows would remove it silently);
* ``/`` and ``\\``, and any ``..`` name - the ways a name points outside;
* control characters, including NUL, and invisible formatting characters;
* an empty name, ``.`` and ``.``-only names;
* a percent-encoded path such as ``..%2f..%2fsettings.json``, which another
  layer might decode after this guard;
* any extension not on the document allow-list;
* anything longer than the cap, after shortening the stem and keeping the
  extension (a name is only refused if even that cannot work).

It normalises the name to NFKC first, so a full-width ``：`` or ``／`` becomes
the real character and is refused instead of sneaking past. It then lowercases
the extension so two uploads of the same document sort together.

``safe_join(root, name)`` sanitises the name, joins it to the upload folder,
resolves both sides (links followed) and refuses when the result is not under
the folder. It returns the path but writes nothing; the caller opens it with
exclusive create (``"xb"``) so an existing file is never silently replaced.

WHAT THIS DOES NOT DO

* It does not create the folder and does not write the file.
* It does not decide whether the content is a real PDF or just bytes with a
  ``.pdf`` name; the P-Doc reader still checks the file itself.
* It shortens a too-long stem (keeping the extension) and normalises Unicode
  case; it does not invent a replacement name for a refused one. The owner is
  told why, on the phone, and chooses a different name - silently replacing a
  name the owner picked is how the wrong document gets attached later.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote

#: Windows device names. Case-insensitive, and still a device when an extension
#: follows (``CON.txt`` is the console). ``CONIN$``, ``CONOUT$`` and ``CLOCK$``
#: are the same class of name and are included for the same reason.
RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)})

#: Extensions P-Doc accepts from a phone upload. Everything else is refused:
#: a project document is read by Jarvis, so an executable, script or archive is
#: never a document.
ALLOWED_DOCUMENT_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".xlsx", ".pptx", ".md", ".txt", ".csv"})

#: The longest returned name, extension included. NTFS allows 255 characters in
#: one name; 120 leaves room for the `` (copy 2)`` suffix a later step may add.
MAX_UPLOAD_NAME_CHARS = 120

#: Characters Windows cannot put in a file name. A colon is handled separately
#: because its danger (a hidden alternate stream) deserves its own sentence.
_WINDOWS_BAD_CHARS = frozenset('<>"|?*')

_DRIVE = re.compile(r"^[A-Za-z]:")


class GuardRefusal(Exception):
    """A plain-English reason this upload name is refused.

    ``str(exc)`` says what is wrong and what the owner can do. Nothing has been
    saved or changed when it is raised.
    """


def _refuse(why: str) -> None:
    raise GuardRefusal(why)


def _has_hidden_character(name: str) -> bool:
    """True for control/format/surrogate characters, which a person cannot see."""
    for ch in name:
        category = unicodedata.category(ch)
        if category in ("Cc", "Cf", "Cs") or ch in ("\u2028", "\u2029"):
            return True
    return False


def _decoded_path_problem(name: str) -> str:
    """Refuse a name that is an encoded path (``..%2f`` and friends).

    The browser and the multipart layer normally decode the name before it gets
    here, but a guard that depends on which layer did that is a guard that can
    be skipped. Decoding up to three times catches double encoding too.
    """
    decoded = name
    for _ in range(3):
        nxt = unquote(decoded, errors="replace")
        if nxt == decoded:
            break
        decoded = nxt
    if decoded == name:
        return ""
    if "\x00" in decoded or _has_hidden_character(decoded):
        return "it contains a hidden character that was written in code"
    if "/" in decoded or "\\" in decoded:
        return "it looks like a folder path written in code"
    if any(part == ".." for part in decoded.replace("\\", "/").split("/")):
        return "it looks like a path to the folder above, written in code"
    if _DRIVE.match(decoded):
        return "it looks like a whole disk path written in code"
    return ""


def _device_name_problem(name: str) -> str:
    """Refuse ``CON``/``NUL``/``COM1`` even when an extension follows."""
    stem = name.split(".", 1)[0].rstrip(" .").upper()
    if stem in RESERVED_DEVICE_NAMES:
        return (f"the name {stem!r} is a name Windows keeps for a device, not a "
                f"file, so saving it can freeze the PC")
    return ""


def sanitize_upload_name(raw_name: str, *,
                         max_chars: int = MAX_UPLOAD_NAME_CHARS,
                         allowed_extensions: frozenset = ALLOWED_DOCUMENT_EXTENSIONS
                         ) -> str:
    """Return a safe file name for a phone upload, or raise GuardRefusal.

    ``raw_name`` is exactly what the phone sent. The returned name has no path,
    no device name, no colon, no trailing dot or space, and ends in one of
    ``allowed_extensions``. It is at most ``max_chars`` characters.
    """
    if not isinstance(raw_name, str) or not raw_name:
        _refuse("The upload has no file name. Please choose the file again.")
    if raw_name != raw_name.strip():
        _refuse("The file name starts or ends with a space. Windows would remove "
                "that space, so the saved name would be different. Please rename "
                "the file and try again.")
    name = unicodedata.normalize("NFKC", raw_name)
    if not name:
        _refuse("The upload has no file name. Please choose the file again.")
    if name != name.strip():
        _refuse("The file name starts or ends with a space. Windows would remove "
                "that space, so the saved name would be different. Please rename "
                "the file and try again.")
    if name in (".", "..") or set(name) == {"."}:
        _refuse(f"The file name {name!r} means a folder, not a file, so it is "
                f"refused. Please choose the file again.")
    if "\x00" in name or _has_hidden_character(name):
        _refuse("The file name contains a character a person cannot see (a "
                "control or invisible code). It is refused because it can hide "
                "the real name. Please rename the file and try again.")
    if ":" in name:
        _refuse("The file name contains a colon (:). On Windows the part after "
                "a colon is a hidden second file joined to the same name, so it "
                "is refused. Please rename the file without a colon.")
    if "/" in name or "\\" in name:
        _refuse("The file name contains a folder separator (/ or \\). That is "
                "how a name can point outside the project's upload folder, so it "
                "is refused. Please choose the file again with a plain name.")
    encoded = _decoded_path_problem(name)
    if encoded:
        _refuse(f"The file name is refused: {encoded}. That could point outside "
                f"the project's upload folder. Please rename the file and try again.")
    bad = sorted({ch for ch in name if ch in _WINDOWS_BAD_CHARS})
    if bad:
        shown = " ".join(bad)
        _refuse(f"The file name contains a character Windows cannot use in a "
                f"name ({shown}). Please rename the file and try again.")
    if name.endswith(".") or name.endswith(" "):
        _refuse("The file name ends with a dot or a space. Windows quietly "
                "removes those, so the saved name would not be the name you "
                "chose. Please rename the file and try again.")
    device = _device_name_problem(name)
    if device:
        _refuse(f"The file name is refused: {device}. Please rename the file "
                f"and try again.")
    ext = os.path.splitext(name)[1].lower()
    if ext not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        shown = ext if ext else "(no extension)"
        _refuse(f"Jarvis can only keep these kinds of file from a project "
                f"upload: {allowed}. This name ends in {shown}, which is not one "
                f"of them. Please choose a document and try again.")
    stem = name[:-len(ext)].rstrip(" .")
    if not stem:
        _refuse("The file name has no name before its extension, so it is "
                "refused. Please rename the file and try again.")
    name = stem + ext
    if len(name) > max_chars:
        keep = max_chars - len(ext)
        if keep < 1:
            _refuse(f"The file's ending ({ext}) is longer than the {max_chars} "
                    f"characters a saved name may use. Please rename the file "
                    f"and try again.")
        stem = stem[:keep].rstrip(" .")
        if not stem:
            _refuse("The file name is too long and nothing is left once it is "
                    "shortened. Please rename the file and try again.")
        name = stem + ext
        device = _device_name_problem(name)
        if device:
            _refuse(f"The file name is refused: {device}. Please rename the "
                    f"file and try again.")
    return name


def safe_join(root, raw_name: str) -> Path:
    """Return ``root`` joined with a safe ``raw_name``, proved to stay inside.

    Raises :class:`GuardRefusal` when the name is refused, when the upload
    folder is not there, or when the joined path resolves outside the folder
    (a link or shortcut in the way is followed, so it is caught). Writes
    nothing.
    """
    name = sanitize_upload_name(raw_name)
    try:
        root_path = Path(os.path.expanduser(str(root))).resolve()
    except (OSError, ValueError):
        _refuse("The project's upload folder cannot be found, so nothing was saved.")
    if not root_path.is_dir():
        _refuse("The project's upload folder is not there, so nothing was saved. "
                "Open the project on the PC once, then try the upload again.")
    try:
        target = (root_path / name).resolve()
    except (OSError, ValueError):
        _refuse("That file name cannot be turned into a place on this PC, so "
                "nothing was saved. Please rename the file and try again.")
    if not target.is_relative_to(root_path):
        _refuse("That file would be saved outside the project's upload folder, "
                "so it is refused. Nothing was saved.")
    return target


__all__ = [
    "ALLOWED_DOCUMENT_EXTENSIONS",
    "GuardRefusal",
    "MAX_UPLOAD_NAME_CHARS",
    "RESERVED_DEVICE_NAMES",
    "safe_join",
    "sanitize_upload_name",
]
