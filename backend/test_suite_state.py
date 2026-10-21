"""A test run writes nothing into the owner's home folder (audit S3).

    python3 test_suite_state.py

Nine suites run real code that writes the audit log - task.stop,
voice.training.decided, wiki.asked - and it went to ~/.openjarvis/logs: 131
fake events in the owner's REAL audit log per run, among the real ones.
run_suites.py (and apply-patches.ps1's step 6, through `run_suites.py
--state-env`) now gives each run a temporary config folder and audit log.

Since 2026-10-20 the audit log is moved by `JARVIS_LOG_DIR` as well, because
moving the config folder alone did not move it (the config beside the modules
names ~/.openjarvis/logs/). This suite is one of the three that test the
logging machinery, so it clears that variable and the runner leaves it out for
it (`run_suites.LOG_MACHINERY_SUITES`). `test_log_isolation.py` proves the
variable and, since Ruling 8.5 (2026-10-21), the automatic guard too.

RULING 8.5 CHANGED WHAT A CONTROL CAN EXPECT. A hand-run `test_*.py` main no
longer writes the owner's real log at all: `jarvis_framework.log_dir()` moves
it to a throwaway directory and says so on stderr. So the CONTROL that used to
prove "a direct run DOES write HOME's log" now proves the new truth - the
guard redirected it, and HOME holds nothing of Jarvis's. The older lesson (the
config's `log_directory` alone does not move the log, because the shipped
config names ~/.openjarvis/logs/) is kept by a control whose `__main__` is a
PRODUCTION-STYLE script, not a test file - the guard never touches those.

Each case below runs a child with HOME (and USERPROFILE, which is Windows'
"~") pointed at an empty folder, and looks in it afterwards.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# This suite tests the runner's OWN state isolation, including the CONTROL runs
# that are deliberately unisolated to prove a leak exists. The runner therefore
# leaves JARVIS_LOG_DIR out for it (run_suites' LOG_MACHINERY_SUITES) - and this
# clears it here too, because apply-patches.ps1 runs every suite directly with
# the variables `--state-env` printed, which include it.
os.environ.pop("JARVIS_LOG_DIR", None)
import run_suites as R  # noqa: E402

try:
    import tomllib
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

FAILED, PASSED = [], []
SKIPPED = []
SUITE = "test_task_control.py"      # writes task.* audit events through jarvis_framework
# Imports jarvis_framework from rebuilt/, where the repository's own config sits
# beside it - with log_directory = "~/.openjarvis/logs/".
SUITE_REBUILT = "test_voice_enroll.py"
TOML = HERE / "rebuilt" / "jarvis-framework.toml"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _env(home: Path, **extra) -> dict:
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONDONTWRITEBYTECODE="1")
    for k in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR", "JARVIS_FRAMEWORK_TOML",
              "JARVIS_BACKEND", "JARVIS_LOG_DIR"):
        env.pop(k, None)
    env.update(extra)
    return env


def _written(home: Path) -> list:
    return sorted(str(p.relative_to(home)) for p in home.rglob("*") if p.is_file())


def _jarvis_files(home: Path) -> list:
    """Only Jarvis's own folder: onnxruntime (which the voice suites load)
    keeps a cache in ~/.cache whatever anyone does."""
    return [p for p in _written(home) if not p.startswith(".cache")]


_DIRECT_REDIRECT = re.compile(r"direct test run: audit log redirected to (.+?);")


def _redirected(result) -> "Path | None":
    """The throwaway audit-log folder the Ruling 8.5 guard named on stderr."""
    m = _DIRECT_REDIRECT.search(result.stderr or "")
    return Path(m.group(1)) if m else None


#: A PRODUCTION-STYLE child: its file name is not test_*, so the Ruling 8.5
#: guard leaves it alone - which is how the old "config alone is not enough"
#: lesson can still be measured.
_CONTROL_SCRIPT = (
    "import jarvis_framework as fw\n"
    "fw.audit_log('gate.asked', {'action': 'control', 'why': 'config log_directory'})\n"
)


def _prod_style_child(folder: Path, name: str = "owner_like_app.py") -> Path:
    f = folder / name
    f.write_text(_CONTROL_SCRIPT, encoding="utf-8")
    return f


def _run(args, env):
    return subprocess.run([sys.executable] + [str(a) for a in args], cwd=HERE, env=env,
                          capture_output=True, text=True, timeout=600)


def _owner_like_backend() -> Path:
    """A backend folder shaped like the owner's: the shipped modules, and the
    shipped config BESIDE them, whose log_directory is ~/.openjarvis/logs/."""
    d = R.stage()
    shutil.copy2(TOML, d / R.CONFIG_NAME)
    return d


def t_the_config_copy_changes_only_log_directory():
    if tomllib is None:
        return skip("no tomllib (Python < 3.11)")
    where = Path(tempfile.mkdtemp(prefix="jarvis-state-")) / "logs"
    real = tomllib.loads(TOML.read_text(encoding="utf-8"))
    check("CONTROL: the shipped config sends the audit log to ~/.openjarvis/logs",
          real["logging"]["log_directory"].startswith("~"), real["logging"])
    copy = tomllib.loads(R._with_log_directory(TOML.read_text(encoding="utf-8"), where))
    check("the copy's log_directory is the temporary folder",
          copy["logging"]["log_directory"] == where.as_posix(), copy["logging"])
    copy["logging"]["log_directory"] = real["logging"]["log_directory"]
    check("and everything else in it is the same", copy == real)
    for text in ("[autonomy]\nx = 1\n", "[logging]\nenabled = true\n[other]\ny = 2\n"):
        got = tomllib.loads(R._with_log_directory(text, where))
        check(f"a config without the key gets it ({text.splitlines()[0]})",
              got["logging"]["log_directory"] == where.as_posix(), got)


def t_a_ci_run_leaves_home_alone():
    staged = R.stage()
    try:
        for suite in (SUITE, SUITE_REBUILT):
            home = Path(tempfile.mkdtemp(prefix="jarvis-empty-home-"))
            try:
                r_direct = _run([HERE / suite], _env(home, JARVIS_BACKEND=str(staged)))
                before = _jarvis_files(home)
                check(f"CONTROL (Ruling 8.5): {suite} run on its own writes NOTHING "
                      f"of Jarvis's into HOME", before == [], before)
                where_direct = _redirected(r_direct)
                check("... and the guard says it moved the audit log to a temporary folder",
                      where_direct is not None and where_direct.is_dir()
                      and str(home) not in str(where_direct),
                      (r_direct.stderr or "")[-600:] + " || " + str(where_direct))
                files_direct = (_jarvis_files(where_direct)
                                if where_direct is not None and where_direct.is_dir() else [])
                check(f"... which really received {suite}'s audit lines",
                      any(re.fullmatch(r"jarvis-\d{4}-\d{2}-\d{2}\.jsonl", f)
                          for f in files_direct), files_direct)
                if where_direct is not None:
                    shutil.rmtree(where_direct, ignore_errors=True)
                shutil.rmtree(home)
                home.mkdir()
                r = _run([HERE / "run_suites.py", suite], _env(home))
                check(f"run_suites.py {suite} passes", r.returncode == 0, r.stdout[-800:])
                # Only Jarvis's own folder counts: onnxruntime (which the voice
                # suites load) keeps a cache in ~/.cache whatever anyone does.
                left = [p for p in _written(home) if not p.startswith(".cache")]
                check(f"and {suite} writes nothing of Jarvis's into HOME", left == [], left)
            finally:
                shutil.rmtree(home, ignore_errors=True)
    finally:
        shutil.rmtree(staged, ignore_errors=True)


def t_an_owner_like_run_leaves_home_alone():
    """The owner's PC: the config beside the modules names ~/.openjarvis/logs,
    which the audit log obeys over the config folder."""
    home = Path(tempfile.mkdtemp(prefix="jarvis-empty-home-"))
    scripts = Path(tempfile.mkdtemp(prefix="jarvis-control-"))
    backend = _owner_like_backend()
    try:
        child = _prod_style_child(scripts)
        env = _env(home, JARVIS_BACKEND=str(backend),
                   OPENJARVIS_CONFIG_DIR=str(home / "elsewhere"))
        env["PYTHONPATH"] = str(backend)
        r_control = _run([child], env)
        before = _jarvis_files(home)
        check("CONTROL: moving only the config folder is not enough - the config's "
              "log_directory still sends the log to HOME for a production-style "
              "main (not a test_ file, which the Ruling 8.5 guard would redirect)",
              r_control.returncode == 0
              and any(p.startswith(".openjarvis") for p in before),
              (before, (r_control.stderr or "")[-500:]))
        check("... and the guard stayed out of it (no redirect notice for that child)",
              "direct test run: audit log redirected to" not in (r_control.stderr or ""),
              (r_control.stderr or "")[-500:])
        shutil.rmtree(home)
        home.mkdir()
        r = _run([HERE / "run_suites.py", SUITE], _env(home, JARVIS_BACKEND=str(backend)))
        check(f"run_suites.py {SUITE} passes against it", r.returncode == 0, r.stdout[-800:])
        check("and writes nothing at all into HOME", _written(home) == [], _written(home))
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(scripts, ignore_errors=True)
        shutil.rmtree(backend, ignore_errors=True)


def t_apply_patches_gets_the_same_variables():
    home = Path(tempfile.mkdtemp(prefix="jarvis-empty-home-"))
    backend = _owner_like_backend()
    state = Path(tempfile.mkdtemp(prefix="jarvis-state-"))
    try:
        r = _run([HERE / "run_suites.py", "--state-env", state],
                 _env(home, JARVIS_BACKEND=str(backend)))
        pairs = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
        check("--state-env prints the config folder variables, pointing into DIR",
              pairs.get("OPENJARVIS_CONFIG_DIR", "").startswith(str(state))
              and pairs.get("JARVIS_CONFIG_DIR") == pairs.get("OPENJARVIS_CONFIG_DIR"), r.stdout)
        toml = Path(pairs.get("JARVIS_FRAMEWORK_TOML", "/nonexistent"))
        check("and a copy of the backend's config, its log_directory inside DIR",
              toml.is_file() and str(state.as_posix()) in toml.read_text(encoding="utf-8"),
              r.stdout)
        check("and writes nothing into HOME", _written(home) == [], _written(home))
        ps1 = (HERE.parent / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
        loop = ps1.index("foreach ($t in $tests)")
        check("apply-patches.ps1 asks for them before its test loop",
              -1 < ps1.find("--state-env") < loop)
    finally:
        for d in (home, backend, state):
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
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
    sys.exit(1 if FAILED else 0)
