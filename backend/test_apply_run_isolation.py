"""Two runs of apply-patches.ps1 in the same second must not share a folder.

    python3 test_apply_run_isolation.py

THE BUG THIS PROVES. apply-patches.ps1 names its throwaway folders from the
clock at ONE-SECOND resolution:

    $Stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
    $rehearsal = Join-Path ([IO.Path]::GetTempPath()) "jarvis-rehearsal-$Stamp"

so two runs started in the same second compute the SAME name for the rehearsal
folder, the LF copy of the patches, the backup folders and the test state
folder. And the first thing Reset-Rehearsal does with that path is

    Remove-Item -LiteralPath $rehearsal -Recurse -Force

which is not "share the folder" but "delete the other run's folder while it is
still applying patches in it". The owner runs this script by hand after every
merge, and a run that loses its rehearsal half-way is the one step that can
leave his install half-patched. Two runs in one second also shared a single
transcript file. Reported after three wasted runs in one day (2026-10-06).

HOW IT IS PROVED, AND WHY THE CLOCK IS DOUBLED. Two runs started by hand
cannot be relied on to land in the same second, so this suite does not wait for
luck: the run is started through a tiny wrapper that defines a `Get-Date` of
its own, returning one fixed second. That is the only thing the wrapper
changes, and the CONTROL check below shows it took effect - a run's transcript
file comes out stamped with that second. Two runs then really are in one
second, every time, on any machine.

The folder a same-second NEIGHBOUR would own is stood up beforehand as a
"decoy": the name the seconds-only stamp gives (`jarvis-rehearsal-<second>`),
holding a file. Run 1's rehearsal folder, if the name is the clock's, is that
same path. So "is the decoy still there afterwards, byte for byte" is the
question "did run 2 delete run 1's folder", asked deterministically - no race to
wait for.

WHAT EACH CHECK FAILS ON. Every check here fails on the script BEFORE the fix
and passes after it (the fix is in the same change; the checks were written
against the old script first, by running this file with JARVIS_TEST_APPLY_PS1
pointed at a copy of the old one). The last check is a regression guard for
"the run still cleans up after itself" - a stale-folder leak would be a
different bug, and removing the cleanup must not be a way to pass this.

HOW IT RUNS THE REAL SCRIPT. Through test_apply_outcomes.py's own harness: the
real apply-patches.ps1 with only its patch list cut to two independent patches,
in a small repository of symlinks, against a backend built from those two
patches' pre-images, so the run really applies them. Importing a suite for a
helper is this repository's way already (test_apply_outcomes.py imports
test_apply_line_endings.py). -Force is passed because the owner's own Jarvis is
usually running while a suite runs, and the "close Jarvis first" check is about
the owner's install, not this throwaway backend.

Skipped where there is no PowerShell 7 (pwsh). Standard library + git + pwsh.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_apply_outcomes as O  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

PWSH = O.PWSH
PS1 = Path(os.environ.get("JARVIS_TEST_APPLY_PS1")
           or HERE.parent / "scripts" / "apply-patches.ps1")

# The second every run is told it is. The value does not matter; that every run
# in one case gets the SAME one is the whole point.
FROZEN = "2026-01-01-000000"

#: A run this suite starts rehearses two patches: seconds, not minutes. A run
#: still going after this is hung, and is killed so a check can say so.
RUN_SECONDS = 300

# A clock double, and nothing else. `Get-Date` is a cmdlet, so a function of
# that name wins inside the script it calls (functions beat cmdlets in
# PowerShell's command precedence) and the script reads the one fixed second.
WRAPPER = """# a clock double, for the test only: runs that must land in one second.
param([string] $Script, [string] $Backend, [string] $Frozen)
function Get-Date {
    param([string] $Format)
    $inv = [Globalization.CultureInfo]::InvariantCulture
    $d = [datetime]::ParseExact($Frozen, 'yyyy-MM-dd-HHmmss', $inv)
    if ($Format) { return $d.ToString($Format, $inv) }
    return $d
}
& $Script -BackendPath $Backend -SkipTests -SkipPackages -Force
exit $LASTEXITCODE
"""

DECOY_TEXT = "run 1 is applying patches in here\n"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond and detail:
        print("        " + str(detail)[-700:])


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print("skip  " + why)


def frozen_wrapper(tmp: Path) -> Path:
    path = tmp / "frozen-clock.ps1"
    path.write_text(WRAPPER, encoding="utf-8", newline="\n")
    return path


def child_env(temp: Path, cfg: Path) -> dict:
    """This run's own TEMP and config folder - never the owner's.

    TEMP is what `[IO.Path]::GetTempPath()` reads, so it is where every
    throwaway folder this run makes will land, and where the decoy stands."""
    env = dict(os.environ)
    env["TEMP"] = str(temp)
    env["TMP"] = str(temp)
    env["OPENJARVIS_CONFIG_DIR"] = str(cfg)
    env.pop("JARVIS_FRAMEWORK_TOML", None)
    return env


def start(wrapper: Path, script: Path, backend: Path, env: dict, log: Path):
    """Start one run, its output going to a FILE.

    Not into a pipe: a run prints dozens of lines, and a full pipe would stall
    it - a hang in the suite instead of a failure with a reason."""
    handle = open(log, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [PWSH, "-NoProfile", "-File", str(wrapper), "-Script", str(script),
         "-Backend", str(backend), "-Frozen", FROZEN],
        stdout=handle, stderr=subprocess.STDOUT, text=True, env=env)
    return proc, handle


def watch(proc, handle, temp: Path) -> set:
    """Wait for a run, looking in TEMP while it works.

    The rehearsal folder is removed in a `finally`, so the only moment a run's
    own name can be seen is while it is running. The caller reports a miss as a
    skip, never as a pass.

    A run that hangs is killed rather than waited for forever, so a hang fails a
    check with a reason instead of stalling the whole suite."""
    seen = set()
    deadline = time.monotonic() + RUN_SECONDS
    while proc.poll() is None:
        if time.monotonic() > deadline:
            proc.kill()
        try:
            seen |= {d.name for d in temp.iterdir() if d.is_dir()}
        except OSError:
            pass          # a folder vanishing mid-scan is the run's own cleanup
        time.sleep(0.005)
    handle.close()
    return seen


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def transcripts(backend: Path) -> list:
    return sorted(p.name for p in (backend / "_jarvis-logs").glob("apply-patches-*.txt"))


def t_one_second_is_not_one_run():
    """The reproduction: two runs, one second, one folder name."""
    if not PWSH:
        return skip("no PowerShell 7 (pwsh) here")
    tmp = O.tmpdir()
    temp = tmp / "temp"
    temp.mkdir()
    cfg = tmp / "cfg"
    cfg.mkdir()
    root = O.mini_repo(tmp / "r")
    be = tmp / "be"
    O.build_backend(be)
    script = root / "scripts" / "apply-patches.ps1"
    wrapper = frozen_wrapper(tmp)

    # What run 1's rehearsal folder is called when the name is the clock's.
    # Run 2 in the same second computes that same name, and opens on it with
    # `Remove-Item -Recurse -Force` - so this is run 1's folder, and the
    # question is whether run 2 walks over it.
    decoy = temp / f"jarvis-rehearsal-{FROZEN}"
    decoy.mkdir()
    (decoy / "run-1-still-working.txt").write_text(DECOY_TEXT, encoding="utf-8")

    log1, log2 = tmp / "run1.log", tmp / "run2.log"
    proc1, handle1 = start(wrapper, script, be, child_env(temp, cfg), log1)
    seen1 = watch(proc1, handle1, temp) - {decoy.name}
    proc2, handle2 = start(wrapper, script, be, child_env(temp, cfg), log2)
    seen2 = watch(proc2, handle2, temp) - {decoy.name}
    out1, out2 = read(log1), read(log2)

    logs = transcripts(be)
    check("CONTROL: the clock double took effect - a run's transcript carries the frozen second",
          len(logs) >= 1 and all(n.startswith(f"apply-patches-{FROZEN}") for n in logs), logs)
    check("CONTROL: run 1 finished cleanly, so the folders it made are a real run's",
          proc1.returncode == 0, out1[-700:])
    check("CONTROL: run 2 finished cleanly too", proc2.returncode == 0, out2[-700:])

    check("the rehearsal folder a same-second neighbour would own is still there, byte for byte",
          decoy.is_dir() and (decoy / "run-1-still-working.txt").is_file()
          and read(decoy / "run-1-still-working.txt") == DECOY_TEXT,
          f"folder there: {decoy.is_dir()}, now holds: "
          f"{sorted(p.name for p in decoy.glob('*')) if decoy.is_dir() else 'gone'}")

    check("two runs in one second leave two transcripts of their own, not one shared file",
          len(logs) == 2 and logs[0] != logs[1], logs)

    if not (seen1 or seen2):
        skip("neither run's rehearsal folder was caught in flight (both were too quick)")
    else:
        check("each run rehearsed in a folder of its own, not in the seconds-only name",
              bool(seen1) and bool(seen2) and not (seen1 & seen2),
              f"run 1: {sorted(seen1)}  run 2: {sorted(seen2)}")

    left = sorted(d.name for d in temp.iterdir() if d.is_dir())
    check("both runs cleaned up their own folders (the decoy is the only thing left)",
          left == [decoy.name], left)


def t_two_runs_at_once_both_finish():
    """Two runs started together, in one second, sharing one TEMP."""
    if not PWSH:
        return skip("no PowerShell 7 (pwsh) here")
    tmp = O.tmpdir()
    temp = tmp / "temp"
    temp.mkdir()
    wrapper = frozen_wrapper(tmp)

    runs = {}
    for which in ("a", "b"):
        root = O.mini_repo(tmp / f"r{which}")
        be = tmp / f"be{which}"
        O.build_backend(be)
        cfg = tmp / f"cfg{which}"
        cfg.mkdir()
        log = tmp / f"run-{which}.log"
        # Both are started before either is waited for: they really overlap.
        runs[which] = (be, log, start(wrapper, root / "scripts" / "apply-patches.ps1",
                                      be, child_env(temp, cfg), log))

    for be, log, (proc, handle) in runs.values():
        watch(proc, handle, temp)

    codes = {w: p.returncode for w, (be, log, (p, h)) in runs.items()}
    outs = {w: read(log) for w, (be, log, (p, h)) in runs.items()}
    check("two runs at once in one second both complete", all(c == 0 for c in codes.values()),
          f"{codes}\n--- a ---\n{outs['a'][-400:]}\n--- b ---\n{outs['b'][-400:]}")

    logs = {w: transcripts(be) for w, (be, log, (p, h)) in runs.items()}
    only = {w: (v[0] if len(v) == 1 else None) for w, v in logs.items()}
    check("... each writing its own transcript, not one file both of them opened",
          only["a"] and only["b"] and only["a"] != only["b"], logs)


def main():
    for fn in (t_one_second_is_not_one_run, t_two_runs_at_once_both_finish):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    for d in O.TMPDIRS:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
