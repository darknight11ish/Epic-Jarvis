"""jarvis_send_file.py - send ONE file from the owner's own listed folders to
the Jarvis phone app, after ONE approval card, without ever putting a raw path
on the phone's route.

THE OWNER'S REQUEST (2026-10-31, their own words): *"am i able to ask jarvis to
search for a file for me and send it to the jarvis android app to view and or
download directly? this would be a file on the desktop"*.

Gemini ruled on it the same day (Q7): build the bounded "send file to phone"
slice, NOT a text-only halfway step and NOT a "share folder" the owner has to
fill by hand at the PC. The owner raised the ceiling and asked for a button on
2026-11-14 (`SEND-TO-PHONE-2GB-DESIGN-2026-11-14.md`): one number
`CAP_BYTES`, one piece size `CHUNK_BYTES`, a `TTL_SECONDS` life renewed per
piece, a `GRACE_SECONDS` wait after the last piece for the phone's own receipt
(`POST /api/files/ack`), and a `POST /api/files/prepare` for the desktop's
"Send a file to your phone…" button. Gemini's Q1 ruling the same day closed the
lost-final-reply hole: the last piece marks `final_served_at`, and the id is
consumed by the phone's receipt (after its own SHA-256 check) or by the grace
running out - whichever is first. This module is the backend half:

  1. SEARCH reuses the existing "Folders Jarvis may look in" allow-list
     (`jarvis_documents.folders()` + `jarvis_documents.allowed_path()`), so a
     file outside it is never a candidate. When the "Protected from Jarvis"
     module (PR #1019, not on this tree yet) is importable, its ONE keep-out
     check is asked as a soft hook - this module never duplicates it.
  2. Each candidate gets an EPHEMERAL opaque `file_id` (random, in memory,
     `TTL_SECONDS`, at most `MAX_PENDING` alive, cleared on restart). The phone
     routes take the id, NEVER a path parameter.
  3. The model tool `send_file_to_phone` is the ONE card: the gate action is
     `send_file_to_phone` (tier "ask"; an unclassified action is forced to ask
     and carries the gate's own outbound worst-case risk line, because a file
     leaving the PC's own folders for the phone's storage can still be copied
     off the phone afterwards). The card's words show the EXACT filename, the
     folder it came from, its byte size, the cap and the life of the link.
  4. The DESKTOP's button is a ROUTE, not a tool: `POST /api/files/prepare`
     takes the absolute path the owner picked in a native dialog, refuses a
     missing file, a folder, a protected path or one over `CAP_BYTES` in words
     BEFORE the card, and otherwise raises the SAME ONE card. It is the only
     place a path may name a file outside the allow-list, because the owner
     picked it himself; the model tool still searches the allow-list only.
  5. NOTHING is fetchable until the card's yes. After approval the phone lists
     it (`GET /api/files/send`) and fetches it ONE PIECE AT A TIME
     (`GET /api/files/download?id=<file_id>&offset=&length=`), base64 in JSON,
     the same shape `/api/pictures/file` already uses. Every answer carries the
     WHOLE file's sha256 and that piece's own hash.
  6. A piece may be retried, and the LAST piece does not consume the id: it
     stamps `final_served_at` and holds the id for `GRACE_SECONDS`, so a lost
     200 on Wi-Fi or Meshnet can be retried inside that window. The phone then
     sends its own receipt (`POST /api/files/ack`) once the whole file's
     SHA-256 has checked out, and that receipt consumes the id - or the grace
     runs out, whichever is first. `single_use` therefore means one completed
     transfer, not a promise that the first fetch uses the id up. An unknown,
     expired or consumed id answers 404 in plain words; so does a file that
     vanished between the card and the fetch, and one that changed answers 409.

WHAT IT WILL NOT DO

  - Read outside the allow-list through the MODEL tool, ever: every candidate
    goes through `jarvis_documents.allowed_path()`, which is the same door
    `my_files` and the folders settings use (no hidden folders, no private
    places, links followed). The ONE exception is the desktop button's route,
    where the owner named the file in a dialog himself.
  - Send more than ONE file per card, more than ONE card at a time, or a file
    over `CAP_BYTES` - a bigger file is refused in words before the card,
    never silently truncated, and never served as one short piece to an old
    client.
  - Put a filesystem path on the phone's route or in the fetch answer: the
    route takes an id and numbers; list answers carry the filename, folder and
    size for the app's own display, and the fetch answer carries only the
    name, whole-file size, MIME type, offsets and the bytes.
  - Run when the gate cannot answer: the tool goes through `jarvis_gate.check`
    like every other tool, and the button's route raises the same card through
    the same gate (`prepare` refuses a bad/missing/oversize file BEFORE the
    card; nothing is registered as fetchable except on an approved verdict).
  - Read or write anything about the pairing token, open a tunnel, or touch
    the network. The routes are local, behind the core's own origin + token
    checks (`X-Jarvis-Client` + token, exactly like `/api/protection` and
    `/api/pictures/file`).

NAMED LIMITS (also in docs/JARVIS-API.md section 172)

  - one file per card, one card at a time;
  - `TTL_SECONDS` from the card's yes, renewed by every piece served;
  - the last piece starts `GRACE_SECONDS`; the phone's receipt (`POST
    /api/files/ack`) consumes the id at once, or the grace runs out - one
    completed transfer, and pieces may be retried before it finishes;
  - `CAP_BYTES`: over it is a plain refusal, never a truncation;
  - at most `MAX_PENDING` (8) ids alive, oldest dropped first;
  - in memory only: a restart clears every id (the phone lane then shows
    "ask Jarvis again" - this is deliberate, not a bug);
  - the phone's View / Save to Downloads UI, `FileProvider`, `ACTION_VIEW` and
    `MediaStore.Downloads` are the PHONE lane's work; this module only makes
    the bytes reachable by an approved id.

Standard library only. No network, no model, no new permission scheme.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit

#: The ceiling ONE file may be. It is the ONLY place the number is written:
#: `cap_sentence()` reads it into the card, the over-cap refusal, the list's
#: `cap_bytes` and the phone-visible words, so none of them can drift from it.
#: The owner chose it on 2026-11-14, replacing the ten-MiB slice of Q7.
CAP_BYTES = 2 * 1024 * 1024 * 1024

#: One piece's size. `GET /api/files/download` serves one piece per request,
#: `length` is never more than this, and the list answers it as `chunk_bytes`
#: so the phone can cut a long file without guessing.
CHUNK_BYTES = 1024 * 1024

#: How long an id lives after the card's yes, and how long a candidate id may
#: wait for its card. Every piece served starts it again: a slow transfer is
#: never cut off mid-file, and an id left in a log is worthless soon after.
TTL_SECONDS = 600

#: How long an id is held after the LAST piece was served, waiting for the
#: phone's own receipt (`POST /api/files/ack`). The last piece does not consume
#: the id: it stamps `final_served_at` and starts this window, so a lost 200 on
#: Wi-Fi or Meshnet is retryable instead of costing a second 2 GiB transfer.
#: The receipt consumes the id at once; serving the last piece again re-arms
#: the window. This is the ceiling, not the usual wait.
GRACE_SECONDS = 60

#: At most this many ids in memory at once. The oldest is dropped, so a long
#: day of asking cannot grow here.
MAX_PENDING = 8

#: How many names a search returns before it says "narrow it down".
SEARCH_LIMIT = 20

#: Bounds for the walk: enough for a normal listed folder, small enough that a
#: huge tree cannot make one model call read a whole drive.
MAX_WALK_FILES = 5000
WALK_SECONDS = 2.0

#: The gate action the ONE card is asked under, for the model tool, the chat
#: fast path and the desktop button alike. The shipped `jarvis-framework.toml`
#: (both copies) carries `send_file_to_phone = "ask"`; the gate forces "ask"
#: for an unclassified action even if that line went missing.
ACTION = "send_file_to_phone"

#: The routes. No route below takes a filesystem path on the phone's side.
LIST_PATH = "/api/files/send"
DOWNLOAD_PATH = "/api/files/download"
PREPARE_PATH = "/api/files/prepare"
ACK_PATH = "/api/files/ack"
GET_PATHS = (LIST_PATH, DOWNLOAD_PATH)
POST_PATHS = (PREPARE_PATH, ACK_PATH)

#: How many names a refusal may quote back to the model/owner.
MAX_NAMES_IN_REFUSAL = 8

_GIB = 1024 * 1024 * 1024

#: Words with no number in them, so they cannot drift from a constant.
GONE_WORDS = "That file is not on this PC any more, so there is nothing to send."
CHANGED_WORDS = ("That file changed since the card was approved, so nothing was sent. "
                 "Ask Jarvis again.")
NO_SEARCH_WORDS = ("No file in your listed folders matches {query!r}. Nothing was sent.")
BAD_NUMBERS_WORDS = ("Give 'offset' and 'length' as whole numbers of bytes - offset 0 "
                     "or more, length at least 1. Nothing was sent.")
PIECES_WORDS = ("This file is bigger than one piece, so ask for it in pieces: give "
                "'offset' and 'length', starting at offset 0. Nothing was sent.")
PAST_END_WORDS = ("That start is at or past the end of the file, so there is nothing to "
                  "send.")
NO_ID_WORDS = "Say which file it is - no path is needed."
NO_PATH_WORDS = ("Say which file to send: this address needs one absolute path, chosen "
                 "on this PC.")
NOT_ABSOLUTE_WORDS = ("That is not a full path, so nothing was sent. Pick the file again "
                      "in the desktop program's dialog.")
FOLDER_WORDS = ("That is a folder, not a file - one file goes on one card. Nothing was "
                "sent.")
NO_CARD_WORDS = ("The approval card could not be raised, so nothing was sent.")
READ_FAILED_WORDS = "That file could not be read just now, so nothing was sent."
PHONE_SURFACE_WORDS = ("That address is for the desktop program: the phone fetches a "
                       "file by its id and never names a path. Nothing was sent.")
BAD_BODY_WORDS = "That request was not readable, so nothing was sent."
UNKNOWN_ROUTE_WORDS = "no such route"
BROKEN_WORDS = "Something went wrong on this PC, so nothing was sent."
ACK_NO_ID_WORDS = ("Say which transfer to confirm by its id - this address never takes a "
                   "path.")
ACK_PATH_WORDS = ("The phone's receipt takes the transfer's id only, never a path. Nothing "
                  "was confirmed.")
ACK_NOT_FINISHED_WORDS = ("That file has not finished arriving yet, so there is nothing to "
                          "confirm. Keep fetching the rest, then send the receipt again.")
ACK_DONE_WORDS = "Transfer finished - that file is no longer waiting for your phone."
ACK_ALREADY_WORDS = ("That transfer has already finished - there is nothing more to "
                     "confirm.")

_lock = threading.Lock()
#: id -> {id, path, name, folder, size, mtime, mime, created, expires,
#:        approved, used, chosen, sha256, final_served_at, acked_at}
#: `used` is also the phone's receipt tombstone, so a repeated receipt answers
#: its own 200 instead of a 404; `final_served_at` is when the last piece was
#: served (0.0 before that), and the id lives `GRACE_SECONDS` past it.
_files: dict = {}


# ---------------------------------------------------------------------------
#   The one number, said the same way everywhere
# ---------------------------------------------------------------------------


def human_bytes(n: int) -> str:
    """A byte count the owner can read, the biggest sensible unit first."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "an unknown size of"
    if n < 1024:
        return f"{n} bytes"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < _GIB:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / _GIB:g} GB"


def ttl_words() -> str:
    """How long the id lives, in the words every sentence uses."""
    if TTL_SECONDS % 60 == 0:
        minutes = TTL_SECONDS // 60
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return f"{TTL_SECONDS} seconds"


def ttl_label() -> str:
    """The same life as one adjective: "10-minute", "45-second"."""
    if TTL_SECONDS % 60 == 0:
        return f"{TTL_SECONDS // 60}-minute"
    return f"{TTL_SECONDS}-second"


def grace_words() -> str:
    """The wait after the last piece, in the words every sentence uses."""
    if GRACE_SECONDS % 60 == 0:
        minutes = GRACE_SECONDS // 60
        return "a minute" if minutes == 1 else f"{minutes} minutes"
    return f"{GRACE_SECONDS} seconds"


def transfer_words() -> str:
    """What "one completed transfer" means, said the same way everywhere.

    Read by the card, the ready sentence and the phone's list, so the receipt
    (`POST /api/files/ack`) and the grace cannot drift apart in one of them.
    """
    return (f"The link is good for one completed transfer: it finishes when your "
            f"phone confirms it, or {grace_words()} after the last piece - "
            "whichever is first.")


def chunk_words() -> str:
    """One piece's size, in the words every sentence uses."""
    if CHUNK_BYTES >= 1024 * 1024 and CHUNK_BYTES % (1024 * 1024) == 0:
        return f"{CHUNK_BYTES // (1024 * 1024)} MiB"
    if CHUNK_BYTES >= 1024 and CHUNK_BYTES % 1024 == 0:
        return f"{CHUNK_BYTES // 1024} KiB"
    return human_bytes(CHUNK_BYTES)


def cap_sentence() -> str:
    """The ceiling as one phrase: a readable size plus the exact bytes."""
    return f"{human_bytes(CAP_BYTES)} ({CAP_BYTES:,} bytes)"


def no_cap_words(name: str, size) -> str:
    """The over-cap refusal, with the same number the card carries."""
    return (f'"{name}" is {int(size):,} bytes, over the {cap_sentence()} this slice '
            "can send. Nothing was sent and no card was raised.")


def empty_file_words(name: str) -> str:
    return f'"{name}" is empty, so there is nothing to send.'


def unknown_id_words() -> str:
    """What an unknown, expired or already-completed id answers."""
    return (f"That file is not waiting for your phone any more - the {ttl_label()} "
            "window has passed, or the transfer has already finished. Ask Jarvis "
            "again.")


# ---------------------------------------------------------------------------
#   Small shared helpers
# ---------------------------------------------------------------------------


def _audit(what: str, detail: dict) -> None:
    """One audit line. Name/size/folder only - never a byte of the file."""
    try:
        import jarvis_framework
        jarvis_framework.audit_log("files." + what, detail)
    except Exception:                                       # noqa: BLE001
        pass


def _protection():
    """The "Protected from Jarvis" module, when this backend has it (PR #1019).

    Deliberately a soft hook: this lane is based before that PR exists, so the
    check is asked only when the module is importable, and never duplicated
    here. On a backend without it, the allow-list is still the whole story.
    Looked up by NAME through importlib, not an `import` line: this branch's
    published base must not need a module that PR #1019 has not merged yet
    (test_base_matches_repo's import closure catches a static import).
    """
    try:
        import importlib
        return importlib.import_module("jarvis_protection")
    except Exception:                                       # noqa: BLE001
        return None


def _folders():
    """The owner's listed folders, through jarvis_documents' own door."""
    import jarvis_documents as DOCS
    return list(DOCS.folders())


def _allowed(path, roots=None):
    """(real, root) when `path` may be read, else None - documents' own door."""
    import jarvis_documents as DOCS
    return DOCS.allowed_path(str(path), list(roots) if roots is not None else None)


def _protection_refusal(path) -> str:
    P = _protection()
    if P is None:
        return ""
    try:
        return P.path_refusal(str(path))
    except Exception:                                       # noqa: BLE001
        return ""


def _surface_refusal(headers) -> str:
    """A sentence when this request is the PHONE naming a path, else "".

    `jarvis_surface` reads the `X-Jarvis-Surface` header both clients already
    send, so the button's route stays a desktop door: a phone that learned the
    address still cannot name a filesystem path. An older client, a script or
    a test sends no header and stays `unknown`, which is allowed - the same
    fail-open-to-the-old-behaviour rule that module itself keeps.
    """
    try:
        import jarvis_surface
        surface = jarvis_surface.from_headers(headers)
        phone = getattr(jarvis_surface, "PHONE", "phone")
    except Exception:                                       # noqa: BLE001
        return ""
    return PHONE_SURFACE_WORDS if surface == phone else ""


def _mime_of(name: str) -> str:
    got = mimetypes.guess_type(str(name))[0]
    return got or "application/octet-stream"


def _id() -> str:
    return "file_" + secrets.token_urlsafe(18)


def _now() -> float:
    return time.time()


def _gate(action, detail, prompt):
    """The ONE gate every card goes through, asked from this module's route."""
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    """The tier `What asks first` has for the card; unreadable answers "ask"."""
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception:                                       # noqa: BLE001
        return "ask"


def _spawn(fn) -> None:
    """The card waits on its own thread, so the route answers 202 now."""
    threading.Thread(target=fn, name="jarvis-send-file-card", daemon=True).start()


def _bad(words: str) -> dict:
    """A route refusal: one plain sentence under the keys both callers read."""
    return {"ok": False, "said": words, "error": words, "reason": "not_sent"}


def _prune_locked(now: float) -> None:
    for key in [k for k, v in _files.items() if now >= float(v.get("expires") or 0)]:
        _files.pop(key, None)
    while len(_files) > MAX_PENDING:
        oldest = min(_files, key=lambda k: _files[k]["created"])
        _files.pop(oldest, None)


def _gone(entry: dict, now: float) -> bool:
    """True when this id may not be served any more.

    A consumed id is never served (the entry stays only as the phone's receipt
    tombstone until its own TTL passes). A live id is gone when `expires` has
    passed, and - whatever `expires` says - `GRACE_SECONDS` after the last
    piece was served: that is the Q1 window, so a retry of the last piece
    inside it still works and nothing is served past it.
    """
    if entry.get("used"):
        return True
    if now >= float(entry.get("expires") or 0):
        return True
    final = float(entry.get("final_served_at") or 0)
    return bool(final) and now - final >= GRACE_SECONDS


# ---------------------------------------------------------------------------
#   Search, inside the allow-list only
# ---------------------------------------------------------------------------


def _walks(roots):
    """Every file `allowed_path` says may be read, yielded sparingly."""
    import jarvis_documents as DOCS                     # noqa: F401  (the door)
    roots = [str(r) for r in roots]
    if not roots:
        return
    # The FIRST question to the door pays for importing it and reading the
    # owner's settings - about a second on this PC, and more on a cold or busy
    # one. That is not time spent walking, so warm both soft hooks BEFORE the
    # budget starts; otherwise a slow start can spend the whole `WALK_SECONDS`
    # and answer "no match" from a folder full of files.
    try:
        _protection_refusal(roots[0])
        _allowed(roots[0], roots)
    except Exception:                                   # noqa: BLE001
        pass
    started = time.monotonic()
    seen = 0
    for root in roots:
        base = str(root)
        if _protection_refusal(base):
            continue
        try:
            walker = os.walk(base, followlinks=False)
            for dirpath, dirnames, filenames in walker:
                dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
                for name in sorted(filenames):
                    if name.startswith("."):
                        continue
                    seen += 1
                    if seen > MAX_WALK_FILES or time.monotonic() - started > WALK_SECONDS:
                        return
                    full = os.path.join(dirpath, name)
                    got = _allowed(full, roots)
                    if got is None:
                        continue
                    real = got[0]
                    if _protection_refusal(real):
                        continue
                    try:
                        size = os.path.getsize(real)
                    except OSError:
                        continue
                    yield {"path": real, "folder": base, "name": name, "size": size,
                           "mtime": float(os.path.getmtime(real))}
        except OSError:
            continue


def search(query, *, roots=None, limit: int = SEARCH_LIMIT) -> dict:
    """Files in the listed folders whose name matches every word of `query`.

    No card, no id, no bytes: this is the read-only half the model tool runs
    inside `prepare()` before anything is proposed. A file outside the
    allow-list is never in the answer.
    """
    words = [w for w in str(query or "").casefold().split() if w]
    if not words:
        raise ValueError("say which file to look for, in a few words")
    roots = _folders() if roots is None else list(roots)
    if not roots:
        raise ValueError("There are no folders on your \"Folders Jarvis may look in\" "
                         "list yet, so there is nothing to search. Add one in Settings.")
    found, scanned = [], 0
    for item in _walks(roots):
        scanned += 1
        hay = item["name"].casefold()
        rel = os.path.relpath(item["path"], item["folder"]).replace(os.sep, "/").casefold()
        if all(w in hay or w in rel for w in words):
            found.append(item)
            if len(found) > limit:
                break
    found.sort(key=lambda i: (-i["mtime"], i["path"].casefold()))
    truncated = len(found) > limit
    matches = found[:limit]
    for item in matches:
        item.pop("path", None)                # the model sees name/folder/size only
    return {"ok": bool(matches), "count": len(matches), "matches": matches,
            "scanned": scanned, "truncated": truncated, "roots": [str(r) for r in roots]}


def candidates(query, *, roots=None) -> list:
    """The search, with the real paths kept out of the model-visible answer."""
    roots = _folders() if roots is None else list(roots)
    raw = []
    for item in _walks(roots):
        raw.append(item)
        if len(raw) > MAX_WALK_FILES:
            break                     # _walks already bounds; belt for tests
    words = [w for w in str(query or "").casefold().split() if w]
    if not words:
        raise ValueError("say which file to look for, in a few words")
    hits = [i for i in raw
            if all(w in i["name"].casefold()
                   or w in os.path.relpath(i["path"], i["folder"]).replace(os.sep, "/").casefold()
                   for w in words)]
    hits.sort(key=lambda i: (-i["mtime"], i["path"].casefold()))
    return hits


# ---------------------------------------------------------------------------
#   The one card's candidate
# ---------------------------------------------------------------------------


def _register(item: dict, *, approved: bool = False, chosen: bool = False) -> dict:
    now = _now()
    entry = {"id": _id(), "path": item["path"], "name": item["name"],
             "folder": item["folder"], "size": int(item["size"]),
             "mtime": float(item.get("mtime") or 0),
             "mime": _mime_of(item["name"]), "created": now,
             "expires": now + TTL_SECONDS, "approved": bool(approved),
             "used": False, "chosen": bool(chosen), "sha256": "",
             "final_served_at": 0.0, "acked_at": 0.0}
    with _lock:
        _prune_locked(now)
        _files[entry["id"]] = entry
    return dict(entry)


def _entry(ident: str):
    with _lock:
        entry = _files.get(ident)
        return dict(entry) if entry is not None else None


def _release(ident: str, why: str = "released") -> None:
    """Forget a candidate and anything a phone could have fetched from it."""
    with _lock:
        entry = _files.pop(ident, None)
    if entry is not None:
        _audit(why, {"id": entry["id"], "name": entry["name"],
                     "folder": entry["folder"], "bytes": entry["size"]})


def _for_state(entry: dict) -> dict:
    """The part a tool `state` may carry: no path in the model-visible result."""
    return {k: entry[k] for k in ("id", "name", "folder", "size", "mime")}


def _cap_words(entry: dict) -> str:
    if int(entry["size"]) > CAP_BYTES:
        raise ValueError(no_cap_words(entry["name"], entry["size"]))
    return (f"This sends ONE file at a time and refuses anything over "
            f"{cap_sentence()}; the phone fetches it in {chunk_words()} pieces, and "
            f"each one keeps the link alive for {ttl_words()}. " + transfer_words())


def card_words(entry: dict) -> str:
    """The ONE card's drawn words: exact name, folder, byte size and the cap."""
    return (f'Send "{entry["name"]}" from {entry["folder"]} to your phone? '
            f'It is {entry["size"]:,} bytes ({human_bytes(entry["size"])} large). '
            + _cap_words(entry))


def _ready_words(entry: dict) -> str:
    """What the approved card, and the button's route, say is now waiting."""
    return (f'Ready - "{entry["name"]}" ({entry["size"]:,} bytes) is waiting for your '
            f"phone, fetched in {chunk_words()} pieces. " + transfer_words())


def _list_said() -> str:
    return ("A file appears here only after the owner approved its card; the phone "
            f"fetches it in {chunk_words()} pieces. " + transfer_words())


def _route_said(state: str, entry) -> str:
    """The button route's `said`, by what the card's answer actually was."""
    if state == "approved" and entry is not None:
        return _ready_words(entry)
    if state == "denied":
        return "You said no, so nothing was sent."
    if state == "timed_out":
        return "Nobody answered the card in time, so nothing was sent."
    if state == "refused":
        return "The card could not be answered, so nothing was sent."
    return ("Waiting for you to say yes. Nothing is fetchable until you approve "
            "the card.")


def _person_said_yes(v) -> bool:
    """A card answer is a yes only at tier "ask" and outcome "approved"."""
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


def prepare(args: dict):
    """Tool prepare(): find exactly ONE allowed file and say the card's words.

    Runs before the gate, so a bad query, no match, several matches, an empty
    file or an over-cap file is refused with a plain sentence and NO card.
    `state` carries the candidate's id and display fields; the card is the
    only yes.
    """
    args = args or {}
    query = args.get("query")
    raw_path = args.get("path")
    if raw_path:
        why = _protection_refusal(str(raw_path))
        if why:
            raise ValueError(why)
        got = _allowed(str(raw_path))
        if got is None:
            raise ValueError("That file is not in a folder on your "
                             "\"Folders Jarvis may look in\" list, so it cannot be sent.")
        real, root = got
        probe = {"path": real, "folder": str(root),
                 "name": os.path.basename(real), "size": os.path.getsize(real),
                 "mtime": os.path.getmtime(real)}
        hits = [probe]
    else:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("say which file to send, by its name or a few words of it")
        hits = candidates(query)
        if not hits:
            raise ValueError(NO_SEARCH_WORDS.format(query=query.strip()[:80]))
        if len(hits) > 1:
            names = ", ".join(i["name"] for i in hits[:MAX_NAMES_IN_REFUSAL])
            raise ValueError(f"{len(hits)} files match; say which one to send: {names}. "
                             "Only ONE file is sent per card.")
    entry = hits[0]
    if int(entry["size"]) <= 0:
        raise ValueError(empty_file_words(entry["name"]))
    _cap_words(entry)                                   # over-cap: refuse, no card
    candidate = _register(entry, approved=False)
    return _for_state(candidate), card_words(candidate)


def approve(state: dict) -> dict:
    """Tool execute(): the card said yes, so the id becomes fetchable.

    ONLY reached on an approved verdict. The id's life restarts here, so the
    phone's window begins at the yes.
    """
    ident = str((state or {}).get("id") or "")
    with _lock:
        entry = _files.get(ident)
        if not entry or entry.get("used"):
            raise ValueError(unknown_id_words())
        entry["approved"] = True
        entry["expires"] = _now() + TTL_SECONDS
        _prune_locked(_now())
        public = dict(entry)
    _audit("approved", {"id": public["id"], "name": public["name"],
                        "folder": public["folder"], "bytes": public["size"]})
    return {"ok": True,
            "file": {k: public[k] for k in ("id", "name", "folder", "size", "mime")},
            "said": _ready_words(public)}


# ---------------------------------------------------------------------------
#   The desktop button's route: the owner picked the file in a dialog
# ---------------------------------------------------------------------------


def _ask(ident: str, card: str, detail: dict, *, gate, tier_of,
         seen: dict | None = None) -> None:
    """Raise the ONE card and settle the candidate on its answer.

    A yes makes the id fetchable (`approve`); a denial, a timeout, a refusal
    or a card that could not be asked RELEASES it immediately, so nothing is
    left for a phone to find. `seen` records the outcome for the route's
    `said` when the card settles before the route has answered.
    """
    def note(state: str) -> None:
        if seen is not None:
            seen["state"] = state

    entry = _entry(ident)
    if entry is None or entry.get("approved"):
        return
    try:
        verdict = gate(ACTION, detail, card)
    except Exception:                                       # noqa: BLE001
        note("refused")
        _release(ident, "refused")
        return
    tier = str(getattr(verdict, "tier", "unknown") or "unknown")
    try:
        action_tier = str(tier_of(ACTION))
    except Exception:                                       # noqa: BLE001
        action_tier = "ask"
    if tier != "ask" or action_tier != "ask":
        note("refused")
        _release(ident, "refused")
        return
    if _person_said_yes(verdict):
        try:
            approve({"id": ident})
        except ValueError:
            note("refused")
            return
        note("approved")
        return
    outcome = str(getattr(verdict, "outcome", "") or "")
    state = outcome if outcome in ("denied", "timed_out") else "refused"
    note(state)
    _release(ident, state)


def prepare_route(body, *, gate=None, tier_of=None, spawn=None) -> tuple:
    """POST /api/files/prepare -> (code, body). The desktop button's door.

    The absolute path comes from the owner's own open-file dialog, so this is
    the ONE place a file outside the allow-list may be named - and only one
    file, never a folder. A missing file, a folder, a protected path, an empty
    file or one over `CAP_BYTES` is refused in words BEFORE the card; anything
    else registers the candidate and raises the SAME `send_file_to_phone` card
    (tier "ask") the model tool raises. `202` with `waiting` says the answer is
    still being waited for; a denial or a timeout has released the candidate by
    the time it answers, and nothing is ever fetchable without the yes.
    """
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(body, dict):
        return 400, _bad(NO_PATH_WORDS)
    raw = body.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return 400, _bad(NO_PATH_WORDS)
    chosen = raw.strip()
    if not os.path.isabs(chosen):
        return 400, _bad(NOT_ABSOLUTE_WORDS)
    try:
        real = os.path.realpath(chosen)
    except OSError:
        real = chosen
    if os.path.isdir(real):
        return 400, _bad(FOLDER_WORDS)
    if not os.path.isfile(real):
        return 400, _bad(GONE_WORDS)
    name = os.path.basename(real)
    why = _protection_refusal(real)
    if why:
        return 400, _bad(why)
    try:
        size = int(os.path.getsize(real))
        mtime = float(os.path.getmtime(real))
    except OSError:
        return 400, _bad(GONE_WORDS)
    if size <= 0:
        return 400, _bad(empty_file_words(name))
    if size > CAP_BYTES:
        return 413, _bad(no_cap_words(name, size))

    item = {"path": real, "folder": os.path.dirname(real), "name": name,
            "size": size, "mtime": mtime}
    candidate = _register(item, approved=False, chosen=True)
    card = card_words(candidate)
    detail = {"text": card,
              "what": "send one file to the phone",
              "file": candidate["name"],
              "size": candidate["size"],
              "folder": candidate["folder"],
              "max_bytes": CAP_BYTES,
              "leaves_this_pc": True}
    seen: dict = {}
    try:
        spawn(lambda: _ask(candidate["id"], card, detail, gate=gate,
                           tier_of=tier_of, seen=seen))
    except Exception:                                       # noqa: BLE001
        _release(candidate["id"], "refused")
        return 503, _bad(NO_CARD_WORDS)
    live = _entry(candidate["id"])
    waiting = bool(live is not None and not live.get("approved"))
    state = str(seen.get("state") or ("approved" if not waiting else ""))
    _audit("prepared", {"id": candidate["id"], "name": candidate["name"],
                        "folder": candidate["folder"], "bytes": candidate["size"]})
    return 202, {"ok": True, "waiting": waiting, "id": candidate["id"],
                 "name": candidate["name"], "folder": candidate["folder"],
                 "size": candidate["size"], "mime": candidate["mime"],
                 "said": _route_said(state, live)}


# ---------------------------------------------------------------------------
#   The phone's two routes
# ---------------------------------------------------------------------------


def pending() -> list:
    """Approved, unexpired, unfinished sends, newest first - display fields only.

    A file whose last piece was served stays here for `GRACE_SECONDS` (the
    phone may still be retrying that piece), then it is gone.
    """
    now = _now()
    with _lock:
        _prune_locked(now)
        got = [dict(v) for v in _files.values()
               if v.get("approved") and not _gone(v, now)]
    got.sort(key=lambda v: -v["created"])
    return [{"id": v["id"], "name": v["name"], "folder": v["folder"],
             "size_bytes": v["size"], "mime": v["mime"],
             "expires_in": max(0, int(v["expires"] - now))} for v in got]


def _lookup(ident: str):
    """The live entry for `ident`, or None once it may not be served.

    An expired id is dropped here. A consumed one answers None but is KEPT as
    the phone's receipt tombstone for its own `TTL_SECONDS`, so a receipt that
    arrives twice is idempotent instead of looking unknown.
    """
    with _lock:
        entry = _files.get(ident)
        if not entry:
            return None
        now = _now()
        if _gone(entry, now):
            if not entry.get("used"):
                _files.pop(ident, None)
            return None
        return dict(entry)


def _whole_sha256(path: str, size: int) -> str:
    """The WHOLE file's hash, read in pieces so a big file is never held."""
    digest = hashlib.sha256()
    left = int(size)
    with open(path, "rb") as fh:
        while left > 0:
            block = fh.read(min(CHUNK_BYTES, left))
            if not block:
                break
            digest.update(block)
            left -= len(block)
    return digest.hexdigest()


def _query_number(params: dict, key: str):
    """(ok, value): absent -> (True, None); present must be a whole number."""
    if key not in params:
        return True, None
    raw = (params.get(key) or [""])[0].strip()
    if not re.fullmatch(r"[0-9]+", raw):
        return False, None
    return True, int(raw)


def download(ident, offset=None, length=None) -> tuple:
    """(http code, body) for one piece of GET /api/files/download.

    `offset` defaults to 0, `length` to `CHUNK_BYTES` and is clamped to both
    `CHUNK_BYTES` and the bytes left. `sha256` is the WHOLE file's lowercase
    hex (cached on the id, re-checked against the file's size and mtime on
    every request) and `chunk_sha256` is this piece's. The last piece does not
    consume the id: it marks `final_served_at` and holds the id for
    `GRACE_SECONDS`, and serving it again re-arms that window - so a dropped
    link can retry the last piece. The phone's receipt (`acknowledge`) consumes
    the id, or the grace runs out.
    """
    ident = str(ident or "").strip()
    if not re.fullmatch(r"file_[A-Za-z0-9_-]{16,64}", ident):
        return 404, {"ok": False, "error": unknown_id_words()}
    entry = _lookup(ident)
    if entry is None or not entry.get("approved"):
        return 404, {"ok": False, "error": unknown_id_words()}
    try:
        start = 0 if offset is None else int(offset)
        want = CHUNK_BYTES if length is None else int(length)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": BAD_NUMBERS_WORDS}
    if start < 0 or want < 1:
        return 400, {"ok": False, "error": BAD_NUMBERS_WORDS}
    want = min(want, CHUNK_BYTES)

    path = entry["path"]
    if entry.get("chosen"):
        real = path
        if _protection_refusal(real):
            _release(ident, "gone")
            return 404, {"ok": False, "error": GONE_WORDS}
    else:
        got = _allowed(path)
        if got is None or _protection_refusal(path):
            _release(ident, "gone")
            return 404, {"ok": False, "error": GONE_WORDS}
        real = got[0]
    try:
        size = int(os.path.getsize(real))
        mtime = float(os.path.getmtime(real))
    except FileNotFoundError:
        _release(ident, "gone")
        return 404, {"ok": False, "error": GONE_WORDS}
    except OSError:
        return 503, {"ok": False, "error": READ_FAILED_WORDS}
    if size != int(entry["size"]) or mtime != float(entry.get("mtime") or 0):
        # The file changed since the card. Nothing is served, and the id is
        # NOT consumed: only the phone's receipt (or the grace) ends it.
        with _lock:
            live = _files.get(ident)
            if live is not None:
                live["sha256"] = ""
        return 409, {"ok": False, "error": CHANGED_WORDS}
    if offset is None and length is None and size > CHUNK_BYTES:
        return 400, {"ok": False, "error": PIECES_WORDS}
    if start >= size:
        return 416, {"ok": False, "error": PAST_END_WORDS}
    take = min(want, size - start)
    try:
        with open(real, "rb") as fh:
            fh.seek(start)
            data = fh.read(take)
    except FileNotFoundError:
        _release(ident, "gone")
        return 404, {"ok": False, "error": GONE_WORDS}
    except OSError:
        return 503, {"ok": False, "error": READ_FAILED_WORDS}
    if len(data) != take:
        return 409, {"ok": False, "error": CHANGED_WORDS}
    whole = str(entry.get("sha256") or "")
    if not whole:
        try:
            whole = _whole_sha256(real, size)
        except OSError:
            return 503, {"ok": False, "error": READ_FAILED_WORDS}
        try:
            if int(os.path.getsize(real)) != size:
                return 409, {"ok": False, "error": CHANGED_WORDS}
        except OSError:
            _release(ident, "gone")
            return 404, {"ok": False, "error": GONE_WORDS}
        with _lock:
            live = _files.get(ident)
            if live is None or live.get("used"):
                return 404, {"ok": False, "error": unknown_id_words()}
            live["sha256"] = whole
    last = start + take >= size
    now = _now()
    with _lock:
        live = _files.get(ident)
        if live is None or _gone(live, now):
            return 404, {"ok": False, "error": unknown_id_words()}
        live["expires"] = now + TTL_SECONDS
        if last:
            # Gemini Q1: the last piece does NOT consume the id. It starts the
            # grace window, and serving this same last piece again re-arms it,
            # so a lost 200 is retried instead of costing a whole 2 GiB again.
            live["final_served_at"] = now
            live["expires"] = now + GRACE_SECONDS
    _audit("downloaded" if last else "piece",
           {"id": ident, "name": entry["name"], "offset": start, "bytes": len(data)})
    return 200, {"ok": True, "id": ident, "name": entry["name"], "size_bytes": size,
                 "mime": entry["mime"], "offset": start, "length": len(data),
                 "sha256": whole,
                 "chunk_sha256": hashlib.sha256(data).hexdigest(),
                 "data": base64.b64encode(data).decode("ascii")}


def acknowledge(body) -> tuple:
    """POST /api/files/ack -> (code, body). The PHONE's receipt, never bytes.

    The phone verifies the whole file's SHA-256 first and only then sends this
    receipt, so the route takes the transfer's id and nothing else: never a
    path, and never a byte of the file. Codes:

      - `200 {"ok": true, "said"}` when the receipt consumes the id, i.e. the
        last piece had been served (`final_served_at`) - and the same `200`
        with "already finished" words when the very same receipt arrives
        again, so a retried receipt is never an error;
      - `409 {"ok": false, "error"}` before the whole file has arrived, because
        there is nothing to confirm yet;
      - `404 {"ok": false, "error"}` for an unknown, expired or already-received
        id, in the same plain sentence the download uses.

    A `path` in the body is refused `400`: this route never accepts a path.
    """
    if not isinstance(body, dict) or "path" in body:
        words = ACK_PATH_WORDS if isinstance(body, dict) else ACK_NO_ID_WORDS
        return 400, {"ok": False, "error": words}
    ident = str(body.get("id") or "").strip()
    if not ident:
        return 400, {"ok": False, "error": ACK_NO_ID_WORDS}
    with _lock:
        entry = _files.get(ident)
        now = _now()
        if entry is not None and entry.get("used"):
            if now >= float(entry.get("expires") or 0):
                _files.pop(ident, None)
                return 404, {"ok": False, "error": unknown_id_words()}
            public = dict(entry)
            code, out, first = 200, {"ok": True, "said": ACK_ALREADY_WORDS}, False
        elif entry is None:
            return 404, {"ok": False, "error": unknown_id_words()}
        elif _gone(entry, now):
            _files.pop(ident, None)
            return 404, {"ok": False, "error": unknown_id_words()}
        elif not float(entry.get("final_served_at") or 0):
            return 409, {"ok": False, "error": ACK_NOT_FINISHED_WORDS}
        else:
            entry["used"] = True
            entry["acked_at"] = now
            entry["expires"] = now + TTL_SECONDS   # the receipt tombstone's own life
            public = dict(entry)
            code, out, first = 200, {"ok": True, "said": ACK_DONE_WORDS}, True
    _audit("acked" if first else "ack_again",
           {"id": public["id"], "name": public["name"], "folder": public["folder"],
            "bytes": public["size"]})
    return code, out


def handle_get(path: str, query: str = "") -> tuple:
    """One GET route -> (code, body). Routes take an id and numbers, never a path."""
    route = urlsplit(str(path or "")).path.rstrip("/")
    if route == LIST_PATH:
        files = pending()
        return 200, {"ok": True, "count": len(files), "files": files,
                     "cap_bytes": CAP_BYTES, "chunk_bytes": CHUNK_BYTES,
                     "ttl_seconds": TTL_SECONDS, "single_use": True,
                     "said": _list_said()}
    if route == DOWNLOAD_PATH:
        try:
            params = parse_qs(str(query or "").lstrip("?"), keep_blank_values=True)
        except Exception:                                   # noqa: BLE001
            params = {}
        ident = (params.get("id") or [""])[0]
        if not ident:
            return 400, {"ok": False, "error": NO_ID_WORDS}
        ok_offset, offset = _query_number(params, "offset")
        ok_length, length = _query_number(params, "length")
        if not (ok_offset and ok_length):
            return 400, {"ok": False, "error": BAD_NUMBERS_WORDS}
        return download(ident, offset=offset, length=length)
    return 404, {"ok": False, "error": UNKNOWN_ROUTE_WORDS}


def handle_post(route: str, body, *, gate=None, tier_of=None, spawn=None) -> tuple:
    """One POST route -> (code, body).

    Two doors: the desktop button's `prepare` (a path, a card) and the phone's
    `ack` (an id, a receipt). Nothing else is a POST here.
    """
    route = urlsplit(str(route or "")).path.rstrip("/")
    if route == ACK_PATH:
        return acknowledge(body)
    if route != PREPARE_PATH:
        return 404, _bad(UNKNOWN_ROUTE_WORDS)
    return prepare_route(body, gate=gate, tier_of=tier_of, spawn=spawn)


# ---------------------------------------------------------------------------
#   install(): the drop-in loader's convention (plugins/ready/send-file)
# ---------------------------------------------------------------------------


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the core's Handler with these four routes.

    The two GETs are the phone's, `POST /api/files/ack` is the phone's receipt,
    and `POST /api/files/prepare` is the desktop button's; all four sit after
    the server's own origin and token checks - the SAME pair every other
    phone-facing route uses (the pairing token and `X-Jarvis-Client`); this
    module adds no new auth scheme. Only the button's route additionally
    refuses a request that says it comes from the phone, because only the
    desktop dialog may name a path; the phone's receipt is deliberately NOT
    refused, since the phone is the one that sends it. Every other request goes
    straight to the original handler, so nothing in the core changes.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if (getattr(get0, "_jarvis_send_file", False)
            and getattr(post0, "_jarvis_send_file", False)):
        return ("  send-file  send one file to the phone, and send a file picked on "
                "this PC (already on)")

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:                                   # noqa: BLE001
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    if not getattr(get0, "_jarvis_send_file", False):
        def do_GET(self):
            parts = urlsplit(str(getattr(self, "path", "") or ""))
            if parts.path.rstrip("/") not in GET_PATHS:
                return get0(self)
            if not _allowed(self):
                return None
            try:
                code, out = handle_get(parts.path, parts.query)
            except Exception as exc:                        # noqa: BLE001
                code, out = 503, {"ok": False, "error": type(exc).__name__}
            return self._send(code, out)

        do_GET._jarvis_send_file = True                     # type: ignore[attr-defined]
        handler_cls.do_GET = do_GET

    if not getattr(post0, "_jarvis_send_file", False):
        def do_POST(self):
            parts = urlsplit(str(getattr(self, "path", "") or ""))
            if parts.path.rstrip("/") not in POST_PATHS:
                return post0(self)
            if not _allowed(self):
                return None
            if parts.path.rstrip("/") == PREPARE_PATH:
                # Only the path-naming door is the desktop's. The phone's
                # receipt (`ack`) must accept `X-Jarvis-Surface: phone`, which
                # is the surface that sends it.
                why = _surface_refusal(getattr(self, "headers", None))
                if why:
                    return self._send(403, _bad(why))
            try:
                body = json.loads(read_body(self) or b"")
            except Exception:                               # noqa: BLE001
                return self._send(400, _bad(BAD_BODY_WORDS))
            try:
                code, out = handle_post(parts.path, body)
            except Exception:                               # noqa: BLE001
                code, out = 503, _bad(BROKEN_WORDS)
            return self._send(code, out)

        do_POST._jarvis_send_file = True                    # type: ignore[attr-defined]
        handler_cls.do_POST = do_POST

    return ("  send-file  send one file from your listed folders (or one picked on "
            "this PC) to the phone: one card, a piece at a time, one completed "
            "transfer")


def _reset_for_tests() -> None:
    with _lock:
        _files.clear()
