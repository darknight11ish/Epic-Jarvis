"""test_github_parity.py - the 2026-11-10 GitHub merge / fix-push / cockpit lane.

    python3 test_github_parity.py

WHAT THIS SUITE IS FOR

The owner's decision of 2026-11-10 (Gemini ruling Q1, "Everything at once")
added three tools to `jarvis_github.py` and `jarvis_agent.py`:

  * `github_pr_scan`  - the READ-ONLY pull request cockpit: merge-ready,
                        blocked, conflicted, running or draft, and which
                        required check holds each one.
  * `github_merge_pr` - merge ONE pull request with a MERGE COMMIT only,
                        pinned to the exact 40-character head commit the card
                        showed.
  * `github_fix_and_push` - copy a failing pull request into an isolated
                        scratch folder, then push the commits to that pull
                        request's OWN branch on a SECOND card.

and the same day's owner directive: "Jarvis fully aware of its abilities around
github, the small details around github, and everything else around github as
well" - so the capability inventory, the token handling, the limits and the
never list are checked here too, against one source of truth
(`jarvis_github.CAPABILITIES`).

This file is deliberately separate from `test_github_tools.py`: that suite
pins the 2026-11-03/09 surface and only adds what that surface needs. Nothing
here opens a socket, reads a real token, starts a real git process, or writes
outside a temporary folder.

WHAT IT PINS, IN ORDER

  1. The merge: merge-commit only (squash/rebase/admin/auto-merge impossible
     by construction), refused for a draft, a conflict, a blocked state, a
     running check, a required check that did not pass, a missing required
     check, a moved head commit or an absent head sha; the success path sends
     exactly the pinned body to exactly one PUT.
  2. Fix-and-push: staged in an isolated folder under the scratch root, the
     push only to a pull request's own branch, never main/master/release/* or
     hotfix/*, never a force/delete/mirror flag, never a changed credential
     file, and the push card shows the failing checks, the files, the commits
     and the exact command. The marker is written once, and a re-prepare does
     not duplicate it.
  3. The cockpit: the five classifications, reads only (GET, no body), and a
     failed read said in plain words.
  4. The job log: the 302 is read, never followed; the signed address must be
     https on a host GitHub owns; the second request carries NO Authorization
     header; any other host is refused.
  5. Awareness: one CAPABILITIES inventory that names every action that is
     really wired, every absolute ban, the token handling, the api.github.com
     limit, the redirect-safe log fetch, the scratch-folder push, the
     default-off card and the stale-stream hold - and the same text on the
     tool descriptions the model reads.
  6. Safety: nothing but GET is sent without a card; every write is at "ask"
     and in NEEDS_A_PERSON; and a stale event stream refuses the approval in
     the desktop's own command (`stale_answer_refusal`).

Standard library only.
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
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-github-parity-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ["JARVIS_NTFY_TOPIC"] = ""

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

import jarvis_github as GH  # noqa: E402
import jarvis_agent as AG  # noqa: E402

TOKEN = "ghp_TESTONLYnotarealtoken0000000000000000"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
MERGED_SHA = "fedcba9876543210fedcba9876543210fedcba98"
OTHER_SHA = "aaaabbbbccccddddeeeeffff00001111222233334"
REPO_NAME = "darknight11ish/Epic-Jarvis"
PR_NUMBER = "1116"
BRANCH = "feature/tray-icon"
TOMLS = (HERE / "rebuilt" / "jarvis-framework.toml",
         REPO / "jarvis-backend" / "jarvis-framework.toml")
COMMANDS_RS = REPO / "jarvis-desktop" / "src-tauri" / "src" / "commands.rs"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """Something this machine cannot run: printed separately, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The fakes: no socket, no process, no real token
# --------------------------------------------------------------------------


class NoSocket:
    """Refuses every real socket, for the whole run."""

    def __enter__(self):
        import socket
        self._socket = socket.socket
        self._pair = socket.socketpair

        def refuse(*_a, **_k):
            raise AssertionError("this suite must never open a socket")

        socket.socket = refuse
        socket.socketpair = refuse
        return self

    def __exit__(self, *_exc):
        import socket
        socket.socket = self._socket
        socket.socketpair = self._pair
        return False


class Routed:
    """A stand-in for `_default_fetch`, answering by URL substring.

    `routes` is `(needle, (status, body))`, first match wins; an address no
    route names is a 404, which is GitHub's answer for a thing that is not
    there either.
    """

    def __init__(self, routes=()):
        self.routes = list(routes)
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}), "body": body})
        for needle, answer in self.routes:
            if needle in url:
                return answer
        return 404, "{}"

    def urls(self):
        return [c["url"] for c in self.calls]

    def methods(self):
        return [c["method"] for c in self.calls]

    def writes(self):
        return [c for c in self.calls if c["method"] not in ("GET", "HEAD")]


class FakeGit:
    """A stand-in for `_default_git`; records every command, starts nothing."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, args, *, cwd=None, env=None):
        self.calls.append({"args": [str(a) for a in args], "cwd": cwd,
                           "env": dict(env or {})})
        joined = " ".join(str(a) for a in args)
        for needle, answer in self.answers:
            if needle in joined:
                return answer
        return 0, "", ""

    def commands(self):
        return [" ".join(c["args"]) for c in self.calls]

    def pushes(self):
        return [c for c in self.calls if c["args"][:1] == ["push"]]


class FakeLog:
    """A stand-in for the job-log opener: `(status, text, headers)`."""

    def __init__(self, location="https://objects.githubusercontent.com/signed?x=1",
                 text="error[E0308]: mismatched types\n", status=302):
        self.location = location
        self.text = text
        self.status = status
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {})})
        if "api.github.com" in url and self.status in (301, 302, 303, 307, 308):
            return self.status, "", {"location": self.location}
        return 200, self.text, {}


class _Token:
    """The saved token, for the length of one block. Always restored."""

    def __init__(self, value=TOKEN):
        self.value = value

    def __enter__(self):
        self._was = GH._token
        GH._token = lambda: self.value
        return self

    def __exit__(self, *_exc):
        GH._token = self._was
        return False


def _json(raw):
    return json.loads(raw.decode("utf-8")) if isinstance(raw, (bytes, bytearray)) \
        else json.loads(raw)


def _all_green(extra=()):
    runs = [{"id": str(900 + i), "name": name, "status": "completed",
             "conclusion": "success",
             "details_url": f"https://github.com/{REPO_NAME}/actions/runs/77/"
                            f"job/{500 + i}"}
            for i, name in enumerate(GH.REQUIRED_CHECKS)]
    runs.extend(extra)
    return 200, json.dumps({"total_count": len(runs), "check_runs": runs})


def _pr(**over):
    doc = {"number": int(PR_NUMBER), "title": "Fix the tray icon", "draft": False,
           "state": "open", "mergeable": True, "mergeable_state": "clean",
           "head": {"sha": HEAD_SHA, "ref": BRANCH,
                    "repo": {"full_name": REPO_NAME}}}
    doc.update(over)
    return 200, json.dumps(doc)


def _merge_request(**over):
    args = {"repo": REPO_NAME, "number": PR_NUMBER, "head_sha": HEAD_SHA}
    args.update(over)
    return GH.plan_merge_pr(args)


def _run_merge(fake):
    with _Token():
        return GH.run(_merge_request(), fetch=fake, approved=True)


# --------------------------------------------------------------------------
#   1. The merge: merge commit only, pinned, and refused before the PUT
# --------------------------------------------------------------------------


def t_the_merge_is_merge_commit_only_by_construction():
    check("the one merge method is 'merge'", GH.MERGE_METHOD == "merge",
          GH.MERGE_METHOD)
    r = _merge_request()
    check("the body is exactly merge_method=merge and the pinned sha",
          r.body == {"merge_method": "merge", "sha": HEAD_SHA}, r.body)
    # None of these can widen the body: the planner builds it field by field.
    for extra in ({"merge_method": "squash"}, {"merge_method": "rebase"},
                  {"admin": True}, {"auto_merge": True},
                  {"bypass_required_checks": True},
                  {"merge_method": ["squash", "rebase"]}):
        r = _merge_request(**extra)
        check(f"{sorted(extra)[0]} cannot change the body",
              r.body == {"merge_method": "merge", "sha": HEAD_SHA}, r.body)
    planners = [n for n in dir(GH) if n.startswith("plan_")]
    check("no planner names squash, rebase, admin or auto-merge",
          not [n for n in planners
               if re.search(r"squash|rebase|admin|auto", n)], planners)
    check("the module's never list still names every banned merge verb",
          {"squash_merge", "rebase_merge", "admin_bypass", "auto_merge",
           "bypass_required_checks"} <= GH.NEVER, sorted(GH.NEVER))
    # A full 40-hex sha is required: a short sha or a branch name could move.
    for bad in ("", None, "abc123", HEAD_SHA[:12], "main", HEAD_SHA + "0",
                "HEAD"):
        try:
            GH.plan_merge_pr({"repo": REPO_NAME, "number": PR_NUMBER,
                              "head_sha": bad})
        except GH.GitHubError:
            continue
        check(f"a head sha that is not 40 hex is refused: {bad!r}", False)
        return
    check("a head sha that is not 40 hex is refused", True)


def t_the_merge_card_names_what_is_being_merged_and_the_boundary():
    r = _merge_request()
    text = GH.describe(r)
    for word in (REPO_NAME, "#" + PR_NUMBER, HEAD_SHA, "merge commit",
                 "squash", "rebase", "admin", "auto-merge"):
        check(f"the merge card names {word!r}", word in text, text)
    check("... and the exact request body a person can read",
          json.dumps(r.body, sort_keys=True) in text, text)
    check("... and says a moved head commit means nothing is merged",
          "moved" in text.lower() and "nothing is merged" in text.lower(), text)
    check("... and that every required check is re-checked",
          "required check" in text.lower(), text)
    check("... and it is the merge action, not a read",
          r.action == GH.ACTION_MERGE and r.action in GH.ACTIONS, r.action)
    check("... and it is a PUT to the pull request's own merge address",
          r.steps[0].method == "PUT" and
          r.steps[0].url() == f"{GH.GITHUB_API}/repos/{REPO_NAME}/pulls/"
                              f"{PR_NUMBER}/merge", r.urls())


def t_the_merge_refuses_before_sending_anything():
    """Each refusal: ok false, plain words, and NOT ONE PUT."""
    cases = (
        ("a draft", [("/pulls/", _pr(draft=True))], ("draft",)),
        ("a conflict", [("/pulls/", _pr(mergeable=False,
                                        mergeable_state="dirty"))],
         ("conflict",)),
        ("a blocked state", [("/pulls/", _pr(mergeable=False,
                                             mergeable_state="blocked"))],
         ("blocked",)),
        ("a failing check", [("/pulls/", _pr()),
                             ("/check-runs", _all_green(
                                 [{"id": "1", "name": "rust",
                                   "status": "completed",
                                   "conclusion": "failure"}]))],
         ("required check", "rust")),
        ("a running check", [("/pulls/", _pr()),
                             ("/check-runs", _all_green(
                                 [{"id": "2", "name": "rust",
                                   "status": "in_progress",
                                   "conclusion": None}]))],
         ("running", "rust")),
        ("a missing required check", [("/pulls/", _pr()),
                                      ("/check-runs", (200, json.dumps(
                                          {"check_runs": []})))],
         ("has not reported",)),
        ("an already merged pull request", [("/pulls/", _pr(merged=True))],
         ("already merged",)),
        ("a closed pull request", [("/pulls/", _pr(state="closed"))],
         ("closed",)),
        ("a head commit that moved", [("/pulls/", _pr(head={
            "sha": OTHER_SHA, "ref": BRANCH,
            "repo": {"full_name": REPO_NAME}}))],
         ("moved",)),
    )
    for label, routes, words in cases:
        fake = Routed(routes)
        out = _run_merge(fake)
        check(f"{label}: the merge is refused", out.get("ok") is False, out)
        check(f"{label}: ... in plain words",
              all(w.lower() in out.get("error", "").lower() for w in words),
              out.get("error"))
        check(f"{label}: ... and NOT ONE request that writes",
              fake.writes() == [], fake.methods())
        check(f"{label}: ... and no HTTP code in the words",
              not re.search(r"\b(?:HTTP|40[0-9]|500)\b",
                            out.get("error", "")), out.get("error"))


def t_the_merge_success_sends_the_pinned_body_once():
    fake = Routed([
        ("/pulls/1116/merge", (200, json.dumps(
            {"merged": True, "sha": MERGED_SHA,
             "message": "Pull Request successfully merged"}))),
        ("/pulls/1116", _pr()),
        ("/check-runs", _all_green()),
    ])
    out = _run_merge(fake)
    check("a clean, unmoved, green pull request merges", out.get("ok") is True, out)
    check("... and the answer names the merge commit GitHub sent",
          MERGED_SHA in out.get("text", ""), out.get("text"))
    check("... and says merge commit", "merge commit" in out.get("text", ""),
          out.get("text"))
    puts = [c for c in fake.calls if c["method"] == "PUT"]
    check("exactly ONE PUT is sent", len(puts) == 1, fake.methods())
    check("... to the pull request's own merge address",
          puts and puts[0]["url"] == f"{GH.GITHUB_API}/repos/{REPO_NAME}/pulls/"
                                     f"{PR_NUMBER}/merge", puts and puts[0]["url"])
    check("... with exactly the pinned body, no field added",
          puts and _json(puts[0]["body"]) == {"merge_method": "merge",
                                              "sha": HEAD_SHA},
          puts and _json(puts[0]["body"]))
    check("... and the token is in the header, never in the body",
          TOKEN not in str(puts[0]["body"]) if puts else False,
          puts and puts[0]["body"])
    check("every read before the one write was a GET",
          all(c["method"] == "GET" for c in fake.calls
              if c["method"] != "PUT"), fake.methods())


def t_a_merge_github_does_not_confirm_is_not_reported_as_done():
    fake = Routed([
        ("/pulls/1116/merge", (200, "{}")),
        ("/pulls/1116", _pr()),
        ("/check-runs", _all_green()),
    ])
    out = _run_merge(fake)
    check("a 200 with no merge result is not claimed as merged",
          out.get("ok") is False and "check github.com" in
          out.get("error", "").lower(), out)


# --------------------------------------------------------------------------
#   2. Fix-and-push: isolated folder, own branch, credential denylist
# --------------------------------------------------------------------------


def _scratch():
    """A temporary scratch root, and a restore for GH.SCRATCH_ENV."""
    root = tempfile.mkdtemp(prefix="jarvis-parity-scratch-")
    was = os.environ.get(GH.SCRATCH_ENV)
    os.environ[GH.SCRATCH_ENV] = root

    def restore():
        if was is None:
            os.environ.pop(GH.SCRATCH_ENV, None)
        else:
            os.environ[GH.SCRATCH_ENV] = was
        shutil.rmtree(root, ignore_errors=True)

    return root, restore


def _prepare_fake(checks=None):
    routes = [("/pulls/1116", _pr()),
              ("/check-runs", checks or (200, json.dumps({"check_runs": [
                  {"id": "5", "name": "rust", "status": "completed",
                   "conclusion": "failure",
                   "details_url": f"https://github.com/{REPO_NAME}/actions/"
                                  f"runs/77/job/505"}]}))),
              ("/check-runs/5/annotations", (200, "[]"))]
    return Routed(routes)


def _prepare_git():
    return FakeGit([("clone", (0, "", "")),
                    ("fetch origin", (0, "", "")),
                    ("checkout", (0, "", "")),
                    ("branch -m", (0, "", ""))])


def t_prepare_copies_into_the_scratch_folder_and_pushes_nothing():
    root, restore = _scratch()
    try:
        fake = _prepare_fake()
        log = FakeLog()
        git = _prepare_git()
        r = GH.plan_fix_and_push({"repo": REPO_NAME, "number": PR_NUMBER})
        target = os.path.join(root, GH.scratch_folder_name(REPO_NAME, PR_NUMBER))
        text = GH.describe(r)
        check("the prepare card names the folder it will copy into",
              target in text, text[:400])
        check("... and says nothing is pushed in this stage",
              "nothing is pushed" in text.lower(), text)
        with _Token():
            out = GH.run(r, fetch=fake, approved=True, git=git, log=log)
        check("prepare succeeds", out.get("ok") is True, out)
        check("... and says nothing has been pushed",
              "nothing has been pushed" in out.get("text", "").lower(),
              out.get("text", "")[:400])
        check("... and no git push command was run", git.pushes() == [],
              git.commands())
        check("... and the pull request was cloned and fetched",
              any("clone" in c for c in git.commands()) and
              any("fetch origin" in c for c in git.commands()), git.commands())
        marker = os.path.join(target, ".git", GH.MARKER_NAME)
        check("the folder carries the prepare marker", os.path.isfile(marker),
              marker)
        doc = json.loads(Path(marker).read_text(encoding="utf-8"))
        check("the marker names the pull request, branch and head commit",
              doc.get("repo") == REPO_NAME and doc.get("number") == PR_NUMBER
              and doc.get("head_ref") == BRANCH
              and doc.get("head_sha") == HEAD_SHA, doc)
        check("the marker holds the failing check's name, never the token",
              [c.get("name") for c in doc.get("failing_checks") or []] == ["rust"]
              and TOKEN not in json.dumps(doc), doc)
        check("the answer shows the failing check and the end of its log",
              "rust" in out.get("text", "") and "mismatched types" in
              out.get("text", ""), out.get("text", "")[:800])
        check("... and the token is in no word of the answer or marker",
              TOKEN not in out.get("text", "") and TOKEN not in json.dumps(doc))
        # Re-prepare: the folder already exists, and the SAME marker stays one.
        fake2 = _prepare_fake()
        with _Token():
            again = GH.run(r, fetch=fake2, approved=True, git=_prepare_git(),
                           log=FakeLog())
        check("a re-prepare is refused rather than duplicating the folder",
              again.get("ok") is False and "already exists" in
              again.get("error", "").lower(), again)
        check("... and the marker file is still exactly one",
              len([p for p in Path(target).rglob(GH.MARKER_NAME)]) == 1)
        check("... and the refused re-prepare pushed nothing", fake2.writes() == [],
              fake2.methods())
    finally:
        restore()


def t_prepare_refuses_a_fork_and_a_protected_branch():
    root, restore = _scratch()
    try:
        for label, doc, words in (
                ("a fork", _pr(head={"sha": HEAD_SHA, "ref": BRANCH,
                                     "repo": {"full_name": "someone/Epic-Jarvis"}}),
                 ("fork",)),
                ("a protected branch", _pr(head={"sha": HEAD_SHA, "ref": "main",
                                                 "repo": {"full_name": REPO_NAME}}),
                 ("protected", "main"))):
            r = GH.plan_fix_and_push({"repo": REPO_NAME, "number": PR_NUMBER})
            with _Token():
                out = GH.run(r, fetch=Routed([("/pulls/1116", doc)]),
                             approved=True, git=_prepare_git(), log=FakeLog())
            check(f"{label} is refused before any copy",
                  out.get("ok") is False and
                  all(w in out.get("error", "").lower() for w in words), out)
    finally:
        restore()


def t_the_push_card_shows_checks_files_commits_and_the_exact_command():
    root, restore = _scratch()
    try:
        # Prepare a real folder (its marker + .git created by the module), then
        # plan the push against it with a fake git that answers the local reads.
        fake = _prepare_fake()
        git = _prepare_git()
        r = GH.plan_fix_and_push({"repo": REPO_NAME, "number": PR_NUMBER})
        with _Token():
            GH.run(r, fetch=fake, approved=True, git=git, log=FakeLog())
        target = os.path.join(root, GH.scratch_folder_name(REPO_NAME, PR_NUMBER))
        push_git = FakeGit([
            ("branch --show-current", (0, BRANCH + "\n", "")),
            ("status --porcelain", (0, "", "")),
            ("log --oneline", (0, "abc1234 the fix\n" + "def5678 a test\n", "")),
            ("diff --name-only", (0, "backend/jarvis_github.py\nREADME.md\n", "")),
        ])
        push = GH.plan_fix_and_push({"repo": REPO_NAME, "number": PR_NUMBER,
                                     "stage": "push", "worktree": target},
                                    git=push_git)
        text = GH.describe(push)
        command = f"git push origin HEAD:refs/heads/{BRANCH}"
        check("the push card names the exact command", command in text, text)
        check("... and the commits that will go", "abc1234 the fix" in text
              and "def5678 a test" in text, text)
        check("... and the changed files", "backend/jarvis_github.py" in text
              and "README.md" in text, text)
        check("... and the failing check recorded by prepare",
              "rust" in text and "failure" in text, text)
        check("... and says it is the pull request's own branch",
              BRANCH in text, text)
        check("the push is its own action", push.action == GH.ACTION_FIX_PUSH,
              push.action)
        check("... and the plan pushed nothing itself", push_git.pushes() == [],
              push_git.commands())
    finally:
        restore()


def t_the_push_plan_refuses_every_unsafe_folder():
    root, restore = _scratch()
    try:
        fake = _prepare_fake()
        r = GH.plan_fix_and_push({"repo": REPO_NAME, "number": PR_NUMBER})
        with _Token():
            GH.run(r, fetch=fake, approved=True, git=_prepare_git(), log=FakeLog())
        target = os.path.join(root, GH.scratch_folder_name(REPO_NAME, PR_NUMBER))
        outside = tempfile.mkdtemp(prefix="jarvis-not-scratch-")
        try:
            # Outside the scratch root.
            try:
                GH.plan_fix_and_push({"repo": REPO_NAME, "number": PR_NUMBER,
                                      "stage": "push", "worktree": outside},
                                     git=FakeGit())
                check("a folder outside the scratch root is refused", False)
            except GH.GitHubError as exc:
                check("a folder outside the scratch root is refused",
                      "scratch" in str(exc).lower(), str(exc))
            # The pull request's branch is not the folder's branch.
            try:
                GH.plan_fix_and_push(
                    {"repo": REPO_NAME, "number": PR_NUMBER, "stage": "push",
                     "worktree": target},
                    git=FakeGit([("branch --show-current", (0, "other\n", "")),
                                 ("status --porcelain", (0, "", ""))]))
                check("a folder on another branch is refused", False)
            except GH.GitHubError as exc:
                check("a folder on another branch is refused",
                      "own branch" in str(exc).lower(), str(exc))
            # A dirty tree.
            try:
                GH.plan_fix_and_push(
                    {"repo": REPO_NAME, "number": PR_NUMBER, "stage": "push",
                     "worktree": target},
                    git=FakeGit([("branch --show-current", (0, BRANCH + "\n", "")),
                                 ("status --porcelain", (0, " M x.py\n", ""))]))
                check("an uncommitted tree is refused", False)
            except GH.GitHubError as exc:
                check("an uncommitted tree is refused",
                      "not committed" in str(exc).lower(), str(exc))
            # A credential file among the changed files.
            try:
                GH.plan_fix_and_push(
                    {"repo": REPO_NAME, "number": PR_NUMBER, "stage": "push",
                     "worktree": target},
                    git=FakeGit([("branch --show-current", (0, BRANCH + "\n", "")),
                                 ("status --porcelain", (0, "", "")),
                                 ("log --oneline", (0, "abc the fix\n", "")),
                                 ("diff --name-only", (0, ".env\n", ""))]))
                check("a changed credential file is refused", False)
            except GH.GitHubError as exc:
                check("a changed credential file is refused",
                      "key" in str(exc).lower() or "password" in str(exc).lower()
                      or "token" in str(exc).lower(), str(exc))
            # A protected branch named in the marker, not the live PR.
            try:
                GH._push_arguments({"repo": REPO_NAME, "number": PR_NUMBER,
                                    "worktree": target},
                                   FakeGit([("branch --show-current",
                                             (0, BRANCH + "\n", "")),
                                            ("status --porcelain", (0, "", "")),
                                            ("log --oneline",
                                             (0, "abc the fix\n", "")),
                                            ("diff --name-only",
                                             (0, "x.py\n", ""))]))
                check("the push path is reachable for the prepared folder", True)
            except GH.GitHubError as exc:
                check("the push path is reachable for the prepared folder", False,
                      str(exc))
        finally:
            shutil.rmtree(outside, ignore_errors=True)
        # The banned flags are absent by construction, and the set is real.
        for flag in ("--force", "--force-with-lease", "--delete", "--mirror"):
            check(f"{flag} is a banned git flag",
                  flag in GH.BANNED_GIT_FLAGS, sorted(GH.BANNED_GIT_FLAGS))
        parts = {"repo": REPO_NAME, "number": PR_NUMBER, "worktree": target,
                 "branch": BRANCH, "head_ref": BRANCH, "base": HEAD_SHA}
        why, state = GH._safe_push(parts, target, FakeGit([
            ("branch --show-current", (0, BRANCH + "\n", "")),
            ("status --porcelain", (0, "", "")),
            ("diff --name-only", (0, "backend/x.py\n", ""))]))
        check("the safe-push check never builds a banned command",
              not any(f in " ".join(state.get("command") or [])
                      for f in GH.BANNED_GIT_FLAGS), state)
        check("... and the command it does build is the exact one carded",
              " ".join(state.get("command") or []) ==
              f"push origin HEAD:refs/heads/{BRANCH}", state)
    finally:
        restore()


def t_the_credential_denylist_is_the_project_read_lanes_own():
    import jarvis_project_read as PR
    table = (".env", ".env.local", ".netrc", ".git-credentials", ".npmrc",
             "credentials", "credentials.json", "id_rsa", "id_ed25519",
             "server.pem", "store.pfx", "notes.txt", "app/server.py", "key.py")
    for path in table:
        check(f"the denylist agrees with project_read for {path!r}",
              GH._credential_path(path) == bool(PR._credential(path)),
              (GH._credential_path(path), PR._credential(path)))


def t_the_push_run_rechecks_and_pushes_once():
    root, restore = _scratch()
    try:
        fake = _prepare_fake()
        r = GH.plan_fix_and_push({"repo": REPO_NAME, "number": PR_NUMBER})
        with _Token():
            GH.run(r, fetch=fake, approved=True, git=_prepare_git(), log=FakeLog())
        target = os.path.join(root, GH.scratch_folder_name(REPO_NAME, PR_NUMBER))
        local_git = FakeGit([
            ("branch --show-current", (0, BRANCH + "\n", "")),
            ("status --porcelain", (0, "", "")),
            ("log --oneline", (0, "abc1234 the fix\n", "")),
            ("diff --name-only", (0, "backend/x.py\n", "")),
        ])
        push = GH.plan_fix_and_push({"repo": REPO_NAME, "number": PR_NUMBER,
                                     "stage": "push", "worktree": target},
                                    git=local_git)
        run_git = FakeGit([
            ("branch --show-current", (0, BRANCH + "\n", "")),
            ("status --porcelain", (0, "", "")),
            ("diff --name-only", (0, "backend/x.py\n", "")),
        ])
        live = Routed([("/pulls/1116", _pr())])
        with _Token():
            out = GH.run(push, fetch=live, approved=True, git=run_git)
        check("the push runs", out.get("ok") is True, out)
        check("... exactly one git push", len(run_git.pushes()) == 1,
              run_git.commands())
        check("... with HEAD:refs/heads/<the pull request's branch>",
              run_git.pushes() and run_git.pushes()[0]["args"] ==
              ["push", "origin", f"HEAD:refs/heads/{BRANCH}"],
              run_git.pushes())
        check("... and the token rides in the environment, not the arguments",
              TOKEN not in " ".join(run_git.pushes()[0]["args"]) if
              run_git.pushes() else False)
        check("... and the one ref read was a GET", live.writes() == [],
              live.methods())
        # The live pull request moved: refused before the push.
        moved = Routed([("/pulls/1116", _pr(head={"sha": HEAD_SHA,
                                                  "ref": "other-branch",
                                                  "repo": {"full_name": REPO_NAME}}))])
        run_git2 = FakeGit([("branch --show-current", (0, BRANCH + "\n", ""))])
        with _Token():
            out2 = GH.run(push, fetch=moved, approved=True, git=run_git2)
        check("a moved pull request branch refuses the push",
              out2.get("ok") is False and run_git2.pushes() == [],
              (out2, run_git2.commands()))
    finally:
        restore()


# --------------------------------------------------------------------------
#   3. The read-only cockpit
# --------------------------------------------------------------------------


def t_the_cockpit_classifies_and_reads_only():
    prs = [{"number": n, "title": f"PR {n}"} for n in range(1, 6)]
    shas = {n: f"{n:040x}" for n in range(1, 6)}
    routes = [("/pulls?", (200, json.dumps(prs))),
              ("/pulls/5", _pr(head={"sha": shas[5], "ref": "f5",
                                     "repo": {"full_name": REPO_NAME}})),
              ("/pulls/4", _pr(head={"sha": shas[4], "ref": "f4",
                                     "repo": {"full_name": REPO_NAME}})),
              ("/pulls/3", _pr(head={"sha": shas[3], "ref": "f3",
                                     "repo": {"full_name": REPO_NAME}})),
              ("/pulls/2", _pr(head={"sha": shas[2], "ref": "f2",
                                     "repo": {"full_name": REPO_NAME}},
                               mergeable=False, mergeable_state="dirty")),
              ("/pulls/1", _pr(draft=True,
                               head={"sha": shas[1], "ref": "f1",
                                     "repo": {"full_name": REPO_NAME}}))]
    for n in range(1, 6):
        if n == 3:
            routes.append((f"/commits/{shas[n]}/check-runs", _all_green(
                [{"id": "9", "name": "rust", "status": "in_progress",
                  "conclusion": None}])))
        elif n == 4:
            routes.append((f"/commits/{shas[n]}/check-runs", _all_green(
                [{"id": "8", "name": "rust", "status": "completed",
                  "conclusion": "failure"}])))
        else:
            routes.append((f"/commits/{shas[n]}/check-runs", _all_green()))
    fake = Routed(routes)
    r = GH.plan_scan_prs({"repo": REPO_NAME}) if hasattr(GH, "plan_scan_prs") \
        else GH.plan_pr_scan({"repo": REPO_NAME})
    with _Token():
        out = GH.run(r, fetch=fake, approved=True)
    text = out.get("text", "")
    check("the cockpit answers", out.get("ok") is True, out)
    for number, word in ((1, "draft"), (2, "conflicted"), (3, "running"),
                         (4, "blocked"), (5, "merge-ready")):
        check(f"#{number} is classified {word}",
              f"#{number} " in text and f": {word}" in text, text)
    check("a running check is named", "rust" in text, text)
    check("a failing required check is named", "rust finished as failure" in text,
          text)
    check("the cockpit caps at ten pull requests", GH.MAX_PRS == 10, GH.MAX_PRS)
    check("every cockpit request is a GET", set(fake.methods()) == {"GET"},
          fake.methods())
    check("the cockpit writes nothing - no body at all",
          all(c["body"] is None for c in fake.calls),
          [c["body"] for c in fake.calls])
    check("the token is on every read and in no word",
          all(c["headers"].get("Authorization") == f"Bearer {TOKEN}"
              for c in fake.calls) and TOKEN not in text)


def t_a_refused_cockpit_read_is_a_plain_sentence():
    fake = Routed([("/pulls?", (403, "{}"))])
    with _Token():
        out = GH.run(GH.plan_scan_prs({"repo": REPO_NAME}), fetch=fake,
                     approved=True)
    check("a refused cockpit read is a plain sentence, not a crash",
          out.get("ok") is False and "no" in out.get("error", "").lower(), out)
    check("... with no HTTP code in it",
          not re.search(r"\b(?:HTTP|40[0-9]|500)\b", out.get("error", "")), out)


# --------------------------------------------------------------------------
#   4. The job log: a 302 that is read, never followed
# --------------------------------------------------------------------------


def t_the_signed_log_address_is_allowlisted_and_gets_no_token():
    for good in ("https://api.github.com/x", "https://github.com/x",
                 "https://objects.githubusercontent.com/x?y=1",
                 "https://github-production-user-asset-1.githubusercontent.com/x"):
        check(f"an https GitHub host is allowed: {good}",
              GH._log_url_allowed(good))
    for bad in ("http://objects.githubusercontent.com/x",
                "https://evil.example/x", "https://githubusercontent.com.evil/x",
                "https://notgithubusercontent.com/x", "", "ftp://github.com/x"):
        check(f"another host or scheme is refused: {bad}",
              not GH._log_url_allowed(bad))
    log = FakeLog()
    with _Token():
        body, why = GH._job_log(
            f"{GH.GITHUB_API}/repos/{REPO_NAME}/actions/jobs/5/logs", TOKEN,
            open_url=log)
    check("a signed log address is fetched", why == "" and "mismatched" in body,
          (body, why))
    check("the FIRST request sends the token to api.github.com",
          log.calls and log.calls[0]["headers"].get("Authorization") ==
          f"Bearer {TOKEN}", log.calls)
    check("the signed fetch sends NO Authorization header",
          len(log.calls) == 2 and "Authorization" not in log.calls[1]["headers"],
          log.calls)
    check("... and the token appears in no returned word",
          TOKEN not in body and TOKEN not in why)
    evil = FakeLog(location="https://evil.example/signed")
    with _Token():
        body, why = GH._job_log(
            f"{GH.GITHUB_API}/repos/{REPO_NAME}/actions/jobs/5/logs", TOKEN,
            open_url=evil)
    check("a redirect to another host is refused", body == "" and why, (body, why))
    check("... and that host is never contacted", len(evil.calls) == 1,
          evil.calls)
    check("... and the refusal names the hosts it will not fetch",
          "will not fetch" in why, why)


# --------------------------------------------------------------------------
#   5. Awareness: one inventory, wired and honest
# --------------------------------------------------------------------------


def _toml_tiers():
    try:
        import tomllib
    except ImportError:                      # Python < 3.11
        import tomli as tomllib              # type: ignore
    out = []
    for path in TOMLS:
        out.append((path, tomllib.loads(path.read_text(encoding="utf-8"))
                    ["autonomy"]["tiers"]))
    return out


def t_the_capability_inventory_is_the_whole_wired_surface():
    caps = GH.CAPABILITIES
    check("there is ONE capability entry per GitHub tool",
          {c["tool"] for c in caps} == set(AG.GITHUB_TOOLS),
          sorted(c["tool"] for c in caps))
    check("every read tool is a read entry",
          {c["tool"] for c in caps if c["kind"] == "read"} ==
          set(AG.GITHUB_READ_TOOLS))
    check("every action tool is a write entry",
          {c["tool"] for c in caps if c["kind"] == "write"} ==
          set(AG.GITHUB_ACTION_TOOLS))
    check("every write entry's gate is a real closed-set action",
          {c["gate"] for c in caps if c["kind"] == "write"} == set(GH.ACTIONS),
          sorted(c["gate"] for c in caps if c["kind"] == "write"))
    check("every read entry is decided under github_inspect",
          {c["gate"] for c in caps if c["kind"] == "read"} == {GH.ACTION_INSPECT})
    for c in caps:
        check(f"{c['tool']}: the entry says what it does, its card and its limit",
              all(str(c.get(k) or "").strip()
                  for k in ("words", "card", "limit", "gate")), c)
    # Every capability really is wired: its tool's own prepare() builds a
    # Request under the gate action the entry names.
    args = {
        "github_list": {"scope": "pulls", "repo": REPO_NAME},
        "github_read_file": {"repo": REPO_NAME, "path": "README.md"},
        "github_ci_status": {"repo": REPO_NAME, "branch": "main"},
        "github_pr_scan": {"repo": REPO_NAME},
        "github_comment": {"repo": REPO_NAME, "number": PR_NUMBER,
                           "body": "Thanks - this is fixed."},
        "github_open_issue": {"repo": REPO_NAME, "title": "One bug"},
        "github_rerun_workflow": {"repo": REPO_NAME, "run_id": "123"},
        "github_create_repo": {"name": "One-Repo"},
        "github_merge_pr": {"repo": REPO_NAME, "number": PR_NUMBER,
                            "head_sha": HEAD_SHA},
        "github_fix_and_push": {"repo": REPO_NAME, "number": PR_NUMBER},
    }
    gate = {c["tool"]: c["gate"] for c in caps}
    for tool, tool_args in args.items():
        with _Token():
            r, text = AG.TOOLS[tool].prepare(dict(tool_args))
        check(f"{tool}: prepare() builds a Request under {gate[tool]}",
              getattr(r, "action", None) == gate[tool], getattr(r, "action", None))
        check(f"{tool}: ... and the card is not empty", bool(str(text).strip()))


def t_the_awareness_text_answers_what_can_you_do_with_github():
    text = GH.capabilities_text()
    line = GH.capabilities_line()
    checks = {
        "the four reads": ("github_list", "github_read_file", "github_ci_status",
                           "github_pr_scan"),
        "the six carded writes": ("github_comment", "github_open_issue",
                                  "github_rerun_workflow", "github_create_repo",
                                  "github_merge_pr", "github_fix_and_push"),
    }
    for label, names in checks.items():
        missing = [n for n in names if n not in text]
        check(f"the text names {label}", not missing, missing)
    small = {
        "the token is in Windows Credential Manager": "Credential Manager",
        "the token is never printed": "never printed",
        "api.github.com is the only host": "api.github.com",
        "the signed log fetch strips Authorization": "Authorization header",
        "the log host allowlist": "githubusercontent.com",
        "the cockpit is read-only": "read-only",
        "merge is merge-commit only": "merge-commit only",
        "the merge is pinned to the head commit": "pinned to the head commit",
        "fix-push runs in a scratch folder": "scratch root",
        "the push is only to the PR's own branch":
            "pull request's own branch",
        "the protected branches": "release/*",
        "the force/delete/mirror bans": "force",
        "the credential denylist": "credential denylist",
        "default off under What asks first": "What asks first",
        "the stale event stream holds Approve": "stale",
        "the never list": GH.NEVER_WORDS[:40],
    }
    for label, needle in small.items():
        check(f"the full text covers {label}", needle in text, needle)
    check("the one-breath line still names the token handling and the never list",
          "Credential Manager" in line and "never" in line.lower(), line)
    check("the agent's tool-description text is the module's own line",
          AG.GITHUB_CAPABILITIES_WORDS == line, AG.GITHUB_CAPABILITIES_WORDS[:120])
    for tool in ("github_pr_scan", "github_merge_pr", "github_fix_and_push"):
        check(f"the model reads the capability line on {tool}",
              line and line in AG.TOOLS[tool].description,
              AG.TOOLS[tool].description[:120])
    check("no capability text names an action that is not wired",
          not [c for c in GH.CAPABILITIES
               if c["tool"] not in AG.TOOLS])
    check("the never list is the plain sentence, and it is complete",
          all(w in GH.NEVER_WORDS for w in
              ("force-push", "squash", "bypass required", "main",
               "delete/close", "approval card")), GH.NEVER_WORDS)


def t_every_write_is_ask_and_in_needs_a_person():
    tiers = _toml_tiers()
    for path, table in tiers:
        for action in GH.ACTIONS:
            check(f"{path.name}: {action} ships as ask",
                  table.get(action) == "ask", table.get(action))
    for tool in AG.GITHUB_ACTION_TOOLS:
        check(f"{tool} is in NEEDS_A_PERSON", tool in AG.NEEDS_A_PERSON)
    for tool in AG.GITHUB_READ_TOOLS:
        check(f"{tool} asks too, because a read sends the token",
              tool in AG.NEEDS_A_PERSON)
    check("the merge and the push are never auto-approvable",
          all(AG.TOOLS[t].name in AG.NEEDS_A_PERSON
              for t in ("github_merge_pr", "github_fix_and_push")))


# --------------------------------------------------------------------------
#   6. Safety: no write without a card, and a stale stream blocks the yes
# --------------------------------------------------------------------------


def t_no_write_is_sent_without_a_person_saying_yes():
    checks = (
        ("the merge", _merge_request()),
        ("the push", GH.plan_fix_and_push({"repo": REPO_NAME,
                                           "number": PR_NUMBER,
                                           "stage": "prepare"})),
    )
    for label, r in checks:
        fake = Routed([])
        with _Token():
            out = GH.run(r, fetch=fake, approved=False)
        check(f"{label}: an unapproved run is refused",
              out.get("ok") is False and
              out.get("error") == "not approved; nothing was sent", out)
        check(f"{label}: ... and not one request was made", fake.calls == [],
              fake.calls)
    # The approval check happens before the token is even read: a module that
    # can reach the network is not one call away from acting by accident.
    src = (HERE / "jarvis_github.py").read_text(encoding="utf-8")
    body = src.split("def run(", 1)[1].split("def ", 1)[0]
    check("run() refuses an unapproved request before it builds the token",
          body.find("if not approved") < body.find("_need_token"), body[:400])


def t_a_stale_event_stream_holds_the_yes():
    # The desktop's own command is the one place every approval is sent, and
    # its stale rule is `stale_answer_refusal(approved, stale)`: an APPROVE on
    # a stale link is refused (Deny is never held). Pinned from the source, not
    # assumed, because this suite cannot drive the Rust command.
    if not COMMANDS_RS.is_file():
        skip("the desktop's commands.rs is not in this checkout, so the "
             "stale-approve rule cannot be read here")
        return
    rust = COMMANDS_RS.read_text(encoding="utf-8")
    check("the desktop defines the stale-approve rule",
          re.search(r"fn stale_answer_refusal\(approved: bool, stale: bool\)",
                    rust) is not None)
    check("... and every approval goes through it",
          "if let Some(said) = stale_answer_refusal(" in rust)
    check("... with a sentence that says the approve was held",
          "STALE_APPROVE_HELD" in rust)
    check("... and Deny is NOT held (only an APPROVE on a stale link)",
          re.search(r"fn stale_answer_refusal\(approved: bool, stale: bool\)"
                    r"[\s\S]{0,400}?approved\s*&&\s*stale", rust) is not None)
    # The two new writes have no path around that card: each is in the
    # never-loosened set, each is its own "ask" action, and each run() needs
    # approved=True (proved above).
    check("the merge cannot bypass the card",
          "github_merge_pr" in AG.NEEDS_A_PERSON and
          AG.TOOLS["github_merge_pr"].name == "github_merge_pr")
    check("the push cannot bypass the card",
          "github_fix_and_push" in AG.NEEDS_A_PERSON and
          AG.TOOLS["github_fix_and_push"].name == "github_fix_and_push")


def t_the_two_shipped_tomls_are_one_file_and_say_the_small_details():
    a, b = TOMLS
    check("backend/rebuilt's framework file and the base's are byte-identical",
          a.read_bytes() == b.read_bytes())
    text = a.read_text(encoding="utf-8")
    for needle in ("Windows Credential Manager", "api.github.com",
                   "githubusercontent.com", "event stream is stale",
                   "github_merge_pr", "github_fix_and_push"):
        check(f"the shipped Settings copy says {needle!r}", needle in text, needle)


# --------------------------------------------------------------------------
#   The run
# --------------------------------------------------------------------------


if __name__ == "__main__":
    print(f"  file  {HERE / 'jarvis_github.py'}")
    print(f"  file  {HERE / 'jarvis_agent.py'}")
    with NoSocket():
        for fn in (t_the_merge_is_merge_commit_only_by_construction,
                   t_the_merge_card_names_what_is_being_merged_and_the_boundary,
                   t_the_merge_refuses_before_sending_anything,
                   t_the_merge_success_sends_the_pinned_body_once,
                   t_a_merge_github_does_not_confirm_is_not_reported_as_done,
                   t_prepare_copies_into_the_scratch_folder_and_pushes_nothing,
                   t_prepare_refuses_a_fork_and_a_protected_branch,
                   t_the_push_card_shows_checks_files_commits_and_the_exact_command,
                   t_the_push_plan_refuses_every_unsafe_folder,
                   t_the_credential_denylist_is_the_project_read_lanes_own,
                   t_the_push_run_rechecks_and_pushes_once,
                   t_the_cockpit_classifies_and_reads_only,
                   t_a_refused_cockpit_read_is_a_plain_sentence,
                   t_the_signed_log_address_is_allowlisted_and_gets_no_token,
                   t_the_capability_inventory_is_the_whole_wired_surface,
                   t_the_awareness_text_answers_what_can_you_do_with_github,
                   t_every_write_is_ask_and_in_needs_a_person,
                   t_no_write_is_sent_without_a_person_saying_yes,
                   t_a_stale_event_stream_holds_the_yes,
                   t_the_two_shipped_tomls_are_one_file_and_say_the_small_details):
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
