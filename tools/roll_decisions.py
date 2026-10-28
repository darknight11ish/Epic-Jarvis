#!/usr/bin/env python3
"""Roll DECISIONS fragments into `docs/DECISIONS.md`, or check them.

THE RACE THIS ENDS. Every pull request that recorded an owner decision appended
its entry at the end of `docs/DECISIONS.md` - one shared place, by construction.
Two such pull requests therefore changed the same lines and every merge to
`main` turned the rest into CONFLICTS. A conflicted pull request gets **no CI at
all**, and re-clearing one costs a fresh `frontend` run (measured at about 62
minutes; PR #386 is where this crossed). The changelog ended the same race on
2026-10-23 with `changelog.d/`; this is that fix, one file over, and it is
Gemini's ruling Q8 for Epic-Jarvis.

THE RULE NOW. A pull request records ONE decision as ONE small file under
`decisions.d/` and never edits `docs/DECISIONS.md`:

    decisions.d/2026-10-28-a-quieter-hud.md

Its whole content is ONE dated bullet - the same prose that used to be appended
to `docs/DECISIONS.md`:

    - **2026-10-28 — A quieter HUD:** what was decided, and what it replaced.

The date in the filename decides the order and must agree with the date in the
bullet. When a roll is due, someone runs this tool on a quiet `main`, alone, and
opens ONE pull request with the result and nothing else in it; the fragment
files are removed by the same run. **The roll is deliberate, never automatic**:
no workflow and no other tool runs it, and a feature pull request must never
run it - only this tool's own tests and the person doing the roll do. It is
idempotent: rolling twice changes nothing.

WHERE THE ROLL INSERTS, AND WHY. `docs/DECISIONS.md` is **chronological, oldest
first**, so the roll appends at the very END of the file, and the bullets of one
roll are written in date order (oldest of the batch first) rather than newest
first. Newest-first is `CHANGELOG.md`'s order, and copying it here would leave
each rolled batch running backwards inside a file that is otherwise forwards.
`roll_changelog.py` inserts under a heading near the top; this file has no such
place to insert into - everything above the end is history.

This file does carry an anchor heading near its end (MARKER below, under which
the folded fragments read as a section). It is a canary, not the insertion
point: `--check` fails when it disappears, so the tool cannot silently be
pointed at a file that is not the record, while the insertion point stays the
end of the file even if somebody appends an entry above it.

THE CHECK is what CI can run on every pull request: it validates every
fragment's name, its bullet shape and that the date in the name matches the
date in the bullet, and that `docs/DECISIONS.md` still carries the anchor. It
never requires the fragments to have been rolled yet - that would fail the very
pull requests the fragments exist for.

CLAIMS SOURCES ARE RE-ANCHORED. A `docs/CLAIMS.tsv` row may cite a decision as
`decisions.d/<name>.md:<line>`. Once the fragment is rolled that file is gone,
so the same run rewrites those source cells to `docs/DECISIONS.md:<the line the
entry now starts on>`; every other row is left byte for byte alone. The line
number inside the fragment is not preserved (it cannot be: the entry moves), so
the rewrite points at the entry's first line.

Run:

    py -3 tools/roll_decisions.py --check      # validate only (exit 1 on a bad fragment)
    py -3 tools/roll_decisions.py --dry-run    # print what the roll would insert
    py -3 tools/roll_decisions.py              # fold the fragments in and remove them

`--fragments DIR`, `--decisions FILE` and `--claims FILE` point the tool at a
copy, which is how `backend/test_roll_decisions.py` proves it without touching
the real files.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The one shape a fragment's name may have. The date sorts the roll.
FRAGMENT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9][a-z0-9-]*)\.md$")

#: The anchor `--check` looks for in the record. It marks the section the
#: folded fragments read as, and it is the canary that the file in front of this
#: tool is the decision record at all. The roll does NOT insert under it - see
#: WHERE THE ROLL INSERTS in the module docstring.
MARKER = ("## Decisions written as `decisions.d/` fragments, folded in here "
          "in date order")

#: ONE dated bullet: `- **YYYY-MM-DD — Title:** prose`. DOTALL because a long
#: decision wraps; "no blank line" (checked separately) keeps it one bullet.
BULLET_RE = re.compile(r"^- \*\*(\d{4}-\d{2}-\d{2}) — .+?:\*\*\s+\S", re.DOTALL)

#: The record, repo-relative, as a CLAIMS.tsv `source` cell spells it.
RECORD = "docs/DECISIONS.md"

#: A source cell that names one fragment, with the line inside it.
CLAIMS_SOURCE_RE = re.compile(r"^decisions\.d/([^:/\\]+\.md):(\d+)$")


def fragment_paths(fragments: Path) -> list[Path]:
    """Every `*.md` fragment, sorted by name - date first, then slug."""
    if not fragments.is_dir():
        return []
    return sorted((p for p in fragments.glob("*.md") if p.name != "README.md"),
                  key=lambda p: p.name)


def record_files(root: Path = ROOT) -> list[Path]:
    """The decision record as a reader should see it: the rolled file, then the
    fragments that have not been rolled yet, in date order.

    This is the same two-place rule `tools/check_claims.py` applies to a
    `grep:`/`absent:` that names `docs/DECISIONS.md`, and the rule
    `backend/test_promise_guards.py` reads a promise's own words with. It is a
    plain filesystem read - `check_claims.py` judges the TRACKED tree itself,
    because a scratch copy of a fragment is not evidence about the repository.
    """
    out: list[Path] = []
    rolled = root / RECORD
    if rolled.is_file():
        out.append(rolled)
    out.extend(fragment_paths(root / "decisions.d"))
    return out


def record_text(root: Path = ROOT) -> str:
    """Every record file's text, joined - the record as one searchable string."""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace")
                     for path in record_files(root))


def problems(fragments: Path, decisions: Path) -> list[str]:
    """Everything wrong with the fragments and the anchor, in plain words."""
    out: list[str] = []
    if not fragments.is_dir():
        out.append(f"{fragments} does not exist - create it (with its README.md)")
        return out
    if not decisions.is_file():
        out.append(f"{decisions} does not exist")
        return out
    if MARKER not in decisions.read_text(encoding="utf-8"):
        out.append(f"{decisions} no longer carries the anchor heading "
                   f"{MARKER!r}, so this tool cannot tell it is the record")
    for path in fragment_paths(fragments):
        name = path.name
        named = FRAGMENT_RE.match(name)
        if not named:
            out.append(f"{name}: a fragment's name is YYYY-MM-DD-<slug>.md "
                       f"(lowercase letters, digits and hyphens only)")
            continue
        body = path.read_text(encoding="utf-8").strip()
        if not body:
            out.append(f"{name}: empty - a fragment is one dated bullet")
        elif not body.startswith("- "):
            out.append(f"{name}: must start with '- ' (one markdown bullet)")
        elif "\n\n" in body:
            out.append(f"{name}: one bullet only - remove the blank line")
        elif "**" not in body:
            out.append(f"{name}: give the entry a bold title, like "
                       f"'- **YYYY-MM-DD (em dash) Title:** prose'")
        else:
            bullet = BULLET_RE.match(body)
            if not bullet:
                out.append(f"{name}: the bullet must be "
                           f"'- **YYYY-MM-DD (em dash) Title:** prose ...', the same "
                           f"shape as the entries already in {decisions.name}")
            elif bullet.group(1) != named.group(1):
                out.append(f"{name}: the filename says {named.group(1)} and "
                           f"the bullet says {bullet.group(1)} - the date in "
                           f"the name decides the order, so they must agree")
    return out


def planned_block(fragments: Path) -> tuple:
    """(lines, {fragment name: offset in lines}) - oldest first, blank-separated.

    Oldest first, not newest: see WHERE THE ROLL INSERTS in the module
    docstring. The offset is where that fragment's bullet starts inside the
    block, which is what gives its line number in the record afterwards.
    """
    lines: list[str] = []
    starts: dict[str, int] = {}
    for path in fragment_paths(fragments):
        body = path.read_text(encoding="utf-8").strip()
        if not body:
            continue
        if lines:
            lines.append("")
        starts[path.name] = len(lines)
        lines.extend(body.splitlines())
    return lines, starts


def reanchor_sources(claims: Path, moved: dict, *,
                     dry_run: bool = False) -> list:
    """Point every CLAIMS source that names a rolled fragment at the record.

    `moved` maps a rolled fragment's filename to the 1-based line its entry now
    starts on in `docs/DECISIONS.md`. Only the `source` column of a row that
    cites one of those fragments changes; a row's claim, check and state are
    never touched, and a file that names none of them is not written at all.
    Returns [(old, new)] so `--dry-run` can print what a roll would rewrite.
    """
    if not claims.is_file() or not moved:
        return []
    changed: list = []
    out: list[str] = []
    for line in claims.read_text(encoding="utf-8").splitlines():
        cells = line.split("\t")
        if len(cells) == 5:
            found = CLAIMS_SOURCE_RE.match(cells[4].strip())
            if found and found.group(1) in moved:
                new = f"{RECORD}:{moved[found.group(1)]}"
                changed.append((cells[4], new))
                cells[4] = new
                out.append("\t".join(cells))
                continue
        out.append(line)
    if changed and not dry_run:
        claims.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    return changed


def roll(fragments: Path, decisions: Path, *, dry_run: bool = False,
         claims: Path | None = None) -> tuple:
    """Append every fragment's bullet at the end of the record.

    Returns (bullets inserted, fragment files removed). The fragment files are
    removed only after the new record text has been read back and every bullet
    really is in it, and `dry_run` writes nothing at all.
    """
    bad = problems(fragments, decisions)
    if bad:
        raise SystemExit("fix these fragments first:\n  " + "\n  ".join(bad))
    block, starts = planned_block(fragments)
    if not block:
        return 0, 0
    lines = decisions.read_text(encoding="utf-8").splitlines()
    while lines and not lines[-1].strip():
        lines.pop()                       # one clean end, however it was left
    new_lines = lines + [""] + block
    new_text = "\n".join(new_lines) + "\n"
    # 1-based line each fragment's entry starts on once it is in the record.
    moved = {name: len(lines) + start + 2 for name, start in starts.items()}
    if not dry_run:
        decisions.write_text(new_text, encoding="utf-8", newline="\n")
        written = decisions.read_text(encoding="utf-8")
        missing = [path.name for path in fragment_paths(fragments)
                   if path.read_text(encoding="utf-8").strip() not in written]
        if missing:
            raise SystemExit(
                f"{decisions}: the roll did not stick for {len(missing)} "
                f"fragment(s) ({', '.join(missing)}); leaving the fragment "
                f"files alone and re-anchoring nothing")
        if claims is not None:
            reanchor_sources(claims, moved)
        for path in fragment_paths(fragments):
            path.unlink()
    return len(starts), len(starts)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="validate the fragments and the anchor; write nothing")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the bullets and the source re-anchors a roll "
                         "would make; write nothing")
    ap.add_argument("--fragments", default=str(ROOT / "decisions.d"))
    ap.add_argument("--decisions", default=str(ROOT / "docs" / "DECISIONS.md"))
    ap.add_argument("--claims", default=str(ROOT / "docs" / "CLAIMS.tsv"))
    args = ap.parse_args(argv)
    fragments = Path(args.fragments)
    decisions = Path(args.decisions)
    claims = Path(args.claims)
    found = problems(fragments, decisions)
    if args.check:
        for problem in found:
            print(f"::error::{problem}")
        if not found:
            print(f"decisions fragments OK: {len(fragment_paths(fragments))} "
                  f"file(s), every one a single well-formed dated bullet, and "
                  f"{decisions.name} still carries the anchor heading")
        return 1 if found else 0
    if found:
        for problem in found:
            print(f"::error::{problem}")
        return 1
    if args.dry_run:
        block, starts = planned_block(fragments)
        for line in block:
            print(line)
        moved = {}
        tail = decisions.read_text(encoding="utf-8").splitlines()
        while tail and not tail[-1].strip():
            tail.pop()
        for name, start in starts.items():
            moved[name] = len(tail) + start + 2
        changes = reanchor_sources(claims, moved, dry_run=True)
        for old, new in changes:
            print(f"\nwould re-anchor source: {old} -> {new}")
        print(f"\n[{len(starts)} bullet(s) would be appended at the end of "
              f"{decisions.name}, in date order, then that many fragment "
              f"file(s) removed]")
        return 0
    count, _ = roll(fragments, decisions, claims=claims)
    if count == 0:
        print("decisions.d is empty - nothing to roll")
    else:
        print(f"rolled {count} decision(s) into the end of {decisions.name}, "
              f"in date order, and removed the fragment file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
