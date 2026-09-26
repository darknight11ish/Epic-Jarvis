"""jarvis_stop_all.py - "Stop everything": one press halts whatever Jarvis is
doing, and asks nobody first.

The owner's decision of 2026-09-25 (CLAUDE.md, after reviewing the "Build
Your Own Jarvis" prompt pack): a "stop everything" hotkey on the desktop that
halts any action Jarvis is taking on the screen at once. The phone gets a
"Stop everything" button that calls the same route, with the same words.

WHAT ONE PRESS DOES (POST /api/stop_all)

    1. A task that is running - computer control, browser control, phone
       control - stops before its next step (jarvis_task_control's own Stop,
       the one the Stop button already uses). A paused task is forgotten.
    2. The chat answer being written now uses no more tools. Every tool call
       it asks for from here on is refused before it reaches the approval
       gate, and one it already asked about is not run even if its card is
       approved afterwards. The next question works normally.
    3. Everything that registered a stopper here (below) is told to stop:
       focus sessions, and whatever comes later.
    4. Speech is stopped by each app itself, on its own speaker - the PC's
       backend does not play sound. The desktop's hotkey and the phone's
       button stop their own speech before they even call this route, so a
       dead link never keeps Jarvis talking.

It answers what it stopped, in plain sentences, and "Nothing was running"
when there was nothing.

WHAT IT NEVER DOES

    - It never approves, denies or answers an approval card. A card that is
      waiting stays waiting - but see 2: approving it does not make the
      stopped answer act.
    - It never starts, resumes or wakes anything.
    - It never needs a card, and it is never held on a stale event stream:
      stopping only ever makes Jarvis do less (rule 4 blocks ACTING on a
      stale stream, and this is the opposite of acting).
    - It needs the pairing token, like every other route.

WHAT IT CANNOT DO, SAID PLAINLY

    - One step that has already started finishes. A click that is being
      made, a command already running, one web page loading: the stop lands
      before the NEXT step. The three control modules read their checkpoint
      before every step, and that is the only place a stop can land without
      leaving something half done.
    - A reminder or timer that goes off later still goes off: it is not an
      action on the screen, and the one scheduler has its own pause.

REGISTERING A STOPPER (for other features - focus sessions first)

    import jarvis_stop_all
    jarvis_stop_all.register("focus", lambda: "The focus session ended.")
    ...
    jarvis_stop_all.unregister("focus")

A stopper takes no arguments and returns one short sentence saying what it
stopped, or None when it had nothing running (then nothing is said about it).
It must be quick and must not wait for anything: every stopper is called in
turn, inside the owner's request. One that raises is reported as "could not
be stopped" and the others still run. Registering under a name that is
already there replaces the older stopper.

WHY A SHIPPED MODULE AND A WRAPPER, NOT A ROUTE IN jarvis_hud.py

The same shape as jarvis_owner_check.py: stop-all.patch adds one call at
start-up, `install(Handler, ...)`, which wraps the server's POST handler so
POST /api/stop_all is answered here, after the server's own origin and token
checks. Every rule lives in this file, where it can be tested without the
owner's jarvis_hud.py.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional
from urllib.parse import urlsplit

ROUTE = "/api/stop_all"

#: The words both apps use for the control. The desktop's hotkey is called
#: this in Settings, and the phone's button says it.
LABEL = "Stop everything"

NOTHING = "Nothing was running, so there was nothing to stop."

#: The longest sentence kept from one stopper. A stopper's words are shown in
#: a notification and on the phone; they are a sentence, not a report.
MAX_SAID = 200

_lock = threading.Lock()
_generation = 0          # bumped by every stop_all()
_turns = 0               # chat answers being written right now
_stoppers: dict = {}     # name -> callable
_last: dict = {}         # the last stop_all() answer, for the tests and status()
_ARMED = False

#: Plain names for the tools a running task can be. The task's own tool name
#: ("control_computer") means nothing to the owner.
_PLAIN_TOOL = {
    "control_computer": "computer control",
    "control_phone": "phone control",
    "browser_control": "browser control",
}


# ---------------------------------------------------------------- stoppers

def register(name: str, stop: Callable[[], Optional[str]]) -> None:
    """Add a stopper. See "Registering a stopper" above."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a stopper needs a name")
    if not callable(stop):
        raise TypeError("a stopper must be callable")
    with _lock:
        _stoppers[name.strip()] = stop


def unregister(name: str) -> None:
    """Remove a stopper. Removing one that is not there is not an error."""
    with _lock:
        _stoppers.pop(str(name).strip(), None)


def registered() -> list:
    with _lock:
        return sorted(_stoppers)


# ------------------------------------------------ the chat answer's latch

def begin_turn() -> int:
    """A chat answer starts. Returns its mark: stopped_since(mark) becomes
    true once Stop everything is pressed during it. jarvis_agent calls this."""
    global _turns
    with _lock:
        _turns += 1
        return _generation


def end_turn() -> None:
    global _turns
    with _lock:
        _turns = max(0, _turns - 1)


def stopped_since(mark) -> bool:
    """True when Stop everything was pressed after `mark` was taken. A mark of
    None (a caller that never took one) is never stopped."""
    if not isinstance(mark, int) or isinstance(mark, bool):
        return False
    with _lock:
        return _generation > mark


def generation() -> int:
    with _lock:
        return _generation


# ---------------------------------------------------------------- stopping

def _say(text) -> Optional[str]:
    if text is None:
        return None
    s = " ".join(str(text).split())
    if not s:
        return None
    return s if len(s) <= MAX_SAID else s[:MAX_SAID - 3].rstrip() + "..."


def _task_control():
    try:
        import jarvis_task_control
        return jarvis_task_control
    except Exception:
        return None


def _stop_tasks(tc, by: str) -> tuple:
    """([sentences], [problems]) from the task Stop the Stop button uses."""
    if tc is None:
        return [], []
    try:
        running = [r.get("tool") for r in (tc.running() or []) if isinstance(r, dict)]
    except Exception:
        running = []
    try:
        code, out = tc.handle_post("/api/task/stop", {}, by=by)
    except Exception as exc:
        return [], [f"The running task could not be told to stop ({type(exc).__name__})."]
    if code != 200 or not isinstance(out, dict):
        return [], []           # 409: nothing running or paused
    said = []
    if out.get("stopping"):
        names = sorted({_PLAIN_TOOL.get(str(t), str(t)) for t in running if t})
        what = f" ({', '.join(names)})" if names else ""
        said.append(f"The task that was running{what} stops before its next step. "
                    f"Steps already done stay done.")
    if out.get("forgot_paused"):
        said.append("The paused task was forgotten.")
    return said, []


def _audit(detail: dict) -> None:
    try:
        import jarvis_framework
        jarvis_framework.audit_log("stop_all", detail)
    except Exception:
        pass


def stop_all(by: str = "", *, task_control=None) -> dict:
    """Stop everything. Never raises, never approves, never starts anything.

    `task_control` is jarvis_task_control, or a stand-in (tests)."""
    global _generation
    with _lock:
        _generation += 1
        turns = _turns
        stoppers = list(_stoppers.items())
    stopped, problems = _stop_tasks(task_control if task_control is not None
                                    else _task_control(), by)
    if turns:
        stopped.append("The answer being written now uses no more tools, even if you "
                       "approve a card it raised.")
    for name, fn in stoppers:
        try:
            said = _say(fn())
        except Exception as exc:
            problems.append(f"{name} could not be stopped ({type(exc).__name__}).")
            continue
        if said:
            stopped.append(said)
    if stopped:
        message = "Stopped everything. " + " ".join(stopped)
    else:
        message = NOTHING
    if problems:
        message += " " + " ".join(problems)
    out = {"ok": True, "stopped": stopped, "problems": problems, "message": message,
           "at": time.time()}
    with _lock:
        _last.clear()
        _last.update(out)
    # Counts only: never a stopper's words (a focus session's could name an app).
    _audit({"by": by, "stopped": len(stopped), "problems": len(problems)})
    return out


def last() -> Optional[dict]:
    with _lock:
        return dict(_last) if _last else None


# -------------------------------------------------------------- the route

def armed() -> bool:
    """True once install() has wrapped the running server's POST handler."""
    return _ARMED


def install(handler_cls, *, origin_ok, token_ok, read_body=None) -> str:
    """Wrap `handler_cls.do_POST` so POST /api/stop_all is answered here.
    Every other request goes straight to the original. Returns the banner
    line. The server's own origin and token checks decide who may ask."""
    global _ARMED
    original = handler_cls.do_POST
    if getattr(original, "_jarvis_stop_all", False):
        _ARMED = True
        return "  stop       Stop everything answers at POST /api/stop_all (already on)"

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != ROUTE:
            return original(self)
        try:
            if not origin_ok(self):
                return self._send(403, {"error": "cross-origin request refused"})
            if not token_ok(self):
                return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        except Exception:
            return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        if read_body is not None:
            try:
                read_body(self)      # the body means nothing; read so the socket is clean
            except Exception:
                pass
        host = str((getattr(self, "client_address", None) or ("",))[0])
        by = "this PC" if host in ("127.0.0.1", "::1") else "another device"
        return self._send(200, stop_all(by))

    do_POST._jarvis_stop_all = True
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  stop       Stop everything answers at POST /api/stop_all"


def _reset_for_tests() -> None:
    global _generation, _turns, _ARMED
    with _lock:
        _generation = 0
        _turns = 0
        _stoppers.clear()
        _last.clear()
    _ARMED = False


if __name__ == "__main__":
    print(f"  armed      {armed()}")
    print(f"  stoppers   {', '.join(registered()) or 'none registered in this process'}")
