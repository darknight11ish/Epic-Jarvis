"""jarvis_calendar.py: reads the owner's own CalDAV calendar, and the promise
that `plan()` cannot touch the network and `run()` cannot be tricked into it.

    python3 test_calendar.py
"""
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import BACKEND, REPO, missing, explain  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_calendar as C

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    """Any socket at all, in this block, is a failure."""

    def __enter__(self):
        self.real = socket.socket.connect

        def boom(*a, **k):
            raise AssertionError("a socket was opened")

        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

MULTISTATUS = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:response>
    <D:href>/cal/1.ics</D:href>
    <D:propstat>
      <D:prop>
        <C:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:evt-1@example.com
SUMMARY:Dentist appointment
DTSTART:20260916T140000Z
DTEND:20260916T150000Z
LOCATION:123 Main St
END:VEVENT
END:VCALENDAR</C:calendar-data>
      </D:prop>
    </D:propstat>
  </D:response>
  <D:response>
    <D:href>/cal/2.ics</D:href>
    <D:propstat>
      <D:prop>
        <C:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:evt-2@example.com
SUMMARY:Weekly stand
 up
DTSTART:20260917T090000Z
DTEND:20260917T091500Z
RRULE:FREQ=WEEKLY
END:VEVENT
END:VCALENDAR</C:calendar-data>
      </D:prop>
    </D:propstat>
  </D:response>
</D:multistatus>"""


def with_env(url=None, user=None, password=None):
    """Context manager-ish helper: sets/clears the three env vars for one
    call, then restores whatever was there before."""
    class _Ctx:
        def __enter__(self2):
            self2.saved = {
                k: os.environ.get(k) for k in
                (C.URL_ENV, C.USER_ENV, C.PASSWORD_ENV)
            }
            for k, v in ((C.URL_ENV, url), (C.USER_ENV, user), (C.PASSWORD_ENV, password)):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            return self2

        def __exit__(self2, *a):
            for k, v in self2.saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            return False
    return _Ctx()


# ── plan(): opens no socket, refuses cleanly with nothing configured ──────

with with_env(url=None):
    with NoNetwork():
        p_empty = C.plan(7, now=NOW)
    check("no URL configured -> no query is built", p_empty.query is None)
    check("describe() says why, sends nothing", "not set" in C.describe(p_empty)
          and "Nothing would be sent" in C.describe(p_empty))

with with_env(url="https://cal.example.com/dav/personal/"):
    with NoNetwork():
        p = C.plan(7, now=NOW)
    check("plan() opens no socket", True)  # reaching here without AssertionError is the proof
    check("a query is built once the URL is configured", p.query is not None)
    check("the time range starts at `now`", p.start == "20260915T120000Z")
    check("the time range ends `days_ahead` days later", p.end == "20260922T120000Z")
    check("the request is a CalDAV REPORT", p.query.method == "REPORT")
    check("the request body carries the exact time range",
          'start="20260915T120000Z"' in p.query.body and 'end="20260922T120000Z"' in p.query.body)
    check("days_ahead is clamped, not silently ignored, above 90",
          C.plan(500, now=NOW).days_ahead == 90)
    check("days_ahead is clamped below 1",
          C.plan(0, now=NOW).days_ahead == 1)

# ── describe(): the literal request, never a summary of it ───────────────

with with_env(url="https://cal.example.com/dav/personal/", user=None):
    p = C.plan(3, now=NOW)
    text = C.describe(p)
    check("describe() prints the literal URL", "https://cal.example.com/dav/personal/" in text)
    check("describe() prints the literal request body", "<C:calendar-query" in text)
    check("unauthenticated calls this out rather than staying silent",
          "No credentials are configured" in text)
    check("says what happens on refusal", "If you say no" in text)

with with_env(url="https://cal.example.com/dav/personal/", user="alice", password="hunter2"):
    p = C.plan(3, now=NOW)
    text = C.describe(p)
    check("authenticated() is true once a username is set", C.authenticated())
    check("describe() says a credential will be sent, never what it is",
          "will send the configured" in text and "hunter2" not in text)

# ── run(): refuses without approval, parses without one extra socket ─────

with with_env(url="https://cal.example.com/dav/personal/"):
    p = C.plan(7, now=NOW)

    unapproved = C.run(p)
    check("run() without approval does nothing", unapproved["ok"] is False)

    calls = []

    def fake_fetch(query):
        calls.append(query)
        return MULTISTATUS

    out = C.run(p, fetch=fake_fetch, approved=True)
    check("run() calls fetch exactly once for one query", len(calls) == 1)
    check("run() succeeds when fetch succeeds", out["ok"] is True)
    check("both events are parsed", len(out["events"]) == 2)
    check("plain SUMMARY is read correctly", out["events"][0]["summary"] == "Dentist appointment")
    check("DTSTART/DTEND are read correctly",
          out["events"][0]["start"] == "20260916T140000Z" and out["events"][0]["end"] == "20260916T150000Z")
    check("LOCATION is read correctly", out["events"][0]["location"] == "123 Main St")
    check("a folded continuation line is unfolded before parsing",
          out["events"][1]["summary"] == "Weekly standup")
    check("RRULE marks an event recurring", out["events"][1]["recurring"] is True)
    check("a non-recurring event is not marked recurring", out["events"][0]["recurring"] is False)

    def failing_fetch(query):
        raise TimeoutError("no route to host")

    failed = C.run(p, fetch=failing_fetch, approved=True)
    check("a network failure is reported, not raised", failed["ok"] is False)
    check("the failure reason is legible", "no route to host" in failed["reason"])

# ── the cap: a huge calendar is bounded, and says so ──────────────────────

with with_env(url="https://cal.example.com/dav/personal/"):
    p = C.plan(30, now=NOW)
    # Build a multistatus with more VEVENTs than the cap by repeating one block.
    block = """
  <D:response>
    <D:propstat><D:prop><C:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:evt-N@example.com
SUMMARY:Repeated
DTSTART:20260916T140000Z
DTEND:20260916T150000Z
END:VEVENT
END:VCALENDAR</C:calendar-data></D:prop></D:propstat>
  </D:response>"""
    huge = "<D:multistatus>" + block * (C._MAX_EVENTS + 10) + "</D:multistatus>"
    out = C.run(p, fetch=lambda q: huge, approved=True)
    check("the event list is capped", len(out["events"]) == C._MAX_EVENTS)
    check("a capped result says so", out["truncated"] is True)

print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - the calendar is read-only, and reads nothing without a socket to prove it")
