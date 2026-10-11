"""jarvis_tasks.py - the job list: work that outlives one chat turn.

    python3 backend/test_tasks.py

No pytest, no network, no real backend. Real SQLite in a temp file.

WHAT THIS PROVES, and where each came from. Every one of these is a failure
the project has written down as a risk, or a mechanism copied deliberately
from OpenMuse (docs/COMPETITORS-OPENMUSE-2026-10-08.md):

1. **An interrupted step that was going out is never retried behind the
   owner's back.** The job goes to `blocked` with a question; an action left
   mid-flight becomes `outcome_unknown`, never `failed` (which invites a
   retry) and never `succeeded` (which is a guess).
2. **A lease, held honestly.** A job whose lease ran out is picked up again;
   an interrupted read-only step simply runs again; two claimers cannot both
   win a claim.
3. **A checkpoint after every step**, so a restart resumes rather than
   starting over - and one step per tick, so a job never freezes the turn
   that started it.
4. **One idempotency key makes one action.** The same key twice returns the
   first action; it never creates a second.
5. **A decision is bound to the words on the card.** A wrong hash is
   refused; an expired card is refused and marked `expired`; an
   unauthorized decision is refused; a double tap gives back the same
   answer instead of doing it twice.
6. **A timeout is not a denial.** The job waits and asks again rather than
   dying, and a real "no" stops the job dead.
7. **The memo never serves a step that leaves the machine.** A `retry_safe`
   step is reused instead of re-run; a step that acts is never reused.
8. **Nothing here can approve anything, reach the network, or write to a
   client what it should not.** The source is read as text for the last
   group of checks, the same way test_gate_outcome.py reads the gate.
"""
import json
import os
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_tasks as T  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    """The shape the real gate's Verdict has for our purposes, including the
    `outcome` word gate-outcome.patch added and the `request_id` a screen
    points at."""

    def __init__(self, allowed, outcome="approved", reason="", request_id=None):
        self.allowed, self.outcome, self.reason = allowed, outcome, reason
        self.request_id = request_id


def fresh():
    """A job list in its own temp file, so no test can touch another or the
    owner's real one."""
    d = tempfile.mkdtemp(prefix="jarvis-tasks-")
    return T.JobList(T.Store(Path(d) / "tasks.db")), d


def run_ok(step):
    return {"ok": True, "tool": step.get("tool")}


def steps_two(*, acts=True, retry_safe=False):
    return [
        {"tool": "read_calendar", "args": {"day": "today"}, "why": "see the day",
         "acts": False, "retry_safe": True},
        {"tool": "send_email", "args": {"to": "a@b.c"}, "why": "send the note",
         "acts": acts, "retry_safe": retry_safe},
    ]


def crash_mid_step(jl, task_id, *, tool, acts):
    """Leave the row exactly as a killed backend leaves it: `running`, an
    expired lease, and the step it was in the middle of recorded. Raising
    LostLease is the ORDERLY path (the run gives the lease back); a crash is
    this."""
    t = jl.store.get_task(task_id)
    t.status = "running"
    t.lease_until = 0.0
    t.lease_id = "crashed"
    t.inflight = {"index": t.at, "tool": tool, "acts": acts}
    jl.store.save(t)


# --------------------------------------------------------------------------
#   1. An interrupted acting step blocks; an action becomes outcome_unknown
# --------------------------------------------------------------------------

def t_interrupted_acting_step_blocks_and_never_retries():
    jl, _ = fresh()
    t = jl.enqueue("Send the note", "send one note", steps_two())
    seen = []

    def run_step(step):
        seen.append(step["tool"])
        return run_ok(step)

    # First tick: the read-only step runs and checkpoints.
    jl.tick(run_step)
    # Then the PC dies in the middle of the acting step.
    crash_mid_step(jl, t.id, tool="send_email", acts=True)
    report = jl.tick(run_step)
    after = jl.store.get_task(t.id)
    check("a job interrupted mid-acting-step goes to blocked, not queued",
          after.status == "blocked", after.status)
    check("and it asks the owner a question rather than continuing",
          bool(after.question) and "Retry or Cancel" in after.question, after.question)
    check("and it is reported as needing attention",
          any(r.get("id") == t.id for r in report["recovered"]), report["recovered"])
    check("and the acting step was NOT run again", "send_email" not in seen, seen)
    # Nothing further runs while it is blocked.
    before = list(seen)
    jl.tick(run_step)
    check("a blocked job does nothing until the owner answers", seen == before, seen)


def t_interrupted_read_only_step_simply_runs_again():
    jl, _ = fresh()
    t = jl.enqueue("Look at the day", "read the calendar",
                   [{"tool": "read_calendar", "args": {}, "why": "see it",
                     "acts": False, "retry_safe": True}])
    ran = []

    def run_step(step):
        ran.append(step["tool"])
        return run_ok(step)

    crash_mid_step(jl, t.id, tool="read_calendar", acts=False)
    jl.tick(run_step)
    after = jl.store.get_task(t.id)
    check("an interrupted read-only step is safe to do again",
          after.status == "succeeded", after.status)
    check("and it really was run again", ran == ["read_calendar"], ran)


def t_a_restart_turns_a_mid_flight_action_into_unknown():
    jl, _ = fresh()
    a = T.propose_action(jl.store, kind="email.send", title="Send the note",
                         shown="To: a@b.c\nSubject: hello\n\nhello", idem="one-note")
    T.decide_action(jl.store, a.id, a.hash, "approve", authorized=True)
    check("an approved action is executing before the restart",
          (T.get_action(jl.store, a.id) or a).status == "executing")
    out = T.startup(jl.store)
    got = T.get_action(jl.store, a.id)
    check("a restart turns a mid-flight action into outcome_unknown",
          got.status == "outcome_unknown", f"{got.status} {out}")
    check("and the words tell the owner to check the other side first",
          "Check the other side" in got.error, got.error)
    check("and it is NOT failed - a failure would invite a retry",
          got.status != "failed")


# --------------------------------------------------------------------------
#   2. The lease
# --------------------------------------------------------------------------

def t_two_claimers_cannot_both_win():
    jl, _ = fresh()
    t = jl.enqueue("One job", "do one thing",
                   [{"tool": "read_calendar", "args": {}, "why": "look"}])
    first = jl.store.get_task(t.id)
    second = jl.store.get_task(t.id)          # a second reader, same version
    a = jl._claim(first, T._now())
    b = jl._claim(second, T._now())
    check("the first claimer wins", a is not None)
    check("the second claimer is refused, not handed the same job", b is None)


def t_a_run_is_recorded_and_reconciled():
    jl, _ = fresh()
    jl.enqueue("A job", "do it", [{"tool": "read_calendar", "args": {}, "why": "look"}])
    jl.tick(lambda s: run_ok(s))
    # A run left "running" is what a killed process leaves behind.
    with sqlite3.connect(str(jl.store.path)) as c:
        c.execute("INSERT INTO runs(id,task_id,started_at,status) "
                  "VALUES('dead','x',0,'running')")
        c.commit()
    n = jl.store.reconcile_runs()
    check("a run left running by a dead process is marked interrupted", n == 1, n)
    check("and the receipts show the finished attempt",
          any(r["status"] == "succeeded" for r in jl.store.runs()), jl.store.runs())


# --------------------------------------------------------------------------
#   3. A checkpoint per step, one step per tick
# --------------------------------------------------------------------------

def t_one_step_per_tick_and_a_checkpoint_after_it():
    jl, _ = fresh()
    t = jl.enqueue("Three steps", "do three things", [
        {"tool": "read_calendar", "args": {}, "why": "one", "acts": False},
        {"tool": "notes_search", "args": {}, "why": "two", "acts": False},
        {"tool": "file_read", "args": {}, "why": "three", "acts": False},
    ])
    calls = []
    jl.tick(lambda s: (calls.append(s["tool"]), run_ok(s))[1])
    check("one tick runs exactly one step", len(calls) == 1, calls)
    mid = jl.store.get_task(t.id)
    check("and the checkpoint is on disk before the next step",
          mid.at == 1 and len(mid.done) == 1, f"at={mid.at} done={len(mid.done)}")
    jl.tick(lambda s: (calls.append(s["tool"]), run_ok(s))[1])
    jl.tick(lambda s: (calls.append(s["tool"]), run_ok(s))[1])
    end = jl.store.get_task(t.id)
    check("three ticks finish three steps", end.status == "succeeded" and end.at == 3,
          f"{end.status} at={end.at}")
    check("each step left its own line in the feed",
          len([e for e in jl.store.events(t.id) if e["kind"] == "step"]) == 3,
          jl.store.events(t.id))
    check("and a receipt exists for the run",
          any(r["status"] == "succeeded" for r in jl.store.runs(t.id)))


def t_an_earlier_result_is_filled_into_a_later_step():
    jl, _ = fresh()
    t = jl.enqueue("Use the first answer", "do it", [
        {"tool": "web_search", "args": {"q": "widgets"}, "why": "find", "acts": False,
         "retry_safe": True},
        {"tool": "send_email", "args": {"body": "{{step 1}}"}, "why": "send it",
         "risky": True, "from_step": 0},
    ])
    jl.tick(lambda s: {"found": "the best widget"})
    asked = {}

    def ask(step):
        asked.update(step)
        return Verdict(False, outcome="denied")

    jl.tick(lambda s: run_ok(s), ask=ask)
    check("the step that asks again carries the REAL earlier result",
          asked.get("args", {}).get("body") == T.canonical({"found": "the best widget"}),
          asked.get("args"))
    # A placeholder with no from_step would run with the braces still in it.
    try:
        jl.enqueue("Stray placeholder", "do it",
                   [{"tool": "send_email", "args": {"body": "{{step 1}}"}, "why": "send"}])
        check("a stray placeholder is refused, never run literally", False,
              "it was accepted")
    except T.Refused as exc:
        check("a stray placeholder is refused, never run literally", True)
        check("and it says which step to name", "from_step" in str(exc), str(exc))


# --------------------------------------------------------------------------
#   4. Idempotency
# --------------------------------------------------------------------------

def t_one_key_makes_one_action():
    jl, _ = fresh()
    first = T.propose_action(jl.store, kind="email.send", title="Send",
                             shown="To: a@b.c", idem="abc")
    second = T.propose_action(jl.store, kind="email.send", title="Send",
                              shown="To: a@b.c", idem="abc")
    check("the same idempotency key returns the same action",
          first.id == second.id, f"{first.id} {second.id}")
    check("and there is exactly one in the list",
          len([a for a in T.list_actions(jl.store) if a.idem == "abc"]) == 1)
    other = T.propose_action(jl.store, kind="email.send", title="Send other",
                             shown="To: z@y.x")
    check("no key means a fresh action", other.id != first.id)
    check("and the keyed id is derived from the key, so it is stable",
          T.idempotent_id("abc") == first.id)


# --------------------------------------------------------------------------
#   5. The card: hash, expiry, authorization, double tap
# --------------------------------------------------------------------------

def t_a_decision_is_bound_to_the_words_that_were_shown():
    jl, _ = fresh()
    a = T.propose_action(jl.store, kind="email.send", title="Send",
                         shown="To: a@b.c\nSubject: hi\n\nhi")
    try:
        T.decide_action(jl.store, a.id, "0" * 64, "approve", authorized=True)
        check("a wrong hash is refused", False, "it was accepted")
    except T.Refused as exc:
        check("a wrong hash is refused", True)
        check("and it says why, in plain words", "changed since" in str(exc), str(exc))
    still = T.get_action(jl.store, a.id)
    check("and nothing was approved by the refused attempt",
          still.status == "awaiting_review", still.status)
    # Re-wording the card produces a different hash - so an old decision
    # cannot be replayed onto new words.
    b = T.propose_action(jl.store, kind="email.send", title="Send",
                         shown="To: a@b.c\nSubject: hi\n\nhi there")
    check("re-wording the card changes its hash", a.hash != b.hash)


def t_nobody_there_means_nothing_is_decided():
    jl, _ = fresh()
    a = T.propose_action(jl.store, kind="email.send", title="Send", shown="To: a@b.c")
    try:
        T.decide_action(jl.store, a.id, a.hash, "approve", authorized=False)
        check("an unauthorized decision is refused", False, "it was accepted")
    except T.Refused as exc:
        check("an unauthorized decision is refused", True)
        check("and it names the fingerprint or PIN",
              "fingerprint" in str(exc) or "PIN" in str(exc), str(exc))
    check("and the action is still waiting, not executing",
          T.get_action(jl.store, a.id).status == "awaiting_review")


def t_an_expired_card_is_refused_and_marked_expired():
    jl, _ = fresh()
    a = T.propose_action(jl.store, kind="email.send", title="Send", shown="To: a@b.c")
    T.decide_action(jl.store, a.id, a.hash, "deny", authorized=True)  # sanity: deny works
    b = T.propose_action(jl.store, kind="home.control", title="Lights", shown="Kitchen")
    # A card answered after its 30 minutes are up. `now` is passed in rather
    # than the clock being faked, so the test says exactly what it means.
    try:
        T.decide_action(jl.store, b.id, b.hash, "approve", authorized=True,
                        now=b.expires_at + 1)
        check("an expired card is refused", False, "it was accepted")
    except T.Refused as exc:
        check("an expired card is refused", True)
        check("and it says nothing was done", "nothing was done" in str(exc), str(exc))
    check("and it is marked expired, not left waiting",
          T.get_action(jl.store, b.id).status == "expired",
          T.get_action(jl.store, b.id).status)
    check("and it never reached executing",
          T.get_action(jl.store, b.id).decided == "",
          T.get_action(jl.store, b.id).decided)


def t_a_double_tap_decides_once():
    jl, _ = fresh()
    a = T.propose_action(jl.store, kind="email.send", title="Send", shown="To: a@b.c")
    first = T.decide_action(jl.store, a.id, a.hash, "approve", authorized=True)
    second = T.decide_action(jl.store, a.id, a.hash, "approve", authorized=True)
    check("the first tap claims the action", first.status == "executing", first.status)
    check("the second tap does not execute it again", second.status == "executing")
    check("and it is not treated as an error", second.id == a.id)


def t_an_action_that_might_have_gone_out_is_unknown_not_failed():
    jl, _ = fresh()
    a = T.propose_action(jl.store, kind="email.send", title="Send", shown="To: a@b.c")
    T.decide_action(jl.store, a.id, a.hash, "approve", authorized=True)

    def boom(action):
        raise T.OutcomeUnknown("the connection dropped after the request went out")

    got = T.run_action(jl.store, a.id, boom, approved=True)
    check("an uncertain send is outcome_unknown", got.status == "outcome_unknown",
          got.status)
    check("not failed", got.status != "failed")
    plain = T.propose_action(jl.store, kind="email.send", title="Send2", shown="To: d@e.f")
    T.decide_action(jl.store, plain.id, plain.hash, "approve", authorized=True)

    def bam(action):
        raise ValueError("no such address")

    other = T.run_action(jl.store, plain.id, bam, approved=True)
    check("an ordinary failure is failed", other.status == "failed", other.status)
    # A third action, approved but never run without the explicit flag.
    third = T.propose_action(jl.store, kind="email.send", title="Send3", shown="To: g@h.i")
    T.decide_action(jl.store, third.id, third.hash, "approve", authorized=True)
    calls = []
    T.run_action(jl.store, third.id, lambda a: calls.append(1))
    check("an unapproved call to run_action does nothing at all",
          calls == [] and T.get_action(jl.store, third.id).status == "executing",
          f"calls={calls}")


# --------------------------------------------------------------------------
#   6. A timeout is not a denial
# --------------------------------------------------------------------------

def t_a_timed_out_card_waits_and_a_denial_stops_the_job():
    jl, _ = fresh()
    t1 = jl.enqueue("Needs a card", "do it",
                    [{"tool": "send_email", "args": {}, "why": "send", "risky": True}])
    jl.tick(lambda s: run_ok(s), ask=lambda s: Verdict(False, outcome="timed_out"))
    got = jl.store.get_task(t1.id)
    check("a timed-out card does not kill the job", got.status == "queued", got.status)
    check("and it did nothing", got.at == 0 and not got.done)

    t2 = jl.enqueue("Will be refused", "do it",
                    [{"tool": "send_email", "args": {}, "why": "send", "risky": True}])
    jl.tick(lambda s: run_ok(s), ask=lambda s: Verdict(False, outcome="denied"))
    got2 = jl.store.get_task(t2.id)
    check("a real no stops the job", got2.status == "failed", got2.status)
    check("and says which step and why", "you said no at step 1" in got2.error, got2.error)


def t_an_undecided_card_waits_without_running():
    jl, _ = fresh()
    t = jl.enqueue("Waiting", "do it",
                   [{"tool": "send_email", "args": {}, "why": "send", "risky": True}])
    ran = []
    jl.tick(lambda s: (ran.append(1), run_ok(s))[1], ask=lambda s: None)
    got = jl.store.get_task(t.id)
    check("an undecided card puts the job in waiting_approval",
          got.status == "waiting_approval", got.status)
    check("and the step was never run", ran == [])
    check("and the feed says what it is waiting for",
          any(e["kind"] == "approval" for e in jl.store.events(t.id)))


# --------------------------------------------------------------------------
#   7. The memo
# --------------------------------------------------------------------------

def t_the_memo_serves_a_safe_step_and_never_an_acting_one():
    jl, _ = fresh()
    t = jl.enqueue("Repeat a read", "do it",
                   [{"tool": "read_calendar", "args": {"d": 1}, "why": "look",
                     "acts": False, "retry_safe": True}])
    jl.tick(lambda s: {"day": "busy"})
    check("the read completed and was recorded",
          jl.store.get_task(t.id).status == "succeeded")
    # Now put the same step back as if the job had to start over.
    back = jl.store.get_task(t.id)
    back.at, back.status, back.lease_id, back.lease_until = 0, "running", "crashed", 0.0
    back.inflight = {"index": 0, "tool": "read_calendar", "acts": False}
    jl.store.save(back)
    ran = []
    jl.tick(lambda s: (ran.append(1), {"day": "different"})[1])
    check("a retry_safe step is served from the memo, not re-run", ran == [], ran)
    got = jl.store.get_task(t.id)
    check("and the recorded result is the one from the memo",
          "busy" in json.dumps(got.done[-1]["result"]) or
          "busy" in json.dumps(got.done[0]["result"]), got.done)

    jl2, _ = fresh()
    t2 = jl2.enqueue("Send twice?", "do it",
                     [{"tool": "send_email", "args": {"to": "a@b.c"}, "why": "send"}])
    jl2.tick(lambda s: {"sent": True})
    back2 = jl2.store.get_task(t2.id)
    back2.at, back2.status, back2.lease_id, back2.lease_until = 0, "running", "crashed", 0.0
    back2.inflight = {"index": 0, "tool": "send_email", "acts": True}
    jl2.store.save(back2)
    ran2 = []
    jl2.tick(lambda s: (ran2.append(1), {"sent": True})[1])
    check("a step that acts is never served from the memo", ran2 == [], ran2)
    check("and an acting step interrupted mid-flight blocks instead",
          jl2.store.get_task(t2.id).status == "blocked",
          jl2.store.get_task(t2.id).status)


# --------------------------------------------------------------------------
#   8. Steering, and what may never happen
# --------------------------------------------------------------------------

def t_stop_is_immediate_and_ungated():
    jl, _ = fresh()
    jl.enqueue("A job", "do it", [{"tool": "read_calendar", "args": {}, "why": "x"}])
    jl.request_stop()
    report = jl.tick(lambda s: run_ok(s))
    check("Stop stops the tick at once", report["stop"] is True)
    check("and nothing was claimed", report["claimed"] == [], report["claimed"])
    jl.clear_stop()
    check("and clearing it lets work start again",
          jl.tick(lambda s: run_ok(s))["claimed"] != [])


def t_pause_resume_cancel_retry_and_answer():
    jl, _ = fresh()
    t = jl.enqueue("Steer me", "do it", [
        {"tool": "read_calendar", "args": {}, "why": "one", "acts": False},
        {"tool": "read_calendar", "args": {}, "why": "two", "acts": False},
    ])
    jl.tick(lambda s: run_ok(s))
    jl.pause(t.id)
    check("a paused job does not run", jl.tick(lambda s: run_ok(s))["claimed"] == [])
    check("pause is reported as paused", jl.store.get_task(t.id).status == "paused")
    jl.resume(t.id)
    check("resume puts it back in the queue",
          jl.store.get_task(t.id).status == "queued")
    jl.cancel(t.id)
    check("cancel is final for this job", jl.store.get_task(t.id).status == "cancelled")
    jl.retry(t.id)
    check("retry puts a cancelled job back in the queue",
          jl.store.get_task(t.id).status == "queued")
    check("and Retry is the owner's act, not something a tick does by itself",
          "retry" in [e["title"] for e in jl.store.events(t.id)])

    t2 = jl.enqueue("Ask me", "do it", [{"tool": "read_calendar", "args": {}, "why": "x"}])
    got = jl.store.get_task(t2.id)
    got.status = "waiting_input"
    jl.store.save(got)
    jl.answer(t2.id, "the blue one")
    check("answering a question puts the job back in the queue",
          jl.store.get_task(t2.id).status == "queued")


def t_the_queue_refuses_rather_than_dropping():
    jl, _ = fresh()
    for i in range(T.MAX_WAITING):
        jl.enqueue(f"job {i}", "do it", [{"tool": "read_calendar", "args": {}, "why": "x"}])
    try:
        jl.enqueue("one too many", "do it",
                   [{"tool": "read_calendar", "args": {}, "why": "x"}])
        check("a full queue refuses", False, "it was accepted")
    except T.Refused as exc:
        check("a full queue refuses", True)
        check("and says nothing was added", "nothing was added" in str(exc), str(exc))
    for bad in ([], [{"why": "no tool"}], [{"tool": "x"}]):
        try:
            jl.enqueue("bad", "do it", bad)
            check(f"a malformed job is refused: {bad}", False)
        except T.Refused:
            check(f"a malformed job is refused: {bad}", True)


def t_the_private_words_are_not_published():
    jl, _ = fresh()
    jl.enqueue("Take the bins out for mum", "take the bins out", [
        {"tool": "send_email", "args": {"to": "mum@example.com", "body": "private"},
         "why": "tell mum", "risky": True}])
    blob = json.dumps(jl.status())
    check("the counted summary carries no task title",
          "bins" not in blob, blob[:200])
    check("and no step argument", "mum@example.com" not in blob)
    check("but it does name the tool and count the step",
          "send_email" in blob and "\"steps\": 1" in blob)


# --------------------------------------------------------------------------
#   9. The source, read as text - the claims that must not rot
# --------------------------------------------------------------------------

def t_the_module_makes_no_network_call_and_no_key():
    src = (HERE / "jarvis_tasks.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    for banned in ("import socket", "import urllib", "import requests", "http.client",
                   "import ssl", "subprocess", "os.system", "eval(", "exec("):
        check(f"jarvis_tasks.py does not use {banned}", banned not in body)
    for needed in ("def startup", "def guard", "class JobList", "UNKNOWN_WORDS"):
        check(f"jarvis_tasks.py still defines {needed}", needed in src)


def t_nothing_in_the_decision_path_can_approve_by_itself():
    """The same reading test test_gate_outcome.py uses for the no-approve-all
    claim: prose about code goes stale, so the code is read."""
    src = (HERE / "jarvis_tasks.py").read_text(encoding="utf-8")
    check("deciding needs an explicit authorization",
          "authorized: bool = False" in src)
    check("running an action needs an explicit approval",
          "approved: bool = False" in src)
    check("a step's 'acts' defaults to True - assume it changes something",
          's.get("acts", True)' in src)
    check("the four refusals are all still in the decision path",
          "changed since it was shown" in src
          and "fingerprint or PIN" in src
          and "That card expired" in src
          and "action.status != \"awaiting_review\"" in src)
    check("the unknown-outcome wording is still the one that tells the owner "
          "to check first",
          "Check the other " in src and "side before doing it again" in src)
    check("the module never imports the gate, so it cannot approve anything",
          "import jarvis_gate" not in src)
    check("the readable feed is marked local-only",
          "PC's own window only" in src)


def t_a_job_that_stops_to_ask_carries_its_question():
    """`waiting_input` is useless without the question: a screen would say
    "needs an answer" and have nothing to show. Both states that need the owner
    - blocked and waiting_input - carry it, and nothing else does."""
    jl, _ = fresh()
    jl.enqueue("Waiting on you", "do it",
               [{"tool": "read_calendar", "args": {}, "why": "x"}])
    t2 = jl.enqueue("Ask me something", "do it",
                    [{"tool": "send_email", "args": {}, "why": "send"}])
    jl.enqueue("Just running", "do it",
               [{"tool": "read_calendar", "args": {}, "why": "x"}])
    got = jl.store.get_task(t2.id)
    got.status, got.question = "waiting_input", "Which order number is it?"
    jl.store.save(got)

    rows = {r["id"]: r for r in jl.status()["tasks"]}
    asking = rows[t2.id]
    check("a waiting_input job is flagged as needing the owner",
          asking["needs_attention"] is True, asking)
    check("and it carries the question the screen has to show",
          asking["question"] == "Which order number is it?", asking["question"])
    for tid, row in rows.items():
        if tid != t2.id:
            check("a job that has not asked carries no question", row["question"] == "",
                  row["question"])
            check("and is not flagged as needing the owner",
                  row["needs_attention"] is False, row)


# --------------------------------------------------------------------------
#   10. The patch, rehearsed on the text earlier patches wrote
# --------------------------------------------------------------------------

def t_the_patch_applies_to_the_real_backend():
    """`tasks.patch` against the REAL `jarvis_hud.py`, byte for byte.

    WHY THIS IS NOT THE STAND-IN REHEARSAL ANY MORE. Until 2026-10-08 the only
    honest question a checkout could ask was "does this patch match the text
    the patches before it wrote?", answered by `backend/_skeleton.py`. On
    2026-10-08 that proved too weak: `tasks.patch` passed the stand-in and then
    did **not** apply to the real file, because a later patch
    (`note-capture.patch`) had inserted a route between the lines the stand-in
    laid side by side. The stand-in cannot see a patch that came afterwards.

    `jarvis-backend/` is a published copy of the real program, so the rehearsal
    is against that file: apply, check, and reverse must all succeed, and the
    bytes must come back identical. `tools/gen_tasks_patch.py` generates the
    patch from the same file, so the two cannot drift apart.
    """
    import shutil
    import subprocess
    real = HERE.parent / "jarvis-backend" / "jarvis_hud.py"
    patch = HERE / "tasks.patch"
    if not real.exists():
        print("        (skipped: this checkout has no jarvis-backend/ copy of the program)")
        return
    git = shutil.which("git")
    if not git:
        print("        (skipped: git is not installed)")
        return
    # `-c core.autocrlf=false`: the temporary folder has no .gitattributes, and
    # a Windows clone with autocrlf=true would otherwise have git rewrite the
    # file's endings mid-test - a failure with nothing to do with the patch.
    cmd = [git, "-c", "core.autocrlf=false", "-c", "core.eol=lf"]
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-real-patch-"))
    try:
        original = real.read_bytes()
        (tmp / "jarvis_hud.py").write_bytes(original)
        (tmp / "tasks.patch").write_bytes(patch.read_bytes())
        subprocess.run([git, "init", "-q", "."], cwd=tmp, capture_output=True)
        body = ""
        ok = True
        for args in (["apply", "--check", "tasks.patch"], ["apply", "tasks.patch"]):
            r = subprocess.run(cmd + args, cwd=tmp, capture_output=True, text=True)
            if r.returncode != 0:
                ok = False
                check(f"the real jarvis_hud.py accepts tasks.patch ({' '.join(args)})",
                      False, r.stderr.strip())
                break
        if ok:
            # Read the applied text BEFORE reversing: the reverse puts the file
            # back, so reading afterwards would only ever show the original.
            body = (tmp / "jarvis_hud.py").read_text(encoding="utf-8")
            r = subprocess.run(cmd + ["apply", "--reverse", "tasks.patch"], cwd=tmp,
                               capture_output=True, text=True)
            if r.returncode != 0:
                ok = False
                check("and the reverse applies", False, r.stderr.strip())
        if ok:
            check("the real jarvis_hud.py accepts tasks.patch, applies it and reverses it",
                  True)
            check("and reversing gives the file back byte for byte",
                  (tmp / "jarvis_hud.py").read_bytes() == original)
            check("GET /api/tasks is reached", 'if path == "/api/tasks":' in body)
            check("it checks the origin and the token",
                  "_origin_ok(self)" in body and "_token_ok(self)" in body)
            check("it boots the job list once, so an interrupted send is recovered "
                  "without a startup hook to hang it on",
                  "jarvis_tasks.boot_once()" in body)
            check("and the counted summary is what is sent",
                  "jarvis_tasks.JobList().status()" in body)
            check("the routes around it are untouched",
                  'if path == "/api/task":' in body
                  and 'if path == "/api/notes/capture":' in body)
            check("the steering routes are reached",
                  'if route in ("/api/tasks/act", "/api/tasks/input"):' in body)
            check("and they check the origin and the token too",
                  body.count("_origin_ok(self)") >= 2
                  and body.count("_token_ok(self)") >= 2)
            check("Pause, Resume, Cancel and Retry are the only acts offered",
                  '"pause", "resume", "cancel", "retry"' in body)
            check("an unknown act is refused rather than guessed at",
                  "act must be pause, resume" in body)
            check("a refusal from the job list comes back as a plain 409",
                  "except jarvis_tasks.Refused as exc:" in body)
            steering = body.split("api/tasks/act")[1].split('if route in ("/api/task/pause"')[0]
            check("and no steering route can approve anything",
                  "jarvis_gate" not in steering and "owner_check" not in steering
                  and "approved=True" not in steering and "check(" not in steering)
            check("and the code says that plainly, where the next reader will look",
                  "Nothing here approves anything" in steering)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
#   11. The split: an approved plan becomes a job, and every step still asks
# --------------------------------------------------------------------------
def _plan():
    """A plan shaped exactly like `jarvis_plan.propose()`'s output: its own
    dataclass with `.goal` and `.steps`, each step a `PlanStep`."""
    class Step:
        def __init__(self, tool, why, **kw):
            self.tool, self.why = tool, why
            self.args = kw.get("args", {})
            self.risky = kw.get("risky", False)
            self.from_step = kw.get("from_step", None)

    class Plan:
        goal = "book the trip"
        steps = [
            Step("web_search", "find the times", args={"q": "timetable"}),
            Step("send_email", "confirm the booking", args={"to": "a@b.c"}, risky=True),
        ]
    return Plan()


def t_an_unapproved_plan_adds_nothing():
    jl, _ = fresh()
    try:
        T.from_plan(jl, _plan())
        check("an unapproved plan adds no job", False, "it was accepted")
    except T.Refused as exc:
        check("an unapproved plan adds no job", True)
        check("and it says so plainly", "not approved" in str(exc), str(exc))
    check("and the list is still empty", jl.store.list_tasks() == [])
    try:
        T.from_plan(jl, _plan(), approved=True, plan_key="trip")
        T.from_plan(jl, _plan(), approved=True, plan_key="trip")
        check("the same plan key makes one job, not two",
              len(jl.store.list_tasks()) == 1, jl.store.list_tasks())
    except T.Refused as exc:
        check("the same plan key makes one job, not two", False, repr(exc))


def t_a_plan_becomes_a_job_with_nothing_softened():
    jl, _ = fresh()
    t = T.from_plan(jl, _plan(), approved=True)
    check("the job is named after the plan's own goal", t.title == "book the trip", t.title)
    check("both steps are there, in order",
          [s["tool"] for s in t.steps] == ["web_search", "send_email"],
          [s["tool"] for s in t.steps])
    check("the risky step is STILL risky, so it will ask again on its own card",
          t.steps[1]["risky"] is True, t.steps[1])
    check("a plan step defaults to acting, so an interruption blocks rather than retries",
          all(s["acts"] is True for s in t.steps))
    check("and none of them is retry_safe, so no step is replaced by a recorded result",
          not any(s["retry_safe"] for s in t.steps))
    check("each step kept the reason the plan gave",
          all(s["why"] for s in t.steps))


def t_an_approved_plan_runs_through_the_gate_and_asks_again_for_a_risky_step():
    """The whole split, end to end, with the gate injected exactly as the real
    one is: `plan -> approved -> job -> one step per tick -> the risky step's
    own card -> done`. Nothing here is a stand-in for the approval itself."""
    jl, _ = fresh()
    t = T.from_plan(jl, _plan(), approved=True)
    asked, ran = [], []

    def gate_check(step):
        asked.append(step.get("tool"))
        if step.get("tool") == "send_email":
            return Verdict(False, outcome="denied")      # the owner says no
        return Verdict(True, outcome="approved", request_id="r1")

    def run_step(step):
        ran.append(step["tool"])
        return {"ok": True}

    ask = T.gate_ask(gate_check)
    jl.tick(run_step, ask=ask)                       # step 1: safe, runs
    jl.tick(run_step, ask=ask)                       # step 2: risky, asked, denied
    got = jl.store.get_task(t.id)
    check("the safe step ran", ran == ["web_search"], ran)
    check("the risky step was asked about on its own card, inside the job",
          "send_email" in asked, asked)
    check("and a real no stopped the job at that step, keeping what was done",
          got.status == "failed" and got.at == 1 and len(got.done) == 1,
          f"{got.status} at={got.at} done={len(got.done)}")
    check("the job's own approval did not carry the risky step",
          "you said no at step 2" in got.error, got.error)


def t_the_gate_adapter_never_turns_silence_into_permission():
    jl, _ = fresh()
    t = jl.enqueue("Needs a card", "do it",
                   [{"tool": "send_email", "args": {}, "why": "send", "risky": True}])
    ran = []
    # A gate that cannot answer must mean "not decided", never "yes".
    def exploding_gate(step):
        raise RuntimeError("the gate is not available")

    jl.tick(lambda s: (ran.append(1), run_ok(s))[1], ask=T.gate_ask(exploding_gate))
    check("a gate that cannot answer leaves the job waiting, not acting",
          ran == [] and jl.store.get_task(t.id).status == "waiting_approval",
          f"ran={ran} state={jl.store.get_task(t.id).status}")
    # `None` from the gate: still waiting, still nothing run.
    t2 = jl.enqueue("Also needs a card", "do it",
                    [{"tool": "send_email", "args": {}, "why": "send", "risky": True}])
    gone = jl.store.get_task(t.id)
    gone.status = "cancelled"
    jl.store.save(gone)
    jl.tick(lambda s: (ran.append(1), run_ok(s))[1], ask=T.gate_ask(lambda s: None))
    check("None from the gate is 'not decided yet', so the job waits",
          jl.store.get_task(t2.id).status == "waiting_approval",
          jl.store.get_task(t2.id).status)
    check("and still nothing was run", ran == [], ran)


def t_the_gate_adapter_reports_the_gates_own_words():
    seen = {}

    def gate(step):
        seen["called"] = step
        return Verdict(False, outcome="timed_out", reason="nobody was there",
                       request_id="r7")

    out = T.gate_ask(gate)({"tool": "send_email"})
    check("the gate's own outcome is carried through", out.outcome == "timed_out")
    check("its reason is kept", out.reason == "nobody was there")
    check("its request id is kept, so a screen can point at the card",
          out.request_id == "r7")
    check("and allowed is False - the adapter cannot invent a yes", out.allowed is False)
    check("the step was handed over untouched",
          seen.get("called") == {"tool": "send_email"}, seen)
    # An allow is an allow only because the gate said so, and a timeout is
    # carried as a timeout rather than flattened into a denial.
    check("an allow is passed through as one",
          T.gate_ask(lambda s: Verdict(True))({"tool": "x"}).allowed is True)
    check("a verdict with no outcome reads as a denial, not an approval",
          T.gate_ask(lambda s: Verdict(False))({"tool": "x"}).outcome == "denied")


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
