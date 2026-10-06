#!/usr/bin/env python3
"""Find a backend suite check that cannot fail: `check("...", True)`.

    python3 tools/check_vacuous_checks.py [-v]

WHY

On 2026-10-05 this repository found 153 checks in 74 suite files that printed
`ok` while testing nothing at all. Each was `check("SKIP - <reason>", True)`:
the condition was the constant `True`, so the check was counted as a PASS in
the suite's own "N passed" line and in `backend/run_suites.py`'s total. A real
`skip(why)` - counted on its own line, never as a pass - replaced every one.

It came back. On 2026-10-06 the same AST sweep was run again and found 24 more
of exactly the same shape, in 14 files - `check("SKIPPED (this system has no
time.tzset ...)", True)`, `check("(MarkItDown is not installed here - real
conversion skipped)", True)`, `check("SKIP - no jarvis_gate.py here ...", True)`
- every one of them a check the machine had just announced it could not run,
printed as a pass. Two more suites carried the same lie without the word
"skip" in it: a summary line `check("end to end, every one of them stays a
card", True)` that printed `ok` even on the run where the loop above it had
just printed `FAIL` for a phrasing, and `check("the rule, all cases", True)`
over a loop of cases with no `break`.

That is why this is a check and not a habit. The rule is narrow on purpose, so
that everything it reports is a real finding:

  1. A `check()` whose CONDITION is the literal `True` while its own words say
     the check could not run. The suite's own argument is the evidence: if the
     text says a reason it cannot test something here, the project's answer is
     `skip(why)`, which is counted separately - never a pass.
  2. A `check()` whose CONDITION is a non-empty string. A string is always
     truthy, so such a check passes whatever the code does. This is also what a
     swapped-argument call looks like in the one suite whose harness is
     `check(ok, what)` (backend/test_gate_stack_clean.py); that harness is read
     from its own `def check`, not assumed.
  3. A harness whose condition has a DEFAULT (`def check(name, cond=True)`): it
     can then be called with no condition at all, and that call is a pass by
     construction.

WHAT IT DELIBERATELY DOES NOT REPORT. `check(name, True)` is legitimate in two
shapes the AST can see, and both are used widely here:

  * `try: <something that must not raise>; check(name, True)
     except Whatever: check(name, False)` - reaching the `True` IS the proof
     (the same pair backwards pins a refusal);
  * a control that stands for a check made by something else in the same block
     (`with NoNetwork(): ...` then `check("... opened no socket", True)`, or a
     `for ... else:` whose loop body `break`s on a `check(..., False)`).

Those are all reached only because an earlier statement did not raise or a
branch was taken - and every one of them is reported by `-v` so a reader can
see what the rule let through. What is left out is the point of the tool: a
report that names 371 sites teaches nobody anything.

A file that will not parse is a FAILURE, not a pass: its checks were not
looked at, and silence about that is how this whole class starts.
"""
from __future__ import annotations

import ast
import re
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"

#: The suites, by the name the runner and CI know them by.
SUITE_GLOBS = ("test_*.py", "eval_*.py")

#: The words a suite uses when it is telling the reader it could not run the
#: check. Matched against every argument of the call, not just the name: the
#: sqlite-vec family put it in the third argument instead
#: (`check("a NaN row is not written", True, "sqlite-vec absent; skipped")`).
SKIP_WORDS = re.compile(
    r"\bskip(?:s|ped)?\b"
    r"|not installed here"
    r"|not in this checkout"
    r"|not available here"
    r"|cannot be made here"
    r"|not proven",
    re.I)

#: `def check(...)`: the parameter whose argument is the condition. A harness
#: names it one of these; `fn` is test_appearance.py's callable-taking harness,
#: where a string in that position would be called and raise.
COND_PARAMS = ("cond", "condition", "ok", "fn")


def harnesses(tree: ast.Module) -> list[ast.FunctionDef]:
    return [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "check"]


def condition_index(fn: ast.FunctionDef) -> int | None:
    """Which positional argument of this suite's `check()` holds the condition."""
    for i, arg in enumerate(fn.args.args):
        if arg.arg in COND_PARAMS:
            return i
    return None


def literal(node: ast.AST):
    """(is a literal, the value) - for the constants that make a check vacuous."""
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.Name) and node.id in ("True", "False"):
        return True, node.id == "True"
    return False, None


def source_of(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:                                   # pragma: no cover
        return ""


def check_sites(tree: ast.Module):
    """Every `check(...)` call in the file, with the harness it will reach.

    Only bare `check` is followed: the class methods named `check` in
    test_selftest_preflight.py, test_standby_schedule.py and test_topics.py are
    `self.check(...)`/`cls.check(...)`, a different thing with a different
    signature, and they are not this tool's business.
    """
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "check"):
            yield node


def main() -> int:
    verbose = "-v" in sys.argv
    problems: list[tuple[str, int, str, str]] = []      # file, line, rule, what
    unreadable: list[tuple[str, str]] = []
    accepted: list[tuple[str, int, str]] = []           # what -v prints
    files = 0
    sites = 0

    for pattern in SUITE_GLOBS:
        for path in sorted(BACKEND.glob(pattern)):
            files += 1
            rel = path.relative_to(REPO).as_posix()
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as err:
                unreadable.append((rel, str(err)))
                continue
            try:
                # A file with `"\p"` in a regex raises a SyntaxWarning while it
                # parses - real, but not this check's news.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    tree = ast.parse(text)
            except SyntaxError as err:
                unreadable.append((rel, f"line {err.lineno}: {err.msg}"))
                continue

            found = harnesses(tree)
            if not found:
                # No `def check` at module level: either a unittest module or a
                # file that builds its checks some other way. Nothing here to
                # judge, and guessing a signature would be worse than silence.
                continue
            fn = found[0]
            at = condition_index(fn)
            if at is None:
                unreadable.append((rel, "its `def check` has no parameter this tool "
                                        "recognises as the condition"))
                continue
            if fn.args.defaults and at >= len(fn.args.args) - len(fn.args.defaults):
                problems.append((rel, fn.lineno, "a check that can be called with no "
                                 "condition at all",
                                 f"def {fn.name}({', '.join(a.arg for a in fn.args.args)}): "
                                 f"gives `{fn.args.args[at].arg}` a default, so "
                                 f"`check(<name>)` is a pass by construction"))

            for call in check_sites(tree):
                sites += 1
                args = call.args
                if at >= len(args):
                    problems.append((rel, call.lineno, "a check() with no condition",
                                     source_of(call)))
                    continue
                node = args[at]
                is_literal, value = literal(node)
                words = " ".join(source_of(a) for a in args)
                if is_literal and value is True and SKIP_WORDS.search(words):
                    problems.append((rel, call.lineno,
                                     "a fake skip: the condition is the constant True "
                                     "and the words say it could not run",
                                     source_of(call)[:150]))
                    continue
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and node.value.strip():
                    problems.append((rel, call.lineno,
                                     "a string used as the condition (always truthy)",
                                     source_of(call)[:150]))
                    continue
                if is_literal:
                    accepted.append((rel, call.lineno, source_of(call)[:150]))

    for rel, why in unreadable:
        print(f"::error::a suite could not be read, so its checks were NOT looked at - "
              f"silence here would be this check passing having checked nothing:")
        print(f"  {rel}  {why}")

    if problems:
        print(f"::error::a suite check cannot fail - it is counted as a pass whatever "
              f"the code does:")
        for rel, line, rule, what in sorted(problems, key=lambda p: (p[0], p[1])):
            print(f"  {rel}:{line}  {rule}")
            print(f"      {what}")

    if verbose:
        print(f"\n{len(accepted)} constant condition(s) this check accepts as a real "
              f"control (reached only because an earlier statement did not raise or a "
              f"branch was taken):")
        for rel, line, what in accepted:
            print(f"  {rel}:{line}  {what}")

    if problems or unreadable:
        return 1

    print(f"{files} suite file(s) read, {sites} check() call(s) looked at: no check "
          f"is a fake skip, none has a string or defaulted condition.")
    print("A `check(\"SKIP - ...\", True)` is counted as a PASS by the suite and by "
          "backend/run_suites.py; the project's answer is a real `skip(why)`, which is "
          "counted on its own line and never as a pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
