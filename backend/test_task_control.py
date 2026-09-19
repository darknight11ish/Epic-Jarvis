"""jarvis_task_control.py - the pause/stop/inject-note signal store.

    python3 test_task_control.py
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_task_control as TC

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_no_signal_by_default():
    check("an id nobody asked about has no signal", TC.checkpoint("appr_never_touched") is None)


def t_none_task_id_never_raises():
    check("checkpoint(None) is None, not an error", TC.checkpoint(None) is None)


def t_request_rejects_unknown_actions():
    raised = False
    try:
        TC.request("appr_x", "resume")
    except ValueError:
        raised = True
    check("an action other than pause/stop raises", raised)
    check("CONTROL: the bad call left no signal behind", TC.checkpoint("appr_x") is None)


def t_stop_is_read_back():
    TC.request("appr_1", "stop")
    check("stop is read back", TC.checkpoint("appr_1") == "stop")
    TC.clear("appr_1")


def t_pause_is_read_back():
    TC.request("appr_2", "pause")
    check("pause is read back", TC.checkpoint("appr_2") == "pause")
    TC.clear("appr_2")


def t_clear_removes_the_signal():
    TC.request("appr_3", "stop")
    TC.clear("appr_3")
    check("cleared id has no signal", TC.checkpoint("appr_3") is None)


def t_clear_is_safe_on_an_id_with_no_signal():
    # CONTROL: clearing something that was never set must not raise.
    TC.clear("appr_never_set")
    check("clearing an unset id did not raise", True)


def t_a_later_request_replaces_an_earlier_one():
    TC.request("appr_4", "pause")
    TC.request("appr_4", "stop")
    check("the most recent request wins", TC.checkpoint("appr_4") == "stop")
    TC.clear("appr_4")


def t_signals_are_per_task():
    TC.request("appr_5a", "stop")
    check("a different id is untouched", TC.checkpoint("appr_5b") is None)
    TC.clear("appr_5a")


def t_note_is_queued_and_read_back():
    check("no note by default", TC.pending_note("appr_6") is None)
    TC.inject_note("appr_6", "also check the CC line")
    check("the note comes back", TC.pending_note("appr_6") == "also check the CC line")
    TC.clear("appr_6")
    check("clear() drops the note too", TC.pending_note("appr_6") is None)


def t_note_does_not_set_a_pause_or_stop_signal():
    # A note alone must never look like a pause/stop request to run()'s
    # own checkpoint() call - section 3d's "does not alter the steps
    # currently running" would be silently violated otherwise.
    TC.inject_note("appr_7", "wait, also cc Dana")
    check("injecting a note leaves no pause/stop signal", TC.checkpoint("appr_7") is None)
    TC.clear("appr_7")


if __name__ == "__main__":
    for fn in (t_no_signal_by_default, t_none_task_id_never_raises,
               t_request_rejects_unknown_actions, t_stop_is_read_back,
               t_pause_is_read_back, t_clear_removes_the_signal,
               t_clear_is_safe_on_an_id_with_no_signal,
               t_a_later_request_replaces_an_earlier_one,
               t_signals_are_per_task, t_note_is_queued_and_read_back,
               t_note_does_not_set_a_pause_or_stop_signal):
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
