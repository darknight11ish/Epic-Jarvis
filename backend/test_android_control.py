"""jarvis_android_control.py: literal adb commands, never a live session.

Proves: plan() never runs adb, run() refuses without approval, every command
is a real argv list (no shell string, no injection surface), and run()
re-checks the device is still connected before every step rather than
sending a tap toward whatever phone happens to be plugged in now.

    python3 test_android_control.py
"""
import base64
import io
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_android_control as A

#: The receipts database this suite writes to. run() writes one receipt per run
#: that sent something, so the whole suite is pointed at a scratch file BEFORE
#: anything imports jarvis_receipts - the same shape test_receipts.py uses.
#: `os.makedirs` over a fixed name, never tempfile.mkdtemp: a 0o700 directory
#: is not writable in this project's own sandbox, and a suite that could not
#: write there would report a failure that is not the code's.
_RECEIPTS_DIR = Path(tempfile.gettempdir()) / "jarvis-android-control-tests"
os.makedirs(_RECEIPTS_DIR, exist_ok=True)
os.environ["JARVIS_RECEIPTS_DB"] = str(_RECEIPTS_DIR / "receipts.db")

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (A `check("SKIP - ...", True)` would be counted as a pass
    by this suite and by backend/run_suites.py; tools/check_vacuous_checks.py
    exists because that shape shipped.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


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
#: `adb shell dumpsys window` with the home screen in front, not Jarvis. Every
#: input step now asks this first (security audit M3).
FOCUS_OUT = (b"  mCurrentFocus=Window{1a2b u0 com.android.launcher3/"
             b"com.android.launcher3.Launcher}\n"
             b"  mFocusedApp=ActivityRecord{3c4d u0 com.android.launcher3/.Launcher t1}\n")


def adb_ok(devices_out=DEVICES_OUT):
    """A fake `run_adb` that answers `adb devices` and succeeds otherwise."""
    def caller(argv):
        if "dumpsys" in argv:
            return Result(0, FOCUS_OUT)   # another app in front
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
        if "dumpsys" in argv:
            return Result(0, FOCUS_OUT)   # another app in front
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
            if "dumpsys" in argv:
                return Result(0, FOCUS_OUT)   # another app in front
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
    # Security audit L4: no content on the event stream.
    check("the step text is the step's number and a fixed word",
          heard[0] == "Step 1/1: a tap on the phone", heard[0])
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
            if "dumpsys" in argv:
                return Result(0, FOCUS_OUT)   # another app in front
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
            if "dumpsys" in argv:
                return Result(0, FOCUS_OUT)   # another app in front
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
            if "dumpsys" in argv:
                return Result(0, FOCUS_OUT)   # another app in front
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
            if "dumpsys" in argv:
                return Result(0, FOCUS_OUT)   # another app in front
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
            if "dumpsys" in argv:
                return Result(0, FOCUS_OUT)   # another app in front
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
            if "dumpsys" in argv:
                return Result(0, FOCUS_OUT)   # another app in front
            if argv[:2] == ["adb", "devices"]:
                return Result(0, b"List of devices attached\n")   # nothing attached
            return Result(0, b"")
        out = A.run(p, run_adb=gone, checkpoint=checkpoint, approved=True)
    check("the pending pause was read, not stranded", taken == ["pause"], repr(taken))
    check("and the run reports the pause it actually saw",
          out.get("paused") is True, repr(out))


# --------------------------------------------------------------------------
#   Slices 5A and 5B: the node tree, the semantic tap, the safety guards
# --------------------------------------------------------------------------

#: `dumpsys window` with the JARVIS app in front. The one state run() and
#: inspect_ui() must both refuse to act in.
JARVIS_FOCUS = (b"  mCurrentFocus=Window{1a2b u0 com.jarvis.client/"
                b"com.jarvis.client.MainActivity}\n")


def _attrs(pkg="com.example.timer"):
    return ('package="%s" content-desc="%%s" checkable="%%s" checked="false"' % pkg)


def ui_node(text="", resource_id="", cls="android.widget.Button",
            pkg="com.example.timer", bounds="[0,0][100,100]", clickable="true",
            password="false", content_desc="", long_clickable="false",
            scrollable="false", checkable="false", enabled="true"):
    """One `<node .../>` in the shape `uiautomator dump` really writes."""
    return ('<node index="0" text="%s" resource-id="%s" class="%s" package="%s" '
            'content-desc="%s" checkable="%s" checked="false" clickable="%s" '
            'enabled="%s" focusable="false" focused="false" scrollable="%s" '
            'long-clickable="%s" password="%s" selected="false" bounds="%s"/>'
            % (text, resource_id, cls, pkg, content_desc, checkable, clickable,
               enabled, scrollable, long_clickable, password, bounds))


def ui_row(bounds, resource_id="row", clickable="true", *children):
    """A container with children - the shape a clickable row has."""
    return ('<node index="0" text="" resource-id="%s" '
            'class="android.widget.LinearLayout" package="com.example.timer" '
            'content-desc="" checkable="false" checked="false" clickable="%s" '
            'enabled="true" focusable="false" focused="false" scrollable="false" '
            'long-clickable="false" password="false" selected="false" '
            'bounds="%s">%s</node>'
            % (resource_id, clickable, bounds, "".join(children)))


def ui_xml(*nodes):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
            '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>")


def ui_xml_with(declaration, *nodes):
    """A dump carrying a DOCTYPE/ENTITY declaration, in the only place a
    document may carry one: AFTER the XML declaration. Put it before, and the
    document is malformed for a reason that has nothing to do with this guard,
    which would make the check below pass without proving anything."""
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
            + declaration + '<hierarchy rotation="0">' + "".join(nodes)
            + "</hierarchy>")


def ui_adb(xml="", focus=FOCUS_OUT, dump_rc=0):
    """A fake `run_adb` that answers the node dump and the focus question."""
    def caller(argv):
        if "uiautomator" in argv:
            return Result(dump_rc, xml.encode("utf-8"),
                          b"" if dump_rc == 0 else b"no dump for you")
        if "dumpsys" in argv:
            if focus is None:
                return Result(1, b"", b"dumpsys is not answering")
            return Result(0, focus)
        if argv[:2] == ["adb", "devices"]:
            return Result(0, DEVICES_OUT)
        return Result(0, b"")
    return caller


def ui_of(xml, focus=FOCUS_OUT, dump_rc=0):
    with NoRealProcess():
        return A.inspect_ui("EMULATOR123", run_adb=ui_adb(xml, focus, dump_rc))


def _png_bytes(w, h):
    """A real PNG, or None when this machine has no picture library."""
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (30, 30, 40)).save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def t_inspect_ui_reads_the_phone_s_own_tree():
    xml = ui_xml(ui_node(text="Start timer", resource_id="com.example.timer:id/start",
                         bounds="[400,1700][680,1940]"))
    with NoRealProcess():
        ui = A.inspect_ui("EMULATOR123", run_adb=ui_adb(xml))
    check("the dump is read through the injected adb helper", ui["ok"] is True, repr(ui))
    check("its node is there, numbered from 1",
          [n["node_id"] for n in ui["nodes"]] == [1], repr(ui["nodes"]))
    node = ui["nodes"][0]
    check("the centre is the middle of the bounds, integer division",
          (node["cx"], node["cy"]) == (540, 1820), (node["cx"], node["cy"]))
    check("the label and the resource id are carried",
          node["label"] == "Start timer"
          and node["resource_id"] == "com.example.timer:id/start", node)
    check("the count and the root package are reported",
          ui["count"] == 1 and ui["root_package"] == "com.example.timer", ui)


def t_inspect_ui_offers_only_nodes_a_tap_could_act_on():
    xml = ui_xml(
        ui_node(text="Start timer", bounds="[400,1700][680,1940]"),
        ui_node(text="zero width", bounds="[10,10][10,40]"),
        ui_node(text="zero height", bounds="[10,10][40,10]"),
        ui_node(text="plain words", clickable="false",
                cls="android.widget.TextView", bounds="[0,0][100,50]"))
    ui = ui_of(xml)
    check("a node with no width or no height is never offered",
          [n["label"] for n in ui["nodes"]] == ["Start timer"], repr(ui["nodes"]))
    check("... so nothing on the screen can be aimed at a zero-size box",
          all((n["bounds"][2] - n["bounds"][0]) > 0
              and (n["bounds"][3] - n["bounds"][1]) > 0 for n in ui["nodes"]), ui["nodes"])


def t_a_label_inside_a_clickable_row_points_at_the_row():
    row = ui_row("[0,100][1080,200]", "row", "true",
                 ui_node(text="Start timer", clickable="false",
                         cls="android.widget.TextView", bounds="[20,120][300,180]"))
    ui = ui_of(ui_xml(row))
    check("both the row and its label are offered", len(ui["nodes"]) == 2, repr(ui["nodes"]))
    check("the label points at the node a tap would really act on",
          ui["nodes"][1]["actionable_id"] == ui["nodes"][0]["node_id"],
          repr(ui["nodes"]))
    check("the row carries its own id and no actionable parent",
          ui["nodes"][0]["actionable_id"] == ui["nodes"][0]["node_id"], repr(ui["nodes"]))


def t_inspect_ui_masks_a_password_field():
    secret = "hunter2-the-real-password"
    xml = ui_xml(ui_node(text=secret, password="true",
                         resource_id="com.example.timer:id/pw", bounds="[0,0][100,100]"))
    ui = ui_of(xml)
    node = ui["nodes"][0]
    check("the password field's label is replaced", node["text"] == A.PASSWORD_LABEL, node)
    check("and so is its content-desc", node["content_desc"] == A.PASSWORD_LABEL, node)
    check("the secret is nowhere in the result at all",
          secret not in json.dumps(ui), json.dumps(ui)[:200])
    check("but the field is still offered, so it can be tapped",
          node["password"] is True and node["clickable"] is True, node)
    check("the label a card would print is the mask, not the value",
          node["label"] == A.PASSWORD_LABEL, node["label"])


def _with_fake_scrubber(mod):
    """Swap jarvis_scrub out for one call, and put it back."""
    saved = sys.modules.get("jarvis_scrub", "<missing>")
    sys.modules["jarvis_scrub"] = mod
    return saved


def _restore_scrubber(saved):
    if saved == "<missing>":
        sys.modules.pop("jarvis_scrub", None)
    else:
        sys.modules["jarvis_scrub"] = saved


def t_every_label_goes_through_the_scrubber():
    class FakeScrub:
        @staticmethod
        def scrub_text(text):
            return "[REDACTED]" if "token" in text else text

    xml = ui_xml(ui_node(text="the token value", bounds="[0,0][100,100]"),
                 ui_node(text="Start timer", bounds="[0,200][100,300]"))
    saved = _with_fake_scrubber(FakeScrub)
    try:
        ui = ui_of(xml)
    finally:
        _restore_scrubber(saved)
    check("a label with a secret in it is scrubbed",
          ui["nodes"][0]["text"] == "[REDACTED]", ui["nodes"][0])
    check("... and one without is passed through unchanged",
          ui["nodes"][1]["text"] == "Start timer", ui["nodes"][1])
    check("the raw word is nowhere in the result",
          "the token value" not in json.dumps(ui), json.dumps(ui)[:200])


def t_inspect_ui_fails_closed_when_the_scrubber_breaks_or_is_missing():
    class Broken:
        @staticmethod
        def scrub_text(text):
            raise RuntimeError("no scrubber here")

    xml = ui_xml(ui_node(text="the token value", bounds="[0,0][100,100]"))
    saved = _with_fake_scrubber(Broken)
    try:
        ui = ui_of(xml)
    finally:
        _restore_scrubber(saved)
    check("a scrubber that raises gives an EMPTY label, never the raw word",
          ui["nodes"][0]["text"] == "" and ui["nodes"][0]["content_desc"] == "",
          ui["nodes"][0])
    check("... and the raw word is nowhere in the result",
          "the token value" not in json.dumps(ui), json.dumps(ui)[:200])

    saved = _with_fake_scrubber(None)     # `import jarvis_scrub` now fails
    try:
        ui2 = ui_of(xml)
    finally:
        _restore_scrubber(saved)
    check("no scrubber module at all: still an empty label, never raw",
          ui2["nodes"][0]["text"] == "" and "the token value" not in json.dumps(ui2),
          json.dumps(ui2)[:200])


def t_a_dump_declaring_a_doctype_or_an_entity_is_refused():
    node = ui_node(text="Start timer")
    # BOTH of these documents PARSE cleanly in ElementTree - measured - so the
    # guard below is the only thing refusing them. A DOCTYPE placed before the
    # XML declaration is malformed for an unrelated reason and would prove
    # nothing.
    for what, declaration in (
            ("DOCTYPE", '<!DOCTYPE hierarchy SYSTEM "http://example.invalid/x.dtd">'),
            ("ENTITY", '<!DOCTYPE hierarchy [<!ENTITY xxe "boom">]>')):
        bad = ui_xml_with(declaration, node)
        ui = ui_of(bad)
        check(f"a dump declaring a {what} is refused, not parsed",
              ui["ok"] is False and ui["nodes"] == [], repr(ui))
        check(f"... and it names the {what} it refused",
              what in (ui.get("error") or "").upper(), ui.get("error"))
        check(f"... and the same document without the {what} IS parsed",
              ui_of(ui_xml(node))["ok"] is True)


def t_a_malformed_or_failed_dump_is_reported_not_raised():
    ui = ui_of("<hierarchy><node index=\"0\"")
    check("a truncated dump is a plain failure", ui["ok"] is False, repr(ui))
    check("... with a sentence, not a traceback",
          "usable XML" in (ui.get("error") or ""), ui.get("error"))
    ui2 = ui_of("", FOCUS_OUT, dump_rc=1)
    check("a dump command that exits non-zero is a plain failure",
          ui2["ok"] is False and "exit 1" in (ui2.get("error") or ""), repr(ui2))


def t_inspect_ui_refuses_inside_the_jarvis_app():
    xml = ui_xml(ui_node(text="Approve", bounds="[0,0][100,100]"))
    ui = ui_of(xml, JARVIS_FOCUS)
    check("a Jarvis app in front: blocked", ui.get("blocked") is True, repr(ui))
    check("... with the one reason word", ui.get("reason") == "jarvis_in_front", repr(ui))
    check("... and NO nodes at all come back", ui.get("nodes") == [], repr(ui))


def t_inspect_ui_refuses_a_dump_whose_own_root_package_is_jarvis():
    xml = ui_xml(ui_node(text="Approve", pkg="com.jarvis.client", bounds="[0,0][100,100]"))
    ui = ui_of(xml, FOCUS_OUT)          # the launcher is in front, the dump is not
    check("the dump's own package is enough on its own",
          ui.get("blocked") is True and ui.get("reason") == "jarvis_in_front", repr(ui))
    check("... and no nodes come back", ui.get("nodes") == [], repr(ui))


def t_inspect_ui_says_when_it_cannot_tell_which_app_is_in_front():
    """A read is not an input: the nodes come back, with the uncertainty named.
    `run()` asks the same question again and refuses before any step that
    sends input, which is where the refusal has to be."""
    xml = ui_xml(ui_node(text="Start timer", bounds="[0,0][100,100]"))
    ui = ui_of(xml, None)               # the focus question cannot be answered
    check("the nodes are still returned for a read", ui["ok"] is True and ui["count"] == 1,
          repr(ui))
    check("... and the result says it could not tell", ui.get("front_unknown") is True, repr(ui))
    check("... and it is NOT reported as blocked",
          ui.get("blocked") is False and ui.get("nodes") != [], repr(ui))


def t_run_still_refuses_a_tap_when_it_cannot_tell_which_app_is_in_front():
    def gone_focus(argv):
        if "dumpsys" in argv:
            return Result(1, b"", b"dumpsys is not answering")
        if argv[:2] == ["adb", "devices"]:
            return Result(0, DEVICES_OUT)
        return Result(0, b"")
    acted = []

    def caller(argv):
        acted.append(argv)
        return gone_focus(argv)
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "x"}])
        out = A.run(p, run_adb=caller, approved=True, receipt=lambda *a, **k: "")
    check("the tap is not sent when the phone cannot say what is in front",
          out["ok"] is False and "could not tell" in out["reason"], repr(out))
    check("... and no input argv was ever sent",
          not any("input" in argv for argv in acted), repr(acted))


def t_long_press_is_a_clamped_swipe_to_itself():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "hold the button",
                   [{"action": "long_press", "x": 10, "y": 20, "why": "hold"}])
    check("the default hold is 800 ms", p.steps[0].argv[-1] == "800", p.steps[0].argv)
    check("it is a swipe from the point to itself, which is what a hold is",
          p.steps[0].argv == ["adb", "-s", "EMULATOR123", "shell", "input", "swipe",
                              "10", "20", "10", "20", "800"], p.steps[0].argv)
    for asked, want in ((100, "500"), (999999, "5000"), (1200, "1200"), (800, "800")):
        with NoRealProcess():
            p = A.plan("EMULATOR123", "hold",
                       [{"action": "long_press", "x": 1, "y": 2,
                         "duration_ms": asked, "why": "x"}])
        check(f"a {asked} ms hold is clamped to {want} ms", p.steps[0].argv[-1] == want,
              p.steps[0].argv)
    with NoRealProcess():
        p = A.plan("EMULATOR123", "hold",
                   [{"action": "long_press", "x": 1, "y": 2,
                     "duration_ms": "not a number", "why": "x"}])
    check("a duration that is not a number is rejected, not defaulted",
          p.steps == [] and len(p.rejected) == 1, repr(p.rejected))


def t_open_app_refuses_jarvis_and_anything_that_is_not_a_package():
    for bad in ("com.jarvis.client", "com.jarvis.assistant.debug", "com.jarvis",
                "not a package", "com.example;reboot", "com.example.app -n evil",
                "-n", ""):
        with NoRealProcess():
            p = A.plan("EMULATOR123", "open it",
                       [{"action": "open_app", "package": bad, "why": "x"}])
        check(f"open_app refuses {bad!r}", p.steps == [] and len(p.rejected) == 1,
              repr(p.rejected))
    for good in ("com.example.timer", "com.android.settings"):
        with NoRealProcess():
            p = A.plan("EMULATOR123", "open it",
                       [{"action": "open_app", "package": good, "why": "x"}])
        check(f"open_app accepts {good}", len(p.steps) == 1, repr(p.rejected))
    with NoRealProcess():
        p = A.plan("EMULATOR123", "open it",
                   [{"action": "open_app", "package": "com.example.timer", "why": "x"}])
    check("... and starts it with Android's own launcher, as argv",
          p.steps[0].argv == ["adb", "-s", "EMULATOR123", "shell", "monkey",
                              "-p", "com.example.timer", "-c",
                              "android.intent.category.LAUNCHER", "1"],
          p.steps[0].argv)


def t_ui_dump_is_read_only_and_never_heavy():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "read the screen",
                   [{"action": "ui_dump", "why": "", "irreversible": True,
                     "leaves_machine": True}])
    check("a dump is never heavy, whatever the model flagged",
          p.steps[0].heavy is False, p.steps[0])
    check("... and it is the phone's own dump command",
          p.steps[0].argv == ["adb", "-s", "EMULATOR123", "exec-out",
                              "uiautomator", "dump", "/dev/tty"], p.steps[0].argv)
    check("it is in the read-only set, with a screenshot",
          A.READ_ONLY_ACTIONS == ("screenshot", "ui_dump"), A.READ_ONLY_ACTIONS)


def t_a_ui_dump_step_runs_even_with_jarvis_in_front_like_a_screenshot():
    xml = ui_xml(ui_node(text="Start timer", bounds="[0,0][100,100]"))

    def caller(argv):
        if "dumpsys" in argv:
            return Result(0, JARVIS_FOCUS)
        if argv[:2] == ["adb", "devices"]:
            return Result(0, DEVICES_OUT)
        if "uiautomator" in argv:
            return Result(0, xml.encode("utf-8"))
        return Result(0, b"")
    with NoRealProcess():
        p = A.plan("EMULATOR123", "read the screen",
                   [{"action": "ui_dump", "why": "see what is there"}])
        out = A.run(p, run_adb=caller, approved=True, receipt=lambda *a, **k: "")
    check("a read-only dump is not blocked by the Jarvis-in-front guard",
          out["ok"] is True, repr(out))
    check("... and its tree came back, parsed and scrubbed",
          bool(out.get("ui")) and out["ui"][0]["ok"] is True
          and out["ui"][0]["nodes"][0]["label"] == "Start timer", repr(out.get("ui")))


def t_resolve_node_to_tap_by_id_text_and_resource_id():
    ui = ui_of(ui_xml(
        ui_node(text="Start timer", resource_id="com.example.timer:id/start",
                bounds="[400,1700][680,1940]"),
        ui_node(text="Cancel", resource_id="com.example.timer:id/cancel",
                bounds="[0,0][100,100]")))
    by_text = A.resolve_node_to_tap(ui, text="Start timer")
    check("by its words: the card says what it is about to do",
          by_text["ok"] is True
          and by_text["say"] == 'Tap "Start timer" at (540, 1820)', repr(by_text))
    by_id = A.resolve_node_to_tap(ui, node_id=2)
    check("by node id", by_id["ok"] is True and by_id["label"] == "Cancel", repr(by_id))
    by_res = A.resolve_node_to_tap(ui, resource_id="com.example.timer:id/start")
    check("by resource id", by_res["ok"] is True and by_res["node_id"] == 1, repr(by_res))
    check("matching words is case-insensitive",
          A.resolve_node_to_tap(ui, text="start TIMER")["ok"] is True)
    check("a node that is not there is a refusal, not a guess",
          A.resolve_node_to_tap(ui, node_id=99)["ok"] is False,
          A.resolve_node_to_tap(ui, node_id=99))
    check("nothing named at all is a refusal",
          A.resolve_node_to_tap(ui)["ok"] is False, A.resolve_node_to_tap(ui))


def t_resolve_node_to_tap_refuses_to_guess_between_two_matches():
    ui = ui_of(ui_xml(
        ui_node(text="Delete", resource_id="a", bounds="[0,0][100,100]"),
        ui_node(text="Delete", resource_id="b", bounds="[0,200][100,300]")))
    r = A.resolve_node_to_tap(ui, text="Delete")
    check("two nodes reading the same: NOTHING is chosen", r["ok"] is False, repr(r))
    check("... and both are listed so the caller can say which",
          len(r.get("candidates") or []) == 2, repr(r))
    check("... and the reason is in plain words",
          "say which" in (r.get("reason") or ""), r.get("reason"))
    check("a screen with nothing matching is a plain refusal",
          A.resolve_node_to_tap(ui, text="Reboot")["ok"] is False)
    check("no nodes at all is a plain refusal",
          A.resolve_node_to_tap({"nodes": []}, node_id=1)["ok"] is False)


def t_resolve_node_to_tap_flags_a_payment_or_something_undoneable():
    for label, want in (("Pay now", True), ("Send money", True), ("Purchase", True),
                        ("Buy now", True), ("Delete account", True),
                        ("Erase everything", True), ("Uninstall", True),
                        ("Factory reset", True), ("Transfer to savings", True),
                        ("Start timer", False), ("Player one", False),
                        ("Cancel", False)):
        ui = ui_of(ui_xml(ui_node(text=label)))
        r = A.resolve_node_to_tap(ui, node_id=1)
        check(f"{label!r}: flagged as destructive = {want}", r["destructive"] is want,
              repr(r))
        if want:
            check(f"{label!r}: the card gets a sentence, not just a flag",
                  "before you approve" in (r.get("warning") or ""), repr(r))


def t_the_tap_lands_on_the_row_not_on_its_label():
    row = ui_row("[0,100][1080,200]", "row", "true",
                 ui_node(text="Delete", clickable="false",
                         cls="android.widget.TextView", bounds="[20,120][300,180]"))
    ui = ui_of(ui_xml(row))
    r = A.resolve_node_to_tap(ui, text="Delete")
    check("the card names the word the owner recognises", r["label"] == "Delete", repr(r))
    check("... and the point is the clickable row's centre, where the tap lands",
          (r["cx"], r["cy"]) == (540, 150) and r["tap_node_id"] == 1, repr(r))
    check("... and the sentence carries both",
          r["say"] == 'Tap "Delete" at (540, 150)', r["say"])
    check("... and a label reached through a row is still flagged",
          r["destructive"] is True, repr(r))


def t_the_five_original_actions_are_still_exactly_what_they_were():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "the old five", [
            {"action": "tap", "x": 100, "y": 200, "why": "w"},
            {"action": "swipe", "x1": 1, "y1": 2, "x2": 3, "y2": 4,
             "duration_ms": 300, "why": "w"},
            {"action": "key", "key": "back", "why": "w"},
            {"action": "text", "value": "hello there", "why": "w"},
            {"action": "screenshot", "why": "w"}])
    check("CONTROL: all five still build", len(p.steps) == 5, repr(p.rejected))
    check("... and every argv is byte for byte what it was",
          [s.argv for s in p.steps] == [
              ["adb", "-s", "EMULATOR123", "shell", "input", "tap", "100", "200"],
              ["adb", "-s", "EMULATOR123", "shell", "input", "swipe", "1", "2",
               "3", "4", "300"],
              ["adb", "-s", "EMULATOR123", "shell", "input", "keyevent",
               "KEYCODE_BACK"],
              ["adb", "-s", "EMULATOR123", "shell", "input", "text", "hello%sthere"],
              ["adb", "-s", "EMULATOR123", "exec-out", "screencap", "-p"]],
          [s.argv for s in p.steps])
    check("... and an unknown action is still rejected",
          A.plan("EMULATOR123", "x", [{"action": "levitate"}]).rejected != [])


def t_the_three_new_actions_are_literal_argv_and_never_a_shell_string():
    with NoRealProcess():
        p = A.plan("EMULATOR123", "the new three", [
            {"action": "long_press", "x": 1, "y": 2, "why": "w"},
            {"action": "open_app", "package": "com.example.timer", "why": "w"},
            {"action": "ui_dump", "why": "w"}])
    check("all three built", len(p.steps) == 3, repr(p.rejected))
    for step in p.steps:
        check(f"{step.action}: a list of plain strings, not a shell string",
              isinstance(step.argv, list)
              and all(isinstance(a, str) for a in step.argv), step.argv)
    joined = " ".join(a for s in p.steps for a in s.argv)
    check("... and nothing that a phone's own shell would split on",
          not any(ch in joined for ch in (";", "|", "&&", "`", "$(")), joined)


def t_the_new_steps_have_their_own_words_and_leak_no_content():
    check("a hold has a word of its own",
          A._STEP_WORD.get("long_press") == "a long press", A._STEP_WORD)
    check("so does opening an app",
          A._STEP_WORD.get("open_app") == "opening an app", A._STEP_WORD)
    check("so does a screen read",
          A._STEP_WORD.get("ui_dump") == "a screen read", A._STEP_WORD)
    heard = []
    with NoRealProcess():
        p = A.plan("EMULATOR123", "hold the button",
                   [{"action": "long_press", "x": 540, "y": 1820, "why": "w"}])
        A.run(p, run_adb=adb_ok(), announce=heard.append, approved=True,
              receipt=lambda *a, **k: "")
    check("the status line carries the step's word and NOT its coordinates",
          heard and heard[0] == "Step 1/1: a long press on the phone", repr(heard))


def t_run_hands_the_receipt_recorder_what_really_happened():
    seen = []
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap once",
                   [{"action": "tap", "x": 1, "y": 1, "why": "w"}])
        out = A.run(p, run_adb=adb_ok(), approved=True,
                    receipt=lambda plan, result: seen.append((plan, result)) or "rc-test")
    check("the recorder was called once", len(seen) == 1, repr(seen))
    check("... with the plan that was approved", seen and seen[0][0] is p, repr(seen))
    check("... and the result that really happened",
          seen and [s["action"] for s in seen[0][1]["done"]] == ["tap"], repr(seen))
    check("its id is on the result", out.get("receipt_id") == "rc-test", repr(out))

    def explode(plan, result):
        raise RuntimeError("no receipts here")
    with NoRealProcess():
        p2 = A.plan("EMULATOR123", "tap once",
                    [{"action": "tap", "x": 1, "y": 1, "why": "w"}])
        out2 = A.run(p2, run_adb=adb_ok(), approved=True, receipt=explode)
    check("CONTROL: a recorder that raises never fails the action it records",
          out2["ok"] is True and out2.get("receipt_id") == "", repr(out2))


def t_a_run_that_sent_nothing_writes_no_receipt():
    seen = []
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap", [{"action": "tap", "x": 1, "y": 1, "why": "w"}])
        A.run(p, run_adb=adb_ok(devices_out=b"List of devices attached\n\n"),
              approved=True, receipt=lambda plan, result: seen.append(result) or "x")
    check("a plan that never ran sends nothing to the recorder", seen == [], repr(seen))
    check("... and the default recorder writes nothing either",
          A._record_phone_receipt(p, {"done": []}) == "")


def t_a_real_receipt_is_written_for_the_phone():
    try:
        import jarvis_receipts as R
    except Exception as exc:                      # pragma: no cover
        skip(f"jarvis_receipts is not importable here ({type(exc).__name__})")
        return
    with NoRealProcess():
        p = A.plan("EMULATOR123", "tap the start button",
                   [{"action": "tap", "x": 540, "y": 1820, "why": "w"}])
        rid = A._record_phone_receipt(p, {"done": [p.steps[0].as_dict()], "not_run": []})
    check("a real receipt is written and its id comes back",
          bool(rid) and rid.startswith("rc"), rid)
    if not rid:
        return
    try:
        row = R.get(rid) or {}
    except Exception as exc:                      # pragma: no cover
        skip(f"jarvis_receipts.get() could not be read here ({type(exc).__name__})")
        return
    text = json.dumps(row)
    check("... it is a control_phone receipt", row.get("tool_name") == "control_phone",
          text[:200])
    check("... it names the phone and the goal", "EMULATOR123" in text, text[:200])
    check("... and it offers no undo, because a tap cannot be put back",
          not (row.get("undo") or row.get("restorer")), text[:200])


def t_annotate_is_off_until_it_is_switched_on():
    png = _png_bytes(1080, 1920)
    if png is None:                               # pragma: no cover
        skip("no picture library here to make a test PNG")
        return
    nodes = [{"node_id": 1, "bounds": [400, 1700, 680, 1940]}]
    was = A.annotate_nodes_enabled()
    try:
        check("the default is OFF", A.ANNOTATE_NODES_DEFAULT is False,
              A.ANNOTATE_NODES_DEFAULT)
        A.set_annotate_nodes_enabled(False)
        check("off: the picture comes back byte for byte",
              A.annotate_screenshot_with_nodes(png, nodes) == png)
        A.set_annotate_nodes_enabled(True)
        check("the switch remembers that it was turned on",
              A.annotate_nodes_enabled() is True)
        out = A.annotate_screenshot_with_nodes(png, nodes)
        check("on: the picture is changed", out != png and len(out) > 0)
        check("... and is still a real PNG", out[:8] == b"\x89PNG\r\n\x1a\n", out[:8])
        from PIL import Image
        check("... of the same size, so a coordinate still means the same place",
              Image.open(io.BytesIO(out)).size == (1080, 1920),
              Image.open(io.BytesIO(out)).size)
        check("the switch can be turned back off",
              A.set_annotate_nodes_enabled(False) is False
              and A.annotate_screenshot_with_nodes(png, nodes) == png)
    finally:
        A.set_annotate_nodes_enabled(was)


def t_annotate_hands_back_anything_it_cannot_draw_on():
    png = _png_bytes(64, 64)
    if png is None:                               # pragma: no cover
        skip("no picture library here to make a test PNG")
        return
    was = A.annotate_nodes_enabled()
    A.set_annotate_nodes_enabled(True)
    try:
        check("a picture that is not a PNG comes back untouched",
              A.annotate_screenshot_with_nodes(
                  b"not a png at all",
                  [{"node_id": 1, "bounds": [0, 0, 10, 10]}]) == b"not a png at all")
        check("no nodes: untouched",
              A.annotate_screenshot_with_nodes(png, []) == png)
        check("no picture: untouched", A.annotate_screenshot_with_nodes(
            b"", [{"node_id": 1, "bounds": [0, 0, 1, 1]}]) == b"")
    finally:
        A.set_annotate_nodes_enabled(was)


def t_annotate_does_nothing_without_a_picture_library():
    png = _png_bytes(64, 64)
    if png is None:                               # pragma: no cover
        skip("no picture library here to make a test PNG")
        return
    names = ("PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont")
    saved = {name: sys.modules.get(name, "<missing>") for name in names}
    was = A.annotate_nodes_enabled()
    try:
        for name in names:
            sys.modules[name] = None              # `from PIL import ...` now fails
        A.set_annotate_nodes_enabled(True)
        check("no picture library: the picture comes back untouched",
              A.annotate_screenshot_with_nodes(
                  png, [{"node_id": 1, "bounds": [0, 0, 10, 10]}]) == png)
    finally:
        A.set_annotate_nodes_enabled(was)
        for name, mod in saved.items():
            if mod == "<missing>":
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


#: EVERY test in this file, by hand. A `t_` function that is not in here is
#: dead code that reports nothing, so the runner checks this tuple against the
#: module's own `t_` names below and fails if they differ.
RUN = (
    t_planning_runs_nothing, t_unknown_action_is_rejected_not_guessed,
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
    t_a_pause_is_read_even_when_the_device_has_gone,
    # 5A / 5B
    t_inspect_ui_reads_the_phone_s_own_tree,
    t_inspect_ui_offers_only_nodes_a_tap_could_act_on,
    t_a_label_inside_a_clickable_row_points_at_the_row,
    t_inspect_ui_masks_a_password_field,
    t_every_label_goes_through_the_scrubber,
    t_inspect_ui_fails_closed_when_the_scrubber_breaks_or_is_missing,
    t_a_dump_declaring_a_doctype_or_an_entity_is_refused,
    t_a_malformed_or_failed_dump_is_reported_not_raised,
    t_inspect_ui_refuses_inside_the_jarvis_app,
    t_inspect_ui_refuses_a_dump_whose_own_root_package_is_jarvis,
    t_inspect_ui_says_when_it_cannot_tell_which_app_is_in_front,
    t_run_still_refuses_a_tap_when_it_cannot_tell_which_app_is_in_front,
    t_long_press_is_a_clamped_swipe_to_itself,
    t_open_app_refuses_jarvis_and_anything_that_is_not_a_package,
    t_ui_dump_is_read_only_and_never_heavy,
    t_a_ui_dump_step_runs_even_with_jarvis_in_front_like_a_screenshot,
    t_resolve_node_to_tap_by_id_text_and_resource_id,
    t_resolve_node_to_tap_refuses_to_guess_between_two_matches,
    t_resolve_node_to_tap_flags_a_payment_or_something_undoneable,
    t_the_tap_lands_on_the_row_not_on_its_label,
    t_the_five_original_actions_are_still_exactly_what_they_were,
    t_the_three_new_actions_are_literal_argv_and_never_a_shell_string,
    t_the_new_steps_have_their_own_words_and_leak_no_content,
    t_run_hands_the_receipt_recorder_what_really_happened,
    t_a_run_that_sent_nothing_writes_no_receipt,
    t_a_real_receipt_is_written_for_the_phone,
    t_annotate_is_off_until_it_is_switched_on,
    t_annotate_hands_back_anything_it_cannot_draw_on,
    t_annotate_does_nothing_without_a_picture_library,
)


if __name__ == "__main__":
    for fn in RUN:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    # The trap this file's own runner is: a test that was written and never
    # listed reports nothing and is counted as nothing. Checked, not assumed.
    _defined = {name for name, value in list(globals().items())
                if name.startswith("t_") and callable(value)
                and getattr(value, "__module__", None) == __name__}
    _unlisted = sorted(_defined - {fn.__name__ for fn in RUN})
    if _unlisted:
        FAILED.append("every t_ function in this file is in RUN")
        print(f"FAIL  a t_ function that never runs is dead code: {_unlisted}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if SKIPPED:
        print(f"{len(SKIPPED)} skipped (never counted as a pass): "
              + "; ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
