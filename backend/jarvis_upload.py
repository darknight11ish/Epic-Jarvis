"""jarvis_upload.py - a file from your phone, put in a folder Jarvis looks in.

WHAT THIS IS FOR (the owner's ask, 2026-11-05)

"I would like to be able to upload any documents through the jarvis app and
have it be fully processed as if I was uploading it to the jarvis desktop."

Until this module the phone could only READ: a file attached to one chat
question was read in that turn and dropped (`jarvis_attached_file.py`, which
says so itself). Every door that WRITES was the PC's, with a refusal saying so
(`/api/folders/add`, `/api/folders/import`, `/api/notion/import`). So the
missing half was never the processing - folders, the index, the converter, the
Notion import and its Undo all exist and are tested - it was the PIPES: a way
for a paired phone to put a byte on this PC's disk, and a way to hand that byte
to the machinery that already runs for a file the owner dropped there himself.

THIS MODULE IS THE PIPE, AND NOTHING ELSE. It writes ONE file into ONE folder
the owner already listed, and then gets out of the way: `jarvis_documents`
finds it by name on the next look (`_walk` reads the disk), indexes it on the
next search if it is a note or text file (`TextIndex.reconcile`), and reads it
on request through its own converter. Nothing here indexes, converts or
summarises anything, and nothing here is a second reader.

THE DECISION THIS REVERSES, SAID OUT LOUD. On 2026-10-29 the record said, in
as many words: "Deliberately not built, now or later: an upload endpoint, a
resumable or chunked transfer ..." (docs/DECISIONS.md:4943). The owner's ask of
2026-11-05 reverses the upload endpoint and the chunked transfer, and NOT the
rest of that sentence (a document preview, a second image path and an "attach
anything" share target stay not built). The reversal is recorded in
decisions.d/2026-11-05-phone-upload.md; this paragraph is the code's copy of it.
On 2026-11-13 the door gained PHOTOS as plain file copies. That is not the
"second image path" the same sentence refused: no picture decoder, vision
model, OCR or secret cleaner runs here, and no model is shown the bytes. It is
a file landing in a folder, exactly as a document does; the record of THAT
change is decisions.d/2026-11-13-photo-from-phone.md, and the chat picture
path (`jarvis_chat_picture.py` / `ChatPicture`) is untouched.

THE ROUTES (docs/JARVIS-API.md section 196)

    POST /api/upload/begin    {"name", "size", "mime"?, "into", "purpose"?,
                               "sha256"?}
    POST /api/upload/chunk    {"id", "index", "data"}       (base64, 1 MiB raw)
    POST /api/upload/finish   {"id", "sha256"?}

WHY CHUNKS AT ALL. The server's request-body cap is 4 MiB (MAX_BODY, from
token-store.patch), and a Notion export is orders of magnitude larger than
that, so one POST cannot carry the file. 1 MiB of raw bytes is about 1.37 MB of
base64 and JSON - a third of the cap - and it is the same number
`import_history.py` already reads in, so it is not a new number in this
project. A chunk larger than that is refused with a sentence rather than
half-read.

WHERE THE BYTES WAIT, AND WHY IT MATTERS

  * a document: `<the chosen listed folder>\\.jarvis-upload-<id>\\<name>.part`,
    exactly the shape `jarvis_documents.import_notion` already uses for its own
    staging folder (`.jarvis-import-<uuid>`). `jarvis_documents.allowed_path`
    refuses any path with a part starting with ".", so a half-written file is
    unreachable by find, read, search and the index even before `finish` - the
    staging is invisible BY CONSTRUCTION rather than by a list somebody must
    keep up to date.
  * a Notion export: `%LOCALAPPDATA%\\Jarvis\\uploads\\<id>\\<name>`. It is
    deliberately NOT under `~/.openjarvis`: that folder is in
    `jarvis_agent._PROTECTED_DIRS`, so `jarvis_documents.protected()` would
    refuse the file and `jarvis_notion_obsidian.plan_import` would refuse its
    own receiving area. `JARVIS_UPLOADS_DIR` (an absolute path) moves it for a
    suite; nothing else does.

NOTHING LANDS BEFORE A PERSON SAYS YES. For `purpose: "document"` the ONE card
is raised at `begin`, before a byte is written, and every `chunk` while it is
unanswered answers 409 with `waiting: true`. A denied or timed-out card writes
nothing and deletes anything staged. That is rule 4 taken at its word, and the
action is `receive_uploaded_document` - tier "ask", and it is in BOTH
`jarvis_asks_first.HARD_LIMITS` and `MUST_ASK`, so no app and no settings line
can turn the card into a standing yes. A "yes to any file from any device" is
exactly the bulk approval that rule forbids.

For `purpose: "notion"` there is NO card here: the zip is only staged, and the
card that matters is the existing `import_notion_export` one, raised by
`jarvis_notion_obsidian.request_import` with the real note, attachment and
database counts on it (backend/JARVIS-API.md section 152). One card per import,
and the vault is never touched before it.

THE EIGHT DOCUMENT KINDS, PLUS EIGHT PHOTO KINDS ON THE SAME DOOR.
`.pdf .docx .xlsx .pptx .md .markdown .txt .csv` are exactly
`jarvis_attached_file.KINDS` and exactly the phone's document picker. A Notion
`.zip` is the second purpose's business. No audio or video (a different index),
and never an executable or a script: nothing uploaded is ever run. Since
2026-11-13 the same door also carries a PHOTO - `.jpg .jpeg .png .webp .heic
.heif .gif .bmp` - as a PLAIN FILE COPY (the owner's report that Jarvis denied
being able to send a photo to the PC at all). A photo is `PHOTO_EXTENSIONS`
here, never `jarvis_attached_file.IMAGE_KINDS` and never a new entry in its
`KINDS`: that module's list is what the chat attachment READER accepts, and
widening it would let a picture's bytes be read as a document. This module
still never opens a document as text, indexes it or converts it; a photo's
only inspection is a header check (`_photo_problem`) so a renamed program is
not stored as a picture. Nothing on this path shows a model a photo's bytes.

The allowlist is enforced twice - `begin` checks the NAME, `finish` checks the
BYTES - and the byte check is `jarvis_attached_file`'s own magic-byte,
encrypted-PDF and zip-bomb guards for the document kinds, plus the header
check above for a photo, so a `.docx` that is really a renamed archive is
refused rather than handed to a parser.

WHAT `finish` CHECKS BEFORE ANYTHING LANDS
  1. the bytes that really arrived equal the size the phone declared (a
     truncated upload is refused, not saved short);
  2. the sha256 the phone sent, when it sent one, matches the bytes on disk;
  3. the bytes are what the name claims (`%PDF-`, `PK\\x03\\x04` plus the
     right `word/`/`xl/`/`ppt/` member, UTF-8 with no NULs for text);
  4. an encrypted PDF is refused, and a ZIP-based kind or the Notion export is
     judged by `jarvis_documents.zip_bomb_problem` BEFORE any parser sees it.

WHAT IT NEVER DOES

  * It never takes a PATH from the device. The only folder-shaped field is
    `into`, and it is accepted only when it EQUALS one of
    `jarvis_documents.folders()` - the same test `import_notion` makes - so a
    phone cannot create a grant; it can only use one the owner already gave on
    the PC, with a card.
  * It never overwrites the owner's file. A name already taken in "From my
    phone" gets a number (`taxes (2).pdf`), the same rule the Notion importer
    uses.
  * It never runs, opens, converts, indexes or sends anything. The one thing it
    does with the bytes is `os.replace` them into place, on the same volume, so
    the move is atomic.
  * It writes no settings file, no log line with a name in it, and no memory
    fact. The audit rows carry counts and outcomes only.
  * It never calls `jarvis_owner_check.from_this_pc`: a phone IS the caller.
    Origin and token are the core's own checks, handed to `install()`.

LIMITS, IN ONE PLACE

    MAX_DOC_BYTES      50 MiB    a document (the number the desktop reader uses)
    MAX_NOTION_BYTES    4 GiB    one Notion export zip, AS THE PHONE SENDS IT
                                 (raw compressed bytes; the owner's 2026-11-05
                                 number was 250 MiB and he raised it to 4 GiB on
                                 2026-11-09 so a phone may send the same export
                                 the PC takes. NOT the unpacked ceiling - that
                                 is the PC's 4 GB check, a DIFFERENT number)
    CHUNK_BYTES         1 MiB    raw bytes per chunk request
    MAX_ACTIVE             3     uploads in flight at once
    STAGING_MAX         4 GiB    everything staged, all uploads together
                                 (raised 2026-11-09 with the phone's cap, so one
                                 full export can be staged at all)
    LIFETIME_MINUTES      30     an id expires, and its staging goes with it

Standard library only. Nothing here opens a socket, starts a program or reads a
file it did not itself stage. No patch: `plugins/ready/upload` calls install().
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

try:
    import jarvis_documents as docs      # folders, the guards, the one refusal list
except Exception:                        # pragma: no cover - shipped beside it
    docs = None  # type: ignore

try:
    import jarvis_attached_file as attached   # the eight kinds and the byte guards
except Exception:                        # pragma: no cover - shipped beside it
    attached = None  # type: ignore

try:
    import jarvis_framework as fw
except Exception:                        # pragma: no cover
    fw = None  # type: ignore


# --------------------------------------------------------------------------
#   What it is called, and the limits it works inside
# --------------------------------------------------------------------------

TITLE = "A document from your phone"
BEGIN_ROUTE = "/api/upload/begin"
CHUNK_ROUTE = "/api/upload/chunk"
FINISH_ROUTE = "/api/upload/finish"
ROUTES = (BEGIN_ROUTE, CHUNK_ROUTE, FINISH_ROUTE)

#: The ONE gate action a document upload is decided under. Tier "ask", and in
#: `jarvis_asks_first.HARD_LIMITS` and `MUST_ASK` - never loosened, by anyone.
CARD_ACTION = "receive_uploaded_document"

#: The folder a phone's file lands in, inside the listed folder the owner
#: picked. It is inside a folder he already granted, so it needs no second
#: grant, and it says where the file came from.
SUB = "From my phone"

#: The picture extensions this door may carry as a PLAIN FILE COPY, and no
#: others. The same eight names the phone's picture router already treats as a
#: picture by name alone (`jarvis-client/.../AttachFile.kt`, PHOTO_KINDS).
#:
#: DELIBERATELY NOT `jarvis_attached_file.IMAGE_KINDS` and never added to its
#: `KINDS`: that module is the chat attachment READER, and its `read()` must
#: keep refusing a picture's bytes as a document (it does, in `WHY_PICTURE`).
#: This list only says what the folder door may STORE; the backend test
#: `test_upload.t_a_photo_lands_as_a_plain_file` proves a landed photo is still
#: refused by both `jarvis_documents.read` and `jarvis_attached_file.read`.
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp")

#: The purpose a `begin` body may carry. "document" is one file into a listed
#: folder; "notion" is one export zip, staged for the Obsidian import.
PURPOSES = ("document", "notion")

MAX_DOC_BYTES = 50 * 1024 * 1024             # jarvis_documents.MAX_DOC_BYTES
#: ONE NOTION EXPORT, BY THE BYTES THE PHONE SENDS - a DIFFERENT limit from the
#: PC's unpacked ceiling (`jarvis_documents.EXPORT_UNCOMPRESSED_MAX`): that one
#: was 250 MiB and became 4 GB on 2026-11-09, and the owner raised THIS one from
#: 250 MiB to 4 GiB on 2026-11-09 too, deliberately, so a phone can send the
#: same export the PC takes. It is how much crosses his private network in one
#: go, so it is the owner's call, not a side effect of the unpack check - see
#: docs/ARCHITECTURE.md section 8 for the record.
MAX_NOTION_BYTES = 4 * 1024 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024                    # raw bytes; import_history.py's number
MAX_ACTIVE = 3
#: Everything staged, all uploads together. Raised with MAX_NOTION_BYTES on
#: 2026-11-09: a 4 GiB export could not otherwise be staged at all, and the
#: three-in-flight cap still bounds what a stolen token can leave on the disk.
STAGING_MAX = 4 * 1024 * 1024 * 1024
LIFETIME_MINUTES = 30
LIFETIME = LIFETIME_MINUTES * 60

#: A name is the owner's own, so it is kept - but it is a BARE name: no path, no
#: "..", no control character, no leading dot (a hidden file, which every
#: reader refuses anyway), and no Windows reserved name.
NAME_CHARS = 150
_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9]|conin\$|conout\$|clock\$)(\..*)?$",
                       re.I)

#: The staging folder a document is written into, before it lands. The leading
#: dot is the guard: `jarvis_documents.allowed_path` refuses any path part that
#: starts with one, so nothing staged is reachable by find, read or search.
STAGING_PREFIX = ".jarvis-upload-"

#: Moves the Notion staging root for a suite. Absolute, or it is ignored - the
#: same rule `jarvis_plugins.JARVIS_PLUGINS_DIR` keeps, for the same reason.
UPLOADS_ENV = "JARVIS_UPLOADS_DIR"

# --------------------------------------------------------------------------
#   The words both apps show
# --------------------------------------------------------------------------

SPACE_SAID = "Available."
WAITING = "Waiting for your yes on the approval card."
APPROVED = "Approved. Send the file now."
DENIED = "You said no, so that file was not saved."
EXPIRED = "That upload expired, so nothing was saved. Start it again."
UNKNOWN = "Jarvis does not know that upload. Start it again."
NOT_READY = "That upload is not ready for that step yet."
FINISHED = "That upload has already been put together."
OUT_OF_ORDER = ("That piece arrived out of turn, so the file cannot be put together. "
                "Start it again.")
CHUNK_TOO_BIG = "That piece is too big to send - send the file in smaller pieces."
BUSY = "Another file is still on its way - let it finish first."
FULL = ("Jarvis is already holding as many files as it will hold at once - let one "
        "finish first.")
NAME_BAD = ("That file's name is not one Jarvis can save. A name with no folder part, "
            "no dot at the front and under 150 characters is what it needs.")
KIND_BAD = ("Jarvis saves PDF, Word, Excel, PowerPoint, Markdown, text and CSV files from "
            "your phone, and photos (JPG, PNG, WebP, HEIC, GIF or BMP), and that one is not "
            "one of them.")
NOTION_KIND_BAD = "The Notion export must be the .zip file Notion made."
FOLDER_NOT_LISTED = "It can only go into a folder on the list - add the folder first."
FOLDER_GONE = "That folder is not there any more."
NOT_A_PLACE = "Jarvis does not save files in that place."
MISSING = ("Your PC's Jarvis cannot take a file from your phone yet - run "
           "apply-patches.ps1 on the PC.")
TOO_BIG_DOC = "That file is {size}. Files up to {cap} can be sent from your phone."
TOO_BIG_NOTION = "That export is {size}. Exports up to {cap} can be sent from your phone."
DID_NOT_ARRIVE = "The file did not arrive whole, so nothing was saved. Send it again."
SHA_BAD = "The file did not arrive exactly as it left your phone, so nothing was saved."
NOT_WHAT_NAME = "It says it is {kind} but it is not one, so nothing was saved."
ENCRYPTED_PDF = "That PDF is locked with a password, so nothing was saved."
ZIP_PROBLEM = "Jarvis will not open that file: {why}"
NOT_PLAIN_TEXT = "It is not plain text, so nothing was saved."
NO_BYTES = "There were no bytes in it, so nothing was saved."
LINK_REFUSED = "One of the places that would be written is a link, so nothing was saved."
COULD_NOT_SAVE = "It could not be saved on this PC just now. Nothing was changed."
SAVED = ('Saved in "{folder}", in the "{sub}" folder inside it. Ask Jarvis about it '
         'whenever you like.')
EXPORT_ARRIVED = ("Your export arrived. Choose the vault to bring it into, and Jarvis "
                  "will show you what is in it before anything is written.")
CARD_HOW = ("It goes in the \"{sub}\" folder inside \"{folder}\", and from then on Jarvis "
            "can find it by name in your listed folders and read it when you ask - exactly "
            "as a file you put there yourself.")


# --------------------------------------------------------------------------
#   Small helpers
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """Jarvis's settings folder - the two variables every module here reads."""
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    return Path(os.path.expanduser("~")) / ".openjarvis"


def uploads_root() -> Path:
    """Where a Notion export waits: `%LOCALAPPDATA%\\Jarvis\\uploads`.

    NOT `~/.openjarvis`: that folder is in `jarvis_agent._PROTECTED_DIRS`, so
    the Notion importer would refuse its own receiving area. The environment
    override exists for the suite and must be an absolute path.
    """
    override = os.environ.get(UPLOADS_ENV, "").strip()
    if override and os.path.isabs(override):
        return Path(os.path.expanduser(override))
    base = os.environ.get("LOCALAPPDATA", "").strip()
    if base and os.path.isabs(base):
        return Path(base) / "Jarvis" / "uploads"
    return Path(os.path.expanduser("~")) / "AppData" / "Local" / "Jarvis" / "uploads"


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes. Never a file's name and never a folder's path.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-upload-card", daemon=True).start()


def _said_size(n) -> str:
    """A size in the words the owner reads - jarvis_attached_file's own."""
    try:
        return attached.said_size(n) if attached is not None else f"{int(n)} bytes"
    except Exception:
        return "that size"


def _sentence(text: str) -> str:
    s = str(text or "").strip()
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!")) else s + "."


def _kinds() -> dict:
    """The eight DOCUMENT kinds, in the words a person reads - never a second list.

    This stays document-only on purpose: it is what `jarvis_attached_file`
    reads, and the chat attachment reader's list must not grow a picture.
    [PHOTO_EXTENSIONS] is this door's own storage allowlist, asked by
    [_landing_kinds] beside it.
    """
    return dict(attached.KINDS) if attached is not None else {}


def _landing_kinds() -> dict:
    """Every extension this door may STORE: the eight documents plus the eight photos."""
    kinds = _kinds()
    kinds.update({ext: "photo" for ext in PHOTO_EXTENSIONS})
    return kinds


def _is_photo(name) -> bool:
    """Is this file a picture by its extension? Storage decisions only."""
    return _ext(name) in PHOTO_EXTENSIONS


def _ext(name: str) -> str:
    text = str(name or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    at = text.rfind(".")
    if at <= 0 or at == len(text) - 1:
        return ""
    return text[at:]


def safe_name(name) -> str:
    """The file's bare name as it may be kept, or ValueError with a sentence."""
    text = str(name or "").replace("\\", "/").strip()
    if "/" in text:
        raise ValueError(NAME_BAD)
    if not text or text in (".", "..") or text.startswith("."):
        raise ValueError(NAME_BAD)
    if any(ch in text for ch in "\\/") or ".." in text:
        raise ValueError(NAME_BAD)
    if _BAD_CHARS.search(text):
        raise ValueError(NAME_BAD)
    if text != text.strip(" ."):
        raise ValueError(NAME_BAD)
    if _RESERVED.match(text):
        raise ValueError(NAME_BAD)
    if len(text) > NAME_CHARS:
        raise ValueError(NAME_BAD)
    return text


def _cap_for(purpose: str) -> int:
    return MAX_NOTION_BYTES if purpose == "notion" else MAX_DOC_BYTES


def _which_purpose(body: dict) -> str:
    purpose = str((body or {}).get("purpose") or "document").strip().lower()
    return purpose if purpose in PURPOSES else ""


# --------------------------------------------------------------------------
#   The state machine - one entry per upload, in memory and short-lived
# --------------------------------------------------------------------------

_LOCK = threading.RLock()
_UP: dict = {}
_ARMED = False


def _now() -> float:
    return time.time()


def _expired(entry: dict) -> bool:
    return _now() - float(entry.get("seen") or entry.get("created") or 0) > LIFETIME


def _forget(uid: str, *, remove: bool = True, why: str = "") -> None:
    """Drop one upload, and its staging folder with it (never the owner's
    file: everything under staging was created by this module)."""
    with _LOCK:
        entry = _UP.pop(uid, None)
    if entry is not None and remove:
        _remove_tree(entry.get("staging"))
    if entry is not None and why:
        _audit("upload.dropped", {"why": why})


def _remove_tree(path) -> None:
    """Delete one staging folder this module made. Never raises."""
    if not path:
        return
    root = str(path)
    try:
        for base, dirs, files in os.walk(root, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(base, name))
                except OSError:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(base, name))
                except OSError:
                    pass
        os.rmdir(root)
    except OSError:
        pass


def _sweep() -> None:
    """Forget every expired upload, and every staging folder nothing owns.

    Called on `begin`, so a phone that dies mid-upload leaves nothing
    permanent: the id expires after LIFETIME_MINUTES and the bytes go with it.
    """
    with _LOCK:
        gone = [uid for uid, e in _UP.items() if _expired(e)]
    for uid in gone:
        _forget(uid, why="expired")
    root = uploads_root()
    try:
        if not root.is_dir():
            return
        cutoff = _now() - LIFETIME
        with _LOCK:
            live = {str(e.get("staging") or "") for e in _UP.values()}
        for child in root.iterdir():
            try:
                if not child.is_dir() or str(child) in live:
                    continue
                if child.stat().st_mtime < cutoff:
                    _remove_tree(str(child))
            except OSError:
                continue
    except OSError:
        return


def _active() -> list:
    with _LOCK:
        return [e for e in _UP.values() if e.get("state") in ("waiting", "approved", "ready")]


def _staged_bytes() -> int:
    total = 0
    for entry in _active():
        total += int(entry.get("received") or entry.get("size") or 0)
    return total


def _part_of(entry: dict) -> str:
    """The one file this upload's chunks are written into.

    A document gets a `.part` suffix as a second belt (its folder is already
    hidden); a Notion export keeps its own name, because that name decides the
    new vault folder's name and `jarvis_notion_obsidian.extract` only reads a
    path that really ends `.zip`.
    """
    staging = str(entry.get("staging") or "")
    if entry.get("purpose") == "notion":
        return os.path.join(staging, str(entry.get("name")))
    return os.path.join(staging, str(entry.get("name")) + ".part")


def _find(uid) -> Optional[dict]:
    """The live entry for one id, or None. Expires it first, so an id that has
    aged out can never be extended by a late chunk."""
    if not isinstance(uid, str) or not uid:
        return None
    with _LOCK:
        entry = _UP.get(uid)
        if entry is None:
            return None
        if _expired(entry):
            drop = True
        else:
            entry["seen"] = _now()
            drop = False
    if drop:
        _forget(uid, why="expired")
        return None
    return entry


# --------------------------------------------------------------------------
#   The folder a document may go into - by EQUALITY with the owner's own list
# --------------------------------------------------------------------------

def _listed_folder(into) -> tuple:
    """(the real listed folder, "") or (None, the sentence saying why not)."""
    if docs is None:
        return None, MISSING
    if attached is None:
        return None, MISSING
    if not isinstance(into, str) or not into.strip():
        return None, FOLDER_NOT_LISTED
    st = docs.load()
    if st.get("why"):
        return None, _sentence(st["why"])
    listed = [f["path"] for f in st.get("folders") or []]
    if not listed:
        return None, docs.PHONE_ADD
    want = docs._key(into.strip()) if hasattr(docs, "_key") else \
        os.path.normcase(os.path.realpath(into.strip()))
    for root in listed:
        if docs._key(root) == want:
            if not os.path.isdir(root):
                return None, FOLDER_GONE
            if docs.protected(root):
                return None, NOT_A_PLACE
            _P = _protection()
            if _P is not None:
                said = _P.path_refusal(root, write=True)
                if said:
                    return None, _sentence(said)
            return os.path.realpath(root), ""
    return None, FOLDER_NOT_LISTED


def _protection():
    """jarvis_protection, or None when a half-deployed install lacks it."""
    try:
        import jarvis_protection
        return jarvis_protection
    except Exception:
        return None


# --------------------------------------------------------------------------
#   The card - name, size and the folder's NAME, and nothing else
# --------------------------------------------------------------------------

def card(name: str, size: int, folder: str, purpose: str = "document") -> str:
    """What the one approval card says. No path, no bytes, no contents."""
    folder_name = _folder_name(folder)
    if purpose == "notion":
        return "\n".join([
            "Let Jarvis hold this Notion export?",
            "",
            f"File: {name}",
            f"Size: {_said_size(size)}",
            "",
            "Your phone sent Jarvis a zip of your own Notion export. It waits in Jarvis's "
            "own temporary folder, and Jarvis shows you what is inside it - how many "
            "notes, pictures and databases - before anything is written into your vault.",
            "",
            "Bringing it in is a second card of its own, and Undo takes the new folder "
            "back off in one step.",
            "",
            "If you did not just send this from your phone, say no.",
            "",
            "If you say no: nothing is kept.",
        ])
    how = ("It is a photo, so it is saved exactly as it is: Jarvis does not open it, read "
           "words from it or show it to a model on this path (only its first few bytes are "
           "checked, to be sure it really is a picture), and nothing in it is saved as a "
           "fact about you." if _is_photo(name) else
           "It is never opened, run or sent anywhere while it is being saved, and the words "
           "in it count as outside text: they are never saved as a fact about you.")
    return "\n".join([
        "Let Jarvis save this file from your phone?",
        "",
        f"File: {name}",
        f"Size: {_said_size(size)}",
        f"Into: {folder_name} > {SUB}",
        "",
        CARD_HOW.format(sub=SUB, folder=folder_name),
        "",
        how,
        "",
        "If you did not just send this from your phone, say no.",
        "",
        "If you say no: nothing is kept.",
    ])


def _folder_name(path: str) -> str:
    return re.split(r"[\\/]", str(path or "").rstrip("\\/"))[-1] or str(path or "")


def _person_said_yes(v) -> bool:
    if isinstance(v, dict):
        allowed = v.get("allowed") is True
        outcome = v.get("outcome")
        tier = v.get("tier", "ask")
    else:
        allowed = getattr(v, "allowed", False) is True
        outcome = getattr(v, "outcome", None)
        tier = getattr(v, "tier", "ask")
    if not allowed:
        return False
    if outcome is not None:
        return outcome == "approved" and tier == "ask"
    return tier == "ask"


def _ask(uid: str, name: str, size: int, folder: str, *, gate: Callable,
         tier_of: Callable[[str], str]) -> None:
    """Raise the ONE card; write the outcome on the entry. Never raises."""
    entry = _UP.get(uid)
    if entry is None:
        return
    text = card(name, size, folder)
    detail = {"text": text, "what": "save one file your phone sent",
              "setting": "a file arriving from another device",
              "file": name, "size": int(size), "folder": _folder_name(folder),
              "leaves_this_pc": False}
    try:
        verdict = gate(CARD_ACTION, detail, text)
    except Exception as exc:
        return _settle(uid, "refused", f"the approval could not be asked for "
                                       f"({type(exc).__name__})")
    tier = getattr(verdict, "tier", "unknown")
    if tier != "ask" or tier_of(CARD_ACTION) != "ask":
        return _settle(uid, "refused",
                       f"the gate answered at tier {tier!r}, which is not a person saying yes")
    if _person_said_yes(verdict):
        return _settle(uid, "approved", "")
    outcome = getattr(verdict, "outcome", None)
    if outcome in ("denied", "timed_out"):
        return _settle(uid, outcome, "")
    return _settle(uid, "refused", str(getattr(verdict, "reason", "refused"))[:200])


def _settle(uid: str, state: str, why: str) -> None:
    """Record what the person said. A denial also deletes anything staged."""
    with _LOCK:
        entry = _UP.get(uid)
        if entry is None:
            return
        entry["state"] = state
        entry["why"] = why
        entry["seen"] = _now()
        staging = entry.get("staging")
    if state != "approved":
        _remove_tree(staging)
        with _LOCK:
            again = _UP.get(uid)
            if again is not None:
                again["staging"] = None
    _audit("upload.card", {"outcome": state})


# --------------------------------------------------------------------------
#   begin
# --------------------------------------------------------------------------

def request_begin(body, *, gate: Optional[Callable] = None,
                  tier_of: Optional[Callable] = None,
                  spawn: Optional[Callable] = None,
                  sweep: bool = True) -> tuple:
    """POST /api/upload/begin. (code, body). 202 and, for a document, ONE card."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if docs is None or attached is None:
        return 503, {"ok": False, "said": MISSING, "reason": MISSING}
    if not isinstance(body, dict):
        return 400, {"ok": False, "said": "Send the file's name, size and folder.",
                     "reason": "need an object"}
    purpose = _which_purpose(body)
    if not purpose:
        return 400, {"ok": False, "said": KIND_BAD, "reason": "bad purpose"}
    try:
        name = safe_name(body.get("name"))
    except ValueError as exc:
        return 400, {"ok": False, "said": _sentence(exc), "reason": str(exc)}
    ext = _ext(name)
    if purpose == "document":
        # The eight document kinds AND the eight photo kinds (a photo is a
        # plain file copy; see PHOTO_EXTENSIONS). This is the door's storage
        # allowlist, not `jarvis_attached_file.KINDS`.
        if ext not in _landing_kinds():
            return 400, {"ok": False, "said": KIND_BAD, "reason": "kind"}
    elif ext != ".zip":
        return 400, {"ok": False, "said": NOTION_KIND_BAD, "reason": "notion needs .zip"}
    try:
        size = int(body.get("size"))
    except Exception:
        return 400, {"ok": False, "said": "Say how many bytes the file is.",
                     "reason": "bad size"}
    if size <= 0:
        return 400, {"ok": False, "said": NO_BYTES, "reason": "zero bytes"}
    cap = _cap_for(purpose)
    if size > cap:
        said = (TOO_BIG_NOTION if purpose == "notion" else TOO_BIG_DOC).format(
            size=_said_size(size), cap=_said_size(cap))
        return 413, {"ok": False, "said": said, "reason": "too big", "max_bytes": cap}

    folder, why = "", ""
    if purpose == "document":
        folder, why = _listed_folder(body.get("into"))
        if not folder:
            # "not on the list" is the caller naming the wrong thing (400); an
            # empty, damaged or vanished list is this PC's own state (409).
            code = 400 if why == FOLDER_NOT_LISTED else 409
            return code, {"ok": False, "said": _sentence(why), "reason": why}
    if sweep:
        _sweep()
    if len(_active()) >= MAX_ACTIVE:
        return 409, {"ok": False, "said": BUSY, "reason": "busy"}
    if _staged_bytes() + size > STAGING_MAX:
        return 409, {"ok": False, "said": FULL, "reason": "staging full"}

    uid = uuid.uuid4().hex
    entry = {
        "id": uid, "name": name, "size": size, "purpose": purpose,
        "mime": str(body.get("mime") or "")[:120],
        "into": folder, "folder": _folder_name(folder) if folder else "",
        "sha256": str(body.get("sha256") or "").strip().lower()[:64],
        "created": _now(), "seen": _now(), "received": 0, "index": 0,
        "state": "ready" if purpose == "notion" else "waiting",
        "staging": None, "complete": False, "why": "", "digest": None,
    }
    with _LOCK:
        _UP[uid] = entry
    if purpose == "notion":
        # No card here: the card that matters is the import's own, with the
        # real counts on it, and nothing is written into the vault before it.
        _audit("upload.begin", {"purpose": "notion"})
        return 202, {"ok": True, "id": uid, "waiting": False,
                     "chunk_bytes": CHUNK_BYTES, "max_bytes": cap,
                     "said": "Send the export in pieces, then finish."}
    try:
        spawn(lambda: _ask(uid, name, size, folder, gate=gate, tier_of=tier_of))
    except Exception:
        _forget(uid, remove=False)
        return 503, {"ok": False, "said": "The approval card could not be raised, so nothing "
                                          "was sent for.",
                     "reason": "no card"}
    with _LOCK:
        waiting = _UP.get(uid, {}).get("state") == "waiting"
    _audit("upload.begin", {"purpose": "document"})
    return 202, {"ok": True, "id": uid, "waiting": waiting,
                 "chunk_bytes": CHUNK_BYTES, "max_bytes": cap,
                 "said": WAITING if waiting else APPROVED}


# --------------------------------------------------------------------------
#   chunk
# --------------------------------------------------------------------------

def _staging_dir(entry: dict) -> str:
    """Where this upload's bytes wait. Created on the first chunk, so a card
    that is never answered writes nothing at all."""
    if entry["purpose"] == "notion":
        return str(uploads_root() / entry["id"])
    folder = str(entry["into"])
    return os.path.join(folder, STAGING_PREFIX + entry["id"])


def _ensure_staging(entry: dict) -> tuple:
    """(the staging folder, "") or (None, why). Refuses a link on the way."""
    if entry.get("staging") and os.path.isdir(entry["staging"]):
        return entry["staging"], ""
    dest = _staging_dir(entry)
    parent = os.path.dirname(dest)
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError:
        return None, COULD_NOT_SAVE
    if os.path.islink(dest):
        return None, LINK_REFUSED
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError:
        return None, COULD_NOT_SAVE
    if os.path.islink(dest) or not os.path.isdir(dest):
        return None, LINK_REFUSED
    if entry["purpose"] == "document":
        # The staging folder must really be inside the listed folder it was
        # made in, or a junction planted there would move the write elsewhere.
        real = os.path.realpath(dest)
        if not docs._inside(os.path.realpath(entry["into"]), real):
            return None, LINK_REFUSED
    entry["staging"] = dest
    return dest, ""


def request_chunk(body) -> tuple:
    """POST /api/upload/chunk {"id", "index", "data"}. 200 {"received": n}."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "said": NOT_READY, "reason": "need an object"}
    entry = _find(body.get("id"))
    if entry is None:
        return 410, {"ok": False, "said": UNKNOWN, "reason": "unknown"}
    state = entry.get("state")
    if state == "waiting":
        return 409, {"ok": False, "waiting": True, "said": WAITING, "reason": "waiting"}
    if state in ("denied", "timed_out"):
        return 403, {"ok": False, "denied": True, "said": DENIED, "reason": "denied"}
    if state != "approved" and state != "ready":
        return 409, {"ok": False, "said": NOT_READY, "reason": "not ready"}
    if entry.get("complete"):
        return 409, {"ok": False, "said": FINISHED, "reason": "finished"}
    try:
        index = int(body.get("index"))
    except Exception:
        return 400, {"ok": False, "said": OUT_OF_ORDER, "reason": "bad index"}
    if index != int(entry.get("index") or 0):
        return 409, {"ok": False, "said": OUT_OF_ORDER, "reason": "out of order"}

    raw, why = _bytes_of(body.get("data"))
    if why:
        return 400, {"ok": False, "said": why, "reason": why}
    if len(raw) > CHUNK_BYTES:
        return 413, {"ok": False, "said": CHUNK_TOO_BIG, "reason": "chunk too big"}
    if int(entry["received"]) + len(raw) > int(entry["size"]):
        return 413, {"ok": False, "said": DID_NOT_ARRIVE, "reason": "past the declared size"}

    staging, why = _ensure_staging(entry)
    if not staging:
        code = 507 if why == COULD_NOT_SAVE else 403
        return code, {"ok": False, "said": why, "reason": why}
    part = _part_of(entry)
    try:
        with open(part, "ab") as fh:
            fh.write(raw)
    except OSError:
        return 507, {"ok": False, "said": COULD_NOT_SAVE, "reason": "disk"}
    with _LOCK:
        entry["received"] = int(entry["received"]) + len(raw)
        entry["index"] = index + 1
        if entry.get("digest") is None:
            entry["digest"] = hashlib.sha256()
        try:
            entry["digest"].update(raw)
        except Exception:
            entry["digest"] = None
        received = int(entry["received"])
    return 200, {"ok": True, "received": received}


def _bytes_of(data) -> tuple:
    """(raw bytes, why not) for one chunk's base64 field."""
    if not isinstance(data, str) or not data:
        return b"", "That piece arrived with no bytes in it."
    if len(data) > (CHUNK_BYTES * 4) // 3 + 16:
        return b"", CHUNK_TOO_BIG
    try:
        return base64.b64decode(data, validate=False), ""
    except (binascii.Error, ValueError):
        return b"", "That piece did not arrive whole. Start it again."


# --------------------------------------------------------------------------
#   finish - the only moment a file becomes real
# --------------------------------------------------------------------------

#: The ISO base-media brands a `.heic`/`.heif` may carry in its `ftyp` box.
#: The brands Apple and Android cameras write, plus the generic HEIF ones.
HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1")


def _photo_problem(path: str, ext: str) -> str:
    """'' when the bytes on disk really are the picture the name claims.

    A HEADER check and nothing more: it reads at most 64 bytes, never decodes
    the image, never runs OCR and never hands the bytes to a model. It exists
    for the same reason `_magic_problem` does - a `.png` that is really a
    program must be refused rather than stored under a picture's name.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
    except OSError:
        return COULD_NOT_SAVE
    if ext in (".jpg", ".jpeg"):
        ok = head.startswith(b"\xff\xd8\xff")
    elif ext == ".png":
        ok = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext == ".gif":
        ok = head.startswith((b"GIF87a", b"GIF89a"))
    elif ext == ".bmp":
        ok = head.startswith(b"BM")
    elif ext == ".webp":
        ok = len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"WEBP"
    else:                                    # .heic/.heif: an ISO base-media file
        ok = len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS
    if not ok:
        return NOT_WHAT_NAME.format(kind="a photo")
    return ""


def _magic_problem(path: str, ext: str) -> str:
    """'' when the bytes on disk are what the name claims, else a sentence."""
    kind = _landing_kinds().get(ext, "that file")
    if ext in PHOTO_EXTENSIONS:
        # A photo is stored and never read. Its header check is the whole of
        # this door's inspection - no decoder, no OCR, no model.
        return _photo_problem(path, ext)
    try:
        if ext == ".pdf":
            with open(path, "rb") as fh:
                if not fh.read(8).startswith(b"%PDF-"):
                    return NOT_WHAT_NAME.format(kind=kind)
                try:
                    fh.seek(-4096, os.SEEK_END)
                except OSError:
                    fh.seek(0)
                if b"/Encrypt" in fh.read():
                    return ENCRYPTED_PDF
            return ""
        if ext in getattr(attached, "ZIP_KINDS", {}):
            with open(path, "rb") as fh:
                if not fh.read(4).startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
                    return NOT_WHAT_NAME.format(kind=kind)
            with zipfile.ZipFile(path) as zf:
                why = docs.zip_bomb_problem(zf, attached.ZIP_UNCOMPRESSED_MAX)
                if why:
                    return ZIP_PROBLEM.format(why=why)
                why = docs.zip_path_problem(zf)
                if why:
                    return ZIP_PROBLEM.format(why=why)
                names = zf.namelist()
            want = attached.ZIP_KINDS.get(ext, "")
            if want and not any(str(n).startswith(want) or f"/{want}" in f"/{n}"
                                for n in names):
                return NOT_WHAT_NAME.format(kind=kind)
    except zipfile.BadZipFile:
        return NOT_WHAT_NAME.format(kind=kind)
    except OSError:
        return COULD_NOT_SAVE
    return ""


def _text_problem(path: str) -> str:
    """'' for a note, text file or CSV, else why not: no NULs, real UTF-8.

    Read in pieces rather than whole: a 50 MB text file is allowed, and
    decoding it into one string to throw the string away is work nobody needs.
    """
    import codecs
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        with open(path, "rb") as fh:
            head = fh.read(8192)
            if b"\x00" in head:
                return NOT_PLAIN_TEXT
            fh.seek(0)
            while True:
                piece = fh.read(1024 * 1024)
                if not piece:
                    break
                decoder.decode(piece)
            decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return NOT_PLAIN_TEXT
    except OSError:
        return COULD_NOT_SAVE
    return ""


def _notion_zip_problem(path: str) -> str:
    """'' when the staged export may be handed to the importer, else a sentence.

    The checks are the importer's own: `jarvis_documents.zip_bomb_problem` with
    `EXPORT_UNCOMPRESSED_MAX` (the PC's unpacked ceiling - 4 GB since
    2026-11-09; the sentence names the declared size and the ceiling), and
    `jarvis_notion_obsidian._zip_problem` when that module is here, which is
    exactly what `plan_import` will judge it by a moment later.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            why = docs.zip_bomb_problem(zf, docs.EXPORT_UNCOMPRESSED_MAX)
            if why:
                return ZIP_PROBLEM.format(why=why)
            try:
                import jarvis_notion_obsidian
                why = jarvis_notion_obsidian._zip_problem(zf)
            except Exception:
                why = ""
            if why:
                return ZIP_PROBLEM.format(why=why)
    except zipfile.BadZipFile:
        return "That is not a zip Jarvis can open, so nothing was saved."
    except OSError:
        return COULD_NOT_SAVE
    return ""


def _free_name(folder: str, name: str) -> str:
    """`name`, or `name (2)`, `name (3)` ... - never over the owner's file."""
    want = os.path.join(folder, name)
    if not os.path.exists(want):
        return want
    base, ext = os.path.splitext(want)
    i = 2
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def _land(entry: dict, part: str) -> tuple:
    """(the landed path, "") or (None, why). The one write into the owner's folder."""
    folder = str(entry["into"])
    if not os.path.isdir(folder):
        return None, FOLDER_GONE
    if docs.protected(folder):
        return None, NOT_A_PLACE
    sub = os.path.join(folder, SUB)
    if os.path.islink(sub):
        return None, LINK_REFUSED
    try:
        os.makedirs(sub, exist_ok=True)
    except OSError:
        return None, COULD_NOT_SAVE
    if os.path.islink(sub) or not os.path.isdir(sub):
        return None, LINK_REFUSED
    _P = _protection()
    if _P is not None:
        said = _P.path_refusal(sub, write=True)
        if said:
            return None, _sentence(said)
    final = _free_name(sub, str(entry["name"]))
    try:
        os.replace(part, final)
    except OSError:
        return None, COULD_NOT_SAVE
    # The landing must really be readable afterwards, by the SAME rule every
    # read goes through - otherwise the file would sit somewhere the owner can
    # see in Explorer and Jarvis cannot open.
    if docs.allowed_path(final) is None:
        try:
            os.remove(final)
        except OSError:
            pass
        return None, NOT_A_PLACE
    return final, ""


def request_finish(body, *, launch: Optional[Callable[[dict], tuple]] = None) -> tuple:
    """POST /api/upload/finish {"id", "sha256"?}.

    A document LANDS here, after every check, and its staging folder goes. A
    Notion export is only marked complete: it waits for `phone-import`, which
    is where the vault is known and the import card is raised.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "said": NOT_READY, "reason": "need an object"}
    uid = body.get("id")
    entry = _find(uid)
    if entry is None:
        return 410, {"ok": False, "said": UNKNOWN, "reason": "unknown"}
    state = entry.get("state")
    if state == "waiting":
        return 409, {"ok": False, "waiting": True, "said": WAITING, "reason": "waiting"}
    if state in ("denied", "timed_out"):
        return 403, {"ok": False, "denied": True, "said": DENIED, "reason": "denied"}
    if state not in ("approved", "ready"):
        return 409, {"ok": False, "said": NOT_READY, "reason": "not ready"}
    if entry.get("complete"):
        return 409, {"ok": False, "said": FINISHED, "reason": "finished"}
    staging = str(entry.get("staging") or "")
    part = _part_of(entry) if staging else ""
    if not part or not os.path.isfile(part):
        _forget(str(uid), why="missing")
        return 410, {"ok": False, "said": DID_NOT_ARRIVE, "reason": "no bytes"}
    received = os.path.getsize(part)
    if received <= 0:
        _forget(str(uid))
        return 200, {"ok": False, "said": NO_BYTES, "reason": "empty"}
    if received != int(entry["size"]) or received != int(entry.get("received") or 0):
        _forget(str(uid))
        return 200, {"ok": False, "said": DID_NOT_ARRIVE, "reason": "short"}
    if received > _cap_for(entry["purpose"]):
        _forget(str(uid))
        return 413, {"ok": False, "said": TOO_BIG_DOC.format(
            size=_said_size(received), cap=_said_size(_cap_for(entry["purpose"]))),
            "reason": "too big"}

    want = str(body.get("sha256") or entry.get("sha256") or "").strip().lower()[:64]
    if want:
        got = hashlib.sha256()
        try:
            with open(part, "rb") as fh:
                while True:
                    piece = fh.read(1024 * 1024)
                    if not piece:
                        break
                    got.update(piece)
        except OSError:
            _forget(str(uid))
            return 200, {"ok": False, "said": COULD_NOT_SAVE, "reason": "read"}
        if got.hexdigest() != want:
            _forget(str(uid), why="sha")
            return 200, {"ok": False, "said": SHA_BAD, "reason": "sha256"}

    if entry["purpose"] == "notion":
        problem = _notion_zip_problem(part)
        if problem:
            _forget(str(uid), why="not a zip")
            return 200, {"ok": False, "said": problem, "reason": "zip"}
        with _LOCK:
            entry["complete"] = True
            entry["seen"] = _now()
        _audit("upload.staged", {"purpose": "notion"})
        return 200, {"ok": True, "ready": True, "id": str(uid), "name": entry["name"],
                     "size": received, "said": EXPORT_ARRIVED}

    ext = _ext(str(entry["name"]))
    problem = _text_problem(part) if ext in getattr(attached, "TEXT_KINDS", ()) \
        else _magic_problem(part, ext)
    if problem:
        _forget(str(uid), why="not what its name says")
        return 200, {"ok": False, "said": problem, "reason": "bytes"}
    final, why = _land(entry, part)
    if not final:
        _forget(str(uid))
        return (403 if why in (LINK_REFUSED, NOT_A_PLACE) else 200), {
            "ok": False, "said": why, "reason": why}
    folder = _folder_name(entry["into"])
    with _LOCK:
        _UP.pop(str(uid), None)
    _remove_tree(staging)
    _audit("upload.saved", {"purpose": "document"})
    return 200, {"ok": True, "saved": True, "name": os.path.basename(final),
                 "folder": folder, "sub": SUB, "size": received,
                 "said": SAVED.format(folder=folder, sub=SUB)}


# --------------------------------------------------------------------------
#   What the Notion importer asks for: the staged export behind an upload id
# --------------------------------------------------------------------------

def staging_file(upload_id) -> str:
    """The completed Notion export an upload id holds, or "" - never raises.

    This is the ONLY way `jarvis_notion_obsidian.phone_import` learns a path,
    and it is a path this module made itself, in `%LOCALAPPDATA%`: the phone
    never sends one.
    """
    entry = _find(upload_id)
    if entry is None or entry.get("purpose") != "notion" or not entry.get("complete"):
        return ""
    part = _part_of(entry)
    if not os.path.isfile(part):
        return ""
    return part


def release(upload_id) -> None:
    """Delete a staged export and forget it - `phone-import` calls this in a
    `finally`, so the bytes die on success, refusal, a denied card and error."""
    _forget(str(upload_id or ""), why="released")


def _reset_for_tests() -> None:
    global _ARMED
    with _LOCK:
        for uid in list(_UP):
            _remove_tree(_UP[uid].get("staging"))
        _UP.clear()
    _ARMED = False


# --------------------------------------------------------------------------
#   The routes - wrapped round the server's handler
# --------------------------------------------------------------------------

def armed() -> bool:
    return _ARMED


def handle_post(route: str, body, *, gate: Optional[Callable] = None,
                tier_of: Optional[Callable] = None,
                spawn: Optional[Callable] = None) -> tuple:
    if route == BEGIN_ROUTE:
        return request_begin(body, gate=gate, tier_of=tier_of, spawn=spawn)
    if route == CHUNK_ROUTE:
        return request_chunk(body)
    return request_finish(body)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_POST` so the three upload routes are answered here.

    There is NO GET: these are writes, and a GET would be a way to ask what is
    half-written. Every other request goes straight to the original handler.
    Both checks are the core's own - origin and token, the same pair every
    route keeps - and `jarvis_owner_check.from_this_pc` is deliberately NOT
    asked: the caller is a phone, and that is the whole point of the feature.
    """
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_upload", False):
        _ARMED = True
        return "  upload     a document from your phone (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                _send(self, 403, {"ok": False, "said": "That request did not come from here.",
                                  "reason": "origin"})
                return False
            if not token_ok(self):
                _send(self, 401, {"ok": False,
                                  "said": "This app is not paired with your PC.",
                                  "reason": "token"})
                return False
        except Exception:
            _send(self, 401, {"ok": False, "said": "This app is not paired with your PC.",
                              "reason": "token"})
            return False
        return True

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route in ROUTES:
            return _send(self, 405, {"ok": False,
                                     "said": "That is a send-only address: the phone posts to it.",
                                     "reason": "post only"})
        return get0(self)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in ROUTES:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            return _send(self, 400, {"ok": False,
                                     "said": "That request was not readable, so nothing "
                                              "was saved.",
                                     "reason": "body"})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False,
                              "said": "Something went wrong on this PC, so nothing was "
                                      "saved.",
                              "reason": type(exc).__name__}
        return _send(self, code, out)

    do_GET._jarvis_upload = True      # type: ignore[attr-defined]
    do_POST._jarvis_upload = True     # type: ignore[attr-defined]
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return f"  upload     A document from your phone: {len(ROUTES)} routes, one card a file"


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


if __name__ == "__main__":
    print(f"  {TITLE}: {len(ROUTES)} routes, {_said_size(MAX_DOC_BYTES)} a document, "
          f"{_said_size(MAX_NOTION_BYTES)} a Notion export")
    print(f"  the Notion staging folder is {uploads_root()}")
    print(f"  the parts of Jarvis this needs are "
          + ("here" if (docs is not None and attached is not None) else "NOT here"))
