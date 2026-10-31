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

6. **A job can be CREATED from the owner's words (2026-10-30).** Until this
   landed `create()` had no production caller at all, so the queue was a
   library nothing could reach. `jarvis_jobs.handle_create()` is the body
   behind `POST /api/jobs` (`backend/jobs-routes.patch`): it validates the
   kind, the time and the capability list in sentences a person can act on,
   refuses to queue a job that nothing would ever run, passes the request
   through `create()` so the frozen set is exactly what was named, and
   approves NOTHING. A job created with no capabilities parks on its first
   need - which is what makes the second route worth having.

7. **A parked grant can be ANSWERED - for one job, one use, with no rule
   left behind.** `handle_answer()` (behind `POST /api/jobs/answer`) decides
   the single pending grant of the single job it names. A yes is spent the
   next time the handler asks, so a second ask asks again; a no stops THAT
   job at once and the next job needing the same action parks and asks
   again. Nothing writes a capability onto a row or into the framework's tier
   table, and the test proves the file really is unchanged rather than
   trusting a comment. The whole slice is rehearsed against the real
   `jarvis_hud.py`: `backend/jobs-routes.patch` applies, reverses, gives the
   same bytes back, and the applied text carries both POST routes, the two
   facts the Work pane needs (`grants`, `ticking`) and the start-up call that
   registers the one production job body.

8. **The ONE production body ASKS (2026-10-31, DEF-024).** `watch_github`'s
   handler calls `ctx.require("github_read")` before it searches, so a job
   created through the live route with the Work panes' `needs: []` parks in
   `waiting_approval` with one one-shot grant. The tests below drive that
   parked row through `handle_answer`: No fails the job before any search,
   Allow once spends the grant and the search runs on the retry tick, the
   grant is used up rather than inherited, and the queue's own audit verbs
   (`jobs.waiting`, `jobs.grant_decided`, `jobs.capability_granted`) are the
   ones written - no new verb is invented. This is the first production path
   that can park, which is what closes DEF-024 (field-test Matrix Row 22).

WHAT THIS SUITE DOES NOT PROVE, said out loud rather than implied:

  * **Nothing here drives HTTP.** The two route bodies are module functions
    (`handle_create`, `handle_answer`), and the test calls those - the same
    functions the patched route calls. The patch rehearsal proves the route
    reaches them; it does not open a socket, and it never runs on the owner's
    PC. What IS proven end to end is the queue's own state machine: create,
    park, answer, spend, run.
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
  * **Only one production job body exists** (2026-10-30): `watch_github`,
    registered at start-up by `jobs-routes.patch` calling the
    `jarvis_watch.register_job()` that had no caller. The other handlers in
    this file are the suite's own. So the route is no longer a library with no
    way in, but "what a job can DO" is still one kind until another module
    registers one - said in ARCHITECTURE.md section 10 rather than implied.
    Since 2026-10-31 that body ASKS for its `github_read` capability
    (DEF-024), so a route-created job with `needs: []` parks and the answer
    route above is its way back; before that no production body called
    `ctx.require()`, which is why the loop was unreachable on the owner's PC.
"""
import ast
import json
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
#   6. Creating a job: the owner's words, validated, and nothing approved
# --------------------------------------------------------------------------

def t_creating_a_job_validates_the_request_and_creates_exactly_one_row():
    """POST /api/jobs, through the function the route calls.

    BITE: remove the `kind not in known` branch from `handle_create` and the
    first check below fails - an unknown kind would become a row that fails on
    its first tick instead of a sentence while the owner is still there. The
    `needs` refusal is the other one that matters: a `never` action must not
    be frozen onto a row at all, because the frozen set is trusted at
    execution, so catching it here is the only place it can be caught.
    """
    fresh()
    J.register("route_probe", lambda ctx, params: {"ok": True})
    before = len(J.jobs())

    code, out = J.handle_create("not an object")
    check("a body that is not an object is refused", code == 400 and not out["ok"], (code, out))

    code, out = J.handle_create({})
    check("a job with no kind is refused, in words", code == 400 and "kind" in out["error"],
          (code, out))

    code, out = J.handle_create({"kind": "no_such_kind"})
    check("an unknown kind is refused AND names what this PC has",
          code == 400 and "no_such_kind" in out["error"]
          and "route_probe" in out["error"], (code, out))

    code, out = J.handle_create({"kind": J.PLAN_HANDLER})
    check("a plan is refused: it needs steps this route does not take",
          code == 400 and "steps" in out["error"], (code, out))

    code, out = J.handle_create({"kind": "route_probe", "when": "half past never"})
    check("a time that cannot be read is refused, not guessed",
          code == 400 and "time" in out["error"], (code, out))

    code, out = J.handle_create({"kind": "route_probe", "needs": {"a": 1}})
    check("needs must be a list of action names",
          code == 400 and "list" in out["error"], (code, out))

    check("the shipped policy really does forbid post_to_external_service",
          J._tier_of("post_to_external_service") == "never")
    code, out = J.handle_create({"kind": "route_probe",
                                 "needs": ["post_to_external_service"]})
    check("a 'never' action can never be frozen onto a job",
          code == 400 and "never" in out["error"], (code, out))

    code, out = J.handle_create({"kind": "route_probe"}, ticking=False)
    check("with the heartbeat off, a job is refused rather than stranded",
          code == 503 and "heartbeat" in out["error"], (code, out))

    check("not one of those refusals created a row", len(J.jobs()) == before,
          [j["id"] for j in J.jobs()])

    code, out = J.handle_create({"kind": "route_probe",
                                 "text": "check the thing", "when": 0})
    row = J.get(out.get("id", "")) or {}
    check("a good request makes ONE job, nameable by its id",
          code == 200 and out.get("ok") and row.get("id") == out.get("id"),
          (code, out))
    check("the owner's words are the label, and nothing is approved by creating it",
          row.get("label") == "check the thing" and row.get("caps") == [],
          {"label": row.get("label"), "caps": row.get("caps")})
    check("it starts queued and due now",
          row.get("state") == "queued" and row.get("due", 0) <= time.time() + 1,
          {"state": row.get("state"), "due": row.get("due")})
    check("its taint is copied from the gate, never chosen by the caller",
          isinstance(row.get("tainted"), bool), row.get("tainted"))

    code, out = J.handle_create({"kind": "route_probe", "text": "with a yes",
                                 "needs": [PROBE_ACTION]})
    row = J.get(out.get("id", "")) or {}
    check("the capabilities the request names are the frozen set - his yes",
          code == 200 and row.get("caps") == [PROBE_ACTION], row.get("caps"))
    check("and that is exactly two rows after the two good requests",
          len(J.jobs()) == before + 2, [j["label"] for j in J.jobs()])


# --------------------------------------------------------------------------
#   7. Answering one: one job, one use, no rule left behind
# --------------------------------------------------------------------------

def t_a_parked_job_is_exactly_what_the_work_pane_already_reads():
    """The GET /api/jobs body the Work pane reads, after a job parks.

    `jobs-routes.patch` adds two keys to that body (`grants`, `ticking`) and
    changes nothing else. This proves the parked state the pane draws is the
    queue's own: the row says `waiting_approval`, the grant says which job and
    which action, and neither invents a second vocabulary.
    """
    fresh()
    J.register("route_asks", lambda ctx, params: ctx.require(PROBE_ACTION))
    code, out = J.handle_create({"kind": "route_asks", "text": "needs a yes"})
    jid = out.get("id", "")
    check("the job was created", code == 200 and bool(jid), (code, out))
    J.run_due()

    body = {"jobs": J.jobs(), "grants": J.pending_grants(), "status": J.status()}
    row = next((j for j in body["jobs"] if j["id"] == jid), None)
    check("the Work pane's own read shows the job parked",
          bool(row) and row["state"] == "waiting_approval", row)
    check("under the owner's own words",
          bool(row) and row["label"] == "needs a yes", row and row["label"])
    grant = [g for g in body["grants"] if g["job_id"] == jid]
    check("and the grant says which job and which action, and nothing else",
          len(grant) == 1 and grant[0]["action"] == PROBE_ACTION
          and grant[0]["state"] == "pending", grant)
    check("the status half still counts it",
          body["status"]["pending_grants"] == 1
          and "route_asks" in body["status"]["handlers"], body["status"])


def t_answering_a_parked_grant_decides_one_job_and_nothing_else():
    """ONE job's ONE grant, spent once, with the other job untouched.

    BITE: make `answer()` answer every pending grant it can find (drop the
    `len(waiting) > 1` guard and loop) and the second job's grant flips too;
    make it write the capability onto the job row and the frozen-set check
    below fails.
    """
    fresh()
    J.register("route_ask_a", lambda ctx, params: ctx.require(PROBE_ACTION))
    J.register("route_ask_b", lambda ctx, params: ctx.require(PROBE_ACTION))
    a = J.handle_create({"kind": "route_ask_a", "text": "job a"})[1]["id"]
    b = J.handle_create({"kind": "route_ask_b", "text": "job b"})[1]["id"]
    J.run_due()
    check("both jobs parked",
          (J.get(a) or {}).get("state") == "waiting_approval"
          and (J.get(b) or {}).get("state") == "waiting_approval",
          ((J.get(a) or {}).get("state"), (J.get(b) or {}).get("state")))
    grants_a = J.pending_grants(a)
    grants_b = J.pending_grants(b)

    code, out = J.handle_answer({"id": a, "approved": True, "by": "test"})
    check("the answer is accepted, for the action that was asked about",
          code == 200 and out["ok"] and out["grant"]["state"] == "granted"
          and out["grant"]["action"] == PROBE_ACTION, out)
    check("job A's grant is granted and job B's is still PENDING",
          not J.pending_grants(a) and len(J.pending_grants(b)) == 1,
          {"a": J.pending_grants(a), "b": J.pending_grants(b)})
    check("job A was not run inside the HTTP call - it waits for the heartbeat",
          (J.get(a) or {}).get("state") == "waiting_approval",
          (J.get(a) or {}).get("state"))
    check("job B did not move at all",
          (J.get(b) or {}).get("state") == "waiting_approval"
          and (J.get(b) or {}).get("attempts") == 1,
          {"state": (J.get(b) or {}).get("state"),
           "attempts": (J.get(b) or {}).get("attempts")})
    check("neither job's frozen set was widened by answering",
          (J.get(a) or {}).get("caps") == [] and (J.get(b) or {}).get("caps") == [],
          ((J.get(a) or {}).get("caps"), (J.get(b) or {}).get("caps")))

    J.run_due(now=time.time() + 7200)
    check("the granted job ran to the end",
          (J.get(a) or {}).get("state") == "done", (J.get(a) or {}).get("state"))
    check("job B parked again instead",
          (J.get(b) or {}).get("state") == "waiting_approval",
          (J.get(b) or {}).get("state"))
    check("the grant was SPENT by its one use, so a later ask asks again",
          not J.pending_grants(a) and len(J.pending_grants(b)) == 1
          and J.pending_grants(b)[0]["id"] == grants_b[0]["id"],
          {"a": J.pending_grants(a), "b": J.pending_grants(b)})

    code, out = J.handle_answer({"id": a, "approved": True})
    check("a second tap on a spent grant changes nothing (409)",
          code == 409 and out.get("reason") == "nothing_waiting", (code, out))
    code, out = J.handle_answer({"id": "nope-not-a-job", "approved": True})
    check("an unknown job is a 404, in words",
          code == 404 and out.get("reason") == "no_such_job", (code, out))
    code, out = J.handle_answer({})
    check("no job id is a 400", code == 400, (code, out))
    for bad in ("yes", 1, None):
        code, out = J.handle_answer({"id": b, "approved": bad})
        check(f"approved={bad!r} is refused rather than read as a yes",
              code == 400 and "true or false" in out["error"], (code, out))
    check("and none of those refusals spent job B's grant",
          len(J.pending_grants(b)) == 1, J.pending_grants(b))


def t_a_denial_stops_that_one_job_and_never_becomes_a_rule():
    """A No is final for that job and means nothing for the next one.

    This is the rule the gate already follows, applied to a parked job: a
    refusal authorises nothing, remembers nothing, and is not written into the
    policy file. BITE: write the action into the framework's tier table (or
    into the job row's caps) on a denial and the two checks that read the
    bytes and the caps fail; keep the row in `waiting_approval` and the pane
    goes on asking a question already answered.
    """
    fresh()
    risky = "send_email"
    if J._tier_of(risky) != "ask":
        skip(f"this PC's policy does not put {risky} at 'ask', so the risky-action "
             "denial was not checked")
        return
    J.register("route_needs_email", lambda ctx, params: ctx.require(risky))
    framework = Path(os.environ.get("JARVIS_FRAMEWORK_TOML") or "")
    before = framework.read_bytes() if framework.is_file() else None
    if before is None:
        skip("this run has no framework file to prove unchanged, so the "
             "no-standing-rule check read only the row and the grants")
    a = J.handle_create({"kind": "route_needs_email", "text": "send it"})[1]["id"]
    J.run_due()
    grant_a = J.pending_grants(a)
    check("the risky job parked, waiting for a person",
          (J.get(a) or {}).get("state") == "waiting_approval"
          and len(grant_a) == 1 and grant_a[0]["action"] == risky, grant_a)

    code, out = J.handle_answer({"id": a, "approved": False, "by": "test"})
    check("No is accepted and says it stopped that job",
          code == 200 and out["ok"] and out["stopped"] is True
          and out["grant"]["state"] == "denied", out)
    row = J.get(a) or {}
    check("the job is stopped now, not left asking an answered question",
          row.get("state") == "failed" and "you said no" in (row.get("error") or ""),
          {"state": row.get("state"), "error": row.get("error")})
    check("nothing is pending for it any more", not J.pending_grants(a))
    check("its frozen set is unchanged - a denial widens nothing",
          row.get("caps") == [], row.get("caps"))
    if before is not None:
        check("the policy file was not rewritten by a denial",
              framework.read_bytes() == before, str(framework))

    b = J.handle_create({"kind": "route_needs_email", "text": "send it again"})[1]["id"]
    J.run_due()
    grants_b = J.pending_grants(b)
    check("a NEW job needing the same risky action parks and asks again",
          (J.get(b) or {}).get("state") == "waiting_approval"
          and len(grants_b) == 1 and grants_b[0]["state"] == "pending",
          {"state": (J.get(b) or {}).get("state"), "grants": grants_b})
    check("so the No was not remembered as a rule for that action",
          bool(grants_b) and grants_b[0]["id"] != grant_a[0]["id"],
          {"old": grant_a[0]["id"], "new": grants_b and grants_b[0]["id"]})


def t_the_jobs_routes_patch_applies_to_the_real_backend_and_wires_both_routes():
    """`backend/jobs-routes.patch` against the REAL `jarvis_hud.py`.

    WHY A PATCH AT ALL: `jarvis_hud.py` is NOT in `$SHIPPED` - it is one of the
    files the patch stack delivers - so an edit to `jarvis-backend/jarvis_hud.py`
    would never reach the owner's install. This is the same rehearsal
    `initiative-payload.patch` gets: apply, check, reverse, byte for byte, and
    then the one thing the patch is FOR - both POST routes really wired, the
    GET still the read it was, and the file still compiles.
    """
    real = REPO / "jarvis-backend" / "jarvis_hud.py"
    patch = HERE / "jobs-routes.patch"
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
            try:
                compile(body, "jarvis_hud.py (with jobs-routes.patch)", "exec")
                check("the applied file still compiles", True)
            except SyntaxError as exc:
                check("the applied file still compiles", False, str(exc))
            # STRUCTURE, NOT TEXT. Every check below walks the applied file's
            # AST and asserts that a real call or a real dict key is there, so a
            # reworded comment or a renamed local cannot make it pass or fail:
            # tools/check_no_source_pins.py exists because `"x" in source_text`
            # stays green when the behaviour is wrong. This module's own pin
            # ceiling is 3 and the initiative rehearsal above uses them; these
            # checks add none.
            tree = ast.parse(body)

            def _fn(name):
                return next((n for n in ast.walk(tree)
                             if isinstance(n, ast.FunctionDef) and n.name == name), None)

            desktop, post, get, main_fn = (_fn("_desktop_action"), _fn("do_POST"),
                                           _fn("do_GET"), _fn("main"))
            check("the four functions this patch edits are all in the file",
                  all(x is not None for x in (desktop, post, get, main_fn)),
                  [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                   and n.name in ("_desktop_action", "do_POST", "do_GET", "main")])

            calls = [n for n in ast.walk(desktop or ast.Module(body=[], type_ignores=[]))
                     if isinstance(n, ast.Call)]
            jars = {c.func.attr for c in calls
                    if isinstance(c.func, ast.Attribute) and c.func.attr in
                    ("handle_create", "handle_answer")}
            check("the write branch reaches handle_create AND handle_answer",
                  jars == {"handle_create", "handle_answer"}, sorted(jars))

            creator = next((c for c in calls
                            if isinstance(c.func, ast.Attribute)
                            and c.func.attr == "handle_create"), None)
            check("creating passes the REAL heartbeat state, so a job cannot be stranded",
                  creator is not None
                  and any(k.arg == "ticking" for k in creator.keywords),
                  creator and [k.arg for k in creator.keywords])

            route_lists = [
                t for t in ast.walk(post or ast.Module(body=[], type_ignores=[]))
                if isinstance(t, (ast.Tuple, ast.List)) and t.elts
                and all(isinstance(e, ast.Constant) and isinstance(e.value, str)
                        for e in t.elts)
                and "/api/jobs/cancel" in [e.value for e in t.elts]]
            check("both POST routes are in the server's own write list",
                  any({"/api/jobs", "/api/jobs/answer"} <= {e.value for e in t.elts}
                      for t in route_lists),
                  [[e.value for e in t.elts] for t in route_lists])

            jobs_dicts = [
                d for d in ast.walk(get or ast.Module(body=[], type_ignores=[]))
                if isinstance(d, ast.Dict)
                and any(isinstance(k, ast.Constant) and k.value == "jobs"
                        for k in d.keys)]
            keys = {k.value for d in jobs_dicts for k in d.keys
                    if isinstance(k, ast.Constant)}
            check("the GET the Work pane already reads now carries grants and ticking",
                  {"grants", "ticking"} <= keys, sorted(keys))
            check("and it still carries the jobs and status it always did",
                  {"jobs", "status", "available"} <= keys, sorted(keys))

            watch_calls = [c for c in ast.walk(main_fn or ast.Module(body=[], type_ignores=[]))
                           if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                           and c.func.attr == "register_job"]
            check("the one production job body is registered at start-up",
                  bool(watch_calls), watch_calls)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
#   9. The ONE production body asks: DEF-024, closed 2026-10-31
# --------------------------------------------------------------------------
#: The real gate action a background GitHub search asks under - the same name
#: jarvis_tellme.py's own GitHub look uses (jarvis_tellme.py's GITHUB_ACTION).
#: Not the suite's PROBE_ACTION: this is the production capability, and the
#: policy's tier for it is not what decides a job (the frozen row is).
GITHUB_ACTION = "github_read"


def _job_result(row):
    """A finished job's result dict, whether the row holds it decoded or as JSON."""
    got = (row or {}).get("result")
    if isinstance(got, str):
        try:
            got = json.loads(got)
        except ValueError:
            return {}
    return got if isinstance(got, dict) else {}


def _production_watch():
    """The SHIPPED watch module, with its own database and a fake GitHub.

    `jarvis_watch.DB_PATH` and `jarvis_watch._get` are both read at call time
    (the same documented hooks `fresh()` uses for jarvis_jobs, and check()'s
    own docstring says why `_get` is resolved there rather than bound), so
    pointing them at scratch objects cannot touch the owner's watch.db and
    cannot open a socket. Returns (module, fetcher calls, restore).
    """
    import jarvis_watch as W
    scratch = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="watch-"))
    W.DB_PATH = scratch / "watch.db"
    # `_init()` is once per process on purpose, so a moved DB_PATH needs the
    # same reset the module's own tests do - otherwise the second case reads
    # tables the first case's file has.
    W._inited = False
    calls = []

    def fake_get(url, timeout=12.0, headers=None):
        calls.append(url)
        return json.dumps({"items": []})

    real_get = W._get
    W._get = fake_get
    W.add("def024", "python")
    W.register_job()          # the SAME registration the route's start-up makes
    return W, calls, (lambda: setattr(W, "_get", real_get))


def _capture_audit():
    """Capture every audit line the modules write, without touching a real log.

    `jarvis_jobs` and `jarvis_watch` both call `fw.audit_log`, and `fw` is the
    same imported module object in this process, so one replacement catches
    both. Returns (events, restore); the caller restores in a finally.
    """
    if getattr(J, "fw", None) is None:
        return None, (lambda: None)
    events = []

    def recorder(event, detail=None):
        events.append((event, detail if isinstance(detail, dict) else {}))
        return True

    real = J.fw.audit_log
    J.fw.audit_log = recorder
    return events, (lambda: setattr(J.fw, "audit_log", real))


def _created_watch_job(text="watch python"):
    """Create the one production kind through the route body, and return its id."""
    code, out = J.handle_create({"kind": "watch_github", "text": text})
    return code, out, (out or {}).get("id", "")


def t_the_one_production_job_body_parks_and_asks_for_github_read():
    """DEF-024: the body that production actually registers calls ctx.require().

    Before 2026-10-31 the one production handler only reported progress, so no
    route-created job could ever park. This drives a job created through
    `POST /api/jobs`' body with the Work panes' `needs: []`, runs the tick the
    heartbeat runs, and requires the park: `waiting_approval`, ONE unspent
    pending grant for the real `github_read` action, no GitHub request made,
    the frozen set unchanged, and the queue's own `jobs.waiting` line written.

    BITE: delete the `ctx.require("github_read")` line from jarvis_watch's
    handler and the job runs straight to `done` - the first check fails.
    """
    fresh()
    W, calls, restore_get = _production_watch()
    events, restore_audit = _capture_audit()
    try:
        if events is None:
            skip("jarvis_framework is not importable here, so the audit lines "
                 "could not be captured")
            return
        code, out, jid = _created_watch_job()
        check("the live route body creates the one production kind",
              code == 200 and bool(jid), (code, out))
        J.run_due()
        row = J.get(jid) or {}
        check("its handler PARKS the job instead of searching",
              row.get("state") == "waiting_approval", row.get("state"))
        check("no GitHub request was made before the owner answered",
              calls == [], calls)
        grants = J.pending_grants(jid)
        check("ONE one-shot grant waits, for the REAL action github_read",
              len(grants) == 1 and grants[0]["action"] == GITHUB_ACTION
              and grants[0]["state"] == "pending" and grants[0]["used"] is None,
              grants)
        check("the frozen set was not widened by asking",
              row.get("caps") == [], row.get("caps"))
        waiting = [(e, d) for e, d in events if e == "jobs.waiting"]
        check("the queue's own jobs.waiting line names the action",
              len(waiting) == 1 and waiting[0][1].get("action") == GITHUB_ACTION,
              waiting)
        check("nothing was granted by parking",
              not [e for e, _ in events if e == "jobs.capability_granted"], events)
    finally:
        restore_audit()
        restore_get()


def t_allow_once_spends_the_production_grant_and_the_search_runs_exactly_once():
    """Allow once: the parked production job continues and works exactly once.

    Answers the parked grant the way the Work pane's button does
    (`handle_answer`), then drives the retry tick by hand. The grant is spent
    by `ctx.require()` on that tick, the GitHub search really runs (the fake
    fetcher is counted), the job finishes, and `jobs.capability_granted` is
    written once - the queue's existing verb, not a new one.
    """
    fresh()
    W, calls, restore_get = _production_watch()
    events, restore_audit = _capture_audit()
    try:
        if events is None:
            skip("jarvis_framework is not importable here, so the audit lines "
                 "could not be captured")
            return
        _code, _out, jid = _created_watch_job()
        J.run_due()
        check("the production job parked first", len(J.pending_grants(jid)) == 1,
              J.pending_grants(jid))
        code, out = J.handle_answer({"id": jid, "approved": True, "by": "test"})
        check("the Work pane's Allow once is accepted",
              code == 200 and out.get("ok") and out["grant"]["state"] == "granted",
              (code, out))
        check("answering does not run it inside the request",
              (J.get(jid) or {}).get("state") == "waiting_approval",
              (J.get(jid) or {}).get("state"))
        decided = [(e, d) for e, d in events if e == "jobs.grant_decided"]
        check("deciding wrote jobs.grant_decided with the owner's yes",
              len(decided) == 1 and decided[0][1].get("approved") is True, decided)

        J.run_due(now=time.time() + 7200)
        row = J.get(jid) or {}
        check("the retry tick spends the grant and finishes the job",
              row.get("state") == "done", row.get("state"))
        check("the GitHub search really ran, exactly once",
              len(calls) == 1, calls)
        check("and its count is on the job's result",
              _job_result(row).get("checked") == 1, _job_result(row))
        granted = [(e, d) for e, d in events if e == "jobs.capability_granted"]
        check("the queue's jobs.capability_granted line was written once",
              len(granted) == 1 and granted[0][1].get("action") == GITHUB_ACTION,
              granted)
        spent = J._read("SELECT state, used FROM job_grants WHERE job_id=?", (jid,))
        check("the grant is USED UP - granted, and its one use stamped",
              len(spent) == 1 and spent[0]["state"] == "granted"
              and spent[0]["used"] is not None, spent)
        check("nothing is left pending for the job", not J.pending_grants(jid),
              J.pending_grants(jid))
    finally:
        restore_audit()
        restore_get()


def t_no_stops_the_production_job_without_the_search_and_leaves_no_rule():
    """No: that job ends before anything is fetched, and the next one asks again.

    The denial path is `handle_answer(..., approved=False)` ->
    `_stop_denied`, and the proof that it is not a policy change is the second
    job: created the same way, it parks and asks for the same action again.
    """
    fresh()
    W, calls, restore_get = _production_watch()
    events, restore_audit = _capture_audit()
    try:
        if events is None:
            skip("jarvis_framework is not importable here, so the audit lines "
                 "could not be captured")
            return
        _code, _out, jid = _created_watch_job()
        J.run_due()
        first_grant = J.pending_grants(jid)
        check("the production job parked first", len(first_grant) == 1, first_grant)
        code, out = J.handle_answer({"id": jid, "approved": False, "by": "test"})
        check("No is accepted and says it stopped that job",
              code == 200 and out.get("ok") and out.get("stopped") is True,
              (code, out))
        row = J.get(jid) or {}
        check("the job is failed with the owner's answer as its reason",
              row.get("state") == "failed"
              and "you said no" in (row.get("error") or ""),
              {"state": row.get("state"), "error": row.get("error")})
        check("no GitHub request was made", calls == [], calls)
        decided = [(e, d) for e, d in events if e == "jobs.grant_decided"]
        check("jobs.grant_decided recorded the No",
              len(decided) == 1 and decided[0][1].get("approved") is False, decided)
        check("its frozen set is unchanged - a No widens nothing",
              row.get("caps") == [], row.get("caps"))

        _code, _out, jid2 = _created_watch_job("watch python again")
        J.run_due()
        second = J.pending_grants(jid2)
        check("a NEW job asks again - the No left no rule",
              (J.get(jid2) or {}).get("state") == "waiting_approval"
              and len(second) == 1 and second[0]["action"] == GITHUB_ACTION
              and second[0]["state"] == "pending", second)
        check("and the new grant is a different one",
              bool(second) and bool(first_grant)
              and second[0]["id"] != first_grant[0]["id"],
              {"old": first_grant and first_grant[0]["id"],
               "new": second and second[0]["id"]})
        check("still no GitHub request from either job", calls == [], calls)
    finally:
        restore_audit()
        restore_get()


def t_a_second_require_does_not_inherit_a_spent_grant():
    """One Allow once authorises ONE use, so a second ask in the same run parks.

    A handler that asks twice is the shape this proves: the first ask spends
    the answered grant and passes; the second finds no grant it may use, so it
    records a NEW pending one and parks the job again. BITE: make
    `_grant_step()` treat a spent grant as still granted and the second ask
    passes too - the parked check fails.
    """
    fresh()
    asks = {"passed": 0}

    def body(ctx, params):
        ctx.require(PROBE_ACTION)      # spends the owner's one use
        asks["passed"] += 1
        ctx.require(PROBE_ACTION)      # must ask again, not inherit
        asks["passed"] += 1
        return {"ok": True}

    J.register("asks_twice", body)
    code, out = J.handle_create({"kind": "asks_twice", "text": "two questions"})
    check("the live route body created the two-question job", code == 200, (code, out))
    jid = (out or {}).get("id", "")
    J.run_due()
    first = J.pending_grants(jid)
    check("the first question parks it",
          len(first) == 1 and asks["passed"] == 0, {"grants": first, "asks": asks})
    J.handle_answer({"id": jid, "approved": True, "by": "test"})
    J.run_due(now=time.time() + 7200)
    second = J.pending_grants(jid)
    check("the spent grant lets the first ask through",
          asks["passed"] == 1, asks)
    check("the SECOND require parks it again with a NEW pending grant",
          (J.get(jid) or {}).get("state") == "waiting_approval"
          and len(second) == 1 and second[0]["state"] == "pending"
          and second[0]["id"] != first[0]["id"],
          {"state": (J.get(jid) or {}).get("state"), "grants": second})
    check("and it did not run past the second question", asks["passed"] == 1, asks)


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
