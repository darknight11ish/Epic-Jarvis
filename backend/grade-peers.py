#!/usr/bin/env python3
"""Run the redundancy grader over real GitHub data, and print the table.

    python backend/grade-peers.py [path/to/peer-stats.json]

`jarvis_research.grade_repo` decides ADOPT / FORK AND EXTEND / BUILD CUSTOM on
three things: popularity, maintenance and licence. It has never been run on
real data, because the container these sessions run in cannot reach
`api.github.com` — it answers 403, and so does `github.com`. Only
`raw.githubusercontent.com` gets through.

Two attempts to get the numbers out of a second model produced no star counts
at all, and a 5-in-6 error rate on the claims that COULD be checked against
source files. So:

    1. Run `scripts\\fetch-repo-stats.ps1` on a machine with a browser's view
       of the internet. It writes `backend/peer-stats.json`.
    2. Run this.

No network here. It reads the file and does arithmetic.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_research as R


def main() -> int:
    where = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "peer-stats.json"
    if not where.is_file():
        print(f"No data at {where}\n")
        print("Get it first, on a machine that can reach api.github.com:")
        print("    .\\scripts\\fetch-repo-stats.ps1")
        return 1

    try:
        # utf-8-SIG, not utf-8. PowerShell 5.1's `Set-Content -Encoding UTF8`
        # writes a byte-order mark, and json.loads rejects it with
        # "Unexpected UTF-8 BOM" - which reads like the file is corrupt when
        # it is perfectly good. utf-8-sig strips a BOM if there is one and is
        # identical to utf-8 if there is not.
        raw = json.loads(where.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"{where} is not readable JSON: {type(exc).__name__}: {exc}")
        return 1

    graded, skipped = [], []
    for key, repo in raw.items():
        if not isinstance(repo, dict) or repo.get("error"):
            skipped.append((key, (repo or {}).get("error", "no data")))
            continue
        repo.setdefault("full_name", key)
        # html_url is not in the saved shape; grade_repo only uses it for
        # display and tolerates its absence, but a link is worth having.
        repo.setdefault("html_url", f"https://github.com/{key}")
        try:
            graded.append(R.grade_repo(repo))
        except Exception as exc:
            skipped.append((key, f"{type(exc).__name__}: {exc}"))

    if not graded:
        print("Nothing could be graded.")
        for name, why in skipped:
            print(f"  {name}: {why}")
        return 1

    # Worst verdict last, so the things worth adopting are at the top where
    # they will actually be read.
    order = {"ADOPT": 0, "FORK AND EXTEND": 1, "BUILD CUSTOM": 2}
    graded.sort(key=lambda g: (order.get(g["verdict"], 9), -g["stars"]))

    width = max(len(g["name"]) for g in graded)
    print(f"\n{'repo':<{width}}  {'stars':>7}  {'licence':<12}  {'pushed':>8}  verdict")
    print("-" * (width + 46))
    for g in graded:
        age = g["days_since_push"]
        pushed = "unknown" if age is None else f"{age}d"
        print(f"{g['name']:<{width}}  {g['stars']:>7}  "
              f"{(g['licence'] or 'NONE'):<12}  {pushed:>8}  {g['verdict']}"
              + ("  ARCHIVED" if g["archived"] else ""))

    print()
    for verdict in ("ADOPT", "FORK AND EXTEND", "BUILD CUSTOM"):
        rows = [g for g in graded if g["verdict"] == verdict]
        if not rows:
            continue
        print(f"== {verdict} ({len(rows)}) ==")
        for g in rows:
            print(f"  {g['name']}\n      {g['why']}")
        print()

    if skipped:
        print("== not graded ==")
        for name, why in skipped:
            print(f"  {name}: {why}")
        print()

    # The thresholds, printed rather than assumed, because a verdict without
    # its cutoffs is an opinion.
    print(f"Thresholds: popular >= {R.POPULAR_STARS} stars, viable >= "
          f"{R.VIABLE_STARS}, stale after {R.FRESH_DAYS} days.")
    print("A verdict is about whether to take the CODE. A project can be "
          "BUILD CUSTOM\nand still be worth reading - see docs/PEERS.md, "
          "where several are.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
