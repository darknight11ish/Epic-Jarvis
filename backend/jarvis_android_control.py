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
"""

from __future__ import annotations

import base64
import re
import shlex
import subprocess
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


# --------------------------------------------------------------------------
#   The plan - the literal adb command line for each requested step
# --------------------------------------------------------------------------

@dataclass
class Step:
    action: str              # "tap" | "swipe" | "key" | "text" | "screenshot"
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


def describe(p: Plan) -> str:
    """The card text. Every literal command in full - this is an adb
    command line, and summarising it defeats the point of printing one."""
    lines = [f"Jarvis would like to do this on device {p.device}: {p.goal}",
             "",
             f"{len(p.steps)} step(s), weight: {p.weight}.",
             "Talks to your own paired phone over adb. Nothing goes to a "
             "third party.",
             ""]
    for i, s in enumerate(p.steps, 1):
        lines += [f"  {i}. {s.action}" +
                  ("  [irreversible or leaves the machine]" if s.heavy else ""),
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

def _real_adb(argv: list, timeout: float = 15.0):
    return subprocess.run(argv, capture_output=True, timeout=timeout)


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

    done, results = [], []
    for i, step in enumerate(p.steps, 1):
        if p.device not in _current_serials(caller):
            return {"ok": False,
                    "reason": (f"step {i} ({step.action}): device "
                               f"{p.device!r} is no longer connected - "
                               "stopping rather than sending it to whatever "
                               "phone is plugged in now"),
                    "done": [s.as_dict() for s in done],
                    "not_run": [s.as_dict() for s in p.steps[i - 1:]]}
        tell(f"Step {i}/{len(p.steps)}: {step.action} on {p.device}")
        signal = check()
        if signal in ("stop", "pause"):
            remaining = p.steps[i - 1:]
            result = {"ok": False,
                      "reason": ("stopped by request" if signal == "stop"
                                 else "paused by request - resuming needs a new decision"),
                      "done": [s.as_dict() for s in done],
                      "not_run": [s.as_dict() for s in remaining]}
            if signal == "pause":
                result["paused"] = True
            return result
        result = caller(step.argv)
        rc = getattr(result, "returncode", 0)
        if rc != 0:
            stderr = getattr(result, "stderr", b"")
            msg = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else str(stderr)
            return {"ok": False,
                    "reason": f"step {i} ({step.action}) failed (exit {rc}): {msg.strip()}",
                    "done": [s.as_dict() for s in done],
                    "not_run": [s.as_dict() for s in p.steps[i - 1:]]}
        done.append(step)
        if step.action == "screenshot":
            # base64, not raw bytes: this dict is handed straight to
            # json.dumps() by the caller (run_local_turn, so the model can
            # see the tool's result) - json.dumps() cannot serialize bytes
            # at all and raises TypeError, which was uncaught at that call
            # site and crashed the whole turn.
            raw = getattr(result, "stdout", b"")
            results.append(base64.b64encode(raw).decode("ascii"))
    tell("Done.")
    return {"ok": True, "done": [s.as_dict() for s in done], "not_run": [],
            "screenshots": results}
