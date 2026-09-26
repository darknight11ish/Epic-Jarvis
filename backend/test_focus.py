"""test_focus.py - focus sessions: a timer plus Quiet, drifts named out loud
on this PC, and NOTHING of what was in front kept (the owner's decision of
2026-09-25).

    python3 backend/test_focus.py

What it proves, with a clock the test moves by hand, a stand-in for the
Windows reader (what is "in front" is whatever the test says), the REAL
scheduler on a temporary SQLite file, the rebuilt jarvis_power.py and the
REAL jarvis_power_switch.py (only the gate is a stand-in, saying "auto"):

  - off unless started: nothing is read before a session starts or after it
    ends, and importing the module starts nothing;
  - the deferred lock: Jarvis's own windows are home base and never settle;
    Windows' own surfaces (desktop, taskbar, lock screen) count as nothing;
    one look does not lock, two looks in a row on the same app (and site)
    do, and "Locked on." is said; a browser whose site cannot be read locks
    on the browser alone only after APP_ONLY_AFTER_S, and says so;
  - drifts: the grace, the count, the canned lines - three tiers of four,
    named or nameless, warm or plain - the first one naming the owner's own
    "on what", the nag while one drift lasts, and "call me out every ...";
  - home base inside a drift neither counts nor splits it;
  - snooze, "I need a minute", "I'm doing research" (now, just after, and in
    advance), pause, resume, extend, "lock on this" (from the app, and from
    Jarvis's own window), stop;
  - the timer is ONE job on the one scheduler, kind "focus", not listed in
    Coming up and telling nobody; it ends the session and the report card
    is said; pause takes the job off and resume puts a new one on;
  - Quiet during the session, and Active again at the end ONLY if focus set
    it and nobody changed it since;
  - THE PRIVACY LAW: with a made-up program and site nobody would write in
    canned text, the name reaches the spoken line and the voice - and
    nowhere else: not the status, the diag, the report card, the ledger, the
    audit log, the events, the scheduler's file, a spoken "how am I doing?",
    or the engine's memory once the line was said or expired;
  - fingerprints are salted per session: the same app gives a different key
    in the next session;
  - the ledger holds numbers and true/false only, whatever it is handed;
  - the spoken line goes only to this PC (another address is refused), once;
  - no socket is opened by a whole session; the voice is made without
    say()'s bookkeeping, so no question window (and no microphone) opens;
  - the fast path: every command, the short ones only while a session runs,
    and near misses left for the rest of the grammar or the model;
  - focus.patch applies after the whole stack, reverses, checks origin and
    token, and its blocks run; the module is shipped and loaded by the
    scheduler.
No network, no model.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, missing, require_shipped  # noqa: E402

require_shipped("jarvis_focus.py", "jarvis_schedule.py", "jarvis_quick.py",
                "jarvis_power_switch.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-focus-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
_FW_AUDIT = []
fw.audit_log = lambda event, detail=None, **k: _FW_AUDIT.append((event, detail))
fw.action_tier = lambda action: "auto"
sys.modules["jarvis_framework"] = fw


class _Verdict:
    allowed, tier, outcome, reason = True, "auto", "auto", "tier is auto"


_gate = types.ModuleType("jarvis_gate")
_gate.check = lambda action, detail, prompt="": _Verdict()
sys.modules["jarvis_gate"] = _gate
if missing("jarvis_power.py"):
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_schedule as S  # noqa: E402
import jarvis_focus as F  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_power as P  # noqa: E402
import jarvis_power_switch as PS  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = float(t)

    def __call__(self):
        return self.t


WORK = {"exe": r"C:\Program Files\Code\Code.exe", "title": "essay.md - Code",
        "cls": "Chrome_WidgetWin_1"}
DOCS = {"exe": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "title": "Essay - Google Docs - Google Chrome", "cls": "Chrome_WidgetWin_1",
        "host": "docs.google.com"}
YOUTUBE = dict(DOCS, title="cats - YouTube - Google Chrome", host="www.youtube.com")
GMAIL = dict(DOCS, title="Inbox - Gmail", host="mail.google.com")
CHROME_TYPING = dict(DOCS, host="")           # the address box can't be read
SLACK = {"exe": r"C:\Users\me\AppData\Local\slack\slack.exe", "title": "Slack",
         "cls": "Chrome_WidgetWin_1"}
JARVIS = {"exe": r"C:\Program Files\Jarvis Desktop\jarvis-desktop.exe", "title": "Jarvis",
          "cls": "Tauri Window"}
JARVIS_WIDGET = {"exe": r"C:\x\other.exe", "title": "Jarvis Desktop Widget", "cls": "x"}
DESKTOP = {"exe": r"C:\Windows\explorer.exe", "title": "Program Manager", "cls": "Progman"}
LOCKSCREEN = {"exe": r"C:\Windows\SystemApps\LockApp.exe", "title": "", "cls": "x"}

# THE MADE-UP NAMES. Nobody would write these in canned text, so finding
# one anywhere can only mean it leaked from what was "in front".
FAKE_APP = "Zqxwarblefonk"
FAKE_SITE = "plimbertonfrazzle.example"
FAKE_TITLE = "Glorbnax quarterly secrets"
MADE_UP_APP = {"exe": rf"C:\Games\{FAKE_APP}.exe", "title": FAKE_TITLE, "cls": "Glorbnax"}
MADE_UP_SITE = dict(DOCS, title=FAKE_TITLE + " - Google Chrome",
                    host=f"https://www.{FAKE_SITE}/private/path?token=glorbnaxtoken")
LEAKS = (FAKE_APP.lower(), "plimberton", "frazzle", "glorbnax")


class World:
    """An engine with a hand-moved clock, the real scheduler and stand-ins
    for what is in front, the bus and the audit log."""

    def __init__(self, *, power=False, manner="warm", name="w"):
        self.clock = Clock()
        self.front = None
        self.looks = 0
        self.events, self.audits = [], []
        self.db = _TMP / f"{name}-{len(os.listdir(_TMP))}.db"
        self.ledger = self.db.with_suffix(".json")
        self.s = S.Scheduler(self.db, clock=self.clock, spawn=lambda fn: fn(),
                             publish=lambda k, d: self.events.append((k, d)))

        def probe():
            self.looks += 1
            return dict(self.front) if self.front else None
        no_power = lambda: (_ for _ in ()).throw(RuntimeError("no power here"))  # noqa: E731
        self.e = F.Engine(clock=self.clock, probe=probe, sched=lambda: self.s,
                          power=(lambda: P) if power else no_power,
                          switch=(lambda: PS) if power else no_power,
                          publish=lambda k, d: self.events.append((k, d)),
                          audit=lambda ev, d: self.audits.append((ev, d)),
                          ledger=self.ledger, manner_of=lambda: manner, threads=False)
        self.e._rot = [0, 0, 0]
        self.said = []

    def at(self, front, seconds=1, ticks=1):
        """`ticks` looks, `seconds` apart, with `front` in front. Collects
        what would have been said."""
        self.front = front
        for _ in range(ticks):
            self.clock.t += seconds
            self.e.tick()
            self.collect()

    def collect(self):
        m = self.e._mail
        if m is not None:
            self.said.append(self.e.take_line(m[0]))

    def start(self, minutes=30, intent=""):
        code, out = self.e.start(minutes, intent, by="this PC")
        self.e._rot = [0, 0, 0]      # the lines in order, so the test can name them
        self.collect()
        return code, out

    def lock_on_work(self, front=None):
        self.at(JARVIS)
        self.at(front or WORK, ticks=2)


# --------------------------------------------------------------------------

def t_off_unless_started():
    w = World()
    w.at(YOUTUBE, ticks=5)
    check("before a session nothing is read (the reader is never asked)", w.looks == 0)
    check("... nothing is said and no event goes out", not w.said and not w.events)
    check("importing the module starts no look thread", not F.ENGINE.thread_alive()
          and not F.ENGINE.on)
    w.start()
    w.lock_on_work()
    w.e.act("stop")
    n = w.looks
    w.at(YOUTUBE, ticks=5)
    check("after it ends nothing is read again", w.looks == n)
    code, out = w.e.act("pause")
    check("a command with no session is a plain 409", code == 409
          and out["error"] == "No focus session is running.")


def t_the_deferred_lock():
    w = World()
    code, out = w.start(30)
    check("start answers 200 and says to go to the work", code == 200
          and "lock on there once you settle" in out["said"], out)
    st = w.e.status()
    check("... deferred, no target, 30 minutes", st["deferred"] and not st["locked"]
          and st["minutes"] == 30 and st["left_s"] == 1800, st)
    w.at(JARVIS, ticks=10)
    w.at(JARVIS_WIDGET, ticks=5)
    check("Jarvis's own windows are home base: they never settle",
          w.e.status()["deferred"] and not w.said)
    w.at(DESKTOP, ticks=5)
    w.at(LOCKSCREEN, ticks=5)
    check("the desktop and the lock screen count as nothing", w.e.status()["deferred"])
    w.at(WORK)
    check("ONE look does not lock", w.e.status()["deferred"])
    w.at(SLACK)
    w.at(WORK)
    check("a different app resets the settle count", w.e.status()["deferred"]
          and w.e.diag()["settle_ticks"] == 1)
    w.at(WORK)
    st = w.e.status()
    check("two looks in a row on the same app lock on", st["locked"] and st["lock"] == "app"
          and not st["deferred"], st)
    check("... and say \"Locked on.\"", w.said == [F.LOCKED_LINE], w.said)
    check("... and the status line says on target", st["line"].endswith("on target."), st)

    w = World()
    w.start()
    w.at(DOCS, ticks=2)
    st = w.e.status()
    check("in a browser whose site is read, it locks on the app AND the site",
          st["lock"] == "app_and_site", st)
    w.at(YOUTUBE, ticks=2)
    check("... another site in the same browser is a drift", w.e.status()["drifting"]
          and w.e.status()["drifts"] == 1)

    w = World()
    w.start()
    w.at(CHROME_TYPING, ticks=2)
    check("a browser whose site cannot be read does not lock at once (no guessing)",
          w.e.status()["deferred"])
    w.at(CHROME_TYPING, ticks=int(F.APP_ONLY_AFTER_S) - 3)
    check("... not before APP_ONLY_AFTER_S", w.e.status()["deferred"])
    w.at(CHROME_TYPING, ticks=3)
    st = w.e.status()
    check("... then it locks on the browser alone", st["locked"] and st["lock"] == "app", st)
    check("... and says so out loud", w.said[-1] == F.LOCKED_APP_ONLY_LINE, w.said)


def t_drifts_and_the_lines():
    w = World()
    w.start(30, "the Essay")
    w.lock_on_work()
    w.said.clear()
    w.front = YOUTUBE
    w.clock.t += 1
    w.e.tick()
    w.collect()
    check("the first look away is inside the grace: no drift, nothing said",
          w.e.status()["drifts"] == 0 and not w.said)
    w.at(WORK)
    check("a blip shorter than the grace is not a drift", w.e.status()["drifts"] == 0
          and not w.e.status()["drifting"])
    w.at(YOUTUBE, ticks=2)
    check("still away at the next look: one drift", w.e.status()["drifts"] == 1)
    check("the first callout names the distraction AND the owner's own words",
          w.said == ["YouTube doesn't look like the Essay to me."], w.said)
    w.at(YOUTUBE, ticks=10)
    check("no second line before the nag time", len(w.said) == 1)
    w.at(YOUTUBE, ticks=int(F.NAG_EVERY_S))
    check("while one drift lasts it says something again (a firmer tier)",
          len(w.said) == 2 and w.said[1] == F.WARM_NAMED[1][0].format(name="YouTube"), w.said)
    check("... and it is still ONE drift", w.e.status()["drifts"] == 1)
    w.at(WORK)
    w.at(GMAIL, ticks=2)
    check("a second drift is named by the site's own name, in tier two",
          w.said[-1] == F.WARM_NAMED[1][1].format(name="Gmail"), w.said)
    w.at(WORK)
    w.at(MADE_UP_SITE, ticks=2)
    check("an unmapped site is said by its bare domain", FAKE_SITE in w.said[-1], w.said)
    w.at(WORK)
    w.at(SLACK, ticks=2)
    check("an app is said by its name", "Slack" in w.said[-1], w.said)
    check("the lines escalate to tier three and stay there",
          w.said[-1] in [x.format(name="Slack") for x in F.WARM_NAMED[2]], w.said)
    check("every tier has four lines, named and nameless, warm and plain",
          all(len(t) == 4 for pools in (F.WARM_NAMED, F.WARM_NAMELESS, F.PLAIN_NAMED,
                                        F.PLAIN_NAMELESS) for t in pools)
          and all(len(p) == 3 for p in (F.WARM_NAMED, F.WARM_NAMELESS, F.PLAIN_NAMED,
                                        F.PLAIN_NAMELESS)))
    check("every named line has a place for the name; no nameless one does",
          all("{name}" in x for p in (F.WARM_NAMED, F.PLAIN_NAMED) for t in p for x in t)
          and not any("{" in x for p in (F.WARM_NAMELESS, F.PLAIN_NAMELESS)
                      for t in p for x in t))
    check("no line says \"stop\" (the stop word) - so Jarvis never stops itself",
          not any(re.search(r"\bstop\b", x, re.I) for p in (F.WARM_NAMED, F.WARM_NAMELESS,
                  F.PLAIN_NAMED, F.PLAIN_NAMELESS) for t in p for x in t))

    w = World(manner="plain")
    w.start(30, "the essay")
    w.lock_on_work()
    w.at(YOUTUBE, ticks=2)
    check("the plain manner is businesslike, and does not play with the owner's words",
          w.said[-1] == "Off target: YouTube.", w.said)

    saved = F.NAMING
    F.NAMING = False
    try:
        w = World()
        w.start()
        w.lock_on_work()
        w.at(YOUTUBE, ticks=2)
        check("with NAMING off the nameless lines are used",
              w.said[-1] == F.WARM_NAMELESS[0][0] and "YouTube" not in w.said[-1], w.said)
    finally:
        F.NAMING = saved

    w = World()
    w.start()
    w.lock_on_work()
    code, out = w.e.act("nag", 30)
    check("\"call me out every 30 seconds\" sets the nag", w.e.nag_every == 30
          and "30 seconds" in out["said"], out)
    w.e.act("nag", 1)
    check("... never more often than NAG_MIN_S", w.e.nag_every == F.NAG_MIN_S)


def t_home_base_inside_a_drift():
    w = World()
    w.start()
    w.lock_on_work()
    w.at(YOUTUBE, ticks=3)
    adrift = w.e.adrift_s
    w.at(JARVIS, ticks=20)
    check("time at home base in the middle of a drift is not counted as adrift",
          w.e.adrift_s == adrift)
    w.at(YOUTUBE, ticks=2)
    check("... and going back is the SAME drift, not a second one",
          w.e.status()["drifts"] == 1)


def t_snooze_relief_research():
    w = World()
    w.start()
    w.lock_on_work()
    code, out = w.e.act("snooze", 10)
    check("snooze: no callouts for the time asked", "10 minutes" in out["said"], out)
    w.said.clear()
    w.at(YOUTUBE, ticks=5)
    check("... a drift while snoozed is said to nobody, but counted",
          not w.said and w.e.status()["drifts"] == 1)
    check("... and the status says how long is left of it", "No callouts for" in
          w.e.status()["note"])
    w.clock.t += 600
    w.at(YOUTUBE)
    check("... after it, the callouts come back", len(w.said) == 1, w.said)

    w = World()
    w.start()
    w.lock_on_work()
    code, out = w.e.act("relief")
    check("\"I need a minute\": no nudges for three minutes", "3 minutes" in out["said"])
    w.said.clear()
    w.at(YOUTUBE, ticks=100)
    check("... none inside them", not w.said)
    w.clock.t += 100
    w.at(YOUTUBE)
    check("... and back after", len(w.said) == 1)

    w = World()
    w.start()
    w.lock_on_work()
    w.at(YOUTUBE, ticks=10)
    check("drifting: counted", w.e.status()["drifts"] == 1 and w.e.status()["adrift_s"] > 0)
    code, out = w.e.act("research")
    st = w.e.status()
    check("\"I'm doing research\" while away refunds THIS trip: no drift, no time adrift",
          st["drifts"] == 0 and st["adrift_s"] == 0 and st["excused_s"] > 0, st)
    w.said.clear()
    w.at(YOUTUBE, ticks=3 * int(F.NAG_EVERY_S))
    check("... and nothing is said until back on the work", not w.said
          and w.e.status()["line"].endswith("research, not counted."))
    w.at(WORK)
    w.at(YOUTUBE, ticks=2)
    check("back on the work, the next trip counts again", w.e.status()["drifts"] == 1
          and len(w.said) == 1)

    w = World()
    w.start()
    w.lock_on_work()
    w.at(YOUTUBE, ticks=6)
    w.at(WORK)
    w.clock.t += 20
    w.e.act("research")
    check("said just AFTER coming back, it still refunds that trip",
          w.e.status()["drifts"] == 0 and w.e.status()["adrift_s"] == 0)

    w = World()
    w.start()
    w.lock_on_work()
    code, out = w.e.act("research")
    check("said in advance, it says the next trip won't count",
          "next trip away" in out["said"], out)
    w.at(WORK, ticks=3)
    w.at(YOUTUBE, ticks=5)
    check("... the next trip is not counted", w.e.status()["drifts"] == 0 and not
          [x for x in w.said if x != F.LOCKED_LINE])


def t_found_in_the_audit():
    w = World()
    w.start()
    w.lock_on_work()
    w.at(YOUTUBE, ticks=4)
    w.e.act("research")
    code, out = w.e.act("research")
    check("\"I'm doing research\" said twice on one trip refunds nothing more",
          out["said"] == "Already noted - this trip doesn't count.", out)
    saved = F.ENGINE
    F.ENGINE = w.e
    try:
        code, out = F.handle_act({"do": "nag", "seconds": 45})
        check("the route's nag takes SECONDS", code == 200 and w.e.nag_every == 45, out)
        code, out = F.handle_act({"do": "extend", "minutes": 5})
        check("... and extend takes minutes", code == 200 and w.e.status()["minutes"] == 35, out)
    finally:
        F.ENGINE = saved

    # A look that was being taken when the session ended changes nothing.
    w = World()
    w.start()
    w.lock_on_work()

    def ends_mid_look():
        w.e.finish(completed=False, speak=False)
        return dict(YOUTUBE)
    w.e.probe = ends_mid_look
    w.clock.t += 1
    w.e.tick()
    w.clock.t += 1
    w.e.tick()
    st = w.e.status()
    check("a session that ended during a look is not drifted, spoken to or counted",
          not st["on"] and st["report"]["drifts"] == 0 and w.e._mail is None, st)


def t_lock_on_this():
    w = World()
    w.start()
    w.lock_on_work()
    w.at(DOCS, ticks=4)
    check("docs is a drift from the code editor", w.e.status()["drifts"] == 1)
    w.front = DOCS
    code, out = w.e.act("lock")
    st = w.e.status()
    check("\"lock on this\" from the app itself locks on it now", st["lock"] == "app_and_site"
          and out["said"].startswith(F.LOCKED_LINE), out)
    check("... and forgives the trip that got it there", st["drifts"] == 0
          and "doesn't count" in out["said"], out)
    w.at(DOCS, ticks=3)
    check("... it is now on target", w.e.status()["on_target"] is True)
    w.front = JARVIS
    code, out = w.e.act("lock")
    check("from Jarvis's own window (a button, or typing to it) it waits for the owner "
          "to land instead - it never locks on Jarvis", out["said"] == F.REARM_LINE
          and w.e.status()["deferred"], out)
    w.at(WORK, ticks=2)
    check("... and locks where they land", w.e.status()["lock"] == "app"
          and w.said[-1] == F.LOCKED_LINE)


def t_pause_resume_extend_and_the_scheduler():
    w = World()
    w.start(30)
    jid = w.e.job_id
    job = w.s.job(jid)
    check("the end is ONE job on the one scheduler, kind \"focus\"",
          job and job["kind"] == F.KIND and abs(job["left"] - 1800) < 2, job)
    check("... not listed in Coming up (the focus panel counts down)",
          not [j for j in w.s.listed() if j["kind"] == F.KIND])
    check("... and it tells nobody when it goes off", job.get("notify") is False
          and S.KINDS[F.KIND].notify is False)
    w.lock_on_work()
    w.clock.t += 300
    code, out = w.e.act("pause")
    check("pause keeps the time left and takes the job off", w.e.status()["paused"]
          and w.s.job(jid) is None and "Nothing is watched" in out["said"], out)
    left = w.e.status()["left_s"]
    n = w.looks
    w.at(YOUTUBE, ticks=30)
    check("... while paused nothing is read and nothing counts", w.looks == n
          and w.e.status()["drifts"] == 0 and w.e.status()["left_s"] == left)
    w.e.act("resume")
    check("resume puts ONE new job on, at the time left", w.e.job_id != jid
          and abs(w.s.job(w.e.job_id)["left"] - left) < 2)
    code, out = w.e.act("extend", 10)
    check("extend moves the end by the minutes asked", w.e.status()["minutes"] == 40
          and abs(w.s.job(w.e.job_id)["left"] - (left + 600)) < 2, out)
    code, out = w.e.act("extend", 999)
    check("... never past MAX_MINUTES", w.e.status()["minutes"] == 40
          and str(F.MAX_MINUTES) in out["said"])
    w.at(WORK, ticks=5)
    w.clock.t = w.e.ends_at + 1
    fired = w.s.tick()
    check("the scheduler's job going off...", w.e.job_id == "" or fired, fired)
    kind = S.KINDS[F.KIND]
    # The real scheduler spawns on_fire; the module's own is wired to F.ENGINE,
    # so this world calls its engine's.
    w.e.on_fire(fired[0] if fired else "")
    st = w.e.status()
    check("... ends the session, completed", not st["on"] and st["report"]["completed"], st)
    check("... and the report card is said", w.e._mail is not None
          and w.e._mail[1].startswith("Focus session done."), w.e._mail)
    check("the kind's on_fire is the module engine's", kind.on_fire is F._on_fire)

    w = World()
    w.start(30)
    w.e.on_scheduler = False
    w.e.job_id = ""
    w.lock_on_work()
    w.clock.t = w.e.ends_at + 1
    w.e.tick()
    check("with no scheduler, the look ends it at its time instead",
          not w.e.status()["on"] and w.e.status()["report"]["completed"])


def t_the_report_card_and_the_ledger():
    w = World()
    w.start(10)
    w.lock_on_work()
    w.at(WORK, ticks=8 * 60)
    w.at(YOUTUBE, ticks=60)
    w.at(WORK, ticks=10)
    w.clock.t = w.e.ends_at + 1
    rep = w.e.finish(completed=True)
    check("the report card: on target, drifts, minutes adrift, percent",
          rep["drifts"] == 1 and rep["on_target_min"] >= 8 and rep["adrift_min"] == 1
          and rep["percent"] is not None and rep["lines"][0].startswith("On target: "), rep)
    check("... a session 85% on target, run to the end, is clean and starts a streak",
          rep["clean"] and rep["streak"] == 1 and "Streak: 1 clean session in a row." in
          rep["lines"], rep)
    rows = F.read_ledger(w.ledger)
    check("the ledger holds one row, with only the whitelisted keys",
          len(rows) == 1 and list(rows[0]) == list(F.LEDGER_KEYS), rows)
    w.start(10)
    w.lock_on_work()
    w.at(YOUTUBE, ticks=5 * 60)
    code, out = w.e.act("stop")
    rep = w.e.status()["report"]
    check("stopped early and mostly adrift: not clean, the streak starts again",
          not rep["clean"] and rep["streak"] == 0 and rep["title"] ==
          "Focus session stopped early.", rep)
    check("\"stop focus\" answers with the report, and the PC does not say it a second "
          "time", out["said"] == rep["spoken"] and w.e._mail is None, out)
    raw = json.loads(w.ledger.read_text())
    check("... the ledger file has two rows of numbers and true/false only",
          len(raw) == 2 and all(isinstance(v, (int, bool)) for r in raw for v in r.values()),
          raw)

    row = F.ledger_row({"at": "yesterday", "planned_min": "thirty", "drifts": FAKE_APP,
                        "percent": None, "completed": "yes", "label": FAKE_SITE,
                        "on_target_min": 12.6})
    check("ledger_row turns every value into a number or true/false, and drops "
          "anything not whitelisted - a word cannot survive it",
          set(row) == set(F.LEDGER_KEYS) and row["on_target_min"] == 13
          and row["percent"] == -1 and FAKE_SITE not in json.dumps(row)
          and FAKE_APP not in json.dumps(row), row)
    w2 = World()
    rows = [dict(r, clean=True) for r in F.read_ledger(w.ledger)] + [
        F.ledger_row({"clean": False}), F.ledger_row({"clean": True}),
        F.ledger_row({"clean": True})]
    check("the streak is the clean sessions at the end, in a row", F.streak_of(rows) == 2)
    F.write_ledger(rows * 100, w2.ledger)
    check("the ledger keeps the last LEDGER_KEEP sessions",
          len(F.read_ledger(w2.ledger)) == F.LEDGER_KEEP)
    st = w2.e.status()
    check("with no session this run, the status shows the last report from the ledger",
          st["report"] and st["report"]["streak"] == 2 and not st["on"], st)


def t_quiet_and_back():
    P.set_mode("active", why="startup")
    w = World(power=True)
    code, out = w.start(20)
    check("started while Active: Jarvis goes Quiet, recorded as the focus session's",
          P.current() == "quiet" and P.status()["why"] == F.WHY
          and "Quiet until it ends" in out["said"], (P.status(), out))
    w.lock_on_work()
    w.e.act("stop")
    check("at the end: Active again", P.current() == "active")

    P.set_mode("active", why="startup")
    w = World(power=True)
    w.start(20)
    PS.set_mode("standby", by="this PC", wait_s=5, models=types.SimpleNamespace(
        resident_models=lambda: [], unload=lambda n: None),
        ollama=types.SimpleNamespace(url=None), others=[])
    w.e.act("stop")
    check("the owner chose Standby during the session: it stays on Standby",
          P.current() == "standby")

    P.set_mode("quiet", why="the owner, from this PC")
    w = World(power=True)
    code, out = w.start(20)
    check("started while already Quiet: left alone, and nothing claims it",
          "Quiet until it ends" not in out["said"] and not w.e.set_quiet, out)
    w.e.act("stop")
    check("... and the end does not wake it", P.current() == "quiet")
    P.set_mode("active", why="startup")


def _all_text(w: World, extra=()) -> str:
    """Everything that is kept or leaves the engine, as one string."""
    parts = [json.dumps(w.e.status()), json.dumps(w.e.diag()),
             json.dumps(w.events), json.dumps(w.audits, default=str),
             json.dumps(_FW_AUDIT, default=str)]
    if w.ledger.exists():
        parts.append(w.ledger.read_text(encoding="utf-8", errors="replace"))
    parts.append(w.db.read_bytes().decode("utf-8", "replace"))
    with sqlite3.connect(w.db) as c:
        parts.append(json.dumps([list(r) for r in c.execute("SELECT * FROM jobs")], default=str))
    parts.extend(extra)
    return "\n".join(parts).lower()


def _engine_memory(e) -> str:
    out = []
    for k, v in vars(e).items():
        if k in ("clock", "probe", "_sched", "_power", "_switch", "publish", "audit",
                 "manner_of", "_lock", "_stop", "_thread"):
            continue
        out.append(f"{k}={v!r}")
    return "\n".join(out).lower()


def t_the_privacy_law():
    w = World()
    w.start(30, "the essay")
    w.lock_on_work()
    w.said.clear()
    w.at(MADE_UP_SITE, ticks=2)
    site_line = list(w.said)
    w.at(WORK)
    w.at(MADE_UP_APP, ticks=2)
    app_line = w.said[len(site_line):]
    check("the made-up site IS named in the spoken line (the test really drove a callout)",
          site_line and FAKE_SITE in site_line[0], site_line)
    check("... and so is the made-up app", app_line and FAKE_APP in app_line[0], app_line)
    check("the spoken line names the SITE, never the page's address or its secrets",
          not [x for x in site_line if "private" in x or "token" in x or "glorbnax" in x.lower()])
    # "how am I doing?" through the real fast path, with this world's engine.
    saved = F.ENGINE
    F.ENGINE = w.e
    try:
        reply = Q.answer("how am I doing?", sched=w.s, now=w.clock.t)
    finally:
        F.ENGINE = saved
    check("\"how am I doing?\" is answered from counts", reply is not None
          and "drift" in reply.reply, reply)
    mid = _all_text(w, extra=[reply.reply if reply else ""])
    check("DURING the session: no made-up name in the status, the diag, the events, the "
          "audit log, the scheduler's file or the spoken status",
          not [x for x in LEAKS if x in mid], [x for x in LEAKS if x in mid])
    check("... nor in the engine's own memory once the line was said",
          not [x for x in LEAKS if x in _engine_memory(w.e)],
          [x for x in LEAKS if x in _engine_memory(w.e)])
    # A line nobody fetched is erased after CALLOUT_TTL_S.
    w.at(WORK)
    w.front = MADE_UP_SITE
    for _ in range(2):
        w.clock.t += 1
        w.e.tick()
    w.e.nag_every = F.NAG_MIN_S
    for _ in range(int(F.NAG_MIN_S)):
        w.clock.t += 1
        w.e.tick()
    check("a line waiting to be fetched holds the name (for up to CALLOUT_TTL_S)",
          w.e._mail is not None and FAKE_SITE in w.e._mail[1], w.e._mail)
    w.front = WORK
    w.clock.t += F.CALLOUT_TTL_S + 1
    w.e.tick()
    check("... and nobody fetching it erases it at the next look after that",
          w.e._mail is None and not [x for x in LEAKS if x in _engine_memory(w.e)])
    w.e.act("stop")
    after = _all_text(w)
    check("AFTER the session: no made-up name in the report card, the ledger or anywhere "
          "above", not [x for x in LEAKS if x in after], [x for x in LEAKS if x in after])
    check("... nor the page's secret path, token or title",
          "private/path" not in after and "glorbnaxtoken" not in after)


def t_fingerprints_are_per_session():
    salt1, salt2 = b"a" * 32, b"b" * 32
    a1, a2 = F.look_from(WORK, salt1), F.look_from(WORK, salt2)
    check("the same app gives a different fingerprint in another session",
          a1.app_key and a1.app_key != a2.app_key)
    check("... and the same one within a session", F.look_from(WORK, salt1).app_key == a1.app_key)
    y = F.look_from(YOUTUBE, salt1)
    check("the fingerprint is not the name", "youtube" not in y.site_key
          and "chrome" not in y.app_key)
    check("www. and m. are the same site; docs and mail are two",
          F.look_from(dict(YOUTUBE, host="m.youtube.com"), salt1).site_key == y.site_key
          and F.look_from(GMAIL, salt1).site_key != F.look_from(DOCS, salt1).site_key)
    check("the address is cut to its host", F.host_of("https://www.youtube.com/watch?v=1")
          == "www.youtube.com" and F.host_of("youtube.com/watch") == "youtube.com")
    check("text typed in the address box is not a site", F.host_of("how to boil an egg") == ""
          and F.host_of("egg") == "")
    check("names: a big site, a bare domain, an app, a Store-less exe",
          (F.site_name("www.instagram.com"), F.site_name("news.bbc.co.uk"),
           F.site_name("blog.example.com"), F.app_name("slack.exe"), F.app_name("my_game.exe"))
          == ("Instagram", "the BBC", "example.com", "Slack", "My game"))
    w = World()
    w.start()
    w.lock_on_work()
    s1 = w.e._t_app
    w.e.act("stop")
    w.start()
    w.lock_on_work()
    check("the target fingerprint differs between two sessions on the same app",
          s1 and w.e._t_app and s1 != w.e._t_app)
    w.e.act("stop")
    check("... and the session's key is dropped at the end", w.e._salt == b""
          and w.e._t_app == "")


class _FakeSpeech(types.ModuleType):
    def __init__(self):
        super().__init__("jarvis_speech")
        self.heard = []
        self.said_calls = 0

    def _synthesise(self, text, start_better=True):
        self.heard.append(text)
        return [0.0] * 160, 16000, "kokoro", "builtin", "", "", ""

    def _write_wav(self, samples, rate):
        return b"RIFF" + b"\0" * 40

    def say(self, *a, **k):          # must never be used: it keeps the text
        self.said_calls += 1
        return None


def t_the_line_goes_to_this_pc_only():
    w = World()
    saved_engine, saved_speech = F.ENGINE, sys.modules.get("jarvis_speech")
    fake = _FakeSpeech()
    sys.modules["jarvis_speech"] = fake
    F.ENGINE = w.e
    try:
        w.start()
        w.at(JARVIS)
        w.front = WORK
        w.clock.t += 1
        w.e.tick()
        w.clock.t += 1
        w.e.tick()
        seq = w.e._mail[0]
        code, out, ctype = F.handle_callout(f"seq={seq}", "100.64.0.7")
        check("the phone (or any other address) is refused the spoken line", code == 403
              and w.e._mail is not None)
        code, out, ctype = F.handle_callout(f"seq={seq + 1}", "127.0.0.1")
        check("a wrong number gets nothing, and the line stays", code == 404
              and w.e._mail is not None)
        code, out, ctype = F.handle_callout(f"seq={seq}", "127.0.0.1")
        check("this PC gets the line as SOUND (a WAV), not as words",
              code == 200 and ctype == "audio/wav" and out.startswith(b"RIFF")
              and FAKE_SITE.encode() not in out)
        check("... through the voice's _synthesise, never say() (which keeps what was said "
              "and can open the listening window)", fake.said_calls == 0 and fake.heard
              and "Locked on." in fake.heard[0])
        code, out, ctype = F.handle_callout(f"seq={seq}", "::1")
        check("... once: asked again, it is gone", code == 404 and out["reason"] == "no_line")
        # A drift to the made-up site: its line is fetched.
        w.at(WORK, ticks=3)
        w.said.clear()
        w.front = MADE_UP_SITE
        for _ in range(2):
            w.clock.t += 1
            w.e.tick()
        seq = w.e._mail[0]
        code, out, ctype = F.handle_callout(f"seq={seq}", "127.0.0.1")
        check("a drift's line reaches the voice with the name in it - the one place it goes",
              code == 200 and FAKE_SITE in fake.heard[-1] and w.e._mail is None, fake.heard)
        w.front = WORK
        w.clock.t += 1
        w.e.tick()
        w.front = SLACK
        for _ in range(2):
            w.clock.t += 1
            w.e.tick()
        seq = w.e._mail[0]
        w.clock.t += F.CALLOUT_TTL_S + 1
        code, out, ctype = F.handle_callout(f"seq={seq}", "127.0.0.1")
        check("a line that waited longer than CALLOUT_TTL_S is gone", code == 404
              and w.e._mail is None)
        check("from_this_pc: loopback only", F.from_this_pc("127.0.0.1") and
              F.from_this_pc("::1") and F.from_this_pc("::ffff:127.0.0.1")
              and not F.from_this_pc("100.64.0.7") and not F.from_this_pc("192.168.1.5")
              and not F.from_this_pc(""))
    finally:
        F.ENGINE = saved_engine
        if saved_speech is None:
            sys.modules.pop("jarvis_speech", None)
        else:
            sys.modules["jarvis_speech"] = saved_speech


def t_no_socket_no_model_no_microphone():
    real = socket.socket.connect
    opened = []

    def refuse(self, *a, **k):
        opened.append(a)
        raise OSError("no network in this test")
    socket.socket.connect = refuse
    try:
        w = World()
        w.start(30, "the essay")
        w.lock_on_work()
        w.at(YOUTUBE, ticks=3)
        w.e.act("research")
        w.e.act("snooze")
        w.at(WORK, ticks=3)
        w.e.act("stop")
    finally:
        socket.socket.connect = real
    check("a whole session opens no socket", not opened, opened)
    src = (HERE / "jarvis_focus.py").read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"#.*", "", code)
    check("no AI model: nothing here talks to the chat path or Ollama",
          not re.search(r"jarvis_agent|ollama|/api/chat|jarvis_router", code, re.I))
    check("it never opens a microphone: no hear(), no wake switch, no listening window, "
          "and not say() (which opens the window after a question)",
          not re.search(r"\.hear\(|set_wake_enabled|_open_awake|_note_said|jarvis_speech\.say\(",
                        code))
    check("no answer it gives ends with a question, so the phone's \"keep listening after "
          "a question\" never opens its microphone because of one",
          not re.search(r"\?\"\s*[,)\]]|\?\"$", code, re.M), re.findall(r".{30}\?\"", code))
    check("it sends no input: no clicks, no keys", not re.search(
        r"SendKeys|\.Click\(|SendInput|keybd_event|mouse_event", code))


def _q(text, on_engine, now):
    saved = F.ENGINE
    F.ENGINE = on_engine
    try:
        return Q.match(text, now)
    finally:
        F.ENGINE = saved


def t_the_fast_path():
    w = World()
    now = w.clock.t
    starts = {
        "focus for 30 minutes": (30, ""),
        "Jarvis, focus for 30 minutes on the Essay please": (30, "the Essay"),
        "start a focus session": (None, ""),
        "let's focus for an hour": (60, ""),
        "a 45 minute focus session": (45, ""),
        "30 minutes of focus": (30, ""),
        "start focusing for 20 minutes": (20, ""),
        "help me focus for half an hour": (30, ""),
        "focus on the thumbnail sprint for 25 minutes": (25, "the thumbnail sprint"),
        "focus mode for 90 minutes": (90, ""),
    }
    for text, (mins, on) in starts.items():
        got = _q(text, w.e, now)
        ok = got is not None and got.name == "focus_start" and got.f.get("minutes") == mins \
            and (got.f.get("text") or "") == on
        check(f"start: {text!r}", ok, got)
    for text in ("focus on the positives", "I can't focus", "how do I focus better",
                 "what is focus mode", "focus"):
        got = _q(text, w.e, now)
        check(f"not a command (left for the model): {text!r}", got is None
              or not got.name.startswith("focus_"), got)
    always = {"stop focus": "focus_stop", "end the focus session": "focus_stop",
              "I'm done focusing": "focus_stop", "pause focus": "focus_pause",
              "resume the focus session": "focus_resume", "extend focus by 10 minutes":
              "focus_extend", "add 15 minutes to my focus session": "focus_extend",
              "how's my focus going": "focus_status", "focus status": "focus_status"}
    for text, name in always.items():
        got = _q(text, w.e, now)
        check(f"explicit, even with no session: {text!r}", got is not None and got.name == name,
              got)
    short = {"pause": "focus_pause", "resume": "focus_resume", "snooze": "focus_snooze",
             "snooze for 10 minutes": "focus_snooze", "give me fifteen seconds": "focus_snooze",
             "I need a minute": "focus_relief", "give me a minute": "focus_relief",
             "no Jarvis, I need to do something important": "focus_relief",
             "I'm doing research": "focus_research",
             "it's okay, I'm doing research": "focus_research",
             "this is research": "focus_research", "lock on this": "focus_lock",
             "lock on this tab": "focus_lock", "keep me in this tab": "focus_lock",
             "okay I'm gonna need you to keep me in this tab": "focus_lock",
             "this is the app I'm working in": "focus_lock", "how am I doing?": "focus_status",
             "extend it by 5 minutes": "focus_extend",
             "call me out every thirty seconds": "focus_nag"}
    for text in short:
        got = _q(text, w.e, now)
        check(f"with NO session, the short phrase is not ours: {text!r}", got is None
              or not got.name.startswith("focus_"), got)
    w.start()
    for text, name in short.items():
        got = _q(text, w.e, now)
        check(f"during a session: {text!r}", got is not None and got.name == name, got)
    got = _q("call me out every thirty seconds", w.e, now)
    check("... \"every thirty seconds\" is 30 seconds", got and got.f["seconds"] == 30, got)
    for text, want in (("remind me every 2 hours to stretch", "reminder_set"),
                       ("set a timer for 10 minutes", "timer_set"),
                       ("stop", None), ("pause the timer", "timer_pause")):
        got = _q(text, w.e, now)
        check(f"during a session, other commands keep their meaning: {text!r}",
              (got is None and want is None) or (got is not None and got.name == want), got)
    # Acting, through answer(): the replies are the engine's own words.
    saved = F.ENGINE
    F.ENGINE = w.e
    try:
        w.e.act("stop")
        r = Q.answer("focus for 20 minutes on the Essay", sched=w.s, now=w.clock.t)
        check("\"focus for 20 minutes on the Essay\" starts one, in the owner's capitals",
              r and r.intent == "focus_start" and w.e.on and w.e.intent == "the Essay"
              and "Focus for 20 minutes, on the Essay." in r.reply, r)
        r = Q.answer("focus for 20 minutes", sched=w.s, now=w.clock.t)
        check("a second start while one runs says so", r and "already running" in r.reply, r)
        r = Q.answer("how long is left", sched=w.s, now=w.clock.t)
        check("\"how long is left\" with no timer answers for the session",
              r and r.intent == "focus_status" and "left" in r.reply, r)
        w.s.add_timer(300, "pasta")
        r = Q.answer("how long is left", sched=w.s, now=w.clock.t)
        check("... but a running timer still comes first", r and r.intent == "timer_status", r)
        r = Q.answer("pause", sched=w.s, now=w.clock.t)
        check("\"pause\" pauses the session", r and w.e.paused, r)
        r = Q.answer("stop focus", sched=w.s, now=w.clock.t)
        check("\"stop focus\" ends it with the report card", r and not w.e.on
              and r.reply.startswith("Focus session stopped early."), r)
        check("... and the sentence is not learned as a fact (the scheduler marks it)",
              w.s.was_command("stop focus"))
        r = Q.answer("stop focus", sched=w.s, now=w.clock.t)
        check("\"stop focus\" with none running says so", r and r.reply ==
              "No focus session is running.", r)
        body = {"messages": [{"role": "user", "content": "focus for 30 minutes",
                              "provenance": "clipboard"}]}
        check("pasted text never starts one (only the owner's own words act)",
              Q.answer_turn(body, sched=w.s, now=w.clock.t) is None and not w.e.on)
    finally:
        F.ENGINE = saved


def _rehearse():
    order = _stack.order()
    if "focus.patch" not in order:
        return False, "focus.patch is not in apply-patches.ps1's list", ""
    before = order[:order.index("focus.patch")]
    patch = (HERE / "focus.patch").read_text(encoding="utf-8")
    text, log = _stack.stand_in("jarvis_hud.py", before)
    if text is None:
        return False, "; ".join(log), ""
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-focus-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr, ""
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True, text=True)
        if r.returncode != 0 or (d / "jarvis_hud.py").read_text(encoding="utf-8") != text:
            return False, "does not reverse cleanly: " + r.stderr, ""
        return True, "", after
    finally:
        shutil.rmtree(d, ignore_errors=True)


class _Handler:
    def __init__(self, path="/api/focus", peer="127.0.0.1", body=b"{}"):
        self.sent = None
        self.path = path
        self.client_address = (peer, 5555)
        self.body = body

    def _send(self, code, out, ctype=None):
        self.sent = (code, out, ctype)
        return self.sent


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, why, hud = _rehearse()
    check("focus.patch applies to what the whole stack wrote, and reverses", ok, why)
    if not ok:
        return
    check("... and patches only jarvis_hud.py",
          (HERE / "focus.patch").read_text(encoding="utf-8").count("+++ b/") == 1)
    i = hud.index('        if path in ("/api/focus", "/api/focus/diag", "/api/focus/callout"):')
    get_blk = hud[i:hud.index('        if path == "/api/schedule":', i)]
    j = hud.index('        if route in ("/api/focus/start", "/api/focus/act"):')
    post_blk = hud[j:hud.index('        if route == "/api/second-card":', j)]
    for name, blk in (("GET", get_blk), ("POST", post_blk)):
        check(f"{name} checks the origin and the token first",
              blk.index("_origin_ok(self)") < blk.index("import jarvis_focus")
              and "_token_ok(self)" in blk)
    ns = {"json": json}
    exec(compile("def g(self, path, _origin_ok, _token_ok):\n" + get_blk, "<GET>", "exec"), ns)
    exec(compile("def p(self, route, _origin_ok, _token_ok, _read_body):\n" + post_blk,
                 "<POST>", "exec"), ns)
    w = World()
    saved = F.ENGINE
    F.ENGINE = w.e
    yes = lambda s: True  # noqa: E731
    try:
        h = _Handler()
        ns["g"](h, "/api/focus", yes, yes)
        check("GET /api/focus answers the status", h.sent[0] == 200 and h.sent[1]["on"] is False)
        ns["g"](h, "/api/focus", yes, lambda s: False)
        check("... 401 without the token", h.sent[0] == 401)
        ns["g"](h, "/api/focus", lambda s: False, yes)
        check("... 403 from another origin", h.sent[0] == 403)
        h = _Handler("/api/focus/start", "100.64.0.7")
        ns["p"](h, "/api/focus/start", yes, yes, lambda s: b'{"minutes": 15, "on": "notes"}')
        check("POST /api/focus/start from the phone starts one (no card)",
              h.sent[0] == 200 and w.e.on and w.e.planned_s == 900, h.sent)
        check("... and records it came from another device",
              ("focus.start", {"minutes": 15, "by": "another device", "quiet": "failed",
                               "on_scheduler": True}) in w.audits, w.audits)
        ns["p"](h, "/api/focus/act", yes, yes, lambda s: b'{"do": "pause"}')
        check("POST /api/focus/act pauses it", h.sent[0] == 200 and w.e.paused)
        ns["p"](h, "/api/focus/act", yes, yes, lambda s: b'{"do": "approve_all"}')
        check("... an unknown action is 400", h.sent[0] == 400)
        ns["p"](h, "/api/focus/act", yes, yes, lambda s: b"not json")
        check("... a body that is not JSON is 400", h.sent[0] == 400)
        h = _Handler("/api/focus/diag")
        ns["g"](h, "/api/focus/diag", yes, yes)
        check("GET /api/focus/diag answers booleans and counts",
              h.sent[0] == 200 and "front_is_browser" in h.sent[1])
        h = _Handler("/api/focus/callout?seq=1", "100.64.0.7")
        ns["g"](h, "/api/focus/callout", yes, yes)
        check("GET /api/focus/callout from another address is 403", h.sent[0] == 403)
        h = _Handler("/api/focus/callout?seq=99", "127.0.0.1")
        ns["g"](h, "/api/focus/callout", yes, yes)
        check("... from this PC with nothing waiting, 404", h.sent[0] == 404)
        mod = sys.modules.get("jarvis_focus")
        sys.modules["jarvis_focus"] = None
        try:
            ns["g"](h, "/api/focus", yes, yes)
        finally:
            sys.modules["jarvis_focus"] = mod
        check("... 503 available:false without jarvis_focus.py", h.sent[0] == 503
              and h.sent[1]["available"] is False)
    finally:
        F.ENGINE = saved
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies focus.patch after reach.patch and power-mode.patch",
          names.index("reach.patch") < names.index("focus.patch")
          and names.index("power-mode.patch") < names.index("focus.patch"))
    check("jarvis_focus.py is shipped (apply-patches.ps1 $SHIPPED and _where.SHIPPED)",
          "'jarvis_focus.py'" in ps1 and "jarvis_focus.py" in SHIPPED)
    check("the scheduler loads it before its loop first runs (KIND_MODULES)",
          "jarvis_focus" in S.KIND_MODULES)


def t_wired_at_merge():
    """Joined at the merge (2026-09-25): Stop everything pauses a running
    session, and the lines follow the owner's warm / plain setting."""
    import jarvis_stop_all as SA
    check("Stop everything knows the focus stopper", "focus" in SA.registered())
    w = World(name="stopall")
    saved = F.ENGINE
    F.ENGINE = w.e
    try:
        w.e.start(10, "", by="a test")
        said = F._stop_for_stop_all()
        check("Stop everything pauses a running session, and says so",
              w.e.on and w.e.paused and said == "The focus session was paused.", said)
        check("... and says nothing when none is running", F._stop_for_stop_all() is None)
    finally:
        F.ENGINE = saved
    import jarvis_manner
    real = jarvis_manner.current
    try:
        jarvis_manner.current = lambda: "plain"
        check("the lines follow the owner's manner setting: plain", F.manner() == "plain")
        jarvis_manner.current = lambda: "warm"
        check("... and warm", F.manner() == "warm")
    finally:
        jarvis_manner.current = real


def main():
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
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
