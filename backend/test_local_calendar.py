"""test_local_calendar.py - the Jarvis-owned local calendar (jarvis_local_calendar.py).

    py -3 test_local_calendar.py

WHAT THIS PROVES

  1. THE STORE AND ITS WALL CLOCK. An event is saved with its date and time as
     they read on the clock, never as an epoch; a date/time on either side of a
     daylight-saving change keeps the SAME wall reading, and the epoch ordering
     follows the clock's own jump. Rows are plain SQLite in `calendar.db`
     (`JARVIS_CALENDAR_DB` points every test at a throwaway file), opened with
     the shared closing connection.
  2. THE FOUR ROUTES. GET /api/calendar (the window and one event by id), POST
     /add, /act and /settings, driven through the same stand-in Handler the
     project's other route suites use: origin and token are checked on all of
     them, a route that is not ours goes straight to the original handler, and
     a malformed body answers 400 in words.
  3. THE SWITCH. No file is ON. OFF answers `on: false` with an empty list but
     KEEPS every row and the count; an add while off is refused in words; a
     damaged settings file is OFF with a `why`; a damaged database answers
     `available: false` with a `why`, never a traceback.
  4. ONE EVENT AT A TIME, NO BULK. `delete` removes one; "delete_all" and the
     other bulk verbs are refused; the module has no clear-range route.
  5. RECURRENCE, v1 and real: daily with a count, weekly with an until date,
     monthly clamped to the short months (a 31st lands on 28 February), and a
     ONE-DAY read window that includes today and not tomorrow.
  6. THE RECORDS. `calendar.db` is on `jarvis_backup.SOURCE_DBS` (a missing
     name is a silent backup loss), and the module opens no socket, no URL
     opener and no model.
  7. THE SELF-CHECK. `jarvis_local_calendar.self_check()` passes in a throwaway
     folder and removes it.

WHAT IT DOES NOT PROVE

No real backend, no real Handler, no app and no network. It does not prove the
HUD or phone screens: those are separate slices and their own tests.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_local_calendar.py", "jarvis_sqlite.py", "jarvis_backup.py")

import jarvis_backup as B  # noqa: E402
import jarvis_local_calendar as C  # noqa: E402
import jarvis_sqlite  # noqa: E402

PASSED, FAILED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-calendar-tests-"))
_ROUND = 0


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    print(f"skip  {why}")


def begin():
    """A fresh database and a fresh settings file for one group of checks."""
    global _ROUND
    _ROUND += 1
    folder = TMP / f"round{_ROUND}"
    folder.mkdir(parents=True, exist_ok=True)
    old_db = os.environ.get("JARVIS_CALENDAR_DB")
    old_set = os.environ.get("JARVIS_CALENDAR_SETTINGS")
    os.environ["JARVIS_CALENDAR_DB"] = str(folder / "calendar.db")
    os.environ["JARVIS_CALENDAR_SETTINGS"] = str(folder / "calendar-settings.json")
    jarvis_sqlite.forget_initialized()
    return old_db, old_set


def end(old):
    db = os.environ.get("JARVIS_CALENDAR_DB")
    if db:
        jarvis_sqlite.forget_initialized(db)
    old_db, old_set = old
    for key, value in (("JARVIS_CALENDAR_DB", old_db),
                       ("JARVIS_CALENDAR_SETTINGS", old_set)):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def add(**fields):
    body = {"title": "Dentist", "date": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
            "time": "14:30"}
    body.update(fields)
    return C.handle_add(body)


# ══════════════════════════════════════════════════════════════════════════
#   1. The store and the wall clock
# ══════════════════════════════════════════════════════════════════════════

def t_the_store_is_plain_sqlite_and_the_wall_clock_is_the_record():
    old = begin()
    try:
        day = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
        code, out = add(title="Dentist", date=day, time="14:30",
                        place="High Street", notes="Bring the form",
                        remind_minutes=30, tz="America/Los_Angeles")
        check("add saves one event and answers it in words",
              code == 200 and out["ok"] and out["event"]["title"] == "Dentist"
              and out["said"].startswith("Dentist,"), out)
        ev = out["event"]
        check("the event is the contract's shape, with source local",
              set(("id", "title", "date", "time", "end_date", "end_time", "all_day",
                   "place", "notes", "remind_minutes", "recurrence", "tz",
                   "source")) <= set(ev) and ev["source"] == "local", sorted(ev))
        check("id is c + 10 lowercase hex", re.fullmatch(r"c[0-9a-f]{10}", ev["id"]) is not None,
              ev["id"])
        check("the wall clock is kept as the strings the owner wrote",
              ev["date"] == day and ev["time"] == "14:30" and ev["all_day"] is False,
              (ev["date"], ev["time"]))
        check("the end defaults to the start day", ev["end_date"] == day)
        check("place, notes, remind_minutes and tz are stored",
              ev["place"] == "High Street" and ev["notes"] == "Bring the form"
              and ev["remind_minutes"] == 30 and ev["tz"] == "America/Los_Angeles", ev)
        check("a row really is in calendar.db",
              (Path(os.environ["JARVIS_CALENDAR_DB"])).is_file()
              and C._stored_count() == 1)
        check("reading it back by id gives the same fields",
              C.get_one(ev["id"]) == ev)
        code, one = C.handle_get(C.READ_PATH, {"id": ev["id"]})
        check("?id= answers one event, with the on flag",
              code == 200 and one["event"]["id"] == ev["id"] and one["on"] is True, one)
        code, missing = C.handle_get(C.READ_PATH, {"id": "c0000000000"})
        check("?id= for an event that is gone answers 404 no_such_event",
              code == 404 and missing["reason"] == "no_such_event", missing)
        code, bad = C.handle_get(C.READ_PATH, {"id": "not-an-id"})
        check("?id= with a malformed id is the same honest 404", code == 404, bad)
    finally:
        end(old)


def t_daylight_saving_keeps_the_wall_reading():
    """The two DST readings, proved against a real IANA zone.

    The shipped path (`tz=None`) reads this PC's own clock through mktime; a
    runner in UTC has no DST to read. Passing a real zone through the same
    function proves both edge cases everywhere, and the property the design
    cares about is the same one: 09:00 stays 09:00.
    """
    try:
        from zoneinfo import ZoneInfo
        la = ZoneInfo("America/Los_Angeles")
    except Exception as exc:            # noqa: BLE001 - said, not counted as a pass
        skip(f"DST: no time-zone database here ({type(exc).__name__})")
        return
    spring_before = C._wall_epoch(2026, 3, 7, 9, 0, la)
    spring_after = C._wall_epoch(2026, 3, 8, 9, 0, la)
    check("DST: 09:00 on the day before and the day of the spring jump reads 09:00",
          C._tz_wall(spring_before, la) == datetime.datetime(2026, 3, 7, 9, 0)
          and C._tz_wall(spring_after, la) == datetime.datetime(2026, 3, 8, 9, 0),
          (C._tz_wall(spring_before, la), C._tz_wall(spring_after, la)))
    check("DST: those two 09:00s are 23 hours apart, because one hour was skipped",
          int(spring_after - spring_before) == 23 * 3600,
          int(spring_after - spring_before))
    gap = C._wall_epoch(2026, 3, 8, 2, 30, la)
    check("DST: a time that never happened goes at the moment of the jump",
          C._tz_wall(gap, la) == datetime.datetime(2026, 3, 8, 3, 0),
          C._tz_wall(gap, la))
    fold = C._wall_epoch(2026, 11, 1, 1, 30, la)
    two = [datetime.datetime(2026, 11, 1, 1, 30, tzinfo=la, fold=f).timestamp()
           for f in (0, 1)]
    check("DST: a time that happened twice takes the first reading",
          len(set(two)) == 2 and fold == min(two)
          and C._tz_wall(fold, la) == datetime.datetime(2026, 11, 1, 1, 30)
          and C._tz_wall(fold + 3600, la) == datetime.datetime(2026, 11, 1, 1, 30),
          (fold, two))
    # And the shipped no-zone path still answers the same wall reading it was
    # given, on this PC's own clock (no DST assumption needed).
    now = datetime.datetime.now()
    got = C._wall_epoch(now.year, now.month, now.day, 9, 0)
    check("the shipped wall clock round-trips 09:00 on this PC",
          C._pc_wall(got)[3:5] == (9, 0), C._pc_wall(got))


# ══════════════════════════════════════════════════════════════════════════
#   2. The routes, through the same stand-in Handler as the other suites
# ══════════════════════════════════════════════════════════════════════════

class FakeHandler:
    @staticmethod
    def build():
        class H:
            def __init__(self):
                self.path = ""
                self.answers = []
                self.original = 0

            def _send(self, code, out):
                self.answers.append((code, out))
                return code, out

            def do_GET(self):
                self.original += 1
                return "original-get"

            def do_POST(self):
                self.original += 1
                return "original-post"

        return H


def install(handler_cls, *, origin=True, token=True, body=b"{}"):
    return C.install(handler_cls, origin_ok=lambda h: origin,
                     token_ok=lambda h: token, read_body=lambda h: body)


def wrapped(**kwargs):
    H = FakeHandler.build()
    install(H, **kwargs)
    return H()


def t_the_routes_are_wired_through_install():
    old = begin()
    try:
        fresh = FakeHandler.build()
        banner = install(fresh)
        check("install says the calendar is on and names its routes",
              "Jarvis Calendar" in banner and "/api/calendar" in banner, banner)
        check("install twice is harmless", "already on" in install(fresh))

        h = wrapped()
        h.path = C.READ_PATH
        h.do_GET()
        check("GET /api/calendar is answered here",
              h.answers and h.answers[0][0] == 200 and "events" in h.answers[0][1],
              h.answers)

        other = wrapped()
        other.path = "/api/something-else"
        check("an unrelated route goes straight to the original handler",
              other.do_GET() == "original-get" and other.original == 1)

        cross = wrapped(origin=False)
        cross.path = C.READ_PATH
        cross.do_GET()
        check("a cross-origin read is refused before anything else",
              cross.answers and cross.answers[0][0] == 403, cross.answers)

        no_token = wrapped(token=False)
        no_token.path = C.ADD_PATH
        no_token.do_POST()
        check("a write without the token is refused",
              no_token.answers and no_token.answers[0][0] == 401, no_token.answers)

        bad = wrapped(body=b"not json")
        bad.path = C.ADD_PATH
        bad.do_POST()
        check("a malformed body answers 400, not a traceback",
              bad.answers and bad.answers[0][0] == 400, bad.answers)

        wrong = wrapped(body=b"{}")
        wrong.path = "/api/calendar/nope"
        check("an unknown /api/calendar route is not answered by this module",
              wrong.do_POST() == "original-post" and wrong.original == 1)

        check("every path this module answers is under /api/calendar",
              all(p.startswith("/api/calendar") for p in C.ROUTES)
              and len(set(C.ROUTES)) == len(C.ROUTES), C.ROUTES)
    finally:
        end(old)


def t_add_update_delete_one_at_a_time():
    old = begin()
    try:
        code, out = add()
        check("POST /add saves one event", code == 200 and out["ok"], out)
        eid = out["event"]["id"]

        code, missing = C.handle_add({"time": "14:30"})
        check("a title is required, refused in words",
              code == 400 and "title" in missing["error"].lower(), missing)
        code, bad_date = C.handle_add({"title": "X", "date": "2026-02-30"})
        check("an impossible date is refused", code == 400, bad_date)
        code, bad_time = C.handle_add({"title": "X", "time": "25:00"})
        check("an impossible time is refused", code == 400, bad_time)
        code, backwards = C.handle_add({"title": "X", "time": "15:00", "end_time": "14:00"})
        check("an end before the start is refused", code == 400, backwards)
        code, typo = C.handle_add({"title": "X", "titel": "oops"})
        check("an unknown field is refused rather than ignored",
              code == 400 and "titel" in typo["error"], typo)
        code, long_title = C.handle_add({"title": "x" * (C.MAX_TITLE + 1)})
        check("a title is capped, not silently cut mid-word",
              code == 200 and len(long_title["event"]["title"]) == C.MAX_TITLE,
              len(long_title["event"]["title"]) if code == 200 else long_title)

        code, changed = C.handle_act({"id": eid, "do": "update",
                                      "title": "Dentist (moved)", "time": "15:00"})
        check("update changes the named fields and keeps the rest",
              code == 200 and changed["event"]["title"] == "Dentist (moved)"
              and changed["event"]["time"] == "15:00"
              and changed["event"]["date"] == out["event"]["date"], changed)
        check("the change is really on disk, not only in the answer",
              C.get_one(eid)["title"] == "Dentist (moved)")
        code, gone = C.handle_act({"id": "c0000000000", "do": "update", "title": "X"})
        check("updating an event that is not there answers 404",
              code == 404 and gone["reason"] == "no_such_event", gone)
        code, nothing = C.handle_act({"id": eid, "do": "explode"})
        check("an unknown verb is refused", code == 400, nothing)
        code, no_id = C.handle_act({"do": "delete"})
        check("delete needs one id", code == 400, no_id)
        before = C._stored_count()
        code, deleted = C.handle_act({"id": eid, "do": "delete"})
        check("delete removes exactly that event",
              code == 200 and C._stored_count() == before - 1
              and C.get_one(eid) is None, deleted)
    finally:
        end(old)


def t_no_bulk_and_no_delete_all():
    old = begin()
    try:
        for verb in ("delete_all", "clear", "clear_range", "delete_range", "bulk"):
            code, out = C.handle_act({"do": verb})
            check(f"the bulk verb {verb!r} is refused in words",
                  code == 400 and (out.get("reason") == "no_bulk"
                                   or "id" in out.get("error", "")), out)
        source = Path(C.__file__).read_text(encoding="utf-8")
        check("the module has no delete-all route or bulk function",
              "delete_all" in source                   # only the refusal list
              and "DELETE FROM events WHERE id" in source
              and "DELETE FROM events" not in source.replace(
                  "DELETE FROM events WHERE id = ?", ""))
        check("no clear-range route exists",
              not any("clear" in p for p in C.ROUTES))
    finally:
        end(old)


def t_a_full_store_says_so():
    old = begin()
    keep = C.MAX_STORED
    try:
        C.MAX_STORED = 2
        check("two events fit", add(title="One")[0] == 200 and add(title="Two")[0] == 200)
        code, out = C.handle_add({"title": "Three"})
        check("a full store answers 409 in words, never drops the newest",
              code == 409 and out["reason"] == "full" and C._stored_count() == 2, out)
    finally:
        C.MAX_STORED = keep
        end(old)


# ══════════════════════════════════════════════════════════════════════════
#   3. The switch: on by default, off hides but keeps, damage is said
# ══════════════════════════════════════════════════════════════════════════

def t_off_hides_but_keeps_every_event():
    old = begin()
    try:
        code, out = add(title="Kept while off")
        check("one event is saved while the switch is on", code == 200)
        eid = out["event"]["id"]
        code, switched = C.handle_settings({"on": False})
        check("POST /settings turns the calendar off and says so",
              code == 200 and switched["on"] is False and "off" in switched["said"], switched)
        hidden = C.list_events(7)
        check("off: the read is honest, empty, and counts what it keeps",
              hidden["on"] is False and hidden["events"] == []
              and hidden["sources"]["local"] == {"state": "off", "count": 1}, hidden)
        code, refused = C.handle_add({"title": "Not while off"})
        check("off: an add is refused in words",
              code == 409 and refused["reason"] == "off" and C._stored_count() == 1, refused)
        code, refused_act = C.handle_act({"id": eid, "do": "delete"})
        check("off: acting on an event is refused too", code == 409, refused_act)
        check("?id= still answers the stored event, with on: false",
              C.handle_get(C.READ_PATH, {"id": eid})[1]["on"] is False)
        code, back = C.handle_settings({"on": True})
        check("POST /settings turns it back on", code == 200 and back["on"] is True)
        shown = C.list_events(7)
        check("on again: every event is still there, untouched",
              shown["on"] is True and len(shown["events"]) == 1
              and shown["events"][0]["id"] == eid
              and shown["events"][0]["title"] == "Kept while off", shown)
        code, bad = C.handle_settings({"on": "yes"})
        check("the switch refuses a value that is not true/false", code == 400, bad)
    finally:
        end(old)


def t_no_file_is_on_and_damage_is_off_with_a_why():
    old = begin()
    try:
        check("no settings file means ON, from the default",
              C.settings() == {"on": True, "why": "", "changed": 0.0,
                               "source": "default"}, C.settings())
        Path(os.environ["JARVIS_CALENDAR_SETTINGS"]).write_text("{not json",
                                                                encoding="utf-8")
        st = C.settings()
        check("a damaged settings file is OFF, with a why",
              st["on"] is False and st["source"] == "damaged" and st["why"], st)
        out = C.list_events(7)
        check("...and the read carries that why rather than an error",
              out["available"] is True and out["on"] is False and out.get("why"), out)
        code, fixed = C.handle_settings({"on": True})
        check("turning it back on repairs the file",
              code == 200 and C.settings()["on"] is True
              and C.settings()["source"] == "file")
    finally:
        end(old)


def t_a_damaged_database_is_said_not_a_traceback():
    old = begin()
    try:
        Path(os.environ["JARVIS_CALENDAR_DB"]).write_bytes(b"this is not a database")
        jarvis_sqlite.forget_initialized()
        out = C.list_events(7)
        check("a damaged database answers available: false with a why",
              out["available"] is False and out["on"] is False
              and out["events"] == [] and out.get("why")
              and out["sources"]["local"]["state"] == "damaged", out)
        code, _ = C.handle_get(C.READ_PATH, {})
        check("...and the route still answers 200 rather than crashing", code == 200)
        code, refused = C.handle_add({"title": "X"})
        check("a write into a damaged store answers 503, not a traceback",
              code == 503, refused)
    finally:
        end(old)


# ══════════════════════════════════════════════════════════════════════════
#   4. Recurrence, v1 and real
# ══════════════════════════════════════════════════════════════════════════

def t_recurrence_is_expanded_in_the_window():
    old = begin()
    try:
        today = datetime.date.today()
        code, rec = add(title="Stand-up", date=today.isoformat(), time="09:00",
                        recurrence="daily", recur_count=3)
        check("a daily repeat is accepted", code == 200
              and rec["event"]["recurrence"] == "daily"
              and rec["event"]["recur_count"] == 3, rec)
        out = C.list_events(7)
        check("daily: three occurrences in the window, not one",
              len(out["events"]) == 3
              and [e["date"] for e in out["events"]]
              == [(today + datetime.timedelta(days=n)).isoformat() for n in range(3)],
              [e["date"] for e in out["events"]])
        check("daily: every occurrence carries the same id and 09:00",
              len({e["id"] for e in out["events"]}) == 1
              and all(e["time"] == "09:00" for e in out["events"]))
        check("the stored event is still ONE row, on its start date",
              len(C._all_rows()) == 1 and C.get_one(rec["event"]["id"])["date"] == today.isoformat())
    finally:
        end(old)


def t_monthly_31st_is_clamped_to_the_short_months():
    base = datetime.date(2027, 1, 31)
    ev = {"date": base.isoformat(), "recurrence": "monthly", "recur_count": 4,
          "recur_until": None}
    days = C._series_dates(ev, base, datetime.date(2027, 6, 1))
    check("monthly 31st: Jan 31, Feb 28, Mar 31, Apr 30",
          [d.isoformat() for d in days]
          == ["2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30"],
          [d.isoformat() for d in days])
    leap = C._series_dates({"date": "2028-01-31", "recurrence": "monthly",
                            "recur_count": 2, "recur_until": None},
                           datetime.date(2028, 1, 31), datetime.date(2028, 4, 1))
    check("monthly 31st in a leap year: Feb 29",
          [d.isoformat() for d in leap] == ["2028-01-31", "2028-02-29"],
          [d.isoformat() for d in leap])


def t_weekly_until_and_the_one_day_window():
    old = begin()
    try:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=7)
        until = (today + datetime.timedelta(days=7)).isoformat()
        code, rec = add(title="Weekly", date=start.isoformat(), time="10:00",
                        recurrence={"mode": "weekly", "until": until})
        check("a weekly repeat with an until date is accepted",
              code == 200 and rec["event"]["recurrence"] == "weekly"
              and rec["event"]["recur_until"] == until, rec)
        seven = C.list_events(7)
        check("weekly: the last week is outside the window",
              all(e["date"] >= today.isoformat() for e in seven["events"]), seven["events"])
        one = C.list_events(1)
        check("a one-day window includes today and not tomorrow",
              one["days"] == 1 and len(one["events"]) == 1
              and one["events"][0]["date"] == today.isoformat(), one)
        check("days is clamped to 1..90",
              C.list_events(1000)["days"] == 90 and C.list_events(0)["days"] == 1)
    finally:
        end(old)


def t_a_multi_day_event_overlaps_the_window_and_is_shown_once():
    old = begin()
    try:
        today = datetime.date.today()
        code, out = add(title="Conference", date=(today - datetime.timedelta(days=1)).isoformat(),
                        time="09:00", end_date=(today + datetime.timedelta(days=1)).isoformat(),
                        end_time="17:00")
        check("a spanning event is saved", code == 200, out)
        listing = C.list_events(1)
        check("a multi-day event that started yesterday still shows today",
              len(listing["events"]) == 1
              and listing["events"][0]["date"]
              == (today - datetime.timedelta(days=1)).isoformat(), listing["events"])
    finally:
        end(old)


# ══════════════════════════════════════════════════════════════════════════
#   5. The records: backup and no egress
# ══════════════════════════════════════════════════════════════════════════

def t_backup_and_no_socket():
    check("calendar.db is on the list of databases the backup copies",
          "calendar.db" in B.SOURCE_DBS, B.SOURCE_DBS)
    source = Path(C.__file__).read_text(encoding="utf-8")
    check("the module imports no socket, HTTP client, requests or urllib.request",
          not re.search(r"^\s*(?:import|from)\s+(socket|http|urllib\.request|"
                        r"requests|urllib3)\b", source, re.M))
    check("the module never imports the approval gate or a credential store",
          not re.search(r"^\s*(?:import|from)\s+(jarvis_gate|jarvis_credentials|"
                        r"keyring|win32cred)\b", source, re.M))
    check("it opens the database with the shared closing connection",
          "jarvis_sqlite.connect" in source
          and not re.search(r"^\s*sqlite3\.connect\(", source, re.M))


def t_the_self_check_passes_and_removes_its_folder():
    before = set(TMP.iterdir())
    code = C.self_check()
    after = set(TMP.iterdir())
    check("py -3 jarvis_local_calendar.py check passes", code == 0, code)
    check("the self-check leaves no folder behind", before == after,
          sorted(str(p) for p in after - before))


# ══════════════════════════════════════════════════════════════════════════
#   Run
# ══════════════════════════════════════════════════════════════════════════

def main():
    for fn in (t_the_store_is_plain_sqlite_and_the_wall_clock_is_the_record,
               t_daylight_saving_keeps_the_wall_reading,
               t_the_routes_are_wired_through_install,
               t_add_update_delete_one_at_a_time,
               t_no_bulk_and_no_delete_all,
               t_a_full_store_says_so,
               t_off_hides_but_keeps_every_event,
               t_no_file_is_on_and_damage_is_off_with_a_why,
               t_a_damaged_database_is_said_not_a_traceback,
               t_recurrence_is_expanded_in_the_window,
               t_monthly_31st_is_clamped_to_the_short_months,
               t_weekly_until_and_the_one_day_window,
               t_a_multi_day_event_overlaps_the_window_and_is_shown_once,
               t_backup_and_no_socket,
               t_the_self_check_passes_and_removes_its_folder):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    jarvis_sqlite.forget_initialized()
    for path in sorted(TMP.rglob("*"), reverse=True):
        try:
            path.unlink() if path.is_file() else path.rmdir()
        except OSError:
            pass
    try:
        TMP.rmdir()
    except OSError:
        pass
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
