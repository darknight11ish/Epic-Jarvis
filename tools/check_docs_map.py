#!/usr/bin/env python3
"""Check the two numbers `docs/README.md` states about this directory.

WHY THIS EXISTS. `docs/README.md` is the map of `docs/`, and it opens by
stating how many markdown documents are here and how big they are. Both are
hand-typed, and nothing re-measured them: on 2026-10-11 the page still said
290 documents and about 6.8 MB, measured 2026-10-06, while the tree held 342
and 8,144,671 bytes - 52 documents and a fifth of the size out of date, on
the one page a reader uses to find their way around. This repository has
already paid for an inventory nobody re-ran: `plugins/README.md` sat at 138
entries against a 139-patch stack through eighteen merges, because no CI step
checked it, until `tools/check_plugins.py` started checking it.

WHAT IT CHECKS. Both numbers, in every place the page states them - the prose
line, the comment on the page's own measuring command, and (for the size) the
reminder that calls it "around N MB". The count is checked exactly; the size
to within a tenth, because the page says "about" and "around" and tells the
reader to re-measure rather than trust the digits. A byte-exact rule would
contradict the page it is checking.

It never asks the page to keep its wording: a statement that is not there is
simply not checked, and every statement that IS there is printed before the
verdict, so a pattern that stopped matching cannot pass unnoticed. The page
failing to state a number at all is a failure.

Both numbers are measured the way the page's own command measures them -
every `*.md` under `docs/`, subfolders included, which is what
`Get-ChildItem docs -Recurse -Filter *.md` counts.

Run:  py -3 tools/check_docs_map.py
Exit: 0 when the page matches the tree, 1 otherwise, naming every difference.

`--docs` and `--readme` point it at another copy, so a failure can be proved
without dirtying the real page.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: How far the stated size may be from the measured one: a tenth. The page
#: says the size is "about" and "around", so this is the page's own looseness,
#: not a lowered bar for the count.
SIZE_SLACK = 0.10

#: One million bytes to the "MB" the page prints (6.8 MB was 6,760,000 bytes).
BYTES_PER_MB = 1_000_000

#: Where the page states the document count, and what each pattern captures.
COUNT_SPOTS = (
    ("the prose line",
     re.compile(r"There are \*\*([\d,]+) markdown documents\*\*")),
    ("the comment on the measuring command",
     re.compile(r"\.Count\s*#\s*([\d,]+)\s+documents")),
)

#: Where the page states how big `docs/` is. The third entry is a unit: "mb"
#: for the figures written in MB, "bytes" for the one written in bytes.
SIZE_SPOTS = (
    ("the prose line",
     re.compile(r"adding up to about \*\*([\d.]+)\s*MB\*\*"), "mb"),
    ("the comment on the measuring command",
     re.compile(r"Measure-Object[^\n]*#\s*about\s*([\d,]+)\s*bytes"), "bytes"),
    ("the reminder to re-measure it",
     re.compile(r'the size as "around ([\d.]+)\s*MB"'), "mb"),
)


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"{'ok   ' if cond else 'FAIL '} {name}")
    if detail and not cond:
        for line in detail.splitlines():
            print(f"        {line}")
    return cond


def documents(docs: Path) -> list[Path]:
    """Every markdown document under `docs/`, subfolders included.

    The same set the page's own `Get-ChildItem docs -Recurse -Filter *.md`
    counts. The suffix is compared lowercase, so a `.MD` on a
    case-insensitive filesystem cannot hide from either count.
    """
    return sorted(p for p in docs.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".md")


def statements(text: str, spots) -> list[tuple[str, int]]:
    """(where it is, what it says in plain bytes/count) for each statement found.

    `spots` is COUNT_SPOTS or SIZE_SPOTS. A spot that matches nothing is left
    out - the page is free to reword itself - and `main` fails only when NOTHING
    states the number.
    """
    found: list[tuple[str, int]] = []
    for spot in spots:
        where, pattern = spot[0], spot[1]
        unit = spot[2] if len(spot) > 2 else "count"
        for m in pattern.finditer(text):
            raw = m.group(1).replace(",", "")
            if unit == "mb":            # the page writes these in MB, as in 6.8 MB
                value = int(float(raw) * BYTES_PER_MB)
            else:                       # "count" and "bytes" are plain integers
                value = int(raw)
            found.append((f"{where} ({unit})", value))
    return found


def thousands(value: int) -> str:
    return f"{value:,}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the document count and size in docs/README.md "
                    "against the documents that are really there."
    )
    parser.add_argument("--docs", default=str(ROOT / "docs"),
                        help="the directory to count (default: <repo>/docs)")
    parser.add_argument("--readme", default=None,
                        help="the page to read (default: <docs>/README.md)")
    args = parser.parse_args(argv)

    docs = Path(args.docs)
    readme = Path(args.readme) if args.readme else docs / "README.md"

    if not docs.is_dir():
        print(f"docs map FAILED: {docs} is not a directory")
        return 1
    if not readme.is_file():
        print(f"docs map FAILED: {readme} is not a file")
        return 1

    files = documents(docs)
    real_count = len(files)
    real_bytes = sum(p.stat().st_size for p in files)
    text = readme.read_text(encoding="utf-8")

    counted = statements(text, COUNT_SPOTS)
    sized = statements(text, SIZE_SPOTS)
    for where, value in counted:
        print(f"found  {where} says {thousands(value)} documents")
    for where, value in sized:
        print(f"found  {where} says {thousands(value)} bytes")

    ok = True
    ok &= check(f"{readme} states how many documents there are", bool(counted),
                "neither \"There are **N markdown documents** here\" nor "
                "\"# N documents\" is on the page; this check cannot measure "
                "a number the page no longer states")
    if counted:
        ok &= check(f"every document count on the page matches the tree "
                    f"({thousands(real_count)})",
                    all(n == real_count for _, n in counted),
                    "\n".join(f"{where} says {thousands(n)}" for where, n in counted)
                    + f"\nthe tree holds {thousands(real_count)} markdown "
                      f"documents under {docs}")

    ok &= check(f"{readme} states how big {docs.name}/ is", bool(sized),
                "no size in MB and no byte figure is on the page; this check "
                "cannot measure a number the page no longer states")
    if sized:
        low = int(real_bytes * (1 - SIZE_SLACK))
        high = int(real_bytes * (1 + SIZE_SLACK))
        ok &= check(f"every size on the page is within {SIZE_SLACK:.0%} of the "
                    f"tree ({thousands(real_bytes)} bytes)",
                    all(low <= b <= high for _, b in sized),
                    "\n".join(f"{where} says {thousands(b)} bytes" for where, b in sized)
                    + f"\nthe tree holds {thousands(real_bytes)} bytes, so "
                      f"within {SIZE_SLACK:.0%} means {thousands(low)}-"
                      f"{thousands(high)}")

    if not ok:
        print(f"\ndocs map FAILED. Re-run the two lines the page prints and "
              f"put today's numbers in it:")
        print("  (Get-ChildItem docs -Recurse -Filter *.md).Count")
        print('  "{0:N0}" -f (Get-ChildItem docs -Recurse -Filter *.md | '
              "Measure-Object -Property Length -Sum).Sum")
        return 1

    print(f"\ndocs map OK: {thousands(real_count)} documents, "
          f"{thousands(real_bytes)} bytes, and {readme.name} agrees")
    return 0


if __name__ == "__main__":
    sys.exit(main())
