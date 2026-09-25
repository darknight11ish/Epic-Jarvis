"""jarvis_calendar.py: reads the owner's own CalDAV calendar, and the promise
that `plan()` cannot touch the network and `run()` cannot be tricked into it.

    python3 test_calendar.py
"""
import os
import socket
import sys
import time
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

# ── repeating events: the common rules, worked out (both sources) ─────────
# Every time here ends in Z (or is all-day with days to spare), so the
# checks hold in any time zone this runs in.


def ics(*events):
    return "BEGIN:VCALENDAR\r\n" + "".join(
        "BEGIN:VEVENT\r\n" + "\r\n".join(lines) + "\r\nEND:VEVENT\r\n" for lines in events
    ) + "END:VCALENDAR\r\n"


def feed_read(text, days, now):
    """What run() keeps from `text` for `days` from `now`, as a private link
    (the window is picked out here, not by a server)."""
    link = "https://calendar.google.com/calendar/ical/x/" + "private-" + "9a" * 16 + "/basic.ics"
    saved = os.environ.get("JARVIS_CALENDAR_ICS_SECRET_URL")
    os.environ["JARVIS_CALENDAR_ICS_SECRET_URL"] = link
    try:
        p = C.plan(days, now=now)
        return C.run(p, fetch=lambda q: text, approved=True)
    finally:
        if saved is None:
            os.environ.pop("JARVIS_CALENDAR_ICS_SECRET_URL", None)
        else:
            os.environ["JARVIS_CALENDAR_ICS_SECRET_URL"] = saved


def starts(out, summary=None):
    return [e["start"] for e in out["events"] if summary is None or e["summary"] == summary]


def ev(uid, summary, start, *more):
    return [f"UID:{uid}", f"SUMMARY:{summary}", f"DTSTART:{start}", *more]


W = datetime(2026, 9, 14, 0, 0, 0, tzinfo=timezone.utc)      # a Monday

cases = [
    ("DAILY", ev("d", "Pills", "20260101T080000Z", "RRULE:FREQ=DAILY"), 3,
     ["20260914T080000Z", "20260915T080000Z", "20260916T080000Z"]),
    ("DAILY, every 2 days", ev("d2", "Run", "20260901T060000Z", "RRULE:FREQ=DAILY;INTERVAL=2"), 5,
     ["20260915T060000Z", "20260917T060000Z"]),
    ("WEEKLY on two days, years back", ev("w", "Gym", "20190101T180000Z",
                                          "RRULE:FREQ=WEEKLY;BYDAY=TU,TH"), 7,
     ["20260915T180000Z", "20260917T180000Z"]),
    ("WEEKLY, every 2 weeks, week starting Sunday",
     ev("w2", "Bins", "20260906T070000Z", "RRULE:FREQ=WEEKLY;INTERVAL=2;WKST=SU;BYDAY=SU,MO"),
     14, ["20260920T070000Z", "20260921T070000Z"]),
    ("MONTHLY on its day", ev("m", "Rent", "20250315T090000Z", "RRULE:FREQ=MONTHLY"), 7,
     ["20260915T090000Z"]),
    ("MONTHLY, the second Tuesday", ev("m2", "Club", "20250101T190000Z",
                                        "RRULE:FREQ=MONTHLY;BYDAY=2TU"), 30,
     ["20261013T190000Z"]),
    ("MONTHLY, the last Friday", ev("m3", "Payday", "20250131T120000Z",
                                     "RRULE:FREQ=MONTHLY;BYDAY=-1FR"), 30,
     ["20260925T120000Z"]),
    ("MONTHLY, the last day (BYMONTHDAY=-1)", ev("m4", "Invoice", "20250131T100000Z",
                                                 "RRULE:FREQ=MONTHLY;BYMONTHDAY=-1"), 20,
     ["20260930T100000Z"]),
    ("MONTHLY on the 31st skips short months", ev("m5", "Odd", "20260131T100000Z",
                                                  "RRULE:FREQ=MONTHLY"), 60,
     ["20261031T100000Z"]),
    ("YEARLY, a birthday (all day)", ["UID:y", "SUMMARY:Mum", "DTSTART;VALUE=DATE:19600916",
                                      "DTEND;VALUE=DATE:19600917", "RRULE:FREQ=YEARLY"], 7,
     ["20260916"]),
    ("YEARLY, the second Sunday of May", ev("y2", "Mothers", "20200510T100000Z",
                                            "RRULE:FREQ=YEARLY;BYMONTH=5;BYDAY=2SU"), 90,
     []),
    ("COUNT ends it", ev("c", "Course", "20260901T170000Z", "RRULE:FREQ=WEEKLY;COUNT=3"), 21,
     ["20260915T170000Z"]),
    ("UNTIL ends it", ev("u", "Trial", "20260901T170000Z",
                         "RRULE:FREQ=DAILY;UNTIL=20260915T170000Z"), 7,
     ["20260914T170000Z", "20260915T170000Z"]),
    ("EXDATE removes one", ev("x", "Lesson", "20260907T160000Z", "RRULE:FREQ=DAILY;COUNT=20",
                              "EXDATE:20260915T160000Z,20260916T160000Z"), 4,
     ["20260914T160000Z", "20260917T160000Z"]),
]
for name, lines, days, want in cases:
    out = feed_read(ics(lines), days, W)
    check(f"repeats worked out - {name}", starts(out) == want, starts(out))

out = feed_read(ics(ev("y3", "Mothers", "20200510T100000Z", "RRULE:FREQ=YEARLY;BYMONTH=5;BYDAY=2SU")),
                30, datetime(2027, 5, 1, tzinfo=timezone.utc))
check("repeats worked out - YEARLY, the second Sunday of May 2027", starts(out) == ["20270509T100000Z"],
      starts(out))

# One occurrence moved, one cancelled (RECURRENCE-ID), the series itself weekly.
out = feed_read(ics(
    ev("s", "Standup", "20260107T090000Z", "DTEND:20260107T091500Z", "RRULE:FREQ=WEEKLY"),
    ev("s", "Standup (moved)", "20260916T110000Z", "DTEND:20260916T111500Z",
       "RECURRENCE-ID:20260916T090000Z"),
    ev("s", "Standup", "20260923T090000Z", "RECURRENCE-ID:20260923T090000Z",
       "STATUS:CANCELLED")), 14, W)
check("a moved occurrence replaces the one it moved, and a cancelled one is gone",
      [(e["summary"], e["start"]) for e in out["events"]] == [("Standup (moved)", "20260916T110000Z")],
      [(e["summary"], e["start"]) for e in out["events"]])
check("an occurrence keeps its length (DTEND follows it)", out["events"][0]["end"] == "20260916T111500Z",
      out["events"])

out = feed_read(ics(ev("b", "Odd rule", "20260101T100000Z", "RRULE:FREQ=MONTHLY;BYSETPOS=-1;BYDAY=MO")),
                7, W)
check("a rule not worked out is kept once, at its first date, and says so",
      len(out["events"]) == 1 and out["events"][0].get("rule_not_worked_out") is True
      and out["events"][0]["start"] == "20260101T100000Z", out["events"])
out = feed_read(ics(ev("b2", "Ended", "20200101T100000Z",
                       "RRULE:FREQ=MONTHLY;BYSETPOS=-1;BYDAY=MO;UNTIL=20210101T000000Z")), 7, W)
check("... but not when its UNTIL has passed", out["events"] == [], out["events"])

real = C._MAX_STEPS
C._MAX_STEPS = 50
try:
    out = feed_read(ics(ev("cap", "Daily", "20000101T080000Z", "RRULE:FREQ=DAILY;COUNT=100000")), 3, W)
finally:
    C._MAX_STEPS = real
check("a rule past the step cap is not worked out (kept once, said)",
      len(out["events"]) == 1 and out["events"][0].get("rule_not_worked_out") is True, out["events"])
t0 = time.time()
out = feed_read(ics(*[ev(f"many{i}", "Daily", "19900101T080000Z", "RRULE:FREQ=DAILY")
                      for i in range(300)]), 90, W)
check("300 daily repeats since 1990, 90 days asked: fast, and capped at 50",
      time.time() - t0 < 10 and len(out["events"]) == C._MAX_EVENTS and out["truncated"] is True,
      (time.time() - t0, len(out["events"])))

# A reminder inside the event has a SUMMARY of its own; the event's is shown.
out = feed_read(ics(["UID:a", "DTSTART:20260915T090000Z", "BEGIN:VALARM", "ACTION:DISPLAY",
                     "SUMMARY:Reminder text", "TRIGGER:-PT10M", "END:VALARM",
                     "SUMMARY:Call the bank\\, then lunch", "DURATION:PT30M"]), 3, W)
check("a reminder's own SUMMARY is not taken for the event's, and \\, reads as a comma",
      [e["summary"] for e in out["events"]] == ["Call the bank, then lunch"], out["events"])
check("DURATION gives the end", out["events"][0]["end"] == "20260915T093000Z", out["events"])

# A time zone Python knows is turned into an exact time; one it does not is
# shown as this PC's time (as before).
zone_known = C._zone("America/New_York") is not None
out = feed_read(ics(["UID:tz", "SUMMARY:NY call", "DTSTART;TZID=America/New_York:20260915T090000",
                     "RRULE:FREQ=WEEKLY"]), 7, W)
want = ["20260915T130000Z"] if zone_known else ["20260915T090000"]
check(f"a TZID event ({'zone data here' if zone_known else 'no zone data here'})",
      starts(out) == want, starts(out))
out = feed_read(ics(["UID:tz2", "SUMMARY:Somewhere", 'DTSTART;TZID="Nowhere/Made up":20260915T090000']),
                7, W)
check("an unknown TZID is shown as this PC's time", starts(out) == ["20260915T090000"], starts(out))


print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - the calendar is read-only, and reads nothing without a socket to prove it")
