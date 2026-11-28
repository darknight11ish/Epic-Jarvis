"""test_browser_test_guard.py - the default suite run cannot put a VISIBLE
browser window on the owner's screen, and this proves it without opening one.

    python3 backend/test_browser_test_guard.py

WHY THIS EXISTS (measured 2026-10-26). On the owner's PC, where Playwright IS
installed, a plain `py -3 -B backend/run_suites.py` ran
`backend/test_chatbot_sites.py`, and Playwright opened a real Chromium window
for every chatbot site profile - `chatgpt-profile10` and the rest, under a
temp folder, `ms-playwright\\chromium-1248\\chrome-win64\\chrome.exe`, parented
by the Playwright driver's node.exe. The owner saw "the browser keeps opening
and closing rapidly", and the suite's own "is Playwright installed?" check
could never stop it, because being installed is the normal state there and
nothing asked whether a window was allowed. The same one visible launch
(`jarvis_chatbot_web.py`'s `headless=False` `launch_persistent_context`) is
driven by four suites, so all four are guarded, not only the one that happened
to be measured first.

WHAT IT PINS, with no browser started anywhere:

  1. EACH GUARD IS REAL AND FIRST. Every guarded suite assigns the one opt-in
     name, gives it exactly "1" as its value, and puts
     `if not visible_browser_tests_allowed(): print(...); return 0` as the
     FIRST statement of main()'s try. No browser launch may sit at module level
     (it would run on import), inside that guard, or in the try's `finally`
     (which runs even on the guard's return); every other launch must be in a
     function main() reaches after the guard.
  2. THE SUITE ITSELF REFUSES, END TO END. Only after the source pin for
     `test_chatbot_sites.py` passes does this suite run it as a subprocess with
     the opt-in removed and `PLAYWRIGHT_BROWSERS_PATH` pointing at an EMPTY
     folder - a second seatbelt, so even a guard deleted since the pin could
     not find a browser to start. The run must exit 0, print exactly the one
     SKIPPED sentence, and print no check.
  3. THE RUNNER SKIPS THEM BY NAME. `backend/run_suites.py`'s
     `VISIBLE_BROWSER_SUITES` names each of the four with a reason, and its
     `_suite_job()` returns `skip` for each while the opt-in is unset - a
     default full run never executes them at all. That is the second,
     independent layer; the skip line carries the opt-in's name.
  4. THE SET IS COMPLETE, AND ONLY FOR THIS MODULE. The four names are exactly
     the backend suites that import `jarvis_chatbot_web`, so a new suite that
     drives that window fails here until it is guarded too; all five files
     assign the same opt-in value; and the runner's reader fails closed - only
     "1" is an opt-in, never "yes", "true" or "0". THE COMPLETENESS PIN IS NOT
     A BACKEND-WIDE GUARANTEE: `jarvis_browser_control.py` has its own visible
     launch by default (`_HEADLESS = False`, `launch(headless=_HEADLESS)`), so
     two facts about it are pinned here as well - its importer set (five files,
     so a NEW suite that imports it is noticed) and the one live suite's
     headless override. Whether any OTHER known importer launches visibly is
     not statically decidable from an import, and is not claimed.
  5. THE CODE-ONLY HALVES STILL RUN IN CI, AND REQUIRED CI CANNOT LAUNCH A
     BROWSER (corrected twice on 2026-11-17). The CI job that runs the backend
     sweep (`backend-shard` since the job was sharded on 2026-11-13; `backend`
     before that) and `backend-windows` both carry
     `JARVIS_ALLOW_VISIBLE_BROWSER_TESTS: "1"`, so each suite runs its code
     checks - the 441, in all. The browser half moved twice in one day:
       * this item used to say "no runner installs a Playwright browser, so the
         real-browser half prints SKIP ... playwright is not installed". That
         became FALSE on 2026-10-27 (#925), when `backend-shard` began installing
         Playwright's Chromium for `test_browser_control_live.py`. With the
         opt-in set and a browser present, all four suites really drove a
         browser in a REQUIRED job: measured on one green run, 2026-11-17,
         486 s / 117 s / 55 s / 12 s against sub-second for a code-only suite,
         and a Playwright `Locator.click` timed out there once.
       * the first fix gave the window its own switch, `JARVIS_RUN_REAL_BROWSER`,
         asked for BEFORE `playwright_installed()`, which nothing in ci.yml sets.
       * THE SECOND FIX, pinned here: the switch was not enough, because a guard
         that relies on a browser being ABSENT cannot protect a job that
         installs one - and "nothing sets the switch" is a promise, not a
         mechanism. The install is GONE from the required sweep, so a required
         backend job cannot even launch a browser. The one suite it served is
         skipped BY NAME by `run_suites.py` when Playwright is absent (printed,
         counted, and named in SKIPPED BY NAME - never `ok`, never a pass), and
         runs for real in ci.yml's INFORMATIONAL `backend-browser-live` job.
         `frontend-shard` is the one REQUIRED job that still installs a browser,
         and must: its own page tests ARE browser tests. That exception is
         written down in the test below, not hidden.
  6. THE CLI CANNOT START THE FLEET BY ACCIDENT. `run_suites.py --help` prints
     the usage and exits 0 without staging or running; a path-shaped or unknown
     argument (`backend/test_x.py`, a typo) fails and names the bare form
     (`test_x.py`) instead of being silently dropped and running everything.
     Both are measured traps from 2026-10-26: two agents typed the path form
     and started the whole fleet.

No Playwright is imported, no browser process is started, no page is served.
Every source check walks `ast` nodes instead of comparing source text, because
`tools/check_no_source_pins.py` counts a text pin and this file has no ceiling.

Run it through the runner (`python -B backend/run_suites.py
test_browser_test_guard.py`) or directly; it opens no browser. The one shipped
module it pins is read from `_where.BACKEND` - this folder in a clone, the
staged flattening under the runner, or `JARVIS_BACKEND` on a real install.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_suites as R  # noqa: E402
from _where import BACKEND  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

#: The one opt-in, as every file must spell it. It says a suite may RUN.
OPT_IN = "JARVIS_ALLOW_VISIBLE_BROWSER_TESTS"

#: The SECOND switch, the one that says a browser window may actually OPEN
#: (2026-11-17). CI sets OPT_IN above; nothing in CI may set this one.
REAL_BROWSER = "JARVIS_RUN_REAL_BROWSER"

#: The backend suites that import `jarvis_browser_control` today. An IMPORTER
#: set, never a launch claim: a suite reaches the module's visible launch
#: through its own helpers, so an import cannot decide whether a window opens.
#: The one live suite's headless override is pinned separately.
BROWSER_CONTROL_IMPORTERS = (
    "test_browser_control.py", "test_browser_control_live.py",
    "test_browser_engine.py", "test_duet_d2.py", "test_form_review.py")

#: The workflow whose backend jobs run the suites on a machine with no
#: Playwright browser, and must therefore carry the opt-in. The sweep job is
#: `backend-shard` since 2026-11-13 (`backend` is the aggregator over it);
#: `t_ci_keeps_the_code_only_checks` accepts either shape.
CI_YML = HERE.parent / ".github" / "workflows" / "ci.yml"

#: The REQUIRED backend jobs, which must not be able to launch a browser at all
#: (2026-11-17). `backend` is the aggregator over the shards, `backend-windows`
#: the other required backend half - and since 2026-11-27 that half is an
#: aggregator too, with `backend-windows-shard` running the suites (the matrix
#: job is what must not install a browser; a job that only reads
#: `needs.<job>.result` cannot launch one).
REQUIRED_BACKEND_JOBS = ("backend", "backend-shard", "backend-windows",
                         "backend-windows-shard")

#: THE ONLY ci.yml JOBS ALLOWED TO INSTALL PLAYWRIGHT, AND WHY EACH MUST.
#: `frontend-shard` is REQUIRED and is a browser job by nature: every suite in
#: jarvis-desktop/tests/ drives a headless Chromium through tests/uikit.mjs, so
#: removing its browser would delete the tests, not protect anything. The rule
#: this file enforces is about the BACKEND sweep, where a browser was accidental.
#: `backend-browser-live` is INFORMATIONAL - no ruleset requires it - and is where
#: test_browser_control_live.py really runs, because the required sweep may not
#: install a browser. A THIRD name appearing here is a decision to let a browser
#: into another job: make it deliberately, and say why in this tuple.
PLAYWRIGHT_INSTALL_JOBS = {"frontend-shard", "backend-browser-live"}

#: Every backend suite that drives jarvis_chatbot_web's visible window.
GUARDED = ("test_chatbot_gemini.py", "test_chatbot_sites.py",
           "test_handoff.py", "test_support_widget.py")

#: Suites that IMPORT `jarvis_chatbot_web` without being browser suites, and
#: the only names each may use on it. `test_chatbot_api.py` drives the driver's
#: own pure `_egress_refusal`; its `.open()` calls are the chatbot ADAPTER's,
#: not a window. The completeness check proves this map's claim rather than
#: trusting it: a name outside the set fails there.
IMPORT_ONLY = {"test_chatbot_api.py": frozenset({"_egress_refusal"})}

#: A Call attribute that starts a browser. The adapters' `open()` is what
#: reaches jarvis_chatbot_web's own launch; the other two are the raw calls.
LAUNCHES = {"open", "launch", "launch_persistent_context"}

#: Whether the source pin for test_chatbot_sites.py passed. The subprocess in
#: check 2 must not run unless it did (the brief's "if and only if the guard is
#: in place first").
SITES_GUARDED = [False]


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
#   Reading a file as ast, never as source text
# ---------------------------------------------------------------------------

def _tree(path: Path):
    """The parsed file. `ast` throughout: see the docstring on source pins."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _importers(module: str) -> set:
    """The backend test files that import `module`, by the ast walk.

    The same walk the completeness pin below uses, so the two importer sets
    cannot be derived differently.
    """
    found = set()
    for path in sorted(HERE.glob("test_*.py")):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom) and node.module == module:
                found.add(path.name)
            elif isinstance(node, ast.Import) and any(
                    a.name == module for a in node.names):
                found.add(path.name)
    return found


def _names_used_on(path, alias: str) -> set:
    """Every attribute this file reads off `alias.` - `W._egress_refusal` -> {"_egress_refusal"}.

    The completeness check uses it to prove that a suite importing the module
    without being a browser suite touches nothing on it but the names its
    `IMPORT_ONLY` row allows.
    """
    return {n.attr for n in ast.walk(_tree(path))
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == alias}


def _module_values(tree, name) -> list:
    """Every value a module-level `name = ...` assignment gives it, in order."""
    return [node.value for node in tree.body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name]


def _attribute_assignments(tree, attr) -> list:
    """Every `something.<attr> = value`: (line, target, value).

    `Assign` and `AnnAssign` both, because either is an assignment.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        found += [(node.lineno, target, value) for target in targets
                  if isinstance(target, ast.Attribute) and target.attr == attr]
    return found


def _headless_keywords(tree) -> list:
    """Every `headless=` keyword passed to any `....launch(...)` call."""
    return [k for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "launch"
            for k in n.keywords if k.arg == "headless"]


def _constant(tree, name):
    """The module-level `name = "<literal>"` value, or None."""
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            return node.value.value
    return None


def _main_and_guard(tree):
    """(main FunctionDef, the Try in it, the guard If) - missing pieces None."""
    main = next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    if main is None:
        return None, None, None
    body = next((n for n in main.body if isinstance(n, ast.Try)), None)
    if body is None or not body.body:
        return main, body, None
    guard = body.body[0] if isinstance(body.body[0], ast.If) else None
    return main, body, guard


def _is_launch(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in LAUNCHES)


def _launches(node) -> list:
    """Every browser-start call inside one AST node (a Module, an If, ...)."""
    return [n for n in ast.walk(node) if _is_launch(n)]


def _launches_in(statements) -> list:
    """Every browser-start call inside a list of statements."""
    return [n for stmt in statements for n in ast.walk(stmt) if _is_launch(n)]


def _names(nodes) -> set:
    return {n.id for node in nodes for n in ast.walk(node) if isinstance(n, ast.Name)}


def _units(tree) -> dict:
    return {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def _top_unit(tree, node):
    """The top-level def/class a node lives in; None means module level."""
    parent = {child: p for p in ast.walk(tree) for child in ast.iter_child_nodes(p)}
    cur = node
    while cur in parent and not isinstance(parent[cur], ast.Module):
        cur = parent[cur]
    return cur if isinstance(cur, (ast.FunctionDef, ast.ClassDef)) else None


# ---------------------------------------------------------------------------
#   1. Every visible-browser launch is behind a first-statement guard
# ---------------------------------------------------------------------------

def _guard_problems(tree) -> list:
    """Every reason a browser launch in this file is NOT behind the guard."""
    main, body, guard = _main_and_guard(tree)
    if main is None:
        return ["it has no main()"]
    if body is None or guard is None:
        return ["main() does not start with a guard inside a try"]
    problems = []

    test = guard.test
    helper_call = (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
                   and isinstance(test.operand, ast.Call)
                   and isinstance(test.operand.func, ast.Name)
                   and test.operand.func.id == "visible_browser_tests_allowed"
                   and not test.operand.args and not test.operand.keywords)
    if not helper_call:
        problems.append("main()'s first statement is not "
                        "`if not visible_browser_tests_allowed():`")
    if not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "print" for n in ast.walk(guard)):
        problems.append("the guard prints no SKIPPED sentence")
    if not any(isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
               and n.value.value == 0 for n in ast.walk(guard)):
        problems.append("the guard does not return 0")

    problems += [f"a browser launch is inside the guard itself (line {n.lineno})"
                 for n in _launches_in(guard.body)]
    problems += [f"a browser launch is in main()'s finally, which runs even when "
                 f"the guard returns (line {n.lineno})"
                 for n in _launches_in(body.finalbody)]

    # What main() can reach AFTER the guard, through the module's own defs.
    units = _units(tree)
    reachable = {"main"}
    frontier = (_names(body.body[1:]) & set(units)) - reachable
    while frontier:
        reachable |= frontier
        nxt = set()
        for name in frontier:
            nxt |= _names([units[name]]) & set(units)
        frontier = nxt - reachable

    for call in _launches(tree):
        owner = _top_unit(tree, call)
        if owner is None:
            problems.append(f"a browser launch runs at module level "
                            f"(line {call.lineno})")
        elif owner.name == "main":
            if call.lineno <= guard.lineno:
                problems.append(f"main() launches at line {call.lineno}, before the "
                                f"guard at line {guard.lineno}")
        elif owner.name not in reachable:
            problems.append(f"{owner.name} launches at line {call.lineno} but main() "
                            f"does not reach it after the guard")
    return problems


def _reads_the_opt_in(tree) -> bool:
    """The suite has its own reader, comparing against the literal "1"."""
    helper = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == "visible_browser_tests_allowed"), None)
    if helper is None:
        return False
    return any(
        isinstance(n, ast.Compare)
        and any(isinstance(op, ast.Eq) for op in n.ops)
        and any(isinstance(c, ast.Constant) and c.value == "1" for c in n.comparators)
        for n in ast.walk(helper))


def _browser_half_self_skips(tree) -> bool:
    """main() runs the code checks, then skips the real-browser half.

    That gate is what makes the CI opt-in safe: a runner has no Playwright
    browser, so the suite's code-only half runs and the browser half prints
    "SKIP the real-browser half: <why>" and exits 0, exactly as before the
    guard. Structural (`ast`), never a source-text pin.
    """
    main, _body, _guard = _main_and_guard(tree)
    if main is None:
        return False
    calls = {n.func.attr for n in ast.walk(main)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    words = [n.value for n in ast.walk(main)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return ("playwright_installed" in calls
            and any("real-browser half" in word for word in words))


def _reads_the_window_switch(tree) -> bool:
    """The suite has its own window reader, and it names REAL_BROWSER_ENV.

    And it compares against the literal "1", the same fail-closed rule as the
    opt-in - a half-typed "yes" must never open a window.
    """
    helper = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == "real_browser_window_allowed"), None)
    if helper is None:
        return False
    if not any(isinstance(n, ast.Name) and n.id == "REAL_BROWSER_ENV"
               for n in ast.walk(helper)):
        return False
    return any(
        isinstance(n, ast.Compare)
        and any(isinstance(op, ast.Eq) for op in n.ops)
        and any(isinstance(c, ast.Constant) and c.value == "1" for c in n.comparators)
        for n in ast.walk(helper))


def _window_gate_comes_first(tree) -> bool:
    """main() asks for the WINDOW switch BEFORE it asks for Playwright.

    Structural, and the order is the point: the browser-half skip is assigned
    from `real_browser_window_allowed()`, and that call is on an earlier line
    than the first `playwright_installed()` call. So "Playwright is installed",
    which is the normal state of both the owner's PC and the required Ubuntu
    job, can never by itself reach a launch.
    """
    main, _body, _guard = _main_and_guard(tree)
    if main is None:
        return False
    window = [n for n in ast.walk(main)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "real_browser_window_allowed"]
    installed = [n for n in ast.walk(main)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "playwright_installed"]
    if not window or not installed:
        return False
    return min(n.lineno for n in window) < min(n.lineno for n in installed)


def t_each_guarded_suite_is_guarded():
    for name in GUARDED:
        path = HERE / name
        if not path.is_file():
            check(f"{name} exists", False, str(path))
            continue
        tree = _tree(path)
        value = _constant(tree, "VISIBLE_BROWSER_ENV")
        check(f"{name}: the opt-in is {OPT_IN}", value == OPT_IN, repr(value))
        check(f"{name}: it reads the opt-in itself, and only \"1\" is one",
              _reads_the_opt_in(tree))
        problems = _guard_problems(tree)
        check(f"{name}: every browser launch is behind a first-statement guard "
              f"that prints SKIPPED and returns 0", not problems, "; ".join(problems))
        check(f"{name}: with the opt-in set the code checks run, and the "
              f"real-browser half self-skips when Playwright is missing",
              _browser_half_self_skips(tree))
        window = _constant(tree, "REAL_BROWSER_ENV")
        check(f"{name}: the window switch it reads is {REAL_BROWSER}",
              window == REAL_BROWSER, repr(window))
        check(f"{name}: it reads the window switch itself, and only \"1\" is one",
              _reads_the_window_switch(tree))
        check(f"{name}: the browser half asks for the window switch BEFORE it "
              f"asks whether Playwright is installed",
              _window_gate_comes_first(tree))
        if name == "test_chatbot_sites.py":
            SITES_GUARDED[0] = not problems


# ---------------------------------------------------------------------------
#   2. The suite itself exits 0, having run nothing and launched nothing
# ---------------------------------------------------------------------------

def t_the_suite_refuses_end_to_end():
    """Run test_chatbot_sites.py with the opt-in unset.

    ONLY after the source pin above proved its guard, as the brief requires.
    The empty PLAYWRIGHT_BROWSERS_PATH is a second seatbelt: if the guard were
    deleted after the pin, there is still no browser binary for Playwright to
    start, so this test cannot put a window on anyone's screen either way."""
    if not SITES_GUARDED[0]:
        skip("the source pin for test_chatbot_sites.py failed, so its guard is not "
             "proven: it was NOT run")
        return
    env = dict(os.environ)
    env.pop(OPT_IN, None)
    env["PYTHONIOENCODING"] = "utf-8"
    empty = Path(tempfile.mkdtemp(prefix="jarvis-guard-no-browser-"))
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(empty)
    try:
        try:
            r = subprocess.run(
                [sys.executable, "-B", str(HERE / "test_chatbot_sites.py")],
                cwd=HERE, env=env, capture_output=True, text=True, timeout=300,
                encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            check("test_chatbot_sites.py finishes instead of waiting", False,
                  "timeout after 300 s")
            return
    finally:
        shutil.rmtree(empty, ignore_errors=True)
    out = (r.stdout or "") + (r.stderr or "")
    lines = [line for line in out.splitlines() if line.strip()]
    check("test_chatbot_sites.py exits 0 with the opt-in unset", r.returncode == 0,
          (r.returncode, out[-900:]))
    check("it prints one SKIPPED sentence and nothing else - no check ran",
          len(lines) == 1 and lines[0].startswith("SKIPPED  test_chatbot_sites.py"),
          lines)
    check("that sentence says it did NOT run and is NOT a pass",
          len(lines) == 1 and "did NOT run" in lines[0] and "NOT pass" in lines[0],
          lines)
    check("and it names the opt-in the operator would set",
          len(lines) == 1 and OPT_IN in lines[0], lines)
    check("no traceback and no browser error", "Traceback" not in out
          and "Executable doesn't exist" not in out, out[-900:])


# ---------------------------------------------------------------------------
#   3. run_suites.py skips the four by name - the second layer
# ---------------------------------------------------------------------------

def t_the_runner_skips_them_by_name():
    listed = getattr(R, "VISIBLE_BROWSER_SUITES", None)
    listed_ok = isinstance(listed, dict)
    check("run_suites.py has the VISIBLE_BROWSER_SUITES skip list",
          listed_ok, repr(listed))
    if not listed_ok:
        return
    check("the runner's opt-in variable is the one the suites read",
          getattr(R, "VISIBLE_BROWSER_ENV", None) == OPT_IN,
          repr(getattr(R, "VISIBLE_BROWSER_ENV", None)))
    check("every guarded suite is named in the skip list",
          set(GUARDED) <= set(listed), sorted(set(listed)))
    for name in GUARDED:
        if name not in listed:
            continue
        reason = listed[name]
        check(f"{name}: the skip list gives a reason",
              isinstance(reason, str) and len(reason.strip()) > 10, repr(reason))

    # The worker env, minus the opt-in, so a regression that ignored the
    # `env` argument still cannot hand the opt-in to a spawned suite.
    env = {k: v for k, v in os.environ.items() if k != OPT_IN}
    reader_ok = R.visible_browser_opted_in({}) is False
    check("the runner reads the opt-in from the env it is given, and "
          "an empty one is no opt-in", reader_ok)
    if not reader_ok:
        return
    for name in GUARDED:
        if name not in listed:
            continue
        got = R._suite_job(HERE / name, HERE, env)
        check(f"{name}: the runner reports it `skip`, never runs it and never "
              f"passes it", got["status"] == "skip", got["line"])
    got = R._suite_job(HERE / "test_chatbot_sites.py", HERE, env)
    check("test_chatbot_sites.py's skip line names the reason and the opt-in",
          OPT_IN in got["line"] and "VISIBLE browser" in got["line"], got["line"])
    check("a suite the runner skipped counts no checks",
          got["counts"] == {"passed": 0, "skipped": 0, "failed": 0}, got["counts"])


# ---------------------------------------------------------------------------
#   4. The guarded set is complete, and one name covers all of it
# ---------------------------------------------------------------------------

def t_the_guarded_set_is_complete():
    importers = _importers("jarvis_chatbot_web")
    # IMPORT-ONLY, AND PROVED (2026-11-17). A suite may import the module
    # without being a browser suite: the only public way to drive that driver's
    # own pure `_egress_refusal` is through it, and the one-gate work needed
    # exactly that. `test_chatbot_api.py`'s own `.open()` calls are the chatbot
    # ADAPTER's, not a window, which is why `LAUNCHES` cannot decide this on its
    # own. So the exemption is a named map, and the check below proves its
    # claim: that suite touches nothing on the module but `_egress_refusal`.
    check("the guarded list is exactly the backend suites that import "
          "jarvis_chatbot_web - the module whose visible launch THESE FOUR "
          "reach (not a backend-wide guarantee: jarvis_browser_control.py has "
          "its own visible default; its importer set and the live suite's "
          "headless override are pinned separately, and whether any other "
          "importer launches visibly is not statically decidable)",
          importers == set(GUARDED) | set(IMPORT_ONLY), sorted(importers))
    uses = _names_used_on(HERE / "test_chatbot_api.py", "W")
    check("the one suite that imports it without launching a browser uses "
          "NOTHING on it but the driver's pure `_egress_refusal`",
          "test_chatbot_api.py" in IMPORT_ONLY
          and uses <= set(IMPORT_ONLY["test_chatbot_api.py"]), sorted(uses))


# ---------------------------------------------------------------------------
#   4b. The other visible launch: jarvis_browser_control.py
#
#   The completeness pin above covers importers of jarvis_chatbot_web only.
#   These pin what can be measured for the OTHER module whose default is a
#   visible window - and say what is not claimed: an import is not a launch.
# ---------------------------------------------------------------------------

def t_the_browser_control_visible_default_is_pinned():
    """The shipped module's default really is a visible window, and its launch
    really obeys the switch.

    Read from `_where.BACKEND` - the repo's own copy in a clone, the staged
    flattening under the runner, `JARVIS_BACKEND` on a real install - so the
    pins read the copy the backend job sees. That mode has a trap MEASURED
    here on 2026-10-26: an ambient `JARVIS_BACKEND` pointed the read at the
    owner's installed copy, so the pins passed while THIS repository's copy
    said `_HEADLESS = True`. The identity check below is what refuses that:
    when the two are different files they must be the same text, so the pins
    can never pass by reading a different tree."""
    path = BACKEND / "jarvis_browser_control.py"
    ours = HERE / "jarvis_browser_control.py"
    if not path.is_file():
        check("the shipped jarvis_browser_control.py is where the backend reads "
              "it", False, f"{path} is not a file (_where.BACKEND is {BACKEND})")
        return
    if (os.environ.get("JARVIS_BACKEND") and ours.is_file()
            and path.resolve() != ours.resolve()):
        check("the jarvis_browser_control.py these pins read is this "
              "repository's copy, not a different tree JARVIS_BACKEND names",
              path.read_bytes().replace(b"\r\n", b"\n")
              == ours.read_bytes().replace(b"\r\n", b"\n"),
              f"{path} differs from {ours}")
    tree = _tree(path)
    values = _module_values(tree, "_HEADLESS")
    check("the shipped jarvis_browser_control.py still defaults to a VISIBLE "
          "window: its one module-level _HEADLESS assignment is False",
          len(values) == 1 and isinstance(values[0], ast.Constant)
          and values[0].value is False,
          [ast.unparse(v) for v in values] or "no module-level _HEADLESS = ...")
    headless = _headless_keywords(tree)
    check("... and its launch still obeys that switch: `launch(headless=_HEADLESS)`",
          any(isinstance(k.value, ast.Name) and k.value.id == "_HEADLESS"
              for k in headless),
          [ast.unparse(k) for k in headless] or "no launch(headless=...) call")


def t_the_live_suite_turns_the_visible_default_off():
    """One suite switches the visible default off for itself, and no other
    backend suite touches `_HEADLESS` at all."""
    live = HERE / "test_browser_control_live.py"
    if not live.is_file():
        check("test_browser_control_live.py is where this file expects it",
              False, str(live))
        return
    hits = _attribute_assignments(_tree(live), "_HEADLESS")
    ok = (len(hits) == 1 and isinstance(hits[0][1].value, ast.Name)
          and hits[0][1].value.id == "B"
          and isinstance(hits[0][2], ast.Constant)
          and hits[0][2].value is True)
    check("test_browser_control_live.py still turns the visible default off for "
          "itself: one `B._HEADLESS = True` assignment",
          ok, [(line, ast.unparse(target), ast.unparse(value))
               for line, target, value in hits])
    owners = {path.name: _attribute_assignments(_tree(path), "_HEADLESS")
              for path in sorted(HERE.glob("test_*.py"))}
    owners = {name: hits for name, hits in owners.items() if hits}
    check("no other backend suite assigns _HEADLESS at all - exactly one file "
          "does, and it is the live suite",
          set(owners) == {"test_browser_control_live.py"},
          {name: [(line, ast.unparse(target)) for line, target, _v in hits]
           for name, hits in owners.items()})


def t_the_browser_control_importer_set_is_pinned():
    """A new suite that imports the module fails here until it is looked at."""
    importers = _importers("jarvis_browser_control")
    check("jarvis_browser_control.py's importer set is exactly the frozen five "
          "- an IMPORTER set, NOT a launch claim: launching visibly is not "
          "statically decidable from an import, and the live suite's headless "
          "override is pinned separately",
          importers == set(BROWSER_CONTROL_IMPORTERS), sorted(importers))


def t_one_opt_in_name_and_it_fails_closed():
    names = {name: _constant(_tree(HERE / name), "VISIBLE_BROWSER_ENV")
             for name in GUARDED}
    names["run_suites.py"] = getattr(R, "VISIBLE_BROWSER_ENV", None)
    check("all five files agree on the one opt-in name",
          set(names.values()) == {OPT_IN}, names)
    opted = R.visible_browser_opted_in
    check("the runner's reader accepts \"1\"", opted({OPT_IN: "1"}) is True)
    check("and a value typed with spaces around it is still the one opt-in",
          opted({OPT_IN: " 1 "}) is True)
    check("a missing variable is no opt-in", opted({}) is False)
    for value in ("", "0", "2", "yes", "true", "on", "1x"):
        check(f"it fails closed on {value!r}", opted({OPT_IN: value}) is False, value)


# ---------------------------------------------------------------------------
#   5. CI keeps the code-only halves, and still has no browser to open
# ---------------------------------------------------------------------------

def _job_block(text: str, name: str) -> str:
    """One job's lines in ci.yml, from `  <name>:` to the next `  <job>:`.

    A tiny reader instead of a YAML import: `pyyaml` is installed in CI but not
    on the owner's PC, and this must run in the required backend job without a
    new dependency. Indentation is the structure: job keys sit at two spaces,
    a job's own keys at four.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.rstrip() == f"  {name}:"), None)
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[i]):
            end = i
            break
    return "\n".join(lines[start:end])


def _required_check_names() -> set:
    """The check names `backend/jarvis_github.py` calls REQUIRED_CHECKS.

    Read with `ast`, like every other pin in this file. The authority for
    "required" is the repository RULESET (id 24677804, measured 2026-10-27:
    rust, frontend, backend, backend-windows, credential-manager, powershell-5,
    phone-unit-tests); this tuple is the code's own copy of that list, and it is
    what every merge decision in the app is made from. A ci.yml job name absent
    from it is therefore not a required check for the app's own merge gate.
    """
    tree = _tree(HERE / "jarvis_github.py")
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "REQUIRED_CHECKS"
                and isinstance(node.value, (ast.Tuple, ast.List))):
            return {e.value for e in node.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


def _job_blocks(text: str) -> dict:
    """Every job under `jobs:`, name -> its lines (the same reader as `_job_block`)."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.rstrip() == "jobs:"), 0)
    names = [line.strip()[:-1] for line in lines[start:]
             if re.match(r"^  [A-Za-z0-9_-]+:\s*$", line)]
    return {name: _job_block(text, name) for name in names}


def _job_code(block: str) -> str:
    """A job's lines with its `#` comments removed - the YAML that actually RUNS.

    A text search cannot answer "does this job install a browser" over the whole
    block, because a comment is exactly where this project writes down what it
    REMOVED ("the `playwright install --with-deps chromium` step is gone"). Step
    names, `run:` bodies and `uses:` lines are kept; comment lines are not.
    """
    return "\n".join(line for line in block.splitlines()
                     if not line.lstrip().startswith("#"))


def t_ci_keeps_the_code_only_checks():
    if not CI_YML.is_file():
        check("ci.yml is where this test expects it", False, str(CI_YML))
        return
    text = CI_YML.read_text(encoding="utf-8")
    # THE JOB THAT RUNS THE SWEEP (2026-11-13). It was `backend`; since the
    # job was sharded it is `backend-shard`, and `backend` is the aggregator
    # that needs every shard - so the opt-in must be on the job that starts
    # the suites, and the required check must still be gated on that job.
    # Either shape is accepted, and each check below fails if the opt-in, the
    # job, or the gate goes away.
    backend_block = _job_block(text, "backend")
    shard_block = _job_block(text, "backend-shard")
    if shard_block and "backend/run_suites.py" in shard_block:
        sweep_job, sweep_block = "backend-shard", shard_block
    else:
        sweep_job, sweep_block = "backend", backend_block
    check(f"ci.yml has the `{sweep_job}` job that runs the backend suite sweep",
          bool(sweep_block), sweep_job)
    check(f"ci.yml's `{sweep_job}` job carries the opt-in, so the four suites' "
          f"code-only checks still run on a runner with no Playwright browser",
          bool(re.search(r'JARVIS_ALLOW_VISIBLE_BROWSER_TESTS:\s*["\']1["\']',
                         sweep_block or "")), (sweep_block or "")[:500])
    if shard_block:
        check("the required `backend` check is the aggregator over `backend-shard`",
              bool(re.search(r"needs:\s*\[?[^\]\n]*backend-shard",
                             backend_block or "")), (backend_block or "")[:400])
    # The Windows job names the four directly (the runner layer does not apply
    # there). Quoted entries only: the comment above its `env:` names them too.
    # SINCE 2026-11-27 that job is `backend-windows-shard` (a matrix), and the
    # required `backend-windows` is the aggregator over it - so the suite-list
    # pin reads the job that CARRIES the list, and the required name is checked
    # to be an aggregator rather than to hold the list. The fallback keeps this
    # readable if the two jobs are ever one again.
    windows = _job_block(text, "backend-windows-shard")
    windows_name = "backend-windows-shard" if windows else "backend-windows"
    windows = windows or _job_block(text, "backend-windows")
    check(f"ci.yml has the `{windows_name}` job", bool(windows), windows_name)
    if windows_name == "backend-windows-shard":
        required = _job_block(text, "backend-windows")
        check("the required `backend-windows` check is the aggregator over "
              "`backend-windows-shard`",
              bool(re.search(r"needs:\s*\[?[^\]\n]*backend-windows-shard",
                             required or "")), (required or "")[:400])
    for suite in GUARDED:
        check(f"ci.yml's `{windows_name}` job still runs {suite} by name",
              f"'{suite}'" in windows)


def t_no_required_backend_job_can_open_a_browser():
    """The ruling of 2026-11-17: required CI must not even be ABLE to launch a browser.

    WHY THIS PIN FLIPPED, which is the reason it is written down instead of
    reversed in silence. Until today this test demanded the OPPOSITE - that the
    required sweep job DID install a Playwright browser, "so the guard rests on
    the display switch, not on a package's absence". That was half a fix: it
    protected the four visible-browser suites from a browser they no longer
    needed to see, while leaving the browser installed in a REQUIRED job where
    they could reach it. Measured on one green run (2026-11-17): 486 s, 117 s,
    55 s and 12 s for suites whose code-only halves take under a second, and a
    Playwright `Locator.click` timed out in that job once. A guard that depends
    on a browser being absent cannot protect a job that installs one, so the
    install left the required sweep the same day and this test now pins THAT.

    WHAT IS PINNED - four halves, because any one alone would be misleading:
      * no REQUIRED backend job installs Playwright, so there is nothing to
        launch (`backend`, `backend-shard`, `backend-windows`);
      * the only jobs that DO install it are named in
        `PLAYWRIGHT_INSTALL_JOBS`, and one of them is informational - so a new
        job that installs a browser fails here until somebody writes down why;
      * nothing in ci.yml sets `JARVIS_RUN_REAL_BROWSER`, the display switch;
      * the one suite the removed install existed for is skipped BY NAME by
        `run_suites.py` when its package is absent - printed, counted, named in
        SKIPPED BY NAME, never `ok` - and ci.yml's informational
        `backend-browser-live` job is what runs it for real.

    WHAT IS NOT CLAIMED. `frontend-shard` is a REQUIRED job that installs a
    browser and must: its own tests are browser tests. This rule is about the
    backend sweep, where the browser was accidental and cost up to eight minutes
    a suite. Making "no required job can launch a browser" literally true would
    mean deleting the desktop page tests, which is not a fix.
    """
    if not CI_YML.is_file():
        check("ci.yml is where this test expects it", False, str(CI_YML))
        return
    text = CI_YML.read_text(encoding="utf-8")
    blocks = _job_blocks(text)
    check("the ci.yml job reader found the jobs it must judge",
          set(REQUIRED_BACKEND_JOBS) | PLAYWRIGHT_INSTALL_JOBS <= set(blocks),
          sorted(blocks))
    for name in REQUIRED_BACKEND_JOBS:
        code = _job_code(blocks.get(name, ""))
        check(f"ci.yml's `{name}` job does NOT install Playwright - a required job "
              f"must not be able to launch a browser",
              "playwright" not in code.lower(), code[:500])
    installs = {name for name, block in blocks.items()
                if "playwright" in _job_code(block).lower()}
    check("the only jobs that install Playwright are the two named ones - "
          "`frontend-shard` (REQUIRED, and its own tests ARE browser tests) and "
          "`backend-browser-live` (INFORMATIONAL, the live backend suite); a third "
          "means a browser was let into another job",
          installs == PLAYWRIGHT_INSTALL_JOBS, sorted(installs))
    # Comment lines are skipped here for the same reason `_job_code` skips them:
    # the comments now RECORD the switch when they explain why nothing sets it
    # ("JARVIS_RUN_REAL_BROWSER=1 is not set ..."), and a text pin that reads its
    # own explanation as a violation is the shape this project has been bitten by.
    hits = [line.strip() for line in text.splitlines()
            if not line.lstrip().startswith("#")
            and re.search(re.escape(REAL_BROWSER) + r"\s*[:=]", line)]
    check(f"nothing in ci.yml sets {REAL_BROWSER}, so no CI run can open a browser "
          f"window", not hits, hits)

    live = blocks.get("backend-browser-live", "")
    check("ci.yml has the informational `backend-browser-live` job and it runs the "
          "one suite the removed install existed for",
          "run_suites.py test_browser_control_live.py" in live, live[:600])
    required = _required_check_names()
    check("the required-check names were read out of backend/jarvis_github.py - a "
          "silent empty set would make the next check vacuous",
          bool(required) and "backend" in required, sorted(required))
    check("... so that suite still runs for real on every push, in a job no ruleset "
          "requires",
          "playwright" in _job_code(live).lower()
          and "backend-browser-live" not in required, live[:600])

    # The runner's half: a named skip, not a started suite and not a pass. The
    # package name is swapped for one that cannot exist so the branch is proved
    # on a machine that HAS Playwright - which is where this suite runs.
    check("run_suites.py maps the live suite to the module it really imports",
          getattr(R, "NEEDS_PACKAGE", {}).get("test_browser_control_live.py")
          == "playwright.sync_api", getattr(R, "NEEDS_PACKAGE", None))
    saved = dict(getattr(R, "NEEDS_PACKAGE", {}))
    try:
        R.NEEDS_PACKAGE["test_browser_control_live.py"] = "jarvis_no_such_module_xyz"
        got = R._suite_job(HERE / "test_browser_control_live.py", HERE, {})
    finally:
        R.NEEDS_PACKAGE.clear()
        R.NEEDS_PACKAGE.update(saved)
    check("a suite whose optional package is missing is reported `skip` - with the "
          "package, the reason, and where it does run",
          got["status"] == "skip" and "jarvis_no_such_module_xyz" in got["line"]
          and "backend-browser-live" in got["line"], got)
    check("... and it says out loud that a skip is not a pass",
          "A skip is not a pass" in got["line"], got)
    check("... and counts nothing at all: not a pass, not a failure",
          got["counts"] == {"passed": 0, "skipped": 0, "failed": 0}, got["counts"])


# ---------------------------------------------------------------------------
#   6. The CLI cannot start the whole fleet by accident
# ---------------------------------------------------------------------------

def _runner(args, timeout=300):
    """Run the real runner's command line, with the opt-in removed."""
    env = dict(os.environ)
    env.pop(OPT_IN, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(HERE / "run_suites.py"), *args],
        cwd=HERE, env=env, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")


def t_the_cli_cannot_start_the_fleet_by_accident():
    help_run = _runner(["--help"], timeout=120)
    out = (help_run.stdout or "") + (help_run.stderr or "")
    check("--help exits 0", help_run.returncode == 0,
          (help_run.returncode, out[-600:]))
    check("--help prints a short usage, the bare suite form and the options",
          "usage: run_suites.py" in out and "test_ui_control.py" in out
          and "--jobs" in out and OPT_IN in out, out[-900:])
    check("--help runs nothing: no backend staged, no suite summary",
          "backend:" not in out and " passed, " not in out and "ok    " not in out,
          out[-900:])

    path_run = _runner(["backend/test_ui_control.py"], timeout=120)
    out = (path_run.stdout or "") + (path_run.stderr or "")
    check("a PATH-shaped argument is refused, never silently ignored",
          path_run.returncode != 0, (path_run.returncode, out[-600:]))
    check("... and the message names the bare form to type instead",
          "test_ui_control.py" in out and "path, not a suite name" in out, out)
    check("... before anything is staged or run",
          "backend:" not in out and " passed, " not in out and "ok    " not in out,
          out[-900:])

    typo_run = _runner(["test_no_suite_is_named_this.py"], timeout=300)
    out = (typo_run.stdout or "") + (typo_run.stderr or "")
    check("an unknown bare suite name is a failure, never the whole fleet",
          typo_run.returncode != 0, (typo_run.returncode, out[-600:]))
    check("... it names the typo and the bare form to use",
          "no suite here is named" in out and "test_no_suite_is_named_this.py" in out
          and "bare file name" in out, out[-900:])
    check("... and not one suite ran",
          "ok    " not in out and "skip  " not in out, out[-900:])


def main():
    for fn in (t_each_guarded_suite_is_guarded,
               t_the_suite_refuses_end_to_end,
               t_the_runner_skips_them_by_name,
               t_the_guarded_set_is_complete,
               t_the_browser_control_visible_default_is_pinned,
               t_the_live_suite_turns_the_visible_default_off,
               t_the_browser_control_importer_set_is_pinned,
               t_one_opt_in_name_and_it_fails_closed,
               t_ci_keeps_the_code_only_checks,
               t_no_required_backend_job_can_open_a_browser,
               t_the_cli_cannot_start_the_fleet_by_accident):
        print(f"--- {fn.__name__} ---")
        try:
            fn()
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            check(f"{fn.__name__} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
