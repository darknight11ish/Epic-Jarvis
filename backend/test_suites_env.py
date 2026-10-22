"""`backend/run_suites.py` is HERMETIC by default - the ambient JARVIS_BACKEND
is ignored unless the caller asks for it explicitly.

    python3 test_suites_env.py

WHY THIS EXISTS (Ruling 11, 2026-10-21). `JARVIS_BACKEND` is set for the
owner's Windows account on this PC, pointing at the LIVE backend folder. The
runner used to read it whenever it was set, so a plain
`python -B backend/run_suites.py` - the command the README and every agent
runs - tested the live folder without the person typing anything. R1 makes the
default a throwaway staged copy and adds two explicit live modes,
`--use-env-backend` and `--backend-path DIR`, each announced with a loud
one-line banner on stdout.

WHAT IT PROVES, and each check BITES - it fails on the old behaviour:
1. A canary `JARVIS_BACKEND` is IGNORED by a default run: the output carries
   the "Note: ignoring ambient JARVIS_BACKEND" banner, the run stages a copy
   ("(staged: ..." on the backend line), and the canary folder is never
   imported or written to. On the old code the canary WAS the backend.
2. `--use-env-backend` reaches the canary and says "LIVE MODE ... (--
   use-env-backend)".
3. `--backend-path DIR` reaches DIR and says "LIVE MODE ... (--backend-path)".
4. Either explicit mode without a usable folder is REFUSED (exit 2, plain
   words), never silently replaced by a staged copy; the two together are
   refused.
5. `--state-env` still works and still reads the ambient variable - that is
   the patcher's own subcommand, which sets it explicitly for its own child.
6. No `jarvis-sweep-*` / `jarvis-direct-*` / `jarvis-staged-backend-*` folder
   is left behind by any of these runs (each subprocess gets its own TEMP, so
   the check cannot see another run's folders).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

# NOTE: no `require_shipped("run_suites.py")` here on purpose - the runner is
# test plumbing, not a shipped module (backend/_where.NOT_SHIPPED), so the
# staged copy this suite itself runs against does not contain it; the copy
# under test is the repository's own, at HERE/run_suites.py.

RUNNER = HERE / "run_suites.py"
#: A real suite, fast and hermetic (12 checks, reads the tree only). Its name
#: must be a valid one or the runner treats the argument as a typo - and a
#: mistyped name is a FAILURE there, on purpose.
FAST_SUITE = "test_no_scratch_in_the_tree.py"
BANNER_IGNORED = "[run_suites] Note: ignoring ambient JARVIS_BACKEND"
BANNER_LIVE = "[run_suites] LIVE MODE: running against un-staged backend at"

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} ({why})")


def _canary(root: Path) -> tuple:
    """A folder that would be obvious if anything imported from it."""
    folder = root / "canary-backend"
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / "CANARY_WAS_IMPORTED.txt"
    (folder / "jarvis_memory.py").write_text(
        "open(r'%s', 'w').write('imported this folder')\n" % marker,
        encoding="utf-8")
    return folder, marker


def _env(temp: Path, **overrides) -> dict:
    """A child environment with its OWN TEMP, so leftovers are measurable."""
    temp.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in os.environ.items()
             if k not in ("JARVIS_BACKEND", "OPENJARVIS_CONFIG_DIR",
                          "JARVIS_CONFIG_DIR", "JARVIS_INSIDE_PATCHER")}
    clean.update({
        "TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
        # The runner's own lock/state folder, never the owner's real one.
        "OPENJARVIS_CONFIG_DIR": str(temp / "config"),
    })
    clean.update(overrides)
    return clean


def _run(argv, env, timeout=180):
    result = subprocess.run(
        [sys.executable, "-B", str(RUNNER), *argv], cwd=str(REPO), env=env,
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or ""), result.stdout or ""


def _leftovers(temp: Path) -> list:
    if not temp.is_dir():
        return []
    return sorted(p.name for p in temp.iterdir()
                  if p.name.startswith(("jarvis-sweep-", "jarvis-direct-",
                                        "jarvis-staged-backend-",
                                        "jarvis-suite-state-")))


def t_default_run_ignores_the_ambient_backend():
    root = Path(tempfile.mkdtemp(prefix="jarvis-r1-default-"))
    try:
        canary, marker = _canary(root)
        env = _env(root / "tmp", JARVIS_BACKEND=str(canary))
        code, out, stdout = _run([FAST_SUITE], env)
        check("a default run still passes its one suite", code == 0, (code, out[-600:]))
        check("the first stdout line is the the 'ignoring ambient JARVIS_BACKEND' banner",
              stdout.splitlines()[:1] == [
                  "[run_suites] Note: ignoring ambient JARVIS_BACKEND (staging "
                  "hermetic copy; pass --use-env-backend to test live folder)"],
              stdout.splitlines()[:2])
        check("... and it says it staged a copy", "(staged: every shipped module, "
              "flattened)" in out, out[-600:])
        check("the canary backend can never be the one this run used",
              str(canary) not in out.replace(str(root / "tmp"), ""), 
              [line for line in out.splitlines() if str(canary) in line][:3])
        check("the canary folder was never imported (its marker is absent)",
              not marker.exists(), marker)
        check("no staging folder was left behind",
              _leftovers(root / "tmp") == [], _leftovers(root / "tmp"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_use_env_backend_is_an_explicit_live_mode():
    root = Path(tempfile.mkdtemp(prefix="jarvis-r1-env-"))
    try:
        canary, _marker = _canary(root)
        env = _env(root / "tmp", JARVIS_BACKEND=str(canary))
        code, out, _stdout = _run(["--use-env-backend", FAST_SUITE], env)
        check("--use-env-backend announces LIVE MODE with the flag",
              f"{BANNER_LIVE} {canary.resolve()} (--use-env-backend)" in out,
              out[:400])
        check("... and the backend line is the named folder, not a staged copy",
              f"backend: {canary.resolve()}" in out and "(staged:" not in out,
              out[:600])
        check("... it does not also print the ignoring banner",
              BANNER_IGNORED not in out, out[:300])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_backend_path_names_the_folder_outright():
    root = Path(tempfile.mkdtemp(prefix="jarvis-r1-path-"))
    try:
        canary, _marker = _canary(root)
        env = _env(root / "tmp")
        code, out, _stdout = _run(["--backend-path", str(canary), FAST_SUITE], env)
        check("--backend-path announces LIVE MODE with the flag",
              f"{BANNER_LIVE} {canary.resolve()} (--backend-path)" in out,
              out[:400])
        check("... and the backend line is the named folder",
              f"backend: {canary.resolve()}" in out and "(staged:" not in out,
              out[:600])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_explicit_modes_refuse_what_they_cannot_honour():
    root = Path(tempfile.mkdtemp(prefix="jarvis-r1-refuse-"))
    try:
        env = _env(root / "tmp")
        code, out, _stdout = _run(["--use-env-backend", FAST_SUITE], env)
        check("--use-env-backend without JARVIS_BACKEND is refused, not staged",
              code == 2 and "FAIL" in out and "JARVIS_BACKEND is not set" in out,
              (code, out[:300]))
        check("... and it started nothing", "backend:" not in out, out[:400])
        canary, _marker = _canary(root)
        code, out, _stdout = _run(
            ["--use-env-backend", "--backend-path", str(canary), FAST_SUITE], env)
        check("--use-env-backend and --backend-path together are refused",
              code == 2 and "pass one of them" in out, (code, out[:300]))
        missing = root / "not-a-folder"
        code, out, _stdout = _run(["--backend-path", str(missing), FAST_SUITE], env)
        check("a --backend-path that is not a folder is refused",
              code == 2 and "is not a folder" in out, (code, out[:300]))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_state_env_is_unchanged_and_still_reads_the_patcher_value():
    """The patcher sets JARVIS_BACKEND for its own child; --state-env keeps that."""
    root = Path(tempfile.mkdtemp(prefix="jarvis-r1-state-"))
    try:
        canary, _marker = _canary(root)
        env = _env(root / "tmp", JARVIS_BACKEND=str(canary))
        where = root / "suite-state"
        code, out, _stdout = _run(["--state-env", str(where)], env)
        check("--state-env still answers 0", code == 0, (code, out[-400:]))
        check("... printing the suite state variables, one KEY=VALUE a line",
              "OPENJARVIS_CONFIG_DIR=" in out, out[:400])
        check("... without the ambient-ignored banner (it is the patcher's own "
              "subcommand)", BANNER_IGNORED not in out, out[:300])
        check("... and without staging anything",
              "backend:" not in out and _leftovers(root / "tmp") == [],
              out[:300])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_updater_names_its_own_backend_explicitly():
    """The update's proof run must not depend on any environment variable."""
    sys.path.insert(0, str(REPO / "tools"))
    import update_backend as U  # noqa: E402

    cmd = U.suites_command(REPO, 14, REPO / "jarvis-backend")
    check("the updater passes --backend-path, not an ambient variable",
          "--backend-path" in cmd, cmd)
    check("... naming the folder it was given",
          str((REPO / "jarvis-backend").resolve()) in cmd, cmd)
    check("... and keeps the worker count and its own lock bypass",
          "--jobs" in cmd and cmd[cmd.index("--jobs") + 1] == "14"
          and U.LOCK_BYPASS_FLAG in cmd, cmd)


if __name__ == "__main__":
    for fn in (t_default_run_ignores_the_ambient_backend,
               t_use_env_backend_is_an_explicit_live_mode,
               t_backend_path_names_the_folder_outright,
               t_explicit_modes_refuse_what_they_cannot_honour,
               t_state_env_is_unchanged_and_still_reads_the_patcher_value,
               t_the_updater_names_its_own_backend_explicitly):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
