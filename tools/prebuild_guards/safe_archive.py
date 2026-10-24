"""Read one XML part out of an Office or EPUB zip without being blown up.

WHY THIS FILE EXISTS

A Word, Excel or PowerPoint file (`.docx`, `.xlsx`, `.pptx`) and an EPUB book
(`.epub`) are zip files. The text lives in XML inside them, such as
``word/document.xml``. A small zip can claim - or really contain - a part that
unpacks to gigabytes, and a small XML document can declare entities that expand
to gigabytes. Either one can use up all the PC's memory before a parser returns
a single word. This module is the one door P-Doc and P-Pub should use to read
such a part: it checks the archive, reads a bounded number of bytes, refuses
XML tricks, and only then lets the standard parser see anything.

WHAT THE ZIP HEADER DOES AND DOES NOT TELL YOU

Every member's central-directory record carries a ``file_size`` (how big the
part claims to be once unpacked) and a ``compress_size``. Those are the
archive's own claims, written by whoever made the file. A crafted archive can
write any number there. So this module uses the declared sizes only in two
directions:

* to refuse EARLY when they already look impossible (too many members, a
  declared total over the cap, a claimed compression ratio over the cap), and
* never to allow anything. The part is then read with
  ``fp.read(MAX_XML_MEMBER_BYTES + 1)`` and the number of bytes actually
  returned is what decides. Reading one byte past the cap is what proves the
  cap was crossed without ever holding the whole thing.

WHAT ``xml.etree.ElementTree`` DOES AND DOES NOT PROTECT AGAINST

ElementTree is the standard library's XML parser. It is not a security
sandbox:

* it EXPANDS internal entities declared in a DOCTYPE, so a few hundred bytes
  of ``<!ENTITY ...>`` can become megabytes ("billion laughs" / XML bomb);
* it does not give the caller a size or nesting budget before parsing;
* entity handling is exactly the area where builds and versions differ (what
  one version resolves, another refuses), so this module does not try to
  characterise it: it refuses every DOCTYPE/ENTITY declaration instead;
* a parse error is raised only after the parser has read the document, which
  is already too late for an entity expansion.

What it does do: it refuses malformed XML, it does not run scripts, and with
this module's checks it only ever receives at most
``MAX_XML_MEMBER_BYTES`` bytes that contain no DOCTYPE or ENTITY.

WHY THE DOCTYPE CHECK MUST COME BEFORE THE PARSER

By the time ``ET.fromstring(raw)`` raises, expat has already expanded the
entities it met. Catching the exception then would be catching the explosion,
not preventing it. So ``_declares_doctype`` runs first and refuses the bytes
outright. A plain byte search is not enough: XML sent as UTF-16 spells
``<!DOCTYPE`` with a zero byte after every letter, so the search finds nothing
while the parser reads it normally. This module therefore also lets expat read
the bytes with handlers that stop the moment a DOCTYPE or ENTITY declaration
begins. (The same lesson is already written down in
``backend/jarvis_news.py``'s ``_declares_doctype``, measured 2026-09-27.)

The standard ``defusedxml`` package would do some of this, but it is not
available here and this project adds no dependency for it.

WHAT THIS DOES NOT DO

* It does not unpack the archive to disk. It returns one parsed XML element.
* It is not a general XML sandbox: after this guard, treat the element as
  untrusted data, never resolve external references yourself and never enable
  XInclude.
* It does not validate that the XML is the schema you expected. The caller
  still checks which elements it reads, caps the text it keeps and treats the
  words as data, not instructions.
* It does not stop a caller from opening the zip a second time with
  ``zf.read(name)`` and bypassing it. The one entry point is the rule.

HOW TO USE IT

    import zipfile
    from safe_archive import GuardRefusal, read_xml_member

    try:
        with zipfile.ZipFile(path) as zf:
            root = read_xml_member(zf, "word/document.xml")
    except (zipfile.BadZipFile, OSError) as exc:
        # Say, in plain words, that the file is not a readable document.
        ...
    except GuardRefusal as exc:
        # ``str(exc)`` is already a sentence for the owner.
        ...
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
import zlib

#: The most members an Office document or an EPUB book may hold. A real book is
#: a few hundred parts; 2,000 is generous and still stops an archive made of
#: thousands of tiny entries (which is how one kind of bomb gets past a size
#: check).
MAX_ARCHIVE_MEMBERS = 2_000

#: The most bytes read from one XML member. The read asks for one more than
#: this, and that extra byte is the proof the limit was crossed.
MAX_XML_MEMBER_BYTES = 25 * 1024 * 1024

#: The most the members may CLAIM to unpack to in total (100 MiB), matching
#: ``jarvis_documents.DOC_UNCOMPRESSED_MAX``. This is a cheap first refusal; the
#: bounded reads are the real protection.
MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024

#: The most the archive may claim to shrink its contents by. Office XML repeats
#: its tags, so it compresses well - but not by a factor of a thousand. 100 is
#: the same ceiling ``jarvis_notion_obsidian.MAX_ZIP_RATIO`` uses.
MAX_COMPRESSION_RATIO = 100

#: A member name longer than this is not a real Office or EPUB part.
MAX_MEMBER_NAME_CHARS = 512


class GuardRefusal(Exception):
    """A plain-English reason this archive or part will not be read.

    ``str(exc)`` is written for a beginner: it says what was refused and what
    to do about it. Nothing has been parsed or unpacked when it is raised.
    """


def _refuse(why: str) -> None:
    raise GuardRefusal(why)


def member_name_problem(name: str) -> str:
    """'' when ``name`` stays inside the archive, else a short reason.

    Refused: empty names, absolute names, drive-qualified names, backslashes,
    a name longer than any real part, and any ``..`` path segment. This is the
    same rule as ``jarvis_documents.zip_path_problem``; it is restated here
    because this module is a drop-in and must not depend on a backend module
    being importable from ``tools/``.
    """
    if not isinstance(name, str) or not name:
        return "a part has no name"
    if len(name) > MAX_MEMBER_NAME_CHARS:
        return f"a part name is longer than {MAX_MEMBER_NAME_CHARS} characters"
    if "\x00" in name:
        return "a part name contains a hidden zero byte"
    if "\\" in name:
        return (f"a part is named {name!r}, and a backslash in a zip name can "
                f"point outside it")
    flat = name.replace("\\", "/")
    if flat.startswith("/"):
        return f"a part is named {name!r}, which points at the top of the disk"
    if re.match(r"^[A-Za-z]:", flat):
        return f"a part is named {name!r}, which starts with a drive letter"
    if any(part == ".." for part in flat.split("/")):
        return f"a part is named {name!r}, which points outside the archive"
    return ""


def _infolist(zf) -> list:
    try:
        infos = zf.infolist()
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        _refuse(f"Jarvis will not open this file: its list of parts cannot be read "
                f"({type(exc).__name__}), so it is not a valid zip. Nothing was opened.")
    if not isinstance(infos, list):
        infos = list(infos)
    return infos


def _size_words(limit: int) -> str:
    """``25 MB`` for a round number of MiB, else ``512 bytes``."""
    if limit and limit % (1024 * 1024) == 0:
        return f"{limit // (1024 * 1024)} MB"
    return f"{limit:,} bytes"


def _archive_problem(zf, *, max_members: int, max_total_bytes: int,
                     max_ratio: int) -> None:
    """Refuse an archive from its own directory before any part is opened."""
    infos = _infolist(zf)
    if len(infos) > max_members:
        _refuse(f"Jarvis will not open this file: it is a zip holding more than "
                f"{max_members:,} separate parts, which is more than a normal document "
                f"or book has. Nothing was opened.")
    total = 0
    packed = 0
    for info in infos:
        why = member_name_problem(str(getattr(info, "filename", "") or ""))
        if why:
            _refuse(f"Jarvis will not open this file: {why}. Nothing was opened.")
        if _is_dir(info):
            continue
        size = max(0, int(getattr(info, "file_size", 0) or 0))
        total += size
        packed += max(0, int(getattr(info, "compress_size", 0) or 0))
        if max_total_bytes and total > max_total_bytes:
            _refuse(f"Jarvis will not open this file: its parts say they would unpack "
                    f"to more than {_size_words(max_total_bytes)}, which is "
                    f"what a zip bomb looks like. Nothing was opened.")
    if total > 0 and packed == 0:
        _refuse("Jarvis will not open this file: it says it holds data but no "
                "compressed bytes at all, which a real document never does. "
                "Nothing was opened.")
    if packed > 0 and max_ratio and total / packed > max_ratio:
        _refuse(f"Jarvis will not open this file: it claims to shrink its parts by "
                f"more than {max_ratio} times, which is what a zip bomb looks like. "
                f"Nothing was opened.")


def _is_dir(info) -> bool:
    try:
        return bool(info.is_dir())
    except (AttributeError, ValueError):
        return str(getattr(info, "filename", "") or "").endswith("/")


def _is_encrypted(info) -> bool:
    return bool(int(getattr(info, "flag_bits", 0) or 0) & 0x1)


def _declares_doctype(raw: bytes) -> bool:
    """True when ``raw`` declares a DOCTYPE or an ENTITY, in any encoding.

    The byte search catches the common UTF-8 form cheaply. Expat then reads the
    bytes with handlers that stop the moment either declaration starts, which
    also catches UTF-16 and other encodings the parser understands. A document
    expat cannot read at all returns False here and is left to ElementTree,
    which will refuse it as malformed.
    """
    if re.search(rb"<!DOCTYPE|<!ENTITY", raw, re.IGNORECASE):
        return True

    import xml.parsers.expat

    class _Stop(Exception):
        pass

    def _stop(*_args):
        raise _Stop()

    parser = xml.parsers.expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _stop
    parser.EntityDeclHandler = _stop
    try:
        parser.Parse(raw, True)
    except _Stop:
        return True
    except Exception:
        return False
    return False


def read_xml_member(zf, member_name: str, *,
                    max_member_bytes: int = MAX_XML_MEMBER_BYTES,
                    max_total_bytes: int = MAX_TOTAL_UNCOMPRESSED_BYTES,
                    max_members: int = MAX_ARCHIVE_MEMBERS,
                    max_ratio: int = MAX_COMPRESSION_RATIO) -> ET.Element:
    """Return the parsed XML of ``member_name`` inside an open ``ZipFile``.

    Raises :class:`GuardRefusal` with a sentence the owner can read when the
    archive or the part is refused. Never reads more than ``max_member_bytes``
    plus one byte, never trusts ``ZipInfo.file_size`` to decide that, and never
    hands a DOCTYPE or ENTITY to the parser.

    Callers open the file themselves so they can catch ``zipfile.BadZipFile``
    and say the file is not a readable document. They should call this BEFORE
    any other read of the same member.
    """
    why = member_name_problem(member_name)
    if why:
        _refuse(f"Jarvis will not open this file: {why}. Nothing was opened.")
    _archive_problem(zf, max_members=max_members, max_total_bytes=max_total_bytes,
                     max_ratio=max_ratio)
    infos = _infolist(zf)
    info = next((i for i in infos
                 if str(getattr(i, "filename", "") or "") == member_name), None)
    if info is None:
        _refuse(f"Jarvis will not open this file: it has no part called "
                f"{member_name!r}, so there is no text to read.")
    if _is_dir(info):
        _refuse(f"Jarvis will not open this file: {member_name!r} is a folder in "
                f"the archive, not a document part.")
    declared = max(0, int(getattr(info, "file_size", 0) or 0))
    if declared > max_member_bytes:
        # A safe use of the header: it can only make us refuse EARLIER. If it
        # lies low, the bounded read below is what decides.
        _refuse(f"Jarvis will not open this file: the part {member_name!r} says it "
                f"is bigger than {_size_words(max_member_bytes)} once unpacked, "
                f"which is more than one document part should be. Nothing was opened.")
    if _is_encrypted(info):
        _refuse("Jarvis will not open this file: one part is locked with a "
                "password, and Jarvis does not ask for or keep document passwords. "
                "Nothing was opened.")
    try:
        with zf.open(info) as fp:
            raw = fp.read(max_member_bytes + 1)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError,
            zlib.error, OSError, ValueError) as exc:
        _refuse(f"Jarvis will not open this file: the part {member_name!r} could "
                f"not be read ({_reason(exc)}), so the file may be damaged or not "
                f"a real Office or EPUB file. Nothing was opened.")
    if not isinstance(raw, (bytes, bytearray)):
        _refuse(f"Jarvis will not open this file: the part {member_name!r} did not "
                f"come back as data. Nothing was opened.")
    if len(raw) > max_member_bytes:
        _refuse(f"Jarvis will not open this file: the part {member_name!r} is bigger "
                f"than {_size_words(max_member_bytes)} once unpacked, "
                f"which is more than one document part should be. Nothing was opened.")
    if _declares_doctype(raw):
        _refuse("Jarvis will not open this file: it carries instructions for "
                "defining its own text shortcuts (a DOCTYPE or ENTITY). A real "
                "document never needs those, and they can make one small file "
                "expand until the PC runs out of memory. Nothing was opened.")
    try:
        return ET.fromstring(bytes(raw))
    except (ET.ParseError, ValueError):
        _refuse(f"Jarvis will not open this file: the part {member_name!r} is not "
                f"readable as a document part, so the document may be damaged or "
                f"not a real Office or EPUB file. Nothing was opened.")


def _reason(exc: Exception) -> str:
    """A plain-ish word for why the zip reader failed, never a wall of jargon."""
    if isinstance(exc, zipfile.BadZipFile):
        return "the zip is damaged"
    if isinstance(exc, RuntimeError):
        return "the part is locked"
    if isinstance(exc, NotImplementedError):
        return "the part uses a kind of compression this PC cannot open"
    return "the zip reader stopped"


__all__ = [
    "GuardRefusal",
    "MAX_ARCHIVE_MEMBERS",
    "MAX_COMPRESSION_RATIO",
    "MAX_TOTAL_UNCOMPRESSED_BYTES",
    "MAX_XML_MEMBER_BYTES",
    "member_name_problem",
    "read_xml_member",
]
