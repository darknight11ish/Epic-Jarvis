"""test_goals.py - "Goals with one card per step" (the owner's "build it
now", 2026-09-27; docs/creativity-2026-09-25/future.md idea 3).

    python3 backend/test_goals.py

What it proves, with a stubbed scheduler (a real jarvis_schedule.Scheduler,
a hand-moved clock, no real thread, no real gate) and real SQLite files in a
temporary folder:
  - a new goal is a DRAFT, its plan defaulting to the goal's own words as
    one step, with no card raised and no scheduler job created;
  - accepting a goal keeps the owner's own edited plan, sets up exactly ONE
    weekly check-in job on the one scheduler, through the SAME
    schedule_repeat card mechanism a repeating reminder or the morning
    briefing already uses - approving it changes nothing that acts;
  - a SECOND goal's check-in, sharing the same default weekly rule, is not
    refused as a duplicate (goal_checkin's has_text=True is the reason);
  - marking a step done, and stopping a goal, need no card and are
    immediate; stopping deletes the scheduler job too;
  - the weekly check-in's own note is deterministic - built only from the
    goal's own already-stored plan - and correct once a step is done;
  - a plan over the step limit, or with no steps, is refused with a plain
    sentence, never a stack trace;
  - the HTTP routes (install/handle_get/handle_post) answer exactly the
    shapes above, and 404 for both an unknown goal and an unrelated route
    (so the original handler still gets a chance).

Every check fails on the code before this feature: jarvis_goals.py and
goals.patch did not exist.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_goals.py", "jarvis_schedule.py")

import jarvis_goals as G  # noqa: E402
import jarvis_schedule as S  # noqa: E402

PASSED, FAILED = [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-goals-"))


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


class World:
    """A real Scheduler (its own SQLite file) plus a real Goals store (its
    own), wired together exactly as register() would - but without touching
    the module-level singletons, so tests never share state."""

    def __init__(self, t=1_000_000.0, *, answer="approved", tier="ask"):
        self.clock = Clock(t)
        self.cards, self.events = [], []
        self.answer, self.tier = answer, tier
        n = len(os.listdir(_TMP))
        self.sched = S.Scheduler(_TMP / f"sched-{n}.db", clock=self.clock, gate=self.gate,
                                 tier_of=lambda a: self.tier, spawn=lambda fn: fn(),
                                 publish=lambda k, d: self.events.append((k, d)))
        self.benches = {}
        self.g = G.Goals(_TMP / f"goals-{n}.db", clock=self.clock, scheduler=self.sched,
                         bench_reader=self.read_bench)
        S.register_kind(
            G.KIND, "goal check-in", "Jarvis: a goal check-in is due.",
            on_fire=lambda jid: self.g.on_checkin(self.g.goal_id_for_job(jid)),
            note=lambda jid: self.g.checkin_note(self.g.goal_id_for_job(jid)),
            **G.KIND_OPTIONS,
        )

    def read_bench(self, project, bench):
        """A stand-in for jarvis_projects: a benchmark as its read answers it."""
        return self.benches[(project, bench)]     # KeyError = gone

    def gate(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

def t_a_new_goal_is_a_draft_with_a_default_plan_and_raises_nothing():
    w = World()
    goal = w.g.create("insulate the garage before winter")
    check("a new goal is a draft", goal["status"] == "draft")
    step = goal["plan"][0]
    check("its plan defaults to its own words, one step",
          len(goal["plan"]) == 1 and step["step"] == "insulate the garage before winter"
          and step["by"] == "" and step["done"] is False)
    check("...with an id, no done date, no locks, no measure",
          step["id"] == "s1" and step["done_at"] is None and step["needs"] == []
          and step["measure"] is None and step["state"] == "open"
          and step["waiting_on"] == [] and step["lock_words"] == "")
    check("no card was raised by creating a draft", w.cards == [])
    check("no scheduler job exists yet", w.sched.listed() == [])


def t_a_given_plan_is_kept_as_given():
    w = World()
    goal = w.g.create("learn to bake bread", plan=[{"step": "buy flour", "by": "this week"},
                                                    {"step": "try a recipe", "by": ""}])
    check("a given plan is kept, not replaced", len(goal["plan"]) == 2)
    check("each step keeps its own words", goal["plan"][0]["step"] == "buy flour")


def t_accepting_raises_no_card_and_approves_nothing_that_acts():
    """The owner's decision of 2026-09-28: the weekly check-in needs no card,
    like a plain repeating reminder (2026-09-26) - only the owner's own tap
    sets it up, and Stop tracking removes it at once."""
    w = World(answer="denied")      # a card, if one were raised, would be refused
    goal = w.g.create("insulate the garage before winter")
    accepted = w.g.accept(goal["id"], plan=[{"step": "contact 3 installers", "by": "this week"}])
    check("accepting sets the goal active", accepted["status"] == "active")
    check("no card was raised", w.cards == [], w.cards)
    check("the check-in the answer carries is already active, not waiting",
          accepted["checkin"]["state"] == "active", accepted["checkin"])
    job = w.sched.job(accepted["checkin"]["id"])
    check("the job is on the list at once", job is not None and job["state"] == "active")
    check("the job repeats weekly", job["repeat"] == "every Monday at 09:00", job.get("repeat"))
    check("the kind is registered as a plain repeat (no card)",
          G.KIND_OPTIONS["plain_repeat"] is True and S.KINDS[G.KIND].plain_repeat is True)
    w.g.stop(goal["id"])
    check("Stop tracking removes the check-in at once",
          w.sched.job(accepted["checkin"]["id"]) is None
          or w.sched.job(accepted["checkin"]["id"])["state"] not in ("active", "waiting"))


def t_a_second_goal_with_the_same_default_rule_is_not_refused_as_a_duplicate():
    w = World()
    g1 = w.g.create("insulate the garage before winter")
    g2 = w.g.create("learn to bake bread")
    w.g.accept(g1["id"])
    try:
        w.g.accept(g2["id"])
        ok = True
    except Exception as exc:
        ok, err = False, exc
    check("a second goal's weekly check-in is not treated as a duplicate repeat",
          ok, "" if ok else repr(err))
    check("both check-in jobs exist", len(w.sched.listed()) == 2)


def t_accepting_a_goal_that_is_not_a_draft_is_refused():
    w = World()
    goal = w.g.create("insulate the garage before winter")
    w.g.accept(goal["id"])
    try:
        w.g.accept(goal["id"])
        ok = False
    except ValueError:
        ok = True
    check("accepting an already-active goal is refused", ok)


def t_marking_a_step_and_stopping_need_no_card_and_are_immediate():
    w = World()
    goal = w.g.create("insulate the garage before winter",
                      plan=[{"step": "contact installers", "by": ""},
                            {"step": "pick one", "by": ""}])
    accepted = w.g.accept(goal["id"])
    job_id = accepted["checkin"]["id"]
    before_cards = len(w.cards)
    w.g.mark_step(goal["id"], 0, True)
    check("marking a step raises no card", len(w.cards) == before_cards)
    stopped = w.g.stop(goal["id"])
    check("stopping raises no card", len(w.cards) == before_cards)
    check("stopping marks the goal stopped", stopped["status"] == "stopped")
    check("stopping deletes the check-in job", w.sched.job(job_id) is None)


def t_marking_an_out_of_range_step_is_refused():
    w = World()
    goal = w.g.create("insulate the garage before winter")
    for bad in (-1, 1, "0", True):
        try:
            w.g.mark_step(goal["id"], bad, True)
            check(f"marking step {bad!r} was refused", False)
        except (ValueError, KeyError):
            check(f"marking step {bad!r} was refused", True)


def t_the_weekly_checkin_note_is_deterministic_and_reflects_done_steps():
    w = World()
    goal = w.g.create("insulate the garage before winter",
                      plan=[{"step": "contact installers", "by": "this week"},
                            {"step": "pick one", "by": ""}])
    accepted = w.g.accept(goal["id"])
    note1 = w.g.checkin_note(goal["id"])
    check("the note names the goal and the next open step",
          "insulate the garage" in note1 and "contact installers" in note1, note1)
    w.g.mark_step(goal["id"], 0, True)
    note2 = w.g.checkin_note(goal["id"])
    check("once the first step is done, the note moves to the next one",
          "pick one" in note2 and "contact installers" not in note2, note2)
    job_id = accepted["checkin"]["id"]
    check("the same note reaches the scheduler's own job view",
          w.sched.job(job_id)["note"] == note2)
    w.g.mark_step(goal["id"], 1, True)
    note3 = w.g.checkin_note(goal["id"])
    check("every step done says so", "every step is marked done" in note3, note3)
    # on_checkin must never raise, whatever the goal's state.
    try:
        w.g.on_checkin("no-such-goal")
        w.g.on_checkin(goal["id"])
        ok = True
    except Exception:
        ok = False
    check("on_checkin never raises", ok)


def t_a_plan_over_the_limit_or_empty_is_refused_with_a_plain_sentence():
    checks = [
        ([], "empty plan"),
        ([{"step": ""}], "an empty step"),
        ([{"step": "x"}] * (G.MAX_STEPS + 1), "too many steps"),
        ([{"step": "x" * (G.MAX_TEXT + 1)}], "a step too long"),
        ([{"step": "x", "by": "y" * (G.MAX_BY + 1)}], "a date label too long"),
        ("not a list", "not a list at all"),
        ([1, 2], "steps that are not objects"),
    ]
    for plan, label in checks:
        try:
            G.clean_plan(plan)
            check(f"refused: {label}", False)
        except ValueError as exc:
            check(f"refused: {label}", True)
            check(f"  ...with a plain sentence, not a bare type name ({label})",
                 str(exc) not in ("", "ValueError") and " " in str(exc), repr(exc))


def t_too_many_open_goals_is_refused():
    w = World()
    for i in range(G.MAX_GOALS):
        w.g.create(f"goal {i}")
    try:
        w.g.create("one too many")
        check("the goal limit is enforced", False)
    except OverflowError:
        check("the goal limit is enforced", True)


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

class FakeHandler:
    def do_GET(self):
        self._send(404, {"error": "original handler"})

    def do_POST(self):
        self._send(404, {"error": "original handler"})


class Req(FakeHandler):
    def __init__(self, path, body=None):
        self.path = path
        self._body = json.dumps(body if body is not None else {}).encode()
        self.sent = None

    def _send(self, code, out):
        self.sent = (code, out)


class _Patched:
    """Keeps jarvis_goals.get()/register() pointed at ONE World for as long
    as the `with` block runs - `handle_get`/`handle_post` look `get` up in
    the module's globals at CALL time, not when `install()` was run, so the
    patch must still be in place when the route handlers are actually
    called, not only while `install()` itself runs."""

    def __init__(self, w: "World", *, origin_ok=lambda h: True, token_ok=lambda h: True):
        self.w, self._origin_ok, self._token_ok = w, origin_ok, token_ok

    def __enter__(self):
        self._real_get, self._real_register = G.get, G.register
        G.get = lambda: self.w.g
        G.register = lambda: None  # World() already registered the kind
        self.handler_cls = type("H", (FakeHandler,), {})
        self.banner = G.install(self.handler_cls, origin_ok=self._origin_ok,
                                token_ok=self._token_ok, read_body=lambda h: h._body)
        return self

    def __exit__(self, *exc):
        G.get, G.register = self._real_get, self._real_register


def t_the_routes_answer_the_same_shapes_the_store_does():
    w = World()
    with _Patched(w) as p:
        handler_cls, banner = p.handler_cls, p.banner
        check("install() returns a banner naming the route", "goals" in banner, banner)

        r = Req("/api/goals", {"text": "insulate the garage before winter"})
        handler_cls.do_POST(r)
        check("POST /api/goals creates a draft",
              r.sent[0] == 200 and r.sent[1]["goal"]["status"] == "draft")
        gid = r.sent[1]["goal"]["id"]

        r = Req(f"/api/goals/{gid}/accept",
               {"plan": [{"step": "contact 3 installers", "by": "this week"}]})
        handler_cls.do_POST(r)
        check("POST .../accept activates it",
              r.sent[0] == 200 and r.sent[1]["goal"]["status"] == "active")

        r = Req("/api/goals")
        handler_cls.do_GET(r)
        check("GET /api/goals lists it", r.sent[0] == 200 and len(r.sent[1]["goals"]) == 1)

        r = Req(f"/api/goals/{gid}")
        handler_cls.do_GET(r)
        check("GET /api/goals/<id> reads it back", r.sent[0] == 200 and r.sent[1]["goal"]["id"] == gid)

        r = Req(f"/api/goals/{gid}/step", {"index": 0, "done": True})
        handler_cls.do_POST(r)
        check("POST .../step marks it done", r.sent[1]["goal"]["plan"][0]["done"] is True)

        r = Req(f"/api/goals/{gid}/stop", {})
        handler_cls.do_POST(r)
        check("POST .../stop stops it", r.sent[1]["goal"]["status"] == "stopped")

        r = Req("/api/goals/no-such-id")
        handler_cls.do_GET(r)
        check("an unknown goal is a plain 404", r.sent == (404, {"ok": False, "error": "no such goal"}))

        r = Req("/api/goals", "not an object")
        r._body = b"not json"
        handler_cls.do_POST(r)
        check("a body that is not JSON is a plain 400, never a stack trace", r.sent[0] == 400)

        r = Req("/api/something/else")
        handler_cls.do_GET(r)
        check("an unrelated route still reaches the original handler",
              r.sent == (404, {"error": "original handler"}))
        r = Req("/api/something/else")
        handler_cls.do_POST(r)
        check("...for POST too", r.sent == (404, {"error": "original handler"}))


def t_a_refused_origin_or_token_never_reaches_the_store():
    w = World()
    with _Patched(w, origin_ok=lambda h: False) as p:
        r = Req("/api/goals", {"text": "x"})
        p.handler_cls.do_POST(r)
        check("a bad origin is refused before the store is touched",
              r.sent == (403, {"error": "cross-origin request refused"}))
        check("nothing was created", w.g.list() == [])


# --------------------------------------------------------------------------
#   Step locks, done dates and the pace line (JARVIS-API section 101)
# --------------------------------------------------------------------------

PROJ, BENCH = "a" * 32, "b" * 32


def bench(latest=None, target=30.0, better="lower", *, sensitive=False, forecast=None,
          name="5k time", unit="min"):
    return {"id": BENCH, "name": name, "unit": unit, "better": better, "target": target,
            "sensitive": sensitive, "keep_on_screen": sensitive,
            "latest": None if latest is None else {"id": "x", "value": latest, "at": 1.0},
            "forecast": forecast}


RANGE = {"state": "range", "words": "About 6 to 9 weeks at this pace."}


def garage(w, extra=None):
    """quote -> pick -> install (each waits on the one before)."""
    plan = [{"id": "s1", "step": "get three quotes", "by": "this week"},
            {"id": "s2", "step": "pick an installer", "needs": ["s1"]},
            {"id": "s3", "step": "book the install", "needs": ["s2"]}]
    if extra:
        plan += extra
    return w.g.create("insulate the garage", plan=plan)


def t_plan_steps_get_stable_ids_and_keep_them_when_reordered():
    w = World()
    goal = w.g.create("x", plan=[{"step": "one"}, {"step": "two", "needs": ["s1"]}])
    check("steps without ids get s1, s2 by position",
          [s["id"] for s in goal["plan"]] == ["s1", "s2"] and goal["plan"][1]["needs"] == ["s1"])
    flipped = [dict(goal["plan"][1]), dict(goal["plan"][0])]
    flipped[0]["needs"] = ["s1"]
    accepted = w.g.accept(goal["id"], plan=flipped)
    check("reordered steps keep their ids, so a lock still points at the right step",
          [s["id"] for s in accepted["plan"]] == ["s2", "s1"]
          and accepted["plan"][0]["needs"] == ["s1"], accepted["plan"])
    dup = w.g.create("y", plan=[{"id": "s1", "step": "a"}, {"id": "s1", "step": "b"}])
    check("a repeated id is given a fresh one, never two steps sharing one",
          len({s["id"] for s in dup["plan"]}) == 2, dup["plan"])
    seven = w.g.create("z", plan=[{"step": f"step {i}"} for i in range(7)])
    check("7 steps is still the limit and all get ids",
          len({s["id"] for s in seven["plan"]}) == 7)
    try:
        w.g.create("z", plan=[{"step": f"step {i}"} for i in range(8)])
        check("8 steps is still refused", False)
    except ValueError:
        check("8 steps is still refused", True)


def refused(w, plan, needle=""):
    before = len(w.g.list())
    try:
        w.g.create("g", plan=plan)
        return False
    except ValueError as exc:
        return needle in str(exc) and len(w.g.list()) == before      # and nothing was stored


def t_cycles_unknown_ids_and_too_many_needs_are_refused_on_save():
    w = World()
    check("a step that waits on itself is refused, naming it",
          refused(w, [{"id": "s1", "step": "paint", "needs": ["s1"]}], '"paint" cannot wait on itself'))
    check("a step that waits on a step that is not there is refused",
          refused(w, [{"id": "s1", "step": "paint", "needs": ["s9"]}], "not in this plan"))
    check("a two-step loop is refused, naming both steps",
          refused(w, [{"id": "s1", "step": "paint", "needs": ["s2"]},
                      {"id": "s2", "step": "sand", "needs": ["s1"]}],
                  "in a circle"))
    check("a three-step loop is refused",
          refused(w, [{"id": "s1", "step": "a", "needs": ["s3"]},
                      {"id": "s2", "step": "b", "needs": ["s1"]},
                      {"id": "s3", "step": "c", "needs": ["s2"]}], "in a circle"))
    four = [{"id": f"s{i}", "step": f"n{i}"} for i in range(1, 5)]
    four.append({"id": "s5", "step": "last", "needs": ["s1", "s2", "s3", "s4"]})
    check("more than 3 needs is refused", refused(w, four, "at most 3 other steps"))
    ok = four[:4] + [{"id": "s5", "step": "last", "needs": ["s1", "s2", "s3"]}]
    check("exactly 3 needs is fine", not refused(w, ok))
    diamond = [{"id": "s1", "step": "a"}, {"id": "s2", "step": "b", "needs": ["s1"]},
               {"id": "s3", "step": "c", "needs": ["s1"]},
               {"id": "s4", "step": "d", "needs": ["s2", "s3"]}]
    check("a diamond (two steps sharing a prerequisite) is not a cycle", not refused(w, diamond))
    check("needs must be a list of ids", refused(w, [{"step": "a", "needs": "s1"}]))
    check("a repeated need is counted once",
          not refused(w, [{"id": "s1", "step": "a"}, {"id": "s2", "step": "b", "needs": ["s1", "s1"]}]))


def t_a_locked_step_shows_why_and_a_hand_tick_on_it_is_refused():
    w = World()
    goal = garage(w)
    plan = goal["plan"]
    check("the first step is open, the next two are locked",
          [s["state"] for s in plan] == ["open", "locked", "locked"], [s["state"] for s in plan])
    check("a locked step says what it waits for, in words",
          plan[1]["lock_words"] == 'after: "get three quotes"' and plan[1]["waiting_on"] == ["s1"])
    check("...and step three waits on step two only",
          plan[2]["lock_words"] == 'after: "pick an installer"')
    try:
        w.g.mark_step(goal["id"], 2, True)
        check("ticking a locked step by hand is refused", False)
    except G.Locked as exc:
        check("ticking a locked step by hand is refused, in a plain sentence",
              str(exc) == 'Do "pick an installer" first, or tick it if it is already done.'
              and exc.waiting_on == ["s2"], str(exc))
    check("nothing was written by the refused tick",
          [s["done"] for s in w.g.get(goal["id"])["plan"]] == [False, False, False])
    check("no 'unlock anyway' exists: the step is still locked",
          w.g.get(goal["id"])["plan"][2]["state"] == "locked")
    w.clock.t += 60
    after = w.g.mark_step(goal["id"], 0, True)
    check("ticking the prerequisite unlocks the next step at once",
          [s["state"] for s in after["plan"]] == ["done", "open", "locked"])
    check("...and writes the time it was ticked", after["plan"][0]["done_at"] == w.clock.t)
    check("a tick raises no card", w.cards == [])


def t_undo_clears_the_done_time_and_never_cascades():
    w = World()
    goal = garage(w)
    w.g.mark_step(goal["id"], 0, True)
    w.clock.t += 10
    w.g.mark_step(goal["id"], 1, True)
    t2 = w.clock.t
    w.clock.t += 10
    after = w.g.mark_step(goal["id"], 0, False)          # Undo the first tick
    p = after["plan"]
    check("undo clears that step's done time", p[0]["done"] is False and p[0]["done_at"] is None)
    check("a later step that was already done stays done, with its own time",
          p[1]["done"] is True and p[1]["done_at"] == t2 and p[1]["state"] == "done")
    check("...and reads 'after ... (open again)'",
          p[1]["lock_words"] == 'after: "get three quotes" (open again)' and p[1]["waiting_on"] == ["s1"],
          p[1]["lock_words"])
    check("unticking a step that was never ticked is harmless",
          w.g.mark_step(goal["id"], 2, False)["plan"][2]["done_at"] is None)
    again = w.g.mark_step(goal["id"], 1, True)           # ticking a done step again: no new time
    check("ticking an already-done step keeps its first time", again["plan"][1]["done_at"] == t2)
    byid = w.g.mark_step(goal["id"], None, True, step_id="s1")
    check("a step can be ticked by its id", byid["plan"][0]["done"] is True)
    try:
        w.g.mark_step(goal["id"], None, True, step_id="s7")
        check("an unknown id is refused", False)
    except ValueError:
        check("an unknown id is refused", True)


def t_reaching_a_number_meets_a_step_but_never_ticks_it():
    w = World()
    w.benches[(PROJ, BENCH)] = bench(latest=31.0)
    goal = w.g.create("race", plan=[
        {"id": "s1", "step": "get the 5k under 30", "measure": {"project": PROJ, "bench": BENCH}},
        {"id": "s2", "step": "enter the race", "needs": ["s1"]}])
    p = goal["plan"]
    check("target not reached: step one open, step two locked",
          [s["state"] for s in p] == ["open", "locked"])
    w.benches[(PROJ, BENCH)] = bench(latest=29.5)
    p = w.g.get(goal["id"])["plan"]
    check("target reached: the step is 'met_by_number' and the next step unlocks",
          [s["state"] for s in p] == ["met_by_number", "open"], [s["state"] for s in p])
    check("...but the owner's tick is untouched: done false, no done time",
          p[0]["done"] is False and p[0]["done_at"] is None)
    check("...and it says so in words, with the number",
          p[0]["reached"] is True
          and p[0]["reached_words"] == "The number reached its target: 29.5 min (target 30 min).",
          p[0]["reached_words"])
    check("the benchmark's name is sent for the screen", p[0]["measure_name"] == "5k time")
    w.clock.t += 5
    ticked = w.g.mark_step(goal["id"], 0, True)["plan"][0]
    check("the owner can still tick it: now done, with a time",
          ticked["state"] == "done" and ticked["done_at"] == w.clock.t)
    # the other way: a hand tick meets a step whose number has not arrived
    w.benches[(PROJ, BENCH)] = bench(latest=35.0)
    p = w.g.get(goal["id"])["plan"]
    check("a hand tick meets a measure step whose number has not arrived: step two open",
          p[0]["state"] == "done" and p[1]["state"] == "open")
    # higher is better
    w.benches[(PROJ, BENCH)] = bench(latest=21.1, target=21.0, better="higher", name="Long run", unit="km")
    g2 = w.g.create("dist", plan=[{"step": "run 21 km", "measure": {"project": PROJ, "bench": BENCH}}])
    check("higher is better: latest >= target is reached", g2["plan"][0]["state"] == "met_by_number")
    check("a benchmark that is gone leaves the step open and says so",
          (lambda: (w.benches.clear(), w.g.get(g2["id"])["plan"][0])[1])()["measure_gone"] is True)


def t_a_measure_must_follow_a_real_benchmark_with_a_target():
    w = World()
    step = {"step": "under 30", "measure": {"project": PROJ, "bench": BENCH}}
    check("a benchmark that does not exist is refused on save", refused(w, [step], "does not exist"))
    w.benches[(PROJ, BENCH)] = bench(latest=31.0, target=None)
    check("a benchmark with no target is refused, asking for one",
          refused(w, [step], "has no target yet - set one first"))
    w.benches[(PROJ, BENCH)] = bench(latest=31.0, better=None)
    check("a benchmark that does not say better is higher or lower is refused",
          refused(w, [step], "no target yet"))
    check("a measure that is not two benchmark ids is refused",
          refused(w, [{"step": "x", "measure": {"project": "p", "bench": "b"}}], "does not exist")
          and refused(w, [{"step": "x", "measure": "nope"}], "does not exist"))
    w.benches[(PROJ, BENCH)] = bench(latest=31.0)
    goal = w.g.create("ok", plan=[dict(step, id="s1")])
    check("a good measure is kept", goal["plan"][0]["measure"] == {"project": PROJ, "bench": BENCH})
    w.benches[(PROJ, BENCH)] = bench(latest=31.0, target=None)      # target removed later
    accepted = w.g.accept(goal["id"], plan=[dict(goal["plan"][0])])
    check("a measure that did not change is not re-checked when the goal is saved again",
          accepted["status"] == "active")


def t_a_broken_reader_is_not_a_gone_benchmark_and_does_not_relock():
    w = World()
    w.benches[(PROJ, BENCH)] = bench(latest=29.5)
    goal = w.g.create("race", plan=[
        {"id": "s1", "step": "get the 5k under 30", "measure": {"project": PROJ, "bench": BENCH}},
        {"id": "s2", "step": "enter the race", "needs": ["s1"]}])
    check("reader fine, target reached: step two open",
          [s["state"] for s in w.g.get(goal["id"])["plan"]] == ["met_by_number", "open"])
    real = w.read_bench

    def broken(project, bench_id):
        raise RuntimeError("database is locked")
    w.g._bench_reader = broken
    p = w.g.get(goal["id"])["plan"]
    check("a reader that raises something else: the step is NOT 'measure_gone'",
          p[0]["measure_gone"] is False and p[0]["reached"] is False, p[0])
    check("...its own state is not a tick and not locked", p[0]["state"] == "open", p[0]["state"])
    check("...and the step that waits on it is not re-locked", p[1]["state"] == "open"
          and p[1]["waiting_on"] == [], p[1])
    w.g._bench_reader = real
    w.benches.clear()
    p = w.g.get(goal["id"])["plan"]
    check("a real KeyError is still 'measure_gone'", p[0]["measure_gone"] is True, p[0])
    check("...and a gone number no longer meets the step, so its dependant waits again",
          p[1]["state"] == "locked", p[1]["state"])


def t_repeated_needs_are_deduped_before_the_limit():
    w = World()
    plan = [{"id": "s1", "step": "a"}, {"id": "s2", "step": "b"}, {"id": "s3", "step": "c"},
            {"id": "s4", "step": "d"},
            {"id": "s5", "step": "e", "needs": ["s1", "s1", "s2", "s2", "s3", "s3"]}]
    goal = w.g.create("dupes", plan=plan)
    check("s1,s1,s2,s2,s3,s3 is three needs, not six: saved once each",
          goal["plan"][4]["needs"] == ["s1", "s2", "s3"], goal["plan"][4]["needs"])
    check("four different needs are still refused",
          refused(w, [dict(plan[0]), dict(plan[1]), dict(plan[2]), dict(plan[3]),
                      {"id": "s5", "step": "e", "needs": ["s1", "s2", "s3", "s4", "s1"]}],
                  "at most 3"))


def t_the_lock_applies_on_the_tick_route_only():
    w = World()
    goal = w.g.create("draft done", plan=[
        {"id": "s1", "step": "first"},
        {"id": "s2", "step": "second", "done": True, "needs": ["s1"]}])
    p = goal["plan"]
    check("a draft step saved done with unmet needs is kept done, with the accept-time stamp",
          p[1]["done"] is True and p[1]["done_at"] == w.clock.t and p[1]["state"] == "done"
          and p[1]["lock_words"] == 'after: "first" (open again)', p[1])


def t_old_plans_load_with_defaults_and_get_ids_on_the_next_save():
    import sqlite3
    w = World()
    old = [{"step": "contact installers", "by": "this week", "done": True},
           {"step": "pick one", "by": "", "done": False}]
    con = sqlite3.connect(w.g.path)
    con.execute("INSERT INTO goals (id, text, plan, status, created, changed, checkin_job) "
                "VALUES ('gold', 'old goal', ?, 'draft', 1, 1, NULL)", (json.dumps(old),))
    con.commit()
    con.close()
    goal = w.g.get("gold")
    p = goal["plan"]
    check("an old plan loads: ids s1, s2 by position, no done time (unknown), no locks",
          [s["id"] for s in p] == ["s1", "s2"] and p[0]["done_at"] is None and p[0]["needs"] == []
          and p[0]["measure"] is None and p[0]["state"] == "done" and p[1]["state"] == "open", p)
    check("loading wrote nothing: the stored plan still has no ids",
          "id" not in json.loads(sqlite3.connect(w.g.path).execute(
              "SELECT plan FROM goals WHERE id='gold'").fetchone()[0])[0])
    w.g.mark_step("gold", 1, True)
    stored = json.loads(sqlite3.connect(w.g.path).execute(
        "SELECT plan FROM goals WHERE id='gold'").fetchone()[0])
    check("the next save writes the ids", [s["id"] for s in stored] == ["s1", "s2"])
    check("the step ticked before this existed keeps 'unknown' as its time, the new tick has one",
          stored[0]["done_at"] is None and stored[1]["done_at"] == w.clock.t)


def t_the_weekly_check_in_skips_locked_steps_and_says_when_waiting():
    w = World()
    goal = garage(w)
    w.g.accept(goal["id"])
    note = w.g.checkin_note(goal["id"])
    check("the note picks the first step that is not locked",
          'still on track for "get three quotes" (this week)?' in note, note)
    w.g.mark_step(goal["id"], 0, True)
    note = w.g.checkin_note(goal["id"])
    check("once the quotes are done, the note moves to the step that unlocked",
          '"pick an installer"' in note and "book the install" not in note, note)
    check("the next open step is the first unlocked one",
          w.g.next_open_step(goal["id"])["step"] == "pick an installer")
    # A defensive path: a stored plan with a circle (the routes refuse to save one).
    import sqlite3
    cyc = [{"id": "s1", "step": "paint", "by": "", "done": False, "done_at": None,
            "needs": ["s2"], "measure": None},
           {"id": "s2", "step": "sand", "by": "", "done": False, "done_at": None,
            "needs": ["s1"], "measure": None}]
    g = w.g.create("cycle test")
    con = sqlite3.connect(w.g.path)
    con.execute("UPDATE goals SET plan = ?, status = 'active' WHERE id = ?", (json.dumps(cyc), g["id"]))
    con.commit()
    con.close()
    note = w.g.checkin_note(g["id"])
    check("every open step locked: 'Waiting on ...' (and no endless loop)",
          note.startswith('"cycle test": Waiting on "') and note.endswith('".'), note)
    check("...and no next step", w.g.next_open_step(g["id"]) is None)


def t_the_check_in_says_a_number_reached_its_target_and_adds_a_pace_line():
    w = World()
    w.benches[(PROJ, BENCH)] = bench(latest=29.0)
    goal = w.g.create("race", plan=[
        {"id": "s1", "step": "5k under 30", "measure": {"project": PROJ, "bench": BENCH}},
        {"id": "s2", "step": "enter", "needs": ["s1"]}])
    w.g.accept(goal["id"])
    note = w.g.checkin_note(goal["id"])
    check("a number that reached its target: 'tick it when you are ready'",
          note == '"race": 5k under 30: the number reached its target - tick it when you are ready.',
          note)
    # Not reached, a real range, non-private: one neutral pace line.
    w.benches[(PROJ, BENCH)] = bench(latest=33.0, forecast=RANGE)
    note = w.g.checkin_note(goal["id"])
    check("a real range on a non-private benchmark adds one neutral pace line",
          note == '"race": still on track for "5k under 30"? About 6 to 9 weeks at this pace.', note)
    for label, f in (("not enough numbers", {"state": "not_enough", "words": "Not enough numbers yet - 2 more needed."}),
                     ("never reached", {"state": "never", "words": "Not reached at this pace."}),
                     ("open ended", {"state": "open_ended", "words": "About 4 weeks or more - x"}),
                     ("none at all", None)):
        w.benches[(PROJ, BENCH)] = bench(latest=33.0, forecast=f)
        check(f"no pace line when the answer is {label}",
              w.g.checkin_note(goal["id"]) == '"race": still on track for "5k under 30"?')
    w.benches[(PROJ, BENCH)] = bench(latest=80.0, target=70.0, sensitive=True, forecast=RANGE,
                                     name="Weight", unit="kg")
    note = w.g.checkin_note(goal["id"])
    check("a health or money benchmark's range never reaches the check-in note",
          "weeks" not in note and "pace" not in note, note)
    w.benches[(PROJ, BENCH)] = bench(latest=79.0, target=70.0, better="lower", sensitive=True,
                                     name="Weight", unit="kg")
    check("...but it stays on the screen: the goal read still carries the range's step state",
          w.g.get(goal["id"])["plan"][0]["measure_sensitive"] is True)
    w.g.stop(goal["id"])
    check("a stopped goal has no note", w.g.checkin_note(goal["id"]) == "")


def t_the_routes_carry_locks_ids_and_the_409():
    w = World()
    with _Patched(w) as p:
        hc = p.handler_cls
        r = Req("/api/goals", {"text": "garage", "plan": [
            {"step": "quotes"}, {"step": "pick", "needs": ["s1"]}]})
        hc.do_POST(r)
        gid = r.sent[1]["goal"]["id"]
        plan = r.sent[1]["goal"]["plan"]
        check("POST /api/goals keeps needs and answers ids and states",
              r.sent[0] == 200 and plan[1]["needs"] == ["s1"] and plan[1]["state"] == "locked")
        r = Req("/api/goals", {"text": "loop", "plan": [
            {"id": "s1", "step": "a", "needs": ["s2"]}, {"id": "s2", "step": "b", "needs": ["s1"]}]})
        hc.do_POST(r)
        check("a circle is a plain 400 with a sentence",
              r.sent[0] == 400 and "in a circle" in r.sent[1]["error"], r.sent)
        r = Req(f"/api/goals/{gid}/step", {"index": 1, "done": True})
        hc.do_POST(r)
        check("ticking a locked step is a 409 with the sentence and what it waits on",
              r.sent[0] == 409 and r.sent[1]["ok"] is False and r.sent[1]["locked"] is True
              and r.sent[1]["waiting_on"] == ["s1"]
              and r.sent[1]["error"] == 'Do "quotes" first, or tick it if it is already done.',
              r.sent)
        r = Req(f"/api/goals/{gid}/step", {"id": "s1", "done": True})
        hc.do_POST(r)
        check("POST .../step accepts {id, done}",
              r.sent[0] == 200 and r.sent[1]["goal"]["plan"][0]["done"] is True
              and r.sent[1]["goal"]["plan"][1]["state"] == "open")
        r = Req(f"/api/goals/{gid}/step", {"id": 5, "done": True})
        hc.do_POST(r)
        check("a step id that is not text is a plain 400", r.sent[0] == 400)
        r = Req("/api/goals")
        hc.do_GET(r)
        check("GET /api/goals says the limits and the lock words",
              r.sent[1]["limits"]["needs"] == 3 and r.sent[1]["limits"]["steps"] == 7
              and r.sent[1]["words"]["locked_refusal"].startswith("Do "), r.sent[1]["limits"])


def t_no_sql_is_stored_and_the_goal_module_calls_no_model():
    src = (HERE / "jarvis_goals.py").read_text(encoding="utf-8")
    check("plan steps are two fixed fields checked by plain code: no eval, exec or stored query",
          "eval(" not in src and "exec(" not in src and "criteria" not in src.lower())
    import re
    check("this module still opens no socket",
          not re.search(r"^\s*(import|from)\s+(socket|urllib\.request|http\.client|requests|subprocess)\b", src, re.M))


def main() -> int:
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
