"""jarvis_chat_log.py - chat history, kept on this PC, encrypted.

NEW MODULE, shipped whole (chat-history.patch calls it from /api/chat and
adds the /api/history routes; docs/JARVIS-API.md section 18).

WHAT IT IS FOR
The owner decided on 2026-09-24 that chat history, including what is said to
Jarvis by voice, is kept on the PC by default, encrypted, with a switch to
turn it off. Until now the only copy of a conversation was the one an app
held in memory, and it was gone when the app closed.

It is also the PC's OWN record of each turn, written as the turn arrives,
with where its words came from (`provenance`): typed, voice, shared from
another app, the clipboard, pasted, or words sent with a picture. The apps
re-send the whole conversation with every question, and a re-sent turn is
the app's say-so, not the PC's. Automatic learning (jarvis_auto_learn.py,
docs/JARVIS-API.md section 19) trusts this PC's record instead - through
the LIVE-TURN REGISTRY (_note_live, live_turn), which record_turn() writes
on every request WHETHER OR NOT history is on: in memory only, the newest
LIVE_MAX turns, a hash of each live message (never the words) with its
provenance, the voice check's facts, the conversation id, the app, and
whether a tool read outside text in that turn.

WHAT IS KEPT, per /api/chat request
  - The NEWEST user message only - the live one, never the re-sent history
    (plus, when the phone shared text, the shared message sent just before
    it in the same request; see _live_user_messages).
  - The answer, only when the local model made it through
    jarvis_agent.run_local_turn and it finished. A cloud answer is NOT kept:
    the user turn is recorded with answer_kept false.
  - `read_outside`: true when any tool ran in that turn (every tool result
    is text Jarvis did not get from the owner). From that turn on the
    conversation is `tainted`.
  - when, which app (`device`, informational only), which model (`lane`),
    and the turn's number in the conversation.
  - A picture: its words only, as `picture_caption`. The picture never.
Not kept: tool output, system or context messages, deep questions, wiki
jobs, notes (#obs, #log), approval cards - none of them come through here.

ENCRYPTION (CLAUDE.md rule 3)
Every piece of text - each turn, and each conversation's title - is
encrypted on its own with AES-256-GCM (the `cryptography` package) and a
fresh 12-byte nonce. The conversation id and turn number are the associated
data, so a row cannot be moved to another conversation or place and still
open. The key is 32 random bytes, kept in Windows Credential Manager under
KEY_TARGET (through jarvis_token_store.WindowsStore), made on first use and
read back before it is used.

FAIL CLOSED. If `cryptography` is missing, Credential Manager cannot be used,
or the key does not open what is already kept: NOTHING is recorded, nothing
is written in plain text, and status() says why in plain words
(`recording: false`, `why_not`). There is no plain-text fallback anywhere.

What is NOT encrypted, said plainly: the plain columns - conversation id,
turn number, times, role, provenance, device, model name, read_outside,
answer_kept. They say when and how often you talked to Jarvis, not what
about. The settings file (on/off and how long to keep) is plain too; it
holds no chat text.

KEEPING AND DELETING
`keep_days` is 0 (keep until deleted, the default), 30, 90 or 365.
Conversations whose last turn is older are deleted when this module is
first used after the backend starts, and then at most once a day. Deleting
removes the rows; SQLite would otherwise leave the deleted bytes in the
file's free pages until they are reused, so `secure_delete` is on (freed
content is overwritten with zeros) and VACUUM runs after a delete, at most
once an hour.

THE SWITCH (the same shape as jarvis_learning_switch.py)
  ON   one approval card, action `history_enable`, and 202 {"waiting": true}
       at once. Only tier "ask" with outcome "approved" turns it on.
  OFF  immediate, never a card; withdraws a waiting ON. What is already kept
       stays until it is deleted or expires.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid as _uuid
from collections import OrderedDict
from contextlib import closing
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    AESGCM = None  # type: ignore
    InvalidTag = Exception  # type: ignore

ACTION = "history_enable"

#: Where the key is filed in Credential Manager. The owner can see (and
#: delete) it in Control Panel -> Credential Manager -> Windows Credentials.
KEY_TARGET = "Jarvis Backend/chat history key"

#: What an app may say a user message's words came from. Anything else, or
#: nothing, is recorded as "unknown" - and "unknown" counts as NOT the
#: owner's own words to everything that cares.
PROVENANCES = ("typed", "voice", "shared", "clipboard", "pasted", "picture_caption")
DEVICES = ("desktop", "hud", "phone")
KEEP_DAYS = (0, 30, 90, 365)
VOICE_WINDOW = 600          # a transcript counts as voice for 10 minutes
LIVE_MAX = 200              # the live-turn registry holds this many turns
TITLE_CHARS = 80
LIST_DEFAULT, LIST_MAX = 30, 100
_CID = re.compile(r"[A-Za-z0-9_-]{8,64}")   # used with fullmatch: no trailing newline
_SWEEP_EVERY = 86400
_VACUUM_EVERY = 3600
_CHECK = b"jarvis chat history"

CARD_TEXT = "\n".join([
    "Turn chat history back on?",
    "",
    "Jarvis will keep your chats, including voice, on this PC, encrypted. "
    "Nothing leaves this PC.",
    "",
    "If you say no: chat history stays off.",
])

OFF_TEXT = ("Chat history is off. Nothing new is kept. What is already kept "
            "stays until you delete it.")


class KeyUnavailable(Exception):
    """The key could not be had. The message is plain words for the owner and
    never holds the key."""


# ------------------------------------------------------------------ the key

class CredentialKey:
    """The key in Windows Credential Manager, through
    jarvis_token_store.WindowsStore (reused, not copied).

    A key provider is any callable that returns the 32-byte key or raises
    KeyUnavailable; tests pass their own. (A later Docker option will need a
    provider that reads a secret file - not built.)
    """

    def __init__(self, target: str = KEY_TARGET, store_factory: Optional[Callable] = None):
        self.target = target
        self._factory = store_factory

    def _store(self):
        if self._factory is not None:
            return self._factory()
        try:
            import jarvis_token_store as ts
        except Exception:
            raise KeyUnavailable("jarvis_token_store.py is not installed, so the key "
                                 "cannot be kept in Credential Manager") from None
        try:
            return ts.WindowsStore(target=self.target)
        except ts.Unavailable:
            raise KeyUnavailable("there is no Windows Credential Manager on this "
                                 "system to keep the key in") from None
        except Exception as exc:
            raise KeyUnavailable(f"Credential Manager could not be opened "
                                 f"({type(exc).__name__})") from None

    def __call__(self) -> bytes:
        store = self._store()
        try:
            text = store.read()
            if text is None:
                made = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
                store.write(made)
                text = store.read()
                if text != made:
                    raise KeyUnavailable("a new key was saved in Credential Manager "
                                         "but could not be read back")
            key = base64.b64decode(text, validate=True)
        except KeyUnavailable:
            raise
        except Exception as exc:
            # StoreError carries a Windows error number only; anything else is
            # named by type, never by message, so no key text can reach a log.
            why = str(exc) if type(exc).__name__ == "StoreError" else type(exc).__name__
            raise KeyUnavailable(f"Credential Manager could not be used for the "
                                 f"chat history key ({why})") from None
        if len(key) != 32:
            raise KeyUnavailable("the chat history key in Credential Manager is not "
                                 "a 32-byte key")
        return key


def _config_dir() -> Path:
    """The same folder jarvis_voices._config_dir() uses (not imported from
    there: that module loads the voice engines)."""
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


# ----------------------------------------------------------- reading a turn

def _text_of(content):
    """(words, has_picture) of one message's content."""
    if isinstance(content, str):
        return content, False
    if isinstance(content, list):
        words, picture = [], False
        for part in content:
            if not isinstance(part, dict):
                continue
            kind = part.get("type")
            if kind == "text" and isinstance(part.get("text"), str):
                words.append(part["text"])
            elif kind in ("image_url", "image", "input_image") or "image_url" in part:
                picture = True
        return "\n".join(w for w in words if w), picture
    return "", False


def _live_user_messages(messages) -> list:
    """The user message(s) this request is really asking, oldest first.

    The newest user message only - everything before it is history the app
    re-sent. One exception: the phone sends shared text as its own message,
    `provenance: "shared"`, IMMEDIATELY before the owner's typed message in
    the same request (docs/JARVIS-API.md section 18). That one is live too,
    so it is kept with it. On the next request an answer sits between them,
    so it is never picked up twice."""
    if not isinstance(messages, list):
        return []
    at = None
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user":
            at = i
            break
    if at is None:
        return []
    out = [messages[at]]
    if at > 0:
        prev = messages[at - 1]
        if (isinstance(prev, dict) and prev.get("role") == "user"
                and prev.get("provenance") == "shared"
                and messages[at].get("provenance") != "shared"):
            out.insert(0, prev)
    return out


def _norm(text: str) -> str:
    return " ".join(str(text or "").split())


def _hash(text: str) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ the log

class ChatLog:
    """One history database. The module keeps one (see _log()); tests make
    their own with a temporary folder and a key provider of their own."""

    def __init__(self, db_path, settings_path, key_provider: Callable[[], bytes], *,
                 clock: Callable[[], float] = time.time, crypto: bool = True):
        self.db_path = Path(db_path)
        self.settings_path = Path(settings_path)
        self._provider = key_provider
        self._clock = clock
        self._crypto = crypto and AESGCM is not None
        self._lock = threading.RLock()
        self._aead = None
        self._last_sweep: Optional[float] = None
        self._last_vacuum = 0.0
        self._vacuum_due = False
        self._heard: dict = {}        # sha256 of a transcript -> (at, facts)
        # The live-turn registry (see _note_live): in memory only, hashes
        # and tags, never the words.
        self._live: "OrderedDict" = OrderedDict()   # (cid, sha256) -> entry
        self._taint: "OrderedDict" = OrderedDict()  # cid -> seq it was tainted from
        self._live_seq = 0

    # -- settings ---------------------------------------------------------
    def settings(self) -> dict:
        """{"enabled", "keep_days", "why"}. No file: on, keep forever - the
        owner's default. A file that cannot be read: OFF, and why - it may
        be the file that said off."""
        try:
            raw = self.settings_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"enabled": True, "keep_days": 0, "why": ""}
        except OSError as exc:
            return {"enabled": False, "keep_days": 0,
                    "why": f"the chat history settings file could not be read "
                           f"({type(exc).__name__}), so nothing is kept until it can"}
        try:
            d = json.loads(raw)
            enabled = d.get("enabled", True)
            keep = d.get("keep_days", 0)
            if not isinstance(enabled, bool) or keep not in KEEP_DAYS or isinstance(keep, bool):
                raise ValueError
        except Exception:
            return {"enabled": False, "keep_days": 0,
                    "why": f"the chat history settings file ({self.settings_path}) is "
                           f"damaged, so nothing is kept. Turn history off and on again "
                           f"to rewrite it"}
        return {"enabled": enabled, "keep_days": keep, "why": ""}

    def _save_settings(self, **changes) -> dict:
        with self._lock:
            cur = self.settings()
            new = {"enabled": cur["enabled"], "keep_days": cur["keep_days"]}
            new.update(changes)
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.settings_path.with_name(self.settings_path.name + ".tmp")
            tmp.write_text(json.dumps(new), encoding="utf-8")
            os.replace(tmp, self.settings_path)
            return new

    def set_enabled(self, on: bool) -> dict:
        self._save_settings(enabled=bool(on))
        return {"ok": True, "enabled": bool(on)}

    # -- the database -----------------------------------------------------
    def _connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(self.db_path), timeout=5.0)
        c.execute("PRAGMA secure_delete = ON")
        c.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v BLOB)")
        c.execute("CREATE TABLE IF NOT EXISTS conversations ("
                  " id TEXT PRIMARY KEY, title BLOB, started REAL, updated REAL,"
                  " device TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS turns ("
                  " conversation_id TEXT NOT NULL, idx INTEGER NOT NULL, at REAL,"
                  " role TEXT, provenance TEXT, device TEXT, lane TEXT,"
                  " read_outside INTEGER, answer_kept INTEGER, voice_check TEXT,"
                  " text BLOB, PRIMARY KEY (conversation_id, idx))")
        c.execute("CREATE INDEX IF NOT EXISTS conversations_updated"
                  " ON conversations (updated)")
        return c

    def _cipher(self):
        """The AES-GCM object, or KeyUnavailable with the reason in words."""
        # The whole of it under the lock, the key provider included: two
        # requests on first use each made a key, and the one cached for this
        # process could differ from the one Credential Manager kept - after a
        # restart the history could not be opened at all (chat history
        # audit, 2026-09-24, reproduced).
        with self._lock:
            return self._cipher_locked()

    def _cipher_locked(self):
        if self._aead is not None:
            return self._aead
        if not self._crypto:
            raise KeyUnavailable("the encryption package (cryptography) is not "
                                 "installed on this PC, so nothing is kept. Install it "
                                 "with: py -3 -m pip install -r backend\\requirements.txt")
        key = self._provider()
        if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
            raise KeyUnavailable("the chat history key is not a 32-byte key")
        aead = AESGCM(bytes(key))
        with closing(self._connect()) as c:
            row = c.execute("SELECT v FROM meta WHERE k='check'").fetchone()
            if row is None:
                with c:
                    c.execute("INSERT INTO meta (k, v) VALUES ('check', ?)",
                              (self._seal(aead, _CHECK, b"check"),))
            else:
                try:
                    ok = self._open(aead, row[0], b"check") == _CHECK
                except Exception:
                    ok = False
                if not ok:
                    raise KeyUnavailable(
                        "the key in Credential Manager does not open the chat history "
                        "kept on this PC (it was replaced or deleted), so nothing new is "
                        "kept. To start again with an empty history, stop Jarvis and "
                        f"delete {self.db_path}")
        self._aead = aead
        return aead

    @staticmethod
    def _seal(aead, plain: bytes, aad: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + aead.encrypt(nonce, plain, aad)

    @staticmethod
    def _open(aead, blob: bytes, aad: bytes) -> bytes:
        blob = bytes(blob)
        return aead.decrypt(blob[:12], blob[12:], aad)

    @staticmethod
    def _aad(cid: str, idx) -> bytes:
        return f"{cid}|{idx}".encode("utf-8")

    def _recording(self):
        """(aead or None, why_not)."""
        st = self.settings()
        if not st["enabled"]:
            return None, st["why"] or "Chat history is off."
        try:
            return self._cipher(), ""
        except KeyUnavailable as exc:
            return None, str(exc)
        except Exception as exc:
            return None, f"the chat history could not be opened ({type(exc).__name__})"

    # -- housekeeping -----------------------------------------------------
    def _housekeeping(self) -> None:
        now = self._clock()
        if self._last_sweep is None or now - self._last_sweep >= _SWEEP_EVERY:
            self._last_sweep = now
            try:
                self.sweep()
            except Exception:
                pass
        if self._vacuum_due and now - self._last_vacuum >= _VACUUM_EVERY:
            self._vacuum()

    def _vacuum(self) -> None:
        with self._lock:
            try:
                with closing(self._connect()) as c:
                    c.execute("VACUUM")
                self._vacuum_due = False
                self._last_vacuum = self._clock()
            except Exception:
                self._vacuum_due = True

    def _deleted(self) -> None:
        """After rows were deleted: VACUUM now, or once the hour is up."""
        self._vacuum_due = True
        if self._clock() - self._last_vacuum >= _VACUUM_EVERY:
            self._vacuum()

    def _drop(self, c, ids) -> None:
        for cid in ids:
            c.execute("DELETE FROM turns WHERE conversation_id=?", (cid,))
            c.execute("DELETE FROM conversations WHERE id=?", (cid,))

    def sweep(self) -> int:
        """Delete conversations whose last turn is older than keep_days.
        Returns how many."""
        keep = self.settings()["keep_days"]
        if not keep or not self.db_path.exists():
            return 0
        cutoff = self._clock() - keep * 86400
        with self._lock, closing(self._connect()) as c:
            with c:
                ids = [r[0] for r in c.execute(
                    "SELECT id FROM conversations WHERE updated < ?", (cutoff,))]
                self._drop(c, ids)
        if ids:
            self._deleted()
        return len(ids)

    # -- voice ------------------------------------------------------------
    def note_transcript(self, text: str, *, strictness, model, mode,
                        source: str = "") -> None:
        """The PC's speech route produced this transcript. For 10 minutes a
        user message with exactly these words, claimed as voice, is recorded
        as "voice"; otherwise as "voice_unverified". Only a hash is kept.

        `source` is how the clip started: "push_to_talk" (the talk button)
        or "wake_word" ("hey Jarvis"), kept with the voice check's facts so
        automatic learning can honour the owner's "hands-free" voice setting
        (jarvis_auto_learn.check_voice). "" when the speech route did not
        say - which that check treats as hands-free."""
        if not isinstance(text, str) or not _norm(text):
            return
        now = self._clock()
        with self._lock:
            for h in [h for h, (t, _) in self._heard.items() if now - t > VOICE_WINDOW]:
                del self._heard[h]
            if len(self._heard) >= 500:
                del self._heard[min(self._heard, key=lambda h: self._heard[h][0])]
            self._heard[_hash(text)] = (now, {"strictness": str(strictness),
                                              "model": str(model), "mode": str(mode),
                                              "source": str(source or "")})

    def _heard_facts(self, text: str):
        # Used up on the first match: one spoken sentence verifies ONE chat
        # turn, not any number of claims of it for ten minutes.
        with self._lock:
            got = self._heard.pop(_hash(text), None)
        if got is None or self._clock() - got[0] > VOICE_WINDOW:
            return None
        return got[1]

    # -- the live-turn registry -------------------------------------------
    def _note_live(self, cid: str, rows, device: str, read_outside: bool,
                   now: float) -> None:
        """Remember, for automatic learning, that THIS PC saw these user
        messages arrive live, with where their words came from.

        Written on every /api/chat request whether or not history is on,
        because automatic learning must work either way and must never trust
        a turn only because an app re-sent it (docs/JARVIS-API.md section
        19). In memory only, and never the words: a hash of each message,
        its provenance, the voice check's facts for a verified voice turn,
        the conversation id, the app, and whether a tool read outside text
        in that turn. The newest LIVE_MAX turns; a restart forgets them all,
        and a turn this PC does not remember is never learned from
        automatically (it becomes a card instead)."""
        with self._lock:
            first = None
            for text, prov, voice_check in rows:
                self._live_seq += 1
                first = self._live_seq if first is None else first
                key = (cid, _hash(text))
                self._live.pop(key, None)
                self._live[key] = {"conversation_id": cid, "message_hash": key[1],
                                   "provenance": prov, "voice_check": voice_check,
                                   "read_outside": bool(read_outside), "device": device,
                                   "at": now, "seq": self._live_seq}
            if read_outside and first is not None and cid not in self._taint:
                # From this turn on, the whole conversation is tainted.
                self._taint[cid] = first
            while len(self._live) > LIVE_MAX:
                self._live.popitem(last=False)
            while len(self._taint) > LIVE_MAX:
                self._taint.popitem(last=False)

    def live_turn(self, conversation_id, text) -> Optional[dict]:
        """The registry's entry for this message in this conversation, or
        None if this PC did not see it arrive live (or has forgotten it).
        `tainted` is true when the conversation read outside text at or
        before this turn."""
        if not (isinstance(conversation_id, str) and _CID.fullmatch(conversation_id)):
            return None
        if not isinstance(text, str) or not _norm(text):
            return None
        with self._lock:
            got = self._live.get((conversation_id, _hash(text)))
            if got is None:
                return None
            out = dict(got)
            if isinstance(out.get("voice_check"), dict):
                out["voice_check"] = dict(out["voice_check"])
            since = self._taint.get(conversation_id)
            out["tainted"] = since is not None and since <= out["seq"]
            return out

    def conversation_tainted(self, conversation_id) -> bool:
        """Has any live turn of this conversation read outside text?"""
        with self._lock:
            return conversation_id in self._taint

    # -- recording ----------------------------------------------------------
    def record_turn(self, body, *, lane: str = "", turn: Optional[dict] = None,
                    at: Optional[float] = None) -> dict:
        """Record one /api/chat request. `body` is the request as it arrived
        (with provenance, conversation_id and device); `turn` is what
        jarvis_agent.run_local_turn returned, or None when the answer was not
        made by it (a cloud lane, or the plain relay). Never raises for a bad
        body; returns {"recorded": bool, "why": ...}."""
        if not isinstance(body, dict):
            return {"recorded": False, "why": "not a chat request"}
        self._housekeeping()
        live = _live_user_messages(body.get("messages"))
        if not live:
            return {"recorded": False, "why": "no user message"}
        now = self._clock()
        at = float(at) if isinstance(at, (int, float)) and not isinstance(at, bool) else now
        device = body.get("device") if body.get("device") in DEVICES else "unknown"
        cid = body.get("conversation_id")
        if not (isinstance(cid, str) and _CID.fullmatch(cid)):
            # An older app sends none. Its turns are kept together per app
            # and per day rather than lost or scattered one per request.
            cid = "untagged-" + device + "-" + time.strftime("%Y%m%d", time.localtime(at))
        turn = turn if isinstance(turn, dict) else None
        read_outside = bool(turn and turn.get("tools_ran"))
        answer = turn.get("answer") if turn else None
        answer_kept = bool(turn and turn.get("finish_reason") and not turn.get("client_gone")
                           and isinstance(answer, str) and answer.strip())
        rows = self._live_rows(live)
        # The live-turn registry is written for EVERY request, before the
        # switch is read: automatic learning trusts only turns this PC saw
        # arrive, whether or not history is kept (jarvis_auto_learn.py).
        self._note_live(cid, rows, device, read_outside, now)
        aead, why = self._recording()
        if aead is None:
            return {"recorded": False, "why": why}
        rows = [(text, prov, None if vc is None else json.dumps(vc, sort_keys=True))
                for text, prov, vc in rows]
        if not rows:
            return {"recorded": False, "why": "no words in the user message"}
        return self._write_turn(aead, cid, rows, device, lane, read_outside, answer_kept,
                                answer, at, now)

    def _live_rows(self, live) -> list:
        """[(words, provenance, voice check facts or None)] for the live
        message(s). A claimed "voice" turn uses up its transcript here, once:
        see _heard_facts."""
        rows = []
        for m in live:
            text, picture = _text_of(m.get("content"))
            prov = m.get("provenance")
            prov = prov if prov in PROVENANCES else "unknown"
            voice_check = None
            if picture and prov in ("typed", "voice"):
                # Only the owner's own words become "picture_caption". Pasted,
                # clipboard and shared text sent with a picture keep their
                # less-trusted tag, and a missing tag stays "unknown".
                prov = "picture_caption"
            elif prov == "voice":
                facts = self._heard_facts(text)
                if facts is None:
                    prov = "voice_unverified"
                else:
                    voice_check = dict(facts)
            if not text.strip() and not picture:
                continue
            rows.append((text, prov, voice_check))
        return rows

    def _write_turn(self, aead, cid, rows, device, lane, read_outside, answer_kept,
                    answer, at, now) -> dict:
        lane = str(lane or "")[:200]
        with self._lock, closing(self._connect()) as c:
            with c:
                conv = c.execute("SELECT id FROM conversations WHERE id=?", (cid,)).fetchone()
                nxt = c.execute("SELECT COALESCE(MAX(idx), -1) + 1 FROM turns"
                                " WHERE conversation_id=?", (cid,)).fetchone()[0]
                if conv is None:
                    first = next((r[0] for r in rows if r[0].strip()), "")
                    title = (first.strip().splitlines() or [""])[0][:TITLE_CHARS]
                    c.execute("INSERT INTO conversations (id, title, started, updated, device)"
                              " VALUES (?,?,?,?,?)",
                              (cid, self._seal(aead, title.encode("utf-8"),
                                               self._aad(cid, "title")), at, now, device))
                elif rows[0][1] == "shared" and len(rows) > 1:
                    # A shared message already recorded with the turn before
                    # (that turn failed, so the app re-sent it next to this one).
                    last = c.execute("SELECT idx, text, provenance FROM turns WHERE"
                                     " conversation_id=? AND role='user'"
                                     " ORDER BY idx DESC LIMIT 1", (cid,)).fetchone()
                    if last and last[2] == "shared":
                        try:
                            same = self._open(aead, last[1], self._aad(cid, last[0])) \
                                == rows[0][0].encode("utf-8")
                        except Exception:
                            same = False
                        if same:
                            rows = rows[1:]
                for text, prov, voice_check in rows:
                    c.execute("INSERT INTO turns (conversation_id, idx, at, role, provenance,"
                              " device, lane, read_outside, answer_kept, voice_check, text)"
                              " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (cid, nxt, at, "user", prov, device, lane, int(read_outside),
                               int(answer_kept), voice_check,
                               self._seal(aead, text.encode("utf-8"), self._aad(cid, nxt))))
                    nxt += 1
                if answer_kept:
                    c.execute("INSERT INTO turns (conversation_id, idx, at, role, provenance,"
                              " device, lane, read_outside, answer_kept, voice_check, text)"
                              " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (cid, nxt, now, "assistant", None, device, lane,
                               int(read_outside), 1, None,
                               self._seal(aead, answer.encode("utf-8"), self._aad(cid, nxt))))
                c.execute("UPDATE conversations SET updated=?, device=? WHERE id=?",
                          (now, device, cid))
        return {"recorded": True, "conversation_id": cid, "answer_kept": answer_kept}

    # -- reading ------------------------------------------------------------
    def status(self) -> dict:
        st = self.settings()
        aead, why = self._recording()
        return {"enabled": st["enabled"], "recording": aead is not None, "why_not": why,
                "waiting": state()["waiting"], "keep_days": st["keep_days"],
                "encrypted": True}

    def list(self, limit=LIST_DEFAULT, before=None) -> dict:
        self._housekeeping()
        out = self.status()
        out["conversations"] = []
        try:
            limit = max(1, min(LIST_MAX, int(limit)))
        except (TypeError, ValueError):
            limit = LIST_DEFAULT
        if not self.db_path.exists():
            return out
        try:
            aead = self._cipher()
        except KeyUnavailable as exc:
            # Titles cannot be opened; say why rather than show blanks.
            out["why_not"] = out["why_not"] or str(exc)
            return out
        sql = ("SELECT c.id, c.title, c.started, c.updated, c.device,"
               " (SELECT COUNT(*) FROM turns t WHERE t.conversation_id=c.id),"
               " (SELECT COUNT(*) FROM turns t WHERE t.conversation_id=c.id AND"
               "   t.provenance IN ('voice','voice_unverified')),"
               " (SELECT COUNT(*) FROM turns t WHERE t.conversation_id=c.id AND"
               "   t.read_outside=1)"
               " FROM conversations c")
        # Paging by whole seconds (`updated` goes out as one, and comes back
        # as `before`). A page never splits a second: when its last row shares
        # a second with rows the LIMIT cut off, those rows join this page. So
        # `before` can safely mean "strictly older seconds" - nothing is
        # skipped and nothing repeats (chat history audit, 2026-09-24: rows in
        # the boundary's second used to be skipped).
        where, args = "", []
        if isinstance(before, (int, float)) and not isinstance(before, bool) \
                and math.isfinite(before):
            where = " WHERE c.updated < ?"
            args.append(float(math.floor(before)))
        with self._lock, closing(self._connect()) as c:
            rows = c.execute(sql + where + " ORDER BY c.updated DESC, c.id DESC LIMIT ?",
                             args + [limit]).fetchall()
            if len(rows) == limit:
                sec = math.floor(rows[-1][3] or 0)
                have = {r[0] for r in rows}
                rest = c.execute(sql + " WHERE c.updated >= ? AND c.updated < ?"
                                 " ORDER BY c.updated DESC, c.id DESC",
                                 [float(sec), float(sec + 1)]).fetchall()
                rows += [r for r in rest if r[0] not in have]
        for cid, title, started, updated, device, n, voice, outside in rows:
            out["conversations"].append({
                "id": cid, "title": self._title(aead, cid, title),
                "started": int(started or 0), "updated": int(updated or 0),
                "turns": int(n), "device": device or "unknown",
                "has_voice": bool(voice), "tainted": bool(outside)})
        return out

    def _title(self, aead, cid, blob) -> str:
        try:
            return self._open(aead, blob, self._aad(cid, "title")).decode("utf-8")
        except Exception:
            return "(this title could not be opened)"

    def get(self, cid):
        """The whole conversation, or None if there is no such one. Raises
        KeyUnavailable when it cannot be opened."""
        self._housekeeping()
        if not (isinstance(cid, str) and _CID.fullmatch(cid)) or not self.db_path.exists():
            return None
        with self._lock, closing(self._connect()) as c:
            conv = c.execute("SELECT title FROM conversations WHERE id=?", (cid,)).fetchone()
            if conv is None:
                return None
            rows = c.execute("SELECT idx, at, role, provenance, read_outside, answer_kept,"
                             " text FROM turns WHERE conversation_id=? ORDER BY idx",
                             (cid,)).fetchall()
        aead = self._cipher()
        turns = []
        for idx, at, role, prov, outside, kept, blob in rows:
            try:
                text = self._open(aead, blob, self._aad(cid, idx)).decode("utf-8")
            except Exception:
                text = "(this line could not be opened)"
            t = {"role": role, "text": text, "at": int(at or 0)}
            if role == "user":
                t.update(provenance=prov or "unknown", read_outside=bool(outside),
                         answer_kept=bool(kept))
            turns.append(t)
        return {"id": cid, "title": self._title(aead, cid, conv[0]),
                "tainted": any(bool(r[4]) for r in rows), "turns": turns}

    def tainted_from(self, cid):
        """The number of the first turn that read outside text, or None. Every
        turn from that one on is tainted (for the later learning build)."""
        if not self.db_path.exists():
            return None
        with self._lock, closing(self._connect()) as c:
            row = c.execute("SELECT MIN(idx) FROM turns WHERE conversation_id=?"
                            " AND read_outside=1", (cid,)).fetchone()
        return None if row is None or row[0] is None else int(row[0])

    def delete(self, cid) -> bool:
        """One conversation. True if there was one. There is no delete-all."""
        if not (isinstance(cid, str) and _CID.fullmatch(cid)) or not self.db_path.exists():
            return False
        with self._lock, closing(self._connect()) as c:
            with c:
                found = c.execute("SELECT 1 FROM conversations WHERE id=?",
                                  (cid,)).fetchone() is not None
                if found:
                    self._drop(c, [cid])
        if found:
            self._deleted()
        return found

    def set_keep_days(self, days) -> int:
        self._save_settings(keep_days=days)
        return self.sweep()


# ------------------------------------------------------ the module's own log

_DEFAULT: Optional[ChatLog] = None
_DEFAULT_LOCK = threading.Lock()


def _log() -> ChatLog:
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            d = _config_dir()
            _DEFAULT = ChatLog(d / "chat-history.db", d / "chat-history.json",
                               CredentialKey())
        return _DEFAULT


def use(log: Optional[ChatLog]) -> None:
    """Replace the module's log (tests). None: make the real one on next use."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = log


def record_turn(body, *, lane: str = "", turn: Optional[dict] = None,
                at: Optional[float] = None) -> dict:
    return _log().record_turn(body, lane=lane, turn=turn, at=at)


def note_transcript(text: str, *, strictness, model, mode, source: str = "") -> None:
    """Called by the PC's speech route with each transcript it produced."""
    _log().note_transcript(text, strictness=strictness, model=model, mode=mode,
                           source=source)


def live_turn(conversation_id, text) -> Optional[dict]:
    """For jarvis_auto_learn: did this PC see this message arrive live, in
    this conversation, and with what provenance? None if not."""
    return _log().live_turn(conversation_id, text)


def conversation_tainted(conversation_id) -> bool:
    return _log().conversation_tainted(conversation_id)


def status() -> dict:
    return _log().status()


# ------------------------------------------------------ turning it back on

_LOCK = threading.Lock()
_PENDING: dict = {}          # {"id", "since"} while an ON card waits
_WITHDRAWN: set = set()
_LAST: dict = {}             # {"outcome", "why", "at"} - how the last card ended
_LATEST: dict = {}           # {"id"} - the card raised most recently; only it sets _LAST
#: Held from an approved card's "was it withdrawn?" check through
#: set_enabled(True), and from OFF's withdrawing through set_enabled(False):
#: an OFF pressed in between used to be answered "off" and then overwritten
#: by the card (red team R5). Always taken BEFORE _LOCK.
_SWITCH = threading.Lock()


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        import jarvis_framework as _fw
        return str(_fw.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-history-card", daemon=True).start()


def _audit(event: str, detail: dict) -> None:
    try:
        import jarvis_framework as _fw
        _fw.audit_log(event, detail)
    except Exception:
        pass


def _finish(pid: str, outcome: str, why: str = "") -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        if _LATEST.get("id") not in (None, pid):
            # An older, withdrawn card answered after a newer one was raised:
            # its outcome must not be shown as the newer card's.
            return
        _LAST.clear()
        _LAST.update(outcome=outcome, why=why, at=time.time())
    _audit("history.card", {"outcome": outcome})


def _decide(pid: str, apply: Callable[[bool], dict], gate: Callable,
            tier_of: Callable[[str], str]) -> None:
    try:
        v = gate(ACTION, {"text": CARD_TEXT, "what": "turn on chat history",
                          "leaves_this_pc": False}, CARD_TEXT)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(ACTION) != "ask":
        return _finish(pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused")))
    with _SWITCH:
        # Held until history is on and _LAST says so: an OFF pressed
        # meanwhile waits for it, then turns history off (R5).
        with _LOCK:
            withdrawn = pid in _WITHDRAWN
        if withdrawn:
            return _finish(pid, "withdrawn",
                           "you turned chat history off while the card was waiting")
        try:
            out = apply(True) or {}
        except Exception as exc:
            return _finish(pid, "failed", f"{type(exc).__name__}")
        if out.get("ok") is False:
            return _finish(pid, "failed", str(out.get("error", "")))
        _finish(pid, "enabled")


def _keep_words(days: int) -> str:
    return {0: "Conversations are kept until you delete them.",
            30: "Conversations older than 30 days are deleted.",
            90: "Conversations older than 90 days are deleted.",
            365: "Conversations older than 1 year are deleted."}[days]


def request_settings(body, *, gate: Optional[Callable] = None,
                     tier_of: Optional[Callable[[str], str]] = None,
                     spawn: Optional[Callable] = None, log: Optional[ChatLog] = None) -> tuple:
    """POST /api/history/settings. Returns (http code, body). One setting per
    request: {"enabled": bool} or {"keep_days": 0|30|90|365}."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    log = log or _log()
    if not isinstance(body, dict) or len(body) != 1:
        return 400, {"error": 'send one setting: {"enabled": true|false} or '
                              '{"keep_days": 0|30|90|365}'}
    key, value = next(iter(body.items()))
    if key == "keep_days":
        if isinstance(value, bool) or value not in KEEP_DAYS:
            return 400, {"error": "keep_days must be 0 (keep until deleted), 30, 90 or 365"}
        try:
            deleted = log.set_keep_days(value)
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not save the setting ({type(exc).__name__})"}
        _audit("history.keep_days", {"keep_days": value, "deleted": deleted})
        out = log.status()
        out.update(ok=True, deleted=deleted,
                   message=_keep_words(value) + (
                       f" {deleted} conversation{'' if deleted == 1 else 's'} "
                       f"{'was' if deleted == 1 else 'were'} deleted now." if deleted
                       else " None were deleted now."))
        return 200, out
    if key != "enabled" or not isinstance(value, bool):
        return 400, {"error": 'need {"enabled": true|false} or {"keep_days": 0|30|90|365}'}
    if not value:
        with _SWITCH:
            # The lock an approved card holds from its withdrawn check to
            # set_enabled(True): this OFF is never overwritten by it (R5).
            with _LOCK:
                if _PENDING:
                    # Withdrawn AND no longer the waiting card: approving it
                    # does nothing, and a later ON raises a fresh card instead
                    # of pointing at this one (chat history audit, 2026-09-24).
                    _WITHDRAWN.add(_PENDING["id"])
                    _PENDING.clear()
            try:
                log.set_enabled(False)
            except Exception as exc:
                return 500, {"ok": False,
                             "error": f"could not save the setting ({type(exc).__name__})"}
        _audit("history.off", {})
        out = log.status()
        out.update(ok=True, enabled=False, waiting=False, message=OFF_TEXT)
        return 200, out
    if log.settings()["enabled"] and not state()["waiting"]:
        out = log.status()
        out.update(ok=True, message="Chat history is already on.")
        return 200, out
    tier = tier_of(ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {tier!r} in jarvis-framework.toml; turning chat history on "
            f"needs a person to say yes, so it must be 'ask'")}
    with _LOCK:
        pid = None if _PENDING else _uuid.uuid4().hex
        if pid is not None:
            _PENDING.update(id=pid, since=time.time())
            _LATEST["id"] = pid
    if pid is None:
        # status() reads the card state under _LOCK, so not inside it.
        out = log.status()
        out.update(ok=True, waiting=True, enabled=False,
                   message="A card to turn chat history on is already waiting for "
                           "your approval.")
        return 202, out
    try:
        spawn(lambda: _decide(pid, log.set_enabled, gate, tier_of))
    except Exception:
        with _LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    out = log.status()
    out.update(ok=True, waiting=True, enabled=False,
               message="Waiting for your approval. Chat history turns on only if you "
                       "approve the card, on your PC or phone.")
    return 202, out


def state() -> dict:
    """{"waiting": bool, "last": {...} | None} - the ON card."""
    with _LOCK:
        return {"waiting": bool(_PENDING), "last": dict(_LAST) or None}


def _reset_for_tests() -> None:
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST.clear()
        _LATEST.clear()


# ------------------------------------------------------------- the routes

def _query(qs: str) -> dict:
    from urllib.parse import parse_qs
    try:
        return {k: v[0] for k, v in parse_qs(qs or "", keep_blank_values=True).items() if v}
    except Exception:
        return {}


def handle_get(path: str, query: str = "") -> tuple:
    """GET /api/history and /api/history/conversation. (code, body)."""
    q = _query(query)
    log = _log()
    if path == "/api/history":
        try:
            limit = int(q.get("limit", LIST_DEFAULT))
        except (TypeError, ValueError):
            limit = LIST_DEFAULT
        before = None
        try:
            b = float(q["before"]) if q.get("before") else None
            # Seconds, not milliseconds: anything past tomorrow is ignored.
            if b is not None and 0 < b < time.time() + 86400:
                before = b
        except (TypeError, ValueError):
            before = None
        return 200, log.list(limit=limit, before=before)
    if path == "/api/history/conversation":
        cid = q.get("id", "")
        if not _CID.fullmatch(cid or ""):
            return 400, {"error": "need ?id=<conversation id>"}
        try:
            conv = log.get(cid)
        except KeyUnavailable as exc:
            return 503, {"error": str(exc)}
        if conv is None:
            return 404, {"error": "no such conversation - it may have been deleted"}
        return 200, conv
    return 404, {"error": "no such route"}


def handle_post(route: str, body) -> tuple:
    """POST /api/history/delete and /api/history/settings. (code, body)."""
    if route == "/api/history/delete":
        if not isinstance(body, dict) or set(body) != {"id"} or not isinstance(body["id"], str):
            return 400, {"error": 'need {"id": "<conversation id>"} - one conversation '
                                  'per request'}
        if not _log().delete(body["id"]):
            return 404, {"error": "no such conversation - it may already be deleted"}
        _audit("history.delete", {})
        return 200, {"ok": True}
    if route == "/api/history/settings":
        return request_settings(body)
    return 404, {"error": "no such route"}
