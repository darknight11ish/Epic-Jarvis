"""check_desktop_lockfile.py - jarvis-desktop's package.json and its lockfile must agree.

    python3 tools/check_desktop_lockfile.py
    python3 tools/check_desktop_lockfile.py --package P.json --lock L.json

WHAT IT IS, AND WHY (2026-11-18, the two CI guards the external review asked
for). `Desktop release` installs with `npm ci`, which REFUSES to install when
`package.json` and `package-lock.json` disagree. PR #1319 added `typescript` to
`jarvis-desktop/package.json` and never regenerated `package-lock.json`, and
EIGHT `Desktop release` runs then failed at `npm ci` - unnoticed for two days,
because no REQUIRED check ever ran `npm ci`. #1386 fixed the lockfile; this is
the guard that stops the recurrence.

It lives in a REQUIRED job (the `frontend-shard` job behind the ruleset's
required `frontend` check, shard 1 only) rather than in `audit`, because that
is the whole lesson: an informational signal was exactly what was missing.
`audit` is informational and does not gate a merge - a lockfile desync must
block the merge that introduces it, not scroll past in a job nobody waits for.

HOW IT COMPARES, and why this is the same question `npm ci` asks. No npm, no
node, no network, no `node_modules`: a lockfileVersion 3 lock records the root
project's dependency maps in `packages[""]`, and the version each name
resolves to under `packages["node_modules/<name>"]`. `npm ci` fails when a
name in `package.json` is absent from the lock, when the ranges disagree, or
when the resolved entry is missing. This checks exactly those three, for
`dependencies`, `devDependencies`, `optionalDependencies` and
`peerDependencies`, plus the two files' `name`/`version`.

WHY NOT JUST `npm ci --dry-run`. It answers the same question and it is what
the release runs, but on a cold runner it resolves the whole tree (seconds,
and network); this comparison is measured at about 0.05 s and cannot be
floored by a registry outage. The release workflow keeps the real `npm ci`.
The two together are the ruling: keep `npm ci`, and add a cheap sync check.

WHAT IT NEVER DOES. It never writes, never runs npm, never touches a
lockfile. `--package`/`--lock` exist so a fixture pair can be given to it
(used by `backend/test_desktop_lockfile_sync.py`); the paths are resolved
relative to the repository root otherwise.

Exit 0 = in sync. Exit 1 = every disagreement, then the ONE fix line:

    FIX  cd jarvis-desktop && npm install --package-lock-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_PACKAGE = REPO / "jarvis-desktop" / "package.json"
DEFAULT_LOCK = REPO / "jarvis-desktop" / "package-lock.json"

#: The dependency maps a root package can carry. `npm ci` reconciles every one
#: of them; leaving one out is how a lockfile drifts silently (a test-only
#: package is exactly what #1319 added).
FIELDS = ("dependencies", "devDependencies", "optionalDependencies",
          "peerDependencies")

#: The single command that makes the pair agree again. Named in the failure so
#: nobody has to guess, and quoted in the reports the guard writes.
FIX = "cd jarvis-desktop && npm install --package-lock-only"


def _load(path: Path):
    """(data, problem). A missing or unreadable file is a problem, not a crash."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read {path}: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"{path} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, f"{path} is not a JSON object"
    return data, None


def _deps(entry, field):
    """A dependency map from a package.json or lockfile root entry."""
    value = entry.get(field) or {}
    return value if isinstance(value, dict) else {}


def compare(package: dict, lock: dict) -> list[str]:
    """Every way `lock` disagrees with `package`. An empty list means in sync."""
    problems: list[str] = []

    for field in ("name", "version"):
        want = package.get(field)
        got = lock.get(field)
        if want and got and want != got:
            problems.append(f"name/version disagree: package.json says "
                            f"{field}={want!r}, package-lock.json says {got!r}")

    version = lock.get("lockfileVersion")
    if version is None:
        problems.append("package-lock.json has no lockfileVersion")
        return problems
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        problems.append(
            f"package-lock.json (lockfileVersion {version}) has no `packages` "
            "table, so a dependency cannot be shown to resolve; regenerate it "
            "with the fix below")
        return problems
    root = packages.get("")
    if not isinstance(root, dict):
        problems.append("package-lock.json has no root package entry "
                        "(packages[\"\"])")
        return problems

    for field in FIELDS:
        want = _deps(package, field)
        got = _deps(root, field)
        for name, want_range in sorted(want.items()):
            if name not in got:
                problems.append(
                    f"package-lock.json's root package is missing "
                    f"{name}@{want_range} ({field})")
            elif got[name] != want_range:
                problems.append(
                    f"{name} range disagrees ({field}): package.json asks for "
                    f"{want_range!r}, package-lock.json records {got[name]!r}")
        for name, got_range in sorted(got.items()):
            if name not in want:
                problems.append(
                    f"package-lock.json's root package lists {name}@{got_range} "
                    f"({field}) but package.json does not")

    for name in sorted(set(_deps(package, "dependencies"))
                       | set(_deps(package, "devDependencies"))
                       | set(_deps(package, "optionalDependencies"))):
        if f"node_modules/{name}" not in packages:
            problems.append(
                f"package-lock.json has no resolved entry for {name} "
                f"(packages[\"node_modules/{name}\"])")
    return problems


def check(package_path: Path = DEFAULT_PACKAGE,
          lock_path: Path = DEFAULT_LOCK) -> list[str]:
    """Every disagreement between the two files, each line plain enough to act on."""
    package, problem = _load(package_path)
    if problem:
        return [problem]
    lock, problem = _load(lock_path)
    if problem:
        return [problem]
    return compare(package, lock)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE,
                        help="the package.json to check")
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK,
                        help="the package-lock.json to check")
    args = parser.parse_args(argv)

    problems = check(args.package, args.lock)
    if not problems:
        package, _ = _load(args.package)
        count = sum(len(_deps(package, field)) for field in FIELDS)
        print(f"ok    {_rel(args.package)} and {_rel(args.lock)} agree "
              f"({count} dependenc{'y' if count == 1 else 'ies'})")
        return 0
    print(f"FAIL  {_rel(args.package)} and {_rel(args.lock)} are out of sync")
    for problem in problems:
        print(f"      {problem}")
    print(f"FIX   {FIX}")
    return 1


def _rel(path: Path) -> str:
    """The path as a reader would name it: repo-relative when it is inside."""
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
