"""jarvis_briefing.py - the morning briefing: a short list of the day,
put together on this PC WITHOUT the AI model.

NEW MODULE, shipped whole (briefing.patch adds the routes).

THE OWNER'S DECISIONS THAT SHAPE IT (2026-09-25, CLAUDE.md)
  * ONE scheduler. The briefing is a KIND of job on jarvis_schedule.py
    (register_kind, below), not a loop of its own: the same clock, the same
    missed-while-the-PC-was-off rule, the same `schedule` event, and the same
    Coming up list in both apps, where it can be paused or deleted.
  * Anything that repeats ("every weekday at 7") asks ONCE, with the
    scheduler's own `schedule_repeat` card listing the next three times.
    A one-off ("brief me tomorrow at 7") needs no card.
  * Each run only READS. Nothing here acts, approves or changes a setting.
  * Rule 1: email, files, credentials and memory stay on this PC. The
    briefing is assembled in code, not written by a model - so it works when
    the model is slow, unloaded or asleep, and nothing of it is sent to any
    model, local or cloud. It is kept in this process's memory only (the
    latest one), never written to disk, and never put on the event bus.

WHAT IS IN IT - only what Jarvis can already read on this PC
  * Today's calendar events - only when the calendar is set up for Jarvis
    (JARVIS_CALDAV_URL, or the private calendar link
    JARVIS_CALENDAR_ICS_SECRET_URL - Google Calendar's - and `calendar_read`
    in [tools].enabled), read through
    jarvis_calendar.py's one read-only request, and only when the gate lets
    that read run without a person (tier "auto" or "notify", the shipped
    "auto"). Tier "ask": it is left out and the briefing says why - a
    briefing at 7 in the morning does not raise a card to read a calendar.
  * Today's alarms, reminders and timers still to come, and the open to-do
    items (jarvis_schedule.py).
  * How many approval cards are waiting (jarvis_gate.pending()). A number,
    and "open Jarvis to answer" - never an Approve.
  * Only when email is set up the same way (JARVIS_IMAP_HOST, `email_check`
    in [tools].enabled, `email_read` not "ask"): HOW MANY unread emails -
    the number only (jarvis_email.count(): no sender, subject or text is
    ever fetched). Whether senders should be shown is the owner's call and
    is not built.
  * Weather and news: NOT AVAILABLE. No provider has been chosen, so the
    briefing says so in a line of its own and fetches nothing from the
    internet.

WHERE IT SHOWS
Both apps: a notification with only "Jarvis: your morning briefing is
ready." (the kind's lock-screen words - never the briefing's own, on a lock
screen or a Windows toast, whatever the privacy settings), which opens the
briefing in the app (desktop: Brain -> Work; phone: Mind). The words are
read from `GET /api/briefing` behind the token. "Hide memory lists and
chat history" hides the lines and keeps the counts. It is read aloud only
when the owner asks ("read my briefing", jarvis_quick.py), and then under
the apps' existing private-answer rule (it is marked private).

The `schedule` event for a briefing: "fired" when its time comes (the
scheduler's own), then "ready" once it is put together - the apps notify on
"ready", so the notification is never ahead of the briefing.

OFFERS
The briefing makes no offer of its own - it never suggests setting itself
up, or anything else. If one is ever added, it goes through
jarvis_backoff.py first, like every other offer.
"""
from __future__ import annotations

import calendar as _cal
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

import jarvis_schedule as S

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Words - both apps say the same (jarvis-desktop/src/briefing.js,
#   jarvis-client net/Briefing.kt)
# --------------------------------------------------------------------------

KIND = "briefing"
NOUN = "morning briefing"
TITLE = "Morning briefing"

#: All a lock screen, a Windows toast or a phone notification ever shows.
LOCK_SCREEN = "Jarvis: your morning briefing is ready."

OUTSIDE_LINE = ("Weather and news: not available. No provider has been chosen, "
                "so Jarvis fetches nothing from the internet for this.")

EMPTY = "No briefing yet. Say \"brief me now\", or set one up to arrive each morning."

#: The lines on the schedule_repeat card, in place of its usual paragraph.
CARD_NOTE = (
    "Each time, Jarvis puts together a short list on this PC, without the AI model:",
    "  - today's calendar events, if your calendar is set up for Jarvis",
    "  - today's alarms, reminders and timers, and your to-do list",
    "  - how many approval cards are waiting",
    "  - how many unread emails you have (the number only), if email is set up",
    "Weather and news are not included: no provider has been chosen.",
    "It only reads. It changes nothing and approves nothing.",
    "",
    "It runs on this PC, by this PC's clock. Reading your calendar and email is a "
    "request to your own calendar and mail servers, the same as asking Jarvis to "
    "read them, under the same settings. Nothing else is sent anywhere, and nothing "
    "goes to the AI model.",
    "The apps say only \"" + LOCK_SCREEN + "\"; the briefing is in the app. It is "
    "read aloud only when you ask (\"read my briefing\").",
)

#: How long the calendar and email reads may take together, in seconds.
READ_DEADLINE = 25.0

#: How many lines one section lists.
MAX_ITEMS = 8
MAX_TODO_ITEMS = 5
MAX_ITEM_CHARS = 120

CALENDAR_ACTION = "calendar_read"
EMAIL_ACTION = "email_read"
CALENDAR_TOOL = "calendar_read"
EMAIL_TOOL = "email_check"

S.register_kind(KIND, NOUN, LOCK_SCREEN, has_text=False, owner_listed=True,
                repeatable=True, card_note=CARD_NOTE,
                on_fire=lambda job_id: _on_fire(job_id))

# --------------------------------------------------------------------------
#   What touches the outside - replaceable, so the tests open no socket
# --------------------------------------------------------------------------


def _tier_of(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tools_enabled() -> set:
    try:
        cfg = fw.load_framework() if fw is not None else {}
        return set((cfg.get("tools") or {}).get("enabled") or [])
    except Exception:
        return set()


def _pending_count() -> Optional[int]:
    try:
        import jarvis_gate
        return len(jarvis_gate.pending() or [])
    except Exception:
        return None


def _publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


@dataclass
class Deps:
    tier_of: Callable[[str], str] = _tier_of
    gate: Callable = _gate
    tools_enabled: Callable[[], set] = _tools_enabled
    pending_count: Callable[[], Optional[int]] = _pending_count
    calendar_fetch: Optional[Callable] = None     # jarvis_calendar.run's `fetch`
    email_search: Optional[Callable] = None       # jarvis_email.count's `search`
    publish: Callable[[str, dict], None] = _publish
    deadline: float = READ_DEADLINE


# --------------------------------------------------------------------------
#   Plain words
# --------------------------------------------------------------------------

def _plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _join(items: list) -> str:
    items = [str(i) for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _clean(text, cap: int = MAX_ITEM_CHARS) -> str:
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or ""))
    t = " ".join(t.split())
    if len(t) > cap:
        t = t[:cap - 3].rstrip() + "..."
    return t


def _date_words(t: float) -> str:
    lt = time.localtime(t)
    return f"{S.WEEKDAYS[lt.tm_wday]} {lt.tm_mday} {S.MONTHS[lt.tm_mon - 1]}"


def _today(now: float) -> tuple:
    """(start, end) of today by this PC's clock, as epochs."""
    lt = time.localtime(now)
    start = S.wall_to_epoch(lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0)
    y, mo, d = S._add_days(lt.tm_year, lt.tm_mon, lt.tm_mday, 1)
    return start, S.wall_to_epoch(y, mo, d, 0, 0)


def _section(key: str, title: str, state: str, summary: str, items=None) -> dict:
    return {"key": key, "title": title, "state": state, "summary": summary,
            "items": list(items or [])}


# --------------------------------------------------------------------------
#   Where each part comes from, and whether it can be read without a person
# --------------------------------------------------------------------------

def _env(deps: Deps, name: str) -> str:
    # The same variables jarvis_calendar.py and jarvis_email.py read, read
    # the same way: fresh, from the environment, every time.
    import os
    return str(os.environ.get(name, "") or "").strip()


def _calendar_words() -> str:
    try:
        import jarvis_calendar as CAL
        return CAL.source_words()
    except Exception:
        return "your calendar"


def sources(deps: Optional[Deps] = None) -> dict:
    """What a briefing would include, without reading anything: for the
    apps' settings ("Your calendar: included"). Opens no socket."""
    deps = deps or Deps()
    enabled = deps.tools_enabled()

    def one(tool: str, action: str, env_names, what: str) -> dict:
        names = (env_names,) if isinstance(env_names, str) else tuple(env_names)
        if tool not in enabled or not any(_env(deps, n) for n in names):
            return {"state": "off",
                    "said": f"Not included: {what} is not set up for Jarvis on this PC."}
        tier = deps.tier_of(action)
        if tier not in ("auto", "notify"):
            return {"state": "asks",
                    "said": f"Not included: your settings ask for a yes each time Jarvis "
                            f"reads {what}, and a briefing does not raise a card for that."}
        return {"state": "on", "said": f"Included: {what}."}

    return {
        # Either calendar source counts (jarvis_calendar.source()); the words
        # name the one in use - "your Google Calendar (private link)" - and
        # never the link itself.
        "calendar": one(CALENDAR_TOOL, CALENDAR_ACTION,
                        ("JARVIS_CALDAV_URL", "JARVIS_CALENDAR_ICS_SECRET_URL"),
                        _calendar_words()),
        "email": one(EMAIL_TOOL, EMAIL_ACTION, "JARVIS_IMAP_HOST",
                     "how many unread emails you have"),
        "weather": {"state": "not_available", "said": OUTSIDE_LINE},
    }


# --------------------------------------------------------------------------
#   The calendar - today's events, read-only
# --------------------------------------------------------------------------

_STAMP = re.compile(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?")


def event_when(raw: str) -> Optional[tuple]:
    """(date (y, m, d) by this PC's clock, "HH:MM" or None for all day) for
    an ICS DTSTART value, or None when it cannot be read.

    A time ending in Z is UTC, turned into this PC's time. A time with no Z
    ("floating", or with a TZID parameter this minimal reader does not
    follow) is taken as this PC's own time - said plainly in
    docs/JARVIS-API.md, since an event kept in another time zone shows at
    the wrong hour."""
    m = _STAMP.fullmatch(str(raw or "").strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if m.group(4) is None:
        return (y, mo, d), None
    hh, mm, ss = int(m.group(4)), int(m.group(5)), int(m.group(6) or 0)
    if m.group(7):
        try:
            lt = time.localtime(_cal.timegm((y, mo, d, hh, mm, ss, 0, 0, 0)))
        except (OverflowError, ValueError):
            return None
        return (lt.tm_year, lt.tm_mon, lt.tm_mday), f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    return (y, mo, d), f"{hh:02d}:{mm:02d}"


def calendar_items(events: list, now: float) -> list:
    """Today's events as lines, all-day ones first, then by time."""
    lt = time.localtime(now)
    today = (lt.tm_year, lt.tm_mon, lt.tm_mday)
    rows = []
    for e in events or []:
        if not isinstance(e, dict):
            continue
        summary = _clean(e.get("summary") or "(no title)")
        when = event_when(e.get("start") or "")
        repeats = bool(e.get("recurring"))
        if when is None:
            rows.append(((2, "99:99"), f"{summary} (time not readable)"))
            continue
        day, hhmm = when
        tail = ""
        if day != today:
            # The calendar says it is on today: a repeating event whose rule
            # jarvis_calendar could not work out (so its first date is what
            # is shown - the common rules ARE worked out, and then the date
            # is today's), or one that began earlier and is still going.
            tail = " (repeats)" if repeats else " (continues from an earlier day)"
        if hhmm is None:
            rows.append(((0, ""), f"All day: {summary}{tail}"))
        else:
            rows.append(((1, hhmm), f"{hhmm} {summary}{tail}"))
    rows.sort(key=lambda r: r[0])
    return [r[1] for r in rows]


def _read_calendar(now: float, deps: Deps) -> dict:
    title = "Calendar"
    import jarvis_calendar as CAL
    start, _ = _today(now)
    p = CAL.plan(1, now=datetime.fromtimestamp(start, tz=timezone.utc))
    if p.query is None:
        return _section("calendar", title, "failed",
                        "Not read: the calendar's settings on this PC need a look "
                        "(backend/README.md, the calendar).")
    text = CAL.describe(p)
    try:
        v = deps.gate(CALENDAR_ACTION, {"text": text, "for": "the morning briefing"}, text)
    except Exception:
        v = None
    if getattr(v, "allowed", False) is not True:
        return _section("calendar", title, "refused",
                        "Not read: the approval gate did not let this read run.")
    out = CAL.run(p, fetch=deps.calendar_fetch, approved=True)
    if not out.get("ok"):
        return _section("calendar", title, "failed",
                        "Not read: the calendar server did not answer.")
    items = calendar_items(out.get("events") or [], now)
    if not items:
        return _section("calendar", title, "empty", "Nothing on your calendar today." + (
            " Some events may be missing: the calendar is larger than Jarvis reads at once."
            if out.get("incomplete") else ""))
    shown = items[:MAX_ITEMS]
    more = len(items) - len(shown)
    summary = _plural(len(items), "event") + " today" + ("" if not out.get("truncated")
                                                         else " (the first 50 read)")
    if out.get("incomplete"):
        # A private calendar link hands over the whole calendar; past
        # jarvis_calendar's cap the rest is not read.
        summary += (". Some may be missing: the calendar is larger than Jarvis "
                    "reads at once")
    if more > 0:
        shown.append(f"... and {more} more")
    return _section("calendar", title, "ok", summary + ".", shown)


def _read_email(deps: Deps) -> dict:
    title = "Email"
    import jarvis_email as MAIL
    p = MAIL.plan(1, unread_only=True)
    if not p.configured:
        return _section("email", title, "failed", "Not read: email's settings on this PC "
                                                  "need a look.")
    text = ("Jarvis would like to count the unread messages in the \"" + p.mailbox
            + "\" mailbox on " + p.host + ":" + str(p.port) + " for the morning briefing: "
            "one connection, search UNSEEN, the number only - no sender, subject or text "
            "is read.")
    try:
        v = deps.gate(EMAIL_ACTION, {"text": text, "for": "the morning briefing"}, text)
    except Exception:
        v = None
    if getattr(v, "allowed", False) is not True:
        return _section("email", title, "refused",
                        "Not read: the approval gate did not let this read run.")
    out = MAIL.count(p, search=deps.email_search, approved=True)
    if not out.get("ok"):
        return _section("email", title, "failed", "Not read: the mail server did not answer.")
    n = int(out.get("count") or 0)
    return _section("email", title, "ok",
                    "No unread email." if n == 0 else _plural(n, "unread email") + ".")


def _in_thread(fn, *args) -> tuple:
    box: dict = {}

    def work():
        try:
            box["out"] = fn(*args)
        except Exception as exc:
            box["error"] = type(exc).__name__
    t = threading.Thread(target=work, name="jarvis-briefing-read", daemon=True)
    t.start()
    return t, box


# --------------------------------------------------------------------------
#   The parts read from this PC
# --------------------------------------------------------------------------

def _today_section(sched, now: float) -> dict:
    _, end = _today(now)
    rows = []
    kinds = {"alarm": 0, "reminder": 0, "timer": 0}
    for j in sched.listed():
        k = j.get("kind")
        if k not in kinds or j.get("state") != "active":
            continue
        due = j.get("due")
        if not isinstance(due, (int, float)) or due >= end or due < now - 60:
            continue
        kinds[k] += 1
        words = _clean(j.get("text") or "")
        again = " (repeats)" if j.get("repeats") else ""
        if k == "timer":
            name = f"{words} timer" if words else "Timer"
            line = f"{name} - {S.length_words(max(0.0, due - now))} left"
        elif k == "alarm":
            line = f"{S.clock(due)} alarm" + (f": {words}" if words else "") + again
        else:
            line = f"{S.clock(due)} {words or 'reminder'}{again}"
        rows.append((due, line))
    rows.sort(key=lambda r: r[0])
    parts = [_plural(n, k) for k, n in kinds.items() if n]
    if not parts:
        return _section("today", "Today", "empty", "Nothing else set for today.")
    items = [r[1] for r in rows[:MAX_ITEMS]]
    if len(rows) > MAX_ITEMS:
        items.append(f"... and {len(rows) - MAX_ITEMS} more")
    return _section("today", "Today", "ok", _join(parts) + " still to come today.", items)


def _todo_section(sched, now: float) -> dict:
    todos = sched.todos()
    if not todos:
        return _section("todo", "To-do list", "empty", "Nothing on your to-do list.")
    items = []
    for t in todos[:MAX_TODO_ITEMS]:
        line = _clean(t.get("text") or "")
        due = t.get("due")
        if isinstance(due, (int, float)):
            line += f" (due {S.when_words(due, now)})"
        items.append(line)
    if len(todos) > MAX_TODO_ITEMS:
        items.append(f"... and {len(todos) - MAX_TODO_ITEMS} more")
    return _section("todo", "To-do list", "ok", _plural(len(todos), "open item") + ".", items)


def _approvals_section(deps: Deps) -> dict:
    n = deps.pending_count()
    if n is None:
        return _section("approvals", "Approvals", "failed",
                        "Could not count the approval cards.")
    if n == 0:
        return _section("approvals", "Approvals", "empty", "No approval cards waiting.")
    return _section("approvals", "Approvals", "ok",
                    ("1 card is" if n == 1 else f"{n} cards are")
                    + " waiting for your yes or no. Open Jarvis to answer.")


# --------------------------------------------------------------------------
#   Putting it together
# --------------------------------------------------------------------------

def render(b: dict) -> str:
    """The briefing as plain lines - the chat answer and the apps' text."""
    lines = [b["heading"]]
    if b.get("missed"):
        lines.append(f"(Due {b['missed'].replace('missed at ', 'at ')} - the PC was off or "
                     f"asleep, so it is late.)")
    for s in b["sections"]:
        lines.append(f"{s['title']}: {s['summary']}")
        lines.extend(f"- {i}" for i in s["items"])
    lines.append(OUTSIDE_LINE)
    for n in b.get("not_included") or []:
        lines.append(n)
    return "\n".join(lines)


def build(*, sched=None, now: Optional[float] = None, deps: Optional[Deps] = None,
          source: str = "now", job: Optional[str] = None, missed: str = "") -> dict:
    """One briefing. Reads only; acts on nothing; opens a socket only for
    the calendar and email reads, and only as their own settings allow."""
    deps = deps or Deps()
    sched = sched or S.get()
    now = time.time() if now is None else now
    src = sources(deps)
    started = time.time()
    reads = {}
    if src["calendar"]["state"] == "on":
        reads["calendar"] = _in_thread(_read_calendar, now, deps)
    if src["email"]["state"] == "on":
        reads["email"] = _in_thread(_read_email, deps)
    sections = []
    not_included = []
    if src["calendar"]["state"] != "on":
        not_included.append(src["calendar"]["said"])
    if src["email"]["state"] != "on" and src["email"]["state"] != "off":
        not_included.append(src["email"]["said"])
    today = _today_section(sched, now)
    todo = _todo_section(sched, now)
    approvals = _approvals_section(deps)
    got = {}
    for key, (thread, box) in reads.items():
        thread.join(max(0.0, deps.deadline - (time.time() - started)))
        title = "Calendar" if key == "calendar" else "Email"
        if thread.is_alive():
            got[key] = _section(key, title, "slow", "Not read: it did not answer in time.")
        elif "out" in box:
            got[key] = box["out"]
        else:
            got[key] = _section(key, title, "failed", "Not read: something went wrong "
                                                      f"({box.get('error', 'unknown')}).")
    if "calendar" in got:
        sections.append(got["calendar"])
    sections.extend([today, todo, approvals])
    if "email" in got:
        sections.append(got["email"])
    b = {
        "id": "b" + uuid.uuid4().hex[:10],
        "made": now,
        "date": _date_words(now),
        "heading": f"Your briefing for {_date_words(now)}, made at {S.clock(now)}.",
        "source": source,
        "job": job,
        "missed": missed,
        "late": bool(missed),
        "private": True,
        "sections": sections,
        "not_included": not_included,
        # Outside text in the lines (calendar titles come from the calendar
        # server): a chat answer that quotes them marks the conversation as
        # having read outside text, like the calendar tool would.
        "read": [CALENDAR_ACTION] if any(s["key"] == "calendar" and s["items"]
                                         for s in sections) else [],
        "lock_screen": LOCK_SCREEN,
    }
    b["text"] = render(b)
    return b


# --------------------------------------------------------------------------
#   The latest one - in memory only
# --------------------------------------------------------------------------

_LATEST: dict = {"briefing": None, "building": 0}
_LATEST_LOCK = threading.Lock()
_BUILD_LOCK = threading.Lock()


def latest() -> Optional[dict]:
    with _LATEST_LOCK:
        b = _LATEST["briefing"]
        return dict(b) if b else None


def building() -> bool:
    with _LATEST_LOCK:
        return _LATEST["building"] > 0


def make(*, sched=None, now: Optional[float] = None, deps: Optional[Deps] = None,
         source: str = "now", job: Optional[str] = None, missed: str = "") -> dict:
    """Build one and keep it as the latest. One at a time."""
    with _LATEST_LOCK:
        _LATEST["building"] += 1
    try:
        with _BUILD_LOCK:
            b = build(sched=sched, now=now, deps=deps, source=source, job=job, missed=missed)
        with _LATEST_LOCK:
            _LATEST["briefing"] = b
        return dict(b)
    finally:
        with _LATEST_LOCK:
            _LATEST["building"] -= 1


def forget() -> None:
    """For the tests: no briefing kept."""
    with _LATEST_LOCK:
        _LATEST["briefing"] = None


def _on_fire(job_id: str, *, sched=None, deps: Optional[Deps] = None) -> None:
    """A briefing job went off (the scheduler calls this on its own thread,
    after its "fired" event). Build it, keep it, then ring "ready" - always,
    even when a part could not be read, so the apps are never left waiting."""
    deps = deps or Deps()
    try:
        sched = sched or S.get()
        view = sched.job(job_id) or {}
        make(sched=sched, deps=deps, source="schedule", job=job_id,
             missed=str(view.get("missed") or ""))
    finally:
        deps.publish("schedule", {"id": job_id, "kind": KIND, "state": "ready"})


# --------------------------------------------------------------------------
#   Routes (briefing.patch hands the request here)
# --------------------------------------------------------------------------

def setups(sched=None) -> list:
    """The briefing jobs on the list (active, paused, or waiting for a card)."""
    sched = sched or S.get()
    return [j for j in sched.listed() if j.get("kind") == KIND]


def handle_get(sched=None, deps: Optional[Deps] = None) -> tuple:
    """GET /api/briefing - the latest briefing (or null), whether one is
    being put together, the briefing jobs, and what a briefing includes.
    Behind the token: the lines are the owner's own day."""
    return 200, {"available": True, "briefing": latest(), "building": building(),
                 "setups": setups(sched), "sources": sources(deps),
                 "title": TITLE, "lock_screen": LOCK_SCREEN, "empty": EMPTY}


def handle_now(body=None, sched=None, deps: Optional[Deps] = None) -> tuple:
    """POST /api/briefing/now {} - put one together now and answer with it.
    Reads only (it is not held on a stale link in either app, like every
    read). Up to READ_DEADLINE seconds when the calendar or mail server is
    slow."""
    if body is not None and not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    try:
        b = make(sched=sched, deps=deps, source="now")
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}
    return 200, {"ok": True, "briefing": b}
