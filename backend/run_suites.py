"""Run every backend suite that can run without the owner's PC, and skip - by
name, with the reason - the ones that cannot. This is what CI runs.

    python3 backend/run_suites.py

WHY A RUNNER AND NOT JUST A LOOP. About twenty suites test a patch against the
file it patches - jarvis_hud.py, jarvis_gate.py, jarvis_extract.py,
jarvis_models.py - and those files live only on the owner's PC, never in this
repository (backend/.gitignore refuses them). Run anywhere else, those suites
fail with an ImportError that looks exactly like a broken patch. A CI job
that is always red teaches everyone to ignore it, so those suites are
SKIPPED here, each one named with the files it is waiting for - and only
while those files are absent. Every other suite must pass.

THE BACKEND IT RUNS AGAINST. Not this folder: a temporary folder holding a
copy of every module apply-patches.ps1 ships (backend/_where.py SHIPPED),
side by side, the way they sit on the owner's PC - rebuilt/ flattened in.
So the suites exercise the shipped LAYOUT, not the repository's folders, and
a module that only works because of where it sits in this repository fails
here. Set JARVIS_BACKEND to run against a real backend instead; then nothing
is staged, and a suite is skipped only if its files are really not there.

THE OWNER'S STATE IS LEFT ALONE. The suites run real code that writes -
the audit log, approval queues, switch files - so each run gets a temporary
config folder and audit log (private_state below), deleted afterwards.
apply-patches.ps1 asks for the same variables with `--state-env DIR`.

The skip list is explicit, not guessed from a failure: a suite that is not in
it and fails is a failure, and a suite in it whose files ARE present runs.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

# Suite -> the backend files it needs. Found by running each suite in a
# checkout without them and reading which import or file read failed first,
# then reading the suite for its other imports and BACKEND / "..." reads.
# Every entry names at least one file that only the owner's PC has
# (OWNER_FILES), which is what makes it skip here; the rebuilt modules it
# also uses are listed for completeness. test_embedding_guard.py is NOT here:
# it needs only jarvis_memory.py, the staged rebuilt copy satisfies it, and
# it passes against that copy - so it runs.
NEEDS_OWNER = {
    "test_appearance.py": ("jarvis_hud.py",),
    "test_approval_notice.py": ("jarvis_gate.py", "jarvis_events.py"),
    "test_bitemporal.py": ("jarvis_hud.py", "jarvis_memory.py"),
    "test_decide_once.py": ("jarvis_extract.py", "jarvis_hud.py", "jarvis_memory.py"),
    "test_degrade_filter.py": ("jarvis_hud.py",),
    "test_documents_honesty.py": ("jarvis_hud.py",),
    "test_events_pump.py": ("jarvis_hud.py", "jarvis_events.py"),
    "test_extraction_wiring.py": ("jarvis_hud.py", "jarvis_events.py"),
    "test_gate_egress.py": ("jarvis_gate.py", "jarvis_hud.py", "jarvis_events.py"),
    "test_gate_outcome.py": ("jarvis_gate.py",),
    "test_gate_push.py": ("jarvis_gate.py",),
    "test_gpu_offload.py": ("jarvis_hud.py", "jarvis_models.py"),
    "test_import_history.py": ("jarvis_extract.py", "jarvis_memory.py"),
    "test_memory_noise.py": ("jarvis_extract.py", "jarvis_hud.py", "jarvis_memory.py"),
    "test_memory_pane.py": ("jarvis_hud.py",),
    "test_memory_prefix.py": ("jarvis_hud.py",),
    "test_memory_safety.py": ("jarvis_extract.py", "jarvis_memory.py"),
    # It lifts the real `_completions_url` and `_auth_headers` out of
    # jarvis_hud.py, so it needs that file - and, since 2026-10-06, the real
    # jarvis_chatbot_api too (the cloud lane's resolver): without it the
    # module-level `import jarvis_chatbot_api` inside the lifted function
    # fails and every cloud check would read as "no lane".
    "test_ollama_direct.py": ("jarvis_hud.py",),
    "test_token_file.py": ("jarvis_hud.py",),
    "test_voice_503.py": ("jarvis_hud.py",),
}

# The files only the owner's PC has. Checked below: every NEEDS_OWNER entry
# must name one, so the list cannot be used to skip a suite that could run.
OWNER_FILES = {"jarvis_hud.py", "jarvis_gate.py", "jarvis_extract.py", "jarvis_models.py",
               "jarvis_skills.py"}


CONFIG_NAME = "jarvis-framework.toml"

#: "N passed" / "N skipped" / "N failed" as a suite prints them at the end.
#: Looked up by the word, not by position: every harness in this folder prints
#: the three, but the older ones print them in a different order.
_SUMMARY = {"passed": re.compile(r"(\d+)\s+passed\b"),
            "skipped": re.compile(r"(\d+)\s+skipped\b"),
            "failed": re.compile(r"(\d+)\s+failed\b")}

#: What a reader counts by eye, for a suite that prints no summary at all:
#: `ok` and `FAIL` from check(), `skip` from skip() (or an older harness's own
#: "SKIP  <name>"). The word has to end there or be followed by a space or a
#: colon - test_topics.py has a real check named "skipped-this-week is a number
#: per topic", and counting a check as a skip would be this bug in reverse.
_LINE = {"passed": re.compile(r"^ok\b"),
         "skipped": re.compile(r"^skip(ped)?(?=[ \t:]|$)", re.I),
         "failed": re.compile(r"^FAIL\b")}

#: unittest's own summary, for the three suites built on it (test_rebuilt.py,
#: test_speech.py, test_thinking.py). Without this the three of them reported as
#: "0 passed, 0 skipped, 0 failed" - the same numbers a suite that printed
#: nothing at all gives, which is the one shape this runner must never confuse
#: with a pass. It matters two ways round: unittest exits 0 just as happily
#: having run NO tests (every method renamed away, or a TestCase that stopped
#: matching `unittest.main()`'s default), and a suite that prints nothing is
#: exactly the class `tools/check_vacuous_checks.py` exists for one level down.
#: unittest counts a skipped test inside "Ran N tests", so the passes are what
#: is left after the skips and the failures, not the total on its own.
_UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
_UNITTEST_BAD = re.compile(r"^FAILED \(([^)]*)\)", re.M)
_UNITTEST_SKIPPED = re.compile(r"skipped=(\d+)")

#: A line that LOOKS like a suite's own summary: a count, then "passed" or
#: "failed". Used to find the summary anywhere in the output rather than only in
#: its last four lines - see `_last_summary_line`.
_SUMMARY_LINE = re.compile(r"^\s*\d+\s+(?:passed|failed)\b")


def _last_summary_line(out: str) -> str:
    """The last line of `out` that carries a suite's own summary, or "".

    WHY NOT THE LAST FOUR LINES. That is what this used to read, and a suite
    that prints a traceback AFTER its summary pushed the summary out of the
    window: `test_news.py` failed with a traceback on stderr and the runner
    printed "FAIL test_news.py (exit 1) 65 passed, 0 skipped, 0 failed" beside
    it. The verdict was still right - it comes from the exit code - but the
    numbers were wrong, and the numbers are what a reader believes. The last
    line that looks like a summary is the suite's own last word whatever
    happens after it."""
    last = ""
    for line in out.splitlines():
        if _SUMMARY_LINE.match(line):
            last = line
    return last


def counts(out: str) -> dict:
    """{'passed': n, 'skipped': n, 'failed': n} for one suite's output.

    The suite's OWN final line is believed when it has one: it knows what it
    counted, and a `skip()` no longer lands in its "passed". A unittest suite
    is believed through unittest's own summary. Only a suite that prints
    neither is counted from its own lines."""
    summary = _last_summary_line(out)
    got = {}
    for word, pat in _SUMMARY.items():
        m = pat.search(summary)
        got[word] = int(m.group(1)) if m else None
    if got["passed"] is not None and got["failed"] is not None:
        return {"passed": got["passed"], "skipped": got["skipped"] or 0,
                "failed": got["failed"]}
    m = _UNITTEST_RAN.search(out)
    if m:
        total = int(m.group(1))
        bad = _UNITTEST_BAD.search(out)
        failed = 0
        if bad:
            for _kind, number in re.findall(r"(failures|errors)=(\d+)", bad.group(1)):
                failed += int(number)
        skipped = _UNITTEST_SKIPPED.search(out)
        skipped = int(skipped.group(1)) if skipped else 0
        return {"passed": max(0, total - skipped - failed), "skipped": skipped,
                "failed": failed}
    counted = {w: 0 for w in _LINE}
    for line in out.splitlines():
        for word, pat in _LINE.items():
            if pat.match(line):
                counted[word] += 1
                break
    return counted


def _config_the_suites_would_read(env: dict, backend: Path):
    """The jarvis-framework.toml jarvis_framework.config_path() would find for
    a suite, BEFORE the config folder is moved: the override, the config
    folder, beside the modules, one folder up - and last this repository's
    rebuilt/ copy, which is what a suite that imports rebuilt/ directly
    (test_voice_enroll, test_speech, ...) finds beside jarvis_framework.py.
    Its log_directory is ~/.openjarvis/logs/ too."""
    raw = env.get("JARVIS_FRAMEWORK_TOML")
    home_cfg = env.get("OPENJARVIS_CONFIG_DIR") or env.get("JARVIS_CONFIG_DIR")
    cfg_dir = Path(os.path.expanduser(home_cfg)) if home_cfg \
        else Path(os.path.expanduser("~")) / ".openjarvis"
    for c in (Path(os.path.expanduser(raw)) if raw else None, cfg_dir / CONFIG_NAME,
              backend / CONFIG_NAME, backend.parent / CONFIG_NAME,
              HERE / "rebuilt" / CONFIG_NAME):
        if c is not None and c.is_file():
            return c
    return None


def _with_log_directory(toml: str, where: Path) -> str:
    """`toml` with [logging].log_directory set to `where` - a TOML literal
    string, forward slashes, so a Windows path needs no escaping."""
    line = f"log_directory = '{where.as_posix()}'"
    lines = toml.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "[logging]")
    except StopIteration:
        return toml.rstrip("\n") + f"\n\n[logging]\n{line}\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
               len(lines))
    for i in range(start + 1, end):
        if lines[i].split("=", 1)[0].strip() == "log_directory":
            lines[i] = line
            break
    else:
        lines.insert(start + 1, line)
    return "\n".join(lines) + "\n"


def private_state(env: dict, backend: Path, where: Path) -> dict:
    """`env`, changed so the suites write their state under `where`, never
    into the owner's real config folder.

    Several suites run real code that writes: the audit log (131 fake
    events - "voice.training.decided", "wiki.asked", "task.stop" - landed
    in ~/.openjarvis/logs in one run), approval queues, switch files. That
    folder is jarvis_framework._config_dir(): OPENJARVIS_CONFIG_DIR, then
    JARVIS_CONFIG_DIR, then ~/.openjarvis. Both variables now point at a
    temporary folder.

    That alone is not enough on the owner's PC: the config beside the
    modules sets [logging].log_directory = "~/.openjarvis/logs/", which the
    audit log honours over the config folder. So that config is copied into
    the temporary folder with only log_directory changed, and
    JARVIS_FRAMEWORK_TOML points at the copy. A suite that sets
    JARVIS_FRAMEWORK_TOML itself (test_rebuilt, test_router_private_terms)
    still reads the file it chose.

    PYTHONIOENCODING is set here too, and it is not about state: it is a
    bug this runner had on Windows. A Windows console (and a pipe) defaults
    Python's stdout to the ANSI code page, cp1252 here, and 56 of the
    suites print a non-ASCII character that cp1252 cannot encode - the
    Cyrillic host test_youtube.py refuses, an em dash, a curly quote. The
    print raises UnicodeEncodeError, the suite exits 1, and it is reported
    as a FAILING SUITE when the check itself passed. test_youtube.py failed
    that way in both the 15:48 and the 19:09 runs on 2026-10-03, for a link
    its parser had correctly refused. jarvis_voices.py:2490 and
    backend/README.md's own preflight line already set this variable for
    the same reason; the runners simply never did."""
    out = dict(env)
    out["PYTHONIOENCODING"] = "utf-8"
    cfg = where / "config"
    logs = where / "logs"
    cfg.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    found = _config_the_suites_would_read(env, backend)
    out["OPENJARVIS_CONFIG_DIR"] = str(cfg)
    out["JARVIS_CONFIG_DIR"] = str(cfg)
    if found is not None:
        copy = cfg / CONFIG_NAME
        copy.write_text(_with_log_directory(found.read_text(encoding="utf-8"), logs),
                        encoding="utf-8")
        out["JARVIS_FRAMEWORK_TOML"] = str(copy)
    return out


def stage() -> Path:
    d = Path(tempfile.mkdtemp(prefix="jarvis-staged-backend-"))
    for rel in _where.SHIPPED:
        shutil.copy2(HERE / rel, d / rel.rsplit("/", 1)[-1])
    return d


def suite_result(name: str, took: str, code, stdout, stderr, why="") -> tuple:
    """How one finished suite is reported: ("ok"|"FAIL", counts, the line, the
    lines to echo under it). Every suite is reported, including the one that
    printed nothing at all - which is why `stdout`/`stderr` may be None and
    are read as empty text, never assumed to be a string. That None is not
    hypothetical: it is what subprocess leaves behind when a suite is killed
    by a signal, or when the spawn itself fails. Reading it as a string
    raised TypeError at `r.stdout + r.stderr` and ended the whole sweep, so
    the results of every suite after it were never printed.

    `why` is the runner's own reason for a suite that never produced a line of
    its own - a spawn that raised, say. The suite's counts are honestly zero,
    so the reason is what says the suite did not run at all.

    A suite that exits 0 having reported NO checks at all is the one shape this
    runner must never call a pass. It cannot be told apart from a suite whose
    checks all vanished - a loop over an empty list, a guard that can never be
    true, a main() that returns before printing - and the browser suite found on
    2026-10-05 did exactly that: it exited 0 having run nothing, and stayed
    green. So exit 0 with every count zero is reported as failed, and the reason
    says which shape it was.

    Only exit 0 is "ok". Anything else is reported as failed - including a
    suite the runner could not read an exit code for at all, which is why
    the check is `code == 0` and not `code == 0 or code is None`."""
    out = (stdout or "") + (stderr or "")
    n = counts(out)
    said = f"{n['passed']} passed, {n['skipped']} skipped, {n['failed']} failed"
    silent = code == 0 and not any(n.values())
    if silent:
        code = "printed no checks"
    if code == 0:
        # The numbers are shown whenever they are not already on the suite's
        # own last line: a suite that skipped something (its own line would
        # have said so), or one that prints no "N passed" summary of its own -
        # the three unittest suites, and the older harnesses counted from
        # their own `ok` lines. Otherwise a reader sees
        # `ok  test_speech.py  2.0s` with no idea whether 25 checks ran or
        # none did, which is the blind spot this runner closed.
        tail = "\n".join(out.strip().splitlines()[-4:])
        own_summary = _SUMMARY["passed"].search(tail)
        note = f"  {said}" if (n["skipped"] or not own_summary) else ""
        return "ok", n, f"ok    {name:<34} {took}{note}", []
    if not out.strip() and not why:
        # a suite that said nothing is still reported in full: which suite,
        # what it exited with, and that there was no output to quote.
        said += "  (no output)"
    line = f"FAIL  {name:<34} {took}  (exit {code})  {said}"
    echo = [f"      {why}"] if why else []
    if silent:
        echo.append("      it exited 0 having printed no `ok`, `FAIL` or `skip` line "
                    "and no summary - so nothing here proves that any check ran. A "
                    "check that cannot fail, one level up.")
    echo += ["      " + l for l in out.splitlines()
             if l.startswith("FAIL") or "Traceback" in l or "failed:" in l]
    # One GitHub annotation is built from this line, and a spawn failure
    # carries the operating system's whole sentence. Capped so the suite's
    # name and its exit code are never pushed out of the annotation; the full
    # text is echoed under the line.
    return "FAIL", n, line[:200], echo


def main(only=()) -> int:
    """Every suite, or only the ones named (`run_suites.py test_x.py ...`).

    A name given on the command line that is not a suite here is a FAILURE, not
    an empty run: a sweep that prints "0 passed, 0 skipped, 0 failed" and exits
    0 for a mistyped name is the same lie one level up from the suites this
    runner exists to distrust (`backend/test_jobs.py` is named in the docs but
    lives only on the owner's PC, so a typo there was easy to make)."""
    real = os.environ.get("JARVIS_BACKEND")
    backend = Path(real).resolve() if real else stage()
    print(f"backend: {backend}" + ("" if real else "  (staged: every shipped module, flattened)"))
    known = sorted(HERE.glob("test_*.py"))
    suites = [s for s in known if s.name in only] if only else known
    names = {s.name for s in suites}
    unknown = [n for n in only if n not in {s.name for s in known}]
    stale = [] if only else sorted(set(NEEDS_OWNER) - names)
    passed, failed, skipped = [], [], []
    # The checks inside the suites that ran, summed from what each suite
    # reported. A suite that exits 0 having skipped every check it has is still
    # "ok" here - the numbers beside it are what say so.
    ran = {"passed": 0, "skipped": 0, "failed": 0}
    if unknown:
        print(f"FAIL  no suite here is named: {', '.join(unknown)}")
        failed += unknown
    if stale:
        print(f"FAIL  run_suites.py lists suites that do not exist: {stale}")
        failed += stale
    no_owner = sorted(k for k, v in NEEDS_OWNER.items() if not set(v) & OWNER_FILES)
    if no_owner:
        print(f"FAIL  run_suites.py skips suites that need nothing from the owner's PC: {no_owner}")
        failed += no_owner
    state = Path(tempfile.mkdtemp(prefix="jarvis-suite-state-"))
    env = private_state(dict(os.environ, JARVIS_BACKEND=str(backend),
                             PYTHONDONTWRITEBYTECODE="1"), backend, state)
    print(f"state: {state}  (config folder and audit log for this run, not yours)")
    for s in suites:
        need = NEEDS_OWNER.get(s.name, ())
        absent = [f for f in need if not (backend / f).is_file()]
        if absent:
            skipped.append(s.name)
            print(f"skip  {s.name:<34} needs the owner's {', '.join(absent)}")
            continue
        t0 = time.time()
        why = ""
        try:
            # errors="replace" and an explicit utf-8 decode: the child is run
            # with PYTHONIOENCODING=utf-8 (see private_state), so decoding its
            # output with the console's own code page raised
            # UnicodeDecodeError INSIDE subprocess's reader thread, which left
            # r.stdout as None and crashed this whole runner with
            # "unsupported operand type(s) for +: 'NoneType' and 'str'" - one
            # suite's non-ASCII output taking the entire run down with it.
            # That happened on 2026-10-03, at test_mail_mask.py.
            r = subprocess.run([sys.executable, str(s)], cwd=HERE, env=env,
                               capture_output=True, text=True, timeout=900,
                               encoding="utf-8", errors="replace")
            code, got_out, got_err = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            code, got_out, got_err = "timeout", "", ""
        except OSError as exc:
            # The child never started at all - an executable that cannot run,
            # a path that is gone, a permission the sandbox refuses. The suite
            # has no exit code to compare with 0, so it is FAILED and the
            # reason is carried into the report; continuing is the point,
            # because the suites after this one still have results worth
            # printing.
            code, got_out, got_err = None, "", ""
            why = f"the suite could not be started: {exc}"
        took = f"{time.time() - t0:5.1f}s"
        status, n, line, echo = suite_result(s.name, took, code, got_out, got_err, why)
        for w in ran:
            ran[w] += n[w]
        if status == "ok":
            passed.append(s.name)
            print(line)
            continue
        failed.append(s.name)
        print(line)
        for el in echo:
            print(el)
        tail = ((got_out or "") + (got_err or "")).strip().splitlines()[-40:]
        print("\n".join("      " + l for l in tail))
    if not real:
        shutil.rmtree(backend, ignore_errors=True)
    shutil.rmtree(state, ignore_errors=True)
    print(f"\n{ran['passed']} passed, {ran['skipped']} skipped, {ran['failed']} failed")
    if ran["skipped"] or skipped:
        print(f"      (a skip is a check that could not run here: {ran['skipped']} inside the "
              f"suites above, {len(skipped)} whole suite(s) that need files which live only on "
              f"the owner's PC)")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


def state_env(where: str) -> int:
    """`--state-env DIR`: print, one KEY=VALUE a line, the variables that send
    the suites' state to DIR. apply-patches.ps1 runs the suites itself, one by
    one, and sets these first - so the two runners cannot disagree about
    where test state goes.

    PYTHONIOENCODING is printed here for a different reason: apply-patches.ps1
    runs each suite as its own process, so without it in this list the suites
    it runs would still be on the console's code page and still crash on a
    non-ASCII suite name (see private_state). A variable already set to this
    value is not printed, which is fine - the script's own copy is the same."""
    backend = Path(os.environ.get("JARVIS_BACKEND") or HERE).resolve()
    env = private_state(dict(os.environ), backend, Path(where))
    for k in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR", "JARVIS_FRAMEWORK_TOML",
              "PYTHONIOENCODING"):
        if env.get(k) and env.get(k) != os.environ.get(k):
            print(f"{k}={env[k]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--state-env":
        sys.exit(state_env(sys.argv[2]))
    sys.exit(main(tuple(a for a in sys.argv[1:] if a.startswith("test_"))))
