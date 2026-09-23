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

HOW A CLIENT REACHES IT (task-control.patch)

`POST /api/task/pause|resume|stop|note` and `POST /api/pending/<id>/amend`
are real routes now, added to jarvis_hud.py by `backend/task-control.patch`.
The patch is only a doorway: every decision about what those five do lives
in `handle_post()` below, where it can be tested without the HTTP server.
The names are the ones both clients were already calling, so neither client
had to change its address.

WHAT EACH ONE MEANS - in plain words, because the owner reads these

    stop      Stop what is running, at its next step. Steps already done
              stay done. Also forgets a paused task. Needs no approval card:
              stopping is the safe direction, the same way Deny is.
    pause     Stop at the next step, but remember the steps that did not run.
              No approval card either.
    resume    Does NOT just carry on. It raises an approval card through
              jarvis_gate, listing every step that is left, in full. Nothing
              runs until that card is answered - or, if the owner's own tier
              for that action is "auto", until the gate says so, exactly as
              for the original run. docs/AUTONOMY-PROPOSALS.md section 3d:
              "Resuming a pause is one explicit 'continue' decision."
    note      A sentence for what runs next. Handed to the model when the
              current step finishes, or shown on the resume card. It never
              changes a step that was approved and never approves anything.
    amend     A note on ONE waiting approval card. The card is not changed,
              approved or denied. The note travels with the owner's decision:
              when that card is answered, the model reads it with the answer.

The run() loops still import nothing from here. jarvis_agent.py is the
caller: it registers a running task with begin()/end(), hands each run() a
`checkpoint` lambda, and records a paused plan with remember_paused().

Kept deliberately small: in-memory dicts behind a lock, not a database
table or a JSON sidecar. The only two things on either end of a real HTTP
route - the request handler and the thread running a plan - are the SAME
process (jarvis_hud.py is the HTTP server; run() executes on a thread
that server starts), so nothing here needs to survive a restart. A task
that was mid-run when the server restarted is not resumable anyway - the
client watching it would see the connection drop first.
"""
from __future__ import annotations

import collections
import dataclasses
import importlib
import secrets
import threading
import time
from typing import Callable, Optional

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



# ==========================================================================
#   task-control.patch: the running task, the paused task, and the routes
# ==========================================================================
#
# Everything below is what the five HTTP routes do. jarvis_hud.py only parses
# the request and calls handle_post(); none of the RULES live there.

#: The longest note kept, in characters. A note is a sentence or two for the
#: model, not a document - and a bound stops one request growing memory.
MAX_NOTE_CHARS = 1000

#: Approval-card notes kept at once. The oldest is dropped past this. There
#: is only ever a handful of cards waiting; this is a ceiling, not a target.
_MAX_AMENDS = 64

#: A paused plan older than this is forgotten. Its steps were checked against
#: the screen as it was when it paused; after an hour that picture is stale,
#: and "continue" should be a fresh request, not a resumption.
PAUSED_TTL_SECONDS = 3600

_running: dict = {}        # task_id -> {"tool": str, "started": float}
_paused: dict = {}         # at most one entry: task_id -> record (see remember_paused)
_amends: "collections.OrderedDict" = collections.OrderedDict()  # approval id -> note
_resuming: dict = {}       # at most one entry: task_id -> {"since": float}
_last_result: dict = {}    # what the last resumed run did, for GET /api/task
_log = collections.deque(maxlen=50)


def _clean_note(raw) -> Optional[str]:
    """A note as it will be stored, or None if there is nothing in it.

    Control characters are dropped (newlines and tabs kept): this text is
    read back to a model and printed on a card, and a stray escape sequence
    is noise in both. Cut at MAX_NOTE_CHARS rather than refused, so a long
    paste keeps its first part instead of vanishing.
    """
    if not isinstance(raw, str):
        return None
    text = "".join(ch for ch in raw if ch in "\n\t" or ch >= " ").strip()
    if not text:
        return None
    return text[:MAX_NOTE_CHARS]


def _audit(what: str, detail: dict) -> None:
    """One line in the owner's audit log, and one in the in-memory history.

    Never the note text: jarvis_framework.audit_log writes a plain file, and
    a note can say anything. Its length is enough to show one was sent.
    """
    entry = {"at": time.time(), "what": what}
    entry.update(detail)
    with _lock:
        _log.append(entry)
    try:
        import jarvis_framework
        jarvis_framework.audit_log("task." + what, detail)
    except Exception:
        pass


def _set_activity(state: str, detail: str = "") -> None:
    """Report a change through the one event bus. Best-effort."""
    try:
        import jarvis_events
        jarvis_events.set_activity(state, detail)
    except Exception:
        pass


def new_task_id() -> str:
    return "task_" + secrets.token_hex(6)


def begin(task_id: str, tool: str) -> None:
    """A multi-step plan has been approved and is starting to run."""
    with _lock:
        _running[task_id] = {"tool": str(tool), "started": time.time()}


def end(task_id: str) -> None:
    """That plan's run() returned, however it ended.

    A pause or stop that arrived after its last checkpoint is spent here: it
    was meant for this run, and must not land on whatever reuses the id.
    The task's note is NOT dropped - take_note() is how it is picked up.
    """
    with _lock:
        _running.pop(task_id, None)
        _signals.pop(task_id, None)


def running() -> list:
    with _lock:
        return [{"id": k, **v} for k, v in _running.items()]


def take_note(task_id: Optional[str]) -> Optional[str]:
    """The note queued for a task, removed as it is read (delivered once)."""
    if task_id is None:
        return None
    with _lock:
        return _notes.pop(task_id, None)


def remember_paused(task_id: str, *, tool: str, action: str, module: str,
                    plan, not_run: int, done: int) -> None:
    """Keep what a paused run did not do, so Resume can offer exactly that.

    `plan` must be the plan to run on resume - the ORIGINAL plan cut down to
    the steps that did not run - never something rebuilt from the model's
    arguments. The resume card shows this object's describe() text, and
    run() executes this same object, so what is approved is what runs.

    One paused task at a time. A second pause replaces the first: two
    half-finished plans behind one Resume button would make "resume"
    ambiguous, and the older one's picture of the screen is the staler.
    """
    with _lock:
        _paused.clear()
        _paused[task_id] = {"tool": str(tool), "action": str(action),
                            "module": str(module), "plan": plan,
                            "not_run": int(not_run), "done": int(done),
                            "at": time.time()}


def _current_paused() -> Optional[tuple]:
    """(task_id, record) for the paused task, or None. Expires a stale one."""
    with _lock:
        for tid, rec in list(_paused.items()):
            if time.time() - rec["at"] > PAUSED_TTL_SECONDS:
                _paused.pop(tid, None)
                _notes.pop(tid, None)
                continue
            return tid, rec
    return None


def paused() -> Optional[dict]:
    """The paused task, as a client may see it: no plan object, no note text."""
    cur = _current_paused()
    if cur is None:
        return None
    tid, rec = cur
    with _lock:
        waiting = tid in _resuming
    return {"id": tid, "tool": rec["tool"], "steps_done": rec["done"],
            "steps_left": rec["not_run"], "paused_at": rec["at"],
            "resume_waiting_for_approval": waiting}


def effective_activity(state: str, detail: str = "") -> tuple:
    """What `_activity()` in jarvis_hud.py should really report.

    A chat turn ends by reporting "idle". If it ended because its plan was
    PAUSED, "idle" is not true - a paused task is waiting for Resume or
    Stop - and both clients show their Resume button only when activity is
    "paused" (they must never decide that for themselves; see
    docs/AUTONOMY-PROPOSALS.md section 3d). So while a task is paused, idle
    reads as paused. Every other state passes through untouched.
    """
    if str(state) != "idle":
        return state, detail
    p = paused()
    if p is None:
        return state, detail
    if p["resume_waiting_for_approval"]:
        return "paused", "Waiting for your approval to continue."
    left = p["steps_left"]
    return "paused", (f"Paused with {left} step{'s' if left != 1 else ''} not run. "
                      f"Resume asks you first; Stop forgets it.")


def status() -> dict:
    """GET /api/task - what is running, what is paused. No note text."""
    with _lock:
        last = dict(_last_result)
        log = list(_log)[-10:]
    return {"available": True, "running": running(), "paused": paused(),
            "last_resumed": last or None, "recent": log}


# ---- approval-card notes (POST /api/pending/<id>/amend) ------------------

def amend(approval_id: str, note: str) -> None:
    """Keep one note against one waiting approval card. Approves nothing."""
    with _lock:
        _amends[str(approval_id)] = {"note": note, "at": time.time()}
        _amends.move_to_end(str(approval_id))
        while len(_amends) > _MAX_AMENDS:
            _amends.popitem(last=False)


def take_amend(approval_id: Optional[str]) -> Optional[str]:
    """The note on an approval card, removed as it is read - or None.

    jarvis_agent.py calls this right after the gate answers, so the note
    reaches the model WITH the owner's answer, whichever answer it was.
    """
    if approval_id is None:
        return None
    with _lock:
        got = _amends.pop(str(approval_id), None)
    return got["note"] if got else None


# ---- resume: one new decision, never a carry-on --------------------------

def _gate_check(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing CLOSED on any error - as jarvis_agent does."""
    class _Refused:
        allowed = False
        outcome = "refused"

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate
    except Exception as exc:
        return _Refused(f"the approval gate is not available here ({exc})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:
        return _Refused(f"the approval gate raised {type(exc).__name__}: {exc}")


def resume_card_text(task_id: str, rec: dict, module) -> str:
    """The card for "continue this paused task?". Every remaining step, in full.

    The steps come from the module's own describe() of the cut-down plan -
    the same function that wrote the first card - so nothing is summarised.
    """
    done = rec["done"]
    lines = [f"Continue the task Jarvis paused? {done} step{'s' if done != 1 else ''} "
             f"already ran and stay done. Only the steps below would run, and each "
             f"one is checked against the screen again just before it runs.", ""]
    lines.append(module.describe(rec["plan"]))
    with _lock:
        note = _notes.get(task_id)
    if note:
        lines += ["", "Your note on this task (it changes none of the steps above):",
                  note]
    lines += ["", "If you say no: nothing more runs. The task stays paused until "
                  "you press Stop, or until it is an hour old."]
    return "\n".join(lines)


def _record_last(**fields) -> None:
    with _lock:
        _last_result.clear()
        _last_result.update(fields)
        _last_result["at"] = time.time()


def _resume_worker(task_id: str, rec: dict, by: str, gate_check: Callable,
                   importer: Callable) -> None:
    try:
        try:
            module = importer(rec["module"])
            text = resume_card_text(task_id, rec, module)
        except Exception as exc:
            _audit("resume_failed", {"task": task_id, "by": by,
                                     "error": f"{type(exc).__name__}: {exc}"})
            _record_last(task=task_id, ok=False,
                         reason=f"could not prepare the resume: {exc}")
            return
        verdict = gate_check(rec["action"], {"text": text},
                             f"resume paused task {rec['tool']} ({task_id})")
        if not getattr(verdict, "allowed", False):
            # Denied, timed out or refused: nothing runs, and it stays paused.
            _audit("resume_refused", {"task": task_id, "by": by,
                                      "outcome": str(getattr(verdict, "outcome", "refused"))})
            return
        with _lock:
            if _paused.get(task_id) is not rec:
                # Stopped (or replaced) while the card was waiting. The owner's
                # later Stop wins over an approval of the earlier question.
                return
            _paused.pop(task_id, None)
        _audit("resumed", {"task": task_id, "by": by,
                           "outcome": str(getattr(verdict, "outcome", ""))})
        new_id = new_task_id()
        begin(new_id, rec["tool"])
        # The task's note, if any, was on the card; it moves with the task.
        with _lock:
            if task_id in _notes:
                _notes[new_id] = _notes.pop(task_id)
        _set_activity("working", f"Continuing {rec['tool']}...")
        try:
            result = module.run(rec["plan"], approved=True,
                                announce=lambda t: _set_activity("working", t),
                                checkpoint=lambda: checkpoint(new_id))
        except Exception as exc:
            result = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
        finally:
            end(new_id)
        result = result if isinstance(result, dict) else {"ok": False}
        not_run = len(result.get("not_run") or [])
        done_now = len(result.get("done") or [])
        if result.get("paused"):
            steps = list(getattr(rec["plan"], "steps", []) or [])
            remember_paused(new_id, tool=rec["tool"], action=rec["action"],
                            module=rec["module"],
                            plan=dataclasses.replace(rec["plan"],
                                                     steps=steps[len(steps) - not_run:]),
                            not_run=not_run, done=rec["done"] + done_now)
        else:
            with _lock:
                _notes.pop(new_id, None)
        _record_last(task=new_id, ok=bool(result.get("ok")), steps_done=done_now,
                     steps_not_run=not_run, paused=bool(result.get("paused")),
                     reason=str(result.get("reason") or "")[:300])
    finally:
        with _lock:
            _resuming.pop(task_id, None)
        state, detail = effective_activity("idle", "")
        _set_activity(state, detail)


def resume(by: str = "", *, gate_check: Optional[Callable] = None,
           importer: Optional[Callable] = None, wait: bool = False) -> tuple:
    """Raise the "continue?" card for the paused task. Returns (code, body).

    The card is raised on a background thread, because jarvis_gate.check()
    waits for the owner's answer and an HTTP request must not. `wait=True`
    runs it inline (tests only).
    """
    cur = _current_paused()
    if cur is None:
        return 409, {"ok": False, "error": "nothing is paused, so there is nothing to resume"}
    tid, rec = cur
    with _lock:
        if tid in _resuming:
            return 409, {"ok": False, "error": "a resume card for this task is already "
                                               "waiting for your answer"}
        _resuming[tid] = {"since": time.time()}
    _audit("resume_asked", {"task": tid, "by": by})
    args = (tid, rec, by, gate_check or _gate_check, importer or importlib.import_module)
    state, detail = effective_activity("idle", "")
    _set_activity(state, detail)
    if wait:
        _resume_worker(*args)
    else:
        threading.Thread(target=_resume_worker, args=args, name="jarvis-task-resume",
                         daemon=True).start()
    return 202, {"ok": True, "task": tid, "asking": True,
                 "message": "Nothing has run yet. An approval card lists the steps "
                            "that are left; the task continues only if you approve it."}


# ---- the routes ----------------------------------------------------------

TASK_ROUTES = ("/api/task/pause", "/api/task/resume", "/api/task/stop", "/api/task/note")


def is_amend_route(route: str) -> bool:
    return (isinstance(route, str) and route.startswith("/api/pending/")
            and route.endswith("/amend") and route.count("/") == 4)


def _pending_ids() -> Optional[set]:
    """Ids of the approval cards waiting right now, or None if unreadable."""
    try:
        import jarvis_gate
        return {str(r.get("id")) for r in (jarvis_gate.pending() or [])
                if isinstance(r, dict)}
    except Exception:
        return None


def handle_post(route: str, body, *, by: str = "",
                pending_ids: Optional[Callable[[], Optional[set]]] = None,
                gate_check: Optional[Callable] = None,
                importer: Optional[Callable] = None) -> tuple:
    """Everything the POST routes do. Returns (http_status, json_body).

    None of these is a decision about anything Jarvis is waiting on, and none
    can grant anything: stop and pause only make work end sooner, a note is
    text, and resume only ASKS. That is why they need no approval card
    themselves - and why resume is the one that raises one.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}

    if is_amend_route(route):
        from urllib.parse import unquote
        approval_id = unquote(route[len("/api/pending/"):-len("/amend")])
        note = _clean_note(body.get("note"))
        if not approval_id:
            return 400, {"ok": False, "error": "no approval id in the address"}
        if note is None:
            return 400, {"ok": False, "error": "the note is empty"}
        ids = (pending_ids or _pending_ids)()
        if ids is None:
            return 503, {"ok": False, "error": "the approval queue could not be read, "
                                               "so the note was not kept"}
        if approval_id not in ids:
            return 409, {"ok": False, "error": "that card is no longer waiting - it was "
                                               "answered, or it expired"}
        amend(approval_id, note)
        _audit("amend", {"approval": approval_id, "by": by, "chars": len(note)})
        return 200, {"ok": True, "id": approval_id, "kept": True,
                     "message": "Kept with this card. Nothing was approved or denied. "
                                "Jarvis reads your note together with your answer."}

    if route == "/api/task/stop":
        with _lock:
            ids = list(_running)
        for tid in ids:
            request(tid, "stop")
        forgot = None
        cur = _current_paused()
        if cur is not None:
            forgot = cur[0]
            with _lock:
                _paused.pop(forgot, None)
                _notes.pop(forgot, None)
        if not ids and forgot is None:
            return 409, {"ok": False, "error": "nothing is running or paused"}
        _audit("stop", {"tasks": ids, "forgot_paused": forgot, "by": by})
        if forgot is not None and not ids:
            _set_activity("idle", "")
        return 200, {"ok": True, "stopping": ids, "forgot_paused": forgot,
                     "message": ("Stopping at the next step; steps already done stay done."
                                 if ids else "The paused task was forgotten.")}

    if route == "/api/task/pause":
        with _lock:
            ids = list(_running)
        if not ids:
            already = paused() is not None
            return 409, {"ok": False, "error": ("it is already paused" if already
                                                else "nothing is running")}
        for tid in ids:
            request(tid, "pause")
        _audit("pause", {"tasks": ids, "by": by})
        return 200, {"ok": True, "pausing": ids,
                     "message": "Pausing at the next step. The Resume button appears "
                                "once it has actually stopped."}

    if route == "/api/task/resume":
        return resume(by, gate_check=gate_check, importer=importer)

    if route == "/api/task/note":
        note = _clean_note(body.get("note"))
        if note is None:
            return 400, {"ok": False, "error": "the note is empty"}
        with _lock:
            ids = list(_running)
        target = ids[0] if ids else None
        where = "running"
        if target is None:
            cur = _current_paused()
            if cur is not None:
                target, where = cur[0], "paused"
        if target is None:
            return 409, {"ok": False, "error": "nothing is running or paused to "
                                               "attach this note to"}
        inject_note(target, note)
        _audit("note", {"task": target, "by": by, "chars": len(note)})
        return 200, {"ok": True, "task": target,
                     "message": ("Jarvis reads this when the current step finishes. "
                                 "It changes no step you already approved."
                                 if where == "running" else
                                 "Kept with the paused task; it is shown on the "
                                 "resume card. It changes none of the steps.")}

    return 404, {"ok": False, "error": "no such task route"}
