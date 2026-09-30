"""jarvis_forget_range.py - "Forget a time frame": forget what Jarvis learned
and delete the chats from some days, after a checked list and ONE card.

NEW MODULE, shipped whole. forget-range.patch installs its routes
(docs/JARVIS-API.md section 64); jarvis_quick.py calls parse_phrase() and
quick_answer() for "forget what you learned last week".

THE OWNER'S DECISION (2026-09-28, CLAUDE.md)
The owner may ask, by voice or typing, to forget what Jarvis learned or said
in a time frame ("forget what you learned last week", "delete my chats from
1 to 15 September"). Nothing is removed at once: both apps show the exact
facts and chats from that time, each ticked; the owner can untick any; ONE
approval card listing every item is decided by tapping only - never by
voice. Approved, the facts are FORGOTTEN (retired, exactly as Forget does -
never erased) and the chats DELETED, with 10 minutes to Undo. Erasing a
fact's words for good stays the separate, per-fact "Erase the words". This
is the one exception to "irreversible bulk actions stay off the API"
(JARVIS-API section 18), made safe by the list, the card and the Undo.

WHICH FACTS, WHICH CHATS
  * Facts by when Jarvis SAVED them (the `created` date), never by their
    "true from" date: "I moved here in 2019", said today, was learned today.
    Only facts still in use - a forgotten or erased one has nothing left to
    forget.
  * Chats by when they happened. A conversation that OVERLAPS the days
    counts - one message inside is enough - and the WHOLE conversation is
    deleted; the list marks one that also has messages from outside the
    days (`spills`), so that is never a surprise.
  * Dates are the PC's own local time, and inclusive: "1 to 15 September"
    is from midnight at the start of the 1st to the end of the 15th. A
    frame may also carry a time of day ("this morning": midnight to 11:59
    am).
  * At most MAX_ITEMS (200) facts and chats together in one go. More than
    that and the list says how many and asks for fewer days - no list is
    sent, and nothing can be forgotten from it.

THE CARD
action `memory_forget_range`, tier "ask" only (anything else and the route
answers 503 - a line in the settings file can never become the owner's
yes), and never an "always allow": What asks first cannot loosen it
(jarvis_asks_first.HARD_LIMITS). Its text lists EVERY fact word for word and
every chat's title, with their dates (ARCHITECTURE section 3). The gate's
risk line calls it local and NOT reversible (after the 10 minutes the chats
are gone for good), so approving it is a risky approval: Windows Hello on
the PC, the screen lock on the phone. Nothing changes before a person
approves. A spoken "yes" approves nothing - there is no approving by voice
anywhere in Jarvis.

APPROVED
Each fact: jarvis_memory.retire(), the same call Forget makes - so it gets
the same "forgotten" mark (meta.forgotten_at), which is what keeps a
question about the past from bringing it back and, once the audit branch's
"a forgotten or erased fact is not learned again automatically" lands,
what stops the learner saving it again. Each chat: jarvis_chat_log.take_out()
- deleted from the history file at once (secure_delete, as a single delete
is), and held IN MEMORY ONLY, still sealed exactly as it was on disk, for
the Undo.

UNDO: ten minutes, one tap, no card
POST /api/memory/forget_range/undo puts it all back: the facts un-forgotten
(jarvis_memory.unforget - only a fact still exactly as this Forget left it;
one erased in the meantime stays erased) and the chats written back. No
card: it only restores what the owner had ten minutes ago. The hold ends
after UNDO_SECONDS (600) or when the backend stops, WHICHEVER COMES FIRST -
it is never written to disk, so a restart ends it by itself, and a timer
drops it at ten minutes. After that the chats are gone for good; the facts
stay forgotten, as after any Forget. One Undo window at a time: while one
is open, forgetting another time frame waits until it closes.

Standard library only. Nothing here sends anything anywhere.
"""
from __future__ import annotations

import calendar
import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

ACTION = "memory_forget_range"
ROUTE = "/api/memory/forget_range"
PREVIEW = ROUTE + "/preview"
UNDO = ROUTE + "/undo"
ROUTES = (ROUTE, PREVIEW, UNDO)

#: Facts and chats together, in one list and on one card.
MAX_ITEMS = 200
#: How long Undo lasts after the card is approved.
UNDO_SECONDS = 600
UNDO_MINUTES = UNDO_SECONDS // 60
#: How long a spoken or typed request stays filled in for the apps.
ASKED_SECONDS = 1800
KINDS = ("facts", "chats")

#: The quick choices both apps offer, in this order, and their names.
PRESETS = (
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("this_week", "This week"),
    ("last_week", "Last week"),
    ("last_7_days", "The last 7 days"),
    ("this_month", "This month"),
    ("last_month", "Last month"),
)

# --------------------------------------------------------------------------
#   The words both apps show (tools/gen_forget_range_cases.py writes them
#   into the contract file each app's tests read)
# --------------------------------------------------------------------------

WORDS = {
    "title": "Forget a time frame",
    "under": ("Choose some days. Jarvis lists what it learned and your chats from then - "
              "untick anything you want to keep, then tap Forget these. Nothing is removed "
              "until you approve the card, and for 10 minutes one tap on Undo puts it all "
              "back."),
    "from": "From",
    "to": "To",
    "date_hint": "A date like 2026-09-01",
    "custom": "Choose the dates",
    "kinds": "What to look for",
    "kind_facts": "What Jarvis learned",
    "kind_chats": "Chats",
    "show": "Show the list",
    "facts_head": "What Jarvis learned then",
    "chats_head": "Chats from then",
    "forget": "Forget these",
    "none_ticked": "Tick at least one thing to forget.",
    "waiting": "Waiting for your yes on the approval card. Nothing is removed until you "
               "approve it - saying yes out loud does not.",
    "undo": "Undo",
    "undo_left": "{minutes} min left to undo",
    "spills": "Also has messages from outside these days. Tick it only if the whole chat should go.",
    # The owner, 2026-09-28 ("Chats, after the chat audit"): "Forget a time
    # frame" asks before removing a customer-support chat's record. The
    # simplest honest way: it is listed like every chat, but NOT ticked to
    # start with - it goes only if the owner ticks it, and the card names it.
    "support": "A customer-support chat record - kept unless you tick it.",
    "kind_live": "Live",
    "kind_support": "Support chat",
    "kind_chatbot": "Chat with an AI",
    "kind_compare": "Comparison",
    "erase_note": ("Facts are forgotten, as Forget does: they stop being used and stay in the "
                   "history. To wipe a fact's words for good, use Erase the words on that "
                   "fact."),
    "pinned": "Always kept in mind",
    "between_us": "Between us",
    "asked": "You asked Jarvis to forget {said}. Check the list below.",
    "stale": "The connection to Jarvis is catching up, so nothing can be sent until it does.",
    "missing": "Your PC's Jarvis cannot forget a time frame yet - run apply-patches.ps1 on "
               "the PC.",
    "bad_date": "Type the dates like 2026-09-01.",
    "locked": "Unlock Jarvis to see this list.",
}

MISSING = WORDS["missing"]

#: What the status says after a card, by the gate's outcome.
LAST_WORDS = {
    "done": "Done. You can undo it for 10 minutes.",
    "denied": "Nothing was forgotten - you said no.",
    "timed_out": "Nothing was forgotten - the card timed out.",
    "refused": "Nothing was forgotten.",
    "failed": "Nothing was forgotten - something went wrong on the PC.",
    "undone": "Put back. Everything is as it was before.",
    "kept": ("The 10 minutes to undo are over. The chats are gone for good; the facts stay "
             "forgotten."),
}

_MONTHS = ("january february march april may june july august september october "
           "november december").split()
_MONTH_SHORT = {m[:3]: i + 1 for i, m in enumerate(_MONTHS)}
_MONTH_SHORT["sept"] = 9
_WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday".split()

# --------------------------------------------------------------------------
#   Replaceable pieces, so the tests open nothing real
# --------------------------------------------------------------------------


def _now() -> float:
    """This module's clock: the Undo's ten minutes, the frames and the
    spoken request's half hour. (Whether a fact is still in use is read
    against the real clock, the memory store's own rule.)"""
    return time.time()


def _audit(event: str, detail: dict) -> None:
    # Counts and outcomes only. Never a fact's words or a chat's title.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _tier(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-forget-range-card", daemon=True).start()


def _memory():
    import jarvis_memory
    return jarvis_memory.store()


def _chats():
    import jarvis_chat_log
    return jarvis_chat_log


# --------------------------------------------------------------------------
#   Time frames - the PC's local time
# --------------------------------------------------------------------------

_WHEN = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?")


class Frame:
    """A time frame: [start, end) in epoch seconds, and how it is written.

    `frm` and `to` are the canonical text - "2026-09-01", or with a time,
    "2026-09-28T00:00" - inclusive at both ends, the way the apps show and
    send it back. `said` is it in words."""

    __slots__ = ("start", "end", "frm", "to", "said")

    def __init__(self, start: float, end: float, frm: str, to: str, said: str):
        self.start, self.end, self.frm, self.to, self.said = start, end, frm, to, said

    def view(self) -> dict:
        return {"from": self.frm, "to": self.to, "said": self.said,
                "start": int(self.start), "end": int(self.end)}


def _stamp(d: datetime) -> float:
    return time.mktime(d.timetuple())


def _day_words(d: date, year: bool = True) -> str:
    return f"{d.day} {_MONTHS[d.month - 1].capitalize()}" + (f" {d.year}" if year else "")


def _clock_words(h: int, m: int) -> str:
    if h == 0 and m == 0:
        return "midnight"
    if h == 12 and m == 0:
        return "noon"
    half = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {half}"


def frame_said(a: datetime, b: datetime, timed: bool) -> str:
    """"1 to 15 September 2026", "30 August to 5 September 2026", "28
    September 2026", or with times, "28 September 2026, midnight to 11:59
    am". `a` and `b` are the first and the last moment, both inclusive."""
    da, db = a.date(), b.date()
    if timed:
        if da == db:
            return f"{_day_words(da)}, {_clock_words(a.hour, a.minute)} to " \
                   f"{_clock_words(b.hour, b.minute)}"
        return f"{_day_words(da)}, {_clock_words(a.hour, a.minute)}, to " \
               f"{_day_words(db)}, {_clock_words(b.hour, b.minute)}"
    if da == db:
        return _day_words(da)
    if da.year == db.year and da.month == db.month:
        return f"{da.day} to {_day_words(db)}"
    if da.year == db.year:
        return f"{_day_words(da, year=False)} to {_day_words(db)}"
    return f"{_day_words(da)} to {_day_words(db)}"


def _parse_when(text) -> Optional[tuple]:
    """(datetime, has_time) from "2026-09-01" or "2026-09-01T09:30"; None
    for anything else."""
    if not isinstance(text, str):
        return None
    m = _WHEN.fullmatch(text.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not 2000 <= y <= 2100:
        return None
    try:
        if m.group(4) is None:
            return datetime(y, mo, d), False
        h, mi = int(m.group(4)), int(m.group(5))
        return datetime(y, mo, d, h, mi), True
    except ValueError:
        return None


def frame_of(frm, to, now: Optional[float] = None) -> Frame:
    """The Frame from the apps' two dates (inclusive). ValueError, in a
    sentence, for anything that is not one."""
    now = _now() if now is None else now
    a = _parse_when(frm)
    b = _parse_when(to)
    if a is None or b is None:
        raise ValueError("Type the dates like 2026-09-01.")
    (da, ta), (db, tb) = a, b
    timed = ta or tb
    first = da
    # The last moment, inclusive: the end of that day, or the end of that minute.
    last = db.replace(hour=23, minute=59) if not tb else db
    end = _stamp(last) + 60
    start = _stamp(first)
    if end <= start:
        raise ValueError("The first date is after the last one.")
    if start > now:
        raise ValueError("Those days have not happened yet, so there is nothing to forget.")
    canon_a = first.strftime("%Y-%m-%dT%H:%M") if timed else first.strftime("%Y-%m-%d")
    canon_b = last.strftime("%Y-%m-%dT%H:%M") if timed else db.strftime("%Y-%m-%d")
    return Frame(start, end, canon_a, canon_b, frame_said(first, last, timed))


def _day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def preset_frame(name: str, now: Optional[float] = None) -> Frame:
    """One of PRESETS, in the PC's local time."""
    now = _now() if now is None else now
    today = datetime.fromtimestamp(now).date()
    if name == "today":
        a = b = today
    elif name == "yesterday":
        a = b = today - timedelta(days=1)
    elif name == "this_week":
        a, b = today - timedelta(days=today.weekday()), today
    elif name == "last_week":
        monday = today - timedelta(days=today.weekday())
        a, b = monday - timedelta(days=7), monday - timedelta(days=1)
    elif name == "last_7_days":
        a, b = today - timedelta(days=6), today
    elif name == "this_month":
        a, b = today.replace(day=1), today
    elif name == "last_month":
        first = today.replace(day=1)
        b = first - timedelta(days=1)
        a = b.replace(day=1)
    else:
        raise ValueError("Pick one of the choices, or type two dates.")
    return frame_of(a.isoformat(), b.isoformat(), now)


def frame_from_query(q: dict, now: Optional[float] = None) -> Frame:
    preset = q.get("preset")
    if preset:
        return preset_frame(preset, now)
    return frame_of(q.get("from"), q.get("to"), now)


def kinds_of(raw) -> tuple:
    """"facts", "chats" or both, from "facts,chats" or a list. ValueError
    for none or anything else."""
    if raw is None or raw == "":
        return KINDS
    parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    out = []
    for p in parts:
        p = str(p).strip()
        if p not in KINDS:
            raise ValueError('Choose "facts", "chats" or both.')
        if p not in out:
            out.append(p)
    if not out:
        raise ValueError('Choose "facts", "chats" or both.')
    return tuple(k for k in KINDS if k in out)


# --------------------------------------------------------------------------
#   What is in a frame
# --------------------------------------------------------------------------


def _count(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _meta(raw) -> dict:
    try:
        m = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
    except (TypeError, ValueError):
        return {}
    return m if isinstance(m, dict) else {}


def _short_day(at: float, ref_year: Optional[int] = None) -> str:
    d = datetime.fromtimestamp(at).date()
    return _day_words(d, year=ref_year is not None and d.year != ref_year)


def _fact_item(row: dict, pinned: set, year: int) -> dict:
    kind = _meta(row.get("meta")).get("kind")
    return {"id": int(row["id"]), "text": str(row.get("text") or ""),
            "saved": int(row.get("created") or 0),
            "label": "Saved " + _short_day(float(row.get("created") or 0), year),
            "pinned": int(row["id"]) in pinned, "between_us": kind == "shared"}


def _chat_label(c: dict, year: int) -> str:
    a = datetime.fromtimestamp(c["started"]).date()
    b = datetime.fromtimestamp(c["updated"]).date()
    days = _day_words(a, year=a.year != year) if a == b else (
        f"{_day_words(a, year=a.year != year)} to {_day_words(b, year=b.year != year)}")
    return f"{days} · {_count(c['turns'], 'message')}"


def _chat_item(c: dict, year: int) -> dict:
    kind = c.get("kind") or "chat"
    return {"id": c["id"], "title": c["title"] or "(no title)", "started": int(c["started"]),
            "updated": int(c["updated"]), "turns": int(c["turns"]),
            "in_frame": int(c["in_frame"]), "spills": bool(c["spills"]),
            "label": _chat_label(c, year), "kind": kind,
            # A support record starts unticked in both apps (WORDS["support"]),
            # and so does a chat with messages from outside the days: since
            # "Continue this chat" a chat can span weeks, and one message
            # inside the days would delete all of it (the second chat audit,
            # 2026-09-28, finding 10).
            "ticked": kind != "support" and not bool(c["spills"])}


def _pinned(mem) -> set:
    try:
        return {int(f["id"]) for f in mem.profile()}
    except Exception:
        return set()


def _summary(nf: Optional[int], nc: Optional[int], said: str) -> str:
    parts = []
    if nf is not None:
        parts.append(_count(nf, "fact"))
    if nc is not None:
        parts.append(_count(nc, "chat"))
    return " and ".join(parts) + f" from {said}."


def preview(frame: Frame, kinds=KINDS, *, mem=None, chats=None) -> dict:
    """What is in `frame`: the facts saved then and the chats that overlap
    it, each with a label, oldest first. Over MAX_ITEMS together: the
    counts only, `too_many`, and no list."""
    kinds = tuple(kinds)
    year = datetime.fromtimestamp(frame.start).year
    out = {"ok": True, "frame": frame.view(), "kinds": list(kinds), "facts": [], "chats": [],
           "counts": {}, "too_many": False, "max_items": MAX_ITEMS, "chats_why": ""}
    facts_rows, nf, chat_rows, nc = [], None, [], None
    if "facts" in kinds:
        mem = mem if mem is not None else _memory()
        facts_rows, nf = mem.saved_between(frame.start, frame.end, MAX_ITEMS + 1)
        out["counts"]["facts"] = nf
    if "chats" in kinds:
        chats = chats if chats is not None else _chats()
        got = chats.overlapping(frame.start, frame.end, MAX_ITEMS + 1)
        chat_rows, nc = got.get("items") or [], int(got.get("total") or 0)
        out["counts"]["chats"] = nc
        if got.get("why_not"):
            out["chats_why"] = ("Your chats from then could not be read: "
                                + str(got["why_not"]).rstrip(".") + ".")
    total = (nf or 0) + (nc or 0)
    out["said"] = _summary(nf, nc, frame.said)
    out["empty"] = total == 0
    if total > MAX_ITEMS:
        out["too_many"] = True
        out["said"] = (f"That is {_summary(nf, nc, frame.said)[:-1]} - more than {MAX_ITEMS} "
                       f"at once. Choose fewer days.")
        return out
    if "facts" in kinds:
        pinned = _pinned(mem)
        out["facts"] = [_fact_item(r, pinned, year) for r in facts_rows]
    out["chats"] = [_chat_item(c, year) for c in chat_rows]
    return out


# --------------------------------------------------------------------------
#   The card
# --------------------------------------------------------------------------


def card_text(frame: Frame, facts: list, chats: list) -> str:
    """Every fact word for word and every chat's title, with their dates."""
    lines = [f"Forget what Jarvis learned and delete your chats from {frame.said}?"
             if facts and chats else
             f"Forget what Jarvis learned from {frame.said}?" if facts else
             f"Delete your chats from {frame.said}?", ""]
    if facts:
        lines.append(f"Jarvis will forget {'this fact' if len(facts) == 1 else f'these {len(facts)} facts'}"
                     " - it stops using them, and they stay in the history as forgotten:")
        for i, f in enumerate(facts, 1):
            lines.append(f"{i}. \"{f['text']}\" - {f['label'][:1].lower() + f['label'][1:]}")
        lines.append("")
    if chats:
        lines.append(f"Jarvis will delete {'this chat' if len(chats) == 1 else f'these {len(chats)} chats'}"
                     " from this PC:")
        for i, c in enumerate(chats, 1):
            lines.append(f"{i}. \"{c['title']}\" - {c['label']}")
            if c.get("kind") == "support":
                lines.append("   This is a customer-support chat's record - you ticked it, "
                             "so it is deleted too.")
            if c.get("spills"):
                lines.append("   It also has messages from outside these days: the whole chat "
                             "is deleted.")
        # What deleting a chat does not touch (the second chat audit,
        # 2026-09-28): the same sentence every delete dialog says.
        lines.append("Facts you did not tick stay. Copies in older backups stay until they age out.")
        lines.append("")
    lines += [
        f"For {UNDO_MINUTES} minutes after you approve, one tap on Undo puts everything back. "
        "After that the chats are gone for good, and the facts stay forgotten. Nothing is "
        "erased: a fact's words stay in the history unless you use Erase the words on it.",
        "",
        "Nothing is removed unless you approve this card. Saying yes out loud does not "
        "approve it.",
        "",
        "If you did not just ask for this, say no.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   State: one card at a time, one Undo window at a time
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
#: Held while approved changes are made and while Undo runs, so the two
#: never interleave.
_SWITCH = threading.Lock()
_STATE: dict = {"pending": None, "last": None, "undo": None, "asked": None}


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _finish(token: str, outcome: str, why: str = "", message: str = "") -> None:
    with _LOCK:
        p = _STATE["pending"]
        if p and p.get("token") == token:
            _STATE["pending"] = None
        _STATE["last"] = {"outcome": outcome, "why": why, "at": _now(),
                          "message": message or LAST_WORDS.get(outcome, "")}
    _audit("memory.forget_range.card", {"outcome": outcome})


def _purge(token: str) -> None:
    """The ten minutes are up: the held chats are dropped, for good."""
    with _SWITCH:
        with _LOCK:
            u = _STATE["undo"]
            if not u or u.get("token") != token:
                return
            _STATE["undo"] = None
            u["chats"] = {}
            _STATE["last"] = {"outcome": "kept", "why": "", "at": _now(),
                              "message": LAST_WORDS["kept"]}
    _audit("memory.forget_range.kept", {})


def _timer(seconds: float, fn: Callable[[], None]) -> None:
    t = threading.Timer(seconds, fn)
    t.daemon = True
    t.name = "jarvis-forget-range-undo"
    t.start()


def _expire(now: float) -> None:
    """The lazy half of the ten-minute limit (the timer is the other)."""
    with _LOCK:
        u = _STATE["undo"]
        # `until` is a wall-clock time (shown to the apps); `mono_until` is the same
        # ten minutes on the MONOTONIC clock, so a clock set back while the Undo
        # is open cannot stretch it past ten real minutes (time audit, 2026-09-30).
        token = u["token"] if u and (u["until"] <= now or (
            u.get("mono_until") is not None and time.monotonic() >= u["mono_until"])) else None
        a = _STATE["asked"]
        if a and a["at"] + ASKED_SECONDS <= now:
            _STATE["asked"] = None
    if token:
        _purge(token)


def _undo_view(u: Optional[dict], now: float) -> Optional[dict]:
    if not u:
        return None
    left = max(0, int(u["until"] - now))
    nf, nc = len(u["facts"]), len(u["chats"])
    done = []
    if nf:
        done.append("forgot " + _count(nf, "fact"))
    if nc:
        done.append("deleted " + _count(nc, "chat"))
    said = (" and ".join(done) or "nothing changed")
    return {"until": int(u["until"]), "seconds_left": left,
            "minutes_left": max(1, -(-left // 60)) if left else 0,
            "facts": nf, "chats": nc, "frame": u["frame"],
            "said": said[:1].upper() + said[1:] + f" from {u['frame']}."}


def status(now: Optional[float] = None) -> dict:
    now = _now() if now is None else now
    _expire(now)
    with _LOCK:
        p, last, u, a = (_STATE["pending"], _STATE["last"], _STATE["undo"],
                         _STATE["asked"])
        return {
            "available": True, "title": WORDS["title"],
            "waiting": p is not None,
            "waiting_for": dict(p["counts"], frame=p["frame"]) if p else None,
            "undo": _undo_view(u, now),
            "last": dict(last) if last else None,
            "asked": {k: a[k] for k in ("id", "from", "to", "said", "kinds")} if a else None,
            "max_items": MAX_ITEMS, "undo_minutes": UNDO_MINUTES,
            "presets": [{"id": k, "label": v} for k, v in PRESETS],
        }


# --------------------------------------------------------------------------
#   Asking: POST /api/memory/forget_range
# --------------------------------------------------------------------------


def _check_facts(mem, ids: list, frame: Frame) -> tuple:
    """(items still in the frame, ids that are not)."""
    now = time.time()
    pinned = _pinned(mem)
    year = datetime.fromtimestamp(frame.start).year
    ok, gone = [], []
    for fid in ids:
        row = mem.get(fid)
        if (row is None or row.get("erased_at") is not None
                or (row.get("valid_to") is not None and row["valid_to"] <= now)
                or not frame.start <= float(row.get("created") or 0) < frame.end):
            gone.append(fid)
        else:
            ok.append(_fact_item(row, pinned, year))
    return ok, gone


def _check_chats(chats, ids: list, frame: Frame) -> tuple:
    year = datetime.fromtimestamp(frame.start).year
    got = chats.overlapping(frame.start, frame.end, len(ids) + 1, only=ids)
    if got.get("why_not"):
        raise PermissionError("Your chats could not be read: "
                              + str(got["why_not"]).rstrip(".") + ".")
    found = {c["id"]: c for c in got.get("items") or []}
    ok = [_chat_item(found[i], year) for i in ids if i in found]
    gone = [i for i in ids if i not in found]
    return ok, gone


def _ids(raw, kind) -> list:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{kind} is a list")
    out = []
    for i in raw:
        if kind == "facts":
            if not isinstance(i, int) or isinstance(i, bool) or i <= 0:
                raise ValueError("facts are whole-number ids")
        elif not (isinstance(i, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", i)):
            raise ValueError("chats are conversation ids")
        if i in out:
            raise ValueError("an id is there twice")
        out.append(i)
    return out


def request(body, *, now: Optional[float] = None, mem=None, chats=None,
            gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
            spawn: Optional[Callable] = None) -> tuple:
    """{"from", "to", "facts": [ids], "chats": [ids]} - the ids still ticked.
    202 and ONE card, or why not. Nothing changes here."""
    now = _now() if now is None else now
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    _expire(now)
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "Send a JSON object."}
    try:
        frame = frame_of(body.get("from"), body.get("to"), now)
        fids = _ids(body.get("facts"), "facts")
        cids = _ids(body.get("chats"), "chats")
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    if not fids and not cids:
        return 400, {"ok": False, "error": WORDS["none_ticked"]}
    if len(fids) + len(cids) > MAX_ITEMS:
        return 400, {"ok": False, "error": f"At most {MAX_ITEMS} at once. Choose fewer days."}
    t = tier_of(ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {t!r} in jarvis-framework.toml; forgetting a time frame "
            f"needs a person to say yes, so it must be 'ask'")}
    with _LOCK:
        if _STATE["pending"] is not None:
            return 409, {"ok": False, "error": "A card for this is already waiting - answer it "
                                               "first."}
        u = _STATE["undo"]
        if u is not None:
            left = max(1, -(-int(u["until"] - now) // 60))
            return 409, {"ok": False, "error": (
                f"You can still undo the last time frame you forgot, for about "
                f"{_count(left, 'more minute')}. Once that time is up, or you tap Undo, you "
                f"can forget another.")}
    try:
        facts, gone_f = _check_facts(mem if mem is not None else _memory(), fids, frame) \
            if fids else ([], [])
        chat_items, gone_c = _check_chats(chats if chats is not None else _chats(), cids,
                                          frame) if cids else ([], [])
    except PermissionError as exc:
        return 503, {"ok": False, "error": str(exc)}
    if gone_f or gone_c:
        return 409, {"ok": False, "changed": True, "error": (
            "The list changed since you read it - something on it was already forgotten, "
            "deleted, or is not from those days. Read the list again.")}
    text = card_text(frame, facts, chat_items)
    counts = {"facts": len(facts), "chats": len(chat_items)}
    with _LOCK:
        if _STATE["pending"] is not None:
            return 409, {"ok": False, "error": "A card for this is already waiting - answer it "
                                               "first."}
        token = uuid.uuid4().hex
        _STATE["pending"] = {"token": token, "since": now, "counts": counts,
                             "frame": frame.said}
        _STATE["asked"] = None
    job = {"token": token, "frame": frame, "facts": fids, "chats": cids, "text": text,
           "counts": counts}
    try:
        spawn(lambda: _decide(job, mem, chats, gate, tier_of))
    except Exception:
        with _LOCK:
            _STATE["pending"] = None
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "counts": counts,
                 "message": "Waiting for your approval. Nothing is forgotten or deleted "
                            "unless you approve the card."}


def _decide(job: dict, mem, chats, gate: Callable, tier_of: Callable) -> None:
    token, text = job["token"], job["text"]
    detail = {"text": text, "what": "forget facts and delete chats from a time frame",
              "frame": job["frame"].said, "facts": job["counts"]["facts"],
              "chats": job["counts"]["chats"], "leaves_this_pc": False}
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        return _finish(token, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(ACTION) != "ask":
        return _finish(token, "refused", f"the gate answered at tier {vtier!r}, which is not "
                                         f"a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(token, outcome)
        return _finish(token, "refused", str(getattr(v, "reason", "refused"))[:200])
    try:
        apply(job, mem=mem, chats=chats)
    except Exception as exc:
        with _LOCK:
            some = (_STATE["undo"] or {}).get("token") == token
        return _finish(token, "failed", type(exc).__name__, message=(
            "Something went wrong part of the way. What was done can be undone for 10 minutes."
            if some else ""))


def _forget_one(mem, fid: int, frame: Frame) -> Optional[dict]:
    """Forget ONE fact exactly as Forget does (retire()), when it is still
    in use and still from the frame. What Undo needs, or None."""
    try:
        row = mem.get(fid)
        now = time.time()
        if (row is None or row.get("erased_at") is not None
                or (row.get("valid_to") is not None and row["valid_to"] <= now)
                or not frame.start <= float(row.get("created") or 0) < frame.end):
            return None             # forgotten, erased or changed while the card waited
        before = row.get("valid_to")
        if not mem.retire(fid):
            return None
        after = mem.get(fid) or {}
        if after.get("retired_at") is None:
            return None
        return {"id": fid, "valid_to": before, "stamp": float(after["retired_at"])}
    except Exception:
        return None


def apply(job: dict, *, mem=None, chats=None, now: Optional[float] = None,
          timer: Optional[Callable] = None) -> dict:
    """After a person's yes: forget each fact (retire, exactly as Forget),
    take each chat out into the Undo hold, and start the ten minutes."""
    timer = timer or _timer
    frame = job["frame"]
    token = job["token"]
    held_facts, held_chats = [], {}
    with _SWITCH:
        try:
            if job["facts"]:
                mem = mem if mem is not None else _memory()
                for fid in job["facts"]:
                    got = _forget_one(mem, fid, frame)
                    if got is not None:
                        held_facts.append(got)
            if job["chats"]:
                chats = chats if chats is not None else _chats()
                # Only the ones still in the frame (none was deleted or
                # moved while the card waited).
                got = chats.overlapping(frame.start, frame.end, len(job["chats"]) + 1,
                                        only=job["chats"])
                still = [c["id"] for c in got.get("items") or []]
                if still:
                    held_chats = chats.take_out(still)
        finally:
            # Whatever was done is held for Undo, even when something failed
            # part of the way: nothing done here is ever left without it.
            now = _now() if now is None else now
            with _LOCK:
                _STATE["undo"] = {"token": token, "until": now + UNDO_SECONDS,
                                  "mono_until": time.monotonic() + UNDO_SECONDS,
                                  "facts": held_facts, "chats": held_chats,
                                  "frame": frame.said}
                p = _STATE["pending"]
                if p and p.get("token") == token:
                    _STATE["pending"] = None
                _STATE["last"] = {"outcome": "done", "why": "", "at": now,
                                  "message": LAST_WORDS["done"]}
            timer(UNDO_SECONDS, lambda: _purge(token))
    _audit("memory.forget_range.done", {"facts": len(held_facts), "chats": len(held_chats)})
    return {"facts": len(held_facts), "chats": len(held_chats)}


# --------------------------------------------------------------------------
#   Undo: POST /api/memory/forget_range/undo - one tap, no card
# --------------------------------------------------------------------------


def undo(*, now: Optional[float] = None, mem=None, chats=None) -> tuple:
    now = _now() if now is None else now
    _expire(now)
    with _SWITCH:
        with _LOCK:
            u = _STATE["undo"]
            if u is None:
                return 409, {"ok": False, "error": (
                    "There is nothing to undo - the 10 minutes are up, or it was already "
                    "undone.")}
            _STATE["undo"] = None
        back_f, kept_f = 0, 0
        if u["facts"]:
            mem = mem if mem is not None else _memory()
            for f in u["facts"]:
                try:
                    ok = mem.unforget(f["id"], stamp=f["stamp"], valid_to_before=f["valid_to"])
                except Exception:
                    ok = False
                back_f += 1 if ok else 0
                kept_f += 0 if ok else 1
        back_c, failed_c = 0, {}
        if u["chats"]:
            chats = chats if chats is not None else _chats()
            got = chats.put_back(u["chats"])
            back_c = len(got.get("restored") or [])
            failed_c = got.get("failed") or {}
        u["chats"] = {}
        parts = []
        if back_f:
            parts.append(_count(back_f, "fact"))
        if back_c:
            parts.append(_count(back_c, "chat"))
        said = ("Put back: " + " and ".join(parts) + ".") if parts else "Nothing was put back."
        if kept_f:
            said += (" 1 fact stayed forgotten: its words were erased, or it changed, since."
                     if kept_f == 1 else
                     f" {kept_f} facts stayed forgotten: their words were erased, or they "
                     f"changed, since.")
        if failed_c:
            why = next(iter(failed_c.values()))
            said += f" {_count(len(failed_c), 'chat')} could not be put back: {why}"
        with _LOCK:
            _STATE["last"] = {"outcome": "undone", "why": "", "at": now, "message": said}
    _audit("memory.forget_range.undone", {"facts": back_f, "chats": back_c})
    return 200, {"ok": True, "restored": {"facts": back_f, "chats": back_c},
                 "not_restored": {"facts": kept_f, "chats": len(failed_c)}, "message": said}


# --------------------------------------------------------------------------
#   By voice or typing: "forget what you learned last week"
# --------------------------------------------------------------------------
#
# jarvis_quick.py hands every sentence it has tidied (lower case, "Jarvis,"
# and "please" off) to parse_phrase(). It NEVER removes anything: a
# sentence it understands fills in the list in both apps' Brain and says
# so. A date it cannot be sure of is asked about, not guessed.

_VERB = r"(?:forget|delete|remove|clear|erase|wipe|get\s+rid\s+of)"
_FACTS_OBJ = (r"(?:what|everything|anything|all|the\s+things?|things?)\s+(?:that\s+)?"
              r"(?:you(?:'ve|\s+have)?\s+)?(?:learned|learnt|remembered|picked\s+up|"
              r"found\s+out)(?:\s+about\s+me)?"
              r"|(?:the\s+|my\s+)?(?:facts|memories)(?:\s+you\s+(?:learned|learnt|saved))?")
_CHATS_OBJ = (r"(?:all\s+)?(?:(?:my|our|the)\s+)?(?:chats?|conversations?|chat\s+history|"
              r"messages|history)")
_BOTH_OBJ = (r"(?:what|everything|anything|all)\s+(?:that\s+)?(?:i\s+(?:said|told\s+you|typed|"
             r"asked(?:\s+you)?|said\s+to\s+you)|we\s+(?:said|talked\s+about|discussed))"
             r"|everything|all\s+of\s+it")

_ORD = {w: i + 1 for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth "
    "thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth"
    .split())}
_ORD.update({"twenty " + w: 20 + i + 1 for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth".split())})
_ORD.update({"thirtieth": 30, "thirty first": 31})
_CARD = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
_CARD.update({"twenty " + w: 20 + i + 1 for i, w in enumerate(
    "one two three four five six seven eight nine".split())})
_CARD.update({"thirty": 30, "thirty one": 31})
_DAYWORDS = sorted(list(_ORD) + list(_CARD), key=len, reverse=True)
_DAY = r"(?:\d{1,2}(?:st|nd|rd|th)?|" + "|".join(w.replace(" ", r"[\s-]") for w in _DAYWORDS) + ")"
_MONTH = r"(?:" + "|".join(_MONTHS) + r"|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)"
_YEAR = r"(?:20\d\d)"
_DAY_MONTH = (r"(?:the\s+)?(?P<@D@>" + _DAY + r")\s+(?:of\s+)?(?P<@M@>" + _MONTH + r")"
              r"(?:,?\s+(?P<@Y@>" + _YEAR + r"))?")
_MONTH_DAY = (r"(?P<@M@>" + _MONTH + r")\s+(?:the\s+)?(?P<@D@>" + _DAY + r")"
              r"(?:,?\s+(?P<@Y@>" + _YEAR + r"))?")


def _dm(tag: str) -> str:
    return _DAY_MONTH.replace("@D@", "d" + tag).replace("@M@", "m" + tag).replace("@Y@", "y" + tag)


def _md(tag: str) -> str:
    return _MONTH_DAY.replace("@D@", "d" + tag).replace("@M@", "m" + tag).replace("@Y@", "y" + tag)


def _day_num(tok: Optional[str]) -> Optional[int]:
    if tok is None:
        return None
    t = re.sub(r"[\s-]+", " ", tok.strip())
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?", t)
    n = int(m.group(1)) if m else (_ORD.get(t) or _CARD.get(t))
    return n if n and 1 <= n <= 31 else None


def _month_num(tok: Optional[str]) -> Optional[int]:
    if not tok:
        return None
    if tok in _MONTHS:
        return _MONTHS.index(tok) + 1
    return _MONTH_SHORT.get(tok) or _MONTH_SHORT.get(tok[:3])


_N_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "fourteen": 14, "thirty": 30}


class _Ask(Exception):
    """A date this cannot be sure of: the question to ask instead."""


def _date_or_ask(y: Optional[int], m: int, d: int, today: date, *, ref: Optional[date] = None
                 ) -> date:
    """A day, with the year filled in when it was not said: this year - or,
    when that has not happened yet, an honest question."""
    try:
        if y is not None:
            return date(y, m, d)
        got = date(today.year, m, d)
    except ValueError:
        raise _Ask(f"There is no {d} {_MONTHS[m - 1].capitalize()}. Which day did you mean?")
    if got > (ref or today):
        raise _Ask(f"{d} {_MONTHS[m - 1].capitalize()} has not happened yet this year. Did you "
                   f"mean {d} {_MONTHS[m - 1].capitalize()} {today.year - 1}? Say the year, or "
                   f"choose the days in Brain, under {WORDS['title']}.")
    return got


def _time_of(t: str, now: float) -> Optional[tuple]:
    """(first moment, last moment, timed) for the time words `t`, or None
    when `t` is not a time frame at all. Raises _Ask for one that is, but
    cannot be pinned down."""
    today = datetime.fromtimestamp(now).date()
    one = lambda d: (_day(d), _day(d).replace(hour=23, minute=59), False)  # noqa: E731
    span = lambda a, b: (_day(a), _day(b).replace(hour=23, minute=59), False)  # noqa: E731
    t = re.sub(r"^(?:from|on|in|during|over|for)\s+", "", t.strip())
    if t in ("today", "earlier today", "so far today"):
        return one(today)
    if t == "yesterday":
        return one(today - timedelta(days=1))
    parts = {"morning": (0, 0, 11, 59), "afternoon": (12, 0, 17, 59),
             "evening": (18, 0, 23, 59)}
    m = re.fullmatch(r"(this|yesterday)\s+(morning|afternoon|evening)|tonight", t)
    if m:
        d = today if (m.group(1) or "this") == "this" else today - timedelta(days=1)
        h0, m0, h1, m1 = parts[m.group(2) or "evening"]
        return (_day(d).replace(hour=h0, minute=m0), _day(d).replace(hour=h1, minute=m1), True)
    if t == "last night":
        raise _Ask("Do you mean yesterday evening, or all of yesterday? Say \"yesterday "
                   "evening\" or \"yesterday\".")
    if t == "this week":
        return span(today - timedelta(days=today.weekday()), today)
    if t == "last week":
        monday = today - timedelta(days=today.weekday())
        return span(monday - timedelta(days=7), monday - timedelta(days=1))
    if t in ("the last week", "the past week"):
        return span(today - timedelta(days=6), today)
    if t == "this month":
        return span(today.replace(day=1), today)
    if t == "last month":
        b = today.replace(day=1) - timedelta(days=1)
        return span(b.replace(day=1), b)
    if t in ("the last month", "the past month"):
        return span(today - timedelta(days=29), today)
    m = re.fullmatch(r"(?:the\s+)?(?:last|past)\s+(\d{1,3}|" + "|".join(_N_WORDS) + r")\s+days", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _N_WORDS[m.group(1)]
        if not 1 <= n <= 366:
            raise _Ask("That is more days than Jarvis looks back in one go. Choose the days in "
                       f"Brain, under {WORDS['title']}.")
        return span(today - timedelta(days=n - 1), today)
    m = re.fullmatch(r"(last\s+)?(" + "|".join(_WEEKDAYS) + r")", t)
    if m:
        want = _WEEKDAYS.index(m.group(2))
        back = (today.weekday() - want) % 7
        if back == 0:
            if not m.group(1):
                last = today - timedelta(days=7)
                raise _Ask(f"Today is {_WEEKDAYS[want].capitalize()}. Do you mean today, or "
                           f"last {_WEEKDAYS[want].capitalize()}, {_day_words(last, False)}?")
            back = 7
        return one(today - timedelta(days=back))
    m = re.fullmatch(r"since\s+(.+)", t)
    if m:
        got = _time_of(m.group(1), now)
        if got is None:
            return None
        return (got[0], _day(today).replace(hour=23, minute=59), False)
    if re.search(r"\b\d{1,2}\s*/\s*\d{1,2}(?:\s*/\s*\d{2,4})?\b", t):
        raise _Ask("A date written with slashes can be read two ways. Say the month's name, "
                   "like \"3 September\".")
    # A whole month: "in September", "September 2025".
    m = re.fullmatch(r"(?P<m>" + _MONTH + r")(?:\s+(?P<y>" + _YEAR + r"))?", t)
    if m:
        mo = _month_num(m.group("m"))
        y = int(m.group("y")) if m.group("y") else None
        if y is None:
            y = today.year
            if date(y, mo, 1) > today:
                raise _Ask(f"{_MONTHS[mo - 1].capitalize()} has not happened yet this year. Did "
                           f"you mean {_MONTHS[mo - 1].capitalize()} {today.year - 1}? Say the "
                           f"year.")
        last = date(y, mo, calendar.monthrange(y, mo)[1])
        return span(date(y, mo, 1), min(last, today) if last > today else last)
    # One day: "3 September", "the 3rd of September", "September 3rd 2026".
    for pat in (_dm("a"), _md("a")):
        m = re.fullmatch(pat, t)
        if m:
            d, mo = _day_num(m.group("da")), _month_num(m.group("ma"))
            if d is None or mo is None:
                return None
            y = int(m.group("ya")) if m.group("ya") else None
            return one(_date_or_ask(y, mo, d, today))
    # A range: "1 to 15 September", "from September 1 to 15", "30 August to
    # 5 September", "between 1 and 15 September", "1-15 September".
    t2 = re.sub(r"^between\s+", "", t)
    sep = r"\s*(?:-|to|and|until|till|through|thru)\s*"
    tries = (
        (r"(?:the\s+)?(?P<da>" + _DAY + r")" + sep + _dm("b")),
        (_dm("a") + sep + _dm("b")),
        (_md("a") + sep + r"(?:the\s+)?(?P<db>" + _DAY + r")(?:,?\s+(?P<yb>" + _YEAR + r"))?"),
        (_md("a") + sep + _md("b")),
    )
    for pat in tries:
        m = re.fullmatch(pat, t2)
        if not m:
            continue
        g = m.groupdict()
        db_, mb = _day_num(g.get("db")), _month_num(g.get("mb") or g.get("ma"))
        da_, ma = _day_num(g.get("da")), _month_num(g.get("ma") or g.get("mb"))
        if None in (db_, mb, da_, ma):
            return None
        yb = int(g["yb"]) if g.get("yb") else None
        ya = int(g["ya"]) if g.get("ya") else None
        end = _date_or_ask(yb, mb, db_, today)
        try:
            start = date(ya if ya is not None else end.year, ma, da_)
        except ValueError:
            raise _Ask(f"There is no {da_} {_MONTHS[ma - 1].capitalize()}. Which day did you "
                       f"mean?")
        if start > end and ya is None:
            try:
                start = start.replace(year=end.year - 1)
            except ValueError:
                # "29 February to 15 January" said in a leap year: the day before
                # it is a year with no 29 February, so there is no first day.
                raise _Ask(f"I could not work out which days you mean by {da_} "
                           f"{_MONTHS[ma - 1].capitalize()} to {db_} "
                           f"{_MONTHS[mb - 1].capitalize()}. Say the two dates with their "
                           f"years, like \"1 September 2026 to 15 September 2026\".")
        if start > end:
            raise _Ask("The first day is after the last one. Which days did you mean?")
        return span(start, end)
    m = re.fullmatch(r"(?:the\s+)?" + _DAY, t)
    if m and _day_num(t.replace("the ", "")):
        raise _Ask("Which month? Say it like \"3 September\".")
    return None


def parse_phrase(s: str, now: Optional[float] = None) -> Optional[dict]:
    """None - not a request to forget a time frame (the sentence goes on
    to the rest of jarvis_quick, or the model). Otherwise one of:
        {"frame": Frame, "kinds": ("facts", "chats"), "erase": bool}
        {"ask": "<a question>"}   - a date it will not guess
    `s` is jarvis_quick.normalise()'s text."""
    now = _now() if now is None else now
    if not isinstance(s, str) or len(s) > 200:
        return None
    m = re.fullmatch(r"(?:(?:please|can\s+you|could\s+you|i\s+want\s+you\s+to)\s+)?"
                     r"(?P<verb>" + _VERB + r")\s+(?P<rest>.+)", s.strip())
    if not m:
        return None
    rest = m.group("rest")
    erase = m.group("verb").startswith(("erase", "wipe"))
    # The time words are at the end. Try the longest tail first.
    words = rest.split()
    for cut in range(1, len(words)):
        obj = " ".join(words[:cut])
        when = " ".join(words[cut:])
        kinds = _kinds_of_obj(obj)
        if kinds is None:
            continue
        try:
            got = _time_of(when, now)
        except _Ask as ask:
            return {"ask": str(ask)}
        if got is None:
            continue
        a, b, timed = got
        if _stamp(a) > now:
            return {"ask": "That has not happened yet, so there is nothing to forget."}
        if timed:
            frame = frame_of(a.strftime("%Y-%m-%dT%H:%M"), b.strftime("%Y-%m-%dT%H:%M"), now)
        else:
            frame = frame_of(a.date().isoformat(), b.date().isoformat(), now)
        return {"frame": frame, "kinds": kinds, "erase": erase}
    return None


def _kinds_of_obj(obj: str) -> Optional[tuple]:
    """The kinds the object words name - "what you learned" is facts, "my
    chats" chats, "what I said" or "everything" both, and two joined with
    "and" - or None when they are not one of these."""
    obj = re.sub(r"\s+(?:from|on|in|during|over|for|since)$", "", obj.strip())
    pieces = re.split(r"\s+and\s+(?:" + _VERB + r"\s+)?", obj)
    kinds = set()
    for p in pieces:
        p = p.strip()
        if re.fullmatch(_FACTS_OBJ, p):
            kinds.add("facts")
        elif re.fullmatch(_CHATS_OBJ, p):
            kinds.add("chats")
        elif re.fullmatch(_BOTH_OBJ, p):
            kinds.update(KINDS)
        else:
            return None
    return tuple(k for k in KINDS if k in kinds) if kinds else None


def quick_answer(got: dict, now: Optional[float] = None, *, mem=None, chats=None) -> tuple:
    """(what Jarvis says, whether the apps open the list). It fills in the
    list in both apps' Brain (status()["asked"]) and says where it is - and
    never removes anything. `got` is parse_phrase()'s. A question, nothing
    found, or a list that cannot be read opens nothing."""
    now = _now() if now is None else now
    if got.get("ask"):
        return got["ask"], False
    frame, kinds = got["frame"], got["kinds"]
    try:
        p = preview(frame, kinds, mem=mem, chats=chats)
    except Exception:
        return ("I could not read what Jarvis learned or said then. Choose the days in Brain, "
                f"under {WORDS['title']}."), False
    lead = ""
    if got.get("erase"):
        lead = ("I can forget them, but not erase their words: that is \"Erase the words\", on "
                "one fact at a time. ")
    if p["empty"] and not p["chats_why"]:
        what = {("facts",): "Jarvis learned nothing", ("chats",): "there are no chats",
                KINDS: "Jarvis learned nothing and there are no chats"}[tuple(kinds)]
        return lead + f"There is nothing to forget: {what} from {frame.said}.", False
    with _LOCK:
        _STATE["asked"] = {"id": uuid.uuid4().hex[:12], "from": frame.frm, "to": frame.to,
                           "said": frame.said, "kinds": list(kinds), "at": now}
    where = f"in Brain, under {WORDS['title']}"
    found = _summary(p["counts"].get("facts"), p["counts"].get("chats"), frame.said)[:-1]
    if p["too_many"]:
        return lead + (f"That is {found} - more than {MAX_ITEMS} at once. I've put the dates "
                       f"{where}: choose fewer days there."), True
    return lead + (f"I've put the list {where}: {found}. Check it, untick anything you want "
                   f"to keep, and tap Forget these, then Approve on the card. Nothing is "
                   f"removed until you do - saying yes out loud does not approve it."), True


# --------------------------------------------------------------------------
#   The routes (docs/JARVIS-API.md section 64)
# --------------------------------------------------------------------------


def _query(qs: str) -> dict:
    try:
        return {k: v[0] for k, v in parse_qs(qs or "", keep_blank_values=True).items() if v}
    except Exception:
        return {}


def handle_get(route: str, query: str = "", *, now: Optional[float] = None, mem=None,
               chats=None) -> tuple:
    if route == ROUTE:
        return 200, status(now)
    if route == PREVIEW:
        q = _query(query)
        try:
            frame = frame_from_query(q, now)
            kinds = kinds_of(q.get("kinds"))
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
        try:
            return 200, preview(frame, kinds, mem=mem, chats=chats)
        except Exception as exc:
            return 503, {"ok": False, "error": f"it could not be read ({type(exc).__name__})"}
    if route == UNDO:
        return 405, {"ok": False, "error": "use POST for this"}
    return 404, {"ok": False, "error": "no such route"}


def handle_post(route: str, body, **kw) -> tuple:
    if route == ROUTE:
        return request(body, **kw)
    if route == UNDO:
        if body is not None and not isinstance(body, dict):
            return 400, {"ok": False, "error": "Send a JSON object."}
        keep = {k: kw[k] for k in ("now", "mem", "chats") if k in kw}
        return undo(**keep)
    if route == PREVIEW:
        return 405, {"ok": False, "error": "use GET for this"}
    return 404, {"ok": False, "error": "no such route"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so these routes are answered
    here, after the server's own origin and token checks. Every other
    request goes straight to the original. Returns the banner line."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_forget_range", False):
        return "  forget     Forget a time frame (already on)"

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
            code, out = 503, {"available": False, "error": type(exc).__name__}
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
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_forget_range = True
    do_POST._jarvis_forget_range = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return (f"  forget     Forget a time frame: a checked list, one card, "
            f"{UNDO_MINUTES} minutes to undo")


def _reset_for_tests() -> None:
    with _LOCK:
        _STATE.update(pending=None, last=None, undo=None, asked=None)
