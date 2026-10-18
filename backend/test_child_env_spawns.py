"""A structural guard: every backend child spawn gets a filtered environment.

2026-10-18, audit F1. `sidecar.rs:497` can put the pairing token into the
backend's own environment (`HUD_TOKEN`). A child started with `subprocess.*`
and no `env=` inherits it, plus every other secret the owner has exported - so
the rule is: every spawn either passes an environment or is on the small,
reviewed allow-list below (only calls whose environment arrives another way).

This is a STRUCTURAL test, not a grep: the file's syntax tree is walked, so a
call split over lines, an `env=` moved into a dict, or a new spawn added
anywhere in `backend/jarvis_*.py` is seen. A stale allow-list entry fails too,
so an exception cannot stay behind after its call changes.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILED, PASSED = [], []
SPAWN = {
    ("subprocess", "Popen"), ("subprocess", "run"), ("subprocess", "call"),
    ("subprocess", "check_output"), ("subprocess", "check_call"),
    ("os", "system"),
}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


@dataclass(frozen=True)
class Reviewed:
    """One spawn whose environment is handled, but not by a literal `env=`."""
    file: str
    function: str
    why: str


#: The only reviewed exceptions. Each is checked to still exist, so this list
#: cannot quietly outlive the call it describes.
ALLOWED = (
    Reviewed("jarvis_mcp.py", "__init__",
             "Popen(argv, **common); `common` carries env=env at line 696, built from "
             "jarvis_child_env.inherited() plus the server's own configured names"),
    Reviewed("jarvis_mcp.py", "_spawn_windows",
             "Popen(argv, **common); the same env as the POSIX branch"),
)


def _calls(tree: ast.AST):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def function_of(node):
        cursor = node
        while cursor in parents:
            cursor = parents[cursor]
            if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cursor.name
        return "<module>"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
            key = (fn.value.id, fn.attr)
        else:
            continue
        if key not in SPAWN:
            continue
        yield node, function_of(node)


def main() -> int:
    found = 0
    matched = set()
    for path in sorted(HERE.glob("jarvis_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            check(f"{path.name} parses", False, exc)
            continue
        for node, function in _calls(tree):
            found += 1
            has_env = any(kw.arg == "env" for kw in node.keywords)
            reviewed = next((r for r in ALLOWED
                             if r.file == path.name and r.function == function), None)
            if has_env:
                check(f"{path.name}:{node.lineno} {function}: passes env=", True)
                continue
            if reviewed is not None:
                matched.add(reviewed)
                check(f"{path.name}:{node.lineno} {function}: reviewed exception", True,
                      reviewed.why)
                continue
            check(f"{path.name}:{node.lineno} {function}: passes env= or is reviewed",
                  False, "a child here would inherit HUD_TOKEN/JARVIS_TOKEN")
    check("the scan found the backend's real spawns (not an empty tree)", found >= 20, found)
    for entry in ALLOWED:
        check(f"the reviewed exception is still real: {entry.file}:{entry.function}",
              entry in matched, entry.why if entry in matched else "no such spawn any more")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
