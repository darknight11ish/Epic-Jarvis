"""jarvis_send_file.py - send ONE file from the owner's own listed folders to
the Jarvis phone app, after ONE approval card, without ever putting a raw path
on the phone's route.

THE OWNER'S REQUEST (2026-10-31, their own words): *"am i able to ask jarvis to
search for a file for me and send it to the jarvis android app to view and or
download directly? this would be a file on the desktop"*.

Gemini ruled on it the same day (Q7): build the bounded "send file to phone"
slice, NOT a text-only halfway step and NOT a "share folder" the owner has to
fill by hand at the PC. This module is the backend half:

  1. SEARCH reuses the existing "Folders Jarvis may look in" allow-list
     (`jarvis_documents.folders()` + `jarvis_documents.allowed_path()`), so a
     file outside it is never a candidate. When the "Protected from Jarvis"
     module (PR #1019, not on this tree yet) is importable, its ONE keep-out
     check is asked as a soft hook - this module never duplicates it.
  2. Each candidate gets an EPHEMERAL opaque `file_id` (random, in memory,
     `TTL_SECONDS` = 10 minutes, at most `MAX_PENDING` alive, cleared on
     restart). The phone route takes the id, NEVER a path parameter.
  3. The model tool `send_file_to_phone` is the ONE card: the gate action is
     `send_file_to_phone` (tier "ask"; an unclassified action is forced to ask
     and carries the gate's own outbound worst-case risk line, because a file
     leaving the PC's own folders for the phone's storage can still be copied
     off the phone afterwards). The card's words show the EXACT filename, the
     folder it came from, its byte size, the cap and the life of the link.
  4. NOTHING is fetchable until the card's yes. After approval the phone lists
     it (`GET /api/files/send`) and fetches the bytes by id
     (`GET /api/files/download?id=<file_id>`), base64 in JSON, the same shape
     `/api/pictures/file` already uses. A fetched id is used up (single use) -
     a second fetch answers 404 in plain words; so does an expired or unknown
     id, and a file that vanished between the card and the fetch.

WHAT IT WILL NOT DO

  - Read outside the allow-list, ever: every candidate goes through
    `jarvis_documents.allowed_path()`, which is the same door `my_files` and
    the folders settings use (no hidden folders, no private places, links
    followed).
  - Send more than ONE file per card, more than ONE card at a time, or a file
    over `CAP_BYTES` = 10 MiB - a bigger file is refused in words before the
    card, never silently truncated.
  - Put a path on the phone's route or in the fetch answer: the route takes an
    id; list answers carry the filename, folder and size for the app's own
    display, and the fetch answer carries only the name, size, MIME type and
    the bytes.
  - Run when the gate cannot answer: the tool goes through `jarvis_gate.check`
    like every other tool (`prepare` refuses a bad/oversize/missing file
    BEFORE the card; `execute` only runs on an approved verdict).
  - Read or write anything about the pairing token, open a tunnel, or touch
    the network. The routes are local, behind the core's own origin + token
    checks (`X-Jarvis-Client` + token, exactly like `/api/protection` and
    `/api/pictures/file`).

NAMED LIMITS (also in docs/JARVIS-API.md section 172)

  - one file per card, one card at a time;
  - `TTL_SECONDS` (10 minutes) from the card's yes, then the id is gone;
  - single use: a successful fetch consumes the id;
  - `CAP_BYTES` = 10,485,760 bytes (10 MiB); over it is a plain refusal;
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

#: One file per card, at most 10 MiB of bytes (Gemini Q7's 10-25 MB range; ten
#: is the number this slice promises). Over the cap is refused in words in
#: `prepare`, so no card is ever raised for a file that could not be sent.
CAP_BYTES = 10 * 1024 * 1024

#: How long an id lives after the card's yes (and how long a candidate id may
#: wait for its card). Ten minutes is long enough to pick up the phone and
#: short enough that an id left in a log is worthless.
TTL_SECONDS = 10 * 60

#: At most this many ids in memory at once. The oldest is dropped, so a long
#: day of asking cannot grow here.
MAX_PENDING = 8

#: How many names a search returns before it says "narrow it down".
SEARCH_LIMIT = 20

#: Bounds for the walk: enough for a normal listed folder, small enough that a
#: huge tree cannot make one model call read a whole drive.
MAX_WALK_FILES = 5000
WALK_SECONDS = 2.0

#: The gate action the ONE card is asked under. The shipped
#: `jarvis-framework.toml` (both copies) carries `send_file_to_phone = "ask"`;
#: the gate forces "ask" for an unclassified action even if that line went
#: missing, and its unknown-action risk line is the outbound one.
ACTION = "send_file_to_phone"

#: The routes. No route below takes a filesystem path.
LIST_PATH = "/api/files/send"
DOWNLOAD_PATH = "/api/files/download"
GET_PATHS = (LIST_PATH, DOWNLOAD_PATH)

#: How many names a refusal may quote back to the model/owner.
MAX_NAMES_IN_REFUSAL = 8

_REFUSED = {
    "no_vault": ("No files can be sent: {why}."),
}
UNKNOWN_ID_WORDS = ("That file is not waiting for your phone any more - the ten-minute "
                    "window has passed, or it has already been downloaded. Ask Jarvis again.")
GONE_WORDS = "That file is not on this PC any more, so there is nothing to send."
CHANGED_WORDS = ("That file changed since the card was approved, so nothing was sent. "
                 "Ask Jarvis again.")
NO_CAP_WORDS = ("{name} is {size} bytes, over the 10 MiB (10,485,760 bytes) this "
                "slice can send. Nothing was sent and no card was raised.")
NO_SEARCH_WORDS = ("No file in your listed folders matches {query!r}. Nothing was sent.")

_lock = threading.Lock()
_files: dict = {}           # id -> {id, path, name, folder, size, mime, created, expires, approved, used}


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


def human_bytes(n: int) -> str:
    """A byte count the owner can read, exact bytes in brackets by callers."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "an unknown size of"
    if n < 1024:
        return f"{n} bytes"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


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


def _mime_of(name: str) -> str:
    got = mimetypes.guess_type(str(name))[0]
    return got or "application/octet-stream"


def _id() -> str:
    return "file_" + secrets.token_urlsafe(18)


def _now() -> float:
    return time.time()


def _prune_locked(now: float) -> None:
    for key in [k for k, v in _files.items() if now >= float(v.get("expires") or 0)]:
        _files.pop(key, None)
    while len(_files) > MAX_PENDING:
        oldest = min(_files, key=lambda k: _files[k]["created"])
        _files.pop(oldest, None)


# ---------------------------------------------------------------------------
#   Search, inside the allow-list only
# ---------------------------------------------------------------------------


def _walks(roots):
    """Every file `allowed_path` says may be read, yielded sparingly."""
    import jarvis_documents as DOCS                     # noqa: F401  (the door)
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


def _register(item: dict, *, approved: bool = False) -> dict:
    now = _now()
    entry = {"id": _id(), "path": item["path"], "name": item["name"],
             "folder": item["folder"], "size": int(item["size"]),
             "mime": _mime_of(item["name"]), "created": now,
             "expires": now + TTL_SECONDS, "approved": bool(approved),
             "used": False}
    with _lock:
        _prune_locked(now)
        _files[entry["id"]] = entry
    return dict(entry)


def _for_state(entry: dict) -> dict:
    """The part a tool `state` may carry: no path in the model-visible result."""
    return {k: entry[k] for k in ("id", "name", "folder", "size", "mime")}


def _cap_words(entry: dict) -> str:
    if entry["size"] > CAP_BYTES:
        raise ValueError(NO_CAP_WORDS.format(name=entry["name"],
                                             size=f"{entry['size']:,}"))
    return ("This slice sends ONE file at a time and refuses anything over 10 MiB "
            "(10,485,760 bytes); the link lasts 10 minutes and works once.")


def card_words(entry: dict) -> str:
    """The ONE card's drawn words: exact name, folder, byte size and the cap."""
    return (f'Send "{entry["name"]}" from {entry["folder"]} to your phone? '
            f'It is {entry["size"]:,} bytes ({human_bytes(entry["size"])} large). '
            + _cap_words(entry))


def prepare(args: dict):
    """Tool prepare(): find exactly ONE allowed file and say the card's words.

    Runs before the gate, so a bad query, no match, several matches or an
    over-cap file is refused with a plain sentence and NO card. `state` carries
    the candidate's id and display fields; the card is the only yes.
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
    said = _cap_words(entry)
    candidate = _register(entry, approved=False)
    return _for_state(candidate), card_words(candidate)


def approve(state: dict) -> dict:
    """Tool execute(): the card said yes, so the id becomes fetchable.

    ONLY reached on an approved verdict (`_one_call` calls execute only then).
    The id's life restarts here, so the phone's ten minutes begin at the yes.
    """
    ident = str((state or {}).get("id") or "")
    with _lock:
        entry = _files.get(ident)
        if not entry:
            raise ValueError(UNKNOWN_ID_WORDS)
        entry["approved"] = True
        entry["expires"] = _now() + TTL_SECONDS
        _prune_locked(_now())
        public = dict(entry)
    _audit("approved", {"id": public["id"], "name": public["name"],
                        "folder": public["folder"], "bytes": public["size"]})
    return {"ok": True,
            "file": {k: public[k] for k in ("id", "name", "folder", "size", "mime")},
            "said": (f"Ready - \"{public['name']}\" ({public['size']:,} bytes) is waiting "
                     f"for your phone for ten minutes. It can be downloaded once.")}


# ---------------------------------------------------------------------------
#   The phone's two routes
# ---------------------------------------------------------------------------


def pending() -> list:
    """Approved, unexpired, unused sends, newest first - display fields only."""
    now = _now()
    with _lock:
        _prune_locked(now)
        got = [dict(v) for v in _files.values()
               if v.get("approved") and not v.get("used") and now < v["expires"]]
    got.sort(key=lambda v: -v["created"])
    return [{"id": v["id"], "name": v["name"], "folder": v["folder"],
             "size_bytes": v["size"], "mime": v["mime"],
             "expires_in": max(0, int(v["expires"] - now))} for v in got]


def _lookup(ident: str):
    with _lock:
        entry = _files.get(ident)
        if not entry:
            return None
        now = _now()
        if now >= float(entry.get("expires") or 0) or entry.get("used"):
            _files.pop(ident, None)
            return None
        return dict(entry)


def download(ident) -> tuple:
    """(http code, body) for GET /api/files/download?id=<file_id>."""
    ident = str(ident or "").strip()
    if not re.fullmatch(r"file_[A-Za-z0-9_-]{16,64}", ident):
        return 404, {"ok": False, "error": UNKNOWN_ID_WORDS}
    entry = _lookup(ident)
    if entry is None or not entry.get("approved"):
        return 404, {"ok": False, "error": UNKNOWN_ID_WORDS}
    got = _allowed(entry["path"])
    if got is None or _protection_refusal(entry["path"]):
        with _lock:
            _files.pop(ident, None)
        return 404, {"ok": False, "error": GONE_WORDS}
    real = got[0]
    try:
        size = os.path.getsize(real)
        if size > CAP_BYTES:
            return 413, {"ok": False, "error": NO_CAP_WORDS.format(
                name=entry["name"], size=f"{size:,}")}
        if size != int(entry["size"]):
            return 409, {"ok": False, "error": CHANGED_WORDS}
        with open(real, "rb") as fh:
            data = fh.read(CAP_BYTES + 1)
    except FileNotFoundError:
        return 404, {"ok": False, "error": GONE_WORDS}
    except OSError:
        return 503, {"ok": False, "error": "That file could not be read just now, so "
                                           "nothing was sent."}
    if not data or len(data) > CAP_BYTES:
        return 413, {"ok": False, "error": NO_CAP_WORDS.format(
            name=entry["name"], size=f"{len(data):,}")}
    with _lock:
        live = _files.get(ident)
        if live is None or live.get("used"):
            return 404, {"ok": False, "error": UNKNOWN_ID_WORDS}
        live["used"] = True                  # single use: a retry gets 404
    _audit("downloaded", {"id": ident, "name": entry["name"], "bytes": len(data)})
    return 200, {"ok": True, "name": entry["name"], "size_bytes": len(data),
                 "mime": entry["mime"], "sha256": hashlib.sha256(data).hexdigest(),
                 "data": base64.b64encode(data).decode("ascii")}


def handle_get(path: str, query: str = "") -> tuple:
    """One GET route -> (code, body). Routes take an id, never a path."""
    route = urlsplit(str(path or "")).path.rstrip("/")
    if route == LIST_PATH:
        files = pending()
        return 200, {"ok": True, "count": len(files), "files": files,
                     "cap_bytes": CAP_BYTES, "ttl_seconds": TTL_SECONDS,
                     "single_use": True,
                     "said": ("A file appears here only after the owner approved its "
                              "card; it can be downloaded once, within ten minutes.")}
    if route == DOWNLOAD_PATH:
        try:
            ident = (parse_qs(str(query or "").lstrip("?"), keep_blank_values=True)
                     .get("id") or [""])[0]
        except Exception:                                   # noqa: BLE001
            ident = ""
        if not ident:
            return 400, {"ok": False, "error": ("Say which file: ?id=<file_id>. This route "
                                                "never takes a path.")}
        return download(ident)
    return 404, {"ok": False, "error": "no such route"}


# ---------------------------------------------------------------------------
#   install(): the drop-in loader's convention (plugins/ready/send-file)
# ---------------------------------------------------------------------------


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the core's Handler with these two routes.

    After the server's own origin and token checks - the SAME pair every other
    phone-facing route uses (the pairing token and `X-Jarvis-Client`); this
    module adds no new auth scheme. A POST is untouched.
    """
    get0 = handler_cls.do_GET
    if getattr(get0, "_jarvis_send_file", False):
        return "  send-file  send one file to the phone (already on)"

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

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        if parts.path.rstrip("/") not in GET_PATHS:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(parts.path, parts.query)
        except Exception as exc:                            # noqa: BLE001
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_send_file = True
    handler_cls.do_GET = do_GET
    return ("  send-file  send one file from your listed folders to the phone "
            "(one card, ten minutes, one download)")


def _reset_for_tests() -> None:
    with _lock:
        _files.clear()
