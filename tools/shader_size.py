#!/usr/bin/env python3
"""Estimate a shader's size the way Android's shader compiler measures it.

Android compiles a face's AGSL shader with Skia in "strict ES2" mode, and in
that mode Skia refuses any shader whose flattened size is over 100,000
("error: program is too large" - it throws, and the app crashes when the face
is drawn). The rule, from Skia's own SkSLCheckProgramStructure.cpp:

  - every expression costs 1, and most statements 1;
  - a call to one of the shader's own functions costs that function's WHOLE
    size, every time it is called;
  - a `for` loop costs its body times its iteration count.

A newer Skia on a PC (skia-python) and WebGL both accept a shader that
breaks this rule, which is how the red panda first shipped over the limit and
crashed the phone's emulator test. This measures the rule instead of hoping.

It works on the desktop's GLSL copy (the same source as the phone's AGSL),
using glslang's syntax tree. glslang's tree is shaped a little differently
from Skia's, so the count is an estimate, not the exact figure: it is checked
against Nucleus (which Android accepts) and the first red panda (which it
refused), and faces are held to a margin well under the limit.

    python3 tools/shader_size.py            # every critter shader, and Nucleus
    python3 tools/shader_size.py --check    # exit 1 if a critter is over budget

Needs `glslangValidator` (Debian/Ubuntu package glslang-tools).
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 100_000
# Held to 60% of the limit: the estimate is not Skia's exact count.
BUDGET = 60_000

LINE = re.compile(r"^\d+:\d+\s(\s*)(.*)$")


def tree(glsl: str):
    """glslang's syntax tree as (depth, text) rows."""
    with tempfile.NamedTemporaryFile("w", suffix=".frag", delete=False) as f:
        f.write(glsl)
        path = f.name
    out = subprocess.run(["glslangValidator", "-i", path], capture_output=True, text=True)
    if "ERROR" in out.stdout or "ERROR" in out.stderr:
        errors = [l for l in (out.stdout + out.stderr).splitlines() if "ERROR" in l]
        sys.exit("glslang could not read the shader:\n" + "\n".join(errors[:20]))
    rows = []
    for line in out.stdout.splitlines():
        m = LINE.match(line)
        if m:
            rows.append((len(m.group(1)) // 2, m.group(2)))
    return rows


def build(rows):
    """Nest the rows into (text, children) nodes by depth."""
    root = ("root", [])
    stack = [(-1, root)]
    for depth, text in rows:
        node = (text, [])
        while stack[-1][0] >= depth:
            stack.pop()
        stack[-1][1][1].append(node)
        stack.append((depth, node))
    return root


def fname(text):
    m = re.match(r"(?:Function Definition|Function Call): ([A-Za-z_0-9]+)\(", text)
    return m.group(1) if m else None


def loop_count(cond):
    """The N in `i < N`: the loop's iteration count, as Skia unrolls it."""
    for text, kids in walk(cond):
        m = re.match(r"(\d+) \(const int\)", text)
        if m:
            return int(m.group(1))
    return 1


def walk(node):
    yield node
    for k in node[1]:
        yield from walk(k)


def measure(glsl: str) -> int:
    root = build(tree(glsl))
    funcs = {}
    for text, kids in walk(root):
        n = fname(text)
        if text.startswith("Function Definition") and n:
            funcs[n] = (text, kids)
    cache = {}

    def fsize(name):
        if name not in cache:
            cache[name] = 0  # recursion guard; shaders cannot recurse anyway
            text, kids = funcs[name]
            cache[name] = sum(cost(k) for k in kids if not k[0].startswith("Function Parameters"))
        return cache[name]

    def cost(node):
        text, kids = node
        if text.startswith("Function Call"):
            n = fname(text)
            args = sum(cost(k) for k in kids)
            return (fsize(n) if n in funcs else 1) + args
        if text.startswith("Loop with condition"):
            # glslang writes a label ("Loop Condition", "Loop Body") and puts
            # the part it names right after it, as a sibling.
            n = 1
            for i, k in enumerate(kids):
                if k[0].startswith("Loop Condition") and i + 1 < len(kids):
                    n = loop_count(kids[i + 1])
            return sum(cost(k) for k in kids) * n
        if text.startswith(("Sequence", "Function Parameters", "Loop Condition", "Loop Body",
                            "Loop Terminal Expression", "true case", "false case", "Test condition")):
            return sum(cost(k) for k in kids)
        if text.startswith("Linker Objects"):
            return 0
        # Where glslang's tree is bushier than Skia's, count what Skia counts:
        #  - `v.xyz` and `v.x` are one swizzle over `v` in Skia; glslang adds
        #    a node per component index.
        if text.startswith(("vector swizzle", "direct index")) and kids:
            rest = kids[1:]
            if all(k[0].startswith(("Sequence", "Constant")) for k in rest):
                return 1 + cost(kids[0])
        #  - a literal is one node in Skia (a vector literal, one per
        #    component plus its constructor); glslang adds a "Constant:"
        #    header above the values.
        if text.startswith("Constant:"):
            return 1 if len(kids) <= 1 else len(kids) + 1
        return 1 + sum(cost(k) for k in kids)

    return fsize("main")


def critters():
    js = (ROOT / "jarvis-desktop" / "src" / "critters-gen.js").read_text(encoding="utf-8")
    return {m.group(1): json.loads(m.group(2)) for m in re.finditer(r"  (\w+): (\".*\"),\n", js)}


def nucleus():
    html = (ROOT / "jarvis-desktop" / "src" / "faces.html").read_text(encoding="utf-8")
    common = re.search(r"const GLSL_COMMON = `(.*?)`;", html, re.S).group(1)
    body = re.search(r"const NUCLEUS_FS = GLSL_COMMON \+ `(.*?)`;", html, re.S).group(1)
    return common + body


def main():
    check = "--check" in sys.argv
    print(f"Android's limit {LIMIT:,}; critters are held to {BUDGET:,}.")
    print(f"  nucleus (accepted on Android): {measure(nucleus()):,}")
    over = []
    for name, glsl in critters().items():
        n = measure(glsl)
        flag = "OVER BUDGET" if n > BUDGET else "ok"
        print(f"  {name}: {n:,}  {flag}")
        if n > BUDGET:
            over.append(name)
    if check and over:
        sys.exit(f"over budget: {', '.join(over)} - Android would refuse or come close to refusing it")


if __name__ == "__main__":
    main()
