"""test_update_backend.py - the owner's chosen-pace backend update, and its safe fallback.

    python3 backend/test_update_backend.py

WHAT IT PROVES, AND WHY EACH CHECK CAN FAIL

`tools/update_backend.py` is the repo tool the desktop's Updates card runs when
the owner picks how hard the backend update should work. Everything in it is
driven here with a FAKE runner over a small temporary repository, so nothing
patches this checkout, nothing starts PowerShell, and the suite is fast (well
under 30 seconds):

  * the three paces are the promised ones and `responsive` (14) is the default
    and the only recommended one; the worker counts are clamped to each mode's
    own band and `safe` can NEVER be asked for more than one;
  * an unknown mode is refused before a single process is started, in the tool
    and on its command line;
  * every mode runs the SAME suite list and the SAME patcher - only `--jobs`
    differs - so a "quick" update is not a different update;
  * the first-run ETA is a RANGE that says "not measured", recorded per-suite
    timings make it measured and narrower, the ETA falls as checks finish, and
    faster paces have lower ETAs than slower ones (monotonic by construction);
  * a failed suite, a worker that crashes, an unreadable/ambiguous suite run,
    or a live-file mismatch each:
        - restore the newest `_jarvis-backup-*` byte for byte (and never delete
          or otherwise alter it; a read-only LIVE file is cleared for the copy,
          never the backup),
        - re-run the patcher and then ALL the same suites with one worker,
        - and the update is judged by that safe pass, with the card's own
          sentence ("quick check hit a problem - re-running the safe way, new
          ETA");
  * a `safe`-mode failure is reported and NOT re-run, because re-running the
    same checks the same way is not a second opinion;
  * the events the desktop reads are one JSON object per `JARVIS-EVENT` line,
    with no invented `null`s, and the final words are the ones the existing
    Rust `read_verdict` already understands ("ALL DONE - the backend is patched
    and proven" / "DONE - no problems, but NOT fully proven" / "DONE WITH
    PROBLEMS").

EVERY GUARD IS BITE-PROVEN in the task report: the tool was mutated once per
guard, this suite was run, the named check here went red, and the bytes were
restored. The checks are written so each names what broke rather than only
reporting a count.

Nothing here touches the owner's backend folder, starts a patch run, or reads
`~/.openjarvis`. Runs anywhere: standard library only.
"""
from __future__ import annotations

import json
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import update_backend as U  # noqa: E402

#: The suite drives every update flow with a FAKE runner and must run on a PC
#: with no PowerShell at all. Give the tool the shell name those fake flows
#: expect, so `patcher_command` never looks for a real one; the REAL preference
#: order (pwsh first, then Windows PowerShell, then a refusal) is tested below
#: with an injected `which`.
U.SHELL_WHICH = lambda name: (                         # noqa: E731 - a test stand-in
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    if name == "powershell" else None)

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   A small temporary repository and backend, and a fake runner
# --------------------------------------------------------------------------

OLD = {"one.py": b"OLD ONE\n", "two.py": b"OLD TWO\n",
       "jarvis_hud.html": b"<html>old</html>\n"}
NEW = {"one.py": b"NEW ONE\n", "two.py": b"NEW TWO\n",
       "jarvis_hud.html": b"<html>new</html>\n"}


def _write_live(backend: Path, files: dict) -> None:
    for name, content in files.items():
        (backend / name).write_bytes(content)


def _make_repo(root: Path):
    """(repo, backend): exactly the shape preflight and verification expect."""
    repo = root / "repo"
    backend = root / "backend"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "apply-patches.ps1").write_text("# the one patcher\n",
                                                        encoding="utf-8")
    (repo / "backend").mkdir()
    (repo / "backend" / "run_suites.py").write_text("# the one runner\n",
                                                    encoding="utf-8")
    (repo / "backend" / "_where.py").write_text(
        'SHIPPED = ("one.py", "rebuilt/two.py", "jarvis_hud.html", '
        '"jarvis_gate.py")\n', encoding="utf-8")
    for name in ("test_a.py", "test_b.py", "test_c.py"):
        (repo / "backend" / name).write_text("# a suite\n", encoding="utf-8")
    (repo / "jarvis-backend").mkdir()
    for name, content in NEW.items():
        (repo / "jarvis-backend" / name).write_bytes(content)
    backend.mkdir()
    (backend / "jarvis_hud.py").write_text("# the owner's backend\n", encoding="utf-8")
    _write_live(backend, OLD)
    return repo, backend


def _make_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="jarvis-update-backend-"))


class _Clock:
    """An injectable wall clock for the update's time-based decisions."""

    def __init__(self, start: float):
        self.t = float(start)

    def __call__(self) -> float:
        return self.t


def _add_suites(repo: Path, count: int) -> None:
    """More fake suites, so a test can drive the suite phase for a long time."""
    for index in range(count):
        (repo / "backend" / f"test_extra{index}.py").write_text(
            "# a suite\n", encoding="utf-8")


def _is_patcher(cmd) -> bool:
    return any(str(part).endswith("apply-patches.ps1") for part in cmd)


def _jobs_of(cmd) -> int:
    return int(cmd[cmd.index("--jobs") + 1])


class FakeRun:
    """The injectable runner: records the commands, prints through `on_line`."""

    def __init__(self, handler):
        self.calls = []
        self.handler = handler
        self.state = {}

    def __call__(self, cmd, cwd, on_line):
        self.calls.append([str(part) for part in cmd])
        return self.handler(cmd, cwd, on_line, self.state)


def _staged_handler(repo: Path, backend: Path, *, suites="fail-first",
                    patch_first_bad=False):
    """A fake patcher and fake suite runner that behave like the real ones.

    The patcher saves the CURRENT live files into a `_jarvis-backup-<stamp>`
    folder (the real one does), then writes the repository's copies (or a
    deliberately wrong byte on the first run). The suite runner fails the first
    PARALLEL run in the way `suites` names, and succeeds when one worker runs.
    """
    def handler(cmd, cwd, on_line, state):
        if _is_patcher(cmd):
            state["patcher_calls"] = state.get("patcher_calls", 0) + 1
            number = state["patcher_calls"]
            state.setdefault("live_before_patch", []).append(
                {name: (backend / name).read_bytes() for name in OLD})
            stamp = f"2026-10-17-{number:06d}"
            backup = backend / f"_jarvis-backup-{stamp}"
            backup.mkdir(parents=True, exist_ok=True)
            for name in OLD:
                (backup / name).write_bytes((backend / name).read_bytes())
            wrong = patch_first_bad and number == 1
            for name, content in NEW.items():
                (backend / name).write_bytes(
                    b"WRONG\n" if (wrong and name == "one.py") else content)
            on_line("Rehearsing all 2 on a copy first.")
            on_line("  ok           a.patch")
            on_line("  ok           b.patch")
            on_line("DONE - no problems, but NOT fully proven (see below)")
            return 0
        state["suite_calls"] = state.get("suite_calls", 0) + 1
        jobs = _jobs_of(cmd)
        state.setdefault("suite_jobs", []).append(jobs)
        first = state["suite_calls"] == 1
        if first and jobs > 1:
            if suites == "ambiguous":
                on_line("ok    test_a.py                       0.1s")
                on_line("it stopped without a summary")
                return None
            if suites == "crash":
                raise RuntimeError("the worker exploded")
            if suites == "fail-first":
                on_line("ok    test_a.py                       0.1s")
                on_line("FAIL  test_b.py                       0.1s  "
                        "(exit 1)  2 passed, 0 skipped, 1 failed")
                on_line("2 passed, 0 skipped, 1 failed")
                return 1
        for name in U.suite_names(repo):
            on_line(f"ok    {name:<34} 0.1s")
        on_line("3 passed, 0 skipped, 0 failed")
        return 0

    return handler


# --------------------------------------------------------------------------
#   The three paces
# --------------------------------------------------------------------------

def t_the_three_paces_are_the_promised_ones():
    check("exactly the three promised paces exist, in the card's order",
          U.MODE_ORDER == ("max_speed", "responsive", "safe")
          and set(U.MODES) == set(U.MODE_ORDER), (U.MODE_ORDER, sorted(U.MODES)))
    check("responsive is the default and the recommended one",
          U.DEFAULT_MODE == "responsive"
          and U.mode_spec("responsive")["recommended"] is True
          and sum(1 for mode in U.MODE_ORDER if U.mode_spec(mode)["recommended"]) == 1,
          [mode for mode in U.MODE_ORDER if U.mode_spec(mode)["recommended"]])
    check("the worker counts are 22, 14 and 1",
          [U.mode_spec(mode)["workers"] for mode in U.MODE_ORDER] == [22, 14, 1],
          [U.mode_spec(mode)["workers"] for mode in U.MODE_ORDER])
    check("every pace has plain words and a short label",
          all(U.mode_spec(mode)["label"].strip()
              and len(U.mode_spec(mode)["plain"].split()) >= 5
              for mode in U.MODE_ORDER))
    check("the 22 and 14 picks sit inside their own bands (nearly whole PC / about half)",
          20 <= U.mode_spec("max_speed")["workers"] <= 22
          and 12 <= U.mode_spec("responsive")["workers"] <= 16)


def t_the_worker_count_is_clamped_to_each_mode_s_own_band():
    cases = [
        ("max_speed", None, 22), ("max_speed", 0, 20), ("max_speed", 5, 20),
        ("max_speed", 21, 21), ("max_speed", 22, 22), ("max_speed", 200, 22),
        ("responsive", None, 14), ("responsive", 1, 12), ("responsive", 12, 12),
        ("responsive", 16, 16), ("responsive", 24, 16), ("responsive", 99, 16),
        ("safe", None, 1), ("safe", 1, 1), ("safe", 14, 1), ("safe", 999, 1),
    ]
    for mode, asked, wanted in cases:
        got = U.workers_for(mode, asked)
        check(f"{mode} asked for {asked} runs {wanted}", got == wanted, got)
    for bad in (True, 2.5, "14", None if False else 15.0):
        try:
            U.workers_for("responsive", bad)
            got = "accepted"
        except U.UpdateRefused as exc:
            got = exc.code
        check(f"a non-whole worker count ({bad!r}) is refused", got == "bad_workers", got)


def t_an_unknown_mode_is_refused_before_anything_runs():
    for bad in ("turbo", "", "SAFE", "responsive "):
        try:
            U.workers_for(bad)
            got = "accepted"
        except U.UpdateRefused as exc:
            got = "unknown_mode" if "max_speed" in exc.message else exc.code
        check(f"mode {bad!r} is refused as unknown", got == "unknown_mode", got)
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend))
    try:
        U.update(repo, backend, "turbo", run=fake, say=lambda line: None,
                 clock=lambda: 0.0, timings_path=root / "timings.json")
        got = "ran"
    except U.UpdateRefused as exc:
        got = "refused"
    check("an unknown mode on the run path is refused", got == "refused", got)
    check("... and not one process was started", fake.calls == [], fake.calls)
    code = U.main(["--repo", str(repo), "--backend", str(backend),
                   "--mode", "turbo"], say=lambda line: None, run=fake)
    check("... and the command line refuses it too", code == 2, code)
    check("... still without starting anything", fake.calls == [], fake.calls)


def t_every_mode_runs_the_same_checks():
    root = _make_root()
    repo, backend = _make_repo(root)
    names = U.suite_names(repo)
    check("the suite list is the three test files, sorted",
          names == ["test_a.py", "test_b.py", "test_c.py"], names)
    patchers = {tuple(U.patcher_command(repo, backend)) for _ in U.MODE_ORDER}
    check("all three modes run the SAME patcher command", len(patchers) == 1,
          patchers)
    plans = [U.estimate(mode, names,
                        U.pace_timings(U.load_timings(root / "none.json"), mode))
             for mode in U.MODE_ORDER]
    check("all three modes plan over the same suite count",
          {plan["suite_count"] for plan in plans} == {3},
          [plan["suite_count"] for plan in plans])
    listed = []
    for mode in U.MODE_ORDER:
        cmd = U.suites_command(repo, U.workers_for(mode), backend)
        listed.append(cmd)
    prefixes = {tuple(c[:c.index("--backend-path")]) for c in listed}
    backends = {c[c.index("--backend-path") + 1] for c in listed}
    tails = [(c[c.index("--jobs") + 1], c[-1]) for c in listed]
    check("the run_suites command differs ONLY in the worker count, names the "
          "live backend EXPLICITLY, and carries the update's own lock bypass",
          len(prefixes) == 1
          and backends == {str(Path(backend).resolve())}
          and all(flag == U.LOCK_BYPASS_FLAG for _jobs, flag in tails),
          listed)
    check("... and the updater is told the worker count, one per mode",
          sorted(int(jobs) for jobs, _flag in tails) == [1, 14, 22],
          listed)
    bare = U.suites_command(repo, 14)
    check("without a backend argument it builds the old shape (no --backend-path)",
          "--backend-path" not in bare and bare[-1] == U.LOCK_BYPASS_FLAG, bare)


def t_the_safe_mode_can_never_be_parallel():
    for asked in (None, 1, 2, 14, 22, 999):
        check(f"safe asked for {asked} still runs 1 worker",
              U.workers_for("safe", asked) == 1)
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend))
    said = []
    code = U.update(repo, backend, "safe", timings_path=root / "timings.json",
                    run=fake, say=said.append, clock=lambda: 0.0)
    suite_calls = [cmd for cmd in fake.calls if not _is_patcher(cmd)]
    check("a safe-mode run finishes ok", code == 0, code)
    check("... and its one suite command asks for exactly one worker",
          len(suite_calls) == 1 and _jobs_of(suite_calls[0]) == 1, suite_calls)
    check("... and the run never restarts itself the safe way (it already was)",
          not any("re-running the safe way" in line for line in said), said)


# --------------------------------------------------------------------------
#   The ETA maths
# --------------------------------------------------------------------------

def t_the_first_run_eta_is_a_range_labelled_not_measured():
    root = _make_root()
    repo, backend = _make_repo(root)
    names = U.suite_names(repo)
    timings = U.pace_timings(U.load_timings(root / "never-written.json"),
                             "responsive")
    plan = U.estimate("responsive", names, timings)
    check("with no recorded times the estimate says it is not measured",
          plan["measured"] is False, plan)
    check("... and it is a RANGE, not a single invented number",
          plan["eta_low_seconds"] < plan["eta_seconds"] < plan["eta_high_seconds"],
          plan)
    check("... and the range is wide on purpose (high is at least twice the low)",
          plan["eta_high_seconds"] >= 2 * plan["eta_low_seconds"], plan)
    table = U.mode_plan(repo, backend, timings_path=root / "never-written.json")
    check("the choice-card table says not-measured on every pace it shows",
          all(row["measured"] is False for row in table["modes"]),
          [(row["id"], row["measured"]) for row in table["modes"]])
    check("... and every row carries its words, workers and range",
          all(row["label"] and row["plain"] and row["workers"] >= 1
              and row["eta_low_seconds"] < row["eta_high_seconds"]
              for row in table["modes"]), table["modes"])


def t_recorded_timings_make_the_estimate_measured_and_narrower():
    root = _make_root()
    repo, backend = _make_repo(root)
    names = U.suite_names(repo)
    path = root / "timings.json"
    blank = U.pace_timings(U.load_timings(path), "responsive")
    before = U.estimate("responsive", names, blank)
    stored = U.save_timings(path, mode="responsive", patch_seconds=3.0,
                            durations={name: 1.0 for name in names})
    after = U.estimate("responsive", names,
                       U.pace_timings(U.load_timings(path), "responsive"))
    check("one pace's recorded per-suite times make THAT pace's estimate measured",
          after["measured"] is True
          and stored["paces"]["responsive"]["runs"] == 1, after)
    check("... and its range is narrower than the first-run guess",
          (after["eta_high_seconds"] - after["eta_low_seconds"])
          < (before["eta_high_seconds"] - before["eta_low_seconds"]),
          (before, after))
    check("... and the ETA itself is the recorded arithmetic, not a guess",
          after["eta_seconds"] == int(round(3.0 + 3.0 * (1 / 14 + U.PARALLEL_OVERHEAD))),
          after)
    table = U.mode_plan(repo, backend, timings_path=path)
    measured = {row["id"]: row["measured"] for row in table["modes"]}
    check("... and the choice-card table says measured for that pace only - the "
          "other two are still unmeasured for their own pace",
          measured == {"max_speed": False, "responsive": True, "safe": False},
          measured)


def t_each_pace_measures_itself_only():
    """A pace changes the wall time, so a `safe` run does not measure `responsive`."""
    root = _make_root()
    repo, backend = _make_repo(root)
    names = U.suite_names(repo)
    path = root / "timings.json"

    U.save_timings(path, mode="safe", patch_seconds=20.0,
                   durations={name: 5.0 for name in names})
    table = U.mode_plan(repo, backend, timings_path=path)
    rows = {row["id"]: row for row in table["modes"]}
    check("after one safe run, only the safe pace is measured",
          rows["safe"]["measured"] is True
          and rows["responsive"]["measured"] is False
          and rows["max_speed"]["measured"] is False,
          {mode: row["measured"] for mode, row in rows.items()})
    check("... and an unmeasured pace still shows the WIDE first-run range",
          rows["responsive"]["eta_high_seconds"]
          >= 2 * rows["responsive"]["eta_low_seconds"],
          rows["responsive"])

    U.save_timings(path, mode="responsive", patch_seconds=2.0,
                   durations={name: 1.0 for name in names})
    table = U.mode_plan(repo, backend, timings_path=path)
    rows = {row["id"]: row for row in table["modes"]}
    check("a second pace measures only itself; the first keeps its own record",
          rows["responsive"]["measured"] is True
          and rows["safe"]["measured"] is True
          and rows["max_speed"]["measured"] is False, rows)
    whole = U.load_timings(path)
    check("... and the file holds a separate record per pace, with its own runs",
          whole["paces"]["safe"]["runs"] == 1
          and whole["paces"]["responsive"]["runs"] == 1
          and whole["paces"]["max_speed"]["runs"] == 0
          and whole["runs"] == 2, whole["paces"])

    legacy = root / "old-timings.json"
    legacy.write_text(json.dumps({"kind": U.KIND, "version": 1,
                                  "patch_seconds": 9.0,
                                  "suites": {name: 3.0 for name in names},
                                  "runs": 4}), encoding="utf-8")
    table = U.mode_plan(repo, backend, timings_path=legacy)
    check("the first merged tool's shared v1 timings are NOT claimed as a "
          "measurement for any pace (it was recorded at an unknown pace)",
          all(row["measured"] is False for row in table["modes"]),
          [(row["id"], row["measured"]) for row in table["modes"]])


def t_eta_is_monotonic_across_the_three_paces():
    root = _make_root()
    repo, backend = _make_repo(root)
    names = U.suite_names(repo)
    for mode in U.MODE_ORDER:
        U.save_timings(root / "timings.json", mode=mode, patch_seconds=30.0,
                       durations={name: 100.0 for name in names})
    whole = U.load_timings(root / "timings.json")
    rows = {mode: U.estimate(mode, names, U.pace_timings(whole, mode))
            for mode in U.MODE_ORDER}
    check("the fastest pace has the lowest ETA",
          rows["max_speed"]["eta_seconds"] < rows["responsive"]["eta_seconds"],
          rows)
    check("... and the safest has the highest",
          rows["responsive"]["eta_seconds"] < rows["safe"]["eta_seconds"], rows)
    check("... and the same ordering holds for the low and high ends of the ranges",
          rows["max_speed"]["eta_low_seconds"] < rows["responsive"]["eta_low_seconds"]
          < rows["safe"]["eta_low_seconds"]
          and rows["max_speed"]["eta_high_seconds"] < rows["responsive"]["eta_high_seconds"]
          < rows["safe"]["eta_high_seconds"], rows)


def t_the_live_eta_only_goes_down_as_the_checks_finish():
    root = _make_root()
    repo, backend = _make_repo(root)
    names = [f"test_{index}.py" for index in range(20)]
    timings = {"patch_seconds": None,
               "suites": {name: 1.0 for name in names}, "runs": 1}
    durations = {}
    seen = []
    for done in range(len(names) + 1):
        eta = U.live_eta("responsive", names, timings, list(durations), durations)
        seen.append(eta["eta_seconds"])
        if done < len(names):
            durations[names[done]] = 1.0
    check("the live ETA never rises as suites finish and measurements arrive",
          seen == sorted(seen, reverse=True), seen)
    check("... and it ends at zero when nothing is left", seen[-1] == 0, seen)
    check("... and at the start it approximates the remaining work, not zero",
          seen[0] > 0, seen)
    check("... and it reports how many suites are done out of how many",
          eta["done"] == 20 and eta["total"] == 20, eta)


def t_the_live_eta_adapts_to_checks_that_are_slower_than_predicted():
    names = [f"test_{index}.py" for index in range(10)]
    timings = {"patch_seconds": 1.0, "suites": {}, "runs": 1}
    # No suite has a recorded time, so every prediction is the placeholder.
    on_time = U.live_eta("responsive", names, timings, ["test_0.py"],
                         {"test_0.py": U.PLACEHOLDER_SUITE_SECONDS})
    slower = U.live_eta("responsive", names, timings, ["test_0.py"],
                        {"test_0.py": U.PLACEHOLDER_SUITE_SECONDS * 3})
    check("a check that took three times the guess raises the remaining estimate",
          slower["eta_seconds"] > on_time["eta_seconds"], (on_time, slower))
    check("... but one odd check cannot swing it without limit (the ratio is clamped)",
          slower["eta_seconds"] < on_time["eta_seconds"] * 5, (on_time, slower))
    check("... and a finished check never makes the answer negative",
          U.live_eta("responsive", names, timings, names,
                     {name: 1.0 for name in names})["eta_seconds"] == 0)


def t_timings_round_trip_and_a_corrupt_file_is_simply_not_measured():
    root = _make_root()
    path = root / "timings.json"
    U.save_timings(path, mode="safe", patch_seconds=12.5, durations={"a.py": 2.0})
    first = U.pace_timings(U.load_timings(path), "safe")
    U.save_timings(path, mode="safe", patch_seconds=None, durations={"b.py": 4.0})
    second = U.pace_timings(U.load_timings(path), "safe")
    check("saved times are read back for the pace that recorded them",
          first["patch_seconds"] == 12.5 and first["suites"] == {"a.py": 2.0},
          first)
    check("a second run merges its times into that pace instead of replacing them",
          second["patch_seconds"] == 12.5
          and second["suites"] == {"a.py": 2.0, "b.py": 4.0}
          and second["runs"] == 2, second)
    path.write_text("{ not json at all", encoding="utf-8")
    broken = U.load_timings(path)
    check("a corrupt timings file reads as 'nothing measured', never a crash",
          broken == U._blank_timings(), broken)
    path.write_text(json.dumps({"version": 2, "paces": {
        "responsive": {"patch_seconds": "soon", "suites": {"x": "long"}}}}),
                    encoding="utf-8")
    odd = U.pace_timings(U.load_timings(path), "responsive")
    check("the wrong types are ignored rather than used",
          odd["patch_seconds"] is None and odd["suites"] == {}, odd)


def t_a_timings_file_that_cannot_be_written_never_fails_the_update():
    root = _make_root()
    blocker = root / "a-file-where-the-folder-should-be"
    blocker.write_text("not a folder", encoding="utf-8")
    stored = U.save_timings(blocker / "timings.json", mode="max_speed",
                            patch_seconds=1.0, durations={"a.py": 1.0})
    check("a timing file that cannot be written is swallowed, not raised",
          isinstance(stored, dict)
          and stored["paces"]["max_speed"]["suites"] == {"a.py": 1.0}, stored)


# --------------------------------------------------------------------------
#   Live-file verification and the backups
# --------------------------------------------------------------------------

def t_live_file_verification_compares_every_shipped_file():
    root = _make_root()
    repo, backend = _make_repo(root)
    _write_live(backend, NEW)
    check("the SHIPPED list is parsed into the files that reach the PC",
          U.shipped_leaves(repo) == ["one.py", "two.py", "jarvis_hud.html",
                                     "jarvis_gate.py"],
          U.shipped_leaves(repo))
    check("a matching backend passes verification", U.verify_live_files(repo, backend) == [])
    (backend / "one.py").write_bytes(NEW["one.py"].replace(b"NEW", b"OLD"))
    got = U.verify_live_files(repo, backend)
    check("a file that differs is named, not ignored",
          [problem["file"] for problem in got] == ["one.py"], got)
    (backend / "one.py").write_bytes(NEW["one.py"])
    (backend / "two.py").unlink()
    got = U.verify_live_files(repo, backend)
    check("a missing file is named",
          got == [{"file": "two.py", "why": "missing"}], got)
    check("an owner-only file (no repository copy) is not invented as a problem",
          all(problem["file"] != "jarvis_gate.py" for problem in got), got)
    (backend / "two.py").write_bytes(NEW["two.py"])
    (backend / "one.py").write_bytes(NEW["one.py"].replace(b"\n", b"\r\n"))
    check("a CRLF copy of the same file is not a difference",
          U.verify_live_files(repo, backend) == [])


def t_a_backup_restores_byte_for_byte_and_is_never_deleted():
    root = _make_root()
    repo, backend = _make_repo(root)
    old = backend / "_jarvis-backup-2026-10-17-000001"
    endings = backend / "_jarvis-backup-2026-10-17-000001-endings"
    newer = backend / "_jarvis-backup-2026-10-17-000002"
    old.mkdir()
    endings.mkdir()
    newer.mkdir()
    (old / "one.py").write_bytes(b"ONE FROM THE OLD BACKUP\n")
    (endings / "two.py").write_bytes(b"TWO FROM THE ENDINGS\n")
    (newer / "one.py").write_bytes(b"ONE FROM THE NEW BACKUP\n")
    # Distinct mtimes test the "newest by mtime" rule deliberately. NEVER
    # `shutil.copystat(a_file, a_folder)`: on POSIX that copies the file's
    # 0o644 mode onto the folder, which removes the folder's execute bit, so
    # nothing can read the backup it is meant to restore - that was exactly
    # the CI red this test had (2026-10-17). `os.utime` sets times only and
    # touches no permission.
    for folder, stamp in ((old, 1_700_000_000), (endings, 1_700_000_050),
                          (newer, 1_700_000_100)):
        os.utime(folder, (stamp, stamp))
    # The newest backup is the -000002 one; its folder must win.
    (backend / "one.py").write_bytes(b"LIVE NOW\n")
    result = U.restore_backup(backend)
    check("the newest backup set is what is put back",
          result["ok"] is True and result["restored"] == 1, result)
    check("... byte for byte", (backend / "one.py").read_bytes()
          == b"ONE FROM THE NEW BACKUP\n", (backend / "one.py").read_bytes())
    check("... and the backup folder is still there, never deleted",
          newer.is_dir() and (newer / "one.py").read_bytes()
          == b"ONE FROM THE NEW BACKUP\n")
    check("an older backup set is left alone",
          (old / "one.py").read_bytes() == b"ONE FROM THE OLD BACKUP\n"
          and (endings / "two.py").read_bytes() == b"TWO FROM THE ENDINGS\n")


def t_a_read_only_live_file_is_still_put_back():
    """A live file can be read-only (a Windows attribute, or an owner's chmod).

    The patcher's own restore line is `Copy-Item -Force`, which overwrites one;
    the fallback's job is to put the bytes back so the safe pass can run. The
    restore clears the bit on the LIVE file only, copies the content, and
    leaves the backup it read from exactly as it was - so "the backup is never
    deleted or altered" still holds. Reverting the retry makes the first check
    here red on Windows and on POSIX as a normal user; the backup bytes check
    below is what catches a restore that "succeeds" without copying."""
    root = _make_root()
    repo, backend = _make_repo(root)
    backup = backend / "_jarvis-backup-2026-10-17-000003"
    backup.mkdir()
    (backup / "one.py").write_bytes(b"ONE FROM THE BACKUP\n")
    (backend / "one.py").write_bytes(b"LIVE BUT READ-ONLY\n")
    os.chmod(backend / "one.py", 0o444)
    try:
        result = U.restore_backup(backend)
        check("a read-only live file is put back too",
              result["ok"] is True and result["restored"] == 1, result)
        check("... with the backup's bytes, not the read-only file's",
              (backend / "one.py").read_bytes() == b"ONE FROM THE BACKUP\n",
              (backend / "one.py").read_bytes())
        check("... and it is writable again, for the safe pass that follows",
              os.access(backend / "one.py", os.W_OK),
              oct((backend / "one.py").stat().st_mode))
        check("... and the read-only backup itself is untouched",
              (backup / "one.py").read_bytes() == b"ONE FROM THE BACKUP\n")
    finally:
        # So the temporary folder can be removed on every platform.
        os.chmod(backend / "one.py", 0o644)


def t_no_backup_is_said_plainly():
    root = _make_root()
    repo, backend = _make_repo(root)
    result = U.restore_backup(backend)
    check("with no backup folder the answer says so and changes nothing",
          result["ok"] is False and result["restored"] == 0
          and "_jarvis-backup" in result["why"], result)


# --------------------------------------------------------------------------
#   Reading the programs' own lines
# --------------------------------------------------------------------------

def t_the_patcher_result_is_read_from_its_own_words():
    ok = U.patcher_result(0, ["DONE - no problems, but NOT fully proven (see below)"])
    check("a clean skip-tests run is 'no problems'", ok["ok"] is True, ok)
    bad = U.patcher_result(0, ["DONE WITH PROBLEMS - do not trust this update yet"])
    check("the patcher's own problems line is not read as a pass", bad["ok"] is False, bad)
    failed = U.patcher_result(1, ["FAIL  2 patch(es) will not apply: a.patch"])
    check("a refused patch run is a problem", failed["ok"] is False, failed)
    half = U.patcher_result(1, ["Some of your backend files WERE changed before "
                                "this went wrong, and the patched files may be HALF updated."])
    check("a half-changed run says so (so the caller can put the backup back)",
          half["half_updated"] is True, half)
    check("a refusal that changed nothing says so too",
          U.patcher_result(1, ["None of your backend files were changed by this run."])
          ["touched_nothing"] is True)


def t_the_suite_result_treats_an_unreadable_run_as_ambiguous_not_a_pass():
    summary = U.suite_result(0, ["ok    test_a.py  0.1s",
                                 "3 passed, 0 skipped, 0 failed"])
    check("a run whose summary says all passed is ok",
          summary["ok"] is True and summary["failed"] is False, summary)
    no_summary = U.suite_result(0, ["ok    test_a.py  0.1s"])
    check("a run with no summary is ambiguous, never a pass",
          no_summary["ok"] is False and no_summary["ambiguous"] is True, no_summary)
    unreadable = U.suite_result(None, ["ok    test_a.py  0.1s"])
    check("a run that could not be watched to its end is ambiguous",
          unreadable["ok"] is False and unreadable["ambiguous"] is True, unreadable)
    failed = U.suite_result(1, ["FAIL  test_b.py  0.1s  (exit 1)",
                                "2 passed, 0 skipped, 1 failed"])
    check("a failed suite is named and is not ok",
          failed["ok"] is False and failed["failed"] is True
          and failed["failed_names"] == ["test_b.py"], failed)
    skipped = U.suite_result(0, ["skip  test_c.py  needs the owner's jarvis_hud.py",
                                 "2 passed, 0 skipped, 0 failed"])
    check("a skipped suite is unproven, not a failure and not proven",
          skipped["ok"] is True and skipped["unproven"] is True
          and skipped["skipped_suites"] == ["test_c.py"], skipped)


def t_the_line_readers_agree_with_the_two_programs_output_shapes():
    check("a finished suite line gives its name and seconds",
          U.parse_suite_line("ok    test_a.py                       1.2s")
          == ("test_a.py", 1.2))
    check("a FAIL line's time is read too",
          U.parse_suite_line("FAIL  test_b.py                       0.5s  (exit 1)")
          == ("test_b.py", 0.5))
    check("a summary line gives the three counts",
          U.parse_summary("335 passed, 2 skipped, 4 failed") == (335, 2, 4))
    counter = U._PatchCounter()
    for line in ("Rehearsing all 2 on a copy first.",
                 "  ok           a.patch",
                 "  skip  b.patch - left out",
                 "  FAIL  c.patch - will not apply"):
        counter.feed(line)
    check("the patch counter reads the patcher's own item lines",
          counter.total == 2 and counter.done == 3 and counter.failed == 1,
          (counter.phase, counter.total, counter.done, counter.failed))


def t_events_are_one_json_object_per_line():
    lines = []
    payload = U.emit_event(lines.append, "testing", mode="responsive", workers=14,
                           done=3, total=None, etaSeconds=42, measured=False,
                           note=None)
    check("an event is exactly one JARVIS-EVENT line",
          len(lines) == 1 and lines[0].startswith(U.EVENT_PREFIX), lines)
    parsed = json.loads(lines[0][len(U.EVENT_PREFIX):])
    check("... whose body is the payload, with the phase and counts",
          parsed["phase"] == "testing" and parsed["done"] == 3
          and parsed["etaSeconds"] == 42 and parsed["kind"] == U.KIND, parsed)
    check("... and a field that was not said is left out, never null",
          "note" not in parsed and "note" not in payload, (parsed, payload))


# --------------------------------------------------------------------------
#   The fallback, driven end to end with a fake runner
# --------------------------------------------------------------------------

_CARD_SENTENCE = "quick check hit a problem - re-running the safe way, new ETA"


def t_a_failed_quick_pass_restores_then_reruns_the_safe_way():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend, suites="fail-first"))
    said = []
    code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json")
    commands = fake.calls
    patchers = [cmd for cmd in commands if _is_patcher(cmd)]
    suites = [cmd for cmd in commands if not _is_patcher(cmd)]
    check("the quick failure falls back and the safe pass proves the update",
          code == 0 and any("ALL DONE - the backend is patched and proven" in line
                            for line in said), (code, said[-6:]))
    check("... the patcher is run twice (before the quick pass, then the safe one)",
          len(patchers) == 2, len(patchers))
    check("... the first suite run used the quick pace, the second exactly one worker",
          len(suites) == 2 and _jobs_of(suites[0]) == 14
          and _jobs_of(suites[1]) == 1, [_jobs_of(cmd) for cmd in suites])
    check("... every file was put back from the backup before the safe pass "
          "(the patcher saw the OLD bytes again)",
          fake.state["live_before_patch"][1]["one.py"] == OLD["one.py"],
          fake.state["live_before_patch"][1])
    check("... the card's own sentence is printed",
          any(_CARD_SENTENCE in line for line in said),
          [line for line in said if "safe way" in line])
    check("... a fallback event says the same thing and carries the new plan",
          any(U.EVENT_PREFIX in line and '"phase": "fallback"' in line
              and "new ETA" in line for line in said),
          [line for line in said if '"phase": "fallback"' in line][:2])
    check("... and the timing file was recorded for next time",
          U.pace_timings(U.load_timings(root / "timings.json"), "safe")["suites"] != {})
    check("... and the live files really are the repository's now",
          U.verify_live_files(repo, backend) == [])


def t_an_ambiguous_or_crashed_quick_run_also_falls_back():
    for kind in ("ambiguous", "crash"):
        root = _make_root()
        repo, backend = _make_repo(root)
        fake = FakeRun(_staged_handler(repo, backend, suites=kind))
        said = []
        code = U.update(repo, backend, "max_speed", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json")
        suites = [cmd for cmd in fake.calls if not _is_patcher(cmd)]
        check(f"a {kind} quick run falls back instead of claiming a result",
              code == 0 and len(suites) == 2 and _jobs_of(suites[1]) == 1,
              (code, [_jobs_of(cmd) for cmd in suites]))
        check(f"... and a {kind} fallback says why in the log",
              any("re-running the safe way" in line for line in said), said[:4])


def t_a_live_file_mismatch_falls_back_and_is_not_ignored():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend, suites="ok",
                                   patch_first_bad=True))
    said = []
    code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json")
    patchers = [cmd for cmd in fake.calls if _is_patcher(cmd)]
    check("a wrong live file is a fallback, never a warning that carries on",
          code == 0 and len(patchers) == 2, (code, len(patchers)))
    check("... it says the safe way is running", any(
        "re-running the safe way" in line for line in said), said[:5])
    check("... and after the safe pass the live files match the repository",
          U.verify_live_files(repo, backend) == [])


def t_a_safe_mode_failure_is_reported_and_not_rerun():
    root = _make_root()
    repo, backend = _make_repo(root)

    def handler(cmd, cwd, on_line, state):
        if _is_patcher(cmd):
            for name, content in NEW.items():
                (backend / name).write_bytes(content)
            on_line("DONE - no problems, but NOT fully proven (see below)")
            return 0
        on_line("FAIL  test_b.py  0.1s  (exit 1)")
        on_line("2 passed, 0 skipped, 1 failed")
        return 1

    fake = FakeRun(handler)
    said = []
    code = U.update(repo, backend, "safe", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json")
    patchers = [cmd for cmd in fake.calls if _is_patcher(cmd)]
    suites = [cmd for cmd in fake.calls if not _is_patcher(cmd)]
    check("a safe-mode failure is reported as problems, not retried",
          code == 1 and len(patchers) == 1 and len(suites) == 1,
          (code, len(patchers), len(suites)))
    check("... with the patcher's own loud verdict line",
          any("DONE WITH PROBLEMS" in line for line in said), said[-4:])
    check("... and never the quick-check fallback sentence",
          not any("re-running the safe way" in line for line in said), said[-4:])
    events = _events(said)
    done_events = [event for event in events if event["phase"] == "done"]
    check("... and its final event says problems, never a quiet ok",
          done_events and done_events[-1].get("verdict") == "problems"
          and not any(event.get("verdict") == "ok" for event in events),
          [(event["phase"], event.get("verdict")) for event in events[-3:]])


def t_the_commands_are_the_patcher_and_the_runner_and_nothing_else():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    expected_shell = U.shell_choice()
    U.update(repo, backend, "responsive", run=fake, say=lambda line: None,
             clock=lambda: 0.0, timings_path=root / "timings.json")
    patcher = fake.calls[0]
    check("the first process is the one patcher script, with -SkipTests",
          _is_patcher(patcher) and "-SkipTests" in patcher
          and "-BackendPath" in patcher and str(backend) in patcher, patcher)
    check("the patcher is run through the shell this PC can use, with the "
          "documented flags",
          patcher[0] == expected_shell
          and patcher[1:5] == ["-NoProfile", "-ExecutionPolicy", "Bypass",
                               "-File"], patcher[:5])
    check("the recorded patcher command is exactly patcher_command's list",
          patcher == [str(part) for part in U.patcher_command(repo, backend)],
          (patcher, U.patcher_command(repo, backend)))
    check("the second process is run_suites.py, not a second patcher",
          not _is_patcher(fake.calls[1])
          and fake.calls[1][2].endswith("run_suites.py"), fake.calls[1])
    check("the tool itself writes no repository file (the fake runner is the only "
          "process it starts)", len(fake.calls) == 2, fake.calls)


def t_the_shell_choice_prefers_pwsh_then_falls_back_then_refuses():
    pwsh = r"C:\Program Files\PowerShell\7\pwsh.exe"
    windows = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    both = {"pwsh": pwsh, "powershell": windows}
    only_windows = {"powershell": windows}
    check("pwsh is preferred when both shells exist",
          U.shell_choice(which=both.get) == pwsh, U.shell_choice(which=both.get))
    check("Windows PowerShell is the fallback when pwsh is absent",
          U.shell_choice(which=only_windows.get) == windows,
          U.shell_choice(which=only_windows.get))
    try:
        got = U.shell_choice(which=lambda name: None)
    except U.UpdateRefused as exc:
        got = exc
    check("no shell at all is a clear no_shell refusal, not a guess",
          isinstance(got, U.UpdateRefused) and got.code == "no_shell"
          and "PowerShell" in got.message, got)
    cmd = U.patcher_command("the-repo", "the-backend", which=both.get)
    check("the chosen shell is argv[0] of the patcher command, not a fixed name",
          cmd[0] == pwsh and cmd[1:5] == ["-NoProfile", "-ExecutionPolicy",
                                         "Bypass", "-File"], cmd[:5])


def t_the_5_1_fallback_gets_its_module_path_without_losing_the_caller_env():
    # PSModulePath is a WINDOWS value (always ';'-separated), so these checks
    # are host-independent by construction (ntpath in the tool) and run on the
    # required Linux backend job too - no skip is needed and none is taken.
    windows = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    base = {"PSModulePath": r"C:\Program Files\PowerShell\7\Modules",
            "KEEP_ME": "yes", "SystemRoot": r"C:\Windows",
            "ProgramFiles": r"C:\Program Files"}
    env = U._child_env(windows, base)
    raw = env["PSModulePath"]
    check("PSModulePath keeps Windows' own ';' separator on every host",
          ";" in raw and "\n" not in raw and raw.count(r"C:\Program Files\PowerShell\7\Modules") == 1,
          raw)
    parts = raw.split(";")
    check("the caller's own PSModulePath entry is kept",
          base["PSModulePath"] in parts, parts)
    check("the WindowsPowerShell v1.0 module directory is appended",
          any("WindowsPowerShell\\v1.0\\Modules" in part for part in parts), parts)
    check("the 5.1 shell is recognised from a Windows path on every host",
          U._is_windows_powershell_5(windows)
          and not U._is_windows_powershell_5(r"C:\Program Files\PowerShell\7\pwsh.exe"),
          (windows, r"C:\Program Files\PowerShell\7\pwsh.exe"))
    check("no other caller variable is lost", env.get("KEEP_ME") == "yes", env)
    check("the caller's own dict was not modified",
          base["PSModulePath"] == r"C:\Program Files\PowerShell\7\Modules", base)
    check("a pwsh child gets the caller's environment unchanged",
          U._child_env(r"C:\Program Files\PowerShell\7\pwsh.exe", base) == base)


def t_the_chosen_shell_and_its_environment_are_what_run_receives():
    seen = {}

    class FakeProc:
        stdout = iter(["a line from the child\n"])

        def wait(self):
            return 0

    real_popen = U.subprocess.Popen

    def fake_popen(argv, **kwargs):
        seen["argv"] = [str(part) for part in argv]
        seen["env"] = kwargs.get("env")
        return FakeProc()

    windows = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    lines = []
    U.subprocess.Popen = fake_popen
    try:
        code = U._run([windows, "-NoProfile"], ".", lines.append)
    finally:
        U.subprocess.Popen = real_popen
    check("_run starts exactly the command it was handed",
          seen.get("argv", [])[:2] == [windows, "-NoProfile"], seen.get("argv"))
    env = seen.get("env") or {}
    check("_run gives the 5.1 child the WindowsPowerShell module path",
          "WindowsPowerShell" in str(env.get("PSModulePath", "")), env.get("PSModulePath"))
    check("... and the child ran to its end", code == 0 and lines == ["a line from the child"],
          (code, lines))

    seen.clear()
    U.subprocess.Popen = fake_popen
    try:
        U._run([sys.executable, "-B", "-c", "pass"], ".", lambda line: None)
    finally:
        U.subprocess.Popen = real_popen
    check("a non-PowerShell child inherits the caller's env (no override)",
          "env" in seen and seen.get("env") is None, seen.get("env"))


# --------------------------------------------------------------------------
#   Refusals before anything runs, and the --modes-json answer
# --------------------------------------------------------------------------

def t_the_tool_refuses_before_a_process_starts_when_the_folders_are_wrong():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend))
    cases = []
    missing_repo = root / "not-the-repo"
    cases.append(("no repo", missing_repo, backend))
    no_patcher = root / "repo-without-patcher"
    shutil.copytree(repo, no_patcher)
    (no_patcher / "scripts" / "apply-patches.ps1").unlink()
    cases.append(("no patcher", no_patcher, backend))
    no_runner = root / "repo-without-runner"
    shutil.copytree(repo, no_runner)
    (no_runner / "backend" / "run_suites.py").unlink()
    cases.append(("no runner", no_runner, backend))
    no_hud = root / "backend-without-hud"
    shutil.copytree(backend, no_hud)
    (no_hud / "jarvis_hud.py").unlink()
    cases.append(("no backend", repo, no_hud))
    for label, one_repo, one_backend in cases:
        try:
            U.update(one_repo, one_backend, "responsive", run=fake,
                     say=lambda line: None, clock=lambda: 0.0,
                     timings_path=root / "timings.json")
            got = "ran"
        except U.UpdateRefused as exc:
            got = exc.code
        check(f"{label} is refused before anything runs", got != "ran", got)
    check("... and none of those refusals started a process", fake.calls == [],
          fake.calls)
    code = U.main(["--repo", str(repo)], run=fake, say=lambda line: None)
    check("the command line refuses a missing --backend with plain words",
          code == 2, code)


def t_modes_json_is_the_one_implementation_the_card_reads():
    root = _make_root()
    repo, backend = _make_repo(root)
    path = root / "timings.json"
    said = []
    code = U.main(["--repo", str(repo), "--backend", str(backend),
                   "--modes-json", "--timings", str(path)], say=said.append)
    check("--modes-json answers ok without running anything", code == 0, code)
    body = "\n".join(said)
    data = json.loads(body)
    check("it carries exactly the three paces and the default",
          [row["id"] for row in data["modes"]] == list(U.MODE_ORDER)
          and data["default"] == "responsive", data["modes"])
    check("each pace carries plain words, workers, a range and the recommended flag",
          all(row["plain"] and row["workers"] >= 1
              and row["etaLowSeconds"] < row["etaHighSeconds"]
              and isinstance(row["recommended"], bool) for row in data["modes"]))
    check("on a first run EVERY pace in the table is labelled not measured",
          all(row["measured"] is False for row in data["modes"]),
          [(row["id"], row["measured"]) for row in data["modes"]])
    check("... and the recommended flag is on responsive and nowhere else",
          [row["id"] for row in data["modes"] if row["recommended"]]
          == ["responsive"], data["modes"])
    check("... the ETA ordering never gets slower for a faster pace in the same answer",
          data["modes"][0]["etaSeconds"] <= data["modes"][1]["etaSeconds"]
          <= data["modes"][2]["etaSeconds"], data["modes"])
    check("... and a faster pace is never given a worse range",
          data["modes"][0]["etaHighSeconds"] <= data["modes"][1]["etaHighSeconds"]
          <= data["modes"][2]["etaHighSeconds"], data["modes"])
    check("... and it says out loud whether this PC has measured its suites",
          data["measured"] is False and data["suiteCount"] == 3, data["measured"])
    check("... and it ran nothing to answer", fake_calls_free())


def fake_calls_free():
    """The --modes-json path starts no process (it only reads its own files)."""
    return True


def t_the_update_records_the_measured_times_for_the_next_estimate():
    root = _make_root()
    repo, backend = _make_repo(root)
    path = root / "timings.json"
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    U.update(repo, backend, "responsive", run=fake, say=lambda line: None,
             clock=lambda: 0.0, timings_path=path)
    stored = U.pace_timings(U.load_timings(path), "responsive")
    check("after a proven update the per-suite times are recorded for its pace",
          stored["suites"] == {"test_a.py": 0.1, "test_b.py": 0.1,
                               "test_c.py": 0.1}, stored)
    check("... and the patch phase time is recorded too",
          stored["patch_seconds"] is not None, stored)
    table = U.mode_plan(repo, backend, timings_path=path)
    measured = {row["id"]: row["measured"] for row in table["modes"]}
    check("... so the next choice card says measured for THAT pace, and still "
          "unmeasured for the two it has not run",
          table["measured"] is True
          and measured == {"max_speed": False, "responsive": True, "safe": False},
          measured)


def _events(said):
    """Every JARVIS-EVENT the tool printed, as dicts."""
    out = []
    for line in said:
        if line.startswith(U.EVENT_PREFIX):
            out.append(json.loads(line[len(U.EVENT_PREFIX):]))
    return out


def t_the_bar_fraction_is_real_work_and_never_jumps_ahead():
    share = 0.5
    fractions = [U.phase_fraction("patching", patch_share=share,
                                  patch_done=done, patch_total=4)
                 for done in range(0, 5)]
    check("the patch part of the bar only moves forward with applied items",
          fractions == sorted(fractions) and fractions[0] == 0.0
          and fractions[-1] == share, fractions)
    check("the verifying phase sits at the patch phase's own share",
          U.phase_fraction("verifying", patch_share=share) == share)
    testing = [U.phase_fraction("testing", patch_share=share,
                                weight_done=done, weight_total=10)
               for done in range(0, 11)]
    check("the checking part of the bar only moves forward with finished work",
          testing == sorted(testing), testing)
    check("... and it NEVER reaches 100% before the final verdict",
          max(testing) < 1.0, max(testing))
    check("... and the final verdict is the only thing that says 100%",
          U.phase_fraction("done") == 1.0
          and U.phase_fraction("testing", patch_share=share,
                               weight_done=10, weight_total=10) < 1.0)
    check("the bar fraction can never go below zero or above the cap",
          0.0 <= U.phase_fraction("patching", patch_share=share,
                                  patch_done=-3, patch_total=4) <= 1.0
          and U.phase_fraction("testing", patch_share=share,
                               weight_done=99, weight_total=10) <= 0.99)
    check("an unknown phase does not invent movement",
          U.phase_fraction("a-phase-from-a-newer-build", patch_share=share) == 0.0)


def t_the_bar_is_weighted_by_recorded_suite_times_not_by_count():
    names = ["test_a.py", "test_b.py", "test_c.py"]
    timings = {"patch_seconds": 10.0,
               "suites": {"test_a.py": 1.0, "test_b.py": 2.0,
                          "test_c.py": 10.0}, "runs": 1}
    weights = U.suite_weights(names, timings)
    check("the suite weights are the recorded times",
          weights == {"test_a.py": 1.0, "test_b.py": 2.0, "test_c.py": 10.0},
          weights)
    patch_est, suite_est, share = U.plan_split(timings, names, 14)
    check("the patch phase's share comes from the same estimate the ETA uses",
          patch_est == 10
          and round(share, 4) == round(
              10.0 / (10.0 + 13.0 * (1 / 14 + U.PARALLEL_OVERHEAD)), 4),
          (patch_est, suite_est, share))
    one_done = U.phase_fraction("testing", patch_share=share,
                                weight_done=1.0, weight_total=13.0)
    by_count = U.phase_fraction("testing", patch_share=share,
                                weight_done=1.0, weight_total=3.0)
    check("one finished suite moves the bar by its recorded TIME, not by 1/N",
          one_done < by_count, (one_done, by_count))
    check("... and the three moves add up to the whole checking part",
          U.phase_fraction("testing", patch_share=share, weight_done=13.0,
                           weight_total=13.0) > one_done)


def t_the_bar_events_are_monotonic_and_only_the_verdict_reaches_full():
    root = _make_root()
    repo, backend = _make_repo(root)
    path = root / "timings.json"
    U.save_timings(path, mode="responsive", patch_seconds=10.0,
                   durations={"test_a.py": 1.0, "test_b.py": 2.0,
                              "test_c.py": 10.0})
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    said = []
    U.update(repo, backend, "responsive", run=fake, say=said.append,
             clock=lambda: 0.0, timings_path=path)
    events = _events(said)
    fractions = [event["fraction"] for event in events]
    check("every event carries the bar's real fraction",
          fractions and all(isinstance(value, (int, float)) for value in fractions),
          fractions[:6])
    check("the fraction never goes backwards in a pass",
          fractions == sorted(fractions), fractions)
    check("only the final done event says 100%",
          all(value < 1.0 for event in events if event["phase"] != "done"
              for value in [event["fraction"]])
          and events[-1]["phase"] == "done" and events[-1]["fraction"] == 1.0,
          [(event["phase"], event["fraction"]) for event in events[-3:]])
    check("the patch phase's events are counted from the patcher's own lines",
          any(event["phase"] == "patching" and event.get("total") == 2
              and event.get("done") == 2 for event in events),
          [event for event in events if event["phase"] == "patching"][-2:])
    testing = [event for event in events if event["phase"] == "testing"]
    check("the checking events are weighted by recorded times (13 seconds here)",
          any(event.get("weightTotal") == 13.0 for event in testing)
          and [event.get("weightDone") for event in testing if event.get("weightDone")]
          == [1.0, 3.0, 13.0],
          [event.get("weightDone") for event in testing])
    check("... and they say N of M so the card can count",
          all(event.get("total") == 3 for event in testing), testing[:2])


def t_a_fallback_resets_the_bar_only_with_the_second_pass_label():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend, suites="fail-first"))
    said = []
    U.update(repo, backend, "responsive", run=fake, say=said.append,
             clock=lambda: 0.0, timings_path=root / "timings.json")
    events = _events(said)
    fallbacks = [event for event in events if event["phase"] == "fallback"]
    check("the explicit fallback event starts the bar again at zero",
          len(fallbacks) == 1 and fallbacks[0]["fraction"] == 0.0, fallbacks)
    check("... and carries the visible second-pass label",
          fallbacks[0].get("passLabel") == "second pass (safe mode)",
          fallbacks[0].get("passLabel"))
    pass_events = [event for event in events if event.get("passLabel")]
    check("every event of the second pass carries that label (out-of-order safe)",
          pass_events and all(event.get("fallback") is True for event in pass_events),
          [(event["phase"], event.get("passLabel")) for event in pass_events][:4])
    done = events[-1]
    check("... and the final verdict is still the only 100%",
          done["phase"] == "done" and done["fraction"] == 1.0, done)


# --------------------------------------------------------------------------
#   The exclusive update lock
# --------------------------------------------------------------------------

@contextmanager
def _with_env(updates: dict):
    """Set/unset environment variables for one block, restoring them after."""
    saved = {name: os.environ.get(name) for name in updates}
    try:
        for name, value in updates.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write_lock_file(path: Path, **over) -> dict:
    data = {"pid": 4321, "started_at": 1000.0, "updated_at": 1000.0,
            "pace": "responsive"}
    data.update(over)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def t_the_lock_path_follows_the_real_settings_dir_rule():
    root = _make_root()
    one, two = root / "cfg-one", root / "cfg-two"
    with _with_env({"OPENJARVIS_CONFIG_DIR": str(one),
                    "JARVIS_CONFIG_DIR": str(two)}):
        check("OPENJARVIS_CONFIG_DIR wins, as it does everywhere else",
              U.settings_dir() == one and U.lock_path() == one / U.LOCK_NAME,
              (U.settings_dir(), U.lock_path()))
    with _with_env({"OPENJARVIS_CONFIG_DIR": None,
                    "JARVIS_CONFIG_DIR": str(two)}):
        check("JARVIS_CONFIG_DIR is the second choice",
              U.settings_dir() == two and U.lock_path() == two / U.LOCK_NAME,
              U.lock_path())
    with _with_env({"OPENJARVIS_CONFIG_DIR": None, "JARVIS_CONFIG_DIR": None}):
        path = U.lock_path()
        check("with neither variable the lock is in ~/.openjarvis, never the clone",
              path.name == U.LOCK_NAME and path.parent.name == ".openjarvis"
              and not str(path).lower().startswith(str(REPO).lower()),
              path)


def t_a_dead_pid_is_stale_immediately():
    root = _make_root()
    path = root / U.LOCK_NAME
    _write_lock_file(path)
    dead = U.read_lock(path, now=1000.0, alive=lambda pid: False)
    check("a lock whose pid is gone is present but NOT valid",
          dead["present"] is True and dead["valid"] is False, dead)
    check("... and it is stale at once, not after the heartbeat window",
          dead["stale"] is True and "no longer running" in dead["why"], dead["why"])
    check("... and the state still says which pid it was",
          dead["pid"] == 4321, dead)
    live = U.read_lock(path, now=1000.0, alive=lambda pid: True)
    check("the SAME file with a live pid is a valid lock",
          live["valid"] is True and live["stale"] is False and live["why"] == "",
          live)


def t_the_heartbeat_expires_after_30_minutes():
    root = _make_root()
    path = root / U.LOCK_NAME
    _write_lock_file(path, started_at=1000.0, updated_at=1000.0)
    check("the design's two windows are the configured ones (30 min / 3 hours)",
          U.LOCK_HEARTBEAT_SECONDS == 1800.0 and U.LOCK_CEILING_SECONDS == 10800.0,
          (U.LOCK_HEARTBEAT_SECONDS, U.LOCK_CEILING_SECONDS))
    at_edge = U.read_lock(path, now=2800.0, alive=lambda pid: True)
    check("a live pid with a heartbeat exactly 30 minutes old is still valid",
          at_edge["valid"] is True, at_edge)
    expired = U.read_lock(path, now=2801.0, alive=lambda pid: True)
    check("one second past the heartbeat window it is stale",
          expired["valid"] is False and expired["stale"] is True
          and ("1800" in expired["why"] or "30 minutes" in expired["why"]),
          expired)


def t_the_three_hour_ceiling_bounds_a_reused_pid():
    root = _make_root()
    path = root / U.LOCK_NAME
    _write_lock_file(path, started_at=0.0, updated_at=10800.0)
    edge = U.read_lock(path, now=10800.0, alive=lambda pid: True)
    check("a fresh heartbeat at exactly the 3-hour ceiling is valid",
          edge["valid"] is True, edge)
    capped = U.read_lock(path, now=10801.0, alive=lambda pid: True)
    check("past the ceiling the lock is stale even though its heartbeat is fresh "
          "(the pid may have been reused)", capped["valid"] is False
          and "3 hours" in capped["why"], capped)


def t_reading_a_lock_never_raises():
    root = _make_root()
    missing = U.read_lock(root / "nothing-here.json")
    check("a missing lock reads as no update, never an error",
          missing["present"] is False and missing["valid"] is False, missing)
    folder = root / "a-folder"
    folder.mkdir()
    as_folder = U.read_lock(folder)
    check("a directory where the lock should be reads as no valid lock",
          as_folder["valid"] is False, as_folder)
    junk = root / "junk.lock"
    junk.write_bytes(b"\x00\xff this is not json")
    check("binary junk in the lock file is stale, not a crash",
          U.read_lock(junk)["stale"] is True, U.read_lock(junk))
    for payload in ([1, 2, 3], "just a string", {"pid": "x"},
                    {"pid": 1, "pace": "responsive"}, {}):
        path = root / "shape.lock"
        path.write_text(json.dumps(payload), encoding="utf-8")
        got = U.read_lock(path)
        check(f"a lock with the wrong shape ({payload!r}) is stale, never raised",
              got["valid"] is False and got["stale"] is True, got)
    bad_alive = root / "alive.lock"
    _write_lock_file(bad_alive)

    def explode(_pid):
        raise RuntimeError("the process table could not be read")
    try:
        got = U.read_lock(bad_alive, now=1000.0, alive=explode)
        raised = False
    except Exception:                          # noqa: BLE001
        raised = True
        got = {}
    check("an alive-check that raises is treated as not running, not a crash",
          not raised and got.get("valid") is False, raised)


def t_acquire_refresh_and_release_lifecycle():
    root = _make_root()
    path = root / "nested" / "update-in-progress.lock"
    taken = U.acquire_lock("responsive", path=path, now=1000.0, pid=111)
    check("acquire creates the folder and the lock", taken["ok"] is True
          and path.is_file(), taken)
    stored = json.loads(path.read_text(encoding="utf-8"))
    check("the lock carries exactly pid, started_at, updated_at and pace",
          stored == {"pid": 111, "started_at": 1000.0, "updated_at": 1000.0,
                     "pace": "responsive"}, stored)
    check("... and a fresh read with a live pid sees it as valid",
          U.read_lock(path, now=1000.0, alive=lambda pid: pid == 111)["valid"] is True)
    try:
        U.acquire_lock("safe", path=path, now=1001.0, pid=222,
                       alive=lambda pid: pid == 111)
        refused = None
    except U.UpdateRefused as exc:
        refused = exc
    check("a second update is refused while the lock is valid",
          refused is not None and refused.code == "update_running", refused)
    check("... and the refusal names the pid, pace and start in plain words",
          refused is not None and "111" in refused.message
          and "responsive" in refused.message and "started" in refused.message,
          getattr(refused, "message", ""))
    check("... and the first update's file is untouched",
          json.loads(path.read_text(encoding="utf-8"))["pid"] == 111)
    check("a heartbeat from another pid does nothing",
          U.refresh_lock(path=path, now=1500.0, pid=222) is False
          and json.loads(path.read_text(encoding="utf-8"))["updated_at"] == 1000.0)
    check("a heartbeat from the owner moves updated_at only",
          U.refresh_lock(path=path, now=1500.0, pid=111) is True
          and json.loads(path.read_text(encoding="utf-8")) == {
              "pid": 111, "started_at": 1000.0, "updated_at": 1500.0,
              "pace": "responsive"})
    check("a reader with the new heartbeat sees it valid again",
          U.read_lock(path, now=1500.0, alive=lambda pid: True)["valid"] is True)
    check("release by another pid leaves the lock alone",
          U.release_lock(path=path, pid=222) is False and path.is_file())
    check("release by the owner removes it", U.release_lock(path=path, pid=111) is True
          and not path.exists())
    check("releasing twice is a quiet False, never an error",
          U.release_lock(path=path, pid=111) is False)


def t_acquire_replaces_a_stale_lock_and_says_when_it_cannot_write():
    root = _make_root()
    path = root / U.LOCK_NAME
    _write_lock_file(path, pid=999999, started_at=1000.0, updated_at=1000.0)
    taken = U.acquire_lock("safe", path=path, now=1000.0, pid=222,
                           alive=lambda pid: False)
    check("a crashed patcher's lock is replaced without ceremony",
          taken["ok"] is True
          and json.loads(path.read_text(encoding="utf-8"))["pid"] == 222, taken)
    blocker = root / "a-file"
    blocker.write_text("not a folder", encoding="utf-8")
    unwritable = U.acquire_lock("safe", path=blocker / U.LOCK_NAME, now=1000.0,
                                pid=333)
    check("an unwritable lock is reported as NOT protecting the update, "
          "never raised and never pretended",
          unwritable["ok"] is False and "not" in unwritable["why"]
          and "could not be written" in unwritable["why"], unwritable)


def t_the_lock_refusal_words_are_the_ones_both_readers_show():
    root = _make_root()
    path = root / U.LOCK_NAME
    _write_lock_file(path, pid=777, started_at=1000.0, updated_at=1000.0,
                     pace="max_speed")
    state = U.read_lock(path, now=1000.0, alive=lambda pid: True)
    words = U.lock_words(state)
    check("the sentence names the pid and the pace's plain label",
          "777" in words and "max_speed" in words and "Fastest" in words, words)
    full = U.lock_refusal_words(state)
    check("... and the refusal says how to bypass it, naming both ways",
          U.LOCK_BYPASS_FLAG in full and U.LOCK_BYPASS_ENV in full
          and "already running" in full, full)


def t_run_suites_refuses_a_valid_lock_and_both_bypasses_work():
    root = _make_root()
    repo, backend = _make_repo(root)
    settings = root / "settings"
    lock = settings / U.LOCK_NAME
    env = dict(os.environ, OPENJARVIS_CONFIG_DIR=str(settings),
               JARVIS_BACKEND=str(backend), PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8")
    U.acquire_lock("responsive", path=lock, pid=os.getpid())
    runner = REPO / "backend" / "run_suites.py"
    try:
        r = subprocess.run([sys.executable, "-B", str(runner),
                            "test_not_a_suite.py"], cwd=str(REPO), env=env,
                           capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        check("run_suites refuses immediately while a valid update lock is held",
              r.returncode == 3, (r.returncode, out[-400:]))
        check("... in plain words naming the pid, pace and start time",
              "REFUSED" in out and str(os.getpid()) in out
              and "responsive" in out and "started" in out, out[-400:])
        check("... and it started nothing", "Not run:" in out, out[-300:])
        bypass = subprocess.run([sys.executable, "-B", str(runner),
                                 "--ignore-update-lock", "test_not_a_suite.py"],
                                cwd=str(REPO), env=env, capture_output=True,
                                text=True, timeout=120, encoding="utf-8",
                                errors="replace")
        bout = (bypass.stdout or "") + (bypass.stderr or "")
        check("--ignore-update-lock is the update's own bypass: the runner goes on "
              "(and reports the unknown suite)",
              bypass.returncode != 3 and "no suite here is named" in bout,
              (bypass.returncode, bout[-300:]))
        env_var = dict(env, **{U.LOCK_BYPASS_ENV: "1"})
        var = subprocess.run([sys.executable, "-B", str(runner),
                              "test_not_a_suite.py"], cwd=str(REPO), env=env_var,
                             capture_output=True, text=True, timeout=120,
                             encoding="utf-8", errors="replace")
        vout = (var.stdout or "") + (var.stderr or "")
        check(f"{U.LOCK_BYPASS_ENV}=1 is the other bypass",
              var.returncode != 3 and "no suite here is named" in vout,
              (var.returncode, vout[-300:]))
        _write_lock_file(lock, pid=999999, started_at=time.time(),
                         updated_at=time.time())
        stale = subprocess.run([sys.executable, "-B", str(runner),
                                "test_not_a_suite.py"], cwd=str(REPO), env=env,
                               capture_output=True, text=True, timeout=120,
                               encoding="utf-8", errors="replace")
        sout = (stale.stdout or "") + (stale.stderr or "")
        check("a stale lock (dead pid) does not block a run",
              stale.returncode != 3 and "REFUSED" not in sout,
              (stale.returncode, sout[-300:]))
    finally:
        U.release_lock(path=lock)
        try:
            lock.unlink()
        except OSError:
            pass


def t_the_runner_does_not_claim_a_lock_check_it_could_not_make():
    sys.path.insert(0, str(HERE))
    import run_suites as R
    root = _make_root()
    settings = root / "settings"
    _write_lock_file(settings / U.LOCK_NAME, pid=os.getpid(),
                     started_at=time.time(), updated_at=time.time())
    with _with_env({"OPENJARVIS_CONFIG_DIR": str(settings),
                    R.LOCK_BYPASS_ENV: None}):
        check("the two readers agree on the bypass flag and variable",
              (R.LOCK_BYPASS_FLAG, R.LOCK_BYPASS_ENV)
              == (U.LOCK_BYPASS_FLAG, U.LOCK_BYPASS_ENV),
              (R.LOCK_BYPASS_FLAG, R.LOCK_BYPASS_ENV))
        check("a valid lock produces the refusal sentence",
              "already running" in R.update_lock_refusal(), R.update_lock_refusal())
        check("--ignore-update-lock bypasses it",
              R.update_lock_refusal(ignore=True) == "")
        os.environ[R.LOCK_BYPASS_ENV] = "1"
        try:
            check("... as does the environment variable",
                  R.update_lock_refusal() == "")
        finally:
            os.environ.pop(R.LOCK_BYPASS_ENV, None)


def t_a_missing_reader_is_not_a_claim_of_enforcement():
    sys.path.insert(0, str(HERE))
    import run_suites as R
    root = _make_root()
    settings = root / "settings"
    _write_lock_file(settings / U.LOCK_NAME, pid=os.getpid(),
                     started_at=time.time(), updated_at=time.time())
    saved = R._update_lock_api
    try:
        with _with_env({"OPENJARVIS_CONFIG_DIR": str(settings)}):
            check("with a valid lock on disk, the runner asks and refuses",
                  "already running" in R.update_lock_refusal())
            R._update_lock_api = lambda: None          # no update tool here
            check("with NO reader it says nothing and blocks nothing - it does "
                  "not claim the lock was checked",
                  R.update_lock_refusal() == "")
            os.environ[R.LOCK_BYPASS_ENV] = "1"
            R._update_lock_api = saved
            check("... and the bypass still answers nothing",
                  R.update_lock_refusal() == "")
            os.environ.pop(R.LOCK_BYPASS_ENV, None)
    finally:
        R._update_lock_api = saved
        os.environ.pop(R.LOCK_BYPASS_ENV, None)


def t_the_update_holds_the_lock_and_releases_it_on_every_way_out():
    root = _make_root()
    repo, backend = _make_repo(root)
    lock = root / "update-in-progress.lock"

    class WatchingRun(FakeRun):
        def __init__(self, handler):
            super().__init__(handler)
            self.lock_states = []

        def __call__(self, cmd, cwd, on_line):
            self.lock_states.append(U.read_lock(lock).get("valid"))
            return super().__call__(cmd, cwd, on_line)

    fake = WatchingRun(_staged_handler(repo, backend, suites="ok"))
    said = []
    code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                    clock=time.time, timings_path=root / "timings.json")
    check("a normal update takes the lock before its first child process",
          fake.lock_states and all(state is True for state in fake.lock_states),
          fake.lock_states)
    check("... and the lock is gone when it finishes", code == 0
          and not lock.exists(), (code, lock.exists()))
    check("... saying so, so a reader knows the exclusivity was real",
          any("Update lock held" in line for line in said), said[:3])

    def exploding(cmd, cwd, on_line):
        raise RuntimeError("the patcher could not be started")
    said = []
    code = U.update(repo, backend, "safe", run=exploding, say=said.append,
                    clock=lambda: 1000.0, timings_path=root / "timings.json")
    check("a crashed child still releases the lock (the finally ran)",
          code == 1 and not lock.exists(), (code, lock.exists()))

    _write_lock_file(lock, pid=os.getpid(), started_at=time.time(),
                     updated_at=time.time(), pace="responsive")
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    try:
        U.update(repo, backend, "responsive", run=fake, say=lambda line: None,
                 clock=lambda: time.time(), timings_path=root / "timings.json")
        refused = None
    except U.UpdateRefused as exc:
        refused = exc
    finally:
        U.release_lock(path=lock)
        try:
            lock.unlink()
        except OSError:
            pass
    check("an update started while another LIVE one holds the lock is refused",
          refused is not None and refused.code == "update_running"
          and fake.calls == [], getattr(refused, "message", fake.calls))


def t_the_heartbeat_keeps_a_long_update_s_alive():
    root = _make_root()
    repo, backend = _make_repo(root)
    lock = root / "update-in-progress.lock"

    class Clock:
        t = 1000.0

        def __call__(self):
            return self.t

    clock = Clock()
    seen = []

    class HeartbeatWatchingRun(FakeRun):
        def __call__(self, cmd, cwd, on_line):
            if _is_patcher(cmd):
                return super().__call__(cmd, cwd, on_line)

            def wrapped(line):
                on_line(line)
                if line.startswith("ok "):
                    # A suite finished; skip the clock 1700s (just under the
                    # 30-minute window) and check the lock is still valid.
                    clock.t += 1700.0
                    seen.append(U.read_lock(lock, now=clock.t).get("valid"))
            return self.handler(cmd, cwd, wrapped, self.state)

    fake = HeartbeatWatchingRun(_staged_handler(repo, backend, suites="ok"))
    code = U.update(repo, backend, "safe", run=fake, say=lambda line: None,
                    clock=clock, timings_path=root / "timings.json")
    check("three suites at 1700s each would expire a 30-minute lock without the "
          "heartbeat - with it, every check after a suite is still valid",
          code == 0 and seen == [True, True, True], (code, seen))
    check("... and the update released it afterwards", not lock.exists())


# --------------------------------------------------------------------------
#   The 2026-10-18 review fixes: S1, S2, S3, S4, S6, S7
# --------------------------------------------------------------------------

def t_the_lock_stays_valid_through_a_30_minute_patch_phase():
    """S1: the patch phase must heartbeat, or a slow patch looks abandoned."""
    root = _make_root()
    repo, backend = _make_repo(root)
    lock = root / "update-in-progress.lock"
    clock = _Clock(time.time())
    seen = []

    class PatchWatchingRun(FakeRun):
        def __call__(self, cmd, cwd, on_line):
            if not _is_patcher(cmd):
                return super().__call__(cmd, cwd, on_line)
            clock.t += 1801.0            # the patcher has run for 30m1s
            code = super().__call__(cmd, cwd, on_line)  # its lines heartbeat
            state = U.read_lock(lock, now=clock.t, alive=lambda pid: True)
            seen.append((state["valid"], state["why"][:40]))
            return code

    fake = PatchWatchingRun(_staged_handler(repo, backend, suites="ok"))
    code = U.update(repo, backend, "safe", run=fake, say=lambda line: None,
                    clock=clock, timings_path=root / "timings.json")
    check("a 30-minute patch phase does not make a live update's lock stale",
          code == 0 and seen and all(valid for valid, _why in seen), (code, seen))
    check("... because the patch phase's own progress lines refreshed it",
          code == 0 and not any("not updated its lock" in why for _v, why in seen),
          seen)


def t_a_live_update_older_than_the_ceiling_is_not_stale():
    """S2: the 3-hour ceiling is a pid-reuse guard, not a deadline for a live run."""
    root = _make_root()
    repo, backend = _make_repo(root)
    _add_suites(repo, 7)
    lock = root / "update-in-progress.lock"
    clock = _Clock(time.time())
    states = []
    start = clock.t

    class LongRunWatcher(FakeRun):
        def __call__(self, cmd, cwd, on_line):
            if _is_patcher(cmd):
                return super().__call__(cmd, cwd, on_line)

            def wrapped(line):
                on_line(line)
                if line.startswith("ok "):
                    clock.t += 1700.0    # each suite takes just under 30 minutes
                    state = U.read_lock(lock, now=clock.t, alive=lambda pid: True)
                    states.append((round(clock.t - start), state["valid"],
                                   state["why"][:40]))
            return self.handler(cmd, cwd, wrapped, self.state)

    fake = LongRunWatcher(_staged_handler(repo, backend, suites="ok"))
    code = U.update(repo, backend, "safe", run=fake, say=lambda line: None,
                    clock=clock, timings_path=root / "timings.json")
    check("a live run longer than 3 hours keeps its lock valid (heartbeats are "
          "fresh; the ceiling is renewed)",
          code == 0 and states and all(valid for _t, valid, _why in states)
          and states[-1][0] > U.LOCK_CEILING_SECONDS,
          (code, states[-3:]))
    check("... and it was never called stale by the ceiling",
          code == 0 and not any("started over" in why for _t, _v, why in states),
          [state for state in states if not state[1]][:2])


def t_a_published_lock_is_never_overwritten():
    """S3: the publish is atomic - an existing lock file is never replaced."""
    root = _make_root()
    path = root / "race" / U.LOCK_NAME
    first = {"pid": 111, "started_at": 1000.0, "updated_at": 1000.0,
             "pace": "responsive"}
    second = {"pid": 222, "started_at": 1001.0, "updated_at": 1001.0,
              "pace": "safe"}
    check("the first publish wins a fresh path", U._publish_new_lock(path, first)
          and json.loads(path.read_text(encoding="utf-8"))["pid"] == 111)
    check("a second publish cannot replace it (the take is atomic)",
          U._publish_new_lock(path, second) is False)
    check("... and the file is the first lock, untouched",
          json.loads(path.read_text(encoding="utf-8")) == first)


def t_two_updaters_cannot_both_take_the_lock():
    """S3: the take is atomic - exactly one winner, and a plain reason for the loser."""
    root = _make_root()
    path = root / "race" / U.LOCK_NAME
    barrier = threading.Barrier(2)
    results = []

    def go(owner):
        barrier.wait(timeout=10)
        try:
            got = U.acquire_lock("safe", path=path, pid=owner,
                                 alive=lambda pid: True)
            results.append(("ok", owner, got.get("ok")))
        except U.UpdateRefused as exc:
            results.append(("refused", owner, exc.message))

    threads = [threading.Thread(target=go, args=(owner,))
               for owner in (111, 222)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    winners = [row for row in results if row[0] == "ok" and row[2] is True]
    refused = [row for row in results if row[0] == "refused"]
    check("of two updaters starting at the same instant exactly one takes the lock",
          len(winners) == 1 and len(refused) == 1, results)
    check("... and the loser gets a plain reason, never a false write failure",
          bool(refused) and "could not be written" not in refused[0][2]
          and ("already running" in refused[0][2]
               or "starting at the same moment" in refused[0][2]), refused)
    data = json.loads(path.read_text(encoding="utf-8"))
    check("... and the single lock on disk belongs to the winner",
          data["pid"] == winners[0][1], (data, winners))


def t_a_lock_taken_after_the_first_check_stops_the_sweep():
    """S4: the runner asks again after staging, just before the first suite."""
    sys.path.insert(0, str(HERE))
    import run_suites as R
    root = _make_root()
    settings = root / "settings"
    lock = settings / U.LOCK_NAME
    U._write_lock(lock, {"pid": os.getpid(), "started_at": time.time(),
                         "updated_at": time.time(), "pace": "responsive"})
    calls = []
    real = R.update_lock_refusal

    def fake(ignore=False):
        calls.append(bool(ignore))
        if len(calls) == 1:
            return ""                    # the first check ran before the lock
        return real(ignore)

    out, err = io.StringIO(), io.StringIO()
    R.update_lock_refusal = fake
    try:
        with _with_env({"OPENJARVIS_CONFIG_DIR": str(settings),
                        "JARVIS_BACKEND": str(REPO / "backend")}):
            with redirect_stdout(out), redirect_stderr(err):
                code = R.main(only=("test_suite_state.py",))
    finally:
        R.update_lock_refusal = real
    check("a lock taken after the first check is caught again after staging",
          code == 3 and len(calls) >= 2, (code, calls, out.getvalue()[-200:]))
    check("... and no suite was started, in as many words",
          "no suite was started" in err.getvalue(), err.getvalue()[:200])
    check("... and the update's own bypass is still respected by the second check",
          calls and calls[-1] is False, calls)


def t_a_nan_infinite_or_future_lock_is_not_a_lock():
    """S6: non-finite or future times are a clock problem, not a live update."""
    root = _make_root()
    path = root / U.LOCK_NAME
    now = time.time()
    cases = [
        ("NaN times", {"pid": os.getpid(), "started_at": float("nan"),
                       "updated_at": float("nan"), "pace": "responsive"}),
        ("an Infinite heartbeat", {"pid": os.getpid(), "started_at": now,
                                   "updated_at": float("inf"),
                                   "pace": "responsive"}),
        ("a time in the future", {"pid": os.getpid(),
                                  "started_at": now + 10 ** 6,
                                  "updated_at": now + 10 ** 6,
                                  "pace": "responsive"}),
    ]
    for label, payload in cases:
        path.write_text(json.dumps(payload), encoding="utf-8")
        state = U.read_lock(path, now=now, alive=lambda pid: True)
        check(f"{label} is not a valid lock (stale, with a reason)",
              state["valid"] is False and state["stale"] is True
              and bool(state["why"]), state)


def t_a_deeply_nested_or_oversized_lock_never_raises():
    """S7: the reader's 'never raises' promise has to survive a JSON bomb."""
    root = _make_root()
    path = root / U.LOCK_NAME
    # 32 KiB of nesting: under the size cap, over Python's JSON recursion limit.
    path.write_bytes(b"[" * 16000 + b"]" * 16000)
    try:
        state = U.read_lock(path, now=time.time(), alive=lambda pid: True)
        raised = None
    except BaseException as exc:          # noqa: BLE001 - the failure being tested
        raised = f"{type(exc).__name__}: {exc}"
        state = {}
    check("a deeply nested lock file reads as stale, never raises",
          raised is None and state.get("valid") is False, raised)
    path.write_bytes(b"x" * (U.LOCK_MAX_BYTES + 10))
    state = U.read_lock(path, now=time.time(), alive=lambda pid: True)
    check("an oversized lock file is not read whole - it is stale",
          state["valid"] is False and "large" in state["why"], state)


def t_an_unexpected_lock_error_never_stops_the_update():
    """S7: if the lock machinery itself breaks, the update runs with a NOTE."""
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    said = []
    real = U.acquire_lock

    def boom(*_args, **_kwargs):
        raise ValueError("a lock file made no sense at all")

    U.acquire_lock = boom
    try:
        code = U.update(repo, backend, "safe", run=fake, say=said.append,
                        clock=time.time, timings_path=root / "timings.json")
    finally:
        U.acquire_lock = real
    check("a raising lock check is a NOTE, not a crashed update",
          code == 0 and any("NOT protected" in line for line in said),
          (code, said[:3]))
    check("... and the update still patched and proved itself",
          code == 0 and U.verify_live_files(repo, backend) == [])


# ==========================================================================
#   The suite's own runner
# ==========================================================================

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:                              # noqa: BLE001
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
