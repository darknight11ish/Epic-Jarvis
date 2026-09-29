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
        self.g = G.Goals(_TMP / f"goals-{n}.db", clock=self.clock, scheduler=self.sched)
        S.register_kind(
            G.KIND, "goal check-in", "Jarvis: a goal check-in is due.",
            on_fire=lambda jid: self.g.on_checkin(self.g.goal_id_for_job(jid)),
            note=lambda jid: self.g.checkin_note(self.g.goal_id_for_job(jid)),
            **G.KIND_OPTIONS,
        )

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
    check("its plan defaults to its own words, one step",
          goal["plan"] == [{"step": "insulate the garage before winter",
                            "by": "", "done": False}])
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
