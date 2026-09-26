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

A SECOND SOURCE: A PRIVATE CALENDAR LINK (the owner's decision, 2026-09-25)
Google Calendar cannot be read over CalDAV without OAuth. What Google offers
instead is "Secret address in iCal format" (Google Calendar -> Settings ->
the calendar -> Integrate calendar): a private https link to a read-only
.ics file of the whole calendar. `JARVIS_CALENDAR_ICS_SECRET_URL` holds it.
Anyone who has that link can read the calendar, so it is handled exactly
like a password:
  - the NAME has SECRET in it, so jarvis_child_env keeps it out of every
    program Jarvis starts (shell commands included), and jarvis_scrub
    replaces its value anywhere it would reach the log;
  - it is read fresh from the environment inside `_fetch_feed` only - it is
    never put in a Plan, a Query, a card (`describe()` names only the host,
    "calendar.google.com"), a result, or an error message (`_hide_link`);
  - it is sent only to the host it names, over https (plain http:// only
    inside the owner's own networks, the same rule as the CalDAV address),
    and a redirect is followed only to https on the same host or between
    Google's own calendar hosts, never anywhere else (`_FeedRedirect`).
When both are set, the private link wins and the card says the CalDAV
address was not read: one plan is one request, and someone who has just set
up the private link has said which calendar they mean. A Google calendar
cannot be reached over CalDAV anyway.

The feed is the WHOLE calendar, years of it, so `run()` reads at most
_MAX_BYTES of it (and for at most _READ_SECONDS), works out repeats, and
keeps only the events inside the requested days - on this PC. Google learns
that the link was used; it is not told which days Jarvis wanted.

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
read-only summary feature. `_read_event` instead reads the five fields
worth showing (SUMMARY, DTSTART, DTEND or DURATION, LOCATION, UID) and what
repeats need (RRULE, EXDATE, RECURRENCE-ID, STATUS), unfolds folded lines,
skips what is nested inside an event (a VALARM reminder's own SUMMARY), and
gives up cleanly on anything it does not recognise rather
than guessing - the same "report what did not match, do not invent" rule
`jarvis_ui_control.plan()`'s `unmatched` list already follows.

REPEATING EVENTS (since 2026-09-25, for both sources)
A private calendar link hands over each weekly meeting ONCE, with its first
date years ago and an RRULE saying how it repeats - so without working the
repeats out, nearly every real calendar would read as empty. `_expand`
works out the common rules, which is what Google writes: FREQ=DAILY,
WEEKLY, MONTHLY and YEARLY, with INTERVAL, COUNT, UNTIL, BYDAY (weekdays,
and "2TU"/"-1FR" in a month), BYMONTHDAY and BYMONTH, WKST, plus EXDATE
(a deleted occurrence) and RECURRENCE-ID (one occurrence moved or
cancelled). It is capped (_MAX_STEPS per rule, _EXPAND_BUDGET per read).
A rule it does not understand (BYSETPOS, BYWEEKNO, BYYEARDAY, BYHOUR, a
YEARLY BYDAY with no BYMONTH, RDATE) is NOT guessed at: the event is kept
once, at its first date, marked `rule_not_worked_out` - what every event
got before - so it is never silently lost.

TIME ZONES
A time with a TZID ("09:00 in Europe/London") is turned into an exact time
when Python can find that zone (`zoneinfo`). On Windows that needs the
`tzdata` package, which requirements.txt does NOT install; without it the
time is shown as this PC's own time, as before - right whenever the event's
zone is the PC's zone, which is the usual case, and an hour or more out when
it is not.

TESTING WITHOUT A REAL CALDAV SERVER
`plan()` takes an injectable `now`, so the time-range in the request body is
exact and deterministic in a test. `run()` takes an injectable `fetch`,
exactly how jarvis_research.py injects its own network call - the real
`_default_fetch` is the only thing that ever opens a socket, and it is never
called by anything in this file except itself.
"""


from __future__ import annotations

import calendar as _cal
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from datetime import time as _time_of_day
from typing import Callable, Optional

import jarvis_local_http

URL_ENV = "JARVIS_CALDAV_URL"
USER_ENV = "JARVIS_CALDAV_USER"
PASSWORD_ENV = "JARVIS_CALDAV_PASSWORD"

#: The private calendar link (Google's "Secret address in iCal format"). The
#: word SECRET in the name is load-bearing: jarvis_child_env keeps any such
#: name out of the programs Jarvis starts, and jarvis_scrub removes its value
#: from the log. test_calendar.py checks both.
ICS_URL_ENV = "JARVIS_CALENDAR_ICS_SECRET_URL"

# A calendar with hundreds of events in the window asked for is not a
# reading list, it is a data dump - capped the same way jarvis_agent's
# _tool_content caps any one tool's result, but here at the source, so the
# card itself never claims to show more than it will act on.
_MAX_EVENTS = 50
_MAX_FIELD_CHARS = 300

#: The most of one answer read, in bytes, and for how long. A private link
#: hands over the WHOLE calendar - every event since it was made - which for
#: a busy calendar kept for years is a few megabytes. Past the cap the rest
#: is not read, and the result says so (`incomplete`).
_MAX_BYTES = 10 * 1024 * 1024
_READ_SECONDS = 30.0
#: How long one wait for the server may take (connecting, or one read).
_TIMEOUT = 20.0

#: Google's own calendar hosts. A redirect from one to another is followed:
#: the link already belongs to Google. Nothing else is, see _FeedRedirect.
_GOOGLE_HOSTS = frozenset({"calendar.google.com", "www.google.com", "google.com"})
_MAX_REDIRECTS = 3

#: Working out repeats: at most this many periods (days, weeks, months or
#: years) looked at for one rule, and this many over one whole read. A rule
#: that needs more is not worked out (see "REPEATING EVENTS" above).
_MAX_STEPS = 20_000
_EXPAND_BUDGET = 400_000
#: Occurrences of one event kept inside the window asked for.
_MAX_PER_EVENT = 400

_REFUSED = "nothing is read; the calendar stays unknown to Jarvis"


def _feed_url() -> str:
    return os.environ.get(ICS_URL_ENV, "").strip()


def _configured() -> bool:
    return bool(os.environ.get(URL_ENV, "").strip()) or bool(_feed_url())


def authenticated() -> bool:
    """Whether a username is configured. Never reveals the password."""
    return bool(os.environ.get(USER_ENV, "").strip())


def source() -> str:
    """Which calendar a read would use: "ics" (the private link - it wins
    when both are set), "caldav", or "" for none. Reads no value out."""
    if _feed_url():
        return "ics"
    if os.environ.get(URL_ENV, "").strip():
        return "caldav"
    return ""


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(str(url or "")).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _is_google(host: str) -> bool:
    return host in _GOOGLE_HOSTS


def source_words() -> str:
    """How the apps and the card name the calendar that would be read -
    "your Google Calendar (private link)" - never the link itself."""
    if source() == "ics":
        if _is_google(_host(_feed_url())):
            return "your Google Calendar (private link)"
        return "your calendar (private link)"
    return "your calendar"


# --------------------------------------------------------------------------
#   The plan - one request, worked out locally, sent to no one yet
# --------------------------------------------------------------------------

@dataclass
class Query:
    """The one request this plan would make, in full - except the private
    link, which is never in here: see `private_link`."""
    url: str
    method: str
    body: str
    why: str = ""
    #: True for the private calendar link. `url` is then only its scheme and
    #: host ("https://calendar.google.com/"); the link itself is read from
    #: the environment by `_fetch_feed`, at the moment it is sent, and must
    #: still start with this `url` or nothing is sent.
    private_link: bool = False

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
    #: "caldav" or "ics" (the private link).
    source: str = "caldav"
    #: How the card names the calendar ("your Google Calendar (private link)").
    named: str = "your calendar"
    #: One more line for the card, e.g. that the CalDAV address was not read.
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def plan(days_ahead: int = 7, *, now: Optional[datetime] = None,
         end: Optional[datetime] = None) -> Plan:
    """Work out the one request that would read the next `days_ahead` days.

    Opens no socket - the request is built from the configured address and
    the current time only. `now` is injectable for exact, reproducible test
    ranges; real callers leave it as None and get the real current time.
    `end`, when given, is where the read stops instead of `days_ahead` whole
    24-hour days - the morning briefing reads "today" from local midnight to
    local midnight, which is 23 or 25 hours on the days the clocks change.
    """
    days_ahead = max(1, min(90, int(days_ahead)))
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    start = moment
    if end is not None:
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        end = min(max(end, start + timedelta(minutes=1)), start + timedelta(days=90))
    else:
        end = moment + timedelta(days=days_ahead)
    start_s, end_s = _ics_stamp(start), _ics_stamp(end)

    feed = _feed_url()
    if feed:
        return _plan_feed(feed, days_ahead, start_s, end_s)

    url = os.environ.get(URL_ENV, "").strip()
    if not url:
        return Plan(
            days_ahead=days_ahead, start=start_s, end=end_s, query=None,
            if_refused=_REFUSED, authenticated=authenticated(),
            reason_empty=(f"{URL_ENV} is not set (nor {ICS_URL_ENV}) - there is no "
                          "calendar to read"))
    # Security audit L7: no password over plain http:// off the owner's own networks.
    insecure = jarvis_local_http.plain_http_problem(url, URL_ENV, "the calendar password")
    if insecure:
        return Plan(
            days_ahead=days_ahead, start=start_s, end=end_s, query=None,
            if_refused=_REFUSED, authenticated=authenticated(), reason_empty=insecure)

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
        if_refused=_REFUSED, authenticated=authenticated())


def _feed_problem(feed: str) -> str:
    """"" when the private link may be sent, else the plain sentence saying
    why not. Never quotes the link - only, at most, its host."""
    try:
        parts = urllib.parse.urlsplit(feed)
        scheme, host = parts.scheme.lower(), (parts.hostname or "")
        parts.port                      # a port that is not a number raises here
        has_login = bool(parts.username or parts.password)
    except ValueError:
        return (f"{ICS_URL_ENV} is not an address Jarvis can read. Copy the private "
                "link again from your calendar's settings")
    if scheme == "webcal":
        return (f"{ICS_URL_ENV} starts with webcal://. Change webcal:// to https:// "
                "(the rest of the link stays the same) and Jarvis can read it")
    if scheme not in ("https", "http") or not host:
        return (f"{ICS_URL_ENV} is not a web address starting with https://. Copy the "
                "private link again from your calendar's settings")
    if has_login:
        return (f"{ICS_URL_ENV} has a user name or password written into it. A private "
                "calendar link needs neither - copy it again from your calendar's settings")
    if scheme == "http":
        return jarvis_local_http.plain_http_problem(feed, ICS_URL_ENV,
                                                    "the private calendar link")
    return ""


def _shown(feed: str) -> str:
    """The part of the private link that may be shown: scheme and host."""
    parts = urllib.parse.urlsplit(feed)
    host = (parts.hostname or "").lower().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    return f"{parts.scheme.lower()}://{host}{f':{port}' if port else ''}/"


def _plan_feed(feed: str, days_ahead: int, start_s: str, end_s: str) -> Plan:
    named = source_words()
    problem = _feed_problem(feed)
    if problem:
        return Plan(days_ahead=days_ahead, start=start_s, end=end_s, query=None,
                    if_refused=_REFUSED, authenticated=False, reason_empty=problem,
                    source="ics", named=named)
    note = ""
    if os.environ.get(URL_ENV, "").strip():
        note = (f"{URL_ENV} is set too. It is not read while the private link is set; "
                "clear one of the two to choose.")
    query = Query(
        url=_shown(feed), method="GET", body="", private_link=True,
        why=(f"download {named} and keep only the events between {start_s} and "
             f"{end_s}, on this PC"))
    return Plan(days_ahead=days_ahead, start=start_s, end=end_s, query=query,
                if_refused=_REFUSED, authenticated=False, source="ics", named=named,
                note=note)


def _ics_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def describe(p: Plan) -> str:
    """The card text. The literal request - never a summary of it - except
    the private link, which is a secret and is never shown."""
    if p.query is None:
        return (f"Jarvis would like to read the calendar for the next "
                f"{p.days_ahead} day(s), but {p.reason_empty}. Nothing would "
                "be sent.")
    if p.query.private_link:
        return _describe_feed(p)
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


def _describe_feed(p: Plan) -> str:
    host = _host(p.query.url)
    lines = [
        f"Jarvis would like to read {p.named}, for the events between {p.start} "
        f"and {p.end} ({p.days_ahead} day(s) ahead).",
        "",
        f"1 request, to {host}.",
        "No password is sent: the private link itself is the key, so it is never "
        "shown - not on this card, and not in Jarvis's log.",
        "",
        f"  GET {p.query.url}<the rest of your private link, hidden>",
        f"     why: {p.query.why}",
        "",
        f"What leaves this machine: the private link, sent only to {host}. It "
        "sends back the whole calendar, and Jarvis keeps only the days above, on "
        "this PC. Not your other files, not your conversation.",
    ]
    if p.note:
        lines += ["", p.note]
    lines += ["", f"If you say no: {p.if_refused}"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - one request, then a minimal, honest ICS read
# --------------------------------------------------------------------------

class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Stops a redirect from carrying the CalDAV password to another host.

    `urllib` copies every header except content-length/content-type onto the
    redirect target, cross-host included, so a 302 hands over Basic auth -
    which, unlike a bearer token, is the owner's actual reusable password in
    base64. Rule 3 says a credential is "sent only to the one service it
    authenticates against".

    Today this is also reached only for methods the handler redirects, and
    `REPORT` is not one of them - but that is an accident of which verb
    CalDAV happens to use, not a control. This is the control.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"refused to follow a redirect to {newurl}: the calendar password "
            f"would have been sent there. Point {URL_ENV} at the final address "
            f"instead.",
            headers,
            fp,
        )


class _LinkProblem(Exception):
    """A private-link read stopped here, before or while sending. Its
    message is written here and never holds the link."""


class _FeedRedirect(urllib.request.HTTPRedirectHandler):
    """Where a private link may be redirected, and where not.

    The secret is in the ADDRESS, not in a header, so a redirect cannot
    carry it anywhere by itself - but a redirect target made from the link
    (Google's own ones keep the path) is the link, and an address outside
    Google's hosts has no business receiving it. So a redirect is followed
    only to https:// on the same host, or from one of Google's calendar
    hosts to another (`_GOOGLE_HOSTS`; the link belongs to Google already);
    at most _MAX_REDIRECTS times. Anything else stops the read, and the
    message names only the host it pointed at, never the address."""

    max_redirections = _MAX_REDIRECTS
    max_repeats = 2

    def __init__(self, feed: str):
        super().__init__()
        parts = urllib.parse.urlsplit(feed)
        self.scheme = parts.scheme.lower()
        self.host = (parts.hostname or "").lower().rstrip(".")

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            parts = urllib.parse.urlsplit(newurl)
            scheme, host = parts.scheme.lower(), (parts.hostname or "").lower().rstrip(".")
        except ValueError:
            scheme, host = "", ""
        same = host == self.host and scheme in {"https", self.scheme}
        google = scheme == "https" and _is_google(host) and _is_google(self.host)
        if not (same or google):
            try:
                fp.close()
            except Exception:
                pass
            raise _LinkProblem(
                f"the calendar service tried to send Jarvis on to "
                f"{host or 'another address'}, and Jarvis did not follow: the private "
                f"link would have gone there too. Nothing was read")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Text(str):
    """What a fetch read. `cut` is True when the cap or the time limit
    stopped the reading early."""
    cut = False


def _read_capped(r, *, clock: Callable[[], float] = time.monotonic) -> str:
    """At most _MAX_BYTES of the answer, for at most _READ_SECONDS."""
    chunks, got, cut = [], 0, False
    t0 = clock()
    while True:
        b = r.read(65536)
        if not b:
            break
        chunks.append(b)
        got += len(b)
        if got > _MAX_BYTES or clock() - t0 > _READ_SECONDS:
            cut = True
            break
    out = _Text(b"".join(chunks)[:_MAX_BYTES].decode("utf-8", "replace"))
    out.cut = cut
    return out


def _default_fetch(q: Query) -> str:
    """The real call. For the private link, `_fetch_feed`. For CalDAV,
    Basic auth from the environment, read fresh - never cached, never
    logged, and never followed onto a redirect (see `_RefuseRedirect`).
    Raises on any non-2xx status; callers see that as a real error rather
    than an empty, misleadingly clean result."""
    if q.private_link:
        return _fetch_feed(q)
    user = os.environ.get(USER_ENV, "")
    password = os.environ.get(PASSWORD_ENV, "")
    req = urllib.request.Request(
        q.url, data=q.body.encode("utf-8"), method=q.method,
        headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "1"})
    if user:
        import base64
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")
    # Plain http:// (home network, Tailscale, Meshnet) never via a proxy -
    # jarvis_local_http.opener_for (security audit L7).
    opener = jarvis_local_http.opener_for(q.url, _RefuseRedirect)
    with opener.open(req, timeout=_TIMEOUT) as r:
        return _read_capped(r)


def _fetch_feed(q: Query) -> str:
    """The one GET of the private link. The link is read from the
    environment here, at the moment it is sent, and nowhere else; no
    header carries anything secret. The same checks as `plan()` run again,
    and the link must still point where the card said."""
    feed = _feed_url()
    if not feed:
        raise _LinkProblem(f"{ICS_URL_ENV} is no longer set, so there is nothing to read")
    problem = _feed_problem(feed)
    if problem:
        raise _LinkProblem(problem)
    if _shown(feed) != q.url:
        raise _LinkProblem("the private link was changed after this read was planned, "
                           "so it was not sent. Ask again")
    req = urllib.request.Request(feed, method="GET",
                                 headers={"Accept": "text/calendar, */*;q=0.5"})
    # https:// keeps urllib's usual proxy handling, where a proxy sees only
    # the host (the link travels inside the encrypted connection). Plain
    # http:// - allowed only inside the owner's own networks - never goes
    # through a proxy at all (jarvis_local_http.opener_for).
    opener = jarvis_local_http.opener_for(feed, _FeedRedirect(feed))
    with opener.open(req, timeout=_TIMEOUT) as r:
        return _read_capped(r)


_ANY_URL = re.compile(r"(?i)\b((?:https?|webcal)://[^/\s\"'<>]+)(/[^\s\"'<>]*)?")
_PRIVATE_BITS = re.compile(r"(?i)/calendar/ical/[^\s\"'<>]*|\bprivate-[0-9a-z]{8,}[^\s\"'<>]*")


def _hide_link(text) -> str:
    """`text` with the private link taken out, however it is written: its
    exact value (and URL-quoted), any address's path (only the host stays),
    and anything shaped like a Google private-feed path."""
    s = str(text or "")
    feed = _feed_url()
    if feed:
        forms = {feed, urllib.parse.quote(feed, safe=""), urllib.parse.quote(feed, safe=":/")}
        try:
            path = urllib.parse.urlsplit(feed).path
            if len(path) >= 8:
                forms.add(path)
        except ValueError:
            pass
        for v in sorted(forms, key=len, reverse=True):
            if v:
                s = s.replace(v, "[the private link]")
    s = _ANY_URL.sub(lambda m: m.group(1) + ("/[hidden]" if (m.group(2) or "/") != "/"
                                              else (m.group(2) or "")), s)
    return _PRIVATE_BITS.sub("[hidden]", s)


def _feed_failure(exc: BaseException) -> str:
    """Why a private-link read failed, in plain words, without the link."""
    if isinstance(exc, _LinkProblem):
        words = str(exc)
    elif isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code in (404, 410):
            words = (f"the calendar service says this private link does not exist "
                     f"({code}). If it was reset in the calendar's settings, set the new one")
        elif code in (401, 403):
            words = (f"the calendar service refused the private link ({code}). Copy it "
                     "again from the calendar's settings")
        else:
            words = f"the calendar service answered with an error ({code})"
    elif isinstance(exc, TimeoutError) or (isinstance(exc, urllib.error.URLError)
                                           and isinstance(exc.reason, TimeoutError)):
        words = "the calendar service did not answer in time"
    elif isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, socket.gaierror):
        words = ("could not look up the calendar service's address - is this PC "
                 "connected to the internet?")
    elif isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        words = ("could not reach the calendar service ("
                 + (str(reason) if isinstance(reason, str) else type(reason).__name__) + ")")
    else:
        words = f"{type(exc).__name__}: {exc}"
    return _hide_link(words)


# --------------------------------------------------------------------------
#   Reading the ICS text
# --------------------------------------------------------------------------

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


def _top_level(lines: list) -> list:
    """The event's own lines, without the components nested in it (VALARM:
    a reminder has a SUMMARY and a DESCRIPTION of its own)."""
    out, depth = [], 0
    for line in lines:
        up = line.upper()
        if up.startswith("BEGIN:"):
            depth += 1
        elif up.startswith("END:"):
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(line)
    return out


def _split_line(line: str):
    """(NAME, params, value) - the first ":" outside double quotes ends the
    name and parameters (a TZID may be quoted and hold a colon)."""
    quoted = False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            head, value = line[:i], line[i + 1:]
            name, _, params = head.partition(";")
            return name.strip().upper(), params, value.strip()
    return None


def _props(lines: list, name: str) -> list:
    """Every (params, value) for `name`, in order."""
    out = []
    for line in lines:
        got = _split_line(line)
        if got and got[0] == name:
            out.append((got[1], got[2]))
    return out


def _prop(lines: list, name: str):
    got = _props(lines, name)
    return got[0] if got else None


def _field(lines: list, name: str) -> Optional[str]:
    got = _prop(lines, name)
    return got[1] if got else None


def _param(params: str, key: str) -> str:
    for piece in params.split(";"):
        k, _, v = piece.partition("=")
        if k.strip().upper() == key:
            return v.strip().strip('"')
    return ""


def _text(value: str) -> str:
    """ICS text: "\\," is a comma, "\\;" a semicolon, "\\n" a line break."""
    return re.sub(r"\\([\\;,nN])", lambda m: " " if m.group(1) in "nN" else m.group(1),
                  value)


_ZONES: dict = {}


def _zone(tzid: str):
    """The time zone called `tzid`, or None when Python cannot find it (on
    Windows, without the `tzdata` package, it finds none - see TIME ZONES
    above). Never raises."""
    tzid = str(tzid or "").strip().strip('"')
    if not tzid:
        return None
    if tzid in _ZONES:
        return _ZONES[tzid]
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(tzid)
    except Exception:
        zone = None
    if len(_ZONES) < 256:
        _ZONES[tzid] = zone
    return zone


_STAMP_RE = re.compile(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?")


def _moment(params: str, value: str):
    """(kind, naive datetime, tzid) for a DTSTART-style value, or None.
    kind: "date" (all day), "utc" (ends in Z), "tz" (a TZID Python knows),
    "floating" (no zone, or one Python does not know: this PC's time)."""
    m = _STAMP_RE.fullmatch(str(value or "").strip().upper())
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m.group(4) is None:
            return ("date", datetime(y, mo, d), "")
        dt = datetime(y, mo, d, int(m.group(4)), int(m.group(5)), min(59, int(m.group(6))))
    except ValueError:
        return None
    if m.group(7):
        return ("utc", dt, "")
    tzid = _param(params, "TZID")
    if tzid and _zone(tzid) is not None:
        return ("tz", dt, tzid)
    return ("floating", dt, "")


def _epoch(kind: str, dt: datetime, tzid: str = "") -> float:
    """The exact moment, as seconds since 1970."""
    if kind == "utc":
        return float(_cal.timegm(dt.timetuple()))
    if kind == "tz":
        zone = _zone(tzid)
        if zone is not None:
            try:
                return dt.replace(tzinfo=zone).timestamp()
            except (OverflowError, OSError, ValueError):
                pass
    try:
        return time.mktime(dt.timetuple())          # this PC's own time
    except (OverflowError, OSError, ValueError):
        return float(_cal.timegm(dt.timetuple()))


def _naive(epoch: float, kind: str, tzid: str = "") -> datetime:
    """`epoch` as a wall-clock time in an event's own frame."""
    if kind == "utc":
        return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)
    if kind == "tz" and _zone(tzid) is not None:
        return datetime.fromtimestamp(epoch, _zone(tzid)).replace(tzinfo=None)
    return datetime.fromtimestamp(epoch)


def _fmt(dt: datetime, with_time: bool, z: bool = False) -> str:
    s = f"{dt.year:04d}{dt.month:02d}{dt.day:02d}"
    if with_time:
        s += f"T{dt.hour:02d}{dt.minute:02d}{dt.second:02d}" + ("Z" if z else "")
    return s


def _stamp(kind: str, dt: datetime, tzid: str = "") -> str:
    """The ICS stamp the rest of Jarvis reads (jarvis_briefing.event_when):
    a zoned time is given as UTC ("...Z"), so it shows at the right hour."""
    if kind == "date":
        return _fmt(dt, False)
    if kind == "utc":
        return _fmt(dt, True, True)
    if kind == "tz":
        try:
            return _fmt(datetime.fromtimestamp(_epoch(kind, dt, tzid), timezone.utc), True, True)
        except (OverflowError, OSError, ValueError):
            pass
    return _fmt(dt, True)


_DURATION_RE = re.compile(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")


def _duration(value: str) -> Optional[timedelta]:
    m = _DURATION_RE.fullmatch(str(value or "").strip().upper())
    if not m or not any(m.group(i) for i in range(2, 7)):
        return None
    w, d, h, mi, s = (int(m.group(i) or 0) for i in range(2, 7))
    length = timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)
    return timedelta(0) if m.group(1) == "-" else length


def _read_event(body: str) -> dict:
    """One VEVENT, the fields worth showing plus what repeats need."""
    lines = _top_level(_unfold(body))
    ds, de = _prop(lines, "DTSTART"), _prop(lines, "DTEND")
    start = _moment(*ds) if ds else None
    end = _moment(*de) if de else None
    length, has_end = timedelta(0), end is not None
    if start is not None:
        if end is not None:
            if end[0] == start[0] and end[2] == start[2]:
                length = end[1] - start[1]
            else:
                length = timedelta(seconds=_epoch(*end) - _epoch(*start))
        else:
            dur = _prop(lines, "DURATION")
            got = _duration(dur[1]) if dur else None
            has_end = got is not None
            length = got if got is not None else (
                timedelta(days=1) if start[0] == "date" else timedelta(0))
        length = max(length, timedelta(0))
    rid = _prop(lines, "RECURRENCE-ID")
    rrule = _prop(lines, "RRULE")
    exdates = []
    for params, value in _props(lines, "EXDATE"):
        for one in value.split(","):
            got = _moment(params, one)
            if got is not None:
                exdates.append(got)
    return {
        "summary": _text(_field(lines, "SUMMARY") or "(no title)")[:_MAX_FIELD_CHARS],
        "location": _text(_field(lines, "LOCATION") or "")[:_MAX_FIELD_CHARS],
        "uid": _field(lines, "UID") or "",
        "raw_start": ds[1] if ds else "", "raw_end": de[1] if de else "",
        "start": start, "length": length, "has_end": has_end,
        "rrule": rrule[1] if rrule else None,
        "exdates": exdates,
        "rid": _moment(*rid) if rid else None,
        "cancelled": (_field(lines, "STATUS") or "").strip().upper() == "CANCELLED",
    }


def _keys(m) -> set:
    """How an occurrence is matched against EXDATE and RECURRENCE-ID: its
    exact moment, or its day for an all-day one."""
    kind, dt, tzid = m
    if kind == "date":
        return {("day", dt.date())}
    return {("at", int(round(_epoch(kind, dt, tzid))))}


def _out(ev: dict, m=None, *, recurring: bool, unworked: bool = False) -> dict:
    if m is None:
        start, end = ev["raw_start"], ev["raw_end"]
    else:
        kind, dt, tzid = m
        start = _stamp(kind, dt, tzid)
        end = _stamp(kind, dt + ev["length"], tzid) if ev["has_end"] else ""
    row = {"summary": ev["summary"], "start": start, "end": end,
           "location": ev["location"], "uid": ev["uid"], "recurring": recurring}
    if unworked:
        row["rule_not_worked_out"] = True
    return row


def _overlaps(ev: dict, m, ws: float, we: float) -> bool:
    kind, dt, tzid = m
    s = _epoch(kind, dt, tzid)
    e = _epoch(kind, dt + ev["length"], tzid)
    return s < we and (e > ws or (e <= s and s >= ws))


# --------------------------------------------------------------------------
#   Repeating events
# --------------------------------------------------------------------------

_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_RULE_PARTS = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "WKST"}
_BYDAY_RE = re.compile(r"([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)")


def _rule(text: str) -> Optional[dict]:
    """An RRULE this module can work out, or None for one it cannot."""
    parts = {}
    for piece in str(text or "").split(";"):
        if not piece.strip():
            continue
        k, sep, v = piece.partition("=")
        if not sep:
            return None
        parts[k.strip().upper()] = v.strip().upper()
    if not set(parts) <= _RULE_PARTS:
        return None
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return None
    try:
        interval = int(parts.get("INTERVAL", "1"))
        count = int(parts["COUNT"]) if "COUNT" in parts else None
        bymonth = [int(x) for x in parts["BYMONTH"].split(",")] if "BYMONTH" in parts else []
        bymonthday = ([int(x) for x in parts["BYMONTHDAY"].split(",")]
                      if "BYMONTHDAY" in parts else [])
    except ValueError:
        return None
    if interval < 1 or (count is not None and count < 1):
        return None
    if any(not 1 <= m <= 12 for m in bymonth):
        return None
    if any(d == 0 or not -31 <= d <= 31 for d in bymonthday):
        return None
    if bymonthday and freq == "WEEKLY":
        return None                       # not allowed with WEEKLY (RFC 5545)
    byday = []
    if "BYDAY" in parts:
        for item in parts["BYDAY"].split(","):
            m = _BYDAY_RE.fullmatch(item.strip())
            if not m:
                return None
            n = int(m.group(1)) if m.group(1) else 0
            if m.group(1) and (freq not in ("MONTHLY", "YEARLY") or n == 0
                               or not -5 <= n <= 5):
                return None
            byday.append((n, _WEEKDAYS[m.group(2)]))
    if freq == "YEARLY" and byday and not bymonth:
        return None                       # "the 20th Monday of the year": not worked out
    wkst = _WEEKDAYS.get(parts.get("WKST", "MO"))
    if wkst is None:
        return None
    until = None
    if "UNTIL" in parts:
        until = _moment("", parts["UNTIL"])
        if until is None:
            return None
    return {"freq": freq, "interval": interval, "count": count, "until": until,
            "byday": byday, "bymonth": bymonth, "bymonthday": bymonthday, "wkst": wkst}


def _month_day(d: int, last: int) -> int:
    v = d if d > 0 else last + 1 + d
    return v if 1 <= v <= last else 0


def _days_in_month(y: int, m: int, rule: dict, first: datetime) -> list:
    last = _cal.monthrange(y, m)[1]
    if rule["byday"]:
        days = set()
        for n, wd in rule["byday"]:
            offset = (wd - _cal.weekday(y, m, 1)) % 7
            matching = list(range(1 + offset, last + 1, 7))
            if n == 0:
                days.update(matching)
            elif 0 < n <= len(matching):
                days.add(matching[n - 1])
            elif n < 0 and -n <= len(matching):
                days.add(matching[n])
        if rule["bymonthday"]:
            days &= {_month_day(d, last) for d in rule["bymonthday"]}
        return sorted(days)
    if rule["bymonthday"]:
        return sorted({v for v in (_month_day(d, last) for d in rule["bymonthday"]) if v})
    return [first.day] if first.day <= last else []


def _periods(rule: dict, first: datetime, k0: int):
    """(the period's first day, [candidate days in it]) in order, from the
    k0-th period on. A period is a day, a week, a month or a year."""
    freq, iv = rule["freq"], rule["interval"]
    fd = first.date()
    weekdays = {wd for _, wd in rule["byday"]}
    k = k0
    while True:
        if freq == "DAILY":
            d = fd + timedelta(days=k * iv)
            ok = ((not rule["bymonth"] or d.month in rule["bymonth"])
                  and (not weekdays or d.weekday() in weekdays)
                  and (not rule["bymonthday"] or d.day in {
                      _month_day(x, _cal.monthrange(d.year, d.month)[1])
                      for x in rule["bymonthday"]}))
            yield d, ([d] if ok else [])
        elif freq == "WEEKLY":
            week = (fd - timedelta(days=(fd.weekday() - rule["wkst"]) % 7)
                    + timedelta(weeks=k * iv))
            wds = sorted(weekdays or {fd.weekday()}, key=lambda wd: (wd - rule["wkst"]) % 7)
            days = [week + timedelta(days=(wd - rule["wkst"]) % 7) for wd in wds]
            yield week, [d for d in days if not rule["bymonth"] or d.month in rule["bymonth"]]
        elif freq == "MONTHLY":
            y, m0 = divmod(fd.year * 12 + fd.month - 1 + k * iv, 12)
            m = m0 + 1
            days = ([] if rule["bymonth"] and m not in rule["bymonth"]
                    else [date(y, m, d) for d in _days_in_month(y, m, rule, first)])
            yield date(y, m, 1), days
        else:
            y = fd.year + k * iv
            months = rule["bymonth"] or (list(range(1, 13)) if rule["bymonthday"]
                                         else [fd.month])
            days = []
            for m in sorted(months):
                days += [date(y, m, d) for d in _days_in_month(y, m, rule, first)]
            yield date(y, 1, 1), days
        k += 1


def _skip(rule: dict, first: datetime, lo: datetime) -> int:
    """How many whole periods can be skipped before `lo` - only when there
    is no COUNT, which has to be counted from the start."""
    iv, fd, ld = rule["interval"], first.date(), lo.date()
    if ld <= fd:
        return 0
    if rule["freq"] == "DAILY":
        n = (ld - fd).days
    elif rule["freq"] == "WEEKLY":
        n = (ld - fd).days // 7
    elif rule["freq"] == "MONTHLY":
        n = (ld.year - fd.year) * 12 + ld.month - fd.month
    else:
        n = ld.year - fd.year
    return max(0, n // iv - 1)


def _expand(ev: dict, rule: dict, ws: float, we: float, budget: list, moved: set):
    """The occurrences of a repeating event inside [ws, we), as moments.
    Returns (moments, worked_out). worked_out is False when a cap stopped
    it; the caller then keeps the event once, as before."""
    kind, first, tzid = ev["start"]
    length = ev["length"]
    at = first.time() if kind != "date" else _time_of_day(0)
    try:
        lo = _naive(ws, kind, tzid) - length - timedelta(days=2)
        hi = _naive(we, kind, tzid) + timedelta(days=2)
    except (OverflowError, OSError, ValueError):
        return [], False
    excluded = set(moved)
    for m in ev["exdates"]:
        excluded |= _keys(m)
    until = rule["until"]
    until_epoch = None if until is None or until[0] == "date" else _epoch(*until)

    def past_until(occ: datetime) -> bool:
        if until is None:
            return False
        if until[0] == "date":
            return occ.date() > until[1].date()
        return _epoch(kind, occ, tzid) > until_epoch

    found = []

    def consider(occ: datetime) -> None:
        m = (kind, occ, tzid)
        keys = _keys(m) | {("day", occ.date())}
        if keys & excluded:
            return
        if _overlaps(ev, m, ws, we) and len(found) < _MAX_PER_EVENT:
            found.append(m)

    n = 1                                  # DTSTART is always the first occurrence
    if not past_until(first):
        consider(first)
    k0 = 0 if rule["count"] else _skip(rule, first, lo)
    steps = 0
    try:
        for period, days in _periods(rule, first, k0):
            steps += 1
            budget[0] -= 1
            if steps > _MAX_STEPS or budget[0] <= 0:
                return [], False
            if datetime.combine(period, _time_of_day(0)) > hi:
                return found, True
            for d in days:
                occ = datetime.combine(d, at)
                if occ <= first:
                    continue
                n += 1
                if rule["count"] is not None and n > rule["count"]:
                    return found, True
                if past_until(occ) or occ > hi:
                    return found, True
                if occ + length >= lo:
                    consider(occ)
    except (OverflowError, ValueError):
        return found, True                # past the year 9999
    return found, True


def _may_occur(ev: dict, ws: float, we: float) -> bool:
    """For a repeat that is not worked out: could it fall in the window at
    all? It starts before the window ends and has not ended (UNTIL) before
    it begins."""
    if _epoch(*ev["start"]) >= we:
        return False
    m = re.search(r"UNTIL=([0-9TZ]+)", str(ev["rrule"] or "").upper())
    until = _moment("", m.group(1)) if m else None
    if until is not None:
        end = _epoch(*until) + (86400 if until[0] == "date" else 0)
        if end < ws:
            return False
    return True


def _events_between(text: str, ws: float, we: float, *, trust_server: bool) -> list:
    """Every event in `text` that falls in [ws, we), repeats worked out, in
    time order. `trust_server` (CalDAV): the server already chose the events
    for this window, so a single event is kept as it came, and a repeat
    whose occurrences are not found here is kept once, as before - nothing
    the server said is in the window is dropped."""
    raw = []
    for block in _CALENDAR_DATA_RE.findall(text) or [text]:
        for body in _VEVENT_RE.findall(block):
            raw.append(_read_event(body))
    moved: dict = {}
    for ev in raw:
        if ev["rid"] is not None and ev["uid"]:
            moved.setdefault(ev["uid"], set()).update(_keys(ev["rid"]))
    budget = [_EXPAND_BUDGET]
    rows = []
    for ev in raw:
        if ev["cancelled"]:
            continue
        start = ev["start"]
        if start is None:
            if trust_server:
                rows.append((float("inf"), _out(ev, recurring=ev["rrule"] is not None)))
            continue
        first_at = _epoch(*start)
        if ev["rrule"] is not None and ev["rid"] is None:
            rule = _rule(ev["rrule"])
            found, worked = (_expand(ev, rule, ws, we, budget, moved.get(ev["uid"], set()))
                             if rule else ([], False))
            if worked:
                for m in found:
                    rows.append((_epoch(*m), _out(ev, m, recurring=True)))
                if not found and trust_server:
                    rows.append((first_at, _out(ev, start, recurring=True)))
            elif trust_server or _may_occur(ev, ws, we):
                rows.append((first_at, _out(ev, start, recurring=True, unworked=True)))
            continue
        if trust_server or _overlaps(ev, start, ws, we):
            rows.append((first_at, _out(ev, start, recurring=ev["rid"] is not None)))
    rows.sort(key=lambda r: r[0])
    return [r[1] for r in rows]


def _window(stamp: str) -> float:
    return float(_cal.timegm(datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").timetuple()))


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
        text = getter(p.query)
    except Exception as exc:
        if p.query.private_link:
            reason = _feed_failure(exc)
        else:
            reason = f"{type(exc).__name__}: {exc}"
        return {"ok": False, "reason": f"the request failed: {reason}", "events": []}

    cut = bool(getattr(text, "cut", False))
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text[:_MAX_BYTES + 1]).decode("utf-8", "replace")
    text = str(text or "")
    if len(text) > _MAX_BYTES:
        text, cut = text[:_MAX_BYTES], True

    events = _events_between(text, _window(p.start), _window(p.end),
                             trust_server=not p.query.private_link)
    out = {"ok": True, "events": events[:_MAX_EVENTS],
           "truncated": len(events) > _MAX_EVENTS, "start": p.start, "end": p.end}
    if cut:
        out["incomplete"] = True
        out["note"] = (f"the calendar was larger than Jarvis reads at once "
                       f"({_MAX_BYTES // (1024 * 1024)} MB, or {int(_READ_SECONDS)} "
                       "seconds), so some events may be missing")
    return out
