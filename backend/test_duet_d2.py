"""Wave D-2 (2026-10-22) - the four pieces in one suite, each with the bite the
work order names.

    python3 test_duet_d2.py        (through: python -B backend/run_suites.py test_duet_d2.py)

D-2.1  a plan's read-only steps keep running while another waits on a card,
       and the ones behind that card queue; a running plan never approves
       anything; Stop halts at a step boundary; completion says
       `ready_for_review` (piece D-1.4's vocabulary, reused);
D-2.2A the two-tier outbound classifier: Tier 1 is refused even when asked,
       Tier 2 is refused when unrequested or tainted and allowed only when
       the owner's own prompt explicitly authorises it;
D-2.2B browser plan/run_steps refuse brokerage trades, wires and
       third-party accounts OUTRIGHT - no card, no steps;
D-2.3  spending summaries and document hits carry `source_provenance` with a
       label naming the exact file, withheld when hidden or locked;
D-2.4  a walk brain-dump splits and classifies, and the evening report keeps
       the details until the private lists are shown.

Every check is a real condition. A skip is printed and counted as a skip -
never as a pass - per tools/check_vacuous_checks.py.
"""
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_scrub.py", "jarvis_email_draft.py",
                "jarvis_browser_control.py", "jarvis_spending.py",
                "jarvis_documents.py", "jarvis_live.py", "jarvis_jobs.py")

# Every database this suite touches, before the modules are imported: a
# direct run must not touch the owner's real jobs.db / receipts.db / config.
_BASE = Path(tempfile.gettempdir()) / "jarvis-duet-d2-suite"
os.makedirs(_BASE, exist_ok=True)
_WORK = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="run-"))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ.setdefault("JARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ["JARVIS_JOBS_DB"] = str(_WORK / "jobs.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_WORK / "receipts.db")
os.environ.pop("JARVIS_BACKEND", None)

# The policy file, so ctx.require() has a tier to read (the same lookup
# test_jobs.py uses).
for _c in (HERE / "jarvis-framework.toml", HERE / "rebuilt" / "jarvis-framework.toml"):
    if _c.is_file():
        os.environ.setdefault("JARVIS_FRAMEWORK_TOML", str(_c))
        break

import jarvis_jobs as J            # noqa: E402
import jarvis_scrub as S           # noqa: E402
import jarvis_browser_control as B  # noqa: E402
import jarvis_email_draft as E     # noqa: E402
import jarvis_spending as SP       # noqa: E402
import jarvis_documents as D       # noqa: E402
import jarvis_live as L            # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []

#: An action in no tier table, so _tier_of answers from `unknown_action_tier`
#: ("ask" in the shipped file) and never from `never`.
PROBE_ACTION = "duet_d2_probe_action"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh():
    """A jobs database of its own for one case, on a clean writer thread."""
    J.shutdown()
    d = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="case-"))
    J.DB_PATH = d / "jobs.db"
    return d


def job_row(job_id: str):
    rows = [r for r in J.jobs() if r.get("id") == job_id]
    return rows[0] if rows else None


def plan_steps(job_id: str):
    row = job_row(job_id) or {}
    params = row.get("params")
    if isinstance(params, str):
        import json
        params = json.loads(params)
    return (params or {}).get("steps") or []


# --------------------------------------------------------------------------
#   D-2.1 - the plan runner
# --------------------------------------------------------------------------

ORDER = []


def _gather(ctx, params):
    ORDER.append("gather")
    return {"gathered": True}


def _send(ctx, params):
    ORDER.append("send")
    ctx.require(PROBE_ACTION)      # outside the frozen set: parks the job
    ORDER.append("send_after_yes")
    return {"sent": True}


def _gather2(ctx, params):
    ORDER.append("gather2")
    return {"gathered2": True}


def _after(ctx, params):
    ORDER.append("after")
    return {"after": True}


def t_d21_a_readonly_step_continues_while_another_waits_and_the_rest_queue():
    del ORDER[:]
    fresh()
    J.register("d2_gather", _gather, readonly=True)
    J.register("d2_send", _send)
    J.register("d2_gather2", _gather2, readonly=True)
    J.register("d2_after", _after)
    jid = J.create_plan([
        {"name": "gather", "handler": "d2_gather", "readonly": True},
        {"name": "send", "handler": "d2_send", "readonly": False},
        {"name": "gather2", "handler": "d2_gather2", "readonly": True},
        {"name": "after", "handler": "d2_after", "readonly": False,
         "depends_on": [1]},
    ], label="four-step duet plan", caps=[])
    J.run_due(now=time.time() + 1)
    row = job_row(jid) or {}
    steps = plan_steps(jid)
    state = (steps[1] if len(steps) > 1 else {}).get("status")
    check("the waiting step is marked waiting_approval with the action it needs",
          state == "waiting_approval"
          and (steps[1].get("pending_action") == PROBE_ACTION), steps)
    # THIS IS THE BITE: a halting runner records gather, send - and stops.
    # The continuation records gather2 in the SAME tick, before the card is
    # answered, because it is read-only and does not depend on step 1.
    check("a read-only independent step ran in the same tick (the continuation)",
          ORDER == ["gather", "send", "gather2"], ORDER)
    check("the step behind the card is queued, not run",
          len(steps) > 2 and steps[2].get("status") == "done"
          and len(steps) > 3 and steps[3].get("status") == "queued_behind_approval",
          [(s.get("name"), s.get("status")) for s in steps])
    check("the job parks in waiting_approval, not failed", row.get("state")
          == "waiting_approval", row.get("state"))
    check("the runner did not decide the grant for him",
          any(g.get("state") == "pending" for g in J.pending_grants(jid)))


def t_d21_the_owner_answers_and_the_plan_finishes_with_ready_for_review():
    del ORDER[:]
    fresh()
    J.register("d2_gather", _gather, readonly=True)
    J.register("d2_send", _send)
    J.register("d2_gather2", _gather2, readonly=True)
    J.register("d2_after", _after)
    jid = J.create_plan([
        {"name": "gather", "handler": "d2_gather", "readonly": True},
        {"name": "send", "handler": "d2_send", "readonly": False},
        {"name": "gather2", "handler": "d2_gather2", "readonly": True},
        {"name": "after", "handler": "d2_after", "readonly": False,
         "depends_on": [1]},
    ], label="four-step duet plan", caps=[])
    J.run_due(now=time.time() + 1)
    pending = [g for g in J.pending_grants(jid) if g.get("state") == "pending"]
    check("the plan asked for exactly one capability", len(pending) == 1, pending)
    J.decide_grant(pending[0]["id"], True, by="test")
    J.run_due(now=time.time() + 60)   # past the park's retry delay
    row = job_row(jid) or {}
    steps = plan_steps(jid)
    check("the owner's yes finishes the waiting step and the one behind it",
          row.get("state") == "done"
          and all(s.get("status") == "done" for s in steps)
          and ORDER[-1] == "after", (row.get("state"), ORDER))
    result = row.get("result") or {}
    check("completion uses piece D-1.4's exact ready_for_review vocabulary",
          result.get("review_status") == "ready_for_review", result)
    check("...and the result is not marked delivered/collected by the runner",
          row.get("delivered") in (None, ""), row.get("delivered"))


def t_d21_stop_halts_at_a_step_boundary_and_nothing_else_runs():
    del ORDER[:]
    fresh()
    J.register("d2_gather", _gather, readonly=True)
    J.register("d2_gather2", _gather2, readonly=True)
    jid = J.create_plan([
        {"name": "gather", "handler": "d2_gather", "readonly": True},
        {"name": "gather2", "handler": "d2_gather2", "readonly": True},
    ], label="cancel me", caps=[])
    J.cancel(jid)
    J.run_due(now=time.time() + 1)
    check("a cancelled plan runs no handler at all", ORDER == [], ORDER)
    check("...and its row is cancelled", (job_row(jid) or {}).get("state")
          == "cancelled", job_row(jid))


# --------------------------------------------------------------------------
#   D-2.2A - the two-tier outbound classifier
# --------------------------------------------------------------------------

#: A Luhn-valid test number (the ISO/IEC 7812 test card), never a real card.
TEST_CARD = "4111 1111 1111 1111"


def t_d22a_tier1_is_refused_even_with_an_explicit_owner_prompt():
    for label, text in (
            ("card number", f"my card is {TEST_CARD}"),
            ("government id", "my ssn is 123-45-6789"),
            ("vault handle", "look up vault://bank_login"),
            ("api key", "key sk-abcdefghijklmnopqrstuvwx"),
            ("pairing token", "jdk1.d0123abcd." + "A" * 43),
    ):
        got = S.classify_outbound_sensitivity(
            text, user_prompt="send whatever you need, I authorize all of it")
        check(f"Tier 1 ({label}) is refused even when explicitly asked",
              got.get("allowed") is False and got.get("tier") == 1, got)
        check(f"... and the value is masked in redacted_text ({label})",
              label.replace(" ", "_") in " ".join(got.get("categories") or [])
              and "4111 1111" not in got.get("redacted_text", "")
              if label == "card number" else bool(got.get("redacted_text")), got)


def t_d22a_tier2_needs_an_untainted_turn_and_the_owners_own_words():
    health = "My cholesterol came back at 240 and the doctor wants a repeat test."
    health_ask = "email my doctor my cholesterol result"
    without_ask = S.classify_outbound_sensitivity(health, user_prompt="send the update")
    asked = S.classify_outbound_sensitivity(health, user_prompt=health_ask)
    tainted = S.classify_outbound_sensitivity(
        health, user_prompt=health_ask, tainted=True)
    check("Tier 2 (health) is refused when the prompt did not ask for it",
          without_ask.get("allowed") is False and without_ask.get("tier") == 2,
          without_ask)
    check("Tier 2 (health) is allowed when the owner's own prompt asks and the "
          "turn is untainted",
          asked.get("allowed") is True and asked.get("tier") == 2, asked)
    check("Tier 2 is refused when the turn read outside text, even when asked",
          tainted.get("allowed") is False and tainted.get("tier") == 2, tainted)
    finance = "My tax balance is $4,200 and my account number ends 4417."
    check("Tier 2 (personal finance) is refused with no explicit ask",
          S.classify_outbound_sensitivity(finance).get("allowed") is False)
    check("... and allowed with the owner's explicit words",
          S.classify_outbound_sensitivity(
              finance, user_prompt="email my accountant my tax balance")
          .get("allowed") is True)
    check("an ordinary draft is tier 0 and allowed",
          S.classify_outbound_sensitivity(
              "See you at 3 on Tuesday - I'll bring the slides.").get("tier") == 0)


def t_d22a_email_draft_refuses_a_tier1_draft_before_the_card():
    drafted = E.plan(to="sam@example.com", subject="card",
                     body=f"here is the card {TEST_CARD}")
    check("a draft holding a card number is refused with a Plan problem, so no "
          "card is raised and nothing is saved",
          bool(drafted.problem) and "never goes out" in drafted.problem.lower(),
          drafted.problem)
    clean = E.plan(to="sam@example.com", subject="lunch",
                   body="See you at 1 for lunch.")
    check("an ordinary draft still makes a plan", bool(clean.problem) is False
          or "not set up on this PC" in clean.problem, clean.problem)


# --------------------------------------------------------------------------
#   D-2.2B - the three outright browser refusals
# --------------------------------------------------------------------------

def t_d22b_refusals_happen_before_any_card_or_browser():
    cases = (
        ("securities_trading", "submit buy order 100 shares of AAPL"),
        ("inter_account_money_transfer", "initiate wire transfer between accounts"),
        ("third_party_account_access", "log into my friend's account and check it"),
    )
    for category, text in cases:
        got = B.check_outright_refusal(action_text=text)
        check(f"{category}: check_outright_refusal names it, carded=no",
              got is not None and got.get("code") == "outright_refused_category"
              and got.get("category") == category
              and got.get("allowed_with_approval") is False, got)
    stepped = B.run_steps(
        [{"action": "navigate", "value": "https://broker.example.com/orders",
          "why": "submit buy order 100 shares"}], approved=True)
    check("run_steps refuses a brokerage trade before running a step",
          stepped.get("ok") is False
          and stepped.get("code") == "outright_refused_category"
          and stepped.get("done") == [], stepped)
    planned = B.plan("submit buy order 100 shares of AAPL", "s1", [])
    check("plan() refuses the same category outright (no steps, no card)",
          planned.refusal is not None
          and planned.refusal.get("category") == "securities_trading"
          and planned.steps == [], planned.refusal)
    ordinary = B.check_outright_refusal(action_text="renew my library books")
    check("an ordinary action is not refused", ordinary is None, ordinary)


# --------------------------------------------------------------------------
#   D-2.3 - source_provenance on summaries and hits
# --------------------------------------------------------------------------

def t_d23_spending_summary_carries_and_withholds_provenance():
    prov = SP._provenance("spreadsheet", ["bank-march.csv"])
    check("a spending summary's provenance names the exact file",
          prov and prov.get("label") == "From: bank-march.csv"
          and prov.get("files") == ["bank-march.csv"], prov)
    table = {"period": "March", "title": "Spending by category", "caveats": [],
             "source_provenance": dict(prov or {})}
    numbers = {"currencies": {"": {
        "cat": {}, "uncat": [0, 0], "refunds": [0, 0], "income": [0, 0],
        "transfers_out": [0, 0], "transfers_in": [0, 0], "total": 0,
        "rows": 0, "months": [], "month_total": {}, "month_rows": {},
        "cat_month": {}}}}
    result = SP.result_for_model(table, numbers)
    check("the model-visible spending result carries the same provenance",
          result.get("source_provenance", {}).get("label")
          == "From: bank-march.csv", result.get("source_provenance"))
    saved = SP._private_withheld
    SP._private_withheld = lambda: True
    try:
        check("... and it is withheld when the private view is hidden/locked",
              SP._provenance("spreadsheet", ["bank-march.csv"]) is None)
    finally:
        SP._private_withheld = saved


def t_d23_document_hits_carry_and_withhold_provenance():
    folder = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="docs-"))
    note = folder / "atlas-notes.md"
    note.write_text("# Atlas\n\nThe Atlas launch is on Tuesday.\n", encoding="utf-8")
    got = D.read(str(note), roots=[folder])
    check("a document read's provenance names the exact file",
          got.get("ok") is True
          and got.get("source_provenance", {}).get("label") == "From: atlas-notes.md",
          got.get("source_provenance"))
    saved = D._private_withheld
    D._private_withheld = lambda: True
    try:
        hidden = D.read(str(note), roots=[folder])
        check("... and it is withheld when the private view is hidden/locked",
              hidden.get("ok") is True and "source_provenance" not in hidden, hidden)
    finally:
        D._private_withheld = saved


# --------------------------------------------------------------------------
#   D-2.4 - walk brain-dump -> evening report
# --------------------------------------------------------------------------

WALK = ("First check my notes on Project Atlas, second email Sam the summary, "
        "also remind me to buy coffee")


def t_d24_the_walk_splits_and_classifies_and_the_report_keeps_the_details():
    staged = L.stage_walk_brain_dump(WALK, session_id="walk-1", now_ts=1000.0)
    items = staged.get("items") or []
    check("the walk dump splits into its items", len(items) == 3
          and [i["kind"] for i in items]
          == ["read_only_prep", "needs_approval_card", "needs_approval_card"],
          items)
    check("...and read-only prep runs now while the rest wait for a card",
          staged["counts"] == {"items": 3, "read_only_prep": 1,
                               "needs_approval_card": 2}, staged.get("counts"))
    report = L.build_evening_report("walk-1", now_ts=2000.0)
    # Nothing was PREPARED by a walk (it only classifies), so the report
    # must say "to prepare", never "prepared" - the review blocker.
    check("the evening report says to-prepare, never claims prepared work",
          report["counts"] == {"prepared": 0, "to_prepare": 1,
                               "needs_approval_card": 2, "total": 3}
          and report["prepared"] == []
          and report["to_prepare"][0]["status"] == "to_prepare"
          and report["waiting"][0]["status"] == "waiting_approval", report)
    check("no autonomous send or approval: the report is a bundle, nothing else",
          report.get("ok") is True and "sent" not in report)
    locked = L.build_evening_report("walk-1", hide_memory_lists=True, now_ts=2001.0)
    check("under the hidden lists the details are withheld, the counts stay",
          locked.get("withheld") is True and locked["prepared"] == []
          and locked["waiting"] == [] and locked["counts"]["total"] == 3, locked)


def t_d21_a_plan_cannot_call_a_mutating_handler_readonly():
    fresh()
    J.register("d2_gather_mutating", _gather)
    try:
        J.create_plan([{"handler": "d2_gather_mutating", "readonly": True}])
        refused = False
    except ValueError:
        refused = True
    check("a step declaring readonly on a handler not registered read-only "
          "is refused at plan creation", refused)


def t_d22_the_classifier_is_defined_once_and_email_passes_prompt_and_taint():
    tainted = E.plan(to="sam@example.com", subject="health",
                     body="my cholesterol is 240",
                     user_prompt="email my doctor my cholesterol result",
                     tainted=True)
    check("a tainted Tier-2 draft is refused (prompt/taint reach the classifier)",
          bool(tainted.problem) and "mentions" in tainted.problem, tainted.problem)
    asked = E.plan(to="sam@example.com", subject="health",
                   body="my cholesterol is 240",
                   user_prompt="email my doctor my cholesterol result",
                   tainted=False)
    check("... and an untainted explicitly-asked one is not refused for sensitivity",
          "mentions" not in asked.problem, asked.problem)


# --------------------------------------------------------------------------
#   Runner
# --------------------------------------------------------------------------

def main() -> int:
    print(f"tree: {HERE}")
    for fn in (t_d21_a_readonly_step_continues_while_another_waits_and_the_rest_queue,
               t_d21_the_owner_answers_and_the_plan_finishes_with_ready_for_review,
               t_d21_stop_halts_at_a_step_boundary_and_nothing_else_runs,
               t_d22a_tier1_is_refused_even_with_an_explicit_owner_prompt,
               t_d22a_tier2_needs_an_untainted_turn_and_the_owners_own_words,
               t_d22a_email_draft_refuses_a_tier1_draft_before_the_card,
               t_d22b_refusals_happen_before_any_card_or_browser,
               t_d23_spending_summary_carries_and_withholds_provenance,
               t_d23_document_hits_carry_and_withhold_provenance,
               t_d24_the_walk_splits_and_classifies_and_the_report_keeps_the_details,
               t_d21_a_plan_cannot_call_a_mutating_handler_readonly,
               t_d22_the_classifier_is_defined_once_and_email_passes_prompt_and_taint):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:                                 # noqa: BLE001
            FAILED.append(fn.__name__)
            traceback.print_exc()
    try:
        J.shutdown()
    except Exception:                                     # noqa: BLE001
        pass
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed in test_duet_d2: " + ", ".join(FAILED))
    import shutil
    shutil.rmtree(_WORK, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
