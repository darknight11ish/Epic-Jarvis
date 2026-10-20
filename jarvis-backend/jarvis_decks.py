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
  * New cards a day: 5 by default (0-20), set in the app. A run shows at most
    20 cards, then the app says it is enough for now; "more" adds 10. That 20
    is a default the settings file can change ([decks] run_limit, below).
  * A card can be rated only after its back was shown in this run.

THE ONE SCHEDULER KIND
`review` (plain_repeat, silent, single, no notification, no card): created with
the first deck, removed with the last. It goes off once a day at 04:00 only to
tell the apps the list changed. Its `note` is the "N cards ready" line.

SLICE 22A: THE VOICE COACH (2026-10-17)
The backend half of the hands-free review, and nothing more: no route, no app
screen, no model call. `grade_spoken_answer()` turns a transcribed spoken
answer into one of the four ratings with plain code - case, punctuation and
fillers aside, then key-token recall and difflib's ratio - so a misheard grade
is a fixed rule, never a model's guess. `low_retrievability_topics()` reads
py-fsrs's own retrievability to name the decks whose cards are fading.
`record_voice_review()` is rate() with one extra thing: it writes a receipt
through jarvis_receipts.py before the row changes, so a misheard grade is one
Undo away. A spoken answer is never marked Easy by code (the grader tops out
at Good): Easy stretches the next interval the most, and speech-to-text is not
certain enough to make that call for the owner.

SLICE 22B: THE PHONE SURFACE (2026-10-17)
Additive fields only - this slice adds no route. GET /api/decks carries the
radar rows in its own "radar" key (`low_retrievability_topics()`'s shapes), and
POST /api/review/reveal takes an optional typed `answer` and answers with the
grader's own "grade" dict in the same reply. Both are extra keys an older app
ignores, and nothing else changes. The spelling of the four PC sentences is in
GRADE_WORDS, one source for both apps' fixtures. The spoken path stays
unbuilt: a phone must not do speech-to-text, and the review is typed only, so
record_voice_review()'s receipt still has no route either.
"""
from __future__ import annotations

import difflib
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
#: How many cards one run shows before the app says it is enough for now
#: (RUN_MORE is what "Do 10 more" adds on top). The number is a DEFAULT, not
#: the only number: _run_limit() reads jarvis-framework.toml's [decks]
#: run_limit and falls back to this one when the key is absent, unreadable or
#: outside RUN_LIMIT_MIN..RUN_LIMIT_MAX - so a settings writer can change it
#: without an edit here, and a nonsense value can never mean "ask no cards".
RUN_LIMIT, RUN_MORE, RUN_IDLE = 20, 10, 30 * 60.0
RUN_LIMIT_MIN, RUN_LIMIT_MAX = 1, MAX_CARDS
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
#   The voice coach: a spoken answer graded by code, and the fading cards
# --------------------------------------------------------------------------
#
# Slice 22A of the voice flashcard coach is these functions and the receipt at
# the end of the file - no route, no app screen, no model call, no new module.
# The review maths stays py-fsrs's; this section only reads it.

#: A reviewed card is worth another look when its memory strength is below this.
LOW_RETRIEVABILITY = 0.75
#: The two lines grade_spoken_answer() puts a spoken answer on. A score exactly
#: on a line belongs to the better mark (>=, not >), and both are N_placeholder:
#: a real calibration would move them on a measured set of answers.
GOOD_AT, HARD_AT = 0.85, 0.50
#: Filled pauses and articles: they are said, not remembered, so they never
#: count toward an answer.
_FILLERS = frozenset(("a", "an", "the", "uh", "um"))
#: What the owner says instead of an answer. "I don't know" is a real signal
#: (bring the card back soon), not a wrong answer to be guessed at - so all of
#: these mean Again, without any comparison.
PASS_PHRASES = frozenset(("i don't know", "i dont know", "skip", "pass", "no idea"))
#: The receipt's name for a voice grade. jarvis_receipts.py treats it as a
#: name, never a path and never importable code.
VOICE_TOOL = "decks.voice_review"
#: The four ratings as the apps label them (the words CLASSES.bad_rating uses).
RATING_WORDS = {"again": "Didn't remember", "hard": "Remembered with effort",
                "good": "Remembered", "easy": "Easy"}
#: The PC's own sentences for one graded answer (slice 22B, 2026-10-17). They
#: live here rather than in an app, because they are the PC's words:
#: grade_spoken_answer() returns one of these four and no app copies one.
GRADE_WORDS = {
    "Good": "That matches the answer - marked Good.",
    "Hard": "That answer is partly right - marked Hard.",
    "Again": "Marked Again so it comes back soon.",
    "no_answer": "There is no answer to compare with, so it is marked Again.",
}

#: A word of an answer: lower case, digits and the apostrophe only, so "don't"
#: does not become "dont" and a number is not dropped as punctuation.
_WORD = re.compile(r"[a-z0-9']+")


def _spoken_tokens(text) -> list:
    """The words that count in a spoken answer. Nothing is guessed: casefold,
    the two typographic apostrophes folded to a plain one, punctuation dropped,
    and the filler words removed."""
    if not isinstance(text, str):
        return []
    flat = text.casefold().replace("\u2019", "'").replace("\u2018", "'")
    return [w for w in _WORD.findall(flat) if w not in _FILLERS]


def _spoken_score(expected: list, spoken: list) -> float:
    """How close one spoken answer is to the card's back, from 0.0 to 1.0.

    Two readings, averaged: how much of the answer's own words were said at
    all (key-token recall), and how closely the two read in the same order
    (difflib's ratio). A paraphrase cannot pass on order alone, and a word
    salad cannot pass on vocabulary alone."""
    if not expected:
        return 0.0
    ratio = difflib.SequenceMatcher(None, " ".join(expected), " ".join(spoken),
                                    autojunk=False).ratio()
    heard = set(spoken)
    recall = sum(1 for word in expected if word in heard) / len(expected)
    return (ratio + recall) / 2.0


def _spoken_rating(score: float) -> tuple:
    """(rating, label, matched) for one score - the only place the two lines
    live, so a test can stand exactly on each of them."""
    if score >= GOOD_AT:
        return 3, "Good", True
    if score >= HARD_AT:
        return 2, "Hard", True
    return 1, "Again", False


def grade_spoken_answer(expected_back, spoken_answer) -> dict:
    """One spoken answer, marked by plain code - no model, no network, no clock.

    Returns {"rating", "label", "matched", "words"}: the four ratings are the
    app's own (1 Again, 2 Hard, 3 Good, 4 Easy); a spoken answer never gets 4
    Easy by code, because Easy stretches the next interval the most and
    speech-to-text is not certain enough to make that call for the owner.

    An empty answer, a filled pause, or one of PASS_PHRASES is Again at once:
    "I don't know" is information, not a wrong answer. Otherwise a score is
    the average of key-token recall and difflib's ratio: >= GOOD_AT is Good,
    >= HARD_AT is Hard (matched), and below HARD_AT is Again (not matched).
    Deterministic: the same two strings always give the same answer."""
    expected = _spoken_tokens(expected_back)
    spoken = _spoken_tokens(spoken_answer)
    said = " ".join(spoken)
    if not expected:
        return {"rating": 1, "label": "Again", "matched": False,
                "words": GRADE_WORDS["no_answer"]}
    if not said or said in PASS_PHRASES:
        return {"rating": 1, "label": "Again", "matched": False,
                "words": GRADE_WORDS["Again"]}
    rating, label, matched = _spoken_rating(_spoken_score(expected, spoken))
    words = GRADE_WORDS[label]
    return {"rating": rating, "label": label, "matched": matched, "words": words}


def _retrievability(card, now: float):
    """py-fsrs's retrievability for one card AT `now` (seconds since 1970, UTC).

    The caller has already resolved the clock; this reads no clock itself.
    None when the card has never been rated - a new card has no memory
    strength to predict - and for a stability that is not a positive number."""
    if not isinstance(card, dict):
        raise TypeError("a card is a dict")
    stability, last = card.get("stability"), card.get("last_review")
    if stability is None or last is None:
        return None
    try:
        s, t = float(stability), float(last)
    except (TypeError, ValueError):
        return None
    if not s > 0:                       # also None for a NaN stability
        return None
    sch = _scheduler(False)             # raises deck_unavailable, in plain words
    probe = fsrs.Card(card_id=1, stability=s, last_review=_dt(t))
    return float(sch.get_card_retrievability(probe, _dt(now)))


def retrievability(card, *, now=None):
    """How likely the owner is to remember this card now, 0.0 to 1.0.

    py-fsrs 6.3.2's own number, from the card's stability and the whole days
    since its last review. `now` is the boundary: tests pass a fixed epoch and
    nothing inside reads the clock again; with no `now`, the real clock is read
    exactly once here. None for a card never rated (there is nothing to
    predict yet)."""
    at = time.time() if now is None else float(now)
    return _retrievability(card, at)


def _radar_add(groups: dict, topic: str, card, cut: float, now: float) -> None:
    """One card into one topic's numbers. A never-rated card is not counted."""
    r = _retrievability(card, now)
    if r is None:
        return
    group = groups.get(topic)
    if group is None:
        group = groups[topic] = {"topic": topic, "cards": 0, "below": 0, "lowest": 1.0}
    group["cards"] += 1
    if r < cut:
        group["below"] += 1
        if r < group["lowest"]:
            group["lowest"] = r


def _radar_words(topic: str, below: int, threshold: float) -> str:
    """The one plain sentence for a topic, from its numbers only."""
    cards = "1 card" if below == 1 else f"{below} cards"
    verb = "has" if below == 1 else "have"
    return (f"{cards} in {topic} {verb} dropped below "
            f"{threshold * 100:.6g}% memory strength")


def low_retrievability_topics(decks_or_cards, *, threshold: float = LOW_RETRIEVABILITY,
                              now=None) -> list:
    """The decks/topics whose reviewed cards are fading, weakest first.

    `decks_or_cards` is one deck, one card, or a list of either. A DECK is
    {"name": ..., "cards": [...]}; a CARD carries py-fsrs's plain numbers
    ({"deck" or "topic": ..., "stability": ..., "last_review": ...}). Cards
    never rated are not counted: no stability means there is nothing to
    predict yet.

    Returns one dict per topic with at least one reviewed card below the
    threshold, sorted by that topic's lowest retrievability first:
    {"topic", "cards" (reviewed cards in it), "below" (cards under the line),
    "lowest" (0.0..1.0), "words" (one plain-English sentence)}.

    `threshold` is a memory strength from 0 to 1. `now` is the boundary: tests
    pass a fixed epoch, and it is read once here, so every card is measured at
    the same moment and nothing flakes at midnight."""
    at = time.time() if now is None else float(now)
    try:
        cut = float(threshold)
    except (TypeError, ValueError):
        raise ValueError("the threshold is a memory strength from 0 to 1")
    if not 0.0 <= cut <= 1.0:
        raise ValueError("the threshold is a memory strength from 0 to 1")
    if isinstance(decks_or_cards, dict):
        items = [decks_or_cards]
    elif isinstance(decks_or_cards, (list, tuple)):
        items = decks_or_cards
    else:
        raise TypeError("decks_or_cards is a deck, a card, or a list of them")
    groups: dict = {}
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("a deck or a card is a dict")
        cards = item.get("cards")
        if isinstance(cards, (list, tuple)):
            topic = str(item.get("name") or item.get("deck") or item.get("topic")
                        or "an unnamed deck")
            for card in cards:
                _radar_add(groups, topic, card, cut, at)
        else:
            topic = str(item.get("deck") or item.get("topic") or item.get("deck_name")
                        or "an unnamed deck")
            _radar_add(groups, topic, item, cut, at)
    out = [group for group in groups.values() if group["below"]]
    out.sort(key=lambda group: (group["lowest"], -group["below"],
                                group["topic"].casefold(), group["topic"]))
    for group in out:
        group["words"] = _radar_words(group["topic"], group["below"], cut)
    return out


# --------------------------------------------------------------------------
#   Small helpers
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def _cfg(key: str, default):
    """One number from jarvis-framework.toml's [decks] table, or `default`.

    The same shape jarvis_jobs._cfg uses: no framework module - this file also
    runs beside a test harness that has none - or a settings file that will
    not read, gives the default rather than an exception. Nothing here is
    required for a deck to work: every number it reads has one already."""
    try:
        return fw.load_framework().get("decks", {}).get(key, default)
    except Exception:
        return default


def _int_cfg(key: str, default: int, lo: int, hi: int) -> int:
    """One whole number from the settings file, inside lo..hi, else `default`.

    The shape jarvis_big_model._int_cfg uses. A value that is not a number, or
    that is outside the range - 0 would ask for no cards at all - is the
    default, so a typo in the settings file can never silently stop a review
    or ask for a thousand cards in one sitting."""
    try:
        v = int(_cfg(key, default))
    except (TypeError, ValueError):
        return default
    return v if lo <= v <= hi else default


def _run_limit() -> int:
    """How many cards this run shows: RUN_LIMIT, or the owner's own number."""
    return _int_cfg("run_limit", RUN_LIMIT, RUN_LIMIT_MIN, RUN_LIMIT_MAX)


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
        c = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
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
                "next_ready_day": None, "line": "", "radar": [],
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
        if out:
            try:
                base["radar"] = self.radar()
            except DeckError:
                base["radar"] = []          # the deck list must never fail because of the radar
        return base

    def radar(self, *, now=None) -> list:
        """The fading-deck rows under the deck list (slice 22B, 2026-10-17).

        `low_retrievability_topics()`'s own rows, weakest first: one per deck
        with a reviewed card below LOW_RETRIEVABILITY, carrying {"topic",
        "cards", "below", "lowest", "words"}. The topic is the deck's name, so
        an app must withhold it under "Hide memory lists and chat history" as
        it withholds the deck list. The numbers are plain columns, so no key is
        needed to count; only the names are opened. A pause is respected: a
        paused deck is left out, as its cards are left out of the review queue.
        A deck whose name cannot be opened is left out rather than hiding the
        rest. `now` is the boundary: tests pass a fixed clock, and with None
        the clock is read once here."""
        at = self._clock() if now is None else float(now)
        with self._lock:
            if not self._exists():
                return []
            with closing(self._connect()) as c:
                decks = c.execute("SELECT id, name, paused FROM decks ORDER BY rowid").fetchall()
                cards = c.execute("SELECT deck_id, stability, last_review FROM cards"
                                  " WHERE last_review IS NOT NULL"
                                  " AND stability IS NOT NULL ORDER BY rowid").fetchall()
            if not decks or not cards:
                return []
            aead = self._cipher()
            by_deck: dict = {}
            for did, stability, last in cards:
                by_deck.setdefault(did, []).append({"stability": stability,
                                                    "last_review": last})
            items = []
            for did, name, paused in decks:
                if paused:               # a paused deck is resting, not fading
                    continue
                mine = by_deck.get(did)
                if not mine:             # nothing rated here: no memory strength to predict
                    continue
                try:
                    topic = self._unseal(aead, name, f"deck|{did}|name")
                except DeckError:
                    continue             # one unreadable name must not hide the rest
                for card in mine:
                    card["deck"] = topic
                items.extend(mine)
        return low_retrievability_topics(items, now=at)

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
            r = self._runs[scope] = {"scope": scope, "done": 0, "cap": _run_limit(), "day": today,
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
                        "card": None, "line": "", "run": {"done": 0, "limit": _run_limit()}}
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

    def reveal(self, cid, answer=None) -> dict:
        """Show one card's back; with a typed `answer`, mark it in the same read.

        The extra "grade" key (slice 22B, 2026-10-17) is
        grade_spoken_answer()'s own dict for the card's back against the typed
        words - the app's "Mark my answer" button sends it. It is additive: a
        caller that sends no answer (every older app) gets exactly the reply it
        always got, and no rating is applied here - the owner still chooses one
        of the four buttons. `answer` that is not a non-blank string is ignored
        rather than failing the reveal."""
        with self._lock:
            if not isinstance(cid, str) or not self._exists():
                raise DeckError("card_not_found")
            with closing(self._connect()) as c:
                row, _n = self._up_for_review(c, cid)
                aead = self._cipher()
                back = self._unseal(aead, row[3], f"card|{cid}|back")
                out = {"ok": True,
                       "back": {"answer": back,
                                "passage": self._unseal(aead, row[4], f"card|{cid}|passage")},
                       "key_label": KEY_LABEL if row[7] == "model" else None}
                if isinstance(answer, str) and answer.strip():
                    out["grade"] = grade_spoken_answer(back, answer)
            now = self._clock()
            self._revealed = {k: v for k, v in self._revealed.items() if now - v < REVEAL_KEEP}
            self._revealed[cid] = now
            return out

    def _rating_plan(self, c, cid: str, rating: str) -> tuple:
        """The checks and the py-fsrs maths one rating makes, from one read.

        rate() and record_voice_review() share this, so a voice grade's receipt
        records exactly the row that is then written: the numbers are computed
        ONCE and used by the UPDATE. Recomputing for the receipt would let
        fuzzing give the snapshot a different due date from the row."""
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
        return row, before, after, now

    def _apply_rating(self, c, cid: str, rating: str, row, after: dict) -> int:
        """Write one rating's numbers into the row, and forget the reveal.

        Returns the lapse this rating added (1 or 0), so a receipt can record
        the same number the row gets."""
        lapse = 1 if (rating == "again" and row[8] == 2) else 0
        c.execute("UPDATE cards SET state=?, step=?, stability=?, difficulty=?, due=?,"
                  " last_review=?, reps=reps+1, lapses=lapses+?,"
                  " first_day=COALESCE(first_day, ?) WHERE id=?",
                  (after["state"], after["step"], after["stability"], after["difficulty"],
                   after["due"], after["last_review"], lapse, self._today(), cid))
        self._revealed.pop(cid, None)
        return lapse

    def _rated_view(self, c, row, deck) -> dict:
        """Which run counted the rating, then the same review answer rate()
        has always returned."""
        if isinstance(deck, str) and deck in ("", row[1]):
            scope = deck
        else:       # an old app that sends none: the newest run this card belongs to
            live = [(v["at"], k) for k, v in self._runs.items() if k in ("", row[1])]
            scope = max(live)[1] if live else ""
        scope = scope or None
        run = self._scope_run(scope)
        run["done"] += 1
        return self._review_view(c, scope)

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
                row, _before, after, _now = self._rating_plan(c, cid, rating)
                self._apply_rating(c, cid, rating, row, after)
                view = self._rated_view(c, row, deck)
            return {"ok": True, "ready": view["ready"], "new_left": view["new_left"],
                    "next": view["card"], "state": view["state"], "line": view["line"],
                    "run": view["run"], "comes_back": _day(after["due"])}

    def record_voice_review(self, cid, rating, *, deck=None, grade=None) -> dict:
        """Rate a card from a spoken answer, and leave an Undo receipt for it.

        The rating is applied exactly as rate() applies it - the same checks
        (the card is up for review, its deck is not paused, and its answer was
        shown this run) and the same py-fsrs maths. Before the row changes, one
        receipt is written through jarvis_receipts.py holding the card's plain
        numbers before AND after, with the live undo callable, so a misheard
        grade is one Undo away. No word of the deck, the card or the spoken
        answer is written in the receipt; the snapshots are numbers only.

        `grade` is optional: grade_spoken_answer()'s dict, used only for the
        receipt's plain-English summary. "record_voice_review" never fails the
        review because receipts are missing: it returns "receipt_id": "" then,
        exactly as jarvis_goals.py does for a tick.

        Returns rate()'s answer plus "receipt_id" and "undoable"."""
        if rating not in RATINGS:
            raise DeckError("bad_rating")
        with self._lock:
            if not isinstance(cid, str) or not self._exists():
                raise DeckError("card_not_found")
            with closing(self._connect()) as c:
                row, before, after, now = self._rating_plan(c, cid, rating)
                counts = c.execute("SELECT reps, lapses, first_day FROM cards WHERE id=?",
                                   (cid,)).fetchone()
                lapse = 1 if (rating == "again" and row[8] == 2) else 0
                before = dict(before, card=cid, deck=row[1], reps=counts[0],
                              lapses=counts[1], first_day=counts[2])
                after = dict(after, card=cid, deck=row[1], reps=counts[0] + 1,
                             lapses=counts[1] + lapse,
                             first_day=counts[2] or self._today(), reviewed_at=now)
                receipt_id = _record_voice_receipt(rating, before, after, grade)
                self._apply_rating(c, cid, rating, row, after)
                view = self._rated_view(c, row, deck)
            return {"ok": True, "ready": view["ready"], "new_left": view["new_left"],
                    "next": view["card"], "state": view["state"], "line": view["line"],
                    "run": view["run"], "comes_back": _day(after["due"]),
                    "receipt_id": receipt_id, "undoable": bool(receipt_id)}

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
#   The receipt: one voice grade, put back in one tap
# --------------------------------------------------------------------------
# A voice grade changes the same row a tap does, but a misheard word is easier
# to miss than a wrong tap - so record_voice_review() writes a receipt through
# jarvis_receipts.py BEFORE the row changes, and Undo puts the schedule back
# exactly as it was. It is optional: a backend folder that has not installed
# jarvis_receipts.py still reviews, it just cannot undo; nothing here may raise
# into the review. The shape is jarvis_goals.py's (the module that first
# recorded a receipt for an everyday action).

def restore_card_state(snapshot) -> None:
    """Put one card's review schedule back exactly as a receipt's before
    snapshot has it.

    This is the SNAPSHOT path: jarvis_receipts.py calls it after a restart,
    when the live undo callable is gone by definition. It needs only the
    numbers - never the card's words and never the key - and it writes through
    this module's own db_path(), so JARVIS_STUDY_DB is honoured. Raises on a
    snapshot it cannot use; the caller reports that in plain words and changes
    nothing."""
    if not isinstance(snapshot, dict):
        raise ValueError("this is not a study card receipt snapshot")
    card_id = str(snapshot.get("card") or "")
    columns = ("state", "step", "stability", "difficulty", "due", "last_review",
               "reps", "lapses", "first_day")
    if not card_id or any(column not in snapshot for column in columns):
        raise ValueError("this study card receipt snapshot has no card or schedule")
    store = Decks()                     # the default path: no key is needed for numbers
    if not store.path.is_file():
        raise KeyError("no such card")
    with store._lock, closing(store._connect()) as c:
        if c.execute("SELECT 1 FROM cards WHERE id=?", (card_id,)).fetchone() is None:
            raise KeyError("no such card")
        c.execute("UPDATE cards SET state=?, step=?, stability=?, difficulty=?, due=?,"
                  " last_review=?, reps=?, lapses=?, first_day=? WHERE id=?",
                  (snapshot["state"], snapshot["step"], snapshot["stability"],
                   snapshot["difficulty"], snapshot["due"], snapshot["last_review"],
                   snapshot["reps"], snapshot["lapses"], snapshot["first_day"], card_id))


def register_receipts() -> bool:
    """Tell jarvis_receipts.py how a voice grade is put back from its snapshot.

    Called once at import, below: a restorer only exists in a process whose
    module was imported, and jarvis_receipts deliberately keeps no list of its
    own. False (never an exception) when jarvis_receipts is not installed."""
    try:
        import jarvis_receipts
        return bool(jarvis_receipts.register_restorer(VOICE_TOOL, restore_card_state))
    except Exception:
        return False


def _record_voice_receipt(rating, before: dict, after: dict, grade=None) -> str:
    """One receipt for one voice grade, or "" - never an exception into the review.

    The summary is plain words and names no card: the snapshots hold py-fsrs's
    numbers only, so the receipt is one more place a deck's owner words are
    not written. `grade` is the grader's dict, when there is one, only to say
    in the summary that what was heard did not match."""
    try:
        import jarvis_receipts
    except Exception:
        return ""
    try:
        summary = f"Rated a card by voice: {RATING_WORDS.get(rating, rating)}"
        if isinstance(grade, dict) and grade.get("matched") is False:
            summary += " (the spoken answer did not match)"
        return jarvis_receipts.record(VOICE_TOOL, summary, before=before, after=after,
                                      undo=lambda: restore_card_state(before))
    except Exception:
        return ""


register_receipts()


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
            return 200, d.reveal(body.get("card"), body.get("answer"))
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
