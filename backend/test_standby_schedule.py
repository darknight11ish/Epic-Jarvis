"""test_standby_schedule.py - the standby schedule ("on standby from 01:00 to
07:00, every day"): a kind of job on the one scheduler, not a second standby.

    python3 backend/test_standby_schedule.py

Task #55, the owner's "sleep feature", built on what was already there
(jarvis_standby_schedule.py's header says why it is called that). What this
proves, with a clock the test moves by hand, real SQLite files in a
temporary folder, the rebuilt jarvis_power.py and the REAL
jarvis_power_switch.py (only the gate, Ollama and jarvis_models are fakes):

  - the rule: every day from one time to another, both ends go off, across
    midnight and across both daylight-saving changes; anything else is
    refused with a sentence; only a window kind may have an end time;
  - setting it up is ONE schedule_repeat card, tier "ask" only, listing the
    next three windows and what each end does; denied or refused sets up
    nothing; there is only ever one;
  - at the start, Jarvis goes on standby through jarvis_power_switch.set_mode
    (power_manage, the same call as the Standby button), which unloads every
    model the everyday Ollama holds; at the end it wakes and loads the chat
    model again; an end that finds it already there does nothing;
  - the end wakes Jarvis ONLY if the schedule put it on standby (the owner's
    decision of 2026-09-25): Standby chosen by hand - before the start or
    during the window - stays; woken by hand, the end does nothing and does
    not put it back; a backend restart inside the window comes back awake;
    a power module that cannot say who chose Standby is left alone;
  - a start refused because a task runs is skipped, and said;
  - the PC off all night (both ends overdue): awake, whichever runs first;
    the PC coming on inside the window: standby, once, late;
  - timers still go off while Jarvis is on standby; the standby job's own
    event says "notify": false (no toast, no notification at 01:00) and
    carries no words;
  - the routes: POST /api/schedule/add with kind "standby" is 202 and a card;
    delete is immediate; the list says which end is next;
  - it is shipped (apply-patches.ps1 $SHIPPED, _where.SHIPPED) and loaded
    before the scheduler's loop first starts.

No pytest, no network, no model.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, missing, require_shipped  # noqa: E402

require_shipped("jarvis_schedule.py", "jarvis_standby_schedule.py", "jarvis_power_switch.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-standby-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw
if missing("jarvis_power.py"):
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_schedule as S  # noqa: E402
import jarvis_standby_schedule as SB  # noqa: E402
import jarvis_power as P  # noqa: E402
import jarvis_power_switch as PS  # noqa: E402

PASSED, FAILED = [], []
_AUDIT = []
S._audit = lambda event, detail: _AUDIT.append((event, detail))


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


def wall(t):
    lt = time.localtime(t)
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min)


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


class World:
    """A scheduler with a hand-moved clock and a gate that records."""

    def __init__(self, t, *, answer="approved", tier="ask", name="w"):
        self.clock = Clock(t)
        self.events, self.cards = [], []
        self.answer, self.tier = answer, tier
        path = _TMP / f"{name}-{len(os.listdir(_TMP))}.db"
        self.fired = []
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate,
                             tier_of=lambda a: self.tier, spawn=self.spawn,
                             publish=lambda k, d: self.events.append((k, d)))

    def spawn(self, fn):
        fn()

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)


RULE = {"every": "day", "at": "01:00", "until": "07:00"}


# --------------------------------------------------------------------------
#   The rule
# --------------------------------------------------------------------------

def t_the_rule():
    use_tz("Europe/London")
    r = S.check_rule({"every": "day", "at": "1:00", "until": "07:00"}, window=True)
    check("a window is every day from one time to another, tidied",
          r == {"every": "day", "at": "01:00", "until": "07:00"}, r)
    for bad, why in (({"every": "weekday", "at": "01:00", "until": "07:00"}, "every day"),
                     ({"every": "day", "at": "07:00", "until": "07:00"}, "same time"),
                     ({"every": "day", "at": "01:00"}, "HH:MM"),
                     ({"every": "day", "at": "25:00", "until": "07:00"}, "not a time")):
        try:
            S.check_rule(bad, window=True)
            check(f"refused: {bad}", False)
        except ValueError as exc:
            check(f"refused with a sentence: {bad}", why in str(exc), str(exc))
    try:
        S.check_rule({"every": "day", "at": "07:00", "until": "08:00"})
        check("a reminder with an end time is refused", False)
    except ValueError as exc:
        check("a reminder with an end time is refused, not silently shortened",
              "only a standby schedule" in str(exc), str(exc))
    fri = local(2026, 9, 25, 12, 0)
    a = S.next_run(RULE, fri)
    b = S.next_run(RULE, a)
    c = S.next_run(RULE, b)
    check("it goes off at both ends: 01:00, then 07:00, then 01:00",
          [wall(x)[3] for x in (a, b, c)] == [1, 7, 1] and wall(a)[:3] == (2026, 9, 26), (a, b, c))
    check("inside at 03:00, outside at 12:00, at the start inside, at the end outside",
          S.in_window(RULE, local(2026, 9, 26, 3, 0))
          and not S.in_window(RULE, local(2026, 9, 26, 12, 0))
          and S.in_window(RULE, local(2026, 9, 26, 1, 0))
          and not S.in_window(RULE, local(2026, 9, 26, 7, 0)))
    night = {"every": "day", "at": "23:00", "until": "07:00"}
    check("across midnight: inside at 23:30 and 06:59, outside at 07:00 and 22:59",
          S.in_window(night, local(2026, 9, 25, 23, 30))
          and S.in_window(night, local(2026, 9, 26, 6, 59))
          and not S.in_window(night, local(2026, 9, 26, 7, 0))
          and not S.in_window(night, local(2026, 9, 26, 22, 59)))
    check("a rule that is not a window is never 'inside'",
          not S.in_window({"every": "day", "at": "07:00"}, fri))
    check("in words", S.rule_words(RULE) == "every day from 01:00 to 07:00")
    # The clocks go back in the UK at 02:00 on Sunday 25 October 2026 (01:00
    # happens twice) and forward at 01:00 on Sunday 28 March 2027 (01:00
    # to 02:00 never happens).
    back = S.next_run(RULE, local(2026, 10, 24, 12, 0))
    check("the night the clocks go back: 01:00 goes off once, the first time",
          wall(back) == (2026, 10, 25, 1, 0) and S.next_run(RULE, back) ==
          local(2026, 10, 25, 7, 0), (wall(back), wall(S.next_run(RULE, back))))
    fwd = S.next_run(RULE, local(2027, 3, 27, 12, 0))
    check("the night the clocks go forward: 01:00 does not exist, it starts at the jump",
          wall(fwd) == (2027, 3, 28, 2, 0) and wall(S.next_run(RULE, fwd)) == (2027, 3, 28, 7, 0),
          wall(fwd))
    check("... and 03:00 that night is inside the window",
          S.in_window(RULE, local(2027, 3, 28, 3, 0)))


# --------------------------------------------------------------------------
#   Setting it up: one card
# --------------------------------------------------------------------------

def t_one_card_to_set_it_up():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)                 # Friday noon
    w = World(now, name="card")
    j = w.s.add_repeat("standby", RULE)
    check("setting it up raises ONE card, schedule_repeat",
          len(w.cards) == 1 and w.cards[0][0] == "schedule_repeat", w.cards)
    prompt = w.cards[0][2]
    check("the card lists the next three windows in full",
          all(x in prompt for x in ("Saturday 26 September, 01:00 to 07:00",
                                    "Sunday 27 September, 01:00 to 07:00",
                                    "Monday 28 September, 01:00 to 07:00")), prompt)
    check("... says what, when, what each end does, what no means, and that nothing leaves",
          prompt.startswith("Set up a standby schedule.")
          and "When: every day from 01:00 to 07:00." in prompt
          and "unloads its models and frees the graphics card(s)" in prompt
          and "loads the chat model again" in prompt
          and "Timers, alarms and reminders still go off" in prompt
          and "Nothing is sent anywhere." in prompt
          and "If you say no: nothing is set up." in prompt, prompt)
    check("... and does not claim it rings on the apps (it notifies nobody)",
          "goes off on both apps" not in prompt)
    check("the detail says it does not leave this PC",
          w.cards[0][1].get("leaves_this_pc") is False)
    v = w.s.job(j["id"])
    check("approved: set up, next end 01:00 tomorrow, said as 'on standby at'",
          v["state"] == "active" and wall(v["due"]) == (2026, 9, 26, 1, 0)
          and v["when"] == "on standby at 01:00 tomorrow"
          and v["repeat"] == "every day from 01:00 to 07:00", v)
    check("its lock-screen words are the kind's, and it says notify false",
          v["lock_screen"] == "Jarvis: standby schedule." and v["notify"] is False, v)
    try:
        w.s.add_repeat("standby", {"every": "day", "at": "02:00", "until": "06:00"})
        check("only one standby schedule", False)
    except OverflowError as exc:
        check("only one standby schedule: a second is refused, with how to change it",
              "already a standby schedule - delete it first" in str(exc), str(exc))
    check("... and raised no second card", len(w.cards) == 1)

    for answer in ("denied", "timed_out"):
        w2 = World(now, answer=answer, name=answer)
        j2 = w2.s.add_repeat("standby", RULE)
        check(f"{answer}: nothing set up", w2.s.job(j2["id"]) is None and w2.s.listed() == [])
    w3 = World(now, tier="auto", name="auto")
    j3 = w3.s.add_repeat("standby", RULE)
    check("tier \"auto\" is refused without asking - a config line is not a yes",
          w3.cards == [] and w3.s.job(j3["id"]) is None)
    w4 = World(now, name="waiting")
    w4.spawn = lambda fn: None
    w4.s._spawn = w4.spawn
    j4 = w4.s.add_repeat("standby", RULE)
    check("while the card waits: listed as waiting, and nothing goes off",
          w4.s.job(j4["id"])["state"] == "waiting" and w4.s.tick(now + 3 * 86400) == [])
    check("... and a second one is refused even then",
          _raises(lambda: w4.s.add_repeat("standby", RULE), OverflowError))


def _raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


# --------------------------------------------------------------------------
#   The two ends, through the REAL power switch
# --------------------------------------------------------------------------

class FakeOllama:
    def __init__(self, loaded=()):
        self.loaded = list(loaded)
        self.url = "http://127.0.0.1:11434"
        self.unloads, self.loads = [], []

    def ps(self):
        return list(self.loaded)

    def unload(self, name):
        self.unloads.append(name)
        self.loaded = [n for n in self.loaded if n != name]

    def load(self, name):
        self.loads.append(name)
        self.loaded.append(name)


class Gate:
    """jarvis_gate at the shipped tier for power_manage: auto."""

    def __init__(self):
        self.asked = []

    def check(self, action, detail, prompt=""):
        self.asked.append((action, prompt))
        return types.SimpleNamespace(allowed=True, outcome="auto", tier="auto", reason="auto")


def _world_with_power(now, name):
    w = World(now, name=name)
    S._SCHED = w.s
    gate = Gate()
    sys.modules["jarvis_gate"] = types.SimpleNamespace(check=gate.check)
    models = types.SimpleNamespace(current_model=lambda: "jarvis-primary",
                                   resident_models=lambda: [], unload=lambda n: None)
    sys.modules["jarvis_models"] = models
    ollama = FakeOllama(["jarvis-primary:latest", "qwen2.5vl:7b"])
    PS.everyday_ollama = lambda: ollama
    PS._spawn_warm = lambda fn: fn()
    PS._free_other_engines = lambda others=None: []
    P.set_mode("active", "test")
    SB._LAST.clear()
    return w, gate, ollama


def _done():
    S._SCHED = None
    for m in ("jarvis_gate", "jarvis_models"):
        sys.modules.pop(m, None)
    P.set_mode("active", "test")


def _settled():
    for _ in range(300):
        if not PS._PENDING:
            return
        time.sleep(0.02)


def t_the_two_ends():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w, gate, ollama = _world_with_power(now, "ends")
    SB.CLOCK = w.clock
    try:
        j = w.s.add_repeat("standby", RULE)
        w.s.add_timer(3 * 3600)                    # a timer due at 15:00
        w.clock.t = local(2026, 9, 26, 1, 0)
        went = w.s.tick()
        _settled()
        ev = [d for k, d in w.events if d.get("state") == "fired" and d["id"] == j["id"]]
        check("01:00: the standby job went off (and so did the 15:00 timer, late)",
              j["id"] in went, went)
        check("its event says notify false and carries no words",
              ev and ev[-1].get("notify") is False and set(ev[-1]) ==
              {"id", "kind", "state", "late", "notify"}, ev)
        timer_ev = [d for k, d in w.events if d.get("kind") == "timer" and d["state"] == "fired"]
        check("a timer's event still notifies (no notify key)",
              timer_ev and "notify" not in timer_ev[-1], timer_ev)
        check("Jarvis is on standby, through power_manage like the Standby button",
              P.current() == "standby" and gate.asked and gate.asked[-1][0] == "power_manage"
              and "asked from the standby schedule" in gate.asked[-1][1], gate.asked)
        check("... recorded as the standby schedule, not 'the owner' (the tray's 'set by hand')",
              P.status()["why"] == "the standby schedule", P.status())
        check("... and every model the everyday Ollama held was unloaded",
              ollama.loaded == [] and set(ollama.unloads) == {"jarvis-primary:latest",
                                                              "qwen2.5vl:7b"}, ollama.unloads)
        v = w.s.job(j["id"])
        check("the list: next end 07:00, said as 'awake at ... if the schedule put it on "
              "standby', and how it went",
              v["when"] == "awake at 07:00 today, if the schedule put it on standby"
              and v["note"] == "Went on standby at 01:00.", v)

        # A timer set and going off while on standby: the scheduler does not
        # look at the power mode.
        t2 = w.s.add_timer(60)
        w.clock.t += 61
        check("a timer set while on standby goes off while on standby",
              t2["id"] in w.s.tick() and P.current() == "standby")

        w.clock.t = local(2026, 9, 26, 7, 0)
        w.s.tick()
        _settled()
        check("07:00: awake again (Active)", P.current() == "active", P.current())
        check("... and the chat model loaded again at once (the warm-up)",
              ollama.loads == ["jarvis-primary"], ollama.loads)
        v = w.s.job(j["id"])
        check("the list: 'Woke at 07:00 and loaded the chat model (jarvis-primary) again.', "
              "next 'on standby at 01:00 tomorrow'",
              v["note"] == "Woke at 07:00 and loaded the chat model (jarvis-primary) again."
              and v["when"] == "on standby at 01:00 tomorrow", v)

        # Woken by hand at 03:00: 07:00 finds it awake and does nothing.
        w.clock.t = local(2026, 9, 27, 1, 0)
        w.s.tick()
        _settled()
        PS.set_mode("active", gate_check=lambda *a: Verdict(True, "auto", "auto"),
                    warm=lambda fn: None)
        _settled()
        n_before = len(gate.asked)
        w.clock.t = local(2026, 9, 27, 7, 0)
        w.s.tick()
        _settled()
        check("woken by hand before the end: the end changes nothing, and says so",
              len(gate.asked) == n_before and w.s.job(j["id"])["note"] == "Already awake at 07:00.",
              w.s.job(j["id"]))

        # Put on standby by hand before the start: the start changes nothing.
        w.clock.t = local(2026, 9, 27, 23, 0)
        PS.set_mode("standby", gate_check=lambda *a: Verdict(True, "auto", "auto"))
        _settled()
        n_before = len(gate.asked)
        w.clock.t = local(2026, 9, 28, 1, 0)
        w.s.tick()
        _settled()
        check("already on standby by hand at the start: nothing asked, and it says the end "
              "will leave it", len(gate.asked) == n_before
              and w.s.job(j["id"])["note"] == ("Already on standby at 01:00 - you chose it, so "
                                               "the end of the schedule will leave it on."),
              w.s.job(j["id"])["note"])
        check("... and the start did not take it over: it is still the owner's standby",
              P.status()["why"] == "the owner, from an app", P.status())
        w.clock.t = local(2026, 9, 28, 7, 0)
        w.s.tick()
        _settled()
        check("... so at the end it STAYS on standby - the owner chose it (2026-09-25)",
              P.current() == "standby" and len(gate.asked) == n_before
              and w.s.job(j["id"])["note"] == ("Left on standby at 07:00: you chose Standby "
                                               "yourself, so it stays on until you choose "
                                               "Active."), w.s.job(j["id"])["note"])
    finally:
        SB.CLOCK = time.time
        _done()


def _manual(mode):
    """A tap in either app: the same call, recorded as the owner's."""
    out = PS.set_mode(mode, gate_check=lambda *a: Verdict(True, "auto", "auto"),
                      warm=lambda fn: None)
    _settled()
    return out


def t_only_the_schedules_own_standby_is_woken():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w, gate, ollama = _world_with_power(now, "owner")
    SB.CLOCK = w.clock
    try:
        j = w.s.add_repeat("standby", RULE)

        def at(d, hh):
            w.clock.t = local(2026, 9, d, hh, 0)
            w.s.tick()
            _settled()
            return w.s.job(j["id"])["note"]

        # Night 1: the schedule's own standby, woken by hand at 03:00.
        at(26, 1)
        check("night 1: the schedule put it on standby", P.current() == "standby"
              and P.status()["why"] == SB.WHY)
        _manual("active")
        n = len(gate.asked)
        note = at(26, 7)
        check("woken by hand at 03:00: 07:00 does nothing, and does not put it back on standby",
              P.current() == "active" and len(gate.asked) == n
              and note == "Already awake at 07:00.", note)

        # Night 2: woken by hand at 03:00, then Standby by hand at 04:00.
        at(27, 1)
        _manual("active")
        _manual("standby")
        check("Standby by hand during the window is the owner's",
              P.status()["why"] == "the owner, from an app")
        note = at(27, 7)
        check("... so 07:00 leaves it on standby, and says why",
              P.current() == "standby" and note.startswith("Left on standby at 07:00: you chose "
                                                            "Standby yourself"), note)
        _manual("active")

        # Night 3: the schedule's standby, and a tap on Standby again changes
        # nothing - it is still the schedule's, so 07:00 wakes it.
        at(28, 1)
        code, out = _manual("standby")
        check("a tap on Standby while already on standby records nothing",
              code == 200 and out["changed"] is False and P.status()["why"] == SB.WHY, out)
        at(28, 7)
        check("... so 07:00 wakes it", P.current() == "active")

        # Night 4: the backend restarts at 03:00. The mode lives in memory, so
        # it comes back Active ("startup"); the start already went off.
        at(29, 1)
        with P._LOCK:
            P._state.update({"mode": "active", "since": time.time(), "why": "startup"})
        n = len(gate.asked)
        w.clock.t = local(2026, 9, 29, 3, 0)
        check("a restart inside the window: nothing goes off before 07:00",
              w.s.tick() == [] and P.current() == "active")
        note = at(29, 7)
        check("... and 07:00 finds it awake and does nothing", P.current() == "active"
              and len(gate.asked) == n and note == "Already awake at 07:00.", note)

        # A power module that cannot say who chose Standby: left alone.
        at(30, 1)
        real_status = P.status
        P.status = lambda: (_ for _ in ()).throw(RuntimeError("no status"))
        try:
            note = at(30, 7)
        finally:
            P.status = real_status
        check("who chose Standby cannot be read: left on standby, and said",
              P.current() == "standby" and note.startswith("Left on standby at 07:00: Jarvis "
                                                            "could not tell who chose Standby"),
              note)
        check("set_by_schedule: True, False, or None when it cannot say",
              SB.set_by_schedule(types.SimpleNamespace(status=lambda: {"why": SB.WHY})) is True
              and SB.set_by_schedule(types.SimpleNamespace(
                  status=lambda: {"why": "the owner, from tray"})) is False
              and SB.set_by_schedule(types.SimpleNamespace()) is None)
        # Standby set some other way (the idle timer, "exit"): not the
        # owner's words, and not the schedule's - left on, said plainly.
        _manual("active")
        w.clock.t = local(2026, 10, 1, 1, 0)
        w.s.tick()
        _settled()
        with P._LOCK:
            P._state["why"] = "idle timer"
        w.clock.t = local(2026, 10, 1, 7, 0)
        w.s.tick()
        _settled()
        note = w.s.job(j["id"])["note"]
        check("standby set by something else (an idle timer): left on, and not called yours",
              P.current() == "standby" and note == ("Left on standby at 07:00: the schedule did "
                                                    "not put it on standby, so it stays on until "
                                                    "you choose Active."), note)
    finally:
        SB.CLOCK = time.time
        _done()


def t_a_skipped_start_then_standby_by_hand_stays():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w, gate, ollama = _world_with_power(now, "skip-owner")
    SB.CLOCK = w.clock
    real_tasks = PS._running_tasks
    try:
        j = w.s.add_repeat("standby", RULE)
        PS._running_tasks = lambda: ["appr_busy"]
        w.clock.t = local(2026, 9, 26, 1, 0)
        w.s.tick()
        _settled()
        check("01:00 skipped because a task ran: still awake", P.current() == "active")
        PS._running_tasks = real_tasks
        _manual("standby")
        w.clock.t = local(2026, 9, 26, 7, 0)
        w.s.tick()
        _settled()
        check("the owner then chose Standby: 07:00 leaves it",
              P.current() == "standby"
              and w.s.job(j["id"])["note"].startswith("Left on standby at 07:00"))
    finally:
        PS._running_tasks = real_tasks
        SB.CLOCK = time.time
        _done()


def t_a_running_task_skips_that_night():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w, gate, ollama = _world_with_power(now, "task")
    SB.CLOCK = w.clock
    real_tasks = PS._running_tasks
    PS._running_tasks = lambda: ["appr_busy"]
    try:
        j = w.s.add_repeat("standby", RULE)
        w.clock.t = local(2026, 9, 26, 1, 0)
        w.s.tick()
        _settled()
        v = w.s.job(j["id"])
        check("a task running at 01:00: no standby, nothing unloaded, and the list says why",
              P.current() == "active" and ollama.unloads == []
              and v["note"] == ("Skipped standby at 01:00: a task was running, and standby "
                                "would unload the model it uses."), v)
    finally:
        PS._running_tasks = real_tasks
        SB.CLOCK = time.time
        _done()


def t_missed_while_the_pc_was_off():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w, gate, ollama = _world_with_power(now, "missed")
    SB.CLOCK = w.clock
    try:
        j = w.s.add_repeat("standby", RULE)
        # Off from Friday noon to Saturday 08:00: 01:00 and 07:00 both went by.
        w.clock.t = local(2026, 9, 26, 8, 0)
        went = w.s.tick()
        _settled()
        v = w.s.job(j["id"])
        check("the PC off all night: it goes off ONCE, late, and Jarvis is awake",
              went == [j["id"]] and P.current() == "active" and gate.asked == []
              and v.get("missed") == "missed at 01:00", (went, v))
        check("... and the next end is tonight's 01:00, not a burst",
              wall(v["due"]) == (2026, 9, 27, 1, 0), wall(v["due"]))
        # On again at 03:00 inside the next window: standby then, once.
        w.clock.t = local(2026, 9, 27, 3, 0)
        went = w.s.tick()
        _settled()
        check("the PC coming on at 03:00, inside the window: standby, once, late",
              went == [j["id"]] and P.current() == "standby"
              and w.s.job(j["id"])["note"] == "Went on standby at 03:00.",
              (went, w.s.job(j["id"])))
        check("... and the next end is 07:00", wall(w.s.job(j["id"])["due"]) == (2026, 9, 27, 7, 0))
    finally:
        SB.CLOCK = time.time
        _done()


def t_turning_it_off():
    use_tz("Europe/London")
    now = local(2026, 9, 25, 12, 0)
    w, gate, ollama = _world_with_power(now, "off")
    SB.CLOCK = w.clock
    try:
        j = w.s.add_repeat("standby", RULE)
        n = len(w.cards)
        code, out = w.s.act(j["id"], "pause")
        check("Pause: immediate, no card", code == 200 and len(w.cards) == n)
        w.clock.t = local(2026, 9, 26, 1, 0)
        check("paused: 01:00 does nothing", w.s.tick() == [] and P.current() == "active")
        w.s.act(j["id"], "resume")
        w.clock.t = local(2026, 9, 27, 1, 0)
        w.s.tick()
        _settled()
        check("resumed: the next 01:00 goes on standby", P.current() == "standby")
        code, out = w.s.act(j["id"], "delete")
        check("Delete: immediate, no card, gone from the list",
              code == 200 and len(w.cards) == n and w.s.listed() == [])
        check("... and it does NOT wake Jarvis (that is what Active is for)",
              P.current() == "standby")
        w.clock.t = local(2026, 9, 27, 7, 0)
        check("... and 07:00 does nothing any more", w.s.tick() == [] and P.current() == "standby")
        j2 = w.s.add_repeat("standby", {"every": "day", "at": "02:00", "until": "06:00"})
        check("after deleting it, a new one may be set up (a new card)",
              w.s.job(j2["id"])["state"] == "active" and len(w.cards) == n + 1)
    finally:
        SB.CLOCK = time.time
        _done()


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

def t_the_routes():
    use_tz("Europe/London")
    w = World(time.time(), name="routes")
    w.spawn = lambda fn: None                    # the card stays up
    w.s._spawn = w.spawn
    S._SCHED = w.s
    try:
        code, out = S.handle_add({"kind": "standby", "repeat": RULE})
        check("POST /api/schedule/add kind standby: 202, waiting for its card",
              code == 202 and out["waiting"] is True and out["job"]["kind"] == "standby"
              and out["job"]["state"] == "waiting", (code, out))
        code, out2 = S.handle_add({"kind": "standby", "repeat": RULE})
        check("a second one: 409, with the reason", code == 409
              and "already a standby schedule" in out2["error"], out2)
        check("no repeat: 400", S.handle_add({"kind": "standby"})[0] == 400)
        code, lst = S.handle_get("")
        row = [j for j in lst["jobs"] if j["kind"] == "standby"]
        check("GET /api/schedule lists it, with its repeat words",
              row and row[0]["repeat"] == "every day from 01:00 to 07:00", lst)
        code, out3 = S.handle_act({"id": out["job"]["id"], "do": "delete"})
        check("delete it by id: immediate", code == 200 and S.handle_get("")[1]["jobs"] == [])
        check("an unknown kind's error names standby too",
              "standby" in S.handle_add({"kind": "everything"})[1]["error"])
    finally:
        S._SCHED = None


# --------------------------------------------------------------------------
#   Shipped, and loaded before the loop starts
# --------------------------------------------------------------------------

def t_shipped_and_loaded():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    import _where
    check("apply-patches.ps1 and _where.SHIPPED copy it in",
          "'jarvis_standby_schedule.py'" in shipped
          and "jarvis_standby_schedule.py" in _where.SHIPPED)
    check("the scheduler imports it before its loop first starts",
          "jarvis_standby_schedule" in S.KIND_MODULES
          and "_load_kind_modules()" in (HERE / "jarvis_schedule.py").read_text(encoding="utf-8"))
    k = S.KINDS.get("standby")
    check("registered as a window kind that notifies nobody and is one of its kind",
          k is not None and k.window and k.single and not k.notify and k.on_fire is SB.on_fire)
    about = "\n".join(SB.ABOUT)
    check("the card says the end wakes it only if the schedule put it on standby",
          "At the end, if the schedule put it on standby, it wakes (Active)" in about
          and "If you chose Standby yourself, it stays on standby until you choose Active."
          in about, about)
    src = (HERE / "jarvis_standby_schedule.py").read_text(encoding="utf-8")
    check("it unloads nothing itself and runs no timer of its own: every change goes "
          "through jarvis_power_switch.set_mode",
          "switch.set_mode(" in src and ".unload(" not in src and "threading.Thread" not in src
          and "time.sleep" not in src)


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
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
