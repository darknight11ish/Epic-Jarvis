"""jarvis_backoff.py - when Jarvis may OFFER something on its own, and when
it must keep quiet. It never approves anything and never acts: it only
answers "may I ask the owner this now?".

NEW MODULE, shipped whole (briefing.patch).

WHAT IT IS FOR, IN PLAIN WORDS
Jarvis sometimes offers things nobody asked for: the once-a-day "overnight
memory tidying" card (rebuilt/jarvis_sleep.py) and the "save this routine as
a skill?" card (jarvis_skill_discovery.py). An assistant that keeps asking
the same question after being told no is a nag, and a nag gets switched
off. Three rules, the same for every offer:

  1. A few at most. No more than MAX_WAITING offers may be waiting for an
     answer at once. The next one waits its turn.
  2. Not while the owner is talking to Jarvis. No offer within
     QUIET_AFTER_CHAT seconds (two minutes) of the last chat message.
  3. A "no" is heard. Each "no" to an offer keeps that SAME offer quiet for
     1 day, then 7 days, then 30 days (SILENCE_DAYS; the 30 repeats). The
     offer is matched by a stable fingerprint of what it offers - never by
     its wording, so a reworded card is still the same offer. A "yes" wipes
     the count.

WHAT IT MUST NEVER DO
  * Approve, act, or change a tier. Nothing here calls the gate. It is
    consulted only by the code that would raise an OFFER, before it asks.
  * Block the owner's own requests. A "no" to "shall I tidy memory
    overnight?" does not stop the owner switching it on themselves, and a
    "no" to a skill offer does not stop them asking for that routine. No
    route, no fast-path answer and no tool the owner uses asks this module
    anything. A "no" is also never turned into a memory rule or a standing
    setting (Leon, whose design this follows, can save a declined offer as
    a remembered preference; that part was deliberately not taken).

WHAT IS KEPT, AND WHERE
`backoff.json` in the Jarvis settings folder (JARVIS_BACKOFF_FILE overrides
it, for the tests): for each offer that has been declined, its fingerprint
(a hash - no words), how many times it was declined, and until when it is
quiet. Nothing else. Which offers are waiting right now, and when the owner
last chatted, are kept in memory only: a restart forgets them, which can
only let one offer through a little early, never hide one for good.

A state file that cannot be read makes every offer wait (fails quiet), and
status() says so - the same choice jarvis_skill_discovery.py makes for its
own ledger.

WHERE THE DESIGN COMES FROM
Leon (leon-ai/leon, MIT), server/src/core/pulse-manager.ts, its pulse
manager's limits: MAX_PENDING_MATTERS, ACTIVE_CONVERSATION_GRACE_MS (two
minutes) and PULSE_DECLINE_COOLDOWN_MS (1, 7 and 30 days), with each
offer's suppression keyed by a sha256 fingerprint. The design is followed;
no code was copied. THIRD-PARTY-NOTICES.txt credits it.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

#: At most this many offers waiting for an answer at once ("a few"; Leon
#: allows six pending matters - Jarvis's offers are cards, so fewer).
MAX_WAITING = 3

#: No offer within this many seconds of the last chat message.
QUIET_AFTER_CHAT = 120.0

#: A declined offer is quiet for this many days: the first "no", the second,
#: and every one after that.
SILENCE_DAYS = (1, 7, 30)

#: An offer handed out and never answered stops counting as waiting after
#: this long, so a card nobody saw cannot hold the others back for ever.
WAITING_FOR = 24 * 3600.0

#: The most declined offers remembered. The oldest quiet-and-expired ones go
#: first; one still quiet is never dropped while an expired one could be.
MAX_KEPT = 64

REASONS = {
    "": "It may ask now.",
    "silenced": "You said no to this recently, so it waits before asking again.",
    "conversation": "You are talking to Jarvis, so it waits until you have finished.",
    "too_many": "Other offers are already waiting for an answer.",
    "waiting": "This one is already waiting for your answer.",
    "unreadable": "Jarvis could not read its own record of your answers, so it does "
                  "not offer anything until that file can be read.",
}


def fingerprint(kind: str, subject: str = "") -> str:
    """A stable id for an offer: WHAT is offered (`kind`, like
    "sleep_time_offer") and ABOUT WHAT (`subject`, like a routine's tool
    chain). Case and spacing do not count. Never its wording."""
    def norm(s) -> str:
        return " ".join(str(s or "").lower().split())
    return hashlib.sha256(f"{norm(kind)}|{norm(subject)}".encode("utf-8")).hexdigest()[:24]


def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def state_path() -> Path:
    env = os.environ.get("JARVIS_BACKOFF_FILE")
    return Path(env) if env else _config_dir() / "backoff.json"


class Unreadable(Exception):
    pass


class Backoff:
    """The three rules. `clock` and `path` are replaceable for the tests."""

    def __init__(self, path: Optional[Path] = None, *, clock: Callable[[], float] = time.time):
        self._path = Path(path) if path is not None else None
        self.now = clock
        self._lock = threading.RLock()
        self._last_chat: Optional[float] = None
        self._waiting: dict = {}          # fingerprint -> when it was handed out

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else state_path()

    # ---- the file ------------------------------------------------------------

    def _load(self) -> dict:
        p = self.path
        if not p.is_file():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            offers = data.get("offers") if isinstance(data, dict) else None
            if not isinstance(offers, dict):
                raise ValueError("no offers table")
        except Exception as exc:
            raise Unreadable(type(exc).__name__)
        out = {}
        for fp, row in offers.items():
            if isinstance(fp, str) and isinstance(row, dict):
                try:
                    out[fp] = {"declines": max(0, int(row.get("declines", 0))),
                               "until": float(row.get("until", 0.0)),
                               "last": float(row.get("last", 0.0))}
                except (TypeError, ValueError):
                    continue
        return out

    def _save(self, offers: dict) -> None:
        now = self.now()
        if len(offers) > MAX_KEPT:
            # Expired ones first, oldest first; a still-quiet offer is kept
            # whenever an expired one can go instead.
            order = sorted(offers.items(), key=lambda kv: (kv[1]["until"] > now, kv[1]["last"]))
            for fp, _ in order[:len(offers) - MAX_KEPT]:
                offers.pop(fp, None)
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "offers": offers}, indent=1), encoding="utf-8")
        os.replace(tmp, p)

    # ---- the conversation ------------------------------------------------------

    def note_conversation(self, at: Optional[float] = None) -> None:
        """A chat message arrived (the /api/chat route calls this, for every
        turn, typed or said). In memory only."""
        with self._lock:
            self._last_chat = self.now() if at is None else float(at)

    def quiet_for(self, now: Optional[float] = None) -> float:
        """Seconds until the conversation rule allows an offer (0: now)."""
        now = self.now() if now is None else now
        with self._lock:
            last = self._last_chat
        if last is None:
            return 0.0
        return max(0.0, QUIET_AFTER_CHAT - (now - last))

    # ---- the question ------------------------------------------------------------

    def _expire_waiting(self, now: float) -> None:
        for fp, at in list(self._waiting.items()):
            if now - at >= WAITING_FOR:
                self._waiting.pop(fp, None)

    def may_offer(self, fp: str, now: Optional[float] = None) -> tuple:
        """(True, "") when this offer may be made now; (False, reason) when
        not, with `reason` a key of REASONS. Asks nobody and changes nothing."""
        now = self.now() if now is None else now
        with self._lock:
            try:
                offers = self._load()
            except Unreadable:
                return False, "unreadable"
            row = offers.get(fp)
            if row is not None and row["until"] > now:
                return False, "silenced"
            if self.quiet_for(now) > 0:
                return False, "conversation"
            self._expire_waiting(now)
            if fp in self._waiting:
                return False, "waiting"
            if len(self._waiting) >= MAX_WAITING:
                return False, "too_many"
            return True, ""

    def opened(self, fp: str, now: Optional[float] = None) -> None:
        """The offer was handed to the owner and now waits for an answer."""
        with self._lock:
            self._waiting[fp] = self.now() if now is None else now

    def closed(self, fp: str) -> None:
        """The offer was answered (in any way), or withdrawn."""
        with self._lock:
            self._waiting.pop(fp, None)

    def declined(self, fp: str, now: Optional[float] = None) -> float:
        """The owner said no to this offer. Returns until when it is quiet:
        1 day after the first "no", 7 after the second, 30 after every one
        after that. Records a hash, a count and two dates - nothing else."""
        now = self.now() if now is None else now
        with self._lock:
            self._waiting.pop(fp, None)
            try:
                offers = self._load()
            except Unreadable:
                offers = {}     # a broken file is replaced by one that works
            row = offers.get(fp) or {"declines": 0, "until": 0.0, "last": 0.0}
            row["declines"] += 1
            days = SILENCE_DAYS[min(row["declines"], len(SILENCE_DAYS)) - 1]
            row["until"] = now + days * 86400.0
            row["last"] = now
            offers[fp] = row
            self._save(offers)
            return row["until"]

    def accepted(self, fp: str) -> None:
        """The owner said yes: the offer's "no"s are forgotten."""
        with self._lock:
            self._waiting.pop(fp, None)
            try:
                offers = self._load()
            except Unreadable:
                return
            if offers.pop(fp, None) is not None:
                self._save(offers)

    def status(self, now: Optional[float] = None) -> dict:
        """Counts only - there are no words to show."""
        now = self.now() if now is None else now
        with self._lock:
            self._expire_waiting(now)
            waiting = len(self._waiting)
            try:
                offers = self._load()
                readable = True
            except Unreadable:
                offers, readable = {}, False
        return {"readable": readable, "waiting": waiting, "max_waiting": MAX_WAITING,
                "quiet_for": round(self.quiet_for(now), 1),
                "silenced": sum(1 for r in offers.values() if r["until"] > now),
                "silence_days": list(SILENCE_DAYS), "quiet_after_chat": QUIET_AFTER_CHAT}


# --------------------------------------------------------------------------
#   The one this backend uses
# --------------------------------------------------------------------------

_ONE: Optional[Backoff] = None
_ONE_LOCK = threading.Lock()


def get() -> Backoff:
    global _ONE
    with _ONE_LOCK:
        if _ONE is None:
            _ONE = Backoff()
        return _ONE


def note_conversation() -> None:
    """For /api/chat. Never raises."""
    try:
        get().note_conversation()
    except Exception:
        pass
