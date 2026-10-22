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

THE TODAY BOARD (GTD-2, 2026-10-18) - and what it deliberately is not
The Today page grew three additive sections, read through ONE new GET path
on an install that already exists (jarvis_brain_reads.py, which the server
already wraps): `/api/today/cockpit`. No new module, no patch, no
registration.

  * `due_reminders` - active reminders, alarms and timers that are due or
    that went off in the last hour, read from the ONE scheduler
    (jarvis_schedule.py: `listed()` and `went_off()`). It is deliberately
    NOT read from jarvis_tasks.py: that module is the job list (work that
    outlives one chat turn), not the reminder store.
  * `active_next_steps` - the first open step of every active goal
    (jarvis_goals.py: `Goals.list()` + `next_open_step()`), and the first
    open item on every project's work list (jarvis_projects.py: the work
    list is a named list on the one scheduler; `Scheduler.todos()`).
  * `proposals` - "You said you would": commitments found ONLY in the
    owner's own words (`role == "user"`) in recent kept chats, that no open
    reminder or Today card covers yet. Strictly proposals - this module
    creates no reminder and no card; only the owner's own tap may (the app
    copies a "Remind me to ..." prompt into the chat box, and the owner
    sends it through the ordinary flow). Withheld completely while the
    private lists are hidden or App lock is on: the apps pass that state as
    `hidden=1`, and the desktop ALSO blanks the same sections in Rust, so a
    page script cannot read round the lock.

`rollover_cards` (yesterday's unfinished Today cards) is NOT built and the
section is honestly empty: a Today card is a repeating note with no per-day
"done" state, and nothing in jarvis_schedule, jarvis_briefing or this file
stores "this card was on yesterday and is still undone". Reading that from
anywhere would be inventing it, so `rollover_cards()` below returns [] and
this file says why; building it needs new per-day completion state.

THE SAID-I'D-DO SWITCH (owner's ruling, 2026-10-18)
Proposals are OFF by default. `unspoken_commitments_enabled` lives in
`today.json` in the config folder; turning it ON is ONE approval card
(gate action `change_own_config`, tier ask, like the other privacy
switches) and changes nothing until a person approves; turning it OFF is
immediate. A proposal that was said more than `UNSPOKEN_TTL_DAYS` days ago
fades (there is no tap record - a tap only copies a "Remind me to ..."
prompt, so the only honest clock is when the owner said it), and one an
open reminder or Today card already covers is never proposed again.
The scanner makes no model call, opens no socket, and keeps nothing.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

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


# --------------------------------------------------------------------------
#   The Today board (GTD-2, 2026-10-18)
# --------------------------------------------------------------------------
#
# Three additive sections on one new GET path, `/api/today/cockpit`, which
# jarvis_brain_reads.py answers (the server already wraps its Handler for
# that module, so this needs no patch and no registration). Old reads are
# untouched: the scheduler's own `status()`, `listed()` and `job()` answers
# are exactly what they were, and the new sections are only added by these
# functions - they never edit a scheduler reply in place.

#: GET /api/today/cockpit - the one new read path (jarvis_brain_reads.py).
COCKPIT_PATH = "/api/today/cockpit"

#: The job kinds "due now" covers: the three the scheduler itself notifies
#: for. A Today card is not one of them (a card is a note, not a doorbell).
DUE_KINDS = ("reminder", "alarm", "timer")

#: A reminder this late is "overdue" rather than "due now" (the same grace
#: the briefing's own Today part uses: a job a second past its time is not
#: late yet). N_placeholder until measured on the owner's PC.
OVERDUE_GRACE = 60.0

#: How many of each the board carries. Small on purpose: it is a page, not
#: a list you scroll. N_placeholder until measured.
MAX_DUE_REMINDERS = 8
MAX_NEXT_STEPS = 6
MAX_PROPOSALS = 5

#: How much kept chat the scanner reads: the newest few conversations, and
#: the owner's own turns in them. N_placeholder until measured.
RECENT_CONVERSATIONS = 3
RECENT_TURNS = 40
MAX_PROPOSAL_TEXT = 200

#: The optional fields a reminder row may carry once session A's GTD-1 work
#: merges (`context_bundle`, `suggested_prompt`, `snooze_count`,
#: `stuck_hint`). They are copied ONLY when the scheduler's own view really
#: has them; with today's scheduler they never do, so the board is complete
#: and honest either way - no invented defaults, no invented context.
CONTEXT_KEYS = ("context_bundle", "suggested_prompt", "snooze_count", "stuck_hint")

#: Said when the board cannot be read at all (an older PC, a broken store).
BOARD_FAILED = ("Your PC's Jarvis cannot read the Today board just now - run "
                "apply-patches.ps1 on the PC.")

# --------------------------------------------------------------------------
#   The said-I'd-do switch (owner's ruling, 2026-10-18: OFF by default)
# --------------------------------------------------------------------------

#: Where the switch lives: beside schedule.db and memory.db, in the config
#: folder, like every other privacy switch (`screen-picture.json` shape).
SETTINGS_FILE = "today.json"

#: The gate action turning the scanner ON uses: the repo's existing
#: "change a setting that widens what Jarvis reads about you" action, tier
#: ask. No new gate row, no new action.
UNSPOKEN_ACTION = "change_own_config"

#: A proposal said longer ago than this is not offered again. The owner's
#: ruling says 3 days (N_placeholder until measured on the owner's PC).
UNSPOKEN_TTL_DAYS = 3

UNSPOKEN_LABEL = "Said-I'd-do suggestions"
UNSPOKEN_DETAIL = ("When this is on, the Today page offers things YOU said you would do "
                   "(only your own words, never a temporary or crisis chat) that no reminder "
                   "covers yet - as suggestions only. Jarvis never creates a reminder from one "
                   "without your tap. Off unless you turn it on.")
UNSPOKEN_ON_CARD = "\n".join([
    "Turn on said-I'd-do suggestions.",
    "",
    "Jarvis will read your own words in recent kept chats (never a temporary chat and "
    "never a crisis chat, and never what Jarvis or a tool said) and offer first-person "
    "promises like \"I'll send the report tomorrow\" on the Today page as suggestions.",
    "",
    "Nothing is created from a suggestion unless you tap it, and the tap only puts a "
    "\"Remind me to ...\" prompt in the chat box for you to send.",
    "A suggestion fades after 3 days. Turning this off is instant, from either app.",
    "",
    "If you say no: the Today page shows no suggestions.",
])
UNSPOKEN_OFF_SAID = "Said-I'd-do suggestions are off. The Today page shows none."
UNSPOKEN_WAITING_SAID = ("Waiting for your approval. Suggestions turn on only if you approve "
                         "the card, on your PC or phone.")
UNSPOKEN_ON_SAID = "Said-I'd-do suggestions are on."
UNSPOKEN_ALREADY_ON = "Said-I'd-do suggestions are already on."
UNSPOKEN_ALREADY_WAITING = "A card to turn on said-I'd-do suggestions is already waiting."
UNSPOKEN_BAD_BODY = 'need {"enabled": true|false}'
UNSPOKEN_CARD_FAILED = "Could not raise the approval card."
UNSPOKEN_TIER_WRONG = ("{action} is tier {tier!r} in jarvis-framework.toml; turning on "
                       "said-I'd-do suggestions needs a person to say yes, so it must be 'ask'")

_SETTINGS_LOCK = threading.Lock()
_SWITCH_LOCK = threading.Lock()
#: The card that is waiting, one at a time: {"id", "since"}. A second ON
#: while one waits answers "already waiting"; OFF withdraws it.
_WAITING: dict = {}
_WITHDRAWN: set = set()


def _config_dir() -> Path:
    """The folder memory.db and feedback.db are in, found the same way every
    switch here finds it."""
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / SETTINGS_FILE


def unspoken_enabled() -> bool:
    """Is the scanner on? No file, a file that never had the key, one that is
    damaged, or a value that is not true/false: OFF - fail closed, the safe
    direction is not reading the owner's words."""
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(doc, dict):
        return False
    value = doc.get("unspoken_commitments_enabled", False)
    return value is True


def _write_switch(on: bool) -> dict:
    with _SETTINGS_LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"unspoken_commitments_enabled": bool(on),
                                   "changed": time.time()}), encoding="utf-8")
        os.replace(tmp, p)
    return {"ok": True, "enabled": bool(on), "label": UNSPOKEN_LABEL}


def set_unspoken(on) -> dict:
    """Writes the switch. OFF is immediate and is never overwritten by a card
    still waiting; ON is only ever called after the owner's own yes."""
    return _write_switch(bool(on))


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        mod = sys.modules.get("jarvis_framework") or fw
        return str(mod.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-today-switch-card", daemon=True).start()


def _decide(pid: str, on: bool, gate: Callable, tier_of: Callable) -> None:
    """One card, in the background (the gate waits for the owner's answer).
    Only tier "ask" with outcome "approved" turns the switch on; denied,
    timed out, refused or turned off while the card waited changes nothing."""
    text = UNSPOKEN_ON_CARD
    try:
        v = gate(UNSPOKEN_ACTION,
                 {"text": text, "what": "read your own recent chat words for said-I'd-do "
                                        "suggestions (suggestions only)", "leaves_this_pc": False},
                 text)
    except Exception:
        _finish(pid)
        return
    if getattr(v, "tier", "unknown") != "ask" or tier_of(UNSPOKEN_ACTION) != "ask":
        _finish(pid)
        return
    if not (getattr(v, "allowed", False) is True
            and getattr(v, "outcome", "") == "approved"):
        _finish(pid)
        return
    with _SWITCH_LOCK:
        withdrawn = pid in _WITHDRAWN or _WAITING.get("id") != pid
        if not withdrawn:
            set_unspoken(True)
    _finish(pid)


def _finish(pid: str) -> None:
    with _SWITCH_LOCK:
        _WITHDRAWN.discard(pid)
        if _WAITING.get("id") == pid:
            _WAITING.clear()


def request_unspoken(enabled, *, gate: Optional[Callable] = None,
                     tier_of: Optional[Callable] = None,
                     spawn: Optional[Callable] = None) -> tuple:
    """POST /api/today/cockpit {"enabled": true|false} - (http code, body).
    ON is 202 while ONE approval card waits ("ask" tier); OFF is immediate.
    Same shape as `jarvis_screen_picture.request` and `jarvis_auto_learn`."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(enabled, bool):
        return 400, {"ok": False, "error": UNSPOKEN_BAD_BODY}
    if not enabled:
        with _SWITCH_LOCK:
            if _WAITING:
                # Withdrawn AND no longer the waiting card: approving it does
                # nothing, and a later ON raises a fresh card.
                _WITHDRAWN.add(str(_WAITING.get("id") or ""))
                _WAITING.clear()
        out = set_unspoken(False)
        out.update(waiting=False, message=UNSPOKEN_OFF_SAID)
        return 200, out
    if unspoken_enabled():
        return 200, {"ok": True, "enabled": True, "waiting": False,
                     "message": UNSPOKEN_ALREADY_ON}
    tier = tier_of(UNSPOKEN_ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": UNSPOKEN_TIER_WRONG.format(action=UNSPOKEN_ACTION,
                                                                     tier=tier)}
    with _SWITCH_LOCK:
        if _WAITING:
            return 202, {"ok": True, "waiting": True, "enabled": False,
                         "message": UNSPOKEN_ALREADY_WAITING}
        pid = uuid.uuid4().hex
        _WAITING.update(id=pid, since=time.time())
    try:
        spawn(lambda: _decide(pid, True, gate, tier_of))
    except Exception:
        _finish(pid)
        return 503, {"ok": False, "error": UNSPOKEN_CARD_FAILED}
    return 202, {"ok": True, "waiting": True, "enabled": False,
                 "message": UNSPOKEN_WAITING_SAID}
#: Words the commitment matcher ignores when it compares a proposal with an
#: existing reminder or card, so "call the dentist" covers "call the dentist
#: tomorrow" but not an unrelated sentence.
_MATCH_STOP = frozenset("""
a an the to on at for my me i you and or of in about this that with it its is
be do does get got go going will need have should must let remind please today
tomorrow tonight soon later then some just really
""".split())

#: The first-person ways the owner says they will do something themselves.
#: Plain, deterministic patterns - no model, and no guess at meaning beyond
#: these ("I'll be honest" is a false positive the owner can simply ignore;
#: nothing is created from a proposal without a tap).
_COMMITMENT = re.compile(
    r"\b(?:i['’]ll|i will|i need to|i have to|i['’]ve got to|i['’]m going to|"
    r"i am going to|i['’]m gonna|let me|remind me to|i must|i should|got to|gotta)\b",
    re.IGNORECASE)

#: The lead-in taken off the front, so the proposal reads as the action
#: ("remind me to call the bank" -> "call the bank").
_COMMITMENT_LEAD = re.compile(
    r"^(?:remind me to|i['’]ll|i will|i need to|i have to|i['’]ve got to|"
    r"i['’]m going to|i am going to|i['’]m gonna|let me|i must|i should|"
    r"got to|gotta)\s+", re.IGNORECASE)

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday")


def _num_or_none(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _due_row(job: dict, now: float, *, went_off: bool) -> dict:
    """One due reminder for the board: the scheduler's own fields, tidied.
    An optional GTD-1 field rides along only when the row really has it.
    `sensitive: true` (when jarvis_sensitive's plain patterns say so) tells
    the UI never to offer the break-into-steps chip for it - no model call."""
    due = _num_or_none(job.get("due"))
    row = {"id": str(job.get("id") or ""), "kind": str(job.get("kind") or ""),
           "text": str(job.get("text") or ""), "due": due,
           "when": str(job.get("when") or ""), "went_off": bool(went_off),
           "overdue": bool(went_off) or (due is not None and due < now - OVERDUE_GRACE)}
    fired = _num_or_none(job.get("fired_at"))
    if fired is not None:
        row["fired_at"] = fired
    for key in CONTEXT_KEYS:
        if key in job:
            row[key] = job[key]
    try:
        import jarvis_sensitive
        if jarvis_sensitive.topic(str(job.get("text") or "")):
            row["sensitive"] = True
    except Exception:
        pass
    return row


def due_reminders(sched, now: float) -> list:
    """Due and overdue reminders for the board, most useful first: what went
    off in the last hour (oldest scheduler read `went_off()`), then anything
    still active whose time has passed. Read-only - nothing is changed,
    fired or snoozed here."""
    out, seen = [], set()
    try:
        went = sched.went_off(now)
    except Exception:
        went = []
    for job in went:
        if not isinstance(job, dict) or job.get("kind") not in DUE_KINDS:
            continue
        jid = str(job.get("id") or "")
        if not jid or jid in seen:
            continue
        seen.add(jid)
        out.append(_due_row(job, now, went_off=True))
    try:
        jobs = sched.listed()
    except Exception:
        jobs = []
    for job in jobs:
        if not isinstance(job, dict) or job.get("kind") not in DUE_KINDS:
            continue
        jid = str(job.get("id") or "")
        due = _num_or_none(job.get("due"))
        if not jid or jid in seen or job.get("state") != "active" or due is None:
            continue
        if due > now:
            continue
        seen.add(jid)
        out.append(_due_row(job, now, went_off=False))
    out.sort(key=lambda r: (not r["went_off"], -r.get("fired_at", 0.0)
                            if r["went_off"] else (r.get("due") or 0.0)))
    return out[:MAX_DUE_REMINDERS]


def active_next_steps(sched, *, goals=None, projects=None) -> list:
    """The first open step of each active goal, and of each project whose
    work list still has open items. Read-only: no step is ticked, no goal
    accepted, no list changed. `goals` and `projects` are whatever
    jarvis_goals.get() / jarvis_projects.get() return, or a test's own store
    with the same public read methods - never their databases opened here."""
    out = []
    try:
        import jarvis_goals
        store = goals if goals is not None else jarvis_goals.get()
        for goal in store.list():
            if not isinstance(goal, dict) or goal.get("status") != "active":
                continue
            step = store.next_open_step(goal.get("id"))
            if not isinstance(step, dict) or not str(step.get("step") or "").strip():
                continue
            out.append({"kind": "goal", "id": str(goal.get("id") or ""),
                        "name": str(goal.get("text") or ""),
                        "step": str(step.get("step") or ""),
                        "by": str(step.get("by") or "")})
    except Exception:
        pass
    try:
        import jarvis_projects
        pstore = projects if projects is not None else jarvis_projects.get()
        open_todos = [t for t in sched.todos()
                      if isinstance(t, dict) and t.get("kind") == "todo"
                      and t.get("state") in ("active", "paused")]
        for project in pstore.list():
            if not isinstance(project, dict):
                continue
            work = project.get("work_list")
            if not isinstance(work, dict) or not str(work.get("name") or ""):
                continue
            first = next((t for t in open_todos
                          if t.get("list") == work.get("name")
                          and str(t.get("text") or "").strip()), None)
            if first is None:
                continue
            out.append({"kind": "project", "id": str(project.get("id") or ""),
                        "name": str(project.get("name") or ""),
                        "step": str(first.get("text") or ""), "by": ""})
    except Exception:
        pass
    return out[:MAX_NEXT_STEPS]


def _words(text) -> list:
    """A phrase as its content words, for the dedupe only. Never stored."""
    raw = str(text or "").casefold().replace("’", "'")
    return [w for w in re.findall(r"[a-z0-9']+", raw) if w not in _MATCH_STOP]


def _covered(text: str, known) -> bool:
    """Does an existing reminder or Today card already cover this proposal?
    True when the existing words are all in the proposal's own content words
    ("call the dentist" covers "call the dentist tomorrow") or the two are
    the same phrase. Deterministic and deliberately generous in one
    direction only: it can hide a proposal, never invent one."""
    want = set(_words(text))
    if not want:
        return False
    for other in known:
        have = set(_words(other))
        if have and have <= want:
            return True
    return False


def suggested_due(text, now: float) -> str:
    """The day the words themselves name, as YYYY-MM-DD, or "" when they
    name none. Plain words only: today, tomorrow, tonight, this evening,
    next week, "in N days", or a weekday name. Never a guess beyond those."""
    t = " ".join(str(text or "").casefold().split())
    base = datetime.date.fromtimestamp(now)
    day = None
    if "tomorrow" in t:
        day = base + datetime.timedelta(days=1)
    elif "next week" in t:
        day = base + datetime.timedelta(days=7)
    else:
        found = re.search(r"\bin (\d{1,2}) days?\b", t)
        if found:
            day = base + datetime.timedelta(days=min(int(found.group(1)), 60))
        elif any(x in t for x in ("tonight", "this evening", "today",
                                  "this afternoon", "this morning")):
            day = base
        else:
            for i, name in enumerate(_WEEKDAYS):
                if re.search(rf"\b{name}\b", t):
                    ahead = (i - base.weekday()) % 7 or 7
                    day = base + datetime.timedelta(days=ahead)
                    break
    return day.isoformat() if day is not None else ""


def scan_unspoken_commitments(turns, *, now: Optional[float] = None,
                              hidden: bool = False, enabled: Optional[bool] = None,
                              existing=(), ttl_days: Optional[int] = None) -> list:
    """Things the OWNER'S OWN WORDS say they will do, that nothing on the PC
    covers yet - strictly proposals: [{text, suggested_due, source_conv_id}].

    OFF unless the owner turned the switch on (`enabled=None` reads the real
    setting from `today.json`), and hidden=True (private lists hidden or App
    lock on) withholds everything as well. Pure and deterministic: same
    turns, same answer (pass `now` for a fixed clock). It reads only turns
    with `role == "user"`; a turn flagged `temporary` or `crisis` is never
    read; a turn older than `ttl_days` (default UNSPOKEN_TTL_DAYS) has faded
    and is not offered; `existing` is the words of open reminders and Today
    cards, so a commitment already covered is not proposed again. Nothing is
    created, changed, logged or sent anywhere - no model call, no socket."""
    if hidden:
        return []
    if enabled is None:
        enabled = unspoken_enabled()
    if enabled is not True:
        return []
    now = time.time() if now is None else float(now)
    ttl = UNSPOKEN_TTL_DAYS if ttl_days is None else int(ttl_days)
    known = [x for x in (existing or ()) if isinstance(x, str)]
    out, seen = [], set()
    for turn in turns or ():
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        if turn.get("temporary") is True or turn.get("crisis") is True:
            continue
        said_at = _num_or_none(turn.get("at"))
        if said_at is not None and now - said_at > ttl * 86400.0:
            continue                  # said too long ago: it has faded
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        cid = turn.get("source_conv_id") or turn.get("conversation") \
            or turn.get("conversation_id") or ""
        cid = cid if isinstance(cid, str) else ""
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            said = " ".join(sentence.split()).strip()
            if not said or "?" in said:
                continue
            found = _COMMITMENT.search(said)
            if found is None:
                continue
            words = _COMMITMENT_LEAD.sub("", said[found.start():], count=1)
            words = words.strip(" \t\r\n.,;:!-\"'“”‘’")
            if len(_words(words)) < 1:
                continue
            if len(words) > MAX_PROPOSAL_TEXT:
                words = words[:MAX_PROPOSAL_TEXT].rsplit(" ", 1)[0].strip(" ,;:-")
            key = " ".join(_words(words))
            if not key or key in seen or _covered(words, known):
                continue
            seen.add(key)
            out.append({"text": words, "suggested_due": suggested_due(words, now),
                        "source_conv_id": cid})
            if len(out) >= MAX_PROPOSALS:
                return out
    return out


def recent_owner_turns() -> list:
    """The owner's own turns from the newest few kept chats, through
    jarvis_chat_log's OWN public reads - this module never opens that
    database. Temporary chats are not kept at all, so they cannot appear; a
    crisis chat is kept but titled "A difficult moment", and every turn in
    it is flagged `crisis` so the scanner leaves it alone. A PC where the
    history cannot be opened answers [] (no proposals), never an error."""
    try:
        import jarvis_chat_log as L
    except Exception:
        return []
    try:
        code, listing = L.handle_get("/api/history",
                                     f"limit={RECENT_CONVERSATIONS}")
        if code != 200 or not isinstance(listing, dict):
            return []
        turns = []
        crisis_title = getattr(L, "CRISIS_TITLE", "A difficult moment")
        for conv in listing.get("conversations") or ():
            if not isinstance(conv, dict):
                continue
            cid = str(conv.get("id") or "")
            if not cid or conv.get("kind") not in ("chat", "live"):
                continue
            ccode, full = L.handle_get("/api/history/conversation", f"id={cid}")
            if ccode != 200 or not isinstance(full, dict):
                continue
            crisis = str(full.get("title") or "") == crisis_title
            for turn in full.get("turns") or ():
                if not isinstance(turn, dict) or turn.get("role") != "user":
                    continue
                turns.append({"role": "user", "text": str(turn.get("text") or ""),
                              "at": int(turn.get("at") or 0),
                              "conversation": cid, "temporary": False,
                              "crisis": crisis})
        return turns[-RECENT_TURNS:]
    except Exception:
        return []


def rollover_cards(*, now: Optional[float] = None) -> list:
    """Yesterday's unfinished Today cards, offered for 1-tap rollover - [] and
    honestly so. A Today card is a repeating rule ("Gym bag", every Monday
    and Wednesday at 07:00): jarvis_schedule keeps the rule, not a per-day
    occurrence, and nothing records "this card was on yesterday and is still
    undone". jarvis_briefing builds its parts fresh on every read and keeps
    nothing per day either. So there is NO real completion/occurrence signal
    to roll over, and this returns [] rather than inventing state. Building
    it needs a new per-day "done" record for Today cards (a schema change,
    not a read) - reported as NOT BUILDABLE in this slice."""
    return []


def cockpit_sections(sched, *, now: float, hidden: bool = False, turns=None,
                     goals=None, projects=None, unspoken: Optional[bool] = None) -> dict:
    """The Today board's payload: `{"available": True}` plus the switch's own
    state, the (always empty, and honestly so) rollover proposal, and a
    section ONLY when that section has something in it. That is the additive
    contract: with nothing due, no next step and no proposal, no new section
    key appears at all (`rollover_cards` and `unspoken_commitments_enabled`
    are this board's own contract, not a change to any older reply).
    `hidden=True` answers with nothing but the marker - no words at all."""
    if hidden:
        return {"available": True, "hidden": True}
    enabled = unspoken_enabled() if unspoken is None else unspoken is True
    out = {"available": True, "unspoken_commitments_enabled": enabled,
           "rollover_cards": rollover_cards(now=now)}
    due = due_reminders(sched, now)
    if due:
        out["due_reminders"] = due
    steps = active_next_steps(sched, goals=goals, projects=projects)
    if steps:
        out["active_next_steps"] = steps
    try:
        covered = [str(j.get("text") or "") for j in sched.listed()
                   if isinstance(j, dict) and j.get("kind") in
                   ("reminder", "alarm", KIND)]
    except Exception:
        covered = []
    proposals = scan_unspoken_commitments(turns or (), now=now, hidden=False,
                                          enabled=enabled, existing=covered)
    if proposals:
        out["proposals"] = proposals
    # Wave D-1 (D7): the Daily Pulse travels on the latest briefing (which
    # already read today's calendar/schedule) - no new read here. Absent when
    # no briefing has been made in this process yet, and never while hidden.
    try:
        import jarvis_briefing as _B
        pulse = (_B.latest() or {}).get("pulse")
        if isinstance(pulse, dict) and (pulse.get("lines") or pulse.get("where_to_look")):
            out["pulse"] = pulse
    except Exception:
        pass
    return out


def read_cockpit(*, sched=None, now: Optional[float] = None, hidden: bool = False,
                 turns=None, goals=None, projects=None,
                 unspoken: Optional[bool] = None) -> dict:
    """The whole board, from this PC's own reads. Never raises: a broken
    read answers `{"available": False, "why": <a sentence>}` so the page
    says so instead of showing an empty board that looks like a quiet day.
    Proposals are read only when the switch is on (no history is opened at
    all while it is off)."""
    try:
        sched = sched if sched is not None else _sched()
        now = float(sched.now() if now is None else now)
        enabled = unspoken_enabled() if unspoken is None else unspoken is True
        if turns is None and enabled and not hidden:
            turns = recent_owner_turns()
        return cockpit_sections(sched, now=now, hidden=hidden, turns=turns or (),
                                goals=goals, projects=projects, unspoken=enabled)
    except Exception:
        return {"available": False, "why": BOARD_FAILED}


def handle_cockpit_post(body) -> tuple:
    """POST /api/today/cockpit {"enabled": true|false} - the said-I'd-do
    switch. OFF is immediate; ON is ONE approval card (202 while it waits).
    Never raises."""
    if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
        return 400, {"ok": False, "error": UNSPOKEN_BAD_BODY}
    try:
        return request_unspoken(body["enabled"])
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}


def _query_flag(query, name: str) -> bool:
    """One yes/no flag out of a query string (or a parsed dict), read with
    plain string work: this module never imports a URL or a socket module,
    and the test that forbids them covers it."""
    raw = ""
    if isinstance(query, dict):
        raw = query.get(name, "")
    else:
        for part in str(query or "").split("&"):
            key, _, value = part.partition("=")
            if key == name:
                raw = value
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def handle_cockpit(query="") -> tuple:
    """GET /api/today/cockpit[?hidden=1] - (200, the board). A read behind
    the pairing token and origin check, like every private list. `hidden=1`
    comes from an app whose "Hide memory lists and chat history" or App lock
    is on; it withholds the words. `query` is the raw query string (a dict is
    accepted too). Never raises."""
    return 200, read_cockpit(hidden=_query_flag(query, "hidden"))
