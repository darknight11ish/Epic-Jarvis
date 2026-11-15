"""test_send_file_chunked.py - the chunked download and the desktop button's route.

    python -B backend/test_send_file_chunked.py

The owner's 2026-11-14 design (`SEND-TO-PHONE-2GB-DESIGN-2026-11-14.md`)
replaced the one-blob download with a piece at a time, and added a "Send a file
to your phone…" button on the desktop. This suite proves, against temporary
folders (never the owner's):

1. ONE NUMBER. `CAP_BYTES`, `CHUNK_BYTES` and `TTL_SECONDS` are the only places
   the ceiling, the piece size and the window are written: the card, every
   refusal, the list's `cap_bytes`/`chunk_bytes`/`ttl_seconds` and the
   phone-visible words all read them, and the module itself spells none of the
   numbers as a literal.
2. A FILE ACROSS PIECES, with `CHUNK_BYTES` raised or lowered: offset
   arithmetic, the clamp to the bytes left and to one piece, `chunk_sha256` for
   the piece against the whole file's `sha256`, and the exact bytes.
3. THE ONE OLD-CLIENT RULE. A request with no `offset` and no `length` for a
   file bigger than one piece is a 400 in plain words - never a truncated 200,
   because an old phone would save a broken file. A file small enough for one
   piece still answers 200 with the whole file.
4. THE LIFE. Every served piece renews the window; a piece may be retried; the
   LAST piece does NOT consume the id - it stamps `final_served_at` and starts
   `GRACE_SECONDS` (60 s), and serving that same last piece again re-arms the
   window, so a lost 200 is retryable; `409` on a changed file (size or mtime)
   serves nothing and does not consume the id; `416` past the end; `400` for
   numbers that are not integers; `404` for an expired id.
5. THE PHONE'S RECEIPT. `POST /api/files/ack` takes only the transfer's id
   (never a path, never a byte in its answer): `200 {"ok": true, "said"}` when
   it consumes the id, `409 {"ok": false, "error"}` before the whole file has
   arrived, `404` for an unknown/expired id, and the same `200` with "already
   finished" words for a second receipt - never an error. It is the phone's
   route, so `X-Jarvis-Surface: phone` is NOT refused there, unlike the
   button's route.
6. THE BUTTON'S ROUTE. `POST /api/files/prepare` takes the absolute path the
   owner picked in the dialog - including one OUTSIDE the allow-list - refuses
   a missing file, a folder, a relative path, an empty file, a protected path
   and one over the cap in words BEFORE the card, and otherwise raises the
   SAME `send_file_to_phone` card (tier "ask") the model tool raises. A denial,
   a timeout or a refused tier releases the candidate: nothing is fetchable.
   The model tool's own allow-list is unchanged.
7. THE PHONE STILL CANNOT NAME A PATH. The prepare route refuses a request
   whose `X-Jarvis-Surface` says phone, while the receipt does not; all routes
   keep the same origin and token checks every phone route has.

No model, no network, no real folders: a temporary settings folder and a
temporary "Folders Jarvis may look in" folder are used for each run.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.pop("JARVIS_BACKEND", None)

_TMP = Path(tempfile.gettempdir()) / ("jarvis-send-file-chunks-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
CONFIG = _TMP / "config"
CONFIG.mkdir(parents=True, exist_ok=True)
ALLOW = _TMP / "allowed"
ALLOW.mkdir(parents=True, exist_ok=True)
OUTSIDE = _TMP / "outside"
OUTSIDE.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONFIG
FW.LOG_DIR = _TMP / "log"
AUDIT = []
FW.audit_log = lambda event, detail: AUDIT.append((event, detail))
FW.load_framework = lambda: {"notes": {}}
sys.modules["jarvis_framework"] = FW

(CONFIG / "folders.json").write_text(
    json.dumps({"folders": [{"path": str(ALLOW), "name": "mine", "added": time.time()}],
                "changed": time.time()}), encoding="utf-8")

import jarvis_send_file as SF  # noqa: E402

TEN = ALLOW / "ten-bytes.bin"
TEN.write_bytes(bytes(range(10)))
NOTES = ALLOW / "notes.txt"
NOTES.write_text("the notes\n", encoding="utf-8")
PICKED = OUTSIDE / "picked-in-the-dialog.bin"
PICKED.write_bytes(b"picked by the owner, outside every listed folder")
EMPTY = ALLOW / "nothing.txt"
EMPTY.write_bytes(b"")

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    SF._reset_for_tests()
    AUDIT.clear()


def raises(fn, *a, **k) -> str:
    try:
        fn(*a, **k)
        return ""
    except ValueError as exc:
        return str(exc)


def approved(item: dict) -> dict:
    """Register + approve one file directly, as the card's yes would."""
    state, _words = SF.prepare({"path": str(item)})
    SF.approve(state)
    return state


class Piece:
    """Context: patch the four constants for the length of one test."""
    saved = None

    def __init__(self, *, chunk=None, cap=None, ttl=None, grace=None):
        self.chunk, self.cap, self.ttl, self.grace = chunk, cap, ttl, grace

    def __enter__(self):
        self.saved = (SF.CAP_BYTES, SF.CHUNK_BYTES, SF.TTL_SECONDS,
                      SF.GRACE_SECONDS)
        if self.chunk is not None:
            SF.CHUNK_BYTES = self.chunk
        if self.cap is not None:
            SF.CAP_BYTES = self.cap
        if self.ttl is not None:
            SF.TTL_SECONDS = self.ttl
        if self.grace is not None:
            SF.GRACE_SECONDS = self.grace

    def __exit__(self, *exc):
        SF.CAP_BYTES, SF.CHUNK_BYTES, SF.TTL_SECONDS, SF.GRACE_SECONDS = self.saved
        return False


class At:
    """Context: the module's clock reads one fixed epoch second.

    The grace is 60 s and the window is 600 s; a real test cannot sleep for
    either. Patching the module's OWN `_now` keeps every comparison it makes -
    `_lookup`, `pending`, `download`, `acknowledge` - agreeing on one time.
    """
    saved = None

    def __init__(self, when):
        self.when = float(when)

    def __enter__(self):
        self.saved = SF._now
        SF._now = lambda: self.when
        return self

    def __exit__(self, *exc):
        SF._now = self.saved
        return False


# ---------------------------------------------------------------------------
#   1. one number, read everywhere
# ---------------------------------------------------------------------------


def t_the_one_number_is_read_everywhere():
    fresh()
    check("the ceiling is the owner's 2 GiB", SF.CAP_BYTES == 2 * 1024 ** 3, SF.CAP_BYTES)
    check("one piece is 1 MiB", SF.CHUNK_BYTES == 1024 * 1024, SF.CHUNK_BYTES)
    check("the window is 600 seconds", SF.TTL_SECONDS == 600, SF.TTL_SECONDS)
    check("the grace is 60 seconds", SF.GRACE_SECONDS == 60, SF.GRACE_SECONDS)
    check("the cap sentence is built from the constant",
          SF.cap_sentence() == f"{SF.human_bytes(SF.CAP_BYTES)} ({SF.CAP_BYTES:,} bytes)",
          SF.cap_sentence())
    check("the piece, window and grace words are built from the constants",
          SF.chunk_words() == "1 MiB" and SF.ttl_words() == "10 minutes"
          and SF.ttl_label() == "10-minute" and SF.grace_words() == "a minute",
          (SF.chunk_words(), SF.ttl_words(), SF.ttl_label(), SF.grace_words()))
    check("the module has no hand-written copy of a number",
          _module_source_spells_no_number())
    # The same code follows a RAISED set of constants, which is what proves
    # every sentence reads them instead of repeating today's values.
    with Piece(chunk=2 * 1024 * 1024, cap=3 * 1024 ** 3, ttl=120, grace=120):
        check("a raised ceiling reaches the card's words",
              "3 GB" in SF.cap_sentence() and f"{SF.CAP_BYTES:,}" in SF.cap_sentence(),
              SF.cap_sentence())
        check("a raised piece, window and grace reach their words",
              SF.chunk_words() == "2 MiB" and SF.ttl_words() == "2 minutes"
              and SF.ttl_label() == "2-minute" and SF.grace_words() == "2 minutes",
              (SF.chunk_words(), SF.ttl_words(), SF.ttl_label(), SF.grace_words()))
        code, out = SF.handle_get("/api/files/send", "")
        check("the list answers the raised numbers",
              code == 200 and out["cap_bytes"] == 3 * 1024 ** 3
              and out["chunk_bytes"] == 2 * 1024 * 1024
              and out["ttl_seconds"] == 120, out)
        check("the list's own words read them",
              "2 MiB" in out["said"] and "2 minutes" in out["said"]
              and "one completed transfer" in out["said"], out["said"])
        _state, words = SF.prepare({"path": str(TEN)})
        check("the card's words read them too",
              "3 GB" in words and f"{SF.CAP_BYTES:,} bytes" in words
              and "2 MiB" in words and "2 minutes" in words
              and "one completed transfer" in words, words)
    fresh()
    why = raises(SF.prepare, {"query": "nothing"})
    check("an empty file is refused in words, before any card",
          "is empty" in why, why)


#: The literals this module must never spell itself: the ceiling and the piece
#: size, the window, the grace, and the old single-fetch promise. They live
#: ONLY in the constants, so a stale copy cannot survive a change.
def _module_source_spells_no_number() -> bool:
    source = (HERE / "jarvis_send_file.py").read_text(encoding="utf-8")
    return not any(needle in source for needle in (
        "10 MiB", "2 GB", "10,485,760", "2,147,483,648",
        "ten minutes", "10 minutes", "works once",
        "one completed download", "already been downloaded", "60 seconds"))


# ---------------------------------------------------------------------------
#   2. one file cut into pieces
# ---------------------------------------------------------------------------


def t_a_file_cut_into_pieces_is_fetched_piece_by_piece():
    fresh()
    with Piece(chunk=4):
        state = approved(TEN)
        ident = state["id"]
        whole = hashlib.sha256(TEN.read_bytes()).hexdigest()
        code, out = SF.download(ident)
        check("an old client asking for a big file gets 400, never a short 200",
              code == 400 and "bigger than one piece" in out.get("error", ""), (code, out))
        code, first = SF.download(ident, offset=0)
        check("the first piece is exactly one piece, with both hashes",
              code == 200 and first["offset"] == 0 and first["length"] == 4
              and base64.b64decode(first["data"]) == bytes(range(4))
              and first["sha256"] == whole
              and first["chunk_sha256"] == hashlib.sha256(bytes(range(4))).hexdigest()
              and first["size_bytes"] == 10 and first["id"] == ident, first)
        check("nothing is consumed by a piece that is not the last",
              [f["id"] for f in SF.pending()] == [ident], SF.pending())
        code, second = SF.download(ident, offset=4, length=4)
        check("the middle piece answers its own offset",
              code == 200 and second["offset"] == 4 and second["length"] == 4
              and base64.b64decode(second["data"]) == bytes(range(4, 8)), second)
        code, last = SF.download(ident, offset=8, length=4)
        check("the last piece is clamped to the bytes left",
              code == 200 and last["offset"] == 8 and last["length"] == 2
              and base64.b64decode(last["data"]) == bytes(range(8, 10)), last)
        check("the last piece does NOT consume the id - it starts the grace",
              [f["id"] for f in SF.pending()] == [ident]
              and not SF._files[ident].get("used")
              and SF._files[ident].get("final_served_at"), SF.pending())
        code, again = SF.download(ident, offset=8, length=4)
        check("the same last piece is retryable inside the grace",
              code == 200 and again["chunk_sha256"] == last["chunk_sha256"], (code, again))
        code, acked = SF.acknowledge({"id": ident})
        check("the phone's receipt then consumes it",
              code == 200 and "finished" in acked.get("said", ""), (code, acked))
        code, out = SF.download(ident, offset=0)
        check("a fetch after the receipt is the plain 404",
              code == 404 and "already finished" in out.get("error", ""), (code, out))


# ---------------------------------------------------------------------------
#   3. offset and length arithmetic
# ---------------------------------------------------------------------------


def t_offset_and_length_arithmetic():
    fresh()
    with Piece(chunk=4):
        state = approved(TEN)
        ident = state["id"]
        code, out = SF.download(ident, offset=0, length=99)
        check("length is never more than one piece",
              code == 200 and out["length"] == min(99, SF.CHUNK_BYTES) == 4, (code, out))
        code, out = SF.download(ident, offset=9, length=4)
        check("a start on the last byte serves one byte and finishes the file",
              code == 200 and out["length"] == 1
              and base64.b64decode(out["data"]) == b"\x09"
              and SF._files[ident].get("final_served_at"), (code, out))
        state = approved(TEN)
        ident = state["id"]
        code, out = SF.download(ident, offset=3, length=4)
        check("a middle slice starts where it was asked to",
              code == 200 and out["offset"] == 3 and out["length"] == 4
              and base64.b64decode(out["data"]) == bytes(range(3, 7)), (code, out))
        code, out = SF.download(ident, offset=7, length=4)
        check("... and the next one is clamped to the bytes left",
              code == 200 and out["offset"] == 7 and out["length"] == 3,
              (code, out))
        state = approved(TEN)
        ident = state["id"]
        for offset in (10, 11, 999):
            code, out = SF.download(ident, offset=offset)
            check(f"offset {offset} is 416 past the end",
                  code == 416 and "past the end" in out.get("error", ""), (code, out))
        for label, kwargs in (("negative offset", {"offset": -1}),
                              ("zero length", {"offset": 0, "length": 0}),
                              ("negative length", {"offset": 0, "length": -4})):
            code, out = SF.download(ident, **kwargs)
            check(f"{label} is 400, not a guess",
                  code == 400 and "whole numbers" in out.get("error", ""), (code, out))

    # The query strings the phone actually sends.
    fresh()
    with Piece(chunk=4):
        state = approved(TEN)
        ident = state["id"]
        code, out = SF.handle_get(SF.DOWNLOAD_PATH, f"id={ident}&offset=abc")
        check("a non-integer offset on the wire is 400",
              code == 400 and "whole numbers" in out.get("error", ""), (code, out))
        code, out = SF.handle_get(SF.DOWNLOAD_PATH, f"id={ident}&length=1.5")
        check("a fractional length on the wire is 400", code == 400, (code, out))
        code, out = SF.handle_get(SF.DOWNLOAD_PATH, f"id={ident}&offset=")
        check("a blank offset on the wire is 400, not a whole-file read",
              code == 400, (code, out))
        code, out = SF.handle_get(SF.DOWNLOAD_PATH, f"id={ident}&offset=0&length=4")
        check("offset and length on the wire select the piece",
              code == 200 and out["offset"] == 0 and out["length"] == 4, (code, out))
        code, out = SF.handle_get(SF.DOWNLOAD_PATH, f"id={ident}&offset=4")
        check("offset alone takes the default piece size",
              code == 200 and out["offset"] == 4 and out["length"] == 4, (code, out))


def t_the_wire_shapes_are_the_contract():
    fresh()
    with Piece(chunk=4):
        state = approved(TEN)
        code, out = SF.download(state["id"], offset=0)
        check("the download answer has exactly the contract's keys",
              code == 200 and set(out) == {
                  "ok", "id", "name", "size_bytes", "mime", "offset", "length",
                  "sha256", "chunk_sha256", "data"}, sorted(out))
        check("... and it carries no folder or path",
              "folder" not in out and "path" not in out
              and str(ALLOW) not in json.dumps({k: v for k, v in out.items()
                                                if k != "data"}), sorted(out))
        code, out = SF.handle_get(SF.LIST_PATH, "")
        check("the list answer has exactly the contract's keys",
              code == 200 and set(out) == {
                  "ok", "count", "files", "cap_bytes", "chunk_bytes",
                  "ttl_seconds", "single_use", "said"}, sorted(out))
        check("the list's file entry has exactly the contract's keys",
              set(out["files"][0]) == {"id", "name", "folder", "size_bytes",
                                       "mime", "expires_in"}, sorted(out["files"][0]))
        fresh()
        code, out = approach({"path": str(PICKED)}, gate=card_gate())
        check("the button's 202 has exactly the contract's keys",
              code == 202 and set(out) == {
                  "ok", "waiting", "id", "name", "folder", "size", "mime", "said"},
              sorted(out))


# ---------------------------------------------------------------------------
#   4. the life: retries, renewal, 409, expiry
# ---------------------------------------------------------------------------


def t_every_piece_renews_the_life_and_retries_work():
    fresh()
    with Piece(chunk=4):
        state = approved(TEN)
        ident = state["id"]
        SF._files[ident]["expires"] = time.time() + 1
        code, first = SF.download(ident, offset=0)
        renewed = SF._files[ident]["expires"] - time.time()
        check("a served piece starts the window again",
              code == 200 and renewed > SF.TTL_SECONDS - 5, (code, renewed))
        code, again = SF.download(ident, offset=0)
        check("the same piece may be retried before the last one",
              code == 200 and again["chunk_sha256"] == first["chunk_sha256"]
              and [f["id"] for f in SF.pending()] == [ident], (code, again))
        code, out = SF.download(ident, offset=4)
        check("the next piece is still there", code == 200, (code, out))
        code, last = SF.download(ident, offset=8)
        check("the last piece serves and starts the grace",
              code == 200 and last["length"] == 2
              and [f["id"] for f in SF.pending()] == [ident], (code, last))
        code, retry = SF.download(ident, offset=8)
        check("... so the last piece can be asked for again",
              code == 200 and retry["length"] == 2, (code, retry))
        code, acked = SF.acknowledge({"id": ident})
        check("the receipt consumes it", code == 200, (code, acked))
        check("after the receipt every piece is 404",
              SF.download(ident, offset=0)[0] == 404
              and SF.download(ident, offset=8)[0] == 404)

        state = approved(TEN)
        ident = state["id"]
        SF._files[ident]["expires"] = time.time() - 1
        code, out = SF.download(ident, offset=0)
        check("an expired id is 404 before its first piece",
              code == 404 and "not waiting for your phone" in out.get("error", ""),
              (code, out))


def t_a_changed_file_is_409_and_is_never_served():
    fresh()
    with Piece(chunk=4):
        changed = ALLOW / "changed-size.bin"
        changed.write_bytes(bytes(range(10)))
        state = approved(changed)
        ident = state["id"]
        check("the first piece of the file is served", SF.download(ident, offset=0)[0] == 200)
        changed.write_bytes(bytes(range(11)))            # size changed since the card
        code, out = SF.download(ident, offset=4)
        check("a file whose SIZE changed is 409 and serves nothing",
              code == 409 and "changed since the card" in out.get("error", "")
              and "data" not in out, (code, out))
        check("a 409 does not consume the id (only the last piece does)",
              ident in SF._files and [f["id"] for f in SF.pending()] == [ident],
              SF.pending())
        changed.unlink()
        code, out = SF.download(ident, offset=4)
        check("a file that vanished afterwards is 404 with plain words",
              code == 404 and "nothing to send" in out.get("error", ""), (code, out))

        touched = ALLOW / "touched-mtime.bin"
        touched.write_bytes(bytes(range(10)))
        state = approved(touched)
        ident = state["id"]
        check("the first piece of the untouched file is served",
              SF.download(ident, offset=0)[0] == 200)
        later = time.time() + 50
        os.utime(touched, (later, later))                 # same size, new mtime
        code, out = SF.download(ident, offset=4)
        check("a file whose MTIME changed is 409 too",
              code == 409 and "changed since the card" in out.get("error", ""), (code, out))


# ---------------------------------------------------------------------------
#   5. an old client never gets a truncated file
# ---------------------------------------------------------------------------


def t_an_old_client_never_gets_a_truncated_file():
    fresh()
    bigger = ALLOW / "bigger-than-a-piece.bin"
    body = bytes(range(256)) * (SF.CHUNK_BYTES // 256) + b"tail"
    bigger.write_bytes(body)
    state = approved(bigger)
    ident = state["id"]
    whole = hashlib.sha256(body).hexdigest()
    code, out = SF.download(ident)
    check("no offset and no length for a big file is 400 with one plain sentence",
          code == 400 and out.get("error") == SF.PIECES_WORDS, (code, out))
    code, out = SF.download(ident, offset=0)
    check("offset 0 alone gets exactly one piece",
          code == 200 and out["offset"] == 0 and out["length"] == SF.CHUNK_BYTES
          and len(base64.b64decode(out["data"])) == SF.CHUNK_BYTES
          and out["size_bytes"] == len(body) and out["sha256"] == whole
          and out["chunk_sha256"] != whole, (code, out.get("length")))
    code, out = SF.download(ident, length=SF.CHUNK_BYTES)
    check("a length with no offset is a deliberate slice, not an old client",
          code == 200 and out["offset"] == 0 and out["length"] == SF.CHUNK_BYTES,
          (code, out))
    code, out = SF.download(ident, offset=SF.CHUNK_BYTES)
    check("the last piece is the bytes left, with the whole file's hash",
          code == 200 and out["offset"] == SF.CHUNK_BYTES and out["length"] == 4
          and base64.b64decode(out["data"]) == b"tail" and out["sha256"] == whole,
          (code, out))
    check("and that last piece leaves the id in the grace window",
          SF.download(ident, offset=SF.CHUNK_BYTES)[0] == 200
          and SF.pending() != [], SF.pending())
    check("the receipt consumes the transfer", SF.acknowledge({"id": ident})[0] == 200)
    check("after the receipt the id is a plain 404", SF.download(ident)[0] == 404)

    exact = ALLOW / "exactly-one-piece.bin"
    exact.write_bytes(b"z" * SF.CHUNK_BYTES)
    state = approved(exact)
    code, out = SF.download(state["id"])
    check("a file of exactly one piece still answers 200 whole",
          code == 200 and out["length"] == SF.CHUNK_BYTES
          and out["sha256"] == out["chunk_sha256"], (code, out.get("length")))
    check("... and it is not consumed until the phone's receipt",
          SF.download(state["id"])[0] == 200
          and SF.acknowledge({"id": state["id"]})[0] == 200
          and SF.download(state["id"])[0] == 404)


# ---------------------------------------------------------------------------
#   6. the last piece's grace, and the phone's receipt
# ---------------------------------------------------------------------------


def t_the_last_piece_leaves_a_grace_window():
    fresh()
    with Piece(chunk=4):
        base = time.time()
        state = approved(TEN)
        ident = state["id"]
        SF.download(ident, offset=0, length=4)
        SF.download(ident, offset=4, length=4)
        code, last = SF.download(ident, offset=8, length=4)
        entry = SF._files[ident]
        check("the last piece is served",
              code == 200 and last["length"] == 2, (code, last))
        check("the last piece does NOT consume the id",
              ident in SF._files and not entry.get("used"), entry)
        check("... it stamps final_served_at",
              abs(float(entry["final_served_at"]) - base) < 5,
              entry.get("final_served_at"))
        check("... and its expiry becomes the grace, not the TTL",
              abs(float(entry["expires"])
                  - (float(entry["final_served_at"]) + SF.GRACE_SECONDS)) < 0.01,
              entry["expires"])
        check("the phone's list still shows it inside the grace",
              [f["id"] for f in SF.pending()] == [ident], SF.pending())
        # A retry of the last piece 10 s later is served AND re-arms both
        # fields, so the retry that matters lands inside a fresh window.
        with At(base + 10):
            code, retry = SF.download(ident, offset=8, length=4)
            entry = SF._files[ident]
            check("a retry of the last piece inside the grace is 200",
                  code == 200 and retry["length"] == 2, (code, retry))
            check("... and it re-arms final_served_at and expires together",
                  abs(float(entry["final_served_at"]) - (base + 10)) < 0.01
                  and abs(float(entry["expires"])
                          - (base + 10 + SF.GRACE_SECONDS)) < 0.01,
                  (entry["final_served_at"], entry["expires"]))
        # 61 s after that last serve, with no receipt, the id is gone.
        with At(base + 10 + SF.GRACE_SECONDS + 1):
            code, out = SF.download(ident, offset=8, length=4)
            check("no receipt and the grace over is a 404 in plain words",
                  code == 404 and out.get("error") == SF.unknown_id_words(),
                  (code, out))
            check("... the phone's list has forgotten it", SF.pending() == [], SF.pending())
            check("... and the entry itself is gone", ident not in SF._files)
            code, out = SF.acknowledge({"id": ident})
            check("a receipt after the grace is 404 too", code == 404, (code, out))


def t_the_phones_receipt_is_the_other_way_an_id_ends():
    fresh()
    with Piece(chunk=4):
        state = approved(TEN)
        ident = state["id"]
        code, out = SF.acknowledge({"id": ident})
        check("a receipt before the whole file arrived is 409",
              code == 409 and out.get("ok") is False
              and out.get("error") == SF.ACK_NOT_FINISHED_WORDS, (code, out))
        check("... and it consumes nothing",
              ident in SF._files and not SF._files[ident].get("used"), SF._files.get(ident))
        for offset in (0, 4, 8):
            SF.download(ident, offset=offset, length=4)
        code, out = SF.acknowledge({"id": ident})
        check("the receipt after the last piece is 200 with one sentence",
              code == 200 and set(out) == {"ok", "said"} and out.get("ok") is True
              and "finished" in out.get("said", ""), (code, out))
        check("the receipt's answer never carries bytes or a path",
              "data" not in out and str(ALLOW) not in json.dumps(out), out)
        check("the receipt consumed the id",
              SF._files[ident].get("used") is True and SF.pending() == [],
              SF._files.get(ident))
        code, out = SF.download(ident, offset=0, length=4)
        check("a slice after the receipt is 404", code == 404, (code, out))
        code, out = SF.acknowledge({"id": ident})
        check("a second receipt is 200, never an error",
              code == 200 and out.get("ok") is True
              and "already finished" in out.get("said", ""), (code, out))

    code, out = SF.acknowledge({"id": "file_" + "x" * 24})
    check("a receipt for an unknown id is 404 with one plain sentence",
          code == 404 and out == {"ok": False, "error": SF.unknown_id_words()},
          (code, out))
    code, out = SF.acknowledge({"id": "C:\\Windows\\notepad.exe"})
    check("a path is not an id on the receipt either", code == 404, (code, out))
    code, out = SF.acknowledge({"path": str(TEN)})
    check("the receipt never accepts a path",
          code == 400 and out.get("ok") is False and "never" in out.get("error", ""),
          (code, out))
    code, out = SF.acknowledge({})
    check("a receipt with no id asks for the id",
          code == 400 and out.get("ok") is False, (code, out))
    code, out = SF.acknowledge([])
    check("a receipt body that is not an object is 400", code == 400, (code, out))


def t_the_card_and_every_sentence_say_one_completed_transfer():
    fresh()
    _state, words = SF.prepare({"path": str(TEN)})
    check("the card says one completed transfer",
          "one completed transfer" in words, words)
    check("the card says when the transfer finishes",
          "phone confirms it" in words and SF.grace_words() in words
          and "whichever is first" in words, words)
    check("the card never says one completed download",
          "completed download" not in words, words)
    with Piece(chunk=4):
        state = approved(TEN)
        ready = SF._ready_words(SF._entry(state["id"]))
        check("the ready sentence says one completed transfer and the grace",
              "one completed transfer" in ready and SF.grace_words() in ready, ready)
    code, out = SF.handle_get(SF.LIST_PATH, "")
    check("the phone's list says one completed transfer",
          code == 200 and "one completed transfer" in out["said"]
          and "completed download" not in out["said"], out.get("said"))
    check("the 404 sentence says the transfer finished, not downloaded",
          "transfer has already finished" in SF.unknown_id_words()
          and "downloaded" not in SF.unknown_id_words(), SF.unknown_id_words())

    class Fresh:
        def do_GET(self):
            self._send(999, {})

        def do_POST(self):
            self._send(999, {})

        def _send(self, code, out):
            pass

    line = SF.install(Fresh, origin_ok=lambda h: True, token_ok=lambda h: True,
                      read_body=lambda h: b"")
    check("install()'s own line says one completed transfer",
          "one completed transfer" in line and "completed download" not in line, line)


def t_the_grace_and_the_ttl_are_one_constant_each():
    # Counted from the syntax tree, not from the text: "written once" is a
    # property of the module's own assignments, and a source-text pin is what
    # tools/check_no_source_pins.py exists to keep OUT of a new suite.
    import ast
    tree = ast.parse((HERE / "jarvis_send_file.py").read_text(encoding="utf-8"))
    assigned: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned[target.id] = assigned.get(target.id, 0) + 1
    for name in ("GRACE_SECONDS", "TTL_SECONDS", "CAP_BYTES", "CHUNK_BYTES"):
        check(f"{name} is written once", assigned.get(name) == 1, assigned.get(name))
    check("the grace words are derived from the constant",
          SF.grace_words() == "a minute"
          and SF.transfer_words().count("a minute") == 1,
          (SF.grace_words(), SF.transfer_words()))
    # Raising ONLY the grace moves the card's words AND the id's own boundary.
    with Piece(grace=120):
        check("a raised grace reaches the card's words",
              SF.grace_words() == "2 minutes"
              and "2 minutes" in SF.card_words(
                  {"name": "x.bin", "folder": "C:\\x", "size": 10}),
              (SF.grace_words(), SF.card_words(
                  {"name": "x.bin", "folder": "C:\\x", "size": 10})))
        base = time.time()
        state = approved(TEN)
        ident = state["id"]
        SF.download(ident, offset=0, length=10)          # the whole file: the last piece
        with At(base + 61):
            check("inside the raised grace the finished id is still servable",
                  SF.download(ident, offset=0, length=10)[0] == 200)
        with At(base + 61 + SF.GRACE_SECONDS + 1):
            check("... and past the grace the same id is 404",
                  SF.download(ident, offset=0, length=10)[0] == 404)


# ---------------------------------------------------------------------------
#   7. the desktop button's route
# ---------------------------------------------------------------------------

CARD_CALLS = []


class Verdict:
    def __init__(self, allowed=True, outcome="approved", tier="ask"):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = tier
        self.action = SF.ACTION
        self.reason = "test"


def card_gate(verdict=None, boom=False):
    CARD_CALLS.clear()

    def gate(action, detail, prompt):
        CARD_CALLS.append({"action": action, "detail": detail, "prompt": prompt})
        if boom:
            raise RuntimeError("the gate is down")
        return verdict if verdict is not None else Verdict()

    return gate


def approach(body, *, gate=None, spawn=None):
    return SF.handle_post(SF.PREPARE_PATH, body,
                          gate=gate or card_gate(), spawn=spawn or (lambda fn: fn()))


def t_the_button_route_raises_the_same_card():
    fresh()
    code, out = approach({"path": str(PICKED)})
    check("the button's route answers 202 with the shown fields",
          code == 202 and out.get("ok") is True and out.get("waiting") is False
          and out.get("id", "").startswith("file_")
          and out.get("name") == PICKED.name
          and out.get("size") == PICKED.stat().st_size
          and out.get("mime") == SF._mime_of(PICKED.name)
          and out.get("folder") == str(OUTSIDE), (code, out))
    check("the route raised ONE card under send_file_to_phone, tier ask",
          len(CARD_CALLS) == 1 and CARD_CALLS[0]["action"] == SF.ACTION
          and CARD_CALLS[0]["detail"]["max_bytes"] == SF.CAP_BYTES, CARD_CALLS[:1])
    check("the card's own words are the prompt AND the detail's text",
          CARD_CALLS[0]["prompt"] == CARD_CALLS[0]["detail"]["text"]
          and CARD_CALLS[0]["prompt"].startswith(f'Send "{PICKED.name}" from ')
          and SF.cap_sentence() in CARD_CALLS[0]["prompt"], CARD_CALLS[:1])
    check("the card names the exact file, folder, byte size and cap",
          CARD_CALLS[0]["detail"]["file"] == PICKED.name
          and CARD_CALLS[0]["detail"]["size"] == PICKED.stat().st_size
          and str(PICKED.stat().st_size) in CARD_CALLS[0]["prompt"]
          and str(OUTSIDE) in CARD_CALLS[0]["prompt"], CARD_CALLS[:1])
    check("an approved card makes it fetchable, and the file is served",
          [f["id"] for f in SF.pending()] == [out["id"]]
          and base64.b64decode(SF.download(out["id"])[1]["data"]) == PICKED.read_bytes())
    check("the route's answer never carries a raw path",
          str(OUTSIDE) not in json.dumps({k: v for k, v in out.items() if k != "folder"}),
          out)
    check("the answer's own words are the ready sentence",
          "Ready" in out.get("said", "") and SF.grace_words() in out.get("said", "")
          and "one completed transfer" in out.get("said", ""), out.get("said"))

    fresh()
    code, out = approach({"path": str(PICKED)},
                         gate=card_gate(Verdict(allowed=False, outcome="denied")))
    check("a denied card releases the candidate at once",
          code == 202 and out.get("waiting") is False and SF._files == {}
          and SF.pending() == [], (code, out))
    check("a denied card says so in words", "You said no" in out.get("said", ""),
          out.get("said"))
    check("a denied card serves nothing",
          SF.download(out["id"])[0] == 404, out.get("id"))

    fresh()
    code, out = approach({"path": str(PICKED)},
                         gate=card_gate(Verdict(allowed=False, outcome="timed_out")))
    check("a timed-out card releases the candidate too",
          code == 202 and SF._files == {} and "Nobody answered" in out.get("said", ""),
          (code, out))

    fresh()
    code, out = approach({"path": str(PICKED)},
                         gate=card_gate(Verdict(allowed=True, outcome="approved",
                                                tier="auto")))
    check("a loosened tier never becomes a standing yes",
          code == 202 and SF._files == {} and out.get("waiting") is False
          and SF.pending() == [], (code, out))

    fresh()
    code, out = approach({"path": str(PICKED)}, gate=card_gate(boom=True))
    check("a gate that cannot answer releases the candidate",
          code == 202 and SF._files == {} and "could not be answered" in out.get("said", ""),
          (code, out))

    fresh()
    def no_thread(fn):
        raise RuntimeError("no threads here")
    code, out = approach({"path": str(PICKED)}, spawn=no_thread)
    check("a card that cannot even be raised is a 503 and leaves nothing",
          code == 503 and SF._files == {} and "could not be raised" in out.get("said", ""),
          (code, out))


def t_the_button_route_refuses_before_the_card():
    fresh()
    protected = ALLOW / "protected.txt"
    protected.write_text("keep out\n", encoding="utf-8")
    stub = types.ModuleType("jarvis_protection")
    stub.path_refusal = (lambda path, **_k: "That is on your Protected from Jarvis list."
                         if os.path.normcase(str(path)) == os.path.normcase(str(protected))
                         else "")
    saved = sys.modules.get("jarvis_protection")
    sys.modules["jarvis_protection"] = stub
    try:
        cases = (
            ("a directory", {"path": str(ALLOW)}, "folder, not a file"),
            ("a missing file", {"path": str(ALLOW / "not-here.bin")}, "not on this PC"),
            ("a relative path", {"path": "not-here.bin"}, "not a full path"),
            ("no path at all", {}, "which file to send"),
            ("a path that is not text", {"path": 5}, "which file to send"),
            ("a body that is not an object", [], "which file to send"),
            ("an empty file", {"path": str(EMPTY)}, "is empty"),
            ("a protected path", {"path": str(protected)}, "Protected from Jarvis"),
        )
        for label, body, words in cases:
            CARD_CALLS.clear()
            code, out = approach(body, gate=card_gate())
            check(f"{label} is refused in words, with no card",
                  code == 400 and words in out.get("said", "") and CARD_CALLS == []
                  and SF._files == {}, (code, out))
            check(f"{label}: the desktop's own reading key is there too",
                  out.get("said") == out.get("error"), (code, out))
    finally:
        if saved is not None:
            sys.modules["jarvis_protection"] = saved
        else:
            sys.modules.pop("jarvis_protection", None)

    fresh()
    with Piece(cap=8):
        CARD_CALLS.clear()
        code, out = approach({"path": str(PICKED)}, gate=card_gate())
        check("a file over the cap is refused in words, with no card",
              code == 413 and "over the" in out.get("said", "")
              and SF.cap_sentence() in out.get("said", "") and CARD_CALLS == []
              and SF._files == {}, (code, out))

    fresh()
    why = raises(SF.prepare, {"path": str(PICKED)})
    check("the MODEL tool still refuses a path outside the allow-list",
          "Folders Jarvis may look in" in why, why)


# ---------------------------------------------------------------------------
#   7. the routes keep the gate, and a phone cannot name a path
# ---------------------------------------------------------------------------


class Handler:
    def __init__(self, path="", body=b"", headers=None):
        self.path = path
        self._body = body
        self.headers = dict(headers or {})
        self.sent = []

    def _send(self, code, out):
        self.sent.append((code, out))

    def do_GET(self):
        self._send(999, {"error": "core route not expected"})

    def do_POST(self):
        self._send(999, {"error": "core route not expected"})


def _request(handler_cls, path, *, body=b"", headers=None, method="GET",
             origin=True, token=True):
    class H(handler_cls):
        def do_GET(self):
            self._send(999, {"error": "core route not expected"})

        def do_POST(self):
            self._send(999, {"error": "core route not expected"})

    SF.install(H, origin_ok=lambda h: origin, token_ok=lambda h: token,
               read_body=lambda h: h._body)
    h = H(path, body, headers)
    getattr(h, "do_" + method)()
    return h.sent[-1]


def t_the_phone_cannot_name_a_path_and_the_routes_keep_the_gate():
    fresh()
    real_gate, real_spawn = SF._gate, SF._spawn
    SF._gate = card_gate()
    SF._spawn = lambda fn: fn()
    try:
        code, out = _request(Handler, SF.PREPARE_PATH,
                             body=json.dumps({"path": str(PICKED)}).encode(),
                             headers={"X-Jarvis-Surface": "phone"}, method="POST")
        check("a phone asking the button's route is 403 and no card is raised",
              code == 403 and CARD_CALLS == [] and SF._files == {}
              and "desktop program" in out.get("said", ""), (code, out))
        code, out = _request(Handler, SF.PREPARE_PATH,
                             body=json.dumps({"path": str(PICKED)}).encode(),
                             headers={"X-Jarvis-Surface": "desktop"}, method="POST")
        check("the desktop's own request raises the card and registers it",
              code == 202 and len(CARD_CALLS) == 1 and out.get("waiting") is False
              and [f["id"] for f in SF.pending()] == [out["id"]], (code, out))
        ident = out.get("id")

        code, out = _request(Handler, SF.PREPARE_PATH,
                             body=json.dumps({"path": str(PICKED)}).encode(),
                             method="POST", token=False)
        check("the button's route is behind the pairing token", code == 401, (code, out))
        code, out = _request(Handler, SF.PREPARE_PATH,
                             body=json.dumps({"path": str(PICKED)}).encode(),
                             method="POST", origin=False)
        check("and behind the origin check", code == 403, (code, out))
        code, out = _request(Handler, SF.PREPARE_PATH, body=b"{not json", method="POST")
        check("an unreadable body is 400 and raises no card",
              code == 400 and "not readable" in out.get("said", ""), (code, out))
        code, out = _request(Handler, "/api/elsewhere", body=b"{}", method="POST")
        check("another POST route still reaches the core", code == 999, (code, out))
        code, out = _request(Handler, SF.LIST_PATH)
        check("the list route answers through install() with both limits",
              code == 200 and out["cap_bytes"] == SF.CAP_BYTES
              and out["chunk_bytes"] == SF.CHUNK_BYTES, (code, out))
        code, out = _request(Handler, SF.DOWNLOAD_PATH, body=b"")
        check("a GET download with no id still asks for one",
              code == 400 and "no path is needed" in out.get("error", ""), (code, out))
        code, out = _request(Handler, SF.DOWNLOAD_PATH + f"?id={ident}&offset=0&length=8")
        check("the download route serves a piece by id and numbers",
              code == 200 and out["offset"] == 0 and out["length"] == 8
              and base64.b64decode(out["data"]) == PICKED.read_bytes()[:8], (code, out))

        # The phone's receipt: behind the same token and origin, and NOT
        # refused for saying it is the phone - that is the surface that sends
        # it, unlike the button's path-naming route above.
        with Piece(chunk=4):
            state = approved(TEN)
            ack_id = state["id"]
            for offset in (0, 4, 8):
                SF.download(ack_id, offset=offset, length=4)
        ack_body = json.dumps({"id": ack_id}).encode()
        code, out = _request(Handler, SF.ACK_PATH, body=ack_body,
                             headers={"X-Jarvis-Surface": "phone"}, method="POST")
        check("the phone's own receipt is accepted, not the prepare 403",
              code == 200 and out.get("ok") is True and "finished" in out.get("said", ""),
              (code, out))
        code, out = _request(Handler, SF.ACK_PATH, body=ack_body, method="POST",
                             token=False)
        check("the receipt is behind the pairing token", code == 401, (code, out))
        code, out = _request(Handler, SF.ACK_PATH, body=ack_body, method="POST",
                             origin=False)
        check("and behind the origin check", code == 403, (code, out))
        code, out = _request(Handler, SF.ACK_PATH, body=b"{not json", method="POST")
        check("an unreadable receipt body is 400",
              code == 400 and "not readable" in out.get("error", ""), (code, out))
        class Twice(Handler):
            pass
        SF.install(Twice, origin_ok=lambda h: True, token_ok=lambda h: True,
                   read_body=lambda h: b"")
        again = SF.install(Twice, origin_ok=lambda h: True, token_ok=lambda h: True,
                           read_body=lambda h: b"")
        check("installing twice is a no-op, so the routes cannot nest",
              "already on" in again, again)
    finally:
        SF._gate, SF._spawn = real_gate, real_spawn


def t_the_records_stay_equal():
    repo = HERE.parent
    check("the published base twin is byte-identical",
          (HERE / "jarvis_send_file.py").read_bytes()
          == (repo / "jarvis-backend" / "jarvis_send_file.py").read_bytes())
    check("the drop-in folder still names one module and one install",
          json.loads((repo / "plugins" / "ready" / "send-file" /
                      "plugin.json").read_text(encoding="utf-8")).get("module")
          == "jarvis_send_file")
    # Read the classifier's own dictionaries from the syntax tree, never as
    # source text: the classification is what matters, and a text pin is what
    # tools/check_no_source_pins.py keeps out of a new suite.
    import ast
    parity_tree = ast.parse((repo / "tools" / "check_parity.py").read_text(encoding="utf-8"))
    dicts = {}
    for node in parity_tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    dicts[target.id] = node.value

    def _keys(node, kind=None):
        if not isinstance(node, ast.Dict):
            return set()
        got = set()
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if kind is not None:
                first = value.elts[0] if isinstance(value, ast.Tuple) and value.elts else None
                if not (isinstance(first, ast.Constant) and first.value == kind):
                    continue
            got.add(key.value)
        return got

    phone_only = _keys(dicts.get("PHONE_ONLY"))
    deliberate = _keys(dicts.get("CLASSIFICATION"), "deliberate")
    check("parity classifies the three sending routes",
          {"/api/files/send", "/api/files/download", "/api/files/ack"} <= phone_only
          and "/api/files/prepare" in deliberate, (sorted(phone_only), sorted(deliberate)))


# ---------------------------------------------------------------------------
#   main
# ---------------------------------------------------------------------------


def main() -> int:
    tests = (
        t_the_one_number_is_read_everywhere,
        t_a_file_cut_into_pieces_is_fetched_piece_by_piece,
        t_offset_and_length_arithmetic,
        t_the_wire_shapes_are_the_contract,
        t_every_piece_renews_the_life_and_retries_work,
        t_a_changed_file_is_409_and_is_never_served,
        t_an_old_client_never_gets_a_truncated_file,
        t_the_last_piece_leaves_a_grace_window,
        t_the_phones_receipt_is_the_other_way_an_id_ends,
        t_the_card_and_every_sentence_say_one_completed_transfer,
        t_the_grace_and_the_ttl_are_one_constant_each,
        t_the_button_route_raises_the_same_card,
        t_the_button_route_refuses_before_the_card,
        t_the_phone_cannot_name_a_path_and_the_routes_keep_the_gate,
        t_the_records_stay_equal,
    )
    for fn in tests:
        print(f"\n--- {fn.__name__}")
        try:
            fn()
        except Exception:                                   # noqa: BLE001
            FAILED.append(fn.__name__ + " raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: " + ", ".join(FAILED))
        shutil.rmtree(_TMP, ignore_errors=True)
        return 1
    print(f"{len(PASSED)} passed, 0 failed - pieces of a big file are fetched by "
          f"offset, the last piece waits {SF.grace_words()} for the phone's "
          f"receipt, and the desktop button raises the same card (under "
          f"{SF.cap_sentence()}, in {SF.chunk_words()} pieces)")
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
