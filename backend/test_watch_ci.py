"""test_watch_ci.py - the GitHub CI watcher: observe mode, one batch per PR, two stages.

    py -3 -B backend/test_watch_ci.py

No pytest, no network, no `gh`, no model, no real backend. A fake clock (every
call takes `now`), a fake `gh` runner (a plain list of arguments in, a string
out), temp files for the decisions log and the receipts.

WHY THIS SUITE EXISTS. Three patterns from `dsh-superagent` were adopted on
2026-11-04 (the owner-forwarded spec, Part II sections 2.2-2.4) because a
watcher that speaks on every check is a watcher the owner mutes:

  1. **`observe` mode.** A new proactive rule runs the whole pipeline and writes
     a decision row instead of interrupting. `GET /api/watch/decisions?limit=50`
     is how the owner reads it and decides whether to promote the rule. The
     single most important check here is therefore the boring one: in observe
     mode the notifier is called ZERO times.
  2. **Per-thread batching and dedupe.** Seven required checks finish minutes
     apart; one pull request at one commit is ONE thread
     (`pr:<number>:<head_sha[:9]>`), and it speaks at most once - fail fast, or
     settle green, or stay quiet. `audit` and `python-advisories` are
     informational and must NEVER be the reason for a notification.
  3. **The two-stage gate.** `gate()` is pure code; only a terminal failure of a
     required check may reach the stage that fetches a log. The check that
     matters is "an informational event calls assess ZERO times", and the
     structural version of it: `jarvis_watch_policy.py` imports nothing at all.

WHAT THIS SUITE DELIBERATELY DOES NOT DO: it never runs `gh`, never opens a
socket, never calls a model, and never starts a thread of its own. Every one of
those is injected, which is also how the crash-recovery check reproduces "the
process died between the write and the send" without dying.
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_watch.py", "jarvis_watch_ci.py",
                "jarvis_watch_policy.py", "jarvis_outbox.py")

# A scratch base made with makedirs, then mkdtemp(dir=...): plain mkdtemp's
# 0o700 mode raises PermissionError in this environment (the note in
# test_jobs.py, which this suite follows for the same reason).
_BASE = Path(tempfile.gettempdir()) / "jarvis-watch-ci-suite"
os.makedirs(_BASE, exist_ok=True)
_WORK = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="run-"))

# Every store is moved BEFORE the modules are imported: a direct run on the
# owner's PC must not touch his real watch.db, decisions, receipts or outbox.
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ.setdefault("JARVIS_CONFIG_DIR", str(_WORK / "cfg"))
os.environ["JARVIS_WATCH_DB"] = str(_WORK / "watch.db")
os.environ["JARVIS_WATCH_CI_DIR"] = str(_WORK / "watch-ci")
os.environ["JARVIS_OUTBOX_PATH"] = str(_WORK / "watch-ci" / "outbox.json")

import jarvis_outbox as OUT      # noqa: E402
import jarvis_watch as W         # noqa: E402
import jarvis_watch_ci as C      # noqa: E402
import jarvis_watch_policy as P  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check that could not run here. Counted as skipped, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh():
    """A decisions log and a receipts file of its own, and a clean outbox."""
    d = Path(tempfile.mkdtemp(dir=str(_BASE), prefix="case-"))
    OUT._reset_for_tests()
    OUT.bind(d / "outbox.json")
    return C.Store(d / "watch-decisions.json", d / "watch-receipts.json")


def now():
    return 1_700_000_000.0


# --- the two things a check needs to build a rollup ----------------------

def rollup(**over):
    """`{name: (conclusion, status)}` for the seven required jobs, SUCCESS by
    default. `audit` is added RED by `with_informational()` below, because its
    being red while a pull request merges is the measured fact this file is
    built on."""
    base = {n: ("SUCCESS", "COMPLETED") for n in P.REQUIRED_CI_JOBS}
    base.update(over)
    return [{"name": k, "status": v[1], "conclusion": v[0]} for k, v in base.items()]


def with_informational(rows, **red):
    rows = list(rows)
    for name in P.INFORMATIONAL_CI_JOBS:
        rows.append({"name": name, "status": "COMPLETED",
                     "conclusion": red.get(name, "FAILURE")})
    return rows


def trigger(pr=1135, sha="a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
            mergeable="MERGEABLE", checks=None, **over):
    t = {"source": "github_pr_ci", "pr": pr, "head_sha": sha,
         "mergeable": mergeable, "checks": checks if checks is not None else rollup()}
    t.update(over)
    return t


# ==========================================================================
#   1. The vocabularies: three modes, a CLOSED reason set, and fail-closed
# ==========================================================================

def t_the_three_modes_and_the_closed_reason_set():
    check("WATCH_MODES is exactly off / observe / active",
          tuple(W.WATCH_MODES) == ("off", "observe", "active"), W.WATCH_MODES)
    check("WATCH_REASONS is a dict of closed codes",
          isinstance(W.WATCH_REASONS, dict) and len(W.WATCH_REASONS) >= 5, W.WATCH_REASONS)
    check("the spec's five reason codes are all there",
          {"ci_all_required_green", "ci_required_failed",
           "ci_still_running_debounced", "duplicate_sha_state",
           "observe_shadow_logged"} <= set(W.WATCH_REASONS))
    check("every reason code has a plain sentence, not a bare code",
          all(isinstance(v, str) and len(v) > 10 for v in W.WATCH_REASONS.values()))
    check("the seven required jobs are the ruleset's own list",
          tuple(P.REQUIRED_CI_JOBS) == ("rust", "frontend", "backend",
                                        "backend-windows", "credential-manager",
                                        "powershell-5", "phone-unit-tests"),
          P.REQUIRED_CI_JOBS)
    check("audit and python-advisories are the informational two",
          tuple(P.INFORMATIONAL_CI_JOBS) == ("audit", "python-advisories"))


def t_a_bad_mode_fails_to_observe_never_to_active():
    check("absent config -> observe", W.pr_checks_mode() == "observe", W.pr_checks_mode())
    real = W._cfg
    try:
        for bad in ("yes", "ON", "loud", "", None, 3):
            W._cfg = lambda k, d, bad=bad: bad
            check(f"[watch] pr_checks_mode={bad!r} -> observe",
                  W.pr_checks_mode() == "observe", W.pr_checks_mode())
        for good in ("off", "observe", "active"):
            W._cfg = lambda k, d, good=good: good
            check(f"[watch] pr_checks_mode={good!r} is honoured",
                  W.pr_checks_mode() == good, W.pr_checks_mode())
        W._cfg = lambda k, d: "ACTIVE"
        check("an upper-case value still reads as active", W.pr_checks_mode() == "active")
    finally:
        W._cfg = real
    check("mode_from() is the same fail-closed rule",
          C.mode_from("nonsense") == "observe" and C.mode_from(None) == "observe"
          and C.mode_from("active") == "active")


# ==========================================================================
#   2. Stage one is PURE: no disk, no network, no model - by import
# ==========================================================================

def t_the_gate_has_no_way_to_spend_anything():
    src = (HERE / "jarvis_watch_policy.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    check("the policy module imports nothing from Jarvis",
          not any(n.startswith("jarvis_") for n in names), sorted(names))
    for bad in ("urllib", "socket", "subprocess", "sqlite3", "http", "requests",
                "pathlib", "os", "shutil"):
        check(f"the policy module cannot reach {bad}",
              bad not in names, sorted(names))
    check("so gate() cannot spend GPU: no model module is even named",
          "jarvis_router" not in names and "jarvis_turn" not in names)


# ==========================================================================
#   3. Pattern 1: observe never speaks; active speaks once
# ==========================================================================

def t_observe_runs_the_pipeline_and_never_interrupts():
    st = fresh()
    sent = []
    row = C.evaluate(trigger(), mode="observe", now=now(), store=st,
                     notify=lambda d: sent.append(d) or "speak",
                     assess=lambda d, t: "")
    check("observe records a would_notify row", row["outcome"] == "would_notify", row)
    check("... and the notifier was NEVER called", sent == [], sent)
    check("... the reason names the verdict", row["reason_code"] == "ci_all_required_green", row)
    check("... and the row says it exists because of observe mode",
          row["shadow_reason_code"] == "observe_shadow_logged", row)
    check("... preview_text is the exact one line that would have been shown",
          isinstance(row["preview_text"], str) and "\n" not in row["preview_text"]
          and row["preview_text"].startswith("PR #1135 is green:"), row["preview_text"])
    check("the row carries every field the spec names",
          {"at", "source", "thread_key", "outcome", "reason_code",
           "preview_text"} <= set(row), sorted(row))
    check("the thread key is pr:<number>:<sha[:9]>",
          row["thread_key"] == "pr:1135:a1b2c3d4e", row["thread_key"])
    check("the row is in the ring buffer", len(C.decisions(10, store=st)) == 1)


def t_active_speaks_once_and_the_receipt_silences_the_rest():
    st = fresh()
    sent = []
    notify = lambda d: sent.append(d.get("preview_text")) or "notify"
    first = C.evaluate(trigger(), mode="active", now=now(), store=st, notify=notify)
    check("active raises exactly one notification", len(sent) == 1, sent)
    check("the row says it was notified", first["outcome"] == "notified", first)
    check("... and delivered", first["delivery"] == "sent", first)
    check("... with no shadow reason", not first["shadow_reason_code"], first)
    for i in range(5):
        row = C.evaluate(trigger(), mode="active", now=now() + i + 1, store=st, notify=notify)
        check(f"poll {i + 2} of the same commit is silent (duplicate_sha_state)",
              row["outcome"] == "ignored" and row["reason_code"] == "duplicate_sha_state", row)
    check("... and NOTHING was delivered a second time", len(sent) == 1, sent)
    check("the duplicate preview says so in plain words",
          "already reported" in row["preview_text"], row["preview_text"])


def t_observe_then_promoted_does_not_re_report_a_finished_commit():
    st = fresh()
    C.evaluate(trigger(), mode="observe", now=now(), store=st)
    sent = []
    row = C.evaluate(trigger(), mode="active", now=now() + 60, store=st,
                     notify=lambda d: sent.append(d) or "notify")
    check("a commit observe already logged is not re-announced after promotion",
          row["outcome"] == "ignored" and sent == [], (row["outcome"], sent))


def t_observe_and_active_write_the_same_kind_of_row():
    a, b = fresh(), fresh()
    C.evaluate(trigger(), mode="observe", now=now(), store=a)
    C.evaluate(trigger(), mode="active", now=now(), store=b,
               notify=lambda d: "notify")
    ra = C.decisions(1, store=a)[0]
    rb = C.decisions(1, store=b)[0]
    check("both modes produce one row with the same reason and preview",
          ra["reason_code"] == rb["reason_code"]
          and ra["preview_text"] == rb["preview_text"]
          and ra["thread_key"] == rb["thread_key"], (ra, rb))
    check("only the outcome and delivery differ",
          ra["outcome"] == "would_notify" and rb["outcome"] == "notified"
          and ra["delivery"] == "shadow" and rb["delivery"] == "sent",
          (ra.get("delivery"), rb.get("delivery")))


# ==========================================================================
#   4. Pattern 2: one batch per PR - quiet, fail fast, settle green
# ==========================================================================

def t_still_running_stays_quiet():
    st = fresh()
    sent = []
    quiet = trigger(checks=rollup(rust=("", "IN_PROGRESS"), frontend=("", "IN_PROGRESS"),
                                  backend=("", "QUEUED")))
    for i in range(4):
        row = C.evaluate(quiet, mode="active", now=now() + i, store=st,
                         notify=lambda d: sent.append(d) or "notify")
        check(f"poll {i + 1}: 4 of 7 finished and none failed -> silent",
              row["outcome"] == "ignored"
              and row["reason_code"] == "ci_still_running_debounced", row)
    check("... not one notification across four polls", sent == [], sent)
    check("the quiet row still says how far it got, for the log",
          "4 of 7 required checks finished" in C.decisions(1, store=st)[0]["preview_text"],
          C.decisions(1, store=st)[0]["preview_text"])


def t_fail_fast_speaks_before_the_slow_check_finishes():
    st = fresh()
    sent = []
    # The measured shape: `rust` fails in minutes while `backend` is still in
    # its fifty-fifth. Waiting for the batch to settle would be the whole bug.
    rows = rollup(rust=("FAILURE", "COMPLETED"), backend=("", "IN_PROGRESS"),
                  **{"backend-windows": ("", "IN_PROGRESS")})
    row = C.evaluate(trigger(checks=rows), mode="active", now=now(), store=st,
                     notify=lambda d: sent.append(d) or "high")
    check("a required FAILURE notifies at once, with two checks still running",
          row["outcome"] == "notified" and row["reason_code"] == "ci_required_failed", row)
    check("... exactly one notification", len(sent) == 1, sent)
    check("... the preview names the failed job",
          "'rust'" in row["preview_text"], row["preview_text"])
    for i in range(3):
        again = C.evaluate(trigger(checks=rows), mode="active", now=now() + i + 1,
                           store=st, notify=lambda d: sent.append(d) or "high")
        check(f"re-poll {i + 1} of the same failure is silent",
              again["reason_code"] == "duplicate_sha_state", again)
    check("... still exactly one notification", len(sent) == 1, sent)


def t_all_green_settles_once():
    st = fresh()
    sent = []
    row = C.evaluate(trigger(checks=with_informational(rollup())), mode="active",
                     now=now(), store=st, notify=lambda d: sent.append(d) or "notify")
    check("all seven SUCCESS and MERGEABLE -> one all-green notification",
          row["outcome"] == "notified"
          and row["reason_code"] == "ci_all_required_green", row)
    check("... one, and only one", len(sent) == 1, sent)
    check("... and it says all seven passed",
          "all 7 required checks passed" in row["preview_text"], row["preview_text"])


def t_the_informational_two_can_never_cause_a_notification():
    st = fresh()
    sent = []
    assess_calls = []
    rows = with_informational(rollup())      # audit + python-advisories RED
    row = C.evaluate(trigger(checks=rows), mode="active", now=now(), store=st,
                     notify=lambda d: sent.append(d) or "notify",
                     assess=lambda d, t: assess_calls.append(d) or "")
    check("all 7 required green with audit RED is all-green, not an alarm",
          row["reason_code"] == "ci_all_required_green" and len(sent) == 1, row)
    check("... and the failed audit was never passed to assess()",
          assess_calls == [], assess_calls)
    # Only the informational two are broken; the seven are not even reported.
    only_inf = with_informational([])
    row = C.evaluate(trigger(pr=99, sha="ffffffffffff", checks=only_inf),
                     mode="active", now=now() + 1, store=st,
                     notify=lambda d: sent.append(d) or "notify")
    check("a rollup with only informational checks is not a judged thread",
          row["outcome"] == "ignored"
          and row["reason_code"] == "ci_no_required_checks", row)
    check("... and it notified nobody", len(sent) == 1, sent)
    # The seven all green but the two informational ones red - still one line.
    check("no row anywhere has an informational job in its reason",
          all("audit" not in str(d.get("preview_text", ""))
              or d["reason_code"] == "ci_all_required_green"
              for d in C.decisions(50, store=st)))


def t_green_but_not_mergeable_is_its_own_sentence():
    st = fresh()
    sent = []
    row = C.evaluate(trigger(mergeable="CONFLICTING"), mode="active", now=now(),
                     store=st, notify=lambda d: sent.append(d) or "notify")
    check("all 7 green + CONFLICTING is NOT 'ready'",
          row["reason_code"] == "ci_green_not_mergeable"
          and row["verdict"] == "green_not_mergeable:CONFLICTING", row)
    check("... it says green is not mergeable, and notifies once", len(sent) == 1
          and "not the same as mergeable" in row["preview_text"], row["preview_text"])


def t_a_new_push_is_a_new_thread():
    st = fresh()
    sent = []
    a = C.evaluate(trigger(sha="aaaaaaaaa1111"), mode="active", now=now(),
                   store=st, notify=lambda d: sent.append(d) or "notify")
    b = C.evaluate(trigger(sha="bbbbbbbbb2222"), mode="active", now=now() + 1,
                   store=st, notify=lambda d: sent.append(d) or "notify")
    check("the first commit notifies", a["outcome"] == "notified", a)
    check("a new head sha is a NEW thread and notifies too",
          b["outcome"] == "notified" and a["thread_key"] != b["thread_key"], (a, b))
    check("... two notifications for two commits, not one suppressed", len(sent) == 2)


def t_a_fixed_failure_then_green_owes_both_sentences():
    st = fresh()
    sent = []
    sha = "ccccccccc3333"
    failed = rollup(rust=("FAILURE", "COMPLETED"))
    row = C.evaluate(trigger(sha=sha, checks=failed), mode="active", now=now(),
                     store=st, notify=lambda d: sent.append(d) or "notify")
    check("the failure is reported", row["reason_code"] == "ci_required_failed", row)
    row = C.evaluate(trigger(sha=sha, checks=rollup()), mode="active", now=now() + 600,
                     store=st, notify=lambda d: sent.append(d) or "notify")
    check("the SAME commit, re-run green, is a second verdict and is reported",
          row["outcome"] == "notified" and row["reason_code"] == "ci_all_required_green", row)
    check("... because the receipt key includes the verdict", len(sent) == 2, sent)


# ==========================================================================
#   5. Pattern 3: only a failed required check may reach assess()
# ==========================================================================

def t_gate_never_calls_assess_for_a_filtered_event():
    st = fresh()
    calls = []
    recorder = lambda d, th: calls.append(d.get("reason_code")) or ""

    cases = [
        ("a bot notification", {"source": "github_notifications", "id": "1",
                                "actor": "dependabot[bot]", "title": "x"}),
        ("a still-running batch", trigger(checks=rollup(rust=("", "IN_PROGRESS")))),
        ("an all-green settle", trigger(checks=rollup())),
        ("a green-but-conflicted PR", trigger(mergeable="CONFLICTING")),
        ("a trigger with no required checks", trigger(checks=with_informational([]))),
        ("an unreadable trigger", {"source": "github_pr_ci", "pr": 0, "head_sha": ""}),
        ("a source this watcher does not read", {"source": "email", "id": "9"}),
        ("a clean repo check", {"source": "repo_check", "name": "checkers",
                                "failed": 0, "total": 20}),
    ]
    for label, trig in cases:
        C.evaluate(trig, mode="active", now=now(), store=st,
                   notify=lambda d: "notify", assess=recorder)
        check(f"assess() was never called for {label}", calls == [], (label, calls))

    C.evaluate(trigger(checks=rollup(rust=("FAILURE", "COMPLETED"))), mode="active",
               now=now() + 1, store=st, notify=lambda d: "notify", assess=recorder)
    check("assess() IS called for a failed required check - exactly once",
          calls == ["ci_required_failed"], calls)


def t_assess_reads_the_failing_run_through_gh_and_never_a_model():
    st = fresh()
    calls = []

    def runner(args):
        calls.append(list(args))
        if args[:2] == ["run", "view"]:
            return "\n".join(["2026-11-04T10:00:00Z some setup line",
                              "##[error]error[E0308]: mismatched types",
                              "2026-11-04T10:00:01Z done"])
        raise AssertionError(f"unexpected gh call: {args}")

    rows = rollup(rust=("FAILURE", "COMPLETED"))
    for row in rows:
        if row["name"] == "rust":
            row["detailsUrl"] = "https://github.com/o/r/actions/runs/4242/job/9"
    trig = trigger(checks=rows)
    line = C.assess_failure({"reason_code": "ci_required_failed", "verdict": "failed:rust"},
                            trig, runner=runner)
    check("assess found the run id in the check's own details URL",
          calls and calls[0][:3] == ["run", "view", "4242"], calls)
    check("... and returns ONE line naming the job and the real error",
          "\n" not in line and "rust" in line and "mismatched types" in line, line)
    check("... with no model anywhere in it (the summarizer defaults to None)",
          C.assess_failure({"verdict": "failed:rust"}, trig, runner=lambda a: "") == "")
    # A rollup with no URL cannot reach a log, and says nothing rather than
    # guessing at a run id.
    bare = trigger(checks=rollup(rust=("FAILURE", "COMPLETED")))
    check("no details URL -> no fetch, an empty summary",
          C.assess_failure({"verdict": "failed:rust"}, bare, runner=runner) == "")


# ==========================================================================
#   6. Crash recovery: written before sent, delivered exactly once after
# ==========================================================================

def t_a_crash_between_write_and_send_is_delivered_once_by_the_next_poll():
    st = fresh()
    boom = lambda d: (_ for _ in ()).throw(RuntimeError("the event bus died"))
    row = C.evaluate(trigger(), mode="active", now=now(), store=st, notify=boom)
    check("a sender that raises does not lose the row",
          row["outcome"] == "would_notify" and row["delivery"] == "failed", row)
    pending = OUT.pending("pr_ci_notice")
    check("the notice is PENDING in the outbox, so it is still owed",
          len(pending) == 1 and pending[0]["key"].startswith("pr:1135:"), pending)
    check("the receipt was written BEFORE the failed send, so a crash cannot "
          "re-derive the verdict", st.receipt(row["receipt_key"]) is not None,
          row.get("receipt_key"))
    sent = []
    row = C.evaluate(trigger(), mode="active", now=now() + 60, store=st,
                     notify=lambda d: sent.append(d) or "notify")
    check("the next poll drains the pending notice exactly once", len(sent) == 1, sent)
    check("... and the outbox is settled", OUT.pending("pr_ci_notice") == [],
          OUT.pending("pr_ci_notice"))
    row = C.evaluate(trigger(), mode="active", now=now() + 120, store=st,
                     notify=lambda d: sent.append(d) or "notify")
    check("... and a later poll does not send it again",
          len(sent) == 1 and row["reason_code"] == "duplicate_sha_state", (sent, row))


def t_a_dropped_notice_is_settled_and_says_why():
    st = fresh()
    row = C.evaluate(trigger(), mode="active", now=now(), store=st,
                     notify=lambda d: "dropped")
    check("the arbiter's DROPPED is recorded as ignored, with its own reason",
          row["outcome"] == "ignored"
          and row["reason_code"] == "attention_budget_dropped"
          and row["delivery"] == "dropped", row)
    check("... and it is not left pending in the outbox", OUT.pending() == [],
          OUT.pending())


def t_observe_never_delivers_even_a_notice_a_crash_left_pending():
    st = fresh()
    boom = lambda d: (_ for _ in ()).throw(RuntimeError("boom"))
    C.evaluate(trigger(), mode="active", now=now(), store=st, notify=boom)
    check("the failed send left one notice owed", len(OUT.pending("pr_ci_notice")) == 1,
          OUT.pending())
    sent = []
    row = C.evaluate(trigger(), mode="observe", now=now() + 1, store=st,
                     notify=lambda d: sent.append(d) or "notify")
    check("OBSERVE delivers nothing, even with a notice owed", sent == [], sent)
    check("... and the notice is still owed, waiting for the mode", len(
        OUT.pending("pr_ci_notice")) == 1, OUT.pending())
    check("... while the row says this commit was already reported",
          row["reason_code"] == "duplicate_sha_state", row)
    sent.clear()
    C.evaluate(trigger(), mode="active", now=now() + 2, store=st,
               notify=lambda d: sent.append(d) or "notify")
    check("promoting to active delivers it exactly once", len(sent) == 1, sent)


def t_a_sender_that_cannot_answer_leaves_the_notice_owed():
    """None is not "dropped": a sender that could not place the notice at all
    (no arbiter, a missing module) must leave it in the outbox, while the
    arbiter's own "dropped" settles it. Collapsing the two would turn a missing
    module into a silently lost notice."""
    st = fresh()
    row = C.evaluate(trigger(), mode="active", now=now(), store=st,
                     notify=lambda d: None)
    check("a sender that cannot answer marks the delivery failed",
          row["delivery"] == "failed" and row["outcome"] == "would_notify", row)
    check("... and the notice is still owed", len(OUT.pending("pr_ci_notice")) == 1,
          OUT.pending())
    sent = []
    C.evaluate(trigger(), mode="active", now=now() + 1, store=st,
               notify=lambda d: sent.append(d) or "notify")
    check("... so the next active run delivers it exactly once", len(sent) == 1, sent)


# ==========================================================================
#   7. The decisions route and the job body
# ==========================================================================

class FakeHandler:
    def __init__(self, path, body=b"{}"):
        self.path = path
        self.body = body
        self.sent = None

    def do_GET(self):
        self.sent = ("original GET", None)

    def _send(self, code, obj):
        self.sent = (code, obj)
        return self.sent


def t_the_decisions_route_answers_only_its_own_path():
    st = fresh()
    C.set_store(st)
    C.evaluate(trigger(), mode="observe", now=now(), store=st)

    class H(FakeHandler):
        pass
    line = C.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                     read_body=lambda h: h.body)
    check("the banner line names the watcher and its mode",
          "GitHub watcher" in line and "observe" in line, line)
    h = H(C.PATH)
    H.do_GET(h)
    check("GET /api/watch/decisions answers here",
          h.sent[0] == 200 and h.sent[1]["available"] is True, h.sent)
    body = h.sent[1]
    check("... with the recent rows, newest first",
          body["count"] == 1 and body["decisions"][0]["thread_key"] == "pr:1135:a1b2c3d4e",
          body.get("decisions"))
    check("... and the closed reason list, so a client can explain a code",
          isinstance(body["reasons"], dict) and "ci_required_failed" in body["reasons"])
    h = H(C.PATH + "?limit=1")
    H.do_GET(h)
    check("?limit=1 is honoured", h.sent[1]["count"] == 1, h.sent)
    check("... and the raw limit reaches view() clamped, never as a crash",
          C.view("0")["count"] == 1 and C.view("-4")["count"] == 1
          and C.view("abc")["count"] == 1 and C.view("9999")["count"] == 1)
    h = H("/api/status")
    H.do_GET(h)
    check("every other GET goes to the server's own handler",
          h.sent[0] == "original GET")
    check("install twice wraps once", "already on" in C.install(
        H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: h.body))
    C._reset_for_tests()


def t_the_route_is_not_on_the_phone_paths_and_reads_only():
    st = fresh()
    C.set_store(st)

    class H(FakeHandler):
        pass
    C.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: h.body)
    h = H(C.PATH)
    H.do_GET(h)
    check("the body is a read: no write, no card, no 'ok' promise",
          "ok" not in h.sent[1] and isinstance(h.sent[1]["decisions"], list))
    check("there is no POST half at all",
          not hasattr(H, "do_POST") or "do_POST" not in H.__dict__)
    C._reset_for_tests()


def t_the_job_body_asks_before_it_reads_github():
    st = fresh()
    C.set_store(st)
    asked = []
    ran = []

    class Ctx:
        def require(self, action, detail=None):
            asked.append(action)
            return True

        def progress(self, fraction=None, note=""):
            ran.append((fraction, note))

    def runner(args):
        ran.append(tuple(args))
        return json.dumps({"number": 7, "headRefOid": "abcdef1234567890",
                           "mergeable": "MERGEABLE", "statusCheckRollup": rollup()})

    real = C.alert_mode
    try:
        C.alert_mode = lambda: "off"
        out = C.handler(Ctx(), {"pr": 7})
        check("mode off: nothing is fetched at all",
              out["mode"] == "off" and out["checked"] == 0
              and not any(isinstance(x, tuple) for x in ran), (out, ran))
        check("... and no capability is asked for", asked == [], asked)

        C.alert_mode = lambda: "observe"
        out = C.handler(Ctx(), {"pr": 7, "_runner": runner})
        check("a running watcher ASKS github_read before it reads GitHub",
              asked == [C.ACTION] == ["github_read"], asked)
        check("... it polled the pull request and evaluated it",
              out["checked"] == 1 and out["decisions"][0]["reason_code"]
              == "ci_all_required_green", out)
        check("... in observe mode, so the row is a would_notify",
              out["decisions"][0]["outcome"] == "would_notify", out)

        asked.clear()
        out = C.handler(Ctx(), {})
        check("no pull request number -> nothing watched, and no ask",
              out["checked"] == 0 and asked == [], (out, asked))
    finally:
        C.alert_mode = real


def t_the_job_body_is_registered_by_name_and_starts_nothing():
    src = (HERE / "jarvis_watch_ci.py").read_text(encoding="utf-8")
    check("the handler name is watch_pr_checks", C.HANDLER == "watch_pr_checks")
    check("registration is by NAME, never a stored callable",
          "jarvis_jobs.register(HANDLER, handler)" in src)
    for forbidden in ("threading.Thread(", "while True", "Timer(",
                      "register_kind", "setInterval"):
        check(f"the module starts no polling of its own ({forbidden})",
              src.count(forbidden) == 0, src.count(forbidden))
    check("it registers nothing at import time",
          "register_job()\n" not in src.split('if __name__')[0].split("def register_job")[0])


def t_the_ci_body_is_reachable_from_the_one_startup_call_that_exists():
    """A test of a function is not a test of its wiring.

    `jarvis_hud.main()` calls exactly ONE registration at start-up -
    `jarvis_watch.register_job()` (jobs-routes.patch) - so a job body registered
    anywhere else would exist in this suite and in no running Jarvis, and
    `POST /api/jobs` with `{"kind": "watch_pr_checks"}` would answer "no handler
    by that name". This calls the SAME function the server calls and checks the
    body arrives with it.
    """
    import jarvis_jobs as J
    W.register_job()
    handlers = J.handlers()
    check("the existing start-up call still registers its own body",
          "watch_github" in handlers, handlers)
    check("... and the CI watcher's body arrives with it",
          C.HANDLER in handlers, handlers)
    check("registering a body starts nothing: the route is not armed and no "
          "decision row was written", C.armed() is False)


def t_status_says_what_is_watched_and_how_loudly():
    st = fresh()
    got = C.status(store=st)
    check("status names the mode and the two job lists",
          got["mode"] == "observe" and len(got["required_jobs"]) == 7
          and len(got["informational_jobs"]) == 2, got)
    check("... and the route it answers", got["path"] == "/api/watch/decisions")
    check("... and that it is not armed until install() is called", got["armed"] is False)


# ==========================================================================

def main() -> int:
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
    shutil.rmtree(_WORK, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
