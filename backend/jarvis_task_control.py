"""A pause/stop/inject-note signal store for a running plan.

docs/AUTONOMY-PROPOSALS.md section 3d: "The run loop already has a
checkpoint: jarvis_ui_control.run(), jarvis_android_control.run(), and
jarvis_browser_control.run() all re-verify the live target before every
step. That is exactly where a control signal is checked too - no new
architecture, one more read at a point that already exists in all three
loops." This module is that one more read.

It is deliberately not imported by any of those three modules. Every one
of them already has a real, working pattern for something a caller must
supply but the module itself cannot know: `announce(text)`, injected as a
plain callback, never imported. This module follows the same shape - a
new `checkpoint()` parameter on each `run()`, which a caller wires to
`lambda: jarvis_task_control.checkpoint(task_id)`. Importing this module
from all three would be the first cross-module dependency any of them
has ever had, for no benefit `announce`'s own pattern does not already
give for free.

What this module does NOT do, and why: it has no HTTP route of its own,
and nothing here decides what a task's real id even is. Something has to
call request()/inject_note() when the owner taps Pause, Stop, or types a
note - and that caller is jarvis_hud.py/jarvis_gate.py, neither of which
is visible anywhere in this repository (see backend/README.md's standing
note on that gap, and degrade-filter.patch's own "future work for
whoever has jarvis_gate.py open"). Wiring a Flask route against a file
this session cannot read or run a test against is exactly the "guessing
blind" mistake ui-control-wiring.patch's own section already made once
and rewrote. So this module, and the `checkpoint` wiring into the three
run() loops, is the verified, testable half: a real signal store and a
real read of it at a real checkpoint, proven by test_task_control.py and
the new cases in test_ui_control.py / test_android_control.py /
test_browser_control.py. The route that lets a client actually SET one,
and the event that reports `activity: "paused"` back out, are future
work for whoever holds jarvis_hud.py/jarvis_gate.py's real source -
backend/README.md names exactly what to add and where, once that source
is in hand.

Kept deliberately dumb: an in-memory dict behind a lock, not a database
table or a JSON sidecar. The only two things on either end of a real HTTP
route - the request handler and the thread running a plan - are the SAME
process (jarvis_hud.py is the HTTP server; run() executes on a thread
that server starts), so nothing here needs to survive a restart. A task
that was mid-run when the server restarted is not resumable anyway - the
client watching it would see the connection drop first.
"""
from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
_signals: dict = {}   # task_id -> "pause" | "stop"
_notes: dict = {}     # task_id -> most recently queued free-text note

_VALID_ACTIONS = ("pause", "stop")


def request(task_id: str, action: str) -> None:
    """Ask a running task to pause or stop at its next checkpoint.

    Raises on an unrecognised action rather than silently storing garbage
    that `checkpoint()` would then have to make sense of - the same
    reasoning jarvis_ui_control.Step's fixed `action` vocabulary uses.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"action must be one of {_VALID_ACTIONS}, got {action!r}")
    with _lock:
        _signals[task_id] = action


def checkpoint(task_id: Optional[str]) -> Optional[str]:
    """The pending signal for a task, or None.

    `None` in, `None` out - a caller with no task_id yet (nothing to pause
    or stop against) gets exactly the "no signal" answer, never a
    KeyError, so `checkpoint=lambda: jarvis_task_control.checkpoint(tid)`
    is safe to wire even when `tid` might be `None`.
    """
    if task_id is None:
        return None
    with _lock:
        return _signals.get(task_id)


def clear(task_id: str) -> None:
    """Drop a task's signal and any queued note.

    Call this once a task reaches a state a client has been told about -
    finished, stopped, or explicitly resumed - so a stale pause from a
    task that already ended can never leak onto a different task that
    happens to reuse the same id.
    """
    with _lock:
        _signals.pop(task_id, None)
        _notes.pop(task_id, None)


def inject_note(task_id: str, note: str) -> None:
    """Queue a free-text note against a running task.

    Per docs/AUTONOMY-PROPOSALS.md section 3b/3d: this never touches the
    plan currently running - those steps finish exactly as approved. The
    note sits here for whatever builds the *next* proposal to read back
    with pending_note(), the same amend-not-splice rule Section 1 states
    for every other decision in this project.
    """
    with _lock:
        _notes[task_id] = note


def pending_note(task_id: str) -> Optional[str]:
    """The most recently queued note for a task, or None."""
    with _lock:
        return _notes.get(task_id)
