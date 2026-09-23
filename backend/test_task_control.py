"""jarvis_task_control.py - the pause/stop/inject-note signal store, and
the routes task-control.patch gives it (Pause, Resume, Stop, a note for what
runs next, and a note on one approval card).

    python3 test_task_control.py

No network, no model, no real gate: a fake module and a fake gate stand in,
and the patch is rehearsed with `git apply` on the text earlier patches wrote.
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_task_control as TC

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_no_signal_by_default():
    check("an id nobody asked about has no signal", TC.checkpoint("appr_never_touched") is None)


def t_none_task_id_never_raises():
    check("checkpoint(None) is None, not an error", TC.checkpoint(None) is None)


def t_request_rejects_unknown_actions():
    raised = False
    try:
        TC.request("appr_x", "resume")
    except ValueError:
        raised = True
    check("an action other than pause/stop raises", raised)
    check("CONTROL: the bad call left no signal behind", TC.checkpoint("appr_x") is None)


def t_stop_is_read_back():
    TC.request("appr_1", "stop")
    check("stop is read back", TC.checkpoint("appr_1") == "stop")
    TC.clear("appr_1")


def t_pause_is_read_back():
    TC.request("appr_2", "pause")
    check("pause is read back", TC.checkpoint("appr_2") == "pause")
    TC.clear("appr_2")


def t_clear_removes_the_signal():
    TC.request("appr_3", "stop")
    TC.clear("appr_3")
    check("cleared id has no signal", TC.checkpoint("appr_3") is None)


def t_clear_is_safe_on_an_id_with_no_signal():
    # CONTROL: clearing something that was never set must not raise.
    TC.clear("appr_never_set")
    check("clearing an unset id did not raise", True)


def t_a_later_request_replaces_an_earlier_one():
    TC.request("appr_4", "pause")
    TC.request("appr_4", "stop")
    check("the most recent request wins", TC.checkpoint("appr_4") == "stop")
    TC.clear("appr_4")


def t_signals_are_per_task():
    TC.request("appr_5a", "stop")
    check("a different id is untouched", TC.checkpoint("appr_5b") is None)
    TC.clear("appr_5a")


def t_note_is_queued_and_read_back():
    check("no note by default", TC.pending_note("appr_6") is None)
    TC.inject_note("appr_6", "also check the CC line")
    check("the note comes back", TC.pending_note("appr_6") == "also check the CC line")
    TC.clear("appr_6")
    check("clear() drops the note too", TC.pending_note("appr_6") is None)


def t_note_does_not_set_a_pause_or_stop_signal():
    # A note alone must never look like a pause/stop request to run()'s
    # own checkpoint() call - section 3d's "does not alter the steps
    # currently running" would be silently violated otherwise.
    TC.inject_note("appr_7", "wait, also cc Dana")
    check("injecting a note leaves no pause/stop signal", TC.checkpoint("appr_7") is None)
    TC.clear("appr_7")


def t_checkpoint_consumes_the_signal():
    # THE BUG THIS FIXES, end to end. checkpoint() used to only READ, and
    # nothing anywhere called clear(), so the pause sat here forever:
    # continuing a paused task started a fresh run whose very first
    # checkpoint found the same pause and stopped again. Permanently - and
    # so did any later task reusing the id.
    TC.request("appr_consume", "pause")
    first = TC.checkpoint("appr_consume")
    second = TC.checkpoint("appr_consume")
    check("the run loop sees the pause", first == "pause")
    check("a second read sees nothing - the signal was spent", second is None,
          repr(second))


def t_a_continued_task_does_not_pause_again():
    # The same thing said the way the owner experiences it.
    TC.request("appr_continue", "pause")
    check("the first run pauses", TC.checkpoint("appr_continue") == "pause")
    # ... the owner presses Continue, which starts a fresh run against the
    # same id. Its first checkpoint must be clean.
    check("the continued run is not paused at step 1",
          TC.checkpoint("appr_continue") is None)


def t_a_spent_stop_does_not_stop_the_next_task():
    TC.request("appr_reused", "stop")
    check("the stop is delivered once", TC.checkpoint("appr_reused") == "stop")
    check("an unrelated task reusing the id runs clean",
          TC.checkpoint("appr_reused") is None)


def t_peek_does_not_consume():
    TC.request("appr_peek", "pause")
    check("peek reports the pending pause", TC.peek("appr_peek") == "pause")
    check("peeking twice still reports it", TC.peek("appr_peek") == "pause")
    check("and the run loop can still take it", TC.checkpoint("appr_peek") == "pause")
    check("which then spends it", TC.peek("appr_peek") is None)
    TC.clear("appr_peek")


def t_peek_of_none_never_raises():
    check("peek(None) is None, not an error", TC.peek(None) is None)


def t_clear_still_cancels_a_signal_nothing_took():
    # clear()'s remaining job: the owner cancels a Pause BEFORE the run loop
    # has reached its next checkpoint, so there is a signal here that
    # nothing will ever pick up.
    TC.request("appr_cancelled", "pause")
    TC.clear("appr_cancelled")
    check("a cancelled pause never reaches the run loop",
          TC.checkpoint("appr_cancelled") is None)



# ==========================================================================
#   task-control.patch: the routes, the paused task, resume, and notes
# ==========================================================================
#
# What these pin, in plain words:
#   - Stop and Pause need no approval card, and are refused honestly (409)
#     when nothing is running - never a 200 that did nothing.
#   - Resume RUNS NOTHING by itself. It raises one card through the gate,
#     listing every step that is left; only an allowed verdict runs them,
#     and it runs the SAME plan object, cut down, not something rebuilt.
#   - A note (for the task, or on one approval card) never approves, denies
#     or changes a step. It reaches the model once, with the answer.
#   - "paused" is reported only after a run really paused.

import dataclasses  # noqa: E402
import json  # noqa: E402
import types  # noqa: E402
import subprocess  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

HERE = Path(__file__).resolve().parent
from _where import BACKEND, REPO, missing  # noqa: E402


def _reset():
    with TC._lock:
        TC._signals.clear(); TC._notes.clear(); TC._running.clear()
        TC._paused.clear(); TC._amends.clear(); TC._resuming.clear()
        TC._last_result.clear(); TC._log.clear()


@dataclasses.dataclass
class FakePlan:
    goal: str
    steps: list = dataclasses.field(default_factory=list)


class FakeModule:
    """Stands in for jarvis_ui_control: describe() and run() with a checkpoint."""
    def __init__(self):
        self.ran = []
        self.on_step = None

    def describe(self, p):
        return "\n".join(f"{i}. {s}" for i, s in enumerate(p.steps, 1))

    def run(self, p, *, approved=False, announce=None, checkpoint=None):
        assert approved is True
        done = []
        for i, s in enumerate(p.steps):
            sig = checkpoint() if checkpoint else None
            if sig in ("stop", "pause"):
                out = {"ok": False, "reason": sig, "done": done,
                       "not_run": list(p.steps[i:])}
                if sig == "pause":
                    out["paused"] = True
                return out
            self.ran.append(s)
            done.append(s)
            if self.on_step:
                self.on_step(s)
        return {"ok": True, "done": done, "not_run": []}


class Verdict:
    def __init__(self, allowed, outcome, request_id=None):
        self.allowed, self.outcome, self.request_id = allowed, outcome, request_id
        self.reason = outcome


def t_stop_and_pause_refuse_when_nothing_runs():
    _reset()
    code, out = TC.handle_post("/api/task/stop", {})
    check("stop with nothing running is a 409, not a 200 that did nothing",
          code == 409 and out["ok"] is False, repr((code, out)))
    code, out = TC.handle_post("/api/task/pause", {})
    check("pause with nothing running is a 409", code == 409, repr((code, out)))
    code, out = TC.handle_post("/api/task/resume", {})
    check("resume with nothing paused is a 409", code == 409, repr((code, out)))
    code, out = TC.handle_post("/api/task/note", {"note": "hi"})
    check("a note with nothing to attach to is a 409", code == 409, repr((code, out)))
    code, _ = TC.handle_post("/api/task/stop", ["not", "an", "object"])
    check("a body that is not an object is a 400", code == 400)


def t_stop_and_pause_reach_a_running_task_without_a_card():
    _reset()
    asked = []
    TC.begin("appr_run", "control_computer")
    code, out = TC.handle_post("/api/task/pause", {}, gate_check=lambda *a: asked.append(a))
    check("pause answers 200", code == 200, repr(out))
    check("pause asked the gate nothing", asked == [])
    check("the run loop sees the pause", TC.checkpoint("appr_run") == "pause")
    code, out = TC.handle_post("/api/task/stop", {})
    check("stop answers 200 and names the task",
          code == 200 and out["stopping"] == ["appr_run"], repr(out))
    check("the run loop sees the stop", TC.checkpoint("appr_run") == "stop")
    TC.end("appr_run")
    check("end() unregisters it", TC.running() == [])
    check("pause and stop were both written to the history",
          [e["what"] for e in TC.status()["recent"]] == ["pause", "stop"])


def t_a_signal_after_the_last_step_does_not_outlive_the_run():
    _reset()
    TC.begin("appr_late", "control_phone")
    TC.handle_post("/api/task/stop", {})
    TC.end("appr_late")      # run() returned before reading it
    check("end() spends a stop nothing read", TC.checkpoint("appr_late") is None)


def t_notes_are_bounded_and_cleaned():
    _reset()
    TC.begin("appr_n", "control_computer")
    code, _ = TC.handle_post("/api/task/note", {"note": "   "})
    check("an empty note is a 400", code == 400)
    code, _ = TC.handle_post("/api/task/note", {"note": 42})
    check("a note that is not text is a 400", code == 400)
    long = "x" * 5000 + "\x1b[31m"
    code, out = TC.handle_post("/api/task/note", {"note": long})
    got = TC.take_note("appr_n")
    check("a long note is kept, cut to the bound", code == 200 and len(got) == TC.MAX_NOTE_CHARS)
    check("control characters are dropped", "\x1b" not in got)
    check("take_note() delivers it once", TC.take_note("appr_n") is None)
    check("a note sets no pause or stop", TC.checkpoint("appr_n") is None)
    TC.end("appr_n")


def t_the_audit_line_never_carries_the_note():
    _reset()
    lines = []
    fw = types.ModuleType("jarvis_framework")
    fw.audit_log = lambda e, d: lines.append((e, json.dumps(d)))
    old = sys.modules.get("jarvis_framework")
    sys.modules["jarvis_framework"] = fw
    try:
        TC.begin("appr_a", "control_computer")
        TC.handle_post("/api/task/note", {"note": "my PIN is 4471"})
        TC.end("appr_a")
    finally:
        if old is None:
            sys.modules.pop("jarvis_framework", None)
        else:
            sys.modules["jarvis_framework"] = old
    check("the note was audited as an event", any(e == "task.note" for e, _ in lines), repr(lines))
    check("the audit line holds its length, not its words",
          all("4471" not in d for _, d in lines), repr(lines))


def t_amend_only_attaches_to_a_card_that_is_waiting():
    _reset()
    code, out = TC.handle_post("/api/pending/appr_9/amend", {"note": "use the work address"},
                               pending_ids=lambda: {"appr_9"})
    check("a note on a waiting card is kept", code == 200 and out["kept"], repr(out))
    check("and it says nothing was approved", "Nothing was approved" in out["message"])
    code, out = TC.handle_post("/api/pending/appr_gone/amend", {"note": "x"},
                               pending_ids=lambda: {"appr_9"})
    check("a card that is not waiting is a 409", code == 409, repr(out))
    code, out = TC.handle_post("/api/pending/appr_9/amend", {"note": "x"},
                               pending_ids=lambda: None)
    check("an unreadable queue is a 503, and nothing is kept", code == 503)
    code, _ = TC.handle_post("/api/pending/appr_9/amend", {"note": ""},
                             pending_ids=lambda: {"appr_9"})
    check("an empty note is a 400", code == 400)
    code, _ = TC.handle_post("/api/pending/a%2Fb/amend", {"note": "y"},
                             pending_ids=lambda: {"a/b"})
    check("a percent-encoded id is decoded before it is looked up", code == 200)
    check("the note comes back once, for that card",
          TC.take_amend("appr_9") == "use the work address" and TC.take_amend("appr_9") is None)
    check("no route here approves, denies or touches the gate's queue",
          "jarvis_gate.decide" not in (HERE / "jarvis_task_control.py").read_text())


def t_amend_notes_are_bounded_in_number():
    _reset()
    for i in range(TC._MAX_AMENDS + 10):
        TC.amend(f"appr_{i}", "n")
    check("at most _MAX_AMENDS notes are held", len(TC._amends) == TC._MAX_AMENDS)
    check("the oldest went first", TC.take_amend("appr_0") is None
          and TC.take_amend(f"appr_{TC._MAX_AMENDS + 9}") == "n")


def _fake_turn(fake_mod, gate, *, press=None, tool_args=None):
    """Drive jarvis_agent.run_local_turn with the fake module as control_computer."""
    import jarvis_agent as AG
    sys.modules["fake_task_mod"] = fake_mod
    old_tool = AG.TOOLS["control_computer"]
    old_map = dict(AG._TASK_MODULES)
    plan = FakePlan("do three things", ["one", "two", "three"])
    AG.TOOLS["control_computer"] = AG.Tool(
        "control_computer", "fake", {"type": "object", "properties": {}},
        lambda args: (plan, fake_mod.describe(plan)),
        lambda args, state, **kw: fake_mod.run(state, approved=True,
                                               announce=kw.get("announce"),
                                               checkpoint=kw.get("checkpoint")),
        needs_announce=True, gate_lookup_name=lambda a: "jarvis_ui_control_run")
    AG._TASK_MODULES["control_computer"] = "fake_task_mod"
    calls = []
    responses = iter([
        {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "control_computer",
                                      "arguments": json.dumps(tool_args or {})}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
    ])

    def post(url, payload):
        calls.append(payload)
        return next(responses)

    class S:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=1024): return b""
    try:
        fake_mod.on_step = press
        AG.run_local_turn([{"role": "user", "content": "go"}], "m", ollama_url="http://x",
                          stream_out=lambda b: None, post=post, gate_check=gate,
                          open_stream=lambda u, p: S(), record_chain=lambda s: None)
    finally:
        AG.TOOLS["control_computer"] = old_tool
        AG._TASK_MODULES.clear(); AG._TASK_MODULES.update(old_map)
        fake_mod.on_step = None
    tool_msgs = [m for m in calls[-1]["messages"] if m.get("role") == "tool"]
    return plan, json.loads(tool_msgs[0]["content"])


def t_pause_mid_run_keeps_the_rest_for_resume():
    _reset()
    mod = FakeModule()
    gate = lambda *a: Verdict(True, "approved", "appr_live")
    plan, fed = _fake_turn(mod, gate,
                           press=lambda s: s == "one" and TC.handle_post("/api/task/pause", {}))
    check("the run stopped after the step it was on", mod.ran == ["one"], repr(mod.ran))
    check("the model was told it was paused, and not to redo it",
          fed.get("paused") is True and "paused_note" in fed, repr(fed))
    p = TC.paused()
    check("the paused task is the approval card's own id", p and p["id"] == "appr_live", repr(p))
    check("two steps are left, one is done", p["steps_left"] == 2 and p["steps_done"] == 1)
    rec = TC._paused["appr_live"]
    check("the kept plan is the ORIGINAL plan, cut down - same type, same goal",
          isinstance(rec["plan"], FakePlan) and rec["plan"].steps == ["two", "three"]
          and rec["plan"].goal == plan.goal)
    check("nothing is still registered as running", TC.running() == [])
    st, detail = TC.effective_activity("idle", "")
    check("idle now reads as paused, so the clients can offer Resume",
          st == "paused" and "2 steps not run" in detail, repr((st, detail)))
    check("any other state passes through untouched",
          TC.effective_activity("working", "x") == ("working", "x"))


def t_resume_asks_first_and_runs_only_the_rest():
    # continues from the paused state above
    mod = FakeModule()
    TC.handle_post("/api/task/note", {"note": "skip the third if it looks odd"})
    seen = []

    def gate(action, detail, prompt):
        seen.append((action, detail["text"]))
        check("nothing ran before the gate answered", mod.ran == [])
        return Verdict(True, "approved", "appr_resume")
    code, out = TC.resume("test", gate_check=gate, importer=lambda n: mod, wait=True)
    check("resume answers 202 and says nothing has run yet",
          code == 202 and "Nothing has run yet" in out["message"], repr(out))
    check("exactly one card was raised, under the ORIGINAL action's tier",
          len(seen) == 1 and seen[0][0] == "jarvis_ui_control_run", repr(seen))
    text = seen[0][1]
    check("the card lists every step that is left, in full",
          "1. two" in text and "2. three" in text and "1. one" not in text)
    check("the card says what refusing costs", "If you say no" in text)
    check("the owner's note is on the card, marked as changing nothing",
          "skip the third" in text and "changes none of the steps" in text)
    check("after approval exactly the remaining steps ran", mod.ran == ["two", "three"],
          repr(mod.ran))
    check("nothing is paused any more", TC.paused() is None)
    check("idle reads as idle again", TC.effective_activity("idle", "")[0] == "idle")
    last = TC.status()["last_resumed"]
    check("the result is reported for the status route",
          last and last["ok"] is True and last["steps_done"] == 2, repr(last))


def t_a_denied_resume_runs_nothing_and_stays_paused():
    _reset()
    mod = FakeModule()
    TC.remember_paused("appr_d", tool="control_computer", action="jarvis_ui_control_run",
                       module="fake", plan=FakePlan("g", ["a", "b"]), not_run=2, done=0)
    for outcome in ("denied", "timed_out", "refused"):
        TC.resume("t", gate_check=lambda *a, o=outcome: Verdict(False, o),
                  importer=lambda n: mod, wait=True)
        check(f"a {outcome} resume ran nothing", mod.ran == [])
    check("it is still paused, so Stop can forget it", TC.paused() is not None)
    code, out = TC.handle_post("/api/task/stop", {})
    check("stop on a paused task forgets it", code == 200 and out["forgot_paused"] == "appr_d")
    check("nothing is paused now", TC.paused() is None)


def t_a_broken_gate_fails_closed():
    _reset()
    mod = FakeModule()
    TC.remember_paused("appr_b", tool="control_computer", action="jarvis_ui_control_run",
                       module="fake", plan=FakePlan("g", ["a"]), not_run=1, done=0)

    def boom(*a):
        raise RuntimeError("gate exploded")
    # The default checker wraps jarvis_gate; exercise it with a gate module that raises.
    gm = types.ModuleType("jarvis_gate")
    gm.check = lambda *a, **k: boom()
    old = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = gm
    try:
        TC.resume("t", importer=lambda n: mod, wait=True)
    finally:
        if old is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = old
    check("a gate that raises runs nothing", mod.ran == [])


def t_stop_while_the_resume_card_waits_wins():
    _reset()
    mod = FakeModule()
    TC.remember_paused("appr_s", tool="control_computer", action="jarvis_ui_control_run",
                       module="fake", plan=FakePlan("g", ["a"]), not_run=1, done=0)

    def gate(*a):
        TC.handle_post("/api/task/stop", {})     # the owner changes their mind
        return Verdict(True, "approved")
    TC.resume("t", gate_check=gate, importer=lambda n: mod, wait=True)
    check("a Stop pressed while the card waited beats approving it", mod.ran == [])


def t_only_one_resume_card_at_a_time():
    _reset()
    TC.remember_paused("appr_o", tool="control_computer", action="jarvis_ui_control_run",
                       module="fake", plan=FakePlan("g", ["a"]), not_run=1, done=0)
    with TC._lock:
        TC._resuming["appr_o"] = {"since": 0}
    code, out = TC.handle_post("/api/task/resume", {})
    check("a second Resume while the card waits is a 409", code == 409, repr(out))
    st, detail = TC.effective_activity("idle")
    check("while the card waits, activity says so", st == "paused" and "approval" in detail)
    _reset()


def t_a_stale_pause_is_forgotten():
    _reset()
    TC.remember_paused("appr_old", tool="control_computer", action="x", module="fake",
                       plan=FakePlan("g", ["a"]), not_run=1, done=0)
    with TC._lock:
        TC._paused["appr_old"]["at"] -= TC.PAUSED_TTL_SECONDS + 1
    check("a pause older than an hour is gone", TC.paused() is None)


def t_the_card_note_reaches_the_model_with_the_answer():
    _reset()
    TC.amend("appr_card", "send it from the work account")
    mod = FakeModule()
    _, fed = _fake_turn(mod, lambda *a: Verdict(False, "denied", "appr_card"))
    check("on a denied card, the model still gets the owner's note",
          fed.get("owner_note") == "send it from the work account", repr(fed))
    check("and the denied plan did not run", mod.ran == [])
    TC.amend("appr_card2", "then close the window")
    _, fed = _fake_turn(mod, lambda *a: Verdict(True, "approved", "appr_card2"))
    check("on an approved card, it goes with the result", fed.get("owner_note") ==
          "then close the window", repr(fed))
    check("and the approved plan ran exactly as shown", mod.ran == ["one", "two", "three"])


def t_a_task_note_reaches_the_model_after_the_step():
    _reset()
    mod = FakeModule()
    _, fed = _fake_turn(mod, lambda *a: Verdict(True, "approved", "appr_tn"),
                        press=lambda s: s == "two" and TC.handle_post(
                            "/api/task/note", {"note": "after this, check the inbox"}))
    check("the note did not change a step", mod.ran == ["one", "two", "three"])
    check("the note is in the result the model reads next",
          fed.get("owner_note") == "after this, check the inbox", repr(fed))


# ---- the patch, rehearsed on the text earlier patches wrote ---------------

_MI_OLD = '                     "/api/memory/learning", "/api/memory/sleep_time"):\n'
_MI_NEW = ('                     "/api/memory/learning", "/api/memory/sleep_time",\n'
           '                     "/api/memory/keep_both"):\n')


def stack_skeleton() -> str:
    """jarvis_hud.py as the stack leaves it, at the places this patch quotes.

    _skeleton.build() gives extraction-wiring's and feedback's after-images;
    memory-intake (later in the stack) then rewrites one tuple line of
    feedback's, which is applied here by hand because its other hunks need
    text no patch quotes.
    """
    import _skeleton
    s = _skeleton.build("extraction-wiring.patch", "feedback.patch")
    assert s.count(_MI_OLD) == 1
    return s.replace(_MI_OLD, _MI_NEW)


def rehearse(patch_names, text):
    git = shutil.which("git")
    if not git:
        return None, "git is not installed"
    d = Path(tempfile.mkdtemp(prefix="jarvis-tc-"))
    try:
        with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        for name in patch_names:
            lf = d / name
            lf.write_bytes((HERE / name).read_bytes().replace(b"\r\n", b"\n"))
            inc = "--include=jarvis_hud.py"   # the stand-in is jarvis_hud.py only
            for args in (["apply", "--check", inc, str(lf)], ["apply", inc, str(lf)]):
                r = subprocess.run([git] + args, cwd=d, capture_output=True, text=True)
                if r.returncode != 0:
                    return False, f"{name}: git {args[0]} {args[1]}: {r.stderr.strip()}"
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        for name in reversed(patch_names):
            r = subprocess.run([git, "apply", "--reverse", "--include=jarvis_hud.py",
                                str(d / name)], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{name}: reverse: {r.stderr.strip()}"
        back = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        if back != text:
            return False, "reverting did not give back the starting text"
        return True, after
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_the_patch_applies_to_what_the_stack_wrote():
    ok, out = rehearse(["task-control.patch"], stack_skeleton())
    if ok is None:
        return check("SKIP - " + out, True)
    check("task-control.patch applies after feedback and memory-intake, and reverts",
          ok is True, out)
    if not ok:
        return
    check("the four task routes and amend are reached",
          '"/api/task/pause", "/api/task/resume", "/api/task/stop"' in out
          and 'route.endswith("/amend")' in out)
    check("GET /api/task is there", 'if path == "/api/task":' in out)
    i = out.index('"/api/task/note") or')
    window = out[i:i + 1400]
    check("the POST routes check the origin and the token",
          "_origin_ok(self)" in window and "_token_ok(self)" in window)
    check("the routes hand everything to jarvis_task_control.handle_post",
          "jarvis_task_control.handle_post(route, body, by=by)" in window)
    check("_activity asks jarvis_task_control first, then the original",
          "effective_activity(state, detail)" in out
          and "def _activity_as_told(state: str" in out)
    # The wrapper really works as Python: exec just the two functions.
    j = out.index("def _activity(state")
    k = out.index('"""Announce what Jarvis is doing', j)
    src = out[j:k].rstrip(" ") + '    """."""\n    TOLD.append((state, detail))\n'
    ns = {"TOLD": []}
    exec(src, ns)
    _reset()
    TC.remember_paused("appr_w", tool="t", action="a", module="m",
                       plan=FakePlan("g", ["x"]), not_run=1, done=0)
    ns["_activity"]("idle")
    ns["_activity"]("working", "Step 1/2")
    check("through the wrapper: idle becomes paused, working passes through",
          ns["TOLD"][0][0] == "paused" and ns["TOLD"][1] == ("working", "Step 1/2"),
          repr(ns["TOLD"]))
    _reset()


def t_the_script_applies_it_last_and_ships_the_module():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    body = ps1[start:ps1.index("\n)", start)]
    names = [l.strip().strip("'") for l in body.splitlines() if l.strip().startswith("'")]
    check("task-control.patch is in the script's list", "task-control.patch" in names)
    check("after feedback and memory-intake (its context is their output)",
          "task-control.patch" in names
          and names.index("task-control.patch") > names.index("memory-intake.patch"))
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    shipped = shipped[:shipped.index("$copied")]
    check("jarvis_task_control.py is copied in by the script",
          "'jarvis_task_control.py'" in shipped)


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has the task routes (task-control.patch applied)",
          '"/api/task/pause", "/api/task/resume"' in s and "def _activity_as_told(" in s)


NEW_TESTS = (t_stop_and_pause_refuse_when_nothing_runs,
             t_stop_and_pause_reach_a_running_task_without_a_card,
             t_a_signal_after_the_last_step_does_not_outlive_the_run,
             t_notes_are_bounded_and_cleaned, t_the_audit_line_never_carries_the_note,
             t_amend_only_attaches_to_a_card_that_is_waiting,
             t_amend_notes_are_bounded_in_number,
             t_pause_mid_run_keeps_the_rest_for_resume,
             t_resume_asks_first_and_runs_only_the_rest,
             t_a_denied_resume_runs_nothing_and_stays_paused,
             t_a_broken_gate_fails_closed, t_stop_while_the_resume_card_waits_wins,
             t_only_one_resume_card_at_a_time, t_a_stale_pause_is_forgotten,
             t_the_card_note_reaches_the_model_with_the_answer,
             t_a_task_note_reaches_the_model_after_the_step,
             t_the_patch_applies_to_what_the_stack_wrote,
             t_the_script_applies_it_last_and_ships_the_module,
             t_the_real_file)

if __name__ == "__main__":
    for fn in (t_no_signal_by_default, t_none_task_id_never_raises,
               t_request_rejects_unknown_actions, t_stop_is_read_back,
               t_pause_is_read_back, t_clear_removes_the_signal,
               t_clear_is_safe_on_an_id_with_no_signal,
               t_a_later_request_replaces_an_earlier_one,
               t_signals_are_per_task, t_note_is_queued_and_read_back,
               t_note_does_not_set_a_pause_or_stop_signal,
               t_checkpoint_consumes_the_signal,
               t_a_continued_task_does_not_pause_again,
               t_a_spent_stop_does_not_stop_the_next_task,
               t_peek_does_not_consume, t_peek_of_none_never_raises,
               t_clear_still_cancels_a_signal_nothing_took) + NEW_TESTS:
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
