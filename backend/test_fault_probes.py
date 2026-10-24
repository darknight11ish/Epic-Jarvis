"""test_fault_probes.py - tools/check_fault_probes.py's own guard, and the
mutation-sanity proof that the probes can fail.

    python3 backend/test_fault_probes.py

WHY THIS SUITE EXISTS. A checker that has never failed is not evidence. Review
#2's harness (`tools/check_fault_probes.py`) claims each hermetic fault probe
proves a real recovery property of the shipped code - so this suite breaks
that code, one named mutation at a time, and requires the checker to say the
RIGHT probe failed for the RIGHT reason.

THE MUTATION-SANITY PROOF, in full: the shipped backend is copied to a
throwaway tree (never the working tree - a mutation is applied to the copy and
restored, or the copy is thrown away). One textual mutation is applied, the
checker is run against the copy, and three things must hold:

  1. the run FAILS (exit 1), so the checker is not a machine that always
     prints green;
  2. the probe named in the mutation's row is the one that failed, with that
     row's expected reason code, so it failed for the RIGHT reason rather than
     because the tree broke under it;
  3. at least three other probes still PASS, so the mutation is surgical and
     the checker is still measuring the other properties.

Then the mutation is undone (a fresh copy is made per mutation, so there is
nothing to restore) and the clean tree is run again: exit 0, five passes, no
failures. That last run is what makes the first five meaningful.

WHAT ELSE IS PINNED HERE:

  * the checker's BLOCKED rows are printed with "NOT a pass", never as PASS,
    and the JSON rows say `blocked` - the project's rule is that BLOCKED is
    never a pass (`docs/FIELD-TEST-MATRIX-2026-10-11.md`);
  * an unknown probe, and a root with no `backend/`, exit 2 ("no run"), never
    0 - "nothing was wrong" and "nothing was looked at" must not print the
    same line;
  * `--list` runs nothing and still prints every blocked row;
  * the probe ids the suite mutates still exist, so a rename cannot leave a
    mutation row pointing at nothing.

No network, no model, no real backend, no third-party package. The child
process the copy probe spawns is the checker's own; this suite spawns only
`sys.executable`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CHECKER = REPO / "tools" / "check_fault_probes.py"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   A throwaway tree, and a way to run the checker against it
# --------------------------------------------------------------------------

def _fresh_dir(base: Path, tag: str) -> Path:
    """mkdtemp's job, done with os.makedirs - see the checker's note: a folder
    mkdtemp made under the Windows agent sandbox refused every write beneath
    it (WinError 5), while an os.makedirs folder accepted files."""
    import uuid
    for _ in range(20):
        candidate = base / f"{tag}-{uuid.uuid4().hex[:10]}"
        try:
            os.makedirs(candidate)
            return candidate
        except FileExistsError:
            continue
    raise OSError(f"no fresh folder name under {base}")


def scratch_base() -> Path:
    """A folder this process may make subfolders in; temp first, then the
    repository's own gitignored scratch (the only place that works under the
    Windows agent sandbox this was written in)."""
    base = Path(tempfile.mkdtemp(prefix="fault-suite-"))
    try:
        _fresh_dir(base, "probe")
        return base
    except OSError:
        shutil.rmtree(base, ignore_errors=True)
    fallback = REPO / ".dsh-scratch" / "fault-probes-tmp"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def copytree_modules(dest: Path) -> Path:
    """A copy of the tree the checker imports from: every shipped module, the
    rebuilt overlay, and the side files beside them. Test files are not
    product code and are not copied."""
    backend = dest / "backend"
    backend.mkdir(parents=True)
    for src in sorted(HERE.glob("*.py")):
        if src.name.startswith("test_"):
            continue
        shutil.copy2(src, backend / src.name)
    rebuilt = HERE / "rebuilt"
    if rebuilt.is_dir():
        shutil.copytree(rebuilt, backend / "rebuilt")
    for side in sorted(HERE.glob("*.json")) + sorted(HERE.glob("*.lock")):
        shutil.copy2(side, backend / side.name)
    return dest


def _check_work() -> Path:
    """A SHORT scratch folder handed to the checker.

    The checker's own default already prefers this repository's
    `.dsh-scratch/`; naming it here as well keeps the sandbox paths short
    when the tree under test is a deep copy (Windows' 260-character limit
    broke `copytree` once - see the checker's `scratch_base` note)."""
    folder = REPO / ".dsh-scratch" / "fault-probes-tmp" / "checker-work"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def run_checker(root: Path, *args: str, json_out: bool = True):
    """(exit code, parsed json or None, raw output)."""
    argv = [sys.executable, "-B", str(CHECKER), "--root", str(root),
            "--workdir", str(_check_work()), *args]
    if json_out:
        argv.append("--json")
    done = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    payload = None
    if json_out:
        try:
            payload = json.loads(done.stdout)
        except ValueError:
            payload = None
    return done.returncode, payload, (done.stdout or "") + (done.stderr or "")


# --------------------------------------------------------------------------
#   One row per probe: the mutation, and the reason that must be reported
# --------------------------------------------------------------------------
#
# (probe id, file, (find, replace), expected reason, what the mutation means)
MUTATIONS = (
    ("fp-busy", "jarvis_sqlite.py",
     ('    "PRAGMA busy_timeout = 5000",\n', ""),
     "busy_timeout_not_5000",
     "the documented 5 s busy timeout is dropped from the four pragmas; the "
     "connection then reports sqlite3's own default instead of F10's value"),
    ("fp-winerror32", "jarvis_sqlite.py",
     ("    conn = sqlite3.connect(path, timeout=timeout, factory=_ClosingConnection)",
      "    conn = sqlite3.connect(path, timeout=timeout)"),
     "handle_left_open",
     "the closing-connection factory is dropped, so `with conn:` commits and "
     "leaves the OS handle open - the WinError 32 family this module exists for"),
    ("fp-corrupt-state", "jarvis_content_risk.py",
     ('    try:\n'
      '        return json.loads(STATE_PATH.read_text("utf-8"))\n'
      '    except Exception:\n'
      '        return {"pins": {}, "rush": {"latch": None, "hits": []}}\n',
      '    return json.loads(STATE_PATH.read_text("utf-8"))\n'),
     "state_crash",
     "the corrupt-state fallback is removed, so a truncated state file raises "
     "instead of answering the documented empty state"),
    ("fp-enospc", "jarvis_vault_organizer.py",
     ('    if free >= 0 and free < need:\n'
      '        return {"ok": False,\n'
      '                "why": f"the first-run copy needs about {_size_words(need)} and only "\n'
      '                       f"{_size_words(free)} is free beside the vault"}\n', ""),
     "enospc_allowed",
     "the free-space guard is removed from the copy pre-flight, so a copy is "
     "allowed with half the needed space free"),
    ("fp-torn-copy", "jarvis_vault_organizer.py",
     ('    base = vault.parent / f"{vault.name}{COPY_SUFFIX} ({day})"',
      '    base = vault / f"{COPY_SUFFIX.strip()} ({day})"'),
     "vault_changed",
     "the copy target moves INSIDE the vault, so a copy that dies partway "
     "changes the real vault - exactly what the copy-first rule forbids"),
)


def _mutate(folder: Path, name: str, find: str, replace: str) -> None:
    path = folder / "backend" / name
    text = path.read_text("utf-8")
    if find not in text:
        raise AssertionError(
            f"the mutation's text is not in {name} any more - the source moved; "
            f"update MUTATIONS in {Path(__file__).name}. Looking for:\n{find[:200]}")
    if text.count(find) > 1:
        raise AssertionError(f"the mutation's text appears {text.count(find)}x in {name}")
    path.write_text(text.replace(find, replace, 1), "utf-8")


def t_clean_tree_passes():
    base = _fresh_dir(scratch_base(), "clean")
    root = copytree_modules(base / "tree")
    code, payload, output = run_checker(root)
    check("the checker exits 0 on a clean copy of the shipped tree", code == 0, output[-800:])
    if payload is None:
        check("the checker printed parseable JSON", False, output[-500:])
        return
    check("five probes ran and none failed",
          payload.get("passed") == 5 and payload.get("failed") == 0,
          f"passed={payload.get('passed')} failed={payload.get('failed')}")
    ids = sorted(p["id"] for p in payload["probes"])
    check("all five probe ids are present",
          ids == sorted(m[0] for m in MUTATIONS), ids)
    check("every blocked row is reported as blocked, never as a pass",
          len(payload["blocked"]) == 7
          and all(row.get("why") and row.get("id") for row in payload["blocked"]),
          [row.get("id") for row in payload["blocked"]])
    check("the blocked rows are NOT probes, so no blocked id can be a pass",
          not ({row["id"] for row in payload["blocked"]} & set(ids)))


def t_every_mutation_is_caught_for_the_right_reason():
    for probe_id, name, (find, replace), reason, meaning in MUTATIONS:
        base = _fresh_dir(scratch_base(), probe_id)
        root = copytree_modules(base / "tree")
        try:
            _mutate(root, name, find, replace)
        except AssertionError as exc:
            check(f"{probe_id}: the mutation can still be applied", False, str(exc))
            continue
        code, payload, output = run_checker(root)
        check(f"{probe_id}: the mutated tree FAILS the run (exit 1)", code == 1,
              output[-900:])
        if payload is None:
            check(f"{probe_id}: the checker printed parseable JSON", False, output[-400:])
            continue
        failed = {p["id"]: p for p in payload["probes"] if p["status"] != "pass"}
        check(f"{probe_id}: the tree is rejected by THAT probe", set(failed) == {probe_id},
              f"failed probes were {sorted(failed)}")
        if probe_id in failed:
            check(f"{probe_id}: it fails for the RIGHT reason ({reason})",
                  failed[probe_id].get("reason") == reason,
                  f"reason was {failed[probe_id].get('reason')!r}: "
                  f"{failed[probe_id].get('detail', '')[:300]}")
        check(f"{probe_id}: the other four probes still pass, so the mutation is surgical",
              payload.get("passed") == 4,
              f"passed={payload.get('passed')} (mutation: {meaning})")


def t_a_blocked_row_is_never_a_pass():
    code, _payload, output = run_checker(REPO, json_out=False)
    _code, payload, _out = run_checker(REPO, json_out=True)
    check("the checkout's own tree is clean for the checker", code == 0, output[-600:])
    blocked_lines = [ln for ln in output.splitlines() if ln.startswith("BLOCKED ")]
    check("the text output prints a BLOCKED line for every blocked row",
          len(blocked_lines) == 7, f"{len(blocked_lines)} line(s)")
    check("no BLOCKED line is labelled PASS",
          all("PASS" not in ln.split()[0] for ln in blocked_lines))
    check("the summary says the blocked rows are not passes",
          "BLOCKED rows are not passes" in output)
    if payload:
        check("no blocked scenario appears among the probes that ran",
              not ({row["id"] for row in payload["blocked"]}
                   & {p["id"] for p in payload["probes"]}))


def t_no_run_is_never_a_pass():
    code, _payload, output = run_checker(REPO, "--probe", "fp-does-not-exist")
    check("an unknown probe exits 2 and says NO RUN", code == 2 and "NO RUN" in output,
          f"exit {code}: {output[-300:]}")
    empty = _fresh_dir(scratch_base(), "not-a-tree")
    code, _payload, output = run_checker(empty)
    check("a root with no backend/ exits 2 and says NO RUN",
          code == 2 and "NO RUN" in output, f"exit {code}: {output[-300:]}")
    done = subprocess.run([sys.executable, "-B", str(CHECKER), "--list"],
                          cwd=str(REPO), capture_output=True, text=True, timeout=120)
    check("--list exits 0 and names every probe without running one",
          done.returncode == 0 and done.stdout.count("PROBE ") == 5,
          done.stdout[-400:])
    check("--list still prints every blocked row",
          done.stdout.count("BLOCKED ") == 7, done.stdout[-600:])


def main() -> int:
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("t_") and callable(f)]
    for name, fn in tests:
        print(f"--- {name} ---")
        try:
            fn()
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    print(f"      ({len(tests)} t_ function(s) were found by name and run)")
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
