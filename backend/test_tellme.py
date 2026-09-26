"""test_tellme.py - "Tell me when ..." (jarvis_tellme.py): an email from a
named sender, or a Home Assistant device reaching a state, watched on the
one scheduler, set up with ONE card, and a match that only notifies.

    python3 backend/test_tellme.py

The owner's decision (CLAUDE.md, 2026-09-25, after the prompt pack):
"'tell me when ...' (a named sender's email, a device change) set up with
one card; a match only notifies - urgent ones as a phone notification that
keeps ringing until seen. No telephony service." What this proves, with a
clock the test moves by hand, real SQLite files in a temporary folder, the
REAL jarvis_schedule.py, jarvis_email.py, jarvis_home.py and jarvis_quick.py
(the mail server, Home Assistant and the gate are fakes; no socket opens):

  - the rule: every N minutes, with a floor of 5 for email and 1 for Home
    Assistant - for this kind only: every other repeat keeps the hourly
    floor; an end is required (30 days by default, 90 at most);
  - setting one up is ONE schedule_repeat card, tier "ask" only, that lists
    what is watched, which server is asked, how often, until when, once or
    every time, and whether it is urgent; denied or refused sets up nothing;
    a source that is not set up, or whose reads ask each time, is refused;
  - email: the first look only notes where the mailbox is; a later look
    matches the From line on this PC ("Alex" finds "Alex Smith", never
    "alexandra@..."); the real IMAP conversation is LOGIN, EXAMINE, UID
    SEARCH and UID FETCH of BODY.PEEK[HEADER.FIELDS (FROM)] - nothing that
    marks, moves or deletes, and the name is never sent to the server;
  - Home Assistant: one GET of one entity, a CHANGE into a wanted state
    matches; already there at the start does not; "unavailable" is skipped;
  - a match only notifies: one `schedule` event {"id","kind","state":
    "matched","urgent"} with no words; the notice ("An email from Alex
    arrived.") is built from the owner's words, never the email's; a
    "once" watch then ends; nothing else happens;
  - a look rings no doorbell and writes no "fired" audit line; the end
    date ends it; the job's view never hands out the watch a second time;
  - each look goes through the gate: a read switched to "ask" later is
    skipped and said, and nothing is read;
  - the fast path: "tell me when an email from Alex arrives", "let me know
    when the washing machine finishes" (found by reading a few likely
    names), "urgently ...", "every time ...", "... for the next 2 hours";
    only the owner's own words; "tell me when it's done" goes to the model;
    the model has no tool for this;
  - it is shipped and loaded before the scheduler's loop starts, and both
    apps carry its lock-screen words.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_schedule.py", "jarvis_tellme.py", "jarvis_quick.py",
                "jarvis_email.py", "jarvis_home.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-tellme-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_schedule as S  # noqa: E402
import jarvis_tellme as TM  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []
_AUDIT = []
S._audit = lambda event, detail: _AUDIT.append((event, detail))
TM._audit = lambda event, detail: _AUDIT.append((event, detail))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def use_tz(name):
    if not hasattr(time, "tzset"):
        return False
    os.environ["TZ"] = name
    time.tzset()
    return True


def local(y, mo, d, hh, mm):
    return S.wall_to_epoch(y, mo, d, hh, mm)


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


class Mail:
    """A mailbox. `look` is the injectable email look: it records what it
    was asked and answers from `arrived` (uid -> raw From header)."""

    def __init__(self):
        self.arrived = {}
        self.uidvalidity = 7
        self.calls = []

    def add(self, uid, from_header):
        self.arrived[uid] = ("From: " + from_header + "\r\n\r\n").encode("utf-8")

    def look(self, p, base, uidvalidity):
        self.calls.append((base, uidvalidity))
        top = max(self.arrived) if self.arrived else 0
        if base is None or uidvalidity != self.uidvalidity:
            return {"uidvalidity": self.uidvalidity, "base": top, "new": []}
        new = [self.arrived[u] for u in sorted(self.arrived) if u > base]
        return {"uidvalidity": self.uidvalidity, "base": max([base] + list(self.arrived)),
                "new": new}


class Home:
    """Home Assistant: entity -> state; a missing one is a 404."""

    def __init__(self):
        self.states = {}
        self.asked = []

    def fetch(self, q):
        self.asked.append(q.url)
        import urllib.error
        if q.entity_id not in self.states:
            raise urllib.error.HTTPError(q.url, 404, "Not Found", {}, None)
        return {"entity_id": q.entity_id, "state": self.states[q.entity_id], "attributes": {}}


class World:
    """A scheduler with a hand-moved clock, a gate that records, a mailbox
    and a Home Assistant - wired into jarvis_tellme."""

    def __init__(self, t, *, answer="approved", tier="ask", name="w", read_tier="auto",
                 tools=("email_check", "home_read")):
        self.clock = Clock(t)
        self.events, self.cards, self.reads = [], [], []
        self.answer, self.tier, self.read_tier = answer, tier, read_tier
        path = _TMP / f"{name}-{len(os.listdir(_TMP))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate,
                             tier_of=lambda a: self.tier, spawn=self.spawn,
                             publish=lambda k, d: self.events.append((k, d)))
        self.mail, self.home = Mail(), Home()
        self.tools = set(tools)
        S._SCHED = self.s
        TM.DEPS = TM.Deps(tier_of=lambda a: self.read_tier, gate=self.read_gate,
                          tools_enabled=lambda: self.tools,
                          publish=lambda k, d: self.events.append((k, d)),
                          email_look=self.mail.look, home_fetch=self.home.fetch,
                          sched=lambda: self.s)

    def spawn(self, fn):
        fn()

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)

    def read_gate(self, action, detail, prompt):
        self.reads.append(action)
        return Verdict(self.read_tier in ("auto", "notify"), self.read_tier, "auto")

    def matched(self):
        return [d for k, d in self.events if k == "schedule" and d.get("state") == "matched"]


os.environ["JARVIS_IMAP_HOST"] = "imap.example.test"
os.environ["JARVIS_IMAP_USER"] = "owner"
os.environ["JARVIS_HOME_URL"] = "http://homeassistant.local:8123"

EMAIL = {"source": "email", "sender": "Alex"}


def _raises(fn, exc, word=""):
    try:
        fn()
    except exc as e:
        return word in str(e)
    except Exception:
        return False
    return False


# --------------------------------------------------------------------------
#   The rule
# --------------------------------------------------------------------------

def t_the_rule_and_its_floors():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    r = TM.check_rule({"every": "minutes", "watch": EMAIL}, now)
    check("email: every 5 minutes by default, ends in 30 days, the watch tidied",
          r["minutes"] == 5 and r["ends"] == TM.days_later(now, 30) and r["watch"] ==
          {"source": "email", "sender": "Alex", "urgent": False, "once": True}, r)
    check("email: looking more often than every 5 minutes is refused",
          _raises(lambda: TM.check_rule({"every": "minutes", "minutes": 1, "watch": EMAIL}, now),
                  ValueError, "every 5 minutes"))
    h = TM.check_rule({"every": "minutes", "watch": {"source": "home",
                                                     "entity": "switch.washer",
                                                     "say": "finishes"}}, now)
    check("Home Assistant: every minute by default", h["minutes"] == 1, h)
    check("at most every hour", _raises(lambda: TM.check_rule(
        {"every": "minutes", "minutes": 61, "watch": EMAIL}, now), ValueError))
    check("an end is kept, up to 90 days; more is refused",
          TM.check_rule({"watch": EMAIL, "ends": now + 90 * 86400}, now)["ends"]
          == now + 90 * 86400 and _raises(lambda: TM.check_rule(
              {"watch": EMAIL, "ends": now + 91 * 86400}, now), ValueError, "90 days"))
    check("an end before the first look is refused",
          _raises(lambda: TM.check_rule({"watch": EMAIL, "ends": now + 60}, now), ValueError))
    for bad in ({"source": "email", "sender": ""}, {"source": "email", "sender": "anyone"},
                {"source": "email", "sender": "x" * 61},
                {"source": "email", "sender": "Alex\r\nBcc: someone"},
                {"source": "home", "entity": "../../api/services", "say": "finishes"},
                {"source": "home", "entity": "switch.washer"},
                {"source": "home", "entity": "switch.washer", "states": ["unavailable"]},
                {"source": "calendar"}):
        check(f"not a watch: {str(bad)[:60]}", _raises(lambda: TM.check_watch(bad), ValueError))
    # The hourly floor for every other repeat is untouched.
    check("every other repeat keeps the hourly floor: minutes are refused by check_rule",
          _raises(lambda: S.check_rule({"every": "minutes", "minutes": 5}), ValueError)
          and S.MIN_EVERY_HOURS == 1)
    check("... and a reminder cannot be made to repeat every few minutes through the route",
          S.handle_add({"kind": "reminder", "repeat": {"every": "minutes", "minutes": 5},
                        "text": "x"})[0] == 400)
    rule = {"every": "minutes", "minutes": 5, "start": now}
    check("every 5 minutes, in words, and the next run", S.rule_words(rule) == "every 5 minutes"
          and S.next_run(rule, now) == now + 300 and S.next_run(rule, now + 1) == now + 300)


# --------------------------------------------------------------------------
#   Setting one up: ONE card
# --------------------------------------------------------------------------

def t_one_card_that_lists_everything():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="card")
    j = TM.add(dict(EMAIL, urgent=True))
    check("ONE card, schedule_repeat", len(w.cards) == 1 and w.cards[0][0] == "schedule_repeat",
          w.cards)
    action, detail, prompt = w.cards[0]
    check("the card says what is watched, which server, how often, until when, once, urgent",
          prompt.startswith('Set up "Tell me when".')
          and "Watching for: an email from Alex." in prompt
          and "every 5 minutes" in prompt
          and "imap.example.test:993" in prompt
          and "the From line of mail that arrived since it last looked" in prompt
          and "PEEK, so nothing is marked as read" in prompt
          and "Until: Sunday 25 October at 12:00 (30 days), or the first time it happens"
          in prompt
          and "Urgent: yes." in prompt and "rings and vibrates until you look" in prompt, prompt)
    check("... what a match does - only telling - and what the lock screen shows",
          "Jarvis only tells you: \"An email from Alex arrived.\"" in prompt
          and "never replies, never acts" in prompt
          and TM.LOCK_SCREEN in prompt and "If you say no: nothing is set up" in prompt, prompt)
    check("... and that the name is not sent to the mail server",
          "they are not sent to the mail server" in prompt)
    check("the card's detail says each look leaves this PC (to the owner's own server)",
          detail.get("leaves_this_pc") is True and "tell me when" in detail.get("what", ""),
          detail)
    v = w.s.job(j["id"])
    check("approved: active, and the first look is NOW (not five minutes later)",
          v["state"] == "active" and v["due"] == now, v)
    check("the view: the owner's words, 'every 5 minutes', urgent, and no watch in the rule",
          v["text"] == "an email from Alex arrives" and v["repeat"] == "every 5 minutes"
          and v["urgent"] is True and "watch" not in v["rule"]
          and v["lock_screen"] == TM.LOCK_SCREEN, v)
    check("its line says until when, and that it rings",
          "Until Sunday 25 October at 12:00, or the first time it happens." in v.get("note", "")
          and "Urgent: rings until you look." in v["note"], v.get("note"))

    for answer in ("denied", "timed_out"):
        w2 = World(now, answer=answer, name=answer)
        j2 = TM.add(EMAIL)
        check(f"{answer}: nothing set up, nothing looked at",
              w2.s.job(j2["id"]) is None and w2.mail.calls == [] and w2.s.tick(now + 3600) == [])
    w3 = World(now, tier="auto", name="auto")
    j3 = TM.add(EMAIL)
    check("tier \"auto\" for schedule_repeat is refused without asking - a config line is "
          "not a yes", w3.cards == [] and w3.s.job(j3["id"]) is None)
    w4 = World(now, name="waiting")
    w4.s._spawn = lambda fn: None
    j4 = TM.add(EMAIL)
    check("while the card waits: listed as waiting, and nothing is looked at",
          w4.s.job(j4["id"])["state"] == "waiting" and w4.s.tick(now + 86400) == []
          and w4.mail.calls == [])

    w5 = World(now, name="nomail", tools=("home_read",))
    check("email not set up for Jarvis: refused with the reason, no card",
          _raises(lambda: TM.add(EMAIL), OverflowError, "email is not set up") and w5.cards == [])
    w6 = World(now, name="askmail", read_tier="ask")
    check("reads that ask each time: refused with the reason, no card",
          _raises(lambda: TM.add(EMAIL), OverflowError, "cannot ask you every 5 minutes")
          and w6.cards == [])
    w8 = World(now, name="notifymail", read_tier="notify")
    check("reads set to notify: refused too - it would message you every 5 minutes",
          _raises(lambda: TM.add(EMAIL), OverflowError, "would then tell you every 5 minutes")
          and w8.cards == [])
    w7 = World(now, name="limits")
    w7.s._spawn = lambda fn: None
    for i in range(TM.MAX_EMAIL_WATCHES):
        TM.add({"source": "email", "sender": f"Person {i}"})
    check("at most 5 watching email (each signs in every few minutes)",
          _raises(lambda: TM.add({"source": "email", "sender": "One more"}), OverflowError,
                  "already 5 watching email"))


def t_the_route():
    use_tz("Europe/London")
    now = time.time()
    w = World(now, name="route")
    w.s._spawn = lambda fn: None
    code, out = S.handle_add({"kind": "tellme", "source": "email", "sender": "Sam",
                              "urgent": True, "days": 2})
    check("POST /api/schedule/add kind tellme: 202, waiting for the card",
          code == 202 and out["waiting"] is True and out["job"]["state"] == "waiting"
          and out["job"]["kind"] == "tellme", (code, out))
    check("... with its end in 2 days", abs(out["job"]["rule"]["ends"] - TM.days_later(now, 2)) < 90,
          out["job"]["rule"])
    code, out = S.handle_add({"kind": "tellme", "source": "home", "entity": "binary_sensor.door",
                              "say": "opens"})
    check("a device: 202", code == 202, out)
    code, out = S.handle_add({"kind": "tellme", "source": "email", "sender": ""})
    check("a bad one: 400 with a sentence", code == 400 and out["error"].endswith("."), out)
    code, out = S.handle_add({"kind": "tellme", "source": "email", "sender": "Sam", "days": 365})
    check("more than 90 days: 400", code == 400 and "90 days" in out["error"], out)
    jid = S.handle_get({})[1]["jobs"][0]["id"]
    code, out = S.handle_act({"id": jid, "do": "delete"})
    check("delete is immediate, one job", code == 200 and w.s.job(jid) is None, out)


# --------------------------------------------------------------------------
#   Email
# --------------------------------------------------------------------------

def t_email_a_match_only_notifies():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="mail")
    w.mail.add(3, "Alex Smith <a.smith@example.test>")      # already there: not new
    j = TM.add(dict(EMAIL, urgent=True))
    w.s.tick()
    check("the first look only notes where the mailbox is - an old email from Alex is not "
          "news", w.mail.calls == [(None, None)] and w.matched() == [], w.mail.calls)
    check("... and it rang no doorbell and wrote no 'fired' audit line",
          not any(k == "schedule" and d.get("state") == "fired" for k, d in w.events)
          and not any(e == "schedule.fired" for e, _ in _AUDIT))
    check("... and the read went through the gate as email_read", w.reads == ["email_read"],
          w.reads)
    w.mail.add(4, "Alexandra Jones <alexandra@example.test>")
    w.mail.add(5, "\"Newsletter\" <news@example.test>")
    w.clock.t = now + 300
    w.s.tick()
    check("5 minutes later: new mail, but not from Alex - nothing",
          w.mail.calls[-1] == (3, 7) and w.matched() == [], w.mail.calls)
    w.mail.add(6, "=?utf-8?q?Alex_Smith?= <a.smith@example.test>")
    w.clock.t = now + 600
    w.s.tick()
    m = w.matched()
    check("an email from Alex: ONE event, the id, the kind and urgent - no words",
          len(m) == 1 and m[0] == {"id": j["id"], "kind": "tellme", "state": "matched",
                                   "urgent": True}, m)
    v = w.s.job(j["id"])
    check("told once, so it ended - still readable by id for the apps",
          v is not None and v["state"] == "fired" and j["id"] not in
          [x["id"] for x in w.s.listed()], v)
    check("the notice is built from the owner's words: 'An email from Alex arrived.'",
          v.get("alert") == "An email from Alex arrived." and v.get("watches") == "email", v)
    blob = json.dumps(v) + json.dumps(w.events) + json.dumps(_AUDIT)
    check("no From line, address or display name of the email anywhere",
          "a.smith" not in blob and "Smith" not in blob and "example.test" not in blob, blob)
    w.clock.t = now + 900
    check("after it ended, nothing looks any more", w.s.tick() == [] and len(w.mail.calls) == 3)
    # What this module keeps for a watch that is gone is forgotten at the next look.
    j2 = TM.add({"source": "email", "sender": "Sam"})
    w.s.tick()
    w.s.act(j2["id"], "delete")
    w.clock.t = now + 25 * 3600
    j3 = TM.add({"source": "email", "sender": "Kim"})
    w.s.tick()
    import sqlite3
    with sqlite3.connect(w.s.path) as c:
        ids = {r[0] for r in c.execute("SELECT id FROM tellme")}
    check("a deleted watch's position, and one over for a day, are forgotten",
          ids == {j3["id"]}, ids)


def t_every_time_and_the_end_date():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="every")
    j = TM.add(dict(EMAIL, once=False), ends=now + 3600)
    w.s.tick()
    for i, t in enumerate((300, 600)):
        w.mail.add(10 + i, "Alex <alex@example.test>")
        w.clock.t = now + t
        w.s.tick()
    check("every time: two emails, two events, still on the list",
          len(w.matched()) == 2 and w.s.job(j["id"])["state"] == "active")
    w.mail.add(20, "Alex <alex@example.test>")
    w.mail.add(21, "alex@example.test")
    w.clock.t = now + 900
    w.s.tick()
    check("two in one look: '2 emails from Alex arrived.'",
          w.s.job(j["id"]).get("alert") == "2 emails from Alex arrived.", w.s.job(j["id"]))
    w.events.clear()
    w.clock.t = now + 3600
    w.s.tick()
    v = w.s.job(j["id"])
    check("at its end date it stops, and the list is told it changed",
          v["state"] == "fired" and any(d.get("state") == "changed" for _, d in w.events), v)
    w.clock.t = now + 7200
    check("... and never looks again", w.s.tick() == [])


def t_looks_are_not_what_i_missed():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="missed")
    TM.add(dict(EMAIL))
    w.s.tick()
    for i in range(1, 13):
        w.clock.t = now + 300 * i
        w.s.tick()
    check("an hour of looks with nothing matching: 'What did I miss?' lists none of them",
          w.s.fired_since(now - 60) == [], w.s.fired_since(now - 60))


def t_past_its_end_it_does_not_look_again():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="slept")
    j = TM.add(dict(EMAIL), ends=now + 3600)
    w.s.tick()
    looks = len(w.mail.calls)
    # The PC sleeps through the end date; an email from Alex comes after it.
    w.mail.add(40, "Alex <alex@example.test>")
    w.events.clear()
    w.clock.t = now + 3 * 86400
    w.s.tick()
    v = w.s.job(j["id"])
    check("woken 3 days after its end: no look, no match - it is simply over",
          len(w.mail.calls) == looks and w.matched() == [] and v["state"] == "fired",
          (w.mail.calls, w.matched(), v))
    check("... and the list is told it changed",
          any(d.get("state") == "changed" for _, d in w.events), w.events)
    check("... and it is not 'something I missed'", w.s.fired_since(now - 60) == [])
    # Paused, the end date passes, then resumed: over, not one more look.
    w.clock.t = now + 4 * 86400
    j2 = TM.add(dict(EMAIL, sender="Sam"), ends=w.clock.t + 3600)
    w.s.tick()
    looks = len(w.mail.calls)
    code, out = w.s.act(j2["id"], "pause")
    w.clock.t += 2 * 3600
    code, out = w.s.act(j2["id"], "resume")
    w.mail.add(41, "Sam <sam@example.test>")
    w.clock.t += 600
    w.s.tick()
    v2 = w.s.job(j2["id"])
    check("paused past its end, then resumed: it ends instead of looking once more",
          code == 200 and v2["state"] == "fired" and len(w.mail.calls) == looks
          and w.matched() == [] and "ended" in out.get("said", ""), (code, out, v2))
    # A look the scheduler hands over after the end is refused by look() too.
    w.clock.t += 86400
    j3 = TM.add(dict(EMAIL, sender="Kim"), ends=w.clock.t + 3600)
    w.clock.t += 2 * 86400
    r = TM.look(j3["id"])
    check("look() itself will not look past the end date, and ends the watch",
          r == {"ok": False, "why": "ended"} and w.s.job(j3["id"])["state"] == "fired", r)


def t_sender_matching():
    m = TM.sender_matches
    check("a name matches a display name, whole words", m("Alex", b"From: Alex Smith <a@x.test>"))
    check("... or an address's words", m("alex", "alex.b@x.test"))
    check("... never a longer word", not m("Alex", "Alexandra <alexandra@x.test>"))
    check("two words both needed", m("the University of Leeds", "University of Leeds "
                                     "<noreply@leeds.test>") and not m("Leeds Uni", "Leeds "
                                                                        "<a@b.test>"))
    check("an address is compared whole", m("sam@x.test", "Sam <SAM@x.test>")
          and not m("sam@x.test", "sam@x.test.evil"))
    check("encoded names are decoded", m("José", "=?utf-8?q?Jos=C3=A9?= <j@x.test>"))
    check("rubbish is never a match", not m("Alex", b"\xff\xfe") and not m("Alex", ""))


def t_the_real_imap_conversation():
    """_default_email_look, against a fake imaplib: the commands sent."""
    sent = []

    class FakeIMAP:
        def __init__(self, host, port, timeout=None):
            sent.append(("CONNECT", host, port))
            self._resp = {}

        def login(self, u, p):
            sent.append(("LOGIN",))

        def select(self, mailbox, readonly=False):
            sent.append(("SELECT", mailbox, readonly))
            self._resp = {"UIDVALIDITY": [b"7"], "UIDNEXT": [b"42"]}
            return "OK", [b"3"]

        def response(self, code):
            return code, self._resp.get(code, [None])

        def uid(self, command, *args):
            sent.append(("UID", command) + args)
            if command == "SEARCH":
                return "OK", [b"41 42 43"]
            return "OK", [(b"42 (UID 42 BODY[HEADER.FIELDS (FROM)] {20}", b"From: Alex <a@b>\r\n"),
                          b")", (b"43 (UID 43 ...", b"From: Bo <c@d>\r\n"), b")"]

        def close(self):
            sent.append(("CLOSE",))

        def logout(self):
            sent.append(("LOGOUT",))

    import imaplib
    real = imaplib.IMAP4_SSL
    imaplib.IMAP4_SSL = FakeIMAP
    try:
        import jarvis_email as MAIL
        p = MAIL.plan(1, unread_only=False)
        first = TM._default_email_look(p, None, None)
        later = TM._default_email_look(p, 41, 7)
    finally:
        imaplib.IMAP4_SSL = real
    check("the first look notes the mailbox's position and reads no message",
          first == {"uidvalidity": 7, "base": 41, "new": [], "fresh": True}, first)
    check("a later look reads the From line of mail above the base only",
          later["base"] == 43 and later["new"] == [b"From: Alex <a@b>\r\n", b"From: Bo <c@d>\r\n"],
          later)
    verbs = {c[0] if c[0] != "UID" else "UID " + c[1] for c in sent}
    check("only LOGIN, a read-only SELECT (EXAMINE), UID SEARCH, UID FETCH, CLOSE, LOGOUT",
          verbs == {"CONNECT", "LOGIN", "SELECT", "UID SEARCH", "UID FETCH", "CLOSE", "LOGOUT"}
          and all(c[2] is True for c in sent if c[0] == "SELECT"), sent)
    fetches = [c for c in sent if c[:2] == ("UID", "FETCH")]
    check("the FETCH asks for BODY.PEEK of the From header only, for the new UIDs",
          fetches == [("UID", "FETCH", "42,43", "(BODY.PEEK[HEADER.FIELDS (FROM)])")], fetches)
    check("the search is by UID only - the watched name never goes to the server",
          [c for c in sent if c[:2] == ("UID", "SEARCH")] == [("UID", "SEARCH", "UID", "42:*")],
          sent)
    src = (HERE / "jarvis_tellme.py").read_text(encoding="utf-8")
    import re
    calls = set(re.findall(r"\bconn\.(\w+)\(", src))
    uid_verbs = set(re.findall(r"\bconn\.uid\(\"(\w+)\"", src))
    check("the module's IMAP calls are only login, select, response, uid, close, logout - "
          "and uid only SEARCH and FETCH (no STORE, COPY, MOVE, EXPUNGE)",
          calls <= {"login", "select", "response", "uid", "close", "logout"}
          and uid_verbs == {"SEARCH", "FETCH"} and "RFC822" not in src.split('"""', 2)[2]
          and "BODY[]" not in src, (calls, uid_verbs))


def t_a_read_switched_to_ask_is_skipped():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="later-ask")
    j = TM.add(EMAIL)
    w.s.tick()
    w.read_tier = "ask"
    w.mail.add(9, "Alex <a@x.test>")
    w.clock.t = now + 300
    w.s.tick()
    v = w.s.job(j["id"])
    check("reads switched to ask later: the look is skipped, nothing read, no match",
          len(w.mail.calls) == 1 and w.matched() == [], w.mail.calls)
    check("... and Coming up says why",
          "your settings ask for a yes each time Jarvis reads email" in v.get("note", ""), v)


# --------------------------------------------------------------------------
#   Home Assistant
# --------------------------------------------------------------------------

def t_a_device_changing():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="home")
    w.home.states["switch.washing_machine"] = "on"
    j = TM.add({"source": "home", "entity": "switch.washing_machine", "name": "washing machine",
                "say": "finishes"})
    prompt = w.cards[-1][2]
    check("the card names the device, the one GET it makes, and the states that count",
          "Watching for: the washing machine (switch.washing_machine) - when it finishes."
          in prompt and "GET http://homeassistant.local:8123/api/states/switch.washing_machine"
          in prompt and "CHANGES to: off, idle, finished" in prompt
          and "Nothing in your home is changed." in prompt, prompt)
    w.s.tick()
    check("the first look: the state now ('on') - no match", w.matched() == [])
    w.home.states["switch.washing_machine"] = "unavailable"
    w.clock.t = now + 60
    w.s.tick()
    w.home.states["switch.washing_machine"] = "on"
    w.clock.t = now + 120
    w.s.tick()
    check("'unavailable' (Home Assistant restarting) is not a change", w.matched() == [])
    w.home.states["switch.washing_machine"] = "off"
    w.clock.t = now + 180
    w.s.tick()
    m = w.matched()
    v = w.s.job(j["id"])
    check("on -> off: ONE event, not urgent, and 'The washing machine finished.'",
          len(m) == 1 and m[0]["urgent"] is False and v.get("alert") ==
          "The washing machine finished.", (m, v))
    check("only GETs of that one entity, and only home_read through the gate",
          set(w.home.asked) == {"http://homeassistant.local:8123/api/states/"
                                "switch.washing_machine"} and set(w.reads) == {"home_read"},
          (w.home.asked, w.reads))

    w2 = World(now, name="home-already")
    w2.home.states["binary_sensor.front_door"] = "on"
    j2 = TM.add({"source": "home", "entity": "binary_sensor.front_door", "say": "opens",
                 "urgent": True, "once": False})
    for i in range(3):
        w2.clock.t = now + 60 * i
        w2.s.tick()
    check("a door already open when it starts is not 'opened'", w2.matched() == [])
    w2.home.states["binary_sensor.front_door"] = "off"
    w2.clock.t = now + 240
    w2.s.tick()
    w2.home.states["binary_sensor.front_door"] = "on"
    w2.clock.t = now + 300
    w2.s.tick()
    check("closed then opened: urgent event, and 'binary_sensor.front_door opened.'",
          [d["urgent"] for d in w2.matched()] == [True]
          and w2.s.job(j2["id"]).get("alert") == "binary_sensor.front_door opened.",
          w2.s.job(j2["id"]))
    w3 = World(now, name="home-404")
    j3 = TM.add({"source": "home", "entity": "switch.nothing_here", "states": ["off"]})
    w3.s.tick()
    check("a device Home Assistant does not have: said under Coming up",
          "Home Assistant says there is no such device" in w3.s.job(j3["id"]).get("note", ""),
          w3.s.job(j3["id"]))


# --------------------------------------------------------------------------
#   The fast path
# --------------------------------------------------------------------------

def t_the_fast_path_understands():
    now = local(2026, 9, 25, 12, 0)
    cases = {
        "tell me when an email from Alex arrives": ("tellme_email", {"who": "Alex"}),
        "Jarvis, let me know when I get an email from Dr Patel": ("tellme_email",
                                                                 {"who": "Dr Patel"}),
        "tell me when Sam emails me": ("tellme_email", {"who": "Sam"}),
        "urgently tell me when an email from the University arrives":
            ("tellme_email", {"who": "the University", "urgent": True}),
        "tell me when an email from Alex arrives, it's urgent": ("tellme_email",
                                                                 {"urgent": True}),
        "tell me every time Sam emails me": ("tellme_email", {"once": False}),
        "let me know when the washing machine finishes": ("tellme_home",
                                                          {"name": "washing machine",
                                                           "say": "finishes"}),
        "tell me when the front door opens": ("tellme_home", {"name": "front door",
                                                               "say": "opens"}),
        "tell me when switch.dryer is off": ("tellme_home", {"entity": "switch.dryer",
                                                             "states": ["off"]}),
        "tell me when sensor.washer_status is idle": ("tellme_home",
                                                      {"entity": "sensor.washer_status",
                                                       "states": ["idle"]}),
        "tell me when the dishwasher is done for the next 2 hours": (
            "tellme_home", {"name": "dishwasher", "ends": now + 7200}),
        "tell me when an email from anyone arrives": ("tellme_help", {}),
    }
    for text, (name, want) in cases.items():
        got = Q.match(text, now)
        ok = got is not None and got.name == name and all(got.f.get(k) == v
                                                           for k, v in want.items())
        check(f"understood: {text!r}", ok, got)
    for text in ("tell me when it's done", "tell me when you are ready", "let me know when "
                 "the timer finishes", "tell me a joke", "tell me when the war of 1812 ended",
                 "tell me when dinner is ready"):
        got = Q.match(text, now)
        check(f"not ours: {text!r}", got is None or not got.name.startswith("tellme"), got)
    check("a 'tell me when' sentence is a command, not a fact to learn",
          Q.is_command("tell me when an email from Alex arrives"))


def t_the_fast_path_sets_one_up():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w = World(now, name="quick")
    w.s._spawn = lambda fn: None
    res = Q.answer("tell me when an email from Alex arrives", sched=w.s, now=now)
    j = w.s.listed()[-1]
    check("set up through the scheduler, waiting for its card, source quick",
          j["kind"] == "tellme" and j["state"] == "waiting" and j["source"] == "quick", j)
    check("the answer says there is a card, how often and until when - and does not say "
          "the name back", "approval card" in res.reply and "every 5 minutes" in res.reply
          and "25 October" in res.reply and "Alex" not in res.reply, res.reply)
    w.home.states["switch.washing_machine"] = "on"
    res = Q.answer("let me know when the washing machine finishes", sched=w.s, now=now)
    j = w.s.listed()[-1]
    check("a device said in words is found by reading a few likely names",
          j["text"] == "the washing machine finishes"
          and w.home.asked[0].endswith("/api/states/switch.washing_machine"), (j, w.home.asked))
    check("... and the answer counts as having read Home Assistant", res.read == ["home_read"],
          res.read)
    res = Q.answer("tell me when the tumble dryer finishes", sched=w.s, now=now)
    check("not found: says which names it tried, and how to say it",
          "could not find a Home Assistant device called tumble dryer" in res.reply
          and "switch.tumble_dryer, binary_sensor.tumble_dryer and sensor.tumble_dryer"
          in res.reply, res.reply)
    check("'tell me when the shop opens' with no such device is a question: the model's",
          Q.answer("tell me when the shop opens", sched=w.s, now=now) is None)
    w.home.states["binary_sensor.garden_gate"] = "off"
    res = Q.answer("tell me when the garden gate opens", sched=w.s, now=now)
    check("... but a real device that opens is set up",
          any(x["text"] == "the garden gate opens" for x in w.s.listed()), res.reply)
    w.home.states["switch.kettle"] = "on"
    w.home.states["sensor.kettle"] = "on"
    res = Q.answer("tell me when the kettle is off", sched=w.s, now=now)
    check("two found: asks which, sets nothing up", "more than one" in res.reply
          and "switch.kettle" in res.reply and not any(
              x["text"].startswith("the kettle") for x in w.s.listed()), res.reply)
    w.tools = {"email_check"}
    res = Q.answer("tell me when the oven turns off", sched=w.s, now=now)
    check("Home Assistant not set up: says so, reads nothing",
          "Home Assistant is not set up for Jarvis" in res.reply, res.reply)
    body = {"messages": [{"role": "user", "content": "tell me when an email from Eve arrives",
                          "provenance": "pasted"}]}
    check("only the owner's own words: a pasted sentence goes to the model",
          Q.answer_turn(body, sched=w.s, now=now) is None)
    agent = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("the model has no tool for it", "jarvis_tellme" not in agent and "tellme" not in agent)


# --------------------------------------------------------------------------
#   Shipped, loaded, and both apps carry the words
# --------------------------------------------------------------------------

def t_shipped_loaded_and_worded():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    import _where
    check("apply-patches.ps1 and _where.SHIPPED copy it in",
          "'jarvis_tellme.py'" in shipped and "jarvis_tellme.py" in _where.SHIPPED)
    check("the scheduler imports it before its loop first starts",
          "jarvis_tellme" in S.KIND_MODULES)
    k = S.KINDS.get("tellme")
    check("registered: repeatable, silent, first look at once, its own check and card",
          k is not None and k.repeatable and k.silent and k.first_now and k.check is not None
          and k.card is not None and k.add is not None and k.lock_screen == TM.LOCK_SCREEN)
    for rel in ("jarvis-desktop/src/coming-up.js",
                "jarvis-desktop/src-tauri/src/brain/schedule.rs",
                "jarvis-client/app/src/main/java/com/jarvis/client/net/Schedule.kt"):
        text = (REPO / rel).read_text(encoding="utf-8")
        check(f"{rel.rsplit('/', 1)[-1]} carries the lock-screen words and the title",
              TM.LOCK_SCREEN in text and '"Tell me when"' in text)


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
        S._SCHED = None
        if orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = orig_tz
        if hasattr(time, "tzset"):
            time.tzset()
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
