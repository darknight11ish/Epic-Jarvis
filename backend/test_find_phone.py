"""test_find_phone.py - "ring my phone" (jarvis_find_phone.py; the owner's
choice of the research audit's idea 7, 2026-09-28).

    python3 backend/test_find_phone.py

Runs anywhere; the event bus is a list here. What it proves:

1. ONE event, `ring_phone`, carrying no words at all - an id, "ring" or
   "stop", when it was sent, until when, and for how long - so a phone can
   refuse one that is stale or replayed (net/FindPhone.kt).
2. Saying it twice in quick succession sends one ring, not two; "stop
   ringing" sends a stop for that ring only while it could still ring.
3. The answer never pretends: every connected phone rings (they share one
   pairing key), and naming a phone says so.
4. The fast path answers it without the AI model and with no card, and
   "where's my phone" is ours but "find my phone charger" is not.
5. jarvis_find_phone.py never imports jarvis_gate: there is no card to ask
   for, by construction.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_find_phone.py", "jarvis_quick.py")
import tempfile  # noqa: E402
_TMP = tempfile.mkdtemp(prefix="jarvis-find-phone-")
os.environ["JARVIS_SCHEDULE_DB"] = os.path.join(_TMP, "schedule.db")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
import jarvis_find_phone as FP  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_one_event_with_no_words():
    FP._reset_for_tests()
    sent = []
    out = FP.ring(now=1000.0, publish=lambda k, d: sent.append((k, d)))
    check("one event", len(sent) == 1 and sent[0][0] == FP.EVENT == "ring_phone")
    d = sent[0][1]
    check("its fields: an id, ring, when, until when, how long - nothing else",
          set(d) == {"id", "state", "at", "until", "seconds"} and d["state"] == "ring"
          and d["at"] == 1000.0 and d["until"] == 1000.0 + FP.RING_SECONDS
          and d["seconds"] == FP.RING_SECONDS and d["id"].startswith("r"), str(d))
    check("the answer says it rings for a minute, even on silent, with Stop",
          out["ok"] and out["said"] == FP.RINGING and "silent" in out["said"]
          and "Stop" in out["said"])
    again = FP.ring(now=1002.0, publish=lambda k, d: sent.append((k, d)))
    check("said twice in a moment: one ring", len(sent) == 1 and again["said"] == FP.ALREADY)
    FP.ring(now=1000.0 + FP.AGAIN_AFTER + 1, publish=lambda k, d: sent.append((k, d)))
    check("said again later: a new ring, a new id", len(sent) == 2
          and sent[1][1]["id"] != sent[0][1]["id"])


def t_stop():
    FP._reset_for_tests()
    sent = []
    check("nothing ringing: says so, sends nothing",
          FP.stop(now=5.0, publish=lambda k, d: sent.append((k, d)))["said"] == FP.NOT_RINGING
          and sent == [])
    FP.ring(now=10.0, publish=lambda k, d: sent.append((k, d)))
    out = FP.stop(now=20.0, publish=lambda k, d: sent.append((k, d)))
    check("stop: for that ring only", out["said"] == FP.STOPPED and sent[-1][1]["state"] == "stop"
          and sent[-1][1]["id"] == sent[0][1]["id"])
    check("a second stop sends nothing more",
          FP.stop(now=21.0, publish=lambda k, d: sent.append((k, d)))["said"] == FP.NOT_RINGING
          and len(sent) == 2)
    FP.ring(now=100.0, publish=lambda k, d: sent.append((k, d)))
    check("after its minute it is not ringing any more",
          FP.stop(now=100.0 + FP.RING_SECONDS + 1,
                  publish=lambda k, d: sent.append((k, d)))["said"] == FP.NOT_RINGING)


def t_honest_about_which_phone():
    FP._reset_for_tests()
    out = FP.ring(named=True, now=1.0, publish=lambda k, d: None)
    check("naming a phone: says every connected phone rings",
          out["said"] == FP.RINGING_NAMED and "cannot tell your phones apart" in out["said"])

    def broken(k, d):
        raise RuntimeError("no bus")
    FP._reset_for_tests()
    out = FP.ring(now=1.0, publish=broken)
    check("no bus: a plain sentence, never a raise", out["ok"] is False and out["said"] == FP.NO_BUS)


def t_the_fast_path():
    for said, name, named in (("ring my phone", "phone_ring", False),
                              ("find my phone", "phone_ring", False),
                              ("Where's my phone?", "phone_ring", False),
                              ("I can't find my phone", "phone_ring", False),
                              ("ring my work phone", "phone_ring", True),
                              ("stop ringing my phone", "phone_stop", None)):
        i = Q.match(said)
        check(f"ours: {said!r}", i is not None and i.name == name
              and (named is None or i.f.get("named") is named), str(i and (i.name, i.f)))
    for said in ("call my mum's phone", "ring my sister's mobile", "call my mum phone",
                 "find my dad's phone"):
        i = Q.match(said)
        check(f"someone else's phone is not the owner's: {said!r}",
              i is None or i.name != "phone_ring", str(i and (i.name, i.f)))
    for said in ("find my phone charger", "call my mum", "ring the doctor"):
        i = Q.match(said)
        check(f"not ours: {said!r}", i is None or not i.name.startswith("phone_"))
    FP._reset_for_tests()
    sent = []
    real = FP._default_publish
    FP._default_publish = lambda k, d: sent.append((k, d))
    try:
        res = Q.answer("ring my phone")
    finally:
        FP._default_publish = real
    check("answered without the model, no card, one event",
          res is not None and res.reply == FP.RINGING and len(sent) == 1)
    route = Q.route_fields(res)
    check("the route says it was answered here", route["lane"] == Q.LANE and route["quick"] ==
          "phone_ring")


def t_never_a_card_by_construction():
    src = (HERE / "jarvis_find_phone.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
        n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    check("jarvis_find_phone.py never imports jarvis_gate", "jarvis_gate" not in names)
    check("... nor opens a socket", "socket" not in names and "urllib" not in src)


def t_the_threads_it_starts_are_stopped_before_the_process_ends():
    """The scheduler's loop and its after-start jobs are daemon threads, and
    the interpreter exits without waiting for them. A suite that asks a fast
    question - `Q.answer("ring my phone")` below runs a real scheduler, because
    jarvis_quick.answer() calls jarvis_schedule.get() - then ends with the loop
    inside a `sqlite3` call, which is the SIGABRT this suite produced about one
    run in four on Ubuntu ("terminate called without an active exception",
    docs/HANDOFF-2026-10-05-tutorials-and-ci.md section 2.2), after all 28
    checks had passed.

    So jarvis_schedule stops its own threads at exit (`_on_exit`). This checks
    it really does - the loop is stopped and waited for, a job of its is waited
    for, and the hook is the one the process itself runs. Nothing is suppressed
    and nothing is exited early; the loop is asked to stop exactly as
    test_briefing.py already asks it."""
    import jarvis_schedule as S

    S.get()                                   # what Q.answer() did above
    check("the scheduler's own loop is running",
          S._SCHED is not None and S._SCHED.running)
    # A job that is really doing something: exit must WAIT for it, up to
    # EXIT_JOIN_SECONDS, instead of walking away from it - that wait is the
    # thing that stops a thread being inside sqlite while the interpreter
    # finalizes. A job that never finishes is a real job too (one waiting on a
    # plug-in program); this one does finish, on purpose.
    ran = []
    S.after_start(lambda: (ran.append(time.time()), time.sleep(0.6)))
    S._on_exit()                              # the hook the process runs itself
    check("after that hook, the loop has stopped", not S._SCHED.running)
    check("... and its own loop is waited for, not left behind",
          not [t for t in threading.enumerate() if t.name == "jarvis-schedule"],
          repr([t.name for t in threading.enumerate()]))
    check("... and a job of its was really waited for, not abandoned",
          bool(ran) and time.time() - ran[0] >= 0.6, repr(ran))
    check("and that hook really is what the process runs at exit",
          _exit_hook_is_registered(), "atexit did not run jarvis_schedule._on_exit")


def _exit_hook_is_registered() -> bool:
    """Start the scheduler in a fresh interpreter, then run the exit handlers
    the way the interpreter itself will - `atexit._run_exitfuncs()`. The
    question is not "did someone write the line" but "does the process end
    with no thread of jarvis_schedule's still running". Removing the
    registration is what makes this check go red."""
    child = (
        "import atexit, os, sys, threading\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "os.environ['JARVIS_SCHEDULE_DB'] = sys.argv[2]\n"
        "os.environ['OPENJARVIS_CONFIG_DIR'] = sys.argv[3]\n"
        "import jarvis_schedule as S\n"
        "S.get()\n"
        "atexit._run_exitfuncs()\n"
        "left = [t.name for t in threading.enumerate()\n"
        "        if t.name.startswith('jarvis-schedule')]\n"
        "print('LEFT', left)\n")
    r = subprocess.run([sys.executable, "-c", child, str(HERE), os.environ["JARVIS_SCHEDULE_DB"],
                        os.environ["OPENJARVIS_CONFIG_DIR"]],
                       capture_output=True, text=True, timeout=90)
    return r.returncode == 0 and "LEFT []" in r.stdout


# BOTH SIDES KEPT (merge of origin/main into next-two-failures). The two
# branches found the same SIGABRT - "terminate called without an active
# exception", once in four Ubuntu runs, after every check had passed - and
# fixed it at the two ends that both needed fixing, so neither fix replaces
# the other:
#
#   * origin/main stops what THIS SUITE started, in `_stop_what_this_suite_started`
#     below, called from __main__. It is the narrower, suite-level fix, and it
#     is deliberately still here.
#   * this branch fixes the module that actually starts the threads:
#     jarvis_schedule now stops its own loop and its after-start jobs at exit
#     (`_on_exit`, registered with atexit). `t_the_threads_it_starts_are_stopped_before_the_process_ends`
#     above is what proves it, including that the hook is the one the process
#     really runs.
#
# The suite-level fix alone leaves the next suite that starts a scheduler free
# to abort the same way; the module-level fix alone would be untested here.
# Running both is safe and strictly safer: `Scheduler.stop()` only sets an
# Event, wakes the loop and joins a thread that has already gone.
def _stop_what_this_suite_started() -> None:
    """Shut the ONE scheduler down again, and wait for it, before this process
    exits.

    `t_the_fast_path` calls jarvis_quick.answer(), which reaches
    jarvis_schedule.get() - and get() STARTS the scheduler's singleton loop
    on a daemon thread that never returns (it waits TICK_MAX = 30 s between
    ticks), plus two one-shot "after start" threads it fires on the first
    start. This suite used to leave all three alive at interpreter teardown,
    which is the abort CI reported once in four runs on this file:

        terminate called without an active exception   (exit -6, SIGABRT)

    A daemon thread does not keep the process alive, but the C runtime it is
    standing in when finalization begins does abort the process. Windows
    happens to survive it; Linux does not, which is why this passed here and
    on the owner's PC and failed on the Ubuntu job. Stop-and-join is already
    in test_briefing.py (twice) and test_tidy.py for the same reason. Joining
    them here is the honest fix: shut down what this suite started, rather
    than hide the crash."""
    try:
        import jarvis_schedule as S
        if S._SCHED is not None:
            S._SCHED.stop()
    except Exception as exc:                       # pragma: no cover - belt and braces
        print(f"note: the scheduler could not be stopped ({type(exc).__name__}: {exc})")
    # The one-shot starters (jarvis_schedule.after_start) are milliseconds of
    # work, but they hold the SQLite handle the scheduler opened, so they get
    # the same courtesy: a bounded join, never a bare exit underneath them.
    for t in list(threading.enumerate()):
        if t is not threading.main_thread() and t.name in (
                "jarvis-schedule", "jarvis-schedule-after-start"):
            t.join(5.0)


if __name__ == "__main__":
    for fn in (t_one_event_with_no_words, t_stop, t_honest_about_which_phone, t_the_fast_path,
               t_never_a_card_by_construction,
               t_the_threads_it_starts_are_stopped_before_the_process_ends):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    _stop_what_this_suite_started()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
