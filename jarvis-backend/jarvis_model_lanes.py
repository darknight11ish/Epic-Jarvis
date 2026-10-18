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

AND NOW IT DOES IT ITSELF. The owner's decision, 2026-10-14: *"Also restart the
lane automatically when it dies."* PR #409 made both apps SAY it and act on
nothing; the button above waits for the owner to press it, and the defect is
that nobody is there to press it at 08:19. So the BACKEND watches the lane
itself - one daemon thread, one loopback GET of the lane's own `/api/tags`
every `CHECK_S`, no model call and no token spent - and restarts it through
exactly the same `start()` as the button: the same lookup of HIS OWN task by
the stable half of its name, the same `["schtasks", "/run", "/tn", <name>]` as
argv, the same watch until the lane really answers. There is no second way to
start a lane in this module, and no hand-rolled `ollama serve` anywhere in it.
It lives in the backend rather than in a desktop window because the phone must
get the same lane back, and the phone is often the only thing looking at the
PC.

THE LOOP MUST NOT FIGHT ITSELF. It does not start anything while the lane
answers; it does not start a second instance while one is starting (`_WATCHING`
is one of three independent guards - `start()`'s own refusals and the Task
Scheduler's own "Running" are the other two); and it does not restart in a tight
loop: `DOWN_BEATS` beats of being down before the first attempt, then
`COOLDOWN_S` doubling between attempts, and at most `AUTO_ATTEMPTS` automatic
starts in one episode. **What happens at the cap:** Jarvis stops trying, the
state goes back to plain `down`, and what remains is exactly the standing
warning PR #409 built - still drawing on both apps, with the button still
there - plus one plain sentence saying it has stopped and why. The episode ends
there. It does not begin again until the lane has really been back (`up` for
`SETTLED_S` - a flap is not a recovery) or the owner starts it himself.

A DELIBERATE STOP CANNOT BE TOLD FROM A CRASH, and this module does not pretend
otherwise. A dead process carries no intent: `schtasks` reports the same
"Ready" whether the lane crashed or was closed on purpose, and there is no
second signal on this PC that means "I meant that". So the answer is not a
cleverer test. It is the owner's own switch (`automatic()`, on by default
because he asked for this, off in one press from either app and immediate), plus
the fact that every automatic restart is SAID - in the apps, in the backend's
own plain words, which is what `auto_note` carries. THE RESIDUAL RISK IS REAL
AND IS NOT HIDDEN: with the switch on, Jarvis will start a lane the owner
stopped deliberately, and will tell him it did. `docs/ARCHITECTURE.md` §8 and
`docs/JARVIS-API.md` §137.3 say the same thing in the same words.

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

THE AUTOMATIC RESTART IS A DIFFERENT CASE, and it is argued rather than
assumed, because the press above is gone. The house rule that governs it is the
one `jarvis-framework.toml` already carries for Docker: *"starting a service
gives Jarvis more, so it asks"* (`docker_service_start = "ask"`). This module
does not go through the gate as that action, and the difference is the thing to
argue, not to wave away. Four reasons, in the order they decide it:

  * WHAT IS STARTED IS NOT A NEW GRANT. A container is a capability Jarvis was
    given and did not have; this lane is the capability Jarvis *is*, the one the
    chat is pointed at, and the one this PC already starts by itself at every
    logon, unattended, with no card and nobody asked. A card here would be
    stricter than the machine's own behaviour, and it would be a card whose only
    content is "run the task that runs anyway".
  * A CARD COULD NOT BE ANSWERED WHEN IT IS NEEDED. The lane dies at 08:19 with
    nobody at a screen. An `ask` card would sit for the 900-second timeout and
    expire, the lane would stay dead, and the next attempt would raise another
    one - which is the defect the owner asked to have fixed, plus a queue of
    expired cards, which is how a person learns that cards are noise.
  * IT IS BOUNDED, REVERSIBLE AND SAID. Three automatic attempts per episode and
    then the plain warning; off in one immediate press from either app; and every
    restart is spoken about in the apps, in this module's own words. It opens no
    socket that was not already open, reaches nothing off this PC, carries no
    data and needs no credential.
  * NOTHING IS AUTO-APPROVED, AND THERE IS NO SECOND PATH. The automatic restart
    raises no card and answers no card - rule 4 is untouched, because answering
    a card is the only thing that rule forbids, and no card exists here. It calls
    the same `start()` the button calls, so it cannot reach an action the owner's
    own press could not, and it can never start a lane the chat is not on. One
    lane, never both, and no latch is cleared anywhere in this file.

So: no card, and no new tier line either. The owner's own instruction of
2026-10-14 is the grant, the switch is how he takes it back, and the sentence in
the apps is how he finds out it was used.

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
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from pathlib import Path
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

#: How often the backend asks whether the lane is answering, in seconds, once
#: `watch_start()` has armed it. One loopback GET of the lane's own
#: `/api/tags` - the same question the apps' 90-second beat asks, no model call,
#: nothing generated and nothing spent. Thirty seconds rather than ninety
#: because this one ACTS: a lane that has been down for a minute and a half is
#: a minute and a half of the owner waiting, and the probe costs one refused
#: connection while everything is fine.
CHECK_S = 30.0

#: How many beats in a row the lane must be down before the FIRST automatic
#: start. Two, so about a minute: a single missed probe is not a dead lane - a
#: lane that is loading a model, a task that has just been launched and a
#: moment of paging all answer `False` once and then answer normally. It is a
#: grace period, not a reading of the owner's intent (see the module header:
#: intent is not readable from a dead process).
DOWN_BEATS = 2

#: How many automatic starts Jarvis will spend on ONE episode - the run of
#: attempts between one real recovery and the next. Three: enough that a single
#: failed launch, a stuck task or a slow first load is survivable, few enough
#: that a lane which is genuinely broken is not hammered. At this number it
#: stops and the warning stands.
AUTO_ATTEMPTS = 3

#: How long after an automatic start the next one is refused, in seconds. Five
#: minutes, and it DOUBLES with each further attempt in the episode (5, then
#: 10), so the three attempts land about a minute, six minutes and sixteen
#: minutes after the lane died - which is a person's timescale, and far longer
#: than the 90 seconds the lane is given to come up, so a second attempt can
#: never overlap the first.
COOLDOWN_S = 300.0

#: How long the lane must be answering before the episode is over and the
#: attempts are forgiven, in seconds. Ten minutes: a lane that answers and dies
#: again inside this window has flapped, not recovered, and it must not be
#: handed a fresh three attempts every time it twitches.
SETTLED_S = 600.0

#: How long an automatic restart is spoken about in the apps, in seconds. Half
#: an hour, and it is the backend that decides - so the desktop and the phone
#: cannot disagree about whether it is still worth mentioning, and neither has
#: to keep a clock of its own. A note that is still TRUE does not expire: the
#: gave-up sentence stands while Jarvis really has given up.
NOTE_S = 1800.0

#: This module's one switch, in the owner's own config folder - never in the
#: repository, never in the toml (no route here may write the toml), the same
#: shape as `jarvis_tutorials.py`'s own small file.
SETTING_NAME = "model-lanes.json"

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

#: What the automatic restarter knows, for the episode it is in. Replaced
#: wholesale by `_forget_episode()`, so a reader never sees half of it. An
#: EMPTY dict is "the lane has been fine": nothing has been tried and nothing
#: has been said.
_AUTO: dict = {}

#: The armed watcher thread and the switch that stops it. Armed by
#: `watch_start()` from the one place the backend wires this feature up - the
#: install block `model-lanes.patch` adds - and NEVER by `install()` itself.
#: That is deliberate and it is the safety property of this whole feature: a
#: test, or any other caller, that installs the routes cannot possibly start a
#: lane on the owner's PC as a side effect.
_WATCHER: Optional[threading.Thread] = None
_WATCHER_STOP: Optional[threading.Event] = None

#: The file this module's one switch lives in. `watch_start()` and the routes
#: never set it: the running backend always uses the owner's own config folder.
#: It exists so a test writes a throwaway file rather than the owner's.
_SETTING_FILE: Optional[str] = None


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
        import jarvis_child_env
        done = subprocess.run(argv, capture_output=True, timeout=timeout,
                              creationflags=creation,
                              env=jarvis_child_env.inherited())
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
    the running backend calls it. The armed watcher, if there is one, is left
    running and is stopped with `watch_stop()`."""
    global _STATE, _WATCHING, _AUTO
    with _STATE_LOCK:
        _STATE = None
        _WATCHING = False
        _AUTO = {}


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
    episode = _auto_snapshot()
    read_tasks = tasks_fn or scheduled_tasks
    switched_on = automatic()
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
        # What the automatic restarter is doing, from the backend's own state,
        # so both apps draw one decision rather than each forming its own.
        "auto": switched_on,
        "auto_attempts": int(episode.get("attempts") or 0),
        "auto_limit": AUTO_ATTEMPTS,
        "auto_capped": bool(episode.get("capped")),
        # The switch's own sentence is reported whenever the switch is OFF,
        # whether the lane is up or down, and never when this PC has no lane to
        # restart: that is what gives the owner a press to turn it back on at
        # any time, from either app, without a settings page of its own.
        "auto_note": ("" if lane is None
                      else OFF_NOTE if not switched_on
                      else _note_of(episode, now)),
        "auto_note_at": episode.get("note_at"),
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
#   The one switch: does Jarvis start it again by itself?
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    """Where the owner's own state lives - never a repository folder."""
    try:
        import jarvis_framework as fw
        where = getattr(fw, "CONFIG_DIR", None)
        if where:
            return Path(where)
    except Exception:
        pass
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def _setting_path() -> Path:
    """This module's own small file, beside the rest of the owner's state."""
    if _SETTING_FILE:
        return Path(_SETTING_FILE)
    return _config_dir() / SETTING_NAME


def automatic() -> bool:
    """Does Jarvis start the lane again by itself when it finds it down?

    ON by default, because the owner decided it in those words on 2026-10-14 -
    *"Also restart the lane automatically when it dies"* - and a feature that
    ships off is not the feature he decided on. So a missing or unreadable file
    is ON and not an error: this switch exists to turn it OFF.

    Read on every call rather than cached, so the watcher thread and the two
    apps can never disagree about it and a press takes effect on the next beat
    at the latest. It is one small local file, read at most a few times a
    minute, and nothing here is on the chat's path.
    """
    try:
        raw = json.loads(_AUTO_SETTING().read_text(encoding="utf-8"))
    except Exception:
        return True
    if not isinstance(raw, dict):
        return True
    value = raw.get("automatic")
    return True if value is None else bool(value)


def set_automatic(on: bool) -> bool:
    """Turn it off, or back on. Immediate in both directions, and no card.

    OFF only narrows what Jarvis does, so it is never gated ("stopping is never
    gated", ARCHITECTURE §3). ON adds nothing the owner's own press does not do
    in the same second - the button beside this switch runs the very same task,
    with no card - so a card here would be stricter than the button it sits
    next to. The module header carries the whole argument.

    True when it is on disk. Written by replace, so a reader never sees half of
    it, and keys this module does not know about are kept.
    """
    path = _AUTO_SETTING()
    try:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            current = {}
        if not isinstance(current, dict):
            current = {}
        current["automatic"] = bool(on)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".model-lanes-",
                                   suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(current, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
#   Restarting it by itself
# ---------------------------------------------------------------------------

def _auto_snapshot() -> dict:
    with _STATE_LOCK:
        return dict(_AUTO)


def _auto_put(**fields) -> None:
    with _STATE_LOCK:
        _AUTO.update(fields)


def _forget_episode() -> None:
    """A real recovery: nothing has been tried, and nothing needs saying."""
    global _AUTO
    with _STATE_LOCK:
        _AUTO = {}


#: What one beat decided. `restart` is the only one that starts anything.
AUTO_ACTIONS = ("off", "up", "watching", "wait", "cooling", "capped", "restart")


def auto_step(up, now, *, enabled=True, watching=False, beats=0, attempts=0,
              last_attempt_at=None, capped=False, down_beats=DOWN_BEATS,
              limit=AUTO_ATTEMPTS, cooldown=COOLDOWN_S) -> str:
    """What to do about the lane, given everything known about it. Pure.

    Every argument is passed in, and nothing is read from the module or from
    the clock - so `test_model_lanes.py` can hold every branch (the grace
    period, the cooldown, the doubling, the cap) without a thread, a socket or
    a second of waiting. The ORDER is the rule:

      1. switched off         -> "off"      the owner's own switch
      2. the lane answers     -> "up"       nothing is ever started
      3. a start is in flight -> "watching" never a second instance
      4. not down long enough -> "wait"     one missed probe is not a dead lane
      5. already capped       -> "capped"   the standing warning is what remains
      6. no attempts left     -> "capped"   and the caller marks the episode
      7. inside the cooldown  -> "cooling"
      8. otherwise            -> "restart"
    """
    if not enabled:
        return "off"
    if up:
        return "up"
    if watching:
        return "watching"
    if int(beats) < int(down_beats):
        return "wait"
    if capped:
        return "capped"
    if int(attempts) >= int(limit):
        return "capped"
    if last_attempt_at is not None:
        # The gap grows with each attempt spent: 5 minutes, then 10.
        gap = float(cooldown) * (2 ** max(0, int(attempts) - 1))
        if (float(now) - float(last_attempt_at)) < gap:
            return "cooling"
    return "restart"


def _clock(now: float) -> str:
    """`08:19` - the time of day, in the owner's own timezone."""
    try:
        return time.strftime("%H:%M", time.localtime(float(now)))
    except Exception:
        return "just now"


#: Said while the switch is off and the lane is down. The apps show it with the
#: one press that turns it back on, so the reason and the remedy are one line.
OFF_NOTE = ("Jarvis is not starting the local model by itself: automatic "
            "restarting is off.")


def _gave_up_note(attempts: int) -> str:
    """What remains when the cap is reached: the warning, and this."""
    return (f"Jarvis started the local model {int(attempts)} times and it did "
            f"not come up, so it has stopped trying. You can still start it "
            f"yourself.")


def _note_of(state: dict, now: float) -> str:
    """The sentence the apps should show, from the episode's own state.

    HALF AN HOUR for anything that has happened and finished - a restart is
    news, not a permanent mark, and a line nobody can get rid of is one the
    owner learns to read past. A sentence that is still TRUE does not expire:
    "it has stopped trying" and "you turned this off" stand while they are
    still the case. The app draws whatever this returns and composes nothing of
    its own, so the two apps cannot come to different words for one fact.
    """
    note = str(state.get("note") or "")
    if not note:
        return ""
    if state.get("note_kind") in ("gave-up", "off"):
        return note
    at = state.get("note_at")
    if at is None or (float(now) - float(at)) > NOTE_S:
        return ""
    return note


def _note_for_start(now: float, code, out) -> tuple:
    """What to say about an automatic start just asked for:
    `(sentence, is_something_being_watched)`.

    The sentence is built HERE and nowhere else. Both apps draw this string
    verbatim - the same rule the approval notice follows (ARCHITECTURE §3): a
    client that composes its own summary from fields has reopened the hole on
    the surface where it is least recoverable, and it is how two apps come to
    say two different things about one event.
    """
    said = str((out or {}).get("message") or (out or {}).get("error") or "").strip()
    when = _clock(now)
    if code in (200, 202):
        if (out or {}).get("changed"):
            return (f"Jarvis started the local model again at {when}, because "
                    f"it was not running. It is waiting for it to answer.", True)
        return (f"Jarvis found the task that starts the local model already "
                f"running at {when}, so it started nothing and is waiting for "
                f"the model to answer.", True)
    return (f"Jarvis tried to start the local model at {when} and your PC "
            f"would not run its own task"
            + (f": {said}" if said else "."), False)


def auto_tick(now: Optional[float] = None, *,
              lane: Optional[Lane] = None,
              probe_fn: Optional[Callable] = None,
              start_fn: Optional[Callable] = None) -> dict:
    """One beat of the automatic restarter. Returns what it decided.

    It starts something only when the decision is `restart`, and then it goes
    through `start()` - the same one action the button uses, with the same
    refusals - so there is no second way to start a lane here. The probe is the
    lane's own `/api/tags` on loopback: no model call, no token, nothing
    generated.

    `lane` is for the tests, exactly as it is on `start()` and `status()`: the
    running backend passes none, and the lane is then the one the CHAT uses.
    """
    now = time.time() if now is None else float(now)
    check = probe_fn or _AUTO_PROBE
    launch = start_fn or _AUTO_START
    lane = lane or target()
    if lane is None:
        # Not pointed at a lane on this PC: there is nothing here to watch.
        return {"ok": True, "action": "off", "lane": "", "note": ""}

    state = _auto_snapshot()
    enabled = automatic()
    with _STATE_LOCK:
        watching = _WATCHING
    up = bool(check(lane.port))
    beats = int(state.get("beats") or 0)
    attempts = int(state.get("attempts") or 0)
    capped = bool(state.get("capped"))
    change: dict = {}

    if up:
        # The lane is answering. A start that was in flight has arrived - and
        # only a REAL recovery forgives the attempts: ten minutes of answering,
        # not one lucky probe.
        up_since = state.get("up_since") or now
        change["up_since"] = up_since
        change["beats"] = 0
        if state.get("awaiting"):
            change.update(
                awaiting=False, note_kind="came-back", note_at=now,
                note=(f"Jarvis restarted the local model by itself at "
                      f"{_clock(state.get('attempt_at') or now)}, and it is "
                      f"answering now."))
        elif state.get("note_kind") == "gave-up":
            # It came back without another attempt, so the gave-up sentence is
            # no longer true.
            change.update(note_kind="", note="", note_at=None)
        if capped and (float(now) - float(up_since)) >= SETTLED_S:
            change.update(capped=False, attempts=0, last_attempt_at=None)
        _auto_put(**change)
        return {"ok": True, "action": "up", "lane": lane.key,
                "note": _note_of({**state, **change}, now)}

    # Not answering. A beat only counts while nothing is being tried.
    change["up_since"] = None
    if watching:
        action = "watching"
    else:
        beats += 1
        change["beats"] = beats
        action = auto_step(False, now, enabled=enabled, watching=False,
                           beats=beats, attempts=attempts,
                           last_attempt_at=state.get("last_attempt_at"),
                           capped=capped)
        if state.get("awaiting"):
            # The watch this module armed has settled, and the lane is still
            # not answering. Said exactly that way: "it came up and died again"
            # is a fact a probe 30 seconds later cannot tell apart from "it
            # never came up", so the sentence claims neither.
            change.update(
                awaiting=False, note_kind="failed", note_at=now,
                note=(f"Jarvis started the local model at "
                      f"{_clock(state.get('attempt_at') or now)}, and it is not "
                      f"answering now, so it is still down."))

    if action == "off":
        change.update(note_kind="off", note_at=now, note=OFF_NOTE)
        _auto_put(**change)
        return {"ok": True, "action": "off", "lane": lane.key, "note": OFF_NOTE}

    if action == "capped":
        if not capped:
            change.update(capped=True, note_kind="gave-up", note_at=now,
                          note=_gave_up_note(attempts))
        _auto_put(**change)
        return {"ok": True, "action": "capped", "lane": lane.key,
                "note": _note_of({**state, **change}, now)}

    if action in ("watching", "wait", "cooling"):
        _auto_put(**change)
        return {"ok": True, "action": action, "lane": lane.key,
                "note": _note_of({**state, **change}, now)}

    # `restart`: spend one attempt, then the ONE action. The count is written
    # BEFORE the call, so a start that throws still costs an attempt and cannot
    # become a loop.
    change.update(attempts=attempts + 1, last_attempt_at=now, attempt_at=now,
                  awaiting=True, note_kind="starting", note_at=now,
                  note=f"Jarvis is starting the local model again at "
                       f"{_clock(now)}, because it was not running.")
    _auto_put(**change)
    try:
        code, out = launch(lane)
    except Exception as exc:
        code, out = 502, {"error": f"{type(exc).__name__}: {exc}"}
    text, watched = _note_for_start(now, code, out)
    _auto_put(awaiting=bool(watched), note=text, note_kind="start", note_at=now)
    return {"ok": True, "action": "restart", "lane": lane.key, "code": code,
            "changed": bool((out or {}).get("changed")), "note": text}


def _watch_loop(stop: threading.Event, tick: Callable, beat: float) -> None:
    """One beat at a time until stopped. Never lets an exception end it: a
    watcher that died would leave the lane down with nothing trying."""
    while not stop.wait(beat):
        try:
            tick()
        except Exception:
            pass


def watch_start(*, tick: Optional[Callable] = None,
                check_s: Optional[float] = None) -> str:
    """Arm the automatic restarter, and return the line the banner prints.

    Called from the ONE place the backend wires this feature up - the install
    block `model-lanes.patch` adds, one line after `install()` - and never from
    `install()` itself. That is the safety property of this feature: a test, or
    any other caller, that installs the routes cannot start a lane on the
    owner's PC as a side effect of testing the wiring.

    `tick` and `check_s` are the tests' seams. The running backend passes
    neither, so one beat is `auto_tick()` - the real probe and the real
    `start()` - and the beat is `CHECK_S`.
    """
    global _WATCHER, _WATCHER_STOP
    if _WATCHER is not None and _WATCHER.is_alive():
        return "  lanes      automatic restart is already watching"
    host = _host_reason()
    if host:
        return "  lanes      automatic restart is OFF here: " + host
    beat = CHECK_S if check_s is None else max(0.01, float(check_s))
    stop = threading.Event()
    _WATCHER_STOP = stop
    _WATCHER = threading.Thread(target=_watch_loop,
                                args=(stop, tick or auto_tick, beat),
                                name="jarvis-model-lane-auto", daemon=True)
    _WATCHER.start()
    return (f"  lanes      a lane that dies is started again by itself, "
            f"checked every {int(beat)}s")


def watch_stop() -> bool:
    """Stop the automatic restarter, if one is armed. True when one was.

    Nothing in the running backend calls this. It is here for the tests, and
    for anyone who wants the watcher off without stopping Jarvis.
    """
    global _WATCHER, _WATCHER_STOP
    stop, _WATCHER_STOP = _WATCHER_STOP, None
    thread, _WATCHER = _WATCHER, None
    if stop is None:
        return False
    stop.set()
    if thread is not None:
        thread.join(timeout=2.0)
    return True


#: The two seams the AUTOMATIC tests replace, so exercising the loop cannot ask
#: a real lane or start a real task. They are the module's own functions by
#: default - the running backend always uses the real ones - and `auto_tick` is
#: the only caller.
_AUTO_PROBE: Callable = probe
_AUTO_START: Callable = start
#: And the one seam for the switch's own file, so a test writes a throwaway.
_AUTO_SETTING: Callable = _setting_path


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


def handle_auto_post(body=None) -> tuple:
    """`POST /api/model-lanes/auto` - whether Jarvis starts the lane itself.

    `{"on": true}` or `{"on": false}`. Both are immediate and neither raises a
    card - OFF only narrows what Jarvis does, and ON is the same action the
    button beside it takes in the same second. It takes no lane name and no
    "all": this is one fact about this PC's one lane, so there is nothing here
    to aim at another lane or at both. `docs/JARVIS-API.md` §137.3 has the whole
    argument, and the module header has the same one.
    """
    if not isinstance(body, dict):
        return 400, _refused("the body must be a JSON object")
    unknown = [k for k in body if k not in ("on", "why")]
    if unknown:
        return 400, _refused(
            "that route takes one option, \"on\": true or false. Not "
            f"understood: {', '.join(sorted(unknown))}")
    if "on" not in body:
        return 400, _refused("that route takes one option, \"on\": true or false")
    on = bool(body.get("on"))
    if not set_automatic(on):
        return 500, _refused("This PC could not write its own setting file, so "
                             "nothing changed.")
    lane = target()
    return 200, dict(status(lane, probe_fn=_PROBE_FOR_ROUTES), changed=True,
                     message=("Jarvis will start the local model again by itself "
                              "when it finds it is not running."
                              if on else
                              "Jarvis will leave the local model alone and say "
                              "it is not running - you can still start it "
                              "yourself."))


GET_ROUTE = "/api/model-lanes"
START_ROUTE = "/api/model-lanes/start"
AUTO_ROUTE = "/api/model-lanes/auto"


def install(handler_cls, *, origin_ok, token_ok, read_body, url: str = "") -> str:
    """Wire the three routes into the backend's own Handler, the way every other
    module here does, and return the line the start-up banner prints.

    All three are behind the backend's own origin and token checks - the same
    gate as `/api/status` - because one of them can start a program, even
    though the program is the owner's own task, and another can decide that
    Jarvis starts it by itself.

    This does NOT arm the automatic restarter. That is `watch_start()`, called
    one line later by the same install block - so nothing that merely installs
    these routes can start a lane on this PC.

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
        if route not in (START_ROUTE, AUTO_ROUTE):
            return post0(self)
        if not allowed(self):
            return None
        try:
            raw = read_body(self) if read_body is not None else b""
            body = json.loads(raw or b"{}") if raw else {}
        except (ValueError, json.JSONDecodeError) as exc:
            return self._send(400, {"error": str(exc)})
        try:
            code, out = (handle_post(body) if route == START_ROUTE
                         else handle_auto_post(body))
        except Exception as exc:
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
        return self._send(code, out)

    do_GET._jarvis_model_lanes = True   # type: ignore[attr-defined]
    do_POST._jarvis_model_lanes = True  # type: ignore[attr-defined]
    handler_cls.do_GET, handler_cls.do_POST = do_GET, do_POST
    return ("  model lanes ready - a lane that is down can be started from "
            "either app, and Jarvis starts it again by itself when you let it")
