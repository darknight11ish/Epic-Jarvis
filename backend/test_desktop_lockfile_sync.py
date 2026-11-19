"""test_desktop_lockfile_sync.py - the CI guard that stops a desktop lockfile desync.

    python3 backend/test_desktop_lockfile_sync.py

WHY THIS EXISTS (2026-11-18, the two CI guards the external review asked for).
PR #1319 added `typescript` to `jarvis-desktop/package.json` and never
regenerated `jarvis-desktop/package-lock.json`. `Desktop release` installs
with `npm ci`, which refuses a desynced pair, so EIGHT release runs failed at
that step from that moment - for two days, unnoticed, because no required job
ran `npm ci`. #1386 fixed the lockfile. The guard is
`tools/check_desktop_lockfile.py`, wired into a REQUIRED job
(`frontend-shard` -> the ruleset's required `frontend` check), and this suite
proves both halves of it:

  1. it FAILS on a deliberately desynced pair, naming the dependency and the
     one fix command - the #1319 shape, as a fixture, not by editing the real
     files;
  2. it PASSES on the real `jarvis-desktop` pair;
  3. it is wired where a merge is blocked, not only into informational
     `audit`; and the release workflow still installs with `npm ci`.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_desktop_lockfile.py"
CI_YML = REPO / ".github" / "workflows" / "ci.yml"
RELEASE_YML = REPO / ".github" / "workflows" / "desktop-release.yml"
PACKAGE = REPO / "jarvis-desktop" / "package.json"
LOCK = REPO / "jarvis-desktop" / "package-lock.json"
FIX = "npm install --package-lock-only"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _run(package, lock, timeout=60):
    """Run the real checker on a fixture pair. (exit code, combined output)."""
    proc = subprocess.run(
        [sys.executable, "-B", str(TOOL),
         "--package", str(package), "--lock", str(lock)],
        capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _pair(tmp: Path, package: dict, lock: dict):
    pkg = tmp / "package.json"
    lck = tmp / "package-lock.json"
    pkg.write_text(json.dumps(package, indent=2), encoding="utf-8")
    lck.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    return pkg, lck


#: A small in-sync pair in the shape the real desktop files have: one dev
#: dependency at the root and its resolved entry under node_modules/.
def _synced():
    package = {"name": "jarvis-desktop", "version": "0.2.0",
               "devDependencies": {"@tauri-apps/cli": "^2.12.0"}}
    lock = {
        "name": "jarvis-desktop",
        "version": "0.2.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {
            "": {"name": "jarvis-desktop", "version": "0.2.0",
                 "devDependencies": {"@tauri-apps/cli": "^2.12.0"}},
            "node_modules/@tauri-apps/cli": {"version": "2.12.4", "dev": True},
        },
    }
    return package, lock


# --------------------------------------------------------------------------
#   1. the real pair passes
# --------------------------------------------------------------------------
def t_the_real_desktop_pair_passes():
    check("the real jarvis-desktop/package.json is where this test expects",
          PACKAGE.is_file(), str(PACKAGE))
    check("the real jarvis-desktop/package-lock.json is there",
          LOCK.is_file(), str(LOCK))
    code, out = _run(PACKAGE, LOCK)
    check("the real desktop pair is in sync (the guard passes on the real files)",
          code == 0, out[-800:])
    check("... and the pass line names both files",
          "package.json" in out and "package-lock.json" in out, out[-200:])
    real = json.loads(PACKAGE.read_text(encoding="utf-8"))
    check("the real package.json still has a devDependency to compare",
          bool(real.get("devDependencies")), json.dumps(real)[:200])


# --------------------------------------------------------------------------
#   2. THE #1319 SHAPE: a package added to package.json, never to the lock
# --------------------------------------------------------------------------
def t_a_package_added_without_the_lock_fails():
    """The exact regression: typescript added to package.json alone."""
    package, lock = _synced()
    package["devDependencies"]["typescript"] = "^5.9.3"
    with tempfile.TemporaryDirectory() as raw:
        pkg, lck = _pair(Path(raw), package, lock)
        code, out = _run(pkg, lck)
    check("a package added to package.json and not the lockfile FAILS",
          code == 1, f"exit {code}\n{out[-800:]}")
    check("... and the failure names the missing package, its range and the field",
          "typescript@^5.9.3" in out and "devDependencies" in out, out[-800:])
    check("... and names the ONE fix command",
          FIX in out and "FIX" in out, out[-400:])
    check("... as a lockfile problem, not a crash",
          "FAIL" in out and "Traceback" not in out, out[-400:])


def t_a_resolved_entry_missing_fails():
    package, lock = _synced()
    del lock["packages"]["node_modules/@tauri-apps/cli"]
    with tempfile.TemporaryDirectory() as raw:
        pkg, lck = _pair(Path(raw), package, lock)
        code, out = _run(pkg, lck)
    check("a lockfile with no resolved entry for a dependency FAILS",
          code == 1, f"exit {code}\n{out[-800:]}")
    check("... and names the missing resolved entry",
          "node_modules/@tauri-apps/cli" in out, out[-800:])


def t_a_range_disagreement_fails():
    package, lock = _synced()
    lock["packages"][""]["devDependencies"]["@tauri-apps/cli"] = "^2.11.0"
    with tempfile.TemporaryDirectory() as raw:
        pkg, lck = _pair(Path(raw), package, lock)
        code, out = _run(pkg, lck)
    check("a range that disagrees between the two files FAILS", code == 1,
          f"exit {code}\n{out[-800:]}")
    check("... and names both ranges",
          "^2.12.0" in out and "^2.11.0" in out, out[-800:])


def t_a_lock_only_dependency_fails():
    package, lock = _synced()
    lock["packages"][""]["devDependencies"]["left-pad"] = "^1.3.0"
    with tempfile.TemporaryDirectory() as raw:
        pkg, lck = _pair(Path(raw), package, lock)
        code, out = _run(pkg, lck)
    check("a dependency the lockfile keeps and package.json does not FAILS",
          code == 1, f"exit {code}\n{out[-800:]}")
    check("... naming what the lockfile lists and package.json does not",
          "left-pad" in out, out[-800:])


def t_a_version_mismatch_fails():
    package, lock = _synced()
    lock["version"] = "0.1.0"
    with tempfile.TemporaryDirectory() as raw:
        pkg, lck = _pair(Path(raw), package, lock)
        code, out = _run(pkg, lck)
    check("a lockfile written for another version FAILS", code == 1,
          f"exit {code}\n{out[-800:]}")
    check("... and names both versions", "0.2.0" in out and "0.1.0" in out,
          out[-800:])


def t_a_broken_or_missing_file_is_a_plain_failure():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        pkg, lck = _pair(tmp, *_synced())
        missing = tmp / "no-such-lock.json"
        code, out = _run(pkg, missing)
        check("a missing lockfile FAILS, naming the path", code == 1
              and "no-such-lock.json" in out, f"exit {code}\n{out[-500:]}")
        lck.write_text("{not json", encoding="utf-8")
        code, out = _run(pkg, lck)
        check("a lockfile that is not JSON FAILS, saying so", code == 1
              and "not valid JSON" in out, f"exit {code}\n{out[-500:]}")
        check("... and no failure is a traceback", "Traceback" not in out,
              out[-300:])


def t_the_check_never_writes():
    package, lock = _synced()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        pkg, lck = _pair(tmp, package, lock)
        before = {p: p.read_bytes() for p in (pkg, lck)}
        code, _out = _run(pkg, lck)
        after = {p: p.read_bytes() for p in (pkg, lck)}
    check("the checker passes the synced fixture", code == 0, str(code))
    check("... and writes neither file", before == after)


# --------------------------------------------------------------------------
#   3. where it is wired: a REQUIRED job, not informational `audit`
# --------------------------------------------------------------------------
def _job_block(text: str, name: str) -> str:
    """One job's lines in a workflow, from `  <name>:` to the next `  <job>:`."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.rstrip() == f"  {name}:"), None)
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[i]):
            end = i
            break
    return "\n".join(lines[start:end])


def _code(block: str) -> str:
    """A job's lines with comments removed - the YAML that actually runs."""
    return "\n".join(line for line in block.splitlines()
                     if not line.lstrip().startswith("#"))


def _required_check_names() -> set:
    """The check names `backend/jarvis_github.py` calls REQUIRED_CHECKS."""
    tree = ast.parse((HERE / "jarvis_github.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "REQUIRED_CHECKS"
                and isinstance(node.value, (ast.Tuple, ast.List))):
            return {e.value for e in node.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


def t_the_lockfile_check_is_in_a_required_job():
    if not CI_YML.is_file():
        check("ci.yml is where this test expects it", False, str(CI_YML))
        return
    text = CI_YML.read_text(encoding="utf-8")
    shard = _job_block(text, "frontend-shard")
    frontend = _job_block(text, "frontend")
    check("ci.yml has the `frontend-shard` job this guard lives in",
          bool(shard), "frontend-shard")
    check("the required `frontend` check is the aggregator over `frontend-shard`",
          bool(re.search(r"needs:\s*\[?[^\]\n]*frontend-shard",
                         frontend or "")) and "name: frontend" in (frontend or ""),
          (frontend or "")[:400])
    check("`frontend` is one of the repository's REQUIRED checks (the ruleset's"
          " seven)", "frontend" in _required_check_names(),
          str(sorted(_required_check_names())))
    checker = "tools/check_desktop_lockfile.py"
    check("the required frontend chain runs the lockfile checker",
          checker in _code(shard), "not found in frontend-shard")
    check("... in shard 1 only, so the four shards do not run it four times",
          bool(re.search(r"if:\s*matrix\.shard\s*==\s*1", _code(shard))),
          _code(shard)[:400])
    audit = _job_block(text, "audit")
    check("the check is not ONLY informational `audit`",
          not (checker in _code(audit) and checker not in _code(shard)))


def t_the_release_keeps_npm_ci():
    """The ruling: keep `npm ci` - never fall back to `npm install` in release CI."""
    if not RELEASE_YML.is_file():
        check("desktop-release.yml is where this test expects it", False,
              str(RELEASE_YML))
        return
    block = _code(_job_block(RELEASE_YML.read_text(encoding="utf-8"), "build"))
    check("the desktop release still installs with `npm ci`",
          re.search(r"^\s*run:\s*npm ci\b", block, re.M) is not None,
          block[:400])
    installs = re.findall(r"^\s*run:\s*npm install\b.*$", block, re.M)
    check("... and never falls back to `npm install`", not installs,
          "\n".join(installs))
    check("the fix command the guard prints is the lockfile-only install, not a"
          " full install", FIX == "npm install --package-lock-only")


def main():
    for fn in (t_the_real_desktop_pair_passes,
               t_a_package_added_without_the_lock_fails,
               t_a_resolved_entry_missing_fails,
               t_a_range_disagreement_fails,
               t_a_lock_only_dependency_fails,
               t_a_version_mismatch_fails,
               t_a_broken_or_missing_file_is_a_plain_failure,
               t_the_check_never_writes,
               t_the_lockfile_check_is_in_a_required_job,
               t_the_release_keeps_npm_ci):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
