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
    """Take the pending signal for a task, or None.

    **This CONSUMES the signal.** Reading it is what acting on it looks
    like, and a signal that has been acted on is spent. That is not a
    convenience; it is the only thing standing between this module and a
    permanently stuck task, and it was missing:

        Pause a task. The run loop reads "pause" and stops. Press
        continue, which starts a FRESH run() against the same id. Its
        very first checkpoint reads the same "pause" still sitting here
        and stops again. And again. Forever - and so does any later task
        that happens to reuse the id.

    `clear()` was written for exactly this and had no caller anywhere
    outside its own tests; none of the three run() loops could call it if
    it wanted to, because they are handed a zero-argument callback and
    have no idea what a task id is (see the module doc on why that is the
    right shape). Taking the signal on read is the fix that needs no new
    plumbing in any of them.

    A `stop` is consumed the same way a `pause` is. The run loop returns
    immediately on either, so neither is read twice inside one run, and a
    stop that outlived its run must not stop the next one.

    `None` in, `None` out - a caller with no task_id yet (nothing to pause
    or stop against) gets exactly the "no signal" answer, never a
    KeyError, so `checkpoint=lambda: jarvis_task_control.checkpoint(tid)`
    is safe to wire even when `tid` might be `None`.
    """
    if task_id is None:
        return None
    with _lock:
        return _signals.pop(task_id, None)


def peek(task_id: Optional[str]) -> Optional[str]:
    """The pending signal for a task WITHOUT consuming it.

    For a caller that wants to show whether a pause is still waiting to be
    picked up - a status route, a test - rather than act on it. Never wire
    a run() loop's `checkpoint` to this: the loop reading a signal is what
    spends it, and a loop that peeked would stop on the same pause every
    time it ran. See `checkpoint()`.
    """
    if task_id is None:
        return None
    with _lock:
        return _signals.get(task_id)


def clear(task_id: str) -> None:
    """Drop a task's signal and any queued note.

    Two real uses, now that `checkpoint()` consumes the signal itself:

    - the owner cancels a Pause they asked for BEFORE the run loop has
      reached its next checkpoint, so there is a signal sitting here that
      nothing will ever take; and
    - a task ends, and its queued note should not be handed to whatever
      next reuses the id.

    Notes are not consumed on read - `pending_note()` is a read, by
    design, because the note is meant to survive until whatever builds the
    next proposal picks it up - so this is the only thing that drops one.
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
