"""jarvis_agent.py - the tool-using chat loop, local lane only, straight to Ollama.

WHAT THIS IS FOR
`/api/chat`'s local lane could only ever produce plain text - the model had
no way to check a fact, read a file, or use any of the eight capabilities
built across this project's sessions (jarvis_ui_control.py,
jarvis_android_control.py, jarvis_research.py, jarvis_browser_control.py,
jarvis_calendar.py, jarvis_email.py, jarvis_notes.py, jarvis_home.py).
This module is the missing loop: it hands Ollama a set of tools, and when
the model asks to use one, gates it through jarvis_gate.check() - the exact
same module and the exact same four-step shape (plan/describe/gate/run) as
everything else in this project - before ever running it.

LOCAL ONLY, ON PURPOSE
This is never called for a cloud lane. Every tool here either reads this
machine (files, memory) or acts on it (a shell, this computer's UI, the
paired phone) - rule 1 of this project's own invariants is that anything
private stays on the local model, and a tool result handed to a cloud
provider is exactly the kind of leak that rule exists to prevent. Wiring
this in is the caller's job (see ollama-direct.patch's own docstring
section); this module refuses nothing about being called from elsewhere, but
nothing here decides that on its own either.

WHAT WAS DELIBERATELY LEFT OUT, AND WHY
See backend/README.md's own section on this. Browser automation exists now
(jarvis_browser_control.py, wired below as "browser_control") but SHIPS
DISABLED - it is not in any `[tools].enabled` list this project ships, the
same opt-in-only mechanism control_computer and control_phone already use,
and its own module docstring says exactly why it should stay off until a
second, larger-context lane is running. Docker-based execution, connectors
and general web search remain excluded with the reasons README.md gives; a
memory_store tool that writes directly to `facts` was excluded on purpose
because this project's memory system exists specifically so nothing reaches
`facts` without a human accepting it through the review queue, and a
chat-time tool would reopen that hole.

The four keyless integrations (calendar_read, email_check, notes_search,
home_read, home_control - five tools, four modules, home split in two
because reading and acting are different tiers) SHIP DISABLED for a
different, simpler reason than browser_control: each needs the owner's own
credentials configured in the environment before it can do anything at
all, so turning one on with nothing configured just means a plan that
always explains why it has nothing to read or nowhere to send. See each
module's own docstring (jarvis_calendar.py, jarvis_email.py,
jarvis_notes.py, jarvis_home.py) and backend/README.md's `calendar-wiring`,
`email-wiring`, `notes-wiring`, and `home-control-wiring` sections for the
exact `jarvis_gate`/`jarvis-framework.toml` lines each one needs.

TESTING WITHOUT A REAL BACKEND
Every tool's actual execution and every call to jarvis_gate are behind
try/except ImportError fallbacks and an injectable `open_stream` (the Ollama
HTTP call) - the loop's own control flow (call model, see tool_calls, gate
each one, feed results back, stop when the model stops asking) is provable
with a scripted fake model and a fake gate, same shape as
jarvis_research.py's `fetch` injection. The fake model speaks Ollama's real
stream format (_ollama_wire.py), and test_chat_stream_contract.py puts what
this module writes through all three apps' readers.

EVERY LOCAL TURN COMES THROUGH HERE (chat-stream.patch), not only one with
tools on: with no tool enabled it is one streamed request, relayed with
thinking cut out, the history fitted to the model's real context, and
keepalives so a phone does not give up. See run_local_turn.
"""

from __future__ import annotations

import ast
import http.client
import json
import operator
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional


# --------------------------------------------------------------------------
#   Tools - each one's ACTION NAME matches an entry jarvis_gate.py already
#   knows a tier for. Adding a tool here never requires a gate change unless
#   the action genuinely does not exist yet.
# --------------------------------------------------------------------------

_ARITH_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


# calculator is tier `auto` - no human ever sees a card for it, so nothing
# in the permission model stands between a wild exponent and this process's
# own CPU/memory. `9**9**9**9**9` is a valid AST with no name and no call,
# so "no names, no calls" alone does not make this tool safe - Python's
# integers have no size limit of their own, and right-associative Pow
# reaches an exponent in the hundreds of millions by its second step.
_MAX_POW_EXPONENT = 1_000
_MAX_POW_BASE = 10 ** 6


def _safe_eval(node):
    """Arithmetic only. No names, no calls, no attribute access - the model
    cannot smuggle a call to anything through the calculator, because there
    is nothing here that resolves a name to a function at all."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ARITH_OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and (
                abs(right) > _MAX_POW_EXPONENT or abs(left) > _MAX_POW_BASE):
            raise ValueError(
                f"{left}**{right} is too large for this calculator "
                f"(exponent over {_MAX_POW_EXPONENT} or base over {_MAX_POW_BASE})")
        return _ARITH_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ARITH_OPS:
        return _ARITH_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"not a plain arithmetic expression (got {type(node).__name__})")


def _run_calculator(args: dict) -> dict:
    expr = str(args.get("expression", ""))
    try:
        value = _safe_eval(ast.parse(expr, mode="eval").body)
    except Exception as exc:
        return {"ok": False, "error": f"could not evaluate {expr!r}: {exc}"}
    return {"ok": True, "value": value}


def _run_memory_search(args: dict) -> dict:
    try:
        import jarvis_memory
    except Exception as exc:
        return {"ok": False, "error": f"memory is not available here: {exc}"}
    query = str(args.get("query", ""))
    k = max(1, min(20, int(args.get("k", 5) or 5)))
    hits = jarvis_memory.store().search(query, k=k)
    return {"ok": True, "facts": [{"id": h.get("id"), "text": h.get("text")} for h in hits]}


_MAX_FILE_READ_BYTES = 200_000

# Windows reserves these names (with or without an extension, in any
# directory) as legacy device files, not ordinary files - CON in particular
# opens as the console, and *reading* it blocks waiting for a keypress that
# will never come on a headless service. No sandbox is implied by this list
# (this tool is a whole-filesystem read, tier-gated like shell_exec is, not
# confined to a project folder) - it only stops a path from resolving to a
# device instead of a file at all.
_RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)})


def _is_reserved_windows_name(path: str) -> bool:
    import ntpath
    for part in ntpath.normpath(path).split(ntpath.sep):
        stem = part.rsplit(".", 1)[0]
        if stem.upper() in _RESERVED_WINDOWS_NAMES:
            return True
    return False


def _run_file_read(args: dict) -> dict:
    path = str(args.get("path", ""))
    if _is_reserved_windows_name(path):
        return {"ok": False, "error": f"{path!r} names a reserved device, not a file"}
    try:
        # Binary, capped by actual bytes read, then decoded - not text mode
        # capped by .read(N), which caps CHARACTERS. A file that is mostly
        # multi-byte UTF-8 (CJK, emoji) could otherwise return up to ~4x
        # _MAX_FILE_READ_BYTES despite the name and the cap both claiming
        # bytes. A cut mid-character at the boundary decodes as U+FFFD via
        # errors="replace", which is fine for a preview truncation point.
        with open(path, "rb") as f:
            raw = f.read(_MAX_FILE_READ_BYTES + 1)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    truncated = len(raw) > _MAX_FILE_READ_BYTES
    content = raw[:_MAX_FILE_READ_BYTES].decode("utf-8", errors="replace")
    return {"ok": True, "content": content, "truncated": truncated}


def _run_shell_exec(args: dict) -> dict:
    import subprocess
    command = str(args.get("command", ""))
    if not command.strip():
        return {"ok": False, "error": "empty command"}
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=max(1.0, min(120.0, float(args.get("timeout_seconds", 30) or 30))))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": result.returncode == 0, "returncode": result.returncode,
            "stdout": result.stdout[-8000:], "stderr": result.stderr[-4000:]}


def _run_shell_exec_tool(args: dict, state, **_) -> dict:
    return _run_shell_exec(args)


def _prepare_control_computer(args: dict):
    try:
        import jarvis_ui_control as U
    except Exception as exc:
        return None, f"Control the computer: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = U.plan(str(args.get("goal", "")), str(args.get("window", "")),
               args.get("requests") or [])
    return p, U.describe(p)


def _run_control_computer(args: dict, plan_obj, *, announce=None, checkpoint=None) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "UI control is not available here"}
    import jarvis_ui_control as U
    return U.run(plan_obj, announce=announce, checkpoint=checkpoint,
                 approved=True)


def _prepare_control_phone(args: dict):
    try:
        import jarvis_android_control as A
    except Exception as exc:
        return None, f"Control the phone: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = A.plan(str(args.get("device", "")), str(args.get("goal", "")),
               args.get("requests") or [])
    return p, A.describe(p)


def _run_control_phone(args: dict, plan_obj, *, announce=None, checkpoint=None) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "phone control is not available here"}
    import jarvis_android_control as A
    return A.run(plan_obj, announce=announce, checkpoint=checkpoint,
                 approved=True)


def _prepare_browser_control(args: dict):
    try:
        import jarvis_browser_control as B
    except Exception as exc:
        return None, f"Control a browser tab: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = B.plan(str(args.get("goal", "")), str(args.get("session", "")),
               args.get("requests") or [], allowed_domains=args.get("allowed_domains"))
    return p, B.describe(p)


def _run_browser_control(args: dict, plan_obj, *, announce=None, checkpoint=None) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "browser control is not available here"}
    import jarvis_browser_control as B
    return B.run(plan_obj, announce=announce, checkpoint=checkpoint,
                 approved=True)


def _prepare_github_search(args: dict):
    try:
        import jarvis_research as R
    except Exception as exc:
        return None, f"Search GitHub about: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = R.plan(str(args.get("idea", "")), args.get("capabilities") or [])
    return p, R.describe(p)


def _run_github_search(args: dict, plan_obj, **_) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "research is not available here"}
    import jarvis_research as R
    out = R.run(plan_obj, approved=True)
    if not out.get("ok"):
        return out
    return R.matrix(out)


def _prepare_calendar_read(args: dict):
    try:
        import jarvis_calendar as CAL
    except Exception as exc:
        return None, f"Read the calendar: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = CAL.plan(int(args.get("days_ahead", 7) or 7))
    return p, CAL.describe(p)


def _run_calendar_read(args: dict, plan_obj, **_) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "the calendar is not available here"}
    import jarvis_calendar as CAL
    return CAL.run(plan_obj, approved=True)


def _prepare_email_check(args: dict):
    try:
        import jarvis_email as MAIL
    except Exception as exc:
        return None, f"Check email: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = MAIL.plan(int(args.get("limit", 10) or 10),
                   unread_only=bool(args.get("unread_only", True)))
    return p, MAIL.describe(p)


def _run_email_check(args: dict, plan_obj, **_) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "email is not available here"}
    import jarvis_email as MAIL
    return MAIL.run(plan_obj, approved=True)


def _prepare_notes_search(args: dict):
    try:
        import jarvis_notes as NOTES
    except Exception as exc:
        return None, f"Search notes: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = NOTES.plan(str(args.get("query", "")), int(args.get("limit", 10) or 10))
    return p, NOTES.describe(p)


def _run_notes_search(args: dict, plan_obj, **_) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "notes search is not available here"}
    import jarvis_notes as NOTES
    return NOTES.run(plan_obj, approved=True)


def _prepare_home_read(args: dict):
    try:
        import jarvis_home as HOME
    except Exception as exc:
        return None, f"Read Home Assistant state: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = HOME.plan_states(args.get("entity_ids") or [])
    return p, HOME.describe(p)


def _run_home_read(args: dict, plan_obj, **_) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "Home Assistant is not available here"}
    import jarvis_home as HOME
    return HOME.run(plan_obj, approved=True)


def _prepare_home_control(args: dict):
    try:
        import jarvis_home as HOME
    except Exception as exc:
        return None, f"Control Home Assistant: {json.dumps(args, ensure_ascii=False)} " \
                      f"(unavailable: {exc})"
    p = HOME.plan_service(str(args.get("domain", "")), str(args.get("service", "")),
                           str(args.get("entity_id", "")), args.get("data") or {})
    return p, HOME.describe(p)


def _run_home_control(args: dict, plan_obj, **_) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "Home Assistant is not available here"}
    import jarvis_home as HOME
    return HOME.run(plan_obj, approved=True)


def _prepare_note(kind: str):
    """prepare() for the two note tools: jarvis_note_capture's plan + card."""
    def prepare(args: dict):
        try:
            import jarvis_note_capture as NC
        except Exception as exc:
            return None, (f"File a note: {json.dumps(args, ensure_ascii=False)} "
                          f"(unavailable: {exc})")
        return (NC.prepare_logseq_tool(args) if kind == "logseq"
                else NC.prepare_joplin_tool(args))
    return prepare


def _run_note(args: dict, plan_obj, **_) -> dict:
    if plan_obj is None:
        return {"ok": False, "error": "note filing is not available here"}
    import jarvis_note_capture as NC
    return NC.run(plan_obj, approved=True)


class Tool:
    """One tool. The gate action is looked up against jarvis_gate's own
    tables (`action_for_tool`) rather than duplicated here, so the tier the
    owner sees in jarvis-framework.toml is the one true source.

    `prepare(args) -> (state, description_text)` runs ONCE, before the gate
    decision, and `execute(args, state, **kwargs)` runs ONLY if approved,
    receiving that SAME `state` back - never a value recomputed from `args`
    a second time. This matters for control_computer/control_phone/
    github_search specifically: their `state` is a Plan built by reading
    live, mutable state (a window's current controls, a phone's current
    screen, whether a token happens to be configured right now). Recomputing
    it at execute() time - the original shape of this module, before this
    was found and fixed - would mean the steps that actually run can differ
    from the ones the approval card showed and a human approved, which is
    exactly the gap docs/ARCHITECTURE.md's "run() executes an approved plan"
    contract, and jarvis_ui_control.run()'s own re-verify-every-step logic,
    both exist to close. `state` is `None` for tools with nothing to plan
    (calculator, memory_search, file_read, shell_exec) - they just re-read
    `args`.

    `gate_lookup_name`, when given, is the name PASSED to
    `jarvis_gate.action_for_tool()` - which may differ from `name` (the one
    the model sees) for two reasons: `action_for_tool` needs the EXACT key
    registered in jarvis_gate's own `_TOOL_ACTIONS` (getting this wrong does
    not raise - it silently falls through to "unclassified_tool", which
    still asks by default but loses the specific risk text the real action
    carries), and some tools resolve to a DIFFERENT action depending on
    runtime state (github_search: authenticated or not), which a static
    name cannot express. Omitted, `name` itself is used - correct for every
    tool here whose model-facing name already IS its jarvis_gate key.
    """

    def __init__(self, name: str, description: str, parameters: dict,
                 prepare: Callable[[dict], tuple],
                 execute: Callable[..., dict], needs_announce: bool = False,
                 gate_lookup_name: Optional[Callable[[dict], str]] = None):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.prepare = prepare
        self.execute = execute
        self.needs_announce = needs_announce
        self.gate_lookup_name = gate_lookup_name

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters}}


def _plain_prepare(label: str) -> Callable[[dict], tuple]:
    return lambda args: (None, f"{label}: {json.dumps(args, ensure_ascii=False)}")


TOOLS: dict = {
    "calculator": Tool(
        "calculator", "Evaluate a plain arithmetic expression.",
        {"type": "object", "properties": {
            "expression": {"type": "string"}}, "required": ["expression"]},
        _plain_prepare("Evaluate"), lambda args, state, **_: _run_calculator(args)),
    "memory_search": Tool(
        "memory_search", "Search what Jarvis has been told and remembers.",
        {"type": "object", "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "how many facts, default 5"}},
         "required": ["query"]},
        _plain_prepare("Search memory for"),
        lambda args, state, **_: _run_memory_search(args)),
    "file_read": Tool(
        "file_read", "Read a local text file.",
        {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]},
        lambda args: (None, f"Read the file: {args.get('path', '')}"),
        lambda args, state, **_: _run_file_read(args)),
    "shell_exec": Tool(
        "shell_exec", "Run one shell command on this machine and return its output.",
        {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout_seconds": {"type": "number"}}, "required": ["command"]},
        lambda args: (None, f"Run this command:\n\n    {args.get('command', '')}"),
        _run_shell_exec_tool),
    "control_computer": Tool(
        "control_computer",
        "Click or type inside another Windows program, by naming its "
        "on-screen controls. Reads the target window first; a control that "
        "cannot be found is reported, not guessed at.",
        {"type": "object", "properties": {
            "goal": {"type": "string"},
            "window": {"type": "string", "description": "the exact window title"},
            "requests": {"type": "array", "items": {"type": "object", "properties": {
                "control": {"type": "string"}, "action": {"type": "string",
                    "enum": ["click", "type", "select", "read"]},
                "value": {"type": "string"}, "why": {"type": "string"},
                "irreversible": {"type": "boolean"},
                "leaves_machine": {"type": "boolean"}}}}},
         "required": ["goal", "window", "requests"]},
        _prepare_control_computer,
        lambda args, state, **kw: _run_control_computer(args, state, announce=kw.get("announce"),
                                                checkpoint=kw.get("checkpoint")),
        needs_announce=True,
        # "control_computer" is a friendlier name for the model than the
        # actual jarvis_gate key ("jarvis_ui_control_run") this maps to -
        # see ui-control-wiring.patch's own _TOOL_ACTIONS entry.
        gate_lookup_name=lambda args: "jarvis_ui_control_run"),
    "control_phone": Tool(
        "control_phone",
        "Tap, swipe, type, press a key, or take a screenshot on the "
        "owner's own paired Android phone over adb.",
        {"type": "object", "properties": {
            "device": {"type": "string"},
            "goal": {"type": "string"},
            "requests": {"type": "array", "items": {"type": "object", "properties": {
                "action": {"type": "string",
                    "enum": ["tap", "swipe", "key", "text", "screenshot"]},
                "x": {"type": "integer"}, "y": {"type": "integer"},
                "x1": {"type": "integer"}, "y1": {"type": "integer"},
                "x2": {"type": "integer"}, "y2": {"type": "integer"},
                "key": {"type": "string"}, "value": {"type": "string"},
                "why": {"type": "string"},
                "irreversible": {"type": "boolean"},
                "leaves_machine": {"type": "boolean"}}}}},
         "required": ["device", "goal", "requests"]},
        _prepare_control_phone,
        lambda args, state, **kw: _run_control_phone(args, state, announce=kw.get("announce"),
                                                checkpoint=kw.get("checkpoint")),
        needs_announce=True,
        gate_lookup_name=lambda args: "jarvis_android_control_run"),
    "browser_control": Tool(
        "browser_control",
        "Drive one browser tab (navigate, click, type, select, read, "
        "read_new, or read_page) by naming its on-screen elements. Reads the "
        "current page first; an element that cannot be found - or that "
        "matches more than one element - is reported, not guessed at (add "
        "'within' with the name of the section it is in to say which). "
        "read_new follows a chat conversation of any length - it takes "
        "the transcript CONTAINER and a cursor, and returns only messages "
        "since that cursor, so a long-running conversation never costs more "
        "per turn than the newest messages in it. read_page returns the "
        "page's main text in capped pieces. The run stops if the page leaves "
        "the allowed sites, asks a question, opens a tab, or starts a "
        "download. Only offered when the "
        "owner has explicitly enabled it - see jarvis_browser_control.py's "
        "own docstring for why it ships off.",
        {"type": "object", "properties": {
            "goal": {"type": "string"},
            "session": {"type": "string", "description": "a label for which browser tab"},
            "allowed_domains": {"type": "array", "items": {"type": "string"},
                "description": "optional hostname allowlist - for navigate steps, and for "
                    "anywhere a click or redirect takes the tab while the plan runs "
                    "(omitted: only the sites the plan itself names)"},
            "requests": {"type": "array", "items": {"type": "object", "properties": {
                "action": {"type": "string",
                    "enum": ["navigate", "click", "type", "select", "read", "read_new",
                             "read_page"]},
                "role": {"type": "string", "description": "accessibility role, e.g. button, "
                    "textbox - for read_new, the role of the message-list CONTAINER"},
                "name": {"type": "string", "description": "the element's accessible name - "
                    "for read_new, the container's accessible name"},
                "within": {"type": "string", "description": "optional: the name of the "
                    "section, dialog, row or list item the element is inside, when two "
                    "elements share a role and name"},
                "value": {"type": "string", "description": "URL for navigate, text for "
                    "type/select (a type may write a saved secret as <secret>name</secret>; "
                    "its real value is never shown to you), for read_new the highest "
                    "message index already seen, for read_page the character offset to "
                    "read from (omit or \"0\" to read from the start)"},
                "why": {"type": "string"},
                "irreversible": {"type": "boolean"},
                "leaves_machine": {"type": "boolean",
                    "description": "true for nearly every step here - a browser step almost "
                                    "always sends something to whoever is on the other end"},
            }}}},
         "required": ["goal", "session", "requests"]},
        _prepare_browser_control,
        lambda args, state, **kw: _run_browser_control(args, state, announce=kw.get("announce"),
                                                checkpoint=kw.get("checkpoint")),
        needs_announce=True,
        # New action name, same reason control_phone is: no existing
        # jarvis_gate tier fits a browser step - see browser-control-wiring
        # in backend/README.md for the [autonomy.tiers] line this needs.
        gate_lookup_name=lambda args: "jarvis_browser_control_run"),
    "github_search": Tool(
        "github_search",
        "Check whether a library or approach for a coding idea already "
        "exists on GitHub, graded by maintenance and licence, before "
        "building it from scratch.",
        {"type": "object", "properties": {
            "idea": {"type": "string"},
            "capabilities": {"type": "array", "items": {"type": "string"}}},
         "required": ["idea"]},
        _prepare_github_search, _run_github_search,
        # Resolved at call time, not import time: whether a token is
        # configured can change between two calls in the same conversation,
        # and jarvis_research.py's own run() already refuses if the token
        # state changes between its plan() and run() - this only decides
        # which action name (and therefore which tier) governs THIS call.
        gate_lookup_name=lambda args: _github_search_action_name()),
    "calendar_read": Tool(
        "calendar_read",
        "Read the owner's own calendar (CalDAV) for the next N days - "
        "event titles, times, and locations. Read-only; never creates or "
        "changes an event.",
        {"type": "object", "properties": {
            "days_ahead": {"type": "integer",
                "description": "how many days ahead to look, default 7, max 90"}}},
        _prepare_calendar_read,
        lambda args, state, **_: _run_calendar_read(args, state),
        gate_lookup_name=lambda args: "jarvis_calendar_read_run"),
    "email_check": Tool(
        "email_check",
        "Check the owner's own IMAP inbox for recent messages - sender, "
        "subject, date, and a short plain-text preview of each. Read-only; "
        "never sends, replies to, deletes, or marks anything.",
        {"type": "object", "properties": {
            "limit": {"type": "integer",
                "description": "how many messages, default 10, max 25"},
            "unread_only": {"type": "boolean",
                "description": "true (default) for unread mail only, false for all"}}},
        _prepare_email_check,
        lambda args, state, **_: _run_email_check(args, state),
        gate_lookup_name=lambda args: "jarvis_email_read_run"),
    "notes_search": Tool(
        "notes_search",
        "Search the owner's own notes in Joplin or Obsidian, over each "
        "app's local REST API. Read-only; never creates or edits a note.",
        {"type": "object", "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer",
                "description": "how many results, default 10, max 20"}},
         "required": ["query"]},
        _prepare_notes_search,
        lambda args, state, **_: _run_notes_search(args, state),
        gate_lookup_name=lambda args: "jarvis_notes_search_run"),
    "home_read": Tool(
        "home_read",
        "Read the current state of specific, named Home Assistant "
        "entities - never the whole house at once. Read-only.",
        {"type": "object", "properties": {
            "entity_ids": {"type": "array", "items": {"type": "string"},
                "description": "e.g. [\"light.kitchen\", \"lock.front_door\"], max 20"}},
         "required": ["entity_ids"]},
        _prepare_home_read,
        lambda args, state, **_: _run_home_read(args, state),
        gate_lookup_name=lambda args: "jarvis_home_read_run"),
    "home_control": Tool(
        "home_control",
        "Call one Home Assistant service on one named entity - turn a "
        "light on, unlock a door, and so on. This changes something real, "
        "not just data; a lock, alarm, or cover action is treated as "
        "especially consequential.",
        {"type": "object", "properties": {
            "domain": {"type": "string", "description": "e.g. \"light\", \"lock\""},
            "service": {"type": "string", "description": "e.g. \"turn_on\", \"unlock\""},
            "entity_id": {"type": "string"},
            "data": {"type": "object",
                "description": "extra service data, e.g. {\"brightness\": 200}"}},
         "required": ["domain", "service", "entity_id"]},
        _prepare_home_control,
        lambda args, state, **_: _run_home_control(args, state),
        gate_lookup_name=lambda args: "jarvis_home_control_run"),
    # The two note WRITES (jarvis_note_capture.py). Their action names are the
    # ones the owner's jarvis-framework.toml already has tiers for, so that
    # file - not this one - decides whether each asks first. Like every tool
    # here they are offered only when [tools].enabled names them. The desktop's
    # #log / #joplin / quick note do NOT go through these: they post the
    # owner's own words to /api/notes/capture, with no model involved.
    "append_logseq_journal": Tool(
        "append_logseq_journal",
        "Add one entry to the end of today's Logseq journal page on this PC. "
        "Only ever adds; never changes or removes anything already written.",
        {"type": "object", "properties": {
            "text": {"type": "string", "description": "the entry, in the owner's words"}},
         "required": ["text"]},
        _prepare_note("logseq"), _run_note,
        gate_lookup_name=lambda args: "append_logseq_journal"),
    "create_joplin_note": Tool(
        "create_joplin_note",
        "Create one NEW note in Joplin on this PC. Never edits an existing note "
        "and never creates a notebook.",
        {"type": "object", "properties": {
            "title": {"type": "string"},
            "body": {"type": "string"},
            "notebook": {"type": "string",
                "description": "an existing notebook's exact name; omit for Joplin's default"}},
         "required": ["title", "body"]},
        _prepare_note("joplin"), _run_note,
        gate_lookup_name=lambda args: "create_joplin_note"),
}


#: The tools that run a multi-step plan, and the module that plans and runs
#: it. These are the ones Pause, Stop and Resume apply to (task-control.patch):
#: each module's run() reads a `checkpoint` before every step. A resume runs
#: the SAME plan object, cut down to the steps that did not run, through the
#: same module's describe() and run() - see jarvis_task_control.resume().
_TASK_MODULES = {
    "control_computer": "jarvis_ui_control",
    "control_phone": "jarvis_android_control",
    "browser_control": "jarvis_browser_control",
}


def _task_control():
    """jarvis_task_control, or None when it is not installed."""
    try:
        import jarvis_task_control
        return jarvis_task_control
    except Exception:
        return None


def _github_search_action_name() -> str:
    try:
        import jarvis_research
        if jarvis_research.authenticated():
            return "jarvis_research_run_authenticated"
    except Exception:
        pass
    return "jarvis_research_run"


#: Tools that must never run unless a PERSON said yes on a card, whatever
#: tier jarvis-framework.toml gives their action.
#:
#: docs/ARCHITECTURE.md §3: "`allowed` is not 'a human decided'" - the gate
#: returns allowed=True on tier `auto` (nobody asked) and `notify` (told
#: after). That was all this loop checked, so `github_search`, which resolves
#: to `web_research` - "auto" in the shipped config - sent a model-chosen
#: search term to GitHub with nobody asked, while §4 lists research as egress
#: "per approved plan" and jarvis_research.run() is documented as executing
#: "a plan that a human has already approved".
#:
#: Each entry either leaves this machine with something the model chose, or
#: can: the gate's own risk table calls a shell, the desktop and the phone
#: "outbound" by their worst case, a browser step nearly always sends
#: something, and home_control moves a real lock or light. The reads the
#: owner chose to leave at "auto" (calendar, email, notes, home state) and the
#: two note writes (owner decision, 2026-09-23: saved straight away, no card)
#: are deliberately NOT here - they are the config's call.
NEEDS_A_PERSON = {
    "github_search": "sends a search term to GitHub",
    "browser_control": "drives a web page, which nearly always sends something",
    "control_computer": "clicks and types in another program, which can press Send",
    "control_phone": "taps on the phone, which can send a message or pay for something",
    "shell_exec": "runs a command, which can do anything, including reach the internet",
    "home_control": "changes something real in the house",
}


#: jarvis_gate stores a card's `detail` as `json.dumps(detail)[:4000]`. A
#: plan longer than that reached the card cut off mid-step - and still had a
#: working Approve button - breaking ARCHITECTURE §3's "every command, every
#: URL, in FULL". A long browser or UI plan could do exactly that.
_GATE_DETAIL_LIMIT = 4000


def _tier_of(action: str) -> str:
    """The configured tier for `action`, or "ask" when it cannot be read -
    the same fail-closed default as the gate's own unknown_action_tier."""
    try:
        import jarvis_framework
        return str(jarvis_framework.action_tier(action))
    except Exception:
        return "ask"


def _card_would_be_cut(name: str, action: str, plan_text: str) -> bool:
    """True when this call would put a plan in front of a person that the
    gate would cut short. Only where a person could be asked: an action at
    tier auto or notify shows no card, and the owner's choice to save notes
    straight away (2026-09-23) is not overridden here - unless the tool is
    one that only ever runs on a person's yes (NEEDS_A_PERSON)."""
    if len(json.dumps({"text": plan_text})) < _GATE_DETAIL_LIMIT:
        return False
    return name in NEEDS_A_PERSON or _tier_of(action) not in ("auto", "notify")


def _a_person_said_yes(verdict) -> bool:
    """True only when the gate's verdict records a human approving.

    Read off `outcome` (gate-outcome.patch) when the gate sets one: only
    "approved" is a person. A gate from before that patch has no `outcome`,
    and then the same rule jarvis_voice_enroll uses applies: allowed AND tier
    "ask" is the only reading that means somebody was asked."""
    if getattr(verdict, "allowed", False) is not True:
        return False
    outcome = getattr(verdict, "outcome", None)
    if outcome is not None:
        return outcome == "approved"
    return getattr(verdict, "tier", None) == "ask"


# --------------------------------------------------------------------------
#   The loop
# --------------------------------------------------------------------------

def _post(url: str, payload: dict, timeout: float = 300.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _open_stream(url: str, payload: dict, timeout: float = 300.0):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=timeout)


def _get_json(url: str, payload: Optional[dict] = None, timeout: float = 4.0) -> dict:
    """A small JSON call to Ollama's own API - GET, or POST when there is a
    body. Only used to look up the context length; see _context_length."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# --------------------------------------------------------------------------
#   What goes down the wire to the app
# --------------------------------------------------------------------------
#
# ONE FORMAT, AND IT IS OLLAMA'S. The HUD page, the quickbar and the phone
# already read Ollama's OpenAI-compatible stream (`data: {chunk}` lines, a
# chunk with a `finish_reason`, then `data: [DONE]`), because a turn without
# tools used to be relayed from Ollama byte for byte. So a tool turn speaks
# exactly that too: every chunk written here has the shape Ollama's own
# `openai.ChatCompletionChunk` has (ollama/openai/openai.go), and the tests
# feed this output through all three apps' real readers
# (test_chat_stream_contract.py).
#
# What is NOT passed on from Ollama, on purpose:
#   - a round's own `finish_reason: "tool_calls"` chunk and its `[DONE]`.
#     Every app treats either as "the answer is over" and would stop reading
#     before the answer was written.
#   - `tool_calls` deltas. Tools are run here, through the gate; the app
#     never sees a request to run one.
#   - `reasoning` deltas (Qwen3's thinking). No app shows them, and thinking
#     text can quote an email or a file the model just read.
#
# Two kinds of line are ADDED, both SSE comments - a line starting with ":",
# which every SSE reader skips, so an app that does not know them loses
# nothing:
#   `: keepalive`               - nothing to say yet, but the PC is still
#                                 here. Sent after KEEPALIVE_SECONDS of
#                                 silence, so a phone's "no bytes for two
#                                 minutes" timeout never fires while an
#                                 approval card waits (the gate waits up to
#                                 three minutes) or a cold model loads.
#   `: jarvis-status <what>`    - what the turn is waiting on, one word from
#                                 STATUS_WORDS. "approval" means a card is up
#                                 and nothing happens until someone answers
#                                 it. Only said once the wait has lasted
#                                 STATUS_DELAY_SECONDS, so a tool the gate
#                                 lets through at once never flashes it.
#
# With `stream: false` the answer is ONE JSON body, Ollama's own
# `chat.completion` shape, and the only thing written before it is blank
# lines ("\n") as keepalives - which every JSON parser skips.

KEEPALIVE_SECONDS = 10.0
STATUS_DELAY_SECONDS = 1.5
STATUS_PREFIX = ": jarvis-status "
STATUS_WORDS = ("thinking", "approval", "working")

#: When the app does not say how long an answer may be. The same number as
#: `num_predict` in jarvis-primary.Modelfile, so every window gets the same
#: length of answer whichever model is loaded.
DEFAULT_MAX_TOKENS = 1024

#: When Ollama cannot say how much context the model has. Ollama's own
#: fallback on this card (docs/MODEL-TOPOLOGY.md), so the smallest it could be.
DEFAULT_CONTEXT = 4096


def content_type(stream: bool) -> str:
    """The Content-Type for a reply written by run_local_turn - the header
    has to match the body, because the HUD page picks its reader from it
    (`text/event-stream` -> read `data:` lines, anything else ->
    `res.json()`). It used to be application/json on an SSE body, and the
    HUD failed every tool turn with "Unexpected token 'd'"."""
    return "text/event-stream" if stream else "application/json"


class ClientGone(Exception):
    """The app that asked for this turn is no longer listening."""


class UpstreamError(Exception):
    """Ollama could not answer. `str()` is a plain sentence for the owner."""


def _status_line(word: str) -> bytes:
    return f"{STATUS_PREFIX}{word}\n\n".encode("utf-8")


def _sse(obj) -> bytes:
    if obj == "[DONE]":
        return b"data: [DONE]\n\n"
    return (b"data: " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n\n")


def _chunk(cid: str, created: int, model: str, delta: dict,
           finish: Optional[str] = None) -> dict:
    """One chunk, in exactly the shape Ollama's openai.ChatCompletionChunk
    serialises to."""
    return {"id": cid, "object": "chat.completion.chunk", "created": created,
            "model": model, "system_fingerprint": "fp_ollama",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


class _Out:
    """The one writer to the app. Several threads write through it (the turn,
    and the keepalive below), so it holds a lock; and it remembers when a
    write failed, which is how this side learns the app went away."""

    _GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
             TimeoutError, socket.timeout, OSError)

    def __init__(self, write: Callable[[bytes], None], sse: bool):
        self._write = write
        self.sse = sse
        self._lock = threading.Lock()
        self.gone = False
        self.last = time.monotonic()
        self.status: Optional[str] = None
        self.status_since = time.monotonic()
        self.status_said = True

    def send(self, data: bytes) -> bool:
        with self._lock:
            if self.gone:
                return False
            try:
                self._write(data)
            except self._GONE:
                self.gone = True
                return False
            self.last = time.monotonic()
            return True

    def set_status(self, word: Optional[str]) -> None:
        self.status = word
        self.status_since = time.monotonic()
        self.status_said = word is None


def _heartbeat(out: _Out, stop: threading.Event, every: float, delay: float) -> None:
    """Keepalives and status lines, until `stop` is set. Runs beside the turn.

    The keepalive is also how a closed app is noticed while nothing else is
    being written - a gate waiting for a card, a tool running - because a
    write to a socket nobody reads fails, and `_Out` remembers that."""
    tick = max(0.02, min(0.5, every / 4, delay / 2 if delay > 0 else 0.5))
    while not stop.wait(tick):
        now = time.monotonic()
        word = out.status
        if (out.sse and word and not out.status_said
                and now - out.status_since >= delay):
            out.status_said = True
            out.send(_status_line(word))
        elif now - out.last >= every:
            out.send(b": keepalive\n\n" if out.sse else b"\n")


# --------------------------------------------------------------------------
#   Qwen3's thinking, kept out of the answer
# --------------------------------------------------------------------------
#
# jarvis-primary.Modelfile says thinking is off, and nothing used to turn it
# off: Ollama switches thinking ON by default for a model that can think
# (server/routes.go: `if req.Think == nil ... req.Think = &api.ThinkValue{Value:
# true}`), so every answer spent part of its 1,024-token allowance on
# reasoning no window showed. The supported switch on the endpoint this
# project uses is `reasoning_effort: "none"` (ollama/openai/openai.go,
# ThinkingFromReasoningEffort: "none" -> think false). Every request below
# sends it; an Ollama too old to know the word "none" answers 400, and the
# request goes again without it.
#
# And in case thinking still arrives INSIDE the text - an older Ollama that
# does not separate it, a model whose template does not - the `<think>` block
# is cut out here, before anything is shown, spoken or kept in history.
REASONING_OFF = {"reasoning_effort": "none"}
_reasoning_field_refused = False


class _ThinkStripper:
    """Removes `<think>...</think>` from text that arrives in pieces. A tag
    split across two pieces is held back until it is whole."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self._buf = ""
        self._inside = False
        self._after_close = False

    def feed(self, text: str) -> str:
        self._buf += text
        out = []
        while self._buf:
            if self._inside:
                i = self._buf.find(self.CLOSE)
                if i < 0:
                    keep = _partial_suffix(self._buf, self.CLOSE)
                    self._buf = self._buf[len(self._buf) - keep:] if keep else ""
                    break
                self._buf = self._buf[i + len(self.CLOSE):]
                self._inside = False
                self._after_close = True
                continue
            if self._after_close:
                stripped = self._buf.lstrip()
                if not stripped:
                    self._buf = ""
                    break
                self._buf = stripped
                self._after_close = False
            i = self._buf.find(self.OPEN)
            if i >= 0:
                out.append(self._buf[:i])
                self._buf = self._buf[i + len(self.OPEN):]
                self._inside = True
                continue
            keep = _partial_suffix(self._buf, self.OPEN)
            out.append(self._buf[:len(self._buf) - keep])
            self._buf = self._buf[len(self._buf) - keep:] if keep else ""
            break
        return "".join(out)

    def flush(self) -> str:
        """What is left at the end. An unfinished think block is dropped."""
        rest = "" if self._inside else self._buf
        self._buf = ""
        return rest


def _partial_suffix(text: str, tag: str) -> int:
    """How many characters at the end of `text` could be the start of `tag`."""
    for n in range(min(len(tag) - 1, len(text)), 0, -1):
        if tag.startswith(text[-n:]):
            return n
    return 0


def strip_thinking(text: str) -> str:
    """The same cut on a whole piece of text."""
    s = _ThinkStripper()
    return s.feed(text) + s.flush()


# --------------------------------------------------------------------------
#   Fitting the conversation into the model's real context
# --------------------------------------------------------------------------
#
# Both apps cap the history they send, sized for num_ctx 16384
# (jarvis-primary.Modelfile). But the model actually loaded may have 4096 -
# Ollama's own default, any model switched to from the phone, or
# jarvis-primary before it was created - and tool results (up to 8,000
# characters each, six rounds) were in nobody's budget. Past the limit Ollama
# drops the earliest turns itself, silently, and leaves no room for the answer.
#
# This is the one place that can know the real number, so it asks Ollama
# (/api/ps for the loaded model, /api/show for its Modelfile) and trims to
# fit BEFORE sending. The apps' own caps stay as an upper bound.

_CTX_CACHE: dict = {}
_CTX_TTL = 60.0


def _lookup_context(ollama_url: str, model: str) -> Optional[int]:
    """The model's context length as Ollama reports it, or None."""
    try:
        ps = _get_json(f"{ollama_url}/api/ps")
        for m in ps.get("models") or []:
            names = {m.get("name"), m.get("model")}
            if model in names or f"{model}:latest" in names:
                n = int(m.get("context_length") or 0)
                if n > 0:
                    return n
    except Exception:
        pass
    try:
        show = _get_json(f"{ollama_url}/api/show", {"model": model})
        m = re.search(r"(?m)^\s*num_ctx\s+(\d+)", str(show.get("parameters") or ""))
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def _context_length(ollama_url: str, model: str) -> int:
    now = time.monotonic()
    hit = _CTX_CACHE.get((ollama_url, model))
    if hit and now - hit[1] < _CTX_TTL:
        return hit[0]
    n = _lookup_context(ollama_url, model) or DEFAULT_CONTEXT
    _CTX_CACHE[(ollama_url, model)] = (n, now)
    return n


def estimate_tokens(obj) -> int:
    """A pessimistic count: 3 characters a token (English is nearer 4), a
    few tokens of framing per message, a flat 1,000 for a picture."""
    if isinstance(obj, list):
        return sum(estimate_tokens(m) for m in obj)
    if isinstance(obj, dict) and "role" in obj:
        content = obj.get("content")
        n = 6
        if isinstance(content, str):
            n += len(content) // 3
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    n += len(str(part.get("text") or "")) // 3
                else:
                    n += 1000
        if obj.get("tool_calls"):
            n += len(json.dumps(obj["tool_calls"], ensure_ascii=False)) // 3
        return n
    return len(json.dumps(obj, ensure_ascii=False)) // 3


#: The Modelfile's SYSTEM block and the chat template.
_TEMPLATE_TOKENS = 300


def fit_messages(messages: list, budget: int) -> list:
    """`messages`, with the oldest earlier turns dropped until they fit in
    `budget` tokens.

    Never dropped: any system message (the recalled facts, the apps' per-turn
    notes, the persona), and the current turn - the newest user message and
    everything after it, tool results included. Earlier turns go oldest
    first, a question together with its answer, never cut mid-message. When
    anything has to go, it goes down to three quarters of the budget, so the
    start of the prompt then stays the same for a few turns and Ollama can
    reuse what it has already read."""
    msgs = list(messages)
    if estimate_tokens(msgs) <= budget:
        return msgs
    last_user = max((i for i, m in enumerate(msgs)
                     if isinstance(m, dict) and m.get("role") == "user"), default=len(msgs))
    target = int(budget * 0.75)
    earlier = [i for i in range(last_user)
               if not (isinstance(msgs[i], dict) and msgs[i].get("role") == "system")]
    dropped: set = set()
    total = estimate_tokens(msgs)
    k = 0
    while k < len(earlier) and total > target:
        i = earlier[k]
        dropped.add(i)
        total -= estimate_tokens(msgs[i])
        k += 1
        # An answer, or a tool result, left without the question before it
        # goes with it.
        while k < len(earlier) and msgs[earlier[k]].get("role") != "user":
            dropped.add(earlier[k])
            total -= estimate_tokens(msgs[earlier[k]])
            k += 1
    return [m for i, m in enumerate(msgs) if i not in dropped]


# --------------------------------------------------------------------------
#   Plain words when Ollama cannot answer
# --------------------------------------------------------------------------

def _ollama_error_text(raw: str) -> str:
    """The message out of an Ollama error body: `{"error": {"message": ...}}`
    on /v1, `{"error": "..."}` on its native API, or the raw text."""
    try:
        body = json.loads(raw)
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            return str(err.get("message") or "")
        if isinstance(err, str):
            return err
    except Exception:
        pass
    return (raw or "").strip()[:300]


def plain_error(exc: BaseException, model: str, said: Optional[str] = None) -> str:
    """What to tell the owner when a request to Ollama failed, and what to
    do about it. Never a Python exception name on its own.

    `said` is the error body when the caller has already read it (an HTTP
    error body can only be read once)."""
    if isinstance(exc, urllib.error.HTTPError):
        if said is None:
            try:
                said = exc.read().decode("utf-8", "replace")
            except Exception:
                said = ""
        said = _ollama_error_text(said)
        if exc.code == 404 and ("not found" in said.lower() or not said):
            return (f"The model “{model}” is not installed on this PC. "
                    f"Install it from Models in the desktop app (or run "
                    f"`ollama pull {model}`), or switch to a model you have.")
        return (f"The local model answered with an error (HTTP {exc.code})"
                + (f": {said}" if said else ".")
                + " Try again; if it keeps happening, restart Ollama.")
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (socket.timeout, TimeoutError)) or isinstance(exc, (socket.timeout, TimeoutError)):
        return ("The local model stopped answering for five minutes. It may be "
                "stuck: restart Ollama, then try again.")
    return ("The local model is not running. Open Ollama on this PC (or run "
            "`ollama serve`), then try again.")


_MAX_TOOL_CONTENT_CHARS = 8000


def _tool_content(result: dict) -> str:
    """A tool's result, as the JSON string fed back to the model - always
    valid JSON, never a byte-slice of one. `json.dumps(result)[:N]` can cut
    off mid-string or mid-structure (an open quote, an unclosed brace), and
    a large result is not a hypothetical here: file_read alone can return
    up to 200,000 characters of content, far past any per-message budget.
    A model reading a hand-mangled JSON fragment as "the tool's answer" is a
    worse failure than an honest, valid, short note that it was too big."""
    full = json.dumps(result, ensure_ascii=False)
    if len(full) <= _MAX_TOOL_CONTENT_CHARS:
        return full
    return json.dumps({
        "ok": result.get("ok"),
        "truncated": True,
        "note": f"the real result was {len(full)} characters - too large to "
                 "show in full here",
    }, ensure_ascii=False)


def _after_task(tc, task_id: str, name: str, action_name: str, plan_obj,
                result: dict) -> dict:
    """What happens once a pausable plan's run() has returned.

    Paused: keep the ORIGINAL plan object, cut down to the steps that did
    not run, so Resume can show and run exactly those (task-control.patch).
    Then, however it ended, hand the model any note the owner sent while it
    ran - "for what runs next", so the model reads it before choosing its
    next step. A note never alters a step that was already approved.
    """
    out = dict(result)
    if out.get("paused") and plan_obj is not None:
        try:
            import dataclasses
            steps = list(getattr(plan_obj, "steps", []) or [])
            not_run = len(out.get("not_run") or [])
            rest = dataclasses.replace(plan_obj, steps=steps[len(steps) - not_run:])
            tc.remember_paused(task_id, tool=name, action=action_name,
                               module=_TASK_MODULES[name], plan=rest,
                               not_run=not_run, done=len(out.get("done") or []))
            out["paused_note"] = ("Paused by the owner. Do not try to redo these steps "
                                  "yourself: the owner can resume them, which asks "
                                  "them first, or stop.")
        except Exception:
            pass
    try:
        note = tc.take_note(task_id)
    except Exception:
        note = None
    if note:
        out["owner_note"] = note
    return out


def _gate_check(action: str, detail: dict, prompt: str):
    """Wraps jarvis_gate.check() so ANY failure here - the module missing,
    or `check()` itself raising for a reason this function cannot predict -
    fails CLOSED, refused, never silently allowed. The try/except covers the
    whole call, not only the import: a module that can act must not turn an
    internal error into an unguarded pass, which is the same standard
    jarvis_gate.py's own docstring holds itself to ("if this module cannot
    do its job it refuses rather than waving things through")."""
    class _Refused:
        def __init__(self, reason):
            self.allowed = False
            self.reason = reason
    try:
        import jarvis_gate
    except Exception as exc:
        return _Refused(f"the approval gate is not available here ({exc}); refusing")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:
        return _Refused(f"the approval gate raised {type(exc).__name__}: {exc}; refusing")


def _record_chain(steps: list) -> None:
    """The default end-of-turn recorder: one audit line naming the tools this
    turn asked for, in order, and whether each ran - then, at most, a
    background check for a routine worth offering as a skill. See
    jarvis_skill_discovery.py for what is written and why.

    Tool NAMES only. `steps` has no field for an argument or a result, so no
    conversation text can reach the log through here. Best-effort: a missing
    module or a failed write must never cost the owner their answer."""
    if not steps:
        return
    try:
        import jarvis_skill_discovery
    except Exception:
        return
    try:
        if jarvis_skill_discovery.record_turn(steps):
            jarvis_skill_discovery.maybe_offer_async()
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Steps, for Brain -> Live
# --------------------------------------------------------------------------
#
# What Jarvis is doing inside one turn - asking the model, using a tool, a
# tool finishing or being refused, writing the answer - published on the one
# event bus as kind "step", so the desktop's Brain -> Live can show it as it
# happens. Before this, Live said per-step reasoning "is not on the bus yet".
#
# THE BUS IS A DOORBELL (docs/ARCHITECTURE.md section 6) and it reaches a
# phone that shows notifications with the screen off. So a step carries an
# ALLOWLIST of fields, every value from our own vocabulary:
#
#   phase   one of _STEP_PHASES
#   tool    a name from TOOLS - never the model's spelling of one, never an
#           argument, never a result. A name the model made up is "unknown".
#   ok      a boolean, on tool_finished
#   round   an integer
#
# Deliberately NOT here: the model's own reasoning (Qwen3's thinking text),
# tool arguments, tool results. Each can quote an email body, a file or a
# secret, and none of that may ride a doorbell. Reading them stays inside
# the authenticated app, where it already is.
_STEP_PHASES = ("model", "tool_started", "tool_finished", "tool_refused", "answer")


def _step_event(phase: str, tool: Optional[str] = None, *,
                ok: Optional[bool] = None, round_no: Optional[int] = None) -> dict:
    """One step, reduced to what the event bus may carry."""
    out: dict = {"phase": phase if phase in _STEP_PHASES else "unknown"}
    if tool is not None:
        out["tool"] = tool if isinstance(tool, str) and tool in TOOLS else "unknown"
    if ok is not None:
        out["ok"] = bool(ok)
    if round_no is not None:
        try:
            out["round"] = int(round_no)
        except (TypeError, ValueError):
            pass
    return out


def _publish_step(step: dict) -> None:
    """The default step sink: the one event bus, best-effort. A missing
    module or a failed publish must never cost the owner their answer."""
    try:
        import jarvis_events
        jarvis_events.BUS.publish("step", step)
    except Exception:
        pass


def offered_tools(enabled_tools) -> list:
    """The tool names a turn actually offers the model: the ones in
    `enabled_tools` that are real tools here, in TOOLS order. `None` means
    every tool (for callers, and tests, that do not read the config).

    `[tools].enabled` in the owner's config can list names this module has
    never had - that list is shared with collect_tools() and /api/status,
    which know other things. Offering "tools" that are not here would mean
    a turn that can only ever be told "no such tool"."""
    if enabled_tools is None:
        return list(TOOLS)
    wanted = set(enabled_tools)
    return [n for n in TOOLS if n in wanted]


class _Round:
    """What one request to the model produced."""

    def __init__(self):
        self.text: list = []
        self.calls: list = []
        self.finish: Optional[str] = None
        self.ended = False
        self.id = ""
        self.created = 0

    def add_calls(self, deltas) -> None:
        """Tool calls as they arrive. Ollama sends each call whole in one
        chunk; the OpenAI format allows the arguments in fragments, the first
        carrying the id and name. Both are put back together here."""
        for d in deltas or []:
            if not isinstance(d, dict):
                continue
            fn = d.get("function") or {}
            cid = d.get("id") or ""
            same = next((c for c in self.calls if cid and c.get("id") == cid), None)
            if same is None and not fn.get("name") and self.calls:
                idx = d.get("index")
                same = next((c for c in self.calls if c.get("_index") == idx), self.calls[-1])
            if same is None:
                same = {"id": cid, "type": "function", "_index": d.get("index"),
                        "function": {"name": fn.get("name") or "", "arguments": ""}}
                self.calls.append(same)
            args = fn.get("arguments")
            if isinstance(args, dict):
                same["function"]["arguments"] = args
            elif isinstance(args, str):
                prev = same["function"]["arguments"]
                same["function"]["arguments"] = (prev if isinstance(prev, str) else "") + args

    def tool_calls(self) -> list:
        return [{k: v for k, v in c.items() if k != "_index"} for c in self.calls]


def _read_chunk(obj: dict, rnd: _Round, on_text: Callable[[str], None]) -> None:
    if not isinstance(obj, dict):
        return
    if obj.get("error"):
        err = obj["error"]
        msg = err.get("message") if isinstance(err, dict) else err
        raise UpstreamError(f"The local model stopped with an error: {msg}")
    rnd.id = rnd.id or str(obj.get("id") or "")
    rnd.created = rnd.created or int(obj.get("created") or 0)
    choice = (obj.get("choices") or [{}])[0] or {}
    delta = choice.get("delta") or choice.get("message") or {}
    text = delta.get("content")
    if isinstance(text, str) and text:
        on_text(text)
    if delta.get("tool_calls"):
        rnd.add_calls(delta["tool_calls"])
    if choice.get("finish_reason"):
        rnd.finish = str(choice["finish_reason"])


def _read_stream(upstream, rnd: _Round, on_text: Callable[[str], None],
                 out: "_Out") -> None:
    """Reads one streamed round from Ollama, line by line, until it ends.

    `read1` where the response has it: it returns what has arrived, where
    `read(1024)` on a chunked response waits until a whole 1,024 bytes have
    come - several tokens at a time instead of one."""
    reader = getattr(upstream, "read1", None) or upstream.read
    buf = b""
    while True:
        if out.gone:
            raise ClientGone()
        data = reader(1024)
        if not data:
            break
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            _read_line(line, rnd, on_text)
            if rnd.ended:
                return
    if buf.strip():
        _read_line(buf, rnd, on_text)


def _read_line(raw: bytes, rnd: _Round, on_text: Callable[[str], None]) -> None:
    line = raw.strip()
    if not line or line.startswith(b":"):
        return
    if line[:5].lower() == b"data:":
        line = line[5:].strip()
    elif re.match(rb"^(event|id|retry):", line, re.I):
        return
    if line == b"[DONE]":
        rnd.ended = True
        return
    try:
        obj = json.loads(line.decode("utf-8", "replace"))
    except ValueError:
        return
    _read_chunk(obj, rnd, on_text)


def run_local_turn(messages: list, model: str, *, ollama_url: str,
                   stream_out: Callable[[bytes], None],
                   enabled_tools: Optional[set] = None,
                   announce: Optional[Callable[[str], None]] = None,
                   post: Optional[Callable[[str, dict], dict]] = None,
                   gate_check: Optional[Callable[[str, dict, str], object]] = None,
                   open_stream: Optional[Callable[[str, dict], object]] = None,
                   max_rounds: int = 6,
                   record_chain: Optional[Callable[[list], None]] = None,
                   on_step: Optional[Callable[[dict], None]] = None,
                   stream: bool = True,
                   request: Optional[dict] = None,
                   abort: Optional[Callable[[object], None]] = None,
                   context_length: Optional[int] = None,
                   keepalive_seconds: float = KEEPALIVE_SECONDS,
                   status_delay: float = STATUS_DELAY_SECONDS) -> dict:
    """One local chat turn, start to finish: asks the model, runs any tool it
    asks for through the gate, and writes the answer to `stream_out` as it is
    written - in Ollama's own format (see "What goes down the wire" above).

    Every round is ONE streamed request. Words go to the app as they arrive;
    tool calls are collected from the same stream. A round that asks for no
    tool IS the answer - it is not asked for a second time. (It used to be:
    each round was generated whole, unseen, then thrown away and generated
    again as a stream - silence, and then a different answer.)

    `stream` is what the app asked for. True: Ollama's SSE lines. False: one
    `chat.completion` JSON body at the end.

    `request` is the app's request body; `temperature`, `top_p` and
    `max_tokens` are taken from it (max_tokens defaults to
    DEFAULT_MAX_TOKENS, so every window gets the same length of answer).

    `enabled_tools` is the set of tool names to offer - see offered_tools().
    Empty, or none of them real: the model gets no `tools` at all.

    Each tool call is gated through jarvis_gate.check() BEFORE it runs -
    approved, denied or timed out all become one message fed back to the
    model, never a bare exception. While the gate waits, the app is sent
    keepalives and `: jarvis-status approval`. If the app has gone by the
    time the gate answers, the tool is NOT run and the turn stops: nobody is
    there to read what it would do.

    `abort(upstream)` is called on a request to Ollama that is being given up
    on (the app went away), so Ollama stops generating; the default closes
    it. `post` is an older, non-streaming way to make each round (a whole
    response dict back) that some tests still use.

    Ollama failing is reported to the app in plain words (plain_error), in
    the same framing, and this returns normally. Returns a small summary:
    {"finish_reason", "client_gone", "rounds"}.

    When the turn is over, `record_chain(steps)` gets the list of tools this
    turn asked for, as `{"tool", "ran", "ok", "outcome"}` dicts in order.
    Omitted, it is `_record_chain` (jarvis_skill_discovery.py). A turn that
    used no tool records nothing, and a recorder that raises is ignored.

    `on_step(step)` is told each step as it happens - see _step_event.
    Omitted, it is `_publish_step`: the event bus, for Brain -> Live.
    """
    recorder = record_chain if record_chain is not None else _record_chain
    steps: list = []
    checker = gate_check or _gate_check
    streamer = open_stream or (lambda url, payload: _open_stream(url, payload))
    closer = abort or (lambda up: getattr(up, "close", lambda: None)())
    convo = list(messages)
    names = offered_tools(enabled_tools)
    tool_schemas = [TOOLS[n].schema() for n in names]
    sink = on_step if on_step is not None else _publish_step
    req = request or {}
    opts: dict = {}
    for key in ("temperature", "top_p"):
        if isinstance(req.get(key), (int, float)) and not isinstance(req.get(key), bool):
            opts[key] = req[key]
    max_tokens = req.get("max_tokens")
    opts["max_tokens"] = (int(max_tokens) if isinstance(max_tokens, int)
                          and not isinstance(max_tokens, bool) and max_tokens > 0
                          else DEFAULT_MAX_TOKENS)
    url = f"{ollama_url}/v1/chat/completions"

    out = _Out(stream_out, sse=bool(stream))
    stop_beat = threading.Event()
    beat = threading.Thread(target=_heartbeat, name="jarvis-keepalive", daemon=True,
                            args=(out, stop_beat, keepalive_seconds, status_delay))
    beat.start()

    answer: list = []
    said = {"any": False, "gap": False}
    cid = f"chatcmpl-jarvis-{int(time.time() * 1000)}"
    created = int(time.time())
    finish: Optional[str] = None
    rounds = 0

    def say_step(phase: str, tool: Optional[str] = None, **kw) -> None:
        try:
            sink(_step_event(phase, tool, **kw))
        except Exception:
            pass

    def emit(text: str) -> None:
        if not text:
            return
        if said["gap"] and said["any"]:
            text = "\n\n" + text
        said["gap"] = False
        said["any"] = True
        answer.append(text)
        if out.sse and not out.send(_sse(_chunk(cid, created, model, {"content": text}))):
            raise ClientGone()

    def budget() -> int:
        n_ctx = context_length or _context_length(ollama_url, model)
        return max(512, n_ctx - opts["max_tokens"] - _TEMPLATE_TOKENS
                   - estimate_tokens(tool_schemas))

    def one_round(offer_tools: bool) -> _Round:
        global _reasoning_field_refused
        rnd = _Round()
        body = {"model": model, "messages": fit_messages(convo, budget()),
                "stream": True, **opts}
        if not _reasoning_field_refused:
            body.update(REASONING_OFF)
        if offer_tools and tool_schemas:
            body["tools"] = tool_schemas
        stripper = _ThinkStripper()
        first = {"text": True}

        def on_text(piece: str) -> None:
            clean = stripper.feed(piece)
            if clean:
                # Kept per round too: a round that then asks for a tool goes
                # back to the model with the words it wrote before asking.
                rnd.text.append(clean)
                if first["text"]:
                    first["text"] = False
                    out.set_status(None)
                    say_step("answer")
                emit(clean)

        if post is not None:
            whole = dict(body, stream=False)
            resp = post(url, whole)
            _read_chunk(resp, rnd, on_text)
            rnd.ended = True
        else:
            for attempt in (1, 2):
                try:
                    upstream = streamer(url, body)
                    break
                except urllib.error.HTTPError as exc:
                    raw = ""
                    try:
                        raw = exc.read().decode("utf-8", "replace")
                    except Exception:
                        pass
                    said_text = _ollama_error_text(raw).lower()
                    if (attempt == 1 and exc.code == 400 and "reasoning_effort" in body
                            and ("reason" in said_text or "think" in said_text)):
                        # An Ollama that does not know "none" yet. Once per
                        # process: it will not learn it before a restart.
                        _reasoning_field_refused = True
                        body.pop("reasoning_effort", None)
                        continue
                    raise UpstreamError(plain_error(exc, model, said=raw)) from exc
                except (urllib.error.URLError, OSError) as exc:
                    raise UpstreamError(plain_error(exc, model)) from exc
            try:
                with upstream:
                    _read_stream(upstream, rnd, on_text, out)
            except ClientGone:
                try:
                    closer(upstream)
                except Exception:
                    pass
                raise
            except (socket.timeout, TimeoutError) as exc:
                raise UpstreamError(plain_error(exc, model)) from exc
            except (http.client.HTTPException, OSError) as exc:
                # Ollama stopped half way through (it crashed, or was
                # restarted). Not a bug here, and not the app leaving - that
                # is ClientGone, above.
                raise UpstreamError(
                    "The local model stopped in the middle of the answer. Try "
                    "again; if it keeps happening, restart Ollama.") from exc
        tail = stripper.flush()
        if tail:
            rnd.text.append(tail)
            if first["text"]:
                first["text"] = False
                say_step("answer")
            emit(tail)
        return rnd

    def fail(message: str) -> None:
        if out.sse:
            out.send(_sse({"error": {"message": message, "type": "jarvis"}}))
        else:
            out.send(json.dumps({"error": message}, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8") + b"\n")

    try:
        last: Optional[_Round] = None
        for _round in range(max_rounds + 1):
            final = _round == max_rounds
            if final:
                convo.append({"role": "system",
                              "content": "Too many tool calls in a row; answer with "
                                         "what you have rather than trying again."})
            rounds += 1
            say_step("model", round_no=_round + 1)
            out.set_status("thinking")
            last = one_round(offer_tools=not final)
            calls = last.tool_calls()
            if final or not calls:
                break
            text = "".join(last.text)
            convo.append({"role": "assistant", "content": text,
                          "tool_calls": [dict(c, function=dict(c["function"]))
                                         for c in calls]})
            said["gap"] = True
            for call in calls:
                if out.gone:
                    raise ClientGone()
                _one_call(call, names, convo, steps, checker, announce, out, say_step)
        finish = (last.finish if last else None) or ("stop" if last and last.ended else None)
        if finish == "tool_calls":
            # The last round asked for a tool anyway, after tools were taken
            # away (max_rounds). Nothing ran; to the app the answer is over.
            finish = "stop"
        if out.sse:
            if last is not None and (last.ended or last.finish):
                out.send(_sse(_chunk(cid, created, model, {}, finish or "stop")))
                out.send(_sse("[DONE]"))
        else:
            out.send(json.dumps({
                "id": cid, "object": "chat.completion", "created": created,
                "model": model, "system_fingerprint": "fp_ollama",
                "choices": [{"index": 0,
                             "message": {"role": "assistant", "content": "".join(answer)},
                             "finish_reason": finish}],
            }, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
    except ClientGone:
        pass
    except UpstreamError as exc:
        fail(str(exc))
    finally:
        stop_beat.set()
        beat.join(timeout=2)
        # After the answer, so counting can never delay it, and in a
        # `finally` because the tools above ran whether or not the answer
        # made it to the client. Only the tools are recorded - see
        # _record_chain. A failing recorder must not replace a real error
        # from the stream, or turn a delivered answer into a failed turn.
        if steps:
            try:
                recorder(steps)
            except Exception:
                pass
    return {"finish_reason": finish, "client_gone": out.gone, "rounds": rounds}


def _one_call(call: dict, names: list, convo: list, steps: list, checker,
              announce, out: "_Out", say_step) -> None:
    """One tool call the model asked for: gate it, run it if allowed, and put
    the result in `convo` for the model to read."""
    fn = (call.get("function") or {})
    name = fn.get("name", "")
    raw_args = fn.get("arguments")
    try:
        # Some OpenAI-compatible backends hand back `arguments` already
        # parsed into an object rather than a JSON string - json.loads() on a
        # dict raises TypeError, not JSONDecodeError.
        args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
    except (json.JSONDecodeError, TypeError):
        args = {}
    if not isinstance(args, dict):
        # `arguments` can be valid JSON and still not be an object - "123"
        # parses to the int 123. Every tool calls args.get(...).
        args = {}
    tool = TOOLS.get(name) if name in names else None
    if tool is None:
        say_step("tool_refused", name)
        result = {"ok": False, "error": f"no such tool: {name!r}"}
        convo.append({"role": "tool", "tool_call_id": call.get("id", ""),
                      "content": _tool_content(result)})
        return
    lookup_name = tool.gate_lookup_name(args) if tool.gate_lookup_name else name
    action_name = lookup_name
    try:
        import jarvis_gate
        action_name, _ = jarvis_gate.action_for_tool(lookup_name, args)
    except Exception:
        pass
    # prepare() inside a try, like execute() below: a prepare-time raise - a
    # tool validating its own arguments, e.g. {"days_ahead": "seven"} - comes
    # back as a tool RESULT the model can read and retry from.
    try:
        state, plan_text = tool.prepare(args)
    except Exception as exc:
        convo.append({"role": "tool",
                      "tool_call_id": call.get("id", ""),
                      "content": _tool_content(
                          {"ok": False,
                           "error": f"{name} could not accept those "
                                    f"arguments: {type(exc).__name__}: {exc}"})})
        steps.append({"tool": name, "ran": False, "ok": False, "outcome": "unknown"})
        say_step("tool_finished", name, ok=False)
        return
    if _card_would_be_cut(name, action_name, plan_text):
        # Refused BEFORE a card is raised - see _card_would_be_cut.
        convo.append({"role": "tool",
                      "tool_call_id": call.get("id", ""),
                      "content": _tool_content(
                          {"ok": False,
                           "error": (f"refused: the plan for {name} is too long "
                                     f"to show in full on one approval card, so "
                                     f"nobody was asked and nothing ran. Make a "
                                     f"shorter plan - fewer steps, or split the "
                                     f"job into several smaller ones.")})})
        steps.append({"tool": name, "ran": False, "ok": False, "outcome": "refused"})
        say_step("tool_refused", name)
        return
    # The gate may wait minutes for a person. Say so to the app (after a
    # moment, so a tool the gate lets straight through never flashes it).
    out.set_status("approval")
    verdict = checker(action_name, {"text": plan_text},
                      f"tool {name} {json.dumps(args, ensure_ascii=False)[:1500]}")
    out.set_status("thinking")
    # What the GATE said, never what the model said: the outcome is read off
    # the verdict (gate-outcome.patch), and a verdict without one is recorded
    # as "unknown" rather than guessed at.
    step = {"tool": name, "ran": False, "ok": False,
            "outcome": str(getattr(verdict, "outcome", None) or "unknown")}
    steps.append(step)
    tc = _task_control()
    # A note the owner attached to THIS card before answering it
    # (POST /api/pending/<id>/amend). It goes to the model with the answer -
    # approved or not - and changes nothing about what was approved. Taken
    # once, so it is never repeated.
    card_note = None
    if tc is not None:
        try:
            card_note = tc.take_amend(getattr(verdict, "request_id", None))
        except Exception:
            card_note = None
    if not getattr(verdict, "allowed", False):
        say_step("tool_refused", name)
        result = {"ok": False,
                  "error": f"refused: {getattr(verdict, 'reason', 'not approved')}"}
    elif name in NEEDS_A_PERSON and not _a_person_said_yes(verdict):
        # Allowed, but nobody was asked. See NEEDS_A_PERSON.
        say_step("tool_refused", name)
        vtier = getattr(verdict, "tier", None) or "unknown"
        # The gate's own name for the action - the key that
        # [autonomy.tiers] uses - rather than the lookup name.
        vaction = getattr(verdict, "action", None) or action_name
        result = {"ok": False,
                  "error": (f"refused: {name} {NEEDS_A_PERSON[name]}, so it "
                            f"only runs after the owner approves it on a "
                            f"card - but the approval gate let it through "
                            f"at tier {vtier!r} without asking anyone. "
                            f"Nothing was run. To use it, set "
                            f"{vaction} to \"ask\" in "
                            f"jarvis-framework.toml's [autonomy.tiers].")}
    elif out.gone:
        # Approved - but the app that asked has gone, so nobody would see
        # what it did or the answer that followed. Not run; the owner is told
        # on the event bus, where they still are.
        say_step("tool_refused", name)
        if announce:
            try:
                announce(f"Did not run {name}: the chat that asked for it was closed.")
            except Exception:
                pass
        raise ClientGone()
    else:
        say_step("tool_started", name)
        out.set_status("working")
        if announce:
            announce(f"Using {name}...")
        kwargs = {"announce": announce} if tool.needs_announce else {}
        # A multi-step plan: register it so Pause/Stop can reach it, and hand
        # run() the checkpoint it reads before every step. The id is the
        # approval card's own when there was one, so "this task" and "that
        # card" are the same thing.
        task_id = None
        if tc is not None and name in _TASK_MODULES:
            task_id = getattr(verdict, "request_id", None) or tc.new_task_id()
            tc.begin(task_id, name)
            kwargs["checkpoint"] = (lambda tid=task_id: tc.checkpoint(tid))
        step["ran"] = True
        try:
            result = tool.execute(args, state, **kwargs)
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            if task_id is not None:
                tc.end(task_id)
            out.set_status("thinking")
        if task_id is not None and isinstance(result, dict):
            result = _after_task(tc, task_id, name, action_name, state, result)
        step["ok"] = isinstance(result, dict) and result.get("ok") is True
        say_step("tool_finished", name, ok=step["ok"])
    if card_note and isinstance(result, dict):
        result = dict(result)
        result["owner_note"] = card_note
    convo.append({"role": "tool", "tool_call_id": call.get("id", ""),
                  "content": _tool_content(result)})
