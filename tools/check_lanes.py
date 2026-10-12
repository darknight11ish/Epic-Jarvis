#!/usr/bin/env python3
"""Check the two Ollama lanes, say plainly which one is down, and print the ONE
command that brings it back.

    py -3 tools/check_lanes.py
    py -3 tools/check_lanes.py --list
    py -3 tools/check_lanes.py --port everyday=59999 --timeout 1

WHY THIS EXISTS, IN ONE PARAGRAPH

On 2026-10-10 at 22:10 both Ollama lanes stopped together and nobody was told.
They came back only when a person noticed and started them by hand, at 22:58
(port 11436) and 23:09 (port 11435). The script that stopped them
(`scripts/move-models-to-d.ps1`, step 8b) then tried to start them again by two
task names typed from memory - `Jarvis Ollama - Everyday model` and
`Jarvis Ollama - Coding model` - while the tasks on this PC really end in
`(RTX 2060)` and `(RTX 2080 Super)`. `Start-ScheduledTask` matched nothing,
`-ErrorAction SilentlyContinue` threw the failure away, and the script exited 0
saying the move was fine. So there are two halves to this tool, and both are
about not being quiet:

  1. DOWN is loud. A lane that does not answer is named, the run exits
     non-zero, and the exact command that starts it is printed. The command is
     built from the task name this PC actually has (looked up by the part of the
     name a rename does not touch), so it cannot name a task that is not there.
  2. "Up" is not the same as "right". A lane can answer /api/ps happily and
     still be carrying a tiny context - measured on this PC on 2026-10-11,
     port 11436 answered while holding a 2,048-token window instead of the
     196,608 its own logon task asks for. `start-lane.ps1` will NOT fix that:
     the port answers, so it prints "already answering - leaving it alone" and
     exits 0. So a lane at the wrong context is also non-zero, and also gets
     its own command.

SKIPPED OFF THE OWNER'S PC. A bare run needs this machine's Task Scheduler and its
lanes on 127.0.0.1, so on any other host (a CI runner included) it prints the
reason and exits 0 rather than reporting NOT HEALTHY - see THE HOST GUARD in
main(). `--tasks-file` supplies the task list yourself and is never skipped.

READ-ONLY. It opens a socket to 127.0.0.1 and prints. It starts nothing, stops
nothing, loads no model and writes no file. It never reads or prints the pairing
token.

EXIT CODES (so another script can notice without reading the words)

    0  every lane answered, at the context its logon task asks for
    1  a lane is DOWN (nothing is listening on its port)
    2  a lane answered, but at a different context than it should have
    3  nothing was looked at at all - which is never a pass

The context numbers below are this PC's settings, mirrored from each lane's own
logon task on 2026-10-11 (`-ContextLength 196608` for the everyday lane on the
RTX 2060, `16384` for the coding lane on the RTX 2080 Super). Change them with
`--context everyday=32768` if the tasks are ever changed; `health.ps1` reads the
number out of the task itself and is the authority when the two disagree.
"""
from __future__ import annotations

import argparse
import csv
import json
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from collections import namedtuple

#: How a lane is described. `key` is what --port/--context name it by,
#: `task_prefix` is the part of its scheduled-task name that a rename does not
#: touch (the RTX model in brackets is deliberately NOT part of it, because
#: that is the half that changed under the script that caused this), and
#: `context` is the window its logon task asks for on this PC.
Lane = namedtuple("Lane", "key plain port task_prefix context")

LANES = (
    Lane("everyday", "EVERYDAY (main), qwen3.5:9b on the RTX 2060",
         11436, "Jarvis Ollama - Everyday model", 196608),
    Lane("coding", "CODING, qwen3:8b on the RTX 2080 Super",
         11435, "Jarvis Ollama - Coding model", 16384),
)

#: What the port that is NOT a Jarvis task is called, for `--port foo=1234`.
UNKNOWN_TASK = "(no scheduled task matched)"

Result = namedtuple("Result", "lane port state detail command")


def scheduled_tasks() -> tuple:
    """Every scheduled task whose name starts with 'Jarvis Ollama'.

    Read with `schtasks`, which ships with Windows and needs no module. Off
    Windows - or if `schtasks` is missing or refuses - this returns () and the
    caller says so rather than guessing a name. A name typed from memory is the
    entire bug this tool was written after, so there is no fallback list here.
    """
    try:
        done = subprocess.run(["schtasks", "/query", "/fo", "csv", "/nh"],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ()
    text = done.stdout.decode("utf-8", errors="replace")
    names = []
    for row in csv.reader(text.splitlines()):
        if not row:
            continue
        name = row[0].lstrip("\\")
        if name.startswith("Jarvis Ollama"):
            names.append(name)
    return tuple(names)


def tasks_from_file(path: str) -> tuple:
    """The task names in `path`, one per line, '#' comments ignored.

    This is how the test drives the tool without an owner's PC: the same code
    path as `scheduled_tasks()` above, with the machine's own answer supplied.
    """
    names = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(line)
    return tuple(names)


def task_for(lane: Lane, tasks: tuple) -> str:
    """The lane's real task name, or "" when this PC has no such task.

    Matched on the stable prefix, so renaming the task to a different card keeps
    working and renaming it away entirely is reported instead of guessed at.
    """
    for name in tasks:
        if name.startswith(lane.task_prefix):
            return name
    return ""


def start_command(lane: Lane, task: str) -> str:
    """The one command that brings this lane back."""
    if task:
        return f"Start-ScheduledTask -TaskName '{task}'"
    return (f'powershell -NoProfile -File '
            f'"%LOCALAPPDATA%\\JarvisOllama\\start-lane.ps1" -Lane '
            f'{"main" if lane.key == "everyday" else "coding"} '
            f'-Port {lane.port} -GpuUuid <that card\'s UUID from '
            f'nvidia-smi -L> -ContextLength {lane.context}')


def fix_command(lane: Lane, task: str) -> str:
    """The one command for a lane that is UP at the wrong context.

    Starting it is not enough: its own `start-lane.ps1` sees the port answering,
    says "already answering - leaving it alone" and exits 0, so the server
    holding the wrong window stays exactly where it is. The server has to go
    first, and then the lane's own task starts it at the right context again.
    One pasteable line; this tool runs neither half.
    """
    stop = (f"$owning = (Get-NetTCPConnection -State Listen -LocalPort "
            f"{lane.port} -ErrorAction SilentlyContinue).OwningProcess; "
            f"if ($owning) {{ Stop-Process -Id $owning -Force }}")
    if task:
        return f"{stop}; Start-ScheduledTask -TaskName '{task}'"
    return f"{stop}; {start_command(lane, task)}"


def probe(port: int, timeout: float):
    """(models, error) for one lane. `models` is what /api/ps reported.

    Read-only: one GET, nothing else. A closed port answers instantly on
    127.0.0.1, so the timeout only matters for a port that is firewalled into
    silence - a lane in that state is DOWN too, which is why the timeout is a
    verdict and not a crash.
    """
    url = f"http://127.0.0.1:{port}/api/ps"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as err:
        # Something IS listening, it just did not like the request. That is not
        # a lane that came back, and it is not silence either - say which.
        return [], f"the port answered HTTP {err.code}, not an Ollama reply"
    except (urllib.error.URLError, OSError, socket.error) as err:
        return [], f"nothing is answering ({err})"
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return [], "the port answered, but not with JSON"
    return list(payload.get("models") or ()), ""


def check_lane(lane: Lane, task: str, timeout: float) -> Result:
    models, error = probe(lane.port, timeout)
    if error:
        return Result(lane, lane.port, "DOWN", error, start_command(lane, task))
    if not models:
        return Result(lane, lane.port, "UP",
                      "up, no model loaded (it loads on the first question)", "")
    got = [m.get("context_length") for m in models]
    # context 0 means "no expectation was given for this port" - a port someone
    # asked about with --port, which has no Jarvis task behind it. Judging it
    # against an unset number would be inventing a verdict.
    wrong = [c for c in got if lane.context > 0 and c != lane.context]
    if wrong:
        detail = (f"UP but loaded at context {wrong[0]}, and this lane's task "
                  f"asks for {lane.context}")
        return Result(lane, lane.port, "WRONG SETTINGS", detail,
                      fix_command(lane, task))
    return Result(lane, lane.port, "UP",
                  f"up at context {got[0]} ({models[0].get('name')})", "")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the Jarvis Ollama lanes. Read-only.")
    parser.add_argument("--list", action="store_true",
                        help="print the lanes this tool knows, look at no port, "
                             "and exit 0")
    parser.add_argument("--port", action="append", default=[], metavar="KEY=N",
                        help="check KEY on port N instead of its usual one; "
                             "KEY may be a lane name or anything you like")
    parser.add_argument("--context", action="append", default=[],
                        metavar="KEY=N", help="the context KEY should be at")
    parser.add_argument("--tasks-file", metavar="FILE",
                        help="read scheduled-task names from FILE, one per "
                             "line, instead of asking this PC")
    parser.add_argument("--timeout", type=float, default=3.0, metavar="SEC",
                        help="how long one lane may take to answer (default 3)")
    args = parser.parse_args(argv)

    lanes = list(LANES)
    overrides = {}
    for item in args.port:
        if "=" not in item:
            print(f"::error::--port wants KEY=PORT, not {item!r}")
            return 3
        key, _, number = item.partition("=")
        try:
            overrides.setdefault(key.strip(), {})["port"] = int(number)
        except ValueError:
            print(f"::error::--port {item!r}: {number!r} is not a port number")
            return 3
    for item in args.context:
        if "=" not in item:
            print(f"::error::--context wants KEY=N, not {item!r}")
            return 3
        key, _, number = item.partition("=")
        try:
            overrides.setdefault(key.strip(), {})["context"] = int(number)
        except ValueError:
            print(f"::error::--context {item!r}: {number!r} is not a number")
            return 3

    known = {lane.key for lane in lanes}
    for key, changes in overrides.items():
        if key in known:
            continue
        # A brand new port someone asked about: check it, and say honestly that
        # no Jarvis task is known for it instead of inventing a task name.
        lanes.append(Lane(key, key, changes.get("port", 0),
                          UNKNOWN_TASK, changes.get("context", 0)))
    lanes = [lane._replace(port=overrides.get(lane.key, {}).get("port", lane.port),
                           context=overrides.get(lane.key, {}).get(
                               "context", lane.context))
             for lane in lanes]

    if args.list:
        print("lanes this tool knows about:")
        for lane in lanes:
            print(f"  {lane.key:<10} port {lane.port:<6} context {lane.context}"
                  f"  -> a task whose name starts with {lane.task_prefix!r}")
            print(f"             {lane.plain}")
        print("no port was looked at: this run proves the table, nothing else.")
        return 0

    bad_lane = [lane for lane in lanes if lane.port <= 0]
    if bad_lane:
        print("::error::nothing was checked: these lanes have no port: "
              + ", ".join(lane.key for lane in bad_lane))
        return 3

    # THE HOST GUARD. This checker's whole job is to look at the owner's own PC:
    # the Task Scheduler (`scheduled_tasks()`, via `schtasks`) and the lanes
    # listening on 127.0.0.1. Neither can be the owner's on a CI runner, so a bare
    # run there is SKIPPED with the reason printed, not reported NOT HEALTHY - a
    # red that means "wrong machine" makes every pull request red and teaches
    # nobody anything. Passing --tasks-file is the caller supplying the machine's
    # own answer, so that path is never skipped.
    if not args.tasks_file and sys.platform != "win32":
        print("SKIP: this checker reads the owner's PC, and this is not it")
        print(f"  host: sys.platform == {sys.platform!r}, and it needs 'win32' - only")
        print("  there can `schtasks` list the tasks named 'Jarvis Ollama...' and")
        print("  only there do the lanes answer on http://127.0.0.1:<port>/api/ps.")
        print("  NOTHING WAS CHECKED, and that is not the same as healthy: run this")
        print("  on the owner's PC for a real answer, or pass --tasks-file to supply")
        print("  the task list yourself.")
        print("exit code: 0 (skipped - the reason is above)")
        return 0
    if args.tasks_file:
        try:
            tasks = tasks_from_file(args.tasks_file)
        except OSError as err:
            print(f"::error::the task list could not be read, so nothing was "
                  f"checked: {err}")
            return 3
        where = f"task list: {args.tasks_file} ({len(tasks)} name(s))"
    else:
        tasks = scheduled_tasks()
        if tasks:
            where = (f"task list: this PC's Task Scheduler "
                     f"({len(tasks)} task(s) named 'Jarvis Ollama...')")
        else:
            # A loud line, never a silent empty list: on a PC where these tasks
            # exist, finding none is news, and it is the exact state that made
            # the 2026-10-10 restart a no-op.
            where = ("task list: this PC's Task Scheduler - NO task was found "
                     "whose name starts with 'Jarvis Ollama'")

    print("Jarvis Ollama lanes - read-only: starts nothing, stops nothing")
    print(where)
    print()

    results = []
    for lane in lanes:
        # A port with no Jarvis task behind it gets no task name, so the tool
        # cannot hand out a command naming a task that does not exist.
        task = "" if lane.task_prefix == UNKNOWN_TASK \
            else task_for(lane, tasks)
        if task:
            print(f"  {lane.key} lane (port {lane.port}) -> task "
                  f"'{task}'")
        else:
            print(f"  {lane.key} lane (port {lane.port}) -> NO scheduled task "
                  f"on this PC starts with {lane.task_prefix!r}")
        results.append(check_lane(lane, task, args.timeout))

    print()
    for result in results:
        mark = {"DOWN": "LANE DOWN     ",
                "WRONG SETTINGS": "LANE WRONG SETTINGS",
                "UP": "up            "}[result.state]
        print(f"  {mark}  {result.lane.key:<10} port {result.port:<6} "
              f"- {result.detail}")

    need_help = [r for r in results if r.command]
    if need_help:
        print()
        print("--- TO FIX: run the command for the lane that needs it ---")
        for result in need_help:
            print(f"  {result.lane.key} (port {result.port}) - {result.detail}")
            print(f"    {result.command}")
        print()
        print("  Nothing above was run by this tool - it only looked and printed.")

    down = [r for r in results if r.state == "DOWN"]
    wrong = [r for r in results if r.state == "WRONG SETTINGS"]
    if down:
        code = 1
    elif wrong:
        code = 2
    else:
        code = 0

    print()
    if code == 0:
        print(f"HEALTHY - {len(results)} lane(s) answered, each at the context "
              f"it should have.")
    elif code == 1:
        print(f"NOT HEALTHY - {len(down)} lane(s) DOWN. The command to bring "
              f"each one back is printed above.")
    else:
        print(f"NOT HEALTHY - {len(wrong)} lane(s) answered at the WRONG "
              f"CONTEXT. Starting a lane will not fix that - the command above "
              f"will.")
    print(f"exit code: {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
