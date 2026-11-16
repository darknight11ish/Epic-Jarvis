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
    """A stand-in for `_default_fetch`: records every call, answers by rule."""

    def __init__(self, status=200, body="[]"):
        self.status = status
        self.body = body
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}),
                           "body": body, "timeout": timeout})
        return self.status, self.body

    def urls(self):
        return [c["url"] for c in self.calls]


class Routed(Fake):
    """A `Fake` that answers by URL substring, first match wins."""

    def __init__(self, routes):
        super().__init__()
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
        return 404, "{}"


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


def _fake(*, runs, checks=NO_CHECKS, jobs=None):
    """The three reads a pull-request CI question makes, in the plan's order."""
    routes = [(f"/commits/{SHA}/check-runs", (200, checks))]
    if jobs is not None:
        routes.insert(0, ("/actions/runs/4242/jobs", (200, jobs)))
    routes.append(("/actions/runs", (200, runs)))
    routes.append(("/pulls/7", (200, _pr_doc())))
    return Routed(routes)


# --------------------------------------------------------------------------
#   1. ONE red run and no check runs: say ONE, never "more than one"
# --------------------------------------------------------------------------


def t_one_red_run_is_never_called_more_than_one():
    """DEF-078: the exact state that produced the false sentence.

    One workflow run on the head commit, red. The check-runs answer reports no
    check runs, so the run itself is judged - and there is exactly one of them.
    """
    fake = _fake(runs=_runs(_run()), jobs=_jobs(_job()))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("the pull-request CI answer is a 200 answer, not an error",
          out.get("ok") is True, out)
    check("ONE red run is never described as 'more than one'",
          "more than one ci run" not in text.lower(), text)
    check("the answer says there is ONE CI run on the commit",
          re.search(r"(?<!more than )one ci run is on the head commit",
                    text.lower()), text)
    check("the answer says the run did not finish successfully",
          "did not finish successfully" in text, text)
    check("... and it never says the run passed",
          " passed" not in text.lower(), text)
    check("the failing run on that commit is still named",
          "CI: failure" in text, text)
    check("one bounded excerpt of the failing log is still shown",
          "error[E0308]" in text, text)
    check("the check-runs read really happened, so the state is the real one",
          any(f"/commits/{SHA}/check-runs" in u for u in fake.urls()),
          fake.urls())


def t_two_red_runs_are_counted_as_two():
    """The count sentence reports the runs it READ, not a fixed phrase."""
    rows = [_run(4242, "CI"), _run(4243, "audit")]
    fake = _fake(runs=_runs(*rows),
                 jobs=_jobs(_job(name="CI", conclusion="failure")))
    out = _run_one("pr", "7", fetch=fake)
    text = out.get("text", "")
    check("two red runs are counted as TWO",
          "2 ci runs are on the head commit" in text.lower(), text)
    check("... and neither is called 'more than one' in the old phrase",
          "more than one ci run" not in text.lower(), text)
    check("... and both runs are named as not successful",
          "CI: failure" in text and "audit: failure" in text, text)


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
    check("... and the ONE run it did read is still counted as one",
          re.search(r"(?<!more than )one ci run is on the head commit",
                    text.lower()), text)
    check("... and no false 'more than one' count is made",
          "more than one ci run" not in text.lower(), text)
    check("... and the failing run remains named",
          "CI: failure" in text, text)


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
    for fn in (t_one_red_run_is_never_called_more_than_one,
               t_two_red_runs_are_counted_as_two,
               t_the_check_run_failure_is_still_the_authority_when_readable,
               t_an_unreadable_check_runs_answer_is_said_not_guessed,
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
