"""jarvis_history_purge.py - clear old chats (and the facts they taught) for a
date range, after a card, TWO separate yeses and a Windows Hello / fingerprint
ticket. This is the one route pair in Jarvis that deletes in bulk and cannot be
undone.

NEW MODULE, shipped whole. `history-purge.patch` is the install block that puts
its three routes on the running server (docs/JARVIS-API.md section 189);
everything else is here.

THE OWNER'S REQUEST (2026-11-04, in his own words)
    "how long does it take for you to clear old chats if i batched a lot of
    them together?" - asked of the live Jarvis, which answered that it had no
    built-in "clear old chats" action and did not track how long it would take.
He then said what he wants: Jarvis should know everything in its own settings
and explain it thoroughly; it should be able to clear conversations it does NOT
have pinned when asked to clear ones of a certain date, INCLUDING FACTS; it must
give a card with all the details, with a DOUBLE CONFIRMATION of yes, and require
a Windows PIN or fingerprint (phone: fingerprint; Windows desktop: Windows
Hello PIN/biometric) before deleting.

WHAT ALREADY EXISTED ON MAIN WHEN THIS WAS WRITTEN, so this module adds to it
rather than pretending it invented it:

  * the chat history: `chat-history.db` in the config folder (~/.openjarvis),
    every title and message sealed with AES-GCM (`jarvis_chat_log.ChatLog`,
    whose key lives in Windows Credential Manager). `pinned` / `pinned_at` are
    plain columns there and `POST /api/history/pin {"id","pinned"}` already
    pins and unpins one chat (`jarvis_chat_log.set_pin`, section 18.3). This
    module never writes that column: it READS it, and a pinned chat is never
    deleted unless the preview was explicitly asked to include them.
  * one conversation at a time: `POST /api/history/delete`, and the carded
    `POST /api/conversations/clear` (action `conversation_clear`).
  * "Forget a time frame" (`jarvis_forget_range.py`, section 64): a checked
    list, ONE approval card, the chats deleted with TEN MINUTES TO UNDO, and
    the facts RETIRED (hidden, words kept).
  * the retention switch: `keep_days` is 0 (keep until deleted, the default),
    30, 90 or 365, and `jarvis_chat_log.sweep` expires chats when it is not 0.
  * facts record WHERE THEY CAME FROM: `jarvis_memory.MemoryStore.add` writes
    `meta["conversation_id"]`, which is what `conversation_facts_view` reads.
    So this module never has to guess which facts a chat taught.

WHAT THIS ADDS, and why it is not a second "Forget a time frame"
  * It is IRREVERSIBLE on purpose - there is no Undo, and the card says so.
    Forget a time frame keeps the words of every fact it forgets and holds the
    chats for ten minutes; the owner asked for the opposite of that when the
    point is to clear things out.
  * It ERASES the words of the facts those chats taught (`MemoryStore.erase`,
    the same call the per-fact "Erase the words" makes), rather than retiring
    them. That is the "INCLUDING FACTS" half of the request.
  * It KEEPS PINNED CHATS. Forget a time frame does not look at the pin at all;
    the owner named the pin as the thing to protect.
  * It asks TWICE and then checks a platform ticket (below). Forget a time
    frame asks once, through the ordinary approval card.

THE THREE ROUTES (the whole contract; nothing else here deletes anything)

    POST /api/history/purge/preview   {from, to, include_facts, include_pinned}
    POST /api/history/purge/confirm   {preview_id, confirm_id, step, auth_ticket}
    POST /api/history/purge/cancel    {preview_id}

`preview` measures and answers; it deletes nothing and remembers what it saw.
`confirm` step 1 is the FIRST yes and only issues the `confirm_id`. `confirm`
step 2 is the SECOND yes and needs a valid `auth_ticket`; it is the ONLY code
path in this module that removes a row. `cancel` drops the preview. A new
preview invalidates the one before it (there is one open preview at a time).

THE AUTH TICKET, AND EXACTLY WHAT IT PROVES (the contract lane P2 builds to)

The ticket is the app's proof that a person was asked by the OPERATING SYSTEM
and said yes. Its text is

    "{preview_id}|{confirm_id}|{method}|{issued_at}"

and the app sends, as `auth_ticket`, the hex HMAC-SHA256 of those bytes under a
key it had to be trusted with:

    v1.{method}.{issued_at}.{hex mac}

  * DESKTOP, method `windows_hello`: the key is a random 32-byte secret this
    backend makes at startup in `~/.openjarvis/purge-auth.key` (created 0600,
    owner only - see `auth_key()`). The desktop app reads that file, proves the
    owner through Windows Hello (`UserConsentVerifier`), and HMACs with it.
  * PHONE, method `phone_biometric`: the key is the EXISTING pairing token, so
    nothing new has to be paired. The Android app shows its fingerprint prompt
    and HMACs with the token it already holds.

The backend accepts a ticket only when every one of these holds, and says which
one failed in words:

  1. it parses, and `method` is `windows_hello` or `phone_biometric`;
  2. `method` MATCHES the app that sent it (`X-Jarvis-Client` decides which key
     is expected: a phone client needs `phone_biometric`, anything else needs
     `windows_hello`);
  3. the HMAC matches, under the key for that method, compared in constant time;
  4. `issued_at` is within 90 seconds of this PC's clock, and not in the future;
  5. it names THIS preview and THIS confirm_id;
  6. it has never been used before (a nonce store in memory, keyed by the
     ticket's own digest - so a replayed ticket is refused even inside the 90
     seconds);
  7. the first yes was recorded for that preview, and the preview has not
     expired (10 minutes) or been cancelled.

WHAT THAT DOES AND DOES NOT PROVE - said plainly, because this is a local-only
trust model and nobody should read more into it:

  * It proves the caller was in possession of a secret that only this owner's
    own install holds (the key file, or the pairing token). The two yeses and
    the 10-minute preview are what prove intent.
  * It does NOT prove a human was present. The backend cannot see the Windows
    Hello prompt or the phone's fingerprint reader - the app asks, and then
    signs. A local program that can read `purge-auth.key` (or the pairing token
    in Credential Manager) could mint a ticket without asking anybody. That is
    the same trust level as the pairing token itself: file-system access to
    this PC's own user account. It is not proof against malware already running
    as the owner, and it was never going to be.
  * The `X-Jarvis-Client` header is asserted by the caller, so it chooses WHICH
    key is expected, not WHO the caller is. Both keys are owner-level secrets
    on this PC, so a caller who spoofs the header to reach the other key gains
    nothing it did not already have.

PINNED CHATS ARE NEVER DELETED by accident
  * The preview leaves them out and says how many it left out
    (`conversations.kept_pinned_count`), and the facts they taught are kept
    too (`facts.kept_due_to_pinned`) because their provenance is a chat that is
    still here.
  * `include_pinned: true` is the only way past that, it is never the default,
    and the card then says in words that pinned chats go too.
  * A chat PINNED AFTER the preview is checked again at execution time and
    SKIPPED, with the skip counted in the audit line - a pin set between the
    card and the second yes is a pin the owner meant.

WHAT IS WRITTEN DOWN
  Every deletion appends ONE line to `~/.openjarvis/purge-audit.jsonl`:
  `audit_id`, `at`, `window`, `preview_id`, `confirm_id`, `auth_method`,
  `client`, the counts deleted and kept, `elapsed_ms`, and whether it was
  measured. NEVER a title, a message, or a word of a fact.

Standard library only. Changes `sqlite3` files on this PC and nothing else.
Nothing here is sent anywhere, and nothing here talks to a model.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

try:                                        # shipped beside this module
    import jarvis_framework as fw
except Exception:                           # pragma: no cover - a PC without it
    fw = None                               # type: ignore

# --------------------------------------------------------------------------
#   Names, routes and the numbers the contract promises
# --------------------------------------------------------------------------

ACTION = "history_purge"
PREVIEW_PATH = "/api/history/purge/preview"
CONFIRM_PATH = "/api/history/purge/confirm"
CANCEL_PATH = "/api/history/purge/cancel"
ROUTES = (PREVIEW_PATH, CONFIRM_PATH, CANCEL_PATH)

SCHEMA = "jarvis-history-purge/1"

#: How long a preview stays valid. Ten minutes: long enough to read a card of
#: 200 chats, short enough that a window left open on a desk goes stale.
PREVIEW_TTL = 600.0
#: How old a signed ticket may be. 90 seconds is the whole life of the second
#: yes, and a ticket older than that is refused even if it is otherwise perfect.
TICKET_SKEW = 90.0
#: How far in the future this PC will accept an `issued_at` (a phone whose clock
#: is a few seconds ahead is not an attacker, but an hour ahead is).
TICKET_FUTURE = 5.0
#: Used tickets are remembered this long, so a replay inside the skew is caught.
NONCE_SECONDS = 3600.0

KEY_NAME = "purge-auth.key"
AUDIT_NAME = "purge-audit.jsonl"
SPEED_NAME = "purge-speed.json"

METHOD_DESKTOP = "windows_hello"
METHOD_PHONE = "phone_biometric"
METHODS = (METHOD_DESKTOP, METHOD_PHONE)

#: The first N fact names the card shows. More than this and the card says how
#: many it is not showing - it counts them, it never hides the number.
NAMES_SHOWN = 40

#: Frame text is the same "YYYY-MM-DD" / "YYYY-MM-DDTHH:MM" the apps already
#: send to Forget a time frame; the parser is that module's, imported.
_WHEN_FORMAT = "YYYY-MM-DD[THH:MM]"

#: `X-Jarvis-Client` values that mean "this came from the phone". Anything else
#: is treated as the PC - which is the strict half: the PC key is the one in
#: `purge-auth.key`, and the phone key is the pairing token.
_PHONE_CLIENTS = frozenset({"android", "phone", "mobile", "jarvis-client",
                            "jarvis_client", "client", "app"})

_WORDS = {
    "irreversible": "This cannot be undone. There is no Undo, and no copy is kept.",
    "no_card": ("This action does not use the ordinary approval card: it asks you "
                "twice here, and the second yes needs your Windows Hello PIN or "
                "fingerprint."),
    "estimate": ("The number of bytes is an estimate. SQLite zeroes a deleted row "
                 "where it is, and the file itself only gets smaller after a "
                 "VACUUM, which happens on the history's own schedule."),
}

#: The three refusals, in the words both apps can show as-is.
_WHY = {
    "bad_request": "Send a JSON object with from and to as YYYY-MM-DD, and "
                   "include_facts / include_pinned as true or false.",
    "bad_window": "That date range could not be read. Use YYYY-MM-DD, or "
                  "YYYY-MM-DDTHH:MM for a time of day, with from before to.",
    "locked": ("The memory lists and chat history are hidden on this PC right now, "
               "so a card cannot show you what it would delete. Turn that off "
               "first."),
    "no_preview": "There is no such preview. It may have been cancelled, replaced "
                  "by a newer one, or it may be more than ten minutes old. Start "
                  "again with a preview.",
    "no_first_yes": ("The first yes was not recorded for this preview, so the "
                     "second one cannot run. Send step 1 first, read the card, "
                     "then send step 2."),
    "already_confirmed": ("The first yes is already recorded. Read the card again "
                          "and send step 2 with your Windows Hello PIN or "
                          "fingerprint."),
    "no_ticket": ("The second yes needs your Windows Hello PIN or your phone's "
                  "fingerprint. Nothing was deleted."),
    "bad_ticket": "That confirmation could not be checked, so nothing was deleted.",
    "wrong_platform": ("That confirmation was signed for a different device than "
                       "the one that sent it, so nothing was deleted."),
    "expired_ticket": ("That confirmation has expired - it is good for 90 seconds. "
                       "Ask for it again. Nothing was deleted."),
    "ticket_reused": ("That confirmation was already used. Ask for a fresh one. "
                      "Nothing was deleted."),
    "no_key": ("This PC has no key for a phone confirmation, so a phone ticket "
               "cannot be checked. Nothing was deleted."),
    "empty": ("That range has nothing to clear: no chats and no facts fall inside "
              "it, so nothing was deleted."),
}


def _now() -> float:
    """This module's clock: the preview's ten minutes and the ticket's 90
    seconds. (Whether a fact is still in use is the memory store's own rule.)"""
    return time.time()


def _words(key: str, **extra) -> str:
    said = _WHY.get(key, "Nothing was deleted.")
    for name, value in extra.items():
        said = said.replace("{" + name + "}", str(value))
    return said


def _fail(key: str, code: str = "", **extra) -> dict:
    return {"ok": False, "error": code or key, "message": _words(key, **extra),
            "irreversible": True}


def _config_dir() -> Path:
    """Where this PC keeps its own files: `fw.CONFIG_DIR` when the framework is
    beside us (~/.openjarvis), the same folder the history database lives in."""
    try:
        if fw is not None and getattr(fw, "CONFIG_DIR", None):
            return Path(str(fw.CONFIG_DIR))
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or ""
    if env:
        return Path(env)
    return Path.home() / ".openjarvis"


def _audit(event: str, detail: dict) -> None:
    """The ordinary audit log (counts and outcomes only, never words)."""
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The live modules this one asks (imported late, so a PC without one says so)
# --------------------------------------------------------------------------

def _chats():
    import jarvis_chat_log
    return jarvis_chat_log


def _memory():
    import jarvis_memory
    return jarvis_memory


def _log(chats=None):
    """The ChatLog to read and delete through.

    A caller may hand over the `jarvis_chat_log` MODULE (which is what a route
    does: `_chats()`), or a `ChatLog` itself (which is what a suite does, so it
    can drive a temporary history). Both are accepted, and neither is guessed: a
    module is asked for its own log, an instance is used as it is.
    """
    got = chats if chats is not None else _chats()
    if hasattr(got, "_connect") and hasattr(got, "db_path"):
        return got
    try:
        return got._log()
    except Exception:
        return got


def _store(mem=None):
    """The MemoryStore: from the module, from an instance, or from a caller."""
    got = mem if mem is not None else _memory()
    if hasattr(got, "store"):
        try:
            return got.store()
        except Exception:
            pass
    return got


def _private_locked() -> tuple:
    """(locked, why) from the trusted App-lock / hide-lists state.

    The same reader `POST /api/history/pin` uses. It is deliberately NOT the
    request's own word for it: a caller cannot talk this PC out of App lock.
    """
    try:
        import jarvis_private_view as PV
        view = PV.effective()
        return bool(view.get("locked")), str(view.get("why") or "")
    except Exception:
        return False, ""


def _frame(frm, to):
    """(start, end, window dict) for the two date strings, inclusive both ends.

    The date grammar is `jarvis_forget_range.frame_of`'s, imported rather than
    written a second time: "1 to 15 September" is the same range there and here,
    and two parsers would drift. A PC without that module gets the plain
    YYYY-MM-DD reading below, and says which one answered.
    """
    try:
        import jarvis_forget_range as FR
        frame = FR.frame_of(frm, to)
        return frame.start, frame.end, frame.view(), "jarvis_forget_range"
    except ImportError:
        pass
    except ValueError as exc:
        raise ValueError(str(exc) or "bad window")
    start, end = _plain_days(frm, to)
    said = f"{frm} to {to}" if frm != to else str(frm)
    return start, end, {"from": frm, "to": to, "said": said,
                        "start": int(start), "end": int(end)}, "local"


def _plain_days(frm, to) -> tuple:
    """The fallback: YYYY-MM-DD (or YYYY-MM-DDTHH:MM), local time, inclusive."""
    def one(text):
        text = str(text or "").strip()
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return time.mktime(time.strptime(text, fmt)), bool(len(text) > 10)
            except ValueError:
                continue
        raise ValueError("bad window")
    a, timed_a = one(frm)
    b, timed_b = one(to)
    if timed_b:
        b += 60.0
    else:
        b += 86400.0
    if b <= a:
        raise ValueError("bad window")
    return a, b


def _day_of(at: float) -> str:
    """The PC's own local day for a moment, as YYYY-MM-DD."""
    try:
        return time.strftime("%Y-%m-%d", time.localtime(float(at)))
    except Exception:
        return ""


# --------------------------------------------------------------------------
#   The keys: one secret file this backend makes, and the phone's own token
# --------------------------------------------------------------------------

_KEY_CACHE: dict = {}
_KEY_LOCK = threading.Lock()


def key_path() -> Path:
    """~/.openjarvis/purge-auth.key - the desktop half's HMAC key."""
    return _config_dir() / KEY_NAME


def auth_key() -> bytes:
    """The 32 random bytes the desktop app signs a Windows Hello yes with.

    Made once, on first use or at startup, with `O_CREAT|O_EXCL` and mode 0600
    so there is no moment when it is world-readable and no race where two
    processes each think they made it (`jarvis_ledger._new_key_file` does the
    same thing for the same reason). The key is never logged, never returned by
    a route, and never leaves this PC: the desktop app reads this one file.

    Raises OSError when the folder cannot be written - a caller then says so
    rather than pretending a ticket could be checked.
    """
    path = key_path()
    cached = _KEY_CACHE.get(str(path))
    if cached:
        return cached
    with _KEY_LOCK:
        cached = _KEY_CACHE.get(str(path))
        if cached:
            return cached
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # THE FOLDER IS PART OF THE KEY'S PRIVACY (2026-11-05). The docstring
            # above promises 0600 on the file, and backend/test_history_purge.py
            # asserts the folder as well ("... and its folder": nothing but the
            # owner may enter it). That assertion was RED on every POSIX runner
            # until this line: `mkdir(mode=0o700)` is masked by the umask and
            # does nothing when the folder is already there (the framework makes
            # it, and the test's own fixture does too), so the folder stayed
            # 0755. The chmod is what actually makes the promise true. On
            # Windows `os.chmod` only touches the read-only bit, so it changes
            # nothing there; on POSIX it takes the config folder - which holds
            # this key, the pairing token and the history database - to the
            # owner-only mode it should always have had.
            try:
                os.chmod(path.parent, 0o700)
            except OSError:
                pass
            try:
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:         # another process won the race
                raw = path.read_bytes()
            else:
                try:
                    os.write(fd, secrets.token_bytes(32))
                finally:
                    os.close(fd)
                raw = path.read_bytes()
        if len(raw) < 16:
            raise OSError(f"{path} is too short to be the purge key")
        _KEY_CACHE[str(path)] = raw
        return raw


def _phone_key() -> bytes:
    """The pairing token, as bytes, or b"" when this PC cannot read it.

    The token is the phone's half of the contract: it already holds it, so a
    fingerprint yes needs nothing new paired. It is read from Windows Credential
    Manager through the shipped `jarvis_token_store` (READ ONLY - the store's
    own `read()`), and from the old plain-text `token` file a PC that has not
    been migrated yet still keeps. Never logged, never returned.
    """
    try:
        import jarvis_token_store as TS
        store = TS.default_store()
        got = store.read()
        if isinstance(got, str) and got:
            return got.encode("utf-8")
    except Exception:
        pass
    try:
        legacy = _config_dir() / "token"
        value = legacy.read_text(encoding="utf-8").strip()
        if value:
            return value.encode("utf-8")
    except Exception:
        pass
    return b""


def mint_ticket(preview_id: str, confirm_id: str, method: str, *, at=None,
                key: Optional[bytes] = None) -> str:
    """The ticket text an app sends back, `v1.{method}.{issued_at}.{hex mac}`.

    This exists so the suite (and a person debugging a phone) can make a real
    ticket from a real key; it is NOT reachable from any route, and it takes the
    key from the caller or from this PC's own two sources. A caller who can call
    this with no key and read the answer could already read the key file, which
    is the trust boundary the module docstring states.
    """
    method = str(method or "")
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}")
    if key is None:
        key = auth_key() if method == METHOD_DESKTOP else _phone_key()
        if not key:
            raise OSError("no key for that method on this PC")
    issued = int(at if at is not None else _now())
    text = f"{preview_id}|{confirm_id}|{method}|{issued}"
    mac = hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v1.{method}.{issued}.{mac}"


#: Used tickets: their own digest, and when they were seen. In memory only -
#: a restart forgets them, which is safe because a ticket also dies at 90
#: seconds and names a preview that a restart has forgotten too.
_USED: dict = {}
_STATE_LOCK = threading.RLock()


def _prune_used(now: float) -> None:
    cut = now - NONCE_SECONDS
    for digest in [d for d, at in _USED.items() if at < cut]:
        _USED.pop(digest, None)


def _platform_method(client: str, explicit: str = "") -> str:
    """Which key this request must be signed with, from the app that sent it.

    `X-Jarvis-Client` is asserted by the caller, so this decides WHICH key is
    expected, never WHO the caller is - both keys are owner-level secrets on
    this PC (see the module docstring).
    """
    if explicit in METHODS:
        return explicit
    name = str(client or "").strip().lower()
    return METHOD_PHONE if name in _PHONE_CLIENTS else METHOD_DESKTOP


def verify_ticket(ticket, preview_id: str, confirm_id: str, *, client: str = "",
                  method: str = "", now: Optional[float] = None) -> tuple:
    """(True, method) or (False, why-dict). Every check, in the order the card
    explains them. Never raises for a bad ticket, never logs it, never says the
    key it compared against."""
    now = _now() if now is None else float(now)
    want = _platform_method(client, method)
    text = ticket if isinstance(ticket, str) else ""
    parts = text.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return False, _fail("no_ticket")
    _, got_method, issued_text, mac = parts
    if got_method not in METHODS:
        return False, _fail("bad_ticket", "bad_ticket")
    if got_method != want:
        return False, _fail("wrong_platform", "wrong_platform")
    try:
        issued = int(issued_text)
    except (TypeError, ValueError):
        return False, _fail("bad_ticket", "bad_ticket")
    if issued > now + TICKET_FUTURE:
        return False, _fail("expired_ticket", "expired_ticket")
    if abs(now - issued) > TICKET_SKEW:
        return False, _fail("expired_ticket", "expired_ticket")
    key = auth_key() if got_method == METHOD_DESKTOP else _phone_key()
    if not key:
        return False, _fail("no_key", "no_key")
    text_signed = f"{preview_id}|{confirm_id}|{got_method}|{issued}"
    expect = hmac.new(key, text_signed.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, mac):
        return False, _fail("bad_ticket", "bad_ticket")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with _STATE_LOCK:
        _prune_used(now)
        if digest in _USED:
            return False, _fail("ticket_reused", "ticket_reused")
        _USED[digest] = now
    return True, got_method


# --------------------------------------------------------------------------
#   What a preview sees (reads only - nothing here deletes)
# --------------------------------------------------------------------------

def _db_bytes(*paths) -> int:
    """The size on disk of a database and its write-ahead log, in bytes."""
    total = 0
    for path in paths:
        for p in (path, Path(str(path) + "-wal")):
            try:
                total += int(p.stat().st_size)
            except OSError:
                continue
    return total


def _turns_total(log) -> int:
    """Every message row in the history file, or 0 when it cannot be read."""
    try:
        with closing(log._connect()) as c:
            row = c.execute("SELECT COUNT(*) FROM turns").fetchone()
        return int(row[0] or 0)
    except Exception:
        return 0


def _pinned_ids(log, ids=None) -> set:
    """The ids among `ids` (or every chat) that carry a pin right now."""
    try:
        with closing(log._connect()) as c:
            if ids is None:
                rows = c.execute("SELECT id FROM conversations WHERE pinned=1"
                                 " AND pinned_at IS NOT NULL").fetchall()
            else:
                ids = [i for i in ids if isinstance(i, str)]
                if not ids:
                    return set()
                marks = ",".join("?" * len(ids))
                rows = c.execute(
                    "SELECT id FROM conversations WHERE pinned=1 AND id IN ("
                    + marks + ")", ids).fetchall()
        return {str(r[0]) for r in rows}
    except Exception:
        return set()


def _facts_of(mem, conversation_ids) -> list:
    """Every fact whose recorded provenance is one of `conversation_ids`.

    The rule is the owner's, in the module docstring: facts are selected by what
    they RECORD, never by a guess. `meta["conversation_id"]` is written when the
    fact is saved (`jarvis_memory.MemoryStore.add`), and a fact that never
    recorded one is simply not in this list - the card says so.

    Forgotten facts are INCLUDED: a forgotten fact still holds its words, and
    the point of this action is that the words go. Erased facts are not (there
    are no words left to erase).
    """
    wanted = {str(c) for c in conversation_ids if isinstance(c, str)}
    if not wanted:
        return []
    out = []
    try:
        st = _store(mem)
        with closing(st._connect()) as c:
            rows = c.execute(
                "SELECT id, text, created, source, meta FROM facts"
                " WHERE erased_at IS NULL AND meta IS NOT NULL"
                " AND meta LIKE '%conversation_id%'").fetchall()
    except Exception:
        return []
    for r in rows:
        try:
            meta = json.loads(r["meta"]) if r["meta"] else {}
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        cid = meta.get("conversation_id")
        if not isinstance(cid, str) or cid not in wanted:
            continue
        out.append({"id": int(r["id"]), "text": str(r["text"] or ""),
                    "created": r["created"], "conversation_id": cid})
    out.sort(key=lambda f: (f["created"] or 0, f["id"]))
    return out


def preview(body, *, now: Optional[float] = None, chats=None, mem=None,
            client: str = "") -> tuple:
    """POST /api/history/purge/preview - measure, answer, delete nothing.

    (http code, answer). The answer is the card: what would go, day by day, by
    name where the facts are known, with every warning and the one sentence
    that matters - this cannot be undone.
    """
    now = _now() if now is None else float(now)
    if not isinstance(body, dict):
        return 400, _fail("bad_request")
    known = {"from", "to", "include_facts", "include_pinned"}
    if body and set(body) - known:
        return 400, _fail("bad_request")
    frm, to = body.get("from"), body.get("to")
    if not isinstance(frm, str) or not isinstance(to, str):
        return 400, _fail("bad_request")
    include_facts = body.get("include_facts", False)
    include_pinned = body.get("include_pinned", False)
    if not isinstance(include_facts, bool) or not isinstance(include_pinned, bool):
        return 400, _fail("bad_request")
    if not _all_text([frm, to]):
        return 400, _fail("bad_request")

    locked, why = _private_locked()
    if locked:
        out = _fail("locked", "locked")
        out["why"] = why
        return 423, out

    try:
        start, end, window, parser = _frame(frm, to)
    except (ValueError, OverflowError, OSError):
        return 400, _fail("bad_window")

    try:
        log = _log(chats)
        store = _store(mem)
    except Exception as exc:
        return 503, {"ok": False, "error": "unreadable",
                     "message": ("this PC could not read its own history "
                                 f"({type(exc).__name__}), so nothing was deleted. "
                                 "Try again - and if it keeps happening, restart "
                                 "Jarvis and ask it what went wrong."),
                     "irreversible": True}

    got = log.overlapping(start, end, limit=100000)
    items = list(got.get("items") or [])
    if not items and got.get("why_not"):
        return 503, {"ok": False, "error": "unreadable",
                     "message": str(got["why_not"]), "irreversible": True}

    pinned_now = _pinned_ids(log, [c["id"] for c in items])
    # `kept_pinned` is about chats the pin SAVED. When the preview was asked to
    # include them, nothing was saved, so it is empty - and the card says
    # separately that pinned chats are going.
    kept_pinned = [] if include_pinned else [
        c for c in items if c["id"] in pinned_now]
    going = items if include_pinned else [c for c in items if c["id"] not in pinned_now]
    going_ids = [c["id"] for c in going]

    per_day: dict = {}
    messages = 0
    spills = 0
    for c in going:
        messages += int(c.get("turns") or 0)
        if c.get("spills"):
            spills += 1
        day = _day_of(c.get("updated") or c.get("started") or 0)
        if day:
            slot = per_day.setdefault(day, {"day": day, "chats": 0, "messages": 0})
            slot["chats"] += 1
            slot["messages"] += int(c.get("turns") or 0)

    facts = _facts_of(store, going_ids) if include_facts else []
    kept_facts = _facts_of(store, [c["id"] for c in kept_pinned]) if kept_pinned else []

    try:
        chat_db = Path(getattr(log, "db_path"))
    except Exception:
        chat_db = _config_dir() / "chat-history.db"
    db_bytes = _db_bytes(chat_db)
    turns_all = _turns_total(log)
    fact_bytes = sum(len(f["text"].encode("utf-8")) + 96 for f in facts)
    chat_part = int(round(db_bytes * (messages / turns_all))) if turns_all else 0
    estimated = fact_bytes + chat_part

    names = [f["text"][:200] for f in facts[:NAMES_SHOWN]]

    warnings = [_WORDS["irreversible"], _WORDS["no_card"], _WORDS["estimate"]]
    if not include_facts:
        taught = _facts_of(store, going_ids)
        if taught:
            warnings.append(
                f"FACTS ARE NOT INCLUDED in this preview. These {len(taught)} "
                f"chat{'s' if len(taught) != 1 else ''} taught {len(taught)} "
                f"fact{'s' if len(taught) != 1 else ''}, and they would be kept. "
                f"Send include_facts: true to clear them as well.")
    if include_pinned and pinned_now:
        warnings.append(
            f"INCLUDE_PINNED IS ON: {len(pinned_now)} pinned chat"
            f"{'s' if len(pinned_now) != 1 else ''} inside these days will be "
            f"deleted too. Pinning does not protect them in this preview.")
    if kept_pinned:
        warnings.append(
            f"{len(kept_pinned)} pinned chat{'s' if len(kept_pinned) != 1 else ''} "
            f"fall inside these days and are KEPT, because they are pinned. Send "
            f"include_pinned: true only if you want those gone too.")
    if kept_facts:
        warnings.append(
            f"{len(kept_facts)} fact{'s' if len(kept_facts) != 1 else ''} that came "
            f"from a pinned chat {'are' if len(kept_facts) != 1 else 'is'} kept with it.")
    if spills:
        warnings.append(
            f"{spills} chat{'s' if spills != 1 else ''} also hold messages from "
            f"OUTSIDE these days, and go in full - this works per chat, not per "
            f"message.")
    if not going and not facts:
        warnings.append("There is nothing to clear in that range.")

    preview_id = str(uuid.uuid4())
    confirm_id = str(uuid.uuid4())
    expires_at = now + PREVIEW_TTL
    counts = {"conversations": len(going), "messages": messages,
              "facts": len(facts)}
    record = {
        "preview_id": preview_id, "confirm_id": confirm_id,
        "generated_at": now, "expires_at": expires_at,
        "window": window, "parser": parser,
        "include_facts": include_facts, "include_pinned": include_pinned,
        "client": str(client or ""),
        "conversation_ids": going_ids,
        "fact_ids": [f["id"] for f in facts],
        "fact_names": [f["text"] for f in facts],
        "counts": counts,
        "kept_pinned": len(kept_pinned),
        "kept_pinned_ids": [c["id"] for c in kept_pinned],
        "kept_facts": len(kept_facts),
        "messages": messages,
        "estimated_bytes_freed": estimated,
        "step1_at": None,
        "db_bytes": db_bytes,
    }
    with _STATE_LOCK:
        _STATE["preview"] = record
        _STATE["last"] = None

    answer = {
        "ok": True, "schema": SCHEMA,
        "preview_id": preview_id,
        "generated_at": int(now), "expires_at": int(expires_at),
        "expires_in_seconds": int(PREVIEW_TTL),
        "window": window,
        "conversations": {
            "count": len(going),
            "per_day": [per_day[k] for k in sorted(per_day)],
            "message_count": messages,
            "kept_pinned_count": len(kept_pinned),
        },
        "facts": {
            "count": len(facts),
            "included": include_facts,
            "names": names,
            "names_shown": len(names),
            "names_truncated": max(0, len(facts) - len(names)),
            "kept_due_to_pinned": len(kept_facts),
        },
        "storage": {"db_bytes": db_bytes,
                    "estimated_bytes_freed": int(estimated),
                    "estimate": True},
        "irreversible": True,
        "warnings": warnings,
        "card": _card(record, going, facts, names, kept_pinned, kept_facts),
        "next": ("Read the card, then send confirm with step 1. The second yes "
                 "needs your Windows Hello PIN or your phone's fingerprint."),
    }
    _audit("history.purge.preview", {"chats": len(going), "facts": len(facts),
                                     "pinned_kept": len(kept_pinned)})
    return 200, answer


def _all_text(values) -> bool:
    return all(isinstance(v, str) and 0 < len(v) <= 64 for v in values)


def _card(record, going, facts, names, kept_pinned, kept_facts) -> dict:
    """The card both apps draw, in one place so the two cannot disagree.

    `details` is EVERY line of it, in reading order, already in plain words:
    the days and how many chats and messages each holds, the facts by their own
    words, what is kept and why, and the sentence that it cannot be undone. An
    app may draw it however it likes; it may not add a line of its own, exactly
    as the feature-guide rule says for a feature's own words.
    """
    window = record["window"]
    details = [f"Clear chats from {window['said']} on this PC."]
    for slot in sorted({(_day_of(c.get("updated") or c.get("started") or 0))
                        for c in going}):
        if not slot:
            continue
        same = [c for c in going
                if _day_of(c.get("updated") or c.get("started") or 0) == slot]
        msgs = sum(int(c.get("turns") or 0) for c in same)
        details.append(f"  {slot}: {len(same)} chat"
                       f"{'s' if len(same) != 1 else ''}, {msgs} message"
                       f"{'s' if msgs != 1 else ''}")
    if record["include_facts"] and record["fact_names"]:
        details.append(f"And {len(record['fact_names'])} fact"
                       f"{'s' if len(record['fact_names']) != 1 else ''} these chats "
                       f"taught, erased for good:")
        for name in names:
            details.append(f"  - {name}")
        if record["fact_names"] and len(record["fact_names"]) > len(names):
            details.append(f"  (and {len(record['fact_names']) - len(names)} more, "
                           f"not listed here)")
    elif not record["include_facts"]:
        details.append("The facts these chats taught are KEPT.")
    if kept_pinned:
        details.append(f"{len(kept_pinned)} pinned chat"
                       f"{'s' if len(kept_pinned) != 1 else ''} in these days "
                       f"{'are' if len(kept_pinned) != 1 else 'is'} kept.")
    if kept_facts:
        details.append(f"{len(kept_facts)} fact"
                       f"{'s' if len(kept_facts) != 1 else ''} from a pinned chat "
                       f"{'are' if len(kept_facts) != 1 else 'is'} kept with it.")
    details.append(_WORDS["irreversible"])
    details.append("This is asked twice: yes now, then your Windows Hello PIN or "
                   "your phone's fingerprint.")
    return {"title": f"Clear {len(going)} chat"
                     f"{'s' if len(going) != 1 else ''} from {window['said']}?",
            "details": details,
            "irreversible": True,
            "undo_seconds": 0,
            "first_yes": "confirm {step: 1} marks that you have read this card.",
            "second_yes": ("confirm {step: 2} needs the Windows Hello / fingerprint "
                           "ticket, and is the only thing that deletes."),
            "counts": dict(record["counts"]),
            "kept": {"pinned": len(kept_pinned), "facts_from_pinned": len(kept_facts)}}


# --------------------------------------------------------------------------
#   The two yeses and the only delete
# --------------------------------------------------------------------------

def _live_preview(preview_id, now: float) -> tuple:
    """(record, None) or (None, (code, answer)). Expiry is checked here, lazily,
    the same way the other timed things in this codebase do it."""
    with _STATE_LOCK:
        rec = _STATE.get("preview")
        if not rec or rec.get("preview_id") != preview_id:
            return None, (404, _fail("no_preview"))
        if now >= float(rec.get("expires_at") or 0):
            _STATE["preview"] = None
            return None, (410, _fail("no_preview"))
        return dict(rec), None


def confirm(body, *, now: Optional[float] = None, chats=None, mem=None,
            client: str = "") -> tuple:
    """POST /api/history/purge/confirm - the FIRST yes, then the SECOND yes.

    Step 1 records that the owner read the card and answers `restated`: the
    exact counts again, so the second screen cannot be built from a stale
    memory. It deletes nothing and issues the `confirm_id`.

    Step 2 is the only code in this module that removes a row. It needs the
    `confirm_id` step 1 issued AND a platform ticket AND a live preview. Any one
    missing and nothing is touched.
    """
    now = _now() if now is None else float(now)
    if not isinstance(body, dict):
        return 400, _fail("bad_request")
    known = {"preview_id", "confirm_id", "step", "auth_ticket"}
    if set(body) - known:
        return 400, _fail("bad_request")
    preview_id = body.get("preview_id")
    step = body.get("step")
    if not isinstance(preview_id, str) or not preview_id or len(preview_id) > 64:
        return 400, _fail("bad_request")
    if isinstance(step, bool) or not isinstance(step, int) or step not in (1, 2):
        return 400, _fail("bad_request")

    locked, why = _private_locked()
    if locked:
        out = _fail("locked", "locked")
        out["why"] = why
        return 423, out

    rec, refused = _live_preview(preview_id, now)
    if refused:
        return refused
    if step == 1:
        return _first_yes(rec, now)

    confirm_id = body.get("confirm_id")
    if not isinstance(confirm_id, str) or confirm_id != rec["confirm_id"]:
        return 400, _fail("no_first_yes")
    if not rec.get("step1_at"):
        return 400, _fail("no_first_yes")
    ticket = body.get("auth_ticket")
    ok, method_or_fail = verify_ticket(ticket, preview_id, confirm_id,
                                       client=client, now=now)
    if not ok:
        code = 401
        out = dict(method_or_fail)
        if out.get("error") in ("no_key",):
            code = 503
        elif out.get("error") in ("expired_ticket", "ticket_reused",
                                  "wrong_platform"):
            code = 409
        _audit("history.purge.refused", {"why": str(out.get("error") or "")})
        return code, out
    return _execute(rec, now, chats=chats, mem=mem, client=client,
                    method=method_or_fail)


def _first_yes(rec, now: float) -> tuple:
    """The FIRST yes: recorded, nothing deleted."""
    with _STATE_LOCK:
        live = _STATE.get("preview")
        if not live or live.get("preview_id") != rec["preview_id"]:
            return 404, _fail("no_preview")
        if live.get("step1_at"):
            return 409, _fail("already_confirmed")
        live["step1_at"] = now
        counts = dict(live["counts"])
        confirm_id = live["confirm_id"]
        window = dict(live["window"])
        kept_pinned = int(live["kept_pinned"])
        kept_facts = int(live["kept_facts"])
        include_facts = bool(live["include_facts"])
        include_pinned = bool(live["include_pinned"])
    _audit("history.purge.first_yes", {"chats": counts["conversations"],
                                       "facts": counts["facts"]})
    return 200, {
        "ok": True, "confirmed": True, "next": "second_yes_required",
        "confirm_id": confirm_id,
        "restated": {
            "preview_id": rec["preview_id"],
            "window": window,
            "conversations": counts["conversations"],
            "messages": counts["messages"],
            "facts": counts["facts"],
            "include_facts": include_facts,
            "include_pinned": include_pinned,
            "kept_pinned": kept_pinned,
            "kept_facts_from_pinned": kept_facts,
            "irreversible": True,
            "cannot_be_undone": True,
        },
        "message": ("That is the first yes. Nothing has been deleted. Send step 2 "
                    "with your Windows Hello PIN or your phone's fingerprint to "
                    "delete them - this cannot be undone."),
    }


def _execute(rec, now: float, *, chats=None, mem=None, client: str = "",
             method: str = "") -> tuple:
    """The only delete in this module. Runs with BOTH yeses and a checked ticket.

    Defensive rules, all of them about not deleting one thing more than the card
    said: a chat pinned since the preview is skipped, a fact whose chat was kept
    is not touched, and a missing row is simply not there. Everything it did is
    counted, audited and timed.
    """
    started = time.monotonic()
    log = _log(chats)
    store = _store(mem)
    ids = [i for i in rec["conversation_ids"] if isinstance(i, str)]
    fact_ids = [i for i in rec["fact_ids"] if isinstance(i, int)]

    # A chat PINNED AFTER the card is a pin the owner meant: skip it, and say so.
    pinned_now = _pinned_ids(log, ids) if ids else set()
    skipped_pinned = []
    if not rec["include_pinned"] and pinned_now:
        skipped_pinned = [i for i in ids if i in pinned_now]
        ids = [i for i in ids if i not in pinned_now]

    deleted_chats = 0
    deleted_messages = 0
    # ONE transaction for the whole batch, not one delete per chat - and that is
    # a measured choice, not a style one (2026-11-04): `delete()` opens the
    # database, reads the chat's words and runs the receipts scrub PER CHAT,
    # which measured 18.9 ms a chat here with only 200 receipt rows. On the
    # owner's own PC, whose receipts store holds far more, that is minutes for a
    # batch he asked to clear. `take_out()` is the same removal in one
    # transaction (`_drop`, secure_delete, the usual VACUUM) and hands back the
    # rows sealed as they were - which is exactly what `purge_held_receipts()`
    # needs to scrub their words out of the receipts store in ONE pass.
    #
    # THE HELD ROWS ARE DROPPED AT ONCE. They exist only so the receipts scrub
    # can read them; this action has no Undo, so nothing here keeps a copy in
    # memory, and the name is cleared as soon as the scrub returns.
    held = {}
    if ids:
        try:
            held = log.take_out(ids) or {}
        except Exception:
            held = {}
        deleted_chats = len(held)
        for h in held.values():
            if isinstance(h, dict):
                deleted_messages += len(h.get("turns") or [])
        if held:
            try:
                log.purge_held_receipts(held)
            except Exception:
                pass
    held = {}

    deleted_facts = 0
    kept_fact_ids = []
    keep_set = set(rec.get("kept_pinned_ids") or [])
    for fid in fact_ids:
        if keep_set:
            try:
                live = _fact_conversation(store, fid)
            except Exception:
                live = None
            if live and live in keep_set:
                kept_fact_ids.append(fid)
                continue
        try:
            out = store.erase(int(fid))
        except Exception:
            out = None
        if isinstance(out, dict):
            deleted_facts += 1

    elapsed_ms = int(round((time.monotonic() - started) * 1000))
    audit_id = str(uuid.uuid4())
    line = {
        "audit_id": audit_id,
        "at": int(now),
        "window": {"from": rec["window"].get("from"), "to": rec["window"].get("to")},
        "preview_id": rec["preview_id"],
        "confirm_id": rec["confirm_id"],
        "auth_method": method,
        "client": str(client or "--"),
        "deleted": {"conversations": deleted_chats, "messages": deleted_messages,
                    "facts": deleted_facts},
        "kept": {"pinned": len(skipped_pinned), "pinned_after_preview":
                 len(skipped_pinned), "facts_from_pinned": len(kept_fact_ids)},
        "estimated_bytes_freed": int(rec.get("estimated_bytes_freed") or 0),
        "elapsed_ms": elapsed_ms,
        "measured": "monotonic clock around the deletes on this PC",
    }
    _write_audit(line)
    with _STATE_LOCK:
        _STATE["preview"] = None
        _STATE["last"] = {"audit_id": audit_id, "at": int(now),
                          "deleted": dict(line["deleted"]),
                          "elapsed_ms": elapsed_ms}
    _audit("history.purge.deleted", {"chats": deleted_chats,
                                     "facts": deleted_facts,
                                     "elapsed_ms": elapsed_ms,
                                     "auth": method})
    return 200, {
        "ok": True, "confirmed": True, "deleted": dict(line["deleted"]),
        "kept": {"pinned": len(skipped_pinned),
                 "facts_from_pinned": len(kept_fact_ids)},
        "audit_id": audit_id,
        "elapsed_ms": elapsed_ms,
        "irreversible": True,
        "message": (f"Deleted {deleted_chats} chat"
                    f"{'s' if deleted_chats != 1 else ''}, "
                    f"{deleted_messages} message"
                    f"{'s' if deleted_messages != 1 else ''} and {deleted_facts} "
                    f"fact{'s' if deleted_facts != 1 else ''} from this PC in "
                    f"{elapsed_ms} ms. This cannot be undone."),
    }


def _fact_conversation(store, fact_id: int) -> str:
    """The conversation a fact still records, or "". Read fresh, at execution
    time, so the pinned-chat rule is applied to what is true now."""
    try:
        st = store
        with closing(st._connect()) as c:
            row = c.execute("SELECT meta FROM facts WHERE id=?", (int(fact_id),)).fetchone()
        if row is None:
            return ""
        meta = json.loads(row["meta"]) if row["meta"] else {}
        cid = meta.get("conversation_id") if isinstance(meta, dict) else None
        return cid if isinstance(cid, str) else ""
    except Exception:
        return ""


def cancel(body, *, now: Optional[float] = None) -> tuple:
    """POST /api/history/purge/cancel - drop the preview. Deletes nothing that
    is stored; it only means the second yes can no longer find a preview."""
    now = _now() if now is None else float(now)
    if not isinstance(body, dict):
        return 400, _fail("bad_request")
    if set(body) - {"preview_id"}:
        return 400, _fail("bad_request")
    preview_id = body.get("preview_id")
    if preview_id is not None and not isinstance(preview_id, str):
        return 400, _fail("bad_request")
    locked, why = _private_locked()
    if locked:
        out = _fail("locked", "locked")
        out["why"] = why
        return 423, out
    with _STATE_LOCK:
        rec = _STATE.get("preview")
        if preview_id and (not rec or rec.get("preview_id") != preview_id):
            return 404, _fail("no_preview")
        _STATE["preview"] = None
    _audit("history.purge.cancelled", {})
    return 200, {"ok": True, "cancelled": True,
                 "message": ("Cancelled. Nothing was deleted and the second yes "
                             "can no longer run.")}


# --------------------------------------------------------------------------
#   The record of a deletion: counts and ids only, never a word
# --------------------------------------------------------------------------

def audit_path() -> Path:
    return _config_dir() / AUDIT_NAME


def _write_audit(line: dict) -> None:
    """Append ONE line to ~/.openjarvis/purge-audit.jsonl.

    Counts, window, both ids, the auth method, the elapsed time - and no title,
    message or word of any fact. Best effort: a deletion that already happened
    must not raise because a log file could not be opened, but the row is
    retried once as a plain `open` before that is accepted.
    """
    text = json.dumps(line, ensure_ascii=False, sort_keys=True)
    path = audit_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
            handle.flush()
        return
    except Exception:
        pass
    try:
        with open(str(path), "a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    except Exception:
        pass


def read_audit(limit: int = 50) -> list:
    """The newest audit lines, for the apps (counts only, so nothing private)."""
    out = []
    try:
        lines = audit_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for raw in lines[-max(0, int(limit)):]:
        try:
            got = json.loads(raw)
        except Exception:
            continue
        if isinstance(got, dict):
            out.append(got)
    return out


# --------------------------------------------------------------------------
#   What Jarvis knows about its own history - measured, never estimated
# --------------------------------------------------------------------------

#: The measured purge speed, this process only, keyed by the row count measured.
_SPEED: dict = {}

#: How many chats and messages the on-demand benchmark builds. Small enough to
#: finish in a blink, large enough that one delete's fixed cost does not
#: dominate: one delete is what a purge does, N times.
BENCH_CHATS = 120
BENCH_TURNS = 6


def _speed_path() -> Path:
    return _config_dir() / SPEED_NAME


def _cached_speed(now: float) -> Optional[dict]:
    """The last measured speed from THIS process, else from a previous one.

    A cached number is only used when it says how it was measured and is less
    than a year old. Anything else is re-measured rather than quoted."""
    with _STATE_LOCK:
        got = _SPEED.get("last")
        if got:
            return dict(got)
    try:
        raw = json.loads(_speed_path().read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        if raw.get("schema") != SCHEMA or not raw.get("measured"):
            return None
        if now - float(raw.get("at") or 0) > 365 * 86400:
            return None
        for key in ("chats", "messages", "elapsed_ms"):
            if not isinstance(raw.get(key), int) or raw[key] <= 0:
                return None
        return raw
    except Exception:
        return None


def benchmark(chats_count: int = BENCH_CHATS, turns: int = BENCH_TURNS) -> dict:
    """Measure how long a purge TOOK on THIS PC, on a COPY - never on the live file.

    Two ways, in this order, because they answer the same question at different
    costs:

      1. A COPY OF THIS PC'S OWN HISTORY. `chat-history.db` is copied into a
         temporary folder and every chat in the COPY is removed with the same
         two calls a purge makes, timed with a monotonic clock. Real chats,
         real page sizes, real receipts scrub - and the live file is opened
         once, to read it, and never written. This is what runs on a PC with
         any history on it, and it takes well under a second.
      2. A SYNTHETIC history, built here with the real `ChatLog`, for a PC with
         no history yet. Slower to build, and it says so in `source` rather
         than pretending to be the same measurement.

    Either way the receipts store is pointed at the temporary folder for the
    length of the run (`JARVIS_RECEIPTS_DB`), so the scrub a purge really pays
    is really paid and the owner's own receipts are never opened. Measured
    2026-11-04: with that line missing, 34 of the 35 ms per chat was the
    owner's live receipts table.

    `where` and `source` say which of the two answered. Nothing here deletes
    anything that is not inside `work`, and `work` is removed before returning
    (a leftover folder is itself a thing this module's suite checks for).
    """
    work = Path(tempfile.mkdtemp(prefix="jarvis-purge-bench-"))
    receipts = 0
    started = 0.0
    deleted = 0
    messages = 0
    elapsed_ms = 0
    source = ""
    chats_there = 0
    scrub_words = 0
    # ISOLATION, and it is not optional: `purge_held_receipts` and `delete`
    # both reach the receipts store, which reads `JARVIS_RECEIPTS_DB` or the
    # live config folder. Pointed at `work` for the length of the run.
    import jarvis_receipts as RCPT
    old_receipts_env = os.environ.get(RCPT.DB_ENV)
    os.environ[RCPT.DB_ENV] = str(work / "receipts.db")
    try:
        receipts = _bench_receipts(RCPT, work / "receipts.db")
    except Exception:
        receipts = 0
    try:
        import jarvis_chat_log as CH
        live = Path(getattr(_log(), "db_path"))
        copied = False
        if live.exists() and live.stat().st_size < 64 * 1024 * 1024:
            try:
                copied = _bench_on_copy(CH, live, work)
            except Exception:
                copied = False
        if copied:
            source = ("a COPY of this PC's own history in a temp folder - the live "
                      "file was read once and never written")
            log = _BENCH["log"]
            ids = _BENCH["ids"]
            messages = _BENCH["messages"]
            chats_there = len(ids)
            started = time.monotonic()
            held = log.take_out(ids) or {}
            deleted = len(held)
            # THE RECEIPTS SCRUB IS PAID HERE, DELIBERATELY (audit finding 2).
            # `purge_held_receipts` needs the live key to read a held row's
            # words, and a COPY cannot have it - so on this path it would
            # silently return 0 and the number quoted to the owner would leave
            # out a cost a real purge pays: one pass over the receipts table per
            # 200 words. The same number of passes is paid here with this
            # benchmark's own throwaway phrases, which touch nothing.
            try:
                words = _bench_words(messages)
                scrub_words = len(words)
                RCPT.purge_many(words)
            except Exception:
                scrub_words = 0
            held = {}
            elapsed_ms = int(round((time.monotonic() - started) * 1000))
        else:
            source = "a SYNTHETIC history built for this measurement (this PC has none yet)"
            built = _bench_synthetic(CH, work, chats_count, turns)
            messages = built["messages"]
            chats_there = built["chats"]
            started = time.monotonic()
            held = built["log"].take_out(built["ids"]) or {}
            deleted = len(held)
            try:
                # The synthetic rows were sealed with a key this process still
                # holds, so the real scrub runs here and its cost is real.
                built["log"].purge_held_receipts(held)
            except Exception:
                pass
            held = {}
            elapsed_ms = int(round((time.monotonic() - started) * 1000))
    finally:
        if old_receipts_env is None:
            os.environ.pop(RCPT.DB_ENV, None)
        else:
            os.environ[RCPT.DB_ENV] = old_receipts_env
        _BENCH.clear()
        try:
            for p in sorted(work.rglob("*"), reverse=True):
                try:
                    p.unlink()
                except OSError:
                    pass
            work.rmdir()
        except OSError:
            pass
    out = {"schema": SCHEMA, "measured": True, "at": int(_now()),
           "chats": deleted, "built": chats_there, "messages": messages,
           "receipts_rows": receipts, "receipts_words": scrub_words,
           "elapsed_ms": elapsed_ms,
           "per_chat_ms": round(elapsed_ms / deleted, 3) if deleted else None,
           "method": ("the same two calls a purge makes - one take_out() for the "
                      "whole batch and one purge_held_receipts() against a temp "
                      "receipts store - timed with a monotonic clock"),
           "source": source,
           "where": "this PC, a copy - never the live chat history"}
    with _STATE_LOCK:
        _SPEED["last"] = dict(out)
    try:
        path = _speed_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        pass
    return out


#: The copy (or synthetic history) the benchmark is timing, held here between
#: the two halves of `benchmark()` and dropped in its `finally`.
_BENCH: dict = {}


def _bench_on_copy(CH, live: Path, work: Path) -> bool:
    """Copy the live history into `work`, open the COPY, and list its chats.

    The copy is opened by a `ChatLog` of its own, and nothing here needs the
    encryption key: `take_out()` copies the sealed rows exactly as they are, it
    does not open them. That is also why a copy of a real history measures the
    real thing (real row sizes, real indexes) instead of a made-up one.
    """
    import shutil
    target = work / "live-copy.db"
    shutil.copyfile(str(live), str(target))
    wal = Path(str(live) + "-wal")
    if wal.exists():
        # The -wal holds the newest rows; without it the copy is older than the
        # file it claims to be. ChatLog opens it by the same name.
        try:
            shutil.copyfile(str(wal), str(target) + "-wal")
        except OSError:
            pass
    cop = CH.ChatLog(target, work / "live-copy.json", lambda: b"")
    with closing(cop._connect()) as c:
        ids = [str(r[0]) for r in c.execute(
            "SELECT id FROM conversations ORDER BY updated").fetchall()]
        messages = int(c.execute("SELECT COUNT(*) FROM turns").fetchone()[0] or 0)
    if not ids:
        return False
    _BENCH.update(log=cop, ids=ids, messages=messages)
    return True


def _bench_synthetic(CH, work: Path, chats_count: int, turns: int) -> dict:
    """A history built here, for a PC that has none yet.

    The rows are written straight into a real `ChatLog`'s schema instead of
    through `record_turn()`: this measures REMOVAL, and `record_turn` spends
    its time sealing words and running the learner, which would report a number
    dominated by setup rather than by the delete. Each message's `text` is the
    same size as a sealed one (a 240-byte blob), so the pages the delete walks
    are the pages a real history has. `source` in the answer says this was
    synthetic - it is never presented as the owner's own history.
    """
    chats_count = max(1, min(2000, int(chats_count)))
    turns = max(2, min(200, int(turns)))
    at = 1_700_000_000.0
    # A clock that ADVANCES with real time: `take_out()` vacuums at most once an
    # hour (`_VACUUM_EVERY`), and a frozen clock would make it vacuum on every
    # call - which is not what a real purge does.
    t0 = time.monotonic()

    def clock():
        return at + (time.monotonic() - t0)

    log = CH.ChatLog(work / "synthetic.db", work / "synthetic.json",
                     lambda: secrets.token_bytes(32), clock=clock)
    ids = []
    with closing(log._connect()) as c:
        with c:
            for i in range(chats_count):
                cid = f"bench-purge-{i:06d}"
                ids.append(cid)
                c.execute(
                    "INSERT INTO conversations (id, title, started, updated, device,"
                    " kind, pinned, pinned_at) VALUES (?,?,?,?,?,?,?,?)",
                    (cid, os.urandom(40), at + i * 10, at + i * 10 + turns,
                     "desktop", "chat", None, None))
                for j in range(turns):
                    c.execute(
                        "INSERT INTO turns (conversation_id, idx, at, role, provenance,"
                        " device, lane, read_outside, answer_kept, voice_check, text)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (cid, j, at + i * 10 + j, "user", "typed", "desktop",
                         "bench", 0, 0, "", os.urandom(240)))
        messages = int(c.execute("SELECT COUNT(*) FROM turns").fetchone()[0] or 0)
    return {"log": log, "ids": ids, "messages": messages, "chats": chats_count}


def _bench_words(messages: int, cap: int = 20000) -> list:
    """As many throwaway phrases as the purge would hand the receipts scrub, so
    the same number of table passes is paid. They are this benchmark's own
    words: nothing in a real receipts store contains them, so nothing is
    matched and nothing is written."""
    return [f"benchmark phrase {i} of the purge timing run"
            for i in range(min(max(0, int(messages)), cap))]


def _bench_receipts(rcpt, path: Path, rows: int = 120) -> int:
    """Fill a THROWAWAY receipts store with ordinary rows, for the benchmark.

    The scrub a purge does is part of what a purge costs, so leaving it out
    would report a number this PC would never see; but running it against the
    owner's own receipts would read the live folder. So the benchmark builds its
    own store and pays the real cost there. The rows hold none of the words the
    benchmark's chats use, so nothing is matched and nothing is written.

    ONE `executemany` in ONE transaction, deliberately: this connection is in
    autocommit mode, and 200 single inserts measured 2.06 s here - each is its
    own commit and its own fsync on this disk. That is setup cost leaking into
    a feature whose whole point is a measured number, so it is paid once, in
    one transaction.

    Returns how many rows the store has, or 0 when it could not be made.
    """
    conn = sqlite3.connect(str(path), timeout=10.0, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(rcpt.SCHEMA)
        conn.execute("BEGIN")
        try:
            conn.executemany(
                "INSERT INTO action_receipts (receipt_id, created_at, tool_name,"
                " summary, before_snapshot_json, after_snapshot_json)"
                " VALUES (?,?,?,?,?,?)",
                [(f"bench-receipt-{i:05d}", 1_700_000_000 + i, "bench",
                  "opened a file on this PC", '{"path": "/x"}', '{"ok": true}')
                 for i in range(max(0, int(rows)))])
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        got = conn.execute("SELECT COUNT(*) FROM action_receipts").fetchone()[0]
        return int(got or 0)
    finally:
        conn.close()


def capability(*, now: Optional[float] = None, chats=None, mem=None,
               measure: bool = True) -> dict:
    """What Jarvis knows about its own chats, from MEASURED state.

    This is the answer to the owner's own question - "how long does it take for
    you to clear old chats if i batched a lot of them together?" - and to
    "where are my chats stored", "how big is it", "do they expire". Every number
    is read now, from this PC, and anything that could not be read says so with
    the reason instead of a comfortable guess.

    The measured purge speed comes from `benchmark()`: a COPY, once, cached to
    `~/.openjarvis/purge-speed.json` so a restart does not re-run it. If the
    benchmark cannot run, `purge_speed.measured` is False and the sentence says
    that it could not be measured - it never guesses.
    """
    now = _now() if now is None else float(now)
    unknown = []
    out = {"schema": SCHEMA, "measured_at": int(now), "unknown": unknown}

    locked, why = _private_locked()
    if locked:
        # The counts are exactly what App lock hides. Say what is withheld.
        return {"schema": SCHEMA, "measured_at": int(now),
                "unknown": ["everything: the memory lists and chat history are "
                            "hidden on this PC right now"],
                "locked": True, "why": why,
                "words": ("The memory lists and chat history are hidden on this "
                          "PC right now, so I will not report their counts or "
                          "size. " + why)}
    try:
        log = _log(chats)
    except Exception as exc:
        unknown.append(f"the chat history module ({type(exc).__name__})")
        log = None

    store = None
    try:
        store = _store(mem)
    except Exception as exc:
        unknown.append(f"the memory module ({type(exc).__name__})")

    where = {"db": "", "folder": str(_config_dir()), "encrypted_at_rest": True,
             "key_store": "Windows Credential Manager"}
    size = {"db_bytes": 0, "wal_bytes": 0, "total_bytes": 0}
    counts = {"conversations": 0, "pinned": 0, "archived": 0, "messages": 0,
              "facts": 0}
    facts_known = False
    recording = {"enabled": None, "keep_days": None, "expires": None,
                 "why_not": ""}

    if log is not None:
        try:
            db = Path(getattr(log, "db_path"))
            where["db"] = str(db)
            size["db_bytes"] = int(db.stat().st_size) if db.exists() else 0
            wal = Path(str(db) + "-wal")
            size["wal_bytes"] = int(wal.stat().st_size) if wal.exists() else 0
            size["total_bytes"] = size["db_bytes"] + size["wal_bytes"]
        except Exception as exc:
            unknown.append(f"the history file's size ({type(exc).__name__})")
        try:
            with closing(log._connect()) as c:
                counts["conversations"] = int(c.execute(
                    "SELECT COUNT(*) FROM conversations").fetchone()[0] or 0)
                counts["pinned"] = int(c.execute(
                    "SELECT COUNT(*) FROM conversations WHERE pinned=1"
                    " AND pinned_at IS NOT NULL").fetchone()[0] or 0)
                counts["archived"] = int(c.execute(
                    "SELECT COUNT(*) FROM conversations WHERE archived_at IS NOT NULL"
                ).fetchone()[0] or 0)
                counts["messages"] = int(c.execute(
                    "SELECT COUNT(*) FROM turns").fetchone()[0] or 0)
        except Exception as exc:
            unknown.append(f"the chat counts ({type(exc).__name__})")
        try:
            st = log.settings()
            recording["enabled"] = bool(st.get("enabled"))
            recording["keep_days"] = int(st.get("keep_days") or 0)
            recording["expires"] = bool(recording["keep_days"])
            recording["why_not"] = str(st.get("why") or "")
        except Exception as exc:
            unknown.append(f"the chat-history switch ({type(exc).__name__})")

    if store is not None:
        try:
            with closing(store._connect()) as c:
                counts["facts"] = int(c.execute(
                    "SELECT COUNT(*) FROM facts WHERE erased_at IS NULL"
                    " AND (valid_to IS NULL OR valid_to > ?)", (now,)).fetchone()[0] or 0)
            facts_known = True
        except Exception as exc:
            unknown.append(f"the fact count ({type(exc).__name__})")

    speed = _cached_speed(now)
    if speed is None and measure:
        try:
            speed = benchmark()
        except Exception as exc:
            unknown.append(f"a measured purge ({type(exc).__name__})")
            speed = None
    purge_speed = {"measured": bool(speed), "chats": None, "elapsed_ms": None,
                   "per_chat_ms": None, "at": None}
    if speed:
        purge_speed.update({"chats": speed.get("chats"),
                            "messages": speed.get("messages"),
                            "elapsed_ms": speed.get("elapsed_ms"),
                            "per_chat_ms": speed.get("per_chat_ms"),
                            "at": speed.get("at")})

    out.update({"where": where, "size": size, "conversations": counts,
                "facts_known": facts_known,
                "recording": recording, "purge_speed": purge_speed,
                "route": {"preview": PREVIEW_PATH, "confirm": CONFIRM_PATH,
                          "cancel": CANCEL_PATH},
                "irreversible": True})
    out["words"] = _capability_words(out)
    return out


def _capability_words(me: dict) -> str:
    """One honest paragraph, built only from the measurements above."""
    who = me["conversations"]
    size = me["size"]
    rec = me["recording"]
    speed = me["purge_speed"]
    parts = []
    parts.append(
        f"Your chats are kept on this PC, encrypted, in {me['where']['db'] or 'the history file'} "
        f"({size['total_bytes']:,} bytes on disk). "
        f"There are {who['conversations']} conversations with {who['messages']} messages in "
        f"all, {who['pinned']} of them pinned and {who['archived']} archived" +
        (f", plus {who['facts']} facts in what I remember."
         if me.get("facts_known") else
         ", and I could not count the facts I remember."))
    if rec["enabled"] is None:
        parts.append("I could not read the chat-history switch, so I will not "
                     "claim whether it is on.")
    elif not rec["enabled"]:
        parts.append("Recording is OFF right now, so new chats are not kept - "
                     "what is already here is still here.")
    elif rec["expires"]:
        parts.append(f"Recording is on and chats expire after {rec['keep_days']} "
                     f"days by the retention setting.")
    else:
        parts.append("Recording is on and nothing expires automatically: the "
                     "retention setting is 0, which means keep until you delete.")
    if speed["measured"]:
        parts.append(
            f"Clearing a batch: I measured it on this PC on a copy of a history, "
            f"not on yours - deleting {speed['chats']} chats ({speed['messages']} "
            f"messages) took {speed['elapsed_ms']} ms, about "
            f"{speed['per_chat_ms']} ms a chat. A batch of "
            f"{who['conversations']} like that would be roughly "
            f"{int(round(who['conversations'] * (speed['per_chat_ms'] or 0)))} ms "
            f"of deleting; the card and the two yeses take as long as you take.")
    else:
        parts.append("I have not measured a clearing run on this PC yet, so I "
                     "will not guess how long one takes.")
    parts.append(
        "Clearing by date exists: it keeps your pinned chats unless you say "
        "otherwise, it can clear the facts those chats taught, it shows you a "
        "card with every count and every fact by name, it asks twice, and the "
        "second yes needs your Windows Hello PIN or your phone's fingerprint. "
        "It cannot be undone.")
    if me.get("unknown"):
        parts.append("I could not read: " + "; ".join(me["unknown"]) + ".")
    return " ".join(parts)


# --------------------------------------------------------------------------
#   The routes on the running server
# --------------------------------------------------------------------------

def handle_post(route: str, body, **kw) -> tuple:
    if route == PREVIEW_PATH:
        keep = {k: kw[k] for k in ("now", "chats", "mem", "client") if k in kw}
        return preview(body, **keep)
    if route == CONFIRM_PATH:
        keep = {k: kw[k] for k in ("now", "chats", "mem", "client") if k in kw}
        return confirm(body, **keep)
    if route == CANCEL_PATH:
        keep = {k: kw[k] for k in ("now",) if k in kw}
        return cancel(body, **keep)
    return 404, {"ok": False, "error": "no such route"}


def handle_get(route: str, query: str = "") -> tuple:
    """No GET at all: the three routes measure with a body or delete, and the
    capability answer is `capability()` (the chat fast path and, if an app ever
    needs it, its own route in its own change). Serving it here as a fourth,
    undocumented GET was a surface nobody had asked for - found in this
    module's own audit and removed rather than documented."""
    if route in ROUTES:
        return 405, {"ok": False, "error": "use POST for this"}
    return 404, {"ok": False, "error": "no such route"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so these routes are answered here,
    after the server's own origin and token checks. Every other request goes
    straight to the original. Returns the banner line."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_history_purge", False):
        return "  purge      Clear old chats by date (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def _client(self) -> str:
        try:
            headers = getattr(self, "headers", {}) or {}
            return str(headers.get("X-Jarvis-Client", "") or "")
        except Exception:
            return ""

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in ROUTES:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in ROUTES:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(route, body, client=_client(self))
        except Exception as exc:
            code, out = 503, {"available": False, "ok": False,
                              "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_history_purge = True
    do_POST._jarvis_history_purge = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    try:
        auth_key()
        key_note = f"key in {key_path()}"
    except Exception as exc:
        key_note = f"NO KEY ({type(exc).__name__}) - a Windows Hello yes cannot be checked"
    return (f"  purge      Clear old chats by date: a card, two yeses, "
            f"Windows Hello / fingerprint ({key_note})")


def startup() -> str:
    """Called once at start-up: make the key file now rather than at the first
    purge, so a PC that cannot write it says so on the banner. Never raises."""
    try:
        auth_key()
        return f"key file ready: {key_path()}"
    except Exception as exc:
        return f"NO KEY ({type(exc).__name__}): a Windows Hello yes cannot be checked"


# --------------------------------------------------------------------------
#   Test hooks
# --------------------------------------------------------------------------

_STATE: dict = {"preview": None, "last": None}


def _reset_for_tests() -> None:
    with _STATE_LOCK:
        _STATE.update(preview=None, last=None)
        _USED.clear()
        _SPEED.clear()
    _KEY_CACHE.clear()
