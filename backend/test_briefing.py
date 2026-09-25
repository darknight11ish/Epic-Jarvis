"""test_briefing.py - the morning briefing, and the back-off for offers.

    python3 backend/test_briefing.py

The owner's decisions of 2026-09-25 (CLAUDE.md; docs/JARVIS-API.md section
22): ONE scheduler, reused for the briefing; anything that repeats asks once
with the scheduler's card, a one-off needs none; each run only READS; rule
1 - email, files and memory stay on this PC, so the briefing is put
together in code, never by a model.

What it proves, with a hand-moved clock, real SQLite files in a temporary
folder, and every socket made to fail:
  - the briefing is a kind of job on the one scheduler: a repeat raises ONE
    schedule_repeat card that lists the next three times and says what each
    run reads; the same repeat twice is refused; a one-off raises none;
  - when it goes off it is put together WITHOUT any model, kept in memory
    only, and rung "ready" after "fired" - the events carry ids and the kind
    only, and no briefing line reaches any file;
  - what is in it: today's calendar (only when set up, and only when the
    gate lets the read run without a person - tier "ask" leaves it out and
    raises no card), today's alarms, reminders and timers, the to-do list,
    the approval count, and the unread-email COUNT only (only when email is
    set up); weather and news say they are not available;
  - a slow calendar is left out at the deadline; a missed run says it is
    late;
  - "brief me now", "brief me every weekday at 7", "stop my briefing" and
    near misses, answered without the model, only for the owner's own words;
    a briefing answer is private and marks the calendar as read;
  - the back-off: at most three offers waiting, none within two minutes of a
    chat message, each "no" quiet for 1, then 7, then 30 days by a stable
    fingerprint, a "yes" wipes it; it approves and acts on nothing, and the
    owner's own requests never consult it;
  - it is applied to the overnight-tidy card ("not now" is a real answer
    now) and to the skill offer (it waits for the owner to stop chatting);
  - briefing.patch applies to what the earlier patches wrote, reverses, and
    its blocks run.

Every check fails on the code before this change: jarvis_briefing.py,
jarvis_backoff.py and briefing.patch did not exist. No pytest, no network,
no model.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-briefing-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
os.environ["JARVIS_BACKOFF_FILE"] = str(_TMP / "config" / "backoff.json")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_briefing.py", "jarvis_backoff.py", "jarvis_schedule.py",
                "jarvis_quick.py", "jarvis_email.py", "jarvis_calendar.py",
                "jarvis_skill_discovery.py", "rebuilt/jarvis_sleep.py")

if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_schedule as S  # noqa: E402
import jarvis_briefing as B  # noqa: E402
import jarvis_backoff as BO  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


def use_tz(name):
    if not hasattr(time, "tzset"):
        return False
    os.environ["TZ"] = name
    time.tzset()
    return True


def local(y, mo, d, hh, mm):
    return S.wall_to_epoch(y, mo, d, hh, mm)


class World:
    """A scheduler with a hand-moved clock, a gate that records, the bus
    captured - and briefing deps that open no socket."""

    def __init__(self, t, *, answer="approved", tier="ask", name="w"):
        self.clock = Clock(t)
        self.events, self.cards, self.reads = [], [], []
        self.answer, self.tier = answer, tier
        path = _TMP / f"{name}-{len(os.listdir(_TMP))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate, tier_of=lambda a: self.tier,
                             spawn=lambda fn: fn(), publish=lambda k, d: self.events.append((k, d)))

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)


ICS = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
{blocks}
</D:multistatus>"""
BLOCK = """  <D:response><D:propstat><D:prop><C:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:{uid}
SUMMARY:{summary}
DTSTART{param}:{start}
{extra}END:VEVENT
END:VCALENDAR</C:calendar-data></D:prop></D:propstat></D:response>"""


def calendar_xml(*events):
    return ICS.format(blocks="\n".join(
        BLOCK.format(uid=f"e{i}", summary=e[0], param=e[1], start=e[2], extra=e[3] if len(e) > 3
                     else "") for i, e in enumerate(events)))


#: The calendar and the mail server "set up" - the same variables
#: jarvis_calendar.py and jarvis_email.py read. Nothing is ever dialled: the
#: reads are injected, and NoSockets below makes any socket fail.
os.environ["JARVIS_CALDAV_URL"] = "https://cal.example.com/dav/"
os.environ["JARVIS_IMAP_HOST"] = "imap.example.com"
_DEPS = B.Deps


def deps(w=None, *, cal_tier="auto", mail_tier="auto", tools=("calendar_read", "email_check"),
         cal=None, count=None, pending=0, gate=None, deadline=5.0):
    seen = [] if w is None else w.reads

    def g(action, detail, prompt):
        seen.append(action)
        if gate is not None:
            return gate(action, detail, prompt)
        return Verdict(True, "auto", "auto")
    tiers = {"calendar_read": cal_tier, "email_read": mail_tier}
    return _DEPS(tier_of=lambda a: tiers.get(a, "ask"), gate=g,
                 tools_enabled=lambda: set(tools), pending_count=lambda: pending,
                 calendar_fetch=cal, email_search=count,
                 publish=(lambda k, d: w.events.append((k, d))) if w is not None
                 else (lambda k, d: None),
                 deadline=deadline)


class NoSockets:
    """Every way out of this process made to fail, and counted."""

    def __enter__(self):
        self.tried = []
        self.saved = (socket.socket.connect, urllib.request.urlopen,
                      socket.create_connection)

        def refuse(*a, **k):
            self.tried.append(a[:1])
            raise AssertionError("a socket was opened")
        socket.socket.connect = refuse
        urllib.request.urlopen = refuse
        socket.create_connection = refuse
        return self

    def __exit__(self, *exc):
        socket.socket.connect, urllib.request.urlopen, socket.create_connection = self.saved


# --------------------------------------------------------------------------
#   The back-off
# --------------------------------------------------------------------------


def fresh_backoff(t=1_000_000.0, name="bo"):
    c = Clock(t)
    return BO.Backoff(_TMP / f"{name}-{time.monotonic_ns()}.json", clock=c), c


def t_fingerprints_are_stable():
    a = BO.fingerprint("sleep_time_offer")
    check("a fingerprint is the same every time, whatever the case and spacing",
          a == BO.fingerprint("  Sleep_Time_Offer ") and len(a) == 24)
    check("... and differs for a different subject",
          BO.fingerprint("skill_offer", "a>b") != BO.fingerprint("skill_offer", "a>c"))


def t_the_three_rules():
    bo, c = fresh_backoff()
    fp = BO.fingerprint("x")
    check("nothing recorded: it may ask", bo.may_offer(fp) == (True, ""))
    bo.note_conversation()
    c.t += 60
    check("a chat message a minute ago: it waits", bo.may_offer(fp) == (False, "conversation"))
    check("... and says how long", 59 <= bo.quiet_for() <= 61)
    c.t += 61
    check("two minutes after the last message: it may ask", bo.may_offer(fp)[0] is True)
    fps = [BO.fingerprint("x", str(i)) for i in range(4)]
    for f in fps[:BO.MAX_WAITING]:
        bo.opened(f)
    check(f"{BO.MAX_WAITING} offers waiting: a fourth waits its turn",
          bo.may_offer(fps[3]) == (False, "too_many"))
    check("an offer already waiting is not handed out twice",
          bo.may_offer(fps[0]) == (False, "waiting"))
    bo.closed(fps[0])
    check("one answered: the next may be offered", bo.may_offer(fps[3])[0] is True)
    c.t += BO.WAITING_FOR + 1
    check("an offer nobody answered stops holding the others back after a day",
          bo.status()["waiting"] == 0)


def t_a_no_is_heard_for_1_then_7_then_30_days():
    bo, c = fresh_backoff(name="no")
    fp = BO.fingerprint("sleep_time_offer")
    days = []
    for _ in range(4):
        until = bo.declined(fp)
        days.append(round((until - c.t) / 86400))
        c.t = until - 1
        check_quiet = bo.may_offer(fp)
        c.t = until + 1
        days.append(check_quiet[1] == "silenced" and bo.may_offer(fp)[0])
    check("each no: quiet 1 day, then 7, then 30, then 30 - and asks again after",
          days == [1, True, 7, True, 30, True, 30, True], repr(days))
    raw = bo.path.read_text(encoding="utf-8")
    check("the file holds a hash, a count and dates - no words",
          "sleep" not in raw and fp in raw and json.loads(raw)["offers"][fp]["declines"] == 4)
    bo.accepted(fp)
    check("a yes wipes the count", fp not in bo.path.read_text(encoding="utf-8"))
    bo2 = BO.Backoff(bo.path, clock=c)
    bo2.declined(fp)
    check("the count survives a restart (a new Backoff on the same file)",
          bo2.may_offer(fp) == (False, "silenced"))


def t_a_broken_file_keeps_offers_quiet_and_says_so():
    bo, c = fresh_backoff(name="broken")
    bo.path.write_text("{ not json", encoding="utf-8")
    check("an unreadable file: no offer", bo.may_offer(BO.fingerprint("x")) == (False, "unreadable"))
    check("... and status says so", bo.status()["readable"] is False)
    bo.declined(BO.fingerprint("x"))
    check("the next no writes a file that works", bo.status()["readable"] is True)


def t_it_keeps_a_bounded_file():
    bo, c = fresh_backoff(name="many")
    for i in range(BO.MAX_KEPT + 10):
        bo.declined(BO.fingerprint("x", str(i)))
        c.t += 1
    rows = json.loads(bo.path.read_text(encoding="utf-8"))["offers"]
    check(f"at most {BO.MAX_KEPT} offers remembered", len(rows) == BO.MAX_KEPT)


def _code_only(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return "\n".join(l.split("#", 1)[0] for l in src.splitlines())


def t_it_never_approves_or_acts():
    code = _code_only((HERE / "jarvis_backoff.py").read_text(encoding="utf-8"))
    check("jarvis_backoff.py calls no gate, no tier and nothing that acts",
          not re.search(r"jarvis_gate|\.check\(|action_tier|approve|subprocess|socket|urllib",
                        code), re.findall(r"jarvis_gate|\.check\(|action_tier|approve", code))
    for f in ("jarvis_quick.py", "jarvis_schedule.py", "jarvis_briefing.py"):
        check(f"the owner's own requests never ask it: {f} does not import it",
              "jarvis_backoff" not in _code_only((HERE / f).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
#   The overnight-tidy card
# --------------------------------------------------------------------------


def t_the_overnight_card_follows_the_back_off():
    import jarvis_sleep as SL
    bo, c = fresh_backoff(t=time.time(), name="sleep")
    saved = BO._ONE
    BO._ONE = bo
    SL._seen.clear()
    try:
        bo.note_conversation(c.t)
        check("while the owner is chatting: no card", SL.reminder_card() is None)
        check("... and the day is NOT used up by that", SL._seen.get("day") is None)
        c.t += BO.QUIET_AFTER_CHAT + 1
        card = SL.reminder_card()
        check("two minutes later: the card", card is not None and card["kind"] == "sleep_time_offer")
        fp = BO.fingerprint(SL.OFFER)
        check("... and it counts as waiting", bo.may_offer(fp) == (False, "waiting"))
        out = SL.not_now()
        check("not now: quiet for a day, and said", out["ok"] is True
              and "1 day" in out["said"] and bo.may_offer(fp) == (False, "silenced"), out)
        SL._seen.clear()
        check("the next day's look while still quiet: no card", SL.reminder_card() is None)
        c.t += 86400 + 5
        SL._seen.clear()
        check("after the day: offered again", SL.reminder_card() is not None)
        out = SL.not_now()
        check("the second not now: a week", "7 days" in out["said"], out)
        on = SL.set_enabled(True)
        check("switching it on is never blocked by a not now (the owner's own choice)",
              on["ok"] is True and SL.enabled() is True, on)
        check("... and a yes wipes the count", bo.may_offer(fp)[1] != "silenced")
        SL.set_enabled(False)
    finally:
        BO._ONE = saved
        SL._seen.clear()


# --------------------------------------------------------------------------
#   The skill offer
# --------------------------------------------------------------------------


def t_the_skill_offer_waits_for_the_owner_to_stop_chatting():
    import jarvis_skill_discovery as SD
    bo, c = fresh_backoff(name="skill")
    slept, offered = [], []

    def sleep(s):
        slept.append(s)
        c.t += s
    saved = SD.plan, SD.offer
    SD.plan = lambda **k: SD.Plan(key="notes_search>calendar_read", chain=("notes_search",
                                  "calendar_read"), turns=3, window_days=14, name="n",
                                  path=str(_TMP / "x" / "SKILL.md"), skill_md="x")
    SD.offer = lambda p, **k: (offered.append((p.key, c.t, bo.status()["waiting"]))
                               or {"outcome": "denied"})
    try:
        bo.note_conversation()
        start = c.t
        started = SD.maybe_offer_async(tier_of=lambda a: "ask", backoff=bo, sleep=sleep)
        for _ in range(200):
            if not SD._IN_FLIGHT.locked():
                break
            time.sleep(0.01)
        check("started", started is True)
        check("the card waited until two minutes after the last message",
              len(offered) == 1 and offered[0][1] - start >= BO.QUIET_AFTER_CHAT, repr(offered))
        check("... counted as waiting while it was up, and closed after",
              offered and offered[0][2] == 1 and bo.status()["waiting"] == 0)
        check("its own no is for good already (the ledger), so nothing is written here",
              not bo.path.exists())
        for f in [BO.fingerprint("o", str(i)) for i in range(BO.MAX_WAITING)]:
            bo.opened(f)
        offered.clear()
        SD.maybe_offer_async(tier_of=lambda a: "ask", backoff=bo, sleep=sleep)
        for _ in range(200):
            if not SD._IN_FLIGHT.locked():
                break
            time.sleep(0.01)
        check("three other offers waiting: no skill card", offered == [])
    finally:
        SD.plan, SD.offer = saved


# --------------------------------------------------------------------------
#   The kind, the card, the event
# --------------------------------------------------------------------------


def t_a_kind_on_the_one_scheduler():
    use_tz("Europe/London")
    k = S.KINDS.get("briefing")
    check("the briefing is a kind of job on the one scheduler, and may repeat",
          k is not None and k.repeatable and not k.has_text and k.on_fire is not None)
    check("... its lock-screen words are generic",
          k.lock_screen == "Jarvis: your morning briefing is ready.")
    check("get() imports it before the loop first runs", "jarvis_briefing" in S.KIND_MODULES)
    w = World(local(2026, 9, 25, 20, 0), name="card")
    j = w.s.add_repeat("briefing", {"every": "weekday", "at": "07:00"}, "ignored words")
    check("a repeat waits for ONE card", j["state"] == "waiting" and len(w.cards) == 1)
    action, detail, prompt = w.cards[0]
    check("the scheduler's own action", action == "schedule_repeat"
          and detail["what"] == "set up a repeating morning briefing")
    check("the card lists the next three times",
          "Monday 28 September at 07:00" in prompt and "Tuesday 29 September at 07:00" in prompt
          and "Wednesday 30 September at 07:00" in prompt, prompt)
    check("... says what each run reads and that it only reads",
          "the number only" in prompt and "It only reads" in prompt
          and "without the AI model" in prompt and "Weather and news are not included" in prompt)
    check("... and does not claim nothing is sent (the calendar read is a request)",
          "Nothing is sent anywhere." not in prompt and "your own calendar and mail servers" in prompt)
    check("a briefing has no words of its own", w.s.job(j["id"])["text"] == "")
    try:
        w.s.add_repeat("briefing", {"every": "weekday", "at": "07:00"})
        dup = None
    except ValueError as exc:
        dup = str(exc)
    check("the same repeat twice is refused, and says why",
          dup is not None and "already set up" in dup, dup)
    n = len(w.cards)
    one = w.s.add_at("briefing", local(2026, 9, 26, 7, 0))
    check("a one-off needs no card", len(w.cards) == n and one["state"] == "active")
    w.tier = "auto"
    w.s.add_repeat("briefing", {"every": "day", "at": "08:00"})
    check("tier auto is refused: a config line is not the owner's yes",
          not [x for x in w.s.listed() if x.get("rule", {}).get("at") == "08:00"])
    code, out = S.handle_add({"kind": "briefing", "repeat": {"every": "day", "at": "06:30"}})
    check("the apps' route takes kind briefing (202, a card)", code == 202, out)
    S._SCHED.stop()
    S._SCHED = None


def t_it_goes_off_is_built_without_a_model_and_rings_ready():
    use_tz("Europe/London")
    B.forget()
    w = World(local(2026, 9, 25, 6, 0), name="fire")
    S._SCHED = w.s
    w.s.add_at("reminder", local(2026, 9, 25, 12, 0), "call the bank")
    w.s.add_todo("renew the prescription")
    job = w.s.add_at("briefing", local(2026, 9, 25, 7, 0))
    d = deps(w, cal=lambda q: calendar_xml(("Dentist", "", "20260925T083000Z")),
             count=lambda p: 3, pending=2)
    saved_fire = B._on_fire
    k = S.KINDS["briefing"]
    k.on_fire = lambda jid: saved_fire(jid, sched=w.s, deps=d)
    import jarvis_agent
    saved_turn = jarvis_agent.run_local_turn

    def no_model(*a, **kw):
        raise AssertionError("the model was asked")
    jarvis_agent.run_local_turn = no_model
    try:
        with NoSockets() as ns:
            w.clock.t = local(2026, 9, 25, 7, 0)
            went = w.s.tick()
        check("it went off, with no socket and no model", went == [job["id"]] and not ns.tried)
        kinds = [(k_, dd.get("state")) for k_, dd in w.events if dd.get("id") == job["id"]]
        check("fired, then ready", kinds[-2:] == [("schedule", "fired"), ("schedule", "ready")],
              repr(kinds))
        check("the events carry ids and the kind only",
              all(set(dd) <= {"id", "kind", "state", "late"} for _, dd in w.events))
        b = B.latest()
        text = b["text"]
        check("it is kept as the latest, for the apps to read",
              b is not None and b["job"] == job["id"] and b["source"] == "schedule")
        check("calendar: today's event at this PC's time (09:30 BST)", "09:30 Dentist" in text, text)
        check("today: the reminder with its words", "12:00 call the bank" in text, text)
        check("to-do: the open item", "renew the prescription" in text)
        check("approvals: the count, and open Jarvis to answer - never an Approve",
              "2 cards are waiting for your yes or no. Open Jarvis to answer." in text)
        check("email: the count only", "Email: 3 unread emails." in text)
        check("weather and news: said to be not available, nothing fetched",
              B.OUTSIDE_LINE in text)
        check("it is marked private, and the calendar as read", b["private"] is True
              and b["read"] == ["calendar_read"])
        on_disk = b"".join(p.read_bytes() for p in _TMP.rglob("*") if p.is_file())
        check("no line of it reached any file", b"Dentist" not in on_disk
              and b"bank" not in on_disk.replace(b"call the bank", b"")
              and b"Open Jarvis" not in on_disk)
        check("... and none reached the event bus",
              "Dentist" not in json.dumps(w.events))
    finally:
        k.on_fire = lambda jid: B._on_fire(jid)
        jarvis_agent.run_local_turn = saved_turn
        S._SCHED = None


def t_missed_while_off_says_late():
    use_tz("Europe/London")
    w = World(local(2026, 9, 25, 6, 0), name="late")
    job = w.s.add_at("briefing", local(2026, 9, 25, 7, 0))
    w.clock.t = local(2026, 9, 25, 10, 0)
    w.s.tick()
    B._on_fire(job["id"], sched=w.s, deps=deps(w, tools=()))
    b = B.latest()
    check("a briefing missed while the PC was off says so",
          b["missed"] == "missed at 07:00" and "(Due at 07:00 - the PC was off or asleep" in b["text"],
          b["text"])


# --------------------------------------------------------------------------
#   What is in it
# --------------------------------------------------------------------------


def t_calendar_lines():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 7, 0)
    xml = calendar_xml(("Stand-up", "", "20260911T080000Z", "RRULE:FREQ=WEEKLY\n"),
                       ("Mum's birthday", ";VALUE=DATE", "20260925"),
                       ("Lunch with Sam", ";TZID=Europe/London", "20260925T123000"),
                       ("Conference", "", "20260924T090000Z"),
                       ("Dentist", "", "20260925T083000Z"))
    w = World(now, name="cal")
    b = B.build(sched=w.s, now=now, deps=deps(w, cal=lambda q: xml, tools=("calendar_read",)))
    cal = next(s for s in b["sections"] if s["key"] == "calendar")
    check("all day first, then by this PC's time; repeats and ongoing said",
          cal["items"] == ["All day: Mum's birthday", "09:00 Stand-up (repeats)",
                           "09:30 Dentist", "10:00 Conference (continues from an earlier day)",
                           "12:30 Lunch with Sam"], repr(cal["items"]))
    check("the count", cal["summary"] == "5 events today.")
    check("the read went through the gate as calendar_read", w.reads == ["calendar_read"])
    check("email not set up: not in it, and not listed as left out",
          all(s["key"] != "email" for s in b["sections"])
          and not any("email" in n for n in b["not_included"]))


def t_what_decides_whether_the_calendar_is_read():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 7, 0)
    w = World(now, name="decide")
    fetched = []
    cal = lambda q: fetched.append(q) or calendar_xml(("Dentist", "", "20260925T083000Z"))
    b = B.build(sched=w.s, now=now, deps=deps(w, cal=cal, cal_tier="ask"))
    check("tier ask: not read, no card, and it says why",
          not fetched and "calendar_read" not in w.reads
          and any("ask for a yes" in n for n in b["not_included"]), b["not_included"])
    b = B.build(sched=w.s, now=now, deps=deps(w, cal=cal, tools=("email_check",)))
    check("the calendar tool not switched on: not read, 'not set up'",
          not fetched and any("not set up" in n for n in b["not_included"]))
    url = os.environ.pop("JARVIS_CALDAV_URL")
    try:
        b = B.build(sched=w.s, now=now, deps=deps(w, cal=cal))
    finally:
        os.environ["JARVIS_CALDAV_URL"] = url
    check("no calendar address: not read", not fetched
          and any("not set up" in n for n in b["not_included"]))
    b = B.build(sched=w.s, now=now, deps=deps(w, cal=cal,
                                              gate=lambda a, d_, p: Verdict(False, "ask", "denied")))
    sec = next(s for s in b["sections"] if s["key"] == "calendar")
    check("the gate says no: not read, and said", not fetched and sec["state"] == "refused")

    def slow(q):
        time.sleep(1.0)
        return calendar_xml(("Late", "", "20260925T083000Z"))
    t0 = time.time()
    b = B.build(sched=w.s, now=now, deps=deps(w, cal=slow, tools=("calendar_read",), deadline=0.2))
    sec = next(s for s in b["sections"] if s["key"] == "calendar")
    check("a slow calendar is left out at the deadline", sec["state"] == "slow"
          and time.time() - t0 < 0.9, (sec, time.time() - t0))

    def broken(q):
        raise OSError("server said: secret-path /dav/me")
    b = B.build(sched=w.s, now=now, deps=deps(w, cal=broken, tools=("calendar_read",)))
    sec = next(s for s in b["sections"] if s["key"] == "calendar")
    check("a failed read says so without quoting the server", sec["state"] == "failed"
          and "secret-path" not in json.dumps(b))


def t_email_is_a_count_and_nothing_else():
    use_tz("Europe/London")
    import jarvis_email as MAIL
    now = local(2026, 9, 25, 7, 0)
    w = World(now, name="mail")
    b = B.build(sched=w.s, now=now, deps=deps(w, count=lambda p: 0, tools=("email_check",)))
    sec = next(s for s in b["sections"] if s["key"] == "email")
    check("no unread email", sec["summary"] == "No unread email." and w.reads == ["email_read"])
    b = B.build(sched=w.s, now=now, deps=deps(w, count=lambda p: 1, tools=("email_check",)))
    check("one", "Email: 1 unread email." in b["text"])
    b = B.build(sched=w.s, now=now, deps=deps(w, count=lambda p: 5, mail_tier="ask"))
    check("tier ask: no count, said", all(s["key"] != "email" for s in b["sections"])
          and any("unread" in n for n in b["not_included"]))
    code = _code_only((HERE / "jarvis_email.py").read_text(encoding="utf-8"))
    count_src = code[code.index("def _default_count"):code.index("def count(")]
    check("the count's connection fetches no message (no FETCH, no RFC822)",
          ".fetch(" not in count_src and "RFC822" not in count_src and "search(" in count_src)
    p = MAIL.plan(1)
    check("count() needs approved=True, like run()", MAIL.count(p, search=lambda _: 9)["ok"] is False)


def t_today_and_the_to_do_list():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 7, 0)
    w = World(now, name="today")
    w.s.add_at("alarm", local(2026, 9, 25, 7, 30))
    w.s.add_at("reminder", local(2026, 9, 26, 9, 0), "tomorrow's thing")
    w.s.add_timer(600, "pasta")
    w.s.add_at("briefing", local(2026, 9, 25, 18, 0))
    for i in range(7):
        w.s.add_todo(f"item {i}")
    b = B.build(sched=w.s, now=now, deps=deps(w, tools=()))
    today = next(s for s in b["sections"] if s["key"] == "today")
    check("today: still to come today, soonest first; tomorrow and the briefing left out",
          today["items"] == ["pasta timer - 10 minutes left", "07:30 alarm"]
          and today["summary"] == "1 alarm and 1 timer still to come today.", repr(today))
    todo = next(s for s in b["sections"] if s["key"] == "todo")
    check("to-do: the count and the first five", todo["summary"] == "7 open items."
          and todo["items"][:5] == [f"item {i}" for i in range(5)]
          and todo["items"][5] == "... and 2 more", repr(todo))
    empty = B.build(sched=World(now, name="empty").s, now=now, deps=deps(tools=(), pending=None))
    ap = next(s for s in empty["sections"] if s["key"] == "approvals")
    check("approvals that cannot be counted say so", ap["state"] == "failed")
    check("an empty day says so plainly",
          "Nothing else set for today." in empty["text"] and "Nothing on your to-do list." in empty["text"])


def t_no_model_is_anywhere_near_it():
    code = _code_only((HERE / "jarvis_briefing.py").read_text(encoding="utf-8"))
    check("jarvis_briefing.py imports no model, no agent, no router",
          not re.search(r"ollama|jarvis_agent|jarvis_router|run_local_turn|jarvis_big_model|"
                        r"jarvis_second_card|chat/completions", code, re.I))


def t_the_routes():
    use_tz("Europe/London")
    B.forget()
    w = World(time.time(), name="routes")
    code, out = B.handle_get(sched=w.s, deps=deps(tools=()))
    check("GET: no briefing yet, with the words to say so", code == 200 and out["briefing"] is None
          and out["empty"] == B.EMPTY and out["lock_screen"] == B.LOCK_SCREEN)
    check("... and what a briefing includes", out["sources"]["calendar"]["state"] == "off"
          and out["sources"]["weather"]["state"] == "not_available")
    w.s.add_repeat("briefing", {"every": "day", "at": "07:00"})
    code, out = B.handle_now({}, sched=w.s, deps=deps(tools=()))
    check("POST now: one, straight away", code == 200 and out["briefing"]["source"] == "now")
    code, out = B.handle_get(sched=w.s, deps=deps(tools=()))
    check("GET: that one is the latest, and the setups are listed",
          out["briefing"]["source"] == "now" and len(out["setups"]) == 1
          and out["setups"][0]["repeat"] == "every day at 07:00")
    check("POST now with a body that is not an object: 400", B.handle_now([], sched=w.s)[0] == 400)


# --------------------------------------------------------------------------
#   Said or typed - without the model
# --------------------------------------------------------------------------


def t_the_grammar():
    now = time.time()
    for s in ("brief me", "brief me now", "Jarvis, brief me now please", "read my briefing",
              "what's my briefing", "what is my morning briefing", "give me my briefing",
              "morning briefing", "my briefing", "read me today's briefing", "read out my briefing"):
        got = Q.match(s, now)
        check(f"now: {s!r}", got is not None and got.name == "briefing_now", got)
    for s, rule in (("brief me every weekday at 7", {"every": "weekday", "at": "07:00"}),
                    ("brief me every day at 6:30am", {"every": "day", "at": "06:30"}),
                    ("set up a morning briefing every weekday morning at 7",
                     {"every": "weekday", "at": "07:00"}),
                    ("brief me on mondays and fridays at 8", {"every": "week", "at": "08:00",
                                                              "days": [0, 4]})):
        got = Q.match(s, now)
        check(f"set up: {s!r}", got is not None and got.name == "briefing_set"
              and got.f["when"].rule == rule, got and got.f)
    got = Q.match("brief me tomorrow at 7", now)
    check("once: 'brief me tomorrow at 7' (the morning)", got is not None
          and got.name == "briefing_set" and got.f["when"].rule is None
          and time.localtime(got.f["when"].at).tm_hour == 7)
    for s in ("stop my briefing", "cancel the morning briefing", "turn off my briefing"):
        got = Q.match(s, now)
        check(f"stop: {s!r}", got is not None and got.name == "briefing_cancel")
    check("stop all: refused like every bulk change",
          Q.match("cancel all my briefings", now).name == "bulk")
    check("when: 'when is my briefing'", Q.match("when is my briefing", now).name == "briefing_list")
    for s in ("brief me on the project", "debrief me", "what is a briefing for",
              "brief me about the news", "write a briefing for my boss"):
        check(f"near miss goes to the model: {s!r}", Q.match(s, now) is None, Q.match(s, now))


def t_answered_without_the_model():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 20, 0)
    w = World(now, name="quick")
    # The card is raised on its own thread on the PC; here it is held, not
    # answered, so the job is seen waiting for it.
    held = []
    w.s._spawn = lambda fn: held.append(fn)
    w.s._gate = lambda *a: w.cards.append(a) or Verdict(True, "ask", "approved")
    saved = B.Deps
    B.Deps = lambda: deps(w, cal=lambda q: calendar_xml(("Dentist", "", "20260925T083000Z")),
                          tools=("calendar_read",))
    try:
        with NoSockets() as ns:
            res = Q.answer("brief me now", sched=w.s, now=now)
        check("brief me now: the briefing itself, no socket", res is not None
              and res.reply.startswith("Your briefing for Friday 25 September") and not ns.tried,
              res and res.reply)
        check("... private (a spoken answer stays on screen), and the calendar marked as read",
              res.private is True and res.read == ["calendar_read"]
              and Q.route_fields(res).get("gate") == "private")
        res = Q.answer("brief me every weekday at 7", sched=w.s, now=now)
        check("a repeat: the card, nothing set up yet", "approval card" in res.reply
              and len(held) == 1 and w.s.listed()[0]["state"] == "waiting", res.reply)
        res = Q.answer("brief me every weekday at 7", sched=w.s, now=now)
        check("the same again: already set up", "already set up" in res.reply, res.reply)
        res = Q.answer("brief me tomorrow at 6:45", sched=w.s, now=now)
        check("once: no card", res.reply == "Briefing set for 06:45 tomorrow." and len(held) == 1,
              res.reply)
        res = Q.answer("stop my briefing", sched=w.s, now=now)
        check("two set up and 'stop my briefing': it asks which, and deletes nothing",
              "2 briefings" in res.reply and len(B.setups(w.s)) == 2, res.reply)
        res = Q.answer("when is my briefing", sched=w.s, now=now)
        check("when: both said", "every weekday" in res.reply and "06:45 tomorrow" in res.reply,
              res.reply)
        w.s.act(B.setups(w.s)[0]["id"], "delete")
        res = Q.answer("stop my briefing", sched=w.s, now=now)
        check("one set up: stopped at once", res.reply.startswith("Stopped your briefing")
              and B.setups(w.s) == [], res.reply)
        body = {"messages": [{"role": "user", "content": "brief me now", "provenance": "pasted"}]}
        check("pasted words do not act: the model", Q.answer_turn(body, sched=w.s, now=now) is None)
        check("the learner skips it", Q.is_command("brief me every weekday at 7"))
    finally:
        B.Deps = saved


# --------------------------------------------------------------------------
#   briefing.patch
# --------------------------------------------------------------------------


def _rehearse():
    order = _stack.order()
    if "briefing.patch" not in order:
        return False, "briefing.patch is not in apply-patches.ps1's list", {}, {}
    before_list = order[:order.index("briefing.patch")]
    patch = (HERE / "briefing.patch").read_text(encoding="utf-8")
    befores, afters = {}, {}
    git = shutil.which("git")
    for target in ("jarvis_hud.py", "jarvis_gate.py"):
        text, log = _stack.stand_in(target, before_list)
        if text is None:
            return False, "; ".join(log), {}, {}
        d = Path(tempfile.mkdtemp(prefix="jarvis-brief-patch-"))
        try:
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
            r = subprocess.run([git, "apply", "--include", target, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{target}: {r.stderr}", {}, {}
            after = (d / target).read_text(encoding="utf-8")
            r = subprocess.run([git, "apply", "-R", "--include", target, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0 or (d / target).read_text(encoding="utf-8") != text:
                return False, f"{target}: does not reverse cleanly: {r.stderr}", {}, {}
        finally:
            shutil.rmtree(d, ignore_errors=True)
        befores[target], afters[target] = text, after
    return True, "", befores, afters


class _Handler:
    def __init__(self, body=b"{}"):
        self.status, self.headers, self.out, self._headers_sent = None, {}, b"", False
        self.wfile = self
        self.sent = None
        self._body = body

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        self.headers[k] = v

    def end_headers(self):
        pass

    def write(self, b):
        self.out += b

    def flush(self):
        pass

    def _send(self, code, out):
        self.sent = (code, out)
        return self.sent


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, why, before, after = _rehearse()
    check("briefing.patch applies to what the earlier patches wrote, and reverses", ok, why)
    if not ok:
        return
    hud, gate = after["jarvis_hud.py"], after["jarvis_gate.py"]
    i = hud.index('        if path == "/api/briefing":')
    blk = hud[i:hud.index('        if path in ("/api/wiki"', i)]
    check("GET /api/briefing checks origin and token", "_origin_ok(self)" in blk
          and "_token_ok(self)" in blk and "jarvis_briefing.handle_get()" in blk)
    i = hud.index('        if route == "/api/briefing/now":')
    blk2 = hud[i:hud.index('        if route == "/api/wiki/ingest":', i)]
    check("POST /api/briefing/now checks origin and token", "_origin_ok(self)" in blk2
          and "_token_ok(self)" in blk2 and "jarvis_briefing.handle_now(body)" in blk2)
    for name, b in (("GET", blk), ("POST", blk2)):
        try:
            compile("def f(self, path, route):\n" + b, "<patched block>", "exec")
            check(f"the patched {name} block compiles", True)
        except SyntaxError as exc:
            check(f"the patched {name} block compiles", False, str(exc))
    # The GET block runs.
    ns = {}
    exec(compile("def f(self, path, _origin_ok, _token_ok):\n" + blk, "<GET>", "exec"), ns)
    h = _Handler()
    ns["f"](h, "/api/briefing", lambda s: True, lambda s: True)
    check("GET runs and answers 200 with the briefing's shape", h.sent and h.sent[0] == 200
          and "briefing" in h.sent[1], h.sent)
    h = _Handler()
    ns["f"](h, "/api/briefing", lambda s: True, lambda s: False)
    check("... 401 without the token", h.sent[0] == 401)
    # The sleep_time block: "not now" is a real answer.
    i = hud.index('            if route == "/api/memory/sleep_time":')
    blk3 = hud[i:hud.index('            if route == "/api/memory/keep_both":', i)]
    import types
    calls = []
    fake = types.SimpleNamespace(not_now=lambda: calls.append("not_now") or {"ok": True},
                                 set_enabled=lambda v: calls.append(("enabled", v)) or {"ok": True},
                                 set_remind=lambda v: calls.append(("remind", v)) or {"ok": True})
    ns = {}
    exec(compile("def f(self, route, body, jarvis_sleep):\n" + blk3, "<sleep>", "exec"), ns)
    h = _Handler()
    ns["f"](h, "/api/memory/sleep_time", {"not_now": True}, fake)
    check("sleep_time {not_now: true} -> jarvis_sleep.not_now()", calls == ["not_now"]
          and h.sent[0] == 200, (calls, h.sent))
    calls.clear()
    ns["f"](h, "/api/memory/sleep_time", {"enabled": True, "not_now": True}, fake)
    check("... never mixed with enable: enable wins, not_now is ignored",
          calls == [("enabled", True)], calls)
    h = _Handler()
    ns["f"](h, "/api/memory/sleep_time", {}, fake)
    check("... and an empty body is still 400", h.sent[0] == 400)
    ns["f"](h, "/api/memory/sleep_time", {"not_now": True},
            types.SimpleNamespace(set_enabled=None, set_remind=None))
    check("an older jarvis_sleep without not_now: 200, nothing written", h.sent[0] == 200)
    # /api/chat: the conversation clock, then the fast path; a briefing
    # answer marks the calendar as read.
    s = hud.index("        # schedule.patch: timers, alarms, reminders and the to-do list are")
    e = hud.index("            return\n", s) + len("            return\n")
    block = hud[s:e]
    check("the conversation clock is noted before the fast path",
          block.index("jarvis_backoff.note_conversation()") < block.index("answer_turn(body)"))
    use_tz("Europe/London")
    w = World(time.time(), name="chat")
    S._SCHED = w.s
    bo, c = fresh_backoff(t=time.time(), name="chat")
    saved_bo, saved_deps = BO._ONE, B.Deps
    BO._ONE = bo
    B.Deps = lambda: deps(w, cal=lambda q: calendar_xml(
        ("Dentist", "", time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(time.time() + 600)))),
        tools=("calendar_read",))
    import jarvis_agent
    saved_turn = jarvis_agent.run_local_turn
    jarvis_agent.run_local_turn = lambda *a, **k: (_ for _ in ()).throw(AssertionError("model"))
    try:
        ns = {}
        exec(compile("import json, socket\n"
                     "def f(self, body, route_header, _history, _temporary_chat):\n" + block,
                     "<chat>", "exec"), ns)
        h, hist = _Handler(), {"turn": None}
        body = {"messages": [{"role": "user", "content": "brief me now", "provenance": "voice"}],
                "stream": False}
        with NoSockets() as nosock:
            ns["f"](h, body, {}, hist, lambda b: False)
        rh = json.loads(h.headers.get("X-Jarvis-Route", "{}"))
        check("brief me now through the patched /api/chat: answered, no model, no socket",
              h.status == 200 and not nosock.tried and rh.get("quick") == "briefing_now"
              and rh.get("gate") == "private", rh)
        check("this PC's record of the turn says the calendar was read (outside text)",
              hist["turn"]["tools_ran"] == ["calendar_read"], hist["turn"])
        check("the owner is chatting: the back-off heard it", bo.quiet_for() > 100)
        h2, hist2 = _Handler(), {"turn": None}
        ns["f"](h2, {"messages": [{"role": "user", "content": "set a timer for 5 minutes",
                                   "provenance": "typed"}]}, {}, hist2, lambda b: False)
        check("an ordinary fast-path answer still reads nothing outside",
              hist2["turn"]["tools_ran"] == [])
    finally:
        BO._ONE, B.Deps = saved_bo, saved_deps
        jarvis_agent.run_local_turn = saved_turn
        S._SCHED = None
    check("the approval notice names the briefing among things that repeat",
          '"schedule_repeat": ("yes", "local", "sets up something that repeats on this PC - '
          'a reminder, an alarm, a morning briefing or a standby schedule' in gate)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies briefing.patch after the patches it builds on",
          all(names.index(p) < names.index("briefing.patch")
              for p in ("schedule.patch", "learning-asks.patch", "memory-pane.patch")))
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    import _where
    check("both new modules are copied in, in _where.SHIPPED too",
          "'jarvis_briefing.py'" in shipped and "'jarvis_backoff.py'" in shipped
          and "jarvis_briefing.py" in _where.SHIPPED and "jarvis_backoff.py" in _where.SHIPPED)


def main():
    orig_tz = os.environ.get("TZ")
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        if orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig_tz
        if hasattr(time, "tzset"):
            time.tzset()
        if S._SCHED is not None:
            S._SCHED.stop()
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
