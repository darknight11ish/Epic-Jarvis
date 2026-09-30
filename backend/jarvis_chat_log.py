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

TAINT SURVIVES A RESTART (security review G1, 2026-09-26). "Has this
conversation read outside text?" (conversation_tainted, the tool loop's
note-write, web-search and lights-without-a-card checks) must not forget
across a backend restart, nor when a conversation falls out of the newest
LIVE_MAX. The first time this process meets a conversation that already has
earlier turns (_seed), it asks the history database's per-turn
`read_outside` column; that answer counts only when the database holds every
earlier user message the request carries. Otherwise - history off, the
database unreadable, a temporary chat, a gap - the conversation counts as
tainted. It fails CLOSED: a turn this process cannot vouch for asks, as a
turn automatic learning does not remember already does.

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
A pasted password, PIN or one-time code within a KEPT message's words is
masked before it is written - see `_mask_for_storage` and
`jarvis_paste_guard.py` (feasibility I115, 2026-09-27). It reaches the
model exactly as typed; only the copy on disk is different.
Not kept: anything from a TEMPORARY chat (`"temporary": true` on the
request, 2026-09-25) - only the registry's hash of its live message, under
the provenance "temporary", so automatic learning never saves from it.
Also not kept: tool output, system or context messages, deep questions, wiki
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

WHAT KIND OF CONVERSATION (the chat audit, 2026-09-28; JARVIS-API section
18.2): each conversation has a plain `kind` - chat, live (Jarvis Live),
support (a customer-support record), chatbot (a conversation with another
AI) or compare (a comparison) - and a `project`, empty until Projects step 4.
A history kept before them is given both in place on first use (_migrate).
A chat that held a crisis turn is titled "A difficult moment", never with
the owner's words (CRISIS_TITLE). Chatbot and compare records are written
whole by record_chatbot, the shape of a support record: role "chatbot",
outside text, never learned from. A support record is never deleted by
"Delete conversations older than" (sweep): only by the owner, in History.

SEARCHING WHAT WAS SAID (docs/JARVIS-API.md section 71, 2026-09-28)
ChatLog.search, for the apps' History search box only (GET
/api/history/search, answered by jarvis_brain_reads.py). Each search opens
every kept turn with the key, in memory, compares it and drops it. There is
NO index and nothing is written - an index would be a plain-text copy of
what this module exists to keep encrypted. Not a tool: nothing a model or a
chat turn can call reaches it.

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
import unicodedata
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
    # Feasibility I115, "Paste guard": masks a pasted password, PIN or
    # one-time code before it is written to the database - see
    # _mask_for_storage. Optional the same way jarvis_framework is above:
    # without it, chat history still works exactly as it did before this
    # feature.
    import jarvis_paste_guard as _paste_guard
except Exception:
    _paste_guard = None  # type: ignore

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
#: The authors of a customer-support chat's rows (record_support, role
#: "support"): the company's side (outside text), Jarvis writing in the
#: owner's name, the owner's own words (typed in the window or in an app),
#: and Jarvis's notes (the details card, offer cards, the reference).
SUPPORT_PROVENANCES = ("support_company", "support_jarvis", "support_owner", "support_note")
SUPPORT_MAX_ROWS = 600
#: The authors of a kept chatbot conversation or comparison's rows
#: (record_chatbot, role "chatbot" - never "user", so the learner never reads
#: a word of it): what Jarvis sent the chatbot, the chatbot's reply (outside
#: text), a note (the goal, how it ended), and the summary this PC wrote from
#: the replies (outside text too).
CHATBOT_PROVENANCES = ("chatbot_jarvis", "chatbot_reply", "chatbot_note", "chatbot_summary")
CHATBOT_MAX_ROWS = 600
#: What kind of conversation a History row is (the chat audit, 2026-09-28;
#: the owner's decisions "History marks Live sessions" and "Chats, after the
#: chat audit"). One column, `conversations.kind`:
#:   chat     an ordinary chat, typed or spoken (every row kept before this
#:            column existed, except support records, is one)
#:   live     a Jarvis Live session (its first message came with `live: true`)
#:   support  a customer-support chat's record (record_support)
#:   chatbot  a conversation Jarvis had with another AI chatbot for the owner
#:   compare  "Ask several and compare": every chatbot's conversation, and the
#:            summary
#: Chats brought in from ChatGPT, Claude, Gemini or DeepSeek (JARVIS-API
#: section 85) are NOT added to History, so there is no "imported" kind.
KINDS = ("chat", "live", "support", "chatbot", "compare")
#: The kinds "Continue this chat" may carry on. Support, chatbot and compare
#: records are read-only: the other side of those was not Jarvis answering
#: the owner, and re-sending them would hand outside text to the model as if
#: it were the owner's conversation.
CONTINUABLE = ("chat", "live")
#: A conversation that held a crisis turn is kept but titled this, never with
#: the owner's words (the owner, 2026-09-28, "Chats, after the chat audit").
CRISIS_TITLE = "A difficult moment"
DEVICES = ("desktop", "hud", "phone")
KEEP_DAYS = (0, 30, 90, 365)
VOICE_WINDOW = 600          # a transcript counts as voice for 10 minutes
LIVE_MAX = 200              # the live-turn registry holds this many turns
#: The most user turns of one continued chat put back in the registry from
#: its own record (see ChatLog._rehydrate). More than the apps ever re-send.
REHYDRATE_MAX = 60
TITLE_CHARS = 80
#: temporary-chat.patch looks for this before it hands this module a
#: temporary chat: a jarvis_chat_log.py without it would keep one.
TEMPORARY_CHAT = True
TEMPORARY_WHY = "a temporary chat is never kept"
#: Jarvis Live's side talk (the owner's answer of 2026-09-28): a remark the
#: model called "not for me" (jarvis_agent's `side_talk`) is not kept in chat
#: history at all - neither the owner's words nor the marker. It goes in the
#: live-turn registry (a hash, in memory) as "temporary", like a temporary
#: chat's turn, so if an app ever re-sent it, automatic learning would make
#: it a card, never a saved fact. jarvis_live.was_side_talk skips it anyway.
SIDE_TALK_WHY = "a side remark in Jarvis Live is never kept"
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


def _earlier_user_messages(messages) -> Optional[int]:
    """How many turns come before the live message(s) in a request: the
    user messages with words or a picture, the way record_turn counts them -
    or 1 when there are none of those but an answer or tool turn is there
    (something earlier happened). None when `messages` is not a list, so it
    cannot be counted."""
    if not isinstance(messages, list):
        return None
    live = _live_user_messages(messages)
    start = len(messages)
    if live:
        start = next(i for i, m in enumerate(messages) if m is live[0])
    users, other = 0, False
    for m in messages[:start]:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "user":
            text, picture = _text_of(m.get("content"))
            if text.strip() or picture:
                users += 1
        elif m.get("role") in ("assistant", "tool"):
            other = True
    return users if users or not other else 1


#: Said under an opened conversation that cannot be continued, by kind. The
#: apps show it where "Continue this chat" would be (both apps, the same
#: words; tools/gen_history_kinds.py copies them into the contract file).
CONTINUE_WHY = {
    "support": "A customer-support record can't be continued: it is the company's words "
               "and what was sent in your name, kept as your record.",
    "chatbot": "A chat with another AI can't be continued here: its replies are outside "
               "text, not a conversation with Jarvis.",
    "compare": "A comparison can't be continued here: its replies are outside text, not a "
               "conversation with Jarvis.",
}


#: Said, in place of the button, under an opened "A difficult moment" chat
#: (the second chat audit, 2026-09-28: "gate on crisis chats"). A crisis turn
#: is never learned from or counted, and the PC puts no such chat's words back
#: in its registry (ChatLog._rehydrate); carrying it on would re-send those
#: words to the model, so the apps offer a fresh start instead. Sent by the PC
#: as `continue_why`, so it is not in the shared per-kind contract.
CRISIS_CONTINUE_WHY = ("This chat is kept as your own record. It is not carried on - start a "
                       "new chat any time, and nothing from that moment is read again.")


# ------------------------------------------------------------ chat tags
#
# "Chat tags and sections in History" (owner, 2026-09-30; docs/CHAT-TAGS-DESIGN.md,
# JARVIS-API section 99). Tag NAMES are the owner's words, so the whole registry
# is one sealed value in `meta` (key "tags"); a chat carries only an opaque
# `tag_id` number in a plain column. Nothing here is ever an index, a fact, or
# read by the learner or a model.

TAG_MAX = 12
TAG_NAME_MAX = 24
TAG_COLOURS = 8
TAG_ICONS = ("briefcase", "book", "home", "folder", "lightbulb", "star", "flag",
             "wrench", "leaf", "music")
#: The starter tags, written the first time the registry is read (ids 1-5).
TAG_STARTERS = (("Work", 0, "briefcase"), ("Learning", 1, "book"), ("Personal", 2, "home"),
                ("Projects", 3, "folder"), ("Ideas", 4, "lightbulb"))
_TAGS_KEY = "tags"
_TAGS_AAD = b"meta|tags"


def _tag_filter(tag):
    """GET /api/history's `tag=` value: an int id, "none", or None (no filter;
    anything else is ignored, like `kind`)."""
    if isinstance(tag, bool):
        return None
    if isinstance(tag, int):
        return tag if tag > 0 else None
    if isinstance(tag, str):
        t = tag.strip()
        if t.lower() == "none":
            return "none"
        if t.isascii() and t.isdigit() and len(t) <= 9 and int(t) > 0:
            return int(t)
    return None


def _tag_where(tag):
    """(sql or "", args) for an already-checked tag filter."""
    if tag == "none":
        return "c.tag_id IS NULL", []
    if isinstance(tag, int):
        return "c.tag_id = ?", [tag]
    return "", []


def _tag_err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


TAG_MESSAGES = {
    "bad_name": "A tag name needs 1 to 24 characters, with at least one letter, number or symbol it can show.",
    "name_taken": "You already have a tag with that name.",
    "too_many_tags": "You can have up to 12 tags. Delete one to make room.",
    "bad_colour": "That colour is not one of the eight.",
    "bad_icon": "That icon is not on the list.",
    "tag_not_found": "That tag is gone. Reload History to see your tags.",
    "not_found": "That chat is gone - it may have been deleted.",
    "bad_request": "That request was not understood.",
}


def _tag_fail(code: str, message: str = "") -> dict:
    return _tag_err(code, message or TAG_MESSAGES.get(code, ""))


def _has_visible_char(n: str) -> bool:
    """True when the name has at least one character a person can see: a
    letter, number, mark, punctuation or symbol. Spaces, control and format
    characters (zero-width joiner...), and blank fillers such as U+3164
    (Hangul filler, category Lo but drawn empty) do not count."""
    for ch in n:
        if ch in "\u3164\u115f\u1160\uffa0\u2800":
            continue
        if unicodedata.category(ch)[0] in "LNMPS":
            return True
    return False


def _clean_tag_name(v):
    """The trimmed, NFC-normalised name, or None if it is not 1-24 code
    points of printable characters with at least one visible one."""
    if not isinstance(v, str):
        return None
    n = unicodedata.normalize("NFC", v).strip()
    if not (1 <= len(n) <= TAG_NAME_MAX):
        return None
    # Printable only - but the joiners that build one emoji out of several
    # (a family, a flag with a skin tone) are allowed inside a name.
    if any(not (ch.isprintable() or ch in "\u200d\u200c") for ch in n):
        return None
    if not _has_visible_char(n):
        return None
    return n


def _tag_key(n: str) -> str:
    """What "the same name" means: NFC, then casefold, then NFC again."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", n).casefold())


def _off_message(why: str, tail: str) -> str:
    """Why history cannot take a change right now, in one plain sentence pair."""
    why = (why or "Chat history is off.").strip()
    return why[:1].upper() + why[1:].rstrip(".") + ". " + tail


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)



def _tag_id(v):
    """A stored tag_id column value as an int, or None (no tag)."""
    return v if isinstance(v, int) and not isinstance(v, bool) else None


#: The `conversations` columns, in ONE place and in one order. Every path that
#: copies a conversation row (get, brief, list, overlapping, take_out, and
#: put_back's _put_one) reads or writes this list, so a new column is one edit
#: here (plus the CREATE TABLE and _migrate) - it can no longer be dropped by
#: one hand-written positional tuple that was missed (the chat tags audit,
#: 2026-09-30; a test pins the list against the real table).
CONV_COLS = ("id", "title", "started", "updated", "device", "kind", "project", "tag_id")


def _conv_cols(alias: str = "", *, raw: bool = False) -> str:
    """CONV_COLS as SQL. `kind` reads as 'chat' when empty, unless `raw`
    (take_out holds a row exactly as it was)."""
    a = alias + "." if alias else ""
    return ", ".join(("COALESCE(%skind, 'chat')" % a) if (c == "kind" and not raw)
                     else a + c for c in CONV_COLS)


def _conv_named(row) -> dict:
    """The first len(CONV_COLS) values of a row read with _conv_cols, by name."""
    return dict(zip(CONV_COLS, row))


def _row(cid, title, started, updated, turns, device, voice, outside, kind, project,
         tag_id=None) -> dict:
    """One History list row, as GET /api/history and the search send it.
    `tag_id`: the chat's one tag (chat tags, 2026-09-30), or None."""
    return {"id": cid, "title": title,
            "started": int(started or 0), "updated": int(updated or 0),
            "turns": int(turns), "device": device or "unknown",
            "has_voice": bool(voice), "tainted": bool(outside),
            "kind": kind if kind in KINDS else "chat", "project": project or None,
            "tag_id": _tag_id(tag_id)}


def _title_from(rows) -> str:
    """A new conversation's title: the first line of the owner's own words
    (typed or said) when there are some, else of the first message - so a
    chat that began with shared text is titled with what the owner asked, not
    with the start of an email (the chat audit, 2026-09-28)."""
    own = [r[0] for r in rows if r[0].strip() and r[1] in ("typed", "voice", "picture_caption")]
    first = own[0] if own else next((r[0] for r in rows if r[0].strip()), "")
    return (first.strip().splitlines() or [""])[0][:TITLE_CHARS]


def _crisis_turn(rows, turn) -> bool:
    """Was this a crisis turn? The answering loop's own flag (`crisis` in
    what jarvis_agent.run_local_turn returned), or the crisis help line's
    phrase check (jarvis_wellbeing.crisis, the same one wellbeing.patch
    runs) on the words just said. Never raises; without jarvis_wellbeing.py
    only the loop's flag counts."""
    if isinstance(turn, dict) and turn.get("crisis"):
        return True
    try:
        import jarvis_wellbeing
    except Exception:
        return False
    for text, _prov, _vc in rows:
        try:
            if jarvis_wellbeing.crisis(text):
                return True
        except Exception:
            continue
    return False


def _norm(text: str) -> str:
    return " ".join(str(text or "").split())


def _hash(text: str) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


# ------------------------------------------------------------- the search
#
# "Search what was said in old chats" (docs/JARVIS-API.md section 71,
# ChatLog.search). The helpers below are pure: they see one conversation's
# opened words, in memory, and return a short snippet in PARTS - plain text
# and matched text, never character offsets - so an app highlights a match
# without counting characters (Python counts code points, JavaScript UTF-16
# units, and an emoji would put every mark after it in the wrong place).

SEARCH_MIN_CHARS = 2         # a search word shorter than this is skipped
SEARCH_MAX_CHARS = 100       # the whole search, after spaces are tidied
SEARCH_MAX_WORDS = 8
SEARCH_DEFAULT, SEARCH_MAX = 20, 50
SEARCH_SCAN_MAX = 5000       # conversations looked at per search, newest first
SEARCH_SECONDS = 4.0         # and no longer than this
SNIPPET_BEFORE = 60          # characters shown before the first match
SNIPPET_CHARS = 180          # characters in a snippet at most

SEARCH_TOO_SHORT = "Type at least two letters to search what was said."
SEARCH_TOO_LONG = (f"That search is too long. Use up to {SEARCH_MAX_WORDS} words, "
                   f"{SEARCH_MAX_CHARS} characters in all.")


def search_terms(query):
    """(the search words, None) or (None, why in plain words). Each word
    once, in the order typed; words shorter than SEARCH_MIN_CHARS are
    skipped ("a", "I" would match every chat)."""
    q = _norm(query if isinstance(query, str) else "")
    if len(q) > SEARCH_MAX_CHARS:
        return None, SEARCH_TOO_LONG
    terms = []
    for w in q.split(" "):
        if len(w) >= SEARCH_MIN_CHARS and w.casefold() not in (t.casefold() for t in terms):
            terms.append(w)
    if not terms:
        return None, SEARCH_TOO_SHORT
    if len(terms) > SEARCH_MAX_WORDS:
        return None, SEARCH_TOO_LONG
    return terms, ""


def _spans(rx, text: str) -> list:
    """Every match of every search word in `text`, overlapping ones merged:
    [(start, end)], in order."""
    spans = sorted((m.start(), m.end()) for r in rx for m in r.finditer(text)
                   if m.end() > m.start())
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _snippet(rx, role, at, text: str) -> dict:
    """A short piece of `text` around its first match, as parts:
    {"role", "at", "before": cut at the start, "after": cut at the end,
    "parts": [{"text", "hit"}]}. Cut on a space where one is near, so a word
    is never shown half."""
    spans = _spans(rx, text)
    first = spans[0][0] if spans else 0
    start = max(0, first - SNIPPET_BEFORE)
    if start > 0:
        space = text.find(" ", start, first)
        start = space + 1 if space != -1 else start
    end = min(len(text), start + SNIPPET_CHARS)
    if end < len(text):
        space = text.rfind(" ", max(first + 1, start + SNIPPET_CHARS // 2), end)
        end = space if space != -1 else end
    parts, at_ = [], start
    for s, e in spans:
        if e <= start or s >= end:
            continue
        s, e = max(s, start), min(e, end)
        if s > at_:
            parts.append({"text": text[at_:s], "hit": False})
        parts.append({"text": text[s:e], "hit": True})
        at_ = e
    if at_ < end:
        parts.append({"text": text[at_:end], "hit": False})
    return {"role": role if role in ("user", "assistant", "title") else "user",
            "at": int(at or 0), "before": start > 0, "after": end < len(text),
            "parts": parts}


def _conversation_hit(rx, title: str, texts: list):
    """(snippet, hits) when EVERY search word is somewhere in the
    conversation - its title or any of its messages - else None. `hits` is
    how many messages hold at least one of them. The snippet is from the
    message that holds the most different search words (the earliest of
    those), or from the title when no message does."""
    seen = [False] * len(rx)
    best, best_n, hits = None, 0, 0
    for role, at, text in texts:
        have = [bool(r.search(text)) for r in rx]
        n = sum(have)
        if n:
            hits += 1
            seen = [a or b for a, b in zip(seen, have)]
            if n > best_n:
                best, best_n = (role, at, text), n
    title_has = [bool(r.search(title or "")) for r in rx]
    seen = [a or b for a, b in zip(seen, title_has)]
    if not all(seen):
        return None
    if best is None:
        return _snippet(rx, "title", 0, title), 0
    return _snippet(rx, *best), hits


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
        # The conversations this process has met (_seed), newest used last.
        # A conversation not in it is "unknown", and is asked about afresh -
        # after a restart, or after LIVE_MAX newer ones pushed it out.
        # _taint only ever holds conversations that are in here.
        self._seen: "OrderedDict" = OrderedDict()   # cid -> True
        self._live_seq = 0
        # conversation id -> {"seq", "erased"}: turns re-registered from the
        # record (see _rehydrate) up to this seq were already learned from
        # before the owner Forgot or Erased a fact of the chat, so the
        # learner must never learn from them again (jarvis_auto_learn.hushed).
        self._hush_floor: dict = {}
        self._schema_ok = False       # _migrate has run on this file (kind, project)

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
                  " device TEXT, kind TEXT, project TEXT, tag_id INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS turns ("
                  " conversation_id TEXT NOT NULL, idx INTEGER NOT NULL, at REAL,"
                  " role TEXT, provenance TEXT, device TEXT, lane TEXT,"
                  " read_outside INTEGER, answer_kept INTEGER, voice_check TEXT,"
                  " text BLOB, PRIMARY KEY (conversation_id, idx))")
        c.execute("CREATE INDEX IF NOT EXISTS conversations_updated"
                  " ON conversations (updated)")
        if not self._schema_ok:
            self._migrate(c)
        return c

    def _migrate(self, c) -> None:
        """A history kept before `kind` and `project` existed (the chat audit,
        2026-09-28): both columns are added once, in place. Every existing
        row becomes "chat", except a customer-support record (its turns are
        role "support"), which becomes "support". An older Live session
        cannot be told from an ordinary chat afterwards - nothing marked it -
        so it stays "chat". `project` stays empty: no chat belongs to a
        project until Projects step 4 is built. Plain columns: no key is
        needed, and no text is opened or rewritten."""
        cols = {r[1] for r in c.execute("PRAGMA table_info(conversations)")}
        with c:
            if "kind" not in cols:
                c.execute("ALTER TABLE conversations ADD COLUMN kind TEXT")
            if "project" not in cols:
                c.execute("ALTER TABLE conversations ADD COLUMN project TEXT")
            # Chat tags (2026-09-30): the chat's one tag, an opaque number.
            # The names live sealed in `meta` (key "tags"), never here.
            if "tag_id" not in cols:
                c.execute("ALTER TABLE conversations ADD COLUMN tag_id INTEGER")
            c.execute("UPDATE conversations SET kind='support' WHERE kind IS NULL AND id IN"
                      " (SELECT DISTINCT conversation_id FROM turns WHERE role='support')")
            c.execute("UPDATE conversations SET kind='chat' WHERE kind IS NULL")
        self._schema_ok = True

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
            c.execute("DELETE FROM meta WHERE k=?", (self._hush_key(cid),))
            self._hush_floor.pop(cid, None)

    def sweep(self) -> int:
        """Delete conversations whose last turn is older than keep_days.
        Returns how many.

        A customer-support chat's record is NOT deleted by this (the owner,
        2026-09-28: "auto-delete ... asks before removing a support chat"):
        it is the owner's own record of what a company agreed to, so it goes
        only when the owner deletes it in History, which asks first. How many
        were kept back is support_past_keep()."""
        keep = self.settings()["keep_days"]
        if not keep or not self.db_path.exists():
            return 0
        cutoff = self._clock() - keep * 86400
        with self._lock, closing(self._connect()) as c:
            with c:
                ids = [r[0] for r in c.execute(
                    "SELECT id FROM conversations WHERE updated < ?"
                    " AND COALESCE(kind, 'chat') != 'support'", (cutoff,))]
                self._drop(c, ids)
        if ids:
            self._deleted()
        return len(ids)

    def support_past_keep(self) -> int:
        """How many customer-support records are older than keep_days - kept
        by sweep() on purpose, for the owner to delete by hand. 0 when
        everything is kept anyway."""
        keep = self.settings()["keep_days"]
        if not keep or not self.db_path.exists():
            return 0
        cutoff = self._clock() - keep * 86400
        with self._lock, closing(self._connect()) as c:
            return int(c.execute("SELECT COUNT(*) FROM conversations WHERE updated < ?"
                                 " AND kind='support'", (cutoff,)).fetchone()[0])

    # -- voice ------------------------------------------------------------
    def note_transcript(self, text: str, *, strictness, model, mode,
                        source: str = "") -> None:
        """The PC's speech route produced this transcript. For 10 minutes a
        user message with exactly these words, claimed as voice, is recorded
        as "voice"; otherwise as "voice_unverified". Only a hash is kept.

        `source` is how the clip started: "push_to_talk" (the talk button)
        or "wake_word" ("hey Jarvis") or, since 2026-09-28, "live" (Jarvis
        Live, jarvis_live.py), kept with the voice check's facts so
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
        automatically (it becomes a card instead). Conversation TAINT does
        not end with a restart: see _seed."""
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
            self._met(cid)
            while len(self._live) > LIVE_MAX:
                self._live.popitem(last=False)

    def _met(self, cid: str) -> None:
        """Mark `cid` as met by this process, newest last. The oldest beyond
        LIVE_MAX is forgotten WHOLE - its taint and its live turns together -
        so it is never half-remembered as clean: next time it is unknown, and
        _seed asks afresh. Under self._lock."""
        self._seen.pop(cid, None)
        self._seen[cid] = True
        while len(self._seen) > LIVE_MAX:
            old, _ = self._seen.popitem(last=False)
            self._taint.pop(old, None)
            self._hush_floor.pop(old, None)
            for key in [k for k in self._live if k[0] == old]:
                del self._live[key]

    # -- taint for a conversation this process has not met ------------------
    def _db_turns(self, cid: str):
        """(user rows, any turn read outside text) for `cid` in the history
        database, or None when there is no database or no row for it. Plain
        columns only: no key is needed. Raises when the file cannot be read."""
        if not self.db_path.exists():
            return None
        with closing(self._connect()) as c:
            row = c.execute("SELECT SUM(role='user'), MAX(read_outside) FROM turns"
                            " WHERE conversation_id=?", (cid,)).fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0] or 0), bool(row[1])

    def _unknown_tainted(self, cid, messages) -> bool:
        """Is a conversation this process has not met tainted? `messages`:
        the request as it arrived (None when the caller has none).

        No earlier turn in the request: a new conversation - clean. The
        history database says a turn read outside text: tainted. The
        database holds every earlier user message the request carries, and
        none read outside text: clean. Anything else - no database, history
        off when those turns were said, a temporary chat, an unreadable file,
        no messages to count - tainted: this PC cannot vouch for turns it
        did not see (G1)."""
        earlier = _earlier_user_messages(messages)
        if earlier == 0:
            return False
        if not (isinstance(cid, str) and _CID.fullmatch(cid)):
            return True
        try:
            db = self._db_turns(cid)
        except Exception:
            return True
        if db is None:
            return True
        users, outside = db
        if outside:
            return True
        return earlier is None or users < earlier

    def _seed(self, cid, messages) -> None:
        """The first time this process meets `cid`: decide its taint from
        _unknown_tainted and remember it. A tainted one is tainted from before
        any turn this process saw (seq 0). Under self._lock."""
        if cid in self._seen:
            self._seen.move_to_end(cid)
            return
        tainted = self._unknown_tainted(cid, messages)
        self._met(cid)
        if tainted:
            self._taint[cid] = 0
        self._rehydrate(cid)

    def _rehydrate(self, cid) -> None:
        """A conversation this process meets for the first time, and the PC
        already holds (after a restart, or "Continue this chat" on a chat the
        registry has forgotten): put the owner's own typed and spoken
        messages of it back in the live-turn registry, from the encrypted
        record.

        Why (the owner, 2026-09-28, after the second chat audit): the apps
        re-send earlier messages with every question, and automatic learning
        saves a fact only from messages this PC saw arrive live. A restart
        wiped the registry, so after Continue every new fact waited as a card
        for about ten questions. The PC's own record is as good as having
        seen the message: it wrote those words itself.

        Only what the record vouches for: user rows tagged "typed" or "voice"
        (never shared, pasted, clipboard, picture, chatbot, support, imported
        or tool text), with the voice check's facts kept beside a spoken one,
        in a chat of a kind the apps may continue, and never in a chat titled
        "A difficult moment". The outside-text mark is not decided here: it
        is the taint _seed just worked out from the same record, and every
        re-registered turn of a tainted chat is tainted. A message the app
        re-sends with other words matches nothing (the registry is keyed by
        the words' hash), so it is a card, as before. Best effort: no key,
        no record or any error re-registers nothing, which is the old
        behaviour. Under self._lock."""
        try:
            if not self.db_path.exists():
                return
            with closing(self._connect()) as c:
                conv = c.execute("SELECT title, COALESCE(kind, 'chat') FROM conversations"
                                 " WHERE id=?", (cid,)).fetchone()
                if conv is None or conv[1] not in CONTINUABLE:
                    return
                rows = c.execute(
                    "SELECT idx, at, provenance, device, read_outside, voice_check, text"
                    " FROM turns WHERE conversation_id=? AND role='user'"
                    " AND provenance IN ('typed', 'voice') ORDER BY idx DESC LIMIT ?",
                    (cid, REHYDRATE_MAX)).fetchall()
                hush = self._hush_read(c, cid)
            if not rows:
                return
            aead = self._cipher()
            if self._title(aead, cid, conv[0]) == CRISIS_TITLE:
                return
            floor_seq = None
            for idx, at, prov, device, outside, vc, blob in reversed(rows):
                try:
                    text = self._open(aead, blob, self._aad(cid, idx)).decode("utf-8")
                except Exception:
                    continue
                if not _norm(text):
                    continue
                voice_check = None
                if prov == "voice" and vc:
                    try:
                        got = json.loads(vc)
                        voice_check = got if isinstance(got, dict) else None
                    except ValueError:
                        voice_check = None
                self._live_seq += 1
                key = (cid, _hash(text))
                self._live.pop(key, None)
                self._live[key] = {"conversation_id": cid, "message_hash": key[1],
                                   "provenance": prov, "voice_check": voice_check,
                                   "read_outside": bool(outside),
                                   "device": device if device in DEVICES else "unknown",
                                   "at": float(at or 0), "seq": self._live_seq,
                                   "from_record": True}
                if hush is not None and idx <= hush["upto"]:
                    floor_seq = self._live_seq
            if floor_seq is not None:
                self._hush_floor[cid] = {"seq": floor_seq, "erased": hush["erased"]}
            while len(self._live) > LIVE_MAX:
                self._live.popitem(last=False)
        except Exception:
            return

    @staticmethod
    def _hush_key(cid: str) -> str:
        return "hush:" + cid

    def _hush_read(self, c, cid: str):
        """{"upto": last turn number, "erased": bool} or None."""
        row = c.execute("SELECT v FROM meta WHERE k=?", (self._hush_key(cid),)).fetchone()
        if row is None:
            return None
        try:
            d = json.loads(bytes(row[0]).decode("utf-8"))
            upto = d["upto"]
            if isinstance(upto, bool) or not isinstance(upto, int):
                return None
            return {"upto": upto, "erased": bool(d.get("erased"))}
        except Exception:
            return None

    def note_hush(self, cid, erased: bool = False) -> None:
        """The owner Forgot or Erased a fact that was said in `cid`
        (jarvis_auto_learn.forgotten_in): keep, in the record itself, that
        every message of it kept so far was already learned from - numbers
        only, never words. After a restart and "Continue this chat" those
        messages come back into the registry (_rehydrate), and without this
        the learner would propose the forgotten fact again. Nothing to keep
        for a chat that is not in the record (a temporary chat, history off).
        Never raises."""
        try:
            if not (isinstance(cid, str) and _CID.fullmatch(cid)) or not self.db_path.exists():
                return
            with self._lock, closing(self._connect()) as c:
                last = c.execute("SELECT MAX(idx) FROM turns WHERE conversation_id=?"
                                 " AND role='user'", (cid,)).fetchone()
                if last is None or last[0] is None:
                    return
                prev = self._hush_read(c, cid) or {"upto": -1, "erased": False}
                new = {"upto": max(int(last[0]), prev["upto"]),
                       "erased": bool(erased or prev["erased"])}
                with c:
                    c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)",
                              (self._hush_key(cid), json.dumps(new).encode("utf-8")))
        except Exception:
            pass

    def hush_floor(self, cid) -> Optional[dict]:
        """{"seq", "erased"} - registry turns of `cid` up to `seq` were
        already learned from before a Forget or Erase - or None."""
        with self._lock:
            got = self._hush_floor.get(cid)
            return dict(got) if got else None

    def live_upto(self, cid) -> Optional[int]:
        """The newest registry seq of `cid`, or None when it has no turn there."""
        with self._lock:
            seqs = [e["seq"] for (c, _h), e in self._live.items() if c == cid]
            return max(seqs) if seqs else None

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

    def live_turn_any(self, text) -> Optional[dict]:
        """live_turn() for a message in ANY conversation: the newest entry
        with exactly these words, or None. For "said again" (jarvis_intake.
        note_said_again), whose caller - the learner - does not know which
        conversation it is reading."""
        if not isinstance(text, str) or not _norm(text):
            return None
        h = _hash(text)
        with self._lock:
            best = None
            for (cid, hh), entry in self._live.items():      # oldest first
                if hh == h:
                    best = (cid, entry)
            if best is None:
                return None
            cid, got = best
            out = dict(got)
            if isinstance(out.get("voice_check"), dict):
                out["voice_check"] = dict(out["voice_check"])
            since = self._taint.get(cid)
            out["tainted"] = since is not None and since <= out["seq"]
            return out

    def conversation_tainted(self, conversation_id, messages=None) -> bool:
        """Has any earlier turn of this conversation read outside text?
        `messages`: the request's messages as they arrived, for a
        conversation this process has not met (see _unknown_tainted). A
        request with no usable conversation id cannot be looked up: it is
        tainted when it carries any earlier turn. Fails closed."""
        if not (isinstance(conversation_id, str) and _CID.fullmatch(conversation_id)):
            return _earlier_user_messages(messages) != 0
        with self._lock:
            self._seed(conversation_id, messages)
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
        side_talk = bool(turn and turn.get("side_talk") is True)
        temporary = body.get("temporary") is True or side_talk
        if temporary:
            # temporary-chat.patch (the owner's decision, 2026-09-25): a
            # temporary chat is never kept. Its turns still go in the
            # live-turn registry below - a hash, never the words, in memory
            # only - so a tool that read outside text still marks the rest of
            # the conversation (the note-write card, jarvis_agent), but under
            # the provenance "temporary": if an app ever re-sent one of them
            # in a normal chat, automatic learning would make it a card
            # ("said in a temporary chat"), never a saved fact.
            rows = [(text, "temporary", None) for text, _prov, _vc in rows]
        # The live-turn registry is written for EVERY request, before the
        # switch is read: automatic learning trusts only turns this PC saw
        # arrive, whether or not history is kept (jarvis_auto_learn.py).
        # A conversation this process has not met is seeded first - from the
        # database as it was BEFORE this turn is written (G1).
        with self._lock:
            self._seed(cid, body.get("messages"))
        self._note_live(cid, rows, device, read_outside, now)
        if side_talk:
            return {"recorded": False, "why": SIDE_TALK_WHY}
        if temporary:
            return {"recorded": False, "why": TEMPORARY_WHY}
        aead, why = self._recording()
        if aead is None:
            return {"recorded": False, "why": why}
        # Feasibility I115, "Paste guard": masked HERE, after _note_live above
        # already hashed the ORIGINAL words (so live_turn()'s exact-hash
        # lookup for automatic learning still matches what the model was
        # actually shown this turn), and only now, right before the words
        # are written to the encrypted database for good.
        crisis = _crisis_turn(rows, turn)
        rows = [(self._mask_for_storage(text), prov,
                 None if vc is None else json.dumps(vc, sort_keys=True))
                for text, prov, vc in rows]
        if not rows:
            return {"recorded": False, "why": "no words in the user message"}
        # Jarvis Live marks each spoken message it sends (`live: true`, the
        # apps' JARVIS-API section 63): a conversation that starts with one
        # is a Live session in History.
        kind = "live" if any(isinstance(m, dict) and m.get("live") is True for m in live) \
            else "chat"
        return self._write_turn(aead, cid, rows, device, lane, read_outside, answer_kept,
                                answer, at, now, kind=kind, crisis=crisis)

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

    def _mask_for_storage(self, text: str) -> str:
        """Feasibility I115, "Paste guard": a pasted password, PIN or
        one-time code, masked before these words are written to the
        encrypted database - never before now. By the time this runs, the
        model has already answered this turn on the ORIGINAL words (`turn`
        is what it returned), and _note_live above has already hashed the
        ORIGINAL words too, so this changes only what is kept, never what
        was seen. Without jarvis_paste_guard.py, or on any error inside it
        (which itself never raises - this is only for a missing module),
        the words are stored exactly as they were before this feature."""
        if _paste_guard is None:
            return text
        try:
            masked, _changed = _paste_guard.guard(text)
            return masked
        except Exception:
            return text

    def _write_turn(self, aead, cid, rows, device, lane, read_outside, answer_kept,
                    answer, at, now, *, kind: str = "chat", crisis: bool = False) -> dict:
        lane = str(lane or "")[:200]
        kind = kind if kind in KINDS else "chat"
        with self._lock, closing(self._connect()) as c:
            with c:
                conv = c.execute("SELECT id FROM conversations WHERE id=?", (cid,)).fetchone()
                nxt = c.execute("SELECT COALESCE(MAX(idx), -1) + 1 FROM turns"
                                " WHERE conversation_id=?", (cid,)).fetchone()[0]
                if conv is None:
                    title = CRISIS_TITLE if crisis else _title_from(rows)
                    c.execute("INSERT INTO conversations (id, title, started, updated, device,"
                              " kind) VALUES (?,?,?,?,?,?)",
                              (cid, self._seal(aead, title.encode("utf-8"),
                                               self._aad(cid, "title")), at, now, device, kind))
                elif crisis:
                    # A crisis turn later in a chat: from now on the chat is
                    # titled "A difficult moment" - never the owner's words.
                    c.execute("UPDATE conversations SET title=? WHERE id=?",
                              (self._seal(aead, CRISIS_TITLE.encode("utf-8"),
                                          self._aad(cid, "title")), cid))
                if conv is not None and rows[0][1] == "shared" and len(rows) > 1:
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

    # -- a customer-support chat (jarvis_support.py) -------------------------
    def record_support(self, cid, title, rows) -> dict:
        """Keep a finished customer-support chat as ONE conversation of its
        own: every row role "support" (never "user", so the learner never
        reads a word of it - jarvis_intake.owner_turns reads role "user"
        only), each with its author as `provenance` (SUPPORT_PROVENANCES),
        read_outside true (the company's words are outside text, so the
        whole record is tainted) and answer_kept false. It never touches the
        live-turn registry: nothing here was said to Jarvis by the owner.
        Encrypted like every other turn; a pasted password or code in any
        row is masked first (_mask_for_storage). Writing the same chat
        again replaces it (a Resume after a pause ends in one record)."""
        return self._record_whole(cid, title or "Support chat", rows, kind="support",
                                  role="support", provenances=SUPPORT_PROVENANCES,
                                  max_rows=SUPPORT_MAX_ROWS)

    # -- a chatbot conversation or comparison (jarvis_chatbot*.py) ----------
    def record_chatbot(self, cid, title, rows, *, kind: str = "chatbot") -> dict:
        """Keep a finished conversation Jarvis had with another AI chatbot
        (kind "chatbot") or a whole comparison (kind "compare") as ONE
        conversation of its own - the owner's decision of 2026-09-28 ("Chats
        with other AIs and comparisons are kept in History, encrypted, marked
        as outside text, never learned from, never read aloud"). Exactly the
        shape of a support record: every row role "chatbot" (never "user" -
        the learner reads role "user" only, so no word of it is ever learned
        from), its author as `provenance` (CHATBOT_PROVENANCES), read_outside
        true (the chatbot's replies are outside text, so the whole record is
        tainted), answer_kept false, never in the live-turn registry. Neither
        app offers "Continue this chat" on it. Writing the same id again
        replaces it."""
        kind = kind if kind in ("chatbot", "compare") else "chatbot"
        return self._record_whole(cid, title or ("Comparison" if kind == "compare"
                                                 else "Chat with a chatbot"),
                                  rows, kind=kind, role="chatbot",
                                  provenances=CHATBOT_PROVENANCES,
                                  max_rows=CHATBOT_MAX_ROWS)

    def _record_whole(self, cid, title, rows, *, kind, role, provenances, max_rows) -> dict:
        """record_support and record_chatbot: one finished record, all
        outside text, written whole (the same id again replaces it)."""
        if not (isinstance(cid, str) and _CID.fullmatch(cid)):
            return {"recorded": False, "why": "not a conversation id"}
        aead, why = self._recording()
        if aead is None:
            return {"recorded": False, "why": why}
        clean = []
        for r in list(rows or [])[:max_rows]:
            if not isinstance(r, dict):
                continue
            prov = r.get("provenance")
            prov = prov if prov in provenances else f"{role}_note"
            text = self._mask_for_storage(str(r.get("text") or ""))
            try:
                at = float(r.get("at") or self._clock())
            except (TypeError, ValueError):
                at = self._clock()
            if text.strip():
                clean.append((prov, text, at))
        if not clean:
            return {"recorded": False, "why": "nothing was said"}
        now = self._clock()
        title = str(title)[:TITLE_CHARS]
        with self._lock, closing(self._connect()) as c:
            with c:
                self._drop(c, [cid])
                c.execute("INSERT INTO conversations (id, title, started, updated, device, kind)"
                          " VALUES (?,?,?,?,?,?)",
                          (cid, self._seal(aead, title.encode("utf-8"),
                                           self._aad(cid, "title")), clean[0][2], now, "pc",
                           kind))
                for idx, (prov, text, at) in enumerate(clean):
                    c.execute("INSERT INTO turns (conversation_id, idx, at, role, provenance,"
                              " device, lane, read_outside, answer_kept, voice_check, text)"
                              " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (cid, idx, at, role, prov, "pc", "", 1, 0, None,
                               self._seal(aead, text.encode("utf-8"), self._aad(cid, idx))))
        return {"recorded": True, "conversation_id": cid, "rows": len(clean)}

    # -- reading ------------------------------------------------------------
    def status(self) -> dict:
        st = self.settings()
        aead, why = self._recording()
        return {"enabled": st["enabled"], "recording": aead is not None, "why_not": why,
                "waiting": state()["waiting"], "keep_days": st["keep_days"],
                "encrypted": True}

    def _keeping(self) -> dict:
        """Whether NEW messages are being kept right now - the small answer
        "Continue this chat" needs (the owner, 2026-09-29): the same
        `enabled` / `recording` / `why_not` the list already carries, nothing
        more. Never raises: a history that cannot say reads as not recording."""
        try:
            st = self.status()
            return {"enabled": bool(st["enabled"]), "recording": bool(st["recording"]),
                    "why_not": str(st["why_not"] or "")}
        except Exception as exc:  # noqa: BLE001 - a read that must not break the chat
            return {"enabled": False, "recording": False,
                    "why_not": f"the chat history could not be checked ({type(exc).__name__})"}

    def list(self, limit=LIST_DEFAULT, before=None, kind=None, tag=None) -> dict:
        """One page of the History list, newest first. `kind`: only that
        kind (KINDS) - "Live only" in both apps; anything else is ignored.
        `tag`: an int (only that tag's chats) or "none" (untagged); anything
        else is ignored."""
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
        sql = ("SELECT " + _conv_cols("c") + ","
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
        where, args = [], []
        if isinstance(before, (int, float)) and not isinstance(before, bool) \
                and math.isfinite(before):
            where.append("c.updated < ?")
            args.append(float(math.floor(before)))
        kind = kind if kind in KINDS else None
        if kind is not None:
            where.append("COALESCE(c.kind, 'chat') = ?")
            args.append(kind)
        out["kind"] = kind
        tag = _tag_filter(tag)
        tag_sql, tag_args = _tag_where(tag)
        if tag_sql:
            where.append(tag_sql)
            args += tag_args
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._lock, closing(self._connect()) as c:
            rows = c.execute(sql + clause + " ORDER BY c.updated DESC, c.id DESC LIMIT ?",
                             args + [limit]).fetchall()
            if len(rows) == limit:
                sec = math.floor(rows[-1][CONV_COLS.index("updated")] or 0)
                have = {r[0] for r in rows}
                extra = " AND COALESCE(c.kind, 'chat') = ?" if kind is not None else ""
                if tag_sql:
                    extra += " AND " + tag_sql
                rest = c.execute(sql + " WHERE c.updated >= ? AND c.updated < ?" + extra
                                 + " ORDER BY c.updated DESC, c.id DESC",
                                 [float(sec), float(sec + 1)]
                                 + ([kind] if kind is not None else [])
                                 + tag_args).fetchall()
                rows += [r for r in rest if r[0] not in have]
        nc = len(CONV_COLS)
        for r in rows:
            cv = _conv_named(r)
            n, voice, outside = r[nc:nc + 3]
            out["conversations"].append(_row(
                cv["id"], self._title(aead, cv["id"], cv["title"]), cv["started"],
                cv["updated"], n, cv["device"], bool(voice), bool(outside),
                cv["kind"], cv["project"], cv["tag_id"]))
        return out

    def _title(self, aead, cid, blob) -> str:
        try:
            return self._open(aead, blob, self._aad(cid, "title")).decode("utf-8")
        except Exception:
            return "(this title could not be opened)"

    def get(self, cid):
        """The whole conversation, or None if there is no such one. Raises
        KeyUnavailable when it cannot be opened. `kind` says what it is,
        `continuable` whether the apps may offer "Continue this chat" on it
        (CONTINUABLE, and not a chat titled "A difficult moment"), and
        `continue_why` why not when they may not. `history` says whether new
        messages are being kept (`enabled`, `recording`, `why_not`), so
        "Continue this chat" can warn when they will not be."""
        self._housekeeping()
        if not (isinstance(cid, str) and _CID.fullmatch(cid)) or not self.db_path.exists():
            return None
        with self._lock, closing(self._connect()) as c:
            got = c.execute(f"SELECT {_conv_cols()} FROM conversations WHERE id=?",
                            (cid,)).fetchone()
            if got is None:
                return None
            conv = _conv_named(got)
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
            if role == "support":
                # A customer-support chat (record_support): who wrote it.
                t.update(provenance=prov or "support_note", read_outside=True)
            elif role == "chatbot":
                # A chatbot conversation or comparison (record_chatbot): who
                # wrote it. Outside text as a whole, like a support record.
                t.update(provenance=prov or "chatbot_note", read_outside=True)
            elif role == "user":
                t.update(provenance=prov or "unknown", read_outside=bool(outside),
                         answer_kept=bool(kept))
            turns.append(t)
        kind = conv["kind"] if conv["kind"] in KINDS else "chat"
        title = self._title(aead, cid, conv["title"])
        crisis = kind in CONTINUABLE and title == CRISIS_TITLE
        return {"id": cid, "title": title, "history": self._keeping(),
                "tainted": any(bool(r[4]) for r in rows), "turns": turns,
                "kind": kind, "project": conv["project"] or None,
                "tag_id": _tag_id(conv["tag_id"]),
                "started": int(conv["started"] or 0), "updated": int(conv["updated"] or 0),
                "continuable": kind in CONTINUABLE and not crisis,
                "continue_why": (CRISIS_CONTINUE_WHY if crisis
                                 else "" if kind in CONTINUABLE else CONTINUE_WHY[kind])}

    def search(self, query, limit=SEARCH_DEFAULT, kind=None) -> dict:
        """Search what was said in the kept conversations (GET
        /api/history/search, docs/JARVIS-API.md section 71; the owner's
        choice of 2026-09-28, under their answer of 2026-09-27: "A search
        box in History for the owner's own old chats is allowed now (shown
        on screen only; nothing saved, nothing handed to the AI)").

        UNLOCK AND SCAN, IN MEMORY, FOR EACH SEARCH. Every turn is opened
        with the key, compared with the search words, and dropped. There is
        NO search index - not FTS5, not a word list, not a cache between
        searches: an index would be a plain-text copy of the chats on disk,
        beside the encrypted one, and "encrypted or not kept" (ARCHITECTURE
        section 5) allows no such thing. The search words are not written
        anywhere, not logged and not audited; nothing in this method writes
        to the database except the keep-period sweep list() already runs.

        The words are matched as the owner typed them, each one anywhere in
        the conversation (so "dentist tuesday" finds a chat that says both,
        in any order, in any message), case ignored. Newest conversations
        first; at most `limit` of them come back, and `more` says there
        were others. The scan stops at SEARCH_SCAN_MAX conversations or
        SEARCH_SECONDS, whichever comes first, and `partial` says so.

        What it reaches is exactly what the History list shows: what is
        still kept. A temporary chat was never kept, so it is never found.
        With history OFF the kept conversations are still searched, as the
        list still lists them - and nothing new is kept by searching.

        `kind` (one of KINDS; anything else is ignored) searches only that
        kind, so "Live only" and a typed search combine (the second chat
        audit, 2026-09-28, finding 8: the search used to return every kind
        while the filter still said "Live only").

        Returns status() plus {"query_ok", "kind", "conversations": [a list() row
        plus "snippet" and "hits"], "more", "partial", "searched"}; or, for
        search words that are too short or too long, {"query_ok": false,
        "why": "<plain sentence>"} and no conversation."""
        self._housekeeping()
        out = self.status()
        kind = kind if kind in KINDS else None
        out.update(query_ok=True, why="", conversations=[], more=False,
                   partial=False, searched=0, kind=kind)
        terms, why = search_terms(query)
        if terms is None:
            out.update(query_ok=False, why=why)
            return out
        try:
            limit = max(1, min(SEARCH_MAX, int(limit)))
        except (TypeError, ValueError):
            limit = SEARCH_DEFAULT
        if not self.db_path.exists():
            return out
        try:
            aead = self._cipher()
        except KeyUnavailable as exc:
            out["why_not"] = out["why_not"] or str(exc)
            return out
        with self._lock, closing(self._connect()) as c:
            convs = c.execute(
                "SELECT " + _conv_cols("c") + " FROM conversations c"
                + (" WHERE COALESCE(c.kind, 'chat') = ?" if kind is not None else "")
                + " ORDER BY c.updated DESC, c.id DESC LIMIT ?",
                ([kind] if kind is not None else []) + [SEARCH_SCAN_MAX + 1]).fetchall()
        if len(convs) > SEARCH_SCAN_MAX:
            convs = convs[:SEARCH_SCAN_MAX]
            out["partial"] = True
        rx = [re.compile(re.escape(t), re.IGNORECASE) for t in terms]
        deadline = time.monotonic() + SEARCH_SECONDS
        found = []
        with closing(self._connect()) as c:
            for n, conv_row in enumerate(convs):
                cv = _conv_named(conv_row)
                cid, title_blob, started, updated = cv["id"], cv["title"], cv["started"], cv["updated"]
                device, rkind, project, tid = cv["device"], cv["kind"], cv["project"], cv["tag_id"]
                if time.monotonic() > deadline:
                    out["partial"] = True
                    break
                out["searched"] = n + 1
                rows = c.execute(
                    "SELECT idx, at, role, provenance, read_outside, text FROM turns"
                    " WHERE conversation_id=? ORDER BY idx", (cid,)).fetchall()
                title = self._title(aead, cid, title_blob)
                texts = []   # (role, at, words) - only while this conversation is looked at
                voice = outside = False
                for idx, at, role, prov, ro, blob in rows:
                    voice = voice or prov in ("voice", "voice_unverified")
                    outside = outside or bool(ro)
                    try:
                        words = self._open(aead, blob, self._aad(cid, idx)).decode("utf-8")
                    except Exception:
                        continue
                    texts.append((role, at, words))
                hit = _conversation_hit(rx, title, texts)
                texts = None
                if hit is None:
                    continue
                if len(found) >= limit:
                    out["more"] = True
                    break
                snippet, hits = hit
                row = _row(cid, title, started, updated, len(rows), device, voice, outside,
                           rkind, project, tid)
                row.update(snippet=snippet, hits=hits)
                found.append(row)
        out["conversations"] = found
        return out

    def brief(self, cid) -> Optional[dict]:
        """One conversation's title, kind and when it was last added to -
        no message is opened. For "Erase the words"'s "Also delete the chat
        it came from" (the chat audit, 2026-09-28), which names the chat
        before asking. None when there is no such conversation; raises
        KeyUnavailable when its title cannot be opened."""
        if not (isinstance(cid, str) and _CID.fullmatch(cid)) or not self.db_path.exists():
            return None
        with self._lock, closing(self._connect()) as c:
            row = c.execute(f"SELECT {_conv_cols()} FROM conversations WHERE id=?",
                            (cid,)).fetchone()
        if row is None:
            return None
        cv = _conv_named(row)
        aead = self._cipher()
        return {"id": cid, "title": self._title(aead, cid, cv["title"]),
                "updated": int(cv["updated"] or 0),
                "kind": cv["kind"] if cv["kind"] in KINDS else "chat",
                "tag_id": _tag_id(cv["tag_id"])}

    # -- chat tags (docs/CHAT-TAGS-DESIGN.md, JARVIS-API section 99) --------
    def _tag_cipher(self):
        """(aead or None, why). Tags are the owner's own labels on chats that
        are already saved, so they work while chat history is switched OFF
        (owner, 2026-09-30: filing an old chat records nothing new). Only a
        missing or wrong key stops them - fail closed, nothing read or
        written."""
        try:
            return self._cipher(), ""
        except KeyUnavailable as exc:
            return None, str(exc)
        except Exception as exc:
            return None, f"the chat history could not be opened ({type(exc).__name__})"

    def _load_tags(self, c, aead) -> dict:
        """The registry {"next_id", "tags": [{"id","name","colour","icon"}]}
        from `meta` (or the starter tags, not yet written). Raises on a value
        that will not open - never guesses."""
        row = c.execute("SELECT v FROM meta WHERE k=?", (_TAGS_KEY,)).fetchone()
        if row is None:
            return {"next_id": len(TAG_STARTERS) + 1, "fresh": True,
                    "tags": [{"id": i + 1, "name": n, "colour": col, "icon": ic}
                             for i, (n, col, ic) in enumerate(TAG_STARTERS)]}
        d = json.loads(self._open(aead, row[0], _TAGS_AAD).decode("utf-8"))
        tags = [{"id": int(t["id"]), "name": str(t["name"]), "colour": int(t["colour"]),
                 "icon": str(t["icon"])} for t in d["tags"]]
        return {"next_id": max(int(d["next_id"]), max((t["id"] for t in tags), default=0) + 1),
                "fresh": False, "tags": tags}

    def _save_tags(self, c, aead, reg: dict) -> None:
        plain = json.dumps({"next_id": reg["next_id"], "tags": reg["tags"]},
                           ensure_ascii=False).encode("utf-8")
        c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)",
                  (_TAGS_KEY, self._seal(aead, plain, _TAGS_AAD)))
        reg["fresh"] = False

    def _tags_answer(self, c, reg: dict) -> dict:
        counts = {int(r[0]): int(r[1]) for r in c.execute(
            "SELECT tag_id, COUNT(*) FROM conversations WHERE tag_id IS NOT NULL"
            " GROUP BY tag_id")}
        ids = {t["id"] for t in reg["tags"]}
        total = int(c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])
        tagged = sum(n for i, n in counts.items() if i in ids)
        return {"ok": True,
                "tags": [dict(t, order=i, count=counts.get(t["id"], 0))
                         for i, t in enumerate(reg["tags"])],
                "untagged": total - tagged}

    def tags(self) -> dict:
        """GET /api/history/tags: {"ok", "tags": [Tag + count], "untagged"}.
        The starter tags are written the first time this is read with the
        key. Without the key: the tags cannot be opened, so none are listed
        and `why_not` says why (the chats still list, untagged)."""
        self._housekeeping()
        try:
            aead = self._cipher()
        except KeyUnavailable as exc:
            return {"ok": True, "tags": [], "untagged": 0, "why_not": str(exc)}
        except Exception as exc:
            return {"ok": True, "tags": [], "untagged": 0,
                    "why_not": f"the chat history could not be opened ({type(exc).__name__})"}
        try:
            with self._lock, closing(self._connect()) as c:
                reg = self._load_tags(c, aead)
                if reg["fresh"]:
                    with c:
                        self._save_tags(c, aead, reg)
                return self._tags_answer(c, reg)
        except Exception as exc:
            return {"ok": True, "tags": [], "untagged": 0,
                    "why_not": f"the tags could not be opened ({type(exc).__name__})"}

    def tag_op(self, body) -> tuple:
        """POST /api/history/tags: add / rename / style / move / delete.
        (http code, answer). Nothing is written without the key or while
        history is off; nothing is guessed."""
        if not isinstance(body, dict) or not isinstance(body.get("op"), str):
            return 400, _tag_fail("bad_request")
        op = body["op"]
        if op not in ("add", "rename", "style", "move", "delete"):
            return 400, _tag_fail("bad_request")
        aead, why = self._tag_cipher()
        if aead is None:
            return 503, _tag_fail("bad_request", _off_message(why, "Tags are not changed."))
        with self._lock, closing(self._connect()) as c:
            try:
                reg = self._load_tags(c, aead)
            except Exception:
                return 503, _tag_fail("bad_request", "The tags could not be opened, so "
                                      "they are not changed.")
            tags = reg["tags"]

            def find(v):
                if not _is_int(v):
                    return None
                return next((t for t in tags if t["id"] == v), None)

            def taken(name, skip=None):
                return any(_tag_key(t["name"]) == _tag_key(name) and t is not skip
                           for t in tags)

            with c:
                if op == "add":
                    if len(tags) >= TAG_MAX:
                        return 409, _tag_fail("too_many_tags")
                    name = _clean_tag_name(body.get("name"))
                    if name is None:
                        return 400, _tag_fail("bad_name")
                    colour = body.get("colour", len(tags) % TAG_COLOURS)
                    if not _is_int(colour) or not 0 <= colour < TAG_COLOURS:
                        return 400, _tag_fail("bad_colour")
                    icon = body.get("icon", "star")
                    if icon not in TAG_ICONS:
                        return 400, _tag_fail("bad_icon")
                    if taken(name):
                        return 409, _tag_fail("name_taken")
                    tag = {"id": reg["next_id"], "name": name, "colour": colour, "icon": icon}
                    reg["next_id"] += 1
                    tags.append(tag)
                elif op == "rename":
                    tag = find(body.get("id"))
                    if tag is None:
                        return 404, _tag_fail("tag_not_found")
                    name = _clean_tag_name(body.get("name"))
                    if name is None:
                        return 400, _tag_fail("bad_name")
                    if taken(name, skip=tag):
                        return 409, _tag_fail("name_taken")
                    tag["name"] = name
                elif op == "style":
                    tag = find(body.get("id"))
                    if tag is None:
                        return 404, _tag_fail("tag_not_found")
                    if "colour" not in body and "icon" not in body:
                        return 400, _tag_fail("bad_request")
                    if "colour" in body:
                        col = body["colour"]
                        if not _is_int(col) or not 0 <= col < TAG_COLOURS:
                            return 400, _tag_fail("bad_colour")
                    if "icon" in body and body["icon"] not in TAG_ICONS:
                        return 400, _tag_fail("bad_icon")
                    if "colour" in body:
                        tag["colour"] = body["colour"]
                    if "icon" in body:
                        tag["icon"] = body["icon"]
                elif op == "move":
                    tag = find(body.get("id"))
                    if tag is None:
                        return 404, _tag_fail("tag_not_found")
                    before = body.get("before")
                    if before is not None:
                        anchor = find(before)
                        if anchor is None:
                            return 404, _tag_fail("tag_not_found")
                    if before is None:
                        tags.remove(tag)
                        tags.append(tag)
                    elif anchor is not tag:
                        tags.remove(tag)
                        tags.insert(tags.index(anchor), tag)
                else:   # delete
                    tag = find(body.get("id"))
                    if tag is None:
                        return 404, _tag_fail("tag_not_found")
                    tags.remove(tag)
                    c.execute("UPDATE conversations SET tag_id=NULL WHERE tag_id=?",
                              (tag["id"],))
                self._save_tags(c, aead, reg)
            out = self._tags_answer(c, reg)
            out["tag"] = next((dict(t, order=i, count=0) for i, t in enumerate(tags)
                               if t["id"] == tag["id"]), None) if op != "delete" else None
            if out["tag"] is not None:
                out["tag"]["count"] = next(t["count"] for t in out["tags"]
                                           if t["id"] == tag["id"])
            return 200, out

    def set_tag(self, cid, tag_id) -> tuple:
        """POST /api/history/tag: file one chat under a tag, or (None) unfile
        it. (http code, answer). One tag per chat; moving is just setting."""
        if not (isinstance(cid, str) and _CID.fullmatch(cid)) \
                or not (tag_id is None or _is_int(tag_id)):
            return 400, _tag_fail("bad_request")
        aead, why = self._tag_cipher()
        if aead is None:
            return 503, _tag_fail("bad_request", _off_message(why, "The chat is not filed."))
        if not self.db_path.exists():
            return 404, _tag_fail("not_found")
        with self._lock, closing(self._connect()) as c:
            if c.execute("SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone() is None:
                return 404, _tag_fail("not_found")
            if tag_id is not None:
                try:
                    reg = self._load_tags(c, aead)
                except Exception:
                    return 503, _tag_fail("bad_request", "The tags could not be opened, so "
                                          "the chat is not filed.")
                if not any(t["id"] == tag_id for t in reg["tags"]):
                    return 404, _tag_fail("tag_not_found")
                if reg["fresh"]:
                    with c:
                        self._save_tags(c, aead, reg)
            with c:
                c.execute("UPDATE conversations SET tag_id=? WHERE id=?", (tag_id, cid))
        return 200, {"ok": True, "id": cid, "tag_id": tag_id}

    def _drop_unknown_tag(self, c, cid: str) -> None:
        """After a chat was put back: a tag deleted while it was held is
        gone, so the chat comes back untagged rather than under a number
        nothing explains. Leaves it alone if the registry cannot be read."""
        try:
            row = c.execute("SELECT tag_id FROM conversations WHERE id=?", (cid,)).fetchone()
            if row is None or row[0] is None:
                return
            ids = {t["id"] for t in self._load_tags(c, self._cipher())["tags"]}
        except Exception:
            return
        if row[0] not in ids:
            c.execute("UPDATE conversations SET tag_id=NULL WHERE id=?", (cid,))

    def tainted_from(self, cid):
        """The number of the first turn that read outside text, or None. Every
        turn from that one on is tainted. The running PC does not call this
        (the learner reads each turn's own `read_outside` mark, and
        _rehydrate does the same per row); it is kept for the tests that
        pin the marks (the second chat audit, 2026-09-28)."""
        if not self.db_path.exists():
            return None
        with self._lock, closing(self._connect()) as c:
            row = c.execute("SELECT MIN(idx) FROM turns WHERE conversation_id=?"
                            " AND read_outside=1", (cid,)).fetchone()
        return None if row is None or row[0] is None else int(row[0])

    def delete(self, cid) -> bool:
        """One conversation. True if there was one. There is no delete-all here: the one
        exception, "Forget a time frame", is take_out() below, after a checked
        list and ONE approval card."""
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

    # -- "Forget a time frame" (jarvis_forget_range.py, 2026-09-28) --------
    #
    # The one exception to "there is no delete-all" (docs/JARVIS-API.md
    # section 18): the owner's decision of 2026-09-28. It never deletes by
    # itself - jarvis_forget_range.py lists the conversations first, the
    # owner unticks any to keep, ONE approval card lists every one, and only
    # the ids on that card reach take_out(). What take_out() removes is held
    # IN MEMORY for the 10-minute Undo (put_back()), still sealed exactly as
    # it was on disk, and never written anywhere else.

    _TURN_COLS = ("conversation_id, idx, at, role, provenance, device, lane, read_outside,"
                  " answer_kept, voice_check, text")

    def overlapping(self, start: float, end: float, limit: int = 201,
                    only=None) -> dict:
        """The conversations that OVERLAP [start, end) - a message at or
        after `start` and before `end`, or one that started before and went
        on after. Oldest first, at most `limit`, with how many in all.

        {"items": [{"id", "title", "started", "updated", "turns", "in_frame",
        "spills"}], "total": n, "why_not": ""}. `spills`: the conversation
        also has messages outside the frame - deleting it deletes those too,
        and the list says so. Titles need the key; without it `why_not` says
        why and `items` is empty. `only`: these ids and no others (checking
        that the ids on an approval card are still in the frame)."""
        out = {"items": [], "total": 0, "why_not": ""}
        if not self.db_path.exists():
            return out
        ids = None
        if only is not None:
            ids = [i for i in only if isinstance(i, str) and _CID.fullmatch(i)]
            if not ids:
                return out
        with self._lock, closing(self._connect()) as c:
            # A conversation's own first and last message, from its turns
            # (`started`/`updated` are the same moments, kept on the row).
            sql = ("SELECT " + _conv_cols("c") + ","
                   " (SELECT COUNT(*) FROM turns t WHERE t.conversation_id=c.id),"
                   " (SELECT COUNT(*) FROM turns t WHERE t.conversation_id=c.id"
                   "   AND t.at >= ? AND t.at < ?),"
                   " (SELECT MIN(at) FROM turns t WHERE t.conversation_id=c.id),"
                   " (SELECT MAX(at) FROM turns t WHERE t.conversation_id=c.id)"
                   " FROM conversations c"
                   " WHERE COALESCE(c.started, c.updated) < ? AND c.updated >= ?")
            where = ("SELECT COUNT(*) FROM conversations c"
                     " WHERE COALESCE(c.started, c.updated) < ? AND c.updated >= ?")
            args = [float(start), float(end), float(end), float(start)]
            count_args = [float(end), float(start)]
            if ids is not None:
                marks = ",".join("?" * len(ids))
                sql += f" AND c.id IN ({marks})"
                where += f" AND c.id IN ({marks})"
                args += ids
                count_args += ids
            out["total"] = int(c.execute(where, count_args).fetchone()[0])
            rows = c.execute(sql + " ORDER BY COALESCE(c.started, c.updated), c.id LIMIT ?",
                             args + [max(0, int(limit))]).fetchall()
        if not rows:
            return out
        try:
            aead = self._cipher()
        except KeyUnavailable as exc:
            out["why_not"] = str(exc)
            return out
        except Exception as exc:
            out["why_not"] = f"the chat history could not be opened ({type(exc).__name__})"
            return out
        nc = len(CONV_COLS)
        for r in rows:
            cv = _conv_named(r)
            cid, title, started, updated = cv["id"], cv["title"], cv["started"], cv["updated"]
            kind, tid = cv["kind"], cv["tag_id"]
            n, inside, first, last = r[nc:nc + 4]
            first = first if first is not None else started
            last = last if last is not None else updated
            out["items"].append({
                "id": cid, "title": self._title(aead, cid, title),
                "started": float(started or first or 0), "updated": float(updated or last or 0),
                "turns": int(n), "in_frame": int(inside),
                "kind": kind if kind in KINDS else "chat", "tag_id": _tag_id(tid),
                "spills": bool((first is not None and first < start)
                               or (last is not None and last >= end))})
        return out

    def take_out(self, cids) -> dict:
        """Deletes these conversations from the file - secure_delete and the
        usual VACUUM, as delete() does - and returns them, sealed as they
        were, for put_back(): {cid: {"conversation": row, "turns": [rows]}}.
        An id that is not there is skipped. The caller keeps what comes back
        in memory only, for the 10-minute Undo."""
        held = {}
        if not self.db_path.exists():
            return held
        with self._lock, closing(self._connect()) as c:
            with c:
                for cid in cids:
                    if not (isinstance(cid, str) and _CID.fullmatch(cid)):
                        continue
                    conv = c.execute(f"SELECT {_conv_cols(raw=True)} FROM conversations"
                                     " WHERE id=?", (cid,)).fetchone()
                    if conv is None:
                        continue
                    turns = c.execute(f"SELECT {self._TURN_COLS} FROM turns"
                                      " WHERE conversation_id=? ORDER BY idx", (cid,)).fetchall()
                    held[cid] = {"conversation": tuple(conv), "turns": [tuple(t) for t in turns]}
                    hush = c.execute("SELECT v FROM meta WHERE k=?",
                                     (self._hush_key(cid),)).fetchone()
                    if hush is not None:
                        held[cid]["hush"] = bytes(hush[0])
                    self._drop(c, [cid])
        if held:
            self._deleted()
        return held

    def put_back(self, held: dict) -> dict:
        """Undo for take_out(): {"restored": [cid], "failed": {cid: why}}.

        A conversation the owner went on with after it was deleted (the app
        still had it open, so a new message made it again) is joined back
        together: the old messages first, the new ones after them. The new
        ones are re-sealed at their new places, which needs the key; without
        it that one conversation is not put back, and `failed` says why."""
        out = {"restored": [], "failed": {}}
        if not isinstance(held, dict) or not held:
            return out
        with self._lock, closing(self._connect()) as c:
            for cid, h in held.items():
                try:
                    with c:
                        self._put_one(c, cid, h)
                        self._drop_unknown_tag(c, cid)
                    out["restored"].append(cid)
                except KeyUnavailable as exc:
                    out["failed"][cid] = str(exc)
                except Exception as exc:
                    out["failed"][cid] = f"it could not be written back ({type(exc).__name__})"
        return out

    def _put_one(self, c, cid: str, h: dict) -> None:
        conv = h["conversation"]
        turns = h["turns"]
        if isinstance(h.get("hush"), (bytes, bytearray)):
            # "Already learned from before a Forget" goes back with the chat.
            c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)",
                      (self._hush_key(cid), bytes(h["hush"])))
        marks = ",".join("?" * 11)
        now_conv = c.execute("SELECT updated FROM conversations WHERE id=?", (cid,)).fetchone()
        if now_conv is None:
            n = len(CONV_COLS)
            conv = tuple(conv) + (None,) * (n - len(conv))    # held before kind/tag existed
            c.execute("INSERT INTO conversations (%s) VALUES (%s)"
                      % (", ".join(CONV_COLS), ",".join("?" * n)), conv[:n])
            for t in turns:
                c.execute(f"INSERT INTO turns ({self._TURN_COLS}) VALUES ({marks})", t)
            return
        aead = self._cipher()
        newer = c.execute(f"SELECT {self._TURN_COLS} FROM turns WHERE conversation_id=?"
                          " ORDER BY idx", (cid,)).fetchall()
        c.execute("DELETE FROM turns WHERE conversation_id=?", (cid,))
        for t in turns:
            c.execute(f"INSERT INTO turns ({self._TURN_COLS}) VALUES ({marks})", t)
        nxt = (max((t[1] for t in turns), default=-1)) + 1
        # Only messages said AFTER the ones held: anything at or before the
        # last held one is already among them - a copy put back by other
        # means in the meantime (restoring a backup, say) - and would
        # otherwise appear twice.
        last_held = max((float(t[2] or 0) for t in turns), default=0.0)
        newer = [t for t in newer if float(t[2] or 0) > last_held]
        for t in newer:
            plain = self._open(aead, t[10], self._aad(cid, t[1]))
            row = list(t)
            row[1] = nxt
            row[10] = self._seal(aead, plain, self._aad(cid, nxt))
            c.execute(f"INSERT INTO turns ({self._TURN_COLS}) VALUES ({marks})", row)
            nxt += 1
        # The old title and first moment; the newer last moment stays.
        c.execute("UPDATE conversations SET title=?, started=? WHERE id=?",
                  (conv[CONV_COLS.index("title")], conv[CONV_COLS.index("started")], cid))
        # The tag it had, unless the owner filed it somewhere since.
        held_tag = conv[CONV_COLS.index("tag_id")] if len(conv) > CONV_COLS.index("tag_id") \
            else None
        if held_tag is not None:
            c.execute("UPDATE conversations SET tag_id=? WHERE id=? AND tag_id IS NULL",
                      (held_tag, cid))


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


def note_hush(conversation_id, erased: bool = False) -> None:
    _log().note_hush(conversation_id, erased)


def hush_floor(conversation_id) -> Optional[dict]:
    return _log().hush_floor(conversation_id)


def live_upto(conversation_id) -> Optional[int]:
    return _log().live_upto(conversation_id)


def live_turn_any(text) -> Optional[dict]:
    """live_turn() in any conversation: the newest entry for these words."""
    return _log().live_turn_any(text)


def conversation_tainted(conversation_id, messages=None) -> bool:
    """For jarvis_agent: has an earlier turn of this conversation read
    outside text? `messages`: the request's, as they arrived. Fails closed
    for a conversation this process has not met (G1)."""
    return _log().conversation_tainted(conversation_id, messages)


def delete(conversation_id) -> bool:
    """One conversation, gone for good. True if there was one to delete.

    The same call `/api/history/delete` makes (`handle_post`, above) and
    what "Erase the words" + "Also delete the chat it came from" makes
    (`jarvis_memory.py` `erase()`, the owner's decision, 2026-09-27) - one
    module function, so both callers delete a conversation the same way."""
    return _log().delete(conversation_id)


def record_support(cid, title, rows) -> dict:
    """A finished customer-support chat (jarvis_support.py), kept encrypted
    as its own conversation - see ChatLog.record_support."""
    return _log().record_support(cid, title, rows)


def record_chatbot(cid, title, rows, *, kind: str = "chatbot") -> dict:
    """A finished chatbot conversation or comparison (jarvis_chatbot.py,
    jarvis_chatbot_compare.py), kept encrypted as its own conversation of
    kind "chatbot" or "compare" - see ChatLog.record_chatbot."""
    return _log().record_chatbot(cid, title, rows, kind=kind)


def status() -> dict:
    return _log().status()


def brief(conversation_id) -> Optional[dict]:
    """One conversation's title, kind and last change - see ChatLog.brief."""
    return _log().brief(conversation_id)


def overlapping(start: float, end: float, limit: int = 201, only=None) -> dict:
    """"Forget a time frame" (jarvis_forget_range.py): the conversations in
    a time frame, with their titles. See ChatLog.overlapping."""
    return _log().overlapping(start, end, limit, only)


def take_out(cids) -> dict:
    """"Forget a time frame", after its ONE approval card: these
    conversations deleted from the file, and handed back sealed, for the
    10-minute Undo. See ChatLog.take_out."""
    return _log().take_out(cids)


def put_back(held: dict) -> dict:
    """The Undo of take_out(). See ChatLog.put_back."""
    return _log().put_back(held)


def tags() -> dict:
    """GET /api/history/tags's answer (ChatLog.tags)."""
    return _log().tags()


def tag_chat(cid, tag_id) -> tuple:
    """POST /api/history/tag: (http code, answer). See ChatLog.set_tag. The
    same call "label this chat Work" makes (jarvis_quick.py)."""
    return _log().set_tag(cid, tag_id)


def search(query, limit=SEARCH_DEFAULT, kind=None) -> dict:
    """GET /api/history/search's answer (ChatLog.search). For the apps'
    History screens only: nothing a model or a chat turn can call reaches
    this (docs/JARVIS-API.md section 71)."""
    return _log().search(query, limit=limit, kind=kind)


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


#: Said with every "Delete conversations older than" choice, in both apps'
#: confirm: customer-support records are never deleted by it.
SUPPORT_KEPT_NOTE = ("Customer-support chat records are not deleted by this - delete one "
                     "yourself in History if you want it gone.")


def support_kept_words(n: int) -> str:
    """After a keep_days change, when support records older than it were
    kept back (ChatLog.sweep)."""
    return (f" {n} customer-support chat record{' was' if n == 1 else 's were'} older than "
            "that and kept - delete one yourself in History if you want it gone.")


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
        try:
            held = log.support_past_keep()
        except Exception:
            held = 0
        out = log.status()
        out.update(ok=True, deleted=deleted, support_kept=held,
                   message=_keep_words(value) + (
                       f" {deleted} conversation{'' if deleted == 1 else 's'} "
                       f"{'was' if deleted == 1 else 'were'} deleted now." if deleted
                       else " None were deleted now.") + (support_kept_words(held)
                                                           if held else ""))
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


#: GET /api/history/search (section 71). jarvis_brain_reads.py answers it;
#: chat-history.patch's own dispatch in jarvis_hud.py never sees it.
SEARCH_PATH = "/api/history/search"


def handle_get(path: str, query: str = "") -> tuple:
    """GET /api/history, /api/history/conversation, /api/history/search and
    /api/history/tags. (code, body)."""
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
        return 200, log.list(limit=limit, before=before, kind=q.get("kind") or None,
                             tag=q.get("tag") or None)
    if path == "/api/history/tags":
        return 200, log.tags()
    if path == SEARCH_PATH:
        # "Search what was said" (section 71). The words arrive in ?q=, are
        # used for this one scan and dropped: never logged, never audited,
        # never kept. A too-short or too-long search is a 200 with
        # query_ok false and a sentence, not an error.
        try:
            limit = int(q.get("limit", SEARCH_DEFAULT))
        except (TypeError, ValueError):
            limit = SEARCH_DEFAULT
        return 200, log.search(q.get("q", ""), limit=limit, kind=q.get("kind") or None)
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
    """POST /api/history/delete, /settings, /tags and /tag. (code, body)."""
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
    if route == "/api/history/tags":
        # Chat tags (section 99): the owner's own organisation, no card.
        return _log().tag_op(body)
    if route == "/api/history/tag":
        if not isinstance(body, dict) or set(body) != {"id", "tag_id"}:
            return 400, _tag_fail("bad_request")
        return _log().set_tag(body["id"], body["tag_id"])
    return 404, {"error": "no such route"}
