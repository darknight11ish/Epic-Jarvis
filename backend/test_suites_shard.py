"""The shard selector: every suite in exactly one slice, and no silent empty shard.

    python3 backend/test_suites_shard.py

WHY THIS EXISTS (2026-11-13). The required `backend` CI job ran
`python backend/run_suites.py` once, and by 2026-11-13 that sweep took 80-90
minutes against the job's own 90-minute wall: PR #1241's run 43547214198 was
CANCELLED at 90m16s with 88m41s of it in the suite step alone, so a good pull
request died of the clock rather than of a test. That job is now four
`run_suites.py --shard I/N` runs in parallel, fanned into the one required
`backend` check (`.github/workflows/ci.yml`, the `backend-shard` job).

A SPLIT IS ONLY AS GOOD AS ITS WORST SILENT FAILURE, and there are two:
  * a suite in no shard, or in two - a test that never runs while the green
    says nothing about it; and
  * a shard with nothing to run - which used to be able to exit 0 with
    "0 passed, 0 skipped, 0 failed", looking exactly like a pass.

WHAT THIS PROVES, and each check BITES. On the code before the selector existed
there is no `run_suites.shard_suites`, so this module raises on import and the
suite FAILS - it cannot pass by not running. Beyond that:
1. Over shard counts 1 to 8, the shards of one run PARTITION the runner's own
   list: every `backend/test_*.py` file is in exactly one shard. `--shard 1/1`
   is the whole list in the same order, which is the old behaviour.
2. A shard is a slice of the sorted list, not a reshuffle: the order inside a
   shard is the runner's order, and two calls give the same split.
3. Shard counts and indices outside the range are REFUSED by the real command
   line with exit 2 and a plain sentence, before anything is staged. Each check
   names that sentence, so a reverted runner's generic "not an option this
   runner knows" refusal cannot satisfy it by accident.
4. A shard that selects no suite is a FAILURE, not an empty pass: the real
   runner is asked for `--shard 1000/10000` (more shards than suites) and must
   exit non-zero naming the broken split. Without the guard it prints 0 passed
   and exits 0 - the exact green this rule exists to stop.
5. The command line really APPLIES the split: two fast suites named on the
   command line, split in half, run one each - `--shard 1/2` takes the first
   and `--shard 2/2` the second - so `--shard` cannot be parsed and ignored.
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
import run_suites as R  # noqa: E402
from _where import REPO  # noqa: E402

#: The repository's own runner - not a staged copy, because `run_suites.py` is
#: test plumbing, NOT a shipped module (`test_shipped_modules.NOT_SHIPPED`), so
#: the staged backend a suite runs against does not contain it.
RUNNER = HERE / "run_suites.py"

#: Two suites that pass in a fraction of a second (measured 0.2 s each on
#: 2026-11-13) and read the tree only, so the command-line checks can afford to
#: run a real shard end to end. Sorted, the first is `...scratch...` and the
#: second `...videos...`, which is the order the split works on.
FAST_SUITES = ("test_no_scratch_in_the_tree.py", "test_no_videos_in_the_tree.py")

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} ({why})")


def _env(temp: Path) -> dict:
    """A child environment with its OWN TEMP, and no ambient backend."""
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
    return clean


def _run(argv, env, timeout=240):
    result = subprocess.run(
        [sys.executable, "-B", str(RUNNER), *argv], cwd=str(REPO), env=env,
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")
    return (result.returncode, (result.stdout or "") + (result.stderr or ""),
            result.stdout or "")


def _ok_names(out: str) -> list:
    """The suite names the runner printed as `ok`, in the order it printed them."""
    return [line.split()[1] for line in out.splitlines()
            if line.startswith("ok ") and len(line.split()) > 1]


def t_the_shards_partition_the_runner_suite_list():
    """Every suite in exactly one shard, for shard counts 1 to 8.

    The list is the runner's own (`sorted(HERE.glob("test_*.py"))`), so this is
    the list CI really splits - not a fixture that could drift from it.
    """
    suites = sorted(HERE.glob("test_*.py"))
    check("the list under test is a real suite list", len(suites) > 50, len(suites))
    all_names = [s.name for s in suites]
    for total in range(1, 9):
        got = []
        for index in range(1, total + 1):
            got += [s.name for s in R.shard_suites(suites, (index, total))]
        check(f"shard count {total}: the shards partition all {len(all_names)} suites",
              sorted(got) == sorted(all_names),
              f"{len(got)} selected, {len(set(got))} distinct, "
              f"{len(all_names)} exist")
        check(f"shard count {total}: each suite appears exactly once",
              len(got) == len(set(got)) == len(all_names),
              f"{len(got)} selected, {len(set(got))} distinct, "
              f"{len(all_names)} exist")
    check("--shard 1/1 is the whole list, in the runner's order",
          [s.name for s in R.shard_suites(suites, (1, 1))] == all_names)
    check("two calls give the same split",
          [[s.name for s in R.shard_suites(suites, (i, 7))] for i in range(1, 8)]
          == [[s.name for s in R.shard_suites(suites, (i, 7))] for i in range(1, 8)])


def t_a_shard_keeps_the_runner_order():
    """A shard is a slice of the sorted list, not a reshuffle of it."""
    suites = sorted(HERE.glob("test_*.py"))
    all_names = [s.name for s in suites]
    for total in (2, 3, 4, 8):
        for index in range(1, total + 1):
            part = [s.name for s in R.shard_suites(suites, (index, total))]
            in_order = part == [name for name in all_names if name in set(part)]
            check(f"shard {index}/{total} keeps the runner's order", in_order,
                  part[:3])


def t_out_of_range_shards_are_refused():
    """Exit 2, a plain sentence, and nothing staged - for every bad value."""
    root = Path(tempfile.mkdtemp(prefix="jarvis-shard-refuse-"))
    try:
        env = _env(root / "tmp")
        refused = (
            ("0/4", "INDEX must be between 1 and 4"),
            ("5/4", "INDEX must be between 1 and 4"),
            ("1/0", "TOTAL must be at least 1"),
            ("two/4", "two whole numbers"),
            ("2", "takes INDEX/TOTAL"),
            ("1/2/3", "takes INDEX/TOTAL"),
        )
        for value, phrase in refused:
            code, out, _stdout = _run(["--shard", value], env)
            check(f"--shard {value} is refused with exit 2", code == 2,
                  (code, out[:300]))
            check(f"... and the refusal explains itself: {phrase!r}",
                  phrase in out, out[:300])
            check(f"... and nothing was staged or started for {value}",
                  "backend:" not in out, out[:300])
        code, out, _stdout = _run(["--shard"], env)
        check("--shard with no value is refused with exit 2", code == 2,
              (code, out[:300]))
        check("... naming the form it needs: INDEX/TOTAL",
              "INDEX/TOTAL" in out, out[:300])
        check("... and nothing was staged or started", "backend:" not in out,
              out[:300])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_shard_with_no_suites_is_a_failure():
    """The empty shard: the one shape that must never come back green.

    `--shard 1000/10000` is a legal split of a run whose suite list is shorter
    than 10000, so it selects nothing. Before the guard this printed
    "0 passed, 0 skipped, 0 failed" and exited 0.
    """
    root = Path(tempfile.mkdtemp(prefix="jarvis-shard-empty-"))
    try:
        env = _env(root / "tmp")
        code, out, _stdout = _run(["--shard", "1000/10000"], env)
        check("a shard that selects no suite does NOT exit 0", code != 0,
              (code, out[-600:]))
        check("... it exits 1, the runner's failure code", code == 1,
              (code, out[-600:]))
        check("... and it names the broken split", "would run no suite at all"
              in out and "the split is broken" in out, out[-600:])
        check("... and the failed shard appears in the run's failed list",
              "failed: shard 1000/10000" in out, out[-600:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_command_line_really_applies_the_split():
    """`--shard` is not parsed and ignored: each half runs its own suite."""
    root = Path(tempfile.mkdtemp(prefix="jarvis-shard-cli-"))
    try:
        env = _env(root / "tmp")
        for value, expected, other in (("1/2", FAST_SUITES[0], FAST_SUITES[1]),
                                       ("2/2", FAST_SUITES[1], FAST_SUITES[0])):
            code, out, _stdout = _run(["--shard", value, *FAST_SUITES], env)
            check(f"--shard {value} passes its one fast suite", code == 0,
                  (code, out[-800:]))
            check(f"... and its header says 1 of 2 suites, not the whole list",
                  f"shard: {value}  (1 of 2 " in out, out[:500])
            check(f"--shard {value} runs {expected} and not {other}",
                  _ok_names(out) == [expected], _ok_names(out))
        code, out, _stdout = _run(["--shard", "1/1", *FAST_SUITES], env)
        check("--shard 1/1 runs both suites, like no --shard at all",
              code == 0 and _ok_names(out) == list(FAST_SUITES),
              (code, _ok_names(out)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    for fn in (t_the_shards_partition_the_runner_suite_list,
               t_a_shard_keeps_the_runner_order,
               t_out_of_range_shards_are_refused,
               t_a_shard_with_no_suites_is_a_failure,
               t_the_command_line_really_applies_the_split):
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
