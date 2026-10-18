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
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_sandbox_exec.py", "jarvis_child_env.py")

import jarvis_child_env as CE  # noqa: E402
import jarvis_sandbox_exec as SE  # noqa: E402

PASSED, SKIPPED, FAILED = [], [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-sandbox-suite-"))

#: The invented bank-style CSV every file check uses. A BOM, a quoted comma,
#: a header and two rows: 9 + 10 = 19 points.
CSV_TEXT = "\ufeffname,points\n\"Ada, Lovelace\",9\nGrace,10\n"
CSV_PATH = TMP / "scores.csv"
CSV_PATH.write_text(CSV_TEXT, encoding="utf-8", newline="")

KEYS = {"ok", "stdout", "figures", "error"}


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
    """True when `res` is the documented four-key result dict."""
    return isinstance(res, dict) and set(res) == KEYS \
        and isinstance(res["ok"], bool) and isinstance(res["stdout"], str) \
        and isinstance(res["figures"], list) and isinstance(res["error"], str)


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
    check("the result is exactly {ok, stdout, figures, error}, with the documented types",
          shape(res), res)
    check("a program's printed text is stdout, not mixed with the sandbox's own result "
          "envelope", shape(res) and res["stdout"] == "hello\n", res)
    check("TIMEOUT_S is the documented hard 5.0-second wall clock",
          SE.TIMEOUT_S == 5.0, SE.TIMEOUT_S)
    check("OUTPUT_CAP is the documented 64 * 1024-byte output cap",
          SE.OUTPUT_CAP == 64 * 1024, SE.OUTPUT_CAP)
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
    check("the unverified result is still the documented four-key shape",
          shape(res) and res["figures"] == [], res)


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
