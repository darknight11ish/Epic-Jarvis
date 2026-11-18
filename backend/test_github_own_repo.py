#!/usr/bin/env python3
"""test_github_own_repo.py - Jarvis uses the repository it already knows.

    python3 backend/test_github_own_repo.py

WHY THIS EXISTS. The measured failure, on the owner's live PC, 2026-11-18
17:20:53Z. The owner asked in chat:

    "What are my open pull requests on Epic-Jarvis?"

and the model DID call the tool. `~/.openjarvis/logs/jarvis-2026-11-18.jsonl`
carries the turn's own `agent.chain` line:

    {"turn": "ad2bf42c721a4729a515c2e03b585725",
     "steps": [{"tool": "github_list", "ran": false, "ok": false,
                "outcome": "unknown"}]}

`outcome: "unknown"` and `ran: false` are the signature of `_one_call`'s
prepare-time exception branch: the planner refused the arguments before
anything was sent. It had passed the BARE repository name "Epic-Jarvis" (the
exact word from the request), and `jarvis_github._check_repo` refused anything
without an owner. The model then relayed that as a question to the owner:

    "I need the full repository name in the format `owner/name`. Could you tell
     me who owns the Epic-Jarvis repository?"

The answer was in the program: `jarvis_github.OWN_REPO` is
`darknight11ish/Epic-Jarvis`, and its own comment says the name matches
case-insensitively. Nothing should have asked the owner who owns his own repo.

WHAT THIS SUITE PROVES, all read-only and with no network and no real token:

  1. the resolver (`jarvis_github.repo_from_words`, used by `_check_repo`)
     turns the bare name, the case variants, and the self phrases ("my repo",
     "my open PRs", "this repository") into `darknight11ish/Epic-Jarvis`;
  2. every GitHub planner that names a repository gets the full one when the
     model passed only the bare name - reads and writes alike;
  3. the owner's exact sentence, with the bare name the model really passed,
     runs `github_list` against his own repository, raises NO approval card
     (reads are card-free), and puts NO ask in front of the owner: one tool
     call, one result, nothing asked twice;
  4. "my open PRs", "my repo" and "this repository" do the same when the model
     leaves the repository out entirely - the tool layer fills it from the
     owner's OWN newest words (`jarvis_agent._github_repo_call`);
  5. a repository that is NOT the owner's is NEVER replaced by his: an
     explicit foreign name passes through unchanged, and when no repository is
     given the existing ask/refusal is exactly what it was;
  6. every GitHub tool whose schema has a `repo` argument carries the sentence
     that says a bare name is fine and Jarvis fills in the owner - the 2026-11-18
     instruction lives in the tool's own description, not in the lane prompt;
  7. a write planned from the bare name shows the FULL name on its card, and a
     read's plan is otherwise byte-for-byte what the full name produced.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-github-own-repo-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ.pop("JARVIS_BACKEND", None)
os.environ.pop("OLLAMA_URL", None)
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_github.py")

import jarvis_agent as AG  # noqa: E402
import jarvis_github as GH  # noqa: E402

PASSED, FAILED = [], []

#: A token distinctive enough that finding it anywhere is a leak, and shaped
#: like the real thing so nothing can pass by being "not token-like".
TOKEN = "ghp_TESTONLYnotarealtoken0000000000000000"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"

OWN = GH.OWN_REPO
FOREIGN = "some-other-org/widgets"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class NoSocket:
    """Refuses every real socket, for the whole run: no real GitHub call."""

    def __enter__(self):
        self._socket = socket.socket
        self._pair = socket.socketpair

        def refuse(*_a, **_k):
            raise AssertionError("this suite must never open a socket")

        socket.socket = refuse
        socket.socketpair = refuse
        return self

    def __exit__(self, *_exc):
        socket.socket = self._socket
        socket.socketpair = self._pair
        return False


class _Token:
    """The saved GitHub token, for one block - the token store is never read."""

    def __init__(self):
        self.value = TOKEN

    def __enter__(self):
        self._was = GH._token
        GH._token = lambda: self.value
        return self

    def __exit__(self, *_exc):
        GH._token = self._was
        return False


class FakeGitHub:
    """The injected HTTP fake: the target gate's two reads, then the answer.

    Since 2026-11-17 every request is put through the Q5 target gate first - a
    `GET /repos/{owner}/{name}` for the repository - so the fake answers those
    its own way and answers the request under test with `status`/`body`.
    `calls` records every address, which is how these tests prove WHICH
    repository was really read.
    """

    ROOT = re.compile(r"^https://api\.github\.com/repos/([^/]+)/([^/]+)$")

    def __init__(self, status=200, body="[]", missing=(), routes=()):
        self.status = status
        self.body = body
        self.calls = []
        self.missing = {m.lower() for m in missing}
        #: (address substring, (status, body)) pairs, answered before the
        #: default `status`/`body`, for the questions that read several things.
        self.routes = list(routes)

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {})})
        root = self.ROOT.match(url.split("?")[0])
        if root:
            repo = f"{root.group(1)}/{root.group(2)}"
            if repo.lower() in self.missing:
                return 404, json.dumps({"message": "Not Found"})
            return 200, json.dumps({"full_name": repo,
                                    "permissions": {"push": True}})
        for needle, answer in self.routes:
            if needle in url:
                return answer
        return self.status, self.body

    def urls(self):
        return [c["url"] for c in self.calls]

    def repos(self):
        """Every `owner/name` a request was sent about, in order."""
        seen = []
        for url in self.urls():
            m = re.search(r"/repos/([^/]+)/([^/?]+)", url)
            if m:
                name = f"{m.group(1)}/{m.group(2)}"
                if name not in seen:
                    seen.append(name)
        return seen


class _Verdict:
    """What the gate answers for a READ at its shipped "auto" tier."""

    allowed = True
    reason = ""
    request_id = "r1"
    tier = "auto"
    outcome = "auto"

    def __init__(self, action):
        self.action = action


class _Gate:
    """The turn's gate seam: records the action, raises NO card for a read."""

    def __init__(self):
        self.asked = []

    def __call__(self, action, detail, prompt):
        self.asked.append((action, detail.get("text", "")))
        return _Verdict(action)


class _Out:
    """The one writer to the app, reduced to what one tool call touches."""

    gone = False

    def __init__(self):
        self.status = None

    def set_status(self, word):
        self.status = word

    def card_answered(self, verdict):
        pass


def _one_call(name, args, user, *, fetch=None):
    """Drive ONE real tool call through `jarvis_agent._one_call`, faked.

    Everything the turn does is the real code: `_github_repo_call`, the schema
    check, `prepare()`, the gate call, `jarvis_github.run()`. Only three seams
    are stand-ins - the model's tool call (this dict), the gate (a fake that
    answers "auto"), and the HTTP (FakeGitHub, injected as
    `_default_fetch_full`). The owner's own words are the real `_TurnWatch`.
    """
    fetch = fetch or FakeGitHub()
    gate = _Gate()
    convo, steps = [], []
    watch = AG._TurnWatch(
        [{"role": "user", "content": user}],
        request={"conversation_id": "conv-own-repo",
                 "messages": [{"role": "user", "content": user,
                               "provenance": "typed"}]})
    call = {"id": "c1",
            "function": {"name": name, "arguments": json.dumps(args)}}
    with _Token():
        real_fetch = GH._default_fetch_full
        GH._default_fetch_full = fetch
        try:
            AG._one_call(call, [name], convo, steps, gate, None, _Out(),
                         lambda *_a, **_k: None, watch=watch)
        finally:
            GH._default_fetch_full = real_fetch
    result = None
    if convo:
        try:
            result = json.loads(convo[-1]["content"])
        except (TypeError, ValueError):
            result = {"raw": convo[-1].get("content")}
    return fetch, gate, steps, result, watch


# --------------------------------------------------------------------------
#   1. The resolver: the owner's own repository, named in his own words
# --------------------------------------------------------------------------

def t_the_owners_own_repository_is_named_in_his_own_words():
    """The bare name and every self phrase resolve; nothing else is touched.

    BEFORE THIS CHANGE: `GH.repo_from_words` did not exist, and
    `GH._check_repo("Epic-Jarvis")` raised `GitHubError` ("needs a repository
    named like owner/name") - the exact refusal the live turn relayed to the
    owner as a question.
    """
    check("OWN_REPO is the published repository", OWN == "darknight11ish/Epic-Jarvis",
          OWN)
    check("OWN_REPO_NAME is its name without the owner",
          GH.OWN_REPO_NAME == "Epic-Jarvis", GH.OWN_REPO_NAME)
    for said in ("Epic-Jarvis", "epic-jarvis", "EPIC-JARVIS", "Epic Jarvis",
                 "EpicJarvis", "the Epic-Jarvis repo", "the epic jarvis repository",
                 "darknight11ish/Epic-Jarvis", "darknight11ish/epic-jarvis"):
        check(f"the bare name {said!r} is the owner's own repository",
              GH.repo_from_words(said) == OWN, GH.repo_from_words(said))
    for said in ("my repo", "my repository", "my own repo", "my own repository",
                 "my GitHub repo", "my GitHub repository",
                 "this repo", "this repository", "this project's repo",
                 "my open PRs", "my open pull requests", "my PRs",
                 "my issues", "our repository"):
        check(f"the self phrase {said!r} is the owner's own repository",
              GH.repo_from_words(said) == OWN, GH.repo_from_words(said))
    # The owner's exact sentence, verbatim, at the layer that changed.
    sentence = "What are my open pull requests on Epic-Jarvis?"
    check("the owner's exact sentence resolves to the full name",
          GH.repo_from_words(sentence) == OWN, GH.repo_from_words(sentence))
    check("... and _check_repo returns it, so no planner can ask",
          GH._check_repo("Epic-Jarvis") == OWN, GH._check_repo("Epic-Jarvis"))
    # A FULL name that is not the owner's is never replaced by his.
    check("a foreign full name is left exactly as typed",
          GH.repo_from_words(FOREIGN) == "", GH.repo_from_words(FOREIGN))
    check("... and the words naming it are left alone too",
          GH.repo_from_words("what are the open PRs on some-other-org/widgets") == "",
          GH.repo_from_words("..."))
    check("... even beside a self phrase (an explicit name wins)",
          GH.repo_from_words("my PRs on some-other-org/widgets") == "",
          GH.repo_from_words("my PRs on some-other-org/widgets"))
    # And a name that is nothing at all never becomes the owner's.
    for junk in ("", "   ", "widgets", "a/b/c", "owner/../etc"):
        check(f"{junk!r} does not resolve to the owner's repository",
              GH.repo_from_words(junk) != OWN, GH.repo_from_words(junk))


# --------------------------------------------------------------------------
#   2. Every repository-naming planner gets the FULL name from the bare one
# --------------------------------------------------------------------------

#: One row per planner that names a repository (2026-11-18: 15 of them; the
#: fix-and-push and open-a-PR stages are checked below, because their prepare
#: stages touch a local folder/GitHub by design).
PLANS = {
    "github_list": (GH.plan_list, {"scope": "pulls"}),
    "github_list(issues)": (GH.plan_list, {"scope": "issues"}),
    "github_read_file": (GH.plan_read_file, {"path": "README.md"}),
    "github_ci_status": (GH.plan_ci, {"branch": "main"}),
    "github_comment": (GH.plan_comment,
                       {"number": "7", "body": "Thanks - done."}),
    "github_open_issue": (GH.plan_open_issue, {"title": "The tray icon stays"}),
    "github_rerun_workflow": (GH.plan_rerun, {"run_id": "9"}),
    "github_pr_scan": (GH.plan_scan_prs, {}),
    "github_pr_detail": (GH.plan_pr_detail, {"number": "7"}),
    "github_merge_pr": (GH.plan_merge_pr,
                        {"number": "7", "head_sha": HEAD_SHA, "title": "Fix",
                         "base_ref": "main"}),
    "github_workflow": (GH.plan_workflow, {"run_id": "9", "action": "cancel"}),
    "github_issue_labels": (GH.plan_issue_labels,
                            {"number": "7", "add": ["bug"]}),
    "github_edit_pr": (GH.plan_edit_pr,
                       {"number": "7", "title": "New", "old_title": "Old"}),
    "github_pr_review": (GH.plan_pr_review,
                         {"number": "7", "event": "COMMENT", "body": "ok"}),
    "github_issue_state": (GH.plan_issue_state,
                           {"number": "7", "action": "close", "title": "T"}),
}


def t_a_bare_owner_name_reaches_every_github_planner():
    """The bare name is resolved by every planner, not only the chat path.

    BEFORE THIS CHANGE: every one of these raised `GitHubError` on
    "Epic-Jarvis", because `_check_repo` demanded `owner/name`.
    """
    for label, (planner, extra) in PLANS.items():
        args = dict(extra, repo="Epic-Jarvis")
        try:
            r = planner(args)
        except Exception as exc:                  # noqa: BLE001 - reported below
            check(f"{label}: the bare name plans the owner's repository", False,
                  f"raised {type(exc).__name__}: {exc}")
            continue
        check(f"{label}: the bare name plans the owner's repository",
              r.repo == OWN and all(OWN in u or "/repos/" not in u for u in r.urls()),
              (r.repo, r.urls()))
    # The two stages whose prepare() then reads a folder/GitHub: the FIRST
    # thing they do is resolve the repository, so with the bare name they get
    # past that and refuse about the folder (a different, honest failure).
    for label, planner, args in (
            ("github_open_pr", GH.plan_open_pr,
             {"base": "main", "branch": "jarvis/new-feature"}),
            ("github_fix_and_push", GH.plan_fix_and_push,
             {"stage": "write", "number": "7", "path": "README.md"})):
        try:
            planner(dict(args, repo="Epic-Jarvis"))
        except GH.GitHubError as exc:
            words = str(exc)
            check(f"{label}: the bare name is resolved before the folder is read",
                  "owner/name" not in words, words[:200])
        except Exception as exc:                  # noqa: BLE001 - network etc
            check(f"{label}: the bare name is resolved before the folder is read",
                  False, f"raised {type(exc).__name__}: {exc}")
        else:
            check(f"{label}: the bare name is resolved before the folder is read",
                  True)


# --------------------------------------------------------------------------
#   3. The measured failure, end to end: no question, no card, his own repo
# --------------------------------------------------------------------------

def t_the_owners_exact_sentence_reads_his_own_pull_requests():
    """The live turn, reproduced: the model passes the bare name the owner said.

    BEFORE THIS CHANGE: `gh._one_call` recorded `{"tool": "github_list", "ran":
    false, "ok": false, "outcome": "unknown"}` and the model's next words were
    the question "who owns the Epic-Jarvis repository?" (the live log line this
    suite's docstring quotes). Here the tool must RUN: one target-gate GET on
    the owner's repository, one GET of its open pull requests, a result with no
    error, NO card, and NO ask in the result.
    """
    sentence = "What are my open pull requests on Epic-Jarvis?"
    fetch, gate, steps, result, watch = _one_call(
        "github_list", {"scope": "pulls", "repo": "Epic-Jarvis"}, sentence)
    check("the tool actually RAN for the owner's own sentence",
          steps == [{"tool": "github_list", "ran": True, "ok": True,
                     "outcome": "auto"}], steps)
    check("... its result has no error and no question",
          isinstance(result, dict) and result.get("ok") is True,
          result)
    check("... and it names no requested repository in the result",
          isinstance(result, dict) and not result.get("error"), result)
    check("... the repository read is the owner's FULL name",
          [r for r in fetch.repos() if r.lower() == OWN.lower()] == [OWN],
          fetch.repos())
    check("... it read exactly his open pull requests",
          any(u.endswith(f"/repos/{OWN}/pulls?state=open&per_page=20")
              for u in fetch.urls()), fetch.urls())
    check("... NO approval card was raised (a read is card-free)",
          watch.cards == 0 and [a for a, _t in gate.asked] == ["github_list"],
          (watch.cards, gate.asked))
    check("... and nothing was put to the owner as a question",
          isinstance(result, dict)
          and "own" not in str(result.get("error", "")).lower()
          and result.get("ok") is True, result)


def t_the_read_tiers_are_auto_in_the_shipped_config():
    """The read is card-free because the shipped tiers say so, and they still do.

    `github_inspect` is the tier every GitHub READ tool is decided under, and
    `github_read` is the scheduled "tell me when" look; BOTH ship "auto", and
    the `[tools].enabled` line is what switches the tools on. A read must not
    ask: nothing here changes a card, and the shipped files are the ground.
    """
    for toml_path in (HERE / "rebuilt" / "jarvis-framework.toml",
                      REPO / "jarvis-backend" / "jarvis-framework.toml"):
        block = toml_path.read_text(encoding="utf-8").split("[autonomy.tiers]", 1)[-1]
        for action in ("github_inspect", "github_read"):
            check(f"{toml_path.name}: {action} ships auto (no card for a read)",
                  re.search(rf'(?m)^{action}\s*=\s*"auto"', block) is not None,
                  action)


def t_my_open_prs_my_repo_and_this_repository_fill_the_repository_in():
    """When the owner names no repository at all, his own words fill it in.

    This is `jarvis_agent._github_repo_call`: the model cannot pass a repository
    the owner never said, so the tool layer reads the owner's OWN newest words
    through the same resolver. BEFORE THIS CHANGE: there was no such fill, and
    `github_list` with no `repo` raised the "could not tell which repository"
    ask (or, for a tool that requires the field, a schema refusal) - a question
    to the owner whose answer was already in the program.
    """
    for user in ("what are my open PRs?",
                 "show me my repo",
                 "what is open on this repository?",
                 "list my pull requests on GitHub"):
        fetch, gate, steps, result, watch = _one_call(
            "github_list", {"scope": "pulls"}, user)
        check(f"{user!r}: the tool ran on the owner's own repository",
              steps and steps[0]["ran"] is True
              and isinstance(result, dict) and result.get("ok") is True,
              (steps, result))
        check(f"{user!r}: ... reading the FULL name, nothing asked",
              fetch.repos() == [OWN] and not (result or {}).get("error"),
              (fetch.repos(), result))
        check(f"{user!r}: ... with no approval card raised",
              watch.cards == 0, watch.cards)
    # A sentence that names a repository in full is NOT one of these: the tool
    # keeps exactly the behaviour it has today (see the control below).


# --------------------------------------------------------------------------
#   4. The control: a foreign repository is NEVER replaced by the owner's
# --------------------------------------------------------------------------

def t_a_foreign_repository_is_never_replaced_by_the_owners():
    """A name that is not the owner's keeps today's refusal/behaviour.

    The owner's 2026-11-17 Q5 ruling ("a GitHub target GitHub does not report is
    REFUSED, never substituted",
    `decisions.d/2026-11-17-github-targets-must-exist.md`) is the reason: a
    wrong-repo answer is worse than a question. This suite's change resolves
    ONLY `OWN_REPO`; a foreign name is not returned by the resolver at all.
    """
    # 1. A foreign FULL name is untouched: the planner names that repository.
    r = GH.plan_list({"scope": "pulls", "repo": FOREIGN})
    check("a foreign full name plans that repository, not the owner's",
          r.repo == FOREIGN and any(f"/repos/{FOREIGN}/pulls" in u
                                    for u in r.urls()),
          (r.repo, r.urls()))
    # 2. And an end-to-end read of it reads THAT repository, never the owner's.
    fetch, _gate, steps, result, _watch = _one_call(
        "github_list", {"scope": "pulls", "repo": FOREIGN},
        "what are the open PRs on some-other-org/widgets")
    check("the foreign read sends nothing about the owner's repository",
          OWN not in fetch.repos(), fetch.repos())
    check("... and it really read the foreign one",
          FOREIGN in fetch.repos() and steps[0]["ran"] is True,
          (fetch.repos(), steps))
    check("... so the substitution never happened", result.get("ok") is True,
          result)
    # 3. A name with no owner at all is refused with EXACTLY today's words -
    #    not resolved to the owner's repository.
    try:
        GH._check_repo("widgets")
    except GH.GitHubError as exc:
        words = str(exc)
        check("a bare name that is not his own is refused as today",
              words == ('Jarvis needs a repository named like "owner/name" '
                        "(letters, numbers, dot, dash and underscore only)."),
              words)
    else:
        check("a bare name that is not his own is refused as today", False,
              "it was accepted")
    # 4. When the owner named a foreign repository and the model left the field
    #    out, the resolver must NOT fill in his own: today's ask stays.
    fetch, _gate, steps, result, watch = _one_call(
        "github_list", {"scope": "pulls"},
        "what are the open PRs on some-other-org/widgets")
    check("a foreign request with no repository field is ASKED, not filled",
          result and result.get("ok") is False
          and "repository" in str(result.get("error", "")).lower(),
          result)
    check("... nothing was sent, so no wrong repository was read",
          fetch.calls == [] and fetch.repos() == [], fetch.calls)
    check("... and no card was raised for it", watch.cards == 0, watch.cards)


# --------------------------------------------------------------------------
#   5. The tool descriptions: the model is told it may pass the bare name
# --------------------------------------------------------------------------

def t_every_github_tool_with_a_repository_says_it_may_be_bare():
    """The "call it, do not ask first" sentence lives in the tool's description.

    `docs/ARCHITECTURE.md` ("An explicit action request reaches its gating
    tool") is the rule: the instruction is in the tool's own description, NOT
    in `jarvis_agent.LANE_SYSTEM`. This is the sentence a 9B model needs in
    front of it - the measured failure was the model asking the owner instead
    of passing the name it already had.
    """
    hint = AG.GITHUB_REPO_ARG_HINT
    check("the hint sentence exists and is not empty", bool(hint), repr(hint))
    for needle in ("Epic-Jarvis", "my repo", "this repository", "do not ask"):
        check(f"the hint says {needle!r}", needle in hint, hint)
    check("... and the hint comes from jarvis_github, beside the resolver",
          hint == GH.REPO_ARG_HINT)
    check("... it is NOT in the lane system prompt (the documented rule)",
          hint not in AG.LANE_SYSTEM)
    repo_tools = [n for n in AG.GITHUB_TOOLS
                  if "repo" in (AG.TOOLS[n].parameters.get("properties") or {})]
    check("there really are GitHub tools that take a repository",
          len(repo_tools) >= 15, repo_tools)
    for name in repo_tools:
        described = AG.TOOLS[name].schema(["github_list"])["function"]["description"]
        check(f"{name}: its description says a bare name is fine",
              hint in described, described[-220:])
    for name in ("github_create_repo", "github_search"):
        check(f"{name}: names no repository to read, so it does not carry it",
              hint not in AG.TOOLS[name].description)


# --------------------------------------------------------------------------
#   6. A write's card shows the full name; a read's plan is otherwise unchanged
# --------------------------------------------------------------------------

def t_a_write_card_names_the_full_repository():
    """Every path benefits: a WRITE planned from the bare name shows the full one.

    The card is where a wrong repository would be visible, and this is why the
    resolution is safe for writes: the resolved name is what the card shows and
    what `run()` then checks against GitHub (Q5). BEFORE THIS CHANGE: the same
    prepare raised instead of producing a card.
    """
    cases = {
        "github_comment": {"number": "7", "body": "Thanks - done."},
        "github_open_issue": {"title": "The tray icon stays"},
        "github_rerun_workflow": {"run_id": "9"},
        "github_merge_pr": {"number": "7", "head_sha": HEAD_SHA,
                            "title": "Fix", "base_ref": "main"},
        "github_issue_labels": {"number": "7", "add": ["bug"]},
    }
    with _Token():
        for name, extra in cases.items():
            args = dict(extra, repo="Epic-Jarvis")
            try:
                r, text = AG.TOOLS[name].prepare(args)
            except Exception as exc:              # noqa: BLE001 - reported
                check(f"{name}: the bare name becomes a card", False,
                      f"raised {type(exc).__name__}: {exc}")
                continue
            check(f"{name}: the bare name becomes a card",
                  r.repo == OWN and OWN in text, (r.repo, text[:160]))
            check(f"{name}: nothing about the owner's name was asked",
                  'owner/name"' not in text and "needs a repository" not in text,
                  text[:200])


def t_a_read_plan_is_unchanged_apart_from_the_name():
    """Resolving the bare name changes the name only - never the read itself."""
    full = GH.plan_list({"scope": "pulls", "repo": OWN})
    bare = GH.plan_list({"scope": "pulls", "repo": "epic-jarvis"})
    check("the bare name plans the SAME repository", full.repo == bare.repo == OWN,
          (full.repo, bare.repo))
    check("... the SAME requests, method and address",
          [(s.method, s.path) for s in full.steps]
          == [(s.method, s.path) for s in bare.steps],
          ([s.path for s in full.steps], [s.path for s in bare.steps]))
    check("... the SAME action, scope and state filter",
          (full.action, full.scope, full.state)
          == (bare.action, bare.scope, bare.state),
          ((full.action, full.scope, full.state),
           (bare.action, bare.scope, bare.state)))
    # And the constructor the model reads carries the hint on the read tool.
    sent = AG.TOOLS["github_list"].schema(["github_list"])
    check("the model is sent the hint with github_list",
          AG.GITHUB_REPO_ARG_HINT in sent["function"]["description"])


# --------------------------------------------------------------------------
#   7. The lead's live battery (2026-11-18 17:57Z): what the questions reach
# --------------------------------------------------------------------------
#
# The eight questions asked of the live Jarvis at 17:57Z, verbatim. The
# evidence is in `~/.openjarvis/logs/jarvis-2026-11-18.jsonl` and
# `speed.jsonl`: seven answered with no tool call, one (the second) DID call
# `github_list` and was refused for the bare name. `speed.jsonl`'s `tools`
# field is NOT "tools were offered" - `jarvis_hud.py:5586` writes
# `tools=int(_turn.get("rounds") or 1) > 1`, i.e. "the turn took more than one
# model round"; so it records "no tool ran", not "no tool was shown". The owner's
# live `[tools].enabled` (checked in his installed framework file the same day)
# names github_list, github_read_file, github_ci_status, github_pr_scan,
# github_comment, github_open_issue, github_rerun_workflow, github_create_repo,
# github_merge_pr, github_fix_and_push, github_search, github_pr_detail and
# github_open_pr - so the tools were enabled; what the model was SHOWN is
# `tool_diet_selection` below (the diet ships ON: TOOL_DIET_DEFAULT = True).
BATTERY = (
    ("What are my open pull requests on Epic-Jarvis?", "github_list"),
    ("Which pull requests are ready to merge?", "github_pr_scan"),
    ("What is failing on pull request 1376?", "github_pr_detail"),
    ("What checks are still running on PR 1378?", "github_ci_status"),
    ("What is the latest commit on main in Epic-Jarvis?", "github_ci_status"),
    ("Which branches have unmerged work?", "github_pr_scan"),
    ("How do I merge a pull request on GitHub?", "github_merge_pr"),
)
#: The allowed names the diet is choosing between on the owner's PC: his live
#: enabled list, reduced to the tools this repository ships.
BATTERY_ALLOWED = (
    "calculator", "change_setting", "memory_search", "web_search",
    "feature_guide", "my_files", "calendar_read", "email_check", "home_read",
    "notes_search", "self_portrait", "conversation_find", "conversation_open",
    "refresh_abilities", "github_list", "github_read_file", "github_ci_status",
    "github_pr_scan", "github_comment", "github_open_issue",
    "github_rerun_workflow", "github_create_repo", "github_merge_pr",
    "github_fix_and_push", "github_search", "github_pr_detail",
    "github_open_pr", "review_changes", "check_records",
)


def t_the_live_battery_questions_offer_the_github_tool_they_need():
    """"What is the latest commit on main in Epic-Jarvis?" was answered with a
    FALSE DENIAL ("I don't have direct access to your GitHub repositories").

    The cause is in the tool diet, not the model: before this branch the
    question's words matched only `web_search` ("latest") and `feature_guide`,
    so `tool_diet_selection` HID every GitHub tool from the model - it could not
    have called one. The fix is the `commit` word on `github_ci_status`'s own
    hint (the newest workflow run names its head commit) plus the call-trigger
    sentence on the read tools' descriptions.
    """
    allowed = [n for n in AG.TOOLS if n in set(BATTERY_ALLOWED)]
    check("the diet is on, so what it shows is what the model can call",
          AG.tool_diet_on() is True)
    for question, needed in BATTERY:
        selection = AG.tool_diet_selection(question, allowed)
        shown = selection["tools"]
        check(f"{question!r}: the tool it needs is shown ({needed})",
              needed in shown, (needed, shown))
        check(f"{question!r}: at least one GitHub tool is shown",
              any(name.startswith("github_") for name in shown), shown)
    # The eighth question is not a GitHub one: its tool is the local record
    # check, and the words must offer that (it was shown only by the
    # every-tool fallback before, which is not the same promise).
    selection = AG.tool_diet_selection(
        "How many open defects are in the register?", allowed)
    check("'defects in the register' offers the tool that reads the register",
          "check_records" in selection["tools"], selection["tools"])


def t_the_live_battery_tool_calls_answer_real_data():
    """The calls the model SHOULD make now return GitHub's own data.

    This is the first, second, third, fourth and fifth questions of the battery,
    each driven through the real `_one_call`/`prepare`/`run` path against the
    injected fake - so the owner's answer is real data and never the
    `owner/name` question. BEFORE THIS CHANGE the first and second calls raised
    "needs a repository named like owner/name" and the fifth was not even
    offered (previous test).
    """
    pulls = json.dumps([{"number": 1376, "title": "fix: the cloud path",
                         "state": "open"}])
    pr = json.dumps({"number": 1376, "title": "fix: the cloud path",
                     "state": "open", "draft": False,
                     "mergeable": True, "mergeable_state": "clean",
                     "head": {"sha": HEAD_SHA}, "base": {"ref": "main"}})
    failing = {"id": 9, "name": "ci", "head_sha": HEAD_SHA,
               "status": "completed", "conclusion": "failure"}
    running = {"id": 10, "name": "ci", "head_sha": HEAD_SHA,
               "status": "in_progress", "conclusion": None}
    branches = {"name": "main"}
    checks = {"check_runs": [{"name": "backend", "status": "completed",
                              "conclusion": "failure"}]}

    # 1. "What are my open pull requests on Epic-Jarvis?" - the exact live
    #    route: the bare name the model really passed.
    fetch = FakeGitHub(routes=[("/pulls?", (200, pulls))])
    _f, _g, steps, result, watch = _one_call(
        "github_list", {"scope": "pulls", "repo": "Epic-Jarvis"},
        BATTERY[0][0], fetch=fetch)
    check("battery 1: the open pull requests are really read",
          steps[0]["ran"] is True and result.get("ok") is True
          and "#1376" in str(result.get("text", "")), result)
    check("battery 1: no owner/name question and no card",
          "owner/name" not in str(result) and watch.cards == 0, result)

    # 2. "Which pull requests are ready to merge?" - the live model's own
    #    choice (github_list) was refused; the same call now answers.
    fetch = FakeGitHub(routes=[("/pulls?", (200, pulls))])
    _f, _g, steps, result, _w = _one_call(
        "github_list", {"scope": "pulls", "repo": "Epic-Jarvis"},
        BATTERY[1][0], fetch=fetch)
    check("battery 2: the ready pull requests are really listed",
          steps[0]["ran"] is True and result.get("ok") is True
          and "#1376" in str(result.get("text", "")), result)

    # 3. "What is failing on pull request 1376?" - the full PR read.
    fetch = FakeGitHub(routes=[("/pulls/1376", (200, pr)),
                               ("/files", (200, "[]")),
                               ("/commits", (200, "[]")),
                               ("/comments", (200, "[]")),
                               ("/reviews", (200, "[]"))])
    _f, _g, steps, result, _w = _one_call(
        "github_pr_detail", {"repo": "Epic-Jarvis", "number": "1376"},
        BATTERY[2][0], fetch=fetch)
    check("battery 3: the pull request is really read",
          steps[0]["ran"] is True and result.get("ok") is True
          and "cloud path" in str(result.get("text", "")), result)

    # 4. "What checks are still running on PR 1378?" - CI status by PR.
    fetch = FakeGitHub(routes=[
        ("/branches/", (200, json.dumps(branches))),
        ("/pulls/1378", (200, json.dumps(dict(json.loads(pr), number=1378)))),
        ("/actions/runs", (200, json.dumps({"workflow_runs": [running]}))),
        ("/check-runs", (200, json.dumps({"check_runs": []})))])
    _f, _g, steps, result, _w = _one_call(
        "github_ci_status", {"repo": "Epic-Jarvis", "pr": "1378"},
        BATTERY[3][0], fetch=fetch)
    check("battery 4: the running checks are really read",
          steps[0]["ran"] is True and result.get("ok") is True
          and ("in_progress" in str(result.get("text", "")).lower()
               or "did not finish" in str(result.get("text", "")).lower()),
          result)

    # 5. "What is the latest commit on main in Epic-Jarvis?" - the newest run
    #    on main names its head commit. The live answer denied access; this one
    #    has the commit.
    fetch = FakeGitHub(routes=[
        ("/branches/main", (200, json.dumps(branches))),
        ("/actions/runs", (200, json.dumps(
            {"workflow_runs": [dict(failing, conclusion="success")]})))])
    _f, _g, steps, result, _w = _one_call(
        "github_ci_status", {"repo": "Epic-Jarvis", "branch": "main"},
        BATTERY[4][0], fetch=fetch)
    text = str(result.get("text", ""))
    check("battery 5: the commit is really read, not denied",
          steps[0]["ran"] is True and result.get("ok") is True
          and not result.get("error")
          and ("don't have" not in text.lower()
               and "no access" not in text.lower()),
          result)
    check("battery 5: ... and the newest run on main is really read",
          "ci" in text.lower()
          and ("passed" in text.lower() or "success" in text.lower()),
          text)


# --------------------------------------------------------------------------

def main() -> int:
    try:
        with NoSocket():
            t_the_owners_own_repository_is_named_in_his_own_words()
            t_a_bare_owner_name_reaches_every_github_planner()
            t_the_owners_exact_sentence_reads_his_own_pull_requests()
            t_the_read_tiers_are_auto_in_the_shipped_config()
            t_my_open_prs_my_repo_and_this_repository_fill_the_repository_in()
            t_a_foreign_repository_is_never_replaced_by_the_owners()
            t_every_github_tool_with_a_repository_says_it_may_be_bare()
            t_a_write_card_names_the_full_repository()
            t_a_read_plan_is_unchanged_apart_from_the_name()
            t_the_live_battery_questions_offer_the_github_tool_they_need()
            t_the_live_battery_tool_calls_answer_real_data()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
