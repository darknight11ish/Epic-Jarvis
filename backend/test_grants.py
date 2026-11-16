"""test_grants.py - the engine behind one plan card per job, and trusted mode.

    python -B backend/test_grants.py

WHAT THIS SUITE IS FOR
`backend/jarvis_grants.py` is deliberately wired to nothing yet. It is the
engine the design document `docs/PLAN-CARD-AND-TRUSTED-MODE.md` describes, and
this suite is the whole proof that its rules are enforced in code before any
caller can lean on them. Every case drives the real module with an injected
clock, a throwaway store and a stand-in for the gate that records the three
grant events; nothing sleeps, nothing touches the network, and nothing is
written to disk.

THE NAMED CASES THE BRIEF ASKS FOR, and where each lives:
  - the cap reached exactly at 20, and the 21st refused
        t_the_cap_is_reached_exactly_at_twenty
  - a requested cap of 99 clamped to 30
        t_a_requested_cap_of_99_is_clamped_to_thirty
  - each banned verb refused
        t_each_banned_verb_is_refused
  - each of the eleven allowed shapes accepted
        t_each_of_the_eleven_shapes_is_accepted
  - an unrelated action (a file write) not covered
        t_a_file_write_is_not_covered_by_trusted_mode
  - a pending card not swallowed
        t_a_pending_card_is_never_swallowed
  - a stale stream voids the window
        t_a_stale_stream_voids_the_window
  - expiry at exactly sixty minutes
        t_a_window_expires_at_exactly_sixty_minutes
  - a restart wipes the window
        t_a_restart_wipes_the_window
  - a pinned head mismatch refused
        t_a_pinned_merge_refuses_a_different_head
  - a closed window cannot be reopened
        t_a_closed_window_cannot_be_reopened
Plus the four corrections made to the prototype during the engine review: the
per-action cap reading, the bans inspecting modifier arguments, the pending card
answering "card" rather than "refuse", and `granted` being written only when a
card would have been raised.

THE AUDIT IS THE GATE'S OWN
`jarvis_gate.grant_made` / `granted` / `grant_ended` are the three writers the
live gate owns. This suite installs a stand-in module with those three names,
so the calls are proved without importing the 3,380-line gate (which needs the
owner's files). `t_the_three_audit_writers_are_the_gates_own` also reads the
published base and the module's own source, proving the event strings are not
copied into the engine.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import traceback
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------------------
# The gate stand-in: exactly the three writers the live gate owns
# ---------------------------------------------------------------------------

GATE_EVENTS = []


def _writer(event):
    def write(**fields):
        GATE_EVENTS.append({"event": event, **fields})

    return write


FAKE_GATE = types.ModuleType("jarvis_gate")
FAKE_GATE.grant_made = _writer("grant_made")
FAKE_GATE.granted = _writer("granted")
FAKE_GATE.grant_ended = _writer("grant_ended")
sys.modules["jarvis_gate"] = FAKE_GATE

import jarvis_grants as jg  # noqa: E402
import _base  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures and small helpers
# ---------------------------------------------------------------------------

T0 = datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc)   # 09:00 PT
T5 = T0 + timedelta(minutes=5)
T59 = T0 + timedelta(minutes=59)
T59_59 = T0 + timedelta(minutes=59, seconds=59)
T60 = T0 + timedelta(minutes=60)
T61 = T0 + timedelta(minutes=61)
SHA_A = "a" * 40
SHA_B = "b" * 40
REPO = "darknight11ish/Epic-Jarvis"
OTHER = "darknight11ish/other"
NEW_REPO = "darknight11ish/new-repo"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this run cannot make: printed as `skip`, never counted a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def target(repo=REPO, **fields):
    return jg.Target(repo, **fields)


def trusted(
    actions=("*",),
    targets=None,
    *,
    job_id="chat-1",
    issued_at=T0,
    expires_at=T60,
    approved=True,
    cap=jg.MAX_TRUSTED_ACTIONS,
):
    if isinstance(actions, str):
        actions = {actions}
    return jg.TrustedSession(
        "trusted",
        job_id,
        actions,
        targets if targets is not None else (target(),),
        issued_at,
        expires_at,
        approved,
        max_actions=cap,
    )


def plan(
    actions,
    targets,
    *,
    job_id="job-1",
    issued_at=T0,
    expires_at=T0 + timedelta(hours=3),
    void_if=(),
):
    return jg.PlanGrant(
        "plan", job_id, actions, targets, issued_at, expires_at, void_if
    )


def merge_args(number=1295, head=SHA_A, checks=True, **extra):
    args = {"repo": REPO, "pr": number}
    if head is not None:
        args["head_sha"] = head
    if checks is not None:
        args["checks_passed"] = checks
    args.update(extra)
    return args


def push_args(branch="feature/x", **extra):
    args = {"repo": REPO, "branch": branch, "stage": "push"}
    args.update(extra)
    return args


def write_args(file="src/a.py", number=1295, **extra):
    args = {"repo": REPO, "pr": number, "file": file, "stage": "write"}
    args.update(extra)
    return args


def review_args(event="COMMENT", number=1295, **extra):
    args = {"repo": REPO, "pr": number, "event": event}
    args.update(extra)
    return args


def expect(decision, outcome):
    assert decision.outcome == outcome, (
        f"expected {outcome}, got {decision.outcome}: {decision.reason}"
    )
    assert decision.reason.strip(), "a decision needs a readable reason"
    assert decision.why_it_matters.strip(), "a decision needs a why_it_matters"
    return decision


def raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    except Exception as exc:  # noqa: BLE001 - the test wants the wrong type named
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(exc).__name__}: {exc}"
        ) from None
    raise AssertionError(f"expected {exc_type.__name__}, nothing was raised")


def events(name):
    return [row for row in GATE_EVENTS if row["event"] == name]


def reset_audit():
    GATE_EVENTS.clear()


# ---------------------------------------------------------------------------
# The allowlist: exactly eleven GitHub shapes
# ---------------------------------------------------------------------------

ELEVEN = {
    "github_comment",
    "github_open_issue",
    "github_rerun_workflow",
    "github_create_repo",
    "github_merge_pr",
    "github_fix_and_push",
    "github_open_pr",
    "github_issue_labels",
    "github_edit_pr",
    "github_pr_review",
    "github_issue_state",
}


def t_the_allowlist_is_exactly_the_eleven_shapes():
    check("the allowlist has exactly eleven actions",
          len(jg.TRUSTED_ALLOWLIST) == 11, jg.TRUSTED_ALLOWLIST)
    check("... and they are the owner's eleven, by name",
          jg.TRUSTED_ALLOWLIST == frozenset(ELEVEN),
          sorted(jg.TRUSTED_ALLOWLIST ^ frozenset(ELEVEN)))
    check("github_workflow is outside the trusted allowlist",
          "github_workflow" not in jg.TRUSTED_ALLOWLIST)
    check("the fix flow's local write is outside the trusted allowlist",
          "github_fix_write" not in jg.TRUSTED_ALLOWLIST)
    check("... but both are real GitHub writes a plan may name",
          {"github_workflow", "github_fix_write"} <= jg.GITHUB_WRITE_ACTIONS)


def t_each_of_the_eleven_shapes_is_accepted():
    session = trusted(actions={"*"}, targets=(target(REPO), target(NEW_REPO)))
    check("'*' expanded to the allowlist at open, and only the allowlist",
          session.allowed_writes == jg.TRUSTED_ALLOWLIST)
    cases = (
        ("comment", "github_comment", {"repo": REPO, "pr": 1295}),
        ("open_issue", "github_open_issue", {"repo": REPO, "title": "one issue"}),
        ("rerun_workflow", "github_rerun_workflow", {"repo": REPO, "run": 7}),
        ("create_repo", "github_create_repo", {"repo": NEW_REPO}),
        ("merge_pr", "github_merge_pr",
         {"repo": REPO, "pr": 1295, "head_sha": SHA_A, "checks_passed": True}),
        ("fix_and_push", "github_fix_and_push",
         {"repo": REPO, "branch": "feature/x", "stage": "push"}),
        ("open_pr", "github_open_pr",
         {"repo": REPO, "branch": "feature/y", "stage": "push"}),
        ("issue_labels", "github_issue_labels", {"repo": REPO, "pr": 1295}),
        ("edit_pr", "github_edit_pr", {"repo": REPO, "pr": 1295}),
        ("pr_review", "github_pr_review", review_args()),
        ("issue_state", "github_issue_state", {"repo": REPO, "issue": 1295}),
    )
    check("the cases really are the eleven shapes", len(cases) == 11)
    for shape, tool, args in cases:
        decision = jg.consult(session, tool, args, T5, stream_fresh=True)
        check(f"trusted mode accepts {shape} ({tool})",
              decision.outcome == "run", decision.reason)
    local = jg.consult(session, "github_fix_and_push", write_args(), T5,
                       stream_fresh=True)
    check("the fix flow's local write stage is not covered, even by '*'",
          local.outcome == "card" and "eleven" in local.reason, local.reason)
    prepare = jg.consult(session, "github_fix_and_push",
                         {"repo": REPO, "number": 1295, "stage": "prepare"},
                         T5, stream_fresh=True)
    check("the fix flow's prepare stage IS covered (it names the pull request)",
          prepare.outcome == "run", prepare.reason)
    workflow = jg.consult(session, "github_workflow",
                          {"repo": REPO, "run": 3}, T5, stream_fresh=True)
    check("github_workflow is not covered either",
          workflow.outcome == "card" and "eleven" in workflow.reason,
          workflow.reason)


def t_a_file_write_is_not_covered_by_trusted_mode():
    session = trusted(actions={"*"})
    for tool, args in (
        ("write_file", {"path": "notes.txt", "content": "x"}),
        ("send_email", {"to": "someone@example.com", "subject": "hi"}),
        ("set_credential", {"name": "token"}),
        ("spend_money", {"amount": 10}),
    ):
        decision = expect(
            jg.consult(session, tool, args, T5, stream_fresh=True), "card"
        )
        check(f"{tool} is carded, not run, inside a trusted window",
              "github" in decision.reason.lower(), decision.reason)


# ---------------------------------------------------------------------------
# The cap: 20 uses per action, ceiling 30, clamped
# ---------------------------------------------------------------------------


def t_the_cap_is_reached_exactly_at_twenty():
    check("MAX_TRUSTED_ACTIONS is 20", jg.MAX_TRUSTED_ACTIONS == 20)
    store = jg.GrantStore()
    session = store.open_trusted("c1", {"github_comment"}, (target(),), T0)
    check("opening a window writes grant_made once",
          session is not None and len(events("grant_made")) == 1)
    for index in range(20):
        decision = store.check(
            "chat:c1", "github_comment", {"repo": REPO, "pr": 1295}, T5,
            stream_fresh=True,
        )
        if decision.outcome != "run":
            check(f"use {index + 1} of 20 runs", False, decision.reason)
            return
    check("all 20 uses of one action run", session.used("github_comment") == 20)
    check("... and 20 granted lines were written", len(events("granted")) == 20)
    decision = expect(
        store.check(
            "chat:c1", "github_comment", {"repo": REPO, "pr": 1295}, T5,
            stream_fresh=True,
        ),
        "refuse",
    )
    check("the 21st use is refused", "20" in decision.reason
          and "cap" in decision.reason.lower(), decision.reason)
    check("... and it did not run or spend a 21st use",
          session.used("github_comment") == 20 and len(events("granted")) == 20)


def t_a_requested_cap_of_99_is_clamped_to_thirty():
    store = jg.GrantStore()
    session = store.open_trusted(
        "c1", {"github_comment"}, (target(),), T0, max_actions=99
    )
    check("a requested cap of 99 is clamped to the hard ceiling of 30",
          session is not None
          and session.max_actions == jg.MAX_TRUSTED_ACTIONS_CEILING == 30,
          None if session is None else session.max_actions)
    session = trusted(actions={"github_comment"}, cap=99)
    check("... the class clamps too, not only the store",
          session.max_actions == 30)
    for _ in range(30):
        if jg.consult(session, "github_comment",
                      {"repo": REPO, "pr": 1295}, T5,
                      stream_fresh=True).outcome != "run":
            check("30 uses run at the ceiling", False)
            return
        jg.record_action(session, "github_comment")
    check("30 uses run at the ceiling", session.used("github_comment") == 30)
    decision = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295},
                   T5, stream_fresh=True),
        "refuse",
    )
    check("the 31st use is refused", "30" in decision.reason, decision.reason)


def t_the_cap_is_per_action():
    session = trusted(actions={"*"}, cap=2)
    for _ in range(2):
        expect(jg.consult(session, "github_merge_pr", merge_args(), T5,
                          stream_fresh=True), "run")
        jg.record_action(session, "github_merge_pr")
    check("two uses of merge_pr are spent",
          session.used("github_merge_pr") == 2)
    expect(jg.consult(session, "github_merge_pr", merge_args(), T5,
                      stream_fresh=True), "refuse")
    decision = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                   stream_fresh=True),
        "run",
    )
    check("a different action still has its own two uses",
          session.remaining("github_comment") == 2, decision.reason)


def t_a_bool_or_a_negative_cap_cannot_be_a_cap():
    raises(ValueError, trusted, actions={"github_comment"}, cap=True)
    session = trusted(actions={"github_comment"}, cap=0)
    check("a cap of zero is clamped up to one, never left at zero",
          session.max_actions == 1)


# ---------------------------------------------------------------------------
# The standing bans: each verb, inside a valid window
# ---------------------------------------------------------------------------


def t_each_banned_verb_is_refused():
    session = trusted(actions={"*"})
    cases = (
        ("auto_merge (modifier)", "github_merge_pr", merge_args(auto_merge=True)),
        ("auto_merge (action)", "github_auto_merge", {"repo": REPO}),
        ("squash (modifier)", "github_merge_pr", merge_args(method="squash")),
        ("squash (action)", "github_squash_merge", {"repo": REPO}),
        ("rebase (modifier)", "github_merge_pr", merge_args(merge_method="rebase")),
        ("force_push", "github_fix_and_push", push_args(force=True)),
        ("admin_bypass", "github_merge_pr", merge_args(admin_bypass=True)),
        ("workflow_dispatch (action)", "github_workflow_dispatch", {"repo": REPO}),
        ("workflow_dispatch (modifier)", "github_workflow",
         {"repo": REPO, "run": 3, "mode": "dispatch"}),
        ("APPROVE", "github_pr_review", review_args(event="APPROVE")),
        ("delete_branch", "github_delete_branch", {"repo": REPO, "branch": "x"}),
        ("delete_release", "github_delete_release", {"repo": REPO, "tag": "v1"}),
    )
    for verb, tool, args in cases:
        decision = jg.consult(session, tool, args, T5, stream_fresh=True)
        check(f"{verb} is refused inside a valid window",
              decision.outcome == "refuse" and "ban" in decision.reason.lower(),
              f"{decision.outcome}: {decision.reason}")
    check("a ban is refused even with no grant at all",
          jg.consult(None, "github_delete_branch", {"repo": REPO, "branch": "x"},
                     T5, stream_fresh=True).outcome == "refuse")
    check("a push to a protected branch is refused too",
          jg.consult(session, "github_fix_and_push", push_args(branch="main"),
                     T5, stream_fresh=True).outcome == "refuse")


def t_a_ban_beats_a_plan_grant():
    grant = plan({"github_merge_pr"}, (target(number=1295, head=SHA_A),))
    decision = expect(
        jg.consult(grant, "github_merge_pr", merge_args(method="squash"), T5,
                   stream_fresh=True),
        "refuse",
    )
    check("a plan that named the merge cannot make a squash legal",
          "ban" in decision.reason.lower(), decision.reason)


# ---------------------------------------------------------------------------
# Pending cards, stale streams, lockdown, reads
# ---------------------------------------------------------------------------


def t_a_pending_card_is_never_swallowed():
    session = trusted(actions={"github_comment"})
    decision = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                   stream_fresh=True, pending_cards=("card-7",)),
        "card",
    )
    check("a pending card is not authorised, and the answer is 'card' (the "
          "card is still the owner's to answer)",
          "card-7" in decision.reason, decision.reason)
    grant = plan({"github_comment"}, (target(number=1295),))
    expect(jg.consult(grant, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                      stream_fresh=True, pending_cards=("card-8",)), "card")
    check("a pending card is not logged as granted",
          events("granted") == [])


def t_a_stale_stream_voids_the_window():
    session = trusted(actions={"github_comment"})
    expect(jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295},
                      T5, stream_fresh=True), "run")
    decision = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                   stream_fresh=False),
        "refuse",
    )
    check("a stale stream refuses the write", "stale" in decision.reason.lower(),
          decision.reason)
    check("... and voids the window itself", session.is_closed)
    ended = events("grant_ended")
    check("... with one grant_ended line, state 'stale'",
          len(ended) == 1 and ended[0]["state"] == "stale", ended)
    again = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                   stream_fresh=True),
        "card",
    )
    check("the same window cannot be used after the stream recovers",
          "closed" in again.reason.lower(), again.reason)
    fresh = trusted(actions={"github_comment"})
    expect(jg.consult(fresh, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                      stream_fresh=True), "run")


def t_void_stale_is_the_call_the_watcher_makes():
    session = trusted(actions={"github_comment"})
    jg.void_stale(session, T5)
    check("void_stale() closes the window without a tool call",
          session.is_closed and "stale" in (session.closed_reason or ""))
    jg.void_stale(session, T5)
    check("... and a second notice writes no second end line",
          len(events("grant_ended")) == 1)
    raises(TypeError, jg.void_stale, plan({"github_comment"},
                                         (target(number=1295),)))


def t_a_stale_stream_blocks_a_read():
    decision = expect(
        jg.consult(None, "github_list", {}, T5, stream_fresh=False), "refuse"
    )
    check("nothing runs on a stale stream, not even a read",
          "stale" in decision.reason.lower(), decision.reason)


def t_reads_run_without_a_grant():
    for tool in ("github_list", "github_read_file", "github_ci_status",
                 "github_pr_scan", "github_pr_detail", "github_search"):
        decision = expect(jg.consult(None, tool, {}, T5, stream_fresh=True), "run")
        check(f"{tool} is a card-free read", decision.grant_kind is None)


def t_lockdown_outranks_a_window():
    session = trusted(actions={"github_comment"})
    decision = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                   stream_fresh=True, lockdown=True),
        "card",
    )
    check("lockdown makes even a covered write ask",
          "lockdown" in decision.reason.lower(), decision.reason)


def t_an_unknown_tool_or_an_unreadable_request_is_refused():
    expect(jg.consult(None, "github_frobnicate", {}, T5, stream_fresh=True),
           "refuse")
    decision = expect(
        jg.consult(None, "github_merge_pr", {"pr": 1295}, T5, stream_fresh=True),
        "refuse",
    )
    check("a write with no repository is refused, not guessed at",
          "repository" in decision.reason.lower(), decision.reason)
    expect(jg.consult(None, "github_merge_pr",
                      {"repo": "not a repo", "pr": 1295}, T5,
                      stream_fresh=True), "refuse")


# ---------------------------------------------------------------------------
# Expiry, restart and reopening
# ---------------------------------------------------------------------------


def t_a_window_expires_at_exactly_sixty_minutes():
    session = trusted(actions={"github_comment"})
    expect(jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295},
                      T59_59, stream_fresh=True), "run")
    decision = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295}, T60,
                   stream_fresh=True),
        "card",
    )
    check("at exactly sixty minutes the window is closed",
          "closed at" in decision.reason or "60 minutes" in decision.reason,
          decision.reason)
    raises(ValueError, trusted, actions={"github_comment"},
           expires_at=T0 + timedelta(minutes=60, seconds=1))


def t_a_restart_wipes_the_window():
    store = jg.GrantStore()
    session = store.open_trusted("c1", {"github_comment"}, (target(),), T0)
    expect(jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295},
                      T5, stream_fresh=True), "run")
    jg.simulate_restart()
    decision = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                   stream_fresh=True),
        "card",
    )
    check("a window opened before a restart cannot run after it",
          "restart" in decision.reason.lower(), decision.reason)
    check("... and the store drops it rather than returning it",
          store.get("chat:c1", T5) is None)
    fresh = trusted(actions={"github_comment"})
    expect(jg.consult(fresh, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                      stream_fresh=True), "run")


def t_a_fresh_engine_has_no_window():
    store = jg.GrantStore()
    check("a fresh store is empty", len(store) == 0 and store.keys() == [])
    check("... has no window for a key", store.get("chat:c1", T5) is None)
    decision = expect(
        store.check("chat:c1", "github_comment", {"repo": REPO, "pr": 1295},
                    T5, stream_fresh=True),
        "card",
    )
    check("... and a write asks for its own card",
          "no grant" in decision.reason.lower(), decision.reason)


def t_a_closed_window_cannot_be_reopened():
    store = jg.GrantStore()
    session = store.open_trusted("c1", {"github_comment"}, (target(),), T0)
    expect(jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295},
                      T5, stream_fresh=True), "run")
    check("close_window() closes it once",
          jg.close_window(session, "the owner said 'trusted mode off'",
                          state="revoked") is True)
    check("... and a second close changes nothing and logs nothing new",
          jg.close_window(session, "again") is False
          and len(events("grant_ended")) == 1)
    decision = expect(
        jg.consult(session, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                   stream_fresh=True),
        "card",
    )
    check("the closed object never becomes live again",
          "closed" in decision.reason.lower(), decision.reason)
    check("... its own status says so", jg.status(session, T5)["live"] is False)
    check("... and the store does not return it",
          store.get("chat:c1", T5) is None)
    check("a window cannot be reopened without a new owner approval",
          store.open_trusted("c1", {"github_comment"}, (target(),), T5,
                             owner_approved=False) is None)
    fresh = store.open_trusted("c1", {"github_comment"}, (target(),), T5)
    check("a new approval opens a NEW window, with its own id",
          fresh is not None and fresh.grant_id != session.grant_id)
    expect(jg.consult(fresh, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                      stream_fresh=True), "run")
    check("... and the same chat has one live window, not two",
          store.open_trusted("c1", {"github_comment"}, (target(),), T5) is None)


def t_an_expired_window_does_not_block_a_new_one():
    store = jg.GrantStore()
    first = store.open_trusted("c1", {"github_comment"}, (target(),), T0,
                               seconds=60)
    check("the first window is open", first is not None)
    second = store.open_trusted("c1", {"github_comment"}, (target(),), T61)
    check("after it expires a new approval opens a new window",
          second is not None and second.grant_id != first.grant_id)
    check("... and the expired one is logged exactly once",
          [row["state"] for row in events("grant_ended")] == ["expired"])


# ---------------------------------------------------------------------------
# Target pinning: trusted merges and plan targets
# ---------------------------------------------------------------------------


def t_a_pinned_merge_refuses_a_different_head():
    session = trusted(
        actions={"github_merge_pr"},
        targets=(target(number=1295, head=SHA_A),),
    )
    decision = expect(
        jg.consult(session, "github_merge_pr", merge_args(head=SHA_B), T5,
                   stream_fresh=True),
        "refuse",
    )
    check("a pinned trusted merge refuses a different head",
          "head_sha" in decision.reason, decision.reason)
    expect(jg.consult(session, "github_merge_pr", merge_args(head=SHA_A), T5,
                      stream_fresh=True), "run")
    grant = plan({"github_merge_pr"}, (target(number=1295, head=SHA_A),))
    decision = expect(
        jg.consult(grant, "github_merge_pr", merge_args(head=SHA_B), T5,
                   stream_fresh=True),
        "card",
    )
    check("a plan pinned to a moved head raises a new card instead",
          "pinned" in decision.reason.lower(), decision.reason)


def t_a_trusted_merge_needs_a_pin_and_passing_checks():
    session = trusted(actions={"github_merge_pr"})
    decision = expect(
        jg.consult(session, "github_merge_pr", merge_args(head=None), T5,
                   stream_fresh=True),
        "refuse",
    )
    check("a trusted merge with no head_sha is refused",
          "head_sha" in decision.reason, decision.reason)
    decision = expect(
        jg.consult(session, "github_merge_pr", merge_args(checks=False), T5,
                   stream_fresh=True),
        "refuse",
    )
    check("a trusted merge with passing checks unstated is refused",
          "check" in decision.reason.lower(), decision.reason)
    grant = plan({"github_merge_pr"}, (target(number=1295, head=SHA_A),))
    decision = expect(
        jg.consult(grant, "github_merge_pr", merge_args(checks=False), T5,
                   stream_fresh=True),
        "card",
    )
    check("... and so is a plan merge on a red check",
          "check" in decision.reason.lower(), decision.reason)


# ---------------------------------------------------------------------------
# The plan grant: exact targets, no silent expansion
# ---------------------------------------------------------------------------


def t_a_plan_runs_the_exact_write_it_named():
    grant = plan({"github_merge_pr"}, (target(number=1295, head=SHA_A),))
    expect(jg.consult(grant, "github_merge_pr", merge_args(), T5,
                      stream_fresh=True), "run")
    decision = expect(
        jg.consult(grant, "github_comment", {"repo": REPO, "pr": 1295}, T5,
                   stream_fresh=True),
        "card",
    )
    check("a plan does not cover an action it did not name",
          "github_merge_pr" in decision.reason, decision.reason)
    decision = expect(
        jg.consult(grant, "github_merge_pr", merge_args(number=1296), T5,
                   stream_fresh=True),
        "card",
    )
    check("a plan for #1295 does not cover #1296",
          "#1295" in decision.reason and "#1296" in decision.reason,
          decision.reason)
    decision = expect(
        jg.consult(grant, "github_merge_pr",
                   {"repo": OTHER, "pr": 1295, "head_sha": SHA_A,
                    "checks_passed": True}, T5, stream_fresh=True),
        "card",
    )
    check("a plan does not cover another repository",
          REPO in decision.reason and OTHER in decision.reason, decision.reason)


def t_a_plan_without_a_job_or_with_a_wildcard_is_rejected():
    raises(ValueError, plan, {"*"}, (target(number=1295),))
    raises(ValueError, jg.PlanGrant, "plan", None, {"github_comment"},
           (target(number=1295),), T0, T60)


def t_a_plan_divergence_voids_the_rest_of_the_plan():
    grant = plan({"github_merge_pr"}, (target(number=1295, head=SHA_A),))
    jg.void(grant, jg.Divergence("head_moved", "aaaaaaaa -> bbbbbbbb"))
    decision = expect(
        jg.consult(grant, "github_merge_pr", merge_args(), T5,
                   stream_fresh=True),
        "card",
    )
    check("a voided plan is a new card, not the old yes stretched",
          "closed" in decision.reason.lower(), decision.reason)
    check("... and voiding is idempotent, with one end line",
          jg.void(grant, jg.Divergence("head_moved", "aaaaaaaa -> bbbbbbbb"))
          is grant
          and len(grant.void_if) == 1
          and len(events("grant_ended")) == 1)
    check("... and the end line says 'voided'",
          events("grant_ended")[0]["state"] == "voided")
    raises(TypeError, jg.void, trusted(actions={"github_comment"}), "head_moved")
    raises(ValueError, jg.void, plan({"github_comment"},
                                     (target(number=1295),)), "the moon")


def t_a_plan_expires_on_its_own():
    grant = plan({"github_comment"}, (target(number=1295),), expires_at=T60)
    expect(jg.consult(grant, "github_comment", {"repo": REPO, "pr": 1295},
                      T59, stream_fresh=True), "run")
    decision = expect(
        jg.consult(grant, "github_comment", {"repo": REPO, "pr": 1295}, T60,
                   stream_fresh=True),
        "card",
    )
    check("a plan grant expires at its own boundary",
          "expired" in decision.reason.lower(), decision.reason)


# ---------------------------------------------------------------------------
# The audit: the gate's own three writers, and only when a card was replaced
# ---------------------------------------------------------------------------


def t_the_three_audit_writers_are_the_gates_own():
    base = _base.folder("jarvis_gate.py")
    if base is None:
        skip("jarvis_gate.py is not in this run's backend or the published base")
    else:
        text = (Path(base) / "jarvis_gate.py").read_text(encoding="utf-8")
        for name in ("grant_made", "granted", "grant_ended"):
            check(f"the gate really has its own {name}()",
                  f"def {name}(" in text)
    source = (HERE / "jarvis_grants.py").read_text(encoding="utf-8")
    check("the engine carries no copy of the gate's event strings",
          '"gate.grant_' not in source and "'gate.grant_" not in source)
    store = jg.GrantStore()
    session = store.open_trusted("c1", {"github_comment"}, (target(),), T0)
    check("opening calls the gate's grant_made with the new id",
          events("grant_made")
          and events("grant_made")[0]["grant_id"] == session.grant_id)
    store.check("chat:c1", "github_comment", {"repo": REPO, "pr": 1295}, T5,
                stream_fresh=True)
    check("a covered run calls the gate's granted with action and id",
          events("granted")
          and events("granted")[0]["action"] == "github_comment"
          and events("granted")[0]["grant_id"] == session.grant_id)
    store.revoke("c1")
    check("closing calls the gate's grant_ended with the state",
          events("grant_ended")
          and events("grant_ended")[0]["state"] == "revoked")


def t_open_refuses_when_the_audit_cannot_be_written():
    store = jg.GrantStore()
    saved = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = None       # makes `import jarvis_gate` fail
    try:
        check("a window that cannot be logged is refused, not opened unlogged",
              store.open_trusted("c1", {"github_comment"}, (target(),), T0)
              is None and len(store) == 0)
    finally:
        sys.modules["jarvis_gate"] = saved


def t_granted_is_written_only_when_a_card_would_have_been_raised():
    store = jg.GrantStore()
    store.open_trusted("c1", {"github_comment"}, (target(),), T0)
    decision = store.check("chat:c1", "github_comment",
                           {"repo": REPO, "pr": 1295}, T5,
                           stream_fresh=True, tier="ask")
    check("a tier-ask run writes one granted line",
          decision.outcome == "run" and len(events("granted")) == 1)
    reset_audit()
    store.open_trusted("c2", {"github_comment"}, (target(),), T0)
    decision = store.check("chat:c2", "github_comment",
                           {"repo": REPO, "pr": 1295}, T5,
                           stream_fresh=True, tier="auto")
    check("a tier-auto run writes no granted line - it would have run anyway",
          decision.outcome == "run" and events("granted") == [])
    check("... and it spends no use of the window",
          store.keys() == ["chat:c1", "chat:c2"]
          and "chat:c2" in store.keys())
    session = store.get("chat:c2", T5)
    check("... proven by the use count still being zero",
          session is not None and session.actions_taken == 0)
    decision = store.check("chat:c2", "github_comment",
                           {"repo": REPO, "pr": 1295}, T5,
                           stream_fresh=True, tier="never")
    check("a 'never' is refused and no grant may lift it",
          decision.outcome == "refuse")


# ---------------------------------------------------------------------------
# The record, its status, and the two-file rule
# ---------------------------------------------------------------------------


def t_status_reads_the_record():
    session = trusted(actions={"github_comment"}, cap=5)
    jg.record_action(session, "github_comment")
    row = jg.status(session, T5)
    check("status says the window is live", row["live"] and row["state"] == "open")
    check("... names the record and its kind",
          row["grant_id"] == session.grant_id and row["kind"] == "trusted")
    check("... reports uses and what is left",
          row["actions_taken"] == 1 and row["remaining"]["github_comment"] == 4)
    check("... and its expiry", row["expires_at"].endswith("UTC")
          and row["expires_in_seconds"] == 55 * 60)
    jg.close_window(session, "the hour was up", state="expired")
    row = jg.status(session, T5)
    check("after closing, status says closed and why",
          not row["live"] and row["state"] == "closed"
          and row["reason"] == "the hour was up")


def t_the_two_copies_are_one_file():
    ours = (HERE / "jarvis_grants.py").read_bytes()
    theirs = (ROOT / "jarvis-backend" / "jarvis_grants.py").read_bytes()
    check("backend/jarvis_grants.py and jarvis-backend/jarvis_grants.py are "
          "byte-identical", ours == theirs)


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------

CASES = (
    t_the_allowlist_is_exactly_the_eleven_shapes,
    t_each_of_the_eleven_shapes_is_accepted,
    t_a_file_write_is_not_covered_by_trusted_mode,
    t_the_cap_is_reached_exactly_at_twenty,
    t_a_requested_cap_of_99_is_clamped_to_thirty,
    t_the_cap_is_per_action,
    t_a_bool_or_a_negative_cap_cannot_be_a_cap,
    t_each_banned_verb_is_refused,
    t_a_ban_beats_a_plan_grant,
    t_a_pending_card_is_never_swallowed,
    t_a_stale_stream_voids_the_window,
    t_void_stale_is_the_call_the_watcher_makes,
    t_a_stale_stream_blocks_a_read,
    t_reads_run_without_a_grant,
    t_lockdown_outranks_a_window,
    t_an_unknown_tool_or_an_unreadable_request_is_refused,
    t_a_window_expires_at_exactly_sixty_minutes,
    t_a_restart_wipes_the_window,
    t_a_fresh_engine_has_no_window,
    t_a_closed_window_cannot_be_reopened,
    t_an_expired_window_does_not_block_a_new_one,
    t_a_pinned_merge_refuses_a_different_head,
    t_a_trusted_merge_needs_a_pin_and_passing_checks,
    t_a_plan_runs_the_exact_write_it_named,
    t_a_plan_without_a_job_or_with_a_wildcard_is_rejected,
    t_a_plan_divergence_voids_the_rest_of_the_plan,
    t_a_plan_expires_on_its_own,
    t_the_three_audit_writers_are_the_gates_own,
    t_open_refuses_when_the_audit_cannot_be_written,
    t_granted_is_written_only_when_a_card_would_have_been_raised,
    t_status_reads_the_record,
    t_the_two_copies_are_one_file,
)


def main() -> int:
    print(f"  module {Path(jg.__file__).resolve()}")
    for fn in CASES:
        reset_audit()
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
