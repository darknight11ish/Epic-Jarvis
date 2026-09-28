"""jarvis_today.py - Today cards: short notes in the owner's own words that
show on the Today part of both apps at a time, on chosen days ("Gym bag" on
Mondays and Wednesdays from 07:00, "Bins out" on Thursday evenings).

NEW MODULE, shipped whole. It needs no patch of its own: jarvis_schedule.py
imports it before its loop first runs (KIND_MODULES), its jobs are added,
listed and deleted through the scheduler's own routes (POST
/api/schedule/add with kind "today", GET /api/schedule, POST
/api/schedule/act), and jarvis_quick.py sets, lists and removes one in the
owner's own words. docs/JARVIS-API.md section 82; backend/README.md "Today
cards".

THE OWNER'S DECISION (2026-09-28, the research audit, idea 6, "build it")
Cards the owner writes in their own words, shown at a time and on chosen
days, like Samsung's Now Brief and Gemini's Daily Brief - plus the
briefing's own parts (calendar, new-email count or senders, coming up, the
weather from the owner's own Home Assistant) on the same page. Only from
sources the briefing already reads: no new way out of this PC.

WHERE THE "TODAY PAGE" IS
The Today page was designed (docs/CUTTING-EDGE-2026-09-26-round2-
experience.md section 4) but never built, and the feasibility audit's ruling
(docs/FEASIBILITY-AUDIT-2026-09-26.md row 24) is that it may only be built
by growing what is already there - never as a fourth summary view. So the
Today part lives on the existing briefing surface in both apps (desktop:
Brain -> Work, just above Morning briefing; phone: Brain, the same place),
and the briefing's parts shown there are the ones the briefing already put
together - read from GET /api/briefing, the latest briefing kept in the
PC's memory. The Today part reads NOTHING new: no calendar, email, weather
or news request of its own (nothing in this file opens a socket).

NO APPROVAL CARD - like a plain repeating reminder (2026-09-26)
Only the owner's own words or taps can set one, it acts on nothing - it only
shows the owner's own words back to them - and deleting it is immediate. So
it is Kind.plain_repeat: on the list at once. The same checks as every other
job: one at a time, never "delete all".

WHERE IT IS KEPT - the one shared scheduler
A job of kind "today" in jarvis_schedule's schedule.db, beside every
reminder: `text` is the card's words, `rule` is when it shows - every day,
every weekday, or chosen days, at a time (the scheduler's own rules; "every
N hours" is refused: a card is for a time of day). The job "goes off" at
that time only to tell both apps the list changed (the `schedule` event's
"changed", ids only), so the card appears without a reload; it is silent -
no notification, no toast, no sound, nothing in "Just went off" or "What
did I miss?". Whether a card shows is worked out from the clock, not from
when it went off, so a PC that was asleep at 07:00 still shows the card
when it wakes: a card shows from its time until the end of that day, on its
days only. A paused card does not show.

PRIVACY
The words are the owner's own: plain SQLite on this PC, like every
reminder. Never written to a log (ids and the kind only), never put on the
event bus, and never sent to any model: the Today part is drawn by the apps
from GET /api/schedule, not by the model. The one way the model sees them is
the owner asking - the model's own "coming up" tool lists the scheduler's
jobs when the owner asks what is coming up, as it does for every reminder.
"Hide memory lists and chat history" hides the words wherever the apps hide
a reminder's words (the desktop's Rust blanks `text`; the phone's
Schedule.hide), and the times and counts stay.
"""
from __future__ import annotations

import json
import time
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

import jarvis_schedule as S

KIND = "today"
NOUN = "Today card"
#: Never shown - a Today card rings no doorbell - but every kind has one.
LOCK_SCREEN = "Jarvis: a card is on your Today page."

#: A card is a few words, not a letter.
MAX_TEXT = 80
#: At most this many cards at once (they count toward the scheduler's own
#: MAX_JOBS too).
MAX_CARDS = 20

#: The rules a card may have: a time of day, not "every N hours".
EVERY = ("day", "weekday", "week")

# --------------------------------------------------------------------------
#   Words - both apps say the same (coming-up.js / today.js, net/Today.kt)
# --------------------------------------------------------------------------

TITLE = "Today"
SET_WORDS = ("Set: “{text}” shows on your Today page {rule}. Next: {next}. No card "
             "needed - delete it under Coming up to stop it.")
ALREADY = "That card is already on your Today page."
TOO_MANY = (f"There are already {MAX_CARDS} Today cards - delete some under Coming up first.")
TOO_LONG = f"A Today card is at most {MAX_TEXT} characters - say it more briefly."
NO_WORDS = "A Today card needs some words: what should it say?"
BAD_RULE = ("A Today card shows every day, every weekday, or on chosen days, at a time of day "
            "- like \"on Mondays at 7\".")
NO_WHEN = ("Say when it should show - like \"show gym bag on my Today page on Mondays at 7\" "
           "or \"... every weekday at 6pm\".")
NONE_SET = "There are no cards on your Today page."
REMOVED = "Removed “{text}” from your Today page."
NO_SUCH = "There is no card “{text}” on your Today page."
WHICH = ("There are {n} cards saying that on your Today page - delete the one you mean under "
         "Coming up.")
MISSING = ("Your PC's Jarvis cannot do Today cards yet - run apply-patches.ps1 on the PC.")


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _sched():
    return S._SCHED if S._SCHED is not None else S.get()


def clean_text(text) -> str:
    """The card's words, tidied: one line, outer quotes and end punctuation
    off ("'gym bag'" -> "gym bag"). The owner's own case is kept."""
    t = " ".join(str(text or "").split())
    t = t.strip(" ,;:!?\"'“”‘’")
    return t


def check(rule, now: Optional[float] = None) -> dict:
    """The scheduler's own rule check, then only a time of day on some days.
    ValueError with a sentence otherwise (Kind.check)."""
    if not isinstance(rule, dict) or str(rule.get("every") or "").strip().lower() not in EVERY:
        raise ValueError(BAD_RULE)
    return S.check_rule(rule, now)


def days_of(rule: dict) -> set:
    every = rule.get("every")
    if every == "day":
        return {0, 1, 2, 3, 4, 5, 6}
    if every == "weekday":
        return {0, 1, 2, 3, 4}
    return set(rule.get("days") or [])


def state_of(rule: Optional[dict], now: float) -> str:
    """"showing" (today is one of its days and its time has come - it shows
    until the end of the day), "later" (later today), or "" (not today).
    Worked out from the clock alone."""
    if not isinstance(rule, dict) or rule.get("every") not in EVERY:
        return ""
    try:
        hh, mm = S._hhmm(rule.get("at"))
    except ValueError:
        return ""
    lt = time.localtime(now)
    if lt.tm_wday not in days_of(rule):
        return ""
    starts = S.wall_to_epoch(lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm)
    return "showing" if now >= starts else "later"


# --------------------------------------------------------------------------
#   Setting, listing and removing one (the route and jarvis_quick.py)
# --------------------------------------------------------------------------

def _cards(sched) -> list:
    """Every Today card on the list (active or paused), oldest first:
    [{"id", "text", "rule", "state"}]."""
    with sched._lock, sched._db() as c:
        rows = c.execute("SELECT id, text, rule, state FROM jobs WHERE kind = ? AND state IN "
                         "('active','paused','waiting') ORDER BY created, rowid",
                         (KIND,)).fetchall()
    out = []
    for r in rows:
        try:
            rule = json.loads(r["rule"]) if r["rule"] else None
        except Exception:
            rule = None
        out.append({"id": r["id"], "text": r["text"], "rule": rule, "state": r["state"]})
    return out


def add(text, rule, *, sched=None, source: str = "app") -> dict:
    """ONE Today card, no approval card. Raises ValueError (a sentence) or
    OverflowError. Returns the job; `already: True` when the same words at
    the same times are already there."""
    sched = sched or _sched()
    text = clean_text(text)
    if not text:
        raise ValueError(NO_WORDS)
    if len(text) > MAX_TEXT:
        raise ValueError(TOO_LONG)
    rule = check(rule, sched.now())
    cards = _cards(sched)
    for j in cards:
        if j["text"].casefold() == text.casefold() and j["rule"] == rule:
            return dict(sched.job(j["id"]) or {"id": j["id"]}, already=True)
    if len(cards) >= MAX_CARDS:
        raise OverflowError(TOO_MANY)
    job = sched.add_repeat(KIND, rule, text, source=source)
    _audit("today.set", {"id": job.get("id")})
    return job


def set_words(job: dict, now: float) -> str:
    rule = job.get("rule") if isinstance(job.get("rule"), dict) else None
    return SET_WORDS.format(text=job.get("text") or "", rule=S.rule_words(rule) or "",
                            next=S.next_words(rule, now) or "see Coming up")


def cards(*, sched=None) -> list:
    """What the fast path lists: [{"id", "text", "shows", "state"}]."""
    sched = sched or _sched()
    now = sched.now()
    return [{"id": j["id"], "text": j["text"], "shows": S.rule_words(j["rule"]),
             "state": state_of(j["rule"], now) if j["state"] == "active" else ""}
            for j in _cards(sched)]


def remove(text, *, sched=None) -> tuple:
    """Delete the ONE card with these words. (ok, said). Several with the
    same words are named, never all deleted."""
    sched = sched or _sched()
    want = clean_text(text).casefold()
    hits = [j for j in _cards(sched) if want and j["text"].casefold() == want]
    if not hits:
        return False, NO_SUCH.format(text=clean_text(text))
    if len(hits) > 1:
        return False, WHICH.format(n=len(hits))
    code, out = sched.act(hits[0]["id"], "delete")
    if code != 200:
        return False, str(out.get("error") or "That did not work.")
    return True, REMOVED.format(text=hits[0]["text"])


def said_of(exc: BaseException) -> str:
    """An error as a sentence: this module's own already end in "." or "?";
    the scheduler's are tidied by its own _sentence."""
    t = str(exc).strip()
    return t if t.endswith((".", "?", "!")) else S._sentence(exc)


def add_route(body: dict) -> tuple:
    """POST /api/schedule/add {"kind": "today", "text", "repeat": {"every":
    "day"|"weekday"|"week", "at": "HH:MM", "days"?}} - both apps' small
    form. 200 {"ok", "job", "said"} (also for one already there, with
    "already": true); 400 with the reason; 409 when full."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    if not isinstance(body.get("text"), str):
        return 400, {"ok": False, "error": NO_WORDS}
    if not isinstance(body.get("repeat"), dict):
        return 400, {"ok": False, "error": NO_WHEN}
    try:
        sched = _sched()
        job = add(body.get("text"), body.get("repeat"), sched=sched, source="app")
    except OverflowError as exc:
        return 409, {"ok": False, "error": said_of(exc)}
    except (ValueError, TypeError) as exc:
        return 400, {"ok": False, "error": said_of(exc)}
    if job.get("already"):
        return 200, {"ok": True, "already": True, "job": job, "said": ALREADY}
    return 200, {"ok": True, "waiting": False, "job": job,
                 "said": set_words(job, sched.now())}


# --------------------------------------------------------------------------
#   The kind (jarvis_schedule.register_kind)
# --------------------------------------------------------------------------

def fields(job_id: str) -> dict:
    """What the apps read beside the words: whether it shows now
    (`today`: "showing" / "later" / ""), and from when ("07:00"). Never
    words."""
    try:
        sched = _sched()
        with sched._lock, sched._db() as c:
            row = c.execute("SELECT rule, state FROM jobs WHERE id = ?",
                            (str(job_id),)).fetchone()
        rule = json.loads(row["rule"]) if row is not None and row["rule"] else None
    except Exception:
        return {}
    if not isinstance(rule, dict):
        return {}
    state = state_of(rule, sched.now()) if row["state"] == "active" else ""
    return {"today": state, "shows_at": str(rule.get("at") or "")}


def _shown(job_id: str) -> None:
    """Its time came: the list is told it changed, so both apps show the
    card now. Nothing else happens - no notification, no sound."""
    try:
        _sched()._changed(job_id, KIND)
    except Exception:
        pass


S.register_kind(KIND, NOUN, LOCK_SCREEN, has_text=True, owner_listed=True, notify=False,
                silent=True, repeatable=True, plain_repeat=True, check=check,
                add=add_route, fields=fields, on_fire=_shown)
