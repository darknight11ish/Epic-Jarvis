"""test_jobs.py - the background job queue, and the WIRING that makes it run.

    python3 backend/test_jobs.py

No pytest, no network, no real backend. Real SQLite in temp files, and an
engine driven for a fraction of a second rather than a heartbeat waited out.

WHY THIS SUITE EXISTS, IN ONE PARAGRAPH. `jarvis_jobs.run_due()` is the
function that runs every due job - the whole of "Jobs that keep going after
the chat ends" - and until 2026-10-15 it had **ZERO production call sites**.
Every suite called it directly, which is the right way to test the function and
exactly why the missing caller was invisible: every check passed, and no
queued job ever ran on the owner's PC. A test of a function is not a test of
its wiring. So the first test below never calls `run_due()`: it starts the
engine and proves the engine's own heartbeat did it.

WHAT THIS PROVES:

1. **The wiring.** `jarvis_initiative.Engine.start()` attaches the queue
   ticker, and the heartbeat's own beat runs a queued job to `done` while the
   test does nothing but wait. It FAILS if `_attach_jobs_ticker()` is removed
   from `start()` - which is the mutation that matters, because removing
   `run_due()` would fail every sensible test, while removing the call site
   left every existing test green.

2. **The owner's limit** (his decision of 2026-10-15, "FINISH WHAT I ALREADY
   STARTED"): a job step that needs a capability the row's frozen set does not
   carry **parks** - `waiting_approval`, one unspent `pending` grant, the
   frozen set unchanged, the step after it never reached - and parks again on
   the next tick. Nothing auto-approves; rule 4 is absolute. It FAILS if
   `JobContext.require()` is made to hand out a yes.

3. **A tick cannot take the heartbeat down, and says what it did.** A tick
   whose work raises returns None and leaves a receipt; a tick that ran
   something leaves a receipt naming counts and ids, never a label or a param.

4. **The HUD can draw a finding.** `jarvis_initiative.drain()` mirrors
   `level`, `check` and `message` FLAT onto every row - which is where
   jarvis_hud.html:2591-2595 reads them - and keeps the nested `finding` dict
   exactly as it was, so every reader that already used it is unaffected.

5. **The phone's `checks` count arrives.** That half is delivered by
   `backend/initiative-payload.patch`, because the body is built in
   `jarvis_hud.py`, which is NOT in `$SHIPPED` - it is one of the files the
   patch stack delivers, so an edit to the copy in this repository could never
   reach the owner. The last test rehearses the patch against
   `jarvis-backend/jarvis_hud.py` (the published copy of the real program):
   apply, reverse, and the new key really in the applied text.

WHAT THIS SUITE DOES NOT PROVE, said out loud rather than implied:

  * **There is no route that creates a job**, so no test can drive one through
    it. Measured in this tree: `GET /api/jobs` lists (jarvis_hud.py:2396) and
    `POST /api/jobs/cancel` cancels (:781); nothing POSTs a job, and
    `create()` has no caller anywhere. The job in test 1 is therefore created
    with `jarvis_jobs.create()` - the same call any future route would make -
    and what is under test is the CALLER of `run_due()`, not the function.
  * Nothing here proves the patch reaches a backend that is already installed:
    that is the installer's job, and the patch is not in `$PATCHES` until the
    Lead registers it (`backend/initiative-payload.patch` says so at the top
    of its hunk). **Measured, not assumed:** while the file is on disk and not
    in the list, `scripts/apply-patches.ps1` refuses the whole run - "1 patch
    file(s) exist but are not in this script's list" - and two suites say the
    same (`test_patch_wellformed.py`, and five checks of
    `test_apply_line_endings.py`). That is why the file and its one-line
    `$PATCHES` entry are ONE change and must land together.
  * **The name is a new file, not the owner's.** Several suites cite
    `test_jobs.py` by line number (test_rebuilt.py:26, :107, :299) and
    run_suites.py's docstring says it "lives only on the owner's PC". That is
    HIS file, beside his backend; this one was added here on 2026-10-15 and is
    a different file with different content. If the two are ever confused,
    renaming this one is the fix.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# The rebuilt modules are the ones under test, so they come first on the path -
# ahead of any copy that may be sitting in the backend folder (test_rebuilt.py
# makes the same call, for the same reason).
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rebuilt"))

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_jobs.py", "rebuilt/jarvis_initiative.py")

# A scratch base made with os.makedirs, and mkdtemp(dir=...) inside it. NOT
# plain tempfile.mkdtemp(): its 0o700 mode raises PermissionError on write in
# this environment, which has wedged suites for 45 minutes.
_BASE = Path(tempfile.gettempdir()) / "jarvis-jobs-suite"
os.makedirs(_BASE, exist_ok=True)
_WORK = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="run-"))

# Every database this suite touches, before the modules are imported:
# jarvis_jobs reads JARVIS_JOBS_DB into DB_PATH at import time, and the whole
# point is that a direct run on the owner's PC must not write his real
# jobs.db, receipts.db or config folder.
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ.setdefault("JARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ["JARVIS_JOBS_DB"] = str(_WORK / "jobs.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_WORK / "receipts.db")

# The policy file, so `ctx.require()` has a tier to read. It sits beside the
# modules when the runner stages them, and under rebuilt/ in a checkout.
for _c in (HERE / "jarvis-framework.toml", HERE / "rebuilt" / "jarvis-framework.toml"):
    if _c.is_file():
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(_c)
        break

import jarvis_initiative as IN   # noqa: E402
import jarvis_jobs as J          # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []

#: An action that appears in no tier table anywhere, so `_tier_of` answers
#: from `unknown_action_tier` - "ask" in the shipped file, never "never". A
#: real action name would make this suite depend on the owner's policy for a
#: result the test is not about.
PROBE_ACTION = "jobs_probe_action"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check that could not run here. Counted as skipped, never as a pass -
    the rule tools/check_vacuous_checks.py exists to enforce."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh():
    """A jobs database of its own for one test, on a clean writer thread.

    `shutdown()` is the module's own hook for exactly this, and DB_PATH is a
    module global the writer thread and the read connections both read, so
    moving it between cases is the documented way rather than a trick.
    """
    J.shutdown()
    d = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="case-"))
    J.DB_PATH = d / "jobs.db"
    return d


def _until(pred, seconds=10.0, step=0.05):
    """`pred()` as soon as it is truthy, or its last value when time is up."""
    end = time.time() + seconds
    got = pred()
    while not got and time.time() < end:
        time.sleep(step)
        got = pred()
    return got


def _tick_receipts():
    """The receipts this suite's ticks wrote, or None when unreadable.

    `jarvis_receipts.record()` writes nothing at all without the project's
    scrubber (its own rule, "no scrubber, nothing written"), so a checkout
    without jarvis_scrub is a reason to skip the record check rather than to
    fail it.
    """
    try:
        import jarvis_receipts
        return [r for r in jarvis_receipts.recent(50)
                if r.get("tool_name") == "jobs.tick"]
    except Exception:
        return None


# --------------------------------------------------------------------------
#   1. The wiring: the engine's own heartbeat runs a queued job
# --------------------------------------------------------------------------

def t_the_engines_heartbeat_runs_a_queued_job_with_no_manual_tick():
    """THE WIRING TEST, and the reason this suite exists.

    Nothing below calls `run_due()` or `tick()`. The job is created the way any
    route would create it (`jarvis_jobs.create()` - there is no create route
    yet, see this file's docstring), the engine is started, and the job must
    reach `done` because the ENGINE's beat ran it.

    BITE: comment out `self._attach_jobs_ticker()` in
    `jarvis_initiative.Engine.start()` and watch this test fail - the job stays
    `queued` for ever, which is the defect exactly. Removing `run_due()`
    instead is not the interesting mutation: that fails everything.
    """
    fresh()
    runs = {"n": 0, "marker": "", "caps": None}

    def body(ctx, params):
        runs["n"] += 1
        runs["marker"] = params.get("marker", "")
        # The frozen set IS the owner's yes: a step inside it runs with nobody
        # there, and that is the half of his decision this job proves.
        runs["caps"] = sorted(ctx.caps)
        return {"ok": True, "marker": runs["marker"]}

    J.register("prove_the_wiring", body)
    jid = J.create("prove_the_wiring", {"marker": "wired"},
                   label="prove the wiring", caps=[PROBE_ACTION])
    check("the job is created queued and due now",
          (J.get(jid) or {}).get("state") == "queued", J.get(jid))

    eng = IN.Engine(heartbeat_minutes=1)
    check("a built engine carries no queue ticker yet",
          IN.JOBS_TICK not in [n for n, _ in eng.checks],
          [n for n, _ in eng.checks])
    try:
        eng.start()
        check("starting the heartbeat attaches the queue ticker",
              IN.JOBS_TICK in [n for n, _ in eng.checks],
              [n for n, _ in eng.checks])
        row = _until(lambda: (J.get(jid) or {}).get("state") in J.TERMINAL
                     and J.get(jid), 10.0)
        check("the engine's own beat ran the job and it finished",
              bool(row) and row["state"] == "done", row)
        check("the handler really ran, once",
              runs["n"] == 1 and runs["marker"] == "wired", dict(runs))
        check("and it ran with the frozen capability set the owner agreed to",
              runs["caps"] == [PROBE_ACTION], runs["caps"])
        check("its result is on the row, delivered to nobody",
              (J.get(jid) or {}).get("result") == {"ok": True, "marker": "wired"},
              (J.get(jid) or {}).get("result"))
    finally:
        eng.stop()


def t_the_queue_ticker_is_attached_once_per_engine():
    """Two starts, or a restart, must not put a second copy of the ticker on
    the heartbeat - a job run twice per beat is the failure that would cause."""
    fresh()
    eng = IN.Engine(heartbeat_minutes=30)
    try:
        eng.start()
        eng.start()
        names = [n for n, _ in eng.checks]
        check("two starts leave exactly one queue ticker",
              names.count(IN.JOBS_TICK) == 1, names)
        eng.stop()
        eng.start()
        names = [n for n, _ in eng.checks]
        check("and a restart adds no second copy",
              names.count(IN.JOBS_TICK) == 1, names)
    finally:
        eng.stop()


# --------------------------------------------------------------------------
#   2. The owner's limit: anything needing a fresh yes parks
# --------------------------------------------------------------------------

def t_a_step_needing_a_fresh_yes_parks_and_never_runs_unattended():
    """THE OWNER'S LIMIT (2026-10-15): "anything that would need a fresh 'yes'
    waits for him".

    The job is created with NO capabilities, and its first act is to ask for
    one. So the engine's beat reaches the job, the job parks in
    `waiting_approval` with one unspent `pending` grant, and the step AFTER the
    question is never reached. The second half drives the tick the heartbeat
    would make thirty seconds later by hand (`run_due(now=...)`) rather than
    sleeping for it, and it must park again, with the grant still unspent.

    BITE: make `JobContext.require()` return True at the top - the shape of
    auto-approval - and watch this test fail: the step after the question runs.
    """
    fresh()
    needs = {"entered": 0, "acted": False}

    def body(ctx, params):
        needs["entered"] += 1
        ctx.require(PROBE_ACTION)      # not in the frozen set: a fresh yes
        needs["acted"] = True          # only reachable if something said yes
        return {"ok": True}

    J.register("needs_a_yes", body)
    jid = J.create("needs_a_yes", {}, label="needs a fresh yes", caps=[])
    check("the job is created with nothing frozen onto it",
          (J.get(jid) or {}).get("caps") == [], (J.get(jid) or {}).get("caps"))

    eng = IN.Engine(heartbeat_minutes=1)
    try:
        eng.start()
        parked = _until(lambda: (J.get(jid) or {}).get("state") == "waiting_approval"
                        and J.get(jid), 10.0)
        check("the engine's beat parked the job instead of running it",
              bool(parked) and parked["state"] == "waiting_approval", parked)
        check("the step after the missing capability never ran",
              needs["acted"] is False, dict(needs))
        grants = J.pending_grants(jid)
        check("one one-shot grant is waiting for the owner, unspent and unapproved",
              len(grants) == 1 and grants[0]["state"] == "pending"
              and grants[0]["action"] == PROBE_ACTION and grants[0]["used"] is None,
              grants)
        check("the frozen set was not widened by asking",
              (J.get(jid) or {}).get("caps") == [], (J.get(jid) or {}).get("caps"))

        # The retry the heartbeat would make 30 seconds later - driven by hand
        # so the test does not sleep, and named here so nobody reads it as the
        # wiring test above calling run_due() for its result.
        J.run_due(now=time.time() + 7200)
        after = J.get(jid) or {}
        check("a later tick parks it again rather than running it",
              after.get("state") == "waiting_approval", after.get("state"))
        check("nothing acted on the second tick either",
              needs["acted"] is False, dict(needs))
        grants = J.pending_grants(jid)
        check("the grant is still pending: nothing here auto-approves",
              len(grants) == 1 and grants[0]["state"] == "pending", grants)
        check("and it is still unspent, so the owner's answer is still worth giving",
              grants and grants[0]["used"] is None, grants)
    finally:
        eng.stop()


# --------------------------------------------------------------------------
#   3. A tick cannot take the heartbeat down, and says what it did
# --------------------------------------------------------------------------

def t_a_tick_that_raises_returns_none_and_is_recorded():
    """A queue that dies silently is the defect this work fixes, so a tick
    whose work raises must not raise into `Engine.beat()` (which would count it
    and carry on, but leave the queue dead) and must be recorded."""
    fresh()
    keep = J.run_due
    J.run_due = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no database today"))
    try:
        got = J.tick()
        check("a tick whose work raises returns None instead of raising",
              got is None, got)
    finally:
        J.run_due = keep
    rows = _tick_receipts()
    if rows is None:
        skip("the receipts store cannot be read here, so the record was not checked")
    else:
        check("what happened is recorded as a receipt",
              len(rows) >= 1 and "could not be ticked" in (rows[0].get("summary") or ""),
              rows)


def t_a_tick_that_ran_something_says_so_and_writes_a_receipt():
    """The record of an unattended run: counts and job ids, never a label, a
    param or an error's words - the rule every record in jarvis_jobs follows."""
    fresh()
    J.register("noop_ok", lambda ctx, params: {"ok": True})
    jid = J.create("noop_ok", {}, label="a label that must not be recorded")
    J.tick()
    check("the job ran", (J.get(jid) or {}).get("state") == "done", J.get(jid))
    rows = _tick_receipts()
    if rows is None:
        skip("the receipts store cannot be read here, so the record was not checked")
        return
    check("the tick left a receipt", len(rows) >= 1, rows)
    if rows:
        summary = rows[0].get("summary") or ""
        check("it says how many ran and how they ended",
              "background job" in summary and "finished" in summary, summary)
        check("and it does NOT carry the owner's own label",
              "must not be recorded" not in summary, summary)


# --------------------------------------------------------------------------
#   4. The HUD can draw a finding: the flat keys, nested dict intact
# --------------------------------------------------------------------------

def t_a_drained_finding_carries_the_three_keys_flat_and_keeps_the_nested_dict():
    """jarvis_hud.html:2591-2595 draws a heartbeat finding from `it.level`,
    `it.check` and `it.message` ON THE ROW, while `file()` nests the finding one
    level down under `finding` - so a finding was served and never drawn.

    `drain()` now carries it both ways. This is the half that reaches the
    owner's PC with no patch at all: jarvis_initiative.py is in `$SHIPPED`.
    """
    e = IN.Engine(heartbeat_minutes=30)
    filed = {"level": "alert", "check": "event stream",
             "message": "the event stream is not running"}
    e.file(IN.BUILTIN_CHECK, filed)

    got = e.drain()
    check("one row came out of drain()", len(got) == 1, got)
    if got:
        row = got[0]
        check("the page's three keys are flat on the row",
              (row.get("level"), row.get("check"), row.get("message"))
              == ("alert", "event stream", "the event stream is not running"), row)
        check("the nested finding dict is untouched",
              row.get("finding") == filed, row.get("finding"))
        check("and the row still names the check that filed it",
              row.get("source") == IN.BUILTIN_CHECK, row.get("source"))

    # A finding that names none of the three: filed under `text`, which is the
    # shape this module's own suite files. It must still be drawable.
    e.file("a_check_with_no_words_of_its_own", {"text": "just some words"})
    row = e.drain()[0]
    check("a finding with no level is a note, so it is still drawn",
          row.get("level") == IN.DEFAULT_LEVEL, row.get("level"))
    check("its words are mirrored from `text`",
          row.get("message") == "just some words", row.get("message"))
    check("and `check` falls back to the source, which is the check's own name",
          row.get("check") == "a_check_with_no_words_of_its_own", row.get("check"))

    # A check may file a plain string - test_rebuilt.py's own Initiative tests
    # do - and that must read as its own message rather than vanishing.
    e.file("a_stringy_check", "a plain string finding")
    row = e.drain()[0]
    check("a string finding reads as its own message",
          row.get("message") == "a plain string finding", row.get("message"))

    check("drain() still marks what it handed out as seen", e.drain() == [])


# --------------------------------------------------------------------------
#   5. The phone's `checks` count: rehearsed against the real jarvis_hud.py
# --------------------------------------------------------------------------

def t_the_checks_key_patch_applies_to_the_real_backend_and_sends_checks():
    """`backend/initiative-payload.patch` against the REAL `jarvis_hud.py`,
    byte for byte.

    WHY A PATCH AT ALL. The phone's "Findings" note reads a `checks` count out
    of the /api/initiative body (BrainScreen.kt:2503-2509), and the body is
    built in `jarvis_hud.py`. That file is NOT in `$SHIPPED` - it is one of the
    files the patch stack delivers - so an edit to the copy in this repository
    would reach the published base and the suites and never reach the owner's
    install. The change therefore has to be a patch, and this is the rehearsal
    that proves the patch matches the text it will be applied to:
    `jarvis-backend/jarvis_hud.py` is a published copy of the real program.

    The check is the same one test_tasks.py makes for `tasks.patch`: apply,
    check, reverse, and the bytes must come back identical - plus the one thing
    this patch is FOR, that the applied route really sends the key.
    """
    real = REPO / "jarvis-backend" / "jarvis_hud.py"
    patch = HERE / "initiative-payload.patch"
    body = ""
    check("the patch file is in backend/", patch.is_file(), patch)
    if not real.exists():
        skip("this checkout has no jarvis-backend/ copy of the program to rehearse against")
        return
    if not patch.is_file():
        return
    git = shutil.which("git")
    if not git:
        skip("git is not installed, so the patch could not be rehearsed")
        return
    # `-c core.autocrlf=false`: the scratch folder has no .gitattributes, and a
    # Windows clone with autocrlf=true would have git rewrite the file's
    # endings mid-test - a failure with nothing to do with the patch.
    cmd = [git, "-c", "core.autocrlf=false", "-c", "core.eol=lf"]
    tmp = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="real-patch-"))
    try:
        original = real.read_bytes()
        (tmp / "jarvis_hud.py").write_bytes(original)
        (tmp / patch.name).write_bytes(patch.read_bytes())
        subprocess.run([git, "init", "-q", "."], cwd=tmp, capture_output=True)
        ok = True
        for args in (["apply", "--check", patch.name], ["apply", patch.name]):
            r = subprocess.run(cmd + args, cwd=tmp, capture_output=True, text=True)
            if r.returncode != 0:
                ok = False
                check(f"the real jarvis_hud.py accepts {patch.name} ({' '.join(args)})",
                      False, r.stderr.strip())
                break
        if ok:
            # Read the applied text BEFORE reversing: the reverse puts the file
            # back, so reading afterwards would only ever show the original.
            body = (tmp / "jarvis_hud.py").read_text(encoding="utf-8")
            r = subprocess.run(cmd + ["apply", "--reverse", patch.name], cwd=tmp,
                               capture_output=True, text=True)
            if r.returncode != 0:
                ok = False
                check("and the reverse applies", False, r.stderr.strip())
        if ok:
            check(f"the real jarvis_hud.py accepts {patch.name}, applies it and reverses it",
                  True)
            check("and reversing gives the file back byte for byte",
                  (tmp / "jarvis_hud.py").read_bytes() == original)
            check('the applied /api/initiative body sends a "checks" count',
                  '"checks":' in body and "watchers" in body)
            check("the count comes from the engine, and 0 when there is no engine",
                  "len(_ENGINE.watchers)" in body and "if _ENGINE else 0" in body)
            check("the rest of the body is untouched: `available` and `items` are still sent",
                  '"available": bool(_ENGINE)' in body and '"items": items' in body)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------

def main() -> int:
    # DISCOVERED, never a hand-written list at the bottom of the file: a
    # `t_` function that is not in a hand list is dead code that silently never
    # runs, which has already happened in this repository today.
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("t_") and callable(f)]
    for name, fn in tests:
        print(f"--- {name} ---")
        try:
            fn()
        except Exception as exc:                    # pragma: no cover
            traceback.print_exc()
            check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    print(f"      ({len(tests)} t_ function(s) were found by name and run)")
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
