"""jarvis_android_control.py - lets Jarvis tap around on the paired phone.

WHAT IT IS FOR, AND WHAT IT DELIBERATELY IS NOT
`Genymobile/scrcpy` was suggested as a way to test the Android app by having
Jarvis drive the phone directly. scrcpy's actual value is a live, low-latency
mirrored video feed with a persistent remote-control session - built for a
human to watch and steer in real time. That is the same shape problem as
`microsoft/UFO` (see docs/UFO-SAFETY-DESIGN.md): a live session that keeps
acting for as long as it runs cannot be the thing one approval card
authorises, because "authorise this session" is a standing grant for
whatever happens inside it, unnamed in advance.

This module does not start a scrcpy session. It uses plain, individual `adb`
commands - the same commands scrcpy itself relies on for control, minus the
persistent video mirror - because a single `adb shell input tap 400 800` is
a literal, printable, one-shot command that a person can read on a card
before it runs. A live mirrored session is not.

THE PERMISSION MODEL
    plan(device, requests)   builds the literal, enumerated adb command line
                             for each requested step. Runs nothing.
    run(plan, approved=True) executes ONLY those commands, in order, each one
                             exactly as printed on the card that was
                             approved. Re-checks the device is still the one
                             that was planned against (same serial) before
                             every command; stops rather than sending a
                             command to a phone that swapped out from under
                             it (unplugged and a different one connected,
                             say).

WHAT ACTUALLY HAPPENS
Every command talks to the device over `adb` - USB, or the phone's own local
network, the same reachability Jarvis's own Android app already uses. This
is the owner's own paired phone, not a third party, so it is not treated as
"leaving the machine" the way an outbound internet request is - but it is
still very much acting on the world (real taps land on a real phone), so the
same plan/describe/gate/run shape as everything else applies in full, and a
step whose own purpose is to make something leave the phone (send a message,
post something) must say so in its own `why`, same as jarvis_research says
what leaves the machine.

TESTING WITHOUT A PHONE
`run_adb` is the one place a real subprocess would be started, and it is
injectable - the default calls the real `adb` binary; tests inject a fake
that returns canned output and never spawns a process.

THE SCREEN'S OWN NODE TREE, AND SAYING WHICH NODE (slices 5A and 5B)
A tap at (540, 1820) is a literal command, and that is what makes it safe to
approve - but it is not something a person can check. `inspect_ui()` reads the
phone's own accessibility tree (`uiautomator dump`) and returns the nodes a
tap could act on, each with a stable 1-based `node_id`; `resolve_node_to_tap()`
turns a node - or the words on it - into the one sentence the card shows
(`Tap "Start timer" at (540, 1820)`), and says so when those words read like a
payment or something that cannot be undone. Three actions were added for it:
`long_press`, `open_app` and the read-only `ui_dump`. Two rules hold across
all of it:

  * THE DUMP IS TEXT THAT ARRIVED FROM OUTSIDE THIS PROGRAM. An app on the
    phone drew every word in it. So a document declaring a DOCTYPE or an
    ENTITY is refused outright (that is the XML parser's external-entity
    door), a password field's label is replaced with `[PASSWORD_FIELD]`, and
    EVERY label goes through `jarvis_scrub` - returning an empty label if the
    scrubber is not installed, never the raw word.
  * JARVIS DOES NOT READ OR TAP INSIDE ITS OWN APP. `inspect_ui()` refuses
    when the phone says a `com.jarvis.` app is in front, or when the dump's
    own root package is one, so a node list can never be used to aim at the
    Jarvis app's own Approve button. `run()` keeps its own check as well.
"""

from __future__ import annotations

import base64
import re
import shlex
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

# adb key event codes worth naming rather than making the caller remember
# numbers. Not exhaustive - just the ones a caller is likely to ask for.
KEYCODES = {
    "back": "KEYCODE_BACK", "home": "KEYCODE_HOME", "enter": "KEYCODE_ENTER",
    "power": "KEYCODE_POWER", "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
}

# `subprocess.run(argv)` with no `shell=True` keeps the HOST safe - each argv
# element is one literal string, nothing here is interpreted by a shell on
# THIS machine. But `adb shell <args...>` joins every argument after `shell`
# with a space and sends the result as ONE command line to the DEVICE's own
# `/system/bin/sh -c`, over the wire - a value of `"hello; reboot"` becomes
# the literal remote command `input text hello; reboot`, which the phone's
# shell splits on `;` and runs both halves. Restricting to a safe, plain-text
# character set closes that off; escaping shell metacharacters instead would
# mean getting `/system/bin/sh`'s own quoting rules exactly right on a
# device this code cannot inspect, for a feature whose whole job is typing
# plain text, not typing shell scripts.
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9 .,!?@_-]*$")
_SAFE_KEYCODE = re.compile(r"^[A-Za-z0-9_]+$")

#: An Android package name: at least two dotted segments, each starting with a
#: letter. Deliberately stricter than the platform allows (`a1.b2` is legal on
#: Android): what arrives here is a value a model produced, and the only thing
#: this pattern has to do is make sure it is a name and nothing else - no
#: space that `adb shell` would split on, no `-` that a shell would read as an
#: option, no `;` at all.
_SAFE_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")

#: A long press is a `swipe` from a point to itself, and these are the bounds
#: that keep a "press" from becoming a 30-second hold nothing can interrupt.
LONG_PRESS_DEFAULT_MS = 800
LONG_PRESS_MIN_MS = 500
LONG_PRESS_MAX_MS = 5000

#: `uiautomator dump`'s own bounds attribute, exactly.
_BOUNDS = re.compile(r"^\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]$")

#: The attribute names that make a node one a tap can act on.
_INTERACTIVE_ATTRS = ("clickable", "long-clickable", "scrollable", "checkable")

#: What a password field's label becomes. The value is never carried at all -
#: not into a card, not into a log line, not into a model's context.
PASSWORD_LABEL = "[PASSWORD_FIELD]"

#: What a label says when it would spend money or cannot be undone. The card
#: shows this so the owner reads the words he is about to approve rather than
#: a pair of coordinates.
_DESTRUCTIVE = re.compile(
    r"pay|send money|purchase|buy now|delete|erase|uninstall|"
    r"factory reset|transfer", re.IGNORECASE)

#: The steps that send NO input to the phone at all - a read of it. The
#: Jarvis-in-front guard exists to stop Jarvis TAPPING inside its own app, so
#: it is not applied to these, which is the rule a screenshot has always had
#: (test_security_pc.py pins it).
READ_ONLY_ACTIONS = ("screenshot", "ui_dump")


# --------------------------------------------------------------------------
#   The plan - the literal adb command line for each requested step
# --------------------------------------------------------------------------

@dataclass
class Step:
    action: str              # "tap" | "swipe" | "key" | "text" | "screenshot"
                             #   | "long_press" | "open_app" | "ui_dump"
    argv: list                # the literal adb command, as a list - never a
                              # shell string, so nothing here is interpreted
                              # by a shell and there is no injection surface
    why: str = ""
    heavy: bool = False

    def as_dict(self) -> dict:
        d = asdict(self)
        d["command"] = " ".join(shlex.quote(a) for a in self.argv)
        return d


@dataclass
class Plan:
    device: str
    goal: str
    steps: list = field(default_factory=list)
    rejected: list = field(default_factory=list)   # requests this module refused to turn into a step
    if_refused: str = ""

    @property
    def weight(self) -> str:
        return "heavy" if any(s.heavy for s in self.steps) else "normal"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["weight"] = self.weight
        return d


def _clamp_duration(value) -> int:
    """A hold's length in milliseconds, inside the bounds this module allows.

    Raises for a value that is not a number at all, so `plan()` reports it as
    one rejected request like every other malformed one - never a silent
    default for a duration somebody asked for.
    """
    ms = int(value)
    return max(LONG_PRESS_MIN_MS, min(LONG_PRESS_MAX_MS, ms))


def _safe_package(value) -> str:
    """A package name this module will hand to the phone's own shell.

    Two refusals, and the second is the important one: anything that is not a
    plain dotted name, and anything under `com.jarvis.` - the same rule
    `run()` enforces before every input step, applied here to the one action
    whose whole purpose is to put an app in front.
    """
    pkg = str(value or "").strip()
    if not _SAFE_PACKAGE.fullmatch(pkg):
        raise ValueError(f"not a package name: {pkg!r}")
    if pkg == "com.jarvis" or pkg.startswith(JARVIS_PACKAGE_PREFIX):
        raise ValueError(
            "Jarvis does not start its own app on the phone: a tap there "
            "could approve a card you never saw")
    return pkg


def _build_step(device: str, r: dict) -> Step:
    action = str(r.get("action", "")).strip()
    why = str(r.get("why", ""))
    heavy = bool(r.get("irreversible")) or bool(r.get("leaves_machine"))
    base = ["adb", "-s", device, "shell"]

    if action == "tap":
        x, y = int(r["x"]), int(r["y"])
        return Step(action, base + ["input", "tap", str(x), str(y)], why, heavy)
    if action == "swipe":
        x1, y1, x2, y2 = (int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"]))
        ms = int(r.get("duration_ms", 300))
        return Step(action, base + ["input", "swipe", str(x1), str(y1),
                                     str(x2), str(y2), str(ms)], why, heavy)
    if action == "key":
        name = str(r.get("key", "")).strip().lower()
        code = KEYCODES.get(name, name.upper())
        if not _SAFE_KEYCODE.fullmatch(code):
            raise ValueError(f"not a plain keycode: {code!r}")
        return Step(action, base + ["input", "keyevent", code], why, heavy)
    if action == "text":
        # adb's own quoting rules for `input text`: spaces must be escaped
        # with %s, and this is the ONE place a raw string is turned into
        # shell-visible tokens - so it is done with a fixed substitution, not
        # by handing the value to a shell. Checked against _SAFE_TEXT BEFORE
        # substitution - see that constant's own comment for why a remote
        # shell, not this process, is what a semicolon or backtick here
        # would reach.
        value = str(r.get("value", ""))
        if not _SAFE_TEXT.fullmatch(value):
            raise ValueError(
                f"text contains a character this tool will not risk sending "
                f"to the phone's own shell: {value!r}")
        return Step(action, base + ["input", "text", value.replace(" ", "%s")],
                    why, heavy)
    if action == "screenshot":
        # Read-only. Never heavy - a screenshot is not irreversible and does
        # not itself send anything anywhere; a caller who then UPLOADS it is
        # a separate, later, own step with its own `why`.
        return Step(action, ["adb", "-s", device, "exec-out", "screencap", "-p"],
                    why or "read the current screen", False)
    if action == "long_press":
        # An on-screen hold, which adb only expresses as a swipe that goes
        # nowhere: `input swipe x y x y <ms>`. The length is clamped, because
        # it is a number a model produced and a thirty-second press is not a
        # press - it is a phone that cannot be interrupted.
        x, y = int(r["x"]), int(r["y"])
        ms = _clamp_duration(r.get("duration_ms", LONG_PRESS_DEFAULT_MS))
        return Step(action, base + ["input", "swipe", str(x), str(y),
                                    str(x), str(y), str(ms)], why, heavy)
    if action == "open_app":
        # `monkey` is Android's own "launch this package's launcher activity":
        # no activity name to guess and no second way to start something on
        # the phone. A `com.jarvis.` package is refused (see _safe_package).
        pkg = _safe_package(r.get("package", ""))
        return Step(action, base + ["monkey", "-p", pkg, "-c",
                                    "android.intent.category.LAUNCHER", "1"],
                    why, heavy)
    if action == "ui_dump":
        # Read-only, like a screenshot, and never heavy: this asks the phone
        # to describe its own screen and sends no input to it at all.
        return Step(action, ["adb", "-s", device, "exec-out",
                             "uiautomator", "dump", "/dev/tty"],
                    why or "read the screen's own node tree", False)
    raise ValueError(f"unknown action {action!r}")


def plan(device: str, goal: str, requests: list) -> Plan:
    """Work out the literal commands. Runs nothing - building an argv list
    and formatting a string are the only things this function does."""
    steps, rejected = [], []
    for r in requests:
        try:
            steps.append(_build_step(device, r))
        except (KeyError, ValueError, TypeError) as exc:
            # TypeError alongside the other two: a request with `"x": null`
            # (or any non-numeric x/y/x1/y1/x2/y2) hits `int(r["x"])`, and
            # int(None) raises TypeError, not ValueError - uncaught here, it
            # used to escape plan() entirely rather than being reported as
            # one rejected request like every other malformed one.
            rejected.append({**r, "reason": str(exc)})
    return Plan(
        device=str(device), goal=str(goal), steps=steps, rejected=rejected,
        if_refused="nothing happens on the phone; the goal is not attempted")


# The weight the CARD prints is the heavier of two: the steps the model
# flagged, and the gate's own risk table - which classifies this whole
# action as one that cannot be undone and leaves the machine (by its worst
# case: tapping the phone can send a message or complete a purchase). The
# card used to print only the model's flags, so a plan whose Send click the
# model left unflagged read "weight: normal" while the notice and the risk
# line said the opposite. `Plan.weight` stays the model's own marking; this
# is what a person is shown.
CARD_WEIGHT_LINE = (
    "weight: heavy - any tap can send something or be impossible to undo, "
    "so the whole plan is treated that way. The steps marked below are the "
    "ones Jarvis flagged itself; an unmarked step is not a promise that it "
    "is safe.")


def describe(p: Plan) -> str:
    """The card text. Every literal command in full - this is an adb
    command line, and summarising it defeats the point of printing one."""
    lines = [f"Jarvis would like to do this on device {p.device}: {p.goal}",
             "",
             f"{len(p.steps)} step(s), {CARD_WEIGHT_LINE}",
             "Talks to your own paired phone over adb. Nothing goes to a "
             "third party.",
             ""]
    for i, s in enumerate(p.steps, 1):
        lines += [f"  {i}. {s.action}" +
                  ("  [Jarvis flagged: irreversible or leaves the machine]" if s.heavy else ""),
                  f"     {' '.join(shlex.quote(a) for a in s.argv)}",
                  f"     why: {s.why}", ""]
    if p.rejected:
        lines.append(f"{len(p.rejected)} requested step(s) could not be "
                      "turned into a command and will NOT run:")
        for r in p.rejected:
            lines.append(f"  - {r.get('action')!r}: {r.get('reason')}")
        lines.append("")
    lines.append(f"If you say no: {p.if_refused}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - only the enumerated commands, against the SAME device
# --------------------------------------------------------------------------

def adb_env() -> dict:
    """What adb inherits (security audit M2): jarvis_child_env's allowlist,
    plus adb's and the Android tools' own settings - never the pairing token
    or a service password, which Jarvis's own environment holds. adb finds
    its pairing key under the user's profile folder, which is on the list."""
    import jarvis_child_env
    return jarvis_child_env.inherited(prefixes=("ANDROID_", "ADB_"))


def _real_adb(argv: list, timeout: float = 15.0):
    return subprocess.run(argv, capture_output=True, timeout=timeout, env=adb_env())


# --------------------------------------------------------------------------
#   Never the Jarvis app (security audit M3, GUARDS S4, 2026-09-25)
#
#   A plan shaped by outside text could tap Approve in the Jarvis app on the
#   phone: one card would then approve another the owner never saw. So
#   before every step that sends input (everything but a screenshot), run()
#   asks the phone which app is in front - `adb shell dumpsys window`, its
#   mCurrentFocus / mFocusedApp lines - and stops if it is a Jarvis app
#   (jarvis-client's com.jarvis.client, the older jarvis-android's
#   com.jarvis.assistant, or any debug build of either: every package under
#   com.jarvis.). If the answer cannot be read, it stops too: "I could not
#   tell" is not "it is safe".
# --------------------------------------------------------------------------

JARVIS_PACKAGE_PREFIX = "com.jarvis."
_FOCUS_LINE = re.compile(r"^\s*(mCurrentFocus|mFocusedApp|mFocusedWindow)=(.*)$", re.M)
_PACKAGE = re.compile(r"\b([A-Za-z][\w]*(?:\.[\w]+)+)/")


def foreground_packages(text: str) -> Optional[list]:
    """The packages `dumpsys window` names as focused; None when it names
    none - no focus line at all (the command failed, or the phone words it
    some other way), or only lines with no package in them
    (`mCurrentFocus=null` while a window opens or the shade is pulled down,
    a popup's window title). None is "could not tell", and nothing is
    tapped: an empty list used to read as "Jarvis is not in front"
    (2026-09-26, outside audit finding 5)."""
    lines = _FOCUS_LINE.findall(text or "")
    pkgs = [m for _key, rest in lines for m in _PACKAGE.findall(rest)]
    return pkgs or None


def _focus_packages(device: str, run_adb: Callable) -> Optional[list]:
    """The packages `dumpsys window` names as focused; None when it cannot be
    read at all. One place this question is asked, so `jarvis_in_front()` and
    `inspect_ui()` cannot come to two different answers about the same phone."""
    try:
        result = run_adb(["adb", "-s", device, "shell", "dumpsys", "window"])
        out = getattr(result, "stdout", b"")
        text = out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out)
        ok = getattr(result, "returncode", 0) == 0
    except Exception:
        ok, text = False, ""
    return foreground_packages(text) if ok else None


def jarvis_in_front(device: str, run_adb: Callable) -> str:
    """"" when it is safe to send input to `device`, else why not."""
    pkgs = _focus_packages(device, run_adb)
    if pkgs is None:
        return ("Jarvis could not tell which app is in front on the phone, so it "
                "stopped rather than risk tapping inside the Jarvis app")
    for pkg in pkgs:
        if pkg.startswith(JARVIS_PACKAGE_PREFIX):
            return (f"the Jarvis app ({pkg}) is in front on the phone, and Jarvis "
                    f"does not tap inside its own app: a tap there could approve a "
                    f"card you never saw")
    return ""


#: The words a live status line may use for a step (see run()).
_STEP_WORD = {"tap": "a tap", "swipe": "a swipe", "key": "a key press",
              "text": "typing", "screenshot": "a screenshot",
              "long_press": "a long press", "open_app": "opening an app",
              "ui_dump": "a screen read"}


def _current_serials(run_adb: Callable) -> set:
    result = run_adb(["adb", "devices"])
    out = getattr(result, "stdout", b"")
    text = out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out)
    serials = set()
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.add(parts[0])
    return serials


def run(p: Plan, *, run_adb: Optional[Callable[[list], object]] = None,
        announce: Optional[Callable[[str], None]] = None,
        checkpoint: Optional[Callable[[], Optional[str]]] = None,
        receipt: Optional[Callable[..., str]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan's commands, in order, against `p.device`.

    `approved` has no default of True, same reason as every other module
    here. Before EVERY command, this checks `p.device` is still in
    `adb devices`'s own list. If it is not - unplugged, swapped for a
    different phone, wireless adb dropped - execution stops rather than
    sending a tap intended for one phone toward whatever is connected now.
    Costs one extra `adb devices` process per step; accepted, since a plan
    that spans a `screenshot` (the step most likely to run long enough for
    the phone to be unplugged mid-plan) is exactly the case this exists for,
    and there is no cheaper way to tell "still that phone" from "some phone"
    between two arbitrary steps.

    `announce(text)` is the same live-status hook as jarvis_ui_control.run -
    wire it to `jarvis_events.set_activity("working", text)` so the owner
    can see, while it is happening, that Jarvis is controlling the phone.

    `checkpoint()` is the same pause/stop hook as jarvis_ui_control.run -
    see that module's own docstring for the exact contract and why this one
    imports nothing to use it.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was sent",
                "plan": p.as_dict()}
    caller = run_adb or _real_adb
    tell = announce or (lambda _text: None)
    check = checkpoint or (lambda: None)
    # Injectable for the same reason run_adb is: a suite must be able to run a
    # whole plan without writing a receipt into the machine it is running on,
    # and one test can hand in a recorder that records nothing.
    write_receipt = receipt or _record_phone_receipt

    done, results, ui_trees = [], [], []

    def stopped_at(i: int, reason: str) -> dict:
        """Every early return from this loop, in one shape.

        `screenshots` is in here for a reason: three of the four ways this
        run can end early used to leave it out entirely, so a run that took
        two screenshots and then hit a pause reported both steps as `done`
        and handed back no images at all. A screenshot already taken is
        work already done, and the result says so on every path. `ui` is the
        same rule for a `ui_dump` step, added with it.
        """
        out = {"ok": False,
               "reason": reason,
               "done": [s.as_dict() for s in done],
               "not_run": [s.as_dict() for s in p.steps[i - 1:]],
               "screenshots": results,
               "ui": ui_trees}
        # A run that got some steps done really did act on the phone, so it
        # is written down like a completed one - and `not_run` says what was
        # left. A run that sent nothing gets no receipt: there is nothing to
        # record and an empty row is worse than none.
        if done:
            out["receipt_id"] = _write_receipt_safely(write_receipt, p, out)
        return out

    for i, step in enumerate(p.steps, 1):
        # The checkpoint is FIRST - before the device re-verification as well
        # as before the announcement, and both orderings matter.
        #
        # Before the announcement, because `announce` is wired to a sticky
        # `set_activity`: announcing a step and then pausing left the Brain
        # window claiming a step that never ran.
        #
        # Before the device check, because `jarvis_task_control.checkpoint()`
        # CONSUMES the signal, and a path that returns without reading it
        # leaves that signal in the store forever - which is exactly the
        # one-way-door bug consuming was introduced to end. The device check
        # sat above this and returned on its own, so a phone unplugged while
        # a pause was pending stranded the pause, and the next run of that
        # task id stopped at step 1 with nothing the owner could do about it.
        # Nothing is sent by reading a signal, so there is no safety cost to
        # asking first; if both are true the run stops either way, and the
        # next one reports the disconnection immediately.
        signal = check()
        if signal in ("stop", "pause"):
            result = stopped_at(
                i, "stopped by request" if signal == "stop"
                   else "paused by request - resuming needs a new decision")
            if signal == "pause":
                result["paused"] = True
            return result
        if p.device not in _current_serials(caller):
            return stopped_at(i, f"step {i} ({step.action}): device "
                                 f"{p.device!r} is no longer connected - "
                                 "stopping rather than sending it to whatever "
                                 "phone is plugged in now")
        if step.action not in READ_ONLY_ACTIONS:
            why_not = jarvis_in_front(p.device, caller)
            if why_not:
                return stopped_at(i, f"step {i} ({step.action}): {why_not}")
        # The line goes out on the event stream (`announce` is wired to
        # jarvis_events.set_activity), which reaches a phone with the screen
        # off - and ARCHITECTURE.md section 6 says an event carries "never
        # content". So only the step's number and a word from a fixed list;
        # never the text typed or the device's serial. Those are on the card the owner approved
        # (security audit L4, 2026-09-25).
        tell(f"Step {i}/{len(p.steps)}: {_STEP_WORD.get(step.action, 'a step')} on "
             f"the phone")
        result = caller(step.argv)
        rc = getattr(result, "returncode", 0)
        if rc != 0:
            stderr = getattr(result, "stderr", b"")
            msg = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else str(stderr)
            return stopped_at(
                i, f"step {i} ({step.action}) failed (exit {rc}): {msg.strip()}")
        done.append(step)
        if step.action == "screenshot":
            # base64, not raw bytes: this dict is handed straight to
            # json.dumps() by the caller (run_local_turn, so the model can
            # see the tool's result) - json.dumps() cannot serialize bytes
            # at all and raises TypeError, which was uncaught at that call
            # site and crashed the whole turn.
            raw = getattr(result, "stdout", b"")
            results.append(base64.b64encode(raw).decode("ascii"))
        elif step.action == "ui_dump":
            # The SAME parse-and-scrub path inspect_ui() uses, so there is one
            # place a screen's words are scrubbed and one place a password
            # field is masked - and a plan whose dump is malformed or declares
            # an ENTITY reports that here rather than failing the step.
            ui_trees.append(_parse_ui_dump(_text_of(result)))
    # One last read, so a Stop that arrived while the final step was running
    # is not thrown away. Every step ran, so `ok` stays True - but the owner
    # pressed Stop and is told it was seen and was too late. The read also
    # SPENDS the signal (jarvis_task_control.checkpoint), which is what keeps
    # a stop that missed its run from stopping the next one instead.
    late = check()
    out = {"ok": True, "done": [s.as_dict() for s in done], "not_run": [],
           "screenshots": results, "ui": ui_trees}
    if done:
        out["receipt_id"] = _write_receipt_safely(write_receipt, p, out)
    if late in ("stop", "pause"):
        out["late_signal"] = late
        out["note"] = (f"a {late} arrived after the last step had already run - "
                       "the plan finished, and nothing was left undone")
        tell(f"Done. (A {late} arrived too late to change anything.)")
    else:
        tell("Done.")
    return out


# --------------------------------------------------------------------------
#   The screen's own node tree - inspect_ui(), resolve_node_to_tap()
#
#   WHY THIS EXISTS. `adb shell input tap 540 1820` is a literal command, and
#   a literal command is what one approval card can honestly authorise - but
#   two numbers on a card are not something a person can check, and a model
#   asked for a tap coordinate is guessing at a picture. So the phone is asked
#   to describe its own screen (uiautomator's accessibility dump), each node a
#   tap could act on gets a stable number, and the card can say
#   `Tap "Start timer" at (540, 1820)` - words the owner can disagree with.
# --------------------------------------------------------------------------

def _text_of(result) -> str:
    """A fake or real CompletedProcess's stdout as text."""
    out = getattr(result, "stdout", b"")
    return out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out)


def _scrub_text(value) -> str:
    """`jarvis_scrub`'s words, or NOTHING AT ALL - never the raw value.

    Fail closed on purpose. A screen's words can hold a token, a key or a
    private message, so a phone whose Jarvis has no scrubber is not a phone to
    print raw text from: an empty label is a worse card and a better failure.
    """
    text = "" if value is None else str(value)
    if not text:
        return ""
    try:
        import jarvis_scrub
        return str(jarvis_scrub.scrub_text(text))
    except Exception:
        return ""


def _jarvis_package(package) -> bool:
    """Is this package name one of Jarvis's own? The one predicate, so the
    focus line and the dump's root package cannot be judged differently."""
    pkg = str(package or "")
    return pkg == "com.jarvis" or pkg.startswith(JARVIS_PACKAGE_PREFIX)


def _bounds(value) -> Optional[list]:
    """`[x1,y1][x2,y2]` as four ints, or None when it is not that shape."""
    m = _BOUNDS.match(str(value or "").strip())
    return [int(g) for g in m.groups()] if m else None


def _is_interactive(attrs) -> bool:
    return any(attrs.get(name) == "true" for name in _INTERACTIVE_ATTRS)


def _parse_ui_dump(xml_text) -> dict:
    """One `uiautomator dump` document -> the nodes a tap could act on.

    NEVER raises, and never returns a raw word. The dump is text that arrived
    from outside this program (an app on the phone drew every label in it), so:

      * a document declaring a DOCTYPE or an ENTITY is REFUSED before any
        parser sees it - that declaration is the XML parser's external-entity
        door, and no real screen dump contains one;
      * a node with `password="true"` has its label replaced with
        `[PASSWORD_FIELD]`, so the value is never carried anywhere at all;
      * every other label goes through `jarvis_scrub`, and comes back EMPTY if
        the scrubber is not there (fail closed - see `_scrub_text`).

    What is INCLUDED: a node with positive width and height that is either
    something a tap acts on (`clickable`, `long-clickable`, `scrollable`,
    `checkable`) or a labelled node inside one - because `"Start timer"` is
    usually a TextView inside the clickable row, and a card that cannot name
    it can only offer coordinates. Each included node gets a 1-based
    `node_id` in document order, which is what makes a screenshot annotation
    (5B) and a `Tap "..." at (x, y)` sentence refer to the same thing.
    """
    raw = "" if xml_text is None else str(xml_text)
    upper = raw.upper()
    # Named one at a time, not with one sentence for both: which declaration
    # was refused is the whole of what this answer has to say, and a document
    # that merely happens to be malformed must not be reported as a refusal.
    # ENTITY is asked first because an entity declaration lives INSIDE a
    # DOCTYPE, and the entity is the more specific - and the more dangerous -
    # of the two.
    for token, what in (("<!ENTITY", "ENTITY"), ("<!DOCTYPE", "DOCTYPE")):
        if token in upper:
            return {"ok": False, "nodes": [], "root_package": "",
                    "error": f"refused: the dump declares a {what}, which no "
                             f"real screen dump contains"}
    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        return {"ok": False, "nodes": [], "root_package": "",
                "error": f"the dump is not usable XML ({type(exc).__name__})"}

    nodes: list = []
    seen_package = {"pkg": ""}
    counter = {"n": 0}

    def walk(el, clickable_above):
        attrs = el.attrib
        pkg = attrs.get("package", "")
        if pkg and not seen_package["pkg"]:
            seen_package["pkg"] = pkg
        box = _bounds(attrs.get("bounds", ""))
        visible = box is not None and box[2] > box[0] and box[3] > box[1]
        is_int = _is_interactive(attrs)
        password = attrs.get("password") == "true"
        labelled = bool((attrs.get("text") or "").strip()
                        or (attrs.get("content-desc") or "").strip())
        mine = None
        if visible and (is_int or (labelled and clickable_above is not None)):
            counter["n"] += 1
            mine = counter["n"]
            # `resource-id` and `class` are identifiers, not words: they are
            # matched on by resolve_node_to_tap(), so scrubbing them would
            # break the lookup they exist for. They are not what a password
            # field hides either - the value is in `text`.
            nodes.append({
                "node_id": mine,
                "cx": (box[0] + box[2]) // 2,
                "cy": (box[1] + box[3]) // 2,
                "bounds": box,
                "text": PASSWORD_LABEL if password
                        else _scrub_text(attrs.get("text")),
                "content_desc": PASSWORD_LABEL if password
                                else _scrub_text(attrs.get("content-desc")),
                "resource_id": attrs.get("resource-id", ""),
                "class": attrs.get("class", ""),
                "package": pkg,
                "clickable": attrs.get("clickable") == "true",
                "long_clickable": attrs.get("long-clickable") == "true",
                "scrollable": attrs.get("scrollable") == "true",
                "checkable": attrs.get("checkable") == "true",
                "enabled": attrs.get("enabled", "true") == "true",
                "password": password,
                "actionable_id": mine if is_int else clickable_above,
            })
            node = nodes[-1]
            node["label"] = (node["text"] or node["content_desc"] or "").strip()
        next_above = mine if (is_int and visible) else clickable_above
        for child in el:
            walk(child, next_above)

    walk(root, None)
    return {"ok": True, "nodes": nodes, "root_package": seen_package["pkg"],
            "error": ""}


def inspect_ui(device: str, *, run_adb: Optional[Callable[[list], object]] = None) -> dict:
    """The phone's own description of its screen, as nodes a tap could act on.

    Read-only: no input is sent to the phone. `run_adb` is injectable exactly
    as `run()`'s is, so a suite can inspect a canned screen and never start a
    process.

    Refused outright (`{"blocked": True, "reason": "jarvis_in_front", ...}`)
    when a `com.jarvis.` app is in front on the phone OR the dump's own root
    package is one: a node list from inside the Jarvis app is a list of the
    owner's Approve buttons, and nothing here should be able to name one.

    When the phone cannot say which app is in front the nodes ARE returned,
    with `front_unknown: True`. That is not a hole: this function taps
    nothing, and `run()` re-asks the same question and refuses before any step
    that sends input. Refusing here as well would make the inspector useless
    on any phone whose `dumpsys` is worded differently, for no safety gained.
    """
    caller = run_adb or _real_adb
    argv = ["adb", "-s", str(device), "exec-out", "uiautomator", "dump", "/dev/tty"]
    try:
        result = caller(argv)
        rc = getattr(result, "returncode", 0)
        text = _text_of(result)
    except Exception as exc:
        return {"ok": False, "blocked": False, "nodes": [], "count": 0,
                "error": f"could not read the screen's node tree "
                         f"({type(exc).__name__})"}
    if rc != 0:
        err = getattr(result, "stderr", b"")
        msg = err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)
        return {"ok": False, "blocked": False, "nodes": [], "count": 0,
                "error": f"the dump failed (exit {rc}): {msg.strip()}"}

    parsed = _parse_ui_dump(text)
    if not parsed["ok"]:
        return {"ok": False, "blocked": False, "nodes": [], "count": 0,
                "error": parsed["error"]}

    pkgs = _focus_packages(str(device), caller)
    focused_jarvis = next((p for p in (pkgs or []) if _jarvis_package(p)), None)
    if focused_jarvis or _jarvis_package(parsed["root_package"]):
        return {"blocked": True, "reason": "jarvis_in_front", "nodes": [],
                "ok": False, "count": 0}

    out = {"ok": True, "blocked": False, "nodes": parsed["nodes"],
           "count": len(parsed["nodes"]), "root_package": parsed["root_package"]}
    if pkgs is None:
        out["front_unknown"] = True
    return out


def _nodes_of(ui_dump) -> list:
    """The node list out of whatever a caller was holding: the whole dict
    `inspect_ui()` returned, or the list on its own."""
    if isinstance(ui_dump, dict):
        nodes = ui_dump.get("nodes")
        return list(nodes) if isinstance(nodes, list) else []
    if isinstance(ui_dump, list):
        return list(ui_dump)
    return []


def _candidate(node: dict) -> dict:
    """One possibility, in the shape the card can print."""
    return {"node_id": node.get("node_id"), "label": node.get("label", ""),
            "cx": node.get("cx"), "cy": node.get("cy"),
            "resource_id": node.get("resource_id", "")}


def resolve_node_to_tap(ui_dump, *, node_id=None, text=None,
                        resource_id=None) -> dict:
    """Say which node a tap would land on, and where - words a person reads.

    Exactly one of `node_id`, `text` or `resource_id` is the question; when
    several match, NOTHING is chosen. Two nodes reading "Delete" is exactly
    the case where guessing is worst, so the answer is the list and a plain
    sentence saying to name one.

    It resolves to the ACTIONABLE node, not to the label: when "Start timer"
    is a TextView inside a clickable row, the coordinates are the row's,
    because that is where the tap will land. The sentence always names the
    label the owner will recognise and the point the tap will use.
    """
    nodes = _nodes_of(ui_dump)
    if not nodes:
        return {"ok": False, "reason": "there are no nodes to resolve against"}
    by_id = {n.get("node_id"): n for n in nodes}

    if node_id is not None:
        try:
            want = int(node_id)
        except (TypeError, ValueError):
            return {"ok": False, "reason": f"node_id {node_id!r} is not a number"}
        found = by_id.get(want)
        if found is None:
            return {"ok": False, "reason": f"there is no node {want} on this screen"}
        matches = [found]
        asked = f"node {want}"
    elif resource_id:
        matches = [n for n in nodes if n.get("resource_id") == resource_id]
        asked = f"resource_id {resource_id!r}"
    elif text:
        needle = str(text).casefold()
        matches = [n for n in nodes
                   if needle and needle in ((n.get("label") or "").casefold())]
        asked = f"text {text!r}"
    else:
        return {"ok": False,
                "reason": "name a node_id, a text or a resource_id - none was given"}

    if not matches:
        return {"ok": False, "reason": f"nothing on this screen matches {asked}"}
    if len(matches) > 1:
        return {"ok": False,
                "reason": f"{len(matches)} nodes match {asked} - say which one",
                "candidates": [_candidate(n) for n in matches]}

    node = matches[0]
    target = by_id.get(node.get("actionable_id")) or node
    label = (node.get("label") or target.get("label") or "").strip()
    hit = _DESTRUCTIVE.search(f'{node.get("label", "")} {target.get("label", "")}')
    say = (f'Tap "{label}" at ({target["cx"]}, {target["cy"]})' if label
           else f'Tap node {target.get("node_id")} at ({target["cx"]}, {target["cy"]})')
    out = {"ok": True,
           "node_id": node.get("node_id"),
           "tap_node_id": target.get("node_id"),
           "cx": target["cx"], "cy": target["cy"],
           "label": label,
           "resource_id": node.get("resource_id", ""),
           "destructive": bool(hit),
           "say": say}
    if hit:
        out["warning"] = ("That label reads like a payment or like something "
                          "that cannot be undone. Read it before you approve.")
    return out


# --------------------------------------------------------------------------
#   5B - Set-of-Mark: number the nodes on the picture
#
#   A vision model looking at a raw screenshot guesses at coordinates. The
#   same picture with `[7]` drawn on the node it should press lets it answer
#   with a node id, and a node id is something resolve_node_to_tap() and the
#   card can both check. OFF by default: it is a new thing to show a model,
#   and every new thing here starts off.
# --------------------------------------------------------------------------

ANNOTATE_NODES_DEFAULT = False
_annotate_enabled = ANNOTATE_NODES_DEFAULT


def annotate_nodes_enabled() -> bool:
    """Is the Set-of-Mark overlay on for this process?"""
    return bool(_annotate_enabled)


def set_annotate_nodes_enabled(on: bool) -> bool:
    """Turn the overlay on or off for this process, and return what it is now.
    Nothing is loosened by it - a tagged picture stays on this PC - so it
    raises no card; it is off, like every other new thing, until it is asked
    for."""
    global _annotate_enabled
    _annotate_enabled = bool(on)
    return _annotate_enabled


def _annotate_font(ImageFont, size: int = 28):
    """A readable font, or PIL's own tiny one, or None. Never raises: a
    missing font is not a reason to refuse to annotate a picture."""
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def annotate_screenshot_with_nodes(png_bytes, nodes, *, enabled=None) -> bytes:
    """The screenshot with each node's number drawn on it. OFF by default.

    Returns the picture UNCHANGED - byte for byte, so a caller can tell - when
    the switch is off, when there is no picture library, when the picture is
    not one this can read, or when there are no nodes. A half-drawn picture or
    an exception would each be worse than the picture it was given.
    """
    on = _annotate_enabled if enabled is None else bool(enabled)
    items = _nodes_of(nodes)
    if not on or not png_bytes or not items:
        return png_bytes
    try:
        import io

        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return png_bytes
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    except Exception:
        return png_bytes
    try:
        draw = ImageDraw.Draw(img)
        font = _annotate_font(ImageFont)
        for node in items:
            box = node.get("bounds") or []
            if len(box) != 4:
                continue
            x1, y1, x2, y2 = (int(v) for v in box)
            draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=3)
            tag = f"[{node.get('node_id')}]"
            try:
                left, top, right, bottom = draw.textbbox((0, 0), tag, font=font)
                tw, th = right - left, bottom - top
            except Exception:
                tw, th = 9 * len(tag), 14
            ty = y1 - th - 6
            if ty < 0:
                ty = y2 + 3
            draw.rectangle([x1, ty, x1 + tw + 8, ty + th + 6], fill=(255, 0, 0))
            draw.text((x1 + 4, ty + 3), tag, fill=(255, 255, 255), font=font)
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        # A picture that cannot be drawn on is handed back exactly as it came.
        return png_bytes


# --------------------------------------------------------------------------
#   The receipt - one row for a run that really did act on the phone
# --------------------------------------------------------------------------

def _write_receipt_safely(write_receipt, p: Plan, out: dict) -> str:
    """A receipt must never fail the thing it records.

    `jarvis_receipts`'s own rule ("`record()` must never raise into the caller"),
    applied to whatever recorder was handed in - including one a caller
    supplied and one that is not installed at all."""
    try:
        return str(write_receipt(p, out) or "")
    except Exception:
        return ""


def _record_phone_receipt(p: Plan, out: dict) -> str:
    """One receipt for one run that sent something, or "".

    The same shape as `jarvis_goals.py`'s own receipt call: not installed is
    not an error, and a receipt that cannot be written must never fail the
    thing it was recording. There is NO `undo` and no restorer, on purpose - a
    tap on a phone cannot be put back, so `jarvis_receipts` says exactly that
    rather than offering a button that pretends otherwise.
    """
    done = out.get("done") or []
    if not done:
        return ""
    try:
        import jarvis_receipts
    except Exception:
        return ""
    try:
        summary = (f'Ran {len(done)} of {len(p.steps)} step(s) on the phone '
                   f'"{p.device}": {p.goal}')
        before = {"device": p.device, "goal": p.goal, "steps": len(p.steps)}
        after = {"done": [s.get("action") for s in done],
                 "not_run": [s.get("action") for s in (out.get("not_run") or [])]}
        return jarvis_receipts.record("control_phone", summary,
                                      before=before, after=after)
    except Exception:
        return ""
