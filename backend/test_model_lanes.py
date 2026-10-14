"""test_model_lanes.py - the button that starts the model lane that is down.

    python3 backend/test_model_lanes.py

WHAT THIS IS FOR. On 2026-10-13 both of the owner's Ollama lanes died at about
16:30 and nothing said so for about five hours. PR #409 made both apps say it on
a standing line, and deliberately made that line DO NOTHING. The owner then
decided it should offer one action, and `backend/jarvis_model_lanes.py` is the
backend half of it.

The failure this suite exists to make impossible is named in that module's own
header and in the brief that asked for it: **a button that reports success and
changes nothing.** Starting a Windows task returns long before a model is
loaded, and it is entirely possible to start the task, have the lane never come
up, and tell the owner it worked. So every check below is about what is CLAIMED
against what is TRUE:

  * only a lane that does not answer is started, and it is started by HIS OWN
    task - the name looked up on this PC, matched by the stable half (the card
    in brackets is the half that changed under the 2026-10-10 accident);
  * nothing is started twice - not while the lane answers, not while a start is
    still being watched, not while the PC's own Task Scheduler says that task is
    already running;
  * "starting" is never "up": the lane answering `/api/tags` is the ONLY thing
    that turns it into `up`, and a start that never comes up settles as `down`
    with a plain sentence and LEAVES THE WARNING STANDING;
  * the lane that is started is the lane the CHAT uses (`OLLAMA_URL`'s port),
    never a guessed one and never both;
  * a task name that is not on this PC is refused in words, and NOTHING is run -
    a command naming a task that does not exist is exactly the 2026-10-10
    accident this project already paid for.

NOTHING HERE TOUCHES THE OWNER'S PC, and that is a rule rather than a hope. His
everyday lane is running while this is written and he needs it. Every check
below injects its own `probe_fn`, `run_fn`, `tasks_fn` and `running_fn`, so no
socket is opened to a real lane, no `schtasks` runs, and no task is started or
stopped. `t_nothing_real_is_ever_run` reads the module's own source and proves
the real functions cannot be reached from a test run: the suite would fail if
someone removed the seams.

Standard library only. No network beyond 127.0.0.1 (and none at all: the one
check that uses a real socket uses a throwaway one this file opened).
"""
from __future__ import annotations

import ast
import io
import json
import socket
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_model_lanes.py")
import jarvis_model_lanes as L  # noqa: E402

PASSED, FAILED = [], []

#: The two task names this PC really has (tools/check_lanes.py carries the same
#: two, and test_lanes.py pins them there). The card in brackets is the half
#: that changed under the 2026-10-10 accident and is deliberately NOT what the
#: lookup matches on.
REAL_TASKS = ("Jarvis Ollama - Everyday model (RTX 2060)",
              "Jarvis Ollama - Coding model (RTX 2080 Super)")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Up:
    """A stand-in for a lane that IS answering, and remembers being asked."""

    def __init__(self, up=True):
        self.up = up
        self.asked = []

    def __call__(self, port, timeout=None):
        self.asked.append(port)
        return self.up


class Runner:
    """A stand-in for the ONE action - starting the lane's own task - recording
    every task name it was asked to start.

    STRICT about what it is handed, deliberately: the real launcher turns the
    name into `["schtasks", "/run", "/tn", <name>]` and the tests below check
    that shape for real (through `_run`), so this seam only has to be honest
    about the one thing `start()` passes it - the task's NAME, never a command
    line and never a list of characters. A stand-in that accepted anything
    would let a launcher that ran nothing look like it worked.
    """

    def __init__(self, result=0):
        self.calls = []
        self.result = result

    def __call__(self, task, timeout=None):
        if not isinstance(task, str) or not task:
            raise AssertionError(
                f"the launcher was handed {type(task).__name__} {task!r}, not a "
                f"task name - start() hands it the name and the launcher builds "
                f"the command")
        self.calls.append(task)
        return self.result, b""


def clean():
    L.reset()


# ---------------------------------------------------------------------------
#   Which lane, and how it is found
# ---------------------------------------------------------------------------

def t_the_lane_is_the_one_the_chat_uses():
    """`OLLAMA_URL`'s port decides, so the lane started is the lane Jarvis
    would talk to. The owner's is 11436, not Ollama's own 11434."""
    check("the owner's everyday address is his everyday lane",
          L.target(url="http://127.0.0.1:11436").key == "everyday")
    check("... and the coding lane's address is the coding lane",
          L.target(url="http://127.0.0.1:11435").key == "coding")
    check("a bare loopback address means Ollama's own default, which is no lane "
          "this PC starts", L.target(url="http://127.0.0.1") is None)
    check("an address on another machine is no lane here at all",
          L.target(url="http://192.168.1.50:11436") is None)
    check("... and so is nonsense", L.target(url="not a url") is None)


def t_the_task_is_found_by_the_half_a_rename_does_not_touch():
    lane = L.LANES[0]
    check("the real task is found",
          L.task_for(lane, REAL_TASKS) == REAL_TASKS[0], L.task_for(lane, REAL_TASKS))
    check("a task renamed to another card is still followed",
          L.task_for(lane, ("Jarvis Ollama - Everyday model (RTX 5090)",))
          == "Jarvis Ollama - Everyday model (RTX 5090)")
    check("a task list with no such name finds NOTHING - there is no fallback "
          "name to type from memory", L.task_for(lane, ("Some Other Task",)) == "")
    check("with no task list at all, still nothing", L.task_for(lane, ()) == "")


def t_the_lane_table_matches_the_read_only_checker():
    """One table, two readers: this module and `tools/check_lanes.py`, the
    read-only tool that has printed the fix since 2026-10-10. They must not
    drift about which port a lane is on or which task starts it - the whole
    2026-10-10 accident was two places disagreeing about a task name."""
    tool = (REPO / "tools" / "check_lanes.py").read_text(encoding="utf-8")
    for lane in L.LANES:
        check(f"tools/check_lanes.py starts {lane.key} on port {lane.port}",
              f"{lane.port}" in tool, f"{lane.port} is not in the tool")
        check(f"... and looks for a task starting {lane.task_prefix!r}",
              lane.task_prefix in tool, lane.task_prefix)
    check("... and both know the owner's two task names end in the cards his PC "
          "really has",
          "(RTX 2060)" in tool and "(RTX 2080 Super)" in tool)


# ---------------------------------------------------------------------------
#   Direction 1: a lane that is DOWN offers exactly one action
# ---------------------------------------------------------------------------

def t_a_down_lane_can_be_started_and_runs_his_own_task():
    clean()
    lane = L.LANES[0]
    probe, runner = Up(up=False), Runner()
    code, out = L.start(lane, probe_fn=probe, run_fn=runner,
                        tasks_fn=lambda: REAL_TASKS, running_fn=lambda name: False,
                        watch=False)
    check("a down lane answers 202 ('starting'), not 200", code == 202,
          f"{code} {out}")
    check("... and it really started a task, exactly once", len(runner.calls) == 1,
          runner.calls)
    check("... and that task is HIS OWN, the name this PC has",
          runner.calls == [REAL_TASKS[0]], runner.calls)
    check("... and the state it reports is 'starting', never 'up'",
          out.get("state") == "starting" and out.get("changed") is True, out)
    check("... and it names the task it started on the PC's own rows, so the "
          "app can say which one it used",
          out.get("task") in ("", REAL_TASKS[0]), out.get("task"))
    check("... and it says out loud that it is waiting for the lane",
          "Waiting for it to answer" in str(out.get("message")), out.get("message"))


def t_the_command_it_really_runs_is_schtasks_run_with_that_task_name():
    """The seam above proves WHICH task; this proves the COMMAND - the real
    `_launch_task`, with only `_run` replaced, so the argv is the argv the PC
    would be given. `schtasks /run /tn "<name>"`, as argv, never a shell."""
    seen = []

    def fake_run(argv, timeout):
        seen.append((list(argv), timeout))
        return 0, b""

    real_run, L._run = L._run, fake_run
    try:
        code, _out = L._launch_task(REAL_TASKS[0])
    finally:
        L._run = real_run
    check("the launcher runs exactly one program, and it is schtasks",
          len(seen) == 1 and seen[0][0][0] == "schtasks", seen)
    check("... with /run /tn and the task name as SEPARATE argv words - a task "
          "name spelled out as characters would run nothing",
          seen and seen[0][0] == ["schtasks", "/run", "/tn", REAL_TASKS[0]], seen)
    check("... and one unbroken task name, not a list of characters",
          seen and isinstance(seen[0][0][-1], str)
          and seen[0][0][-1] == REAL_TASKS[0], seen)
    check("... and the call's own exit code is what is reported",
          code == 0, code)
    check("... and it never asks for a shell",
          "shell=True" not in (HERE / "jarvis_model_lanes.py").read_text(encoding="utf-8"))


def t_a_lane_that_is_up_is_never_started():
    clean()
    lane = L.LANES[0]
    probe, runner = Up(up=True), Runner()
    code, out = L.start(lane, probe_fn=probe, run_fn=runner,
                        tasks_fn=lambda: REAL_TASKS, running_fn=lambda name: False,
                        watch=False)
    check("a lane that answers answers 200 and starts NOTHING",
          code == 200 and runner.calls == [], (code, runner.calls))
    check("... and says so plainly",
          out.get("changed") is False and "already answering" in str(out.get("message")),
          out)


def t_a_start_that_never_comes_up_leaves_the_warning_standing():
    """THE CHECK THIS FILE EXISTS FOR. The task is started, the lane never
    answers, and the module must say `down` - not `up`, not "starting" for
    ever."""
    clean()
    lane = L.LANES[0]
    tasks = lambda: REAL_TASKS  # noqa: E731 - the stand-in task list
    # A real start's own sequence: state armed, then watched until it settles.
    L._begin(lane, REAL_TASKS[0], 1000.0, running=False)
    slept = []
    watch = L._watch(lane, Up(up=False),
                     now=1000.0,
                     sleep=lambda s: slept.append(s),
                     deadline_s=L.POLL_S * 3)
    check("a watch that times out settles as 'down'", watch.get("phase") == "down",
          watch)
    check("... and it says in plain words that the lane did not come up",
          "did not come up" in str(watch.get("message")), watch.get("message"))
    check("... and never claims it is up anywhere in the sentence",
          "is answering" not in str(watch.get("message")), watch.get("message"))
    check("... and it really waited, rather than giving up at once",
          len(slept) >= 3 and all(s == L.POLL_S for s in slept), slept)

    # A REAL clock, because how long ago the start was asked for is what
    # decides this: the state was just settled, so a second press is refused.
    L._begin(lane, REAL_TASKS[0], time.time(), running=False)
    L._finish(False, time.time(),
              "The lane did not answer within 9 seconds of its task being "
              "started, so it did not come up. It is still down.")
    state = L.status(lane, probe_fn=Up(up=False), tasks_fn=tasks)
    check("... and the status the apps read says 'down' too",
          state.get("state") == "down", state)
    check("... and it will not start that task again straight away",
          state.get("can_start") is False
          and "not be started again" in str(state.get("why")), state)


def t_a_start_that_DOES_come_up_says_how_long_it_took():
    clean()
    lane = L.LANES[0]
    answers = {"n": 0}

    def probe_once(port, timeout=None):
        answers["n"] += 1
        return answers["n"] >= 2          # answers on the second ask

    # The state a real start leaves behind before it arms the watch.
    L._begin(lane, REAL_TASKS[0], 1000.0, running=False)
    watch = L._watch(lane, probe_once, now=1000.0, sleep=lambda s: None,
                     deadline_s=L.POLL_S * 5)
    check("a watch whose lane comes back settles as 'up'", watch.get("phase") == "up",
          watch)
    check("... and says the model is answering again",
          "answering again" in str(watch.get("message")), watch.get("message"))
    check("... and remembers how long it waited",
          isinstance(watch.get("waited_s"), float) and watch["waited_s"] > 0,
          watch.get("waited_s"))
    check("... and the status the apps read says 'up' and offers no press",
          L.status(lane, probe_fn=Up(up=True), window=False)["can_start"] is False,
          L.status(lane, probe_fn=Up(up=True), window=False))
    clean()


# ---------------------------------------------------------------------------
#   Direction 2: never a second task
# ---------------------------------------------------------------------------

def t_a_task_the_pc_says_is_running_is_not_started_again():
    clean()
    lane = L.LANES[0]
    probe, runner = Up(up=False), Runner()
    code, out = L.start(lane, probe_fn=probe, run_fn=runner,
                        tasks_fn=lambda: REAL_TASKS, running_fn=lambda name: True,
                        watch=False)
    check("a task the Task Scheduler says is running is NOT started again",
          runner.calls == [], runner.calls)
    check("... and the answer is 202 'waiting', not a refusal",
          code == 202 and out.get("waiting") is True, (code, out))
    check("... and it says why in plain words",
          "already running" in str(out.get("message")), out.get("message"))


def t_a_second_press_while_the_first_is_watched_starts_nothing():
    clean()
    lane = L.LANES[0]
    probe, runner = Up(up=False), Runner()
    tasks, running = (lambda: REAL_TASKS), (lambda name: False)
    code1, out1 = L.start(lane, probe_fn=probe, run_fn=runner,
                          tasks_fn=tasks, running_fn=running, watch=False)
    check("the first press starts it", code1 == 202 and len(runner.calls) == 1,
          (code1, runner.calls))
    # Put the module back into the state a real start leaves behind (a watched
    # one, which the real `start` arms before it returns).
    L._begin(lane, REAL_TASKS[0], __import__("time").time(), running=False)
    code2, out2 = L.start(lane, probe_fn=probe, run_fn=runner,
                          tasks_fn=tasks, running_fn=running, watch=False)
    check("a second press while that one is still being watched starts NOTHING",
          len(runner.calls) == 1, runner.calls)
    check("... and is refused with the reason, as a 409",
          code2 == 409 and "second time" in str(out2.get("error")), (code2, out2))
    clean()


def t_a_task_that_is_not_on_this_pc_is_refused_and_nothing_runs():
    """The shape of 2026-10-10: a command naming a task that is not there."""
    clean()
    lane = L.LANES[0]
    probe, runner = Up(up=False), Runner()
    code, out = L.start(lane, probe_fn=probe, run_fn=runner,
                        tasks_fn=lambda: ("Some Other Program's Task",),
                        running_fn=lambda name: False, watch=False)
    check("with no such task the answer is a refusal, not a start",
          code == 409 and out.get("ok") is False, (code, out))
    check("... and schtasks was NEVER run", runner.calls == [], runner.calls)
    check("... and the sentence names the half of the name it looked for",
          lane.task_prefix in str(out.get("error")), out.get("error"))


def t_the_pc_refusing_to_start_it_is_reported_honestly():
    clean()
    lane = L.LANES[0]
    probe, runner = Up(up=False), Runner(result=1)
    code, out = L.start(lane, probe_fn=probe, run_fn=runner,
                        tasks_fn=lambda: REAL_TASKS, running_fn=lambda name: False,
                        watch=False)
    check("schtasks failing is a 502, not a cheerful success",
          code == 502 and out.get("ok") is False, (code, out))
    check("... and it says the lane is still down",
          "still down" in str(out.get("error")), out.get("error"))


# ---------------------------------------------------------------------------
#   What the apps read
# ---------------------------------------------------------------------------

def t_the_status_never_says_up_from_anything_but_the_lane():
    clean()
    lane = L.LANES[0]
    tasks = lambda: REAL_TASKS  # noqa: E731 - the stand-in task list
    down = L.status(lane, probe_fn=Up(up=False), tasks_fn=tasks)
    check("a lane that does not answer reads 'down'", down["state"] == "down", down)
    check("... and it offers the press", down["can_start"] is True, down)
    up = L.status(lane, probe_fn=Up(up=True), tasks_fn=tasks)
    check("a lane that answers reads 'up' and offers no press",
          up["state"] == "up" and up["can_start"] is False, up)
    check("... and never mentions starting anything",
          "start" not in str(up.get("why")).lower(), up.get("why"))
    # The task list is what stands between a press and nothing: a PC with no
    # such task offers no button, and says why.
    none = L.status(lane, probe_fn=Up(up=False), tasks_fn=lambda: ())
    check("a PC with no such task offers NO press, and says why",
          none["can_start"] is False and "no scheduled task" in none["why"], none)


def t_the_lane_that_is_up_is_the_only_thing_that_clears_the_warning():
    """`false` and "the PC did not say" are different, on the phone as well as
    here (PR #409's rule). This module must never turn unknown into down."""
    clean()
    lane = L.LANES[0]
    known = L.status(lane, probe_fn=Up(up=False), tasks_fn=lambda: REAL_TASKS)
    check("a real down lane can be started", known["can_start"] is True, known)
    # `target()` is what says "Jarvis is not pointed at a lane here", and that
    # is a `down` with no press - never an invented lane.
    none = L.status(None, probe_fn=Up(up=False), window=False)
    check("no target lane is 'down' with no press and a reason",
          none["state"] == "down" and none["can_start"] is False
          and "not pointed at" in none["why"], none)


def t_the_routes_answer_what_they_promise():
    clean()
    body = L.handle_get()
    check("GET /api/model-lanes answers a dict with a state and a message",
          isinstance(body, dict) and body.get("state") in L.PHASES
          and "message" in body, body)
    check("... and says whether a press would do anything",
          "can_start" in body and "why" in body, body)
    check("POST with an empty body is accepted (starts the chat's lane)",
          L.handle_post({})[0] in (200, 202, 409, 502), L.handle_post({})[0])
    code, out = L.handle_post({"lane": "coding"})
    check("POST refuses to start a lane the chat is not on",
          code == 400 and out.get("ok") is False, (code, out))
    code, out = L.handle_post({"all": True})
    check("... and refuses 'start both' outright: there is no bulk action here",
          code == 400, (code, out))
    code, out = L.handle_post("not an object")
    check("... and a body that is not an object", code == 400, (code, out))


def t_the_probe_is_strict_about_what_a_lane_is():
    """A real socket, on a throwaway port this file owns: "something is
    listening" is not "a lane came back"."""
    class Handler(BaseHTTPRequestHandler):
        body, status, ctype = b'{"models":[]}', 200, "application/json"

        def do_GET(self):                                   # noqa: N802
            self.send_response(self.status)
            self.send_header("Content-Type", self.ctype)
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            self.wfile.write(self.body)

        def log_message(self, *args):                       # keep output clean
            pass

    def serve(body, status, ctype="application/json"):
        handler = type("H", (Handler,), {"body": body, "status": status,
                                         "ctype": ctype})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, server.server_address[1]

    def closed_port():
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    check("a port nothing is listening on is NOT up", L.probe(closed_port()) is False)
    for label, body, status in (("an HTTP error", b'{"error":"nope"}', 500),
                                ("junk", b"this is not json at all", 200),
                                ("JSON that is not Ollama's", b'{"hello":1}', 200)):
        server, port = serve(body, status)
        try:
            check(f"a port answering {label} is NOT a lane that came back",
                  L.probe(port) is False)
        finally:
            server.shutdown()
            server.server_close()
    server, port = serve(b'{"models":[]}', 200)
    try:
        check("... and a real Ollama answer IS up", L.probe(port) is True)
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
#   The one thing this module must never be able to do from a test
# ---------------------------------------------------------------------------

def t_nothing_real_is_ever_run_by_this_suite():
    """Every check above injects its own seams, so no task is started and no
    lane is probed. That is a property of the SOURCE, so it is checked there:
    the real `probe`, `_launch_task`, `scheduled_tasks` and `task_running` must
    be reachable only through a default argument, never called at import time
    and never called on a path a test cannot replace."""
    text = (HERE / "jarvis_model_lanes.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    # Only the module's TOP level: a call inside a `def` runs when the function
    # runs, which is the whole point of the seams. A call out here would run at
    # import - which is what a backend does at start-up, on the owner's PC.
    top_calls = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                fn = child.func
                top_calls.append(getattr(fn, "id", None) or getattr(fn, "attr", None))
    check("the module calls none of its own real actions at import time",
          not any(name in top_calls
                  for name in ("_launch_task", "scheduled_tasks", "task_running",
                               "probe", "start")),
          sorted(set(top_calls)))
    # The one external program, as argv, and never a shell.
    check("it runs exactly one external program, and that one is schtasks",
          text.count("schtasks") >= 3 and "shell=True" not in text, text.count("schtasks"))
    for word in ("os.system", "os.popen", "subprocess.call(", "subprocess.Popen("):
        check(f"it never asks the operating system to run anything ({word})",
              word not in text, word)
    check("it opens no socket of its own - the lane probe is loopback urllib",
          "socket.socket" not in text, "socket.socket")
    check("... and the one address it asks is 127.0.0.1",
          "http://127.0.0.1:" in text, "no loopback address")
    # No bulk action, in the two places a caller could ask for one: the body
    # the route accepts, and the launcher itself. `_launch_task` is named
    # exactly once - the function itself, which `start()` reaches through its
    # one default seam - so there is exactly one way for this module to start
    # anything. `"all"` appears only where the route REFUSES it.
    check("nothing in this module can be asked to start more than one lane",
          text.count("_launch_task(") == 1
          and 'unknown = [k for k in body if k != "why"]' in text
          and "for lane in LANES" not in text, text.count("_launch_task("))
    # And the two route paths are the ones the apps call.
    check("the two route paths are the ones the apps call",
          L.GET_ROUTE == "/api/model-lanes"
          and L.START_ROUTE == "/api/model-lanes/start",
          (L.GET_ROUTE, L.START_ROUTE))


def t_the_install_wires_both_routes_behind_the_same_checks():
    """A tiny stand-in Handler, so the wiring itself is exercised: this route
    can start a program, so it is behind the backend's own origin and token
    checks - the same gate as /api/status. The two route seams are replaced, so
    exercising the wiring asks no real lane and starts no real task.

    A FRESH class per install, deliberately: `install()` replaces the class's
    own `do_GET`/`do_POST`, which is what the running backend wants (it calls
    it exactly once, at start-up), and installing twice onto one class would
    test the second wrapper over the first instead of a clean one.
    """
    def handler_class():
        class FakeHandler:
            def __init__(self):
                self.answers = []
                self.path = ""

            def _send(self, code, payload):
                self.answers.append((code, payload))
                return code

            def do_GET(self):
                self.answers.append(("parent-get", None))

            def do_POST(self):
                self.answers.append(("parent-post", None))

        return FakeHandler

    seen = []

    def fake_probe(port, timeout=None):
        seen.append(("probe", port))
        return False

    def fake_start(lane, *a, **k):
        seen.append(("start", lane.key))
        return 202, {"ok": True, "state": "starting", "message": "stand-in"}

    real_probe, real_start = L._PROBE_FOR_ROUTES, L._START_FOR_ROUTES
    L._PROBE_FOR_ROUTES, L._START_FOR_ROUTES = fake_probe, fake_start
    try:
        ok_cls = handler_class()
        banner = L.install(ok_cls, origin_ok=lambda h: True,
                           token_ok=lambda h: True,
                           read_body=lambda h: b'{"why": "test"}',
                           url="http://127.0.0.1:11436")
        check("install() returns a banner line naming the feature",
              "model lanes" in banner, banner)

        fake = ok_cls()
        fake.path = L.GET_ROUTE
        fake.do_GET()
        check("a GET of the read route answers 200 when the checks pass",
              fake.answers and fake.answers[-1][0] == 200, fake.answers)
        check("... and it read the lane through the route's own seam",
              ("probe", 11436) in seen, seen)

        start = ok_cls()
        start.path = L.START_ROUTE
        start.do_POST()
        check("the start route answers through the same checks",
              start.answers and start.answers[-1][0] == 202, start.answers)
        check("... and it started the CHAT's lane, and only that one",
              ("start", "everyday") in seen, seen)

        other = ok_cls()
        other.path = "/api/status"
        other.do_GET()
        check("any other route falls through to the core untouched",
              other.answers == [("parent-get", None)], other.answers)

        # A class of its own, with a token check that refuses: the same route,
        # the same gate as /api/status.
        closed_cls = handler_class()
        L.install(closed_cls, origin_ok=lambda h: True, token_ok=lambda h: False,
                  read_body=lambda h: b"", url="http://127.0.0.1:11436")
        unauth = closed_cls()
        unauth.path = L.GET_ROUTE
        unauth.do_GET()
        check("... and the read is refused without the token (401), like "
              "/api/status", unauth.answers and unauth.answers[-1][0] == 401,
              unauth.answers)
        unauth_post = closed_cls()
        unauth_post.path = L.START_ROUTE
        unauth_post.do_POST()
        check("... and so is a start", unauth_post.answers
              and unauth_post.answers[-1][0] == 401, unauth_post.answers)

        # And an origin that refuses, which is how a page on another site is
        # kept out of a route that starts a program.
        cross_cls = handler_class()
        L.install(cross_cls, origin_ok=lambda h: False, token_ok=lambda h: True,
                  read_body=lambda h: b"", url="http://127.0.0.1:11436")
        cross = cross_cls()
        cross.path = L.START_ROUTE
        cross.do_POST()
        check("... and a cross-origin start is refused (403)",
              cross.answers and cross.answers[-1][0] == 403, cross.answers)
    finally:
        L._PROBE_FOR_ROUTES, L._START_FOR_ROUTES = real_probe, real_start
        clean()


if __name__ == "__main__":
    for fn in (t_the_lane_is_the_one_the_chat_uses,
               t_the_task_is_found_by_the_half_a_rename_does_not_touch,
               t_the_lane_table_matches_the_read_only_checker,
               t_a_down_lane_can_be_started_and_runs_his_own_task,
               t_the_command_it_really_runs_is_schtasks_run_with_that_task_name,
               t_a_lane_that_is_up_is_never_started,
               t_a_start_that_never_comes_up_leaves_the_warning_standing,
               t_a_start_that_DOES_come_up_says_how_long_it_took,
               t_a_task_the_pc_says_is_running_is_not_started_again,
               t_a_second_press_while_the_first_is_watched_starts_nothing,
               t_a_task_that_is_not_on_this_pc_is_refused_and_nothing_runs,
               t_the_pc_refusing_to_start_it_is_reported_honestly,
               t_the_status_never_says_up_from_anything_but_the_lane,
               t_the_lane_that_is_up_is_the_only_thing_that_clears_the_warning,
               t_the_routes_answer_what_they_promise,
               t_the_probe_is_strict_about_what_a_lane_is,
               t_nothing_real_is_ever_run_by_this_suite,
               t_the_install_wires_both_routes_behind_the_same_checks):
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
