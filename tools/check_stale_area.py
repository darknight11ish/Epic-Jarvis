#!/usr/bin/env python3
"""After a change lands, name the areas it touched that nobody has audited since.

    py -3 tools/check_stale_area.py --all             what every PR prints (see below)
    py -3 tools/check_stale_area.py --since <rev>     after a merge you just made
    py -3 tools/check_stale_area.py --check [--since] the desk's strict mode
    py -3 tools/check_stale_area.py --list            every area, and its state either way

WHY THIS EXISTS, AND WHAT IT WAS PROMISED TO BE

This is queue item 10. `docs/HANDOFF-AFTER-PR39.md:300` wrote the promise down:

    - Stale-area check after every big merge (list areas changed since their
      last audit; the coverage map from this session is the template).

and `docs/FEATURE-REVIEW-2026-10-04.md:597` restated the reason:

    Nothing measures whether a merge broke a nearby area - this is queue item
    10 ("a stale-area check after every big merge"), still unbuilt.

So the question this tool answers is NOT "does some document contradict the
tree today". That would be a different tool, and a harder one - and it is not
what the row reserved. This answers the promise: **of the areas this change
touched, which have moved since the last time anybody audited them?** Those are
the places a nearby break could have landed unnoticed, and they are where a
person should look next. It cannot tell you that a change broke something; it
tells you where nobody has looked.

IT RUNS IN CI AND DOES NOT GATE: THE ONE STEP IN `audit` THAT EXITS 0 WITH DEBT

Measured on `2f85d772`: every area in the map has moved since it was last
audited - the map's audits are all 2026-09-24..09-30 and the tree is
2026-10-16. A check that is red on a quiet `main` is one somebody turns off
within a week, so this one is deliberately unlike its neighbours in the `audit`
job, which exit non-zero the moment they find a violation.

    default / --all   debt is PRINTED and the exit code stays 0, so the `audit`
                      job (already informational, never a required check) can
                      carry it on every pull request without blocking anybody.
    --check           the desk's strict mode: exit 1 on debt, and exit 2 when
                      there is nothing to check at all. BLOCKED is never a
                      pass, so an empty range is not a green `--check`.

A tool nobody runs is a document, which is the whole reason for the split: the
debt stays visible on every PR, and the gate stays off.

THE MAP IS THE INPUT, AND IT IS THIS REPOSITORY'S TO KEEP

`tools/stale-areas.tsv` holds one row per area: its globs, the date it was last
audited, and the report that audited it. It is seeded from the coverage map the
promise names - `docs/audit-reports-2026-09-29-30/37-audit-a84616c6.md`, whose
own Key is "NEVER = no report names it. STALE = audited, but the code changed
since" - and its AREAS are that report's areas. Its globs are this file's
transcription of them, and they are meant to be edited: an area whose globs
match no tracked file is reported as a broken map row, never as a pass.

That is the honest reading of the promise. The coverage map is a one-off
narrative report: its areas are prose ("Phone screens (about 60 Plates)"), its
"Last audit" column holds sentences ("09-19 and 09-26 bug audits"), and nothing
in the tree records when any area was last audited. A checker cannot read prose,
so the map becomes data here and a human keeps it current - the same shape as
`backend/_where.py`'s SHIPPED list, `tools/gen_base_from_backend.py`'s BESIDE
table and `docs/CLAIMS.tsv`, all of which are maintained tables a checker reads.
**A row goes quiet when somebody records that the area was audited.** That is
the discipline "after every big merge" was asking for.

A DATED RECORD IS NOT A STALE STATEMENT, AND THIS TOOL MUST NOT SAY IT IS

The worked example, because it is live. `docs/FEATURE-REVIEW-2026-10-04.md:370`
says of `jarvis_initiative.py`: "No importer, no caller (B3 #2) | Delete, or
give it the 'stale-area check' job it was meant for". That was TRUE on
2026-10-04 and is superseded now: the module is `backend/rebuilt/
jarvis_initiative.py`, `jarvis_hud.py` calls `build_from_config()`/`start()`,
and since 2026-10-15 `start()` also registers the job ticker. The sentence is
not stale - it is DATED, and it does its job by saying what was true then.

So this tool reports AREAS and AUDIT DATES. It never reads a document's prose
and never judges a claim. "Not built", written on 30 September, stays true for
ever; what goes stale is the AREA, when code lands in it after the last look.

WHAT IT DELIBERATELY DOES NOT DO

  * It does not decide whether an audit was any good. A row says an area was
    looked at on a date, and that is all it says.
  * It does not read the working copy. Everything is judged with `git ls-files`
    and `git log`, so an untracked scratch copy cannot answer a question about
    the repository - the lesson `tools/check_claims.py` writes down about its
    own paths.
  * It opens no socket and writes nothing.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

#: The area map, relative to the checkout root.
MAP = "tools/stale-areas.tsv"

#: A row's columns, in order.
COLUMNS = ("area", "globs", "last_audited", "verdict", "evidence")

#: The one word that means "no report has ever named this area".
NEVER = "never"

#: The date `--all` ranks from when an area has never been audited. Long
#: enough ago that "commits since" is the whole history, which is the honest
#: answer for an area nobody has ever looked at.
SINCE_FOREVER = "1970-01-01"

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Revisions tried, in order, when the caller names no `--since`. `origin/main`
#: is the branch a pull request is measured against; a clone with no such
#: remote falls back to `main`, then to the previous commit.
SINCE_CANDIDATES = ("origin/main", "main", "HEAD^")


class MapUnreadable(Exception):
    """The area map cannot be read as a map. Never a silent skip."""


class CannotCheck(Exception):
    """There is nothing to check. Not the same as a clean answer."""


def _git(root: Path, *args: str) -> str:
    """One git call, text out.

    `--no-pager` because a pager in a checker is how output disappears, and the
    encoding is explicit because this project has been bitten by cp1252.
    """
    try:
        done = subprocess.run(["git", "--no-pager", *args], cwd=str(root),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as err:                       # no git on this machine
        raise MapUnreadable(f"git could not be run: {err}") from err
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise MapUnreadable(detail[-1] if detail else f"git {args[0]} failed")
    return done.stdout.decode("utf-8", "replace")


def load_map(path: Path) -> list:
    """Every row, as dicts. Refuses a row it cannot evaluate - a row nobody can
    read is a row nobody checked."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise MapUnreadable(f"the area map could not be read: {err}") from err
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        # The column-name line, so the file reads as a table in an editor. It
        # is the header only when it IS the header - a later row called "area"
        # is a duplicate area and is refused below.
        if not rows and parts[0].strip() == COLUMNS[0]:
            continue
        if len(parts) != len(COLUMNS):
            raise MapUnreadable(
                f"{path.name}:{n}: expected {len(COLUMNS)} tab-separated columns "
                f"({'/'.join(COLUMNS)}), found {len(parts)}")
        row = dict(zip(COLUMNS, (p.strip() for p in parts)))
        if not row["area"]:
            raise MapUnreadable(f"{path.name}:{n}: the row names no area")
        globs = [g.strip() for g in row["globs"].split(",") if g.strip()]
        if not globs:
            raise MapUnreadable(f"{path.name}:{n}: {row['area']}: no globs")
        when = row["last_audited"]
        if when != NEVER and not _DATE.match(when):
            raise MapUnreadable(
                f"{path.name}:{n}: {row['area']}: last_audited must be "
                f"{NEVER!r} or YYYY-MM-DD, found {when!r}")
        row["globs"] = globs
        row["line"] = n
        rows.append(row)
    if not rows:
        raise MapUnreadable(f"{path.name}: holds no area rows at all")
    seen = set()
    for row in rows:
        if row["area"] in seen:
            raise MapUnreadable(f"{path.name}:{row['line']}: {row['area']} appears twice")
        seen.add(row["area"])
    return rows


def tracked(root: Path, globs: list) -> list:
    """The TRACKED files this area covers. Untracked scratch cannot answer a
    question about the repository."""
    out = _git(root, "ls-files", "-z", "--", *globs)
    return [f for f in out.split("\0") if f]


def last_change(root: Path, globs: list):
    """(sha, date) of the newest commit touching this area, or None."""
    out = _git(root, "log", "-1", "--format=%H%x09%cI", "--", *globs).strip()
    if not out:
        return None
    sha, _, when = out.partition("\t")
    return sha.strip(), when.strip()[:10]


def changes_since(root: Path, since: str, globs: list) -> list:
    """The commits in `since..HEAD` that touch this area."""
    out = _git(root, "log", "--format=%H", f"{since}..HEAD", "--", *globs)
    return [l.strip() for l in out.splitlines() if l.strip()]


def commits_since(root: Path, since_date: str, globs: list) -> int:
    """How many commits touched this area after `since_date`. `--all` ranks on
    this, so the worst area is read first."""
    out = _git(root, "rev-list", "--count", f"--since={since_date}", "HEAD", "--", *globs)
    return int(out.strip() or 0)


def state(row: dict, newest) -> tuple:
    """(is_stale, why) for one area, from its audit date and its newest change.

    `never` audited is stale the moment the area has any change at all - that
    is the coverage map's own NEVER, and the reason the map exists.
    """
    if newest is None:
        return False, "no commit has ever touched it"
    if row["last_audited"] == NEVER:
        return True, f"never audited, and its newest change is {newest[1]}"
    if newest[1] > row["last_audited"]:
        return True, f"changed {newest[1]}, after its last audit {row['last_audited']}"
    return False, f"audited {row['last_audited']}, unchanged since ({newest[1]})"


def resolve_since(root: Path, wanted) -> str:
    """The revision to measure against: what was asked for, or the first of
    `SINCE_CANDIDATES` this checkout has. `CannotCheck` when there is none."""
    for rev in ([wanted] if wanted else SINCE_CANDIDATES):
        try:
            if _git(root, "rev-parse", "--verify", f"{rev}^{{commit}}").strip():
                return rev
        except MapUnreadable:
            continue
    raise CannotCheck(
        f"no revision to measure against - tried "
        f"{', '.join([wanted] if wanted else list(SINCE_CANDIDATES))}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Name the areas a change touched that nobody has audited since.")
    ap.add_argument("--since", default=None,
                    help="the change to check: <rev>..HEAD "
                         f"(default: the first of {', '.join(SINCE_CANDIDATES)})")
    ap.add_argument("--all", action="store_true",
                    help="ignore the range: report every area that has moved since "
                         "its last audit - the whole tree's debt. What CI runs.")
    ap.add_argument("--check", action="store_true",
                    help="strict: exit 1 on debt and 2 when there is nothing to "
                         "check. The desk's mode; CI runs without it on purpose.")
    ap.add_argument("--map", default=MAP, help=f"the area map (default: {MAP})")
    #: The default root is the checkout THIS SCRIPT lives in, not the working
    #: directory. CI runs it from `jarvis-desktop/src-tauri` (the step's own
    #: `python3 ../../tools/...` says so), and a working-directory default made
    #: it look for `jarvis-desktop/src-tauri/tools/stale-areas.tsv` and die with
    #: a MapUnreadable - which is exactly what happened on PR #486's first run:
    #:
    #:   stale-area: the area map could not be read: [Errno 2] No such file or
    #:   directory: '.../jarvis-desktop/src-tauri/tools/stale-areas.tsv'
    #:
    #: A checker whose answer depends on where it was invoked is the same class
    #: of defect as a test that silently skips: it reports on the wrong thing.
    #: `--root` still overrides it for a deliberate run against another checkout.
    here = Path(__file__).resolve().parent.parent
    ap.add_argument("--root", default=str(here),
                    help="the checkout to check (default: the one this script lives in)")
    ap.add_argument("--list", action="store_true",
                    help="print every area and its state, so 'nothing is wrong' can "
                         "be told apart from 'nothing was looked at'")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    map_path = Path(args.map)
    if not map_path.is_absolute():
        map_path = root / args.map

    # A map nobody can read is a failure in BOTH modes: it is not debt, it is
    # the tool not working, and it must never look like a clean run.
    try:
        rows = load_map(map_path)
    except MapUnreadable as err:
        print(f"::error::stale-area: {err}")
        return 1

    range_note, in_range, rng = "", None, ""
    try:
        if args.all:
            where = f"HEAD, every area"
        else:
            since = resolve_since(root, args.since)
            rng = f"{since}..HEAD"
            revs = changes_since(root, since, ["."])
            in_range = set(revs)
            head = _git(root, "rev-parse", "--short", "HEAD").strip()
            where = f"{rng} ({head})"
            if not in_range:
                range_note = (f"{since}..HEAD is EMPTY - no commit, so no file, so "
                              f"nothing is checked here. This is not a clean tree; it "
                              f"is an empty question. Pass --since <the commit the merge "
                              f"brought in>, or --all for the whole tree's debt.")
    except (MapUnreadable, CannotCheck) as err:
        print(f"::error::stale-area: {err}")
        if args.check:
            return 2
        print("stale-area: nothing was checked (see above). Not a pass - this run "
              "could not ask the question.")
        return 0

    findings, broken, looked = [], [], []
    for row in rows:
        area, globs = row["area"], row["globs"]
        try:
            files = tracked(root, globs)
            if not files:
                broken.append(f"{area}: its globs match no tracked file "
                              f"({', '.join(globs)}) - the map is wrong, not the tree")
                continue
            newest = last_change(root, globs)
            stale, why = state(row, newest)
            touched = args.all or bool(changes_since(root, rng.split("..")[0], globs))
        except (MapUnreadable, CannotCheck) as err:
            broken.append(f"{area}: {err}")
            continue
        looked.append((row, len(files), newest, stale, why, touched))

    if args.list:
        print(f"Every area in {args.map}, measured with git against {where}:")
        for row, n, newest, stale, why, touched in looked:
            mark = "STALE " if (stale and touched) else "ok    "
            print(f"  {mark} {row['area']:<34} {n:>5} file(s)  {why}")
        print("")

    if broken:
        for line in broken:
            print(f"::error::stale-area: {line}")
        print(f"{len(broken)} broken row(s) in {args.map}: a row nobody can evaluate is "
              f"a row nobody checked, so this fails rather than passing over it.")
        return 1

    for row, n, newest, stale, why, touched in looked:
        if stale and touched:
            since = row["last_audited"]
            count = commits_since(root, SINCE_FOREVER if since == NEVER else since,
                                  row["globs"])
            findings.append((row, n, why, count))

    if range_note:
        print(f"stale-area: {range_note}")
        if not args.check:
            print(f"stale-area: the whole tree's debt is what --all reports; run it to "
                  f"see it. Nothing was checked by this run, so nothing here is a pass.")
            return 0
        return 2

    if args.all:
        # A COUNT, not a wall: the number, the three worst, and how to see the
        # rest. A CI log that prints nineteen three-line blocks is a log nobody
        # reads, which is the failure this tool exists to avoid.
        worst = sorted(findings, key=lambda f: -f[3])[:3]
        names = ", ".join(f"{row['area']} ({count} commits since {row['last_audited']})"
                          for row, _n, _why, count in worst)
        print(f"stale-area: {len(findings)} of {len(rows)} areas have moved since they "
              f"were last audited. Worst: {names}."
              if findings else
              f"stale-area: all {len(rows)} areas have been audited since they last "
              f"moved.")
        if findings:
            print(f"           The full list: python -B tools/check_stale_area.py --all "
                  f"--list. This is the audit-debt list, not a gate: it is only cleared "
                  f"by recording an audit in {args.map}.")
        return 1 if (args.check and findings) else 0

    for row, n, why, count in findings:
        print(f"STALE  {row['area']:<34} {n:>5} file(s), {count:>4} commit(s) since "
              f"{row['last_audited']}")
        print(f"       {why}")
        print(f"       evidence: {row['evidence']}")

    if not findings:
        files = len(_git(root, "diff", "--name-only", rng).splitlines())
        print(f"stale-area: {where} touches {files} file(s); every area it touched has "
              f"been audited since it last moved.")
        return 0

    print(f"\n{len(findings)} stale area(s) touched by {where}. Nobody has audited these "
          f"since they last changed, so a break nearby would not have been looked for: "
          f"read them first. Clear one by recording an audit in {args.map}, not by "
          f"rerunning this.")
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
