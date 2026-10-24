#!/usr/bin/env python3
"""Roll CHANGELOG fragments into `CHANGELOG.md`, or check them.

THE RACE THIS ENDS. Every pull request that had a user-visible change appended
its entry at the top of `CHANGELOG.md` - one shared place, by construction. Two
such pull requests therefore changed the same lines and every merge to `main`
turned the rest into CONFLICTS. A conflicted pull request gets **no CI at all**,
and re-clearing one costs a fresh `frontend` run (measured at about 71 minutes
on 2026-10-23; one night lost six of them). This is Gemini's "Attack 6" fix.

THE RULE NOW. A pull request writes ONE small file under `changelog.d/` and
never edits `CHANGELOG.md`:

    changelog.d/2026-10-23-phone-galaxy-band.md

Its whole content is ONE markdown bullet, the same text that used to go into
`CHANGELOG.md`:

    - **The phone's Galaxy gets a read-only "at a glance" band (2026-10-23).** ...

The date in the filename decides the order. When a roll is due, someone runs
this tool on a quiet `main` and opens ONE pull request with the result and
nothing else in it; the fragments are removed by the same run. **The roll is
deliberate, never automatic**, and it is idempotent: rolling twice changes
nothing.

The CHECK is what CI can run on every pull request: it validates every
fragment's name and shape and that `CHANGELOG.md` still carries the heading the
roll inserts under. It never requires the fragments to have been rolled yet -
that would fail the very pull requests the fragments exist for.

Run:

    py -3 tools/roll_changelog.py --check      # validate only (exit 1 on a bad fragment)
    py -3 tools/roll_changelog.py --dry-run    # print what the roll would insert
    py -3 tools/roll_changelog.py              # fold the fragments in and remove them

`--fragments DIR` and `--changelog FILE` point the tool at a copy, which is how
`backend/test_roll_changelog.py` proves it without touching the real files.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAGMENT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9][a-z0-9-]*)\.md$")
#: The heading the roll inserts under; every fragment's text goes right below it.
MARKER = "## Not in a numbered version yet"


def fragment_paths(fragments: Path) -> list[Path]:
    """Every `*.md` fragment, sorted by date then name - oldest first."""
    if not fragments.is_dir():
        return []
    return sorted((p for p in fragments.glob("*.md") if p.name != "README.md"),
                  key=lambda p: p.name)


def problems(fragments: Path, changelog: Path) -> list[str]:
    """Everything wrong with the fragments and the CHANGELOG heading, in words."""
    out: list[str] = []
    if not fragments.is_dir():
        out.append(f"{fragments} does not exist - create it (with its README.md)")
        return out
    if not changelog.is_file():
        out.append(f"{changelog} does not exist")
        return out
    if MARKER not in changelog.read_text(encoding="utf-8"):
        out.append(f"{changelog} no longer carries the heading {MARKER!r}, "
                   f"so the roll has nowhere to insert")
    for path in fragment_paths(fragments):
        name = path.name
        if name == "README.md":
            continue
        if not FRAGMENT_RE.match(name):
            out.append(f"{name}: a fragment's name is YYYY-MM-DD-<slug>.md "
                       f"(lowercase letters, digits and hyphens only)")
            continue
        text = path.read_text(encoding="utf-8")
        body = text.strip()
        if not body:
            out.append(f"{name}: empty - a fragment is one bullet")
        elif not body.startswith("- "):
            out.append(f"{name}: must start with '- ' (one markdown bullet)")
        elif "\n\n" in body:
            out.append(f"{name}: one bullet only - remove the blank line")
        elif "**" not in body:
            out.append(f"{name}: give the entry a bold title, like every "
                       f"CHANGELOG entry ('- **What changed (date).** ...')")
    return out


def insert_line(changelog: Path) -> int:
    """The line index in `changelog`'s lines where the roll inserts."""
    lines = changelog.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == MARKER:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1            # the blank line(s) under the heading stay
            return j
    raise SystemExit(f"{changelog}: no {MARKER!r} heading")


def planned_block(fragments: Path) -> list[str]:
    """The bullet lines, newest first - the order `CHANGELOG.md` keeps."""
    newest_first = list(reversed(fragment_paths(fragments)))
    block = []
    for path in newest_first:
        body = path.read_text(encoding="utf-8").strip()
        if body:
            block.append(body)
    return block


def roll(fragments: Path, changelog: Path, *, dry_run: bool = False) -> tuple:
    """Insert every fragment's bullet under the heading; return (lines, count).

    The files are removed only after the new CHANGELOG text has been read back
    and the block really is in it. `dry_run` writes nothing at all.
    """
    bad = [p for p in problems(fragments, changelog) if "heading" not in p]
    if bad:
        raise SystemExit("fix these fragments first:\n  " + "\n  ".join(bad))
    block = planned_block(fragments)
    if not block:
        return 0, 0
    text = changelog.read_text(encoding="utf-8")
    lines = text.splitlines()
    at = insert_line(changelog)
    new_lines = lines[:at] + block + lines[at:]
    new_text = "\n".join(new_lines) + "\n"
    if not dry_run:
        changelog.write_text(new_text, encoding="utf-8", newline="\n")
        written = changelog.read_text(encoding="utf-8")
        missing = [b for b in block if b not in written]
        if missing:
            raise SystemExit(f"{changelog}: the roll did not stick for "
                             f"{len(missing)} line(s); leaving the fragments alone")
        for path in fragment_paths(fragments):
            path.unlink()
    return len(block), len(block)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="validate the fragments and the heading; write nothing")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the bullets a roll would insert; write nothing")
    ap.add_argument("--fragments", default=str(ROOT / "changelog.d"))
    ap.add_argument("--changelog", default=str(ROOT / "CHANGELOG.md"))
    args = ap.parse_args(argv)
    fragments, changelog = Path(args.fragments), Path(args.changelog)
    found = problems(fragments, changelog)
    if args.check:
        for problem in found:
            print(f"::error::{problem}")
        if not found:
            print(f"changelog fragments OK: {len(fragment_paths(fragments))} file(s), "
                  f"every one a single well-formed bullet")
        return 1 if found else 0
    if found:
        for problem in found:
            print(f"::error::{problem}")
        return 1
    if args.dry_run:
        for line in planned_block(fragments):
            print(line)
        print(f"\n[{len(planned_block(fragments))} bullet(s) would be inserted, "
              f"then that many fragment file(s) removed]")
        return 0
    count, _ = roll(fragments, changelog)
    if count == 0:
        print("changelog.d is empty - nothing to roll")
    else:
        print(f"rolled {count} changelog bullet(s) into {changelog.name} "
              f"and removed the fragment file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
