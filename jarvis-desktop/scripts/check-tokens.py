#!/usr/bin/env python3
"""Find colours a theme cannot reach.

A literal colour inside a `:root` or `[data-theme]` block is a token being
defined, which is what should happen. A literal anywhere else is a value
welded into a component, and no amount of theme switching will move it.

Run before and after the token refactor; the second number is the deliverable.
"""
import re, sys, pathlib

FILES = ["style.css", "widget.css", "settings.css", "brain.css", "theme.css"]
SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                   "/home/user/Epic-Jarvis/jarvis-desktop/src")
# Where defining a literal is legitimate.
DEFINING = re.compile(r'(?::root\b|\[data-theme[^\]]*\])[^{]*\{')
# `\b` alone treats `-` as a boundary, so an ID selector like `#face-frame`
# reads as the hex colour `#face` followed by `-frame` - a false positive
# this script itself was raising. CSS identifiers (and so ID selectors) can
# continue past a hyphen, so the colour must not.
HEX = re.compile(r'#[0-9a-fA-F]{3,8}\b(?![-\w])')
FUNC = re.compile(r'\b(?:rgba?|hsla?)\(')


def colours(src):
    """Every literal colour, as (offset, text).

    `rgb(var(--accent-rgb) / 0.07)` is the TOKEN form, not a literal: the hue
    comes from the theme and only the alpha is local. Telling the two apart
    needs the function's balanced body, because a naive `[^)]*` stops at the
    `)` that closes `var(` — and a lookahead over the rest of the declaration
    would wrongly forgive a real literal that merely sits beside a var, as in
    `box-shadow: 0 0 0 1px rgba(0,0,0,.6), 0 0 22px var(--glow)`.
    """
    for m in HEX.finditer(src):
        yield m.start(), m.group(0)
    for m in FUNC.finditer(src):
        depth, j = 0, m.end() - 1
        while j < len(src):
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = src[m.end():j]
        if "var(" in body:
            continue
        yield m.start(), src[m.start():j + 1]


def strip_comments(src):
    """Blank out /* ... */ but keep the byte offsets, so reported line numbers
    still point at the real line. A hex code quoted in a comment explaining why
    the token contract exists is documentation, not a leak."""
    out = list(src)
    i = 0
    while True:
        a = src.find("/*", i)
        if a < 0:
            break
        b = src.find("*/", a + 2)
        if b < 0:
            b = len(src) - 2
        for j in range(a, b + 2):
            if out[j] != "\n":
                out[j] = " "
        i = b + 2
    return "".join(out)


def blocks(src):
    out = []
    for m in DEFINING.finditer(src):
        i = src.index("{", m.start()); depth = 0; j = i
        while j < len(src):
            if src[j] == "{": depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0: break
            j += 1
        out.append((m.start(), j + 1))
    return out

total = 0
for name in FILES:
    path = SRC / name
    if not path.exists():
        print(f"{name:<14} (missing)"); continue
    src = strip_comments(path.read_text())
    spans = blocks(src)
    hits = []
    for at, text in colours(src):
        if any(a <= at < b for a, b in spans): continue
        hits.append((src[:at].count("\n") + 1, text))
    total += len(hits)
    print(f"{name:<14} {len(hits):>3} unreachable  ({len(spans)} defining block(s))")
    if "-v" in sys.argv:
        for line, colour in hits: print(f"     {name}:{line}  {colour}")
print(f"{'TOTAL':<14} {total:>3}")
sys.exit(1 if total else 0)
