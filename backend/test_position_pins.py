"""tools/check_position_pins.py is the gate, and this proves it is green and honest.

    python3 backend/test_position_pins.py

WHY THIS EXISTS. `tools/check_position_pins.py` is a CEILING RATCHET against a
test pinning a POSITION in source text (`lines[951]`) instead of finding the
thing structurally or exercising the real function. A position pin passes on a
wrong value that happens to sit at the old index and fails on a right value that
moved one line - and it was `tools/check_no_source_pins.py`'s blind spot: a PR
could remove a text pin and add a position pin and the text ratchet saw only one
direction.

This suite is the proof the gate exists, runs, detects the right shape, and
cannot quietly lose either side of its measurement:

  * the tool exits 0 on this tree (the debt is inside its recorded ceilings);
  * it PRINTS the numbers, so a decrease is visible and "nothing is wrong"
    cannot be confused with "nothing was looked at";
  * `--measure` reports the SAME counts the ceiling table records, so the table
    cannot drift away from the measurement in either direction;
  * a source text read by `read_text()`/`getsource()` and indexed by a constant
    is COUNTED: `lines[950]`, `src[1200:1400]`, `src.splitlines()[3]`, `lines[-1]`;
  * the two legitimate shapes are NOT counted - a fixture (`.json`, not `.py`)
    indexed by position, and finding the thing by walking `ast` nodes;
  * the ratchet FAILS both ways, on a temp tree: a planted pin above its
    ceiling fails, the same tree with the ceiling lowered passes, and removing
    the pin while leaving the ceiling raised fails ("the ratchet only turns
    DOWN"). That is the bite proof, kept as a standing test rather than only in
    the pull request that added the checker.
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_position_pins.py"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def run(*args):
    return subprocess.run([sys.executable, "-B", str(TOOL), *args],
                          cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")


def load_module():
    spec = importlib.util.spec_from_file_location("position_pins", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tree_of(src: str) -> ast.AST:
    return ast.parse(src)


def hits(mod, src: str) -> list:
    tree = tree_of(src)
    source_names = mod._assigned_names(tree, mod._py_names(tree))
    line_names = mod._line_names(tree, source_names)
    return mod._pins(tree, source_names, line_names)


def main() -> int:
    gate = run()
    out = (gate.stdout or "") + (gate.stderr or "")
    check("the position-pin gate is green on this tree", gate.returncode == 0, out[-800:])
    check("... and it says a number, so 'nothing is wrong' cannot be 'nothing was looked at'",
          "file(s) still pin a source position" in out, out[-800:])
    check("... and it says what to do instead of pinning a position",
          "ast" in out and "ceiling" in out, out[-800:])

    measured = run("--measure")
    mout = (measured.stdout or "") + (measured.stderr or "")
    check("--measure runs", measured.returncode == 0, mout[-400:])
    mod = load_module()
    found = mod.measure()
    recorded = sum(mod.POSITION_PIN_CEILING.values())
    now = sum(len(v) for v in found.values())
    check("the recorded ceiling total equals what is measured today", recorded == now,
          f"recorded {recorded}, measured {now}")
    for f, hit_lines in found.items():
        if mod.POSITION_PIN_CEILING.get(f, 0) != len(hit_lines):
            check(f"{f}: recorded ceiling matches the measurement", False,
                  f"recorded {mod.POSITION_PIN_CEILING.get(f, 0)}, measured {len(hit_lines)}")

    # ---- what the detector must count --------------------------------------
    source_read = 'src = (HERE / "jarvis_thing.py").read_text(encoding="utf-8")\n'
    check("a line list of a source read, indexed by a constant, is counted",
          len(hits(mod, source_read + "lines = src.splitlines()\nprint(lines[950])\n")) == 1)
    check("... a negative constant index too",
          len(hits(mod, source_read + "lines = src.splitlines()\nprint(lines[-1])\n")) == 1)
    check("... a hard-coded region of the source text counts",
          len(hits(mod, source_read + "print(src[1200:1400])\n")) == 1)
    check("... and a split-and-index in one expression counts",
          len(hits(mod, source_read + 'print(src.splitlines()[3])\n')) == 1)
    check("... but a computed index is not a pin, because it cannot be displaced",
          len(hits(mod, source_read + 'i = 3\nprint(src.splitlines()[i])\n')) == 0)

    # ---- the two legitimate shapes must NOT be counted --------------------
    check("a fixture read (.json) indexed by position is data, not source - not counted",
          len(hits(mod, 'raw = (HERE / "cases.json").read_text(encoding="utf-8")\n'
                        "print(raw.splitlines()[0])\n")) == 0)
    check("finding the call by walking ast nodes is the replacement - not counted",
          len(hits(mod, source_read + "print([n for n in ast.walk(ast.parse(src))\n"
                                      "       if isinstance(n, ast.Call)])\n")) == 0)
    check("indexing an ordinary list is not a source pin",
          len(hits(mod, "rows = [1, 2, 3]\nprint(rows[0])\n")) == 0)

    # ---- the ratchet must fail in BOTH directions -------------------------
    tmp = Path(tempfile.mkdtemp(prefix="position-pins-"))
    try:
        near = tmp / "backend"
        near.mkdir()
        planted = near / "test_planted.py"
        planted.write_text('"""A planted position pin, for the reverse test."""\n'
                           "src = (HERE / \"jarvis_thing.py\").read_text()\n"
                           "lines = src.splitlines()\n"
                           "print(lines[951])\n", encoding="utf-8", newline="\n")
        old_repo, old_ceiling = mod.REPO, mod.POSITION_PIN_CEILING
        try:
            mod.REPO = tmp
            buf = io.StringIO()
            mod.POSITION_PIN_CEILING = {}
            with contextlib.redirect_stdout(buf):
                code = mod.main([])
            text = buf.getvalue()
            check("a file above its ceiling fails the gate", code == 1 and "FAIL" in text, text[-600:])
            check("... and it names the pinned line", "test_planted.py:4" in text, text[-600:])

            mod.POSITION_PIN_CEILING = {"backend/test_planted.py": 1}
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([])
            check("the same tree passes when the ceiling records it", code == 0, buf.getvalue()[-600:])

            planted.write_text('"""The pin was paid off."""\n'
                               "print([n for n in ast.walk(ast.parse('x'))])\n",
                               encoding="utf-8", newline="\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([])
            text = buf.getvalue()
            check("fixing a pin without lowering the ceiling FAILS (the ratchet only turns down)",
                  code == 1 and "only turns DOWN" in text, text[-600:])

            mod.POSITION_PIN_CEILING = {}
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([])
            check("... and with the entry lowered it passes", code == 0, buf.getvalue()[-400:])
        finally:
            mod.REPO, mod.POSITION_PIN_CEILING = old_repo, old_ceiling
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
