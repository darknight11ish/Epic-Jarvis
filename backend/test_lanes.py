"""test_lanes.py - tools/check_lanes.py, the lanes' own guard.

    python3 backend/test_lanes.py

WHAT THIS IS FOR. `tools/check_lanes.py` is the durable half of the fix for
2026-10-10, when both Ollama lanes stopped at 22:10 and came back only because a
person noticed ninety minutes later. The script that stopped them had tried to
start them again by two task names typed from memory - `Jarvis Ollama -
Everyday model` instead of `Jarvis Ollama - Everyday model (RTX 2060)` - and
`-ErrorAction SilentlyContinue` turned that into a cheerful log line and exit 0.

So the one thing this suite must never let happen is the tool quietly going back
to that shape. It proves, on throwaway ports and with a stand-in task list -
NEVER by touching the owner's lanes, which this repository may only read:

  * a CLOSED port is DOWN, the run exits 1, and the exact command that starts
    that lane is printed;
  * the command names the task from the task list it was given, so a renamed
    task is followed rather than missed;
  * a task list with NO `Jarvis Ollama...` name in it says so in a loud line and
    prints no `Start-ScheduledTask` at all - the failure that caused all of this
    was a command naming a task that did not exist, so a command must not be
    printed when there is no task to name;
  * a port that IS listening but is not an Ollama lane (an HTTP error, or JSON
    that is not an Ollama reply) is DOWN, not "up";
  * a lane answering at the WRONG CONTEXT exits 2 and gets the two-part
    command, because `start-lane.ps1` answers /api/version, says "already
    answering - leaving it alone" and exits 0 - so starting it cannot fix a
    lane that is up with the wrong settings;
  * a port number of 0 is refused as "nothing was checked", never as a pass;
  * `--list` names the lane table and says in words that it looked at no port,
    so "nothing is wrong" and "nothing was looked at" stay different sentences.

BOTH LANES ARE ALWAYS REDIRECTED. Every run below passes a port for each lane,
so this suite cannot read the owner's PC: a lane it did not mean to test is
answered by a stand-in server on a loopback port, or by a port nothing is
listening on. That is not tidiness - the first draft of this file overrode only
the lane under test, and on the owner's PC the other lane was really there and
really at the wrong context, so two checks failed for a reason that had nothing
to do with the tool.

Needs nothing from the owner's PC, no network beyond 127.0.0.1, and no
third-party package: the tool is standard library only, and so is this.
"""
from __future__ import annotations

import contextlib
import http.server
import json
import socket
import subprocess
import sys
import tempfile
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_lanes.py"

PASSED, FAILED = [], []

#: The context each lane's logon task asks for on this PC. The tool carries the
#: same two numbers; the stand-in servers below say them back.
EXPECTED = {"everyday": 196608, "coding": 16384}

REAL_TASKS = ["Jarvis Ollama - Everyday model (RTX 2060)",
              "Jarvis Ollama - Coding model (RTX 2080 Super)"]


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def run(*args):
    """(exit code, everything the tool printed) for one run, from the repo root."""
    done = subprocess.run(
        [sys.executable, str(TOOL), *args], cwd=str(REPO),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def free_port() -> int:
    """A port nothing is listening on.

    Bound and released, so the number is one the operating system just handed
    out and no lane can be on - which makes "closed" a fact about this run
    rather than a guess about the machine.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def tasks_file(names) -> str:
    """A stand-in for this PC's Task Scheduler: one task name per line."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8")
    handle.write("# a stand-in for this PC's Task Scheduler\n")
    for name in names:
        handle.write(name + "\n")
    handle.close()
    return handle.name


def lane_body(context: int) -> bytes:
    """/api/ps as a lane at `context` answers it."""
    return json.dumps({"models": [{"name": f"stand-in:{context}",
                                   "context_length": context}]}).encode()


class _Handler(http.server.BaseHTTPRequestHandler):
    """Answers every GET with whatever the test told it to."""

    body = b"{}"
    status = 200

    def do_GET(self):                                   # noqa: N802
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):                       # keep test output clean
        pass


@contextlib.contextmanager
def serve(body: bytes, status: int = 200):
    """A little HTTP server on loopback, so a port answers without a lane.

    Yields its port. Used to tell "an Ollama lane" from "something listening",
    which only a real listener can prove.
    """
    handler = type("H", (_Handler,), {"body": body, "status": status})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@contextlib.contextmanager
def isolated(everyday=None, coding=None, tasks=None):
    """The command-line arguments for one run that cannot reach the owner's PC.

    `everyday` and `coding` each say what that lane's port should be:

      * an int          - use that port, and nothing stands behind it
      * (body, status)  - serve exactly that answer on a fresh port
      * None            - serve a healthy lane at the context it should have

    So a test that cares about ONE lane gets the other one healthy and quiet,
    and the exit code it reads is about the lane it meant to test.
    """
    stops, ports = [], {}
    for key, spec in (("everyday", everyday), ("coding", coding)):
        if spec is None:
            stack = contextlib.ExitStack()
            port = stack.enter_context(serve(lane_body(EXPECTED[key])))
            stops.append(stack)
            ports[key] = port
        elif isinstance(spec, int):
            ports[key] = spec
        else:
            body, status = spec
            stack = contextlib.ExitStack()
            port = stack.enter_context(serve(body, status))
            stops.append(stack)
            ports[key] = port
    try:
        yield ("--port", f"everyday={ports['everyday']}",
               "--port", f"coding={ports['coding']}",
               "--timeout", "2",
               "--tasks-file", tasks if tasks else tasks_file(REAL_TASKS))
    finally:
        for stack in stops:
            stack.close()


# ---------------------------------------------------------------------------
#   The tool is here, and it can say what it knows without touching a port
# ---------------------------------------------------------------------------

def t_the_tool_exists():
    check("tools/check_lanes.py exists", TOOL.is_file(), str(TOOL))


def t_list_names_the_lanes_and_looks_at_no_port():
    """The one run that needs no stand-ins: --list opens no socket at all."""
    code, out = run("--list")
    check("--list exits 0", code == 0, out)
    check("it names both real lane ports (11436 everyday, 11435 coding)",
          "11436" in out and "11435" in out, out)
    check("it names the context each lane should have (196608 and 16384)",
          "196608" in out and "16384" in out, out)
    check("it prints the STABLE part of each task name, not the card in "
          "brackets - the half that a rename does not touch",
          "Jarvis Ollama - Everyday model" in out
          and "Jarvis Ollama - Coding model" in out, out)
    check("it says in words that no port was looked at, so this run cannot be "
          "mistaken for a healthy check",
          "no port was looked at" in out, out)


# ---------------------------------------------------------------------------
#   Direction 1: a lane that is DOWN - the whole point
# ---------------------------------------------------------------------------

def t_a_closed_port_is_down_and_prints_the_one_command():
    port = free_port()
    with isolated(everyday=port) as args:
        code, out = run(*args)
    check("a closed port is reported as LANE DOWN", "LANE DOWN" in out, out)
    check("... and the run exits 1", code == 1, f"exit {code}\n{out}")
    check("... and the lane is named with the port that was asked about",
          f"port {port}" in out, out)
    check("... and the healthy coding lane is not dragged into it",
          "coding" in out and "up " in out, out)
    check("... and the ONE command that brings it back is printed, naming the "
          "task from the task list",
          "Start-ScheduledTask -TaskName "
          "'Jarvis Ollama - Everyday model (RTX 2060)'" in out, out)
    check("... and the run says it ran nothing itself",
          "Nothing above was run by this tool" in out, out)


def t_the_command_follows_a_renamed_task():
    """The card in brackets is the half that changed under the 22:10 bug."""
    port = free_port()
    path = tasks_file(["Jarvis Ollama - Everyday model (RTX 5090)"])
    with isolated(everyday=port, tasks=path) as args:
        code, out = run(*args)
    check("a renamed lane is followed to its new name",
          "Start-ScheduledTask -TaskName 'Jarvis Ollama - Everyday model "
          "(RTX 5090)'" in out, out)
    check("... and the old name is not handed out as the fix",
          "(RTX 2060)" not in out, out)
    check("... and it still exits 1", code == 1, f"exit {code}\n{out}")


def t_no_task_at_all_is_loud_and_prints_no_task_command():
    """The exact shape of 2026-10-10: a command naming a task that is not there.

    So when there is no task to name there must be NO `Start-ScheduledTask` line
    at all. A printed command that cannot work is worse than none, because it is
    what a person pastes.
    """
    port = free_port()
    with isolated(everyday=port,
                  tasks=tasks_file(["Some Other Program's Task"])) as args:
        code, out = run(*args)
    check("with no matching task the run says so loudly",
          "NO scheduled task" in out, out)
    check("... and prints NO Start-ScheduledTask command to paste",
          "Start-ScheduledTask" not in out, out)
    check("... and it still exits 1, so the DOWN is not softened by the "
          "missing name", code == 1, f"exit {code}\n{out}")


# ---------------------------------------------------------------------------
#   "Something is listening" is not "a lane is back"
# ---------------------------------------------------------------------------

def t_a_port_that_answers_with_an_http_error_is_down():
    with isolated(everyday=(b'{"error":"nope"}', 500)) as args:
        code, out = run(*args)
    check("a port answering HTTP 500 is DOWN, not up",
          "LANE DOWN" in out, out)
    check("... and the reason says it answered HTTP, not that it was silent",
          "answered HTTP 500" in out, out)
    check("... and it exits 1", code == 1, f"exit {code}\n{out}")


def t_a_port_that_answers_with_junk_is_down():
    with isolated(everyday=(b"this is not json at all", 200)) as args:
        code, out = run(*args)
    check("a port answering with something that is not JSON is DOWN",
          "LANE DOWN" in out and "not with JSON" in out, out)
    check("... and it exits 1", code == 1, f"exit {code}\n{out}")


# ---------------------------------------------------------------------------
#   Direction 2: up, but at the wrong context
# ---------------------------------------------------------------------------

def t_a_lane_at_the_wrong_context_exits_2_and_gets_the_two_part_command():
    with isolated(everyday=(lane_body(2048), 200)) as args:
        code, out = run(*args)
    check("a lane loaded at 2048 when its task asks for 196608 is "
          "LANE WRONG SETTINGS", "LANE WRONG SETTINGS" in out, out)
    check("... and it exits 2, not 0 and not 1", code == 2,
          f"exit {code}\n{out}")
    check("... and the fix stops the process holding the wrong window first",
          "Stop-Process" in out, out)
    check("... and then starts the lane's own task by its real name",
          "Start-ScheduledTask -TaskName "
          "'Jarvis Ollama - Everyday model (RTX 2060)'" in out, out)


def t_a_lane_at_the_right_context_is_health():
    with isolated() as args:          # both stand-ins at their correct context
        code, out = run(*args)
    check("a lane at exactly the context its task asks for is healthy",
          code == 0, f"exit {code}\n{out}")
    check("... and the healthy line says a number of lanes answered, so "
          "'nothing wrong' cannot be confused with 'nothing looked at'",
          "2 lane(s) answered" in out, out)


def t_a_lane_with_no_model_loaded_is_up_not_down():
    with isolated(coding=(b'{"models":[]}', 200)) as args:
        code, out = run(*args)
    check("a lane that is up with no model loaded is UP, not DOWN - it loads "
          "on the first question", code == 0 and "LANE DOWN" not in out, out)
    check("... and it says so in words",
          "no model loaded" in out, out)


# ---------------------------------------------------------------------------
#   Nothing looked at is never a pass
# ---------------------------------------------------------------------------

def t_a_port_of_zero_is_refused():
    code, out = run("--port=everyday=0", "--port=coding=0")
    check("a lane with no usable port exits 3", code == 3,
          f"exit {code}\n{out}")
    check("... and says nothing was checked, rather than OK",
          "nothing was checked" in out, out)


def t_a_missing_task_file_is_refused():
    code, out = run("--port=everyday=5999", "--port=coding=5998",
                    "--tasks-file", str(REPO / "no-such-task-list.txt"))
    check("a task list that cannot be read exits 3", code == 3,
          f"exit {code}\n{out}")
    check("... and never falls back to guessing task names",
          "could not be read" in out, out)


def t_a_malformed_override_is_refused():
    for bad in ("--port=everyday", "--port=everyday=notaport"):
        code, out = run(bad)
        check(f"{bad} exits 3 with a plain reason", code == 3,
              f"exit {code}\n{out}")


# ---------------------------------------------------------------------------
#   The one thing this tool must never do to the owner's PC
# ---------------------------------------------------------------------------

def t_the_tool_only_reads_and_prints():
    """Read-only is a property of the source, so it is checked there.

    The tool may NAME `Stop-Process` and `Start-ScheduledTask` in the command it
    prints - that is the whole point of it - but it must never run either. The
    only thing it executes is the task reader, and the only file it opens, it
    opens to read.
    """
    text = TOOL.read_text(encoding="utf-8")
    check("it runs exactly one external program, and that one is the task "
          "reader", text.count("subprocess.run(") == 1 and "schtasks" in text,
          text.count("subprocess.run("))
    for word in ("subprocess.call(", "subprocess.check_call(",
                 "subprocess.check_output(", "subprocess.Popen(",
                 "os.system", "os.popen"):
        check(f"it never asks the operating system to run anything ({word})",
              word not in text, word)
    for word in ('"w"', "'w'", '"wb"', "'wb'", "os.remove", "shutil",
                 "unlink", "mkdir", ".write("):
        check(f"it never writes anything ({word})", word not in text, word)
    check("its one open() is the task list, read-only",
          text.count("open(") == 2          # open(path, ...) and urlopen(
          and 'open(path, encoding="utf-8")' in text, text.count("open("))


if __name__ == "__main__":
    for fn in (t_the_tool_exists,
               t_list_names_the_lanes_and_looks_at_no_port,
               t_a_closed_port_is_down_and_prints_the_one_command,
               t_the_command_follows_a_renamed_task,
               t_no_task_at_all_is_loud_and_prints_no_task_command,
               t_a_port_that_answers_with_an_http_error_is_down,
               t_a_port_that_answers_with_junk_is_down,
               t_a_lane_at_the_wrong_context_exits_2_and_gets_the_two_part_command,
               t_a_lane_at_the_right_context_is_health,
               t_a_lane_with_no_model_loaded_is_up_not_down,
               t_a_port_of_zero_is_refused,
               t_a_missing_task_file_is_refused,
               t_a_malformed_override_is_refused,
               t_the_tool_only_reads_and_prints):
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
