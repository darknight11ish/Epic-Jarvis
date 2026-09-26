"""Check the backend's pinned Python packages: the lock is whole, and none has
a known security advisory.

    python3 tools/check_python_advisories.py            # both checks (CI)
    python3 tools/check_python_advisories.py --offline  # the lock only, no network

WHAT IT CHECKS

1. backend/requirements.lock (offline). Every package backend/requirements.txt
   asks for is pinned there with `==`, and every pinned line carries at least
   one `--hash`. pip's hash-checking mode refuses a lock with a line missing
   either, so this finds it here first - and it finds a requirement added to
   requirements.txt but never locked.

2. Advisories (network). For every (name, version) pinned in the lock - on
   every platform and Python version the lock covers, not only this one - it
   asks PyPI's own JSON API (https://pypi.org/pypi/<name>/<version>/json)
   for its `vulnerabilities` list. That list is the Python Packaging
   Authority's advisory database, the same data `pip-audit` reads by
   default. Any advisory not marked withdrawn fails the check, named with
   its id and the version that fixes it.

Why not `pip-audit` itself: it only checks the lines whose markers match the
machine it runs on (here, Linux), so Windows-only packages and the other
Python versions' pins would go unchecked - and it would be one more tool to
pin. This uses the standard library only.

Nothing is sent but the package name and version, with a generic
User-Agent. No account, key or address of the owner is ever in a request.

HOW THE LOCK IS MADE (by hand, when a package changes or once a month):

    uv pip compile backend/requirements.txt --universal --generate-hashes \\
        --python-version 3.10 --exclude-newer <7 days ago, e.g. 2026-09-19T00:00:00Z> \\
        --no-header -o backend/requirements.lock

`--exclude-newer` is the 7-day wait: a release younger than a week is not
picked, so a hijacked release has time to be noticed and pulled first.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQS = ROOT / "backend" / "requirements.txt"
LOCK = ROOT / "backend" / "requirements.lock"
USER_AGENT = "python-advisory-check/1 (+https://pypi.org)"
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_names(text: str) -> set:
    """The packages requirements.txt asks for (requirement lines only)."""
    out = set()
    for raw in text.splitlines():
        s = raw.split("#", 1)[0].strip()
        if not s or s.startswith("-"):
            continue
        out.add(canonical(re.split(r"[\s;<>=!~\[]", s, maxsplit=1)[0]))
    return out


def lock_entries(text: str) -> tuple:
    """([(name, version, hashes)], [problems]). A logical line is joined
    across its backslash continuations first."""
    entries, problems, logical = [], [], []
    cur = ""
    for raw in text.splitlines():
        s = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not s.strip():
            if cur:
                logical.append(cur)
                cur = ""
            continue
        if s.endswith("\\"):
            cur += s[:-1] + " "
            continue
        logical.append(cur + s)
        cur = ""
    if cur:
        logical.append(cur)
    for line in logical:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _PIN.match(s)
        if not m:
            problems.append(f"not pinned with ==: {s[:80]}")
            continue
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})\b", s)
        if not hashes:
            problems.append(f"{m.group(1)}=={m.group(2)} has no --hash")
        entries.append((canonical(m.group(1)), m.group(2), hashes))
    return entries, problems


def check_lock() -> tuple:
    """(pins, problems)."""
    if not LOCK.is_file():
        return [], [f"{LOCK.relative_to(ROOT)} is missing"]
    entries, problems = lock_entries(LOCK.read_text(encoding="utf-8"))
    pinned = {n for n, _v, _h in entries}
    for name in sorted(requirement_names(REQS.read_text(encoding="utf-8")) - pinned):
        problems.append(f"{name} is in requirements.txt but not in requirements.lock - "
                        f"make the lock again (the command is at the top of this file)")
    return sorted({(n, v) for n, v, _h in entries}), problems


def advisories(name: str, version: str, fetch=None) -> list:
    """PyPI's advisories for this exact release, withdrawn ones left out."""
    url = (f"https://pypi.org/pypi/{urllib.parse.quote(name)}/"
           f"{urllib.parse.quote(version)}/json")
    if fetch is None:
        def fetch(u):
            req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT,
                                                     "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
    last = None
    for attempt in range(3):
        try:
            data = fetch(url)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise LookupError(f"{name}=={version} is not on PyPI") from None
            last = exc
        except Exception as exc:      # a network hiccup: try twice more
            last = exc
        time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"PyPI did not answer for {name}=={version}: "
                           f"{type(last).__name__}")
    return [v for v in (data.get("vulnerabilities") or [])
            if isinstance(v, dict) and not v.get("withdrawn")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--offline", action="store_true",
                    help="check the lock only; do not ask PyPI about advisories")
    a = ap.parse_args(argv)
    pins, problems = check_lock()
    for p in problems:
        print(f"FAIL  {p}")
    print(f"{'ok   ' if not problems else 'FAIL '} requirements.lock: {len(pins)} pinned "
          f"releases, every one with a hash, every requirement locked")
    if problems or a.offline:
        return 1 if problems else 0
    found = 0
    for name, version in pins:
        try:
            vulns = advisories(name, version)
        except Exception as exc:
            print(f"FAIL  {name}=={version}: {exc}")
            found += 1
            continue
        for v in vulns:
            found += 1
            fixed = ", ".join(v.get("fixed_in") or []) or "no fixed version listed"
            print(f"FAIL  {name}=={version}: {v.get('id')} "
                  f"({', '.join(v.get('aliases') or []) or 'no alias'}) - fixed in {fixed}")
    print(f"{'ok   ' if not found else 'FAIL '} advisories: {len(pins)} releases checked "
          f"against PyPI, {found} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
