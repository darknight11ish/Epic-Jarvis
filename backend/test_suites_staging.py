"""No run of backend/run_suites.py may leave a `jarvis-*` folder in the
machine's temp folder - not the run's own staging, and not the scratch a suite
makes for itself.

    python3 backend/test_suites_staging.py

WHY THIS EXISTS (measured 2026-10-11). Every run of run_suites.py used to leave
`jarvis-staged-backend-<rand>` (a copy of every shipped module, 10 MB) and
`jarvis-suite-state-<rand>` (the config folder and audit log the suites write,
64 MB in one measured case) under %TEMP%, because both rmtree calls sat at the
END of main(), outside any try/finally: a killed, Ctrl-C'd or CI-cancelled run
skipped both. It was worse than two folders - nearly every suite in this folder
makes its own `jarvis-<suite>-<rand>` at import time with `tempfile.mkdtemp`
and never removes it, which is one folder per suite per run. 20,633 of these
folders reached 123.6 GB and took C: from 165 GB free down to 34 GB.

WHAT IS CHECKED, and why each check can fail:

  1. A finished run leaves NO `jarvis-*` directory. The end-to-end check: a real
     sweep of one small suite is run as a subprocess with its temp folder
     redirected into this test's own scratch folder, and everything under that
     folder is listed afterwards. An EMPTY leftover directory fails this too -
     the twenty thousand were folders that had had their bytes removed from
     them, so counting bytes would have missed them.
  2. The suites' own scratch really is redirected inside the run's folder.
     Without TMPDIR/TEMP/TMP, nothing a suite makes lands there - and check 1
     would then pass for the wrong reason, because the folders would simply be
     somewhere else.
  3. main() removes that folder in a `finally`, and releases the lock BEFORE it
     does: on Windows a file this process still holds open cannot be deleted, so
     removing the folder first silently leaves the whole folder behind.
  4. The reaper removes what an ended run left and NEVER touches a folder a live
     run still holds. Both halves are done for real: a child process claims a
     folder and exits (the operating system drops the lock exactly as a kill
     does), and a folder this process still holds is left alone even with its
     timestamp two hours old.
  5. A folder too fresh to be abandoned, a folder with no marker that is not a
     day old, and a folder that is not this runner's shape at all, are all left
     alone.
  6. THE SUITES' HOME IS A THROWAWAY FOLDER (2026-10-18, Spotlight 2). Each
     run's OPENJARVIS_HOME / JARVIS_HOME point inside its state folder - never
     at the owner's real ~/.openjarvis - and --state-env prints them so a
     patcher run gets the same folder without a second list.
  7. A REAL SWEEP LEAVES A FAKE OWNER'S HOME ALONE: a sentinel file in a fake
     HOME/.openjarvis is unchanged, with nothing made beside it, after a run
     whose header names the throwaway home.
  8. THE ONE ESCAPE HATCH IS EXPLICIT: `JARVIS_TESTS_USE_REAL_HOME=1` keeps
     the caller's own home, says in the header that the run is NOT hermetic,
     and prints no home line from --state-env; it is never the default.

No network, no model, no file of the owner's. Standard library only.
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_suites as R  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []

#: The suite the end-to-end run sweeps. Small and fast (112 lines, no model, no
#: network, nothing of the owner's), and - the reason it is this one and not any
#: other - it MAKES a `jarvis-*` folder of its own at import time
#: (`tempfile.mkdtemp(prefix="jarvis-front-")`). A suite that made no temp
#: folder could not tell a working redirect from no redirect at all.
SUITE = "test_front.py"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def _env(temp: Path) -> dict:
    """The environment a run is given here: none of the owner's settings, and
    every temp variable pointed at `temp` (this test's own scratch folder)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    for k in ("JARVIS_BACKEND", "OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR",
              "JARVIS_FRAMEWORK_TOML"):
        env.pop(k, None)
    for k in ("TMPDIR", "TEMP", "TMP"):
        env[k] = str(temp)
    return env


def _run(args, env, timeout=900):
    return subprocess.run([sys.executable] + [str(a) for a in args], cwd=HERE, env=env,
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def _names(where: Path) -> list:
    """Everything directly under `where`, directories first-class: a leftover
    EMPTY `jarvis-*` directory is the failure this file is about."""
    try:
        return sorted(p.name for p in where.iterdir())
    except OSError as exc:
        return [f"<unreadable: {exc}>"]


def _scratch(prefix: str):
    """A scratch folder this test owns, claimed with a marker and a lock so that
    even a kill of this test cannot leave it behind permanently: the same
    mechanism the runner uses, exercised by the test that checks it."""
    d = Path(tempfile.mkdtemp(prefix=prefix))
    return d, R.claim(d, "staging-test")


def t_a_finished_run_leaves_no_folder():
    """The whole point: run a real sweep, then look for what it left."""
    scratch, lock = _scratch("jarvis-staging-test-")
    temp = scratch / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    try:
        check("CONTROL: nothing is under the temp folder before the run",
              _names(temp) == [], _names(temp))
        # CONTROL, and the reason this test lists NAMES rather than bytes: the
        # 20,633 folders were directories that had had their bytes taken out of
        # them, so a check that counted bytes would have called that clean. An
        # EMPTY leftover directory has to fail this.
        empty = temp / "jarvis-sweep-empty0000"
        empty.mkdir()
        check("CONTROL: an EMPTY jarvis-* directory IS seen by this check, not just bytes",
              _names(temp) == ["jarvis-sweep-empty0000"], _names(temp))
        empty.rmdir()
        r = _run([HERE / "run_suites.py", SUITE], _env(temp))
        after = _names(temp)
        check("CONTROL: the run really staged a backend and ran the suite",
              "(staged: every shipped module, flattened)" in r.stdout
              and f"ok    {SUITE}" in r.stdout,
              r.stdout[-2000:] + "\n--stderr--\n" + r.stderr[-1000:])
        check(f"CONTROL: the sweep of {SUITE} passed on its own terms",
              r.returncode == 0, f"exit {r.returncode}\n" + r.stdout[-2000:])
        check("the run left NO jarvis-* directory behind", after == [], after)
        check("and left nothing that is NOT a jarvis-* folder behind either - one "
              "folder, made and removed",
              [n for n in after if not n.startswith("jarvis-")] == [], after)
    finally:
        if lock is not None:
            os.close(lock)
        shutil.rmtree(scratch, ignore_errors=True)
    check("this test removed its own scratch folder too", not scratch.exists(), str(scratch))


def t_a_suites_own_scratch_lands_inside_the_run():
    """Check 2, on its own: without this the end-to-end check passes for the
    wrong reason - the suites' folders would just be in the machine's temp
    folder instead of inside the run's."""
    scratch, lock = _scratch("jarvis-redirect-test-")
    try:
        root = scratch / "jarvis-sweep-madeup"
        root.mkdir()
        env = R.suite_temp_env({}, root)
        want = str(root / R.SUITE_TEMP_NAME)
        check("TMPDIR, TEMP and TMP all point inside the run's own folder",
              {env.get(k) for k in ("TMPDIR", "TEMP", "TMP")} == {want},
              {k: env.get(k) for k in ("TMPDIR", "TEMP", "TMP")})
        child = subprocess.run(
            [sys.executable, "-c", "import tempfile; print(tempfile.gettempdir())"],
            capture_output=True, text=True, env=dict(os.environ, **env))
        check("and a child process's tempfile.gettempdir() is inside it",
              child.stdout.strip() == want,
              f"got {child.stdout.strip()!r} want {want!r}\n{child.stderr}")
        check("the folder was made, not left to Python's fallback (the working "
              "directory, which would put a suite's scratch in the checkout)",
              (root / R.SUITE_TEMP_NAME).is_dir(), str(root))
    finally:
        if lock is not None:
            os.close(lock)
        shutil.rmtree(scratch, ignore_errors=True)


def t_main_removes_its_folder_in_a_finally():
    """Check 3, read from the source with `ast`: a `finally` is the only thing
    that cleans up when a suite's output raises, and an interrupted run is what
    the reaper is for."""
    tree = ast.parse((HERE / "run_suites.py").read_text(encoding="utf-8"))
    main_fn = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    final = [ast.unparse(n.finalbody) for n in ast.walk(main_fn)
             if isinstance(n, ast.Try) and n.finalbody]
    check("main() wraps the run in a try/finally", bool(final), ast.dump(main_fn)[:400])
    if not final:
        return
    body = final[0]
    removes = "remove_tree(root" in body
    check("and the finally removes this run's own folder", removes, body)
    check("the lock is released BEFORE the folder is removed - on Windows a file "
          "this process still holds open cannot be deleted, and the folder would "
          "be left behind whole",
          removes and "os.close(lock)" in body
          and body.index("os.close(lock)") < body.index("remove_tree(root"),
          body)
    check("this run's folder is claimed with a marker before it is used",
          "claim(root," in ast.unparse(main_fn) and "'sweep'" in ast.unparse(main_fn),
          ast.unparse(main_fn)[:400])


def t_the_reaper_takes_what_a_dead_run_left_and_nothing_else():
    """Checks 4 and 5, on a scratch folder so the machine's real temp folder is
    never listed or touched by this test."""
    scratch, test_lock = _scratch("jarvis-reap-test-")
    try:
        old = time.time() - (R.REAP_AFTER + 600)

        # A run that claimed a folder and then died. Done with a real child
        # process, not a made-up marker: the operating system drops the lock
        # when a process ends, whatever ended it, and that is the whole
        # mechanism - a crafted file could not prove it.
        dead = scratch / "jarvis-dead-run-aaa11111"
        dead.mkdir()
        code = ("import sys; sys.path.insert(0, %r); import run_suites as R\n"
                "from pathlib import Path\n"
                "print(R.claim(Path(%r), 'child') is not None)\n" % (str(HERE), str(dead)))
        child = subprocess.run([sys.executable, "-c", code],
                               capture_output=True, text=True, env=_env(scratch))
        check("CONTROL: a child process claimed the folder and held its lock",
              child.stdout.strip() == "True", child.stdout + child.stderr)
        os.utime(dead, (old, old))

        # A run that is STILL GOING: this process holds the lock.
        live = scratch / "jarvis-live-run-bbb22222"
        live.mkdir()
        live_lock = R.claim(live, "test")
        check("CONTROL: this process holds the live folder's lock", live_lock is not None)
        os.utime(live, (old, old))

        # An older run's folders, from before markers existed: the two shapes
        # that were named in the incident, with nothing to ask about their owner.
        legacy = scratch / "jarvis-staged-backend-eee55555"
        legacy.mkdir()
        os.utime(legacy, (time.time() - (R.REAP_AFTER_UNMARKED + 600),) * 2)
        legacy_state = scratch / "jarvis-suite-state-fff66666"
        legacy_state.mkdir()
        os.utime(legacy_state, (time.time() - (R.REAP_AFTER_UNMARKED + 600),) * 2)

        # Too fresh to be abandoned, even with no owner at all.
        fresh = scratch / "jarvis-fresh-run-ccc33333"
        fresh.mkdir()
        (fresh / R.OWNER_MARKER).write_text("{}", encoding="utf-8")

        # Not this runner's shape.
        other = scratch / "some-other-tool"
        other.mkdir()
        os.utime(other, (old, old))

        # The running sweep's own folder: passed in `keep`, so never a candidate
        # however old it looks.
        mine = scratch / "jarvis-sweep-mine-ddd44444"
        mine.mkdir()
        os.utime(mine, (old, old))

        gone = R.reap_orphans(temp=scratch, keep=(mine,))
        check("the folder the dead run left is reaped", not dead.exists(), gone)
        check("the live run's folder is left ALONE, two hours old and all",
              live.exists(), gone)
        check("an old folder with no marker is reaped (jarvis-staged-backend-)",
              not legacy.exists(), gone)
        check("and so is the other shape from the incident (jarvis-suite-state-)",
              not legacy_state.exists(), gone)
        check("a folder too fresh to be abandoned is left alone", fresh.exists(), gone)
        check("a folder that is not this runner's shape is left alone",
              other.exists(), gone)
        check("the running sweep's own folder is never a candidate", mine.exists(), gone)
        check("the reaper names exactly what it took",
              gone == ["jarvis-dead-run-aaa11111", "jarvis-staged-backend-eee55555",
                       "jarvis-suite-state-fff66666"], gone)
        check("a folder with no marker is not touched until it is a day old",
              R.REAP_AFTER_UNMARKED > R.REAP_AFTER * 4
              and not R._older_than(fresh, R.REAP_AFTER),
              (R.REAP_AFTER, R.REAP_AFTER_UNMARKED))

        # The LOCK, not the pid, is what says "still running": the pid here never
        # changed, only the lock was let go.
        if live_lock is not None:
            os.close(live_lock)
        os.utime(live, (old, old))
        check("once the lock is let go the same folder IS reapable, with the same "
              "pid - which is why a pid alone could not answer this",
              R.reap_orphans(temp=scratch) == ["jarvis-live-run-bbb22222"],
              _names(scratch))
    finally:
        if test_lock is not None:
            os.close(test_lock)
        shutil.rmtree(scratch, ignore_errors=True)


def t_the_shape_is_a_suffix_pattern_not_a_list_of_suite_names():
    """The reaper claims a SHAPE, so a suite added tomorrow is covered without
    editing it, and a name a person chose never is."""
    mine = ["jarvis-sweep-abc12345", "jarvis-staged-backend-p19w120r",
            "jarvis-suite-state-o54lk482", "jarvis-enrol-1bistqo9",
            "jarvis-picture-card-1vd5eh9q", "jarvis-referee-nef3hm6a",
            "jarvis-big-model-_dae1pwr", "jarvis-brain-reads-viacm2at",
            "jarvis-strict-caj_ylfd", "jarvis-front-abc12345"]
    not_mine = ["jarvis", "jarvis-tool", "jarvis-a", "jarvis-.hidden",
                "some-other-tool", "jarvis-framework.toml",
                "jarvis-suite-state", "jarvis-enrol-suite"]
    missed = [n for n in mine if not R.REAPABLE.match(n)]
    taken = [n for n in not_mine if R.REAPABLE.match(n)]
    check("every staging shape the incident names is claimed - both "
          "jarvis-staged-backend- and jarvis-suite-state- included", missed == [], missed)
    check("and no name a person chose is claimed: no random tail, a dot in the "
          "tail, or no `jarvis-` at the front", taken == [], taken)
    check("the shape is a pattern, not a list: _where.SHIPPED's suites are not "
          "named anywhere in it",
          "test_front" not in R.REAPABLE.pattern and "enrol" not in R.REAPABLE.pattern,
          R.REAPABLE.pattern)


def t_stage_still_works_with_no_argument():
    """`stage()` with no argument is what test_suite_state.py calls twice, and
    it removes each folder itself - so it must keep making its own %TEMP%
    folder, not require a root."""
    import inspect
    param = inspect.signature(R.stage).parameters.get("root")
    check("stage() still takes no required argument", param is not None and param.default is None,
          str(inspect.signature(R.stage)))
    check("and stage(root) puts the copy INSIDE that root, so it goes with it",
          "d = root / BACKEND_NAME" in (HERE / "run_suites.py").read_text(encoding="utf-8"))


def t_a_finished_direct_run_leaves_no_folder():
    """THE OTHER HALF OF THE LEAK, and the reason this file has a second
    end-to-end check. #261 closed the SWEEP path. Suites are also run DIRECTLY -
    `python backend/<suite>.py`, which is how every teammate works - and then
    nothing owned their scratch: nearly every suite makes its own
    `jarvis-<suite>-<rand>` at import time and never removes it, one folder per
    suite per run (1,663 under %TEMP% on 2026-10-11, against 581 at 02:20).
    `_where.py` now claims one `jarvis-direct-<rand>` root per PROCESS with the
    same marker and lock as a sweep, points TEMP/TMP/TMPDIR into it, and removes
    it at exit - so one mechanism covers both paths."""
    scratch, lock = _scratch("jarvis-direct-test-")
    temp = scratch / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    try:
        check("CONTROL: nothing is under the temp folder before the run",
              _names(temp) == [], _names(temp))
        r = _run([HERE / SUITE], _env(temp))
        after = _names(temp)
        check("CONTROL: the direct suite really ran",
              f"ok    {SUITE}" in r.stdout or "passed" in r.stdout,
              r.stdout[-1500:] + "\n--stderr--\n" + r.stderr[-800:])
        check("CONTROL: the direct suite passed on its own terms", r.returncode == 0,
              f"exit {r.returncode}\n" + r.stdout[-1500:])
        check("a finished DIRECT run leaves NO jarvis-* folder behind", after == [], after)

        # AND THE CHECK ABOVE CAN FAIL, which is what makes it worth having:
        # with the staging turned off, the very same run leaves the folder where
        # the leak always left it - in the machine's temp folder.
        env = _env(temp)
        env["JARVIS_NO_DIRECT_STAGE"] = "1"
        r2 = _run([HERE / SUITE], env)
        leaked = [n for n in _names(temp) if n.startswith("jarvis-")]
        check("CONTROL: with the staging turned OFF the same run DOES leave a "
              "jarvis-* folder - so the check above is not vacuous",
              bool(leaked) and r2.returncode == 0, _names(temp))
        for name in _names(temp):
            shutil.rmtree(temp / name, ignore_errors=True)
    finally:
        if lock is not None:
            os.close(lock)
        shutil.rmtree(scratch, ignore_errors=True)


def t_private_state_gives_every_run_its_own_home():
    """Check 6: the suites' HOME is a throwaway folder, never the owner's.

    OPENJARVIS_CONFIG_DIR was only half the owner's data. OPENJARVIS_HOME /
    JARVIS_HOME are checked BEFORE it by the modules that keep databases,
    receipts and the inbox, so a run that leaves them unset falls through to
    ~/.openjarvis - the owner's real data, on a patcher run. This is the
    mechanism that stops it, and the header and --state-env are how the other
    two runners learn where it is.
    """
    scratch, lock = _scratch("jarvis-home-test-")
    try:
        state = scratch / R.STATE_NAME
        env = R.private_state({}, HERE, state)
        home = state / R.HOME_NAME
        check("private_state sets OPENJARVIS_HOME to a folder inside the run's state",
              env.get("OPENJARVIS_HOME") == str(home), env.get("OPENJARVIS_HOME"))
        check("... and JARVIS_HOME to the same folder (modules read either name)",
              env.get("JARVIS_HOME") == env.get("OPENJARVIS_HOME"),
              env.get("JARVIS_HOME"))
        check("... and the folder is really made, so a module can write there",
              home.is_dir(), str(home))
        owner_home = Path(os.path.expanduser("~")) / ".openjarvis"
        check("... and it is NOT the owner's real ~/.openjarvis",
              os.path.realpath(str(home)) != os.path.realpath(str(owner_home)),
              (str(home), str(owner_home)))
        words = R.home_words(env)
        check("the run's header names the throwaway home it used",
              str(home) in words and "throwaway" in words, words)

        saved = {k: os.environ.pop(k, None) for k in R.HOME_ENVS}
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                R.state_env(str(state))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        printed = buf.getvalue()
        check("--state-env prints the home variables, so apply-patches.ps1's own "
              "loop sets them and the patcher needs no second list",
              f"OPENJARVIS_HOME={home}" in printed and f"JARVIS_HOME={home}" in printed,
              printed[-600:])
    finally:
        if lock is not None:
            os.close(lock)
        shutil.rmtree(scratch, ignore_errors=True)


def t_private_state_makes_a_stray_model_download_fail_fast():
    """Check 9 (2026-10-18): every run's environment is OFFLINE for model loaders.

    THE DEFECT THIS CLOSES. `test_attention_phrases.py`'s header says "no
    model, no network", but importing the memory store taught fastembed to
    fetch its 5 model files on a cold cache - under the patcher that suite sat
    for 900 s on a download it never wanted. The runner cannot stop a suite
    importing a module; it CAN make the download fail at once in every suite's
    environment (huggingface_hub and friends honour these), which is what this
    checks. The values are the same set `jarvis_child_env` and `jarvis_voices`
    already send, and the switches are FORCED because this is a hermetic-run
    rule - unlike the real-home hatch, a download is never something a suite
    run may opt into.
    """
    scratch, lock = _scratch("jarvis-offline-env-test-")
    try:
        state = scratch / R.STATE_NAME
        expected = {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
            "ANONYMIZED_TELEMETRY": "False",
        }
        env = R.private_state({}, HERE, state)
        got = {k: env.get(k) for k in expected}
        check("the suites' environment tells every model loader it is offline",
              got == expected, got)
        forced = R.private_state({"HF_HUB_OFFLINE": "0"}, HERE, state)
        check("... and a caller's HF_HUB_OFFLINE=0 cannot switch it back on",
              forced.get("HF_HUB_OFFLINE") == "1", forced.get("HF_HUB_OFFLINE"))
        hatch = R.private_state({R.REAL_HOME_ENV: "1"}, HERE, state)
        check("... and the real-home hatch changes where state lives, never "
              "whether a download is allowed",
              hatch.get("HF_HUB_OFFLINE") == "1"
              and hatch.get("TRANSFORMERS_OFFLINE") == "1"
              and not hatch.get("OPENJARVIS_HOME"),
              {k: hatch.get(k) for k in expected})
        # --state-env is the contract apply-patches.ps1 sets its suite loop
        # from, so the switches have to be in what it prints.
        saved = {k: os.environ.pop(k, None) for k in expected}
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                R.state_env(str(state))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        printed = buf.getvalue()
        missing = [k for k, v in expected.items() if f"{k}={v}" not in printed]
        check("--state-env prints the offline switches, so a patcher run gets "
              "them too - no second list", missing == [], missing)
    finally:
        if lock is not None:
            os.close(lock)
        shutil.rmtree(scratch, ignore_errors=True)


def t_a_real_run_leaves_the_home_alone():
    """Check 7: run a real sweep with a fake HOME, and prove a sentinel in its
    ~/.openjarvis was not read into a write, created, or touched."""
    scratch, lock = _scratch("jarvis-home-run-test-")
    try:
        temp = scratch / "temp"
        temp.mkdir()
        owner_home = scratch / "owner-home"
        oj = owner_home / ".openjarvis"
        oj.mkdir(parents=True)
        sentinel = oj / "sentinel.json"
        sentinel.write_text('{"owner": "real data"}', encoding="utf-8")
        before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns,
                  sorted(p.name for p in oj.iterdir()))
        env = _env(temp)
        env["HOME"] = str(owner_home)
        env["USERPROFILE"] = str(owner_home)
        for k in R.HOME_ENVS:
            env.pop(k, None)
        env.pop(R.REAL_HOME_ENV, None)
        r = _run([HERE / "run_suites.py", SUITE], env)
        check("CONTROL: the run passed on its own terms",
              r.returncode == 0,
              f"exit {r.returncode}\n{r.stdout[-1500:]}\n{r.stderr[-800:]}")
        home_line = next((l for l in r.stdout.splitlines() if l.startswith("home: ")), "")
        used = home_line[len("home: "):].split("  ", 1)[0].strip() if home_line else ""
        check("the run's header names a throwaway home",
              bool(used) and "throwaway" in home_line, home_line or r.stdout[:800])
        check("... under this run's own temp area (the fake HOME was not used)",
              bool(used) and os.path.realpath(used).startswith(
                  os.path.realpath(str(scratch))),
              (used, str(scratch)))
        after = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns,
                 sorted(p.name for p in oj.iterdir()))
        check("the fake owner's sentinel file was not written, and nothing new "
              "appeared beside it",
              after == before, (before, after))
    finally:
        if lock is not None:
            os.close(lock)
        shutil.rmtree(scratch, ignore_errors=True)


def t_the_real_home_hatch_is_explicit_and_off_by_default():
    """Check 8: the one way into the real home says so, and is never assumed."""
    scratch, lock = _scratch("jarvis-home-hatch-test-")
    try:
        real = scratch / "owner-home"
        real.mkdir()
        default = R.private_state({"OPENJARVIS_HOME": str(real)}, HERE,
                                  scratch / "state-default")
        check("by DEFAULT an existing OPENJARVIS_HOME is replaced by the throwaway "
              "one (never the real home by accident)",
              default.get("OPENJARVIS_HOME") != str(real)
              and str(scratch / "state-default" / R.HOME_NAME)
              == default.get("OPENJARVIS_HOME"), default.get("OPENJARVIS_HOME"))
        hatched = R.private_state({"OPENJARVIS_HOME": str(real),
                                   R.REAL_HOME_ENV: "1"}, HERE,
                                  scratch / "state-hatch")
        check("with JARVIS_TESTS_USE_REAL_HOME=1 the caller's own home is left alone",
              hatched.get("OPENJARVIS_HOME") == str(real),
              hatched.get("OPENJARVIS_HOME"))
        words = R.home_words(hatched)
        check("... and the header says plainly that the run is NOT hermetic",
              "NOT hermetic" in words and R.REAL_HOME_ENV in words, words)
        saved = {k: os.environ.get(k) for k in (*R.HOME_ENVS, R.REAL_HOME_ENV)}
        try:
            os.environ[R.REAL_HOME_ENV] = "1"
            os.environ["OPENJARVIS_HOME"] = str(real)
            os.environ.pop("JARVIS_HOME", None)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                R.state_env(str(scratch / "state-hatch2"))
            check("--state-env prints NO home line under the hatch, so the "
                  "caller's real home stays theirs",
                  "OPENJARVIS_HOME=" not in buf.getvalue()
                  and "JARVIS_HOME=" not in buf.getvalue(), buf.getvalue()[-400:])
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    finally:
        if lock is not None:
            os.close(lock)
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
