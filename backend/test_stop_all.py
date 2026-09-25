"""test_stop_all.py - "Stop everything" (jarvis_stop_all.py, stop-all.patch).

    python3 backend/test_stop_all.py

The owner's decision of 2026-09-25 (CLAUDE.md, after the "Build Your Own
Jarvis" prompt pack): one hotkey on the desktop - and one button on the
phone - that halts whatever Jarvis is doing at once.

What is proved here, with no owner's files and no network:

  * it stops a fake running action: a plan running step by step stops
    before its next step, and a paused one is forgotten;
  * in the chat loop: a tool call made after the press is refused before
    the gate and never runs; one whose card was approved AFTER the press
    does not run either; a running plan's checkpoint reads "stop"; the next
    question is not affected;
  * registered stoppers (focus sessions will be one) are all called, one
    that raises does not stop the others, and it says what each stopped;
  * the route needs the token (and the origin check) - with neither, it
    stops nothing;
  * it never approves, denies, resumes or starts anything, and needs no
    event stream;
  * the audit line holds counts only, never a stopper's words;
  * stop-all.patch in the whole stack's stand-in: installed before anything
    listens, after owner-check; /api/version's capabilities.stop_all.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_stop_all.py", "jarvis_task_control.py", "jarvis_agent.py",
                "rebuilt/jarvis_events.py")

import jarvis_stop_all as SA  # noqa: E402
import jarvis_task_control as TC  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import _ollama_wire as W  # noqa: E402
import _stack  # noqa: E402

AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

PASSED, FAILED = [], []
TOKEN = "stop-all-test-token"       # a stand-in, not key-shaped


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def fresh():
    SA._reset_for_tests()
    with TC._lock:
        TC._running.clear()
        TC._paused.clear()
        TC._signals.clear()
        TC._notes.clear()
        TC._resuming.clear()


class _NoGate(types.ModuleType):
    """A jarvis_gate that fails the test if anything asks it anything."""

    def __init__(self):
        super().__init__("jarvis_gate")
        self.asked = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def refuse(*a, **k):
            self.asked.append(name)
            raise AssertionError(f"jarvis_gate.{name} was called")
        return refuse


# ------------------------------------------------------------ the module --

def t_nothing_running():
    fresh()
    out = SA.stop_all("this PC", task_control=TC)
    check("nothing running: ok, and it says so plainly",
          out["ok"] is True and out["stopped"] == [] and out["message"] == SA.NOTHING, out)


def t_it_stops_a_fake_running_action():
    fresh()
    TC.begin("task_a", "control_computer")
    ran, ended = [], {}

    def run():
        for step in range(200):
            sig = TC.checkpoint("task_a")
            if sig:
                ended["by"] = sig
                return
            ran.append(step)
            time.sleep(0.01)
        ended["by"] = "finished"

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.05)
    out = SA.stop_all("this PC", task_control=TC)
    t.join(5)
    TC.end("task_a")
    check("a running plan stops before its next step", ended.get("by") == "stop", ended)
    check("long before it would have finished", len(ran) < 150, len(ran))
    check("and the answer says what stopped, in plain words",
          any("computer control" in s and "before its next step" in s for s in out["stopped"]),
          out)
    fresh()
    TC.remember_paused("task_p", tool="control_phone", action="adb_control",
                       module="jarvis_android_control", plan=None, not_run=2, done=1)
    out = SA.stop_all("another device", task_control=TC)
    check("a paused task is forgotten", TC.paused() is None
          and any("paused task was forgotten" in s for s in out["stopped"]), out)
    code, _body = TC.resume("x", gate_check=lambda *a: None, wait=True)
    check("so Resume has nothing to resume", code == 409)


def t_stoppers():
    fresh()
    said = []
    SA.register("focus", lambda: said.append("focus") or "The focus session ended.")
    SA.register("quiet", lambda: None)
    SA.register("broken", lambda: 1 / 0)
    SA.register("late", lambda: said.append("late") or "The countdown was stopped.")
    out = SA.stop_all("this PC", task_control=TC)
    check("every stopper is called, in turn", said == ["focus", "late"], said)
    check("each one's sentence is reported", "The focus session ended." in out["stopped"]
          and "The countdown was stopped." in out["stopped"], out)
    check("one with nothing running says nothing", len(out["stopped"]) == 2, out)
    check("one that raises is named, and did not stop the others",
          any("broken could not be stopped" in p for p in out["problems"]), out)
    check("the message starts 'Stopped everything.'", out["message"].startswith(
        "Stopped everything."), out["message"])
    SA.unregister("focus")
    SA.unregister("not-there")
    check("unregister removes one, and a missing one is not an error",
          SA.registered() == ["broken", "late", "quiet"], SA.registered())
    SA.register("late", lambda: "x" * 500)
    out = SA.stop_all("this PC", task_control=TC)
    check("a stopper's words are kept to one sentence's length",
          all(len(s) <= SA.MAX_SAID for s in out["stopped"]), out)
    for bad in ((" ", lambda: None), ("ok", "not callable")):
        try:
            SA.register(*bad)
            check(f"register refuses {bad[0]!r}", False)
        except (ValueError, TypeError):
            check(f"register refuses {bad[0]!r}", True)


def t_the_latch():
    fresh()
    mark = SA.begin_turn()
    check("before the press: not stopped", SA.stopped_since(mark) is False)
    out = SA.stop_all("this PC", task_control=TC)
    check("after it: stopped", SA.stopped_since(mark) is True)
    check("the answer being written is named", any("uses no more tools" in s
                                                  for s in out["stopped"]), out)
    SA.end_turn()
    later = SA.begin_turn()
    check("the next answer is not stopped", SA.stopped_since(later) is False)
    SA.end_turn()
    check("a caller without a mark is never stopped",
          SA.stopped_since(None) is False and SA.stopped_since(True) is False)


def t_audit_holds_counts_only():
    fresh()
    got = []
    fake = types.ModuleType("jarvis_framework")
    fake.audit_log = lambda event, detail=None: got.append((event, detail)) or True
    saved = sys.modules.get("jarvis_framework")
    sys.modules["jarvis_framework"] = fake
    try:
        SA.register("focus", lambda: "Instagram-was-in-front")
        SA.stop_all("this PC", task_control=TC)
    finally:
        if saved is None:
            sys.modules.pop("jarvis_framework", None)
        else:
            sys.modules["jarvis_framework"] = saved
    check("one audit line", [e for e, _d in got] == ["stop_all"], got)
    check("with counts, never a stopper's words",
          "Instagram" not in json.dumps(got) and got[0][1]["stopped"] == 1, got)


def t_never_approves_or_starts_anything():
    fresh()
    gate = _NoGate()
    saved = {k: sys.modules.get(k) for k in ("jarvis_gate", "jarvis_events")}
    sys.modules["jarvis_gate"] = gate
    sys.modules["jarvis_events"] = None          # no event stream at all
    real_resume = TC.resume
    TC.resume = lambda *a, **k: (_ for _ in ()).throw(AssertionError("resume was called"))
    try:
        TC.begin("task_b", "browser_control")
        TC.remember_paused("task_c", tool="control_phone", action="adb_control",
                           module="jarvis_android_control", plan=None, not_run=1, done=0)
        out = SA.stop_all("this PC", task_control=TC)
    finally:
        TC.resume = real_resume
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        TC.end("task_b")
    check("the gate is never asked anything (no approve, no deny)", gate.asked == [], gate.asked)
    check("nothing is resumed or started", out["ok"] is True)
    check("and it works with no event stream at all", len(out["stopped"]) == 2, out)
    src = (HERE / "jarvis_stop_all.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    body = code.split('"""', 2)[2]      # past the module docstring
    for word in ("approve(", "decide(", "deny(", "resume(", ".start()", "stale"):
        check(f"the module's code never calls {word!r}", word not in body)


# ------------------------------------------------------- the chat loop --

def _calls(*names):
    return [{"id": str(i), "name": n, "arguments": json.dumps(a)}
            for i, (n, a) in enumerate(names)]


def _opener(rounds):
    sent = []
    it = iter(rounds)

    def opener(url, payload):
        sent.append(payload)
        return W.FakeResponse(W.stream(next(it)))
    return opener, sent


def _turn(rounds, gate, *, enabled=None):
    opener, sent = _opener(rounds)
    streamed = []
    AG.run_local_turn([{"role": "user", "content": "go"}], "m",
                      ollama_url="http://127.0.0.1:11434", stream_out=streamed.append,
                      gate_check=gate, open_stream=opener, enabled_tools=enabled,
                      record_chain=lambda s: None, context_length=8192,
                      request={"messages": [{"role": "user", "content": "go",
                                             "provenance": "typed"}]})
    return sent, b"".join(streamed).decode("utf-8", "replace")


def _ok(*_a, **_k):
    return types.SimpleNamespace(allowed=True, tier="ask", action="x", reason="approved",
                                 outcome="approved", request_id=None)


def t_a_tool_call_after_the_press_never_runs():
    fresh()
    ran, asked = [], []
    tool = AG.TOOLS["calculator"]
    real = tool.execute

    def execute(args, state, **kw):
        ran.append(args.get("expression"))
        if len(ran) == 1:
            SA.stop_all("this PC", task_control=TC)     # pressed while it runs
        return {"ok": True, "value": 2}
    tool.execute = execute

    def gate(*a):
        asked.append(a[0])
        return _ok()
    try:
        rounds = [
            [("tool_calls", _calls(("calculator", {"expression": "1+1"}),
                                   ("calculator", {"expression": "2+2"})))],
            [("tool_calls", _calls(("calculator", {"expression": "3+3"})))],
            [("content", "Stopped."), ("done", "stop")],
        ]
        sent, said = _turn(rounds, gate, enabled={"calculator"})
    finally:
        tool.execute = real
    check("the call made before the press ran; none after it", ran == ["1+1"], ran)
    check("the gate was asked once - the refused calls reached nobody", len(asked) <= 1, asked)
    told = [m for m in sent[-1]["messages"] if m.get("role") == "tool"]
    check("the model is told it was stopped, and not to try again",
          sum(1 for m in told if "Stop everything" in m["content"]) == 2, told)
    check("the owner is told once, in the answer", said.count("you pressed Stop everything") == 1,
          said[-400:])


def t_an_approval_after_the_press_does_not_run():
    fresh()
    ran = []
    tool = AG.TOOLS["shell_exec"]
    real_p, real_e = tool.prepare, tool.execute
    tool.prepare = lambda args: (None, "  1. run: echo hi")
    tool.execute = lambda args, state, **kw: ran.append(1) or {"ok": True}

    def gate(*a):
        SA.stop_all("this PC", task_control=TC)          # pressed while the card waits
        return _ok()                                      # ... and then the card is approved
    try:
        rounds = [[("tool_calls", _calls(("shell_exec", {"command": "echo hi"})))],
                  [("content", "ok"), ("done", "stop")]]
        sent, said = _turn(rounds, gate, enabled={"shell_exec"})
    finally:
        tool.prepare, tool.execute = real_p, real_e
    check("a card approved after the press: what it asked for does not run", ran == [], ran)
    check("and the model is told why", any("Stop everything" in m.get("content", "")
                                           for m in sent[-1]["messages"]), sent[-1]["messages"])


def t_a_running_plan_reads_stop_at_its_checkpoint():
    fresh()
    seen = []
    tool = AG.TOOLS["control_computer"]
    real_p, real_e = tool.prepare, tool.execute
    tool.prepare = lambda args: (types.SimpleNamespace(steps=[1, 2, 3, 4]), "  1. click")

    def execute(args, state, **kw):
        cp = kw.get("checkpoint")
        for step in range(4):
            sig = cp() if cp else None
            seen.append(sig)
            if sig:
                return {"ok": False, "stopped": True, "done": [0] * step}
            if step == 1:
                SA.stop_all("this PC", task_control=TC)
        return {"ok": True}
    tool.execute = execute
    try:
        args = {"goal": "x", "window": "Notepad",
                "requests": [{"control": "Edit", "action": "read"}]}
        rounds = [[("tool_calls", _calls(("control_computer", args)))],
                  [("content", "ok"), ("done", "stop")]]
        _turn(rounds, _ok, enabled={"control_computer"})
    finally:
        tool.prepare, tool.execute = real_p, real_e
    check("the plan's checkpoint says 'stop' at the step after the press",
          seen == [None, None, "stop"], seen)
    check("and the task is no longer listed as running", TC.running() == [])


def t_the_next_question_is_not_affected():
    fresh()
    SA.stop_all("this PC", task_control=TC)
    ran = []
    tool = AG.TOOLS["calculator"]
    real = tool.execute
    tool.execute = lambda args, state, **kw: ran.append(1) or {"ok": True, "value": 2}
    try:
        rounds = [[("tool_calls", _calls(("calculator", {"expression": "1+1"})))],
                  [("content", "2"), ("done", "stop")]]
        _turn(rounds, _ok, enabled={"calculator"})
    finally:
        tool.execute = real
    check("a question asked after the press uses its tools normally", ran == [1], ran)


# ------------------------------------------------------------ the route --

class FakeHandler:
    def __init__(self, path, headers):
        self.path = path
        self.headers = headers
        self.client_address = ("127.0.0.1", 50000)
        self.sent = None
        self.original = False

    def do_POST(self):
        self.original = True

    def _send(self, code, body):
        self.sent = (code, body)


def _install():
    class H(FakeHandler):
        pass
    banner = SA.install(H, origin_ok=lambda h: h.headers.get("Origin") != "http://evil.example",
                        token_ok=lambda h: h.headers.get("X-Jarvis-Token") == TOKEN,
                        read_body=lambda h: b"{}")
    return H, banner


def t_the_route():
    fresh()
    H, banner = _install()
    check("install says so on the banner", "/api/stop_all" in banner and SA.armed())
    before = SA.generation()
    h = H("/api/stop_all", {})
    h.do_POST()
    check("no token: 401, and nothing was stopped",
          h.sent and h.sent[0] == 401 and SA.generation() == before, h.sent)
    h = H("/api/stop_all", {"X-Jarvis-Token": TOKEN, "Origin": "http://evil.example"})
    h.do_POST()
    check("another website's page: 403, nothing stopped",
          h.sent[0] == 403 and SA.generation() == before, h.sent)
    h = H("/api/stop_all", {"X-Jarvis-Token": TOKEN})
    h.do_POST()
    check("with the token: 200 and the plain answer",
          h.sent[0] == 200 and h.sent[1]["ok"] is True and "message" in h.sent[1], h.sent)
    check("and it stopped (the latch moved)", SA.generation() == before + 1)
    h = H("/api/task/stop", {"X-Jarvis-Token": TOKEN})
    h.do_POST()
    check("every other route goes to the server's own handler", h.original and h.sent is None)
    h = H("/api/stop_all/", {"X-Jarvis-Token": TOKEN})
    h.do_POST()
    check("a trailing slash is the same route", h.sent and h.sent[0] == 200)
    banner2 = SA.install(H, origin_ok=lambda h: True, token_ok=lambda h: True)
    check("installing twice does not wrap twice", "already on" in banner2)


def t_the_patch_in_the_stack():
    text, log = _stack.stand_in("jarvis_hud.py")
    if text is None:
        check("the server's stand-in builds", False, log)
        return
    check("stop-all.patch needed none of the owner's lines it had not already seen",
          not [l for l in log if l.startswith("stop-all.patch")], log)
    i = text.find("jarvis_stop_all.install(Handler")
    j = text.find("_loopback_companion(bind, HUD_PORT, Handler)\n    print(")
    k = text.find("jarvis_owner_check.install(Handler")
    check("install() is called before anything listens, after owner-check", -1 < k < i < j,
          (k, i, j))
    call = text[i:i + 200]
    check("with the server's own origin and token checks",
          "origin_ok=_origin_ok" in call and "token_ok=_token_ok" in call, call)
    check("a missing module is said on the banner", "Stop everything cannot reach" in text)
    order = _stack.order()
    check("stop-all.patch is applied, after owner-check.patch",
          "stop-all.patch" in order and order.index("owner-check.patch")
          < order.index("stop-all.patch"))


def t_the_handshake():
    try:
        import jarvis_events as E
    except ImportError:
        sys.path.append(str(HERE / "rebuilt"))
        import jarvis_events as E
    SA._ARMED = False
    check("not installed: capabilities.stop_all is false", E._capability_probe()["stop_all"] is False)
    SA._ARMED = True
    try:
        check("installed: true", E._capability_probe()["stop_all"] is True)
    finally:
        SA._ARMED = False
    hello = E.hello("hud")
    check("/api/version says when the server started (for the preflight)",
          isinstance(hello.get("started"), float) and hello["started"] <= time.time())


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception as exc:
                import traceback
                traceback.print_exc()
                check(f"{name} raised {type(exc).__name__}: {exc}", False)
    fresh()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
