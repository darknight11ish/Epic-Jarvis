"""test_sandbox_exec.py - Pillar 15, the hermetic local Python data & maths sandbox
(jarvis_sandbox_exec.py).

    python -B backend/test_sandbox_exec.py

Runs anywhere: no network, no model, no real data (the one CSV is invented in
this suite's own temporary folder). It drives the REAL `run_data_script` and
asserts on the data it returns; it does not read the module's source text.

What it proves:

 1. THE CONTRACT: exactly `ok`, `stdout`, `figures`, `error`; `TIMEOUT_S` is
    5.0; `OUTPUT_CAP` is 64 * 1024; an empty script is allowed.
 2. THE ALLOWED WORLD REALLY WORKS: real `statistics.mean`, exact `decimal`
    arithmetic, `fractions`, and `collections`/`itertools`/`re`/`json`/
    `datetime`, in a separate `python -B -I` child. `from math import ...`
    works too.
 3. A CALLER-SUPPLIED FILE: `csv.reader(read_csv("scores"))` adds up a file
    the caller passed, BOM and quoted comma included. A name the caller did
    not pass - even a real absolute path - is refused; so is a mapping entry
    that does not exist, or is too big, before anything runs.
 4. FIGURES: `figure(name, data)` returns verified JSON data in order; a
    non-JSON value, an empty name and a seventeenth figure are plain refusals.
 5. THE AST ALLOWLIST BITES: socket/urllib/http/ssl (network), subprocess
    (programs), os/sys (the machine), pathlib/shutil (files), ctypes (code),
    and any module outside the ten (random) are refused with plain words.
    `eval`, `exec`, `compile`, `open`, `getattr`, `input`, `globals`, the
    dunder chain `(1).__class__.__base__.__subclasses__()`, dunder names and
    dunder text are refused. Classes and async are refused.
 6. A REFUSED SCRIPT STARTS NO PROCESS AT ALL - spied on the module's one
    child-start call - and the same spy sees a real allowed script start
    exactly one.
 7. THE WALL CLOCK AND THE OUTPUT CAP: a `while True` program is stopped after
    about `TIMEOUT_S` and the child is dead afterwards; a flood above
    `OUTPUT_CAP` is refused with limited stdout and the child is dead; a
    normal amount of output comes back whole.
 8. ERRORS ARE CLEAN DATA: a program that raises comes back as `ok: False`
    with the exception's plain name, output printed before the failure is
    kept, and a syntax error is refused without starting anything.
 9. THE CHILD'S ENVIRONMENT IS SCRUBBED: a secret and `PYTHONPATH` from this
    process never reach it; `jarvis_child_env.inherited()` is the source (a
    stub proves it is called), and its telemetry-off switches are present.
10. THE CHILD IS STARTED THE RIGHT WAY: the same interpreter, `-B`, `-I`,
    stdin/stdout pipes, stderr thrown away, no shell, and the scrubbed
    environment rather than `None`.
11. BAD INPUTS ARE PLAIN REFUSALS BEFORE ANY CHILD STARTS: a non-text script,
    a script over 100 KiB, a bad `read_only_files` shape, an oversized input
    file.
12. LAYER 3: a stubbed child that prints without the run's nonce envelope is
    refused and NOTHING it printed is returned - `ok` cannot be forged from
    stdout alone.
13. THE ALLOCATION-BOMB GUARD: a huge power, left shift, repeated sequence or
    `range` is refused by the AST pass BEFORE any child starts, each with its
    OWN reason code from the closed set `AST_BOMB_REASONS`; the threshold
    itself is a boundary (passing values still run), and small values of every
    shape are still allowed.
14. THE MEMORY CAP IS HONEST: on Windows a running child really is under a
    256 MiB Job Object (the seam says True and the numbers are the constant);
    on Linux/non-Windows the result NEVER claims a cap (`None` / `False`), a
    failed attach is `None` / `False`, and a refused script (no child at all)
    is `None` / `False` too.
15. THE CHAT DOOR: `jarvis_agent.TOOLS['run_data_script']` exists, is in
    exactly one tool group, maps to an EXISTING jarvis_gate action (`file_read`
    when it reads a file, `calculator` when it does not), refuses a file
    outside "Folders Jarvis may look in" before anything runs, uses the code
    and files `prepare()` resolved (never a second lookup from the args), and
    dispatches to `jarvis_sandbox_exec.run_data_script` through a real
    `run_local_turn` round - with `jarvis_gate.latch_taint(why="sandbox_file_read")`
    called exactly when a local file is read.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_sandbox_exec.py", "jarvis_child_env.py", "jarvis_agent.py")

import jarvis_child_env as CE  # noqa: E402
import jarvis_sandbox_exec as SE  # noqa: E402

PASSED, SKIPPED, FAILED = [], [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-sandbox-suite-"))

#: The invented bank-style CSV every file check uses. A BOM, a quoted comma,
#: a header and two rows: 9 + 10 = 19 points.
CSV_TEXT = "\ufeffname,points\n\"Ada, Lovelace\",9\nGrace,10\n"
CSV_PATH = TMP / "scores.csv"
CSV_PATH.write_text(CSV_TEXT, encoding="utf-8", newline="")
#: The path a fake jarvis_documents resolves the CSV to. Different from
#: CSV_PATH string-for-string, so a tool that keeps the RAW argument instead of
#: the resolved path `allowed_path` returned is caught (see the chat-door tests).
RESOLVED_PATH = TMP / "resolved-scores.csv"
RESOLVED_PATH.write_text(CSV_TEXT, encoding="utf-8", newline="")

KEYS = {"ok", "stdout", "figures", "error", "memory_cap_bytes", "memory_cap_enforced"}


def check(name, cond, detail=""):
    """One check. `cond` is always a real condition; never the constant True."""
    ok = bool(cond)
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def shape(res):
    """True when `res` is the documented six-key result dict."""
    if not isinstance(res, dict) or set(res) != KEYS:
        return False
    cap = res["memory_cap_bytes"]
    return (isinstance(res["ok"], bool) and isinstance(res["stdout"], str)
            and isinstance(res["figures"], list) and isinstance(res["error"], str)
            and (cap is None or (isinstance(cap, int) and not isinstance(cap, bool)))
            and isinstance(res["memory_cap_enforced"], bool))


def refused(res, *words):
    """True when `res` is a refusal whose plain-English error contains `words`."""
    if not shape(res) or res["ok"] is not False or not res["error"].strip():
        return False
    text = res["error"].lower()
    return all(str(word).lower() in text for word in words)


@contextlib.contextmanager
def spying():
    """Replace the module's one child-start call with a counting spy.

    The real Popen still runs. `spy.calls` records every argv/kwargs pair an
    allowed run hands it, and a refused script must leave it empty.
    """
    real = SE._POPEN
    spy = _SpawnSpy(real)
    SE._POPEN = spy
    try:
        yield spy
    finally:
        SE._POPEN = real
        for proc in spy.procs:
            try:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5.0)
            except Exception:
                pass


class _SpawnSpy:
    def __init__(self, inner):
        self.inner = inner
        self.calls = []
        self.procs = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))
        proc = self.inner(argv, **kwargs)
        self.procs.append(proc)
        return proc


class _FakeChild:
    """A finished child that only prints `painted`, with no real process."""

    def __init__(self, painted: bytes):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(painted)
        self.returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


@contextlib.contextmanager
def faking(painted: bytes):
    """Make the module talk to a stand-in child instead of a real one."""
    real = SE._POPEN
    child = _FakeChild(painted)
    SE._POPEN = lambda argv, **kwargs: child
    try:
        yield child
    finally:
        SE._POPEN = real


def t_the_contract_is_the_documented_shape():
    res = SE.run_data_script("print('hello')")
    check("the result is exactly {ok, stdout, figures, error} plus the two memory-cap "
          "honesty keys, with the documented types", shape(res), res)
    check("a program's printed text is stdout, not mixed with the sandbox's own result "
          "envelope", shape(res) and res["stdout"] == "hello\n", res)
    check("TIMEOUT_S is the documented hard 5.0-second wall clock",
          SE.TIMEOUT_S == 5.0, SE.TIMEOUT_S)
    check("OUTPUT_CAP is the documented 64 * 1024-byte output cap",
          SE.OUTPUT_CAP == 64 * 1024, SE.OUTPUT_CAP)
    check("MAX_MEMORY_BYTES is the documented 256 MiB job-object cap",
          SE.MAX_MEMORY_BYTES == 256 * 1024 * 1024, SE.MAX_MEMORY_BYTES)
    res = SE.run_data_script("")
    check("an empty script is allowed and prints nothing",
          shape(res) and res["ok"] is True and res["stdout"] == ""
          and res["figures"] == [] and res["error"] == "", res)


def t_the_allowed_modules_really_work():
    res = SE.run_data_script("import math\nprint(math.sqrt(16))")
    check("import math runs in the child: sqrt(16) prints 4.0",
          shape(res) and res["ok"] is True and res["stdout"] == "4.0\n", res)
    res = SE.run_data_script("import statistics\nprint(statistics.mean([1, 2, 3, 4]))")
    check("import statistics runs: mean([1,2,3,4]) prints 2.5",
          shape(res) and res["ok"] is True and res["stdout"] == "2.5\n", res)
    res = SE.run_data_script(
        "from decimal import Decimal\n"
        "print(Decimal('1.10') + Decimal('2.20'))")
    check("decimal arithmetic is exact: 1.10 + 2.20 prints 3.30, not 3.3000000000000003",
          shape(res) and res["ok"] is True and res["stdout"] == "3.30\n", res)
    res = SE.run_data_script(
        "from fractions import Fraction\n"
        "print(Fraction(1, 3) + Fraction(2, 3))")
    check("fractions are exact too: 1/3 + 2/3 prints 1",
          shape(res) and res["ok"] is True and res["stdout"] == "1\n", res)
    res = SE.run_data_script(
        "import collections, datetime, itertools, json, re\n"
        "print(sorted(collections.Counter('aab').items()))\n"
        "print(list(itertools.islice(itertools.count(1), 3)))\n"
        "print(bool(re.match(r'^\\d+$', '123')))\n"
        "print(json.dumps({'x': [1, 2]}))\n"
        "print(datetime.date(2026, 10, 17).isoformat())")
    want = ("[('a', 2), ('b', 1)]\n[1, 2, 3]\nTrue\n{\"x\": [1, 2]}\n2026-10-17\n")
    check("collections, itertools, re, json and datetime all run in one script",
          shape(res) and res["ok"] is True and res["stdout"] == want, res)
    res = SE.run_data_script("from math import sqrt\nprint(sqrt(9))")
    check("from math import sqrt works (an allowlist entry, not a blocked list)",
          shape(res) and res["ok"] is True and res["stdout"] == "3.0\n", res)


def t_a_caller_supplied_csv_is_read():
    code = (
        "import csv\n"
        "rows = list(csv.reader(read_csv('scores').splitlines()))\n"
        "total = sum(int(row[1]) for row in rows[1:])\n"
        "print(total)")
    res = SE.run_data_script(code, {"scores": str(CSV_PATH)})
    check("csv over a caller-provided read-only file: the invented rows add up to 19",
          shape(res) and res["ok"] is True and res["stdout"] == "19\n", res)
    res = SE.run_data_script("print(read_csv('scores').splitlines()[1])",
                             {"scores": CSV_PATH})
    check("read_csv returns the file's text, BOM stripped and a quoted comma intact",
          shape(res) and res["ok"] is True
          and res["stdout"] == '"Ada, Lovelace",9\n', res)
    res = SE.run_data_script("print(read_csv('nope'))", {"scores": str(CSV_PATH)})
    check("a name the caller did not pass is refused: read_csv('nope') reads nothing",
          refused(res, "no file called", "nope"), res)
    res = SE.run_data_script("print(read_csv(%r))" % str(CSV_PATH),
                             {"scores": str(CSV_PATH)})
    check("a REAL absolute path is not a name: read_csv(path) is refused",
          refused(res, "no file called") and "Ada" not in res["stdout"], res)
    missing = TMP / "not-here.csv"
    res = SE.run_data_script("print(1)", {"scores": str(missing)})
    check("a read_only_files entry that does not exist is refused before anything runs",
          refused(res, "not a file that exists"), res)


def t_figures_are_verified_json():
    code = ("figure('evens', {'xs': [0, 2, 4], 'ys': [0, 4, 16]})\n"
            "print('done')")
    res = SE.run_data_script(code)
    want = [{"name": "evens", "data": {"xs": [0, 2, 4], "ys": [0, 4, 16]}}]
    check("figure(name, data) returns the exact data as JSON, with the script's stdout",
          shape(res) and res["ok"] is True and res["stdout"] == "done\n"
          and res["figures"] == want, res)
    res = SE.run_data_script("figure('a', [1, 2])\nfigure('b', {'k': None})")
    check("figures keep their call order and their names",
          shape(res) and res["ok"] is True and res["figures"] == [
              {"name": "a", "data": [1, 2]}, {"name": "b", "data": {"k": None}}], res)
    res = SE.run_data_script("figure('bad', {1, 2})")
    check("a figure that is not JSON is a plain refusal, never a half-written chart",
          refused(res, "figure", "cannot be shown"), res)
    res = SE.run_data_script("figure('', [1])")
    check("a figure with an empty name is a plain refusal",
          refused(res, "figure", "plain-text name"), res)
    res = SE.run_data_script("".join("figure('f', 0)\n" for _ in range(17)))
    check("a seventeenth figure from one script is refused",
          refused(res, "at most 16 figures"), res)


def t_imports_outside_the_allowlist_are_refused():
    network = ["socket", "urllib", "http", "ssl"]
    bad = [(mod, SE.run_data_script(f"import {mod}")) for mod in network]
    check("socket, urllib, http and ssl are refused: the sandbox has no network",
          all(refused(res, mod, "network") for mod, res in bad), bad)
    res = SE.run_data_script("import subprocess")
    check("subprocess is refused: the sandbox never starts another program",
          refused(res, "subprocess", "never starts another program"), res)
    bad = [(mod, SE.run_data_script(f"import {mod}")) for mod in ("os", "sys")]
    check("os and sys are refused: a program cannot reach the machine or the interpreter",
          all(refused(res, mod) and ("machine" in res["error"] or "interpreter" in res["error"])
              for mod, res in bad), bad)
    bad = [(mod, SE.run_data_script(f"import {mod}")) for mod in ("pathlib", "shutil")]
    check("pathlib and shutil are refused: the sandbox has no filesystem access",
          all(refused(res, mod, "filesystem") for mod, res in bad), bad)
    res = SE.run_data_script("import ctypes")
    check("ctypes is refused: the sandbox does not load code from the machine",
          refused(res, "ctypes", "code from the machine"), res)
    res = SE.run_data_script("import random")
    check("a module outside the ten is refused strictly, naming the allowed list",
          refused(res, "random", "allows only", "statistics"), res)
    res = SE.run_data_script("import os.path")
    check("a refused module's submodule (os.path) is refused with the same plain reason",
          refused(res, "os.path", "machine"), res)
    res = SE.run_data_script("from socket import socket as sock")
    check("from-import of a refused module is refused too",
          refused(res, "socket", "network"), res)


def t_dangerous_builtins_are_refused():
    bad = [
        ("eval('1+1')", ("eval", "running text as code")),
        ("exec('x = 1')", ("exec", "running text as code")),
        ("compile('1', '<x>', 'eval')", ("compile", "building code from text")),
        ("open('C:/x')", ("opening files", "read_csv")),
        ("getattr(1, 'real')", ("attribute", "text name")),
        ("input()", ("keyboard input",)),
        ("setattr(type('x', (), {}), 'a', 1)", ("attribute", "text name")),
        ("globals()", ("globals", "own globals")),
        ("locals()", ("locals", "own locals")),
        ("vars()", ("own names",)),
        ("dir()", ("own names",)),
    ]
    for code, words in bad:
        res = SE.run_data_script(code)
        check(f"{code.split('(')[0].strip()} is refused with plain words",
              refused(res, *words), res)


def t_dunder_access_is_refused():
    res = SE.run_data_script("(1).__class__.__base__.__subclasses__()")
    check("the subclass walk (1).__class__.__base__.__subclasses__() is refused",
          refused(res, "special name", "__"), res)
    res = SE.run_data_script("import math\nprint(math.__dict__)")
    check("a dunder attribute on an allowed module (math.__dict__) is refused",
          refused(res, "__dict__"), res)
    res = SE.run_data_script("print.__globals__")
    check("a dunder attribute on a builtin (print.__globals__) is refused",
          refused(res, "__globals__"), res)
    res = SE.run_data_script("x = '__class__'")
    check("a dunder written as text is refused too (it is how a lookup would be reached)",
          refused(res, "__class__"), res)
    res = SE.run_data_script("from math import __loader__")
    check("a dunder imported by name (from math import __loader__) is refused",
          refused(res, "__loader__"), res)
    res = SE.run_data_script("__import__('math')")
    check("__import__ is refused as a special name",
          refused(res, "__import__"), res)


def t_classes_and_async_are_refused():
    res = SE.run_data_script("class A:\n    pass\nprint(A())")
    check("a class definition is refused, in plain words",
          refused(res, "class definitions", "plain functions"), res)
    res = SE.run_data_script("async def f():\n    return 1\nprint(f())")
    check("async code is refused, in plain words",
          refused(res, "async code"), res)


def t_a_refused_script_never_starts_a_process():
    samples = [
        "import socket",
        "import subprocess",
        "open('C:/x')",
        "(1).__class__.__base__.__subclasses__()",
        "eval('1+1')",
        "class A:\n    pass",
        "x = '__class__'",
        "x = 1\n" * 30000,
    ]
    with spying() as spy:
        results = [SE.run_data_script(code) for code in samples]
        refused_all = [refused(res) for res in results]
        started = len(spy.calls)
        allowed = SE.run_data_script("print('allowed')")
        allowed_started = len(spy.calls)
    check("all 8 refused samples come back as plain refusals", all(refused_all),
          list(zip([c[:30] for c in samples], results)))
    check("NOT ONE refused script started a process (the child-start spy saw zero calls)",
          started == 0, f"spy saw {started} call(s)")
    check("the same spy sees an allowed script start exactly one process (the zero above "
          "is not a vacuous spy)",
          allowed_started == 1 and shape(allowed) and allowed["ok"] is True,
          f"spy saw {allowed_started} call(s), result {allowed}")


def t_a_never_ending_program_is_stopped():
    margin = max(2.0, 0.6 * SE.TIMEOUT_S)
    with spying() as spy:
        started = time.monotonic()
        res = SE.run_data_script("while True:\n    pass")
        elapsed = time.monotonic() - started
        # Read the process state HERE, before `spying`'s cleanup: the check
        # below must observe what the MODULE did, not what the test did after.
        children = len(spy.procs)
        alive = [proc.poll() is None for proc in spy.procs]
    check("a never-ending program is refused, and the refusal says it was stopped",
          refused(res, "stopped", "seconds"), res)
    check("it really waited for the wall-clock bound before stopping it (it was not "
          "refused before it ran)",
          elapsed >= 0.75 * SE.TIMEOUT_S,
          f"came back after {elapsed:.2f}s, expected at least "
          f"{0.75 * SE.TIMEOUT_S:.2f}s")
    check("it came back within a bounded margin of that bound",
          elapsed < SE.TIMEOUT_S + margin,
          f"came back after {elapsed:.2f}s, budget {SE.TIMEOUT_S + margin:.2f}s")
    check("the never-ending child process was killed by the module, not left running",
          children == 1 and not any(alive),
          f"spy saw {children} child(ren); alive before cleanup: {alive}")


def t_a_flood_of_output_is_stopped():
    with spying() as spy:
        res = SE.run_data_script("print('x' * 200000)")
        children = len(spy.procs)
        alive = [proc.poll() is None for proc in spy.procs]
    check("a flood of output is refused, and the refusal says how much is allowed",
          refused(res, "printed", str(SE.OUTPUT_CAP)), res)
    check("the returned stdout never exceeds the output cap",
          len(res["stdout"]) <= SE.OUTPUT_CAP, len(res["stdout"]))
    check("the child that flooded the pipe was stopped by the module, not left writing",
          children == 1 and not any(alive),
          f"spy saw {children} child(ren); alive before cleanup: {alive}")
    res = SE.run_data_script("print('y' * 1000)")
    check("a normal amount of output comes back whole",
          shape(res) and res["ok"] is True and res["stdout"] == "y" * 1000 + "\n",
          res)


def t_errors_are_clean_data():
    res = SE.run_data_script("print('before')\n1 / 0")
    check("a program that raises is refused with the exception's plain name and message",
          refused(res, "ZeroDivisionError", "division by zero"), res)
    check("output printed before the failure is kept",
          shape(res) and res["ok"] is False and res["stdout"] == "before\n", res)
    check("a failing program's result is still the four-key shape, ok False, empty figures",
          shape(res) and res["ok"] is False and res["figures"] == [], res)
    with spying() as spy:
        res = SE.run_data_script("if True print(1)")
        started = len(spy.calls)
    check("a syntax error is refused as not valid Python, without starting anything",
          refused(res, "not valid Python") and started == 0,
          f"{res} / spy saw {started} call(s)")


def t_the_child_environment_is_scrubbed():
    secret_name = "JARVIS_SUITE_SANDBOX_SECRET_TOKEN"
    harmless_name = "JARVIS_SUITE_SANDBOX_HARMLESS"
    old = {name: os.environ.get(name) for name in (secret_name, harmless_name)}
    os.environ[secret_name] = "must-never-reach-the-child"
    os.environ[harmless_name] = "not-on-the-allow-list-either"
    try:
        with spying() as spy:
            res = SE.run_data_script("print('env')")
        env = spy.calls[0][1].get("env") if spy.calls else None
        check("the child's environment does not carry a secret from this process",
              isinstance(env, dict) and secret_name not in env, env)
        check("...nor PYTHONPATH (the child is started with -I, and the scrubber drops it)",
              isinstance(env, dict) and "PYTHONPATH" not in env, env)
        check("...nor a harmless-looking parent variable (the allowlist starts from "
              "nothing)", isinstance(env, dict) and harmless_name not in env, env)
        telemetry_ok = isinstance(env, dict) and all(
            env.get(k) == v for k, v in CE.TELEMETRY_OFF.items())
        check("the child gets jarvis_child_env's telemetry-off switches",
              telemetry_ok, (env, CE.TELEMETRY_OFF))
        real = SE._inherited_env
        try:
            SE._inherited_env = lambda: {"STUB_MARK": "yes", "STUB_TOKEN": "no"}
            got = SE._child_env()
        finally:
            SE._inherited_env = real
        check("the child's environment comes FROM jarvis_child_env.inherited(), not from "
              "this process (a stub helper is obeyed, and its secret-looking name is "
              "filtered)",
              got == {"STUB_MARK": "yes"}, got)
        check("the allowed run above still worked with the scrubbed environment",
              shape(res) and res["ok"] is True and res["stdout"] == "env\n", res)
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def t_the_child_is_started_the_right_way():
    with spying() as spy:
        res = SE.run_data_script("print(1)")
    argv, kwargs = spy.calls[0] if spy.calls else ([], {})
    check("the child is the same Python, started with -B and -I",
          argv[:1] == [sys.executable] and "-B" in argv and "-I" in argv, argv[:5])
    check("the child's stdin and stdout are the pipes the payload and result use",
          kwargs.get("stdin") == subprocess.PIPE
          and kwargs.get("stdout") == subprocess.PIPE, kwargs)
    check("the child's stderr is thrown away - it is never a side channel",
          kwargs.get("stderr") == subprocess.DEVNULL, kwargs.get("stderr"))
    check("the child is started without a shell",
          not kwargs.get("shell"), kwargs.get("shell"))
    check("the child is given the scrubbed environment, not None (which would inherit "
          "this process's env)", isinstance(kwargs.get("env"), dict), kwargs.get("env"))
    check("the -B -I child really ran the script", shape(res) and res["ok"] is True
          and res["stdout"] == "1\n", res)


def t_bad_inputs_are_refused_before_anything_runs():
    big_file = TMP / "too-big.csv"
    with open(big_file, "wb") as handle:
        handle.write(b"a" * (SE.MAX_INPUT_BYTES + 1))
    cases = [
        ("a non-text script", lambda: SE.run_data_script(123), "must be text"),
        ("a script over the 100 KiB limit",
         lambda: SE.run_data_script("x = 1\n" * 30000), "bigger than the sandbox"),
        ("read_only_files that is not a dictionary",
         lambda: SE.run_data_script("print(1)", "nope"), "dictionary"),
        ("a read-only file path that is not text",
         lambda: SE.run_data_script("print(1)", {"x": 42}), "must be text"),
        ("a read-only file name that is not text",
         lambda: SE.run_data_script("print(1)", {42: str(CSV_PATH)}), "plain-text name"),
        ("a read-only file over the 1 MiB limit",
         lambda: SE.run_data_script("print(1)", {"x": str(big_file)}),
         "bigger than the sandbox"),
    ]
    with spying() as spy:
        results = [(label, words, call()) for label, call, words in cases]
        started = len(spy.calls)
    for label, words, res in results:
        check(f"{label} is a plain refusal", refused(res, words), res)
    check("none of the six bad inputs started a process", started == 0,
          f"spy saw {started} call(s)")


def t_an_unverified_child_result_is_refused():
    with faking(b"forged output\n"):
        res = SE.run_data_script("print('hi')")
    check("a child whose output carries no run nonce is refused as unverifiable",
          refused(res, "could not be verified"), res)
    check("nothing the unverified child printed is passed on as stdout",
          shape(res) and res["stdout"] == "", res)
    check("the unverified result is still the documented six-key shape",
          shape(res) and res["figures"] == [], res)


# --------------------------------------------------------------------------
#   The allocation-bomb guard (piece 1: the AST pass, before any Popen)
# --------------------------------------------------------------------------

#: (code, the ONE closed-world reason it must get, a word its plain sentence has).
BOMBS = (
    ("print(2 ** 100_000)", "ast_memory_bomb_pow", "power"),
    ("print(2 ** 2 ** 20)", "ast_memory_bomb_pow", "power"),
    ("print(1 << 100_000)", "ast_memory_bomb_lshift", "shifts"),
    ("print('x' * 5_000_000)", "ast_memory_bomb_repeat", "repeats"),
    ("x = [0] * (10 ** 9)", "ast_memory_bomb_repeat", "repeats"),
    ("x = [0] * 1000 * 1000 * 1000", "ast_memory_bomb_repeat", "repeats"),
    ("print(list(range(2_000_000)))", "ast_memory_bomb_range", "range"),
    ("print([i for i in range(2_000_000)])", "ast_memory_bomb_range", "range"),
)


def t_allocation_bombs_are_refused_before_anything_starts():
    with spying() as spy:
        for code, reason, word in BOMBS:
            verdict = SE.validate_sandbox_ast(code)
            res = SE.run_data_script(code)
            check(f"bomb {code[:34]!r} -> {reason}, by validate and by run",
                  verdict["ok"] is False and verdict["reason"] == reason
                  and word in verdict["error"] and refused(res)
                  and res["error"] == verdict["error"], (verdict, res))
        started = len(spy.calls)
    check("not one allocation bomb started a child process", started == 0,
          f"spy saw {started} call(s)")
    res = SE.run_data_script("print(2 ** 20)")
    check("a small power still runs (2 ** 20 prints 1048576)",
          shape(res) and res["ok"] is True and res["stdout"] == "1048576\n", res)
    res = SE.run_data_script("print('x' * 100)")
    check("a small repeat still runs (and prints 100 characters)",
          shape(res) and res["ok"] is True and res["stdout"] == "x" * 100 + "\n", res)
    res = SE.run_data_script("print(list(range(5)))")
    check("a small range still runs (prints [0, 1, 2, 3, 4])",
          shape(res) and res["ok"] is True and res["stdout"] == "[0, 1, 2, 3, 4]\n", res)


def t_the_bomb_reasons_are_a_closed_world():
    want = frozenset({"ast_memory_bomb_pow", "ast_memory_bomb_lshift",
                      "ast_memory_bomb_repeat", "ast_memory_bomb_range"})
    check("AST_BOMB_REASONS is exactly the four documented codes",
          SE.AST_BOMB_REASONS == want, sorted(SE.AST_BOMB_REASONS))
    seen = {SE.validate_sandbox_ast(code)["reason"] for code, _reason, _w in BOMBS}
    check("every bomb shape in this suite lands on its code from that closed set",
          seen == want, sorted(seen))
    for code, _why in (("import socket", "an import refusal"),
                       ("if True print(1)", "a syntax refusal"),
                       ("(1).__class__", "a dunder refusal")):
        verdict = SE.validate_sandbox_ast(code)
        check(f"{_why} carries NO bomb reason", verdict["ok"] is False
              and verdict["reason"] == "" and verdict["error"].startswith("Not run:"),
              verdict)


def t_the_bomb_guard_sits_on_the_stated_threshold():
    cases = [
        ("print(2 ** 10_000)", True, "pow at the bound (10_000)"),
        ("print(2 ** 10_001)", False, "pow one over the bound"),
        ("print(1 << 10_000)", True, "shift at the bound (10_000)"),
        ("print(1 << 10_001)", False, "shift one over the bound"),
        ("x = [0] * 1_000_000", True, "repeat at the bound (1_000_000)"),
        ("x = [0] * 1_000_001", False, "repeat one over the bound"),
        ("x = list(range(1_000_000))", True, "range at the bound (1_000_000)"),
        ("x = list(range(1_000_001))", False, "range one over the bound"),
    ]
    for code, allowed, label in cases:
        verdict = SE.validate_sandbox_ast(code)
        check(f"{label}: {'allowed' if allowed else 'refused as a bomb'}",
              verdict["ok"] is allowed
              and (allowed or verdict["reason"].startswith("ast_memory_bomb_")), verdict)


# --------------------------------------------------------------------------
#   The memory cap (piece 2: Win32 Job Object, or the honest non-Windows answer)
# --------------------------------------------------------------------------

def t_the_memory_cap_is_honest():
    real_windows, real_attach = SE._IS_WINDOWS, SE._attach_job_limit
    calls = []

    def attach_true(proc):
        calls.append(proc)
        return True

    def attach_false(proc):
        calls.append(proc)
        return False

    def attach_boomed(proc):
        calls.append(proc)
        raise RuntimeError("no job object for you")

    try:
        SE._IS_WINDOWS = False
        SE._attach_job_limit = attach_boomed
        call_before = len(calls)
        cap = SE._memory_cap_for(object())
        check("Linux/non-Windows: NO cap is claimed, and the attach seam is never even "
              "called", cap == {"memory_cap_bytes": None, "memory_cap_enforced": False}
              and len(calls) == call_before, cap)
        SE._IS_WINDOWS = True
        for attach, label, enforced in (
                (attach_true, "a real job object", True),
                (attach_false, "an attach that said False", False),
                (attach_boomed, "an attach that raised", False)):
            SE._attach_job_limit = attach
            cap = SE._memory_cap_for(object())
            want = ({"memory_cap_bytes": SE.MAX_MEMORY_BYTES, "memory_cap_enforced": True}
                    if enforced else
                    {"memory_cap_bytes": None, "memory_cap_enforced": False})
            check(f"Windows, {label}: the result claims {'the 256 MiB cap' if enforced else 'NO cap'}",
                  cap == want, cap)
    finally:
        SE._IS_WINDOWS, SE._attach_job_limit = real_windows, real_attach
    res = SE.run_data_script("print(1)")
    if sys.platform == "win32":
        honest = {"memory_cap_bytes": SE.MAX_MEMORY_BYTES, "memory_cap_enforced": True}
    else:
        honest = {"memory_cap_bytes": None, "memory_cap_enforced": False}
    check("a real run reports the PLATFORM's honest cap (never a claim on Linux)",
          shape(res) and all(res.get(k) == v for k, v in honest.items()), res)
    res = SE.run_data_script("print(2 ** 100_000)")
    check("a refused script ran no child, so it claims no memory cap",
          shape(res) and res["memory_cap_bytes"] is None
          and res["memory_cap_enforced"] is False, res)


# --------------------------------------------------------------------------
#   The chat door (piece 3: jarvis_agent.py registers and dispatches the tool)
# --------------------------------------------------------------------------

def _doc_module(name, **attrs):
    """A stand-in module with exactly these attributes, for one `modules()` block."""
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


@contextlib.contextmanager
def modules(**replacement):
    """Temporarily put these modules in `sys.modules` (saved and restored)."""
    saved = {name: sys.modules.get(name) for name in replacement}
    try:
        for name, mod in replacement.items():
            sys.modules[name] = mod
        yield
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


@contextlib.contextmanager
def fake_gate(latch_calls):
    """The two jarvis_gate seams this tool uses, plus a recording latch."""
    def latch_taint(minutes=None, why=""):
        latch_calls.append(why)
        return True

    def action_for_tool(name, params=None):
        table = {"file_read": "read_files_readonly", "calculator": "auto"}
        return table.get(name, "unclassified_tool"), name in table

    with modules(jarvis_gate=_doc_module(
            "jarvis_gate", latch_taint=latch_taint,
            action_for_tool=action_for_tool,
            _TOOL_ACTIONS={"file_read": "read_files_readonly", "calculator": "auto"})):
        yield sys.modules["jarvis_gate"]


def _agent():
    import jarvis_agent
    jarvis_agent._manner_now = lambda *a, **k: None
    return jarvis_agent


def t_the_chat_door_is_registered_and_maps_to_a_real_gate_action():
    AG = _agent()
    tool = AG.TOOLS.get(AG.SANDBOX_TOOL)
    check("run_data_script is a jarvis_agent tool", tool is not None, sorted(
        n for n in AG.TOOLS if "script" in n))
    if tool is None:
        return
    params = tool.parameters
    check("its schema names a required text `code` and an optional `files` object",
          params.get("required") == ["code"]
          and params.get("properties", {}).get("code", {}).get("type") == "string"
          and params.get("properties", {}).get("files", {}).get("type") == "object",
          params)
    homes = (1 if AG.SANDBOX_TOOL in AG.CORE_TOOLS else 0) + sum(
        1 for _g, _w, members in AG.TOOL_GROUPS if AG.SANDBOX_TOOL in members)
    check("it has exactly one home: one tool group, not the core", homes == 1, homes)
    check("a pure calculation is decided under the gate's own calculator key",
          tool.gate_lookup_name({"code": "print(1)"}) == AG.SANDBOX_GATE_PURE
          == "calculator", tool.gate_lookup_name({"code": "print(1)"}))
    check("a file read is decided under the gate's own file_read key",
          tool.gate_lookup_name({"code": "x", "files": {"a": "b"}})
          == AG.SANDBOX_GATE_FILE == "file_read",
          tool.gate_lookup_name({"code": "x", "files": {"a": "b"}}))
    with fake_gate([]) as gate:
        check("both lookup keys are keys jarvis_gate._TOOL_ACTIONS already knows "
              "(this tool needs no gate change)",
              AG.SANDBOX_GATE_FILE in gate._TOOL_ACTIONS
              and AG.SANDBOX_GATE_PURE in gate._TOOL_ACTIONS,
              (AG.SANDBOX_GATE_FILE, AG.SANDBOX_GATE_PURE))
    check("its description fits the 300-token per-tool budget",
          AG.estimate_tokens(tool.schema()) <= 300, AG.estimate_tokens(tool.schema()))


def t_the_chat_door_refuses_files_outside_the_listed_folders():
    AG = _agent()
    tool = AG.TOOLS[AG.SANDBOX_TOOL]
    docs = _doc_module(
        "jarvis_documents", folders=lambda: [str(TMP)],
        allowed_path=lambda path: (
            (str(RESOLVED_PATH), str(TMP))
            if os.path.realpath(str(path)) == os.path.realpath(str(CSV_PATH)) else None))
    with modules(jarvis_documents=docs):
        bad = None
        try:
            tool.prepare({"code": "print(1)",
                          "files": {"secret": str(TMP.parent / "outside.txt")}})
        except ValueError as exc:
            bad = str(exc)
        check("a file outside 'Folders Jarvis may look in' is refused in prepare(), "
              "before any gate or child", isinstance(bad, str)
              and "Folders Jarvis may look in" in bad, bad)
        state, description = tool.prepare(
            {"code": "print(1)", "files": {"scores": str(CSV_PATH)}})
        check("a file inside a listed folder is resolved to the path the file rule "
              "returned, in the state and on the plan",
              state["files"] == {"scores": str(RESOLVED_PATH)}
              and "scores" in description and str(RESOLVED_PATH) in description,
              (state, description))


def t_the_chat_door_uses_the_checked_state_and_dispatches():
    AG = _agent()
    tool = AG.TOOLS[AG.SANDBOX_TOOL]
    spy_calls, latch_calls = [], []
    ran = {"ok": True, "stdout": "ok\n", "figures": [], "error": "",
           "memory_cap_bytes": None, "memory_cap_enforced": False}

    def run_spy(code, read_only_files=None):
        spy_calls.append((code, read_only_files))
        return dict(ran)

    real_run = SE.run_data_script
    SE.run_data_script = run_spy
    try:
        with fake_gate(latch_calls):
            state = {"code": "print(99)",
                     "files": {"scores": str(RESOLVED_PATH)}}
            result = tool.execute({"code": "print(1)", "files": {}}, state)
            check("execute() runs the code and files prepare() resolved, never a second "
                  "lookup from the args",
                  spy_calls == [("print(99)", {"scores": str(RESOLVED_PATH)})],
                  (spy_calls, result))
            check("reading a local file latches the turn as private "
                  "(why='sandbox_file_read')",
                  latch_calls == ["sandbox_file_read"], latch_calls)
            check("the sandbox's own result is what the tool returns", result == ran,
                  result)
            latch_calls.clear()
            spy_calls.clear()
            tool.execute({"code": "print(2)"}, {"code": "print(2)", "files": {}})
            check("a pure calculation reads no file, so it latches nothing",
                  latch_calls == [] and spy_calls == [("print(2)", None)],
                  (latch_calls, spy_calls))
    finally:
        SE.run_data_script = real_run


def t_jarvis_agent_dispatches_a_model_tool_call_to_run_data_script():
    AG = _agent()
    sys.path.insert(0, str(HERE))
    from test_agent import NoRealIO, allow, scripted_stream  # noqa: E402

    spy = []
    ran = {"ok": True, "stdout": "6\n", "figures": [], "error": "",
           "memory_cap_bytes": None, "memory_cap_enforced": False}

    def run_spy(code, read_only_files=None):
        spy.append((code, read_only_files))
        return dict(ran)

    call = {"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"id": "c1", "function": {"name": AG.SANDBOX_TOOL,
                                  "arguments": json.dumps({"code": "print(2 * 3)"})}}]}}]}
    answer = {"choices": [{"message": {"role": "assistant", "content": "It is 6."}}]}
    opener, bodies = scripted_stream([call, answer])
    asked = []

    def gate(action, detail, prompt):
        asked.append(action)
        return allow(action, detail, prompt)

    streamed = []
    real_run = SE.run_data_script
    SE.run_data_script = run_spy
    try:
        with NoRealIO():
            out = AG.run_local_turn(
                [{"role": "user", "content": "what is 2 times 3?",
                  "provenance": "typed"}],
                "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                stream_out=streamed.append, gate_check=gate, open_stream=opener,
                enabled_tools={AG.SANDBOX_TOOL}, record_chain=lambda steps: None,
                on_step=lambda step: None, lane_choice=None)
    finally:
        SE.run_data_script = real_run
    tool_messages = [m["content"] for m in bodies[-1]["messages"]
                     if m.get("role") == "tool"]
    check("a model's tool call really reaches jarvis_sandbox_exec.run_data_script "
          "through the turn loop", spy == [("print(2 * 3)", None)], spy)
    check("that run was decided under an existing gate action (calculator, auto)",
          asked == ["calculator"], asked)
    check("the sandbox's stdout is handed back to the model as the tool result",
          bool(tool_messages) and "6" in tool_messages[-1], tool_messages)
    check("the answer the owner sees is still the model's own words",
          out.get("answer") == "It is 6." or b"It is 6." in b"".join(streamed),
          (streamed, out.get("answer")))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    try:
        import shutil
        shutil.rmtree(TMP, ignore_errors=True)
    except Exception:
        pass
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
