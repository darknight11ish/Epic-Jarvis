"""jarvis_ui_control.py - lets Jarvis click inside OTHER Windows programs.

WHAT IT IS FOR
Jarvis cannot touch any other app's UI today. `microsoft/UFO` was suggested
as a way to fix that - it reads the Windows accessibility tree (UI
Automation, "UIA") instead of guessing pixel coordinates, so it clicks named
buttons rather than blind (x, y) positions. That idea is worth having. UFO's
own architecture is not: see docs/UFO-SAFETY-DESIGN.md for why its live
perceive-act loop - keep clicking on its own judgment until the goal looks
done - is a standing grant for future, unnamed actions, which is exactly what
this project's one hard rule forbids. This module takes the idea (read the
tree, click named controls) and builds it the shape docs/ARCHITECTURE.md
requires instead: no dependency on UFO, no loop.

THE PERMISSION MODEL, WHICH IS THE POINT
    plan(goal, window, requests)   reads the CURRENT accessibility tree of
                                    one window - no input is sent - and binds
                                    each requested control to a concrete,
                                    identified UI element. Returns a Plan: a
                                    bounded, fully enumerated list of Steps
                                    decided now, not improvised later.
    run(plan, approved=True)       executes ONLY the enumerated steps, in
                                    order. Before each one, re-reads the tree
                                    and checks the target is still there,
                                    still enabled, and still the same control
                                    it was at plan time. The moment that is
                                    not true - the window closed, a dialog
                                    appeared, the control moved - run() STOPS
                                    and reports exactly which step failed,
                                    rather than guessing or clicking the
                                    nearest thing. Whatever changed needs a
                                    new plan() and a new decision, not a
                                    retry of the old one.

WHY ONE CARD FOR SEVERAL STEPS IS NOT AN "APPROVE ALL"
Same reasoning as jarvis_research.py, which this module's shape is copied
from: one decision for one bounded, fully-printed set of steps is not a
standing grant. A goal that needs to change mid-way - because a step failed,
or because it turns out to need one more click nobody enumerated - is a NEW
plan and a new decision. Nothing here is allowed to keep going on its own
say-so past the steps that were shown and approved.

WHAT ACTUALLY HAPPENS, AND WHAT DOES NOT LEAVE THIS MACHINE
Reading the accessibility tree and sending a click or keystroke are both
entirely local - no network, no credential, nothing here touches the API-key
rule at all. If a requested step is itself a network action from inside the
target app (typing into a browser that then submits a form), that step's
`why` has to say so, in full, same as jarvis_research says what leaves the
machine - this module does not detect that on its own; the caller states it.

TESTING WITHOUT WINDOWS
Real accessibility-tree reads and real input happen through two small
functions, `read` and `act`, both injectable - exactly how jarvis_research.py
injects `fetch` so its grading logic can be tested with no socket. Nothing in
this file imports a Windows-only package at module load time; the default
`read`/`act` only try to import one when actually called with nothing
injected, and fail with a clear message rather than a stack trace from deep
inside a missing dependency.

ONE WINDOW AT A TIME, AND PROOF THAT AN ACTION LANDED
`get_window_state(pid, window_id)` and `deliver(element_token, action)` are the
second half of this module. The first reads ONE window of another program - its
accessibility tree, and only when asked, that window's OWN pixels - and refuses
to guess which window was meant when a process owns several. The second acts on
one control through a standard UI Automation pattern and then READS THE CONTROL
BACK to say whether anything actually changed: "confirmed", "unverifiable", or
"suspected_noop" with an escalation offered. Background delivery comes first,
because it never raises the window, takes focus or moves the owner's mouse; the
version that takes the screen forward needs its own approval and puts the
previous foreground window back. Both are injectable the same way `read`/`act`
are (`windows`, `tree`, `screen`, `pattern`, `foreground`), so every rung and
every refusal is testable with no desktop at all. Certain key combinations
(Win+L, Ctrl+Alt+Del, Alt+F4) and dangerous shell patterns are refused
outright, by `blocked_hotkey`/`blocked_text`.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

# The two things a caller MUST tell this module, because it cannot infer
# them from the UI tree on its own: whether a step can be undone, and
# whether it makes something leave the machine. Both push a plan to "heavy".
IRREVERSIBLE_HINT = "irreversible"
LEAVES_MACHINE_HINT = "leaves_machine"


# --------------------------------------------------------------------------
#   The plan - built locally from a live but read-only look at the screen
# --------------------------------------------------------------------------

@dataclass
class Step:
    """One concrete action, bound to one concrete control. Nothing here is
    resolved again at run() time except to VERIFY it still matches - the
    identity was decided at plan() time, not guessed at run() time."""
    window: str
    control: str            # the accessible name, as read from the tree
    automation_id: str       # empty string if the control has none
    action: str              # "click" | "type" | "select" | "read"
    value: Optional[str] = None
    why: str = ""
    heavy: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    goal: str
    window: str
    steps: list = field(default_factory=list)
    # Requests that named a control the tree did not have. These are NOT
    # steps and will not run - describe() must say so plainly, because a
    # silently-dropped step is a plan that does something other than what
    # it claims.
    unmatched: list = field(default_factory=list)
    if_refused: str = ""

    @property
    def weight(self) -> str:
        return "heavy" if any(s.heavy for s in self.steps) else "normal"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["weight"] = self.weight
        return d


# How many levels deep _default_read walks below the window itself. Direct
# children only (the original shape here) sees almost nothing in a real
# Windows app: WPF, WinUI and most Win32 dialogs nest their actual controls
# inside panes, group boxes, toolbars and tab items several levels down, so
# every one of them was reported "not found" at plan() time - not because
# the control was not on screen, but because this never looked past the
# window's immediate children. Unbounded recursion is the other failure
# mode (a virtualised list or a deeply nested layout can be very large); an
# explicit, generous-but-finite depth is the middle ground.
_READ_DEPTH = 8


def _default_read(window: str) -> list:
    """The real accessibility-tree read. Windows-only, imported lazily so
    this module loads fine on any platform and fails clearly, not with an
    ImportError three frames down, when nobody injected a `read`."""
    try:
        import uiautomation as auto  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "no UI reader was given and 'uiautomation' is not installed - "
            "this only works on a real Windows desktop with that package "
            "present, or with a `read` function supplied for testing"
        ) from exc
    top = auto.WindowControl(searchDepth=1, Name=window)
    if not top.Exists(maxSearchSeconds=2):
        return []
    out = []

    def walk(parent, depth: int) -> None:
        if depth <= 0:
            return
        for c in parent.GetChildren():
            out.append({
                "name": c.Name,
                "automation_id": getattr(c, "AutomationId", "") or "",
                "control_type": c.ControlTypeName,
                "enabled": bool(c.IsEnabled),
            })
            walk(c, depth - 1)

    walk(top, _READ_DEPTH)
    return out


def _default_act(step: Step) -> Optional[str]:
    """Returns the read-back text for a "read" step, None for every other
    action - `run()` folds a non-None return into that step's own `value`
    before it is reported as done."""
    try:
        import uiautomation as auto  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "no `act` function was given and 'uiautomation' is not "
            "installed - see _default_read"
        ) from exc
    top = auto.WindowControl(searchDepth=1, Name=step.window)
    # top.Control(...) is the real search API (an instance method that
    # returns a plain Control, not a Name/AutomationId-specific subclass) -
    # verified against the library's own source, since a wrong guess here
    # fails silently on a real Windows machine, not in any test this
    # project can run.
    ctrl = (top.Control(AutomationId=step.automation_id) if step.automation_id
            else top.Control(Name=step.control))
    if step.action == "click":
        ctrl.Click()
    elif step.action == "type":
        # Escaped: SendKeys PARSES its argument, so a `{` in the value would
        # start a key name. See escape_sendkeys - this is the pre-existing path
        # and it had the same hole as type_text's.
        ctrl.SendKeys(escape_sendkeys(step.value or ""))
    elif step.action == "select":
        # A plain Control (what .Control() above returns) has no .Select()
        # method at all - that only exists on specific typed subclasses
        # (e.g. ComboBoxControl), none of which this module ever
        # instantiates. GetPattern(SelectionItemPattern) is the one call
        # that works on any Control - it selects THIS control as the chosen
        # item in its container, which matches how a "select" step already
        # names the specific item to select at plan() time, not a separate
        # dropdown-plus-item-name pair.
        pattern = ctrl.GetPattern(auto.PatternId.SelectionItemPattern)
        if pattern is None:
            raise RuntimeError(f'"{step.control}" does not support being selected')
        pattern.Select()
    elif step.action == "read":
        pattern = ctrl.GetPattern(auto.PatternId.ValuePattern)
        return pattern.Value if pattern is not None else ctrl.Name
    else:
        raise ValueError(f"unknown action {step.action!r}")
    return None


# --------------------------------------------------------------------------
#   One window, not the whole screen - and the ladder that proves a click
#   landed
#
#   WHY THIS IS HERE. `plan()`/`run()` above decide on a window BY TITLE and
#   then act blind: `act` clicks and returns nothing, so a step that clicked a
#   control which did not respond is still reported done. This closes that gap,
#   and the shape is deliberate:
#
#     get_window_state(pid, window_id)   everything below is scoped to ONE
#                                        (process, top-level window). A
#                                        screenshot is clipped to that
#                                        window's own rectangle, never the
#                                        primary display - reading the whole
#                                        screen to answer "what is in this
#                                        window" is how a helper that is
#                                        supposed to be looking at one program
#                                        ends up holding whatever else the
#                                        owner had open.
#
#     deliver(...)                       act through Windows UI Automation
#                                        patterns WITHOUT raising the window,
#                                        taking foreground focus or moving the
#                                        physical mouse (rung 1, the default),
#                                        then READ THE CONTROL BACK and say
#                                        whether the change actually happened.
#                                        Only if the control has no background
#                                        pattern at all does it recommend rung
#                                        2 - which needs its own approval -
#                                        front the window, act, and put the
#                                        previous foreground window back.
#
#   Nothing here guesses which window was meant, and nothing here will touch a
#   window of Jarvis's own: the same reasoning as `is_jarvis_window` below, plus
#   the process-name list, because a model shaped by outside text must not be
#   able to approve a card the owner never saw.
#
#   INJECTABLE, LIKE read/act. Every Windows call (`windows`, `tree`, `screen`,
#   `pattern`, `foreground`) is a parameter with a real default that imports
#   `uiautomation` lazily, exactly as `_default_read`/`_default_act` already do.
#   Tests drive the whole ladder - including every refusal - with fakes and no
#   desktop at all, which is the only way any of it is checked off a PC.
# --------------------------------------------------------------------------

#: What a caller may ask for. "ax" never takes a pixel (the tree only); "som"
#: takes the window's own pixels and numbers the elements so a model can point
#: at a control by number instead of by name; "vision" is the pixels alone.
WINDOW_STATE_MODES = ("ax", "som", "vision")

#: The PATTERN actions - each is one standard UI Automation method, not a mouse
#: gesture. `_default_pattern` below is the only place a real pattern is
#: touched, so a test can replace it and drive the whole ladder with no window.
PATTERN_METHODS = {
    "invoke": "invoke",
    "set_value": "set_value",
    "toggle": "toggle",
    "select": "select",
    "scroll": "scroll",
}

#: A window whose title starts with the word Jarvis is refused by
#: `is_jarvis_window` below. The desktop app's PROCESS is blocked by name as
#: well, so a window of Jarvis's own cannot get in by wearing another title.
JARVIS_PROCESSES = ("jarvis", "jarvis.exe", "jarvis-desktop",
                    "jarvis-desktop.exe", "jarvis-hud", "jarvis-hud.exe")

#: Never delivered, whatever the model asks for. These are not "risky": each is
#: a lock screen, a session teardown, or a way to run arbitrary code, and there
#: is no version of a real request that needs them from here.
BLOCKED_KEY_COMBOS = (
    (r"^(?:win|windows|meta|super)\s*\+\s*l$", "win+l locks the PC"),
    (r"^(?:ctrl|control)\s*\+\s*(?:alt|option)\s*\+\s*del(?:ete)?$",
     "ctrl+alt+del is the secure attention sequence"),
    (r"^alt\s*\+\s*f4$", "alt+f4 closes the focused window, including a shell"),
)

#: Patterns that only make sense as a way to run something arbitrary or destroy
#: something. Each is matched against the WHOLE text a step would type, because
#: these are things that arrive pasted into a shell prompt.
BLOCKED_SHELL_PATTERNS = (
    (r"remove-item\b[^\n]*?-recurse\b[^\n]*?-force\b",
     "Remove-Item -Recurse -Force destroys a folder tree"),
    (r"\bformat\s+[a-z]:", "format wipes a drive"),
    (r"\b(?:curl|wget|iwr|invoke-webrequest)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|k|d)?sh\b",
     "downloading a script and piping it into a shell"),
    (r"\b(?:invoke-expression|iex)\b[^\n]*(?:downloadstring|downloadfile|invoke-webrequest|iwr\b)",
     "an Invoke-Expression download cradle"),
)

#: The one shared refusal sentence, so the two callers cannot drift apart.
SHELL_REFUSAL = ("Jarvis will not send that: {what}. Ask for the thing you "
                 "actually want done instead.")


def blocked_hotkey(combo: str) -> Optional[str]:
    """The refusal text for a key combination that is never sent, or None."""
    text = " ".join(str(combo or "").split()).lower()
    if not text:
        return None
    for pattern, why in BLOCKED_KEY_COMBOS:
        if re.match(pattern, text):
            return SHELL_REFUSAL.format(what=why)
    return None


def blocked_text(text: str) -> Optional[str]:
    """The refusal text for text that is a dangerous shell pattern, or None.

    Only the patterns in BLOCKED_SHELL_PATTERNS: typing ordinary prose, a path,
    or a form field is untouched.
    """
    low = str(text or "").lower()
    if not low:
        return None
    for pattern, why in BLOCKED_SHELL_PATTERNS:
        if re.search(pattern, low):
            return SHELL_REFUSAL.format(what=why)
    return None


#: `uiautomation.SendKeys` does not TYPE its argument - it PARSES it. From the
#: installed library's own docstring (`uiautomation/uiautomation.py:2748-2759`):
#:
#:     SendKeys('{Ctrl}a{Delete}{Ctrl}v{Ctrl}s{Ctrl}{Shift}s{Win}e{PageDown}')
#:         # press Ctrl+a, Delete, Ctrl+v, Ctrl+s, Ctrl+Shift+s, Win+e, PageDown
#:     SendKeys('{{}Hello{}}abc')     # type: '{Hello}abc'
#:
#: So a `{` starts a KEY NAME and `{{}`/`{}}` are the literal braces. Everything
#: else - including `` `~!@#$%^&*()-_=+ `` - is typed as itself, because
#: `charMode=True` (the library's default, which this module uses) is what makes
#: ordinary characters literal. Only the two braces need escaping.
#:
#: `str.translate` and not two `.replace()` calls: `"{".replace("{", "{{}")
#: .replace("}", "{}}")` re-reads its own output and produces `{{{}}}` where a
#: single literal `{` was meant. One pass, and the replacements are never
#: rescanned.
_SENDKEYS_ESCAPES = str.maketrans({"{": "{{}", "}": "{}}"})


def escape_sendkeys(text) -> str:
    """`text` as something `SendKeys` will TYPE rather than interpret.

    WHY THIS EXISTS, and it is a security fix, not tidiness. `type_text` handed
    the model's own words straight to `SendKeys`, so `type_text("{Win}l")` would
    press **Win+L and lock the PC** - exactly what `BLOCKED_KEY_COMBOS` refuses
    on the `hotkey` path. The two paths have to agree, or the blocklist is
    decoration. Escaping at the one place that talks to `SendKeys` means a brace
    can never start a key name, whatever the caller passes.

    It also fixes ordinary typing that was already wrong: a sentence or a path
    containing `{` or `}` was read as a key press, so the text that arrived was
    not the text that was asked for.

    Measured, not assumed: the semantics above are quoted from the installed
    library's docstring, and `test_ui_control.py` pins the escaped forms.
    """
    return str(text or "").translate(_SENDKEYS_ESCAPES)


def _uia_lib():
    """The real `uiautomation` module. `sys.modules` is checked first so a test
    can put a fake in its place, the same trick the existing suite already uses
    to reach `_default_read` without a desktop."""
    mod = sys.modules.get("uiautomation")
    if mod is not None:
        return mod
    try:
        import uiautomation as auto  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "no window listing was given and 'uiautomation' is not installed - "
            "this only works on a real Windows desktop with that package "
            "present, or with `windows`/`tree` supplied for testing"
        ) from exc
    return auto


# --------------------------------------------------------------------------
#   Which top-level windows a process owns
# --------------------------------------------------------------------------

def _default_windows(pid) -> list:
    """Every top-level window owned by `pid`, as plain dicts, ALWAYS a list -
    two windows is the normal case for a real app (the main window and a
    splash, a torn-off panel, a dialog), and that list is what lets the caller
    refuse an ambiguous target instead of picking one. Windows-only, imported
    lazily (see `_uia_lib`)."""
    auto = _uia_lib()
    out: list = []

    def _add(ctrl) -> None:
        try:
            rect = ctrl.BoundingRectangle
            bounds = {"left": int(rect.left), "top": int(rect.top),
                      "width": int(rect.right) - int(rect.left),
                      "height": int(rect.bottom) - int(rect.top)}
        except Exception:
            bounds = {}
        try:
            out.append({"window_id": int(ctrl.NativeWindowHandle), "title": ctrl.Name,
                        "class_name": getattr(ctrl, "ClassName", "") or "",
                        "bounds": bounds, "process": getattr(ctrl, "ProcessId", None)})
        except Exception:
            return

    try:
        root = auto.GetRootControl()
        found = root.Control(ProcessId=int(pid), searchDepth=1)
    except Exception as exc:
        raise RuntimeError(f"could not list windows for pid {pid}: {exc}") from exc
    if found is not None:
        _add(found)
    try:
        # The desktop's own children ARE the top-level windows; a process that
        # owns more than one needs this sweep, because the single lookup above
        # only ever answers with the first.
        for child in root.GetChildren():
            if getattr(child, "ProcessId", None) == int(pid):
                _add(child)
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
#   The tree, flattened, with the password fields masked
# --------------------------------------------------------------------------

#: What a password field - and everything inside one - is called instead of its
#: real name, which is itself the secret in a field like "Current password".
_PASSWORD_MASK = "(a password field)"


def _flatten(controls: list) -> list:
    """The tree in reading order, each control carrying its position.

    Duplicate names are common in a real app ("OK" in two dialogs), so nothing
    here looks a control up BY NAME - the position is the identity, and it is
    what the caller's token names.
    """
    flat: list = []

    def walk(items, level: int, in_password: bool) -> None:
        if not isinstance(items, list):
            return
        for c in items:
            if not isinstance(c, dict):
                continue
            masked = in_password or bool(c.get("password"))
            item = dict(c)
            if masked:
                # The whole subtree, not just the field: a password box can
                # hold a "show password" button, or the revealed text itself.
                item["name"] = _PASSWORD_MASK
                item.pop("value", None)
            item["masked"] = masked
            item["level"] = level
            flat.append(item)
            walk(c.get("children") or [], level + 1, masked)

    walk(controls, 0, False)
    return flat


def _control_summary(controls: list) -> list:
    """What the caller is told about a control: never a password's name or
    value (masked by `_flatten`), and nothing a model cannot use."""
    out = []
    for i, c in enumerate(controls):
        entry = {"index": i, "name": c.get("name", ""),
                 "automation_id": str(c.get("automation_id") or ""),
                 "control_type": c.get("control_type", ""),
                 "enabled": bool(c.get("enabled", True)),
                 "patterns": list(c.get("patterns") or [])}
        if c.get("masked"):
            entry["masked"] = True
        out.append(entry)
    return out


def _is_jarvis_process(process) -> bool:
    return str(process or "").strip().lower() in JARVIS_PROCESSES


def jarvis_target_refusal(descriptor: dict) -> str:
    """Why this window of Jarvis's own is never touched, or "" if it is not
    one. Title first (the desktop app's own windows are titled "Jarvis...") and
    the process name as well, so a renamed window does not get in."""
    title = str((descriptor or {}).get("title") or "")
    if is_jarvis_window(title) or _is_jarvis_process((descriptor or {}).get("process")):
        return own_window_refusal(title or "a Jarvis window")
    return ""


def _som_lines(controls: list) -> list:
    """The numbered element list a model reads a screenshot against: one line
    per control, in the same order as the tokens, so a number in the picture
    and a number here are the same control."""
    lines = []
    for entry in _control_summary(controls):
        off = "" if entry["enabled"] else ", disabled"
        lines.append(f'{entry["index"]}. "{entry["name"]}" '
                     f'[{entry["control_type"] or "control"}{off}]')
    return lines


# --------------------------------------------------------------------------
#   The one entry point that looks at a window
# --------------------------------------------------------------------------

def get_window_state(pid, window_id=None, mode: str = "ax", *, windows=None, tree=None,
                     screen=None, revision: Optional[str] = None) -> dict:
    """Everything Jarvis may know about ONE window of another program.

    Never guesses which window was meant: a process that owns more than one
    top-level window, asked for with no `window_id`, is refused outright with
    the candidates listed rather than having one picked.

    `mode="ax"` reads the accessibility tree and takes NO pixels - that is the
    default, because a tree answers "what can I click" without photographing
    anything. `mode="som"` adds the window's OWN pixels and a numbered element
    list whose numbers are the `element_token`s `deliver` accepts.
    `mode="vision"` is the pixels alone.

    The screenshot is clipped to the window's own rectangle (`_default_screen`),
    never the primary display. Password controls - and everything inside them -
    come back masked: the name replaced, the value dropped.
    """
    if mode not in WINDOW_STATE_MODES:
        return {"ok": False, "code": "bad_mode",
                "reason": f"mode must be one of {', '.join(WINDOW_STATE_MODES)}"}
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return {"ok": False, "code": "bad_pid", "reason": "pid must be a number"}

    lister = windows or _default_windows
    try:
        found = [d for d in list(lister(pid) or []) if isinstance(d, dict)]
    except Exception as exc:
        return {"ok": False, "code": "window_lookup_failed",
                "reason": f"{type(exc).__name__}: {exc}"}
    if window_id is not None:
        wanted = str(window_id)
        found = [d for d in found if str(d.get("window_id")) == wanted]
    if not found:
        return {"ok": False, "code": "window_not_found",
                "reason": "that process owns no window with that id"}
    if len(found) > 1:
        # The owner's real window, a splash screen, a torn-off panel - there is
        # no way to tell from here which one was meant, and acting on the wrong
        # one is a real action in a real program. So: refuse, and list them.
        return {"ok": False, "code": "ambiguous_window_target",
                "reason": (f"process {pid} owns {len(found)} top-level windows and "
                           "none was named - say which one"),
                "candidates": [{"window_id": d.get("window_id"), "title": d.get("title"),
                                "class_name": d.get("class_name")} for d in found]}
    target = found[0]
    refusal = jarvis_target_refusal(target)
    if refusal:
        return {"ok": False, "code": "own_window", "reason": refusal}

    reader = tree or _default_tree
    try:
        raw = reader(pid, target.get("window_id")) or {}
    except Exception as exc:
        return {"ok": False, "code": "tree_read_failed",
                "reason": f"{type(exc).__name__}: {exc}"}
    controls = _flatten(raw.get("controls") or [])
    rev = str(revision if revision is not None else raw.get("revision") or _tree_revision())
    # This read is a new generation, and every token minted from an earlier one
    # stops working here - that is the whole stale-token rule, stated as a fact
    # about this window rather than inferred from the tree's revision number.
    gen = _next_generation(target.get("window_id"))
    out = {"ok": True, "pid": pid, "window_id": target.get("window_id"),
           "title": target.get("title", ""), "mode": mode, "state_revision": rev,
           "generation": gen,
           "password_controls_masked": sum(1 for c in controls if c.get("masked"))}
    if mode == "vision":
        # No tree at all: the caller asked for pixels and gets pixels. That is
        # the point of the mode - it is the fallback for a program whose
        # accessibility tree is empty.
        out["elements"] = []
    else:
        out["elements"] = [{**e, "element_token": f"g{gen}:{rev}:{e['index']}"}
                           for e in _control_summary(controls)]
    if mode == "ax":
        out["image"] = None
        out["note"] = "accessibility tree only - no pixels were read"
        _set_revision(rev)
        return out
    shot = screen or _default_screen
    try:
        image = shot(pid, target.get("window_id"), target.get("bounds") or {})
    except Exception as exc:
        return {"ok": False, "code": "screen_capture_failed",
                "reason": f"{type(exc).__name__}: {exc}"}
    out["image"] = image
    if mode == "som":
        out["element_lines"] = _som_lines(controls)
    _set_revision(rev)
    return out


# --------------------------------------------------------------------------
#   Reading the tree of one window, and photographing exactly that window
# --------------------------------------------------------------------------

#: Which capture the tokens below belong to. A token minted against one read is
#: refused against the next, so a stale number cannot be replayed onto whatever
#: element has since taken that slot.
_REV_COUNTER = 0
_REV = {"current": "r0"}


def _next_tree_revision() -> str:
    global _REV_COUNTER
    _REV_COUNTER += 1
    return f"r{_REV_COUNTER}"


def _set_revision(rev: str) -> None:
    _REV["current"] = str(rev)


def revision() -> str:
    """The revision of the most recent capture in this process. A token is only
    good for the read it was minted against."""
    return _REV["current"]


#: How many times each window has been read, keyed by window id. Every token
#: carries the number of the read it came from (`g<generation>:<revision>:<index>`),
#: and a token from an older read is stale - whatever the tree reports now.
_GEN: dict = {}


def _generation(window_id) -> int:
    return int(_GEN.get(str(window_id), 0))


def _next_generation(window_id) -> int:
    _GEN[str(window_id)] = _generation(window_id) + 1
    return _GEN[str(window_id)]


def mark_reread(window_id) -> int:
    """Say "this window was looked at again, without a token" - a screenshot, a
    log line, anything - so tokens minted before it are refused. Returns the new
    generation."""
    return _next_generation(window_id)


def _control_fields(ctrl) -> dict:
    """One UIA control as a plain dict. A password control's VALUE is never read
    here - not masked afterwards, not read at all."""
    is_password = False
    try:
        is_password = bool(ctrl.IsPassword)
    except Exception:
        is_password = False
    fields = {"name": "", "automation_id": "", "control_type": "", "enabled": True,
              "password": is_password, "patterns": [], "children": []}
    if is_password:
        return fields
    try:
        fields["name"] = ctrl.Name or ""
    except Exception:
        pass
    try:
        fields["automation_id"] = getattr(ctrl, "AutomationId", "") or ""
    except Exception:
        pass
    try:
        fields["control_type"] = ctrl.ControlTypeName or ""
    except Exception:
        pass
    try:
        fields["enabled"] = bool(ctrl.IsEnabled)
    except Exception:
        pass
    return fields


def _default_tree(pid, window_id) -> dict:
    """The real accessibility-tree read of ONE window, addressed by its native
    handle - not by name, which two windows can share. Windows-only, imported
    lazily (see `_uia_lib`)."""
    auto = _uia_lib()
    handle = int(window_id)
    try:
        matches = [w for w in _default_windows(pid)
                   if int(w.get("window_id") or 0) == handle]
    except Exception as exc:
        raise RuntimeError(f"could not find window {window_id} of pid {pid}: {exc}") from exc
    if not matches:
        raise RuntimeError(f"pid {pid} has no window {window_id}")
    top = auto.ControlFromHandle(handle)
    if top is None or not top.Exists(maxSearchSeconds=2):
        raise RuntimeError(f"window {window_id} is gone")
    rev = _next_tree_revision()

    def walk(parent, depth: int) -> list:
        if depth <= 0:
            return []
        out = []
        for c in parent.GetChildren():
            fields = _control_fields(c)
            fields["children"] = walk(c, depth - 1)
            out.append(fields)
        return out

    return {"revision": rev, "controls": walk(top, _READ_DEPTH)}


def _default_screen(pid, window_id, bounds):  # pragma: no cover - needs a desktop
    """A picture of the TARGET WINDOW ONLY, as PNG bytes.

    Both Windows calls are scoped to the window's own rectangle: `PrintWindow`
    asks the window to draw itself (which works when it is covered or behind
    another window, and takes nothing the owner did not ask about), and the
    device-context copy reads that. Nothing here ever captures the primary
    display.
    """
    import ctypes  # Windows-only, imported when actually used
    from ctypes import wintypes
    import io

    from PIL import Image  # type: ignore

    rect = bounds or {}
    width, height = int(rect.get("width") or 0), int(rect.get("height") or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError("the window reported no size, so nothing was captured")

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = wintypes.HWND(int(window_id))
    window_dc = user32.GetWindowDC(hwnd)
    if not window_dc:
        raise RuntimeError("Windows would not give a device context for that window")
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, mem_dc, 2):  # 2 = PW_RENDERFULLCONTENT
            gdi32.BitBlt(mem_dc, 0, 0, width, height, window_dc, 0, 0, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth, header.biHeight = width, -height  # top-down rows
        header.biPlanes, header.biBitCount = 1, 32
        buf = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(header), 0)
        image = Image.frombuffer("RGBA", (width, height), buf.raw, "raw", "BGRA", 0, 1)
        out = io.BytesIO()
        image.convert("RGB").save(out, format="PNG")
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, window_dc)
    return out.getvalue()


# --------------------------------------------------------------------------
#   The one place a real UIA pattern is called
# --------------------------------------------------------------------------

class BackgroundUnavailable(RuntimeError):
    """The control has no pattern that can do this without taking the screen."""


def _default_pattern(request: dict):  # pragma: no cover - needs a desktop
    """Call one standard UI Automation pattern method on the control named by
    `request`.

    This is the ONLY function in the module that turns an action into a real
    interaction, and it is the seam the tests replace. It never clicks: no
    `InvokePattern.Invoke()` fallback to a mouse, no `SendKeys`, no
    `SetForegroundWindow`. A control that cannot be driven from the background
    raises `BackgroundUnavailable`, and the ladder decides what to do about it.

    The pattern objects come from `GetPattern`, the same call `_default_act`
    above already uses for a "read" step's `ValuePattern`.
    """
    auto = _uia_lib()
    ctrl = auto.ControlFromHandle(int(request["window_id"])).Control(
        AutomationId=request["uid"])
    if ctrl is None or not ctrl.Exists(maxSearchSeconds=2):
        raise BackgroundUnavailable(f'"{request["name"]}" is no longer in that window')

    def named(pattern: str, method: str) -> str:
        obj = ctrl.GetPattern(getattr(auto.PatternId, pattern))
        if obj is None:
            raise BackgroundUnavailable(f'"{request["name"]}" has no {pattern}')
        getattr(obj, method)()
        return "ok"

    if request["action"] == "invoke":
        return named("InvokePattern", "Invoke")
    if request["action"] == "set_value":
        obj = ctrl.GetPattern(auto.PatternId.ValuePattern)
        if obj is None:
            raise BackgroundUnavailable(f'"{request["name"]}" has no ValuePattern')
        obj.SetValue(str(request["value"] or ""))
        return "ok"
    if request["action"] == "toggle":
        return named("TogglePattern", "Toggle")
    if request["action"] == "select":
        return named("SelectionItemPattern", "Select")
    if request["action"] == "scroll":
        obj = ctrl.GetPattern(auto.PatternId.ScrollPattern)
        if obj is None:
            raise BackgroundUnavailable(f'"{request["name"]}" cannot be scrolled')
        obj.Scroll(auto.ScrollAmount.NoAmount, auto.ScrollAmount.LargeIncrement)
        return "ok"
    raise BackgroundUnavailable(f"no background pattern does {request['action']!r}")


def _default_foreground(window_id, *, restore=None):  # pragma: no cover - needs a desktop
    """Rung 2's only Windows call: front one window and hand back the handle
    that was in front, so the caller can put the owner back where they were.
    `restore=<handle>` puts that handle back instead."""
    import ctypes

    user32 = ctypes.windll.user32
    if restore is not None:
        user32.SetForegroundWindow(ctypes.c_void_p(int(restore)))
        return int(restore)
    previous = int(user32.GetForegroundWindow() or 0)
    user32.SetForegroundWindow(ctypes.c_void_p(int(window_id)))
    return previous


# --------------------------------------------------------------------------
#   Rung 1, then - only when it is genuinely unavailable - rung 2
# --------------------------------------------------------------------------

def _control_at(tree: dict, token: str, expect_revision: Optional[str] = None):
    """(the control a token names, None), or (None, the refusal).

    Two ways a token is stale and both are refused, never quietly repaired: it
    belongs to an earlier read of the window, or the element that has since
    taken that slot is not the one it named (the tree simply has nothing at that
    position). Every refusal here carries `ok: False`, like every other refusal
    a caller can get back.
    """
    generation, rev, index, refusal = _parse_token(token)
    if refusal:
        return None, refusal
    if expect_revision is not None and rev != str(expect_revision):
        return None, {"ok": False, "code": "stale_element_token",
                      "reason": (f"that token was taken from {rev} of this window; "
                                 f"the last read was {expect_revision}")}
    controls = _flatten(tree.get("controls") or [])
    if index >= len(controls):
        return None, {"ok": False, "code": "stale_element_token",
                      "reason": "nothing is at that position any more"}
    return controls[index], None


def _parse_token(token: str):
    """(generation, revision, index, refusal) for an element token.

    A token is `g<generation>:<revision>:<index>` - the generation is which read
    of that window it came from, which is what makes "stale" a fact. The
    two-part `<revision>:<index>` an earlier shape used is still read, because
    refusing every token a caller already holds would be a worse failure than
    the check it buys.
    """
    parts = str(token or "").split(":")
    if len(parts) == 2 and parts[1].isdigit():
        return None, parts[0], int(parts[1]), None
    if len(parts) == 3 and parts[0].startswith("g") and parts[0][1:].isdigit() \
            and parts[2].isdigit():
        return int(parts[0][1:]), parts[1], int(parts[2]), None
    return None, None, None, {
        "ok": False, "code": "bad_element_token",
        "reason": 'an element token looks like "<state_revision>:<index>"'}


def _control_state(tree: dict, index: int) -> Optional[dict]:
    controls = _flatten(tree.get("controls") or [])
    if index >= len(controls):
        return None
    c = controls[index]
    return {"uid": str(c.get("automation_id") or c.get("name") or ""),
            "name": c.get("name", ""), "enabled": bool(c.get("enabled", True)),
            "value": c.get("value")}


def _changed(before: Optional[dict], after: Optional[dict], action: str) -> bool:
    """Did the read-back show the change? Toggle and set_value have a state to
    compare; everything else confirms itself by the control still being there
    and still usable, which is all a click ever leaves behind."""
    if before is None or after is None:
        return False
    if action == "set_value":
        # Setting a value to what it already said is not a failed action, but
        # it is not evidence either - so it is reported unverifiable below, not
        # confirmed.
        return before.get("value") != after.get("value")
    return bool(after.get("enabled")) and after.get("uid") == before.get("uid")


def _background_delivered(tree: dict, control: dict, index: int, action: str, value, *,
                          pattern, window_id, verify: bool):
    """Rung 1, and the read-back that decides which of the three answers it is."""
    patterns = list(control.get("patterns") or [])
    if patterns and action not in patterns:
        return {"path": "uia_background", "verified": False, "effect": "suspected_noop",
                "escalation": {"recommended": "foreground",
                               "code": "background_unavailable",
                               "reason": f'"{control.get("name")}" has no background '
                                         f'pattern for {action}'}}, control
    before = _control_state(tree, index) if verify else None
    request = {"uid": (before or {}).get("uid") or str(control.get("automation_id") or ""),
               "name": control.get("name", ""), "action": action, "value": value,
               "window_id": window_id, "index": index}
    try:
        effect = pattern(request)
    except BackgroundUnavailable as exc:
        return {"path": "uia_background", "verified": False, "effect": "suspected_noop",
                "escalation": {"recommended": "foreground",
                               "code": "background_unavailable",
                               "reason": str(exc)}}, control
    if not isinstance(effect, dict) or str(effect.get("effect", "")) != "ok":
        return {"path": "uia_background", "verified": False, "effect": "suspected_noop",
                "escalation": {"recommended": "foreground",
                               "code": "background_unavailable",
                               "reason": "the pattern run reported no change"}}, control
    if not verify:
        return {"path": "uia_background", "verified": False,
                "effect": "unverifiable"}, control
    after = _control_state(tree, index)
    if _changed(before, after, action):
        return {"path": "uia_background", "verified": True,
                "effect": "confirmed"}, control
    return {"path": "uia_background", "verified": False, "effect": "suspected_noop",
            "escalation": {"recommended": "foreground", "code": "background_delivery_noop",
                           "reason": "the control was driven but did not change"}}, control


def _foreground_delivered(window_id, action, value, *, pattern, foreground):
    """Rung 2. Reached only with the owner's approval for THIS delivery, because
    it takes the screen for a moment. The previous foreground window is handed
    back so the caller can restore it, and a failure does not skip the
    restore."""
    saved = foreground(window_id)
    try:
        effect = pattern({"window_id": window_id, "uid": "", "name": "", "index": None,
                          "action": action, "value": value, "foreground": True})
        ok = isinstance(effect, dict) and str(effect.get("effect", "")) == "ok"
    except Exception as exc:
        return ({"path": "foreground_delivery", "ok": False, "code": "foreground_failed",
                 "reason": f"{type(exc).__name__}: {exc}", "restored": bool(saved)}, saved)
    return ({"path": "foreground_delivery", "ok": ok, "verified": False,
             "effect": "delivered_foreground" if ok else "suspected_noop",
             "restored": bool(saved)}, saved)


def deliver(element_token: str, action: str, *, window_id=None, value=None,
            delivery_mode: str = "background", foreground_approved: bool = False,
            expect_revision: Optional[str] = None, verify: bool = True,
            tree=None, pattern=None, foreground=None) -> dict:
    """Do ONE thing to ONE control, and say honestly what happened.

    `action` is a PATTERN action, not a mouse gesture: `invoke`, `set_value`,
    `toggle`, `select`, `scroll`. Rung 1 (the default, `delivery_mode=
    "background"`) never raises the window, never takes foreground focus and
    never moves the owner's mouse - so it cannot disturb what they are doing. It
    reads the control back afterwards and answers exactly one of:

        {"path": "uia_background", "verified": True,  "effect": "confirmed"}
        {"path": "uia_background", "verified": False, "effect": "unverifiable"}
        {"path": "uia_background", "verified": False, "effect": "suspected_noop",
         "escalation": {"recommended": "foreground", "reason": ...}}

    Rung 2 is asked for, never taken: `delivery_mode="foreground"` is refused
    unless `foreground_approved=True` is also passed, and that flag is the
    owner's answer for this delivery, not a standing permission. It fronts the
    target window, acts, and puts the previous foreground window back.

    A token that no longer matches the window (`stale_element_token`) is refused
    rather than re-resolved - the same reasoning as run()'s re-verification.
    """
    if not str(element_token or "").strip():
        return {"ok": False, "code": "bad_element_token",
                "reason": "an element token is required - take one from get_window_state"}
    if action not in PATTERN_METHODS:
        return {"ok": False, "code": "unknown_action",
                "reason": f"action must be one of {', '.join(sorted(PATTERN_METHODS))}"}
    if delivery_mode not in ("background", "foreground"):
        return {"ok": False, "code": "bad_delivery_mode",
                "reason": 'delivery_mode is "background" (default) or "foreground"'}
    if window_id is None:
        # Without the window there is no way to look at the token at all - and
        # guessing one is exactly what get_window_state refuses to do.
        return {"ok": False, "code": "bad_window_target",
                "reason": "deliver needs the window_id the token came from"}

    getter = tree or _default_tree
    actor = pattern or _default_pattern
    front = foreground or _default_foreground
    try:
        live = getter(None, window_id) or {}
    except Exception as exc:
        return {"ok": False, "code": "tree_read_failed",
                "reason": f"{type(exc).__name__}: {exc}"}
    # Which read of this window the token claims to come from. A token minted
    # before the last look at this window is stale - a fact about this window,
    # not an inference from two revision numbers happening to differ or match.
    generation, token_rev, token_index, bad = _parse_token(element_token)
    if bad is None and generation is not None:
        current, current_rev = _generation(window_id), live.get("revision")
        if generation < current:
            return {"ok": False, "code": "stale_element_token",
                    "reason": (f"that token was taken from {token_rev} of this window; "
                               f"the last read was {current_rev} (read {current} of "
                               f"this window), so the control is no longer identified "
                               "- take a fresh token")}
    control, refusal = _control_at(
        live, element_token, expect_revision if expect_revision is not None else token_rev)
    if refusal:
        return refusal
    index = int(token_index)

    if delivery_mode == "background":
        result, _ = _background_delivered(live, control, index, action, value,
                                          pattern=actor, window_id=window_id, verify=verify)
        if not (result.get("effect") == "suspected_noop"
                and (result.get("escalation") or {}).get("recommended") == "foreground"):
            return result
        if not foreground_approved:
            # The refusal that matters: a background action that did nothing
            # does NOT quietly become a focus-stealing one.
            return {**result, "ok": False, "code": "foreground_not_approved",
                    "reason": ("that control cannot be driven in the background, and "
                               "taking the screen forward was not approved")}
    elif not foreground_approved:
        # Rung 2 is not a mode setting: it is a decision, and the decision has
        # to be on THIS call. A window that steals focus nobody approved is the
        # whole reason the ladder exists.
        return {"ok": False, "path": "uia_background", "verified": False,
                "effect": "suspected_noop", "code": "foreground_not_approved",
                "escalation": {"recommended": "foreground",
                               "code": "foreground_not_approved",
                               "reason": "foreground delivery needs the owner's approval"},
                "reason": ("foreground delivery needs the owner's approval for this "
                           "action - nothing was fronted and nothing was sent")}
    result, saved = _foreground_delivered(window_id, action, value,
                                         pattern=actor, foreground=front)
    try:
        if saved:
            front(None, restore=saved)
    except Exception as exc:
        result["restore_failed"] = f"{type(exc).__name__}: {exc}"
    return result


# --------------------------------------------------------------------------
#   Text and key combinations - the two things that never go to a shell
# --------------------------------------------------------------------------

def type_text(text, *, sender=None, window_id=None) -> dict:
    """Type `text` into the focused control of the target window - unless the
    text is one of the shell patterns that only exist to run something
    arbitrary or destroy something, which is refused before anything is sent.

    Ordinary typing is untouched: a sentence, a path, a search box. The check
    is deliberately narrow (see BLOCKED_SHELL_PATTERNS) because a guard that
    refuses real work gets worked around, and then there is no guard.
    """
    refusal = blocked_text(text)
    if refusal:
        return {"ok": False, "code": "blocked_shell_pattern", "reason": refusal}
    send = sender or _default_keys
    try:
        send("text", str(text or ""), window_id)
    except Exception as exc:
        return {"ok": False, "code": "send_failed",
                "reason": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "sent": "text"}


def hotkey(combo, *, sender=None, window_id=None) -> dict:
    """Send one key combination - unless it is a lock, a session teardown, or
    "close the focused window", each of which is refused before anything is
    sent (see BLOCKED_KEY_COMBOS)."""
    refusal = blocked_hotkey(combo)
    if refusal:
        return {"ok": False, "code": "blocked_hotkey", "reason": refusal}
    send = sender or _default_keys
    try:
        send("hotkey", str(combo or ""), window_id)
    except Exception as exc:
        return {"ok": False, "code": "send_failed",
                "reason": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "sent": "hotkey"}


def _default_keys(kind: str, payload: str, window_id=None):  # pragma: no cover - desktop
    """The real sender, reached only after the guards above. `SendKeys` goes to
    the focused control, so there is nothing here that moves the mouse."""
    auto = _uia_lib()
    target = (auto.ControlFromHandle(int(window_id)) if window_id is not None
              else auto.GetFocusedControl())
    if kind == "text":
        # Escaped - the argument is PARSED by SendKeys, so raw text containing
        # `{` would send a key press instead of typing the character. See
        # escape_sendkeys.
        target.SendKeys(escape_sendkeys(payload))
    else:
        target.SendKeys("{" + "}{".join(str(payload).split("+")) + "}")
    return "ok"


# --------------------------------------------------------------------------
#   Never Jarvis's own windows (security audit M3, GUARDS S4, 2026-09-25)
#
#   A plan shaped by outside text could otherwise say: click "Approve" in
#   "Jarvis Desktop Widget". One card would then approve ANOTHER card, whose
#   details the owner never saw - an approve-all by the back door. So no
#   window of Jarvis's own is ever planned against, or run against.
#
#   The titles are the desktop app's own, read from jarvis-desktop:
#   tauri.conf.json ("Jarvis" - the quickbar - and "Jarvis Desktop Widget"),
#   src-tauri/src/windows.rs (Settings, Brain, Faces, Welcome) and lib.rs
#   (the HUD window, also "Jarvis"), plus each page's own <title>, in case
#   Windows shows that instead ("Jarvis HUD", "Jarvis Widget", "Jarvis
#   Faces"). Any title that STARTS with the word Jarvis is refused as well,
#   so a renamed window, or the HUD page open in a browser tab ("Jarvis HUD -
#   Microsoft Edge"), is covered too. The cost - a window of some other
#   program whose title starts with "Jarvis" cannot be driven - is accepted.
# --------------------------------------------------------------------------

JARVIS_WINDOWS = (
    "Jarvis", "Jarvis Desktop Widget", "Jarvis Desktop \u2014 Settings",
    "Jarvis \u2014 Brain", "Jarvis \u2014 Faces", "Jarvis \u2014 Welcome",
    "Jarvis HUD", "Jarvis Widget", "Jarvis Faces",
)


def is_jarvis_window(window: str) -> bool:
    """True for a window that belongs to Jarvis itself (see above)."""
    title = " ".join(str(window or "").split())
    if title in JARVIS_WINDOWS:
        return True
    return re.match(r"jarvis(?![\w'])", title, re.I) is not None


def own_window_refusal(window: str) -> str:
    return (f"Jarvis does not click or type in its own windows (\"{window}\"): a "
            f"click there could approve a card you never saw. If something in "
            f"Jarvis needs doing, do it yourself.")


#: The words a live status line may use for a step (see run()).
_STEP_WORD = {"click": "a click", "type": "typing", "select": "a selection",
              "read": "reading a value"}


def _find(tree: list, name: str) -> Optional[dict]:
    for c in tree:
        if c.get("name") == name:
            return c
    return None


def plan(goal: str, window: str, requests: list,
         *, read: Optional[Callable[[str], list]] = None) -> Plan:
    """Work out the concrete steps. Reads the screen; sends no input.

    `requests` is a list of dicts, each naming what the caller wants to
    happen, in the owner's or Jarvis's own words - not yet bound to anything
    real:

        {"control": "Send", "action": "click", "why": "..."}
        {"control": "Subject", "action": "type", "value": "...", "why": "...",
         "irreversible": False, "leaves_machine": False}

    Every request is checked against the CURRENT tree right now. A control
    that is not there yet - or not there any more - is not guessed at; it is
    reported in `unmatched` and simply does not become a step.
    """
    if is_jarvis_window(window):
        # Before the tree is even read: nothing about the window is needed.
        raise ValueError(own_window_refusal(window))
    getter = read or _default_read
    tree = getter(window) or []
    steps, unmatched = [], []
    for r in requests:
        name = str(r.get("control", "")).strip()
        action = str(r.get("action", "")).strip()
        found = _find(tree, name)
        if not found or not found.get("enabled", True):
            unmatched.append({**r, "reason": "not found" if not found
                               else "found but disabled"})
            continue
        steps.append(Step(
            window=window, control=name,
            automation_id=str(found.get("automation_id") or ""),
            action=action, value=r.get("value"),
            why=str(r.get("why", "")),
            heavy=bool(r.get(IRREVERSIBLE_HINT)) or bool(r.get(LEAVES_MACHINE_HINT)),
        ))
    return Plan(
        goal=str(goal), window=str(window), steps=steps, unmatched=unmatched,
        if_refused="nothing in this window changes; the goal is not attempted")


# The weight the CARD prints is the heavier of two: the steps the model
# flagged, and the gate's own risk table - which classifies this whole
# action as one that cannot be undone and leaves the machine (by its worst
# case: driving the desktop can click send). The card used to print only the
# model's flags, so a plan whose Send click the model left unflagged read
# "weight: normal" while the notice and the risk line said the opposite.
# `Plan.weight` stays the model's own marking; this is what a person is
# shown.
CARD_WEIGHT_LINE = (
    "weight: heavy - any click can send something or be impossible to undo, "
    "so the whole plan is treated that way. The steps marked below are the "
    "ones Jarvis flagged itself; an unmarked step is not a promise that it "
    "is safe.")


def describe(p: Plan) -> str:
    """The card text. Every step in full, in the order it would run."""
    lines = [f"Jarvis would like to do this in the window \"{p.window}\": {p.goal}",
             "",
             f"{len(p.steps)} step(s), {CARD_WEIGHT_LINE}",
             ""]
    if not p.steps:
        lines.append("No requested control could be matched, so nothing "
                      "would happen.")
    for i, s in enumerate(p.steps, 1):
        target = s.control + (f" (id: {s.automation_id})" if s.automation_id else "")
        detail = f" = {s.value!r}" if s.value is not None else ""
        lines += [f"  {i}. {s.action} \"{target}\"{detail}{'  [Jarvis flagged: irreversible or leaves the machine]' if s.heavy else ''}",
                  f"     why: {s.why}", ""]
    if p.unmatched:
        lines.append(f"{len(p.unmatched)} requested step(s) could NOT be "
                      "matched to anything on screen right now, and will "
                      "NOT run:")
        for u in p.unmatched:
            lines.append(f"  - \"{u.get('control')}\": {u.get('reason')}")
        lines.append("")
    lines.append(f"If you say no: {p.if_refused}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - only the enumerated steps, re-verified just before each one
# --------------------------------------------------------------------------

def run(p: Plan, *, read: Optional[Callable[[str], list]] = None,
        act: Optional[Callable[[Step], None]] = None,
        announce: Optional[Callable[[str], None]] = None,
        checkpoint: Optional[Callable[[], Optional[str]]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan, one step at a time.

    `approved` has no default of True, same reason as jarvis_research.py: a
    module that can act on the world must not be one call away from doing it
    by accident.

    Before EVERY step, the live tree is re-read and the target must still
    exist, still be enabled, and still carry the same automation id (or name,
    if it never had one). If it does not, execution STOPS at that step -
    steps already done are reported as done, the failing step and everything
    after it are reported as not run, and nothing here decides what to do
    about it. That is a new plan() and a new decision.

    `announce(text)`, if given, is called just before each step with a short
    human sentence - this is the hook a caller wires to
    `jarvis_events.set_activity("working", text)` so the owner can see, live,
    that Jarvis is in the middle of doing this. Not wiring it up does not
    disable the safety checks; it only means nobody is told while it runs.

    `checkpoint()`, if given, is read at that same point, before the live
    tree re-read - see docs/AUTONOMY-PROPOSALS.md section 3d, "no new
    architecture, one more read at a point that already exists." A caller
    wires it to `lambda: jarvis_task_control.checkpoint(task_id)`; this
    module has no idea what a task id is and imports nothing to find out,
    the same way it has no idea what `jarvis_events.set_activity` is for
    `announce`. A "stop" ends the run exactly like a failed re-verification
    does. A "pause" ends it the same way but with `paused: True` in the
    result - the steps not yet run stay reported, ready for one explicit
    "continue" decision to become a fresh, approved run() rather than
    resuming on their own.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was done",
                "plan": p.as_dict()}
    if is_jarvis_window(p.window) or any(is_jarvis_window(s.window) for s in p.steps):
        # plan() already refuses these; a Plan built any other way is too.
        return {"ok": False, "reason": own_window_refusal(p.window),
                "done": [], "not_run": [s.as_dict() for s in p.steps]}
    getter = read or _default_read
    actor = act or _default_act
    tell = announce or (lambda _text: None)
    check = checkpoint or (lambda: None)

    done = []
    for i, step in enumerate(p.steps, 1):
        # The checkpoint comes FIRST, before the announcement. It used to
        # come second, and `announce` is wired to
        # `jarvis_events.set_activity("working", text)`, which is sticky -
        # so a pause left the Brain window saying "Step 4/6: click Send"
        # about a step that never ran, and went on saying it.
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
        # The line goes out on the event stream (`announce` is wired to
        # jarvis_events.set_activity), which reaches a phone with the screen
        # off - and ARCHITECTURE.md section 6 says an event carries "never
        # content". So only the step's number and a word from a fixed list;
        # never the control's name or the window's title. Those are on the card the owner approved
        # (security audit L4, 2026-09-25).
        tell(f"Step {i}/{len(p.steps)}: {_STEP_WORD.get(step.action, 'a step')} "
             f"in another program's window")
        tree = getter(step.window) or []
        current = _find(tree, step.control)
        same_control = (
            current is not None
            and current.get("enabled", True)
            and str(current.get("automation_id") or "") == step.automation_id
        )
        if not same_control:
            remaining = p.steps[i - 1:]
            return {"ok": False,
                    "reason": (f"step {i} (\"{step.control}\" in "
                               f"{step.window}) no longer matches what was "
                               "planned - stopping rather than guessing"),
                    "done": [s.as_dict() for s in done],
                    "not_run": [s.as_dict() for s in remaining]}
        try:
            read_back = actor(step)
        except Exception as exc:
            remaining = p.steps[i - 1:]
            return {"ok": False,
                    "reason": f"step {i} failed: {type(exc).__name__}: {exc}",
                    "done": [s.as_dict() for s in done],
                    "not_run": [s.as_dict() for s in remaining]}
        if step.action == "read" and read_back is not None:
            # `value` already means "the text this step carries" for
            # "type" - reusing it for "read"'s result needs no new field on
            # Step, and describe()/as_dict() already render it.
            step.value = read_back
        done.append(step)
    # One last read, so a Stop that arrived while the final step was
    # running is not simply thrown away. The plan really did finish - every
    # step ran, so `ok` stays True and nothing pretends otherwise - but the
    # owner pressed Stop and deserves to be told it was seen and was too
    # late, rather than watching it vanish. This read also SPENDS the
    # signal (see jarvis_task_control.checkpoint), which is what stops a
    # stop that missed its run from stopping the next one instead.
    late = check()
    result = {"ok": True, "done": [s.as_dict() for s in done], "not_run": []}
    if late in ("stop", "pause"):
        result["late_signal"] = late
        result["note"] = (f"a {late} arrived after the last step had already "
                          "run - the plan finished, and nothing was left undone")
        tell(f"Done. (A {late} arrived too late to change anything.)")
    else:
        tell("Done.")
    return result
