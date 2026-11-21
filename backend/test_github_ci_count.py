"""test_github_ci_count.py - DEF-078: the CI count sentence must be true.

    python3 -B test_github_ci_count.py

THE DEFECT (measured 2026-11-16, from the author who left it in
`decisions.d/2026-11-15-github-one-renderer.md`). `github_ci_status` asked about
a pull request answers for the ONE commit at its head: every CHECK GitHub
reports for that commit, and every workflow RUN on it. When the check-runs
answer held no check runs at all, the answer fell back to judging the runs - and
the sentence it used was "More than one CI run is on the head commit of pull
request #N in owner/repo and at least one did not finish successfully", whatever
the run list held. With exactly ONE red run on the head commit and no check runs
readable, that is a false count about the owner's own repository: the reader is
told there is more than one run when Jarvis has only ever seen one, and the
number the sentence asserts is one the reader never managed to verify.

WHAT THIS SUITE PINS

  1. One red run and no check runs: the answer says ONE, names the run's failing
     check and shows one log excerpt - and never says "more than one".
  2. Two red runs and no check runs: the answer counts the TWO it read.
  3. A check-runs answer that could not be read is SAID, not guessed at: the
     answer does not pretend GitHub reported no check runs, and it still counts
     the runs it read truthfully.
  4. A branch read of the same evidence keeps its own sentence (the newest
     run), so the one renderer cannot drift into two contradictory answers.

RULING 5.2 (2026-11-20) is why the expectations below were rewritten. A queued
or in-progress workflow run has `conclusion: None`, and `_ci_words` counted every
conclusion not in the pass set as red - so a run that had NOT FINISHED was
labelled with its own status ("pending") under a "failing check(s)" headline.
Deploy #4 answered "What is failing on pull request 1424?" with

    GitHub reports no check runs on pull request #1424 ...; 2 CI runs are on
    the head commit and at least one did not finish successfully. 2 failing
    check(s): CI: pending Jarvis client: pending

while `gh pr checks 1424` showed those checks PENDING. The ruling: group the
answer honestly as pending vs failing vs passing, never call a pending run a
failure, and read the PR's COMBINED check set - both check runs and the commit
statuses `gh pr checks` also shows. So:

  5. A still-going run is named as still going and nothing has failed - one
     pending run, and two (the measured count).
  6. Failed and pending runs are grouped separately: the failed run is named
     under the failing half, the pending one after it, never as a failure.
  7. A commit STATUS context is judged with the check runs (the combined
     source), and a pending status is still running, not failing.
  8. A commit-statuses read that fails is SAID: the answer is still given, and
     it names the check list as check-runs only.

No socket is opened: every request goes through a fake `fetch`, and `_Token`
replaces the saved credential for the length of one call, so the owner's own
token is never consulted.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# A temp config dir BEFORE any backend import: jarvis_gate opens an approval
# queue at import time, and this suite must not read or write the owner's own.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-github-ci-count-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
# No push: the topic is unset, so nothing can post to ntfy.sh.
os.environ["JARVIS_NTFY_TOPIC"] = ""

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_github as GH  # noqa: E402

#: A token distinctive enough that finding it anywhere is a leak, and shaped
#: like the real thing so nothing can pass by being "not token-like".
TOKEN = "ghp_CICOUNTnotarealtoken00000000000000000"

REPO = "darknight11ish/Epic-Jarvis"
SHA = "0123456789abcdef0123456789abcdef01234567"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Fake:
    """A stand-in for `_default_fetch`: records every call, answers by rule.

    A repository root and a branch are answered by `target_answer` BEFORE
    `status`/`body`: since 2026-11-17 `run()` resolves what a request names
    before it sends anything (the Q5 target gate), and those two reads are not
    the answer this fake is modelling. `missing` and `missing_branches` give
    those names GitHub's real 404.
    """

    def __init__(self, status=200, body="[]", missing=(), missing_branches=()):
        self.status = status
        self.body = body
        self.calls = []
        self.missing = {str(m).lower() for m in missing}
        self.missing_branches = {str(b) for b in missing_branches}

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}),
                           "body": body, "timeout": timeout})
        answer = self.target_answer(url)
        if answer is not None:
            return answer
        return self.status, self.body

    def target_answer(self, url):
        """The gate's own answer for a repository root or a branch, or None."""
        root = _repo_root(url)
        if root is not None:
            if root.lower() in self.missing:
                return 404, "{}"
            return 200, json.dumps({"full_name": root,
                                    "permissions": {"push": True}})
        branch = _branch_name(url)
        if branch is not None:
            if branch in self.missing_branches:
                return 404, "{}"
            return 200, json.dumps({"name": branch})
        return None

    def after_target(self):
        """The calls after the target gate's own leading reads."""
        calls = list(self.calls)
        while calls and self.target_answer(calls[0]["url"]) is not None:
            calls.pop(0)
        return calls

    def urls(self):
        return [c["url"] for c in self.calls]


class Routed(Fake):
    """A `Fake` that answers by URL substring, first match wins."""

    def __init__(self, routes, missing=(), missing_branches=()):
        super().__init__(missing=missing, missing_branches=missing_branches)
        self.routes = list(routes)

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}),
                           "body": body, "timeout": timeout})
        for needle, answer in self.routes:
            if needle in url:
                if callable(answer):
                    return answer(self.calls[-1])
                return answer
        answer = self.target_answer(url)
        if answer is not None:
            return answer
        return 404, "{}"


#: `owner/name` for exactly a repository root under api.github.com, else None.
_REPO_ROOT = re.compile(r"^https://api\.github\.com/repos/([^/?#]+/[^/?#]+)$")

#: The branch name for a branch read, else None (a branch name may hold "/").
_BRANCH_READ = re.compile(r"^https://api\.github\.com/repos/[^/?#]+/[^/?#]+"
                          r"/branches/(.+)$")


def _repo_root(url: str):
    found = _REPO_ROOT.match(str(url or "").split("?")[0])
    return found.group(1) if found else None


def _branch_name(url: str):
    found = _BRANCH_READ.match(str(url or "").split("?")[0])
    return found.group(1) if found else None


class FakeLog:
    """A stand-in for the job-log opener: `(status, text, headers)`."""

    def __init__(self, text="error[E0308]: mismatched types\n"):
        self.text = text
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url})
        if "api.github.com" in url:
            return 302, "", {
                "location": "https://objects.githubusercontent.com/signed?x=1"}
        return 200, self.text, {}


class _Token:
    """The saved token, for the length of one block. Always restored."""

    def __enter__(self):
        self._was = GH._token
        GH._token = lambda: TOKEN
        return self

    def __exit__(self, *_exc):
        GH._token = self._was
        return False


def _run_one(name, *words, fetch, log=None):
    """The answer `github_ci_status` gives for one question, through `run()`."""
    with _Token():
        req = GH.plan_ci({"repo": REPO, name: words[0]})
        return GH.run(req, fetch=fetch, approved=True, log=log or FakeLog())


def _pr_doc(number=7):
    return json.dumps({"number": number, "state": "open",
                       "head": {"sha": SHA, "ref": "fix/the-defect"},
                       "base": {"ref": "main"}})


def _run(run_id=4242, name="CI", conclusion="failure", status="completed"):
    return {"id": run_id, "name": name, "status": status,
            "conclusion": conclusion, "head_branch": "main", "head_sha": SHA}


def _runs(*rows):
    return json.dumps({"total_count": len(rows), "workflow_runs": list(rows)})


def _jobs(*rows):
    return json.dumps({"jobs": list(rows)})


def _job(job_id=11, name="rust", conclusion="failure"):
    return {"id": job_id, "name": name, "status": "completed",
            "conclusion": conclusion}


#: No check runs at all, the answer GitHub really gives a workflow-only repo.
NO_CHECKS = json.dumps({"total_count": 0, "check_runs": []})

#: The commit-statuses answer for a head commit with no status contexts. It is
#: a READABLE answer, so the combined-source read adds no "check-runs only" note.
NO_STATUSES = json.dumps({"state": "success", "statuses": []})


def _fake(*, runs, checks=NO_CHECKS, statuses=NO_STATUSES, status_answer=None,
          jobs=None):
    """The reads a pull-request CI question makes, in the answer's order.

    `status_answer` replaces the commit-statuses answer, so a test can make that
    one read fail; `statuses` is the JSON a readable answer carries. The plan's
    own three reads stay the three in its steps - the statuses read is the extra
    one `_ci_result` makes, and its route is deliberately last but one so it can
    never shadow the check-runs read.
    """
    routes = [(f"/commits/{SHA}/check-runs", (200, checks))]
    if jobs is not None:
        routes.insert(0, ("/actions/runs/4242/jobs", (200, jobs)))
    if status_answer is not None:
        routes.append((f"/commits/{SHA}/status", status_answer))
    else:
        routes.append((f"/commits/{SHA}/status", (200, statuses)))
    routes.append(("/actions/runs", (200, runs)))
    routes.append(("/pulls/7", (200, _pr_doc())))
    return Routed(routes)


# --------------------------------------------------------------------------
#   1. ONE red run and no check runs: say ONE, never "more than one"
# --------------------------------------------------------------------------


def t_the_plan_keeps_its_three_reads():
    """The statuses read is made in `_ci_result`, NOT added to the plan.

    The pull form is recognised by `steps[-1]` being the check-runs read, so a
    fourth planner step would be a change to how the answer is shaped. Ruling
    5.2's combined read is an EXTRA read made by `_ci_result` after the fixed
    three, and the plan must stay exactly the three it advertises.
    """
    r = GH.plan_ci({"repo": REPO, "pr": "7"})
    check("the pull-request plan keeps exactly THREE fixed reads",
          len(r.steps) == 3, [s.path for s in r.steps])
    check("... and the last one is still the head commit's check-runs read",
          "/check-runs" in r.steps[-1].path, [s.path for s in r.steps])
    check("... so the pull form's own detection still sees it",
          bool(r.number) and len(r.steps) >= 3
          and "/check-runs" in r.steps[-1].path)


def t_a_still_going_run_is_never_counted_as_red():
    """RULING 5.2: the measured deploy #4 state - one run still going.

    One workflow run on the head commit is still going (`status: in_progress`,
    `conclusion: None`) and the check-runs answer reports no check runs. The old
    answer counted that run RED because its conclusion was not in the pass set,
    then labelled it with its own status under a "failing check(s)" headline.
    Nothing there has failed.
    """
    fake = _fake(runs=_runs(_run(conclusion=None, status="in_progress")))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("a pull-request CI answer with only a still-going run is a 200",
          out.get("ok") is True, out)
    check("the still-going run is named as still going",
          "still going" in text.lower(), text)
    check("... and the run is named", "CI" in text, text)
    check("... and the answer says nothing is known about it yet",
          "nothing is known about them yet" in text.lower(), text)
    check("... and it never says the run failed or did not finish successfully",
          "did not finish successfully" not in text.lower()
          and "failed" not in text.lower(), text)
    check("... and no 'failing check(s)' list is printed",
          "failing check" not in text.lower(), text)
    check("... and it still reports that GitHub has no check runs there",
          "no check runs" in text.lower(), text)
    check("... and the combined-source read on the head commit really happened",
          any(f"/commits/{SHA}/status" in u for u in fake.urls()), fake.urls())


def t_two_still_going_runs_are_named_and_counted_as_pending():
    """The deploy #4 count: two runs, both PENDING, neither a failure."""
    fake = _fake(runs=_runs(
        _run(4242, "CI", conclusion=None, status="queued"),
        _run(4243, "Jarvis client", conclusion=None, status="in_progress")))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("two still-going runs are counted as two, and both are named",
          "2 ci runs are still going" in text.lower()
          and "CI" in text and "Jarvis client" in text, text)
    check("... and neither is put under a failing-check headline",
          "failing check" not in text.lower(), text)
    check("... and neither is called 'did not finish successfully'",
          "did not finish successfully" not in text.lower(), text)


def t_one_red_run_is_never_called_more_than_one():
    """DEF-078, kept: one FAILED run is said as one run.

    One workflow run on the head commit, finished as a failure. The check-runs
    answer reports no check runs, so the run itself is judged - and there is
    exactly one of them. RULING 5.2 changes the words from "did not finish
    successfully" to "failed": it is a finished failure, not an unfinished run.
    """
    fake = _fake(runs=_runs(_run()), jobs=_jobs(_job()))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("the pull-request CI answer is a 200 answer, not an error",
          out.get("ok") is True, out)
    check("ONE red run is never described as 'more than one'",
          "more than one ci run" not in text.lower(), text)
    check("the answer says there is ONE CI run on the commit, and it failed",
          "one ci run on the head commit failed" in text.lower(), text)
    check("... and it no longer says 'did not finish successfully'",
          "did not finish successfully" not in text.lower(), text)
    check("... and it never says the run passed",
          " passed" not in text.lower(), text)
    check("the failing run on that commit is still named",
          "CI: failure" in text, text)
    check("one bounded excerpt of the failing log is still shown",
          "error[E0308]" in text, text)
    check("the check-runs read really happened, so the state is the real one",
          any(f"/commits/{SHA}/check-runs" in u for u in fake.urls()),
          fake.urls())
    check("the readable empty statuses answer adds no 'check-runs only' note",
          "check-runs only" not in text.lower(), text)


def t_two_red_runs_are_counted_as_two():
    """The count sentence reports the runs it READ, not a fixed phrase."""
    rows = [_run(4242, "CI"), _run(4243, "audit")]
    fake = _fake(runs=_runs(*rows),
                 jobs=_jobs(_job(name="CI", conclusion="failure")))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("two red runs are counted as TWO",
          "2 ci runs on the head commit failed" in text.lower(), text)
    check("... and neither is called 'more than one' in the old phrase",
          "more than one ci run" not in text.lower(), text)
    check("... and neither is called 'did not finish successfully'",
          "did not finish successfully" not in text.lower(), text)
    check("... and both runs are named as not successful",
          "CI: failure" in text and "audit: failure" in text, text)


def t_failed_and_pending_runs_are_grouped_separately():
    """RULING 5.2: a failed run under the failing half, a pending one apart.

    One run finished as a failure and one is still going. The failed one belongs
    under the failing headline; the still-going one is named afterwards as still
    going and is NEVER listed as a failing check.
    """
    fake = _fake(
        runs=_runs(_run(4242, "CI", conclusion="failure"),
                   _run(4243, "Jarvis client", conclusion=None,
                        status="in_progress")),
        jobs=_jobs(_job(name="CI", conclusion="failure")))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("the failed run is named under a failing headline",
          "one ci run on the head commit failed" in text.lower()
          and "1 failing check(s):" in text and "CI: failure" in text, text)
    check("... and the still-going run is named separately, as still going",
          "still going" in text.lower() and "Jarvis client" in text, text)
    check("... and the still-going run is never listed as a failing check",
          "Jarvis client: pending" not in text
          and "Jarvis client: failure" not in text, text)


def t_the_check_run_failure_is_still_the_authority_when_readable():
    """A readable red check keeps its own sentence - the fix touches the fallback."""
    checks = json.dumps({"total_count": 1, "check_runs": [
        {"id": 77, "name": "backend", "status": "completed",
         "conclusion": "failure"}]})
    fake = _fake(runs=_runs(_run()), checks=checks,
                 jobs=_jobs(_job(job_id=88, name="backend")))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("a readable red check is reported as the checks NOT being green",
          "checks on pull request #7" in text and "NOT all green" in text, text)
    check("... and the run count sentence is not used at all",
          "more than one ci run" not in text.lower()
          and "one ci run" not in text.lower(), text)
    check("... and the red check is named", "backend: failure" in text, text)


# --------------------------------------------------------------------------
#   2. A check-runs answer that could not be read is SAID
# --------------------------------------------------------------------------


def t_an_unreadable_check_runs_answer_is_said_not_guessed():
    """No readable check runs is a different fact from 'no check runs exist'."""
    fake = _fake(runs=_runs(_run()), checks="not a github api answer",
                 jobs=_jobs(_job()))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("the unreadable check-runs answer is said in plain words",
          "did not answer with the check runs" in text, text)
    check("... it does not pretend GitHub reported NO check runs",
          "no check runs" not in text.lower(), text)
    check("... and the ONE run it did read is still counted as one, failed",
          "one ci run on the head commit failed" in text.lower(), text)
    check("... and no false 'more than one' count is made",
          "more than one ci run" not in text.lower(), text)
    check("... and the failing run remains named",
          "CI: failure" in text, text)


# --------------------------------------------------------------------------
#   2b. The COMBINED check source: check-runs AND commit statuses
# --------------------------------------------------------------------------


def t_a_commit_status_context_is_judged_with_the_check_runs():
    """RULING 5.2: the PR's check set is check-runs AND commit statuses.

    `gh pr checks` shows both sources. A status context that failed must make
    the commit NOT green even when the check-runs answer is empty and the run
    list is empty (so the head sha can only come from the pull request itself);
    a passing status set must read as a finished check.
    """
    failing = json.dumps({"state": "failure", "statuses": [
        {"context": "ci/legacy", "state": "failure"},
        {"context": "deploy/preview", "state": "success"}]})
    fake = _fake(runs=_runs(), checks=NO_CHECKS, statuses=failing)
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("a failing commit status is judged with the check runs",
          out.get("ok") is True and "NOT all green" in text
          and "ci/legacy: failure" in text, text)
    check("... and it reads the head commit's status endpoint",
          any(f"/commits/{SHA}/status" in u for u in fake.urls()), fake.urls())
    passing = json.dumps({"state": "success", "statuses": [
        {"context": "ci/legacy", "state": "success"}]})
    fake = _fake(runs=_runs(_run(conclusion="success")), checks=NO_CHECKS,
                 statuses=passing)
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("a passing commit status is a check that finished successfully",
          "finished successfully" in text and "NOT all green" not in text, text)


def t_a_pending_commit_status_is_still_running_never_failing():
    """A pending status is not a failure, exactly like a pending check run."""
    statuses = json.dumps({"statuses": [
        {"context": "ci/legacy", "state": "pending"}]})
    fake = _fake(runs=_runs(_run(conclusion=None, status="in_progress")),
                 checks=NO_CHECKS, statuses=statuses)
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("a pending commit status is reported as not finished",
          "not all finished" in text.lower() and "ci/legacy" in text, text)
    check("... and it is never called failing",
          "failed" not in text.lower() and "failing" not in text.lower(), text)


def t_a_statuses_read_that_fails_is_said_not_guessed():
    """The combined read failing is SAID: the answer names check-runs only."""
    fake = _fake(runs=_runs(_run(conclusion="success")), checks=NO_CHECKS,
                 status_answer=(404, "{}"))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("the answer is still given when the statuses read fails",
          out.get("ok") is True and bool(text), out)
    check("... and it says the check list is check-runs only",
          "check-runs only" in text.lower(), text)
    check("... and it does not claim GitHub has no such statuses",
          "no statuses" not in text.lower()
          and "not have that" not in text.lower(), text)


# --------------------------------------------------------------------------
#   3. The branch form of the same evidence keeps its own true sentence
# --------------------------------------------------------------------------


def t_a_branch_read_of_one_red_run_keeps_its_own_sentence():
    """One renderer: the branch form must not contradict the commit form."""
    fake = Routed([("/actions/runs/4242/jobs", (200, _jobs(_job()))),
                   ("/actions/runs", (200, _runs(_run())))])
    out = _run_one("branch", "main", fetch=fake)
    text = out.get("text", "")
    check("the branch answer still names the newest run and its failure",
          "The newest CI run (CI on main) failed" in text, text)
    check("... and it makes no count claim at all",
          "more than one ci run" not in text.lower()
          and "ci runs are on" not in text.lower(), text)
    check("... and it names the failing check the same way",
          "rust: failure" in text, text)


if __name__ == "__main__":
    print(f"  file  {HERE / 'jarvis_github.py'}")
    print(f"  logs  {os.environ['JARVIS_LOG_DIR']}")
    for fn in (t_the_plan_keeps_its_three_reads,
               t_a_still_going_run_is_never_counted_as_red,
               t_two_still_going_runs_are_named_and_counted_as_pending,
               t_one_red_run_is_never_called_more_than_one,
               t_two_red_runs_are_counted_as_two,
               t_failed_and_pending_runs_are_grouped_separately,
               t_the_check_run_failure_is_still_the_authority_when_readable,
               t_an_unreadable_check_runs_answer_is_said_not_guessed,
               t_a_commit_status_context_is_judged_with_the_check_runs,
               t_a_pending_commit_status_is_still_running_never_failing,
               t_a_statuses_read_that_fails_is_said_not_guessed,
               t_a_branch_read_of_one_red_run_keeps_its_own_sentence):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
