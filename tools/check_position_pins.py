#!/usr/bin/env python3
"""No test may pin the POSITION of something in a source file.

    python3 tools/check_position_pins.py            # the gate
    python3 tools/check_position_pins.py --measure  # what is here today

WHY THIS EXISTS. `tools/check_no_source_pins.py` is the ratchet against a test
asserting on the source TEXT of a production module. This is its blind spot, and
the seventh failure of the same shape:

  * a **text pin** (`"invoke(\\"devices_label\\"" in src`) fails when the CONTENT
    it quotes changes - even when the change is an improvement;
  * a **position pin** (`lines[951]`) fails when the thing it points at is
    DISPLACED - one unrelated line added above it and it now reads a different
    line, silently. It passes on a wrong value that happens to sit at the old
    index, and fails on a right value that moved.

PR #525 hit the loophole exactly: replacing a `lines[951]` with a check on the
text at that index **removed** one position pin and **added** one text pin, and
the text ratchet could only see the addition. So a file can move its debt from
the counted column into the uncounted one; this counts it in both.

WHAT IT DETECTS, with `ast.parse` - never by reading source as text (which is
the disease this cures). A module-level name is a SOURCE-TEXT name when it is
assigned from:

  * `Path(...).read_text()` / `.read()` / `open(...).read()` of a `.py` path
  * `inspect.getsource(...)`
  * `subprocess.run/Popen/check_output(...)` naming git together with a
    history or tree verb (`show`, `log`, `cat-file`, `ls-tree`, `rev-list`,
    `blame`, `diff`)

A name is a LINE-ARRAY when it is assigned from `src.splitlines()`,
`src.split("\\n")`, or a region `src[a:b]` of one of those names. Then every
**hard-coded subscript** on those names is counted: `lines[951]`, `lines[-1]`,
`src[1200:1400]`, `src.splitlines()[3]`. A `.json`, `.html` or `.txt` read is
DATA, not source, and indexing a fixture is a legitimate assertion - only `.py`
reads are source (the same line `tools/check_no_source_pins.py` draws).

TWO SHAPES THAT REPLACE A POSITION PIN - and a pin should be replaced by one of
them, not by a cleverer index:

  1. FIND THE THING STRUCTURALLY: walk `ast` nodes (`any(isinstance(n, ast.Call)
     and n.func.attr == "foo" ...)`), or search for the marker text the thing is
     named by, instead of counting lines. Then replacing the line is invisible
     and the check still measures what it claims.

  2. CALL THE REAL FUNCTION, with a spy or a stub, and assert on what it
     received. A position in a file cannot drift if the position is never used.

THE CEILING RATCHET. `POSITION_PIN_CEILING` records the position pins measured on
the day this landed. A file not named there may have ZERO. A recorded number is
a CEILING: it may go down, never up - so the debt is recorded honestly and can
only be paid off, never grown. When the count goes down, lower the entry: this
checker prints both numbers so the movement is visible, and it FAILS in both
directions - above the ceiling, and above the measurement (a ceiling left high
is how the next pin gets room to slip in unnoticed).

The counts are deliberately CONSERVATIVE: a name is treated as source text for
the whole file once it is assigned from a source read anywhere, so a name reused
for something else is still counted. Over-counting only makes the ceiling
honest; under-counting would hide a pin.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Where a position pin may live: the permanent suites and the checkers.
GLOBS = ("backend/test_*.py", "tools/check_*.py", "tools/test_*.py")

#: A recorded ceiling per file. Absent = 0. May only go DOWN.
#: MEASURED ON main when this landed (2026-10-17): 16 pins in 12 files, the
#: debt as it stands. A ceiling may go DOWN only - these are not approvals,
#: they are what the tool found on the day it landed, so an increase is caught
#: and a decrease is visible. The counts are deliberately conservative (a name
#: reused after a source read still counts), so a few are a generic local name
#: that happens to share a source-read name; over-counting keeps the ceiling
#: honest and the next pin cannot hide behind it.
POSITION_PIN_CEILING: dict[str, int] = {
    "backend/test_big_model.py": 2,
    "backend/test_browser_engine.py": 1,
    "backend/test_chatbot.py": 2,
    "backend/test_chatbot_privacy.py": 1,
    "backend/test_chatbot_routes.py": 1,
    "backend/test_cloud_say_yes.py": 1,
    "backend/test_obscura.py": 2,
    "backend/test_security_pc.py": 1,
    "backend/test_stop_all.py": 1,
    "backend/test_tasks.py": 1,
    "backend/test_tellme.py": 1,
    "backend/test_wiki.py": 2,
}

#: git args that read history or a tree rather than the working directory.
GIT_READS = ("show", "log", "cat-file", "ls-tree", "rev-list", "blame", "diff",
             "diff-tree", "merge-base", "rev-parse")

#: subprocess entry points whose output can be source text.
SUBPROCESS = ("run", "Popen", "check_output", "check_call", "call")

#: methods that turn source text into a list of lines.
LINE_SPLITTERS = ("splitlines", "split")


def _attr_chain(node) -> list[str]:
    """[names and attribute names] along a dotted expression, innermost first."""
    out: list[str] = []
    while isinstance(node, ast.Attribute):
        out.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        out.append(node.id)
    return out


def _py_names(tree: ast.AST) -> set[str]:
    """Names assigned from an expression that names a `.py` path.

    `SOURCE = HERE / "jarvis_widgets.py"` then `SOURCE.read_text()` is a source
    read; `FIXTURE / "cases.json"` is data, not source, and indexing it is a
    fixture assertion, not the disease this cures."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None:
            continue
        if not any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                   and n.value.endswith(".py") for n in ast.walk(value)):
            continue
        for t in (getattr(node, "targets", None) or [getattr(node, "target", None)]):
            if isinstance(t, ast.Name):
                names.add(t.id)
    return names


def _is_source_read(node, py_names: set[str]) -> bool:
    """Is this Call an expression that returns the TEXT of a `.py` module?"""
    if not isinstance(node, ast.Call):
        return False
    chain = _attr_chain(node.func)
    if not chain:
        return False
    if chain[-1] == "getsource":
        return True
    if chain[-1] in ("read_text", "read"):
        recv = node.func.value if isinstance(node.func, ast.Attribute) else node
        return any(
            (isinstance(n, ast.Constant) and isinstance(n.value, str)
             and n.value.endswith(".py"))
            or (isinstance(n, ast.Name) and n.id in py_names)
            for n in ast.walk(recv))
    if chain[-1] in SUBPROCESS and any(n == "subprocess" for n in chain):
        words = [n.value for n in ast.walk(node)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]
        return ("git" in words and any(w in GIT_READS for w in words)
                and (any(w.endswith(".py") for w in words)
                     or any(n in py_names for n in names)))
    return False


def _assigned_names(tree: ast.AST, py_names: set[str]) -> set[str]:
    """Every name assigned anywhere from a source read (module-wide, conservative)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            continue
        value = getattr(node, "value", None)
        if value is None:
            continue
        if not any(_is_source_read(n, py_names) for n in ast.walk(value)
                   if isinstance(n, ast.Call)):
            continue
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        for t in targets:
            if isinstance(t, ast.Name):
                names.add(t.id)
    return names


def _is_lines_call(node, source_names: set[str]) -> bool:
    """`src.splitlines()` / `src.split("\\n")` on a source-text name."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in LINE_SPLITTERS):
        return False
    recv = node.func.value
    return isinstance(recv, ast.Name) and recv.id in source_names


def _is_region(node, source_names: set[str]) -> bool:
    """`src[a:b]` - a hard-coded region of a source read."""
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id in source_names
            and _constant_index(node.slice))


def _line_names(tree: ast.AST, source_names: set[str]) -> set[str]:
    """Names that hold the LINES of a source read, or a region of one."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            continue
        value = getattr(node, "value", None)
        if value is None:
            continue
        if not (any(_is_lines_call(n, source_names) for n in ast.walk(value)
                    if isinstance(n, ast.Call))
                or any(_is_region(n, source_names) for n in ast.walk(value))):
            continue
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        for t in targets:
            if isinstance(t, ast.Name):
                names.add(t.id)
    return names


def _constant_index(node) -> bool:
    """An integer constant, or a slice with any constant integer bound."""
    # Python < 3.9 wrapped the subscript in ast.Index; unwrap it when present.
    index_cls = getattr(ast, "Index", None)
    if index_cls is not None and isinstance(node, index_cls):  # pragma: no cover
        node = node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand                      # -1 and +1 are positions
    if isinstance(node, ast.Constant):
        return isinstance(node.value, int) and not isinstance(node.value, bool)
    if isinstance(node, ast.Slice):
        bounds = [node.lower, node.upper, node.step]
        return any(_constant_index(b) for b in bounds if b is not None)
    return False


def _pins(tree: ast.AST, source_names: set[str], line_names: set[str]) -> list[int]:
    """The line numbers where a hard-coded position indexes source text."""
    lines: list[int] = []
    subjects = source_names | line_names
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        value = node.value
        is_lines = _is_lines_call(value, subjects)
        direct = isinstance(value, ast.Name) and value.id in subjects
        if (is_lines or direct) and _constant_index(node.slice):
            lines.append(node.lineno)
    return sorted(set(lines))


def measure() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for pattern in GLOBS:
        for path in sorted(REPO.glob(pattern)):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            except (SyntaxError, UnicodeDecodeError) as exc:
                print(f"SKIP  {path.relative_to(REPO)}: could not be parsed ({exc})")
                continue
            source_names = _assigned_names(tree, _py_names(tree))
            if not source_names:
                continue
            line_names = _line_names(tree, source_names)
            hits = _pins(tree, source_names, line_names)
            if hits:
                found[str(path.relative_to(REPO)).replace("\\", "/")] = hits
    return found


def main(argv: list[str]) -> int:
    found = measure()
    total_now = sum(len(v) for v in found.values())
    total_was = sum(POSITION_PIN_CEILING.get(f, 0) for f in found) + sum(
        n for f, n in POSITION_PIN_CEILING.items() if f not in found)

    if "--measure" in argv:
        for f, hits in sorted(found.items()):
            print(f"{len(hits):4d}  {f}")
            for line in hits:
                print(f"        {f}:{line}")
        print(f"\n{len(found)} file(s), {total_now} position pin(s) - measured on "
              f"{REPO.name}")
        return 0

    failed = 0
    for f, hits in sorted(found.items()):
        ceiling = POSITION_PIN_CEILING.get(f, 0)
        if len(hits) > ceiling:
            failed += 1
            print(f"FAIL  {f}: {len(hits)} position pin(s), ceiling {ceiling}")
            for line in hits:
                print(f"        {f}:{line}")
            print("      a hard-coded position in source text goes red when an unrelated "
                  "line is added above it, and stays green when a different value sits at "
                  "the old index. Find the thing structurally (walk `ast` nodes, or search "
                  "for the marker it is named by), or call the real function and assert on "
                  "what it received.")

    for f, ceiling in sorted(POSITION_PIN_CEILING.items()):
        now = len(found.get(f, []))
        if now < ceiling:
            failed += 1
            print(f"FAIL  {f}: the recorded ceiling is {ceiling} but {now} is measured - "
                  f"the debt was paid, or the entry was raised")
            print("      lower the entry to the measurement: this ratchet only turns DOWN. "
                  "A ceiling left above the real count is how the next pin gets room to "
                  "slip in unnoticed.")

    if found:
        print(f"\n{len(found)} file(s) still pin a source position (was {total_was}):")
        for f, hits in sorted(found.items()):
            print(f"  {f}: " + ", ".join(f"{f}:{n}" for n in hits))
    else:
        print("no file pins a position in source text")

    if failed:
        print(f"\n{failed} file(s) above their ceiling")
        return 1
    print("\nevery position pin is at or below its recorded ceiling; find the thing "
          "structurally (walk `ast` nodes) or call the real function instead")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
