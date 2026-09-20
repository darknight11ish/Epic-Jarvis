"""jarvis_calendar.py - lets Jarvis read the owner's own calendar. Nothing else.

WHAT IT IS FOR
docs/ANDROID-FEATURE-AUDIT.md named this directly: "Calendar (CalDAV), notes
(Obsidian/Joplin local REST), home (Home Assistant's MCP server) - read-only
first, no cloud keys." CalDAV is the open, self-hosted calendar protocol
(Nextcloud, Radicale, Baikal, Fastmail, and others all speak it) - the owner
points this at their own server with their own username/password, exactly
the same shape jarvis_research.py already uses for `JARVIS_GITHUB_TOKEN`.
There is no Google/Microsoft OAuth flow here and none is planned: OAuth
needs a registered app and a cloud key this project has always avoided, and
the whole point of choosing CalDAV is that it does not.

THE PERMISSION MODEL, WHICH IS THE POINT
    plan(days_ahead)      Works out the ONE request this would make - the
                          literal CalDAV REPORT body, with the exact time
                          range - against configured credentials. Opens no
                          socket. Returns a Plan.
    run(plan, approved)   Executes that one request and parses whatever
                          VEVENT blocks come back into a bounded, capped
                          list Jarvis can read out or put in the digest.

Same two-step split as jarvis_research.py, and the same reason: a request
that leaves this machine - even to the owner's own private server, even to
read rather than to act - is not something this module decides to send on
its own. `docs/ARCHITECTURE.md` section 4 draws the egress boundary at
exactly this line ("Three lanes leave the machine. Nothing else may.") and
this module is a fourth, added the same deliberate way
`jarvis_browser_control.py` was: named, documented, gated, and off by
default until the owner turns it on. See backend/README.md's
`calendar-wiring` section for the exact `jarvis_gate`/`jarvis-framework.toml`
lines this needs and the tier this ships with.

WHY THIS SHIPS TIER "auto" WHERE `browser_control` SHIPS "ask"
Judgment call, stated as one so it can be argued with: every step
`jarvis_browser_control.py` takes either sends something to a real person on
the other end or lands on a page nobody has looked at yet, so it can never
default to unattended. Reading this calendar changes nothing, sends nothing
to anyone, and reaches a server the owner runs for themselves - the same
"nothing is sent, nothing acts" reasoning that already makes `jarvis_gate`'s
`_plan` actions (including `jarvis_research.plan()`'s own) `auto` rather than
`ask`. If that reasoning is wrong for a given owner's threat model, one line
in `jarvis-framework.toml` (`calendar_read = "ask"`) overrides it - the
module does not decide its own tier, `jarvis_gate.py` does, same as always.

CREDENTIALS - NEVER STORED HERE, NEVER LOGGED, NEVER ON A CARD
`JARVIS_CALDAV_URL`, `JARVIS_CALDAV_USER`, `JARVIS_CALDAV_PASSWORD` are read
fresh from the environment on every call, exactly like
`jarvis_research.TOKEN_ENV`. This module never writes them to disk and never
puts the password in a `Plan`, a `Query`, or `describe()`'s output -
`describe()` says only THAT the request is authenticated, never with what,
matching `jarvis_research.describe()`'s own auth line.

WHY THE ICS PARSER IS DELIBERATELY MINIMAL
A real RFC 5545 calendar can nest VALARM, VTIMEZONE, RRULE recurrence, and
line-folding across a hard 75-octet limit. Depending on a real icalendar
library would be the first new PyPI dependency this project takes for a
read-only summary feature. `_parse_vevents` instead reads exactly the five
fields worth showing (SUMMARY, DTSTART, DTEND, LOCATION, UID), unfolds
folded lines, and gives up cleanly on anything it does not recognise rather
than guessing - the same "report what did not match, do not invent" rule
`jarvis_ui_control.plan()`'s `unmatched` list already follows. A recurring
event's RRULE is surfaced as raw text, not expanded into individual
occurrences; expanding recurrence correctly is exactly the kind of subtly
wrong date arithmetic this module would rather not ship un-reviewed.

TESTING WITHOUT A REAL CALDAV SERVER
`plan()` takes an injectable `now`, so the time-range in the request body is
exact and deterministic in a test. `run()` takes an injectable `fetch`,
exactly how jarvis_research.py injects its own network call - the real
`_default_fetch` is the only thing that ever opens a socket, and it is never
called by anything in this file except itself.
"""

from __future__ import annotations

import os
import re
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

URL_ENV = "JARVIS_CALDAV_URL"
USER_ENV = "JARVIS_CALDAV_USER"
PASSWORD_ENV = "JARVIS_CALDAV_PASSWORD"

# A calendar with hundreds of events in the window asked for is not a
# reading list, it is a data dump - capped the same way jarvis_agent's
# _tool_content caps any one tool's result, but here at the source, so the
# card itself never claims to show more than it will act on.
_MAX_EVENTS = 50
_MAX_FIELD_CHARS = 300


def _configured() -> bool:
    return bool(os.environ.get(URL_ENV, "").strip())


def authenticated() -> bool:
    """Whether a username is configured. Never reveals the password."""
    return bool(os.environ.get(USER_ENV, "").strip())


# --------------------------------------------------------------------------
#   The plan - one request, worked out locally, sent to no one yet
# --------------------------------------------------------------------------

@dataclass
class Query:
    """The one CalDAV request this plan would make, in full."""
    url: str
    method: str
    body: str
    why: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    days_ahead: int
    start: str
    end: str
    query: Optional[Query] = None
    if_refused: str = ""
    authenticated: bool = False
    # Set instead of building a Query when nothing is configured to ask -
    # `describe()` says so plainly rather than printing a request to nowhere.
    reason_empty: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def plan(days_ahead: int = 7, *, now: Optional[datetime] = None) -> Plan:
    """Work out the one request that would read the next `days_ahead` days.

    Opens no socket - the request body is built from the configured URL and
    the current time only. `now` is injectable for exact, reproducible test
    ranges; real callers leave it as None and get the real current time.
    """
    days_ahead = max(1, min(90, int(days_ahead)))
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    start = moment
    end = moment + timedelta(days=days_ahead)
    start_s, end_s = _ics_stamp(start), _ics_stamp(end)

    url = os.environ.get(URL_ENV, "").strip()
    if not url:
        return Plan(
            days_ahead=days_ahead, start=start_s, end=end_s, query=None,
            if_refused="nothing is read; the calendar stays unknown to Jarvis",
            authenticated=authenticated(),
            reason_empty=f"{URL_ENV} is not set - there is no calendar to read")

    body = (
        '<?xml version="1.0" encoding="utf-8" ?>\n'
        '<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">\n'
        "  <D:prop>\n"
        "    <D:getetag/>\n"
        "    <C:calendar-data/>\n"
        "  </D:prop>\n"
        "  <C:filter>\n"
        '    <C:comp-filter name="VCALENDAR">\n'
        '      <C:comp-filter name="VEVENT">\n'
        f'        <C:time-range start="{start_s}" end="{end_s}"/>\n'
        "      </C:comp-filter>\n"
        "    </C:comp-filter>\n"
        "  </C:filter>\n"
        "</C:calendar-query>\n"
    )
    query = Query(
        url=url, method="REPORT", body=body,
        why=f"read events between {start_s} and {end_s} from the owner's own calendar")
    return Plan(
        days_ahead=days_ahead, start=start_s, end=end_s, query=query,
        if_refused="nothing is read; the calendar stays unknown to Jarvis",
        authenticated=authenticated())


def _ics_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def describe(p: Plan) -> str:
    """The card text. The literal request body - never a summary of it."""
    if p.query is None:
        return (f"Jarvis would like to read the calendar for the next "
                f"{p.days_ahead} day(s), but {p.reason_empty}. Nothing would "
                "be sent.")
    auth_line = (
        "Authenticated: this will send the configured CalDAV username and "
        "password to that server, over that one request."
        if p.authenticated else
        "No credentials are configured - this request will very likely be "
        "refused by the server, which requires them for nearly every real "
        "CalDAV deployment."
    )
    lines = [
        f"Jarvis would like to read calendar events between {p.start} and "
        f"{p.end} ({p.days_ahead} day(s) ahead).",
        "",
        f"1 request, to {p.query.url}.",
        auth_line,
        "",
        f"  REPORT {p.query.url}",
        f"     why: {p.query.why}",
        "     body:",
    ]
    lines += [f"       {line}" for line in p.query.body.splitlines()]
    lines += [
        "",
        "What leaves this machine: the time range above, and the "
        "credentials if configured. Not your other files, not your "
        "conversation.",
        "",
        f"If you say no: {p.if_refused}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - one request, then a minimal, honest ICS read
# --------------------------------------------------------------------------

def _default_fetch(q: Query) -> str:
    """The real CalDAV call. Basic auth from the environment, read fresh -
    never cached, never logged. Raises on any non-2xx status; callers see
    that as a real error rather than an empty, misleadingly clean result."""
    user = os.environ.get(USER_ENV, "")
    password = os.environ.get(PASSWORD_ENV, "")
    req = urllib.request.Request(
        q.url, data=q.body.encode("utf-8"), method=q.method,
        headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "1"})
    if user:
        import base64
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=20.0) as r:
        return r.read().decode("utf-8", "replace")


_CALENDAR_DATA_RE = re.compile(
    r"<[^>:]*:?calendar-data[^>]*>(.*?)</[^>:]*:?calendar-data>",
    re.IGNORECASE | re.DOTALL)
_VEVENT_RE = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.IGNORECASE | re.DOTALL)


def _unfold(ics: str) -> list:
    """RFC 5545 line folding: a continuation line starts with a single
    space or tab and is logically part of the previous line."""
    raw = ics.replace("\r\n", "\n").split("\n")
    out: list = []
    for line in raw:
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line.strip():
            out.append(line)
    return out


def _field(lines: list, name: str) -> Optional[str]:
    prefix = name.upper() + ":"
    prefix_param = name.upper() + ";"
    for line in lines:
        upper = line.upper()
        if upper.startswith(prefix):
            return line[len(prefix):].strip()
        if upper.startswith(prefix_param) and ":" in line:
            return line.split(":", 1)[1].strip()
    return None


def _parse_vevents(xml_text: str) -> list:
    """Every VEVENT block found, across every `calendar-data` the server
    returned - minimal fields only, see the module docstring for why."""
    events = []
    blocks = _CALENDAR_DATA_RE.findall(xml_text) or [xml_text]
    for block in blocks:
        for match in _VEVENT_RE.findall(block):
            lines = _unfold(match)
            summary = _field(lines, "SUMMARY") or "(no title)"
            events.append({
                "summary": summary[:_MAX_FIELD_CHARS],
                "start": _field(lines, "DTSTART") or "",
                "end": _field(lines, "DTEND") or "",
                "location": (_field(lines, "LOCATION") or "")[:_MAX_FIELD_CHARS],
                "uid": _field(lines, "UID") or "",
                "recurring": _field(lines, "RRULE") is not None,
            })
            if len(events) >= _MAX_EVENTS:
                return events
    return events


def run(p: Plan, *, fetch: Optional[Callable[[Query], str]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan. `approved` has no default of True.

    `fetch` is injectable so the parsing below - the part actually worth
    testing - can be proven with no socket, the same technique
    jarvis_research.py's own `run()` uses.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was read",
                "plan": p.as_dict()}
    if p.query is None:
        return {"ok": False, "reason": p.reason_empty, "events": []}

    getter = fetch or _default_fetch
    try:
        xml_text = getter(p.query)
    except Exception as exc:
        return {"ok": False, "reason": f"the request failed: {type(exc).__name__}: {exc}",
                "events": []}

    events = _parse_vevents(xml_text)
    truncated = len(events) >= _MAX_EVENTS
    return {"ok": True, "events": events, "truncated": truncated,
            "start": p.start, "end": p.end}
