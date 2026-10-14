"""jarvis_model_lanes.py - the button that starts the model lane that is down.

WHAT THIS IS FOR, in the owner's own situation. His Jarvis talks to one Ollama
lane, on `OLLAMA_URL` (`http://127.0.0.1:11436` on his PC, not Ollama's own
11434). Each lane is started by HIS OWN Windows logon task - `Jarvis Ollama -
Everyday model (RTX 2060)` and `Jarvis Ollama - Coding model (RTX 2080
Super)` - which run `start-lane.ps1` with that lane's own port, card and
context. On 2026-10-13 both lanes died at about 16:30 and nothing said so for
about five hours; PR #409 made both apps say it, and deliberately made the
warning do NOTHING (`jarvis-desktop/src/lane-warning.js`: "nothing here acts").
The owner has since decided the warning should offer one action, and this
module is the backend half of it.

THE ONE ACTION IS HIS OWN TASK, NEVER A HAND-ROLLED COMMAND. It does not run
`ollama serve`, and it does not build a command line from a remembered task
name. The task name is looked up on THIS PC, by the stable half of the name
(`task_prefix` below - the card in brackets is the half that changed under the
2026-10-10 accident), and the whole action is `schtasks /run /tn <that name>`:
exactly what his logon task is, with his own port, card and context, because
the task itself holds them. `tools/check_lanes.py` has printed that same
command, from the same lookup, since 2026-10-10 - this is that rule, with a
way to run it.

WHICH LANE. `target()` asks the address the CHAT uses, which is
`jarvis_hud.OLLAMA_URL` when this module is beside it - so the lane that is
started is the lane Jarvis would talk to, never a guessed one and never both.
Only a lane that does NOT answer `/api/tags` is started. A lane that answers
is left completely alone.

STARTING A TASK IS NOT THE SAME AS THE MODEL ARRIVING, and this module never
pretends it is. `schtasks /run` returns as soon as the task is launched; the
lane may still be loading a model for a minute. So `start()` starts it and
then WATCHES - a background thread asks `/api/tags` every few seconds - and
the state stays `starting`, with the seconds counted, until the lane really
answers, at which point it is `up` with how long it took. If it never answers
inside `WAIT_S`, the state becomes `down` with a plain sentence saying it did
not come up, and the apps leave the warning standing. That is the whole point:
a button that reports success and changes nothing is the failure this project
keeps finding.

It is not one request that blocks for ninety seconds. The caller gets an
answer at once (`starting`), reads `GET /api/model-lanes` on a short beat
while it says so, and stops asking when it settles.

NOTHING IS STARTED TWICE. The lane is not started if it is already answering,
if this module started that task moments ago and is still watching it, or if
the PC's own Task Scheduler says that task is already running.

PERMISSION - no approval card, and why. This project's one permission model
lives in `docs/ARCHITECTURE.md` §3: plan / describe / the gate / run. The gate
exists to make JARVIS ask before it acts. This runs in the opposite direction:
it is a control the OWNER presses, and the press is the explicit act the gate
would be asking for. Two things decide the tier (`auto`, no card):

  * his own logon task already runs this exact command unattended, at every
    logon, with no card and no question - so a card here would be stricter
    than the thing it duplicates, and a card that only ever repeats a button
    is how a person learns to approve without reading;
  * it is capability worth nothing on its own: it opens no socket that was not
    already open (`/api/tags` on loopback), adds no reach, and is refused
    outright when this PC has no such task, so there is nothing to approve.

So there is no new tier line to loosen, on purpose, and no card. What is NOT
done, because it is forbidden outright: no bulk action, no "start both lanes",
nothing that approves in bulk and nothing that clears a rush latch. One lane -
the one Jarvis talks to - one press.

WHERE IT RUNS. Windows only: `schtasks` and a Windows Task Scheduler. Off
Windows every answer says so in words (`_host_reason`) rather than failing.

Standard library only, no third-party package, no network beyond 127.0.0.1.
It runs one external program (`schtasks`), never a shell, always as argv.
"""
from __future__ import annotations

import csv
import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from typing import Callable, Optional

try:  # beside this file on the PC
    import jarvis_local_http
except Exception:  # pragma: no cover - the tests run without it
    jarvis_local_http = None

#: How a lane is described. `key` is the short name both apps show, `port` is
#: the port this PC starts it on, `task_prefix` is the part of its scheduled
#: task's name that a rename does not touch (the card in brackets is
#: deliberately NOT part of it - that is the half that changed under the
#: 2026-10-10 accident, see tools/check_lanes.py), and `words` is what it is.
Lane = namedtuple("Lane", "key port task_prefix words")

LANES = (
    Lane("everyday", 11436, "Jarvis Ollama - Everyday model",
         "the everyday model (the main one chat uses)"),
    Lane("coding", 11435, "Jarvis Ollama - Coding model",
         "the coding model"),
)

#: The address Jarvis itself talks to when `jarvis_hud.OLLAMA_URL` cannot be
#: read - Ollama's own default, which is what `jarvis_hud.py` falls back to.
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

#: How long the lane is given to answer `/api/tags` after its task is started.
#: Ninety seconds: an 8B model on this PC loads in well under a minute, and a
#: lane that has not answered in a minute and a half did not start. Long
#: enough to be honest, short enough that the owner is not left watching.
WAIT_S = 90.0

#: How often the lane is asked whether it is up yet, in seconds.
POLL_S = 3.0

#: How long after a settled start a second start is refused outright - the
#: window in which the task may have run and the lane still failed. The
#: in-memory state covers this; the number is what makes it visible, and what
#: a restart of the backend loses.
RECENT_S = WAIT_S + 30.0

#: How long one read of `schtasks` may take. It is a Task Scheduler query.
TASK_TIMEOUT_S = 20.0

#: One GET of a lane's `/api/tags` may take this long.
PROBE_TIMEOUT_S = 3.0

#: The phase words, which are also what the apps show. `down` is a verdict
#: about the lane; `unknown` is "nothing here can say" - never drawn as down.
PHASES = ("up", "starting", "down")

_STATE_LOCK = threading.Lock()

#: What this module knows right now. Replaced wholesale, so a reader never sees
#: half of a change. `None` means "nothing was started in this process", which
#: is not a claim about the lane - `status()` reads the lane itself and answers
#: that.
_STATE: Optional[dict] = None

#: Set while a watch thread is running, so one press cannot become two tasks.
_WATCHING = False


# ---------------------------------------------------------------------------
#   The lane Jarvis itself uses
# ---------------------------------------------------------------------------

def _hud_ollama_url() -> str:
    """`OLLAMA_URL` as the backend resolves it, or "" when nothing can say.

    Read from `jarvis_hud` when it is importable, because that module is what
    the chat itself uses (its own `OLLAMA_URL` line), and from the environment
    otherwise. A separate copy of the address is exactly how the desktop's
    health probe came to ask the wrong port (2026-10-13), so there is one.
    """
    try:
        import jarvis_hud
        url = getattr(jarvis_hud, "OLLAMA_URL", "")
        if url:
            return str(url)
    except Exception:
        pass
    return os.environ.get("OLLAMA_URL") or ""


def port_of(url: str) -> Optional[int]:
    """The port in an Ollama address, or None when it cannot be read.

    `http://127.0.0.1:11436` -> 11436. No port means Ollama's own default,
    11434, which is what a bare `http://127.0.0.1` means to every client. An
    address that is not this PC is None: there is no local task to start for a
    lane elsewhere, and guessing one would be the 2026-10-10 mistake with a
    button on it.
    """
    raw = str(url or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parsed = urllib.parse.urlsplit(raw)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return None
    if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return None
    return int(port) if port else 11434


def lane_for_port(port: Optional[int], lanes=None) -> Optional[Lane]:
    """The lane this PC starts on `port`, or None when no lane is known there."""
    if not port:
        return None
    for lane in (LANES if lanes is None else lanes):
        if lane.port == int(port):
            return lane
    return None


def target(lanes=None, *, url: Optional[str] = None) -> Optional[Lane]:
    """The lane the CHAT uses - `OLLAMA_URL`'s port - or None when this PC has
    no lane on it.

    Deliberately not "the everyday lane": the port comes from the address the
    chat talks to, so a PC pointed at the coding lane starts the coding lane.
    None means the chat is not pointed at a lane this module can start, and
    then the route says so in words rather than starting a lane nobody asked
    for.

    `url` overrides the address (the tests do this, so no check here can ever
    reach a real lane). Otherwise the address `install()` was given, otherwise
    the backend's own `OLLAMA_URL`.
    """
    if url is None:
        url = _ROUTE_URL or _hud_ollama_url() or DEFAULT_OLLAMA_URL
    return lane_for_port(port_of(url), lanes)


# ---------------------------------------------------------------------------
#   This PC's own tasks
# ---------------------------------------------------------------------------

def _run(argv: list, timeout: float) -> tuple:
    """(returncode, stdout bytes) for one program run as argv, never a shell."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout,
                              creationflags=creation)
    except (OSError, subprocess.SubprocessError):
        return None, b""
    return done.returncode, done.stdout or b""


def scheduled_tasks() -> tuple:
    """Every scheduled task whose name starts with 'Jarvis Ollama'.

    Read with `schtasks`, which ships with Windows and needs no module - the
    same read, and the same refusal to guess, as `tools/check_lanes.py`. Off
    Windows, or if `schtasks` is missing or refuses, this is `()`: a name typed
    from memory is the entire bug these two files exist after, so there is no
    fallback list.
    """
    code, raw = _run(["schtasks", "/query", "/fo", "csv", "/nh"], TASK_TIMEOUT_S)
    if code is None:
        return ()
    names = []
    for row in csv.reader(raw.decode("utf-8", errors="replace").splitlines()):
        if not row:
            continue
        name = row[0].lstrip("\\")
        if name.startswith("Jarvis Ollama"):
            names.append(name)
    return tuple(names)


def task_for(lane: Lane, tasks) -> str:
    """That lane's real task name on this PC, or "" when there is no such task."""
    for name in tasks or ():
        if name.startswith(lane.task_prefix):
            return name
    return ""


#: What a `schtasks /query /v` status word means. English Windows says
#: "Running"; the words below are what other locales print. Anything else is
#: UNKNOWN, and unknown never starts a second task on its own - it is only ever
#: a reason to WAIT (see `task_running`).
_RUNNING_WORDS = ("running", "wird ausgeführt", "en cours")
_READY_WORDS = ("ready", "bereit", "prêt", "disabled", "deaktiviert")


def task_running(name: str) -> Optional[bool]:
    """Is that task running now? `True`, `False`, or `None` for "cannot say".

    ONE read, one row (`schtasks /query /tn <name> /fo csv /nh /v`), and the
    status column is matched against the words above rather than against a
    column number - the column order is Windows' own. `None` is not "no": this
    answer only ever ADDS a reason to wait, so a locale nobody has seen costs
    nothing and can never cause a second start on its own.
    """
    if not name:
        return None
    code, raw = _run(["schtasks", "/query", "/tn", name, "/fo", "csv", "/nh", "/v"],
                     TASK_TIMEOUT_S)
    if code != 0 or not raw:
        return None
    for row in csv.reader(raw.decode("utf-8", errors="replace").splitlines()):
        for cell in row:
            word = str(cell or "").strip().lower()
            if word in _RUNNING_WORDS:
                return True
            if word in _READY_WORDS:
                return False
    return None


# ---------------------------------------------------------------------------
#   Is the lane answering?
# ---------------------------------------------------------------------------

def probe(port: int, timeout: float = PROBE_TIMEOUT_S) -> bool:
    """Does the lane on `port` answer Ollama's own `/api/tags`?

    `False` on EVERYTHING else - a refused connection, an HTTP error, junk, a
    timeout. "Something is listening" is not "a lane came back" (the rule
    `tools/check_lanes.py` was written around), and this answer decides whether
    the owner is told it came up.
    """
    url = f"http://127.0.0.1:{int(port)}/api/tags"
    try:
        request = urllib.request.Request(url)
        if jarvis_local_http is not None:
            with jarvis_local_http.urlopen(request, timeout) as response:
                body = response.read()
        else:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
    except Exception:
        return False
    try:
        payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
    except ValueError:
        return False
    return isinstance(payload, dict) and "models" in payload


# ---------------------------------------------------------------------------
#   What the apps read
# ---------------------------------------------------------------------------

def _set(**fields) -> None:
    global _STATE
    with _STATE_LOCK:
        state = dict(_STATE or {})
        state.update(fields)
        _STATE = state


def _snapshot() -> Optional[dict]:
    with _STATE_LOCK:
        return dict(_STATE) if _STATE else None


def reset() -> None:
    """Forget everything this process remembers. The tests use it; nothing in
    the running backend calls it."""
    global _STATE, _WATCHING
    with _STATE_LOCK:
        _STATE = None
        _WATCHING = False


def _host_reason() -> str:
    """Why nothing can be started here, in plain words, or "" on Windows."""
    if os.name == "nt":
        return ""
    return ("Starting a model lane is a Windows thing: this PC's own Task "
            "Scheduler holds the task that starts it, and this is not Windows.")


def _elapsed(state: Optional[dict], now: Optional[float] = None) -> Optional[float]:
    """Seconds since the start was asked for, or None when nothing was asked."""
    if not state:
        return None
    started = state.get("started_at")
    if not started:
        return None
    return max(0.0, round((now if now is not None else time.time()) - float(started), 1))


def _seconds(value: Optional[float]) -> str:
    """`12.0` -> `12 seconds`; None -> `a moment`."""
    if value is None:
        return "a moment"
    value = float(value)
    if value < 1:
        return "less than a second"
    whole = int(round(value))
    return f"{whole} second" + ("" if whole == 1 else "s")


def _phase_now(known: Optional[dict], up: bool, now: float) -> str:
    """The phase to report: the lane's own answer wins over anything remembered."""
    if up:
        return "up"
    if known and known.get("phase") == "starting":
        elapsed = _elapsed(known, now)
        return "starting" if (elapsed is not None and elapsed <= WAIT_S) else "down"
    return "down"


def status(lane: Optional[Lane] = None, *, probe_fn: Optional[Callable] = None,
           window: bool = True, tasks_fn: Optional[Callable] = None) -> dict:
    """What is true about the lane right now, as the apps draw it.

    `window` is False for a call that must touch nothing outside this process
    (the watch thread's own reads); on Windows the only other read is the Task
    Scheduler list, which decides whether a press is even possible. `tasks_fn`
    replaces that one read - the real thing by default - so a test can say what
    this PC's Task Scheduler holds without asking it.

    The answer always carries: `state` (up/starting/down), the lane's `key` and
    `port`, this PC's own `task` name (empty when this PC has none), whether a
    press would do anything (`can_start`) and why not (`why`), and - while a
    start is being watched - how long it has been (`elapsed_s`) and how long is
    left (`left_s`).
    """
    now = time.time()
    lane = lane or target()
    known = _snapshot()
    read_tasks = tasks_fn or scheduled_tasks
    out: dict = {
        "ok": True,
        "lane": lane.key if lane else "",
        "words": lane.words if lane else "",
        "port": lane.port if lane else None,
        "task": "",
        "state": "down",
        "can_start": False,
        "why": "",
        "started_at": None,
        "elapsed_s": None,
        "left_s": None,
        "waited_s": None,
        "message": "",
    }

    if lane is None:
        out["why"] = ("Jarvis is not pointed at a model lane on this PC, so "
                      "there is nothing here to start.")
        out["message"] = out["why"]
        return out

    check = probe_fn or probe
    up = bool(check(lane.port))
    if window:
        out["task"] = task_for(lane, read_tasks())

    out["state"] = _phase_now(known, up, now)
    elapsed = _elapsed(known, now)
    out["started_at"] = (known or {}).get("started_at")
    out["elapsed_s"] = elapsed

    if up:
        out["can_start"] = False
        out["why"] = "It is answering - nothing to do."
        if known and known.get("phase") in ("starting", "up"):
            out["waited_s"] = elapsed
            out["message"] = ("The local model came back"
                              + (f" after {_seconds(elapsed)}." if elapsed else "."))
        return out

    if out["state"] == "starting":
        left = max(0.0, round(WAIT_S - (elapsed or 0.0), 1))
        out["left_s"] = left
        out["why"] = "It is starting now."
        out["message"] = (f"Starting the local model. It has been "
                          f"{_seconds(elapsed)}; this can take up to a minute.")
        return out

    if not out["task"]:
        out["why"] = (f"This PC has no scheduled task whose name starts with "
                      f"\"{lane.task_prefix}\", so there is nothing to start. "
                      f"That task is what starts this lane at logon.")
        out["message"] = out["why"]
        return out

    if known and known.get("phase") == "down" and elapsed is not None \
            and elapsed < RECENT_S:
        out["why"] = ("Its task was started and the lane did not come up inside "
                      "the time it was given; it will not be started again "
                      "straight away.")
        out["message"] = str(known.get("message") or out["why"])
        return out

    out["can_start"] = True
    out["why"] = f"Nothing is answering on port {lane.port}."
    return out


# ---------------------------------------------------------------------------
#   Starting it, and watching
# ---------------------------------------------------------------------------

def _refused(message: str) -> dict:
    return {"ok": False, "changed": False, "state": "down",
            "can_start": False, "error": message, "message": message}


def _launch_task(task: str) -> tuple:
    """`schtasks /run /tn <task>` - the same call that starts his lane at
    logon. Never a shell, never a command line built from memory.

    It takes the task's NAME and builds the argv here, so `start()` has one
    thing to hand it and no caller can pass a different command shape.
    """
    code, _raw = _run(["schtasks", "/run", "/tn", str(task)], TASK_TIMEOUT_S)
    return (-1 if code is None else code), b""


def _begin(lane: Lane, task: str, now: float, *, running: bool) -> None:
    global _WATCHING, _STATE
    with _STATE_LOCK:
        _WATCHING = True
        _STATE = {
            "lane": lane.key, "port": lane.port, "task": task,
            "phase": "starting", "started_at": float(now),
            "already_running": bool(running), "message": "",
        }


def _finish(up: bool, now: float, note: str) -> None:
    global _WATCHING, _STATE
    with _STATE_LOCK:
        state = dict(_STATE or {})
        state["phase"] = "up" if up else "down"
        state["settled_at"] = float(now)
        state["waited_s"] = _elapsed(state, now)
        state["message"] = note
        _STATE = state
        _WATCHING = False


def start(lane: Optional[Lane] = None, *, probe_fn: Optional[Callable] = None,
          run_fn: Optional[Callable] = None, tasks_fn: Optional[Callable] = None,
          running_fn: Optional[Callable] = None, watch: bool = True,
          now: Optional[float] = None) -> tuple:
    """Start the lane's OWN task. Returns `(http_status, body)`.

    The rules, in order - each one is a way this could otherwise start
    something nobody asked for:

      1. the lane is answering -> nothing is started (200, `changed: false`);
      2. this is not Windows, or this PC has no such task -> refused, in words,
         and nothing is run (503/409) - a command naming a task that is not
         there is the 2026-10-10 failure this project already paid for;
      3. a start is already being watched -> refused (409), so one press cannot
         become two tasks;
      4. the PC's Task Scheduler says that task is running -> nothing is
         started (202, `changed: false`, "already running") and the lane is
         watched instead: it may just be loading a model;
      5. otherwise `schtasks /run` on that task, then the lane is watched until
         it answers or `WAIT_S` runs out.

    The answer is always immediate. "Starting" is not "started": the apps read
    `GET /api/model-lanes` until it settles, and only the lane really answering
    `/api/tags` turns it into `up`.
    """
    now = now if now is not None else time.time()
    check = probe_fn or probe
    launch = run_fn or _launch_task
    read_tasks = tasks_fn or scheduled_tasks
    read_running = running_fn or task_running
    lane = lane or target()

    if lane is None:
        return 409, _refused("Jarvis is not pointed at a model lane on this PC, "
                             "so there is nothing here to start.")

    if check(lane.port):
        out = status(lane, probe_fn=check, window=False, tasks_fn=read_tasks)
        return 200, dict(out, changed=False,
                         message="The local model is already answering - "
                                 "nothing was started.")

    host = _host_reason()
    if host:
        return 503, _refused(host)

    task = task_for(lane, read_tasks())
    if not task:
        return 409, _refused(
            "This PC has no scheduled task whose name starts with "
            f"\"{lane.task_prefix}\", so there is nothing to start. That task "
            "is what starts this lane at logon.")

    known = _snapshot()
    with _STATE_LOCK:
        watching = _WATCHING
    if watching:
        return 409, _refused("That lane is already being started, and it has "
                             "not answered yet. Nothing was started a second "
                             "time.")
    if known and known.get("task") == task and known.get("phase") == "starting" \
            and (now - float(known.get("started_at") or 0)) < WAIT_S:
        out = status(lane, probe_fn=check, window=False, tasks_fn=read_tasks)
        return 202, dict(out, changed=False, waiting=True,
                         message="That lane is already starting. Nothing was "
                                 "started a second time.")

    if read_running(task) is True:
        _begin(lane, task, now, running=True)
        if watch:
            _spawn_watch(lane, check, now)
        out = status(lane, probe_fn=check, window=False, tasks_fn=read_tasks)
        return 202, dict(out, changed=False, waiting=True,
                         message=f"Its own task (\"{task}\") is already "
                                 f"running, so nothing was started. The lane "
                                 f"has not answered yet - it may be loading "
                                 f"the model.")

    code, _out = launch(task)
    if code != 0:
        return 502, _refused(
            f"The PC refused to start its own task \"{task}\" "
            f"(schtasks exited {code}). Nothing was started; the lane is still "
            f"down.")

    _begin(lane, task, now, running=False)
    if watch:
        _spawn_watch(lane, check, now)
    out = status(lane, probe_fn=check, window=False, tasks_fn=read_tasks)
    return 202, dict(out, changed=True, waiting=True,
                     message=f"Started this PC's own task \"{task}\", which is "
                             f"what starts this lane at logon. Waiting for it "
                             f"to answer.")


def _spawn_watch(lane: Lane, check: Callable, now: float) -> None:
    thread = threading.Thread(target=_watch, args=(lane, check, now),
                              name="jarvis-model-lane-watch", daemon=True)
    thread.start()


def _watch(lane: Lane, check: Callable, now: float = 0.0, *,
           sleep: Callable = time.sleep, deadline_s: float = WAIT_S) -> dict:
    """Ask the lane until it answers, or until it has had long enough.

    Never raises, and always leaves a verdict behind: a watch that died would
    otherwise leave the apps on "starting" for ever. Its own answer decides
    everything - no model name, no log line, only `/api/tags`.
    """
    global _WATCHING
    try:
        waited = 0.0
        while waited < deadline_s:
            sleep(POLL_S)
            waited += POLL_S
            try:
                if check(lane.port):
                    _finish(True, time.time(),
                            "The local model is answering again.")
                    _publish(lane, True, waited)
                    return _snapshot() or {}
            except Exception:
                continue
        _finish(False, time.time(),
                f"The lane did not answer within {_seconds(deadline_s)} of its "
                f"task being started, so it did not come up. It is still down.")
        _publish(lane, False, deadline_s)
        return _snapshot() or {}
    except Exception as exc:  # never leave the apps on "starting"
        _finish(False, time.time(),
                f"Watching the lane failed ({type(exc).__name__}), so it is not "
                f"known to be up. It is still down.")
        return _snapshot() or {}
    finally:
        with _STATE_LOCK:
            _WATCHING = False


def _publish(lane: Lane, up: bool, waited: float) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish("model", {
            "lane": lane.key, "port": lane.port, "up": bool(up),
            "waited_s": round(float(waited), 1)})
    except Exception:
        pass


# ---------------------------------------------------------------------------
#   The routes
# ---------------------------------------------------------------------------

def handle_get() -> dict:
    """`GET /api/model-lanes` - the lane's state, and whether a press would do
    anything. A read: it starts nothing. It does ask the lane one question."""
    return status(probe_fn=_PROBE_FOR_ROUTES)


def handle_post(body=None) -> tuple:
    """`POST /api/model-lanes/start`. An empty body starts the lane the chat
    uses - there is deliberately no `{"lane": "..."}` and no `{"all": true}`,
    so no client can start a lane the chat is not on, and nothing can start
    both at once."""
    if body is not None and body != {}:
        if not isinstance(body, dict):
            return 400, _refused("the body must be a JSON object")
        unknown = [k for k in body if k != "why"]
        if unknown:
            return 400, _refused(
                "that route takes no options: it starts the one lane Jarvis "
                f"talks to. Not understood: {', '.join(sorted(unknown))}")
    lane = target()
    if lane is None:
        return 409, _refused("Jarvis is not pointed at a model lane on this PC, "
                             "so there is nothing here to start.")
    code, out = _START_FOR_ROUTES(lane)
    if code in (200, 202) and isinstance(out, dict):
        out.setdefault("ok", True)
    return code, out


#: The two seams the ROUTE tests replace, so exercising the wiring cannot ask a
#: real lane or start a real task. They are the module's own functions by
#: default - the running backend always uses the real ones - and the two route
#: handlers above are the only callers.
_PROBE_FOR_ROUTES: Callable = probe
_START_FOR_ROUTES: Callable = start

#: The address the routes were installed with. `install()` never passes one in
#: the running backend: `target()` then reads `jarvis_hud.OLLAMA_URL`, which is
#: the address the chat itself uses. It exists so a test can install the routes
#: without the machine's own environment deciding which lane they mean.
_ROUTE_URL: str = ""


GET_ROUTE = "/api/model-lanes"
START_ROUTE = "/api/model-lanes/start"


def install(handler_cls, *, origin_ok, token_ok, read_body, url: str = "") -> str:
    """Wire the two routes into the backend's own Handler, the way every other
    module here does, and return the line the start-up banner prints.

    Both routes are behind the backend's own origin and token checks - the same
    gate as `/api/status` - because this one can start a program, even though
    the program is the owner's own task.

    `url` is for the tests only: the start-up call passes none, and `target()`
    then reads `jarvis_hud.OLLAMA_URL`, the address the chat itself uses.
    """
    global _ROUTE_URL
    if url:
        _ROUTE_URL = str(url)
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_model_lanes", False):
        return "  model lanes ready - a lane that is down can be started (already on)"

    def allowed(self):
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = str(getattr(self, "path", "") or "").split("?", 1)[0].rstrip("/")
        if route != GET_ROUTE:
            return get0(self)
        if not allowed(self):
            return None
        try:
            return self._send(200, handle_get())
        except Exception as exc:
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self):
        route = str(getattr(self, "path", "") or "").split("?", 1)[0].rstrip("/")
        if route != START_ROUTE:
            return post0(self)
        if not allowed(self):
            return None
        try:
            raw = read_body(self) if read_body is not None else b""
            body = json.loads(raw or b"{}") if raw else {}
        except (ValueError, json.JSONDecodeError) as exc:
            return self._send(400, {"error": str(exc)})
        try:
            code, out = handle_post(body)
        except Exception as exc:
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
        return self._send(code, out)

    do_GET._jarvis_model_lanes = True   # type: ignore[attr-defined]
    do_POST._jarvis_model_lanes = True  # type: ignore[attr-defined]
    handler_cls.do_GET, handler_cls.do_POST = do_GET, do_POST
    return ("  model lanes ready - a lane that is down can be started from "
            "either app")
