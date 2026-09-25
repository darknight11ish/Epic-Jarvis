"""jarvis_calendar.py's second source: a private calendar link (Google
Calendar's "Secret address in iCal format"), and the promise that the link
never shows up anywhere but the one request to the service it belongs to.

    python3 test_calendar_link.py

The link is a secret - whoever has it can read the calendar - so every
place it could leak is checked with a fake one: the plan, the card, the
result the model reads, every error, the log (jarvis_scrub, by shape and by
value), the programs Jarvis starts (jarvis_child_env), the cloud lane
(jarvis_router), the morning briefing and what it puts on the bus, and a
real request to a stand-in server on this PC, with its redirects and its
size cap. The fake link is built from pieces (never one literal), so no
secret-shaped string sits in this file.

No request leaves this PC: the only server is on 127.0.0.1, started here.
"""
import http.server
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_calendar.py", "jarvis_local_http.py", "jarvis_scrub.py",
                "jarvis_child_env.py", "jarvis_agent.py", "jarvis_briefing.py",
                "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_calendar as C  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# The fake private link, from pieces. 32 hex characters, like Google's.
TOKEN = "private-" + "0f1e2d3c" * 4
CAL_ID = "owner" + "%40" + "example.com"
LINK = "https://calendar.google.com/calendar/ical/" + CAL_ID + "/" + TOKEN + "/basic.ics"
#: Every form the link could leak in.
FORMS = (LINK, TOKEN, CAL_ID, urllib.parse.quote(LINK, safe=""), "0f1e2d3c" * 4)

NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)


def leaks(obj, forms=FORMS):
    """The forms of the link found in `obj` (as JSON text), or []."""
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    return [f for f in forms if f in text]


class Env:
    """Sets (value) or clears (None) environment variables for one block."""

    def __init__(self, **values):
        self.values = values

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in self.values}
        for k, v in self.values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def link_env(link=LINK, caldav=None):
    return Env(JARVIS_CALENDAR_ICS_SECRET_URL=link, JARVIS_CALDAV_URL=caldav,
               JARVIS_CALDAV_USER=None, JARVIS_CALDAV_PASSWORD=None)


class NoNetwork:
    """Any outgoing connection, in this block, is a failure."""

    def __enter__(self):
        self.real = socket.socket.connect

        def boom(*a, **k):
            raise AssertionError("a socket was opened")

        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


FEED = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Google Inc//Google Calendar 70.9054//EN",
    "BEGIN:VEVENT", "DTSTART:20260916T140000Z", "DTEND:20260916T150000Z",
    "UID:dentist@google.com", "SUMMARY:Dentist", "END:VEVENT",
    # Years ago, weekly on Thursday: must show on 17 September 2026.
    "BEGIN:VEVENT", "DTSTART:20200102T090000Z", "DTEND:20200102T093000Z",
    "RRULE:FREQ=WEEKLY;BYDAY=TH", "UID:standup@google.com", "SUMMARY:Stand-up",
    "END:VEVENT",
    # Outside the window: must not show.
    "BEGIN:VEVENT", "DTSTART:20250101T100000Z", "DTEND:20250101T110000Z",
    "UID:old@google.com", "SUMMARY:Long ago", "END:VEVENT",
    "BEGIN:VEVENT", "DTSTART:20261201T100000Z", "DTEND:20261201T110000Z",
    "UID:later@google.com", "SUMMARY:Much later", "END:VEVENT",
    "END:VCALENDAR", ""])


# ── the plan and the card: the link is never in either ─────────────────────

with link_env():
    with NoNetwork():
        p = C.plan(7, now=NOW)
        text = C.describe(p)
    check("plan() opens no socket for the private link either", True)
    check("the private link is the source", C.source() == "ics" and p.source == "ics")
    check("a query is built: one GET, marked as the private link",
          p.query is not None and p.query.method == "GET" and p.query.private_link is True)
    check("the query holds only the scheme and host", p.query.url == "https://calendar.google.com/",
          p.query.url)
    check("the plan holds no form of the link (as_dict, as the gate and a refusal see it)",
          not leaks(p.as_dict()), leaks(p.as_dict()))
    check("the card holds no form of the link", not leaks(text), leaks(text))
    check("the card names it plainly, and the host",
          "your Google Calendar (private link)" in text and "calendar.google.com" in text, text)
    check("the card says the link is the key and is never shown",
          "never shown" in text and "No password is sent" in text, text)
    check("the card says what leaves: only the link, only to that host",
          "sent only to calendar.google.com" in text, text)
    unapproved = C.run(p)
    check("run() without approval reads nothing, and its answer holds no link",
          unapproved["ok"] is False and not leaks(unapproved), unapproved)

with link_env(caldav="https://cal.example.com/dav/"):
    p = C.plan(3, now=NOW)
    check("both set: the private link wins", p.source == "ics" and p.query.private_link)
    check("... and the card says the CalDAV address was not read",
          "JARVIS_CALDAV_URL is set too" in C.describe(p), C.describe(p))

with link_env(link="https://cal.example.org/feeds/" + TOKEN + "/cal.ics"):
    p = C.plan(3, now=NOW)
    check("another service's private link is named without claiming it is Google's",
          p.named == "your calendar (private link)" and "cal.example.org" in C.describe(p))

# ── addresses refused before anything is sent, and never quoted ───────────

REFUSED = (
    ("webcal://" + LINK[len("https://"):], "Change webcal:// to https://"),
    ("ftp://calendar.google.com/" + TOKEN, "https://"),
    ("file:///C:/Users/me/" + TOKEN + ".ics", "https://"),
    ("http://calendar.google.com/calendar/ical/" + CAL_ID + "/" + TOKEN + "/basic.ics",
     "unencrypted"),
    ("https://me:pw@calendar.google.com/calendar/ical/" + TOKEN, "user name or password"),
    ("https://calendar.google.com:notaport/" + TOKEN, "not an address"),
)
for bad, words in REFUSED:
    with link_env(link=bad):
        p = C.plan(7, now=NOW)
        card = C.describe(p)
        check(f"refused, with the reason ({words!r}), before anything is sent",
              p.query is None and words in p.reason_empty, p.reason_empty)
        check("... and the refusal does not quote the link",
              not leaks(card, FORMS + (bad,)), card)

with link_env(link="http://192.168.1.20:8080/" + TOKEN + "/basic.ics"):
    check("CONTROL: plain http:// inside the home network is planned (the owner's rule)",
          C.plan(7, now=NOW).query is not None)

# ── run(): the window is picked out here, and the answer holds no link ─────

with link_env():
    p = C.plan(7, now=NOW)
    seen = []
    out = C.run(p, fetch=lambda q: seen.append(q) or FEED, approved=True)
    names = [e["summary"] for e in out["events"]]
    check("the fetch was handed no form of the link", not leaks([q.as_dict() for q in seen]))
    check("only the events inside the week asked for", names == ["Dentist", "Stand-up"], names)
    check("the weekly repeat shows on its date in this week",
          out["events"][1]["start"] == "20260917T090000Z", out["events"])
    check("the result holds no form of the link", not leaks(out), leaks(out))

# ── every failure: the reason never holds the link ─────────────────────────

FAILURES = (
    ("an exception quoting the link", ValueError("unknown url type: " + LINK)),
    ("an exception quoting the link URL-quoted", OSError("bad " + urllib.parse.quote(LINK, safe=""))),
    ("an exception quoting the path only", OSError("GET /calendar/ical/" + CAL_ID + "/"
                                                   + TOKEN + "/basic.ics failed")),
    ("a 404 carrying the link as its address",
     urllib.error.HTTPError(LINK, 404, "Not Found", {}, None)),
    ("a 403", urllib.error.HTTPError(LINK, 403, "Forbidden " + LINK, {}, None)),
    ("a connection failure", urllib.error.URLError(OSError("no route to " + LINK))),
    ("a timeout", TimeoutError("timed out reading " + LINK)),
    ("a name that cannot be looked up",
     urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))),
    ("a reason that is text quoting the link", urllib.error.URLError("unknown url type: " + LINK)),
)
with link_env():
    p = C.plan(7, now=NOW)
    for name, exc in FAILURES:
        def boom(q, exc=exc):
            raise exc
        res = C.run(p, fetch=boom, approved=True)
        check(f"{name}: reported, not raised, and the reason holds no link",
              res["ok"] is False and not leaks(res), res)
    res = C.run(p, fetch=lambda q: (_ for _ in ()).throw(
        urllib.error.HTTPError(LINK, 404, "Not Found", {}, None)), approved=True)
    check("a 404 says the link may have been reset", "does not exist" in res["reason"]
          and "set the new one" in res["reason"], res["reason"])

# ── redirects: followed only to https on the same host, or between Google's
#    own calendar hosts; never to anywhere else ──────────────────────────────


class _Req:
    def __init__(self, url):
        self.full_url = url
        self.headers, self.unredirected_hdrs = {}, {}
        self.origin_req_host = "calendar.google.com"
        self.timeout = 5

    def get_method(self):
        return "GET"

    def get_full_url(self):
        return self.full_url

    def header_items(self):
        return []


class _Fp:
    closed = False

    def close(self):
        self.closed = True


h = C._FeedRedirect(LINK)
www = "https://www.google.com/calendar/ical/" + CAL_ID + "/" + TOKEN + "/basic.ics"
try:
    new = h.redirect_request(_Req(LINK), _Fp(), 301, "Moved", {}, www)
    check("a redirect between Google's calendar hosts is followed", new is not None)
except Exception as exc:
    check("a redirect between Google's calendar hosts is followed", False, repr(exc))
for target, why in (("https://evil.example.com/steal/" + TOKEN, "another host"),
                    ("http://calendar.google.com/calendar/ical/" + TOKEN, "plain http"),
                    ("https://calendar.google.com.evil.example/" + TOKEN, "a look-alike host")):
    fp = _Fp()
    try:
        h.redirect_request(_Req(LINK), fp, 302, "Found", {}, target)
        check(f"a redirect to {why} is refused", False)
    except C._LinkProblem as exc:
        check(f"a redirect to {why} is refused, naming the host only",
              not leaks(str(exc), FORMS + (target,)) and fp.closed, str(exc))
check("at most three redirects", C._FeedRedirect.max_redirections == 3)

# ── a real request, to a stand-in server on this PC ────────────────────────
# Plain http:// to 127.0.0.1 is allowed (this PC), so the whole real path
# runs: jarvis_local_http's opener, the redirect handler, the size cap.

HITS = []
BIG = [False]


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):          # the server's own log would print the path
        pass

    def do_GET(self):
        HITS.append(self.path)
        if self.path.startswith("/same/"):
            self.send_response(302)
            self.send_header("Location", "/feed/" + TOKEN + "/basic.ics")
            self.end_headers()
        elif self.path.startswith("/away/"):
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{PORT}/stolen/" + TOKEN)
            self.end_headers()
        elif self.path.startswith("/feed/"):
            body = FEED.encode("utf-8")
            if BIG[0]:
                body = body + b"X-FILLER:" + b"x" * 5000 + b"\r\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"
try:
    with link_env(link=BASE + "/feed/" + TOKEN + "/basic.ics"):
        p = C.plan(7, now=NOW)
        out = C.run(p, approved=True)
        check("a real read of the link: the events of the week",
              out.get("ok") and [e["summary"] for e in out["events"]] == ["Dentist", "Stand-up"],
              out)
        check("... sent as ONE request, to the link itself",
              HITS == ["/feed/" + TOKEN + "/basic.ics"], HITS)
    HITS.clear()
    with link_env(link=BASE + "/same/" + TOKEN + "/basic.ics"):
        out = C.run(C.plan(7, now=NOW), approved=True)
        check("a redirect on the same host is followed", out.get("ok") is True
              and len(HITS) == 2, (out, HITS))
    HITS.clear()
    with link_env(link=BASE + "/away/" + TOKEN + "/basic.ics"):
        out = C.run(C.plan(7, now=NOW), approved=True)
        check("a redirect to another host is not followed: nothing reached it",
              out.get("ok") is False and not any(h.startswith("/stolen/") for h in HITS),
              (out, HITS))
        check("... and the reason says so, without the link",
              "did not follow" in out.get("reason", "") and not leaks(out), out)
    HITS.clear()
    with link_env(link=BASE + "/feed/" + TOKEN + "/basic.ics"):
        p = C.plan(7, now=NOW)
    with link_env(link=BASE.replace("127.0.0.1", "localhost") + "/feed/" + TOKEN + "/basic.ics"):
        out = C.run(p, approved=True)
        check("the link changed after the card: nothing is sent",
              out.get("ok") is False and HITS == [] and "changed" in out.get("reason", ""),
              (out, HITS))
    HITS.clear()
    real_cap = C._MAX_BYTES
    BIG[0], C._MAX_BYTES = True, len(FEED.encode("utf-8")) + 100
    try:
        with link_env(link=BASE + "/feed/" + TOKEN + "/basic.ics"):
            out = C.run(C.plan(7, now=NOW), approved=True)
        check("a calendar larger than the cap: what fits is read, and it says so",
              out.get("ok") is True and out.get("incomplete") is True
              and "may be missing" in out.get("note", "")
              and [e["summary"] for e in out["events"]] == ["Dentist", "Stand-up"], out)
    finally:
        BIG[0], C._MAX_BYTES = False, real_cap
finally:
    server.shutdown()
    server.server_close()


class _Slow:
    """A body that never ends, a chunk at a time."""

    def read(self, n):
        return b"x" * n


ticks = iter(range(0, 10_000, 10))
got = C._read_capped(_Slow(), clock=lambda: float(next(ticks)))
check("the time limit stops a body that never ends", got.cut is True and len(got) < 1_000_000,
      len(got))
check("the fetch timeout is set", C._TIMEOUT == 20.0 and "timeout=_TIMEOUT" in
      (HERE / "jarvis_calendar.py").read_text(encoding="utf-8"))

# ── the log: by shape and by value ────────────────────────────────────────

import jarvis_scrub as SC  # noqa: E402

line = f"GET {LINK} HTTP/1.1 - 200"
check("the log: Google's private-link shape is removed (not set in the environment)",
      not leaks(SC.scrub_text(line)) and "calendar.google.com" in SC.scrub_text(line),
      SC.scrub_text(line))
check("the log: the path alone is removed too",
      not leaks(SC.scrub_text("path=/calendar/ical/" + CAL_ID + "/" + TOKEN + "/basic.ics")))
check("the log: any /private- address is removed",
      not leaks(SC.scrub_text("https://cal.example.org/feeds/" + TOKEN + "/cal.ics")))
check("the log: scrubbing twice changes nothing",
      SC.scrub_text(SC.scrub_text(line)) == SC.scrub_text(line))
odd = "https://cal.example.org/feed?k=" + "Zq9" * 8
with Env(JARVIS_CALENDAR_ICS_SECRET_URL=odd):
    check("the log: a link of any shape is removed by its value (the name says SECRET)",
          odd not in SC.scrub_text("reading " + odd + " now"), SC.scrub_text("reading " + odd))

# ── the programs Jarvis starts, and the cloud lane ─────────────────────────

import jarvis_child_env  # noqa: E402

base = {"PATH": "/usr/bin", C.ICS_URL_ENV: LINK}
check("the variable's name is a secret's name (jarvis_child_env's rule)",
      jarvis_child_env._looks_secret(C.ICS_URL_ENV))
check("a program Jarvis starts does not inherit the link",
      C.ICS_URL_ENV not in jarvis_child_env.inherited(base, names=[C.ICS_URL_ENV])
      and "PATH" in jarvis_child_env.inherited(base))

import jarvis_router  # noqa: E402

check("a message holding the link counts as a secret (kept off the cloud lane)",
      jarvis_router.looks_like_a_secret("my calendar is " + LINK) is not None)
check("... and the router's note does not repeat it",
      not leaks(jarvis_router.looks_like_a_secret("my calendar is " + LINK) or ""))

# ── through jarvis_agent: the card and what the model reads ────────────────

import jarvis_agent as AG  # noqa: E402

with link_env():
    tool = AG.TOOLS["calendar_read"]
    plan_obj, card = tool.prepare({"days_ahead": 3})
    check("the agent's card holds no form of the link", not leaks(card) and
          "your Google Calendar (private link)" in card, card)
    real = C._default_fetch
    C._default_fetch = lambda q: FEED
    try:
        res = tool.execute({"days_ahead": 3}, plan_obj)
    finally:
        C._default_fetch = real
    check("the tool's result, as the model reads it, holds no form of the link",
          res.get("ok") is True and not leaks(AG._tool_content(res)), res)

    def boom(q):
        raise OSError("could not open " + LINK)
    C._default_fetch = boom
    try:
        res = tool.execute({"days_ahead": 3}, plan_obj)
    finally:
        C._default_fetch = real
    check("a failed read, as the model reads it, holds no link",
          res.get("ok") is False and not leaks(AG._tool_content(res)), res)

# ── the morning briefing: its words, the gate, the bus ─────────────────────

import jarvis_briefing as B  # noqa: E402


class _Verdict:
    allowed, tier, outcome = True, "auto", "auto"


gate_seen, bus = [], []
with link_env():
    d = B.Deps(tier_of=lambda a: "auto",
               gate=lambda a, detail, prompt: gate_seen.append((a, detail, prompt)) or _Verdict(),
               tools_enabled=lambda: {"calendar_read"}, pending_count=lambda: 0,
               calendar_fetch=lambda q: FEED, email_search=None,
               publish=lambda k, data: bus.append((k, data)))
    src = B.sources(d)
    check("the briefing's settings say which calendar: Google, private link",
          src["calendar"]["state"] == "on"
          and src["calendar"]["said"] == "Included: your Google Calendar (private link).",
          src["calendar"])
    sec = B._read_calendar(time.mktime((2026, 9, 16, 0, 0, 0, 0, 0, -1)), d)
    check("the briefing reads today's events from the private link",
          sec["state"] in ("ok", "empty") and not leaks(sec), sec)
    check("the gate (and so the audit log) was shown no form of the link",
          gate_seen and not leaks(gate_seen), gate_seen)
    check("nothing on the bus holds the link", not leaks(bus), bus)
    cut = C._Text(FEED)
    cut.cut = True
    d.calendar_fetch = lambda q: cut
    sec = B._read_calendar(time.mktime((2026, 9, 16, 0, 0, 0, 0, 0, -1)), d)
    check("a calendar larger than the cap: the briefing says some may be missing",
          "may be missing" in sec["summary"], sec)
with link_env(link=None):
    d2 = B.Deps(tier_of=lambda a: "auto", tools_enabled=lambda: {"calendar_read"},
                pending_count=lambda: 0)
    check("CONTROL: nothing set - the briefing says the calendar is not set up",
          B.sources(d2)["calendar"]["state"] == "off")

# ── nothing in this module writes to disk ──────────────────────────────────

src_text = (HERE / "jarvis_calendar.py").read_text(encoding="utf-8")
check("jarvis_calendar.py opens no file and writes nothing",
      "open(" not in src_text.replace("opener.open(", "") and ".write" not in src_text)

print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - the private calendar link is read once, sent only where "
      "it belongs, and shown nowhere")
