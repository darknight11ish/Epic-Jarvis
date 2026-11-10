"""test_github_tools.py - the six GitHub tools, their four gate actions, and the patch.

    python3 test_github_tools.py

WHAT THIS SUITE IS FOR

The owner's decision of 2026-11-03: Jarvis may READ his GitHub (repositories,
open pull requests, issues, CI status, one file) and take three small ACTIONS
(comment, open an issue, re-run a workflow) - each action behind its own
approval card - and it may never merge, push, commit, delete or close.

`backend/jarvis_github.py` holds the half that talks to api.github.com;
`backend/jarvis_agent.py` holds the six tools; `backend/github-tools.patch`
gives the gate the four actions. This suite proves the promises each of those
makes, and it proves the patch really applies - with NO network and NO real
token anywhere:

  1. Only api.github.com. Every address every planner can build starts with
     the module's own constant, and no argument the model can write becomes a
     host. A redirect is refused rather than followed, so the token cannot be
     handed to whoever answered (`_RefuseRedirect`).
  2. The read scopes are a CLOSED set. A repository, a path, a branch or a
     number the model wrote is checked before it goes into a URL, so a `../`,
     a `?` or a `#` cannot turn one request into a different one.
  3. The token is never printed. A distinctive fake token is used throughout,
     and every card, result, and failure sentence is searched for it.
  4. No token, no card. The six planners answer "connect GitHub" in plain
     words and `_one_call` returns before the gate - a card nobody could act
     on is never raised.
  5. Each action is ONE card that names exactly what it will do: the
     repository, the number or run, and the comment or issue text in full.
  6. Failures are plain sentences. A refused token, a rate limit and a missing
     repository are said in words, with no HTTP code in them.
  7. Nothing from email, files, credentials or saved memory is ever sent.
  8. There is no tool that can merge, push, commit, delete or close.
  9. The patch: it reverses out of the published base and applies forward
     again byte for byte, it sits between `web-search-grant.patch` and the
     last writer of `jarvis_gate.py` (`unknown-risk-approvable.patch`) so
     neither of those patches' reversals is disturbed, the four tier lines
     ship as "ask", and every table a new tool has to join has it.

THE FAKE HTTP LAYER

Every test drives the module through `run(..., fetch=<fake>)`, which is the one
seam `_default_fetch` sits behind. Nothing here opens a socket: `NoSocket`
replaces `socket.socket` for the whole run, so a mistake that reached the real
network would raise instead of quietly working.

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

READ_TOOLS = ("github_list", "github_read_file", "github_ci_status")
ACTION_TOOLS = ("github_comment", "github_open_issue", "github_rerun_workflow",
                # 2026-11-09: one new, empty repository on the owner's own account.
                "github_create_repo")
ALL_TOOLS = READ_TOOLS + ACTION_TOOLS

#: The arguments each tool needs, so one table drives every test below.
ARGS = {
    "github_list": {"scope": "pulls", "repo": "darknight11ish/Epic-Jarvis"},
    "github_read_file": {"repo": "darknight11ish/Epic-Jarvis", "path": "README.md"},
    "github_ci_status": {"repo": "darknight11ish/Epic-Jarvis", "branch": "main"},
    "github_comment": {"repo": "darknight11ish/Epic-Jarvis", "number": "1116",
                       "body": "Thanks - the rebase is done and the checks are green."},
    "github_open_issue": {"repo": "darknight11ish/Epic-Jarvis",
                          "title": "The tray icon stays after a restart",
                          "body": "Seen twice on 2026-11-03."},
    "github_rerun_workflow": {"repo": "darknight11ish/Epic-Jarvis", "run_id": "123456"},
    "github_create_repo": {"name": "Fitness-Band",
                           "description": "A band that counts steps.",
                           "private": True},
}

#: What each ACTION's card must name, and nothing else has to.
MUST_NAME = {
    "github_comment": ("darknight11ish/Epic-Jarvis", "1116",
                       "Thanks - the rebase is done and the checks are green."),
    "github_open_issue": ("darknight11ish/Epic-Jarvis",
                          "The tray icon stays after a restart",
                          "Seen twice on 2026-11-03."),
    "github_rerun_workflow": ("darknight11ish/Epic-Jarvis", "123456"),
    "github_create_repo": ("Fitness-Band", "Private: yes",
                           "A band that counts steps."),
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
        check(f"{tool}: it says nothing is merged, pushed or closed",
              "merged" in text and "pushed" in text and "closed" in text,
              text[-200:])
        # One POST, never a DELETE/PATCH/PUT that could change more.
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


def t_there_is_no_merging_pushing_committing_or_deleting_tool():
    forbidden = re.compile(
        r"merge|push|commit|delete|remove|close|write_file|edit_file|"
        r"create_branch|force_push", re.I)
    # `pack_remove` is the ONE tool whose name matches and is not GitHub's: the
    # pack manager's removal deletes exactly the files its own ledger recorded
    # (`jarvis-packs.json`) after ONE `modify_own_code` card, and it holds no
    # repository, branch or remote at all (`backend/jarvis_packs.py`, the
    # JARVIS-API section 197 doors). It is exempted HERE rather than renamed,
    # because "remove" is the honest word for it, and the two checks below still
    # hold it - and every GitHub tool - to the rule this section is about.
    NOT_GITHUB_BY_NAME = {"pack_remove"}
    offenders = sorted(n for n in AG.TOOLS
                       if forbidden.search(n) and n not in NOT_GITHUB_BY_NAME)
    check("the registered tool list has no merge/push/commit/delete/close tool",
          not offenders, offenders)
    github_offenders = sorted(n for n in AG.TOOLS
                             if n.startswith("github") and forbidden.search(n))
    check("... and none of the GitHub tools is one of those", not github_offenders,
          github_offenders)

    # The sentence a person gets says it, in plain words.
    check("the refusal names merge, push, commit, delete and close",
          all(w in GH.never_words() for w in
              ("merge", "push", "commit", "delete", "close")), GH.never_words())
    check("... and says why", "deliberate" in GH.never_words(), GH.never_words())
    check("the module names them too", {"merge", "push", "commit", "delete",
                                        "close"} <= GH.NEVER, sorted(GH.NEVER))

    check("no planner exists for any of them",
          not [n for n in dir(GH) if n.startswith("plan_")
               and forbidden.search(n[len("plan_"):])],
          [n for n in dir(GH) if n.startswith("plan_")])

    # Every action tool's own description tells the model what it cannot do.
    for tool in ACTION_TOOLS:
        desc = AG.TOOLS[tool].description.lower()
        check(f"{tool}: its description says it never merges, pushes or closes",
              all(w in desc for w in ("merge", "push", "closes")), desc)


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


def t_the_gate_knows_the_seven_tools_and_five_actions():
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
                         ("github_comment", GH.ACTION_COMMENT),
                         ("github_open_issue", GH.ACTION_OPEN_ISSUE),
                         ("github_rerun_workflow", GH.ACTION_RERUN),
                         ("github_create_repo", GH.ACTION_CREATE_REPO)):
        check(f"the gate maps {tool} to {action}",
              actions.get(tool) == action, actions.get(tool))

    for action in (GH.ACTION_INSPECT, GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE,
                   GH.ACTION_RERUN, GH.ACTION_CREATE_REPO):
        row = risk.get(action)
        check(f"{action} is classified, so its card is not 'unknown'",
              isinstance(row, tuple) and len(row) == 3, row)
    check("the read is reversible and outbound, like every other read of a page",
          risk.get(GH.ACTION_INSPECT, ("",))[0:2] == ("yes", "outbound"),
          risk.get(GH.ACTION_INSPECT))
    for action in (GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE, GH.ACTION_RERUN,
                   GH.ACTION_CREATE_REPO):
        check(f"{action} cannot be undone, and is advertised as such",
              risk.get(action, ("",))[0] == "no", risk.get(action))

    # The patch's added lines must be visible to the parsers the other suites
    # use: one `"_TOOL_ACTIONS"` line per tool, one `"action": (row` per action.
    ptext = PATCH.read_text(encoding="utf-8")
    for tool in ALL_TOOLS:
        check(f"the patch's own + line carries {tool}",
              bool(re.search(r'^\+\s*"%s":\s*"[a-z_]+",?\s*$' % tool, ptext, re.M)),
              tool)
    for action in (GH.ACTION_INSPECT, GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE,
                   GH.ACTION_RERUN, GH.ACTION_CREATE_REPO):
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
                       GH.ACTION_RERUN, GH.ACTION_CREATE_REPO):
            check(f"{toml_path.parent.name}/{toml_path.name}: {action} ships as ask",
                  tiers.get(action) == "ask", tiers.get(action))
        check(f"{toml_path.name}: github_read stayed 'auto' (the watch needs it)",
              tiers.get("github_read") == "auto", tiers.get("github_read"))

    for action in (GH.ACTION_INSPECT, GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE,
                   GH.ACTION_RERUN, GH.ACTION_CREATE_REPO):
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
                   GH.ACTION_RERUN, GH.ACTION_CREATE_REPO):
        check(f"the 'What asks first' page has a row for {action}",
              action in names, sorted(names - {action})[:5])

    import jarvis_owner_check as OC
    check("a GitHub read is a SMALL card on this PC", GH.ACTION_INSPECT in OC.SMALL_ACTIONS)
    for action in (GH.ACTION_COMMENT, GH.ACTION_OPEN_ISSUE, GH.ACTION_RERUN,
                   GH.ACTION_CREATE_REPO):
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
          out.get("ok") is True and text == "# Jarvis\n\nThe README's own words.",
          repr(text)[:200])
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
    check("a huge file is cut, and says so",
          out.get("ok") and GH.CUT_MARKER in out.get("text", ""),
          len(out.get("text", "")))
    check("... at the file cap, not the socket cap",
          len(out.get("text", "")) <= GH.MAX_FILE_CHARS + len(GH.CUT_MARKER) + 2,
          len(out.get("text", "")))

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
    check("the module's never-list still names every irreversible verb",
          {"merge", "push", "commit", "delete", "close"} <= GH.NEVER, sorted(GH.NEVER))
    check("... and the refusal sentence no longer claims create is impossible",
          "create" in GH.never_words() and "cannot create" not in GH.never_words(),
          GH.never_words())


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
                   t_nothing_private_is_ever_sent,
                   t_there_is_no_merging_pushing_committing_or_deleting_tool,
                   t_the_patch_applies_and_reverses_byte_for_byte,
                   t_the_gate_knows_the_seven_tools_and_five_actions,
                   t_every_tier_is_ask_and_the_tables_are_joined,
                   t_a_file_read_shows_the_files_text_not_the_envelope,
                   t_the_answer_is_bounded_and_unapproved_runs_send_nothing,
                   t_create_repo_is_one_carded_call_before_any_network,
                   t_create_repo_body_is_exactly_what_the_card_showed,
                   t_create_repo_never_prints_the_token,
                   t_create_repo_201_reports_only_what_github_answered,
                   t_create_repo_failures_are_githubs_own_words_without_the_token,
                   t_create_repo_has_no_auto_approve_or_bulk_path):
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
