"""test_github_tools.py - the ten GitHub tools, their six gate actions, and the patch.

    python3 test_github_tools.py

WHAT THIS SUITE IS FOR

The owner's decision of 2026-11-03: Jarvis may READ his GitHub (repositories,
open pull requests, issues, CI status, one file) and take three small ACTIONS
(comment, open an issue, re-run a workflow) - each action behind its own
approval card. The owner's decision of 2026-11-10 (Gemini ruling Q1, "Everything
at once") added a read-only PR cockpit, a merge-commit-only merge pinned to the
head sha the card showed, and a fix-and-push into an isolated scratch folder.

`backend/jarvis_github.py` holds the half that talks to api.github.com and (for
the fix stage) to git; `backend/jarvis_agent.py` holds the ten tools;
`backend/github-tools.patch` gives the gate the six actions. This suite proves
the promises each of those makes, and it proves the patch really applies - with
NO network and NO real token anywhere, and NO real git process:

  1. Only api.github.com. Every address every planner can build starts with
     the module's own constant, and no argument the model can write becomes a
     host. A redirect is refused rather than followed, so the token cannot be
     handed to whoever answered (`_RefuseRedirect`). The ONE address that is
     fetched without the token is a job log's signed redirect, and only on an
     https host GitHub owns.
  2. The read scopes are a CLOSED set. A repository, a path, a branch, a number
     or a 40-hex commit the model wrote is checked before it goes into a URL or
     a git command.
  3. The token is never printed, and never in a process command line. It travels
     in the Authorization header, and for BOTH git steps (the prepare clone and
     the push) in git's own environment config - never in the clone URL, never in
     an argument, and never in the folder on disk.
  4. No token, no card. The ten planners answer "connect GitHub" in plain
     words and `_one_call` returns before the gate.
  5. Each action is ONE card that names exactly what it will do - and the merge
     card names the pull request's number, TITLE and TARGET BRANCH, the exact
     40-hex head commit, its github.com address to look at, that the method is
     one merge commit, the seven required checks and that
     squash/rebase/admin/auto-merge are impossible. The PUT body is still pinned
     by its own test to exactly {"merge_method", "sha"}.
  6. Failures are plain sentences. A refused token, a rate limit, a moved head
     commit, a 409 (moved/conflict), a 405 (not mergeable now), a required merge
     queue and a missing repository are said in words, with no HTTP code.
  7. Nothing from email, files, credentials or saved memory is ever sent.
  8. Merge and PR-branch push exist ONLY behind their own cards. The absolute
     bans still hold: force-push, squash-merge, rebase-merge, admin bypass,
     auto-merge, bypassing required checks, pushing to main/master/release/*,
     deleting or closing a repository or branch - and, from the Q3/Q4 rulings,
     approving a PR, closing an issue, editing a comment, dispatching a workflow
     and gists.
  9. The patch: it reverses out of the published base and applies forward
     again byte for byte, it sits between `web-search-grant.patch` and the
     last writer of `jarvis_gate.py` (`unknown-risk-approvable.patch`) so
     neither of those patches' reversals is disturbed, every action ships as
     "ask", and every table a new tool has to join has it.

THE FAKE HTTP LAYER

Every test drives the module through `run(..., fetch=<fake>)` (and, for the fix
stage, `git=<fake>` and `log=<fake>`), which are the seams the real network and
the real process sit behind. Nothing here opens a socket and nothing here runs
git: `NoSocket` replaces `socket.socket` for the whole run, and every git call
goes through `FakeGit`.

Standard library only.
"""
from __future__ import annotations

import ast
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import urllib.error
from pathlib import Path

# A temp config dir BEFORE any backend import: jarvis_gate opens an approval
# queue at import time, and this suite must not read or write the owner's own.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-github-tools-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
# No push: the topic is unset, so nothing can post to ntfy.sh.
os.environ["JARVIS_NTFY_TOPIC"] = ""

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

import jarvis_github as GH  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_card_words as CW  # noqa: E402

GATE_BASE = REPO / "jarvis-backend" / "jarvis_gate.py"
PATCH = HERE / "github-tools.patch"
PS1 = REPO / "scripts" / "apply-patches.ps1"
TOMLS = (HERE / "rebuilt" / "jarvis-framework.toml",
         REPO / "jarvis-backend" / "jarvis-framework.toml")

#: A token distinctive enough that finding it anywhere is a leak, and shaped
#: like the real thing so nothing can pass by being "not token-like".
TOKEN = "ghp_TESTONLYnotarealtoken0000000000000000"

READ_TOOLS = ("github_list", "github_read_file", "github_ci_status",
              # 2026-11-10: the read-only PR cockpit.
              "github_pr_scan")
#: The four actions whose card is ONE POST of something the owner wrote.
POST_ACTION_TOOLS = ("github_comment", "github_open_issue", "github_rerun_workflow",
                     # 2026-11-09: one new, empty repository on the owner's own account.
                     "github_create_repo")
ACTION_TOOLS = POST_ACTION_TOOLS + (
    # 2026-11-10: merge-commit only, pinned to the head sha the card named...
    "github_merge_pr",
    # ... and fix-and-push: a GET/copy card, then a SECOND push card.
    "github_fix_and_push")
ALL_TOOLS = READ_TOOLS + ACTION_TOOLS

#: The commit the merge tests pin, and the one GitHub reports back afterwards.
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
MERGED_SHA = "fedcba9876543210fedcba9876543210fedcba98"

#: The arguments each tool needs, so one table drives every test below.
ARGS = {
    "github_list": {"scope": "pulls", "repo": "darknight11ish/Epic-Jarvis"},
    "github_read_file": {"repo": "darknight11ish/Epic-Jarvis", "path": "README.md"},
    "github_ci_status": {"repo": "darknight11ish/Epic-Jarvis", "branch": "main"},
    "github_pr_scan": {"repo": "darknight11ish/Epic-Jarvis"},
    "github_comment": {"repo": "darknight11ish/Epic-Jarvis", "number": "1116",
                       "body": "Thanks - the rebase is done and the checks are green."},
    "github_open_issue": {"repo": "darknight11ish/Epic-Jarvis",
                          "title": "The tray icon stays after a restart",
                          "body": "Seen twice on 2026-11-03."},
    "github_rerun_workflow": {"repo": "darknight11ish/Epic-Jarvis", "run_id": "123456"},
    "github_create_repo": {"name": "Fitness-Band",
                           "description": "A band that counts steps.",
                           "private": True},
    "github_merge_pr": {"repo": "darknight11ish/Epic-Jarvis", "number": "1116",
                        "head_sha": HEAD_SHA, "title": "Fix the tray icon",
                        "base_ref": "main"},
    "github_fix_and_push": {"repo": "darknight11ish/Epic-Jarvis", "number": "1116"},
}

#: What each action's card must name, and nothing else has to.
MUST_NAME = {
    "github_comment": ("darknight11ish/Epic-Jarvis", "1116",
                       "Thanks - the rebase is done and the checks are green."),
    "github_open_issue": ("darknight11ish/Epic-Jarvis",
                          "The tray icon stays after a restart",
                          "Seen twice on 2026-11-03."),
    "github_rerun_workflow": ("darknight11ish/Epic-Jarvis", "123456"),
    "github_create_repo": ("Fitness-Band", "Private: yes",
                           "A band that counts steps."),
    "github_merge_pr": ("darknight11ish/Epic-Jarvis", "1116", HEAD_SHA,
                        "https://github.com/darknight11ish/Epic-Jarvis/pull/1116",
                        "Fix the tray icon", "Target branch: main",
                        "It will be merged at this exact commit",
                        "one merge commit", "squash", "rebase", "admin",
                        "auto-merge",
                        "GitHub is told: merge, and only merge, at this exact "
                        "commit",
                        "rust, frontend, backend, backend-windows, "
                        "credential-manager, powershell-5, phone-unit-tests"),
    "github_fix_and_push": ("darknight11ish/Epic-Jarvis", "1116", "prepare",
                            "nothing is pushed in this stage"),
}

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass (BLOCKED is never a pass, CLAUDE.md)."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The fake HTTP layer, and the socket ban
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


class Fake:
    """A stand-in for `_default_fetch`: records every call, answers by rule."""

    def __init__(self, status=200, body="[]"):
        self.status = status
        self.body = body
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}),
                           "body": body, "timeout": timeout})
        return self.status, self.body

    def urls(self):
        return [c["url"] for c in self.calls]

    def bodies(self):
        return [c["body"] for c in self.calls]

    def methods(self):
        return [c["method"] for c in self.calls]


class Routed(Fake):
    """A `Fake` that answers by URL substring, first match wins.

    `routes` is a sequence of `(needle, answer)` pairs, where an answer is either
    `(status, body)` or a callable taking the call and returning `(status, body)`.
    An address no route matches is a 404, which is what GitHub answers too.
    """

    def __init__(self, routes):
        super().__init__()
        self.routes = list(routes)

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}),
                           "body": body, "timeout": timeout})
        for needle, answer in self.routes:
            if needle in url:
                if callable(answer):
                    return answer(self.calls[-1])
                return answer
        return 404, "{}"

    def writes(self):
        return [c for c in self.calls if c["method"] not in ("GET", "HEAD")]


class FakeGit:
    """A stand-in for `_default_git`: records every command, answers by rule.

    Nothing here starts a process. `answers` is `(needle, (code, out, err))`,
    matched against the joined arguments, first match wins; anything else is a
    successful empty answer, which is what most read-only git commands give.
    """

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
    """A stand-in for the job-log opener: `(status, text, headers)`.

    GitHub answers the log request with a 302 whose `Location` is the signed
    address; this fake can hand back any `Location`, so the refusal can be driven
    without a network.
    """

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


def _all_green_runs(extra=None, conclusion="success"):
    """The check-runs answer with every REQUIRED check green (or not)."""
    runs = [{"id": str(900 + i), "name": name, "status": "completed",
             "conclusion": conclusion,
             "details_url": "https://github.com/darknight11ish/Epic-Jarvis/"
                            f"actions/runs/77/job/{500 + i}"}
            for i, name in enumerate(GH.REQUIRED_CHECKS)]
    runs.extend(extra or [])
    return json.dumps({"total_count": len(runs), "check_runs": runs})


def _pr_doc(**over):
    """One pull request as GitHub answers `GET /repos/{repo}/pulls/{n}`."""
    doc = {"number": 1116, "title": "Fix the tray icon", "draft": False,
           "state": "open", "mergeable": True, "mergeable_state": "clean",
           "head": {"sha": HEAD_SHA, "ref": "feature/tray-icon",
                    "repo": {"full_name": "darknight11ish/Epic-Jarvis"}},
           "base": {"ref": "main"}}
    doc.update(over)
    return json.dumps(doc)


def _json_object(raw):
    return json.loads(raw.decode("utf-8"))



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


def _card(tool):
    """(the Request, the card text) one tool's prepare() gives, with a token."""
    with _Token():
        return AG.TOOLS[tool].prepare(dict(ARGS[tool]))


def _run(tool, fetch, *, approved=True, args=None):
    """run() one tool's request with the saved token in place for the CALL.

    `_card` restores the token when it returns, so a test that ran the request
    outside another `_Token()` block would meet "connect GitHub first" instead
    of the fake server - which is exactly the mistake this helper prevents.
    """
    with _Token():
        r = AG.TOOLS[tool].prepare(dict(args or ARGS[tool]))[0]
        return r, GH.run(r, fetch=fetch, approved=approved)


def _run_request(r, fetch, *, approved=True, **kwargs):
    """`GH.run` for one already-built request, with the fake token in place.

    A test that builds the Request itself (a plan stage, a modified request)
    must still run it under `_Token`: otherwise the module reads the owner's REAL
    saved token - the fake server never sees it, but a suite must not read a
    real credential at all.
    """
    with _Token():
        return GH.run(r, fetch=fetch, approved=approved, **kwargs)


def _json_body(call):
    raw = call["body"]
    if raw is None:
        return None
    return json.loads(raw.decode("utf-8"))


def _file_envelope(text: str, *, encoding: str = "base64") -> str:
    """The body GitHub REALLY sends for one file: the envelope, not its text.

    `GET /repos/{owner}/{repo}/contents/{path}` answers with
    `{"encoding": "base64", "content": "<base64>"}` (DEF-042, the shape the
    suite's fake used to get wrong by returning the plain text), a JSON list
    for a directory, and `"encoding": "none"` with no content for a file too
    big for this read or a link rather than a file.
    """
    if encoding == "base64":
        content = base64.b64encode(text.encode("utf-8")).decode("ascii")
    else:
        content = ""
    return json.dumps({"type": "file", "encoding": encoding, "content": content,
                       "name": "README.md", "path": "README.md", "size": len(text)})


# --------------------------------------------------------------------------
#   1. Only api.github.com, and a redirect is refused
# --------------------------------------------------------------------------


def t_only_api_github_com():
    host = GH.GITHUB_API
    made = []
    for tool in ALL_TOOLS:
        r, _text = _card(tool)
        made.extend(r.urls())
    made.extend(GH.plan_ci({"repo": "o/r", "pr": "7"}).urls())
    made.extend(GH.plan_read_file({"repo": "o/r", "path": "a/b.md"}).urls())
    made.extend(GH.plan_list({"scope": "repos"}).urls())
    made.extend(GH.plan_create_repo({"name": "Fitness-Band"}).urls())
    made.extend(GH.plan_scan_prs({"repo": "o/r"}).urls())
    made.extend(GH.plan_merge_pr({"repo": "o/r", "number": "7",
                                  "head_sha": "a" * 40, "title": "One fix",
                                  "base_ref": "main"}).urls())
    made.extend(GH.plan_fix_and_push({"repo": "o/r", "number": "7"}).urls())
    check("the planners built some addresses at all", len(made) >= 8, len(made))
    bad = [u for u in made if not u.startswith(host + "/")]
    check("every address any planner can build is under api.github.com", not bad, bad)
    hosts = {u.split("/")[2] for u in made}
    check("and that is the ONLY host in the module", hosts == {"api.github.com"}, hosts)

    # The model cannot hand the module a host: `url` is not an argument any
    # planner reads, so a call that carries one builds the ordinary address.
    r = GH.plan_list({"scope": "repos", "url": "https://evil.example/steal"})
    check("a `url` argument is ignored, never used as the address",
          r.urls() == (host + "/user/repos?per_page=20&sort=updated",), r.urls())
    r = GH.plan_read_file({"repo": "o/r", "path": "a.md",
                           "url": "http://127.0.0.1:1/x"})
    check("... and so is one on the file read",
          r.urls()[0].startswith(host + "/"), r.urls())

    # The merge cannot be pointed at another host or another method either: its
    # one step is a PUT to the pull request's own fixed path.
    r = GH.plan_merge_pr({"repo": "o/r", "number": "7", "head_sha": "a" * 40,
                          "title": "One fix", "base_ref": "main",
                          "url": "https://evil.example/x", "merge_method": "squash"})
    check("a merge ignores a `url` and a `merge_method` the model adds",
          r.urls() == (host + "/repos/o/r/pulls/7/merge",)
          and r.steps[0].method == "PUT"
          and r.body == {"merge_method": "merge", "sha": "a" * 40},
          (r.urls(), r.steps[0].method, r.body))

    # The fix stage's only addresses are the PR and its checks; git's remote is
    # github.com because it is a CLONE of the repository, not an API call.
    fix = GH.plan_fix_and_push({"repo": "o/r", "number": "7"})
    check("the prepare card's one address is the pull request read",
          fix.urls() == (host + "/repos/o/r/pulls/7",), fix.urls())


def t_a_redirect_is_refused():
    handler = GH._RefuseRedirect()
    try:
        handler.redirect_request(
            type("R", (), {"full_url": "https://api.github.com/user"})(),
            None, 302, "Found", {}, "https://evil.example/x")
    except urllib.error.HTTPError as exc:
        check("a redirect raises instead of following it", True)
        check("... and the sentence says why", "token" in str(exc), str(exc))
    except Exception as exc:                       # noqa: BLE001
        check("a redirect raises instead of following it", False, repr(exc))
    else:
        check("a redirect raises instead of following it", False, "it followed it")


# --------------------------------------------------------------------------
#   2. The read scopes are a closed set, and a name is checked before it is used
# --------------------------------------------------------------------------


def t_the_scopes_are_closed_and_names_are_checked():
    check("the scopes are exactly the four the owner named",
          GH.SCOPES == ("repos", "pulls", "issues", "runs"), GH.SCOPES)
    # An EMPTY scope is not a refusal: it is the documented default ("repos"),
    # the same as leaving the argument out.
    check("an empty scope means the documented default, not an error",
          GH.plan_list({"scope": "", "repo": "o/r"}).urls()
          == (GH.GITHUB_API + "/user/repos?per_page=20&sort=updated",),
          GH.plan_list({"scope": "", "repo": "o/r"}).urls())
    for bad in ("all", "everything", "orgs", "PULLS please", "https://evil.example"):
        try:
            GH.plan_list({"scope": bad, "repo": "o/r"})
        except GH.GitHubError:
            continue
        check(f"a scope outside the four is refused: {bad!r}", False)
        return
    check("a scope outside the four is refused", True)

    refused = 0
    for bad_repo in ("../../etc/passwd", "o/r?x=1", "o/r#frag", "o", "a/b/c",
                     "o/r\nX: y", "o\\r", ""):
        try:
            GH.plan_list({"scope": "pulls", "repo": bad_repo})
        except GH.GitHubError:
            refused += 1
    check("every repository name that is not owner/name is refused",
          refused == 8, refused)

    for bad_path in ("../secrets.txt", "/a/../../b", "a?x=1", "a#b", ""):
        try:
            GH.plan_read_file({"repo": "o/r", "path": bad_path})
        except GH.GitHubError:
            continue
        check(f"a path that is not a path inside the repo is refused: {bad_path!r}",
              False)
        return
    check("a path that is not a path inside the repo is refused", True)

    for bad_number in ("abc", "1; rm", "../1", ""):
        try:
            GH.plan_comment({"repo": "o/r", "number": bad_number, "body": "hi"})
        except GH.GitHubError:
            continue
        check(f"a number that is not a number is refused: {bad_number!r}", False)
        return
    check("a number that is not a number is refused", True)

    # A path is percent-encoded rather than pasted, so a space is not a break.
    r = GH.plan_read_file({"repo": "o/r", "path": "docs/a b.md"})
    check("a space in a path is encoded, not left to break the URL",
          "a%20b.md" in r.urls()[0], r.urls())


# --------------------------------------------------------------------------
#   3. The token is never printed
# --------------------------------------------------------------------------


def t_the_token_never_appears_in_any_output():
    shown = []
    for tool in ALL_TOOLS:
        r, text = _card(tool)
        shown.extend([text, json.dumps(r.body or {}), str(r.urls())])
    fake = Fake(200, json.dumps([{"full_name": "o/r", "private": True},
                                 {"full_name": "o/r2"}]))
    for tool in ALL_TOOLS:
        _r, out = _run(tool, fake)
        shown.append(json.dumps(out))
    leaked = [s for s in shown if TOKEN in s]
    check("the token is in none of the cards, bodies, addresses or results",
          not leaked, leaked[:2])

    # CONTROL: it really was sent, in the header, so the check above is not
    # passing because the module forgot to authenticate at all.
    sent = [c for c in fake.calls if c["headers"].get("Authorization") == f"Bearer {TOKEN}"]
    check("CONTROL: it was sent, in the Authorization header",
          len(sent) == len(fake.calls) and bool(sent),
          (len(sent), len(fake.calls)))

    # A server that echoes the token back must not get it onto the card or into
    # the tool result either.
    echo = Fake(200, json.dumps([{"full_name": TOKEN}]))
    r, out = _run("github_list", echo)
    check("a server that echoes the token back is scrubbed before it is shown",
          TOKEN not in json.dumps(out), json.dumps(out)[:200])

    check("the card says a token is used, without saying which",
          "token" in GH.describe(r).lower(), GH.describe(r))


# --------------------------------------------------------------------------
#   4. No token, no card - said plainly
# --------------------------------------------------------------------------


def t_a_read_with_no_token_says_connect_github_and_raises_no_card():
    no = _Token("")
    with no:
        for tool in ALL_TOOLS:
            state, text = AG.TOOLS[tool].prepare(dict(ARGS[tool]))
            ok = isinstance(state, AG._GitHubNoToken)
            check(f"{tool}: no token is a plain answer, not a card", ok, repr(state))
            check(f"{tool}: ... and the words say what to do",
                  "connect GitHub" in getattr(state, "words", ""),
                  getattr(state, "words", ""))
            check(f"{tool}: ... and no card text was built at all", text == "", repr(text))
    check("the sentence is the module's own, in one place",
          "connect GitHub" in GH.NOT_CONNECTED and "\"connect GitHub\"" in GH.NOT_CONNECTED,
          GH.NOT_CONNECTED)

    # The refusal is BEFORE the gate: `_one_call` answers and returns, so no
    # card is raised. Pinned in the source because driving the whole turn loop
    # would need a model; the branch is the thing that must stay.
    src = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    branch = re.search(
        r"if name in GITHUB_TOOLS and isinstance\(state, _GitHubNoToken\):(.*?)return\n",
        src, re.S)
    check("_one_call answers the no-token case itself", branch is not None)
    if branch is not None:
        body = branch.group(1)
        check("... before any gate call in that branch",
              "jarvis_gate" not in body and "check(" not in body, body[:200])
        check("... and it says it raised no card",
              "NO CARD" in body.upper(), body[:200])


# --------------------------------------------------------------------------
#   5. Each action is ONE card naming exactly what it will do
# --------------------------------------------------------------------------


def t_each_action_is_one_card_naming_what_it_does():
    for tool in ACTION_TOOLS:
        r, text = _card(tool)
        check(f"{tool}: exactly one request", len(r.steps) == 1, r.steps)
        check(f"{tool}: exactly one address on the card", len(r.urls()) == 1, r.urls())
        check(f"{tool}: the card prints that address",
              r.urls()[0] in text, text[:200])
        missing = [w for w in MUST_NAME[tool] if w not in text]
        check(f"{tool}: the card names exactly what it will do", not missing, missing)
        check(f"{tool}: it is decided under its own action",
              r.action == tool and r.action in GH.ACTIONS, r.action)
        check(f"{tool}: a person must say yes (NEEDS_A_PERSON)",
              tool in AG.NEEDS_A_PERSON, sorted(AG.NEEDS_A_PERSON))
        # One request, and never a DELETE: nothing here can remove anything.
        check(f"{tool}: the one request is a GET, POST or PUT, never a DELETE",
              r.steps[0].method in ("GET", "POST", "PUT"), r.steps[0].method)

    for tool in POST_ACTION_TOOLS:
        r, text = _card(tool)
        check(f"{tool}: it says nothing is merged, pushed or closed",
              "merged" in text and "pushed" in text and "closed" in text,
              text[-200:])
        check(f"{tool}: the one request is a POST",
              r.steps[0].method == "POST", r.steps[0].method)

    r, text = _card("github_comment")
    check("a comment carries ONLY the body - no other field can be added",
          _json_body({"body": json.dumps(r.body).encode()}) == {"body": r.body["body"]},
          r.body)
    r, text = _card("github_open_issue")
    check("an issue carries a title and a body, and nothing else",
          set(r.body) == {"title", "body"}, sorted(r.body))

    long_text = "x" * (GH.MAX_TEXT + 1)
    try:
        GH.plan_comment({"repo": "o/r", "number": "1", "body": long_text})
    except GH.GitHubError as exc:
        check("a comment too long for ONE card is refused, never cut",
              "longer" in str(exc), str(exc))
    else:
        check("a comment too long for ONE card is refused, never cut", False)


def t_the_reads_ask_too_and_never_write():
    for tool in READ_TOOLS:
        r, text = _card(tool)
        check(f"{tool}: a read is a GET or a GET pair",
              all(s.method == "GET" for s in r.steps), [s.method for s in r.steps])
        check(f"{tool}: a read carries no body at all", r.body is None, r.body)
        check(f"{tool}: a read is decided under github_inspect",
              r.action == GH.ACTION_INSPECT, r.action)
        check(f"{tool}: a read asks a person too (NEEDS_A_PERSON)",
              tool in AG.NEEDS_A_PERSON)
        check(f"{tool}: the card says nothing on GitHub changes",
              "Nothing on GitHub changes" in text, text[:200])


# --------------------------------------------------------------------------
#   6. Failures are plain sentences, with no HTTP code in them
# --------------------------------------------------------------------------


def t_a_refused_token_is_a_plain_sentence():
    r = _card("github_list")[0]
    for status, words in ((401, "refused"), (403, "said no"), (404, "nothing there"),
                          (429, "Too many"), (0, "could not be reached"),
                          (500, "problem on its own side")):
        with _Token():
            out = GH.run(r, fetch=Fake(status, "{}"), approved=True)
        err = out.get("error", "")
        check(f"{status}: it fails, and says so in words",
              out.get("ok") is False and words.lower() in err.lower(), err)
        check(f"{status}: no HTTP code reaches the owner's answer",
              not re.search(r"\b(?:HTTP|40[0-9]|429|500)\b", err), err)


def t_the_ci_answer_tells_the_truth_about_logs():
    """The 2026-11-10 review / ruling Q1 item 7: the old sentence was false.

    `_job_log` reads the end of a failing check's log, and `_failing_evidence`
    reads GitHub's annotations, while a fix is being prepared - so "GitHub keeps
    the log; Jarvis does not read it" contradicted the module's own code. This
    pins the true sentence and that it points at the flow that shows the evidence.
    """
    failed = json.dumps({"workflow_runs": [
        {"name": "CI", "status": "completed", "conclusion": "failure",
         "head_branch": "main"}]})
    _r, out = _run("github_ci_status", Fake(200, failed))
    text = out.get("text", "")
    check("a failed CI run is still reported as failed", "failed" in text, text)
    check("... and the answer no longer says Jarvis does not read the log",
          "Jarvis does not read it" not in text
          and "GitHub keeps the log" not in text, text)
    check("... it says Jarvis can read the end of a failing check's log and "
          "GitHub's annotations",
          "end of a failing check's log" in text and "annotations" in text, text)
    check("... and points at the fix flow that shows them",
          "github_fix_and_push" in text, text)


# --------------------------------------------------------------------------
#   7. Nothing private is ever sent
# --------------------------------------------------------------------------


def t_nothing_private_is_ever_sent():
    # Values that must never appear in a request this module builds. They are
    # marked so a leak is unmistakable.
    PRIVATE = ("sister@example.com", "C:\\Users\\pcadmin\\Documents\\tax.pdf",
               "my saved memory: the owner is buying a house",
               "correct-horse-battery-staple", "sk-EMAIL-ACCOUNT-PASSWORD")
    sent = []
    fake = Fake(200, "[]")
    for tool in ALL_TOOLS:
        _run(tool, fake)
    for call in fake.calls:
        sent.append(call["url"])
        sent.append((call["body"] or b"").decode("utf-8", "replace"))
        sent.append(json.dumps({k: v for k, v in call["headers"].items()
                                if k.lower() != "authorization"}))
    blob = "\n".join(sent)
    leaked = [p for p in PRIVATE if p in blob]
    check("no email address, file path, saved memory or credential is sent",
          not leaked, leaked)

    # And the module holds no reader for them: it imports no mailbox, memory or
    # file module at all, so there is nothing to read them WITH.
    src = (HERE / "jarvis_github.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_][\w.]*)", src, re.M)
    private = {"jarvis_email", "jarvis_memory", "jarvis_files", "jarvis_notes",
               "jarvis_token_store", "jarvis_web", "jarvis_browser"}
    # jarvis_token_store IS imported, inside _token() - that is the one read of
    # the owner's own secret, and it is named here rather than hidden.
    bad = sorted(set(imports) & (private - {"jarvis_token_store"}))
    check("it imports no mailbox, memory, notes or file module", not bad, bad)
    check("... and the one secret it reads is its own token, by name",
          "jarvis_token_store" in imports and 'token_target()' in src, imports)


# --------------------------------------------------------------------------
#   8. There is no tool that can merge, push, commit, delete or close
# --------------------------------------------------------------------------


def t_merge_and_push_exist_only_behind_their_own_cards():
    """2026-11-10: merging and PR-branch pushing exist now - and only carded.

    Before this date the same test pinned their ABSENCE. The owner's ruling
    replaced that: the absolute bans that remain are force-push, squash-merge,
    rebase-merge, admin bypass, auto-merge, bypassing required checks, pushing
    to main/master/release/*, and deleting or closing a repository or branch.
    """
    forbidden = re.compile(r"squash|rebase|admin|force|delete|remove|close|"
                           r"write_file|edit_file|create_branch", re.I)
    # `pack_remove` is the ONE non-GitHub tool whose name matches ("remove"), and
    # it is the pack manager's own ledger delete after one `modify_own_code`
    # card - see its note in `jarvis_agent.TOOLS`. It holds no repository,
    # branch or remote. Exempted here rather than renamed; the GitHub checks
    # below still hold every GitHub tool to the rule.
    NOT_GITHUB_BY_NAME = {"pack_remove"}
    offenders = sorted(n for n in AG.TOOLS
                       if forbidden.search(n) and n not in NOT_GITHUB_BY_NAME)
    check("no registered tool can squash, rebase, admin, force, delete or close",
          not offenders, offenders)

    # The only two merge/push tools are the two carded ones, and each is at
    # "ask" and in NEEDS_A_PERSON.
    merge_push = sorted(n for n in AG.TOOLS
                        if n.startswith("github") and re.search(r"merge|push", n))
    check("the only merge/push tools are the two carded ones",
          merge_push == ["github_fix_and_push", "github_merge_pr"], merge_push)
    for tool in merge_push:
        check(f"{tool}: it is a carded action, not a read",
              tool in AG.GITHUB_ACTION_TOOLS and tool in AG.NEEDS_A_PERSON, tool)

    # The ruling's sentence, word for word - and the same day's Q3/Q4 added the
    # five permanently banned verbs it now has to cover.
    check("the refusal is the owner's 2026-11-10 sentence, word for word",
          GH.never_words() == (
              "Jarvis can never force-push, squash-merge or rebase, use an "
              "admin bypass, turn on auto-merge, bypass required checks, push "
              "directly to main, approve a pull request in your name, close an "
              "issue, edit a comment, dispatch a workflow, use a gist, or "
              "delete/close repositories or branches; every merge or PR-branch "
              "push requires its own approval card."), GH.never_words())
    check("the module names every ban that remains",
          {"force_push", "squash_merge", "rebase_merge", "admin_bypass",
           "auto_merge", "bypass_required_checks", "push_to_main",
           "delete_repository", "close_repository", "delete_branch",
           "close_branch"} <= GH.NEVER, sorted(GH.NEVER))
    check("... and the five permanently banned verbs Q3/Q4 added",
          {"approve_pr", "close_issue", "edit_comment", "workflow_dispatch",
           "gist"} <= GH.NEVER, sorted(GH.NEVER))
    check("... and the one sentence covers every one of them",
          all(w in GH.never_words() for w in
              ("force-push", "squash-merge", "rebase", "admin bypass",
               "auto-merge", "bypass required checks", "main",
               "approve a pull request", "close an issue", "edit a comment",
               "dispatch a workflow", "gist", "delete/close", "approval card")),
          GH.never_words())
    check("... and plain merge/push are NOT banned any more - they are carded",
          "merge" not in GH.NEVER and "push" not in GH.NEVER, sorted(GH.NEVER))

    check("no planner exists for a banned verb",
          not [n for n in dir(GH) if n.startswith("plan_")
               and forbidden.search(n[len("plan_"):])],
          [n for n in dir(GH) if n.startswith("plan_")])

    # Every action tool's own description still says what it cannot do, and the
    # two new ones say it about themselves rather than claiming more.
    for tool in POST_ACTION_TOOLS:
        desc = AG.TOOLS[tool].description.lower()
        check(f"{tool}: its description says it never merges, pushes or closes",
              all(w in desc for w in ("merge", "push", "closes")), desc)
    merge_desc = AG.TOOLS["github_merge_pr"].description.lower()
    check("github_merge_pr says merge commit only, and never squash/rebase/admin",
          all(w in merge_desc for w in ("merge commit", "squash", "rebase",
                                        "admin", "auto-merge")), merge_desc)
    fix_desc = AG.TOOLS["github_fix_and_push"].description.lower()
    check("github_fix_and_push says never force-push and never a protected branch",
          "force-pushes" in fix_desc and "protected branch" in fix_desc, fix_desc)


def t_no_squash_rebase_admin_or_force_path_exists():
    """The merge method is a constant, and nothing can make it anything else."""
    src = (HERE / "jarvis_github.py").read_text(encoding="utf-8")
    # Docstrings talk ABOUT the body (and quote it); the code is what matters.
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    check("MERGE_METHOD is merge", GH.MERGE_METHOD == "merge", GH.MERGE_METHOD)
    # Every place a merge body is written, it is written from the constant.
    literal = re.findall(r'"merge_method"\s*:\s*([^,}\)\n]+)', code)
    check("no merge_method literal exists outside the one constant",
          literal == ["MERGE_METHOD"], literal)
    check("the constant's only value is \"merge\"",
          re.findall(r'^MERGE_METHOD\s*=\s*"([a-z]+)"', src, re.M) == ["merge"],
          re.findall(r'^MERGE_METHOD\s*=\s*"(.*?)"', src, re.M))
    check("no action name or step path mentions squash, rebase, admin or force",
          not [a for a in GH.ACTIONS
               if re.search(r"squash|rebase|admin|force", a)]
          and not [s.path for r in (GH.plan_merge_pr(
              {"repo": "o/r", "number": "1", "head_sha": "a" * 40,
               "title": "One fix", "base_ref": "main"}),)
              for s in r.steps if re.search(r"squash|rebase|admin|force", s.path)],
          GH.ACTIONS)
    check("the banned git flags are the exact set the owner named",
          GH.BANNED_GIT_FLAGS == {"--force", "--force-with-lease", "-f",
                                  "--delete", "--mirror", "--all"},
          sorted(GH.BANNED_GIT_FLAGS))
    # A merge request that carries squash/rebase fields cannot smuggle them in:
    # the body is built field by field from the planner's own two values.
    r = GH.plan_merge_pr({"repo": "o/r", "number": "1", "head_sha": "a" * 40,
                          "title": "One fix", "base_ref": "main",
                          "body": {"merge_method": "squash"},
                          "commit_title": "x", "commit_message": "y"})
    check("a model's own merge body or commit title is ignored entirely",
          r.body == {"merge_method": "merge", "sha": "a" * 40}, r.body)
    # And a sha that is not a full 40 hex characters is refused, not shortened.
    for bad in ("", "abc", "a" * 39, "a" * 41, "HEAD", "refs/heads/main",
                "z" * 40):
        try:
            GH.plan_merge_pr({"repo": "o/r", "number": "1", "head_sha": bad})
        except GH.GitHubError:
            continue
        check(f"a head sha that is not 40 hex characters is refused: {bad!r}",
              False)
        return
    check("a head sha that is not 40 hex characters is refused", True)
    check("an upper-case sha is accepted only by folding it to lower case",
          GH.plan_merge_pr({"repo": "o/r", "number": "1",
                            "head_sha": "A" * 40, "title": "One fix",
                            "base_ref": "main"}).expected_sha == "a" * 40)


# --------------------------------------------------------------------------
#   9. The patch, the tiers, and every table a new tool has to join
# --------------------------------------------------------------------------


def _tables_of(source: str, name: str):
    """The dict literal `name` in `source`, or None."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == name and isinstance(node.value, ast.Dict):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) \
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def _updated_rows(source: str, name: str) -> dict:
    """`name.update({...})` calls anywhere in `source`, merged."""
    out = {}
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == name
                and len(node.args) == 1 and isinstance(node.args[0], ast.Dict)):
            out.update(ast.literal_eval(node.args[0]))
    return out


def t_the_patch_applies_and_reverses_byte_for_byte():
    if not PATCH.is_file():
        check("github-tools.patch exists", False, str(PATCH))
        return
    if not GATE_BASE.is_file():
        skip("the patch rehearsal needs jarvis-backend/jarvis_gate.py")
        return
    text = PATCH.read_text(encoding="utf-8")
    targets = sorted({line[6:].strip() for line in text.splitlines()
                      if line.startswith("+++ b/")})
    check("the patch touches jarvis_gate.py and nothing else",
          targets == ["jarvis_gate.py"], targets)
    check("it is ONE hunk", len([l for l in text.splitlines()
                                 if l.startswith("@@")]) == 1,
          [l for l in text.splitlines() if l.startswith("@@")])

    # The published base IS the state the whole stack leaves, so the patch is
    # rehearsed the other way round: reverse it out of the base (that gives the
    # text before it), then apply it forwards again. The first version of this
    # test read `HEAD:jarvis-backend/jarvis_gate.py` as "the text before it" -
    # which is the SAME file once the base change is committed, so it could only
    # ever have passed before the commit and failed in CI.
    box = _TMP / "gatecheck"
    if box.exists():
        shutil.rmtree(box)
    box.mkdir(parents=True)
    after = GATE_BASE.read_bytes()
    (box / "jarvis_gate.py").write_bytes(after)
    run = lambda *a: subprocess.run(["git", "-C", str(box)] + list(a),  # noqa: E731
                                    capture_output=True, text=True)
    run("init", "-q")
    run("config", "core.autocrlf", "false")
    rev = run("apply", "-R", "--verbose", str(PATCH))
    check("the patch REVERSES out of the published base cleanly", rev.returncode == 0,
          rev.stderr[-400:])
    pre = (box / "jarvis_gate.py").read_bytes()
    check("... and the result is not the base any more (it really removed "
          "something)", pre != after, "the reversed file is byte-identical")
    fwd = run("apply", "--verbose", str(PATCH))
    check("... and applies forwards again, byte for byte",
          fwd.returncode == 0 and (box / "jarvis_gate.py").read_bytes() == after,
          (fwd.returncode, fwd.stderr[-400:]))

    # It must NOT sit after web-search-grant.patch's own block: that patch's last
    # hunk ends at EOF, and anything appended after it makes the reversal fail.
    # Rehearsed here so this suite fails at the desk, not only in that one.
    wsg = REPO / "backend" / "web-search-grant.patch"
    if wsg.is_file():
        wbox = _TMP / "wsgreverse"
        if wbox.exists():
            shutil.rmtree(wbox)
        wbox.mkdir(parents=True)
        (wbox / "jarvis_gate.py").write_bytes(after)
        wrun = lambda *a: subprocess.run(["git", "-C", str(wbox)] + list(a),  # noqa: E731
                                         capture_output=True, text=True)
        wrun("init", "-q")
        wrun("config", "core.autocrlf", "false")
        wrev = wrun("apply", "-R", "--verbose", str(wsg))
        check("web-search-grant.patch still reverses out of the base - this patch "
              "did not land after its end-of-file block",
              wrev.returncode == 0, wrev.stderr[-400:])

    # It is in the list the installer applies, or it never reaches the owner.
    sys.path.insert(0, str(HERE))
    import _stack
    order = list(_stack.order())
    check("the installer applies it", "github-tools.patch" in order,
          order[-3:])
    at = order.index("github-tools.patch") if "github-tools.patch" in order else -1
    check("... immediately after web-search-grant.patch, and ABOVE that patch's "
          "own end-of-file block - which has to stay the last bytes",
          at > 0 and order[at - 1] == "web-search-grant.patch",
          order[max(0, at - 1):at + 1])
    check("... and before unknown-risk-approvable.patch, which must stay the LAST "
          "writer of jarvis_gate.py",
          "unknown-risk-approvable.patch" in order[at + 1:] if at >= 0 else False,
          order[-4:])
    check("... and plugin-loader.patch stays last of all",
          order[-1] == "plugin-loader.patch", order[-2:])


def t_the_gate_knows_the_ten_tools_and_six_actions():
    if not GATE_BASE.is_file():
        skip("the gate tables need jarvis-backend/jarvis_gate.py")
        return
    src = GATE_BASE.read_text(encoding="utf-8")
    actions = _tables_of(src, "_TOOL_ACTIONS") or {}
    actions.update(_updated_rows(src, "_TOOL_ACTIONS"))
    risk = _tables_of(src, "_RISK") or {}
    risk.update(_updated_rows(src, "_RISK"))

    for tool, action in (("github_list", GH.ACTION_INSPECT),
                         ("github_read_file", GH.ACTION_INSPECT),
                         ("github_ci_status", GH.ACTION_INSPECT),
                         ("github_pr_scan", GH.ACTION_INSPECT),
                         ("github_comment", GH.ACTION_COMMENT),
                         ("github_open_issue", GH.ACTION_OPEN_ISSUE),
                         ("github_rerun_workflow", GH.ACTION_RERUN),
                         ("github_create_repo", GH.ACTION_CREATE_REPO),
                         ("github_merge_pr", GH.ACTION_MERGE),
                         ("github_fix_and_push", GH.ACTION_FIX_PUSH)):
        check(f"the gate maps {tool} to {action}",
              actions.get(tool) == action, actions.get(tool))

    for action in (GH.ACTION_INSPECT, GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE,
                   GH.ACTION_RERUN, GH.ACTION_CREATE_REPO, GH.ACTION_MERGE,
                   GH.ACTION_FIX_PUSH):
        row = risk.get(action)
        check(f"{action} is classified, so its card is not 'unknown'",
              isinstance(row, tuple) and len(row) == 3, row)
    check("the read is reversible and outbound, like every other read of a page",
          risk.get(GH.ACTION_INSPECT, ("",))[0:2] == ("yes", "outbound"),
          risk.get(GH.ACTION_INSPECT))
    for action in (GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE, GH.ACTION_RERUN,
                   GH.ACTION_CREATE_REPO, GH.ACTION_MERGE, GH.ACTION_FIX_PUSH):
        check(f"{action} cannot be undone, and is advertised as such",
              risk.get(action, ("",))[0] == "no", risk.get(action))
    for action, must_say in ((GH.ACTION_MERGE, ("merge commit", "cannot",
                                                "undone")),
                             (GH.ACTION_FIX_PUSH, ("push", "branch", "cannot"))):
        words = str(risk.get(action, ("", "", ""))[2]).lower()
        check(f"{action}'s risk words say exactly what changes and that it "
              f"cannot be undone", all(w in words for w in must_say), words)

    # The patch's added lines must be visible to the parsers the other suites
    # use: one `"_TOOL_ACTIONS"` line per tool, one `"action": (row` per action.
    ptext = PATCH.read_text(encoding="utf-8")
    for tool in ALL_TOOLS:
        check(f"the patch's own + line carries {tool}",
              bool(re.search(r'^\+\s*"%s":\s*"[a-z_]+",?\s*$' % tool, ptext, re.M)),
              tool)
    for action in (GH.ACTION_INSPECT, GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE,
                   GH.ACTION_RERUN, GH.ACTION_CREATE_REPO, GH.ACTION_MERGE,
                   GH.ACTION_FIX_PUSH):
        check(f"the patch's own + line carries the {action} risk row",
              bool(re.search(r'^\+\s*"%s":\s*\(' % action, ptext, re.M)), action)


def t_every_tier_is_ask_and_the_tables_are_joined():
    for toml_path in TOMLS:
        text = toml_path.read_text(encoding="utf-8")
        try:
            import tomllib
        except ImportError:                  # Python < 3.11
            import tomli as tomllib          # type: ignore
        tiers = tomllib.loads(text)["autonomy"]["tiers"]
        for action in (GH.ACTION_INSPECT, GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE,
                       GH.ACTION_RERUN, GH.ACTION_CREATE_REPO, GH.ACTION_MERGE,
                       GH.ACTION_FIX_PUSH):
            check(f"{toml_path.parent.name}/{toml_path.name}: {action} ships as ask",
                  tiers.get(action) == "ask", tiers.get(action))
        check(f"{toml_path.name}: github_read stayed 'auto' (the watch needs it)",
              tiers.get("github_read") == "auto", tiers.get("github_read"))
        banned = [k for k in tiers
                  if re.match(r"github_", k)
                  and re.search(r"squash|rebase|admin|force|delete|close", k)]
        check(f"{toml_path.name}: no tier line names a banned action", not banned,
              banned)

    for action in (GH.ACTION_INSPECT, GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE,
                   GH.ACTION_RERUN, GH.ACTION_CREATE_REPO, GH.ACTION_MERGE,
                   GH.ACTION_FIX_PUSH):
        check(f"the card has plain words for {action}", action in CW.TITLES,
              sorted(CW.TITLES))
        check(f"... and they read as an action, not a code name",
              CW.has_written_title(action), CW.TITLES.get(action))

    import jarvis_reach as REACH
    import jarvis_claims as CLAIMS
    for tool in ALL_TOOLS:
        check(f"the Reach page has plain words for {tool}", tool in REACH.TOOL_NAMES)
    for tool in READ_TOOLS:
        check(f"{tool} is a read-only tool for the claim checker",
              tool in CLAIMS.READ_ONLY_TOOLS)
    for tool in ACTION_TOOLS:
        check(f"{tool} is an acting tool for the claim checker",
              tool in CLAIMS.ACTING_TOOLS)

    import jarvis_asks_first as AF
    names = {n for _title, members in AF.GROUPS for n in members}
    for action in (GH.ACTION_INSPECT, GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE,
                   GH.ACTION_RERUN, GH.ACTION_CREATE_REPO, GH.ACTION_MERGE,
                   GH.ACTION_FIX_PUSH):
        check(f"the 'What asks first' page has a row for {action}",
              action in names, sorted(names - {action})[:5])

    import jarvis_owner_check as OC
    check("a GitHub read is a SMALL card on this PC", GH.ACTION_INSPECT in OC.SMALL_ACTIONS)
    for action in (GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE, GH.ACTION_RERUN,
                   GH.ACTION_CREATE_REPO, GH.ACTION_MERGE, GH.ACTION_FIX_PUSH):
        check(f"{action} is NOT a small card - it needs the owner's own check",
              action not in OC.SMALL_ACTIONS,
              sorted(OC.SMALL_ACTIONS))


def t_a_file_read_shows_the_files_text_not_the_envelope():
    """DEF-042: the contents API answers in base64; the tool shows the FILE.

    Read on 2026-11-04, the tool returned the envelope itself - up to 40,000
    characters of base64 where its card, `jarvis_agent`'s tool description and
    `docs/JARVIS-API.md` section 190.1 promise ONE file's text - and this
    suite's fake returned plain text, so its checks could not catch that. The
    fake now returns what GitHub really sends, and the checks below fail if the
    decode is ever removed again.
    """
    _r, out = _run("github_read_file", Fake(200, _file_envelope(
        "# Jarvis\n\nThe README's own words.\n")))
    text = out.get("text", "")
    check("a base64 file answer is decoded to the file's own text",
          out.get("ok") is True and "The README's own words." in text
          and "# Jarvis" in text, repr(text)[:300])
    check("... wrapped in the data delimiters, because a file is fetched text "
          "too (2026-11-10 prompt-injection hardening)",
          text.startswith(GH.GITHUB_TEXT_BEGINS)
          and text.endswith(GH.GITHUB_TEXT_ENDS), repr(text)[:300])
    check("... and never the envelope it arrived in",
          '"encoding"' not in text and '"content"' not in text
          and "base64" not in text, text[:200])

    _r, out = _run("github_read_file", Fake(200, _file_envelope("")))
    check("an empty file says so in one sentence, never the envelope",
          out.get("text") == "That file is empty.", out.get("text"))

    _r, out = _run("github_read_file", Fake(200, json.dumps(
        [{"name": "a.md", "type": "file", "path": "a.md"}])))
    check("a directory is a plain sentence, not a JSON list",
          out.get("ok") is True and "directory" in out.get("text", "")
          and "[" not in out.get("text", ""), out.get("text"))

    _r, out = _run("github_read_file",
                   Fake(200, _file_envelope("x", encoding="none")))
    check("encoding none is a plain sentence, not a silent empty answer",
          out.get("ok") is True and "did not send that file's text" in out.get("text", "")
          and "encoding" not in out.get("text", ""), out.get("text"))


def t_the_answer_is_bounded_and_unapproved_runs_send_nothing():
    _r, out = _run("github_read_file", Fake(200, _file_envelope(
        "a" * (GH.MAX_FILE_CHARS + 5000))))
    text = out.get("text", "")
    check("a huge file is cut, and says so",
          out.get("ok") and "(cut here)" in text, len(text))
    # The cap applies to the file's own text; the two data-delimiter lines are
    # the sanitizer's, not the file's, so they are allowed on top.
    ceiling = (GH.MAX_FILE_CHARS + len("\n(cut here)")
               + len(GH.GITHUB_TEXT_BEGINS) + len(GH.GITHUB_TEXT_ENDS) + 2)
    check("... at the file cap, not the socket cap",
          len(text) <= ceiling, (len(text), ceiling))

    for tool in ALL_TOOLS:
        _r, out = _run(tool, Fake(200, "[]"), approved=False)
        fake = Fake(200, "[]")
        _r, out = _run(tool, fake, approved=False)
        check(f"{tool}: without a person's yes nothing is sent at all",
              out.get("ok") is False and fake.calls == [],
              (out, fake.calls))


# --------------------------------------------------------------------------
#   10. github_create_repo (2026-11-09): ONE card before any network call, and
#       only what GitHub really answered afterwards
# --------------------------------------------------------------------------
#
# The owner's ask: "create a repository called Fitness Band". The card is the
# permission, so these checks drive the SAME seam the other tools use - prepare()
# builds the Request with no fetch at all, run() only works after approved=True -
# and they prove the body is the fixed shape, the token never leaves a card, a
# receipt or an error, and a 201 reports GitHub's own full name and address.


def t_create_repo_is_one_carded_call_before_any_network():
    fake = Fake(201, json.dumps({
        "full_name": "owner/Fitness-Band",
        "html_url": "https://github.com/owner/Fitness-Band", "private": True}))
    with _Token():
        r, text = AG.TOOLS["github_create_repo"].prepare(
            dict(ARGS["github_create_repo"]))
    check("prepare() builds ONE Request with no fetch in sight",
          isinstance(r, GH.Request) and len(r.steps) == 1, type(r))
    check("... one POST to the fixed user/repos address",
          r.steps[0].method == "POST" and r.urls()
          == (GH.GITHUB_API + "/user/repos",), r.urls())
    check("... the card names the exact new name", "Fitness-Band" in text, text[:300])
    check("... and whether it is private", "Private: yes" in text, text[:300])
    check("... and the description that will be sent",
          "A band that counts steps." in text, text[:400])
    check("... and says it stays empty and cannot be deleted",
          "EMPTY" in text and "delete" in text, text[-300:])
    check("... under its own action, never a read or an issue",
          r.action == GH.ACTION_CREATE_REPO and r.action in GH.ACTIONS, r.action)
    check("... and a person must say yes every time (NEEDS_A_PERSON)",
          "github_create_repo" in AG.NEEDS_A_PERSON)

    # THE DENIAL: no yes, no socket. The fake would record the call if it ran.
    out = GH.run(r, fetch=fake, approved=False)
    check("without a person's yes nothing is sent at all",
          out.get("ok") is False and fake.calls == [], (out, fake.calls))
    check("... and the answer says nothing was sent",
          "not approved" in out.get("error", ""), out)
    # And with the yes it is still exactly one request.
    _r, out = _run("github_create_repo", fake)
    check("with a person's yes it is exactly one request", len(fake.calls) == 1,
          fake.calls)


def t_create_repo_body_is_exactly_what_the_card_showed():
    r, text = _card("github_create_repo")
    check("the body carries the name, the private flag and the description",
          r.body == {"name": "Fitness-Band", "private": True,
                     "description": "A band that counts steps."}, r.body)
    check("... and nothing else - no team, org, template or branch field",
          set(r.body) == {"name", "private", "description"}, sorted(r.body))
    check("... and there is no organization endpoint anywhere",
          r.urls() == (GH.GITHUB_API + "/user/repos",), r.urls())

    r = GH.plan_create_repo({"name": "One"})
    check("the private flag defaults to a public repository",
          r.body == {"name": "One", "private": False}, r.body)
    r = GH.plan_create_repo({"name": "One", "description": "  "})
    check("an empty description is left out, never sent as blank",
          "description" not in r.body, r.body)

    # A model cannot widen the call: extra arguments are ignored, and there is no
    # list anywhere in the schema or the planner.
    r = GH.plan_create_repo({"name": "One", "private": False, "team_id": 7,
                             "org": "somebody-else", "names": ["a", "b"],
                             "auto_init": True})
    check("extra arguments cannot add a field or a second repository",
          r.body == {"name": "One", "private": False} and len(r.steps) == 1,
          (r.body, r.steps))
    props = AG.TOOLS["github_create_repo"].parameters["properties"]
    check("the tool takes ONE name, not a list", props["name"]["type"] == "string",
          props["name"])
    check("... and no argument can name an organization, a team or a second repo",
          set(props) == {"name", "description", "private"}, sorted(props))

    # GitHub's own name rule, refused with words that say what to type instead -
    # never silently rewritten into a different repository name.
    for bad in ("Fitness Band", "", ".", "..", "a/b", "a?b", "x" * 101):
        try:
            GH.plan_create_repo({"name": bad})
        except GH.GitHubError as exc:
            continue
        check(f"a name GitHub would refuse is refused here too: {bad!r}", False)
        return
    check("a name GitHub would refuse is refused here too", True)
    try:
        GH.plan_create_repo({"name": "Fitness Band"})
    except GH.GitHubError as exc:
        check("... and the refusal names the real fix (a dash, not a space)",
              "Fitness-Band" in str(exc) and "space" in str(exc).lower(), str(exc))
    try:
        GH.plan_create_repo({"name": "One", "private": "maybe"})
    except GH.GitHubError:
        check("a private flag that is not true/false is refused", True)
    else:
        check("a private flag that is not true/false is refused", False)


def t_create_repo_never_prints_the_token():
    fake = Fake(201, json.dumps({
        "full_name": "owner/Fitness-Band",
        "html_url": "https://github.com/owner/Fitness-Band"}))
    r, text = _card("github_create_repo")
    _r, out = _run("github_create_repo", fake)
    shown = "\n".join([text, json.dumps(r.body), str(r.urls()), json.dumps(out)])
    check("the token is in none of the card, body, address or receipt",
          TOKEN not in shown, [s for s in (text, str(r.body), str(out)) if TOKEN in s])
    sent = [c for c in fake.calls
            if c["headers"].get("Authorization") == f"Bearer {TOKEN}"]
    check("CONTROL: it was sent, in the Authorization header",
          len(sent) == len(fake.calls) == 1, (len(sent), len(fake.calls)))

    # A server that echoes the token in its own error message must not get it
    # onto the answer either.
    echo = Fake(422, json.dumps({"message": "bad request for " + TOKEN}))
    _r, out = _run("github_create_repo", echo)
    check("a server that echoes the token back is scrubbed before it is shown",
          TOKEN not in json.dumps(out), json.dumps(out)[:300])


def t_create_repo_201_reports_only_what_github_answered():
    _r, out = _run("github_create_repo", Fake(201, json.dumps({
        "full_name": "owner/Fitness-Band",
        "html_url": "https://github.com/owner/Fitness-Band", "private": True})))
    said = out.get("text", "")
    check("201 says the repository was created", out.get("ok") is True
          and "created" in said, said)
    check("... with the REAL full name GitHub sent",
          "owner/Fitness-Band" in said, said)
    check("... and the REAL address GitHub sent",
          "https://github.com/owner/Fitness-Band" in said, said)
    check("... and never a guessed or made-up address",
          said.count("github.com") == 1, said)

    # 201 but no repository in the answer: say so, never invent a name or a URL.
    _r, out = _run("github_create_repo", Fake(201, "{}"))
    said = out.get("text", "")
    check("a 201 with no repository in it invents no name and no address",
          out.get("ok") is True and "Fitness-Band" not in said
          and "https://github.com/" not in said, said)
    check("... it says GitHub did not send the repository back",
          "did not send" in said, said)


def t_create_repo_failures_are_githubs_own_words_without_the_token():
    cases = (
        (401, {"message": "Bad credentials"}, "Bad credentials"),
        (422, {"message": "Repository creation failed.",
               "errors": [{"resource": "Repository", "field": "name",
                           "code": "custom",
                           "message": "name already exists on this account"}]},
         "name already exists on this account"),
    )
    for status, payload, needle in cases:
        _r, out = _run("github_create_repo", Fake(status, json.dumps(payload)))
        err = out.get("error", "")
        check(f"{status}: nothing is claimed created",
              out.get("ok") is False and "Nothing was created" in err, err)
        check(f"{status}: GitHub's OWN message is quoted", needle in err, err)
        check(f"{status}: the token is not in the failure", TOKEN not in err, err)
        check(f"{status}: no HTTP code reaches the owner's answer",
              not re.search(r"\b401\b|\b422\b", err), err)
    _r, out = _run("github_create_repo", Fake(401, "{}"))
    check("a refusal with no message still says the token needs replacing",
          "connect GitHub" in out.get("error", ""), out.get("error"))
    _r, out = _run("github_create_repo", Fake(500, "oops"))
    check("a server error with no message is a plain sentence",
          "problem on its own side" in out.get("error", ""), out.get("error"))


def t_create_repo_has_no_auto_approve_or_bulk_path():
    for toml_path in TOMLS:
        try:
            import tomllib
        except ImportError:                  # Python < 3.11
            import tomli as tomllib          # type: ignore
        tiers = tomllib.loads(toml_path.read_text(encoding="utf-8"))["autonomy"]["tiers"]
        check(f"{toml_path.name}: github_create_repo ships as ask",
              tiers.get(GH.ACTION_CREATE_REPO) == "ask",
              tiers.get(GH.ACTION_CREATE_REPO))
    check("it is in the never-loosened set, so a loosened tier still asks",
          "github_create_repo" in AG.NEEDS_A_PERSON)
    check("run() refuses a request that was never approved",
          GH.run(GH.plan_create_repo({"name": "One"}), approved=False)
          .get("error") == "not approved; nothing was sent")
    # There is exactly ONE create planner, and no bulk/org sibling.
    creators = [n for n in dir(GH) if n.startswith("plan_")
                and ("create" in n or "repo" in n)]
    check("there is exactly ONE create planner, and it makes one repository",
          creators == ["plan_create_repo"], creators)
    check("the module's never-list names every ban that remains",
          {"force_push", "squash_merge", "rebase_merge", "admin_bypass",
           "auto_merge", "bypass_required_checks", "push_to_main",
           "delete_repository", "close_repository", "delete_branch",
           "close_branch"} <= GH.NEVER, sorted(GH.NEVER))
    check("... and the refusal names the card in front of every merge and push",
          "approval card" in GH.never_words()
          and "every merge or PR-branch push" in GH.never_words(), GH.never_words())
    check("... and no longer claims merge or push are impossible",
          "cannot merge" not in GH.never_words()
          and "cannot push" not in GH.never_words(), GH.never_words())


# --------------------------------------------------------------------------
#   11. github_pr_scan (2026-11-10): the read-only PR cockpit
# --------------------------------------------------------------------------


def t_pr_scan_classifies_each_open_pull_request():
    prs = [
        {"number": 1, "title": "A draft"},        # draft
        {"number": 2, "title": "Conflicts"},      # dirty
        {"number": 3, "title": "Still running"},  # a check running
        {"number": 4, "title": "Red check"},      # a required check failed
        {"number": 5, "title": "Ready"},          # clean + all green
    ]
    shas = {str(p["number"]): (str(p["number"]) * 40) for p in prs}

    def pr_answer(number, **over):
        head = {"sha": shas[str(number)], "ref": f"b{number}",
                "repo": {"full_name": "o/r"}}
        return _pr_doc(number=number, head=head, **over)

    def runs_for(number):
        if number == 3:
            return json.dumps({"check_runs": [
                {"name": "rust", "status": "in_progress", "conclusion": None}]})
        if number == 4:
            return json.dumps({"check_runs": [
                {"name": "rust", "status": "completed", "conclusion": "failure"},
                {"name": "frontend", "status": "completed", "conclusion": "success"}]})
        return _all_green_runs()

    routes = [("/pulls?", (200, json.dumps(prs)))]
    routes.append(("/pulls/1", (200, pr_answer(1, draft=True))))
    routes.append(("/pulls/2", (200, pr_answer(2, mergeable=False,
                                                mergeable_state="dirty"))))
    routes.append(("/pulls/3", (200, pr_answer(3, mergeable=False,
                                                mergeable_state="unstable"))))
    routes.append(("/pulls/4", (200, pr_answer(4, mergeable=False,
                                                mergeable_state="blocked"))))
    routes.append(("/pulls/5", (200, pr_answer(5))))
    for number, sha in shas.items():
        routes.append((f"/commits/{sha}/check-runs", (200, runs_for(int(number)))))
    fake = Routed(routes)
    _r, out = _run("github_pr_scan", fake)
    text = out.get("text", "")
    check("the cockpit answers", out.get("ok") is True, out)
    for number, word in ((1, "draft"), (2, "conflicted"), (3, "running"),
                         (4, "blocked"), (5, "merge-ready")):
        check(f"#{number} is classified {word}", f"#{number} " in text
              and f": {word}" in text, text)
    check("a running check is named", "rust" in text, text)
    check("a failing required check is named", "rust finished as failure" in text,
          text)
    check("the cockpit caps at ten pull requests", GH.MAX_PRS == 10, GH.MAX_PRS)

    check("every cockpit request is a GET", set(fake.methods()) == {"GET"},
          fake.methods())
    check("the cockpit writes nothing - no body at all",
          all(c["body"] is None for c in fake.calls), fake.bodies())
    check("it reads the list, then each pull request, then its checks",
          len(fake.calls) == 1 + len(prs) + len(prs), len(fake.calls))
    check("the token is sent on every read",
          all(c["headers"].get("Authorization") == f"Bearer {TOKEN}"
              for c in fake.calls))
    check("... and is not in the words", TOKEN not in text, text[:200])
    check("the cockpit is decided under github_inspect, the read action",
          _card("github_pr_scan")[0].action == GH.ACTION_INSPECT)


def t_pr_scan_refuses_a_failed_read_plainly():
    _r, out = _run("github_pr_scan", Routed([("/pulls?", (403, "{}"))]))
    check("a refused list read is a plain sentence, not a crash",
          out.get("ok") is False and "no" in out.get("error", "").lower(), out)
    check("... with no HTTP code in it",
          not re.search(r"\b(?:HTTP|40[0-9]|500)\b", out.get("error", "")), out)


# --------------------------------------------------------------------------
#   12. github_merge_pr (2026-11-10): merge commit only, pinned to the sha
# --------------------------------------------------------------------------


def t_the_merge_card_names_the_pinned_commit_and_the_exact_body():
    r, text = _card("github_merge_pr")
    check("the merge card names the pull request and the repository",
          "darknight11ish/Epic-Jarvis" in text and "#1116" in text, text[:300])
    check("... and the pull request's TITLE, on its own line",
          "Title: Fix the tray icon" in text, text[:400])
    check("... and the TARGET BRANCH it is merged into, on its own line",
          "Target branch: main" in text, text[:400])
    check("... and the EXACT 40-hex head commit it is pinned to",
          HEAD_SHA in text, text[:400])
    check("... and the pull request's real address on github.com, so the owner "
          "can see what he is approving",
          "https://github.com/darknight11ish/Epic-Jarvis/pull/1116" in text,
          text[:500])
    check("... and the plain sentence that says where it is merged",
          "It will be merged at this exact commit: " + HEAD_SHA in text,
          text[:500])
    check("... and the one PUT address",
          r.urls() == (GH.GITHUB_API + "/repos/darknight11ish/Epic-Jarvis/"
                       "pulls/1116/merge",), r.urls())
    check("the body is exactly merge_method=merge and the pinned sha",
          r.body == {"merge_method": "merge", "sha": HEAD_SHA}, r.body)
    # The 2026-11-10 ruling: the card speaks plain words, not JSON. The body is
    # still pinned by the check above and by the run test - a person just does not
    # read `{"merge_method": ...}` on an approval card any more.
    check("... and the card shows NO raw JSON request body",
          "Request body" not in text and '{"merge_method"' not in text, text)
    check("... it says instead what GitHub is told, in words",
          "GitHub is told: merge, and only merge, at this exact commit." in text,
          text)
    check("the card says merge commit only and names the impossible halves",
          all(w in text.lower() for w in ("merge commit", "no squash", "no rebase",
                                          "no admin bypass", "no auto-merge")), text)
    check("... and it names all seven required checks that must have passed",
          all(c in text for c in GH.REQUIRED_CHECKS), text)
    check("... and the whole refusal list is one plain sentence",
          all(w in text.lower() for w in ("draft", "closed or already merged",
                                          "moved to a different commit",
                                          "conflicts with its base",
                                          "check still running",
                                          "required checks not passed")), text)
    check("the card says a changed head commit means nothing is merged",
          "moved since you looked" in text.lower()
          or "still exactly at the head commit" in text.lower(), text)
    check("the merge is its own action and in the closed set",
          r.action == GH.ACTION_MERGE and GH.ACTION_MERGE in GH.ACTIONS,
          r.action)
    check("a person must say yes every time (NEEDS_A_PERSON)",
          "github_merge_pr" in AG.NEEDS_A_PERSON)
    check("run() refuses it without a person's yes",
          GH.run(r, approved=False).get("error") == "not approved; nothing was sent")


def t_merge_refuses_everything_but_a_clean_unmoved_green_pull_request():
    r = _card("github_merge_pr")[0]
    cases = [
        ("draft", {"draft": True}, "draft"),
        ("conflicts", {"mergeable": False, "mergeable_state": "dirty"},
         "conflicts"),
        ("blocked", {"mergeable": False, "mergeable_state": "blocked"},
         "blocked"),
        ("unknown", {"mergeable": None, "mergeable_state": "unknown"},
         "not worked out"),
        ("behind", {"mergeable": False, "mergeable_state": "behind"}, "moved ahead"),
        ("unstable", {"mergeable": False, "mergeable_state": "unstable"},
         "failing or still running"),
        ("already merged", {"merged": True}, "already merged"),
        ("closed", {"state": "closed"}, "closed"),
        ("retargeted", {"base": {"ref": "release/1.2"}}, "retargeted"),
    ]
    for name, over, needle in cases:
        fake = Routed([("/pulls/1116", (200, _pr_doc(**over)))])
        out = _run_request(r, fake)
        check(f"{name}: the merge is refused", out.get("ok") is False, out)
        check(f"{name}: ... in plain words ({needle!r})",
              needle.lower() in out.get("error", "").lower(), out.get("error"))
        check(f"{name}: ... and NOTHING was sent - not even the PUT",
              fake.writes() == [], fake.writes())
        check(f"{name}: ... and it says nothing was merged",
              "nothing was merged" in out.get("error", "").lower(),
              out.get("error"))

    # A moved head commit: the pull request is fine, but it is not the commit
    # the card showed. This is the TOCTOU refusal, and it must name the fix.
    moved = _pr_doc(head={"sha": "b" * 40, "ref": "feature/tray-icon",
                          "repo": {"full_name": "darknight11ish/Epic-Jarvis"}})
    fake = Routed([("/pulls/1116", (200, moved))])
    out = _run_request(r, fake)
    check("a moved head commit is refused", out.get("ok") is False, out)
    moved_words = out.get("error", "").lower()
    check("... and says the pull request moved, and to look again",
          "moved since you looked" in moved_words
          and "look again" in moved_words, out.get("error"))
    check("... and sends nothing", fake.writes() == [], fake.writes())

    # The same head commit, but RETARGETED to another base branch: the card named
    # "main", so this is a different merge from the one the owner approved.
    retargeted = _pr_doc(base={"ref": "release/1.2"})
    fake = Routed([("/pulls/1116", (200, retargeted))])
    out = _run_request(r, fake)
    check("a pull request retargeted to another base branch is refused",
          out.get("ok") is False, out)
    retarget_words = out.get("error", "").lower()
    check("... and names both branches, and says to look again",
          "retargeted" in retarget_words and "release/1.2" in retarget_words
          and "main" in retarget_words and "look again" in retarget_words,
          out.get("error"))
    check("... and sends nothing", fake.writes() == [], fake.writes())

    # A check still running.
    fake = Routed([
        ("/pulls/1116", (200, _pr_doc())),
        ("/check-runs", (200, _all_green_runs(extra=[
            {"name": "audit", "status": "in_progress", "conclusion": None}])))])
    out = _run_request(r, fake)
    check("a running check blocks the merge",
          out.get("ok") is False and "still running" in out.get("error", ""),
          out)
    check("... and nothing was sent", fake.writes() == [], fake.writes())

    # A required check that finished red.
    runs = _all_green_runs(conclusion="failure")
    fake = Routed([("/pulls/1116", (200, _pr_doc())),
                   ("/check-runs", (200, runs))])
    out = _run_request(r, fake)
    check("a failing required check blocks the merge",
          out.get("ok") is False and "required check" in out.get("error", ""),
          out)
    check("... and it is named", "rust" in out.get("error", ""), out.get("error"))
    check("... and nothing was sent", fake.writes() == [], fake.writes())

    # A required check that never reported at all.
    only_one = json.dumps({"check_runs": [
        {"name": "rust", "status": "completed", "conclusion": "success"}]})
    fake = Routed([("/pulls/1116", (200, _pr_doc())),
                   ("/check-runs", (200, only_one))])
    out = _run_request(r, fake)
    check("a required check that never reported blocks the merge",
          out.get("ok") is False
          and "has not reported" in out.get("error", ""), out.get("error"))
    check("... and nothing was sent", fake.writes() == [], fake.writes())

    # A read that fails is a plain sentence, never a merge.
    for status in (401, 403, 404, 500):
        fake = Routed([("/pulls/1116", (status, "{}"))])
        out = _run_request(r, fake)
        check(f"{status}: a failed re-read refuses the merge",
              out.get("ok") is False and fake.writes() == [], (status, out))
        check(f"{status}: ... with no HTTP code in the words",
              not re.search(r"\b(?:HTTP|40[0-9]|500)\b", out.get("error", "")),
              out.get("error"))


def t_merge_sends_exactly_the_pinned_body_once():
    # The merge route comes FIRST: its address contains "/pulls/1116", so a
    # later route would answer the PUT with the pull request itself.
    fake = Routed([
        ("/pulls/1116/merge", (200, json.dumps(
            {"merged": True, "sha": MERGED_SHA, "message": "Pull Request merged"}))),
        ("/pulls/1116", (200, _pr_doc())),
        ("/check-runs", (200, _all_green_runs())),
    ])
    _r, out = _run("github_merge_pr", fake)
    check("the merge succeeds when everything is clean", out.get("ok") is True, out)
    check("... and reports the real merge commit GitHub sent",
          MERGED_SHA in out.get("text", ""), out.get("text"))
    puts = [c for c in fake.calls if c["method"] == "PUT"]
    check("exactly ONE PUT is sent", len(puts) == 1, fake.methods())
    check("... to the pull request's own merge address",
          puts[0]["url"] == GH.GITHUB_API + "/repos/darknight11ish/Epic-Jarvis/"
          "pulls/1116/merge", puts[0]["url"])
    check("... with EXACTLY the pinned body, no field added",
          _json_object(puts[0]["body"]) == {"merge_method": "merge",
                                            "sha": HEAD_SHA},
          _json_object(puts[0]["body"]))
    check("... as JSON, with the content type",
          puts[0]["headers"].get("Content-Type") == "application/json",
          puts[0]["headers"])
    check("... carrying the token, and nothing else of the owner's",
          puts[0]["headers"].get("Authorization") == f"Bearer {TOKEN}")
    check("the merge re-read the pull request first and read its checks",
          [c["method"] for c in fake.calls] == ["GET", "GET", "PUT"],
          fake.methods())


def t_a_merge_answered_without_a_result_is_not_claimed_as_done():
    fake = Routed([
        ("/pulls/1116/merge", (200, "{}")),
        ("/pulls/1116", (200, _pr_doc())),
        ("/check-runs", (200, _all_green_runs())),
    ])
    _r, out = _run("github_merge_pr", fake)
    check("a merge answer with no merged field is not claimed as a merge",
          out.get("ok") is False and "check github.com" in out.get("error", ""),
          out)
    fake = Routed([
        ("/pulls/1116/merge", (405, json.dumps(
            {"message": "Pull Request is not mergeable"}))),
        ("/pulls/1116", (200, _pr_doc())),
        ("/check-runs", (200, _all_green_runs())),
    ])
    _r, out = _run("github_merge_pr", fake)
    check("a refused merge is a plain sentence saying nothing was merged",
          out.get("ok") is False
          and "nothing was merged" in out.get("error", "").lower(),
          out)
    check("... with no HTTP code in it",
          not re.search(r"\b(?:HTTP|405|40[0-9])\b", out.get("error", "")),
          out.get("error"))


def t_a_refused_merge_is_refused_in_the_words_its_cause_deserves():
    """The owner's ruling Q1 item 3 / Q6: the 409, the 405 and the merge queue.

    Each is driven through the real run(), with the pull request and its checks
    clean, so the ONLY reason for the refusal is the PUT's answer - which is what
    makes the words the point of the test.
    """
    clean = [("/pulls/1116", (200, _pr_doc())),
             ("/check-runs", (200, _all_green_runs()))]

    def refused(answer):
        fake = Routed([("/pulls/1116/merge", answer)] + clean)
        _r, out = _run("github_merge_pr", fake)
        check("... it is a refusal", out.get("ok") is False, out)
        check("... with no HTTP code in the words",
              not re.search(r"\b(?:HTTP|40[0-9]|409|405)\b",
                            out.get("error", "")), out.get("error"))
        check("... and it says nothing was merged",
              "nothing was merged" in out.get("error", "").lower(),
              out.get("error"))
        return out.get("error", "")

    # 409: the head moved or the pull request now conflicts - look again first.
    err = refused((409, json.dumps({"message": "Head branch was modified"})))
    check("a 409 says the head commit moved or it conflicts",
          "head commit moved or it has a merge conflict" in err, err)
    check("... and points back at the cockpit before asking again",
          "github_pr_scan" in err and "look at it again" in err.lower(), err)

    # 405: not mergeable right now - checks, review gate or the merge queue.
    err = refused((405, json.dumps({"message": "Pull Request is not mergeable"})))
    check("a 405 says it is not mergeable right now",
          "not mergeable right now" in err, err)
    check("... and names the three things that can hold it",
          all(w in err for w in ("required checks", "review gate",
                                 "merge queue")), err)

    # The merge queue itself, which Q6 says Jarvis must refuse rather than join.
    # GitHub has answered both 405 and 409 for this, so the words are chosen from
    # its own message and not from the status alone.
    for status in (405, 409):
        err = refused((status, json.dumps(
            {"message": "This branch has a merge queue and cannot be merged "
                        "directly"})))
        check(f"{status}: a merge-queue branch gets the one honest sentence",
              "requires GitHub's merge queue" in err
              and "Jarvis does not queue merges" in err, err)
        check(f"{status}: ... which says what to do instead",
              "Queue the merge on GitHub" in err, err)
        check(f"{status}: ... and that Jarvis never claims it merged anything",
              "nothing was merged" in err.lower(), err)

    # Anything else keeps the ordinary plain-words failure.
    err = refused((422, json.dumps({"message": "Validation Failed"})))
    check("another status keeps the ordinary plain-words failure",
          "not valid to github" in err.lower() and "nothing was merged" in err.lower(),
          err)


# --------------------------------------------------------------------------
#   13. github_fix_and_push, stage prepare (2026-11-10)
# --------------------------------------------------------------------------


class _Scratch:
    """A scratch root for one block, pointed at by the module's own env name."""

    def __enter__(self):
        self.root = Path(tempfile.mkdtemp(prefix="jarvis-pr-scratch-"))
        self._was = os.environ.get(GH.SCRATCH_ENV)
        os.environ[GH.SCRATCH_ENV] = str(self.root)
        return self

    def __exit__(self, *_exc):
        if self._was is None:
            os.environ.pop(GH.SCRATCH_ENV, None)
        else:
            os.environ[GH.SCRATCH_ENV] = self._was
        shutil.rmtree(self.root, ignore_errors=True)
        return False


def _prepared_folder(root: Path, *, repo="darknight11ish/Epic-Jarvis",
                     number="1116", head_ref="feature/tray-icon",
                     head_sha=HEAD_SHA, checks=None) -> Path:
    """A folder the prepare stage could have made: the marker in its `.git`."""
    owner, name = repo.split("/", 1)
    folder = Path(root) / f"{owner}__{name}__pr{number}"
    (folder / ".git").mkdir(parents=True, exist_ok=True)
    (folder / ".git" / GH.MARKER_NAME).write_text(json.dumps({
        "repo": repo, "number": number, "head_ref": head_ref,
        "head_sha": head_sha, "failing_checks": checks or []}), encoding="utf-8")
    return folder


def _push_git(*, branch="feature/tray-icon", status="", files="src/tray.rs\nREADME.md\n",
              commits="abc1234 fix the tray icon\n", push=(0, "", "")):
    return FakeGit([
        ("status --porcelain", (0, status, "")),
        ("branch --show-current", (0, branch + "\n", "")),
        ("log --oneline", (0, commits, "")),
        ("diff --name-only", (0, files, "")),
        ("push origin", push),
    ])


def t_fix_prepare_copies_the_pr_into_its_own_scratch_folder():
    routes = [
        ("/pulls/1116", (200, _pr_doc())),
        # The annotations route must be matched BEFORE the plain check-runs one,
        # because its address contains that string too.
        ("/check-runs/55/annotations", (200, json.dumps([
            {"path": "src/tray.rs", "start_line": 12,
             "message": "unused import"}]))),
        ("/check-runs", (200, json.dumps({"check_runs": [
            {"id": 55, "name": "rust", "status": "completed",
             "conclusion": "failure",
             "details_url": "https://github.com/o/r/actions/runs/9/job/77"},
            {"id": 56, "name": "frontend", "status": "completed",
             "conclusion": "success"},
            {"id": 57, "name": "audit", "status": "in_progress",
             "conclusion": None}]}))),
    ]
    git = FakeGit()
    log = FakeLog(text="error[E0308]: mismatched types\n  --> src/tray.rs:3:5\n")
    with _Scratch() as box:
        r = GH.plan_fix_and_push(dict(ARGS["github_fix_and_push"]))
        out = _run_request(r, Routed(routes), git=git, log=log)
        text = out.get("text", "")
        check("prepare succeeds", out.get("ok") is True, out)
        target = box.root / "darknight11ish__Epic-Jarvis__pr1116"
        check("the scratch folder is inside the configured root, named "
              "<owner>__<name>__pr<number>",
              target.is_dir() and str(target) in text, (str(target), text[:300]))
        clone = [c for c in git.calls if "clone" in c["args"]]
        check("it CLONES the pull request's repository into that folder",
              len(clone) == 1 and "https://github.com/darknight11ish/"
              "Epic-Jarvis.git" in clone[0]["args"]
              and str(target) in clone[0]["args"], clone)
        check("the token rides in git's own environment config, never the argv",
              clone[0]["env"].get("GIT_CONFIG_COUNT") == "1"
              and clone[0]["env"].get("GIT_CONFIG_KEY_0") == "http.extraheader"
              and clone[0]["env"].get("GIT_CONFIG_VALUE_0")
              == f"Authorization: Bearer {TOKEN}", clone[0]["env"])
        check("... and no argument on the clone command line says -c or carries "
              "the token",
              "-c" not in clone[0]["args"]
              and not any(TOKEN in a for a in clone[0]["args"]), clone[0]["args"])
        check("... and the token is in no word of the answer", TOKEN not in text)
        check("... and in NO argument of ANY git call this stage made - the "
              "command line is the thing an outsider can read",
              not any(TOKEN in " ".join(c["args"]) for c in git.calls),
              git.commands())
        check("it fetches the pull request's head into a local branch, then "
              "checks it out",
              any(f"pull/1116/head:refs/heads/fix-pr-1116" in " ".join(c["args"])
                  for c in git.calls)
              and any("checkout fix-pr-1116" in " ".join(c["args"])
                      for c in git.calls), git.commands())
        check("the checked-out branch is named the pull request's own branch",
              any("branch -m fix-pr-1116 feature/tray-icon" in " ".join(c["args"])
                  for c in git.calls), git.commands())
        marker = json.loads((target / ".git" / GH.MARKER_NAME).read_text(
            encoding="utf-8"))
        check("the folder records which pull request it is, with no token",
              marker.get("repo") == "darknight11ish/Epic-Jarvis"
              and marker.get("number") == "1116"
              and marker.get("head_ref") == "feature/tray-icon"
              and marker.get("head_sha") == HEAD_SHA
              and TOKEN not in json.dumps(marker), marker)
        check("the answer names the pull request, title, head commit and folder",
              all(w in text for w in ("#1116", "Fix the tray icon", HEAD_SHA,
                                      str(target))), text[:500])
        check("it shows the failing check with GitHub's annotation",
              "rust: failure" in text and "src/tray.rs:12: unused import" in text,
              text)
        check("... and the end of the job log, read without following the "
              "redirect",
              "mismatched types" in text, text)
        check("a check still running is not called a failure", "audit" not in text,
              text)
        check("it says nothing was pushed and what to do next",
              "Nothing has been pushed." in text and 'stage="push"' in text, text)
        check("the annotation and log evidence are bounded",
              len(text) < 6_000, len(text))


def t_fix_prepare_refuses_a_fork_and_a_protected_branch():
    fork = _pr_doc(head={"sha": HEAD_SHA, "ref": "feature/x",
                         "repo": {"full_name": "someone-else/Epic-Jarvis"}})
    git = FakeGit()
    with _Scratch():
        r = GH.plan_fix_and_push(dict(ARGS["github_fix_and_push"]))
        out = _run_request(r, Routed([("/pulls/1116", (200, fork))]), git=git)
        check("a pull request from a fork is refused, and nothing is cloned",
              out.get("ok") is False and "fork" in out.get("error", "")
              and git.calls == [], (out, git.commands()))
    main = _pr_doc(head={"sha": HEAD_SHA, "ref": "main",
                         "repo": {"full_name": "darknight11ish/Epic-Jarvis"}})
    git = FakeGit()
    with _Scratch():
        r = GH.plan_fix_and_push(dict(ARGS["github_fix_and_push"]))
        out = _run_request(r, Routed([("/pulls/1116", (200, main))]), git=git)
        check("a pull request from a protected branch is refused, nothing cloned",
              out.get("ok") is False and "protected branch" in out.get("error", "")
              and git.calls == [], (out, git.commands()))


def t_a_failed_prepare_removes_its_folder_and_the_next_prepare_works():
    """A failed copy must not leave a folder that blocks every later prepare.

    The failure the owner hit: the clone failed, and the folder it had just made
    stayed behind with no `.git` - so the old `.git`-only refusal did not fire,
    and the next prepare ran `git clone` into a non-empty folder. That is a git
    error that names neither the folder nor the earlier failure, and it never
    clears itself.
    """
    routes = [("/pulls/1116", (200, _pr_doc())),
              ("/check-runs", (200, json.dumps({"check_runs": []})))]
    with _Scratch() as box:
        target = box.root / "darknight11ish__Epic-Jarvis__pr1116"
        r = GH.plan_fix_and_push(dict(ARGS["github_fix_and_push"]))
        broken = FakeGit([("clone", (128, "",
                                     "fatal: could not read from remote"))])
        out = _run_request(r, Routed(routes), git=broken)
        check("a failed clone refuses the prepare", out.get("ok") is False, out)
        check("... and the half-made scratch folder is GONE", not target.exists(),
              str(target))
        # The SAME request, with a git that works: the failure is not sticky.
        again = _run_request(r, Routed(routes), git=FakeGit())
        check("preparing again on the same request works", again.get("ok") is True,
              again)
        check("... and that prepare made the folder and its note",
              target.is_dir() and (target / ".git" / GH.MARKER_NAME).is_file(),
              str(target))


def t_a_pre_existing_scratch_folder_is_refused_and_never_deleted():
    """Any content at the target is refused, and it is not this call's to delete.

    The old guard only looked for `.git`, so the folder a failed clone leaves
    (content, no `.git`) passed the guard and the clone ran into it. A folder
    that holds last time's work must survive the refusal untouched.
    """
    routes = [("/pulls/1116", (200, _pr_doc())),
              ("/check-runs", (200, json.dumps({"check_runs": []})))]
    with _Scratch() as box:
        target = box.root / "darknight11ish__Epic-Jarvis__pr1116"
        target.mkdir(parents=True)
        kept = target / "README.md"
        kept.write_text("the owner's own work from last time", encoding="utf-8")
        r = GH.plan_fix_and_push(dict(ARGS["github_fix_and_push"]))
        git = FakeGit()
        out = _run_request(r, Routed(routes), git=git)
        check("a folder with content but no .git is refused", out.get("ok") is False,
              out)
        check("... and says the folder already exists", "already exists" in
              out.get("error", "").lower(), out.get("error"))
        check("... and nothing was cloned into it", git.commands() == [],
              git.commands())
        check("... and the folder and its file are still there",
              target.is_dir() and kept.is_file()
              and kept.read_text(encoding="utf-8")
              == "the owner's own work from last time", str(target))


def t_the_job_log_redirect_is_allowlisted_and_strips_the_token():
    url = GH.GITHUB_API + "/repos/o/r/actions/jobs/77/logs"
    good = FakeLog(location="https://objects.githubusercontent.com/signed?x=1")
    text, why = GH._job_log(url, TOKEN, open_url=good)
    check("a job log's 302 is read, not followed: the first call carries the token",
          len(good.calls) == 2
          and good.calls[0]["headers"].get("Authorization") == f"Bearer {TOKEN}",
          good.calls)
    check("... and the signed address is fetched with NO Authorization header",
          good.calls[1]["url"] == "https://objects.githubusercontent.com/signed?x=1"
          and "Authorization" not in good.calls[1]["headers"], good.calls[1])
    check("... and its tail is what comes back", "mismatched types" in text, text)
    check("... with no error", why == "", why)

    for bad in ("https://evil.example/log", "http://api.github.com/log",
                "https://githubusercontent.com.evil.example/log",
                "https://api.github.com.evil.example/log"):
        fake = FakeLog(location=bad)
        text, why = GH._job_log(url, TOKEN, open_url=fake)
        check(f"a redirect to {bad!r} is refused in plain words",
              text == "" and "will not fetch" in why, (text, why))
        check(f"... and only the one request was made for {bad!r}",
              len(fake.calls) == 1, fake.calls)
        check(f"... and the token is not in the refusal for {bad!r}",
              TOKEN not in why, why)

    check("the allowlist is https only, and only GitHub's own hosts",
          GH._log_url_allowed("https://api.github.com/x")
          and GH._log_url_allowed("https://github.com/x")
          and GH._log_url_allowed("https://objects.githubusercontent.com/x")
          and not GH._log_url_allowed("http://api.github.com/x")
          and not GH._log_url_allowed("https://evil.example/x")
          and not GH._log_url_allowed(""),
          "allowlist")


def t_a_job_log_read_error_is_not_shown_as_a_log_tail():
    """A log Jarvis could not read is said as a READ error, never as its tail.

    `_failing_evidence` used to put the error sentence in the log field, and the
    renderer printed it under "The end of its log:" - words that claim evidence
    the answer does not have. The two are separate fields now.
    """
    routes = [("/pulls/1116", (200, _pr_doc())),
              ("/check-runs/55/annotations", (200, "[]")),
              ("/check-runs", (200, json.dumps({"check_runs": [
                  {"id": 55, "name": "rust", "status": "completed",
                   "conclusion": "failure",
                   "details_url": "https://github.com/o/r/actions/runs/9/job/77"}]})))]
    with _Scratch():
        r = GH.plan_fix_and_push(dict(ARGS["github_fix_and_push"]))
        out = _run_request(r, Routed(routes), git=FakeGit(),
                           log=FakeLog(location="https://evil.example/log"))
        text = out.get("text", "")
        check("prepare still succeeds when the job log cannot be read",
              out.get("ok") is True, out)
        check("... and says GitHub's job log could not be read",
              "GitHub's job log could not be read:" in text, text)
        check("... and does NOT print the error under 'The end of its log:'",
              "The end of its log:" not in text, text)
        check("... while still naming the failing check", "rust: failure" in text,
              text)


# --------------------------------------------------------------------------
#   14. github_fix_and_push, stage push (2026-11-10)
# --------------------------------------------------------------------------


def t_the_push_card_shows_the_commits_files_and_exact_command():
    with _Scratch() as box:
        folder = _prepared_folder(box.root, checks=[
            {"name": "rust", "conclusion": "failure"}])
        git = _push_git()
        r = GH.plan_fix_and_push({
            "repo": "darknight11ish/Epic-Jarvis", "number": "1116",
            "stage": "push", "worktree": str(folder)}, git=git)
        text = GH.describe(r)
        check("the push card names the branch and the folder",
              "feature/tray-icon" in text and str(folder) in text, text[:400])
        check("... the changed files", "src/tray.rs" in text
              and "README.md" in text, text)
        check("... the commits", "abc1234 fix the tray icon" in text, text)
        check("... the failing check from the prepare evidence",
              "rust (failure)" in text, text)
        check("... and the EXACT command that will run",
              "git push origin HEAD:refs/heads/feature/tray-icon" in text, text)
        check("... and that it never force-pushes or pushes main",
              "force-push" in text.lower() and "main" in text, text)
        check("the request carries the branch and folder the card showed",
              r.head_ref == "feature/tray-icon"
              and r.worktree == os.path.normpath(str(folder))
              and r.fix_stage == "push", (r.head_ref, r.worktree, r.fix_stage))
        check("no push command was RUN while planning", git.pushes() == [],
              git.commands())
        check("the plan opened no socket either (NoSocket is active here)", True)


def t_the_push_plan_refuses_every_unsafe_folder():
    repo = "darknight11ish/Epic-Jarvis"
    args = {"repo": repo, "number": "1116", "stage": "push"}
    with _Scratch() as box:
        good = _prepared_folder(box.root)
        outside = Path(tempfile.mkdtemp(prefix="jarvis-not-scratch-"))
        outside_git = _push_git()

        def refused(why_needle, *, worktree=None, git=None, number="1116",
                    repo_arg=repo):
            g = git or _push_git()
            try:
                GH.plan_fix_and_push(dict(args, repo=repo_arg, number=number,
                                          worktree=str(worktree or outside)),
                                     git=g)
            except GH.GitHubError as exc:
                check(f"{why_needle}: the push is refused at the card",
                      why_needle.lower() in str(exc).lower(), str(exc))
                return
            check(f"{why_needle}: the push is refused at the card", False,
                  "it was planned")

        refused("not inside", worktree=outside)
        refused("commit your fix first", worktree=good,
                git=_push_git(status=" M src/tray.rs\n"))
        (box.root / "darknight11ish__Epic-Jarvis__pr2222").mkdir()
        (box.root / "darknight11ish__Epic-Jarvis__pr2222" / "README.md").write_text(
            "x", encoding="utf-8")
        refused("not prepared by github_fix_and_push",
                worktree=box.root / "darknight11ish__Epic-Jarvis__pr2222")
        other = _prepared_folder(box.root, number="9999")
        refused("different pull request", worktree=other)
        refused("on branch", worktree=good,
                git=_push_git(branch="somewhere-else"))
        refused("nothing to push", worktree=good, git=_push_git(commits=""))
        refused("key, a password or a token", worktree=good,
                git=_push_git(files="src/tray.rs\n.env\n"))
        refused("full path", worktree="relative/folder")
        r = GH.plan_fix_and_push(dict(args, worktree=str(good)), git=_push_git())
        check("the same folder with a clean tree plans a push",
              r.fix_stage == "push" and r.head_ref == "feature/tray-icon")
        # A protected branch recorded in the marker can never be pushed to.
        # (This rewrites the same folder's marker, so it is checked LAST.)
        protected = _prepared_folder(box.root, number="1116",
                                     head_ref="release/1.2")
        refused("protected branch", worktree=protected,
                git=_push_git(branch="release/1.2"))
        shutil.rmtree(outside, ignore_errors=True)


def t_the_push_run_rechecks_everything_then_pushes_once():
    repo = "darknight11ish/Epic-Jarvis"
    with _Scratch() as box:
        folder = _prepared_folder(box.root)
        git = _push_git(push=(0, "To github.com:darknight11ish/Epic-Jarvis.git\n"
                                 "   abc1234..def5678  HEAD -> feature/tray-icon\n", ""))
        r = GH.plan_fix_and_push({"repo": repo, "number": "1116",
                                  "stage": "push", "worktree": str(folder)},
                                 git=git)
        fake = Routed([("/pulls/1116", (200, _pr_doc()))])
        out = _run_request(r, fake, git=git)
        check("the push succeeds", out.get("ok") is True, out)
        check("... exactly ONE push command ran", len(git.pushes()) == 1,
              git.commands())
        push = git.pushes()[0]
        check("... and it is exactly the command the card showed",
              push["args"] == ["push", "origin",
                               "HEAD:refs/heads/feature/tray-icon"], push["args"])
        check("... run inside the scratch folder",
              os.path.normcase(os.path.abspath(push["cwd"]))
              == os.path.normcase(os.path.abspath(str(folder))), push["cwd"])
        check("the token is passed in the ENVIRONMENT, never the command line",
              push["env"].get("GIT_CONFIG_COUNT") == "1"
              and push["env"].get("GIT_CONFIG_KEY_0") == "http.extraheader"
              and push["env"].get("GIT_CONFIG_VALUE_0")
              == f"Authorization: Bearer {TOKEN}", push["env"])
        check("... and is in none of the push arguments",
              not any(TOKEN in a for a in push["args"]), push["args"])
        check("... and no word of the answer prints it",
              TOKEN not in json.dumps(out), out)
        check("it re-read the pull request before pushing",
              fake.calls and fake.calls[0]["url"].endswith("/pulls/1116"),
              fake.urls())
        check("... and sent nothing except that read",
              fake.writes() == [], fake.calls)

        # THE REFUSALS, each re-checked at the run stage.
        cases = []
        moved = _pr_doc(head={"sha": HEAD_SHA, "ref": "other-branch",
                              "repo": {"full_name": repo}})
        cases.append(("a branch that moved since the card", moved, None,
                      "nothing was pushed"))
        cases.append(("a pull request that is closed",
                      _pr_doc(state="closed"), None, "closed"))
        for name, pr_body, _unused, needle in cases:
            g = _push_git()
            r2 = GH.plan_fix_and_push({"repo": repo, "number": "1116",
                                       "stage": "push",
                                       "worktree": str(folder)}, git=g)
            out2 = _run_request(r2, Routed([("/pulls/1116", (200, pr_body))]), git=g)
            check(f"{name}: refused at the run stage",
                  out2.get("ok") is False
                  and needle.lower() in out2.get("error", "").lower(), out2)
            check(f"{name}: ... and nothing was pushed", g.pushes() == [],
                  g.commands())

        # A credential file that appeared after the card was shown.
        g = _push_git(files="src/tray.rs\ncredentials.json\n")
        r3 = GH.plan_fix_and_push({"repo": repo, "number": "1116",
                                   "stage": "push", "worktree": str(folder)},
                                  git=_push_git())
        out3 = _run_request(r3, Routed([("/pulls/1116", (200, _pr_doc()))]), git=g)
        check("a credential file in the changed files stops the push",
              out3.get("ok") is False
              and "password or a token" in out3.get("error", ""), out3)
        check("... and nothing was pushed", g.pushes() == [], g.commands())

        # The folder moved outside the scratch root after the card was shown.
        g = _push_git()
        r4 = GH.plan_fix_and_push({"repo": repo, "number": "1116",
                                   "stage": "push", "worktree": str(folder)},
                                  git=g)
        with _Scratch() as elsewhere:
            out4 = _run_request(r4, Routed([("/pulls/1116", (200, _pr_doc()))]), git=g)
            check("a folder outside the scratch root cannot be pushed from",
                  out4.get("ok") is False
                  and "not inside" in out4.get("error", ""), (out4, elsewhere.root))
        check("... and nothing was pushed", g.pushes() == [], g.commands())

        # A git failure is a plain sentence, and it never claims success.
        g = _push_git(push=(1, "", "remote: Permission to o/r.git denied"))
        r5 = GH.plan_fix_and_push({"repo": repo, "number": "1116",
                                   "stage": "push", "worktree": str(folder)},
                                  git=g)
        out5 = _run_request(r5, Routed([("/pulls/1116", (200, _pr_doc()))]), git=g)
        check("a refused git push says so plainly and claims nothing",
              out5.get("ok") is False
              and "nothing was pushed" in out5.get("error", "").lower()
              and "Permission" in out5.get("error", ""), out5)
        check("... and no HTTP code is in the git failure",
              not re.search(r"\b(?:HTTP|40[0-9]|500)\b", out5.get("error", "")),
              out5)

        # The matching 409 for a push: the branch moved on GitHub since prepare,
        # so git refuses as non-fast-forward. Never forced over, and the answer
        # says to prepare again from the new head.
        g = _push_git(push=(1, "", "! [rejected] feature/tray-icon -> "
                                  "feature/tray-icon (non-fast-forward)\n"
                                  "error: failed to push some refs to "
                                  "'https://github.com/o/r.git'\n"
                                  "hint: Updates were rejected because the tip of "
                                  "your current branch is behind\n"))
        r6 = GH.plan_fix_and_push({"repo": repo, "number": "1116",
                                   "stage": "push", "worktree": str(folder)},
                                  git=g)
        out6 = _run_request(r6, Routed([("/pulls/1116", (200, _pr_doc()))]), git=g)
        check("a non-fast-forward push is refused in the branch-moved words",
              out6.get("ok") is False
              and "branch moved on GitHub since this fix was prepared"
              in out6.get("error", ""), out6)
        check("... it says nothing was pushed and to prepare again",
              "nothing was pushed" in out6.get("error", "").lower()
              and "prepare the fix again" in out6.get("error", "").lower(), out6)
        check("... and it never builds a force/delete/mirror flag",
              not any(flag in " ".join(c["args"]) for c in g.calls
                      for flag in GH.BANNED_GIT_FLAGS), g.commands())
        check("... and it never reports the push as done",
              "Pushed " not in out6.get("error", ""), out6)

        # The token is in NO argument of ANY git call in either stage: the command
        # line is the thing `Get-CimInstance Win32_Process` / ps can read.
        check("the token is in no argument of any git call in this whole block",
              not any(TOKEN in " ".join(c["args"]) for c in git.calls),
              [c["args"] for c in git.calls if TOKEN in " ".join(c["args"])])
        check("... and the push itself carried it in the environment",
              all(c["env"].get("GIT_CONFIG_VALUE_0") ==
                  f"Authorization: Bearer {TOKEN}" for c in git.calls
                  if c["args"][:1] == ["push"]), git.calls[-1] if git.calls else {})


def t_fix_and_push_run_refuses_unapproved_and_unknown_stages():
    r = GH.plan_fix_and_push(dict(ARGS["github_fix_and_push"]))
    check("prepare: without a person's yes nothing is sent",
          GH.run(r, approved=False).get("error") == "not approved; nothing was sent")
    import dataclasses
    bad = dataclasses.replace(r, fix_stage="")
    with _Token():
        out = GH.run(bad, fetch=Fake(200, "{}"), approved=True)
    check("an unknown fix stage sends nothing and says so",
          out.get("ok") is False and "which half" in out.get("error", ""), out)
    check("the two fields exist, documented, on Request",
          all(name in GH.Request.__dataclass_fields__
              for name in ("cockpit", "expected_sha", "fix_stage", "head_ref",
                           "worktree")), sorted(GH.Request.__dataclass_fields__))


# --------------------------------------------------------------------------
#   15. both twins, byte for byte
# --------------------------------------------------------------------------


def t_the_twins_are_byte_identical():
    names = ("jarvis_github.py", "jarvis_agent.py", "jarvis_quick.py",
             "jarvis_accounts.py", "jarvis_tool_profiles.py", "jarvis_reach.py",
             "jarvis_claims.py", "jarvis_card_words.py", "jarvis_asks_first.py",
             "jarvis_owner_check.py", "jarvis_connect_account.py",
             "jarvis_feature_catalogue.py")
    for name in names:
        here = HERE / name
        twin = REPO / "jarvis-backend" / name
        if not here.is_file() or not twin.is_file():
            check(f"{name}: both copies exist", False, str(here))
            continue
        check(f"{name}: the two copies are byte-identical",
              here.read_bytes() == twin.read_bytes(), name)


# --------------------------------------------------------------------------
#   16. the shipped tiers and the two new switches, from both copies
# --------------------------------------------------------------------------


def t_the_two_shipped_tomls_are_one_file():
    a, b = TOMLS[0].read_bytes(), TOMLS[1].read_bytes()
    check("backend/rebuilt's framework file and the base's are byte-identical",
          a == b, (len(a), len(b)))
    check("the base's copy carries the two new ask lines",
          b'github_merge_pr           = "ask"' in b
          and b'github_fix_and_push       = "ask"' in b, "missing")


if __name__ == "__main__":
    print(f"  file  {HERE / 'jarvis_github.py'}")
    print(f"  file  {GATE_BASE}")
    print(f"  logs  {os.environ['JARVIS_LOG_DIR']}")
    with NoSocket():
        for fn in (t_only_api_github_com,
                   t_a_redirect_is_refused,
                   t_the_scopes_are_closed_and_names_are_checked,
                   t_the_token_never_appears_in_any_output,
                   t_a_read_with_no_token_says_connect_github_and_raises_no_card,
                   t_each_action_is_one_card_naming_what_it_does,
                   t_the_reads_ask_too_and_never_write,
                   t_a_refused_token_is_a_plain_sentence,
                   t_the_ci_answer_tells_the_truth_about_logs,
                   t_nothing_private_is_ever_sent,
                   t_merge_and_push_exist_only_behind_their_own_cards,
                   t_no_squash_rebase_admin_or_force_path_exists,
                   t_the_patch_applies_and_reverses_byte_for_byte,
                   t_the_gate_knows_the_ten_tools_and_six_actions,
                   t_every_tier_is_ask_and_the_tables_are_joined,
                   t_a_file_read_shows_the_files_text_not_the_envelope,
                   t_the_answer_is_bounded_and_unapproved_runs_send_nothing,
                   t_create_repo_is_one_carded_call_before_any_network,
                   t_create_repo_body_is_exactly_what_the_card_showed,
                   t_create_repo_never_prints_the_token,
                   t_create_repo_201_reports_only_what_github_answered,
                   t_create_repo_failures_are_githubs_own_words_without_the_token,
                   t_create_repo_has_no_auto_approve_or_bulk_path,
                   t_pr_scan_classifies_each_open_pull_request,
                   t_pr_scan_refuses_a_failed_read_plainly,
                   t_the_merge_card_names_the_pinned_commit_and_the_exact_body,
                   t_merge_refuses_everything_but_a_clean_unmoved_green_pull_request,
                   t_merge_sends_exactly_the_pinned_body_once,
                   t_a_merge_answered_without_a_result_is_not_claimed_as_done,
                   t_a_refused_merge_is_refused_in_the_words_its_cause_deserves,
                   t_fix_prepare_copies_the_pr_into_its_own_scratch_folder,
                   t_fix_prepare_refuses_a_fork_and_a_protected_branch,
                   t_a_failed_prepare_removes_its_folder_and_the_next_prepare_works,
                   t_a_pre_existing_scratch_folder_is_refused_and_never_deleted,
                   t_the_job_log_redirect_is_allowlisted_and_strips_the_token,
                   t_a_job_log_read_error_is_not_shown_as_a_log_tail,
                   t_the_push_card_shows_the_commits_files_and_exact_command,
                   t_the_push_plan_refuses_every_unsafe_folder,
                   t_the_push_run_rechecks_everything_then_pushes_once,
                   t_fix_and_push_run_refuses_unapproved_and_unknown_stages,
                   t_the_twins_are_byte_identical,
                   t_the_two_shipped_tomls_are_one_file):
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
