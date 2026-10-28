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
  4. A LOCAL `skip()` helper that counts its skip as a PASS - `PASSED.append(
     name)` inside `skip()`, `passed += 1`, or a call to the suite's own
     `check(name, True)` from there. This is the shape that hid for months in
     `backend/test_public_tunnel_refusal_order.py:58-60` and
     `backend/test_origin_hud_header.py:62-64`: both suites printed
     `2 passed, 0 failed` and exit 0 in the required `backend` job while every
     check of theirs had been skipped, so the job's green claimed two security
     properties had been re-proved when nothing had been read. The suite's own
     `check()` says which list a pass goes in - the tool reads it from there
     rather than assuming a name - and a `skip()` that writes to it is reported
     wherever it appears, because no run can then tell a skip from a pass.

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

#: The list and counter names that mean "a pass" even when the suite's own
#: `check()` cannot be read (a helper defined somewhere else, a harness that
#: records passes some other way). Checked against a name a `skip()` writes to.
PASS_NAME = re.compile(r"^(?:passed|passes|passing|pass|pss|ok|oks|good|"
                       r"succeeded|successes|n_?passed|num_?passed)$", re.I)

#: The names a suite gives its local "this check could not run" helper. The
#: project's convention is `skip()`; the longer forms are only here because a
#: suite that renames it must not thereby escape rule 4.
SKIP_NAMES = ("skip", "skipped", "skip_check", "note_skip", "skip_this")

#: The methods that MUTATE a list. `append` inside `skip()` is the shape that
#: was shipped; the rest would be the same bug spelled differently.
MUTATORS = ("append", "extend", "insert", "add", "update", "appendall")


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


def pass_names(tree: ast.Module) -> set[str]:
    """The names a file's own `check()` writes a PASS into.

    Read from the harness rather than assumed: every one of these suites writes
    `(FAILED if not cond else PASSED).append(name)`, so the list `check()`
    appends to (anywhere inside it) is the list a pass lands in, and a `skip()`
    that touches one of them makes a skip indistinguishable from a pass. A
    suite whose harness records passes some other way contributes nothing here
    and is covered by `PASS_NAME` below instead.
    """
    names: set[str] = set()
    found = harnesses(tree)
    if not found:
        return names
    for node in ast.walk(found[0]):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in MUTATORS):
            # EVERY name the receiver mentions, not only a bare one:
            # `(FAILED if not cond else PASSED).append(name)` is how almost
            # every suite in this folder writes it, and asking for
            # `func.value.id` found nothing at all - the rule then could not
            # see the very shape it exists for (measured: it reported 0
            # findings on the old test_public_tunnel_refusal_order.py).
            for part in ast.walk(node.func.value):
                if isinstance(part, ast.Name):
                    names.add(part.id)
        elif isinstance(node, (ast.AugAssign, ast.Assign)):
            for target in ([node.target] if isinstance(node, ast.AugAssign) else node.targets):
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _names_a_pass(name: str, passes: set[str]) -> bool:
    return name in passes or bool(PASS_NAME.match(name))


def _receiver_names(node: ast.AST) -> set[str]:
    """Every name an expression mentions - see `pass_names` for why not just one."""
    return {part.id for part in ast.walk(node) if isinstance(part, ast.Name)}


def _counts_a_pass(node: ast.stmt, passes: set[str]) -> bool:
    """Is this one STATEMENT writing a pass into the suite's own total?

    A statement, not an expression: `PASSED.append(name)` is an `ast.Expr`
    wrapping the call, and looking for `ast.Call` nodes among statements found
    nothing (measured on the old suites: 0 findings)."""
    if isinstance(node, ast.AugAssign):                     # passed += 1
        target = node.target
        if isinstance(target, ast.Subscript):               # PASSED[0] += ...
            target = target.value
        if isinstance(target, ast.Attribute):               # self.passed += 1
            target = target.value
        return isinstance(target, ast.Name) and _names_a_pass(target.id, passes)
    if isinstance(node, ast.Assign):                        # passed = passed + 1
        return any(isinstance(t, ast.Name) and _names_a_pass(t.id, passes)
                   and any(isinstance(n, ast.Name) and n.id == t.id
                           for n in ast.walk(node.value))
                   for t in node.targets)
    call = node.value if isinstance(node, ast.Expr) else None
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if isinstance(func, ast.Name) and func.id == "check":
        # `skip()` counting a pass through the harness itself. Only
        # `check(name, False)` could be argued for, and that records a FAILURE
        # where a skip belongs, so both are reported.
        return True
    if isinstance(func, ast.Attribute) and func.attr in MUTATORS:
        return any(_names_a_pass(n, passes) for n in _receiver_names(func.value))
    return False


def skip_findings(tree: ast.Module) -> list[tuple[int, str, str]]:
    """(line, rule, what) for every local `skip()` that counts a PASS.

    RULE 4 OF THIS TOOL. A `skip()` helper exists to say a check could not run
    here; the project's rule is that such a check is counted on its own line and
    NEVER as a pass (CLAUDE.md, "BLOCKED and NOT-TESTABLE are never counted as
    passes"). `PASSED.append(name)` inside `skip()` breaks that silently: the
    suite's summary reads `2 passed, 0 failed`, `backend/run_suites.py` sees
    exit 0 and two passes, and the required job's green then claims a check that
    was never made. That is exactly what F-01/F-03 of the 2026-10-27 partner
    audit found in two security suites, and why this rule exists.
    """
    out: list[tuple[int, str, str]] = []
    passes = pass_names(tree)
    for fn in tree.body:
        if not (isinstance(fn, ast.FunctionDef) and fn.name in SKIP_NAMES):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.stmt) and _counts_a_pass(node, passes):
                out.append((node.lineno,
                            "a skip() that counts a PASS - a skip is never a pass",
                            source_of(node)[:150]))
    return out


#: What `findings()` hands back: problems, unreadable, and the constants `-v`
#: prints as controls it let through.
FINDINGS = tuple

def findings(tree: ast.Module, rel: str):
    """(problems, unreadable, accepted) for one parsed suite, as main() reports
    them.

    Split out so `backend/test_vacuous_checks.py` can prove every rule against
    source it writes in the test, instead of only against whatever the tree
    happens to contain today."""
    problems: list[tuple[str, int, str, str]] = []
    unreadable: list[tuple[str, str]] = []
    accepted: list[tuple[str, int, str]] = []
    found = harnesses(tree)
    if not found:
        # No `def check` at module level: either a unittest module or a file
        # that builds its checks some other way. Nothing here to judge, and
        # guessing a signature would be worse than silence.
        return problems, unreadable, accepted
    fn = found[0]
    at = condition_index(fn)
    if at is None:
        unreadable.append((rel, "its `def check` has no parameter this tool "
                                "recognises as the condition"))
        return problems, unreadable, accepted
    if fn.args.defaults and at >= len(fn.args.args) - len(fn.args.defaults):
        problems.append((rel, fn.lineno, "a check that can be called with no "
                         "condition at all",
                         f"def {fn.name}({', '.join(a.arg for a in fn.args.args)}): "
                         f"gives `{fn.args.args[at].arg}` a default, so "
                         f"`check(<name>)` is a pass by construction"))

    for call in check_sites(tree):
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

    # Rule 4 last, so a suite whose skip() also calls check(..., True) is
    # reported for both reasons rather than the first one hiding the second.
    problems += [(rel, line, rule, what) for line, rule, what in skip_findings(tree)]
    return problems, unreadable, accepted


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

            got, bad, ok = findings(tree, rel)
            problems += got
            unreadable += bad
            accepted += ok
            sites += len(list(check_sites(tree)))

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
          f"is a fake skip, none has a string or defaulted condition, and no "
          f"skip() counts a pass.")
    print("A `check(\"SKIP - ...\", True)` - or a `skip()` that appends to PASSED - is "
          "counted as a PASS by the suite and by backend/run_suites.py; the project's "
          "answer is a real `skip(why)`, counted on its own line and never as a pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
