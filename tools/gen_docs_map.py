#!/usr/bin/env python3
"""Write the two numbers `docs/README.md` states about this directory.

WHY THIS EXISTS. `tools/check_docs_map.py` checks the document count and the
size of `docs/` in every place the page states them, and fails when they are
stale. Correcting them meant a person re-running the page's two commands and
typing the results - and typing the size CHANGES the size: on 2026-10-11 two
consecutive runs of the checker on ONE tree moved the byte figure
8,417,863 -> 8,417,870, because writing it into the page changed the page
(DEF-011). A hand-typed figure that changes when you write it cannot be left
correct, and every docs pull request that edited it conflicted with every other
one by construction.

WHAT IT DOES. It measures the tree the way the checker does - importing
`check_docs_map`, so there is ONE definition of where the numbers live and how
they are measured, never a second copy that can drift - and rewrites the digits
in every spot the checker reads:

    count  the prose line, and the comment on the measuring command;
    size   the prose line (MB), the comment (bytes), and the "around N MB"
           reminder.

The wording is never touched, only the number inside it, so the page keeps
saying "about" and "around" and the checker's tenth-of-a-size looseness still
applies. Then it runs the checker on what it wrote and fails if the checker is
not satisfied, so this tool cannot produce a page its own authority rejects.

It also reports any place still stating the OLD number that the checker does not
read - a spot this generator cannot write because nothing defines it - because a
page half-updated is worse than one left alone.

Run:  py -3 tools/gen_docs_map.py            # write the measured numbers
      py -3 tools/gen_docs_map.py --check    # write nothing; fail if it would
Exit: 0 when the page states the measured numbers (and the checker agrees),
      1 otherwise, naming what it could not write.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent


def _checker():
    """`check_docs_map`, loaded by path: the spots and the measurement are its
    own, so this tool and the check that judges it cannot disagree."""
    spec = importlib.util.spec_from_file_location(
        "check_docs_map", TOOLS / "check_docs_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mb(byte_count: int, module) -> str:
    """The page writes MB to one decimal (8.3), which is inside the checker's
    tenth: 0.05 MB of rounding on millions of bytes."""
    return f"{byte_count / module.BYTES_PER_MB:.1f}"


def _swap(pattern: re.Pattern, new: str):
    def replace(m):
        return m.group(0).replace(m.group(1), new)
    return replace


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the document count and size into docs/README.md, "
                    "in every spot tools/check_docs_map.py reads.")
    parser.add_argument("--docs", default=str(ROOT / "docs"),
                        help="the directory to measure (default: <repo>/docs)")
    parser.add_argument("--readme", default=None,
                        help="the page to write (default: <docs>/README.md)")
    parser.add_argument("--check", action="store_true",
                        help="write nothing; fail if the page would change")
    args = parser.parse_args(argv)

    module = _checker()
    docs = Path(args.docs)
    readme = Path(args.readme) if args.readme else docs / "README.md"
    if not docs.is_dir() or not readme.is_file():
        print(f"gen docs map FAILED: {docs} or {readme} is missing")
        return 1

    files = module.documents(docs)
    real_count = len(files)
    # The page is INSIDE the directory it measures, so its own bytes count: the
    # size moves every time the figure is written into it (DEF-011). Everything
    # except this page is therefore measured once, and the page's own length is
    # added per candidate.
    others = sum(p.stat().st_size for p in files if p.resolve() != readme.resolve())
    original = readme.read_text(encoding="utf-8")

    def render(page: str) -> str:
        """`page` with every spot set to the measured values, the page's own
        bytes counted in, so the figure and the file it lives in agree."""
        measured = others + len(page.encode("utf-8"))
        out = page
        for spot in module.COUNT_SPOTS:
            out = spot[1].sub(_swap(spot[1], module.thousands(real_count)), out)
        for spot in module.SIZE_SPOTS:
            unit = spot[2] if len(spot) > 2 else "bytes"
            value = mb(measured, module) if unit == "mb" else module.thousands(measured)
            out = spot[1].sub(_swap(spot[1], value), out)
        return out

    # Iterate to the fixed point: writing the figure changes the figure, and one
    # pass is not enough when the digits' own length changes.
    text = original
    for _ in range(10):
        nxt = render(text)
        if nxt == text:
            break
        text = nxt
    else:
        print("gen docs map FAILED: the page's own size does not settle after ten "
              "passes - writing the figure keeps changing it; report this rather "
              "than committing a number that is wrong the moment it is written")
        return 1

    written = []
    for spot in module.COUNT_SPOTS:
        written.append((f"{spot[0]} (count)", len(spot[1].findall(original))))
    for spot in module.SIZE_SPOTS:
        unit = spot[2] if len(spot) > 2 else "bytes"
        written.append((f"{spot[0]} ({unit})", len(spot[1].findall(original))))

    for where, n in written:
        print(f"{'found' if n else 'none '} {where}: {n} spot(s)")

    counts = sum(n for where, n in written if "(count)" in where)
    sizes = sum(n for where, n in written if "(count)" not in where)
    if not counts or not sizes:
        print("gen docs map FAILED: the page states no count or no size in any "
              "spot the checker reads, so there is nothing to write - correct "
              "the page's wording first")
        return 1

    # A spot the checker does NOT read cannot be written by this tool: report it
    # rather than leaving a page that disagrees with itself.
    readable = module.COUNT_SPOTS + module.SIZE_SPOTS
    for old_number in sorted({m.group(1) for s in readable for m in s[1].finditer(original)}):
        if old_number not in text:
            continue                      # it was replaced, which is the point
        for number, line in enumerate(text.splitlines(), start=1):
            if old_number in line and not any(s[1].search(line) for s in readable):
                print(f"WARN  line {number} still states {old_number} where the "
                      f"checker does not read it: {line.strip()[:110]}")

    changed = text != original
    if args.check:
        if changed:
            print("gen docs map FAILED: the page would change; run it without "
                  "--check and commit what it writes")
            return 1
        print("gen docs map OK: the page already states the measured numbers")
    else:
        if changed:
            readme.write_text(text, encoding="utf-8", newline="\n")
            print(f"gen docs map: wrote {readme}")
        else:
            print("gen docs map: nothing to change")

    verdict = module.main(["--docs", str(docs), "--readme", str(readme)])
    if verdict != 0:
        print("gen docs map FAILED: the checker rejects what this tool wrote")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
