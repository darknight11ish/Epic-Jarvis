"""jarvis_decks.py - review decks (the owner's decision of 2026-09-30;
docs/QUIZ-DECKS-DESIGN.md, JARVIS-API section 102).

NEW MODULE, shipped whole. decks.patch installs the routes (one block in
jarvis_hud.py); jarvis_schedule.py imports this file before its loop first
runs (KIND_MODULES) so the one scheduler kind, `review`, is known.

WHAT IT IS FOR, IN PLAIN WORDS
After a quiz the owner may keep some of its questions in a DECK. A deck's cards
come back on a spaced schedule so the owner can study them again. The owner
rates each card themselves (Didn't remember / Remembered, with effort /
Remembered / Easy); the schedule maths is py-fsrs (MIT, pinned in
requirements.txt, WITHOUT its optimizer extra, which needs torch). Reviewing
calls no model at all.

WHERE THE WORDS ARE KEPT
`study.db` beside schedule.db and goals.db, but not in either. The words - a
deck's name, a card's front, back and source passage - are sealed one by one
with AES-256-GCM, the same scheme chat history uses (a 12-byte nonce, then the
ciphertext, the row's address as the authenticated data), under a key of their
OWN in Windows Credential Manager ("Jarvis Backend/study decks key"), so
deleting this key never touches chat history. No key, no `cryptography`, or a
key that does not open the file: nothing is kept and the error says why - there
is no plain-text path. In plain columns only: ids, the card's kind, the Spanish
level tag, the paused flag, the day it was made, and py-fsrs's numbers. So the
"N cards ready" line needs no key. The file is in the locked backup (owner,
2026-09-30): jarvis_backup.py carries this key beside it, and a restore calls
forget_key() so the running store reopens. No review log is kept (py-fsrs makes one per
rating; only its optimizer reads them). PRAGMA secure_delete is on, and a
deleted card or deck is followed by a VACUUM.

THE RULES IT KEEPS
  * Nothing in a deck is memory, a fact, chat history or context. It is never
    read into the learner, the model, a search or a cloud lane. This module
    imports none of those.
  * No model-callable tool and no voice command makes a deck or a card: only
    an app's tap does (the routes below).
  * No streaks, no guilt words, no points. A day with nothing ready is neutral.
  * Numbers come from code: counts, days, intervals.
  * New cards a day: 5 by default (0-20). A run shows at most 20 cards, then
    the app says it is enough for now; "more" adds 10.
  * A card can be rated only after its back was shown in this run.

THE ONE SCHEDULER KIND
`review` (plain_repeat, silent, single, no notification, no card): created with
the first deck, removed with the last. It goes off once a day at 04:00 only to
tell the apps the list changed. Its `note` is the "N cards ready" line.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover
    AESGCM = None  # type: ignore
    InvalidTag = Exception  # type: ignore

try:
    import fsrs
except Exception:  # pragma: no cover - nothing can be rated without it
    fsrs = None  # type: ignore

# --------------------------------------------------------------------------
#   Numbers and words
# --------------------------------------------------------------------------

#: Where the key is filed in Credential Manager (its own entry).
KEY_TARGET = "Jarvis Backend/study decks key"
_CHECK = b"jarvis study decks"

MAX_DECKS = 20
MAX_CARDS = 1000                  # in all, across every deck
NAME_MAX = 60
FRONT_MAX, BACK_MAX, PASSAGE_MAX = 500, 2000, 800
NEW_PER_DAY_DEFAULT, NEW_PER_DAY_MAX = 5, 20
RUN_LIMIT, RUN_MORE, RUN_IDLE = 20, 10, 30 * 60.0
REVEAL_KEEP = 6 * 3600.0
DESIRED_RETENTION = 0.90
RATINGS = ("again", "hard", "good", "easy")

KIND = "review"
NOUN = "card review"
LOCK_SCREEN = "Jarvis: cards are ready."
JOB_RULE = {"every": "day", "at": "04:00"}

KEY_LABEL = "Answer key written by the model"

CLASSES = {
    "deck_unavailable": (503, "Review decks cannot be used right now. Nothing was kept."),
    "deck_not_found": (404, "That deck is not there any more."),
    "card_not_found": (404, "That card is not up for review right now."),
    "too_many_decks": (409, "There are already 20 decks. Delete one first."),
    "deck_full": (409, "The decks hold 1,000 cards in all, which is the most. "
                       "Delete some cards first."),
    "bad_deck_name": (400, "A deck's name is 1 to 60 characters."),
    "duplicate_card": (409, "That question is already in the deck."),
    "nothing_to_keep": (400, "Tick at least one question to keep."),
    "not_revealed": (409, "Show the answer first, then rate the card."),
    "deck_paused": (409, "That deck is paused. Resume it to review its cards."),
    "bad_rating": (400, "Pick Didn't remember, Remembered with effort, Remembered or Easy."),
    "bad_setting": (400, "New cards a day is a whole number from 0 to 20."),
    "bad_action": (400, "That is not something a deck or card can do."),
    "bad_card": (400, "A card's front is 1 to 500 characters and its back at most 2,000."),
}


class DeckError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code = code
        self.status = CLASSES[code][0]
        self.message = message or CLASSES[code][1]


def err_body(exc: DeckError) -> tuple:
    return exc.status, {"ok": False, "error": exc.code, "message": exc.message}


# --------------------------------------------------------------------------
#   The schedule maths (py-fsrs, the library's own numbers)
# --------------------------------------------------------------------------
#
# No learning steps and no relearning steps: a card rated "Didn't remember"
# comes back the next day, not ten minutes later (one calm pass a day). Desired
# retention is fixed at 0.90. Fuzzing (a little random spread of long
# intervals) is on in real use and off in tests.

_SCHED_CACHE: dict = {}


def _scheduler(fuzz: bool):
    if fsrs is None:
        raise DeckError("deck_unavailable", "The review schedule (py-fsrs) is not installed "
                        "on this PC. Install it with: py -3 -m pip install -r "
                        "backend\\requirements.txt")
    s = _SCHED_CACHE.get(fuzz)
    if s is None:
        s = fsrs.Scheduler(desired_retention=DESIRED_RETENTION, learning_steps=(),
                           relearning_steps=(), enable_fuzzing=bool(fuzz))
        _SCHED_CACHE[fuzz] = s
    return s


def new_state(now: float) -> dict:
    """A card nobody has rated yet, in py-fsrs's terms."""
    return {"state": 1, "step": 0, "stability": None, "difficulty": None,
            "due": float(now), "last_review": None}


def _calendar_due(now: float, due: float) -> float:
    """py-fsrs counts a day as 24 hours. This PC's days are calendar days (23 or
    25 hours twice a year), so a whole-day wait is added to the local date and
    time instead: "3 days" from 23:30 on the evening before the clocks go
    forward still lands on the third calendar day."""
    days = (due - now) / 86400.0
    n = round(days)
    if n < 1 or abs(days - n) > 0.02:
        return due
    return (datetime.fromtimestamp(now) + timedelta(days=n)).timestamp()


def _tomorrow(t: float) -> str:
    return (datetime.fromtimestamp(t) + timedelta(days=1)).strftime("%Y-%m-%d")


def _dt(t):
    return None if t is None else datetime.fromtimestamp(float(t), timezone.utc)


def review(state: dict, rating: str, now: float, fuzz: bool = True) -> dict:
    """The card's numbers after one rating at `now` (seconds since 1970, UTC).
    `state` and the answer are plain dicts: state (1 learning, 2 review, 3
    relearning), step, stability, difficulty, due, last_review."""
    if rating not in RATINGS:
        raise DeckError("bad_rating")
    sch = _scheduler(fuzz)
    card = fsrs.Card(card_id=1, state=fsrs.State(int(state["state"])), step=state.get("step"),
                     stability=state.get("stability"), difficulty=state.get("difficulty"),
                     due=_dt(state["due"]), last_review=_dt(state.get("last_review")))
    rate = {"again": fsrs.Rating.Again, "hard": fsrs.Rating.Hard, "good": fsrs.Rating.Good,
            "easy": fsrs.Rating.Easy}[rating]
    out, _log = sch.review_card(card, rate, _dt(now))
    return {"state": int(out.state.value), "step": out.step, "stability": out.stability,
            "difficulty": out.difficulty, "due": _calendar_due(now, out.due.timestamp()),
            "last_review": out.last_review.timestamp() if out.last_review else None}


# --------------------------------------------------------------------------
#   Small helpers
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def db_path() -> Path:
    env = os.environ.get("JARVIS_STUDY_DB")
    return Path(env) if env else _config_dir() / "study.db"


def _default_provider() -> bytes:
    """The key from Credential Manager, through the same helper chat history
    uses, filed under this module's own name."""
    from jarvis_chat_log import CredentialKey
    return CredentialKey(KEY_TARGET)()


def _day(t: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _clean(s, limit: int) -> str:
    return re.sub(r"\s+", " ", s).strip()[:limit] if isinstance(s, str) else ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def cards_words(n: int) -> str:
    return f"{n} card ready" if n == 1 else f"{n} cards ready"


def line_for(decks: int, ready: int, all_paused: bool) -> str:
    """The one plain line, from numbers only. No deck means no line."""
    if decks == 0:
        return ""
    if ready > 0:
        return cards_words(ready)
    if all_paused:
        return "All decks paused"
    return "Nothing ready today"


def _seal(aead, text: str, aad: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + aead.encrypt(nonce, text.encode("utf-8"), aad.encode("utf-8"))


def _open(aead, blob, aad: str) -> str:
    blob = bytes(blob)
    return aead.decrypt(blob[:12], blob[12:], aad.encode("utf-8")).decode("utf-8")


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v BLOB)",
    "CREATE TABLE IF NOT EXISTS decks (id TEXT PRIMARY KEY, name BLOB NOT NULL,"
    " paused INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cards (id TEXT PRIMARY KEY, deck_id TEXT NOT NULL,"
    " front BLOB NOT NULL, back BLOB NOT NULL, passage BLOB NOT NULL, kind TEXT,"
    " level TEXT, key_source TEXT, state INTEGER NOT NULL, step INTEGER,"
    " stability REAL, difficulty REAL, due REAL NOT NULL, last_review REAL,"
    " reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,"
    " first_day TEXT, created TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS cards_deck ON cards (deck_id)",
)


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

class Decks:
    """One study database. The module keeps one (get()); tests make their own
    with a temporary file, a key provider, a clock and a scheduler of their own."""

    def __init__(self, path=None, key_provider: Optional[Callable[[], bytes]] = None, *,
                 clock: Callable[[], float] = time.time, scheduler=None, fuzz: bool = True,
                 crypto: bool = True):
        self.path = Path(path) if path else db_path()
        self._provider = key_provider or _default_provider
        self._clock = clock
        self._scheduler = scheduler
        self.fuzz = fuzz
        self._crypto = crypto and AESGCM is not None
        self._lock = threading.RLock()
        self._aead = None
        self._revealed: dict = {}     # card id -> when its back was shown
        self._runs: dict = {}         # scope ("" = all decks, else a deck id) -> its run

    # ---- plumbing ---------------------------------------------------------

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(self.path), timeout=5.0, isolation_level=None)
        c.execute("PRAGMA secure_delete = ON")
        for stmt in _SCHEMA:
            c.execute(stmt)
        return c

    def _exists(self) -> bool:
        return self.path.is_file()

    def _today(self) -> str:
        return _day(self._clock())

    def _cipher(self):
        with self._lock:
            if self._aead is not None:
                return self._aead
            if not self._crypto:
                raise DeckError("deck_unavailable",
                                "The encryption package (cryptography) is not installed on "
                                "this PC, so no deck is kept. Install it with: py -3 -m pip "
                                "install -r backend\\requirements.txt")
            try:
                key = self._provider()
            except DeckError:
                raise
            except Exception as exc:
                why = str(exc) if type(exc).__name__ == "KeyUnavailable" \
                    else f"({type(exc).__name__})"
                raise DeckError("deck_unavailable",
                                f"The study decks' key could not be had: {why}. Nothing was kept.")
            if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
                raise DeckError("deck_unavailable", "The study decks' key is not a 32-byte key. "
                                "Nothing was kept.")
            aead = AESGCM(bytes(key))
            with closing(self._connect()) as c:
                row = c.execute("SELECT v FROM meta WHERE k='check'").fetchone()
                if row is None:
                    c.execute("INSERT INTO meta (k, v) VALUES ('check', ?)",
                              (_seal(aead, _CHECK.decode(), "check"),))
                else:
                    try:
                        ok = _open(aead, row[0], "check").encode() == _CHECK
                    except Exception:
                        ok = False
                    if not ok:
                        raise DeckError(
                            "deck_unavailable",
                            "The key in Credential Manager does not open the study decks kept "
                            "on this PC (it was replaced or deleted), so nothing new is kept. "
                            f"To start again with no decks, stop Jarvis and delete {self.path}")
            self._aead = aead
            return aead

    def _unseal(self, aead, blob, aad: str) -> str:
        try:
            return _open(aead, blob, aad)
        except InvalidTag:
            raise DeckError("deck_unavailable", "A deck could not be opened with this key, so it "
                            "is not shown.")
        except Exception:
            raise DeckError("deck_unavailable", "A deck could not be opened, so it is not shown.")

    def _need_fsrs(self) -> None:
        if fsrs is None:
            _scheduler(self.fuzz)      # raises deck_unavailable, in plain words

    def available(self) -> tuple:
        """(True, "") or (False, why in plain words). Never makes a key by
        itself when there is nothing to open."""
        if fsrs is None:
            try:
                _scheduler(self.fuzz)
            except DeckError as exc:
                return False, exc.message
        if not self._crypto:
            try:
                self._cipher()
            except DeckError as exc:
                return False, exc.message
            return False, "Review decks cannot be used right now."
        if not self._exists():
            return True, ""
        try:
            with closing(self._connect()) as c:
                have = c.execute("SELECT 1 FROM decks LIMIT 1").fetchone() is not None
            if have:
                self._cipher()
        except DeckError as exc:
            return False, exc.message
        except Exception as exc:
            return False, f"The study decks file could not be read ({type(exc).__name__})."
        return True, ""

    def _vacuum(self) -> None:
        try:
            with closing(self._connect()) as c:
                c.execute("VACUUM")
        except Exception:
            pass

    # ---- reading the plain numbers (no key needed) -------------------------

    def _rows(self, c) -> tuple:
        decks = c.execute("SELECT id, paused FROM decks ORDER BY rowid").fetchall()
        cards = c.execute("SELECT id, deck_id, last_review, due, first_day, kind, level"
                          " FROM cards ORDER BY rowid").fetchall()
        return decks, cards

    def _new_per_day(self, c) -> int:
        row = c.execute("SELECT v FROM meta WHERE k='new_per_day'").fetchone()
        try:
            n = int(row[0]) if row is not None else NEW_PER_DAY_DEFAULT
        except (TypeError, ValueError):
            n = NEW_PER_DAY_DEFAULT
        return n if 0 <= n <= NEW_PER_DAY_MAX else NEW_PER_DAY_DEFAULT

    def _numbers(self, c, deck: Optional[str] = None) -> dict:
        """Everything the counts need, from the plain columns only."""
        today = self._today()
        decks, cards = self._rows(c)
        paused = {d[0]: bool(d[1]) for d in decks}
        cap = self._new_per_day(c)
        introduced = sum(1 for r in cards if r[4] == today)
        new_left = max(0, cap - introduced)
        reviews, news, later = [], [], []
        for cid, did, last, due, first_day, kind, level in cards:
            if paused.get(did, True):
                continue
            if last is None:
                news.append((did, cid))
            elif _day(due) <= today:
                reviews.append((due, did, cid))
            else:
                later.append(_day(due))
        reviews.sort(key=lambda r: r[0])
        # The day's allowance of new cards is shared by every deck (it is counted
        # from what was learned today), but what a view offers is worked out for
        # the deck asked about: its own reviews, then its own new cards up to it.
        def offered(scope_deck):
            mine = [r for r in reviews if scope_deck is None or r[1] == scope_deck]
            fresh = [x for x in news if scope_deck is None or x[0] == scope_deck][:new_left]
            return mine, fresh

        def ids(pair):
            return [r[2] for r in pair[0]] + [x[1] for x in pair[1]]
        per_deck = {did: len(ids(offered(did))) for did in paused}
        queue = ids(offered(deck))
        every = offered(None)
        # A card is up for review if its own deck would offer it (the deck
        # asked about, or all decks together).
        up = set()
        for did in paused:
            up.update(ids(offered(did)))
        # More new cards than today's allowance: the rest wait for tomorrow. With
        # an allowance of 0 they are not promised at all.
        if cap > 0 and len(news) > len(every[1]):
            later.append(_tomorrow(self._clock()))
        return {"decks": paused, "cards": cards, "per_deck": per_deck, "queue": queue,
                "total": len(ids(every)), "up": up, "new_left": new_left, "new_per_day": cap,
                "next_day": min(later) if later else None,
                "all_paused": bool(paused) and all(paused.values())}

    def line(self) -> str:
        """The scheduler note: from numbers only, so it needs no key."""
        try:
            if not self._exists():
                return ""
            with closing(self._connect()) as c:
                n = self._numbers(c)
            return line_for(len(n["decks"]), n["total"], n["all_paused"])
        except Exception:
            return ""

    def deck_count(self) -> int:
        if not self._exists():
            return 0
        with closing(self._connect()) as c:
            return c.execute("SELECT COUNT(*) FROM decks").fetchone()[0]

    # ---- the deck list ------------------------------------------------------

    @staticmethod
    def _kind_of(cards_of_deck: list) -> str:
        if not cards_of_deck:
            return "empty"
        spanish = sum(1 for r in cards_of_deck if r[6])
        return "spanish" if spanish == len(cards_of_deck) else "study" if spanish == 0 else "mixed"

    def list_decks(self) -> dict:
        ok, why = self.available()
        base = {"ok": True, "available": ok, "why": why, "decks": [], "ready": 0,
                "new_per_day": NEW_PER_DAY_DEFAULT, "new_left": NEW_PER_DAY_DEFAULT,
                "next_ready_day": None, "line": "",
                "limits": {"decks": MAX_DECKS, "cards": MAX_CARDS, "name": NAME_MAX,
                           "front": FRONT_MAX, "back": BACK_MAX,
                           "new_per_day": NEW_PER_DAY_MAX}}
        if not self._exists():
            return base
        with self._lock, closing(self._connect()) as c:
            n = self._numbers(c)
            base.update(ready=n["total"], new_per_day=n["new_per_day"],
                        new_left=n["new_left"], next_ready_day=n["next_day"],
                        line=line_for(len(n["decks"]), n["total"], n["all_paused"]))
            if not ok:
                return base
            aead = self._cipher() if n["decks"] else None
            out = []
            for did, paused in n["decks"].items():
                row = c.execute("SELECT name FROM decks WHERE id=?", (did,)).fetchone()
                mine = [r for r in n["cards"] if r[1] == did]
                out.append({"id": did, "name": self._unseal(aead, row[0], f"deck|{did}|name"),
                            "cards": len(mine), "ready": n["per_deck"].get(did, 0),
                            "paused": bool(paused), "kind": self._kind_of(mine)})
            base["decks"] = out
        return base

    def _deck_view(self, c, did: str) -> dict:
        n = self._numbers(c)
        row = c.execute("SELECT name FROM decks WHERE id=?", (did,)).fetchone()
        if row is None:
            raise DeckError("deck_not_found")
        aead = self._cipher()
        mine = [r for r in n["cards"] if r[1] == did]
        return {"id": did, "name": self._unseal(aead, row[0], f"deck|{did}|name"),
                "cards": len(mine), "ready": n["per_deck"].get(did, 0),
                "paused": bool(n["decks"][did]), "kind": self._kind_of(mine)}

    # ---- making, renaming, pausing, deleting ---------------------------------

    def _name(self, name) -> str:
        n = _clean(name, NAME_MAX + 1)
        if not n or len(n) > NAME_MAX:
            raise DeckError("bad_deck_name")
        return n

    def _new_deck(self, c, aead, name: str) -> str:
        if c.execute("SELECT COUNT(*) FROM decks").fetchone()[0] >= MAX_DECKS:
            raise DeckError("too_many_decks")
        did = "d" + secrets.token_hex(6)
        c.execute("INSERT INTO decks (id, name, paused, created) VALUES (?,?,0,?)",
                  (did, _seal(aead, name, f"deck|{did}|name"), self._today()))
        return did

    def create_deck(self, name) -> dict:
        name = self._name(name)
        self._need_fsrs()
        with self._lock:
            aead = self._cipher()
            with closing(self._connect()) as c:
                did = self._new_deck(c, aead, name)
                view = self._deck_view(c, did)
        self.ensure_job()
        return view

    def deck_act(self, did: str, do, name=None) -> dict:
        do = str(do or "").strip().lower()
        if do not in ("rename", "pause", "resume", "delete"):
            raise DeckError("bad_action")
        with self._lock:
            if not self._exists():
                raise DeckError("deck_not_found")
            with closing(self._connect()) as c:
                if c.execute("SELECT 1 FROM decks WHERE id=?", (did,)).fetchone() is None:
                    raise DeckError("deck_not_found")
                if do == "rename":
                    aead = self._cipher()
                    c.execute("UPDATE decks SET name=? WHERE id=?",
                              (_seal(aead, self._name(name), f"deck|{did}|name"), did))
                elif do in ("pause", "resume"):
                    c.execute("UPDATE decks SET paused=? WHERE id=?", (1 if do == "pause" else 0, did))
                else:
                    ids = [r[0] for r in c.execute("SELECT id FROM cards WHERE deck_id=?", (did,))]
                    c.execute("BEGIN IMMEDIATE")
                    c.execute("DELETE FROM cards WHERE deck_id=?", (did,))
                    c.execute("DELETE FROM decks WHERE id=?", (did,))
                    c.execute("COMMIT")
                    for cid in ids:
                        self._revealed.pop(cid, None)
            if do == "delete":
                self._vacuum()
                self.ensure_job()
                return {"ok": True, "deleted": True}
            with closing(self._connect()) as c:
                return {"ok": True, "deck": self._deck_view(c, did)}

    def set_new_per_day(self, n) -> dict:
        if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= NEW_PER_DAY_MAX:
            raise DeckError("bad_setting")
        with self._lock, closing(self._connect()) as c:
            c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('new_per_day', ?)", (str(n),))
        return {"ok": True, "new_per_day": n}

    # ---- the cards ------------------------------------------------------------

    def _card_row(self, c, cid: str):
        return c.execute("SELECT id, deck_id, front, back, passage, kind, level, key_source,"
                         " state, step, stability, difficulty, due, last_review, first_day"
                         " FROM cards WHERE id=?", (cid,)).fetchone()

    def deck_cards(self, did: str) -> dict:
        with self._lock:
            if not self._exists():
                raise DeckError("deck_not_found")
            with closing(self._connect()) as c:
                d = c.execute("SELECT name FROM decks WHERE id=?", (did,)).fetchone()
                if d is None:
                    raise DeckError("deck_not_found")
                aead = self._cipher()
                out = []
                for r in c.execute("SELECT id FROM cards WHERE deck_id=? ORDER BY rowid", (did,)).fetchall():
                    row = self._card_row(c, r[0])
                    out.append(self._card_full(aead, row))
                return {"ok": True, "deck": {"id": did, "name": self._unseal(aead, d[0], f"deck|{did}|name")},
                        "cards": out}

    def _card_full(self, aead, row) -> dict:
        cid = row[0]
        return {"id": cid, "front": self._unseal(aead, row[2], f"card|{cid}|front"),
                "back": self._unseal(aead, row[3], f"card|{cid}|back"),
                "passage": self._unseal(aead, row[4], f"card|{cid}|passage"),
                "kind": row[5] or "", "level": row[6] or None,
                "key_source": row[7] or None,
                "key_label": KEY_LABEL if row[7] == "model" else None,
                "new": row[13] is None, "due_day": None if row[13] is None else _day(row[12])}

    def card_act(self, did: str, cid: str, do, front=None, back=None) -> dict:
        do = str(do or "").strip().lower()
        if do not in ("edit", "delete"):
            raise DeckError("bad_action")
        with self._lock:
            if not self._exists():
                raise DeckError("card_not_found")
            with closing(self._connect()) as c:
                row = self._card_row(c, cid)
                if row is None or row[1] != did:
                    raise DeckError("card_not_found", "That card is not in this deck any more.")
                if do == "delete":
                    c.execute("DELETE FROM cards WHERE id=?", (cid,))
                    self._revealed.pop(cid, None)
                else:
                    aead = self._cipher()
                    if front is None and back is None:
                        raise DeckError("bad_card")
                    if front is not None:
                        f = front.strip() if isinstance(front, str) else ""
                        if not f or len(f) > FRONT_MAX:
                            raise DeckError("bad_card")
                        # the same duplicate check as keeping: no two cards in a
                        # deck with the same question over the same passage
                        mine = (_norm(f), _norm(self._unseal(aead, row[4], f"card|{cid}|passage")))
                        for r in c.execute("SELECT id, front, passage FROM cards"
                                           " WHERE deck_id=? AND id<>?", (did, cid)).fetchall():
                            if mine == (_norm(self._unseal(aead, r[1], f"card|{r[0]}|front")),
                                        _norm(self._unseal(aead, r[2], f"card|{r[0]}|passage"))):
                                raise DeckError("duplicate_card")
                        c.execute("UPDATE cards SET front=? WHERE id=?",
                                  (_seal(aead, f, f"card|{cid}|front"), cid))
                    if back is not None:
                        b = back.strip() if isinstance(back, str) else None
                        if b is None or len(b) > BACK_MAX:
                            raise DeckError("bad_card")
                        c.execute("UPDATE cards SET back=? WHERE id=?",
                                  (_seal(aead, b, f"card|{cid}|back"), cid))
            if do == "delete":
                self._vacuum()
                return {"ok": True, "deleted": True}
            with closing(self._connect()) as c:
                return {"ok": True, "card": self._card_full(self._cipher(), self._card_row(c, cid))}

    # ---- keeping questions from a quiz (all or nothing) ---------------------------

    def keep(self, spec: dict, cards: list) -> int:
        """Called by jarvis_quiz.finish (injected). `cards` come from the
        quiz's own questions: front, back, passage, kind, level, key_source.
        One transaction: a card that does not fit means none is kept."""
        if not cards:
            raise DeckError("nothing_to_keep")
        self._need_fsrs()
        with self._lock:
            aead = self._cipher()
            now = self._clock()
            with closing(self._connect()) as c:
                c.execute("BEGIN IMMEDIATE")
                try:
                    did = (spec or {}).get("deck")
                    if did:
                        if c.execute("SELECT 1 FROM decks WHERE id=?", (did,)).fetchone() is None:
                            raise DeckError("deck_not_found")
                    elif (spec or {}).get("new_deck") is not None:
                        did = self._new_deck(c, aead, self._name(spec["new_deck"]))
                    else:
                        raise DeckError("deck_not_found", "Choose a deck to keep them in, or name a new one.")
                    if c.execute("SELECT COUNT(*) FROM cards").fetchone()[0] + len(cards) > MAX_CARDS:
                        raise DeckError("deck_full")
                    have = set()
                    for r in c.execute("SELECT id, front, passage FROM cards WHERE deck_id=?", (did,)):
                        have.add((_norm(self._unseal(aead, r[1], f"card|{r[0]}|front")),
                                  _norm(self._unseal(aead, r[2], f"card|{r[0]}|passage"))))
                    for i, k in enumerate(cards):
                        front = _clean(k.get("front"), FRONT_MAX)
                        back = (k.get("back") or "").strip()[:BACK_MAX]
                        passage = _clean(k.get("passage"), PASSAGE_MAX)
                        key = (_norm(front), _norm(passage))
                        if not front:
                            raise DeckError("bad_card")
                        if key in have:
                            raise DeckError("duplicate_card",
                                            f"Question {k.get('n', i + 1)} is already in that deck.")
                        have.add(key)
                        cid = "c" + secrets.token_hex(8)
                        st = new_state(now)
                        c.execute(
                            "INSERT INTO cards (id, deck_id, front, back, passage, kind, level,"
                            " key_source, state, step, stability, difficulty, due, last_review,"
                            " reps, lapses, first_day, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,NULL,?)",
                            (cid, did, _seal(aead, front, f"card|{cid}|front"),
                             _seal(aead, back, f"card|{cid}|back"),
                             _seal(aead, passage, f"card|{cid}|passage"),
                             str(k.get("kind") or "")[:20], str(k.get("level") or "")[:2] or None,
                             str(k.get("key_source") or "")[:8] or None, st["state"], st["step"],
                             None, None, st["due"], None, self._today()))
                    c.execute("COMMIT")
                except BaseException:
                    c.execute("ROLLBACK")
                    raise
        self.ensure_job()
        return len(cards)

    # ---- review -------------------------------------------------------------------

    def _scope_run(self, deck: Optional[str], *, fresh: bool = False) -> dict:
        """The run for one scope. Each scope ("" for all decks, or one deck) has
        its own, so two apps reviewing at once - one on a deck, one on all decks -
        never count each other's cards."""
        now, scope, today = self._clock(), deck or "", self._today()
        self._runs = {k: v for k, v in self._runs.items()
                      if v["day"] == today and now - v["at"] <= RUN_IDLE}
        r = self._runs.get(scope)
        if r is None or fresh:
            r = self._runs[scope] = {"scope": scope, "done": 0, "cap": RUN_LIMIT, "day": today,
                                     "at": now}
        r["at"] = now
        return r

    def _card_view(self, aead, c, cid: str, did: str) -> dict:
        row = self._card_row(c, cid)
        return {"id": cid, "front": self._unseal(aead, row[2], f"card|{cid}|front"),
                "kind": row[5] or "", "level": row[6] or None, "deck": did,
                "new": row[13] is None}

    def _review_view(self, c, deck: Optional[str]) -> dict:
        n = self._numbers(c, deck)
        if deck is not None and deck not in n["decks"]:
            raise DeckError("deck_not_found")
        run = self._scope_run(deck)
        ready = len(n["queue"])
        state, card = "card", None
        if not n["decks"]:
            state = "no_decks"
        elif deck is not None and n["decks"].get(deck):
            state = "paused"
        elif deck is None and n["all_paused"]:
            state = "paused"
        elif not n["queue"]:
            state = "empty"
        elif run["done"] >= run["cap"]:
            state = "enough"
        if state == "card":
            cid = n["queue"][0]
            card = self._card_view(self._cipher(), c, cid, self._card_row(c, cid)[1])
        scope_decks = 1 if deck is not None else len(n["decks"])
        line = line_for(scope_decks, ready, state == "paused")
        if deck is not None and state == "paused":
            line = "This deck is paused"
        return {"ready": ready, "new_left": n["new_left"], "state": state, "card": card,
                "line": line,
                "run": {"done": run["done"], "limit": run["cap"]}}

    def review_state(self, deck: Optional[str] = None) -> dict:
        with self._lock:
            if not self._exists():
                return {"ok": True, "ready": 0, "new_left": NEW_PER_DAY_DEFAULT, "state": "no_decks",
                        "card": None, "line": "", "run": {"done": 0, "limit": RUN_LIMIT}}
            with closing(self._connect()) as c:
                out = self._review_view(c, deck)
            out["ok"] = True
            return out

    def more(self, deck: Optional[str] = None) -> dict:
        """"Do 10 more": raise this run's limit by 10, then the same answer as
        review_state."""
        with self._lock:
            run = self._scope_run(deck)
            run["cap"] += RUN_MORE
        return self.review_state(deck)

    def _up_for_review(self, c, cid: str) -> tuple:
        row = self._card_row(c, cid)
        if row is None:
            raise DeckError("card_not_found")
        n = self._numbers(c)
        if n["decks"].get(row[1]):
            raise DeckError("deck_paused")
        if cid not in n["up"]:
            raise DeckError("card_not_found")
        return row, n

    def reveal(self, cid) -> dict:
        with self._lock:
            if not isinstance(cid, str) or not self._exists():
                raise DeckError("card_not_found")
            with closing(self._connect()) as c:
                row, _n = self._up_for_review(c, cid)
                aead = self._cipher()
                out = {"ok": True,
                       "back": {"answer": self._unseal(aead, row[3], f"card|{cid}|back"),
                                "passage": self._unseal(aead, row[4], f"card|{cid}|passage")},
                       "key_label": KEY_LABEL if row[7] == "model" else None}
            now = self._clock()
            self._revealed = {k: v for k, v in self._revealed.items() if now - v < REVEAL_KEEP}
            self._revealed[cid] = now
            return out

    def rate(self, cid, rating, deck=None) -> dict:
        """`deck` is the scope the app is reviewing ("" or None: all decks, else a
        deck id). If it is missing, or not one this card belongs to, the newest run
        the card belongs to counts it."""
        if rating not in RATINGS:
            raise DeckError("bad_rating")
        with self._lock:
            if not isinstance(cid, str) or not self._exists():
                raise DeckError("card_not_found")
            with closing(self._connect()) as c:
                row = self._card_row(c, cid)
                if row is None:
                    raise DeckError("card_not_found")
                if c.execute("SELECT paused FROM decks WHERE id=?", (row[1],)).fetchone()[0]:
                    raise DeckError("deck_paused")
                if cid not in self._revealed:
                    raise DeckError("not_revealed")
                now = self._clock()
                before = {"state": row[8], "step": row[9], "stability": row[10],
                          "difficulty": row[11], "due": row[12], "last_review": row[13]}
                after = review(before, rating, now, self.fuzz)
                lapse = 1 if (rating == "again" and row[8] == 2) else 0
                c.execute("UPDATE cards SET state=?, step=?, stability=?, difficulty=?, due=?,"
                          " last_review=?, reps=reps+1, lapses=lapses+?,"
                          " first_day=COALESCE(first_day, ?) WHERE id=?",
                          (after["state"], after["step"], after["stability"], after["difficulty"],
                           after["due"], after["last_review"], lapse, self._today(), cid))
                self._revealed.pop(cid, None)
                if isinstance(deck, str) and deck in ("", row[1]):
                    scope = deck
                else:       # an old app that sends none: the newest run this card belongs to
                    live = [(v["at"], k) for k, v in self._runs.items() if k in ("", row[1])]
                    scope = max(live)[1] if live else ""
                scope = scope or None
                run = self._scope_run(scope)
                run["done"] += 1
                view = self._review_view(c, scope)
            return {"ok": True, "ready": view["ready"], "new_left": view["new_left"],
                    "next": view["card"], "state": view["state"], "line": view["line"],
                    "run": view["run"], "comes_back": _day(after["due"])}

    # ---- the scheduler kind's one job -----------------------------------------------

    def ensure_job(self, sched=None) -> str:
        """Keep the scheduler in step with the decks: none, no job; one or more,
        exactly one quiet daily job. Returns "added", "kept", "removed" or ""."""
        try:
            if sched is None:
                sched = self._scheduler
            if sched is None:
                import jarvis_schedule
                sched = jarvis_schedule.get()
            have = sched.jobs_of(KIND)
            if self.deck_count() == 0:
                for jid in have:
                    sched.act(jid, "delete")
                return "removed" if have else ""
            if have:
                for jid in have[1:]:
                    sched.act(jid, "delete")
                return "kept"
            sched.add_repeat(KIND, dict(JOB_RULE), source="decks")
            return "added"
        except Exception:
            return ""


# --------------------------------------------------------------------------
#   The one this backend uses, and its scheduler wiring
# --------------------------------------------------------------------------

_ONE: Optional[Decks] = None
_ONE_LOCK = threading.Lock()


def get() -> Decks:
    global _ONE
    with _ONE_LOCK:
        if _ONE is None:
            _ONE = Decks()
        return _ONE


def _note(job_id: str) -> str:
    return get().line()


def _on_fire(job_id: str) -> None:
    try:
        get().ensure_job()
    except Exception:
        pass


#: How KIND is registered on the one scheduler. plain_repeat: no card (only the
#: owner's tap makes a deck, it only reminds and never acts); silent and not
#: notify: it rings nothing; single: one job however many decks.
KIND_OPTIONS = dict(has_text=False, plain_repeat=True, single=True, silent=True, notify=False,
                    owner_listed=True, repeatable=True)


def register() -> None:
    import jarvis_schedule as S
    S.register_kind(KIND, NOUN, LOCK_SCREEN, on_fire=_on_fire, note=_note, **KIND_OPTIONS)


try:
    import jarvis_schedule as _S
    register()
    _S.after_start(lambda: get().ensure_job())
except Exception:  # pragma: no cover - the scheduler ships beside it
    _S = None


# --------------------------------------------------------------------------
#   The routes both apps call
# --------------------------------------------------------------------------

PATH_DECKS = "/api/decks"
PATH_REVIEW = "/api/review"
_DECK_RX = re.compile(r"^/api/decks/([^/]+)(?:/(act|cards)|/cards/([^/]+)/act)$")


def owns(method: str, route: str) -> bool:
    if method == "GET":
        if route in (PATH_DECKS, PATH_REVIEW):
            return True
        m = _DECK_RX.match(route)
        return bool(m and m.group(2) == "cards")
    if route in (PATH_DECKS, PATH_DECKS + "/settings", PATH_REVIEW + "/reveal",
                 PATH_REVIEW + "/rate", PATH_REVIEW + "/more"):
        return True
    m = _DECK_RX.match(route)
    return bool(m and (m.group(2) == "act" or m.group(3)))


def handle_get(route: str, query: Optional[dict] = None):
    query = query or {}
    try:
        if route == PATH_DECKS:
            return 200, get().list_decks()
        if route == PATH_REVIEW:
            deck = (query.get("deck") or [None])[0] or None
            return 200, get().review_state(deck)
        m = _DECK_RX.match(route)
        if m and m.group(2) == "cards":
            return 200, get().deck_cards(m.group(1))
    except DeckError as e:
        return err_body(e)
    return None


def handle_post(route: str, body):
    if not isinstance(body, dict):
        body = {}
    d = get()
    try:
        if route == PATH_DECKS:
            return 200, {"ok": True, "deck": d.create_deck(body.get("name"))}
        if route == PATH_DECKS + "/settings":
            return 200, d.set_new_per_day(body.get("new_per_day"))
        if route == PATH_REVIEW + "/reveal":
            return 200, d.reveal(body.get("card"))
        if route == PATH_REVIEW + "/rate":
            return 200, d.rate(body.get("card"), body.get("rating"), body.get("deck"))
        if route == PATH_REVIEW + "/more":
            deck = body.get("deck")
            return 200, d.more(deck if isinstance(deck, str) and deck else None)
        m = _DECK_RX.match(route)
        if m and m.group(2) == "act":
            out = d.deck_act(m.group(1), body.get("do"), body.get("name"))
        elif m and m.group(3):
            out = d.card_act(m.group(1), m.group(3), body.get("do"), body.get("front"),
                             body.get("back"))
        else:
            return None
        return 200, out
    except DeckError as e:
        return err_body(e)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the deck and review routes
    are answered here, after the server's own origin and token checks (the
    shape jarvis_goals.install and jarvis_quiz.install use), and hand the quiz
    the function that keeps questions in a deck."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    try:
        import jarvis_quiz
        jarvis_quiz.configure(keep=lambda spec, cards: get().keep(spec, cards))
    except Exception:
        pass
    if getattr(post0, "_jarvis_decks", False):
        return "  decks      Review decks (already on)"

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

    def _split(self) -> tuple:
        u = urllib.parse.urlsplit(str(getattr(self, "path", "") or ""))
        return u.path.rstrip("/"), urllib.parse.parse_qs(u.query)

    def do_GET(self):
        route, query = _split(self)
        if not owns("GET", route):
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route, _query = _split(self)
        if not owns("POST", route):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_decks = True
    do_POST._jarvis_decks = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    try:
        ok, why = get().available()
        n = get().deck_count()
    except Exception as exc:
        return f"  decks      NOT ON ({type(exc).__name__}) - Review decks are off"
    return f"  decks      Review decks: {n} kept" + ("" if ok else f" (cannot be opened: {why})")


def forget_key() -> None:
    """Drop the key the running store holds, so its next use asks Credential
    Manager again (a restore from a backup just replaced the key and the file)."""
    with _ONE_LOCK:
        one = _ONE
    if one is not None:
        with one._lock:
            one._aead = None
            one._revealed.clear()
            one._runs.clear()


def _reset_for_tests() -> None:
    global _ONE
    with _ONE_LOCK:
        _ONE = None
    _SCHED_CACHE.clear()
