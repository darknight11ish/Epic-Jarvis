#!/usr/bin/env python3
"""Checks the defect register: docs/defect-register.tsv and its .md twin.

Four things are fatal, and each one is exit code 1 with the offending row
named in the message:

  a) two entries with status=open that claim the same file,
  b) an open entry naming a file that is not in the checkout,
  c) a malformed row - wrong column count, a status that is not open/closed,
     a missing id, owner, files or evidence, or a duplicate id,
  d) the .md table and the .tsv disagreeing about which defects are open.

It reads two files and nothing else: no network, no subprocesses, no import
outside the standard library. Run it from the repo root:

    py -3 tools/check_defect_register.py

`--root`, `--tsv` and `--md` exist so this same checker can be pointed at a
dirty copy in a temporary directory - which is how each failure is proved
without dirtying the real register.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The exact columns of docs/defect-register.tsv, in order, after the header.
COLUMNS = ("id", "owner", "claimed_at", "status", "files", "evidence", "checkout")
STATUSES = ("open", "closed")

# Fields a row may not leave blank. claimed_at and checkout may be blank.
REQUIRED = ("id", "owner", "status", "files", "evidence")

# A defect id in the .md table's first column, e.g. DEF-001.
MD_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
# The |---|---| separator row of a markdown table.
DASHES = re.compile(r"^-+$")


def parse_tsv(path, problems):
    """Read the .tsv. Returns the well-formed rows, appending problems."""
    try:
        # utf-8-sig so a BOM added by a Windows editor does not hide the
        # header's first column.
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        problems.append(f"{path}: cannot be read ({exc})")
        return []

    lines = text.splitlines()
    if not lines:
        problems.append(f"{path}: is empty")
        return []

    header = [h.strip() for h in lines[0].split("\t")]
    if tuple(header) != COLUMNS:
        problems.append(
            f"{path}:1: header must be exactly "
            + " ".join(COLUMNS)
            + f" as TAB-separated columns; found {len(header)} column(s): "
            + " ".join(header)
        )

    rows = []
    first_line_of = {}
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            problems.append(f"{path}:{number}: blank line")
            continue
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) != len(COLUMNS):
            problems.append(
                f"{path}:{number}: malformed row: {len(cells)} column(s), "
                f"expected {len(COLUMNS)} (TAB-separated)"
            )
            continue

        row = dict(zip(COLUMNS, cells))
        bad = False
        for field in REQUIRED:
            if not row[field]:
                problems.append(f"{path}:{number}: missing {field}")
                bad = True
        if row["status"] and row["status"] not in STATUSES:
            problems.append(
                f"{path}:{number}: status {row['status']!r} is not one of "
                + " or ".join(STATUSES)
            )
            bad = True
        if row["id"]:
            seen_at = first_line_of.get(row["id"])
            if seen_at is not None:
                problems.append(
                    f"{path}:{number}: duplicate id {row['id']!r} "
                    f"(first at line {seen_at})"
                )
                bad = True
            else:
                first_line_of[row["id"]] = number
        if bad:
            continue

        row["_line"] = number
        row["_files"] = [p.strip() for p in row["files"].split(";") if p.strip()]
        if not row["_files"]:
            problems.append(f"{path}:{number}: files names no path")
            continue
        rows.append(row)
    return rows


def check_open_files(tsv, root, rows, problems):
    """(a) two open rows sharing a file, and (b) a file not in the checkout.

    Only open rows are checked: a closed defect may name a file that has
    since been renamed or removed, and that is not a defect in the register.
    """
    claims = {}
    for row in rows:
        if row["status"] != "open":
            continue
        for rel in row["_files"]:
            target = root / rel
            if not target.exists():
                problems.append(
                    f"{tsv}:{row['_line']}: open defect {row['id']} names "
                    f"{rel}, which is not in the checkout ({target})"
                )
            claims.setdefault(rel, []).append(row["id"])

    for rel in sorted(claims):
        ids = claims[rel]
        if len(ids) > 1:
            problems.append(
                "two open defects claim the same file: "
                + " and ".join(ids)
                + f" both name {rel}"
            )


def md_open_ids(path, problems):
    """The ids in the .md table's first column. That table is the open list."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        problems.append(f"{path}: cannot be read ({exc})")
        return set()

    ids = set()
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = stripped.split("|")
        if len(cells) < 2:
            continue
        first = cells[1].strip().strip("`* ")
        if not first or first.lower() == "id" or DASHES.match(first):
            continue
        if MD_ID.match(first):
            if first in ids:
                problems.append(f"{path}:{number}: the table lists {first} twice")
            ids.add(first)
    return ids


def check_open_rows_do_not_name_a_fix(tsv, rows, problems):
    """An OPEN row whose own evidence says it is fixed contradicts itself.

    This is the one stale-row shape a script CAN see: the evidence reads
    "fixed by #255" while `status` still says `open`. It is exactly how
    DEF-004 and DEF-005 sat stale - each row's own evidence named the fix and
    the row stayed open - and this rule would have caught them the day they
    went stale.

    NOT checked here, and not to be faked: whether an open row's DESCRIPTION
    still matches the code. That needs a reader putting prose beside source,
    not a pattern; a checker that pretended to do it would be the vacuous
    check this suite exists to prevent.
    """
    names_a_fix = re.compile(r"\bfixed\s+(?:by|in)\s+(?:PR\s*)?#\d+", re.I)
    for row in rows:
        if row.get("status") != "open":
            continue
        found = names_a_fix.search(row.get("evidence") or "")
        if found:
            problems.append(
                f"{tsv}: {row.get('id')}: is open, but its own evidence names a fix "
                f"({found.group(0)!r}) - close the row or correct the evidence"
            )


def main(argv=None):
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Check docs/defect-register.tsv against "
        "docs/DEFECT-REGISTER.md."
    )
    parser.add_argument(
        "--root", default=str(here),
        help="the checkout the .tsv's file paths are relative to "
             "(default: this repo)",
    )
    parser.add_argument(
        "--tsv", default=None,
        help="the register to read (default: <root>/docs/defect-register.tsv)",
    )
    parser.add_argument(
        "--md", default=None,
        help="the human file to read (default: <root>/docs/DEFECT-REGISTER.md)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    tsv = Path(args.tsv) if args.tsv else root / "docs" / "defect-register.tsv"
    md = Path(args.md) if args.md else root / "docs" / "DEFECT-REGISTER.md"

    problems = []
    rows = parse_tsv(tsv, problems)
    check_open_files(tsv, root, rows, problems)
    check_open_rows_do_not_name_a_fix(tsv, rows, problems)

    tsv_open = {row["id"] for row in rows if row["status"] == "open"}
    listed = md_open_ids(md, problems)

    not_listed = sorted(tsv_open - listed)
    not_open = sorted(listed - tsv_open)
    if not_listed:
        problems.append(
            f"{md}: the table does not list "
            + ", ".join(not_listed)
            + " as open, which the .tsv has open"
        )
    if not_open:
        problems.append(
            f"{md}: the table lists "
            + ", ".join(not_open)
            + " as open, which the .tsv does not have open"
        )

    if problems:
        print(f"defect register FAILED: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    closed = len(rows) - len(tsv_open)
    print(f"defect register OK: {len(tsv_open)} open, {closed} closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
