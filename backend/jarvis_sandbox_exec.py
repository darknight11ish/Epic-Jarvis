"""jarvis_sandbox_exec.py - a hermetic local Python sandbox for small data and maths jobs.

WHY THIS EXISTS

A small local model may one day write a small Python script for the owner: add up
a CSV, take an average, work out a percentage. That script is UNTRUSTED TEXT.
It must not reach the network, read a file the caller did not hand it, find a
secret, start another program, print without limit, or keep running until the
owner notices. This module is the one place that runs such a script.

    from jarvis_sandbox_exec import run_data_script
    result = run_data_script(code, read_only_files={"scores": r"C:\\tmp\\scores.csv"})

THE ONE FUNCTION

`run_data_script(code, read_only_files=None) -> dict` ALWAYS returns the same
four keys, and never raises for a bad script:

    {"ok": bool,          # the script ran to the end without an error
     "stdout": str,       # what the script printed; partial output is kept on error
     "figures": list,     # [{"name": str, "data": <JSON value>}, ...], in call order
     "error": str,        # "" when ok; otherwise one plain-English sentence
     "memory_cap_bytes": int | None,   # the memory cap in force for this run
     "memory_cap_enforced": bool}      # True ONLY when that cap is really in force

`read_only_files` is `name -> path`, or None. The names are the keys a script
may pass to its `read_csv(name)` helper; a path is never a name, so a script
cannot ask for a file the caller did not list. A mapping entry that is not an
existing regular file, is bigger than `MAX_INPUT_BYTES`, has a name longer than
64 characters, or is not text is refused BEFORE anything runs.

THE THREE LAYERS (each is checked by backend/test_sandbox_exec.py)

 1. AN AST ALLOWLIST. The code is parsed with `ast.parse`; it is never executed
    in this process. A script may import only `math, statistics, decimal,
    fractions, datetime, collections, itertools, re, json, csv` (exactly those
    top-level names). Every other import is refused, with the network, program,
    filesystem and code-loading ones named plainly: `os, sys, subprocess,
    socket, urllib, http, pathlib, shutil, ctypes` and their neighbours. It may
    not call `eval`, `exec`, `compile`, `open`, `input`, `getattr`, `setattr`,
    `delattr`, `globals`, `locals`, `vars`, `dir`, `breakpoint`, `help`,
    `exit`, `quit` or `__import__`; it may not reach ANY dunder attribute or
    dunder name (`__class__`, `__subclasses__`, `__globals__`, the lot); it may
    not define a class or use async. The refusal is a plain-English sentence
    and NOTHING IS STARTED: `_POPEN` is not called for a refused script. That
    last point is a test, not a promise.

    THE ALLOCATION-BOMB GUARD runs in the SAME cross-platform pass, before any
    `Popen`, on Linux CI and Windows alike (memory cannot wait for the child's
    own limits): a power with a folded exponent over `AST_POW_MAX_EXPONENT`
    (`2 ** 100000`, `2 ** 2 ** 20`), a left shift over `AST_LSHIFT_MAX`
    (`1 << 100000`), a repeated sequence with a folded constant factor over
    `AST_REPEAT_MAX` (`"x" * 5_000_000`, `[0] * (10 ** 9)`, chained
    `[0] * 1000 * 1000 * 1000`), or a `range(...)` with more than
    `AST_RANGE_MAX` steps. Each has ONE stable reason code in
    `AST_BOMB_REASONS` (`ast_memory_bomb_pow`, `_lshift`, `_repeat`, `_range`);
    `validate_sandbox_ast(code)` returns that code beside the plain sentence.

 2. A SCRUBBED CHILD PROCESS. A script that passes layer 1 runs in a SEPARATE
    `python -B -I` process: `-B` writes no bytecode, `-I` keeps the current
    folder and the user's site-packages off `sys.path` and ignores the
    `PYTHON*` variables. Its environment is `jarvis_child_env.inherited()` -
    Jarvis's own allow-list of what a child may inherit, which never carries a
    token, a key or a password - filtered once more here for belt and braces.
    The child is also handed only a small set of built-ins (no `open`, no
    `eval`, no `type`, no `object`), so a bug in layer 1 does not become a hole.
    The script is sent over the child's standard input as JSON; it is never
    written to a file and never put on a command line.
    A HARD WALL CLOCK: `TIMEOUT_S` (5.0 seconds). A HARD OUTPUT CAP:
    `OUTPUT_CAP` (64 * 1024 bytes) of the child's standard output. The child is
    KILLED and a clean refusal is returned on either. The outcome is not read
    from the exit status alone; see layer 3.

    A HARD MEMORY CAP where the operating system has one. On Windows the child
    is put in a Win32 Job Object BEFORE the script's payload is sent to it, with
    `MAX_MEMORY_BYTES` (256 MiB, `JobObjectExtendedLimitInformation`, the
    process-memory limit) and `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; a script
    that tries to allocate past it fails inside the child, and the job handle is
    closed in a `finally`. On Linux and every other non-Windows system this
    module cannot set a memory limit (Python has no `RLIMIT_AS` equivalent it
    may set safely for another process), so it says so: the result carries
    `"memory_cap_bytes": None, "memory_cap_enforced": False`. A cap is NEVER
    claimed when it is not really in force - the two honesty keys are the
    contract, and a failed attach on Windows also reports `None`/`False`.

 3. A VERIFIED RESULT ONLY. The trusted child wrapper - not the script - prints
    one nonce marker followed by a JSON envelope holding `ok`, `figures` and
    `error`. The nonce is generated by this module for this one run, handed to
    the wrapper inside the stdin payload, and matched in the output, so a
    script cannot forge it: the script has no `sys`, no `os`, no `open` and no
    dunder access, and it never sees the payload. The caller is returned
    `ok`, `stdout`, `figures`, `error` and the two memory-cap honesty keys; the
    child's own stderr is discarded, and anything without a verified envelope
    is a refusal, not a partial pass.

WHAT A SCRIPT'S WORLD LOOKS LIKE

  * Built-ins it has: the pure functions a small calculation needs (`abs`,
    `all`, `any`, `bool`, `bytes`, `chr`, `complex`, `dict`, `divmod`,
    `enumerate`, `filter`, `float`, `format`, `frozenset`, `hash`, `hex`,
    `int`, `isinstance`, `issubclass`, `iter`, `len`, `list`, `map`, `max`,
    `min`, `next`, `oct`, `ord`, `pow`, `print`, `range`, `repr`, `reversed`,
    `round`, `set`, `slice`, `sorted`, `str`, `sum`, `tuple`, `zip`), the usual
    exception classes, and the two helpers below.
  * `read_csv(name)` returns the text of a caller-supplied file, decoded as
    UTF-8 with a BOM stripped (decoded errors are replaced, never a crash).
    `name` must be a key of `read_only_files`; the file may be at most
    `MAX_INPUT_BYTES` (1 MiB). `import csv` plus
    `csv.reader(read_csv("scores").splitlines())` is the intended shape - `io`
    is not importable.
  * `figure(name, data)` records one chart for the caller. `name` is 1-80
    characters of plain text, `data` must be JSON-serialisable (lists, dicts
    with text keys, numbers, text, booleans, None; no NaN/infinity), one
    figure's JSON is at most 8192 bytes, and at most 16 figures are allowed
    from one script. The recorded data is re-readable JSON: the child parses
    its own encoding back before recording it, so a cut-off or invalid value
    becomes a plain-English error, never a half-written chart.
  * A script is at most `MAX_SCRIPT_BYTES` (100 KiB). A longer one is refused
    before parsing, so this process does no unbounded work on untrusted text.

WHAT THIS MODULE DOES NOT DO, SAID PLAINLY

  * It does not decide WHETHER a script should run. There is no route, no tool,
    no approval card and no caller yet: an integration that offers this to the
    model must put its own gate (the one permission model, `jarvis_gate`) in
    front of it. This module only makes the running safe.
  * It is not a kernel sandbox. It is an allow-list plus a separate, scrubbed
    interpreter, which is the right shape for a local-first PC but is not
    SELinux or a container. On Windows the job object bounds the child's RAM;
    on Linux nothing here can, and the result says `memory_cap_enforced: False`
    rather than pretending. The wall clock bounds time and output on every OS.
  * The allocation-bomb guard is a static, conservative rule: it refuses the
    shapes a script uses to ask for a huge object in one expression, not every
    way to build one slowly. The 64 KiB output cap, the 5-second wall clock and
    (on Windows) the 256 MiB job object are what bound the rest.
  * Killing the child needs this process to be alive to do it. If the whole
    backend is killed mid-run, the child is a short-lived orphan; nothing here
    survives longer than the script's own 5-second budget in practice, and the
    child starts no children of its own.
  * A regular expression is still a program: `re` is allowed, so a pathological
    pattern can burn the 5-second budget and be killed. It cannot escape.
  * Two files, one rule: this module and `jarvis-backend/jarvis_sandbox_exec.py`
    are kept byte-identical, like every shipped module.

TESTS: `backend/test_sandbox_exec.py` proves each layer by driving it: the real
refusals, a real CSV, real `statistics`/`decimal`, a real timeout, a real
output flood, every allocation-bomb shape and its closed-world reason code, a
refused script that starts no process at all, a stubbed child that cannot forge
a result, the Windows job-object path behind an injectable seam (and the honest
`None`/`False` fallback), and that `jarvis_agent.py` really dispatches its tool
to `run_data_script`.

Standard library only. It starts one `python -B -I` child and nothing else.
"""
from __future__ import annotations

import ast
import json
import os
import secrets
import subprocess
import sys
import threading
import time

__all__ = ("run_data_script", "validate_sandbox_ast", "TIMEOUT_S", "OUTPUT_CAP",
           "MAX_INPUT_BYTES", "MAX_SCRIPT_BYTES", "MAX_MEMORY_BYTES",
           "ALLOWED_IMPORTS", "AST_BOMB_REASONS")

#: The hard wall clock for one script, in seconds. Layer 2.
TIMEOUT_S = 5.0

#: The hard cap on the child's standard output, in bytes (the verified JSON
#: envelope rides in the same stream and is counted). Layer 2.
OUTPUT_CAP = 64 * 1024

#: The most one caller-supplied read-only file may hold, in bytes.
MAX_INPUT_BYTES = 1024 * 1024

#: The longest script accepted, in bytes. Checked before `ast.parse`.
MAX_SCRIPT_BYTES = 100 * 1024

#: The memory cap a child gets on Windows, in bytes: 256 MiB. Layer 2.
MAX_MEMORY_BYTES = 256 * 1024 * 1024

#: The allocation-bomb guard's bound on a power's folded exponent.
AST_POW_MAX_EXPONENT = 10_000
#: ... on a left shift's folded count.
AST_LSHIFT_MAX = 10_000
#: ... on a repeated sequence's folded constant factor (one `*` chain's product).
AST_REPEAT_MAX = 1_000_000
#: ... on a `range(...)`'s folded number of steps.
AST_RANGE_MAX = 1_000_000

#: The CLOSED set of reason codes the allocation-bomb guard may return. No
#: other code exists, and nothing outside this guard sets one: a test feeds
#: every bomb shape it knows and asserts this set is exactly what came back.
AST_BOMB_REASONS = frozenset((
    "ast_memory_bomb_pow",
    "ast_memory_bomb_lshift",
    "ast_memory_bomb_repeat",
    "ast_memory_bomb_range",
))

#: The plain-English sentence each bomb reason carries to the owner.
_BOMB_WORDS = {
    "ast_memory_bomb_pow":
        "the script asks for a power far too big to work out safely "
        "(2 ** 100000 and the like)",
    "ast_memory_bomb_lshift":
        "the script shifts a number far too far to work out safely "
        "(1 << 100000 and the like)",
    "ast_memory_bomb_repeat":
        "the script repeats something far too many times in one step "
        "(\"x\" * 5000000 and the like)",
    "ast_memory_bomb_range":
        "the script counts through a range with far too many steps in one go",
}

#: The ONLY modules a script may import. Exact top-level names: a submodule
#: such as `collections.abc` is not on this list and is refused by layer 1.
ALLOWED_IMPORTS = frozenset((
    "math", "statistics", "decimal", "fractions", "datetime",
    "collections", "itertools", "re", "json", "csv",
))

#: Imports refused BY NAME, each with the plain reason the owner reads. Any
#: other name not in ALLOWED_IMPORTS gets the generic "allows only" sentence.
_DENIED_IMPORTS = {
    # The machine and the interpreter
    "os": "a program cannot reach the machine or its settings",
    "sys": "a program cannot reach the interpreter's own controls",
    "platform": "a program cannot describe the machine",
    "sysconfig": "a program cannot describe the machine",
    # Other programs
    "subprocess": "the sandbox never starts another program",
    "multiprocessing": "the sandbox never starts another program",
    "pty": "the sandbox never starts another program",
    # The network
    "socket": "the sandbox has no network",
    "urllib": "the sandbox has no network",
    "http": "the sandbox has no network",
    "ssl": "the sandbox has no network",
    "ftplib": "the sandbox has no network",
    "smtplib": "the sandbox has no network",
    "poplib": "the sandbox has no network",
    "imaplib": "the sandbox has no network",
    "telnetlib": "the sandbox has no network",
    "xmlrpc": "the sandbox has no network",
    "webbrowser": "the sandbox has no network and starts no programs",
    # The filesystem
    "pathlib": "the sandbox has no filesystem access",
    "shutil": "the sandbox has no filesystem access",
    "tempfile": "the sandbox has no filesystem access",
    "glob": "the sandbox has no filesystem access",
    "io": "the sandbox has no filesystem access",
    "mmap": "the sandbox has no filesystem access",
    "fcntl": "the sandbox has no filesystem access",
    # Loading code from the machine
    "ctypes": "the sandbox does not load code from the machine",
    "cffi": "the sandbox does not load code from the machine",
    "importlib": "the sandbox controls its own imports and never hands over the loader",
    "site": "the sandbox controls its own imports and never hands over the loader",
    "builtins": "the sandbox hands a program only the few built-ins it needs",
    # Other escape machinery
    "pickle": "the sandbox never rebuilds objects from bytes",
    "marshal": "the sandbox never rebuilds code from bytes",
    "runpy": "the sandbox does not run other code",
    "code": "the sandbox does not run other code",
    "codeop": "the sandbox does not run other code",
    "gc": "the sandbox does not expose the garbage collector",
    "inspect": "the sandbox does not let a program inspect itself",
    "signal": "the sandbox does not let a program reach signals",
    "resource": "the sandbox does not let a program change its own limits",
    "threading": "the sandbox never starts another thread",
    "asyncio": "the sandbox has no event loop and no network",
}

#: Names a script may not use, wherever they appear. `open` is here because a
#: caller-supplied file can only be read through `read_csv(name)`.
_DENIED_NAMES = {
    "eval": "running text as code is not allowed in the sandbox",
    "exec": "running text as code is not allowed in the sandbox",
    "compile": "building code from text is not allowed in the sandbox",
    "open": ("opening files is not allowed in the sandbox - use read_csv(name) "
             "with a file the caller gave the program"),
    "input": "the sandbox has no keyboard input",
    "breakpoint": "the sandbox has no debugger",
    "help": "the sandbox has no interactive help",
    "exit": "the sandbox does not let a program stop the interpreter",
    "quit": "the sandbox does not let a program stop the interpreter",
    "getattr": "looking an attribute up by its text name is not allowed in the sandbox",
    "setattr": "setting an attribute by its text name is not allowed in the sandbox",
    "delattr": "removing an attribute by its text name is not allowed in the sandbox",
    "globals": "reaching into the program's own globals is not allowed in the sandbox",
    "locals": "reaching into the program's own locals is not allowed in the sandbox",
    "vars": "reaching a program's own names is not allowed in the sandbox",
    "dir": "listing a program's own names is not allowed in the sandbox",
}

#: Words that make an inherited environment name look like a secret. The same
#: words `jarvis_child_env` already uses; belt and braces here too.
_SECRET_WORDS = ("TOKEN", "KEY", "PASSWORD", "PASSWD", "SECRET", "CREDENTIAL", "AUTH")

#: The names the fallback below copies when `jarvis_child_env` is not importable.
#: Deliberately a short allow-list, never a copy of this process's environment.
_FALLBACK_ENV = (
    "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "COMSPEC",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432",
    "OS", "SYSTEMDRIVE", "PROGRAMDATA", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "HOMEDRIVE", "HOMEPATH", "HOME", "LANG",
)

try:                                      # the shipped helper, beside this file
    from jarvis_child_env import inherited as _inherited_env
except Exception:                          # pragma: no cover - belt and braces
    def _inherited_env() -> dict:
        """A minimal safe environment, used only if jarvis_child_env is absent."""
        return {k: v for k, v in os.environ.items() if k.upper() in _FALLBACK_ENV}


def _is_dunder(name) -> bool:
    """A name or attribute that starts with `__`: the machinery layer 1 bans."""
    return isinstance(name, str) and name.startswith("__")


def _import_refusal(module) -> str:
    """The plain refusal for importing `module`, or "" when it is allowed."""
    name = str(module)
    if name in ALLOWED_IMPORTS:
        return ""
    root = name.split(".")[0]
    if root in _DENIED_IMPORTS:
        return (f"Not run: importing {name!r} is not allowed - "
                f"{_DENIED_IMPORTS[root]}.")
    return ("Not run: importing " + repr(name) + " is not allowed. The sandbox "
            "allows only: " + ", ".join(sorted(ALLOWED_IMPORTS)) + ".")


def _name_refusal(name: str) -> str:
    """The plain refusal for using a dangerous built-in name, or ""."""
    why = _DENIED_NAMES.get(name)
    return f"Not run: {name!r} is not allowed - {why}." if why else ""


def _fold_int(node, cap: int):
    """`node`'s integer value when it is a harmless constant expression, else None.

    SATURATING, on purpose: a true value above `cap` comes back as `cap + 1`, so
    a comparison against a bound is right without ever building the number the
    guard exists to refuse. Only Constant, unary +/-, + - * ** and << are
    folded, with small iteration counts; anything else is None ("cannot tell
    statically"), never a guess.
    """
    limit = cap + 1

    def walk(n, depth):
        if depth > 40:
            return None
        if isinstance(n, ast.Constant):
            value = n.value
            if isinstance(value, bool) or not isinstance(value, int):
                return None
            return min(value, limit)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            value = walk(n.operand, depth + 1)
            if value is None:
                return None
            return -value if isinstance(n.op, ast.USub) else value
        if not isinstance(n, ast.BinOp):
            return None
        left = walk(n.left, depth + 1)
        right = walk(n.right, depth + 1)
        if left is None or right is None:
            return None
        if isinstance(n.op, ast.Add):
            return min(left + right, limit)
        if isinstance(n.op, ast.Sub):
            return max(min(left - right, limit), -limit)
        if isinstance(n.op, ast.Mult):
            return min(left * right, limit)
        if isinstance(n.op, ast.Pow):
            if right < 0:
                return None                       # a fractional result, not an int
            if right == 0:
                return 1
            if right == 1:
                return min(left, limit)
            if abs(left) > 10 ** 6 or right > 64:
                return limit
            value = 1
            for _ in range(right):
                value *= left
                if abs(value) > limit:
                    return limit
            return value
        if isinstance(n.op, ast.LShift):
            if right < 0 or right > 64 or left < 0:
                return None
            return min(left << right, limit)
        return None

    try:
        return walk(node, 0)
    except (RecursionError, MemoryError, OverflowError, ValueError):
        return None


def _mult_chain_product(node):
    """The saturated product of every foldable integer factor in a `*` chain.

    `[0] * 1000 * 1000 * 1000` is one expression of three nested `ast.Mult`
    nodes: no single factor is over the bound, but their product asks for a
    thousand times a thousand times a thousand items. Walking the whole chain,
    rather than each node's own two operands, is what catches it.
    """
    limit = AST_REPEAT_MAX + 1
    product = 1
    seen = False
    stack = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, ast.BinOp) and isinstance(item.op, ast.Mult):
            stack.append(item.left)
            stack.append(item.right)
            continue
        factor = _fold_int(item, AST_REPEAT_MAX)
        if factor is not None:
            seen = True
            product *= factor
            if product > limit:
                return limit
    return product if seen else None


def _range_steps(node):
    """The number of steps a builtin `range(...)` call would take, or None.

    Covers both shapes the guard exists for: `list(range(N))` and a list
    comprehension's `[... for _ in range(N)]`, because both contain the same
    `ast.Call`.
    """
    if not isinstance(node, ast.Call) or node.keywords:
        return None
    fn = node.func
    if not isinstance(fn, ast.Name) or fn.id != "range":
        return None
    if not 1 <= len(node.args) <= 3:
        return None
    values = [_fold_int(arg, AST_RANGE_MAX) for arg in node.args]
    if any(value is None for value in values):
        return None
    if len(values) == 1:
        start, stop, step = 0, values[0], 1
    elif len(values) == 2:
        start, stop, step = values[0], values[1], 1
    else:
        start, stop, step = values
    if step == 0:
        return None
    span = stop - start
    if step > 0:
        return max(0, (span + step - 1) // step)
    return max(0, (span + step + 1) // step)


def _bomb_reason(tree) -> str:
    """The allocation-bomb reason code for a parsed `tree`, or "".

    Before any child is started, on every platform: a huge `**`, a huge `<<`,
    a `*` chain asking for a huge number of items, or a `range` with a huge
    number of steps. Each maps to exactly one member of `AST_BOMB_REASONS`.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = _fold_int(node.right, AST_POW_MAX_EXPONENT)
            if exponent is not None and exponent > AST_POW_MAX_EXPONENT:
                return "ast_memory_bomb_pow"
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.LShift):
            count = _fold_int(node.right, AST_LSHIFT_MAX)
            if count is not None and count > AST_LSHIFT_MAX:
                return "ast_memory_bomb_lshift"
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            product = _mult_chain_product(node)
            if product is not None and product > AST_REPEAT_MAX:
                return "ast_memory_bomb_repeat"
        elif isinstance(node, ast.Call):
            steps = _range_steps(node)
            if steps is not None and steps > AST_RANGE_MAX:
                return "ast_memory_bomb_range"
    return ""


def validate_sandbox_ast(code: str) -> dict:
    """Layer 1: {"ok", "reason", "error"} for one untrusted script.

    `ok` is True when the code may run; otherwise `error` is one plain-English
    refusal and `reason` is "" (an ordinary refusal) or one member of the
    closed set `AST_BOMB_REASONS` (the allocation-bomb guard). `ast.parse` only
    builds a tree: the code is NEVER executed here, and a refused script
    starts no process.
    """
    verdict = {"ok": False, "reason": "", "error": ""}
    if not isinstance(code, str):
        verdict["error"] = "Not run: the script must be text, so the sandbox can read it."
        return verdict
    if len(code.encode("utf-8", "replace")) > MAX_SCRIPT_BYTES:
        verdict["error"] = (f"Not run: the script is bigger than the sandbox allows "
                            f"({MAX_SCRIPT_BYTES} bytes).")
        return verdict
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        verdict["error"] = (f"Not run: the script is not valid Python (line "
                            f"{exc.lineno}): {exc.msg}.")
        return verdict
    except (ValueError, TypeError, MemoryError) as exc:
        verdict["error"] = f"Not run: the script could not be read as Python ({exc})."
        return verdict
    reason = _bomb_reason(tree)
    if reason:
        verdict["reason"] = reason
        verdict["error"] = f"Not run: {_BOMB_WORDS[reason]}."
        return verdict
    for node in ast.walk(tree):
        why = ""
        if isinstance(node, ast.Import):
            for alias in node.names:
                why = _import_refusal(alias.name)
                if why:
                    break
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                why = "Not run: relative imports are not allowed in the sandbox."
            else:
                why = _import_refusal(node.module or "")
                if not why:
                    for alias in node.names:
                        if _is_dunder(alias.name):
                            why = (f"Not run: the special name {alias.name!r} is not "
                                   f"allowed in the sandbox.")
                            break
        elif isinstance(node, ast.Attribute):
            if _is_dunder(node.attr):
                why = (f"Not run: reaching the special name {node.attr!r} is not "
                       f"allowed in the sandbox.")
        elif isinstance(node, ast.Name):
            if _is_dunder(node.id):
                why = (f"Not run: the special name {node.id!r} is not allowed in "
                       f"the sandbox.")
            else:
                why = _name_refusal(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and _is_dunder(node.value) and node.value.endswith("__"):
            why = (f"Not run: the special name {node.value!r} is not allowed in "
                   f"the sandbox.")
        elif isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith,
                               ast.Await)):
            why = "Not run: async code is not supported in the sandbox."
        elif isinstance(node, ast.ClassDef):
            why = ("Not run: class definitions are not supported in the sandbox - "
                   "write plain functions and data.")
        if why:
            verdict["error"] = why
            return verdict
    verdict["ok"] = True
    return verdict


def _refusal(code: str) -> str:
    """The refusal sentence from `validate_sandbox_ast`: "" when it may run."""
    return validate_sandbox_ast(code)["error"]


def _prepare_files(read_only_files):
    """(name -> absolute path, "") or (None, plain refusal).

    The CALLER is the trust boundary for WHICH files exist; a script can only
    reach the names listed here. Each entry is checked before anything runs.
    """
    if read_only_files is None:
        return {}, ""
    if not isinstance(read_only_files, dict):
        return None, ("Not run: read_only_files must be a dictionary of "
                      "name -> path, or None.")
    out = {}
    for name, where in read_only_files.items():
        if not isinstance(name, str) or not name.strip():
            return None, ("Not run: every read-only file needs a plain-text "
                          "name (the key in read_only_files).")
        if len(name) > 64:
            return None, (f"Not run: the read-only file name {name!r} is longer "
                          f"than the sandbox allows (64 characters).")
        try:
            path = os.fspath(where)
        except TypeError:
            return None, (f"Not run: the path for the read-only file {name!r} "
                          f"must be text.")
        if not isinstance(path, str) or not path:
            return None, (f"Not run: the path for the read-only file {name!r} "
                          f"must be text.")
        if not os.path.isfile(path):
            return None, (f"Not run: the read-only file {name!r} is not a file "
                          f"that exists.")
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return None, (f"Not run: the read-only file {name!r} could not be "
                          f"read ({exc}).")
        if size > MAX_INPUT_BYTES:
            return None, (f"Not run: the read-only file {name!r} is bigger than "
                          f"the sandbox allows ({MAX_INPUT_BYTES} bytes).")
        out[name] = os.path.abspath(path)
    return out, ""


def _looks_secret(name: str) -> bool:
    up = name.upper()
    return any(word in up for word in _SECRET_WORDS)


def _child_env() -> dict:
    """The environment the child may inherit: jarvis_child_env's allow-list,
    filtered once more and never carrying a `PYTHON*` setting."""
    try:
        source = _inherited_env()
    except Exception:
        return {}
    env = {}
    for key, value in dict(source).items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        up = key.upper()
        if up.startswith("PYTHON") or _looks_secret(key):
            continue
        env[key] = value
    return env


# The child's trusted wrapper. The SCRIPT never sees this text or this process:
# it is the program that reads the stdin payload, builds the restricted world,
# runs the script, and prints the one nonce-marked result envelope. `__import__`
# is replaced with a wrapper around the real one that only admits ALLOWED_IMPORTS,
# and the built-ins dict is small on purpose (no open, no eval, no type/object).
_CHILD_SOURCE = r'''
import json
import sys


def _send(marker, result):
    sys.stdout.write(marker)
    sys.stdout.write(json.dumps(result, ensure_ascii=True, allow_nan=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        code = payload["code"]
        files = payload["files"]
        marker = payload["marker"]
        allowed = frozenset(payload["allowed"])
        max_input = int(payload["max_input"])
    except Exception:
        return 2
    try:
        # newline="\n": a pipe would otherwise translate every "\n" to "\r\n"
        # on Windows, so the same script would give a caller different stdout
        # on the owner's PC and in CI. The sandbox always reports plain "\n".
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    except Exception:
        pass
    real_import = __import__

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = str(name).split(".")[0]
        if int(level) != 0 or root not in allowed:
            raise ImportError("importing " + repr(name) + " is not allowed in this sandbox")
        return real_import(name, globals, locals, fromlist, level)

    def read_csv(name):
        if not isinstance(name, str) or name not in files:
            raise ValueError("there is no file called " + repr(name) +
                             " for this program to read")
        with open(files[name], "rb") as handle:
            data = handle.read(max_input + 1)
        if len(data) > max_input:
            raise ValueError("the file " + repr(name) + " is bigger than the sandbox allows")
        return data.decode("utf-8-sig", errors="replace")

    figures = []

    def figure(name, data):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("a figure needs a plain-text name")
        if len(name) > 80:
            raise ValueError("a figure's name must be 80 characters or fewer")
        if len(figures) >= 16:
            raise ValueError("the sandbox allows at most 16 figures from one program")
        try:
            encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("the figure " + repr(name) + " cannot be shown: " + str(exc))
        if len(encoded) > 8192:
            raise ValueError("the figure " + repr(name) + " is too big to show")
        figures.append({"name": name, "data": json.loads(encoded)})

    allowed_builtins = {
        "abs": abs, "all": all, "any": any, "bool": bool, "bytes": bytes,
        "chr": chr, "complex": complex, "dict": dict, "divmod": divmod,
        "enumerate": enumerate, "filter": filter, "float": float,
        "format": format, "frozenset": frozenset, "hash": hash, "hex": hex,
        "int": int, "isinstance": isinstance, "issubclass": issubclass,
        "iter": iter, "len": len, "list": list, "map": map, "max": max,
        "min": min, "next": next, "oct": oct, "ord": ord, "pow": pow,
        "print": print, "range": range, "repr": repr, "reversed": reversed,
        "round": round, "set": set, "slice": slice, "sorted": sorted,
        "str": str, "sum": sum, "tuple": tuple, "zip": zip,
        "Exception": Exception, "ArithmeticError": ArithmeticError,
        "AssertionError": AssertionError, "AttributeError": AttributeError,
        "ImportError": ImportError, "IndexError": IndexError,
        "KeyError": KeyError, "NameError": NameError,
        "OverflowError": OverflowError, "RuntimeError": RuntimeError,
        "StopIteration": StopIteration, "TypeError": TypeError,
        "ValueError": ValueError, "ZeroDivisionError": ZeroDivisionError,
    }
    allowed_builtins["read_csv"] = read_csv
    allowed_builtins["figure"] = figure
    allowed_builtins["__import__"] = safe_import
    namespace = {"__builtins__": allowed_builtins, "__name__": "__main__"}
    try:
        exec(compile(code, "<jarvis sandbox>", "exec"), namespace)
        result = {"ok": True, "figures": figures, "error": ""}
    except BaseException as exc:
        message = "your program stopped with an error: " + type(exc).__name__
        detail = str(exc)
        if detail:
            message = message + ": " + detail
        result = {"ok": False, "figures": figures, "error": message}
    _send(marker, result)
    return 0


sys.exit(_main())
'''


#: The child-start call, kept in one place so a test can spy on it (and prove a
#: refused script starts nothing) without starting a process. Do NOT replace
#: this with a direct subprocess call elsewhere in this module.
_POPEN = subprocess.Popen


def _spawn(argv, env):
    """Start the child. Separate function so one call site owns the flags."""
    kwargs = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        # The child's own stderr is a side channel to nothing: it is thrown
        # away rather than returned, so a script cannot smuggle text out.
        "stderr": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if creationflags:
            kwargs["creationflags"] = creationflags
    return _POPEN(argv, **kwargs)


# --------------------------------------------------------------------------
#   The memory cap: a Win32 Job Object, or an honest "no cap on this OS"
# --------------------------------------------------------------------------
# The numbers are Win32's own (JobObjectExtendedLimitInformation = 9; the two
# flags share a bitfield). Nothing here is imported on Linux: ctypes and the
# wintypes names are loaded INSIDE the Windows function only, so the module
# still imports, and the honest fallback still runs, on a Linux CI runner.
_IS_WINDOWS = sys.platform == "win32"
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


#: The honest cap dict for a return where NO child ran. A copy is made per
#: result so one caller can never change what another sees.
_NO_CHILD_CAP = {"memory_cap_bytes": None, "memory_cap_enforced": False}


def _attach_job_limit(proc) -> bool:
    """Put `proc` in a Win32 Job Object capped at `MAX_MEMORY_BYTES`.

    True only when BOTH the limit was set and the process was assigned. Any
    failure returns False (the caller then reports the cap as NOT enforced); a
    half-made job is closed here, and a successful one is kept on the Popen
    object so `_close_job_limit` can close it after the child is reaped.

    WINDOWS ONLY. The suite replaces this function (never `sys.platform`) to
    prove the cap path on Linux and the failure path anywhere, so this body can
    be one plain sequence of Win32 calls.
    """
    import ctypes
    from ctypes import wintypes

    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimit),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return False
    info = _ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = (
        _JOB_OBJECT_LIMIT_PROCESS_MEMORY | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
    info.ProcessMemoryLimit = MAX_MEMORY_BYTES
    set_ok = bool(kernel32.SetInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
        ctypes.sizeof(info)))
    assigned = bool(set_ok) and bool(
        kernel32.AssignProcessToJobObject(job, int(proc._handle)))
    if not assigned:
        try:
            kernel32.CloseHandle(job)
        except Exception:
            pass
        return False
    proc._jarvis_job_handle = job
    return True


def _close_job_limit(proc) -> None:
    """Close the job handle `_attach_job_limit` kept, if there is one.

    KILL_ON_JOB_CLOSE means closing it also ends any child still inside it -
    belt to the `proc.kill()` the bounds already do."""
    handle = getattr(proc, "_jarvis_job_handle", None)
    if not handle:
        return
    try:
        import ctypes
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
    except Exception:
        pass
    finally:
        try:
            proc._jarvis_job_handle = None
        except Exception:
            pass


def _memory_cap_for(proc) -> dict:
    """{memory_cap_bytes, memory_cap_enforced} for the child `proc`.

    Non-Windows: (None, False) WITHOUT calling the attach function at all -
    never a claimed cap. Windows: the real job object, or (None, False) if it
    could not be set, because a cap that is not in force must not be reported
    as if it were."""
    if not _IS_WINDOWS:
        return {"memory_cap_bytes": None, "memory_cap_enforced": False}
    try:
        worked = _attach_job_limit(proc) is True
    except Exception:
        worked = False
    if worked:
        return {"memory_cap_bytes": MAX_MEMORY_BYTES, "memory_cap_enforced": True}
    return {"memory_cap_bytes": None, "memory_cap_enforced": False}


def _run_child(payload: bytes):
    """Run one child: (raw stdout, overflowed, timed_out, returncode, failure, cap).

    `failure` is "" or a plain refusal for a child that could not even start;
    `cap` is {memory_cap_bytes, memory_cap_enforced} for that child.

    The wall clock covers interpreter start-up and the script. Output is read
    incrementally and the child is KILLED as soon as either bound is crossed;
    it is never waited out after the cap is hit. The memory cap (Windows only)
    is attached BEFORE the payload is fed, so the script's first allocation
    already has it.
    """
    try:
        proc = _spawn([sys.executable, "-B", "-I", "-c", _CHILD_SOURCE],
                      _child_env())
    except (OSError, ValueError) as exc:
        return (b"", False, False, -1,
                "Not run: the sandbox's own Python could not be started "
                f"({exc}).", dict(_NO_CHILD_CAP))
    cap = _memory_cap_for(proc)

    out = bytearray()
    overflow = threading.Event()
    state = {"overflow": False}

    def feed():
        try:
            if proc.stdin is not None:
                proc.stdin.write(payload)
                proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass

    def read():
        try:
            while True:
                chunk = proc.stdout.read1(65536)
                if not chunk:
                    break
                if len(out) + len(chunk) > OUTPUT_CAP:
                    state["overflow"] = True
                    overflow.set()
                    return
                out.extend(chunk)
        except (OSError, ValueError):
            pass

    feeder = threading.Thread(target=feed, daemon=True)
    reader = threading.Thread(target=read, daemon=True)
    try:
        feeder.start()
        reader.start()
    except Exception:
        # A sandbox that cannot start its own threads must not leave the child
        # waiting for a payload that will never come: stop it, then report.
        try:
            proc.kill()
        except OSError:
            pass
        _close_job_limit(proc)
        raise
    timed_out = False
    deadline = time.monotonic() + TIMEOUT_S
    while True:
        if overflow.is_set():
            break
        if proc.poll() is not None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        overflow.wait(min(0.02, remaining))
    if overflow.is_set() or timed_out:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        # The kill did not settle: try once more, then report either way. A
        # child this module cannot stop is a refusal, never a claimed success.
        try:
            proc.kill()
            proc.wait(timeout=5.0)
        except (OSError, subprocess.TimeoutExpired):
            pass
    reader.join(5.0)
    # A reader that is STILL alive here means the kill above did not settle (a
    # child this module cannot stop). Do NOT close the pipe from this thread:
    # on Windows closing a pipe with a read pending in another thread can block
    # for ever. The reader is a daemon, the refusal is returned either way, and
    # the daemon thread ends when the child does.
    feeder.join(2.0)
    overflowed = state["overflow"] or len(out) > OUTPUT_CAP
    _close_job_limit(proc)
    return bytes(out), overflowed, timed_out, proc.returncode, "", cap


def _verified(raw: bytes, marker: bytes):
    """(result dict, "") from a verified envelope, or (None, plain refusal).

    The caller gets only the four documented keys. Anything without the nonce
    marker or with a malformed envelope is a refusal, never a partial answer.
    """
    at = raw.find(marker)
    unverified = ("Not run: the sandbox program's result could not be verified, "
                  "so nothing from it is reported.")
    if at < 0:
        return None, unverified
    try:
        envelope = json.loads(raw[at + len(marker):].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, unverified
    if not isinstance(envelope, dict):
        return None, unverified
    ok = envelope.get("ok")
    figures = envelope.get("figures")
    error = envelope.get("error")
    if type(ok) is not bool or not isinstance(figures, list) \
            or not isinstance(error, str) or len(figures) > 16:
        return None, unverified
    clean = []
    for item in figures:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) \
                or "data" not in item:
            return None, unverified
        clean.append({"name": item["name"], "data": item["data"]})
    return {"ok": ok,
            "stdout": raw[:at].decode("utf-8", "replace"),
            "figures": clean,
            "error": error}, ""


def run_data_script(code: str, read_only_files: dict | None = None) -> dict:
    """Run one small untrusted Python script, hermetically. See the module docstring.

    `code` is untrusted text. `read_only_files` is `name -> path` or None: the
    only files the script can reach, through `read_csv(name)`. Returns
    `{"ok": bool, "stdout": str, "figures": list, "error": str,
    "memory_cap_bytes": int | None, "memory_cap_enforced": bool}` and never
    raises for a bad script; a refused script starts no process at all, and its
    memory-cap keys say so (`None`/`False`). On Windows a running child is under
    a real 256 MiB job-object cap; on Linux nothing here can set one and the
    result says `None`/`False` rather than claiming it.
    """
    refused = {"ok": False, "stdout": "", "figures": [], "error": "",
               "memory_cap_bytes": None, "memory_cap_enforced": False}
    if not isinstance(code, str):
        refused["error"] = "Not run: the script must be text, so the sandbox can read it."
        return refused
    why = _refusal(code)
    if why:
        refused["error"] = why
        return refused
    files, why = _prepare_files(read_only_files)
    if why:
        refused["error"] = why
        return refused
    marker = "===jarvis-sandbox-result-" + secrets.token_hex(16) + "==="
    try:
        # ensure_ascii=True: the payload is ASCII JSON, so a script holding any
        # Unicode (even a lone surrogate) is carried to the child as escapes
        # rather than raising in this process. It is a value in stdin, never a
        # command-line argument, so its size is not limited by the shell.
        payload = json.dumps({
            "code": code,
            "files": files,
            "marker": marker,
            "allowed": sorted(ALLOWED_IMPORTS),
            "max_input": MAX_INPUT_BYTES,
        }, ensure_ascii=True).encode("ascii")
        raw, overflowed, timed_out, returncode, failure, cap = _run_child(payload)
    except Exception as exc:      # the sandbox itself must never raise at a caller
        refused["error"] = f"Not run: the sandbox itself stopped ({type(exc).__name__})."
        return refused
    if failure:
        result = dict(refused)
        result["error"] = failure
        result.update(cap)
        return result
    if timed_out:
        result = dict(refused)
        result["error"] = (f"Not run: the program did not finish within "
                           f"{TIMEOUT_S:g} seconds and was stopped.")
        result.update(cap)
        return result
    if overflowed:
        result = dict(refused)
        result["error"] = (f"Not run: the program printed more than {OUTPUT_CAP} "
                           f"bytes and was stopped.")
        result.update(cap)
        return result
    if returncode != 0:
        result = dict(refused)
        result["error"] = ("Not run: the sandbox program stopped unexpectedly "
                           f"(exit code {returncode}), so nothing from it is reported.")
        result.update(cap)
        return result
    result, unverified = _verified(raw, marker.encode("utf-8"))
    if result is None:
        refused["error"] = unverified
        return refused
    result.update(cap)
    return result
