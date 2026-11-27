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
    PROBLEMS");
  * THE APP PATH'S PROOF IS BOUNDED (Gemini rulings 5.1/5.2, 2026-11-21). The
    default proof stage is the bounded post-update subset - named in
    `bounded_proof_plan`: `py_compile` + imports for every shipped module, the
    live HUD's `/api/version` + `/api/status` + `/api/presets`, the egress
    census, and the gate/egress/reconcile/projects suites - and `--full-proof`
    is the only thing that runs the full suite list. The four phases print
    exactly `PROOF: Step N/4 - <phase> - x of y`, a quiet stretch inside one is
    still heartbeated, and a bounded pass never claims the full check (its
    ending says "proven by the bounded checks ... a subset, not the full
    suite");
  * THE ROUTE IS DETECTED UP FRONT (Gemini ruling 5.5, 2026-11-21). A
    deploy-managed install is recognised from `SOURCE-COMMIT` beside `VERSION`
    and/or a `_jarvis-deploy-backup-tool-*` folder, and takes
    `reconcile_live_backend.py` as the PRIMARY route - the patch stack is never
    started, so its guaranteed ~3-minute 51-hunk refusal is not paid. A legacy
    patch-only install still runs the patch stack first, and a deploy refusal is
    reported verbatim with one `ROUTE:` line and no patch fallback.

EVERY GUARD IS BITE-PROVEN in the task report: the tool was mutated once per
guard, this suite was run, the named check here went red, and the bytes were
restored. Every one of the bounded-proof and route-detection tests was also run
against the tree BEFORE this change and failed there, as it should: the bounded
proof, its plan, its flag, the phase lines, the honest ending and the up-front
route detection did not exist. The checks are written so each names what broke
rather than only reporting a count.

Nothing here touches the owner's backend folder, starts a patch run, or reads
`~/.openjarvis`. Runs anywhere: standard library only.
"""
from __future__ import annotations

import json
import hashlib
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
import reconcile_live_backend as R  # noqa: E402

#: The suite drives every update flow with a FAKE runner and must run on a PC
#: with no PowerShell at all. Give the tool the shell name those fake flows
#: expect, so `patcher_command` never looks for a real one; the REAL preference
#: order (pwsh first, then Windows PowerShell, then a refusal) is tested below
#: with an injected `which`.
U.SHELL_WHICH = lambda name: (                         # noqa: E731 - a test stand-in
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    if name == "powershell" else None)

#: The model-lane probes are REAL loopback HTTP against the owner's Ollama in
#: production; this suite must never touch it (the tool's own docstring promises
#: the suite never starts a real update). Quiet fakes here; every lane test
#: below swaps in its own and restores these.
_QUIET_LANE = {"ok": True, "why": "", "models": []}
U.read_lane_models = lambda: dict(_QUIET_LANE)         # noqa: E731 - a test stand-in
U.warm_lane_model = (                                  # noqa: E731 - a test stand-in
    lambda model, context: {"ok": True, "why": ""})

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
    """(repo, backend): exactly the shape preflight and verification expect.

    The repository also carries the release's bundled look spec, as a real
    program folder does: delivery of that spec is content the file half owns
    (2026-11-21), so every update flow below exercises the real step unless a
    test injects its own.
    """
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
    (repo / "jarvis-desktop" / "src").mkdir(parents=True)
    (repo / U.VISUAL_SPEC_REL).write_text(
        json.dumps({"version": 1, "faces": {"robot": {"eyes": "round"}}}),
        encoding="utf-8")
    backend.mkdir()
    (backend / "jarvis_hud.py").write_text("# the owner's backend\n", encoding="utf-8")
    _write_live(backend, OLD)
    return repo, backend


def _make_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="jarvis-update-backend-"))


@contextmanager
def _no_pin(repo, *, ref=None, say=print):
    """`deploy_source`'s answer for a fixture that is NOT a git checkout.

    The Q5 pin (2026-11-27) resolves a commit before anything runs, and every
    fixture in this suite is a plain temporary folder - there is no git object
    store to pin to and there must be no network read. This stands in for that
    step and says "nothing to pin, so use the folder as it is"; the pin itself is
    proved against REAL repositories in the checks further down. Only a fixture
    that is deploy-managed needs it: a patch-only fixture simply says so.
    """
    yield {"tree": Path(repo), "commit": "", "from": "", "why": "", "note": ""}


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
        if suites == "visible-browser-skip":
            # One whole-suite skip for a VISIBLE browser window, one for a file
            # only the owner's PC has. The runner prints both as `skip` lines;
            # the updater must report them with different reasons.
            for name in U.suite_names(repo):
                if name == "test_b.py":
                    on_line("skip  test_b.py  it opens a real, VISIBLE browser "
                            "window (a support chat); set "
                            "JARVIS_ALLOW_VISIBLE_BROWSER_TESTS=1 to run it")
                elif name == "test_c.py":
                    on_line("skip  test_c.py  needs the owner's jarvis_hud.py")
                else:
                    on_line(f"ok    {name:<34} 0.1s")
            on_line("2 passed, 0 skipped, 0 failed")
            return 0
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
                 clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
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
                    run=fake, say=said.append, clock=lambda: 0.0, full_proof=True)
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
    browser = U.suite_result(
        0, ["skip  test_d.py  it opens a real, VISIBLE browser window (Gemini); "
            "set JARVIS_ALLOW_VISIBLE_BROWSER_TESTS=1 to run it",
            "2 passed, 0 skipped, 0 failed"])
    check("a visible-browser skip is recognised as that reason, and is still "
          "unproven, not failed",
          browser["skipped_suites"] == ["test_d.py"]
          and browser["visible_browser_suites"] == ["test_d.py"]
          and browser["unproven"] is True and browser["failed"] is False, browser)


def t_a_visible_browser_skip_is_not_reported_as_a_missing_owner_file():
    """The owner-facing note must say what is really going on (review, #861).

    The update used to print ONE sentence for every whole-suite skip: "N
    suite(s) need files that live only on the owner's PC". For the four suites
    this branch guards that is false - the files are on his PC and the suite is
    skipped because it would open real, VISIBLE browser windows. Measured here
    through the real update flow with a fake runner, so the fix is checked
    where the owner would see it, not only in the parser.
    """
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend, suites="visible-browser-skip"))
    said = []
    code = U.update(repo, backend, "safe", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
    text = "\n".join(said)
    check("the update still ends unproven, never failed",
          code == 0 and "DONE - no problems, but NOT fully proven" in text,
          (code, said[-8:]))
    check("... the VISIBLE-browser suite is named with the opt-in that runs it",
          "1 suite(s) open a real, VISIBLE browser window on this screen and "
          "were skipped: test_b.py" in text
          and f"Set {U.VISIBLE_BROWSER_ENV}=1 to run them." in text,
          said[-8:])
    check("... the real missing-file skip keeps its own reason, with its name",
          "need files that live only on the owner's PC and were skipped: test_c.py"
          in text, said[-8:])
    check("... and the visible-browser suite is NOT put in that list",
          "owner's PC and were skipped: test_b.py" not in text, said[-8:])
    check("... the final event still says unproven, not ok",
          (lambda done: bool(done) and done[-1].get("verdict") == "unproven")(
              [e for e in _events(said) if e.get("phase") == "done"]), _events(said)[-3:])


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
                    clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
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
                        clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
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
                    clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
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
                    clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
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
             clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
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
    # A Python child gets ONE extra variable - the one that makes its printout
    # arrive line by line - and nothing else is touched.
    py_env = U._child_env(sys.executable, base, python=True)
    check("a Python child is marked unbuffered, and only that is added",
          py_env == dict(base, PYTHONUNBUFFERED="1"), py_env)
    check("... while a shell child is not marked, so its module path is the only change",
          "PYTHONUNBUFFERED" not in U._child_env(windows, base))


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
    before = os.environ.get("PYTHONUNBUFFERED")
    U.subprocess.Popen = fake_popen
    try:
        U._run([sys.executable, "-B", "-c", "pass"], ".", lambda line: None)
    finally:
        U.subprocess.Popen = real_popen
    env = seen.get("env") or {}
    check("a Python child is given an environment that makes it write each line "
          "at once, so the desktop's live log (and its progress bound) sees it",
          env.get("PYTHONUNBUFFERED") == "1", seen.get("env"))
    check("... and the caller's own environment is kept in that copy",
          env is not None and ("PATH" in env or "Path" in env), env)
    # A Python child's environment is a COPY: the CALLER's own environment is
    # untouched, so setting PYTHONUNBUFFERED for a child never leaks upward.
    check("... without being written back into this process's own environment",
          os.environ.get("PYTHONUNBUFFERED") == before, os.environ.get("PYTHONUNBUFFERED"))


# --------------------------------------------------------------------------
#   The proof stage's own sign of life (measured 2026-11-21)
# --------------------------------------------------------------------------
#
# THE MEASURED FAILURE. The owner's PC, 2026-11-21: the automatic finish for
# desktop 0.2.491 started at 07:07 PT, the deploy route carried the file half
# (VERSION 0.2.491 at 07:11), delivered the look spec and recorded the everyday
# lane's model, and then the proof suites ran. At 07:55 PT - 48m 10s in - the
# desktop's 15-minute silence bound ended that HEALTHY run, because ONE proof
# suite can print nothing between suite boundaries (`test_live_settings_parity.py`
# was one; the previous full run took ~48-57 minutes). "No output" was read as a
# stall. The fix is the heartbeat below; the silence bound keeps its 15 minutes
# and now means "the heartbeat AND the child both stopped", which is a real hang.
# Every test here drives the injected clock and scripted child output - no real
# five-minute wait is ever paid.


def t_the_proof_stage_says_it_is_alive_at_least_every_five_minutes():
    check("the heartbeat is every five minutes - a third of the app's 15-minute "
          "silence bound, so it can never be late enough to trip it",
          U.PROOF_HEARTBEAT_SECONDS == 300.0, U.PROOF_HEARTBEAT_SECONDS)
    check("... and the bound it exists for is still the app's own 15 minutes",
          300.0 < 15 * 60, U.PROOF_HEARTBEAT_SECONDS)

    said = []
    beat = U._ProofHeartbeat(said.append, started=1000.0)
    check("nothing is printed before the first five quiet minutes",
          beat.beat(1299.0) is None and said == [], said)
    line = beat.beat(1300.0)
    check("... at five quiet minutes the proof stage says it is still running, "
          "in the one measured shape",
          line == "PROOF: still running - 5m 00s elapsed, checking the backend "
                  "against the live folder", line)
    check("... and the line is on the run's own output", said == [line], said)

    # The measured run, to the minute: 48m 10s of a proof stage. A minute at a
    # time is exactly what the runner's quiet poll checks, and the rule the
    # app's bound depends on is that no two of the tool's own lines are ever
    # five minutes apart.
    run_said = []
    run_beat = U._ProofHeartbeat(run_said.append, started=1000.0)
    minutes = []
    for minute in range(1, 49):
        if run_beat.beat(1000.0 + minute * 60.0) is not None:
            minutes.append(minute)
    check("a 48-minute proof stage is heartbeated about every five minutes",
          minutes == [5, 10, 15, 20, 25, 30, 35, 40, 45], minutes)
    check("... so the log grew at least once every five minutes, never the "
          "fifteen the app calls a stall",
          all(later - earlier <= 5 for earlier, later in zip([0] + minutes, minutes)),
          minutes)
    check("... and the elapsed clock in the line is the RUN's, not the interval's",
          run_said[-1].startswith("PROOF: still running - 45m 00s elapsed"),
          run_said[-1])


def t_a_real_child_line_restarts_the_heartbeat_clock():
    # Real suite output is progress of its own: a suite that finishes must not
    # be followed by a heartbeat three minutes later claiming the same quiet
    # stretch, and the elapsed time stays the run's from its start.
    said = []
    beat = U._ProofHeartbeat(said.append, started=0.0)
    beat.saw_output(240.0)          # a suite finished four minutes in
    check("a real child line restarts the five-minute clock",
          beat.beat(539.0) is None and said == [], said)
    check("... so the next heartbeat is five minutes after the suite line, not "
          "after the last heartbeat",
          beat.beat(540.0) is not None
          and said == ["PROOF: still running - 9m 00s elapsed, checking the "
                       "backend against the live folder"], said)
    check("... and a quiet poll with no heartbeat prints nothing at all",
          beat.beat(541.0) is None)


def t_a_quiet_child_is_heartbeated_by_the_runner_loop():
    # `follow_child` is the loop the real pipe reader (`_follow_pipe`) runs:
    # scripted child output plus a fake clock, so "silent for 24 minutes" is a
    # test rather than an afternoon.
    class Ticker:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            self.t += 60.0          # each poll is one minute of quiet child
            return self.t

    clock = Ticker()
    script = ([U._QUIET] * 6
              + ["ok    test_live_settings_parity.py      1.2s"]
              + [U._QUIET] * 24
              + [U._ENDED])
    said = []
    beat = U._ProofHeartbeat(said.append, started=0.0)
    U.follow_child(lambda: script.pop(0), said.append, beat, clock=clock)
    heartbeat_lines = [line for line in said
                       if line.startswith(U.PROOF_HEARTBEAT_PREFIX)]
    child_lines = [line for line in said
                   if not line.startswith(U.PROOF_HEARTBEAT_PREFIX)]
    check("the child's own output flows through unchanged and in order",
          child_lines == ["ok    test_live_settings_parity.py      1.2s"],
          child_lines)
    check("... and the 24 quiet minutes around it are heartbeated every five",
          [line.split(" elapsed")[0] for line in heartbeat_lines]
          == ["PROOF: still running - 5m 00s",
              "PROOF: still running - 12m 00s",
              "PROOF: still running - 17m 00s",
              "PROOF: still running - 22m 00s",
              "PROOF: still running - 27m 00s"], heartbeat_lines)
    check("... each heartbeat is the one documented line, not a raw count",
          all(line.endswith(", checking the backend against the live folder")
              for line in heartbeat_lines), heartbeat_lines)
    # Without a heartbeat the same loop is exactly the old reader: every child
    # line, and silence while the child says nothing.
    quiet = [U._QUIET, "one line", U._ENDED]
    plain = []
    U.follow_child(lambda: quiet.pop(0), plain.append, None, clock=clock)
    check("without a heartbeat the loop is the old reader: lines only",
          plain == ["one line"], plain)


def t_only_the_proof_suites_child_gets_the_heartbeat():
    root = _make_root()
    repo, backend = _make_repo(root)
    check("the suites command is the proof stage",
          U._is_proof_stage(U.suites_command(repo, 14, backend)) is True,
          U.suites_command(repo, 14, backend))
    check("... and the patcher is NOT - its own progress lines already arrive "
          "per patch, so it needs no second kind of output",
          U._is_proof_stage(U.patcher_command(repo, backend)) is False,
          U.patcher_command(repo, backend))
    check("... nor is the release's additive tool writer",
          U._is_proof_stage([sys.executable, "-B",
                             str(repo / U.NEW_TOOLS_TOOL_REL), "--add", "x",
                             "--apply"]) is False)


def t_the_real_runner_wires_the_heartbeat_to_the_proof_child():
    # The real `_run` builds the heartbeat for the suites child and for nothing
    # else, and hands every real child line to the same callback unchanged.
    root = _make_root()
    repo, backend = _make_repo(root)
    built, saw = [], []

    class RecordingHeartbeat:
        def __init__(self, say, started, *, interval=U.PROOF_HEARTBEAT_SECONDS):
            built.append((say, started, interval))

        def saw_output(self, now):
            saw.append(now)

        def beat(self, now):
            saw.append(("beat", now))

    class FakeProc:
        def __init__(self, lines):
            self.stdout = iter(lines)

        def wait(self):
            return 0

    real_popen, real_heartbeat = U.subprocess.Popen, U._ProofHeartbeat
    U._ProofHeartbeat = RecordingHeartbeat
    U.subprocess.Popen = lambda argv, **kwargs: FakeProc(
        ["ok    test_a.py                       0.1s\n", "2 passed, 0 skipped, 0 failed\n"])
    got, patcher_got = [], []
    try:
        code = U._run(U.suites_command(repo, 14, backend), ".", got.append)
        suites_built, suites_saw = list(built), list(saw)
        built.clear()
        patcher_code = U._run(U.patcher_command(repo, backend), ".", patcher_got.append)
        patcher_built = list(built)
    finally:
        U.subprocess.Popen, U._ProofHeartbeat = real_popen, real_heartbeat
    check("the real runner builds a heartbeat for the proof child",
          len(suites_built) == 1 and suites_built[0][0] is print
          and suites_built[0][2] == U.PROOF_HEARTBEAT_SECONDS, suites_built)
    check("... and does not build one for the patcher",
          patcher_built == [], patcher_built)
    check("... the child's lines still reach the runner's callback unchanged",
          got == ["ok    test_a.py                       0.1s",
                  "2 passed, 0 skipped, 0 failed"]
          and patcher_got == list(got), (got, patcher_got))
    check("... every child line is progress that resets the heartbeat clock",
          len(suites_saw) == 2 and not any(isinstance(item, tuple)
                                           for item in suites_saw), suites_saw)
    check("... and both children ran to their end",
          code == 0 and patcher_code == 0, (code, patcher_code))
    check("the five-minute interval is well inside the app's own 15-minute "
          "silence bound (backend_update.rs's SCRIPT_SILENCE_LIMIT)",
          U.PROOF_HEARTBEAT_SECONDS * 3 <= 15 * 60, U.PROOF_HEARTBEAT_SECONDS)


def t_the_heartbeat_words_are_the_owner_s_clock():
    check("whole minutes and zero-padded seconds, as the owner reads a clock",
          [U.elapsed_words(0), U.elapsed_words(5), U.elapsed_words(65),
           U.elapsed_words(24 * 60 + 5), U.elapsed_words(60 * 60 + 7 * 60)]
          == ["0m 00s", "0m 05s", "1m 05s", "24m 05s", "1h 07m"],
          [U.elapsed_words(24 * 60 + 5), U.elapsed_words(60 * 60 + 7 * 60)])
    check("... and the measured ending's own number is written as 48m 10s",
          "48m 10s" in U.proof_heartbeat_words(48 * 60 + 10),
          U.proof_heartbeat_words(48 * 60 + 10))
    check("... with the one prefix the app's log and tail carry",
          U.proof_heartbeat_words(0).startswith("PROOF: still running - "),
          U.proof_heartbeat_words(0))


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
                     timings_path=root / "timings.json", full_proof=True)
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
             clock=lambda: 0.0, timings_path=path, full_proof=True)
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
             clock=lambda: 0.0, timings_path=path, full_proof=True)
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
             clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
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
                    clock=time.time, timings_path=root / "timings.json", full_proof=True)
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
                    clock=lambda: 1000.0, timings_path=root / "timings.json", full_proof=True)
    check("a crashed child still releases the lock (the finally ran)",
          code == 1 and not lock.exists(), (code, lock.exists()))

    _write_lock_file(lock, pid=os.getpid(), started_at=time.time(),
                     updated_at=time.time(), pace="responsive")
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    try:
        U.update(repo, backend, "responsive", run=fake, say=lambda line: None,
                 clock=lambda: time.time(), timings_path=root / "timings.json", full_proof=True)
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
                    clock=clock, timings_path=root / "timings.json", full_proof=True)
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
                    clock=clock, timings_path=root / "timings.json", full_proof=True)
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
                    clock=clock, timings_path=root / "timings.json", full_proof=True)
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
                        clock=time.time, timings_path=root / "timings.json", full_proof=True)
    finally:
        U.acquire_lock = real
    check("a raising lock check is a NOTE, not a crashed update",
          code == 0 and any("NOT protected" in line for line in said),
          (code, said[:3]))
    check("... and the update still patched and proved itself",
          code == 0 and U.verify_live_files(repo, backend) == [])


# ==========================================================================
#   The owner's everyday model lane is recorded and put back (2026-11-21)
# ==========================================================================
#
# Measured on the owner's PC, 2026-11-21, after the same auto-finish run this
# suite's progress bound was fixed for: the proof suites run against the live
# backend folder and at least one of them loads a different model on the
# everyday lane without putting the owner's back. Lane 11436 - whose preset-table
# row is `qwen3.5:9b` at 196,608 tokens - was left resident on
# `jarvis-primary:latest` at 16,384, and the field battery's PRESETS row then
# failed ("the everyday lane is on a model its own preset table declares for it"
# / "on its one-card model at 196,608"). The owner restored it by hand.
#
# The rule these checks hold: the lane's resident model+context is read BEFORE
# the proof suites and warmed back at the RECORDED context when they leave a
# different one; a lane that cannot be read restores nothing and says so; and a
# run the desktop's bound ends is restored from the record it wrote first, by
# the tool's own `--restore-lane` mode. Nothing here touches the real Ollama:
# the seam functions are faked for every check.
#
# The tool's suite itself must never touch the owner's Ollama: `read_lane_models`
# and `warm_lane_model` are module-level seams, and the quiet fakes at the top
# of this file are what every other update flow in this suite runs with.

@contextmanager
def _lane_seams(read, warm):
    """Swap the tool's model-lane seams for one check, and put the fakes back."""
    real_read, real_warm = U.read_lane_models, U.warm_lane_model
    U.read_lane_models, U.warm_lane_model = read, warm
    try:
        yield
    finally:
        U.read_lane_models, U.warm_lane_model = real_read, real_warm


def _a_lane_handler(repo: Path, backend: Path, lane: dict, *, changed=True):
    """A patcher + suite runner that leaves the everyday lane switched.

    The measured failure in one line: the suite phase puts a different model on
    the lane (`changed=True`) and never puts the owner's back.
    """
    def handler(cmd, cwd, on_line, state):
        if _is_patcher(cmd):
            state["patcher_calls"] = state.get("patcher_calls", 0) + 1
            for name, content in NEW.items():
                (backend / name).write_bytes(content)
            on_line("Rehearsing all 2 on a copy first.")
            on_line("  ok           a.patch")
            on_line("DONE - no problems, but NOT fully proven (see below)")
            return 0
        # Snapshot what the record held when the suites started (it is removed
        # once the lane is back, so it cannot be read after the run).
        if "record_at_first_suite" not in state:
            path = U.lane_state_path(backend)
            try:
                state["record_at_first_suite"] = json.loads(
                    path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state["record_at_first_suite"] = None
        if changed:
            lane["models"] = [{"model": "jarvis-primary:latest", "context": 16384}]
        for name in U.suite_names(repo):
            on_line(f"ok    {name:<34} 0.1s")
        on_line("3 passed, 0 skipped, 0 failed")
        return 0

    return handler


def t_the_owner_s_everyday_model_lane_is_put_back_after_the_proof_suites():
    root = _make_root()
    repo, backend = _make_repo(root)
    lane = {"models": [{"model": "qwen3.5:9b", "context": 196608}]}
    warmed = []

    def read():
        return {"ok": True, "why": "", "models": list(lane["models"])}

    def warm(model, context):
        warmed.append((model, int(context)))
        lane["models"] = [{"model": model, "context": int(context)}]
        return {"ok": True, "why": ""}

    fake = FakeRun(_a_lane_handler(repo, backend, lane))
    said = []
    with _lane_seams(read, warm):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json", full_proof=True)
    report = "\n".join(said)
    lane_lines = [line for line in said if line.startswith(U.LANE_PREFIX)]
    saved = fake.state.get("record_at_first_suite")
    check("the lane is recorded BEFORE the proof suites run - the record names "
          "the owner's own model and context",
          saved is not None, saved)
    check("... and the recorded pair is what was resident (qwen3.5:9b at 196608)",
          isinstance(saved, dict) and saved.get("model") == "qwen3.5:9b"
          and saved.get("context") == 196608, saved)
    check("the everyday model is warmed back at its RECORDED context once the "
          "suites left another one",
          warmed == [("qwen3.5:9b", 196608)], warmed)
    check("... the run report says it was restored, in ONE LANE line",
          len(lane_lines) == 1
          and "qwen3.5:9b" in lane_lines[0] and "196608" in lane_lines[0]
          and "jarvis-primary:latest" in lane_lines[0]
          and "read it back in place" in lane_lines[0], lane_lines)
    check("... the pre-suite record is gone once the lane is back",
          not U.lane_state_path(backend).exists())
    check("... and the backend update itself still proved itself",
          code == 0 and "ALL DONE - the backend is patched and proven" in report,
          (code, said[-5:]))


def t_a_lane_the_suites_left_alone_is_not_touched():
    root = _make_root()
    repo, backend = _make_repo(root)
    lane = {"models": [{"model": "qwen3.5:9b", "context": 196608}]}
    warmed = []

    def read():
        return {"ok": True, "why": "", "models": list(lane["models"])}

    def warm(model, context):
        warmed.append((model, int(context)))
        return {"ok": True, "why": ""}

    said = []
    with _lane_seams(read, warm):
        code = U.update(repo, backend, "responsive",
                        run=FakeRun(_a_lane_handler(repo, backend, lane, changed=False)),
                        say=said.append, clock=lambda: 0.0,
                        timings_path=root / "timings.json", full_proof=True)
    lane_lines = [line for line in said if line.startswith(U.LANE_PREFIX)]
    check("a lane the proof suites left on the owner's model is NOT warmed again",
          code == 0 and warmed == [], (code, warmed))
    check("... the report says it was left alone, in one LANE line",
          len(lane_lines) == 1 and "left it alone" in lane_lines[0]
          and "qwen3.5:9b" in lane_lines[0], lane_lines)
    check("... and no record is left behind",
          not U.lane_state_path(backend).exists())


def t_an_unreadable_lane_is_reported_and_nothing_is_restored():
    root = _make_root()
    repo, backend = _make_repo(root)
    lane = {"models": [{"model": "jarvis-primary:latest", "context": 16384}]}
    warmed = []

    def read():
        return {"ok": False, "why": "ConnectionRefusedError: [WinError 10061]",
                "models": []}

    said = []
    with _lane_seams(read, lambda model, context: warmed.append((model, context))):
        code = U.update(repo, backend, "responsive",
                        run=FakeRun(_a_lane_handler(repo, backend, lane, changed=False)),
                        say=said.append, clock=lambda: 0.0,
                        timings_path=root / "timings.json", full_proof=True)
    lane_lines = [line for line in said if line.startswith(U.LANE_PREFIX)]
    check("a lane that cannot be read is NOT guessed at - no model is named or warmed",
          warmed == [], warmed)
    check("... and the report says the lane could not be read and nothing was restored",
          len(lane_lines) == 1 and "could not be read" in lane_lines[0]
          and "nothing was restored" in lane_lines[0]
          and "ConnectionRefusedError" in lane_lines[0], lane_lines)
    check("... while the backend update itself is unaffected",
          code == 0 and not U.lane_state_path(backend).exists(), code)


def t_a_model_with_no_recorded_context_is_never_warmed():
    # A preload that names no context is the 2026-10-10 bug: it reloads a model
    # at Ollama's own 2,048 instead of the lane's window. So a record with no
    # context restores nothing, even if the suites changed the lane.
    warmed = []
    said = []
    got = U.restore_lane(
        {"ok": True, "model": "qwen3.5:9b", "context": None},
        read=lambda: {"ok": True, "why": "",
                      "models": [{"model": "other", "context": 8192}]},
        warm=lambda model, context: warmed.append((model, context)) or {"ok": True, "why": ""},
        say=said.append)
    check("a recorded model with no recorded context is never warmed without one",
          got["done"] is True and warmed == []
          and "did not report a context" in said[0] and "nothing was restored" in said[0],
          (got, said))
    # The lane cannot be read AFTER the suites: a blind warm could load a model
    # whose name this run never recorded, so nothing is restored and the record
    # is kept for the desktop's retry.
    said_again = []
    got_again = U.restore_lane(
        {"ok": True, "model": "qwen3.5:9b", "context": 196608},
        read=lambda: {"ok": False, "why": "no answer", "models": []},
        warm=lambda model, context: {"ok": True, "why": ""},
        say=said_again.append)
    check("a lane that cannot be read after the suites restores nothing and says so",
          got_again["done"] is False and "could not be read after the proof suites"
          in said_again[0] and "not claimed" in said_again[0], (got_again, said_again))


def t_the_record_restores_the_lane_when_the_desktop_ends_the_run():
    # THE TIMEOUT ENDING. The tool wrote the lane's record before the proof
    # suites; the desktop's progress bound then ended it before it could restore
    # anything. The record is what the desktop's `--restore-lane` run uses.
    root = _make_root()
    backend = _make_repo(root)[1]
    lane = {"models": [{"model": "qwen3.5:9b", "context": 196608}]}
    U.record_lane_state(
        backend, read=lambda: {"ok": True, "why": "", "models": list(lane["models"])})
    record_path = U.lane_state_path(backend)
    saved = json.loads(record_path.read_text(encoding="utf-8"))
    check("the tool writes the pre-suite record where the desktop looks for it",
          record_path.is_file() and saved.get("model") == "qwen3.5:9b"
          and saved.get("context") == 196608, saved)

    lane["models"] = [{"model": "jarvis-primary:latest", "context": 16384}]
    warmed = []

    def read():
        return {"ok": True, "why": "", "models": list(lane["models"])}

    def warm(model, context):
        warmed.append((model, int(context)))
        lane["models"] = [{"model": model, "context": int(context)}]
        return {"ok": True, "why": ""}

    said = []
    with _lane_seams(read, warm):
        code = U.main(["--restore-lane", "--backend", str(backend)], say=said.append)
    lane_lines = [line for line in said if line.startswith(U.LANE_PREFIX)]
    check("a run the desktop ended is restored from its record at the recorded pair",
          code == 0 and warmed == [("qwen3.5:9b", 196608)], (code, warmed))
    check("... the report says it was restored, in one LANE line",
          len(lane_lines) == 1 and "read it back in place" in lane_lines[0]
          and "qwen3.5:9b" in lane_lines[0], lane_lines)
    check("... and the record is removed, so it can never override a later choice",
          not record_path.exists())
    # With no record left there is nothing to say: the tool's own ending had
    # already put the lane back.
    said_again = []
    with _lane_seams(read, warm):
        code_again = U.main(["--restore-lane", "--backend", str(backend)],
                            say=said_again.append)
    check("a restore-mode run with no record left does nothing and says nothing",
          code_again == 0 and said_again == []
          and warmed == [("qwen3.5:9b", 196608)], (code_again, said_again))


def t_a_failed_restore_is_reported_and_the_record_is_kept_for_the_desktop():
    root = _make_root()
    backend = _make_repo(root)[1]
    record = U.record_lane_state(
        backend,
        read=lambda: {"ok": True, "why": "",
                      "models": [{"model": "qwen3.5:9b", "context": 196608}]})
    lane = {"models": [{"model": "jarvis-primary:latest", "context": 16384}]}

    def read():
        return {"ok": True, "why": "", "models": list(lane["models"])}

    said = []
    got = U.restore_lane_after_suites(
        backend, record, read=read,
        warm=lambda model, context: {"ok": False, "why": "the load was refused"},
        say=said.append)
    check("a restore that failed is reported honestly, never claimed as back",
          got["done"] is False and "failed" in said[0]
          and "not claimed to be back" in said[0], (got, said))
    check("... and the record is KEPT for the desktop's one retry",
          U.lane_state_path(backend).is_file())
    # The desktop's retry works, and only then is the record removed.
    warmed = []

    def warm(model, context):
        warmed.append((model, int(context)))
        lane["models"] = [{"model": model, "context": int(context)}]
        return {"ok": True, "why": ""}

    retried = U.restore_saved_lane(backend, read=read, warm=warm,
                                   say=lambda line: None)
    check("the desktop's retry warms the recorded pair back and removes the record",
          retried == 0 and warmed == [("qwen3.5:9b", 196608)]
          and not U.lane_state_path(backend).exists(), (retried, warmed))


def t_the_model_lane_is_only_ever_read_on_this_pc():
    check("a loopback OLLAMA_URL is the lane",
          U.lane_url("http://127.0.0.1:11436") == "http://127.0.0.1:11436")
    check("... localhost and ::1 are this PC too",
          U.lane_url("http://localhost:11434/") == "http://localhost:11434"
          and U.lane_url("http://[::1]:11434") == "http://[::1]:11434")
    check("... an unset lane is the backend's own loopback default",
          U.lane_url("") == U.DEFAULT_OLLAMA_URL
          and U.lane_url(None) == U.DEFAULT_OLLAMA_URL)
    check("another machine's lane is REFUSED, never contacted",
          U.lane_url("http://192.168.1.50:11434") is None
          and U.lane_url("https://example.com") is None
          and U.lane_url("ftp://127.0.0.1:11434") is None)
    check("no lane at all is an honest 'not read', not a guess",
          U.lane_models(url="")["ok"] is False
          and "loopback" in U.lane_models(url="")["why"])


# ==========================================================================
#   The route is chosen with evidence: the deploy-managed install (2026-11-21)
# ==========================================================================
#
# Measured on the owner's own PC, 2026-11-21 00:25-00:28 PT, the real end-to-end
# test. Desktop 0.2.487 was installed by its installer; the next start detected
# BackendOlder and ran the automatic finish. The backend half was the patch
# stack - and this install's live files come from tools/reconcile_live_backend.py
# (the published base plus the HUD deltas), not from a full apply-patches.ps1
# run. The stack rehearsed on a copy, refused 51 of its 160 patches
# ("51 patch(es) will not apply to your files as they are"), changed nothing,
# and the automatic finish reported the backend half failed even though the
# deploy tool - run by hand - finished the same update with 0 refusals.
#
# These checks hold the whole rule: the measured case finishes via the deploy
# route (VERSION written, the same suites run, the report naming BOTH routes);
# a deploy-tool refusal is reported verbatim and claims nothing; a patched
# install never takes the deploy route; a refusal for another reason is not
# routed around; and the lock, pace, safe second pass and timings still hold.

#: The patch program's real refusal shape, abridged to the lines the tool
#: reads. This is the transcript the owner's automatic finish wrote.
_MEASURED_REFUSAL = [
    "Rehearsing all 160 on a copy first.",
    "  ok           a.patch",
    "  FAIL         b.patch",
    "51 patch(es) will not apply. NOTHING HAS BEEN CHANGED.",
    "(The rehearsal ran on a copy. Your backend files were not changed - not "
    "even their line endings.)",
    "51 patch(es) will not apply to your files as they are: b.patch. "
    "Nothing was changed.",
    "What to do: read the problem list above, fix the first one, run the",
    "same command again. If it is not clear, send back the log file.",
    " DONE WITH PROBLEMS - do not trust this update yet",
    "None of your backend files were changed by this run.",
]


def _refusal_then_suites(repo: Path, backend: Path, *, suites_fail_first=False):
    """A patch-stack refusal, then the normal parallel/safe suite runs."""
    def handler(cmd, cwd, on_line, state):
        if _is_patcher(cmd):
            state["patcher_calls"] = state.get("patcher_calls", 0) + 1
            for line in _MEASURED_REFUSAL:
                on_line(line)
            state["after_patch"] = {name: (backend / name).read_bytes()
                                    for name in OLD}
            return 1
        state["suite_calls"] = state.get("suite_calls", 0) + 1
        jobs = _jobs_of(cmd)
        state.setdefault("suite_jobs", []).append(jobs)
        if suites_fail_first and state["suite_calls"] == 1 and jobs > 1:
            on_line("ok    test_a.py                       0.1s")
            on_line("FAIL  test_b.py                       0.1s  "
                    "(exit 1)  2 passed, 0 skipped, 1 failed")
            on_line("2 passed, 0 skipped, 1 failed")
            return 1
        names = U.suite_names(repo)
        for name in names:
            on_line(f"ok    {name:<34} 0.1s")
        on_line(f"{len(names)} passed, 0 skipped, 0 failed")
        return 0

    return handler


def _deploy_ok(backend: Path, *, version="0.2.487", ref="a" * 40, calls=None,
               writes=True):
    """A successful deploy route: writes the release's bytes and VERSION.

    Returns the same report shape `U.deploy_route` does, so the state machine is
    driven exactly as the real one drives it.
    """
    def deploy(repo_arg, backend_arg, *, say):
        if calls is not None:
            calls.append({"repo": str(repo_arg), "backend": str(backend_arg)})
        if writes:
            for name, content in NEW.items():
                (Path(backend_arg) / name).write_bytes(content)
            (Path(backend_arg) / "VERSION").write_bytes(version.encode())
        say("RESULT: PASS - backend reconciled; restart Jarvis and read the "
            "start-up banner.")
        return {"ok": True, "code": 0, "ref": ref, "version": version,
                "desktop_version": version, "why": "",
                "lines": ["RESULT: PASS"]}

    return deploy


def _deploy_refused(why, *, lines=None):
    """A deploy route that refused: its own words, no write, nothing claimed."""
    def deploy(repo_arg, backend_arg, *, say):
        said = list(lines or [why])
        for line in said:
            say(line)
        return {"ok": False, "code": 2, "ref": "", "version": "",
                "desktop_version": "", "why": why, "lines": said}

    return deploy


def t_the_patch_refusal_is_recognised_only_from_its_measured_shape():
    got = U.patch_refusal(_MEASURED_REFUSAL)
    check("the measured transcript IS the deploy-managed refusal shape",
          got["refused"] is True and got["count"] == 51
          and got["nothing_changed"] is True and got["half_updated"] is False,
          got)
    check("... and its one sentence names the count and the install type",
          "51 hunk(s)" in U.refusal_route_words(got)
          and "this install" in U.refusal_route_words(got),
          U.refusal_route_words(got))
    # The same words WITH the half-updated warning is the one shape that must
    # never be routed around: the files really were changed.
    half = list(_MEASURED_REFUSAL) + [
        "Some of your backend files WERE changed before this went wrong, and the",
        "patched files may be HALF updated.",
    ]
    check("a half-updated patch run is never treated as the deploy-managed shape",
          U.patch_refusal(half)["refused"] is False, U.patch_refusal(half))
    # A refusal for another reason is not evidence for the deploy route.
    other = ["Jarvis looks like it is still running (pid 42). Close it, then "
             "run this again (or add -Force).",
             " DONE WITH PROBLEMS - do not trust this update yet",
             "None of your backend files were changed by this run."]
    check("a refusal for another reason keeps today's behaviour",
          U.patch_refusal(other)["refused"] is False
          and U.patch_refusal(other)["count"] is None, U.patch_refusal(other))
    check("a clean patcher run is not a refusal",
          U.patch_refusal(["DONE - no problems, but NOT fully proven"])["refused"]
          is False)
    check("a refusal without a printed count says so rather than inventing one",
          "refused to apply" in U.refusal_route_words({"count": None}),
          U.refusal_route_words({"count": None}))
    check("the deploy tool's own REFUSED line is quoted verbatim",
          U.deploy_failure_words(["a line", "REFUSED: the working tree is at "
                                  "HEAD x but --ref y is z"], 2)
          == "REFUSED: the working tree is at HEAD x but --ref y is z",
          U.deploy_failure_words(["REFUSED: nope"], 2))
    check("... and a failed apply's RESULT line is quoted too",
          U.deploy_failure_words(["a line", "RESULT: FAIL - the live folder was "
                                  "rolled back"], 1).startswith("RESULT: FAIL"),
          U.deploy_failure_words(["RESULT: FAIL - x"], 1))


def t_the_measured_deployed_install_finishes_by_the_deploy_route():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_refusal_then_suites(repo, backend))
    deploys = []
    said = []
    code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json",
                    deploy=_deploy_ok(backend, calls=deploys), full_proof=True)
    patchers = [cmd for cmd in fake.calls if _is_patcher(cmd)]
    suites = [cmd for cmd in fake.calls if not _is_patcher(cmd)]
    tail = "\n".join(said)
    check("the measured deploy-managed install finishes: the backend half succeeds",
          code == 0 and "ALL DONE - the backend is patched and proven" in tail,
          (code, said[-6:]))
    check("... the patch program is tried ONCE and not run again on the safe pass",
          len(patchers) == 1, len(patchers))
    check("... the deploy route is called ONCE, on the SAME backend folder the "
          "patch program was given",
          len(deploys) == 1 and deploys[0]["backend"] == str(backend)
          and deploys[0]["repo"] == str(repo), deploys)
    check("... it changed nothing before the deploy, so nothing was restored over it",
          fake.state["after_patch"] == {name: OLD[name] for name in OLD}
          and (backend / "one.py").read_bytes() == NEW["one.py"],
          fake.state["after_patch"])
    check("... VERSION is written from the installed desktop, as the deploy proved",
          (backend / "VERSION").read_text(encoding="utf-8").strip() == "0.2.487",
          (backend / "VERSION").read_text(encoding="utf-8"))
    check("... the SAME proof suites run against the live folder at the chosen pace",
          len(suites) == 1 and _jobs_of(suites[0]) == 14
          and "--backend-path" in suites[0], [_jobs_of(cmd) for cmd in suites])
    check("... the report names BOTH routes and why the second one ran",
          "the patch stack refused 51 hunk(s) on this install" in tail
          and "deploy route carried the update" in tail
          and "reconcile_live_backend.py" in tail, said[-8:])
    check("... the ROUTE line is printed last, so the card's own tail holds it",
          [line for line in said if line.startswith(U.ROUTE_PREFIX)][-1]
          .startswith(U.ROUTE_PREFIX + "the patch stack refused 51 hunk(s)"),
          said[-3:])
    check("... exactly ONE ROUTE line: the report, not a running commentary",
          sum(1 for line in said if line.startswith(U.ROUTE_PREFIX)) == 1,
          [line for line in said if line.startswith(U.ROUTE_PREFIX)])
    check("... and a proven deploy-route update never reads as problems",
          tail.rfind("ALL DONE - the backend is patched and proven")
          > tail.rfind("DONE WITH PROBLEMS"), said[-4:])
    stored = U.pace_timings(U.load_timings(root / "timings.json"), "responsive")
    check("... the deploy phase's time is recorded as the patch phase's time",
          stored["patch_seconds"] is not None and stored["suites"] != {}, stored)


def t_a_patched_install_never_takes_the_deploy_route():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    deploys = []
    said = []
    code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json",
                    deploy=_deploy_ok(backend, calls=deploys), full_proof=True)
    check("an install the patch stack can apply is UNCHANGED: no deploy route",
          code == 0 and deploys == [], (code, deploys))
    check("... and no ROUTE line is printed for it",
          not any(line.startswith(U.ROUTE_PREFIX) for line in said),
          [line for line in said if "ROUTE" in line])


def t_a_refusal_for_another_reason_is_not_routed_around():
    root = _make_root()
    repo, backend = _make_repo(root)

    def handler(cmd, cwd, on_line, state):
        if _is_patcher(cmd):
            on_line("Jarvis looks like it is still running (pid 42). Close it, "
                    "then run this again (or add -Force).")
            on_line(" DONE WITH PROBLEMS - do not trust this update yet")
            on_line("None of your backend files were changed by this run.")
            return 1
        for name in U.suite_names(repo):
            on_line(f"ok    {name:<34} 0.1s")
        on_line("3 passed, 0 skipped, 0 failed")
        return 0

    deploys = []
    said = []
    code = U.update(repo, backend, "responsive", run=FakeRun(handler),
                    say=said.append, clock=lambda: 0.0,
                    timings_path=root / "timings.json",
                    deploy=_deploy_ok(backend, calls=deploys), full_proof=True)
    check("a refusal the deploy route is not evidence for is reported, not routed",
          code == 1 and deploys == [], (code, deploys))
    check("... with the patch program's own final line and no ROUTE claim",
          any("DONE WITH PROBLEMS" in line for line in said)
          and not any(line.startswith(U.ROUTE_PREFIX) for line in said),
          said[-4:])


def t_a_deploy_route_refusal_is_reported_verbatim_and_claims_nothing():
    root = _make_root()
    repo, backend = _make_repo(root)
    refused_line = ("REFUSED: the working tree is at HEAD attacker but --ref "
                    "deadbeef is other, so this tool will not run from a "
                    "different commit")
    said = []
    code = U.update(repo, backend, "responsive",
                    run=FakeRun(_refusal_then_suites(repo, backend)),
                    say=said.append, clock=lambda: 0.0,
                    timings_path=root / "timings.json",
                    deploy=_deploy_refused(refused_line), full_proof=True)
    tail = "\n".join(said)
    check("a deploy-tool refusal is an honest failure, never a claimed update",
          code == 1 and "ALL DONE" not in tail
          and "DONE WITH PROBLEMS" in tail, (code, said[-5:]))
    check("... the deploy tool's refusal is reported VERBATIM",
          refused_line in tail, [line for line in said if "REFUSED" in line])
    check("... the ROUTE line names both routes and that the deploy did not finish",
          any(line.startswith(U.ROUTE_PREFIX)
              and "the patch stack refused 51 hunk(s)" in line
              and "deploy route did not finish" in line for line in said),
          [line for line in said if line.startswith(U.ROUTE_PREFIX)])
    check("... nothing is written, no VERSION is claimed, and no suite passes for it",
          not (backend / "VERSION").exists()
          and all((backend / name).read_bytes() == OLD[name] for name in OLD),
          {name: (backend / name).read_bytes() for name in OLD})
    for forbidden in ("both halves now match", "the two halves now match",
                      "now match", "IN SYNC"):
        check(f"... and it never says {forbidden!r}",
              forbidden not in tail)


def _deploy_fake_repo(root: Path, *, script: str):
    """A temporary repository + live folder the REAL deploy tool can deploy.

    `repo/.git` only satisfies the deploy tool's "is this a repository" check:
    every blob is supplied by the injected `show`/`resolve_shas` seams, so no
    git object store and no network are needed. The live folder's five patched
    base files are the repository's PUBLISHED BASE copies (`jarvis-backend/`),
    so the deploy tool's literal HUD deltas are already present - the same state
    the owner's deploy-managed install is in, and the state the deploy tool plans
    no delta for.
    """
    repo, backend = _make_repo(root)
    (repo / ".git").mkdir()
    base = HERE.parent / "jarvis-backend"
    for name in R.PATCHED_FILES:
        source = base / name
        target = backend / name
        if source.is_file():
            shutil.copyfile(source, target)
        else:                       # a clone without the published base
            target.write_text(f"# live {name}\n", encoding="utf-8")
    (repo / "scripts" / "apply-patches.ps1").write_text(script, encoding="utf-8")
    return repo, backend


_DEPLOY_SHIFTED = ("--- a/other.txt\n+++ b/other.txt\n@@ -1 +1 @@\n-old\n"
                   "+new\n")
_DEPLOY_BESIDE = {"requirements.lock": b"locked\n",
                  "quiz_grader_cases.json": b"{}\n"}


def _deploy_show(script: str):
    """The ref's blobs for the real deploy tool, served without git."""
    blobs = dict(NEW)
    blobs.update(_DEPLOY_BESIDE)
    blobs["other.patch"] = _DEPLOY_SHIFTED.encode()

    def show(repo, ref, path):
        if path == "scripts/apply-patches.ps1":
            return script.encode()
        if path in blobs:
            return blobs[path]
        raise R.Refused(f"the fixture has no blob for {path}")

    return show


_DEPLOY_SCRIPT = ('$SHIPPED = @(\n  "one.py"\n  "two.py"\n  "jarvis_hud.html"\n'
                  ')\n\n$PATCHES = @(\n  "other.patch"\n)\n')
_DEPLOY_SCRIPT_NO_PATCHES = '$SHIPPED = @(\n  "one.py"\n)\n'


def t_the_deploy_route_really_runs_reconcile_and_proves_its_result():
    root = _make_root()
    repo, backend = _deploy_fake_repo(root, script=_DEPLOY_SCRIPT)
    ref = "a" * 40
    said = []
    report = U.deploy_route(
        repo, backend, say=said.append, module=R, ref=ref,
        show=_deploy_show(_DEPLOY_SCRIPT),
        resolve_shas=lambda repo_arg, ref_arg: (ref_arg, ref_arg),
        version_reader=lambda path: "0.2.487", skip_plugins=True,
        lane_preflight=lambda: None)
    tail = "\n".join(said)
    check("the deploy route runs reconcile's own --apply and succeeds",
          report["ok"] is True and report["code"] == 0, report)
    check("... the live folder really holds the ref's bytes",
          (backend / "one.py").read_bytes() == NEW["one.py"]
          and (backend / "two.py").read_bytes() == NEW["two.py"]
          and (backend / "jarvis_hud.html").read_bytes() == NEW["jarvis_hud.html"],
          (backend / "one.py").read_bytes())
    check("... the shared VERSION marker was written from the installed desktop",
          (backend / "VERSION").read_text(encoding="utf-8") == "0.2.487"
          and report["version"] == "0.2.487", report["version"])
    check("... SOURCE-COMMIT names the deployed commit beside it",
          json.loads((backend / "SOURCE-COMMIT").read_text(encoding="utf-8")
                     )["commit"] == ref
          and report["ref"] == ref, report["ref"])
    check("... the deploy tool's own RESULT: PASS is in the report",
          "RESULT: PASS" in tail, said[-6:])
    check("... the route probes are skipped FOR A STATED REASON, never silently",
          "ROUTE PROBES:" in tail
          and "the backend is stopped for this update" in tail
          and "NOT a route pass" in tail, said[-8:])


def t_the_deploy_route_never_claims_a_marker_it_could_not_prove():
    # The bytes deploy fine; the marker does not match the installed desktop
    # afterwards. That is an honest failure, never "both halves match".
    root = _make_root()
    repo, backend = _deploy_fake_repo(root, script=_DEPLOY_SCRIPT)
    readings = iter(["0.2.487", "0.2.488"])
    said = []
    report = U.deploy_route(
        repo, backend, say=said.append, module=R, ref="a" * 40,
        show=_deploy_show(_DEPLOY_SCRIPT),
        resolve_shas=lambda repo_arg, ref_arg: (ref_arg, ref_arg),
        version_reader=lambda path: next(readings), skip_plugins=True,
        lane_preflight=lambda: None)
    check("a VERSION that does not equal the installed desktop is a FAILURE",
          report["ok"] is False and "0.2.487" in report["why"]
          and "0.2.488" in report["why"], report)
    check("... and it says the two halves are not proved to match",
          "not proved to match" in report["why"], report["why"])

    # The deploy tool refuses before writing: nothing is deployed and the
    # refusal is the tool's own sentence, captured verbatim.
    root2 = _make_root()
    repo2, backend2 = _deploy_fake_repo(root2, script=_DEPLOY_SCRIPT_NO_PATCHES)
    before = {name: (backend2 / name).read_bytes() for name in R.PATCHED_FILES}
    said2 = []
    report2 = U.deploy_route(
        repo2, backend2, say=said2.append, module=R, ref="a" * 40,
        show=_deploy_show(_DEPLOY_SCRIPT_NO_PATCHES),
        resolve_shas=lambda repo_arg, ref_arg: (ref_arg, ref_arg),
        version_reader=lambda path: "0.2.487", skip_plugins=True,
        lane_preflight=lambda: None)
    check("a deploy-tool refusal is a failure with the tool's own REFUSED line",
          report2["ok"] is False and report2["why"].startswith("REFUSED:")
          and "PATCHES" in report2["why"], report2)
    check("... and a refusal writes nothing and claims no marker",
          before == {name: (backend2 / name).read_bytes()
                     for name in R.PATCHED_FILES}
          and not (backend2 / "VERSION").exists(), report2["lines"][-3:])
    check("... with the refusal quoted verbatim in its output",
          any(line.startswith("REFUSED:") for line in report2["lines"])
          and report2["why"] in report2["lines"], report2["lines"][-3:])


def t_the_deploy_route_keeps_the_lock_pace_and_timings():
    root = _make_root()
    repo, backend = _make_repo(root)
    timings = root / "timings.json"
    lock = timings.with_name(U.LOCK_NAME)
    seen = {}

    def deploy(repo_arg, backend_arg, *, say):
        seen["lock_held_during_deploy"] = lock.is_file()
        for name, content in NEW.items():
            (Path(backend_arg) / name).write_bytes(content)
        (Path(backend_arg) / "VERSION").write_bytes(b"0.2.487")
        return {"ok": True, "code": 0, "ref": "b" * 40, "version": "0.2.487",
                "desktop_version": "0.2.487", "why": "", "lines": []}

    fake = FakeRun(_refusal_then_suites(repo, backend))
    said = []
    code = U.update(repo, backend, "safe", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=timings, deploy=deploy, full_proof=True)
    check("the deploy route runs INSIDE the update lock, and the lock is released",
          code == 0 and seen.get("lock_held_during_deploy") is True
          and not lock.exists(), (code, seen, lock.exists()))
    check("... the chosen pace is what the proof suites use (safe = one worker)",
          fake.state.get("suite_jobs") == [1], fake.state.get("suite_jobs"))
    stored = U.pace_timings(U.load_timings(timings), "safe")
    check("... and the deploy phase's own time is recorded for that pace",
          stored["patch_seconds"] is not None and stored["suites"] != {}, stored)


def t_the_deploy_route_s_safe_second_pass_does_not_undo_the_deploy():
    root = _make_root()
    repo, backend = _make_repo(root)
    deploys = []
    fake = FakeRun(_refusal_then_suites(repo, backend, suites_fail_first=True))
    said = []
    code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json",
                    deploy=_deploy_ok(backend, calls=deploys), full_proof=True)
    tail = "\n".join(said)
    check("a failed quick check on the deploy route falls back to one worker",
          code == 0 and "ALL DONE" in tail
          and fake.state.get("suite_jobs") == [14, 1],
          (code, fake.state.get("suite_jobs"), said[-5:]))
    check("... the patch stack is NOT run again (it refused once, and would again)",
          fake.state.get("patcher_calls") == 1, fake.state.get("patcher_calls"))
    check("... the deploy is NOT repeated, because it already proved the bytes",
          len(deploys) == 1, deploys)
    check("... the fallback says nothing is put back, because the files are proved",
          any("nothing is put back" in line for line in said),
          [line for line in said if "safe way" in line][:2])
    check("... and the live files are still the deploy's bytes, never a backup's",
          (backend / "one.py").read_bytes() == NEW["one.py"],
          (backend / "one.py").read_bytes())


def t_an_unproven_deploy_route_update_is_not_reported_as_proved():
    """A deploy that carried the files, on a run whose checks skipped: partial."""
    root = _make_root()
    repo, backend = _make_repo(root)

    def handler(cmd, cwd, on_line, state):
        if _is_patcher(cmd):
            for line in _MEASURED_REFUSAL:
                on_line(line)
            return 1
        for name in U.suite_names(repo):
            if name == "test_b.py":
                on_line("skip  test_b.py  it opens a real, VISIBLE browser window "
                        "(a support chat); set "
                        "JARVIS_ALLOW_VISIBLE_BROWSER_TESTS=1 to run it")
            else:
                on_line(f"ok    {name:<34} 0.1s")
        on_line("2 passed, 0 skipped, 0 failed")
        return 0

    said = []
    code = U.update(repo, backend, "responsive", run=FakeRun(handler),
                    say=said.append, clock=lambda: 0.0,
                    timings_path=root / "timings.json",
                    deploy=_deploy_ok(backend), full_proof=True)
    tail = "\n".join(said)
    check("a deploy-route update with a skipped check is NOT reported as proved",
          code == 0 and "NOT fully proven" in tail and "ALL DONE" not in tail,
          (code, said[-5:]))
    check("... and its ROUTE line says the checks did not prove the whole update",
          any(line.startswith(U.ROUTE_PREFIX)
              and "did not prove the whole update" in line for line in said)
          and not any(line.startswith(U.ROUTE_PREFIX)
                      and "are the proof" in line for line in said),
          [line for line in said if line.startswith(U.ROUTE_PREFIX)])


# ==========================================================================
#   The release's own files reach this PC (2026-11-21, off-peak field test)
# ==========================================================================
#
# The same rule as "both halves updated": a release ships code AND the defaults
# and files the half needs to be usable. Two gaps were measured on the live PC:
# PM2's eight project tools were ON in the published config and absent from the
# owner's own `jarvis-framework.toml`, and the desktop's look spec disagreed with
# the live backend folder's copy on every start. Both steps run AFTER the update
# proves itself, are reported verbatim (`TOOL DEFAULTS:` / `BESIDE:`), and can
# never fail the backend update.

SHIPPED_TOML = ('[tools]\n'
                'enabled = ["calculator", "new_tool", "old_tool"]\n\n'
                '[voice]\nenabled = true\n')
PREVIOUS_TOML = '[tools]\nenabled = ["calculator", "old_tool"]\n'


def _tool_defaults_fixture(root: Path):
    """(repo, backend, live config): a release that newly ships `new_tool`."""
    repo, backend = _make_repo(root)
    (repo / U.BASE_REL).mkdir(parents=True, exist_ok=True)
    (repo / U.BASE_REL / U.FRAMEWORK_NAME).write_text(SHIPPED_TOML, encoding="utf-8")
    live = backend / U.FRAMEWORK_NAME
    live.write_text('# the owner\'s own settings\n[voice]\nenabled = true\n\n'
                    '[tools]\nenabled = ["calculator"]\n', encoding="utf-8")
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / U.NEW_TOOLS_TOOL_REL).write_text(
        "# the release's additive tool writer; its real suite is "
        "backend/test_enable_new_tools.py\n", encoding="utf-8")
    return repo, backend, live


def t_a_newly_shipped_tool_reaches_the_config_and_an_owner_removed_tool_stays():
    root = _make_root()
    repo, backend, live = _tool_defaults_fixture(root)
    said, calls = [], []

    def fake_git_show(repo_arg, ref, path):
        if ref != "7add1b7c1d5f":
            return None, f"git show of {ref} exited 128 (bad object)"
        return PREVIOUS_TOML, ""

    def fake_run(cmd, cwd, on_line):
        calls.append([str(part) for part in cmd])
        if not any(str(part).endswith("enable_new_tools.py") for part in cmd):
            return 1
        # The real tool's contract: write ONLY the names it was given.
        names = cmd[cmd.index("--add") + 1].split(",")
        current = U.framework_tool_defaults_in(live)[0] or []
        merged = current + [name for name in names if name not in current]
        live.write_text('[tools]\nenabled = ['
                        + ", ".join(f'"{name}"' for name in merged) + ']\n',
                        encoding="utf-8")
        on_line("would add 1 tool(s) to the owner's config: " + ", ".join(names))
        on_line("added 1 tool(s); backup at jarvis-framework.toml.before-enable-tools-x")
        return 0

    report = U.enable_new_tool_defaults(repo, backend, "7add1b7c1d5f",
                                        say=said.append, run=fake_run,
                                        git_show=fake_git_show)
    now = U.framework_tool_defaults_in(live)[0]
    check("a tool the release NEWLY ships ON reaches the owner's config",
          report["ok"] is True and report["added"] == ["new_tool"]
          and now is not None and "new_tool" in now, (report, now))
    check("... and a tool the owner turned off is NOT re-enabled (it shipped at the "
          "baseline too, so it is never named)",
          "old_tool" not in now and report["added"] == ["new_tool"],
          (now, report["added"]))
    check("... the writer is called ONCE with exactly the new name and --apply",
          len(calls) == 1
          and calls[0][calls[0].index("--add") + 1] == "new_tool"
          and "--apply" in calls[0], calls)
    check("... the report names the baseline commit and the new tool",
          any("baseline: the shipped tool defaults at 7add1b7c1d5f" in line
              for line in said)
          and any("newly ships these tools on: new_tool" in line for line in said),
          said)
    check("... and relays the writer's own lines verbatim under its prefix",
          any(line.startswith("TOOL DEFAULTS: added 1 tool(s); backup at")
              for line in said), said)

    # A second run is the no-op the update path relies on.
    said_second, calls_second = [], []
    report_second = U.enable_new_tool_defaults(
        repo, backend, "7add1b7c1d5f", say=said_second.append,
        run=lambda cmd, cwd, on_line: calls_second.append(cmd) or 0,
        git_show=fake_git_show)
    check("a second run adds nothing and starts no writer",
          report_second["ok"] is True and report_second["invoked"] is False
          and report_second["added"] == [] and calls_second == []
          and any("nothing to add" in line for line in said_second),
          (report_second, calls_second, said_second))


def t_a_legacy_missing_tool_is_never_added_from_absence_alone():
    # Exactly PM2's eight were shipped before the owner's previous desktop build:
    # the automatic rule cannot know them, and "absent from the live list and
    # present in shipped" is how a deliberate OFF would be flipped back ON.
    root = _make_root()
    repo, backend, live = _tool_defaults_fixture(root)
    (repo / U.BASE_REL / U.FRAMEWORK_NAME).write_text(
        '[tools]\nenabled = ["calculator", "legacy_tool"]\n', encoding="utf-8")
    said, calls = [], []
    report = U.enable_new_tool_defaults(
        repo, backend, "7add1b7c1d5f", say=said.append,
        run=lambda cmd, cwd, on_line: calls.append(cmd) or 0,
        git_show=lambda repo_arg, ref, path: (
            '[tools]\nenabled = ["calculator", "legacy_tool"]\n', ""))
    check("a tool merely ABSENT from the live list is never added by itself",
          report["ok"] is True and report["added"] == [] and calls == [],
          (report, calls))
    check("... and the report says this release ships nothing new, in that order",
          any("ships no tool that the release before this update did not already "
              "ship on" in line for line in said), said)
    check("... while the owner's live list is left exactly as it was",
          U.framework_tool_defaults_in(live)[0] == ["calculator"],
          U.framework_tool_defaults_in(live))


def t_a_missing_or_unreadable_baseline_is_reported_not_guessed():
    root = _make_root()
    repo, backend, live = _tool_defaults_fixture(root)

    def missing(repo_arg, ref, path):
        return None, "git show of deadbee exited 128 (bad object)"

    said, calls = [], []
    report = U.enable_new_tool_defaults(repo, backend, "deadbee",
                                        say=said.append,
                                        run=lambda cmd, cwd, on_line: calls.append(cmd) or 0,
                                        git_show=missing)
    check("a baseline commit this clone does not have refuses the add, naming it",
          report["ok"] is False and "deadbee" in report["why"]
          and any("could not be read" in line and "deadbee" in line for line in said),
          (report["why"], said))
    check("... and NOTHING is written or run",
          calls == [] and U.framework_tool_defaults_in(live)[0] == ["calculator"],
          (calls, U.framework_tool_defaults_in(live)))

    # A build that recorded no commit cannot name the previous release at all.
    said_none = []
    report_none = U.enable_new_tool_defaults(repo, backend, None,
                                             say=said_none.append,
                                             run=lambda cmd, cwd, on_line: 0)
    check("a build with no recorded commit says exactly that and adds nothing",
          report_none["ok"] is False
          and "does not record which commit" in report_none["why"], report_none)


def t_the_config_step_missing_from_a_release_is_reported_and_never_fatal():
    root = _make_root()
    repo, backend, live = _tool_defaults_fixture(root)
    (repo / U.NEW_TOOLS_TOOL_REL).unlink()          # a release before the writer
    said = []
    report = U.enable_new_tool_defaults(
        repo, backend, "7add1b7c1d5f", say=said.append,
        git_show=lambda repo_arg, ref, path: (PREVIOUS_TOML, ""))
    check("a release without the config step says the step is not in it",
          report["ok"] is False and "not in this release" in report["why"]
          and any("not in this release" in line for line in said),
          (report, said))
    check("... names the tools that therefore were NOT enabled",
          any("new_tool" in line and "NOT enabled" in line for line in said), said)

    # And the whole update still ends as a proven backend update.
    repo2, backend2 = _make_repo(root / "second")
    fake = FakeRun(_staged_handler(repo2, backend2, suites="ok"))
    said2 = []
    code = U.update(repo2, backend2, "safe", run=fake, say=said2.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json",
                    previous_release="7add1b7c1d5f", full_proof=True)
    check("... and a failed/reported config step never fails the backend update",
          code == 0 and any(line.startswith("TOOL DEFAULTS:") for line in said2),
          (code, [line for line in said2 if line.startswith("TOOL DEFAULTS:")]))


SPEC_OLD = {"version": 1, "palette": {"ink": "#111111", "paper": "#fafafa"}}
SPEC_NEW = {"version": 1, "palette": {"ink": "#111111", "paper": "#fafafa"},
            "faces": {"robot": {"eyes": "round"}}}


def _spec_fixture(root: Path, *, shipped=SPEC_NEW, live=SPEC_OLD):
    """(repo, backend, shipped path, live path) with real files on disk."""
    repo, backend = _make_repo(root)
    shipped_path = repo / U.VISUAL_SPEC_REL
    shipped_path.write_text(json.dumps(shipped, indent=1) + "\n", encoding="utf-8")
    live_path = backend / U.VISUAL_SPEC_NAME
    if live is not None:
        live_path.write_text(json.dumps(live, indent=1) + "\n", encoding="utf-8")
    return repo, backend, shipped_path, live_path


def t_the_release_s_look_spec_is_delivered_and_the_desktop_warning_disappears():
    root = _make_root()
    repo, backend, shipped_path, live_path = _spec_fixture(root)
    old = live_path.read_bytes()
    said = []
    report = U.deliver_visual_spec(repo, backend, say=said.append)
    written = live_path.read_bytes()
    backups = list(backend.glob(U.VISUAL_SPEC_NAME + ".before-visual-spec-*"))
    check("the release's look spec is written into the live backend folder",
          report["ok"] is True and report["wrote"] is True
          and written == shipped_path.read_bytes(), (report, len(written)))
    check("... which is EXACTLY what the desktop's drift check compares (parsed "
          "structure equals), so its disagreement warning has nothing left to say",
          json.loads(written) == json.loads(shipped_path.read_text(encoding="utf-8")),
          "the served copy is not the release's")
    check("... the old copy is backed up beside it, byte for byte",
          len(backups) == 1 and backups[0].read_bytes() == old, backups)
    check("... and the report carries one BESIDE: line naming what was written",
          any(line.startswith("BESIDE: " + U.VISUAL_SPEC_NAME) and "wrote" in line
              for line in said), said)

    said_second = []
    backups_before = set(backend.glob(U.VISUAL_SPEC_NAME + ".before-visual-spec-*"))
    report_second = U.deliver_visual_spec(repo, backend, say=said_second.append)
    backups_after = set(backend.glob(U.VISUAL_SPEC_NAME + ".before-visual-spec-*"))
    check("a second run is a no-op: identical copy, no second backup, no write",
          report_second["ok"] is True and report_second["wrote"] is False
          and backups_after == backups_before
          and any("unchanged" in line for line in said_second),
          (report_second, said_second))


def t_an_identical_or_formatting_only_look_spec_is_not_rewritten():
    root = _make_root()
    repo, backend, shipped_path, live_path = _spec_fixture(root)
    live_path.write_bytes(shipped_path.read_bytes())
    before = live_path.read_bytes()
    said = []
    report = U.deliver_visual_spec(repo, backend, say=said.append)
    check("an identical look spec is reported unchanged, not rewritten",
          report["wrote"] is False and live_path.read_bytes() == before
          and any("unchanged" in line for line in said), (report, said))
    check("... and no backup is made for a file it did not touch",
          not list(backend.glob(U.VISUAL_SPEC_NAME + ".before-visual-spec-*")))

    # The desktop compares STRUCTURE, so whitespace/key order is not a difference.
    live_path.write_text(json.dumps(SPEC_NEW, sort_keys=True), encoding="utf-8")
    said_order = []
    report_order = U.deliver_visual_spec(repo, backend, say=said_order.append)
    check("... and a copy that differs only in formatting is the same look spec",
          report_order["wrote"] is False
          and any("only formatting differs" in line for line in said_order),
          (report_order, said_order))


def t_a_look_spec_that_cannot_be_read_is_reported_and_nothing_is_written():
    root = _make_root()
    repo, backend, shipped_path, live_path = _spec_fixture(root)
    before = live_path.read_bytes()

    shipped_path.unlink()
    said = []
    report = U.deliver_visual_spec(repo, backend, say=said.append)
    check("a missing release copy is reported, nothing written",
          report["ok"] is False and report["wrote"] is False
          and live_path.read_bytes() == before
          and any("could not be read" in line and "NOT delivered" in line
                  for line in said), (report, said))

    shipped_path.write_text("{ not json", encoding="utf-8")
    said_bad = []
    report_bad = U.deliver_visual_spec(repo, backend, say=said_bad.append)
    check("a release copy that is not JSON is reported, nothing written",
          report_bad["ok"] is False and live_path.read_bytes() == before
          and any("not readable JSON" in line for line in said_bad),
          (report_bad, said_bad))
    shipped_path.write_text(json.dumps(SPEC_NEW), encoding="utf-8")
    # An unreadable LIVE copy (a directory where the file should be) is refused
    # rather than guessed at, and the release's copy is not written over it.
    live_path.unlink()
    live_path.mkdir()
    said_live = []
    report_live = U.deliver_visual_spec(repo, backend, say=said_live.append)
    check("an unreadable live copy is reported, nothing written",
          report_live["ok"] is False and report_live["wrote"] is False
          and any("live copy" in line and "could not be read" in line
                  for line in said_live), (report_live, said_live))


def t_the_look_spec_runs_with_the_file_half_and_the_config_step_only_after_proof():
    # THE MEASURED 2026-11-21 RUN. The auto-finish started at 11:08:54Z, the
    # deploy route wrote VERSION 0.2.488 and SOURCE-COMMIT d7003442e, and the
    # proof suites then legitimately ran ~57+ minutes. The desktop's one-hour
    # wall clock ended the run at 12:08:54Z, so the release's look spec was
    # never delivered and every start still said it DISAGREED. The spec now goes
    # with the FILE half (step 2b), before the suites; the config defaults still
    # need the whole proof, because they change the owner's own config.
    root = _make_root()
    repo, backend = _make_repo(root)
    ran = []
    at_first_suite = []

    def fake_beside(repo_arg, backend_arg, previous, *, say):
        ran.append("beside")
        say("BESIDE: jarvis-visual-spec.json unchanged")

    def fake_tools(repo_arg, backend_arg, previous, *, say):
        ran.append("tools")
        say("TOOL DEFAULTS: nothing to add")

    def handler(cmd, cwd, on_line, state):
        if _is_patcher(cmd):
            for name, content in NEW.items():
                (backend / name).write_bytes(content)
            on_line("DONE - no problems, but NOT fully proven (see below)")
            return 0
        at_first_suite.append(list(ran))
        for name in U.suite_names(repo):
            on_line(f"ok    {name:<34} 0.1s")
        on_line("3 passed, 0 skipped, 0 failed")
        return 0

    said = []
    code = U.update(repo, backend, "responsive", run=FakeRun(handler),
                    say=said.append, clock=lambda: 0.0,
                    timings_path=root / "timings.json",
                    previous_release="7add1b7c1d5f",
                    tool_defaults=fake_tools, beside_files=fake_beside, full_proof=True)
    check("after a PROVEN update both release-step kinds run, with the baseline",
          code == 0 and ran == ["beside", "tools"], (code, ran))
    check("... the look spec is delivered BEFORE the first proof suite runs",
          at_first_suite == [["beside"]], at_first_suite)
    check("... and both report lines are in the run's own output",
          sum("BESIDE:" in line for line in said) == 1
          and sum("TOOL DEFAULTS:" in line for line in said) == 1, said[-6:])

    # An UNPROVEN update (a skipped check) is still an applied file half: the
    # spec is delivered, the config step is not - exactly the rule "content,
    # not proof".
    root2 = _make_root()
    repo2, backend2 = _make_repo(root2)
    ran2 = []

    def fake_beside2(repo_arg, backend_arg, previous, *, say):
        ran2.append("beside")

    def fake_tools2(repo_arg, backend_arg, previous, *, say):
        ran2.append("tools")

    code2 = U.update(repo2, backend2, "safe",
                     run=FakeRun(_staged_handler(repo2, backend2,
                                                 suites="visible-browser-skip")),
                     say=lambda line: None, clock=lambda: 0.0,
                     timings_path=root2 / "timings.json",
                     previous_release="7add1b7c1d5f",
                     tool_defaults=fake_tools2, beside_files=fake_beside2, full_proof=True)
    check("an UNPROVEN update still delivers the look spec, and changes no config",
          code2 == 0 and ran2 == ["beside"], (code2, ran2))

    # A run that never gets past the route (here: a non-deploy-shape refusal,
    # nothing changed) fails BEFORE the file half is proved, so neither step
    # runs and the owner's config and spec are untouched.
    root3 = _make_root()
    repo3, backend3 = _make_repo(root3)
    ran3 = []

    def handler3(cmd, cwd, on_line, state):
        if _is_patcher(cmd):
            on_line("Jarvis looks like it is still running (pid 42). Close it, "
                    "then run this again (or add -Force).")
            on_line(" DONE WITH PROBLEMS - do not trust this update yet")
            on_line("None of your backend files were changed by this run.")
            return 1
        on_line("FAIL  test_b.py  0.1s  (exit 1)")
        on_line("2 passed, 0 skipped, 1 failed")
        return 1

    code3 = U.update(repo3, backend3, "safe", run=FakeRun(handler3),
                     say=lambda line: None, clock=lambda: 0.0,
                     timings_path=root3 / "timings.json",
                     previous_release="7add1b7c1d5f",
                     tool_defaults=lambda *a, **k: ran3.append("tools"),
                     beside_files=lambda *a, **k: ran3.append("beside"), full_proof=True)
    check("a run that never proved its files never runs the release-file steps",
          code3 == 1 and ran3 == [], (code3, ran3))


def t_the_look_spec_reaches_the_live_folder_even_when_the_proof_never_finishes():
    # The measured incident, end to end and with the REAL delivery step: the
    # deploy route carries the file half (VERSION written, bytes proved) and
    # then the proof suites never finish - the desktop's bound ends the run.
    # The owner must still be left with the release's look spec, and the run's
    # report must say so.
    root = _make_root()
    repo, backend = _make_repo(root)
    seen = {}

    def handler(cmd, cwd, on_line, _state):
        if _is_patcher(cmd):
            for line in _MEASURED_REFUSAL:
                on_line(line)
            return 1
        # The suite phase never finishes: an ambiguous runner on every pass,
        # which is exactly what the desktop's bound does to this tool (its
        # output stops and the app ends it), from this side of the pipe.
        seen.setdefault(
            "spec_at_first_suite",
            (backend / U.VISUAL_SPEC_NAME).exists()
            and (backend / U.VISUAL_SPEC_NAME).read_bytes()
            == (repo / U.VISUAL_SPEC_REL).read_bytes())
        on_line("ok    test_a.py                       0.1s")
        return None

    said = []
    code = U.update(repo, backend, "responsive", run=FakeRun(handler),
                    say=said.append, clock=lambda: 0.0,
                    timings_path=root / "timings.json",
                    deploy=_deploy_ok(backend, version="0.2.487"), full_proof=True)
    tail = "\n".join(said)
    check("a proof phase that never finishes is still an honest failed update",
          code == 1 and "DONE WITH PROBLEMS" in tail, (code, said[-5:]))
    check("... and the release's look spec was already delivered BEFORE the "
          "first proof suite, while the file half was proved",
          seen.get("spec_at_first_suite") is True, seen)
    check("... the live copy really is the release's own spec",
          (backend / U.VISUAL_SPEC_NAME).read_bytes()
          == (repo / U.VISUAL_SPEC_REL).read_bytes(),
          (backend / U.VISUAL_SPEC_NAME).read_bytes()[:40])
    check("... and the run report carries one verbatim BESIDE: line saying what "
          "reached the PC",
          sum(1 for line in said if line.startswith("BESIDE: ")) == 1
          and any(line.startswith("BESIDE: ") and "wrote" in line
                  and U.VISUAL_SPEC_NAME in line for line in said),
          [line for line in said if line.startswith("BESIDE: ")])

    # A deploy that never proved the bytes/markers is the other direction: the
    # spec must NOT be delivered then - the file half is not proved, so nothing
    # the release owns is written on a claim.
    root2 = _make_root()
    repo2, backend2 = _make_repo(root2)
    before = (repo2 / U.VISUAL_SPEC_REL).read_bytes()
    said2 = []
    refused = ("REFUSED: the working tree is at HEAD attacker but --ref deadbeef "
               "is other")
    code2 = U.update(repo2, backend2, "responsive",
                     run=FakeRun(_refusal_then_suites(repo2, backend2)),
                     say=said2.append, clock=lambda: 0.0,
                     timings_path=root2 / "timings.json",
                     deploy=_deploy_refused(refused), full_proof=True)
    check("a deploy that did not prove its bytes+markers delivers no look spec",
          code2 == 1
          and not (backend2 / U.VISUAL_SPEC_NAME).exists()
          and not any(line.startswith("BESIDE:") for line in said2),
          (code2, [line for line in said2 if line.startswith("BESIDE:")]))
    check("... and the release's own spec is untouched",
          (repo2 / U.VISUAL_SPEC_REL).read_bytes() == before)


def t_a_look_spec_that_cannot_be_delivered_never_fails_the_update():
    # The step is content, not proof: a program folder whose desktop spec cannot
    # be read still finishes the backend half, and says which read failed.
    root = _make_root()
    repo, backend = _make_repo(root)
    (repo / U.VISUAL_SPEC_REL).unlink()
    said = []
    code = U.update(repo, backend, "responsive",
                    run=FakeRun(_staged_handler(repo, backend, suites="ok")),
                    say=said.append, clock=lambda: 0.0,
                    timings_path=root / "timings.json", full_proof=True)
    tail = "\n".join(said)
    check("an undeliverable look spec leaves a PROVEN backend update proven",
          code == 0 and "ALL DONE - the backend is patched and proven" in tail,
          (code, said[-5:]))
    check("... and says exactly which read failed, verbatim",
          any(line.startswith("BESIDE: ")
              and "NOT delivered" in line and "could not be read" in line
              for line in said), [line for line in said if line.startswith("BESIDE:")])


def t_the_tool_lines_its_own_printout_so_the_desktop_sees_progress():
    # The desktop's progress bound tells a working run from a wedged one by
    # whether the run's log is still growing, so this tool's own printout is
    # line-buffered. The helper must never break a run on a stream it cannot
    # reconfigure (a test capture, an old Python).
    class NoReconfigure:
        def write(self, _text):
            pass

        def flush(self):
            pass

    real = sys.stdout
    sys.stdout = NoReconfigure()
    try:
        U.line_buffered_stdout()          # a stream with no reconfigure: no crash
    finally:
        sys.stdout = real
    check("line buffering never breaks an update on a stream it cannot reconfigure",
          True)
    with redirect_stdout(io.StringIO()) as captured:
        U.line_buffered_stdout()
        print("one complete line")
    check("... and a real capture still receives whole lines",
          captured.getvalue() == "one complete line\n", captured.getvalue())


# ==========================================================================
#   The bounded post-update proof (Gemini rulings 5.1/5.2, 2026-11-21)
# ==========================================================================
#
# THE RULING. The in-app auto-finish and the press path both run this tool, and
# both must finish in minutes: the proof stage is a BOUNDED post-update smoke +
# invariant subset (module imports + py_compile, the live HUD's /api/version +
# /api/status + /api/presets, look-spec agreement, gate/egress/reconcile/projects
# smoke checks), not the ~48-65-minute full suite list. `--full-proof` keeps the
# full sweep for a manual developer run. While the subset runs the Updates card
# gets `PROOF: Step N/4 - <phase> - x of y` lines (ruling 5.2), with the existing
# five-minute heartbeat underneath for a quiet stretch.
#
# EVERY CHECK HERE FAILS ON THE TREE BEFORE THIS CHANGE: the bounded proof, its
# plan, the flag, the phase lines and the honest ending did not exist.
#
# ONE HONEST LIMIT, SAID HERE RATHER THAN DISCOVERED LATER: the Rust app still
# reads its "proven" verdict off the words "patched and proven", so the bounded
# ending keeps that phrase - and then says, in the same sentence, that this is
# the bounded subset and not the full suite. The desktop's card/verdict wording
# is another lane's file (`backend_update.rs` was not edited here).

BOUNDED_INPROCESS_CHECKS = ("compile_shipped_modules", "probe_live_hud",
                            "look_spec_agreement", "live_config_reads")


@contextmanager
def _fake_proof_checks(*, fail=None, calls=None):
    """Fake the bounded proof's in-process checks; the heavy ones never run.

    The child-command checks (the import-all command, the egress census and the
    three invariant suites) still go through the injected `run`, so their real
    commands are driven; these five are the heavy in-process ones, and a fake
    for each is what "each bounded check's command named and run with fakes for
    the heavy ones" means. Every fake records its name in `calls`.
    """
    originals = {name: getattr(U, name) for name in BOUNDED_INPROCESS_CHECKS}

    def fake_for(name):
        def fake(*args, **kwargs):
            if calls is not None:
                calls.append(name)
            ok = fail != name
            return {"ok": ok, "why": "" if ok else "the fixture refused this check",
                    "failed": [], "checked": 1, "answered": 3, "total": 3,
                    "routes": {}, "tools": 1, "same": "bytes"}

        return fake

    try:
        for name in originals:
            setattr(U, name, fake_for(name))
        yield calls
    finally:
        for name, fn in originals.items():
            setattr(U, name, fn)


def _bounded_handler(repo: Path, backend: Path, *, patch=True):
    """A fake runner for the bounded app path, and nothing else.

    It answers exactly the commands the bounded proof names - the patcher (only
    when this fixture is a legacy patch-only install), the import-all child, the
    egress census and `run_suites.py <one suite>` - and raises on anything else,
    so a bounded run that started a full sweep or an unknown program fails the
    test rather than passing by accident.
    """
    def handler(cmd, cwd, on_line, state):
        argv = [str(part) for part in cmd]
        if _is_patcher(cmd):
            state["patcher_calls"] = state.get("patcher_calls", 0) + 1
            if not patch:
                raise AssertionError(
                    "the patch stack must NOT run on a deploy-managed install")
            stamp = "2026-11-21-000001"
            backup = backend / f"_jarvis-backup-{stamp}"
            backup.mkdir(parents=True, exist_ok=True)
            for name in OLD:
                (backup / name).write_bytes((backend / name).read_bytes())
            for name, content in NEW.items():
                (backend / name).write_bytes(content)
            on_line("Rehearsing all 2 on a copy first.")
            on_line("  ok           a.patch")
            on_line("DONE - no problems, but NOT fully proven (see below)")
            return 0
        state.setdefault("commands", []).append(argv)
        if any(part.endswith("run_suites.py") for part in argv):
            state.setdefault("suite_commands", []).append(argv)
            named = [part for part in argv if part.startswith("test_")
                     and part.endswith(".py")]
            if not named:
                raise AssertionError(
                    "the bounded proof must never start the full sweep: " + repr(argv))
            name = named[-1]
            state.setdefault("suite_names", []).append(name)
            on_line(f"ok    {name:<34} 0.1s")
            on_line("1 passed, 0 skipped, 0 failed")
            return 0
        if "-c" in argv and U.PROOF_IMPORT_SOURCE in argv:
            state["import_calls"] = state.get("import_calls", 0) + 1
            on_line("imported 3 of 3 shipped modules from the fixture backend")
            return 0
        if any(part.endswith("check_egress_gate.py") for part in argv):
            state["egress_calls"] = state.get("egress_calls", 0) + 1
            on_line("ok every outbound host mention is accounted for")
            return 0
        raise AssertionError(
            "the bounded proof started an unknown command: " + repr(argv[:4]))

    return handler


def _mark_deploy_managed(backend: Path, *, commit="d7003442e", backups=1) -> None:
    """The two pieces of evidence the deploy tool writes, and nothing else."""
    (Path(backend) / "VERSION").write_bytes(b"0.2.491")
    (Path(backend) / U.SOURCE_COMMIT_NAME).write_text(
        json.dumps({"commit": commit}) + "\n", encoding="utf-8")
    for index in range(backups):
        (Path(backend) / f"{U.DEPLOY_BACKUP_PREFIX}2026-11-21-00000{index}"
         ).mkdir(parents=True, exist_ok=True)


#: The leaves `_mark_deploy_manifest` records: the fixture's three shipped files,
#: the patched base file the deploy writes deltas into, and the two release
#: markers beside them. `jarvis_hud.py` is deliberately in it - it has no
#: `jarvis-backend/` twin, so only the manifest can prove its bytes.
MANIFEST_LEAVES = ("one.py", "two.py", "jarvis_hud.html", "jarvis_hud.py",
                   "VERSION", "SOURCE-COMMIT")


def _mark_deploy_manifest(backend: Path, *, commit="a" * 40,
                          version="0.2.491", names=MANIFEST_LEAVES) -> Path:
    """A live folder carrying the deploy tool's own content-hash manifest (ruling 4).

    Built through the REAL deploy tool's `build_deploy_manifest`, so the fixture
    and the writer cannot drift: the tests below prove what the deploy tool would
    have written, not a copy of its format.
    """
    backend = Path(backend)
    (backend / "VERSION").write_bytes(version.encode("utf-8"))
    (backend / U.SOURCE_COMMIT_NAME).write_text(json.dumps(
        {"schema": R.SOURCE_COMMIT_SCHEMA, "commit": commit,
         "ref": "origin/main", "version": version}) + "\n", encoding="utf-8")
    files = {}
    for leaf in names:
        data = (backend / leaf).read_bytes()
        files[leaf] = {"size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}
    path = backend / U.DEPLOY_MANIFEST_NAME
    path.write_bytes(R.build_deploy_manifest(commit, version, files))
    return path


def t_the_bounded_proof_is_named_and_runs_the_required_real_commands():
    root = _make_root()
    repo, backend = _make_repo(root)
    plan = U.bounded_proof_plan(repo, backend)
    by_id = {row["id"]: row for row in plan}
    ids = [row["id"] for row in plan]
    check("the bounded proof has the four real phases, in the card's order",
          [phase["name"] for phase in U.BOUNDED_PROOF_PHASES]
          == ["module imports", "instant API answers", "core invariants",
              "look spec & config"], U.BOUNDED_PROOF_PHASES)
    check("... and every check names one of them",
          all(0 <= row["phase"] < len(U.BOUNDED_PROOF_PHASES) for row in plan))
    check("the subset starts with py_compile and the shipped-module imports",
          ids[:2] == ["py_compile", "imports"], ids)
    check("... checks the live HUD's three instant routes", "live_hud" in ids)
    check("... runs the gate/egress/reconcile/projects smoke checks",
          {"egress", "gate_egress", "reconcile_live_backend", "projects"}
          <= set(ids), ids)
    check("... and proves the look spec and the live config",
          {"look_spec", "config"} <= set(ids), ids)
    import_command = by_id["imports"]["command"]
    check("the import check is ONE real command: python -B -c <import-all> <live> <names>",
          import_command[:3] == [sys.executable, "-B", "-c"]
          and import_command[3] == U.PROOF_IMPORT_SOURCE
          and import_command[4] == str(backend), import_command[:4])
    check("... naming every module this repository ships whole, and no beside-file",
          json.loads(import_command[-1]) == ["one", "two", "jarvis_gate"],
          json.loads(import_command[-1]))
    check("the egress smoke check is the existing census tool",
          Path(by_id["egress"]["command"][-1]).name == "check_egress_gate.py",
          by_id["egress"]["command"])
    for suite in U.BOUNDED_INVARIANT_SUITES:
        row = by_id[suite[len("test_"):-len(".py")]]
        check(f"the {suite} smoke check runs through the real suite runner",
              any(str(part).endswith("run_suites.py") for part in row["command"])
              and suite in row["command"]
              and U.LOCK_BYPASS_FLAG in row["command"], row["command"])
        # MEASURED 2026-11-21: in live mode two of these suites fail on a healthy
        # install because the live folder is a PATCHED DEPLOYMENT, not the
        # repository's tree. The suites are therefore STAGED from this update's
        # own copy (as CI runs them); the live folder is proven by the deploy
        # route's own bytes-and-markers check and by the checks that read it
        # directly. A plan that passes --backend-path is back to proving the
        # patched deployment with the repository's words, which reported 7/9 on
        # an update that was genuinely installed.
        check(f"the {suite} smoke check is STAGED (no --backend-path): the live "
              f"folder is a patched deployment, proven by the deploy route's own "
              f"bytes check",
              "--backend-path" not in row["command"], row["command"])
    check("the bounded plan is 9 checks in 4 phases (2/1/4/2)",
          [sum(1 for row in plan if row["phase"] == index) for index in range(4)]
          == [2, 1, 4, 2] and len(plan) == 9,
          [sum(1 for row in plan if row["phase"] == index) for index in range(4)])


def t_the_app_path_runs_the_bounded_proof_and_never_the_full_sweep():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_bounded_handler(repo, backend))
    calls = []
    said = []
    with _fake_proof_checks(calls=calls):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json")
    tail = "\n".join(said)
    check("the app path finishes on the bounded proof", code == 0, (code, said[-8:]))
    check("... every in-process check ran exactly once, with its fake",
          calls == list(BOUNDED_INPROCESS_CHECKS), calls)
    check("... the invariant smoke checks are the three named real suites",
          fake.state.get("suite_names") == list(U.BOUNDED_INVARIANT_SUITES),
          fake.state.get("suite_names"))
    check("... the import-all child ran once, with the shipped module names",
          fake.state.get("import_calls") == 1, fake.state.get("import_calls"))
    check("... and the egress census ran once",
          fake.state.get("egress_calls") == 1, fake.state.get("egress_calls"))
    full = [cmd for cmd in fake.state.get("suite_commands", [])
            if not any(part.startswith("test_") for part in cmd)]
    check("... and the FULL suite sweep (a run_suites call naming no suite) "
          "was never started", full == [], full)
    check("... the four phases each printed their PROOF: Step line",
          all(f"PROOF: Step {index}/4 - {phase['name']}" in tail
              for index, phase in enumerate(U.BOUNDED_PROOF_PHASES, 1)))
    check("... the ending claims the BOUNDED checks by number, never the full check",
          "ALL DONE - the backend is patched and proven by the bounded checks "
          "(9 of 9): a subset, not the full suite." in tail, said[-4:])
    check("... and the exact full-sweep ending was NOT printed",
          "ALL DONE - the backend is patched and proven" not in
          [line.strip() for line in said],
          [line for line in said if line.startswith("ALL DONE")])
    check("... the ending names the developer flag that runs the full sweep",
          "--full-proof" in tail)
    check("... and no hour-scale ETA is claimed for a bounded run",
          "Estimated from the times recorded on this PC" not in tail
          and "First run: no times recorded on this PC yet" not in tail, said[:8])


def t_the_full_sweep_runs_only_with_the_developer_flag():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    said = []
    code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                    clock=lambda: 0.0, timings_path=root / "timings.json",
                    full_proof=True)
    tail = "\n".join(said)
    check("--full-proof still runs the FULL suite list, at the chosen pace",
          code == 0 and fake.state.get("suite_calls") == 1
          and fake.state.get("suite_jobs") == [14],
          (code, fake.state.get("suite_calls"), fake.state.get("suite_jobs")))
    check("... and its ending is the full-sweep line, unchanged",
          "ALL DONE - the backend is patched and proven" in tail, said[-4:])
    check("... no bounded subset is run in full-proof mode",
          "PROOF: Step " not in tail and "bounded checks" not in tail)
    check("... and its plan still carries the measured/unmeasured ETA words",
          "Estimated from the times recorded on this PC" in tail
          or "First run: no times recorded on this PC yet" in tail, said[:10])
    parsed = U.parse_args(["--repo", "r", "--backend", "b", "--full-proof"])
    check("the command line flag is --full-proof", parsed["full_proof"] is True)
    check("... and it is OFF on the app path unless a developer asks",
          U.parse_args(["--repo", "r", "--backend", "b"])["full_proof"] is False)
    check("... and the usage line names it", "--full-proof" in U._usage())


def t_the_bounded_proof_prints_the_card_s_step_lines_per_phase():
    import re as _re
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_bounded_handler(repo, backend))
    said = []
    with _fake_proof_checks():
        result = U.bounded_proof(repo, backend, say=said.append, run=fake,
                                 clock=lambda: 0.0)
    pattern = _re.compile(
        r"^PROOF: Step (\d)/4 - (module imports|instant API answers|"
        r"core invariants|look spec & config) - (\d+) of (\d+)$")
    step_lines = [line for line in said if line.startswith(U.PROOF_STEP_PREFIX)]
    parsed = [pattern.match(line) for line in step_lines]
    check("the bounded proof passed every check", result["ok"] is True
          and result["passed"] == result["total"] == 9, result)
    check("every PROOF line is the card's exact shape, with four phases",
          len(step_lines) == 13 and all(parsed), step_lines)
    order = ["module imports", "instant API answers", "core invariants",
             "look spec & config"]
    phases = [match.group(2) for match in parsed]
    check("... the four real phases, in order", phases ==
          [name for name in order for _ in range(
              sum(1 for match in parsed if match.group(2) == name))], phases)
    for name in order:
        rows = [match for match in parsed if match.group(2) == name]
        check(f"... {name!r} opens at 0 of N and closes at N of N",
              rows[0].group(3) == "0" and rows[0].group(4) == str(len(rows) - 1)
              and rows[-1].group(3) == rows[-1].group(4), [m.groups() for m in rows])
    check("... the phase counts are the plan's own checks (2/1/4/2)",
          [len([match for match in parsed if match.group(2) == name]) - 1
           for name in order] == [2, 1, 4, 2],
          [len([match for match in parsed if match.group(2) == name]) - 1
           for name in order])
    check("... and the closing line counts every check",
          parsed[-1].group(3) == parsed[-1].group(4) == "2", parsed[-1].groups())


def t_a_quiet_bounded_phase_is_heartbeated_but_a_healthy_one_is_not():
    class Clock:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            return self.t

        def advance(self, seconds):
            self.t += float(seconds)

    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_bounded_handler(repo, backend))
    clock = Clock()
    said = []
    with _fake_proof_checks():
        def slow_compile(*args, **kwargs):
            clock.advance(301.0)          # one quiet stretch, four seconds early
            return {"ok": True, "checked": 1, "failed": []}

        U.compile_shipped_modules = slow_compile
        result = U.bounded_proof(repo, backend, say=said.append, run=fake,
                                 clock=clock)
    heartbeat = [line for line in said
                 if line.startswith(U.PROOF_HEARTBEAT_PREFIX + "still running")]
    steps = [index for index, line in enumerate(said)
             if line.startswith(U.PROOF_STEP_PREFIX)]
    beats = [index for index, line in enumerate(said)
             if line.startswith(U.PROOF_HEARTBEAT_PREFIX + "still running")]
    check("the bounded proof still passes with one long, quiet check",
          result["ok"] is True, result)
    check("a quiet stretch inside a phase is heartbeated, inside the five minutes",
          len(heartbeat) == 1 and "5m 0" in heartbeat[0], heartbeat)
    check("... and the heartbeat keeps the documented line shape",
          heartbeat and heartbeat[0].startswith(
              "PROOF: still running - 5m 01s elapsed, checking the backend "
              "against the live folder"), heartbeat)
    check("... it lands BETWEEN that phase's own PROOF: Step lines",
          steps and steps[0] < beats[0] < steps[2], (steps, beats))
    check("the heartbeat interval is still well inside the app's 15-minute silence "
          "bound", U.PROOF_HEARTBEAT_SECONDS == 300.0
          and U.PROOF_HEARTBEAT_SECONDS * 3 <= 15 * 60, U.PROOF_HEARTBEAT_SECONDS)

    # A healthy bounded run - every check quick - prints no heartbeat at all:
    # nothing here is near the five minutes, so no app bound can fire on it.
    healthy = []
    repo2, backend2 = _make_repo(_make_root())
    fake2 = FakeRun(_bounded_handler(repo2, backend2))
    with _fake_proof_checks():
        U.bounded_proof(repo2, backend2, say=healthy.append, run=fake2,
                        clock=lambda: 0.0)
    check("... and a healthy bounded run prints no heartbeat at all",
          not any(line.startswith(U.PROOF_HEARTBEAT_PREFIX + "still running")
                  for line in healthy),
          [line for line in healthy if line.startswith("PROOF:")][:4])


def t_the_py_compile_check_compiles_the_live_folders_own_bytes():
    root = _make_root()
    repo, backend = _make_repo(root)
    for name in ("one.py", "two.py", "jarvis_gate.py"):
        (backend / name).write_text("value = 1\n", encoding="utf-8")
    good = U.compile_shipped_modules(repo, backend)
    check("every shipped module compiles from the live folder",
          good["ok"] is True and good["checked"] == 3 and good["failed"] == [],
          good)
    check("... and the check writes no __pycache__ into the live folder",
          not list(backend.rglob("__pycache__")),
          list(backend.rglob("__pycache__")))
    (backend / "two.py").write_text("def broken(:\n", encoding="utf-8")
    bad = U.compile_shipped_modules(repo, backend)
    check("a broken LIVE module is a failed check, named by its file",
          bad["ok"] is False and any("two.py" in line for line in bad["failed"]),
          bad)
    (backend / "two.py").write_text("value = 2\n", encoding="utf-8")
    (backend / "jarvis_gate.py").unlink()
    missing = U.compile_shipped_modules(repo, backend)
    check("a shipped module missing from the live folder is a failure too",
          missing["ok"] is False
          and any("jarvis_gate.py" in line for line in missing["failed"]),
          missing)
    (backend / "jarvis_gate.py").write_text("value = 3\n", encoding="utf-8")
    result = U.import_shipped_modules(repo, backend)
    check("every shipped module imports from the live folder in one child",
          result["ok"] is True and result["checked"] == 3, result)
    (backend / "jarvis_gate.py").write_text(
        "raise ImportError('the gate is broken')\n", encoding="utf-8")
    broken = U.import_shipped_modules(repo, backend)
    check("... and an import that raises is a failed check, named by module",
          broken["ok"] is False
          and any("FAIL import jarvis_gate" in line for line in broken["lines"]),
          broken)


def t_the_live_hud_probe_is_an_honest_failure_without_a_hud():
    root = _make_root()
    repo, backend = _make_repo(root)
    result = U.probe_live_hud(backend / "not-a-backend", say=lambda line: None)
    check("a folder with no jarvis_hud.py is an honest failed check, never a pass",
          result["ok"] is False and result["answered"] == 0
          and "jarvis_hud.py" in result["why"], result)
    check("... and the probe's own routes are the three instant ones",
          result["total"] == 3, result)


def t_a_bounded_ending_never_claims_the_full_check():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_bounded_handler(repo, backend))
    said = []
    with _fake_proof_checks():
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json")
    tail = "\n".join(said)
    ending = [line for line in said if line.startswith("ALL DONE")]
    check("a bounded pass exits ok and says so in the bounded words",
          code == 0 and ending
          and ending[-1].startswith(
              "ALL DONE - the backend is patched and proven by the bounded "
              "checks ("), ending)
    check("... it is a claim about the subset, never the full check",
          "a subset, not the full suite" in ending[-1]
          and "the full check passed" not in tail.lower(), ending)
    check("... and the exact full-sweep ending is never printed for it",
          "ALL DONE - the backend is patched and proven" not in
          [line.strip() for line in said], ending)
    check("... while still containing the words the desktop's read_verdict uses, "
          "so 'both or neither' reads the same", "patched and proven" in ending[-1])
    check("... and it tells a developer the one command that runs the full sweep",
          "--full-proof" in ending[-1] or "--full-proof" in tail, ending)


# ==========================================================================
#   The deploy-managed install is detected up front (Gemini ruling 5.5)
# ==========================================================================
#
# THE RULING. Check SOURCE-COMMIT up front: if the install is deploy-managed,
# run tools/reconcile_live_backend.py as the PRIMARY route (skipping the
# guaranteed ~3-minute 51-hunk refusal), and fall back to apply-patches.ps1 only
# for a legacy patch-only install. Never guess; a deploy refusal is reported
# verbatim; one ROUTE: line names the route and why; "both or neither" is
# untouched.
#
# EVERY CHECK HERE FAILS ON THE TREE BEFORE THIS CHANGE: there was no up-front
# detection, so a deploy-managed fixture ran the patch stack first.


def _empty_marker_root():
    root = _make_root()
    _, backend = _make_repo(root)
    (backend / "VERSION").write_bytes(b"0.2.491")
    (backend / U.SOURCE_COMMIT_NAME).write_text("", encoding="utf-8")
    return backend


def _garbage_marker_root():
    root = _make_root()
    _, backend = _make_repo(root)
    (backend / "VERSION").write_bytes(b"0.2.491")
    (backend / U.SOURCE_COMMIT_NAME).write_text(
        json.dumps({"commit": "not-a-commit"}) + "\n", encoding="utf-8")
    return backend


def t_a_deploy_managed_install_is_detected_from_evidence_up_front():
    root = _make_root()
    repo, backend = _make_repo(root)
    plain = U.deploy_managed_evidence(backend)
    check("a legacy patch-only install shows NO deploy evidence",
          plain["managed"] is False and plain["why"] == "", plain)
    (backend / "VERSION").write_bytes(b"0.2.491")
    version_only = U.deploy_managed_evidence(backend)
    check("VERSION alone is NOT deploy evidence (the app writes it too)",
          version_only["managed"] is False, version_only)
    (backend / U.SOURCE_COMMIT_NAME).write_text(
        json.dumps({"commit": "d7003442e"}) + "\n", encoding="utf-8")
    marker = U.deploy_managed_evidence(backend)
    check("SOURCE-COMMIT beside VERSION IS deploy evidence",
          marker["managed"] is True and "SOURCE-COMMIT" in marker["why"]
          and "d7003442e" in marker["why"], marker)
    check("... and the ROUTE words name that evidence, never a guess",
          "this install is deploy-managed" in U.deploy_primary_words(marker)
          and "SOURCE-COMMIT" in U.deploy_primary_words(marker),
          U.deploy_primary_words(marker))

    root2 = _make_root()
    _, backups_only = _make_repo(root2)
    (backups_only / f"{U.DEPLOY_BACKUP_PREFIX}2026-11-21-000000").mkdir()
    backup_evidence = U.deploy_managed_evidence(backups_only)
    # MEASURED 2026-11-21 (audit): the deploy tool NEVER deletes its backup
    # folders, so one stale folder would send a legacy install down the deploy
    # route forever. A backup folder CORROBORATES the marker; it never selects.
    check("a _jarvis-deploy-backup-tool-* folder ALONE is NOT deploy evidence "
          "(the tool never deletes them)",
          backup_evidence["managed"] is False
          and backup_evidence["backups"], backup_evidence)
    (backups_only / "VERSION").write_bytes(b"0.2.491")
    (backups_only / U.SOURCE_COMMIT_NAME).write_text(
        json.dumps({"commit": "d7003442e"}) + "\n", encoding="utf-8")
    both = U.deploy_managed_evidence(backups_only)
    check("... but it corroborates a real SOURCE-COMMIT marker",
          both["managed"] is True and "SOURCE-COMMIT" in both["why"]
          and U.DEPLOY_BACKUP_PREFIX in both["why"], both)
    empty_commit = U.deploy_managed_evidence(_empty_marker_root())
    check("an EMPTY SOURCE-COMMIT beside VERSION is NOT deploy evidence",
          empty_commit["managed"] is False, empty_commit)
    not_hex = U.deploy_managed_evidence(_garbage_marker_root())
    check("a SOURCE-COMMIT that is not a commit is NOT deploy evidence",
          not_hex["managed"] is False, not_hex)

    root3 = _make_root()
    _, marker_only = _make_repo(root3)
    (marker_only / U.SOURCE_COMMIT_NAME).write_text(
        json.dumps({"commit": "d7003442e"}) + "\n", encoding="utf-8")
    lonely = U.deploy_managed_evidence(marker_only)
    check("SOURCE-COMMIT without VERSION is not 'beside VERSION', so not evidence",
          lonely["managed"] is False, lonely)


def t_a_valid_deploy_manifest_is_the_strongest_deploy_evidence():
    """Gemini's ruling 4 (2026-11-21): the content-hash manifest selects the route.

    A `DEPLOY-MANIFEST` beside `VERSION` whose `manifest_sha256` recomputes from
    its own `files` map is the deploy tool's own record of the release it wrote,
    so it is the STRONGEST evidence and is preferred over the older
    `SOURCE-COMMIT` marker, which stays the fallback for installs deployed
    before the manifest existed.
    """
    root = _make_root()
    try:
        repo, backend = _make_repo(root)
        _write_live(backend, NEW)
        path = _mark_deploy_manifest(backend)
        record = json.loads(path.read_text(encoding="utf-8"))
        evidence = U.deploy_managed_evidence(backend)
        check("manifest: a valid DEPLOY-MANIFEST beside VERSION IS deploy evidence",
              evidence["managed"] is True and evidence["corrupt"] == "", evidence)
        check("... the evidence words name the manifest, its commit and its file count",
              "DEPLOY-MANIFEST" in evidence["why"]
              and record["commit"][:12] in evidence["why"]
              and f"{len(record['files'])} file(s) hashed" in evidence["why"],
              evidence["why"])
        check("... and it is PREFERRED over SOURCE-COMMIT, which is not named",
              "SOURCE-COMMIT sits beside VERSION" not in evidence["why"],
              evidence["why"])
        check("... the ROUTE words carry that same evidence",
              "DEPLOY-MANIFEST" in U.deploy_primary_words(evidence),
              U.deploy_primary_words(evidence))

        # A manifest with no VERSION beside it cannot say which release it is:
        # that is unusable evidence, not "no manifest".
        (backend / "VERSION").unlink()
        unpaired = U.deploy_managed_evidence(backend)
        check("manifest: a valid manifest with NO VERSION beside it is unusable, "
              "and says so", unpaired["managed"] is False
              and bool(unpaired["corrupt"])
              and "VERSION is not beside it" in unpaired["corrupt"], unpaired)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_corrupt_deploy_manifest_refuses_the_update_and_runs_neither_route():
    """Ruling 4: malformed/edited evidence is a REFUSAL, never a silent fallback.

    The two guesses a fallback would make are both wrong on a deploy-managed
    install: the patch stack refuses by construction, and a deploy over an
    unreadable record claims bytes nobody has checked. So neither route starts.
    """
    root = _make_root()
    try:
        repo, backend = _make_repo(root)
        _write_live(backend, NEW)
        path = _mark_deploy_manifest(backend)
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["manifest_sha256"] = "0" * 64            # the seal no longer recomputes
        path.write_text(json.dumps(doc), encoding="utf-8")
        before = {name: (backend / name).read_bytes() for name in NEW}
        fake = FakeRun(_bounded_handler(repo, backend))
        deploys = []
        said = []
        with _fake_proof_checks():
            code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                            clock=lambda: 0.0, timings_path=root / "timings.json",
                            deploy=_deploy_ok(backend, calls=deploys))
        tail = "\n".join(said)
        patchers = [cmd for cmd in fake.calls if _is_patcher(cmd)]
        check("manifest: a corrupt manifest REFUSES the whole update", code == 1
              and "DONE WITH PROBLEMS" in tail and "ALL DONE" not in tail,
              (code, said[-6:]))
        check("... the words name the corrupt marker and why it cannot be used",
              "REFUSED" in tail and "DEPLOY-MANIFEST" in tail
              and "does not recompute" in tail, said[-6:])
        check("... the patch stack is NEVER started (no guessing at the install type)",
              patchers == [] and "patcher_calls" not in fake.state, patchers)
        check("... and the deploy route is never started either", deploys == [], deploys)
        check("... nothing is written and nothing is claimed as updated",
              all((backend / name).read_bytes() == before[name] for name in before)
              and "DONE WITH PROBLEMS - nothing was run" in tail,
              {name: (backend / name).read_bytes() for name in before})
        check("... and it says how to repair the record",
              "reconcile_live_backend.py" in tail and "--apply" in tail, said[-6:])

        # The same refusal for a file that is not JSON at all.
        path.write_bytes(b"{ not json")
        said2 = []
        with _fake_proof_checks():
            code2 = U.update(
                repo, backend, "responsive",
                run=FakeRun(_bounded_handler(repo, backend)), say=said2.append,
                clock=lambda: 0.0, timings_path=root / "timings2.json",
                deploy=_deploy_refused("the deploy route must not run"))
        tail2 = "\n".join(said2)
        check("... and a manifest that is not JSON is refused the same way",
              code2 == 1 and "DEPLOY-MANIFEST" in tail2 and "not JSON" in tail2,
              said2[-6:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_live_file_edited_after_the_deploy_fails_manifest_verification():
    """Ruling 4's verification half: the manifest proves bytes the twins cannot.

    `jarvis_hud.py` is a patched base file with no `jarvis-backend/` twin, so
    before the manifest a hand edit to it was invisible to `verify_live_files`.
    Now every file the deploy recorded is checked against its size+sha256, and
    the existing twin compare still runs afterwards.
    """
    root = _make_root()
    try:
        repo, backend = _make_repo(root)
        _write_live(backend, NEW)                  # the state the deploy wrote
        _mark_deploy_manifest(backend)
        check("manifest: a folder the manifest describes verifies clean",
              U.verify_live_files(repo, backend) == [],
              U.verify_live_files(repo, backend))

        # An edit to a listed file that has NO repository twin: only the
        # manifest can catch it, and it must.
        (backend / "jarvis_hud.py").write_text("# edited by hand\n", encoding="utf-8")
        problems = U.verify_live_files(repo, backend)
        check("manifest: a live file edited after the deploy is a FAILURE",
              any(p["file"] == "jarvis_hud.py" and "DEPLOY-MANIFEST" in p["why"]
                  for p in problems), problems)

        # A missing listed file is a failure too.
        _write_live(backend, {"jarvis_hud.py": b"# the owner's backend\n"})
        _mark_deploy_manifest(backend)
        (backend / "two.py").unlink()
        problems = U.verify_live_files(repo, backend)
        check("manifest: a listed live file that is MISSING is a failure",
              any(p["file"] == "two.py" and "DEPLOY-MANIFEST" in p["why"]
                  for p in problems), problems)

        # The twin compare STILL runs: a shipped file edited away from the
        # repository's bytes is caught even when the manifest was rewritten.
        _write_live(backend, NEW)
        _mark_deploy_manifest(backend)
        (backend / "one.py").write_bytes(b"NEW ONE, BUT EDITED\n")
        problems = U.verify_live_files(repo, backend)
        check("manifest: the existing twin compare still runs after the manifest",
              any(p["file"] == "one.py" and p["why"] == "differs" for p in problems),
              problems)
        check("... and the same file is also named by the manifest check",
              any(p["file"] == "one.py" and "DEPLOY-MANIFEST" in p["why"]
                  for p in problems), problems)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_corrupt_manifest_fails_live_verification_instead_of_being_ignored():
    """A manifest that cannot be validated is a failure naming it, never 'no manifest'."""
    root = _make_root()
    try:
        repo, backend = _make_repo(root)
        _write_live(backend, NEW)
        path = _mark_deploy_manifest(backend)
        clean = U.verify_live_files(repo, backend)
        path.write_bytes(b"{ not json")
        problems = U.verify_live_files(repo, backend)
        check("verify: a corrupt DEPLOY-MANIFEST is a failure that names it",
              any(p["file"] == "DEPLOY-MANIFEST" and "corrupt" in p["why"]
                  for p in problems), problems)
        check("... it is NOT silently ignored (the clean result is not returned)",
              clean == [] and problems != [], (clean, problems))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_without_a_manifest_live_verification_is_exactly_todays_behaviour():
    """An install from before ruling 4 keeps the old behaviour, byte for byte."""
    root = _make_root()
    try:
        repo, backend = _make_repo(root)
        problems = U.verify_live_files(repo, backend)
        expected = [{"file": "one.py", "why": "differs"},
                    {"file": "two.py", "why": "differs"},
                    {"file": "jarvis_hud.html", "why": "differs"}]
        check("no manifest: live verification is exactly the twin compare, as before",
              problems == expected, problems)
        check("no manifest: ... with no DEPLOY-MANIFEST entry in it",
              not any(p["file"] == "DEPLOY-MANIFEST" for p in problems), problems)
        evidence = U.deploy_managed_evidence(backend)
        check("no manifest: a legacy install still shows no deploy evidence",
              evidence["managed"] is False and evidence["corrupt"] == "", evidence)
        # SOURCE-COMMIT alone keeps working as the fallback evidence.
        _mark_deploy_managed(backend)
        fallback = U.deploy_managed_evidence(backend)
        check("no manifest: SOURCE-COMMIT beside VERSION is still the fallback",
              fallback["managed"] is True and fallback["corrupt"] == ""
              and "SOURCE-COMMIT" in fallback["why"], fallback)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_deploy_managed_install_takes_reconcile_first_with_no_patch_run():
    root = _make_root()
    repo, backend = _make_repo(root)
    _mark_deploy_managed(backend)
    fake = FakeRun(_bounded_handler(repo, backend, patch=False))
    deploys = []
    calls = []
    said = []
    with _fake_proof_checks(calls=calls):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=_deploy_ok(backend, calls=deploys), pin=_no_pin)
    tail = "\n".join(said)
    patchers = [cmd for cmd in fake.calls if _is_patcher(cmd)]
    route_lines = [line for line in said if line.startswith(U.ROUTE_PREFIX)]
    check("a detected deploy-managed install finishes through the deploy route",
          code == 0 and deploys and len(deploys) == 1, (code, deploys, said[-8:]))
    check("... the patch stack was NEVER started, so its 51-hunk refusal was "
          "skipped rather than paid", patchers == [] and "patcher_calls" not in fake.state,
          patchers)
    check("... the deploy tool ran on the SAME backend folder",
          deploys[0]["backend"] == str(backend)
          and deploys[0]["repo"] == str(repo), deploys)
    check("... ONE ROUTE line names the evidence and why the deploy route ran",
          len(route_lines) == 1
          and "this install is deploy-managed" in route_lines[0]
          and "SOURCE-COMMIT sits beside VERSION" in route_lines[0]
          and "the deploy route carried the update" in route_lines[0],
          route_lines)
    check("... and the report says the refusal was detected up front",
          "detected from evidence on disk before anything runs" in tail
          and "guaranteed refusal is skipped" in tail, said[-10:])
    check("... the bounded proof then ran on the deployed bytes, as the app path",
          fake.state.get("import_calls") == 1
          and fake.state.get("suite_names") == list(U.BOUNDED_INVARIANT_SUITES),
          fake.state.get("suite_names"))
    check("... and the bounded ending is the deploy route's own",
          "proven by the bounded checks (9 of 9)" in tail
          and "ROUTE: this install is deploy-managed" in tail, said[-4:])


def t_a_legacy_patch_only_install_still_runs_the_patch_stack():
    root = _make_root()
    repo, backend = _make_repo(root)
    fake = FakeRun(_bounded_handler(repo, backend))
    deploys = []
    said = []
    with _fake_proof_checks():
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=_deploy_ok(backend, calls=deploys))
    tail = "\n".join(said)
    check("a legacy patch-only install is patched by the patch stack, as before",
          code == 0 and fake.state.get("patcher_calls") == 1,
          (code, fake.state.get("patcher_calls")))
    check("... and the deploy route is never touched for it", deploys == [], deploys)
    check("... and no ROUTE line is printed for it",
          not any(line.startswith(U.ROUTE_PREFIX) for line in said),
          [line for line in said if "ROUTE" in line])
    check("... and it proves itself with the bounded subset and the honest ending",
          "proven by the bounded checks (9 of 9)" in tail, said[-4:])


def t_a_deploy_refusal_on_the_detected_route_is_verbatim_and_never_falls_back():
    root = _make_root()
    repo, backend = _make_repo(root)
    _mark_deploy_managed(backend)
    refused_line = ("REFUSED: the working tree is at HEAD attacker but --ref "
                    "deadbeef is other, so this tool will not run from a "
                    "different commit")
    fake = FakeRun(_bounded_handler(repo, backend, patch=False))
    said = []
    with _fake_proof_checks():
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=_deploy_refused(refused_line), pin=_no_pin)
    tail = "\n".join(said)
    patchers = [cmd for cmd in fake.calls if _is_patcher(cmd)]
    route_lines = [line for line in said if line.startswith(U.ROUTE_PREFIX)]
    check("a deploy refusal on the detected route is an honest failure",
          code == 1 and "ALL DONE" not in tail
          and "DONE WITH PROBLEMS" in tail, (code, said[-6:]))
    check("... the deploy tool's own refusal is reported VERBATIM",
          refused_line in tail, [line for line in said if "REFUSED" in line])
    check("... the patch stack is never tried as a fallback (it refuses by "
          "construction on this install)", patchers == [], patchers)
    check("... and no proof check runs for a route that did not finish",
          fake.state.get("suite_names") is None
          and fake.state.get("import_calls") is None, fake.state)
    check("... with exactly ONE ROUTE line: detected, and the deploy did not finish",
          len(route_lines) == 1 and "this install is deploy-managed" in route_lines[0]
          and "the deploy route did not finish" in route_lines[0], route_lines)
    check("... and nothing is written or claimed as updated",
          all((backend / name).read_bytes() == OLD[name] for name in OLD)
          and (backend / "VERSION").read_text(encoding="utf-8") == "0.2.491",
          {name: (backend / name).read_bytes() for name in OLD})



# ==========================================================================
#   WHICH COMMIT THE APP DEPLOYS: the release's own, never the checkout's HEAD
# ==========================================================================
#
# The owner's ruling Q5 (2026-11-27), and the measured failure it answers
# (DEF-099): launching desktop 0.2.519 auto-ran this tool and it deployed the
# program folder's own HEAD - the stale local checkout `cac8a8824` - while the
# desktop half was the published release `e719ccbf4`.
#
# So these use a REAL git repository whose HEAD is one commit behind its own
# origin/main, and the thing each one measures is WHICH COMMIT THE DEPLOY WAS
# HANDED. They can all fail in the direction that matters: the first goes red if
# the pin falls back to the checkout (`seen["sha"] == head` instead of `origin`),
# and the run's own live-file check would go red too, because the fake deploy
# carries the bytes of the tree it was given and the run compares them with the
# PINNED tree's `jarvis-backend/`.

#: git must not read this PC's user config and must not rewrite line endings.
_PIN_GIT_CONFIG = ["-c", "user.name=Jarvis suite",
                   "-c", "user.email=suite@example.invalid",
                   "-c", "commit.gpgsign=false",
                   "-c", "core.autocrlf=false"]


def _pin_git(repo, *args) -> str:
    """git in `repo`, stripped stdout; a failure raises. Real objects, no fakes."""
    proc = subprocess.run(["git"] + _PIN_GIT_CONFIG + [str(part) for part in args],
                          cwd=str(repo), capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(str(a) for a in args)} failed in {repo}: "
                           f"{proc.stderr}")
    return proc.stdout.strip()


def _pin_repo(root: Path) -> dict:
    """A checkout one commit BEHIND its own origin/main, as on the owner's PC.

    Returns `{"repo", "backend", "head", "origin", "upstream"}`. `head` is the
    commit the checkout is on and its published base holds the OLD bytes;
    `origin` is the commit origin/main is on and holds the NEW bytes - so WHICH
    commit a deploy read is visible in the bytes it carried, not only in a number.

    The live folder is made deploy-managed the way the owner's is (VERSION with
    SOURCE-COMMIT beside it), so the deploy route is the primary route and no
    patch stack is ever started here.
    """
    repo, backend = _make_repo(root)
    for name, content in OLD.items():                 # commit A: this checkout
        (repo / "jarvis-backend" / name).write_bytes(content)
    _pin_git(repo, "init", "-q", "-b", "main")
    # THIS PC'S GLOBAL CONFIG MAY BE autocrlf=true, which would check the
    # throwaway copy out with CRLF while the fixture's bytes are LF. Pin it off,
    # so "which bytes did the deploy read" is a byte comparison and not a
    # question about somebody's git config. (Production is safe either way:
    # `verify_live_files` compares with line endings normalised, and the deploy
    # tool reads its module bytes out of the object store, not off the disk.)
    _pin_git(repo, "config", "core.autocrlf", "false")
    _pin_git(repo, "add", "-A")
    _pin_git(repo, "commit", "-q", "-m", "the release this PC is on")
    head = _pin_git(repo, "rev-parse", "HEAD")
    for name, content in NEW.items():                 # commit B: origin/main
        (repo / "jarvis-backend" / name).write_bytes(content)
    _pin_git(repo, "add", "-A")
    _pin_git(repo, "commit", "-q", "-m", "the release origin/main is on")
    origin = _pin_git(repo, "rev-parse", "HEAD")
    _pin_git(repo, "reset", "-q", "--hard", head)     # the checkout stays behind
    upstream = root / "upstream.git"
    _pin_git(root, "init", "-q", "--bare", str(upstream))
    _pin_git(repo, "remote", "add", "origin", str(upstream))
    _pin_git(repo, "push", "-q", "origin", f"{origin}:refs/heads/main")
    _pin_git(repo, "fetch", "-q", "origin")
    (backend / "VERSION").write_text("0.2.518", encoding="utf-8")
    (backend / "SOURCE-COMMIT").write_text(json.dumps({"commit": head}),
                                           encoding="utf-8")
    return {"repo": repo, "backend": backend, "head": head, "origin": origin,
            "upstream": upstream}


def _pin_deploy(backend: Path, seen: dict, *, refuse=False):
    """A stand-in for the deploy route that records WHICH TREE it was handed.

    It carries that tree's own published base into the live folder, exactly as
    `tools/reconcile_live_backend.py --apply` carries the bytes of the commit it
    was given - so a deploy handed the wrong tree writes the wrong bytes and the
    run's own live-file check says so, without this fake having to be believed.
    """
    def deploy(repo_arg, backend_arg, *, say):
        tree = Path(repo_arg)
        seen["repo"] = str(tree)
        seen["sha"] = _pin_git(tree, "rev-parse", "HEAD")
        seen["head_ref"] = _pin_git(tree, "rev-parse", "--abbrev-ref", "HEAD")
        seen["status"] = _pin_git(tree, "status", "--porcelain")
        seen["base"] = (tree / "jarvis-backend" / "one.py").read_bytes()
        if refuse:
            line = "REFUSED: the deploy tool refused this on purpose"
            say(line)
            return {"ok": False, "code": 2, "ref": "", "version": "",
                    "desktop_version": "", "why": line, "lines": [line]}
        for name in NEW:
            (Path(backend_arg) / name).write_bytes(
                (tree / "jarvis-backend" / name).read_bytes())
        (Path(backend_arg) / "VERSION").write_text("0.2.519", encoding="utf-8")
        say("RESULT: PASS - backend reconciled; restart Jarvis and read the "
            "start-up banner.")
        return {"ok": True, "code": 0, "ref": seen["sha"], "version": "0.2.519",
                "desktop_version": "0.2.519", "why": "",
                "lines": ["RESULT: PASS"]}

    return deploy


@contextmanager
def _with_published(answer):
    """Swap the published-release reader for one answer, and put it back."""
    before = U.read_published_release
    U.read_published_release = lambda repo, **kw: dict(answer)
    try:
        yield
    finally:
        U.read_published_release = before


def _worktrees(repo: Path) -> list:
    """The repository's worktree paths, as Paths.

    `git worktree list` prints forward slashes even on Windows, so the paths are
    compared as Paths and never as strings.
    """
    return [Path(line.split(" ", 1)[1]) for line in
            _pin_git(repo, "worktree", "list", "--porcelain").splitlines()
            if line.startswith("worktree ")]


def _only_worktree(repo: Path) -> bool:
    """True when the repository lists exactly ONE worktree and it is `repo`.

    A leftover throwaway copy is a new bug of its own, so every pinning check
    ends with this. Resolved Paths, because git prints `C:/...` and Windows
    hands out `C:\\...`.
    """
    return ([path.resolve() for path in _worktrees(repo)]
            == [Path(repo).resolve()])


def t_the_app_deploys_origin_main_not_the_checkout_s_head():
    root = _make_root()
    fixture = _pin_repo(root)
    repo, backend = fixture["repo"], fixture["backend"]
    seen, said = {}, []
    fake = FakeRun(_refusal_then_suites(repo, backend))
    with _with_published({"version": "", "commit": "",
                          "why": "not recorded (this test)"}):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=_pin_deploy(backend, seen), full_proof=True)
    tail = "\n".join(said)
    check("the checkout really is one commit behind origin/main (the fixture)",
          fixture["head"] != fixture["origin"]
          and _pin_git(repo, "rev-parse", "HEAD") == fixture["head"]
          and _pin_git(repo, "rev-parse", "origin/main") == fixture["origin"],
          fixture["head"])
    check("the app-triggered update deploys origin/main's commit, NOT the "
          "checkout's HEAD",
          code == 0 and seen.get("sha") == fixture["origin"],
          (code, seen.get("sha"), fixture["origin"], fixture["head"]))
    check("... from a clean DETACHED copy (no branch of the owner's is moved)",
          seen.get("head_ref") == "HEAD" and seen.get("status") == "",
          (seen.get("head_ref"), seen.get("status")))
    check("... carrying that commit's bytes, not the checkout's",
          seen.get("base") == NEW["one.py"], seen.get("base"))
    check("... and the run says so: the PIN line names the commit and that it is "
          "not this folder's HEAD",
          any(line.startswith("PIN  ") and fixture["origin"][:12] in line
              and "not from this folder's own HEAD" in line for line in said),
          [line for line in said if line.startswith("PIN")])
    check("... the run finished and proved the live files against the PINNED "
          "tree (the checkout's base holds the other bytes)",
          code == 0 and "ALL DONE" in tail, (code, said[-6:]))
    suites = [cmd for cmd in fake.calls if not _is_patcher(cmd)]
    check("... and the proof ran the PINNED tree's suites, not the checkout's",
          bool(suites) and str(repo) not in suites[0][2],
          suites[0][:3] if suites else [])
    check("the owner's checkout is untouched: same HEAD, same bytes, no new "
          "branch, nothing uncommitted",
          _pin_git(repo, "rev-parse", "HEAD") == fixture["head"]
          and _pin_git(repo, "status", "--porcelain") == ""
          and len(_pin_git(repo, "branch", "--list").splitlines()) == 1
          and (repo / "jarvis-backend" / "one.py").read_bytes() == OLD["one.py"],
          (_pin_git(repo, "rev-parse", "HEAD"),
           _pin_git(repo, "status", "--porcelain")))
    check("... and the throwaway copy is GONE when the run ends",
          _only_worktree(repo), _worktrees(repo))


def t_a_manual_ref_head_still_deploys_the_commit_head_names():
    root = _make_root()
    fixture = _pin_repo(root)
    repo, backend = fixture["repo"], fixture["backend"]
    seen, said = {}, []
    fake = FakeRun(_refusal_then_suites(repo, backend))
    with _with_published({"version": "0.2.519", "commit": fixture["origin"],
                          "why": ""}):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=_pin_deploy(backend, seen), full_proof=True,
                        ref="HEAD")
    check("a developer's --ref HEAD still deploys the commit HEAD names",
          code == 0 and seen.get("sha") == fixture["head"],
          (code, seen.get("sha"), fixture["head"]))
    check("... and it BEATS both the published release's commit and origin/main",
          seen.get("sha") != fixture["origin"],
          (seen.get("sha"), fixture["origin"]))
    check("... with the PIN line naming the override, so the log says which ran",
          any(line.startswith("PIN  --ref HEAD") for line in said),
          [line for line in said if line.startswith("PIN")])


def t_the_published_release_s_commit_is_preferred_over_origin_main():
    root = _make_root()
    fixture = _pin_repo(root)
    repo, backend = fixture["repo"], fixture["backend"]
    seen, said = {}, []
    fake = FakeRun(_refusal_then_suites(repo, backend))
    # The release names the commit the checkout is on; origin/main is the newer
    # one. A pin that ignored the release would deploy origin/main instead.
    with _with_published({"version": "0.2.519", "commit": fixture["head"],
                          "why": ""}):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=_pin_deploy(backend, seen), full_proof=True)
    check("the published release's own commit wins over origin/main",
          code == 0 and seen.get("sha") == fixture["head"],
          (code, seen.get("sha"), fixture["head"], fixture["origin"]))
    check("... and the PIN line names the release it came from",
          any(line.startswith("PIN  the published desktop release 0.2.519")
              for line in said), [line for line in said if line.startswith("PIN")])


def t_a_pin_that_cannot_be_made_refuses_instead_of_deploying_the_checkout():
    root = _make_root()
    fixture = _pin_repo(root)
    repo, backend = fixture["repo"], fixture["backend"]
    # Offline, and this checkout has never seen an origin/main: the two things
    # that must produce a refusal rather than the DEF-099 fallback.
    _pin_git(repo, "remote", "set-url", "origin", str(root / "nowhere"))
    _pin_git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    seen, said, deploys = {}, [], []
    fake = FakeRun(_refusal_then_suites(repo, backend))

    def deploy(repo_arg, backend_arg, *, say):
        deploys.append(str(repo_arg))
        return _pin_deploy(backend, seen, refuse=True)(repo_arg, backend_arg, say=say)

    with _with_published({"version": "", "commit": "",
                          "why": "the published release could not be read "
                                 "(URLError: offline)"}):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=deploy, full_proof=True)
    tail = "\n".join(said)
    check("a deploy-managed install with nothing to pin REFUSES instead of "
          "deploying the checkout", code == 1 and deploys == [],
          (code, deploys, said[-4:]))
    check("... the sentence names what could not be read (the release AND the fetch)",
          "REFUSED" in tail and "published release could not be read" in tail
          and "origin/main could not be read" in tail, said[-6:])
    check("... and it says in so many words that the folder was NOT deployed in "
          "its place", "was NOT deployed in its place" in tail, said[-6:])
    check("... nothing was written and no new version is claimed",
          (backend / "VERSION").read_text(encoding="utf-8") == "0.2.518"
          and (backend / "one.py").read_bytes() == OLD["one.py"],
          (backend / "VERSION").read_text(encoding="utf-8"),
          )
    check("... no patch stack ran either (a deploy-managed install has none that "
          "applies)", fake.calls == [], fake.calls)
    check("... the checkout is untouched and no throwaway copy is left",
          _pin_git(repo, "rev-parse", "HEAD") == fixture["head"]
          and _only_worktree(repo), _worktrees(repo))


def t_a_failed_deploy_still_removes_the_throwaway_copy():
    root = _make_root()
    fixture = _pin_repo(root)
    repo, backend = fixture["repo"], fixture["backend"]
    seen, said = {}, []
    fake = FakeRun(_refusal_then_suites(repo, backend))
    with _with_published({"version": "", "commit": "",
                          "why": "not recorded (this test)"}):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=_pin_deploy(backend, seen, refuse=True),
                        full_proof=True)
    check("a deploy that fails is an honest failure, never a claimed update",
          code == 1 and "DONE WITH PROBLEMS" in "\n".join(said), (code, said[-4:]))
    check("... and its throwaway copy is removed on the failure path too",
          seen.get("sha") == fixture["origin"]
          and _only_worktree(repo), _worktrees(repo))


def t_a_pinned_patch_install_runs_the_patched_tree_s_own_patcher():
    """The OTHER route reads the pinned tree too (measured, not assumed).

    A patch-only install has no deploy tool to point elsewhere, but the patcher
    it runs takes its own scripts, its patch list and the desktop's Cargo.lock
    from the folder it sits in - so running the PINNED tree's copy is what makes
    "the whole run reads one tree" true for this route as well. That is also the
    shape `scripts/update-jarvis.ps1` already describes around its (unused)
    throwaway source copy.
    """
    root = _make_root()
    fixture = _pin_repo(root)
    repo, backend = fixture["repo"], fixture["backend"]
    # A PATCH-ONLY install: the deploy evidence is removed, so the patch stack is
    # the route and nothing about the deploy tool is involved.
    (backend / "SOURCE-COMMIT").unlink()
    (backend / "VERSION").unlink()
    deploys, said = [], []
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    with _with_published({"version": "", "commit": "",
                          "why": "not recorded (this test)"}):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        deploy=_deploy_ok(backend, calls=deploys), full_proof=True)
    patchers = [cmd for cmd in fake.calls if _is_patcher(cmd)]
    own = str(repo / "scripts" / "apply-patches.ps1")
    check("a patch install that can be pinned still finishes by the patch stack",
          code == 0 and len(patchers) == 1 and deploys == [],
          (code, len(patchers), deploys))
    check("... and the patcher it runs is the PINNED tree's copy, not the "
          "checkout's",
          bool(patchers) and own not in patchers[0]
          and any(str(part).endswith("apply-patches.ps1")
                  and str(tempfile.gettempdir()) in str(part)
                  for part in patchers[0]),
          patchers[0] if patchers else [])
    check("... and its throwaway copy is gone when the run ends",
          _only_worktree(repo), _worktrees(repo))


def t_a_patch_only_install_says_it_could_not_pin_and_still_works():
    root = _make_root()
    repo, backend = _make_repo(root)          # not a git checkout at all
    said = []
    fake = FakeRun(_staged_handler(repo, backend, suites="ok"))
    with _with_published({"version": "", "commit": "",
                          "why": "not recorded (this test)"}):
        code = U.update(repo, backend, "responsive", run=fake, say=said.append,
                        clock=lambda: 0.0, timings_path=root / "timings.json",
                        full_proof=True)
    tail = "\n".join(said)
    check("a folder that is not a git checkout still updates by the patch stack",
          code == 0 and "ALL DONE" in tail, (code, said[-5:]))
    check("... and it SAYS OUT LOUD that it could not be pinned - never silently",
          any(line.startswith("NOTE  this program folder is not a git checkout")
              for line in said),
          [line for line in said if line.startswith("NOTE")])


def t_the_cleanup_refuses_any_path_outside_the_temporary_folder():
    """MEASURED 2026-11-27, expensively: this cleanup deleted a repository.

    The driver was handed `Path("")` to mean "there is no worktree". `Path("")`
    is `"."`, so `shutil.rmtree(".")` set about removing the folder the tool was
    running from - and it took the working tree with it before it was stopped.
    The guard is `_under_temp_folder`, and this proves it REFUSES before any
    deletion: the folder is still there afterwards, which is the only claim worth
    making (a raised exception would not prove that nothing was removed).
    """
    outside = Path(tempfile.gettempdir()).parent
    keeper = outside / "q5-a folder that must survive"
    if keeper.exists():
        shutil.rmtree(keeper, ignore_errors=True)
    keeper.mkdir(parents=True)
    for name in ("one.txt", "two.txt"):
        (keeper / name).write_text("still here\n", encoding="utf-8")
    nested = keeper / "nested"
    nested.mkdir()
    (nested / "three.txt").write_text("still here too\n", encoding="utf-8")
    for bad in ("", ".", "..", str(keeper)):
        U._release_worktree(outside, bad, bad)
        check(f"the cleanup refused {bad!r} and left the folder alone",
              keeper.is_dir() and (keeper / "one.txt").is_file()
              and (nested / "three.txt").is_file(), bad)
    check("... and it names no folder inside the temporary store it did not make",
          U._under_temp_folder("") is False
          and U._under_temp_folder(".") is False
          and U._under_temp_folder(keeper) is False,
          [U._under_temp_folder(value) for value in ("", ".", keeper)])
    check("... while a folder it DID make under the temporary store is accepted",
          U._under_temp_folder(Path(tempfile.gettempdir()) / "jarvis-deploy-source-x")
          is True)
    # A path it made itself is removed, so the guard is not simply "never delete".
    mine = Path(tempfile.mkdtemp(prefix="jarvis-deploy-source-test-"))
    (mine / "tree").mkdir()
    (mine / "tree" / "junk.txt").write_text("junk\n", encoding="utf-8")
    U._release_worktree(outside, mine / "tree", mine)
    check("... and a throwaway folder it made IS removed", not mine.exists(), mine)
    shutil.rmtree(keeper, ignore_errors=True)


def t_ref_is_the_manual_override_and_nothing_else_produces_it():
    base = ["--repo", "r", "--backend", "b"]
    check("the app path carries no ref at all, so the pin decides",
          U.parse_args(base)["ref"] is None, U.parse_args(base)["ref"])
    check("a developer can name HEAD, a branch or a commit",
          U.parse_args(base + ["--ref", "HEAD"])["ref"] == "HEAD"
          and U.parse_args(base + ["--ref", "main"])["ref"] == "main"
          and U.parse_args(base + ["--ref", "c" * 40])["ref"] == "c" * 40,
          U.parse_args(base + ["--ref", "main"])["ref"])
    refused = ""
    try:
        U.parse_args(base + ["--ref", ""])
    except U.UpdateRefused as exc:
        refused = exc.message
    check("an empty --ref is refused, not read as 'no --ref' (the silent "
          "substitution a developer would never see)",
          "must not be empty" in refused, refused)
    check("the usage line names the override", "--ref" in U._usage(), U._usage())
    # The desktop's own command line IS the app-triggered path: it must have no
    # way to pass a ref, or an app update could pin itself to a stale checkout.
    rust = (HERE.parent / "jarvis-desktop" / "src-tauri" / "src"
            / "backend_update.rs")
    text = rust.read_text(encoding="utf-8", errors="replace") if rust.is_file() else ""
    start = text.find("pub fn tool_args(")
    end = text.find("\n}\n", start) if start >= 0 else -1
    body = text[start:end] if start >= 0 and end > start else ""
    check("the desktop's own command line (tool_args) has no --ref in it",
          bool(body) and '"--ref"' not in body and "-ref" not in body,
          body or "not read - this checkout has no desktop half")


def t_the_release_feed_is_the_app_s_own_and_its_commit_is_never_invented():
    root = _make_root()
    repo, _backend = _make_repo(root)
    (repo / "jarvis-desktop" / "src-tauri").mkdir(parents=True, exist_ok=True)
    (repo / "jarvis-desktop" / "src-tauri" / "tauri.conf.json").write_text(
        json.dumps({"plugins": {"updater": {"endpoints": [
            "https://example.invalid/desktop-latest/latest.json"]}}}),
        encoding="utf-8")
    check("the feed URL is READ from the app's own updater config, not typed here",
          U.updater_endpoint(repo)
          == "https://example.invalid/desktop-latest/latest.json",
          U.updater_endpoint(repo))
    asked = {}

    def opener(url):
        asked["url"] = url
        return {"version": "0.2.519", "commit": "17A92E5F" + "a" * 32}

    got = U.read_published_release(repo, opener=opener)
    check("the manifest's commit is read and lower-cased",
          got["commit"] == ("17a92e5f" + "a" * 32) and got["why"] == "", got)
    check("... and the request went to the one URL the app itself reads",
          asked.get("url", "").endswith("/desktop-latest/latest.json"), asked)
    got = U.read_published_release(repo, opener=lambda url: {"version": "0.2.519"})
    check("a manifest with no commit says 'not recorded' and invents nothing",
          got["commit"] == "" and "not recorded" in got["why"], got)
    got = U.read_published_release(
        repo, opener=lambda url: {"version": "0.2.519", "commit": "not-a-commit"})
    check("a commit that is not a hex sha is refused, not resolved",
          got["commit"] == "" and "not a hex sha" in got["why"], got)
    got = U.read_published_release(
        repo, opener=lambda url: (_ for _ in ()).throw(OSError("offline")))
    check("a feed that cannot be read is a plain sentence, never an exception",
          got["commit"] == "" and "could not be read" in got["why"], got)
    got = U.read_published_release(_make_repo(_make_root())[0],
                                   opener=lambda url: {"commit": "a" * 40})
    check("a checkout with no updater config asks nothing at all",
          got["commit"] == "" and "no readable desktop updater config" in got["why"],
          got)


# ==========================================================================
#   The suite's own runner
# ==========================================================================


def t_the_deploy_tool_loads_with_its_dataclasses():
    """MEASURED 2026-11-21 02:52 on the owner's PC: the deploy route could never start.

    `load_deploy_tool()` executed `tools/reconcile_live_backend.py` through
    importlib WITHOUT registering it in `sys.modules`. Python 3.12's
    `dataclasses` resolves `KW_ONLY` through
    `sys.modules[cls.__module__].__dict__`, so the first `@dataclass`
    (`ShippedAction`) raised `AttributeError: 'NoneType' object has no attribute
    '__dict__'` - and the in-app auto-finish could only report "the deploy route
    itself failed". The file's own CLI imports it normally, so only this dynamic
    path was broken; the lane's tests faked the module and missed it.
    """
    import sys as _sys
    # A fresh load, exactly the app's first load: drop any copy another suite
    # test already put in sys.modules, and this loader's own cache.
    _sys.modules.pop("reconcile_live_backend", None)
    U._DEPLOY_MODULE = None
    mod = U.load_deploy_tool()
    check("load_deploy_tool() returns the deploy module", mod is not None)
    check("... and it is registered in sys.modules (what dataclasses needs)",
          _sys.modules.get(mod.__name__) is mod, mod.__name__)
    check("... so a real dataclass in it can be built",
          bool(mod.DeltaAction("p", "jarvis_hud.py", "insert")))
    check("... and the deploy entry point is callable", callable(mod.run_deploy))


def t_a_bounded_suite_that_skipped_checks_is_reported_not_hidden():
    """MEASURED 2026-11-21 (audit): a suite exiting 0 can print
    "N passed, M skipped". "9 of 9" must not fold those skips into "proven"."""
    root = _make_root()
    repo, backend = _make_repo(root)
    lines = ["ok one", "2 passed, 1 skipped, 0 failed", "skip two - needs a file"]

    def run(argv, cwd, on_line):
        for line in lines:
            on_line(line)
        return 0

    with _fake_proof_checks():
        result = U.bounded_proof(repo, backend, run=run, say=lambda line: None,
                                 clock=lambda: 0.0)
    check("a passing check that skipped one of its own checks is still ok",
          result["ok"] is True and result["passed"] == result["total"], result["passed"])
    check("... but the skip count is carried, not hidden",
          result["skipped"] >= 1 and result["unproven"] is True, result["skipped"])
    rows = [row for row in result["checks"] if row["skipped"]]
    check("... and the row names which check skipped something", bool(rows), rows[:2])


def t_the_deploy_route_proof_sentence_reports_checks_skipped_inside_suites():
    """MEASURED 2026-11-21: 0.2.495's ROUTE line said "passed (9 of 9)" while 4
    checks inside test_reconcile_live_backend were skipped. The count must travel
    with the claim, so the one sentence that names the proof says it too.

    Gemini's rulings 1 and 5.3 (2026-11-21) then made the card show it COMPACTLY
    - the skip count and the honesty marker in one parenthesis - while the full
    explanation stays in the transcript: `(9 of 9, 4 skipped - a subset, not the
    full suite)`. The no-skip wording is byte-identical to what it was before the
    rulings.
    """
    plain = {"passed": 9, "total": 9, "skipped": 0}
    check("with no skips the sentence is byte-identical to before ruling 1",
          U.bounded_proof_phrase(plain) ==
          "and the bounded checks above passed (9 of 9); they are a subset, "
          "not the full suite", U.bounded_proof_phrase(plain))
    with_skips = {"passed": 9, "total": 9, "skipped": 4}
    said = U.bounded_proof_phrase(with_skips)
    check("... and the skip count plus the honesty marker are shown COMPACTLY, "
          "in one parenthesis",
          said == ("and the bounded checks above passed (9 of 9, 4 skipped - "
                   "a subset, not the full suite)"), said)
    check("... the old trailing 'with 4 check(s) ...' clause is still gone",
          "with 4 check(s)" not in said, said)
    check("... the long explanation is NOT carried on the card (ruling 5.3 puts "
          "it in the transcript)",
          "not counted as proven" not in said, said)
    check("... while the subset marker stays in the sentence",
          "a subset, not the full suite" in said, said)
    check("... and the phrase holds no full stop of its own (the ROUTE sentence "
          "supplies the one that ends it)",
          "." not in said, said)

def t_the_four_bounded_proof_phase_names_are_frozen():
    """Gemini's ruling 2 (2026-11-21): the four phase labels are a contract.

    The desktop's `update_progress.rs` parses the wire SHAPE, and the card
    renders the phase name it is given VERBATIM, so a renamed label changes what
    the owner reads with no Rust change at all. The exact four strings are pinned
    here; changing one is now a breaking contract change - written in
    `docs/JARVIS-API.md` section 184.12 first, then in the code and this test -
    the same treatment as a route change. `backend/test_api_doc.py` proves the
    page's frozen list and this tuple agree.
    """
    names = [phase["name"] for phase in U.BOUNDED_PROOF_PHASES]
    check("the four bounded-proof phase names are frozen, in order",
          names == ["module imports", "instant API answers", "core invariants",
                    "look spec & config"], names)
    check("... and there are exactly four phases",
          len(names) == 4, len(names))
    check("... the internal ids are still the short ids, not the labels",
          [phase["id"] for phase in U.BOUNDED_PROOF_PHASES]
          == ["imports", "answers", "invariants", "spec"],
          [phase["id"] for phase in U.BOUNDED_PROOF_PHASES])
    check("... and the progress line prints one of these labels verbatim",
          U.PROOF_STEP_SHAPE.format(step=2, steps=len(names), phase=names[1],
                                    done=1, total=1)
          == "PROOF: Step 2/4 - instant API answers - 1 of 1",
          U.PROOF_STEP_SHAPE.format(step=2, steps=len(names), phase=names[1],
                                    done=1, total=1))


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
