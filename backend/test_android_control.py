"""jarvis_android_control.py: literal adb commands, never a live session.

Proves: plan() never runs adb, run() refuses without approval, every command
is a real argv list (no shell string, no injection surface), and run()
re-checks the device is still connected before every step rather than
sending a tap toward whatever phone happens to be plugged in now.

    python3 test_android_control.py
"""
import base64
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_android_control as A

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Result:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class NoRealProcess:
    """Fail loudly if the real subprocess-calling adb ever runs."""

    def __enter__(self):
        self.real = A._real_adb
        def boom(argv, timeout=15.0):
            raise AssertionError(f"a real process was started: {argv}")
        A._real_adb = boom
        return self

    def __exit__(self, *a):
        A._real_adb = self.real
        return False


DEVICES_OUT = b"List of devices attached\nEMULATOR123\tdevice\n\n"


def adb_ok(devices_out=DEVICES_OUT):
    """A fake `run_adb` that answers `adb devices` and succeeds otherwise."""
    def caller(argv):
        if argv[:2] == ["adb", "devices"]:
            return Result(0, devices_out)
        return Result(0, b"")
    return caller


def t_planning_runs_nothing():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "open the app and tap through onboarding",
                   [{"action": "tap", "x": 100, "y": 200, "why": "tap the app icon"},
                    {"action": "text", "value": "hello there", "why": "type a greeting",
                     "irreversible": False}])
    check("both requests became steps", len(p.steps) == 2, repr(p.steps))
    check("nothing rejected", p.rejected == [], repr(p.rejected))
    check("the tap step is a literal argv, not a shell string",
          p.steps[0].argv == ["adb", "-s", "EMULATOR123", "shell", "input", "tap", "100", "200"],
          repr(p.steps[0].argv))
    check("text spaces are escaped adb's way, not shell-quoted",
          "%s" in " ".join(p.steps[1].argv) and "hello there" not in p.steps[1].argv,
          repr(p.steps[1].argv))


def t_unknown_action_is_rejected_not_guessed():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "do something weird",
                   [{"action": "levitate", "why": "x"}])
    check("an unknown action becomes 0 steps", p.steps == [], repr(p.steps))
    check("and is reported as rejected", len(p.rejected) == 1, repr(p.rejected))


def t_missing_fields_are_rejected_not_guessed():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap somewhere",
                   [{"action": "tap", "x": 5, "why": "missing y"}])
    check("a tap missing y is rejected, not defaulted to 0", p.steps == [], repr(p.steps))
    check("card explains why", "y" in A.describe(p) or "reason" in repr(p.rejected))


def t_a_null_coordinate_is_rejected_not_a_crash():
    """int(None) raises TypeError, not ValueError - plan()'s own except used
    to only catch (KeyError, ValueError), so a request like
    {"action": "tap", "x": null, "y": null} escaped plan() entirely instead
    of landing in `rejected` like every other malformed request."""
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap nothing in particular",
                   [{"action": "tap", "x": None, "y": None, "why": "x"}])
    check("a null coordinate is rejected, not a crash", p.steps == [], repr(p.steps))
    check("and is reported as rejected", len(p.rejected) == 1, repr(p.rejected))


def t_shell_metacharacters_in_typed_text_are_rejected():
    """`adb shell <args...>` joins every argument with a space and runs the
    result as ONE command on the DEVICE's own shell - `input text "hello;
    reboot"` becomes the remote command `input text hello; reboot`, which
    the phone's shell splits on `;` and runs both halves. This is the one
    thing standing between "type this text" and arbitrary code execution on
    the paired phone."""
    for bad in ("hello; reboot", "a && pm uninstall com.jarvis.client",
                "$(reboot)", "`reboot`", "a | b", "a > /sdcard/x"):
        with NoRealProcess():
            p = A.plan("EMULATOR123", "type something",
                       [{"action": "text", "value": bad, "why": "x"}])
        check(f"rejected as unsafe for the remote shell: {bad!r}",
              p.steps == [] and len(p.rejected) == 1, repr(p.rejected))
    with NoRealProcess():
        p = A.plan("EMULATOR123", "type something",
                   [{"action": "text", "value": "hello world, how are you?", "why": "x"}])
    check("plain text with normal punctuation still works",
          len(p.steps) == 1, repr(p.rejected))


def t_shell_metacharacters_in_a_keycode_are_rejected():
    for bad in ("x; reboot", "$(reboot)", "back`;`"):
        with NoRealProcess():
            p = A.plan("EMULATOR123", "press a key",
                       [{"action": "key", "key": bad, "why": "x"}])
        check(f"rejected as unsafe for the remote shell: {bad!r}",
              p.steps == [] and len(p.rejected) == 1, repr(p.rejected))
    with NoRealProcess():
        p = A.plan("EMULATOR123", "press back", [{"action": "key", "key": "back", "why": "x"}])
    check("a real, named keycode still works", len(p.steps) == 1, repr(p.rejected))


def t_the_card_prints_every_command_in_full():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap the button",
                   [{"action": "tap", "x": 1, "y": 2, "why": "because the button is there"}])
    card = A.describe(p)
    check("the device is named", "EMULATOR123" in card, card)
    check("the literal command is on the card", "input tap 1 2" in card, card)
    check("the reason is on the card", "because the button is there" in card, card)
    check("it says this stays with the owner's own phone",
          "own paired phone" in card, card)
    check("it says what refusing costs", "If you say no" in card, card)


def t_run_refuses_without_approval():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "x"}])
        out = A.run(p, run_adb=lambda argv: (_ for _ in ()).throw(
            AssertionError("adb ran without approval")))
    check("run() does nothing without approval", out["ok"] is False, repr(out))
    check("and says so plainly", "not approved" in out["reason"], out["reason"])


def t_run_refuses_if_the_device_disconnected():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "x"}])
        out = A.run(p, run_adb=adb_ok(devices_out=b"List of devices attached\n\n"),
                    approved=True)
    check("a vanished device stops execution", out["ok"] is False, repr(out))
    check("and says which device and why", "EMULATOR123" in out["reason"]
          and "no longer connected" in out["reason"], out["reason"])
    check("nothing is reported done", out["done"] == [], repr(out))


def t_run_stops_at_the_first_failed_command():
    calls = []
    def caller(argv):
        if argv[:2] == ["adb", "devices"]:
            return Result(0, DEVICES_OUT)
        calls.append(argv)
        if len(calls) == 1:
            return Result(0, b"")
        return Result(1, b"", b"device offline mid-command")
    with NoRealProcess():
        p = A.plan("EMULATOR123", "two taps",
                   [{"action": "tap", "x": 1, "y": 1, "why": "first"},
                    {"action": "tap", "x": 2, "y": 2, "why": "second"}])
        out = A.run(p, run_adb=caller, approved=True)
    check("the first command ran", len(calls) == 2, repr(calls))  # devices check not counted
    check("run() reports the failure", out["ok"] is False, repr(out))
    check("names the failing step and the exit reason",
          "step 2" in out["reason"] and "device offline" in out["reason"], out["reason"])
    check("exactly one step reported done", len(out["done"]) == 1, repr(out["done"]))
    check("the failed step is in not_run, not silently dropped",
          len(out["not_run"]) == 1, repr(out["not_run"]))


def t_run_executes_every_approved_step_and_reports_screenshots():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "look then tap",
                   [{"action": "screenshot", "why": "see what's on screen"},
                    {"action": "tap", "x": 5, "y": 5, "why": "tap it"}])
        def caller(argv):
            if argv[:2] == ["adb", "devices"]:
                return Result(0, DEVICES_OUT)
            if "screencap" in argv:
                return Result(0, b"\x89PNGfakebytes")
            return Result(0, b"")
        out = A.run(p, run_adb=caller, approved=True)
    check("CONTROL: a fully valid plan runs to completion", out["ok"] is True, repr(out))
    check("both steps done, nothing left", len(out["done"]) == 2 and out["not_run"] == [], repr(out))
    # base64, not raw bytes: the caller (run_local_turn) feeds this whole
    # dict to json.dumps(), which cannot serialize bytes at all.
    check("the screenshot is returned base64-encoded, not as raw bytes "
          "json.dumps() would crash on",
          out["screenshots"] == [base64.b64encode(b"\x89PNGfakebytes").decode("ascii")],
          repr(out))
    check("it really is JSON-serializable now",
          json.dumps(out) is not None)


def t_announce_is_called_and_is_optional():
    heard = []
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "x"}])
        out = A.run(p, run_adb=adb_ok(), announce=heard.append, approved=True)
    check("announce heard the step and a final message", len(heard) == 2, repr(heard))
    check("the step text names the device", "EMULATOR123" in heard[0], heard[0])
    with NoRealProcess():
        p2 = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "x"}])
        out2 = A.run(p2, run_adb=adb_ok(), approved=True)
    check("CONTROL: omitting announce still runs to completion", out2["ok"] is True, repr(out2))


def t_checkpoint_stop_ends_the_run_before_the_next_step():
    acted = []
    signals = iter([None, "stop"])
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap twice",
                   [{"action": "tap", "x": 1, "y": 1, "why": "x"},
                    {"action": "tap", "x": 2, "y": 2, "why": "y"}])
        def caller(argv):
            if argv[:2] == ["adb", "devices"]:
                return Result(0, DEVICES_OUT)
            acted.append(argv)
            return Result(0, b"")
        out = A.run(p, run_adb=caller, checkpoint=lambda: next(signals), approved=True)
    check("only the first tap ran", len(acted) == 1, repr(acted))
    check("run() reports not-ok", out["ok"] is False, repr(out))
    check("the reason names a stop", "stopped" in out["reason"], out["reason"])
    check("the second step is reported not-run", len(out["not_run"]) == 1, repr(out))


def t_checkpoint_pause_ends_the_run_and_says_so():
    acted = []
    signals = iter([None, "pause"])
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap twice",
                   [{"action": "tap", "x": 1, "y": 1, "why": "x"},
                    {"action": "tap", "x": 2, "y": 2, "why": "y"}])
        def caller(argv):
            if argv[:2] == ["adb", "devices"]:
                return Result(0, DEVICES_OUT)
            acted.append(argv)
            return Result(0, b"")
        out = A.run(p, run_adb=caller, checkpoint=lambda: next(signals), approved=True)
    check("only the first tap ran", len(acted) == 1, repr(acted))
    check("the result says paused", out.get("paused") is True, repr(out))
    check("the second step is still reported, ready to resume",
          len(out["not_run"]) == 1, repr(out))


def t_no_checkpoint_given_behaves_exactly_as_before():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "x"}])
        out = A.run(p, run_adb=adb_ok(), approved=True)
    check("CONTROL: runs to completion with no checkpoint hook at all",
          out["ok"] is True and out["not_run"] == [], repr(out))


def t_a_pause_still_returns_the_screenshots_already_taken():
    # A screenshot already captured is work already done. Three of the four
    # ways this run can end early used to drop `screenshots` entirely, so a
    # run that shot the screen and then hit a pause reported that step as
    # `done` and handed back no image at all - the one thing the step exists
    # to produce.
    signals = iter([None, "pause"])
    with NoRealProcess():
        p = A.plan("EMULATOR123", "look then tap",
                   [{"action": "screenshot", "why": "see what's on screen"},
                    {"action": "tap", "x": 2, "y": 2, "why": "y"}])
        def caller(argv):
            if argv[:2] == ["adb", "devices"]:
                return Result(0, DEVICES_OUT)
            return Result(0, b"\x89PNGfakebytes")
        out = A.run(p, run_adb=caller, checkpoint=lambda: next(signals), approved=True)
    check("the run paused", out.get("paused") is True, repr(out))
    check("the screenshot step is reported done", len(out["done"]) == 1, repr(out))
    check("and its image came back with it",
          out.get("screenshots") == [base64.b64encode(b"\x89PNGfakebytes").decode("ascii")],
          repr(out.get("screenshots")))


def t_a_failed_step_still_returns_earlier_screenshots():
    # Same rule on the adb-failure path, which had the same hole.
    with NoRealProcess():
        p = A.plan("EMULATOR123", "look then tap",
                   [{"action": "screenshot", "why": "see what's on screen"},
                    {"action": "tap", "x": 2, "y": 2, "why": "y"}])
        calls = []
        def caller(argv):
            if argv[:2] == ["adb", "devices"]:
                return Result(0, DEVICES_OUT)
            calls.append(argv)
            if len(calls) == 1:
                return Result(0, b"\x89PNGfakebytes")
            return Result(1, b"", b"device offline")
        out = A.run(p, run_adb=caller, approved=True)
    check("the run reports not-ok", out["ok"] is False, repr(out))
    check("the earlier screenshot survived the failure",
          out.get("screenshots") == [base64.b64encode(b"\x89PNGfakebytes").decode("ascii")],
          repr(out.get("screenshots")))


def t_a_stop_during_the_final_step_is_reported_not_swallowed():
    signals = iter([None, "stop"])
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "x"}])
        out = A.run(p, run_adb=adb_ok(), checkpoint=lambda: next(signals), approved=True)
    check("the plan really did finish", out["ok"] is True, repr(out))
    check("the late stop is acknowledged", out.get("late_signal") == "stop", repr(out))


def t_the_checkpoint_is_read_before_the_step_is_announced():
    # `announce` is wired to a sticky set_activity, so announcing a step and
    # then pausing left the Brain window naming a step that never ran. This
    # ordering had no test until a mutation run showed a straight revert of
    # it passing the whole suite.
    heard, acted = [], []
    signals = iter([None, "pause"])
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap twice",
                   [{"action": "tap", "x": 1, "y": 1, "why": "x"},
                    {"action": "tap", "x": 2, "y": 2, "why": "y"}])
        def caller(argv):
            if argv[:2] == ["adb", "devices"]:
                return Result(0, DEVICES_OUT)
            acted.append(argv)
            return Result(0, b"")
        out = A.run(p, run_adb=caller, announce=heard.append,
                    checkpoint=lambda: next(signals), approved=True)
    check("only the first tap ran", len(acted) == 1, repr(acted))
    check("exactly one step was announced", len(heard) == 1, repr(heard))
    check("and it is the step that actually ran",
          heard and heard[0].startswith("Step 1/2"), repr(heard))
    check("nothing claimed the run finished",
          not any("Done" in line for line in heard), repr(heard))


def t_a_pause_is_read_even_when_the_device_has_gone():
    # The checkpoint sat BELOW the device re-verification, which returns on
    # its own - so a phone unplugged while a pause was pending stranded the
    # pause in the store, and since checkpoint() consumes, nothing would ever
    # take it. The next run of that task id stopped at step 1, permanently:
    # the one-way door the consuming change exists to prevent.
    taken = []

    def checkpoint():
        # A real store hands the signal over once and then has nothing.
        return taken.append("pause") or "pause" if not taken else None

    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "x"}])
        def gone(argv):
            if argv[:2] == ["adb", "devices"]:
                return Result(0, b"List of devices attached\n")   # nothing attached
            return Result(0, b"")
        out = A.run(p, run_adb=gone, checkpoint=checkpoint, approved=True)
    check("the pending pause was read, not stranded", taken == ["pause"], repr(taken))
    check("and the run reports the pause it actually saw",
          out.get("paused") is True, repr(out))


if __name__ == "__main__":
    for fn in (t_planning_runs_nothing, t_unknown_action_is_rejected_not_guessed,
               t_missing_fields_are_rejected_not_guessed,
               t_a_null_coordinate_is_rejected_not_a_crash,
               t_shell_metacharacters_in_typed_text_are_rejected,
               t_shell_metacharacters_in_a_keycode_are_rejected,
               t_the_card_prints_every_command_in_full, t_run_refuses_without_approval,
               t_run_refuses_if_the_device_disconnected,
               t_run_stops_at_the_first_failed_command,
               t_run_executes_every_approved_step_and_reports_screenshots,
               t_announce_is_called_and_is_optional,
               t_checkpoint_stop_ends_the_run_before_the_next_step,
               t_checkpoint_pause_ends_the_run_and_says_so,
               t_no_checkpoint_given_behaves_exactly_as_before,
               t_a_pause_still_returns_the_screenshots_already_taken,
               t_a_failed_step_still_returns_earlier_screenshots,
               t_a_stop_during_the_final_step_is_reported_not_swallowed,
               t_the_checkpoint_is_read_before_the_step_is_announced,
               t_a_pause_is_read_even_when_the_device_has_gone):
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
