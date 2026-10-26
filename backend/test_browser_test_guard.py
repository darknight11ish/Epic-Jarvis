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
     A BACKEND-WIDE GUARANTEE: `jarvis_browser_control.py` also has a visible
     launch by default (`_HEADLESS = False`, :1284/:1460), and a new suite that
     drives IT visibly would not be caught here.
  5. THE CODE-ONLY HALVES STILL RUN IN CI. Both CI backend jobs carry
     `JARVIS_ALLOW_VISIBLE_BROWSER_TESTS: "1"`; no runner installs a Playwright
     browser, so each suite runs its code checks and its real-browser half
     prints `SKIP the real-browser half: playwright is not installed` and exits
     0 - the pre-guard behaviour, 441 checks in all. This file also pins that
     each suite still has that browser-half gate, so the opt-in cannot silently
     turn a CI run into a browser launch.
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
test_browser_test_guard.py`) or directly; it needs nothing but the repository.
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

PASSED, FAILED, SKIPPED = [], [], []

#: The one opt-in, as every file must spell it.
OPT_IN = "JARVIS_ALLOW_VISIBLE_BROWSER_TESTS"

#: The workflow whose two backend jobs run the suites on a machine with no
#: Playwright browser, and must therefore carry the opt-in.
CI_YML = HERE.parent / ".github" / "workflows" / "ci.yml"

#: Every backend suite that drives jarvis_chatbot_web's visible window.
GUARDED = ("test_chatbot_gemini.py", "test_chatbot_sites.py",
           "test_handoff.py", "test_support_widget.py")

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
    importers = set()
    for path in sorted(HERE.glob("test_*.py")):
        tree = _tree(path)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "jarvis_chatbot_web":
                found = True
            elif isinstance(node, ast.Import) and any(
                    a.name == "jarvis_chatbot_web" for a in node.names):
                found = True
        if found:
            importers.add(path.name)
    check("the guarded list is exactly the backend suites that import "
          "jarvis_chatbot_web - the module whose visible launch THESE FOUR "
          "reach (not a backend-wide guarantee: jarvis_browser_control.py has "
          "its own visible default and is not covered)",
          importers == set(GUARDED), sorted(importers))


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


def t_ci_keeps_the_code_only_checks():
    if not CI_YML.is_file():
        check("ci.yml is where this test expects it", False, str(CI_YML))
        return
    text = CI_YML.read_text(encoding="utf-8")
    for job in ("backend", "backend-windows"):
        block = _job_block(text, job)
        check(f"ci.yml has the `{job}` job", bool(block), job)
        check(f"ci.yml's `{job}` job carries the opt-in, so the four suites' "
              f"code-only checks still run on a runner with no Playwright browser",
              bool(re.search(r'JARVIS_ALLOW_VISIBLE_BROWSER_TESTS:\s*["\']1["\']',
                             block)), block[:500])
    # The Windows job names the four directly (the runner layer does not apply
    # there). Quoted entries only: the comment above its `env:` names them too.
    windows = _job_block(text, "backend-windows")
    for suite in GUARDED:
        check(f"ci.yml's `backend-windows` job still runs {suite} by name",
              f"'{suite}'" in windows)


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
               t_one_opt_in_name_and_it_fails_closed,
               t_ci_keeps_the_code_only_checks,
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
