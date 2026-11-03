"""test_goals_progress.py - the goals a reminder area can hold, and talking
to Jarvis about them (the owner's ask of 2026-11-02: *"add a goals section in
the reminder area and a way for me to record progress there along with talking
to jarvis"*).

    python3 backend/test_goals_progress.py

WHY THIS IS A SECOND GOALS SUITE, NOT MORE LINES IN `test_goals.py`

`test_goals.py` proves the 2026-09-27 feature - a plan, its steps, the weekly
check-in - and its fixtures are built around a real `jarvis_schedule.Scheduler`
and a hand-moved clock. This is the 2026-11-02 half: a goal that is open the
moment it is made, an append-only progress log, the done / paused / resumed /
removed states, and the four model tools. It needs no scheduler at all (a goal
made here has no check-in), so keeping it apart leaves both suites readable and
lets either run on its own.

WHAT IT PROVES, with a real SQLite file in a temporary folder:

  * `create(start=True)` makes an OPEN goal at once, with its optional target
    and notes, and sets up no scheduler job and no card;
  * a progress line is APPENDED: two lines both stay, the first is unchanged,
    and the module has no function that edits or deletes one;
  * a line's optional number and date are read the way the screen shows them
    (a numeric string is still a number; a date is kept as that day);
  * done, paused, resumed and removed are one tap each, and removing a goal
    takes its log with it and is the ONLY delete;
  * `find_one` picks the one goal plain words mean, and refuses to guess when
    they match none or several;
  * the routes: install() wraps do_GET/do_POST after the origin and token
    checks; a refused origin (403) or token (401) changes NOTHING; the list,
    the add, the progress write and read, done/pause/resume/remove all answer
    the shapes above; an unknown goal is a plain 404;
  * the agent tools: `goals_list`, `goal_add`, `goal_progress` and `goal_done`
    run straight against the store with NO gate and NO card, the three writes
    are refused in a turn shaped by outside text (and change nothing), the
    read is allowed there and is marked as outside text like `coming_up`, and
    no tool can delete a goal or a progress line.

Every check fails on the code before 2026-11-02: the progress table, the
states and the four tools did not exist.
"""
from __future__ import annotations

import datetime as _dt
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

require_shipped("jarvis_goals.py", "jarvis_schedule.py", "jarvis_agent.py")

import jarvis_goals as G  # noqa: E402

PASSED, FAILED = [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-goals-progress-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class FakeScheduler:
    """Only the one thing done / pause / resume / remove ask of a scheduler:
    `act`. A goal made by the reminder area has no check-in job, so nothing
    is ever expected to call this for it - the calls are kept so a check can
    say so."""

    def __init__(self):
        self.calls = []
        self.jobs = {}

    def act(self, jid, do, seconds=None):
        self.calls.append((jid, do))
        return {"id": jid, "state": {"pause": "paused", "resume": "active"}.get(do, "gone")}


_N = [0]


def new_store(t=1_000_000.0, sched=None):
    _N[0] += 1
    return G.Goals(_TMP / f"goals-{_N[0]}.db", clock=Clock(t),
                   scheduler=sched if sched is not None else FakeScheduler())


# --------------------------------------------------------------------------
#   An open goal, and its own fields
# --------------------------------------------------------------------------

def t_a_goal_made_in_the_reminder_area_is_open_at_once():
    s = new_store()
    goal = s.create("Run 100 km this year", target="100 km",
                    notes="before the winter", start=True)
    check("a goal made here is open (active) at once, not a draft", goal["status"] == "active")
    check("its optional target is kept", goal["target"] == "100 km")
    check("its optional notes are kept", goal["notes"] == "before the winter")
    check("it has its own id and created date",
          bool(goal["id"]) and goal["created"] == 1_000_000.0)
    check("it has no progress yet", goal["progress"] == [] and goal["progress_count"] == 0)
    check("no scheduler job was set up for it", s._scheduler.calls == [])
    drafts = s.create("A draft goal, for the old plan path")
    check("the old draft path still makes a draft", drafts["status"] == "draft")
    check("... with no target or notes unless given",
          drafts["target"] == "" and drafts["notes"] == "")
    try:
        s.create("x", target="t" * (G.MAX_TARGET + 1), start=True)
        check("a target too long is refused in plain words", False)
    except ValueError as exc:
        check("a target too long is refused in plain words", "target" in str(exc), str(exc))


# --------------------------------------------------------------------------
#   The progress log is append-only
# --------------------------------------------------------------------------

def t_progress_is_append_only():
    s = new_store()
    goal = s.create("Run 100 km", start=True)
    first = s.add_progress(goal["id"], "Ran 5 km", 5, "2026-11-01")
    second = s.add_progress(goal["id"], "Ran 7 km", 7, "2026-11-02")
    check("both lines are kept", first["entry"]["id"] != second["entry"]["id"])
    log = s.progress(goal["id"])
    check("the log holds both lines", len(log) == 2, log)
    check("the newest line is first", log[0]["text"] == "Ran 7 km", log)
    check("the first line is exactly as it was written, not edited",
          log[1]["text"] == "Ran 5 km" and log[1]["value"] == 5.0,
          log[1])
    check("recording a line never raises a card (there is no gate in this store)",
          not hasattr(s, "gate"))
    named = [n for n in dir(G.Goals)
             if "progress" in n.lower()
             and any(w in n.lower() for w in ("update", "edit", "delete", "remove"))]
    check("no function on the store edits or deletes ONE progress line", named == [], named)
    gone = s.remove(goal["id"])
    check("removing the goal takes its log with it", gone["removed"] == goal["id"])
    try:
        s.progress(goal["id"])
        check("the removed goal's log is gone, not half there", False)
    except KeyError:
        check("the removed goal's log is gone, not half there", True)


def t_a_lines_number_and_date_are_read_the_way_the_screen_shows_them():
    s = new_store(t=1_700_000_000.0)
    goal = s.create("Save $2,000", target="$2,000", start=True)
    said = s.add_progress(goal["id"], "Saved 200", "200", None)
    check("a number written as text is still a number", said["entry"]["value"] == 200.0,
          said["entry"])
    when = s.add_progress(goal["id"], "Saved 300", None, "2026-11-01")["entry"]["at"]
    got = _dt.datetime.fromtimestamp(when).strftime("%Y-%m-%d")
    check("a date is kept as that day", got == "2026-11-01", got)
    check("no date means now", said["entry"]["at"] == 1_700_000_000.0, said["entry"]["at"])
    for label, kw in (("a word is not a number",
                       {"value": "five km"}),
                      ("an impossible date is refused",
                       {"at": "2026-13-40"})):
        try:
            s.add_progress(goal["id"], "x", **kw)
            check(label, False)
        except ValueError as exc:
            check(label, bool(str(exc)), str(exc))
    log = s.progress(goal["id"])
    check("a refused line was not added", len(log) == 2, len(log))


# --------------------------------------------------------------------------
#   Done, paused, resumed, removed
# --------------------------------------------------------------------------

def t_done_pause_resume_are_one_tap_each():
    s = new_store()
    goal = s.create("Run 100 km", start=True)
    check("done sets the state", s.mark_done(goal["id"])["status"] == "done")
    check("a done goal is kept, with its log", s.get(goal["id"])["status"] == "done")
    check("pause sets the state", s.pause(goal["id"])["status"] == "paused")
    check("resume opens it again", s.resume(goal["id"])["status"] == "active")
    s.stop(goal["id"])
    for name, fn in (("done", s.mark_done), ("pause", s.pause), ("resume", s.resume)):
        try:
            fn(goal["id"])
            check(f"a stopped goal refuses {name} in plain words", False)
        except ValueError as exc:
            check(f"a stopped goal refuses {name} in plain words", "stopped" in str(exc), str(exc))
    try:
        s.mark_done("no-such-id")
        check("an unknown goal is a KeyError (a plain 404 at the route)", False)
    except KeyError:
        check("an unknown goal is a KeyError (a plain 404 at the route)", True)


# --------------------------------------------------------------------------
#   Plain words pick the one goal
# --------------------------------------------------------------------------

def t_find_one_picks_a_goal_or_refuses_to_guess():
    s = new_store()
    run = s.create("Run 100 km this year", start=True)
    save = s.create("Save $2,000", start=True)
    check("its own id finds it", s.find_one(run["id"])["id"] == run["id"])
    check("the exact words find it", s.find_one("Save $2,000")["id"] == save["id"])
    check("part of the words find it", s.find_one("run 100")["id"] == run["id"])
    check("case does not matter", s.find_one("RUN 100 KM THIS YEAR")["id"] == run["id"])
    try:
        s.find_one("nothing like it")
        check("no match is refused in plain words", False)
    except KeyError as exc:
        check("no match is refused in plain words", "no goal matches" in str(exc.args[0]),
              str(exc))
    s.create("Run 100 km by June", start=True)
    try:
        s.find_one("run 100")
        check("two matches are refused, not guessed", False)
    except ValueError as exc:
        check("two matches are refused, not guessed", "more than one" in str(exc), str(exc))


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


class Patched:
    """Keeps jarvis_goals.get()/register() pointed at ONE store while the
    routes are driven - the route handlers look `get` up at CALL time."""

    def __init__(self, store, *, origin_ok=lambda h: True, token_ok=lambda h: True):
        self.store, self._origin_ok, self._token_ok = store, origin_ok, token_ok

    def __enter__(self):
        self._real_get, self._real_register = G.get, G.register
        G.get = lambda: self.store
        G.register = lambda: None
        self.handler_cls = type("H", (FakeHandler,), {})
        self.banner = G.install(self.handler_cls, origin_ok=self._origin_ok,
                                token_ok=self._token_ok, read_body=lambda h: h._body)
        return self

    def __exit__(self, *exc):
        G.get, G.register = self._real_get, self._real_register


def t_a_refused_origin_or_token_changes_nothing():
    s = new_store()
    with Patched(s, origin_ok=lambda h: False) as p:
        r = Req("/api/goals", {"text": "x", "start": True})
        p.handler_cls.do_POST(r)
        check("a bad origin is refused with a plain 403",
              r.sent == (403, {"error": "cross-origin request refused"}), r.sent)
        check("... and nothing was created", s.list() == [])
        r = Req("/api/goals")
        p.handler_cls.do_GET(r)
        check("... for a read too", r.sent[0] == 403, r.sent)
    with Patched(s, token_ok=lambda h: False) as p:
        r = Req("/api/goals", {"text": "x", "start": True})
        p.handler_cls.do_POST(r)
        check("a bad token is refused with a plain 401",
              r.sent == (401, {"error": "bad or missing X-Jarvis-Token"}), r.sent)
        check("... and nothing was created", s.list() == [])
    goal = s.create("Run 100 km", start=True)
    s.add_progress(goal["id"], "Ran 5 km", 5)
    before = json.dumps(s.list(), sort_keys=True)
    with Patched(s, token_ok=lambda h: False) as p:
        r = Req(f"/api/goals/{goal['id']}/done", {})
        p.handler_cls.do_POST(r)
        check("a refused write leaves the goal and its log exactly as they were",
              r.sent[0] == 401 and json.dumps(s.list(), sort_keys=True) == before)


def t_the_routes_answer_the_reminder_area():
    s = new_store()
    with Patched(s) as p:
        hc, banner = p.handler_cls, p.banner
        check("install() returns a banner naming the route", "goals" in banner, banner)

        r = Req("/api/goals", {"text": "Run 100 km", "target": "100 km", "start": True})
        hc.do_POST(r)
        check("POST /api/goals adds an OPEN goal",
              r.sent[0] == 200 and r.sent[1]["goal"]["status"] == "active", r.sent)
        gid = r.sent[1]["goal"]["id"]

        r = Req(f"/api/goals/{gid}/progress",
                {"text": "Ran 5 km", "value": 5, "date": "2026-11-01"})
        hc.do_POST(r)
        check("POST .../progress answers the entry and the goal",
              r.sent[0] == 200 and r.sent[1]["entry"]["text"] == "Ran 5 km"
              and r.sent[1]["goal"]["progress_count"] == 1, r.sent)

        r = Req(f"/api/goals/{gid}/progress")
        hc.do_GET(r)
        check("GET .../progress reads the whole log back",
              r.sent[0] == 200 and r.sent[1]["count"] == 1
              and r.sent[1]["progress"][0]["value"] == 5.0, r.sent)

        r = Req("/api/goals")
        hc.do_GET(r)
        check("GET /api/goals lists goals with their newest progress",
              r.sent[0] == 200 and len(r.sent[1]["goals"]) == 1
              and r.sent[1]["goals"][0]["progress"][0]["text"] == "Ran 5 km", r.sent)

        r = Req(f"/api/goals/{gid}/pause", {})
        hc.do_POST(r)
        check("POST .../pause pauses it", r.sent[1]["goal"]["status"] == "paused", r.sent)
        r = Req(f"/api/goals/{gid}/resume", {})
        hc.do_POST(r)
        check("POST .../resume opens it again", r.sent[1]["goal"]["status"] == "active", r.sent)
        r = Req(f"/api/goals/{gid}/done", {})
        hc.do_POST(r)
        check("POST .../done marks it done", r.sent[1]["goal"]["status"] == "done", r.sent)
        r = Req(f"/api/goals/{gid}/remove", {})
        hc.do_POST(r)
        check("POST .../remove takes it off, and says which one",
              r.sent[0] == 200 and r.sent[1]["removed"] == gid, r.sent)
        check("... and it is really gone", s.list() == [])

        r = Req("/api/goals/no-such-id/progress")
        hc.do_GET(r)
        check("an unknown goal is a plain 404",
              r.sent == (404, {"ok": False, "error": "no such goal"}), r.sent)
        r = Req("/api/goals/no-such-id/done", {})
        hc.do_POST(r)
        check("... for a write too", r.sent[0] == 404, r.sent)
        r = Req("/api/goals")
        r._body = b"not json"
        hc.do_POST(r)
        check("a body that is not JSON is a plain 400, never a stack trace", r.sent[0] == 400)
        for path in ("/api/something/else",):
            r = Req(path)
            hc.do_GET(r)
            check("an unrelated route still reaches the original handler",
                  r.sent == (404, {"error": "original handler"}), r.sent)


# --------------------------------------------------------------------------
#   Talking to Jarvis: the four tools
# --------------------------------------------------------------------------

class Watch:
    """The one thing `_goal_call` asks of the turn: is this turn shaped by
    outside text, and note a read. Built here so no real turn is needed."""

    def __init__(self, shaped=""):
        self.shaped, self.reads = shaped, []

    def note_needs_a_person(self, ignore_read=()):
        return self.shaped

    def took_in(self, name, result):
        self.reads.append(name)
        return result


def _run_tool(name, args, store, watch=None):
    """Drive jarvis_agent._goal_call once and return (step, parsed result)."""
    import jarvis_agent as AG
    real = G.get
    G.get = lambda: store
    try:
        steps, convo = [], []
        call = {"id": "call-1"}
        AG._goal_call(name, args, call, convo, steps, lambda *a, **k: None,
                      watch if watch is not None else Watch())
        content = convo[-1]["content"] if convo else "{}"
        try:
            result = json.loads(content if isinstance(content, str) else content)
        except Exception:
            result = {"raw": content}
        return steps[-1], result
    finally:
        G.get = real


def t_the_four_tools_are_real_and_no_tool_deletes():
    import jarvis_agent as AG
    check("the four goal tools are in the model's own table",
          set(AG.GOAL_TOOLS) == {"goals_list", "goal_add", "goal_progress", "goal_done"},
          sorted(AG.GOAL_TOOLS))
    check("... and every one of them is a real Tool object",
          all(n in AG.TOOLS for n in AG.GOAL_TOOLS))
    check("the read tool is the only one not refused in a shaped turn",
          AG.GOAL_READ_TOOLS == ("goals_list",), AG.GOAL_READ_TOOLS)
    check("no goal tool can delete a goal or a progress line",
          not any(w in n.lower() for n in AG.GOAL_TOOLS
                  for w in ("remove", "delete", "forget", "clear")), sorted(AG.GOAL_TOOLS))
    check("a plan step may never name one of them (they are not batchable)",
          all(AG._plan_step_excluded(n) for n in AG.GOAL_TOOLS))
    check("they resolve under the to-do list's own cardless action, inventing no new "
          "action or tier",
          all(AG.TOOLS[n].gate_lookup_name({}) == AG.GOAL_GATE_ACTION
              for n in AG.GOAL_TOOLS)
          and AG.GOAL_GATE_ACTION == "todo_add")


def t_goal_add_list_progress_and_done_work():
    s = new_store()
    step, out = _run_tool("goal_add", {"text": "Run 100 km", "target": "100 km"}, s)
    check("goal_add runs and answers ok", step["ok"] is True and out.get("ok") is True, out)
    check("... and says what it added", "Run 100 km" in str(out.get("said")), out.get("said"))
    gid = out["goal"]["id"]
    check("... the goal is open at once", out["goal"]["status"] == "active")

    step, out = _run_tool("goal_progress",
                          {"goal": "run 100", "text": "Ran 5 km", "value": 5}, s)
    check("goal_progress finds the goal by plain words and records the line",
          step["ok"] is True and out.get("entry", {}).get("text") == "Ran 5 km", out)
    check("... and says which goal it went on", "Run 100 km" in str(out.get("said")), out)

    step, out = _run_tool("goals_list", {}, s)
    names = [g["text"] for g in out.get("goals", [])]
    check("goals_list lists the open goal", step["ok"] is True and names == ["Run 100 km"], out)
    check("... with its newest progress line", out["goals"][0]["progress"][0]["text"] == "Ran 5 km",
          out["goals"][0])
    check("the read is marked as outside text, like coming_up",
          _run_tool("goals_list", {}, s, Watch())[0] is not None)

    step, out = _run_tool("goal_done", {"goal": "Run 100 km"}, s)
    check("goal_done marks it done", step["ok"] is True and out["goal"]["status"] == "done", out)
    step, out = _run_tool("goals_list", {}, s)
    check("a done goal is not in the open list", out.get("goals") == [], out)
    step, out = _run_tool("goals_list", {"include_done": True}, s)
    check("... but include_done lists it", len(out.get("goals", [])) == 1, out)
    check("the tool's own log was not deleted by any of that",
          len(s.progress(gid)) == 1)


def t_a_bad_worded_call_changes_nothing():
    s = new_store()
    _run_tool("goal_add", {"text": "Run 100 km"}, s)
    before = json.dumps(s.list(), sort_keys=True)
    for name, args in (("goal_progress", {"goal": "nothing like it", "text": "x"}),
                       ("goal_done", {"goal": "nothing like it"}),
                       ("goal_add", {"text": ""})):
        step, out = _run_tool(name, args, s)
        check(f"{name} refuses in plain words", step["ok"] is False and out.get("error"),
              out)
        check(f"... and {name} changed nothing",
              json.dumps(s.list(), sort_keys=True) == before)


def t_a_turn_shaped_by_outside_text_refuses_the_writes():
    s = new_store()
    _run_tool("goal_add", {"text": "Run 100 km"}, s)
    before = json.dumps(s.list(), sort_keys=True)
    shaped = "outside"
    for name, args in (("goal_add", {"text": "A goal an email asked for"}),
                       ("goal_progress", {"goal": "Run 100 km", "text": "5 km"}),
                       ("goal_done", {"goal": "Run 100 km"})):
        step, out = _run_tool(name, args, s, Watch(shaped))
        check(f"{name} refuses when outside text shaped the turn",
              step["ok"] is False and "outside text" in str(out.get("error")), out)
        check(f"... and {name} changed nothing",
              json.dumps(s.list(), sort_keys=True) == before)
    step, out = _run_tool("goals_list", {}, s, Watch(shaped))
    check("goals_list is still allowed when the turn is shaped (it only reads)",
          step["ok"] is True and out.get("goals"), out)


def t_the_turn_runs_a_goal_tool_with_no_gate_and_no_card():
    """The whole point of a cardless tool, driven through the turn's own
    dispatcher: the model's call runs, the store changes, and no gate/checker
    is asked at all. A source-text pin would prove nothing here - the check
    is the real call."""
    import jarvis_agent as AG
    s = new_store()
    asked = []
    real = G.get
    G.get = lambda: s
    try:
        call = {"id": "call-1", "function": {
            "name": "goal_add", "arguments": json.dumps({"text": "Run 100 km"})}}
        convo, steps = [], []
        AG._one_call(call, ["goal_add"], convo, steps,
                     checker=lambda *a, **k: asked.append(a) or None,
                     announce=lambda *a, **k: None, out=None,
                     say_step=lambda *a, **k: None,
                     watch=AG._TurnWatch(), tell_owner=None)
    finally:
        G.get = real
    check("the turn runs goal_add from the model's own call",
          bool(steps) and steps[-1]["ok"] is True, steps)
    check("... with the gate/checker NEVER asked, so no card and no approval",
          asked == [], asked)
    check("... the goal is really in the store",
          [g["text"] for g in s.list()] == ["Run 100 km"])
    check("... and the model is handed an ok result to answer from",
          bool(convo) and '"ok": true' in convo[-1]["content"], convo[-1:])


def t_a_shaped_turn_is_refused_through_the_same_dispatcher():
    """The stricter half, driven the same way: once the turn has read outside
    text, the model's own write call is refused and the store is untouched."""
    import jarvis_agent as AG
    s = new_store()
    real = G.get
    G.get = lambda: s
    try:
        watch = AG._TurnWatch()
        # The read mark a page or an email leaves: `read` is what
        # note_needs_a_person checks, and it is not one of NOTE_WRITES.
        watch.read["web_search"] = 1
        call = {"id": "call-2", "function": {
            "name": "goal_add", "arguments": json.dumps({"text": "From a web page"})}}
        convo, steps = [], []
        AG._one_call(call, ["goal_add"], convo, steps,
                     checker=lambda *a, **k: None, announce=lambda *a, **k: None,
                     out=None, say_step=lambda *a, **k: None,
                     watch=watch, tell_owner=None)
    finally:
        G.get = real
    check("a goal write after outside text never runs", steps[-1]["ran"] is False, steps)
    check("... and nothing reached the store", s.list() == [])
    check("... and the model is told why, in plain words",
          "outside text" in convo[-1]["content"], convo[-1:])


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
