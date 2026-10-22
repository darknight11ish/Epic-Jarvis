"""test_duet_d1.py - Wave D-1 of the Claude Duet blueprint (2026-10-22).

    python3 backend/test_duet_d1.py

Runs anywhere; no model, no network, no live writes. What it proves:

D3 (proactive first-step prep, jarvis_calendar.py):
1. A meeting that ends (or is still going) up to 120 minutes before a flight
   departure is flagged; 121 minutes is not. A meeting up to 60 minutes after
   landing is flagged. Two events at DIFFERENT addresses less than 30 minutes
   apart are flagged; the same address, or 30 minutes, is not.
2. Only travel-SHAPED events count as travel: a travel word, or two airport
   codes with a direction. A lone three-letter word ("Gym") never does.
3. A title that claims a weekday or a date its start does not match is reported
   with BOTH claims; a correct title produces nothing; a caller-supplied claim
   about one event is compared with that event only (and skipped when the event
   is not there - never guessed).
4. The 2-minute prep covers external meetings only, uses the caller's OWN
   read-only people/notes providers, and says what is missing instead of
   drawing a blank card.

D4 (quiet threads, jarvis_email.py):
5. waiting_on_them: owner sent last, 3..14 days quiet, a question or a request
   in the text the local read already produced; 2 days or 15 days is not.
6. waiting_on_you: a human's question unanswered for MORE than 48 hours; 48
   hours exactly is not; newsletters/automated senders are skipped; a thread
   with no already-read text is not guessed at.
7. A row carries the display name only - never a subject, a body or an address.

D6 (owner-only completion, jarvis_schedule.py):
8. "Ready for your review" is its own marker: Jarvis can propose it, the view
   says it, and the item's state does not change. Only the owner's explicit
   act("done") marks it done and clears the marker. Only a to-do item can wait
   for review; the audit line carries ids only, never the item's words.

D7 (Daily Pulse, jarvis_briefing.py / jarvis_today.py):
9. The Pulse is built only from what was already read: schedule lines, the
   quiet-thread count, the approvals count and the caller's own money/study/
   PC-health extras; the "where to look" strip is capped at three and puts a
   calendar collision first; a source nobody read is listed as not checked,
   never shown as 0.
10. The briefing carries `pulse` and its text says the strip; the Today board
    shows the latest briefing's pulse and withholds it while hidden.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_calendar.py", "jarvis_email.py", "jarvis_schedule.py",
                "jarvis_briefing.py", "jarvis_today.py")

TMP = Path(tempfile.mkdtemp(prefix="jarvis-duet-d1-"))
os.environ["JARVIS_SCHEDULE_DB"] = str(TMP / "schedule.db")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ.setdefault("JARVIS_LOG_DIR", str(TMP / "logs"))
sys.path.append(str(HERE / "rebuilt"))

import jarvis_briefing as B  # noqa: E402
import jarvis_calendar as CAL  # noqa: E402
import jarvis_email as MAIL  # noqa: E402
import jarvis_schedule as S  # noqa: E402
import jarvis_today as T  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def day_event(summary, start, end, *, loc="", uid=""):
    return {"summary": summary, "start": stamp(start), "end": stamp(end),
            "location": loc, "uid": uid}


BASE = datetime(2026, 10, 22, 0, 0)
#: 2026-10-22 is a Thursday (checked in the test rather than assumed).
BASE_WEEKDAY = BASE.strftime("%A")


# --------------------------------------------------------------------------
#   D3 - travel / flight collisions
# --------------------------------------------------------------------------

def t_d3_travel_collisions_and_their_boundaries():
    flight = day_event("Flight LHR -> JFK", BASE.replace(hour=18), BASE.replace(hour=19),
                       loc="Heathrow", uid="f1")

    def collides(meeting):
        rows = CAL.detect_travel_and_flight_collisions([flight, meeting])
        return [r for r in rows if r["kind"] == "before_departure"
                and r["other"] == meeting["summary"]]

    exact = day_event("Client call", BASE.replace(hour=14), BASE.replace(hour=16))
    check("a meeting ending exactly 120 minutes before departure is flagged",
          len(collides(exact)) == 1, collides(exact))
    just_out = day_event("Client call", BASE.replace(hour=14), BASE.replace(hour=15, minute=59))
    check("... and one ending 121 minutes before is not",
          collides(just_out) == [], collides(just_out))
    overlap = day_event("Site visit", BASE.replace(hour=17, minute=30),
                        BASE.replace(hour=17, minute=45))
    check("a meeting still going right before departure is flagged",
          len(collides(overlap)) == 1, collides(overlap))
    rows = CAL.detect_travel_and_flight_collisions([flight, exact])
    check("the warning names both events and says it is about the flight",
          "Client call" in rows[0]["said"] and "Flight LHR -> JFK" in rows[0]["said"]
          and "120 minutes" in rows[0]["said"], rows)

    landing = day_event("Flight back", BASE.replace(hour=10), BASE.replace(hour=12),
                        loc="JFK", uid="f2")
    after = day_event("Taxi", BASE.replace(hour=12, minute=30),
                      BASE.replace(hour=13), loc="JFK arrivals")
    rows = CAL.detect_travel_and_flight_collisions([landing, after])
    check("a meeting 30 minutes after landing is flagged",
          [r["kind"] for r in rows] == ["after_landing"] and rows[0]["minutes"] == 30,
          rows)
    later = day_event("Taxi", BASE.replace(hour=13, minute=1), BASE.replace(hour=14))
    rows = CAL.detect_travel_and_flight_collisions([landing, later])
    check("... and one 61 minutes after is not",
          [r for r in rows if r["kind"] == "after_landing"] == [], rows)


def t_d3_different_addresses_and_travel_shape():
    one = day_event("Viewing", BASE.replace(hour=9), BASE.replace(hour=10),
                    loc="1 Oak Street")
    two = day_event("Survey", BASE.replace(hour=10, minute=29),
                    BASE.replace(hour=11), loc="2 Elm Road")
    rows = CAL.detect_travel_and_flight_collisions([one, two])
    check("two events 29 minutes apart at different addresses are flagged",
          [r["kind"] for r in rows] == ["different_addresses"] and rows[0]["minutes"] == 29,
          rows)
    later = day_event("Survey", BASE.replace(hour=10, minute=30),
                      BASE.replace(hour=11), loc="2 Elm Road")
    check("... and two 30 minutes apart are not",
          [r for r in CAL.detect_travel_and_flight_collisions([one, later])
           if r["kind"] == "different_addresses"] == [])
    same = day_event("Second meeting", BASE.replace(hour=10, minute=20),
                     BASE.replace(hour=11), loc="1 Oak Street")
    check("... and two at the SAME address are never flagged",
          [r for r in CAL.detect_travel_and_flight_collisions([one, same])
           if r["kind"] == "different_addresses"] == [])

    check("a travel word makes an event travel", CAL.is_travel_event(
        {"summary": "Flight to Berlin", "location": "Tegel"}))
    check("two airport codes with a direction do too", CAL.is_travel_event(
        {"summary": "LHR \u2192 JFK", "location": ""}))
    check("a train counts", CAL.is_travel_event(
        {"summary": "Train to York", "location": "Platform 3"}))
    check("a lone three-letter word is NOT travel",
          not CAL.is_travel_event({"summary": "Gym session", "location": "Gym"}))
    check("an ordinary meeting is not travel",
          not CAL.is_travel_event({"summary": "Tax return review", "location": "Office"}))


# --------------------------------------------------------------------------
#   D3 - wrong-day anomalies
# --------------------------------------------------------------------------

def t_d3_wrong_day_anomalies_report_both_claims():
    wrong_day = day_event("Showing - Tuesday", BASE.replace(hour=9),
                          BASE.replace(hour=10), loc="1 Oak Street", uid="ev1")
    rows = CAL.detect_calendar_anomalies([wrong_day])
    actual = BASE.strftime("%A")
    if actual == "Tuesday":
        # Keep the test meaningful on any weekday by using a different one.
        wrong_day["summary"] = "Showing - Wednesday"
        rows = CAL.detect_calendar_anomalies([wrong_day])
        actual = BASE.strftime("%A")
    check("a title claiming the wrong weekday is reported as a mismatch",
          [r["kind"] for r in rows] == ["weekday_mismatch"], rows)
    check("... and it reports BOTH claims, without choosing one",
          rows[0]["claimed"] in ("Tuesday", "Wednesday")
          and rows[0]["actual"] == actual
          and rows[0]["claimed"] in rows[0]["said"] and actual in rows[0]["said"],
          rows)
    right_day = day_event(f"Showing - {actual}", BASE.replace(hour=9),
                          BASE.replace(hour=10), loc="1 Oak Street")
    check("a correct weekday produces nothing",
          CAL.detect_calendar_anomalies([right_day]) == [])
    wrong_date = day_event("Showing - November 6", BASE.replace(hour=9),
                           BASE.replace(hour=10), loc="1 Oak Street")
    rows = CAL.detect_calendar_anomalies([wrong_date])
    check("a title claiming the wrong date is a date mismatch",
          [r["kind"] for r in rows] == ["date_mismatch"], rows)
    claimed = {"event_uid": "ev1", "claimed_weekday": "Monday"}
    rows = CAL.detect_calendar_anomalies([right_day | {"uid": "ev1"}], [claimed])
    check("a caller's claim about one event is compared with that event",
          len(rows) == 1 and rows[0]["claimed"] == "Monday", rows)
    check("... and a claim about an event that is not there is skipped, not guessed",
          CAL.detect_calendar_anomalies([right_day], [claimed]) == [])


# --------------------------------------------------------------------------
#   D3 - 2-minute prep
# --------------------------------------------------------------------------

def t_d3_two_minute_prep_degrades_honestly():
    events = [
        day_event("Client call", BASE.replace(hour=10), BASE.replace(hour=11),
                  loc="12 Oak Street"),
        day_event("Lunch", BASE.replace(hour=12), BASE.replace(hour=13)),  # no place
        day_event("Flight", BASE.replace(hour=18), BASE.replace(hour=19),
                  loc="Heathrow"),  # travel, not a meeting to prep
    ]
    cards = CAL.meeting_prep(events, people=lambda e: ["Alex"], notes=lambda e: ["Q3 deck"])
    check("one prep card per external meeting, travel excluded",
          [c["summary"] for c in cards] == ["Client call"], cards)
    check("the card carries what the caller's own reads returned",
          cards[0]["people"] == ["Alex"] and cards[0]["notes"] == ["Q3 deck"]
          and cards[0]["missing"] == [], cards)
    cards = CAL.meeting_prep(events)
    check("with no providers the card SAYS what is missing",
          cards and cards[0]["missing"] == ["notes", "people"]
          and "missing" in cards[0]["said"], cards)
    cards = CAL.meeting_prep(events, people=lambda e: 1 / 0, notes=None)
    check("a broken provider is a missing source, not a crash",
          cards and "people" in cards[0]["missing"], cards)


# --------------------------------------------------------------------------
#   D4 - quiet threads
# --------------------------------------------------------------------------

def t_d4_waiting_on_them_boundaries():
    now = 1_790_000_000.0

    def row(days, *, text="Can you confirm the date?", automated=False):
        return {"thread": f"t{days}{automated}", "direction": "out",
                "at": now - days * 86400, "who": "Alex", "text": text,
                "automated": automated}

    check("3 days quiet, with a question, is waiting on them",
          [r["kind"] for r in MAIL.find_quiet_threads([row(3)], now=now)]
          == ["waiting_on_them"])
    check("2 days is too early",
          MAIL.find_quiet_threads([row(2)], now=now) == [])
    check("14 days is the last day that still counts",
          [r["kind"] for r in MAIL.find_quiet_threads([row(14)], now=now)]
          == ["waiting_on_them"])
    check("15 days is not",
          MAIL.find_quiet_threads([row(15)], now=now) == [])
    check("a request word counts without a question mark",
          [r["kind"] for r in MAIL.find_quiet_threads(
              [row(5, text="Please confirm the booking")], now=now)]
          == ["waiting_on_them"])
    check("a message with neither a question nor a request is not guessed at",
          MAIL.find_quiet_threads([row(5, text="Thanks, see you then.")], now=now) == [])
    check("a thread with no already-read text is not guessed at",
          MAIL.find_quiet_threads([row(5, text="")], now=now) == [])


def t_d4_waiting_on_you_and_automated_skips():
    now = 1_790_000_000.0

    def row(hours, *, automated=False, headers=None, who="Sam"):
        m = {"thread": f"in{hours}{automated}{who}", "direction": "in",
             "at": now - hours * 3600, "who": who,
             "text": "Could you send the file?"}
        if automated:
            m["automated"] = True
        if headers:
            m["headers"] = headers
        return m

    check("49 hours unanswered is waiting on you",
          [r["kind"] for r in MAIL.find_quiet_threads([row(49)], now=now)]
          == ["waiting_on_you"])
    check("48 hours exactly is NOT (the text says longer than)",
          MAIL.find_quiet_threads([row(48)], now=now) == [])
    check("an automated sender is skipped",
          MAIL.find_quiet_threads([row(72, automated=True)], now=now) == [])
    check("a List-Unsubscribe header is skipped",
          MAIL.find_quiet_threads(
              [row(72, headers=["List-Unsubscribe: <mailto:u@example.com>"])],
              now=now) == [])
    check("a human with a question is kept",
          len(MAIL.find_quiet_threads([row(72)], now=now)) == 1)


def t_d4_rows_never_carry_email_words():
    now = 1_790_000_000.0
    msgs = [{"thread": "secret-thread", "direction": "in", "at": now - 72 * 3600,
             "who": "Sam", "subject": "SECRET SUBJECT",
             "text": "SECRET BODY could you reply?", "headers": []}]
    rows = MAIL.find_quiet_threads(msgs, now=now)
    blob = json.dumps(rows)
    check("a quiet-thread row carries the name, not the subject or the body",
          rows and "SECRET" not in blob and "Sam" in blob, rows)
    check("the briefing's one-line summary counts the two classes",
          MAIL.quiet_threads_line(rows) ==
          "1 message(s) from someone waiting on your reply.")
    check("... and an empty list says nothing",
          MAIL.quiet_threads_line([]) == "")


# --------------------------------------------------------------------------
#   D6 - owner-only completion
# --------------------------------------------------------------------------

def t_d6_ready_for_review_is_never_done():
    audit = []
    real_audit = S._audit
    S._audit = lambda event, detail: audit.append((event, dict(detail)))
    try:
        clock = Clock(1_790_000_000.0)
        sched = S.Scheduler(TMP / "d6-schedule.db", clock=clock,
                            gate=lambda *a: None, tier_of=lambda a: "ask")
        todo = sched.add_todo("buy milk")
        jid = todo["id"]
        check("a new to-do starts active", sched.job(jid)["state"] == "active")
        code, out = sched.propose_ready(jid)
        check("Jarvis can mark a to-do ready for review", code == 200
              and out.get("ready_for_review") is True, (code, out))
        view = sched.job(jid)
        check("the view says so, with the one sentence",
              view.get("ready_for_review") is True
              and view.get("ready_said") == S.READY_SAID, view)
        check("... and the task is NOT done by itself",
              view["state"] == "active", view)
        code, _out = sched.propose_ready(jid)
        check("proposing again is idempotent and still not done",
              code == 200 and sched.job(jid).get("ready_for_review") is True
              and sched.job(jid)["state"] == "active")
        reminder = sched.add_at("reminder", clock() + 3600, "call Alex")
        code, out = sched.propose_ready(reminder["id"])
        check("a reminder cannot wait for review (only the owner's to-do list)",
              code == 409 and "ready_for_review" not in sched.job(reminder["id"]))
        ready_rows = [row for row in audit if row[0] == "schedule.ready"]
        check("the audit line is ids only, never the item's words",
              ready_rows and set(ready_rows[-1][1]) == {"id", "kind", "reason"}
              and "buy milk" not in json.dumps(ready_rows[-1][1]), audit)
        code, _out = sched.act(jid, "done")
        after = sched.job(jid)
        check("only the owner's own done marks it done",
              code == 200 and after["state"] == "done", (code, after))
        check("... and done clears the ready marker",
              after.get("ready_for_review") in (None, False), after)
        code, _out = sched.propose_ready(jid)
        check("a done item cannot be proposed ready again", code == 409)
    finally:
        S._audit = real_audit


# --------------------------------------------------------------------------
#   D7 - Pulse
# --------------------------------------------------------------------------

def t_d7_pulse_is_honest_and_capped():
    quiet = [{"kind": "waiting_on_you"}, {"kind": "waiting_on_them"}]
    sections = [
        {"key": "today", "state": "ok", "summary": "2 alarms still to come today.",
         "items": ["a", "b"]},
        {"key": "todo", "state": "ok", "summary": "1 open item.", "items": ["milk"]},
    ]
    deps = B.Deps(quiet_threads=lambda: quiet)
    pulse = B.pulse_from(sections=sections,
                         warnings=[{"said": "Your meeting ends 30 minutes before the flight."}],
                         quiet_rows=quiet, approvals=2,
                         extras={"money": "Netflix rose $2.00",
                                 "anomalies": ["2 decks due today"]}, deps=deps)
    check("a collision is the FIRST thing in the where-to-look strip",
          pulse["where_to_look"][0] == "Your meeting ends 30 minutes before the flight.",
          pulse)
    check("the strip is capped at three items",
          len(pulse["where_to_look"]) == 3, pulse)
    check("the lines name the schedule, the approval count and the money source",
          any("2 alarms" in ln for ln in pulse["lines"])
          and any("2 approval cards are waiting" in ln for ln in pulse["lines"])
          and any("Netflix" in ln for ln in pulse["lines"]), pulse)
    check("a source nobody read is listed, not shown as 0",
          "study decks" in pulse["not_checked"]
          and "PC and GPU health" in pulse["not_checked"]
          and "money and subscriptions" not in pulse["not_checked"], pulse)
    calm = B.pulse_from(sections=[], warnings=[], quiet_rows=[],
                        approvals=0, extras=None, deps=B.Deps())
    check("a normal day has no strip at all", calm["where_to_look"] == [], calm)
    check("... and still says which sources were not checked",
          set(calm["not_checked"]) >= {"quiet email threads", "money and subscriptions",
                                        "study decks", "PC and GPU health"}, calm)


def t_d7_briefing_carries_the_pulse_and_today_surfaces_it():
    clock = Clock(1_790_000_000.0)
    sched = S.Scheduler(TMP / "d7-schedule.db", clock=clock,
                        gate=lambda *a: None, tier_of=lambda a: "ask")
    quiet = [{"kind": "waiting_on_you", "who": "Sam", "hours": 72.0,
              "said": "Sam asked you something 72 hours ago and there has been no reply."}]
    deps = B.Deps(tools_enabled=lambda: set(), pending_count=lambda: 0,
                  quiet_threads=lambda: quiet)
    b = B.build(sched=sched, now=clock(), deps=deps)
    check("the briefing carries a pulse block", isinstance(b.get("pulse"), dict), b.get("pulse"))
    check("... with the quiet-thread warning in the strip",
          any("waiting on your reply" in x for x in b["pulse"]["where_to_look"]),
          b["pulse"])
    check("... and the quiet section is a real section",
          any(s.get("key") == "quiet" for s in b["sections"]), b["sections"])
    check("the briefing's text says the strip",
          "Where to look today:" in b["text"], b["text"])
    real_latest = B.latest
    B.latest = lambda: {"pulse": {"lines": ["Pulse line."],
                                  "where_to_look": ["Look here."],
                                  "not_checked": []}}
    try:
        board = T.cockpit_sections(sched, now=clock(), turns=(), unspoken=False)
        check("the Today board shows the latest briefing's pulse",
              board.get("pulse", {}).get("where_to_look") == ["Look here."], board)
        hidden = T.cockpit_sections(sched, now=clock(), turns=(), hidden=True,
                                    unspoken=False)
        check("... and while hidden it carries nothing at all",
              "pulse" not in hidden and hidden.get("hidden") is True, hidden)
    finally:
        B.latest = real_latest


# --------------------------------------------------------------------------
#   The twins, and the contract that nothing new was logged
# --------------------------------------------------------------------------

def t_changed_modules_have_identical_twins():
    for name in ("jarvis_calendar.py", "jarvis_email.py", "jarvis_schedule.py",
                 "jarvis_briefing.py", "jarvis_today.py"):
        ours = (HERE / name).read_bytes()
        twin = (HERE.parent / "jarvis-backend" / name).read_bytes()
        check(f"{name} and its jarvis-backend twin are byte-identical",
              hashlib.sha256(ours).hexdigest() == hashlib.sha256(twin).hexdigest())


if __name__ == "__main__":
    for fn in (t_d3_travel_collisions_and_their_boundaries,
               t_d3_different_addresses_and_travel_shape,
               t_d3_wrong_day_anomalies_report_both_claims,
               t_d3_two_minute_prep_degrades_honestly,
               t_d4_waiting_on_them_boundaries,
               t_d4_waiting_on_you_and_automated_skips,
               t_d4_rows_never_carry_email_words,
               t_d6_ready_for_review_is_never_done,
               t_d7_pulse_is_honest_and_capped,
               t_d7_briefing_carries_the_pulse_and_today_surfaces_it,
               t_changed_modules_have_identical_twins):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
