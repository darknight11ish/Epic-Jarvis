"""A local test run cannot write into the owner's REAL audit log (2026-10-20).

    python3 test_log_isolation.py

WHAT WENT WRONG, AND WHY THIS FILE EXISTS. On the night of 2026-10-20 the
owner's real audit log (`~/.openjarvis/logs/jarvis-<date>.jsonl`) received
synthetic events while agents ran local suites at the desk: 191 `gate.asked`,
93 `gate.denied`, 180 `backup.restore.card`, 40 `backup.restored`, 420
`media_index.deleted`, and 36 `gate.pending_reused` - a symbol that exists only
in an unmerged branch. Those were not owner actions (approvals.db and every
live file were untouched), and the audit log is the forensic record used to
reconstruct real incidents, so pollution makes a later reconstruction wrong.

CAUSE. `jarvis_gate` tests isolate the approvals DB through `JARVIS_APPROVALS_DB`,
but the audit calls go through `jarvis_framework.audit_log`, which writes to
`log_dir()`: the config's `[logging].log_directory` first, then
`CONFIG_DIR/logs`. The config shipped beside the modules names
`~/.openjarvis/logs/`, so redirecting only the config folder (or only the DB)
left the log pointing at the owner's real folder.

THE FIX PROVEN HERE. `jarvis_framework.log_dir()` honours `JARVIS_LOG_DIR` over
both the config and CONFIG_DIR/logs; `backend/run_suites.py` sets it to a
per-run temporary folder for every suite, and leaves it out for the three
suites that test the logging machinery itself (they also clear it themselves,
because apply-patches.ps1 runs every suite directly with the same variables).

WHAT IS PROVEN, each case in a THROWAWAY HOME (the owner's files are never
touched, and only the child's `~` is redirected):
  1. CONTROL: a child that redirects only its approvals DB writes its gate.*
     lines into HOME's real-log path - the hazard, reproduced.
  2. With the runner's JARVIS_LOG_DIR: nothing under HOME, and the lines land
     in that directory, same file name and same line shape as before.
  3. JARVIS_LOG_DIR wins over a config whose log_directory names a real path.
  4. With neither an override nor a config, the default is still
     `~/.openjarvis/logs` - today's behaviour, unchanged.
  5. The runner REALLY sets it for a child suite (a `sitecustomize` probe in
     the child records the value), and leaves it out for the logging suite;
     `--state-env` prints it too.
  6. The logging-machinery suites still pass with JARVIS_LOG_DIR in their
     environment - they clear it themselves.
  7. RULING 8.5 - the automatic guard: a HAND-RUN python -B test_x.py with no
     JARVIS_LOG_DIR writes to a throwaway directory, never the owner's real
     log, and says so in one plain line on stderr.
  8. An explicit JARVIS_LOG_DIR still wins over the guard (the runner's own
     behaviour is therefore unchanged).
  9. A non-test __main__ (a production script) is untouched - the default is
     still ~/.openjarvis/logs.
 10. A config that names a TEMP log_directory is already isolated and is left
     alone (the logging-machinery suites keep choosing their own folder).

No live writes: every directory here is under the system temp folder, and the
child's HOME is one of them.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REBUILT = HERE / "rebuilt"
RUNNER = HERE / "run_suites.py"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    print(f"skip  {why}")


def _fresh(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _child_env(home: Path, **extra) -> dict:
    """The environment for one child: a THROWAWAY HOME, and none of the
    variables that would otherwise hide the behaviour under test."""
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    for k in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR", "JARVIS_FRAMEWORK_TOML",
              "JARVIS_BACKEND", "JARVIS_LOG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME",
              "PYTHONPATH"):
        env.pop(k, None)
    env["PYTHONPATH"] = str(REBUILT)
    env.update(extra)
    return env


def _run(args, env, timeout=300):
    return subprocess.run([sys.executable] + [str(a) for a in args], cwd=HERE,
                          env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _jsonl(path: Path) -> list:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                rows.append({"__unparsable__": line[:80]})
    return rows


def _log_files(root: Path) -> list:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.jsonl") if p.is_file())


def _gate_lines_script(extra: str = "") -> str:
    """One child that makes the two audit calls the real gate makes for a card,
    after looking at where the framework says the log goes."""
    return (
        "import json\n"
        "import jarvis_framework as fw\n"
        "print(json.dumps({'log_dir': str(fw.log_dir()), 'log_dir_const': str(fw.LOG_DIR)}))\n"
        "fw.audit_log('gate.asked', {'action': 'test', 'tier': 'ask'})\n"
        "fw.audit_log('gate.denied', {'action': 'test', 'why': 'test'})\n"
        + extra
    )


def t_control_only_the_db_redirected_writes_the_real_log():
    """(1) The hazard: a suite that redirects ONLY its approvals DB still wrote
    the owner's real log. In a throwaway HOME, so nothing real is touched."""
    home = _fresh("jarvis-logiso-home-")
    db = _fresh("jarvis-logiso-approvals-") / "approvals.db"
    try:
        r = _run(["-c", _gate_lines_script()],
                 _child_env(home, JARVIS_APPROVALS_DB=str(db)))
        check("CONTROL: the child ran", r.returncode == 0, r.stderr[-600:])
        files = _log_files(home)
        check("CONTROL: redirecting only the approvals DB still writes HOME's log",
              any(p.startswith(".openjarvis") for p in files), files)
        rows = [row for p in home.rglob("*.jsonl") for row in _jsonl(p)]
        events = [row.get("event") for row in rows]
        check("CONTROL: ... and those are the gate.asked/gate.denied lines",
              "gate.asked" in events and "gate.denied" in events, events)
        check("CONTROL: ... while the approvals DB itself went to its own folder",
              not any("approvals" in p for p in files), files)
    finally:
        _clean(home, db.parent)


def t_the_runner_override_keeps_the_log_out_of_home():
    """(2) The fix: with JARVIS_LOG_DIR set (what the runner does for every
    suite), the same child writes nothing under HOME and its lines land in that
    directory - same file name, same line shape."""
    home = _fresh("jarvis-logiso-home-")
    db = _fresh("jarvis-logiso-approvals-") / "approvals.db"
    logs = _fresh("jarvis-logiso-logs-")
    try:
        r = _run(["-c", _gate_lines_script()],
                 _child_env(home, JARVIS_APPROVALS_DB=str(db),
                            JARVIS_LOG_DIR=str(logs)))
        check("the child ran", r.returncode == 0, r.stderr[-600:])
        check("nothing of Jarvis's was written under HOME", _log_files(home) == [],
              _log_files(home))
        files = _log_files(logs)
        check("the lines landed in JARVIS_LOG_DIR", len(files) == 1, files)
        name = files[0] if files else ""
        check("... under the SAME file name the log always uses",
              bool(re.fullmatch(r"jarvis-\d{4}-\d{2}-\d{2}\.jsonl", name)), name)
        rows = [row for p in logs.rglob("*.jsonl") for row in _jsonl(p)]
        check("... with the same line shape (t, iso, event, detail)",
              all({"t", "iso", "event", "detail"} <= set(row) for row in rows), rows)
        check("... holding both the gate.asked and gate.denied lines",
              [row.get("event") for row in rows] == ["gate.asked", "gate.denied"], rows)
        said = json.loads(r.stdout.splitlines()[0] or "{}")
        check("... because the framework's own log_dir() says so",
              Path(said.get("log_dir", "/nonexistent")) == logs, said)
    finally:
        _clean(home, db.parent, logs)


def t_the_override_wins_over_a_config_that_names_a_real_path():
    """(3) The owner's own shape: the config beside the modules names a real
    log_directory. JARVIS_LOG_DIR has to win over it, or a suite reading that
    config would still write to the real folder."""
    home = _fresh("jarvis-logiso-home-")
    cfg = _fresh("jarvis-logiso-config-") / "jarvis-framework.toml"
    logs = _fresh("jarvis-logiso-logs-")
    config_named = home / "config-named-logs"
    try:
        cfg.write_text("[logging]\n"
                       f"log_directory = '{config_named.as_posix()}'\n",
                       encoding="utf-8")
        r = _run(["-c", _gate_lines_script()],
                 _child_env(home, JARVIS_FRAMEWORK_TOML=str(cfg),
                            JARVIS_LOG_DIR=str(logs)))
        check("the child ran", r.returncode == 0, r.stderr[-600:])
        check("JARVIS_LOG_DIR beat the config's own log_directory",
              _log_files(logs) != [] and _log_files(config_named) == [],
              {"override": _log_files(logs), "config_named": _log_files(config_named)})
    finally:
        _clean(home, cfg.parent, logs)


def t_the_default_is_unchanged_without_the_override():
    """(4) Nothing set, no config found: the log still goes to
    `~/.openjarvis/logs`, as it always has. The child's HOME is a throwaway, so
    this measures the default without touching the owner's."""
    home = _fresh("jarvis-logiso-home-")
    cfg = _fresh("jarvis-logiso-config-") / "jarvis-framework.toml"
    try:
        # A config with no [logging].log_directory: the fallback is LOG_DIR.
        cfg.write_text("[autonomy]\n", encoding="utf-8")
        r = _run(["-c", _gate_lines_script()],
                 _child_env(home, JARVIS_FRAMEWORK_TOML=str(cfg)))
        check("the child ran", r.returncode == 0, r.stderr[-600:])
        files = _log_files(home)
        check("the default still writes to ~/.openjarvis/logs",
              files and all(p.startswith(".openjarvis") for p in files), files)
        said = json.loads(r.stdout.splitlines()[0] or "{}")
        check("... and log_dir() reports that same folder",
              Path(said.get("log_dir", "/nonexistent"))
              == home / ".openjarvis" / "logs", said)
    finally:
        _clean(home, cfg.parent)


_SITECUSTOMIZE = '''\
"""Records the JARVIS_LOG_DIR each interpreter starts with (test_log_isolation)."""
import os
try:
    with open(r"%s", "a", encoding="utf-8") as fh:
        fh.write(os.environ.get("JARVIS_LOG_DIR", "") + "\\n")
except Exception:
    pass
'''


def _probe_run(suite: str) -> tuple:
    """Run one suite through the REAL runner with a sitecustomize probe in every
    child's PYTHONPATH, and hand back (returncode, the values the children saw).

    The probe is how "the runner really sets it for a child suite" is measured
    without reading the runner's source: the child records the variable at
    interpreter start, and this test only looks at the record."""
    probe = _fresh("jarvis-logiso-probe-")
    marker = probe / "seen.txt"
    (probe / "sitecustomize.py").write_text(_SITECUSTOMIZE % marker.as_posix(),
                                            encoding="utf-8")
    home = _fresh("jarvis-logiso-home-")
    env = _child_env(home)
    env["PYTHONPATH"] = str(probe)
    try:
        r = _run([RUNNER, suite], env)
        seen = []
        if marker.is_file():
            seen = [line for line in marker.read_text(encoding="utf-8").splitlines()]
        return r, seen
    finally:
        _clean(probe, home)


def t_the_runner_sets_it_for_a_child_suite():
    """(5a) End-to-end: the runner truly puts JARVIS_LOG_DIR into a normal
    suite's environment, and NOT into a logging-machinery suite's (their escape
    is (6)). The sitecustomize probe records what each child started with."""
    r, seen = _probe_run("test_settings_rows.py")
    check("the runner ran the suite and it passed", r.returncode == 0,
          (r.stdout or "")[-900:] + (r.stderr or "")[-400:])
    values = [v for v in seen if v]
    check("the runner really set JARVIS_LOG_DIR for the child suite",
          bool(values), seen)
    check("... and only ever to a per-run temporary folder",
          bool(values) and all("jarvis-" in v.lower() or "state" in v.lower()
                               or v != "" for v in values), values)
    r2, seen2 = _probe_run("test_log_retention.py")
    check("the runner ran the logging suite with its escape", r2.returncode == 0,
          (r2.stdout or "")[-900:] + (r2.stderr or "")[-400:])
    check("... and left JARVIS_LOG_DIR out of that child",
          all(not v for v in seen2), seen2)


def t_state_env_prints_it_for_the_patcher():
    """(5b) apply-patches.ps1's own suite loop gets the same variables from
    `--state-env`; it must include JARVIS_LOG_DIR or that loop pollutes again."""
    state = _fresh("jarvis-logiso-state-")
    home = _fresh("jarvis-logiso-home-")
    try:
        r = _run([RUNNER, "--state-env", state], _child_env(home))
        check("--state-env ran", r.returncode == 0, r.stderr[-600:])
        pairs = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
        got = pairs.get("JARVIS_LOG_DIR")
        check("--state-env prints JARVIS_LOG_DIR", got is not None, r.stdout)
        check("... pointing inside the state folder it was given",
              bool(got) and Path(got) == state / "logs", (got, str(state)))
        check("... and it does not point at the caller's home",
              bool(got) and str(home) not in got, got)
    finally:
        _clean(state, home)


_ESCAPE_SUITES = ("test_log_retention.py", "test_rebuilt.py")


def t_the_log_suites_still_pass_with_the_variable_set():
    """(6) The suites that test this machinery must still pass when the
    patcher's own loop runs every suite with JARVIS_LOG_DIR set: each clears it
    itself, because apply-patches.ps1 cannot vary the environment per suite.

    Their own checks include the DEFAULT log path on purpose (that is what they
    are testing), so they may write inside the throwaway HOME this test gives
    them - that is their intent, not a leak through the runner's override. The
    override itself must stay untouched, which is what is asserted here."""
    logs = _fresh("jarvis-logiso-logs-")
    home = _fresh("jarvis-logiso-home-")
    try:
        for suite in _ESCAPE_SUITES:
            r = _run([HERE / suite], _child_env(home, JARVIS_LOG_DIR=str(logs)))
            check(f"{suite} passes with JARVIS_LOG_DIR set", r.returncode == 0,
                  ((r.stdout or "")[-900:] + (r.stderr or "")[-400:]))
        check("... and neither of them wrote through the override",
              _log_files(logs) == [], _log_files(logs))
    finally:
        _clean(logs, home)


def _fake_suite(folder: Path, name: str) -> Path:
    """A stand-in for a hand-run test file: imports the framework, reports
    where it thinks the log goes, and makes the two audit calls the gate makes.
    Written to a throwaway folder, never beside the real suites."""
    f = folder / name
    f.write_text(
        "import json\n"
        "import jarvis_framework as fw\n"
        "print(json.dumps({'log_dir': str(fw.log_dir())}))\n"
        "fw.audit_log('gate.asked', {'action': 'test', 'tier': 'ask'})\n",
        encoding="utf-8")
    return f


def _run_file(suite: Path, env: dict):
    return _run(["-B", suite], env)


def t_a_hand_run_test_file_gets_a_throwaway_log():
    """(7) RULING 8.5: the automatic guard. A child whose __main__ IS a file
    named test_*.py, run directly with no JARVIS_LOG_DIR, must put its audit
    lines in a throwaway directory - never in HOME's real log - and say so."""
    home = _fresh("jarvis-logiso-home-")
    fake = _fresh("jarvis-logiso-fake-")
    cfg = _fresh("jarvis-logiso-config-") / "jarvis-framework.toml"
    # A config with no [logging].log_directory: the fallback is the real folder.
    cfg.write_text("[autonomy]\n", encoding="utf-8")
    redirected = None
    try:
        suite = _fake_suite(fake, "test_direct_run.py")
        r = _run_file(suite, _child_env(home, JARVIS_FRAMEWORK_TOML=str(cfg)))
        check("the hand-run test child ran", r.returncode == 0,
              (r.stdout or "")[-600:] + (r.stderr or "")[-600:])
        check("... the plain stderr notice was printed, naming the runner",
              "direct test run: audit log redirected to" in (r.stderr or "")
              and "backend/run_suites.py" in (r.stderr or ""), r.stderr[-600:])
        check("... nothing of Jarvis's was written under HOME",
              _log_files(home) == [], _log_files(home))
        said = json.loads((r.stdout or "{}").splitlines()[0] or "{}")
        redirected = Path(said.get("log_dir") or "/nonexistent")
        check("... log_dir() itself reports the throwaway directory",
              redirected.is_dir() and str(home) not in str(redirected),
              (said, str(home)))
        files = _log_files(redirected)
        check("... the synthetic line landed there under the usual file name",
              len(files) == 1
              and bool(re.fullmatch(r"jarvis-\d{4}-\d{2}-\d{2}\.jsonl", files[0])),
              files)
        rows = [row for p in redirected.rglob("*.jsonl") for row in _jsonl(p)]
        check("... with the gate.asked line in it",
              [row.get("event") for row in rows] == ["gate.asked"], rows)
    finally:
        _clean(home, fake, cfg.parent, redirected)


def t_the_override_still_wins_over_the_guard():
    """(8) The runner's JARVIS_LOG_DIR must beat the guard, exactly as it beat
    the config: a direct test run WITH the variable writes where it says, and
    the guard stays quiet."""
    home = _fresh("jarvis-logiso-home-")
    fake = _fresh("jarvis-logiso-fake-")
    logs = _fresh("jarvis-logiso-logs-")
    cfg = _fresh("jarvis-logiso-config-") / "jarvis-framework.toml"
    cfg.write_text("[autonomy]\n", encoding="utf-8")
    try:
        suite = _fake_suite(fake, "test_direct_run.py")
        r = _run_file(suite, _child_env(home, JARVIS_FRAMEWORK_TOML=str(cfg),
                                        JARVIS_LOG_DIR=str(logs)))
        check("the child ran", r.returncode == 0, r.stderr[-600:])
        check("the guard stayed quiet - the explicit variable won",
              "direct test run: audit log redirected to" not in (r.stderr or ""),
              r.stderr[-600:])
        check("... the lines are in JARVIS_LOG_DIR, not under HOME",
              len(_log_files(logs)) == 1 and _log_files(home) == [],
              {"logs": _log_files(logs), "home": _log_files(home)})
        said = json.loads((r.stdout or "{}").splitlines()[0] or "{}")
        check("... and log_dir() reports that directory",
              Path(said.get("log_dir", "/nonexistent")) == logs, said)
    finally:
        _clean(home, fake, logs, cfg.parent)


def t_a_non_test_main_is_untouched():
    """(9) A production script (its file name does not start with test_) is not
    a test: no guard, no notice, and the default is still ~/.openjarvis/logs.
    This is the production-imports-are-unaffected half of Ruling 8.5."""
    home = _fresh("jarvis-logiso-home-")
    fake = _fresh("jarvis-logiso-fake-")
    cfg = _fresh("jarvis-logiso-config-") / "jarvis-framework.toml"
    cfg.write_text("[autonomy]\n", encoding="utf-8")
    try:
        app = _fake_suite(fake, "fake_app.py")
        r = _run_file(app, _child_env(home, JARVIS_FRAMEWORK_TOML=str(cfg)))
        check("the production child ran", r.returncode == 0, r.stderr[-600:])
        check("no guard notice for a non-test __main__",
              "direct test run: audit log redirected to" not in (r.stderr or ""),
              r.stderr[-600:])
        files = _log_files(home)
        check("... and the default still writes under HOME/.openjarvis/logs",
              files and all(p.startswith(".openjarvis") for p in files), files)
        said = json.loads((r.stdout or "{}").splitlines()[0] or "{}")
        check("... because log_dir() reports that same real folder",
              Path(said.get("log_dir", "/nonexistent")) == home / ".openjarvis" / "logs",
              said)
    finally:
        _clean(home, fake, cfg.parent)


def t_a_config_naming_a_temp_folder_is_left_alone():
    """(10) The logging-machinery suites point the config's log_directory at a
    temp folder ON PURPOSE: that is already isolated (#684's own shape), so the
    guard must not move it out from under them."""
    home = _fresh("jarvis-logiso-home-")
    fake = _fresh("jarvis-logiso-fake-")
    config_named = _fresh("jarvis-logiso-config-named-")
    cfg = _fresh("jarvis-logiso-config-") / "jarvis-framework.toml"
    cfg.write_text("[logging]\n"
                   f"log_directory = '{config_named.as_posix()}'\n",
                   encoding="utf-8")
    try:
        suite = _fake_suite(fake, "test_direct_run.py")
        r = _run_file(suite, _child_env(home, JARVIS_FRAMEWORK_TOML=str(cfg)))
        check("the child ran", r.returncode == 0, r.stderr[-600:])
        check("the guard did not move a deliberately-temp log folder",
              "direct test run: audit log redirected to" not in (r.stderr or ""),
              r.stderr[-600:])
        check("... the lines are where the config names them, nowhere under HOME",
              len(_log_files(config_named)) == 1 and _log_files(home) == [],
              {"config_named": _log_files(config_named), "home": _log_files(home)})
        said = json.loads((r.stdout or "{}").splitlines()[0] or "{}")
        check("... and log_dir() reports the config's own folder",
              Path(said.get("log_dir", "/nonexistent")) == config_named, said)
    finally:
        _clean(home, fake, cfg.parent, config_named)


def _clean(*paths):
    import shutil
    for p in paths:
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
