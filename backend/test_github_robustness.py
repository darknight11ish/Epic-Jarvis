"""test_github_robustness.py - the ADVERSARIAL suite for jarvis_github.py.

    python3 test_github_robustness.py

WHAT THIS SUITE IS FOR

`backend/test_github_tools.py` proves the GitHub tools do the right thing when
they are used properly. This suite does the opposite: it drives the PLANNERS and
the TRANSPORT BOUNDARY with the arguments a hostile model, a confused model or a
hostile answer would produce, and pins that each one is refused, bounded or
reported - in plain words, before anything is sent.

It is deliberately independent of the agent layer: every check calls `plan_*`,
`describe`, `run` or the fetch boundary of `backend/jarvis_github.py` directly,
with a fake `fetch` that records the call. Nothing here opens a socket, runs
git, or reads a real credential (`_Token` replaces `GH._token` for the length of
one block, so the owner's saved token is never consulted).

THE SIX THINGS IT PINS

  1. HOSTILE ARGUMENTS. A repository named `a/b/../../c` (or `owner/..`, or one
     with a newline in it), a 5,000-character title, text carrying the
     direction-override characters that make one line DRAW as another, a commit
     id of 39 or 41 hex characters, a number of 0, -1 or "abc", a `base_ref` of
     `main..evil`, `refs/heads/main` or `HEAD`, and an empty string where a value
     is required: every one is REFUSED with a plain sentence, and no request is
     built from it.
  2. NO UNCONTROLLED ADDRESS. Every URL any planner can produce starts with the
     module's own `https://api.github.com/`, names that host and no other, carries
     no fragment, and puts only the module's own query keys in the query. A
     request the module did not write itself (`@evil.example/x`, `//evil.example/x`,
     an absolute URL, a `#` fragment) is refused at the transport boundary BEFORE
     `fetch` is called - so a model cannot choose a host, and the token cannot be
     sent anywhere else.
  3. BOUNDED ANSWERS. A 5 MB body, a `pulls/{n}/files` list over the read cap, a
     truncated answer and a binary blob each come out either bounded, with one
     line naming what was left out, or as an explicit error. NO case may come out
     as a silent empty list ("there are no open pull requests", "Changed files
     (0)") when GitHub really sent something.
  4. FAILURE SHAPES. 401, a 403 rate limit (with `Retry-After`), 404, 422, 500, a
     non-JSON body, a redirect and an empty body each produce ONE plain sentence:
     no HTTP code, no JSON, no traceback, and something the owner can do next.
  5. TOKEN HYGIENE. The token a test injects appears zero times in every card,
     every answer and every error, and no `Authorization` header value is ever
     printed. The header is checked to REALLY carry the token, so those "never
     printed" checks are not passing because nothing was ever sent.
  6. THE MERGE PIN. A merge plan carries exactly `{"merge_method": "merge",
     "sha": <the exact 40 hex>}` and no other field, whatever the arguments say;
     a sha that is not 40 hex characters is refused before a request exists.

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
import urllib.parse
from pathlib import Path

# A temp config dir BEFORE any backend import: jarvis_gate opens an approval
# queue at import time, and this suite must not read or write the owner's own.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-github-robust-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
# No push: the topic is unset, so nothing can post to ntfy.sh.
os.environ["JARVIS_NTFY_TOPIC"] = ""

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_github as GH  # noqa: E402

#: A token distinctive enough that finding it anywhere is a leak, and shaped
#: like the real thing so nothing can pass by being "not token-like".
TOKEN = "ghp_ROBUSTNESSnotarealtoken000000000000000"

REPO = "darknight11ish/Epic-Jarvis"
SHA = "0123456789abcdef0123456789abcdef01234567"

#: The characters that make text draw as something other than what it is: an
#: RLO/LRO override, a bidi isolate, a bidi mark, a zero-width space and a BOM.
BIDI = "\u202e"
HOSTILE_TEXT = "Fix the tray icon \u202eevil\u202c \u2066x\u2069"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   A plain sentence, and a refusal that sends nothing
# --------------------------------------------------------------------------

#: A `4xx`/`5xx` code as a bare number. The owner must never read one, so a
#: sentence that contains one is not a plain sentence.
_HTTP_CODE = re.compile(r"(?<![\w.])(?:4\d\d|5\d\d)(?![\w.])")


def _plain_words(text, limit=900):
    """True only for one plain line a person can read and act on.

    Not empty, one line, ends like a sentence, and holds no HTTP code, URL,
    JSON, traceback, Python repr or token - the shape every refusal and every
    failure sentence in this module promises.
    """
    text = str(text or "").strip()
    if not text or len(text) > limit:
        return False
    if "\n" in text or "\r" in text:
        return False
    if not text.endswith("."):
        return False
    if TOKEN in text or "HTTP" in text or "Traceback" in text:
        return False
    if "{" in text or "}" in text or "Step(" in text or "Request(" in text:
        return False
    if "http://" in text or "https://" in text:
        return False
    return not _HTTP_CODE.search(text)


def _refused(label, fn):
    """The planner refused `fn()` in plain words, and nothing was sent.

    A planner that ACCEPTS a hostile value is not merely recorded as a failure:
    the request it built is then run against a recording fake, and the URL it
    would have sent is printed, because "what would have gone out" is the fact
    that matters.
    """
    try:
        made = fn()
    except GH.GitHubError as exc:
        text = str(exc)
        check(f"{label}: refused", True)
        check(f"{label}: ... in one plain sentence", _plain_words(text), text)
        return
    except Exception as exc:                 # noqa: BLE001 - any other raise is a bug
        check(f"{label}: refused", False, f"raised {type(exc).__name__}: {exc}")
        return
    sent = Fake()
    _run_request(made, sent)
    where = [c["url"] for c in sent.calls] or [s.url() for s in made.steps]
    check(f"{label}: refused", False, f"ACCEPTED - it would have sent {where}")


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
    """A stand-in for the fetch seam: records every call, answers by rule.

    `headers` is returned as the third value when it is given, which is the shape
    the real `_default_fetch_full` answers in - that is how the `Retry-After`
    case is driven without a network.
    """

    def __init__(self, status=200, body="[]", headers=None):
        self.status = status
        self.body = body
        self.headers = headers
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}), "body": body,
                           "timeout": timeout})
        if self.headers is None:
            return self.status, self.body
        return self.status, self.body, dict(self.headers)

    def urls(self):
        return [c["url"] for c in self.calls]


class Routed(Fake):
    """A `Fake` that answers by URL substring, first match wins."""

    def __init__(self, routes):
        super().__init__()
        self.routes = list(routes)

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}), "body": body,
                           "timeout": timeout})
        for needle, answer in self.routes:
            if needle in url:
                if callable(answer):
                    return answer(self.calls[-1])
                return answer
        return 404, "{}"


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


def _run_request(r, fetch, *, approved=True):
    """`GH.run` for one request, with the fake token in place for the CALL."""
    with _Token():
        return GH.run(r, fetch=fetch, approved=approved)


def _card(plan, args):
    """(the Request, the card text) one planner gives, with a token in place."""
    with _Token():
        r = plan(dict(args))
        return r, GH.describe(r)


#: One VALID argument set per planner, used by the address checks. Every one is
#: the shape `jarvis_agent` builds from real arguments; the hostile cases are
#: below, and each of those is refused before a Request exists.
VALID = (
    ("plan_list repos", GH.plan_list, {"scope": "repos"}),
    ("plan_list pulls", GH.plan_list, {"scope": "pulls", "repo": REPO}),
    ("plan_list issues", GH.plan_list, {"scope": "issues", "repo": REPO}),
    ("plan_list runs", GH.plan_list, {"scope": "runs", "repo": REPO}),
    ("plan_read_file", GH.plan_read_file,
     {"repo": REPO, "path": "docs/a b.md", "ref": "feature/tray-icon"}),
    ("plan_ci branch", GH.plan_ci, {"repo": REPO, "branch": "main"}),
    ("plan_ci pr", GH.plan_ci, {"repo": REPO, "pr": "7"}),
    ("plan_ci latest", GH.plan_ci, {"repo": REPO}),
    ("plan_comment", GH.plan_comment,
     {"repo": REPO, "number": "1116", "body": "Thanks - the rebase is done."}),
    ("plan_open_issue", GH.plan_open_issue,
     {"repo": REPO, "title": "The tray icon stays", "body": "Seen twice."}),
    ("plan_rerun", GH.plan_rerun, {"repo": REPO, "run_id": "123456"}),
    ("plan_create_repo", GH.plan_create_repo, {"name": "Fitness-Band"}),
    ("plan_scan_prs", GH.plan_scan_prs, {"repo": REPO}),
    ("plan_merge_pr", GH.plan_merge_pr,
     {"repo": REPO, "number": "1116", "head_sha": SHA, "title": "Fix it",
      "base_ref": "main"}),
    ("plan_pr_detail", GH.plan_pr_detail, {"repo": REPO, "number": "1116"}),
    ("plan_workflow", GH.plan_workflow,
     {"repo": REPO, "run_id": "123456", "action": "cancel"}),
    ("plan_issue_labels", GH.plan_issue_labels,
     {"repo": REPO, "number": "1116", "add": ["triage"]}),
    ("plan_edit_pr", GH.plan_edit_pr,
     {"repo": REPO, "number": "1116", "title": "Fix it, properly",
      "old_title": "Fix it"}),
    ("plan_pr_review", GH.plan_pr_review,
     {"repo": REPO, "number": "1116", "event": "COMMENT", "body": "Looks good."}),
    ("plan_issue_state", GH.plan_issue_state,
     {"repo": REPO, "number": "1116", "action": "close", "title": "The tray icon"}),
    ("plan_open_pr prepare", GH.plan_open_pr,
     {"repo": REPO, "base": "main", "branch": "jarvis/new-feature"}),
)

#: The planners whose arguments need a REAL prepared folder on this PC, so their
#: addresses are covered by `backend/test_github_tools.py` (which builds one in a
#: temp folder) rather than here. Named so a NEW planner cannot be forgotten.
NEEDS_A_FOLDER = ("plan_fix_and_push",)

#: The only query keys the module itself writes. A model's value may fill one of
#: these; it may never ADD one, and it may never add a fragment.
QUERY_KEYS = frozenset({"per_page", "sort", "state", "ref", "branch", "head_sha"})


# --------------------------------------------------------------------------
#   1. Hostile arguments
# --------------------------------------------------------------------------


def t_a_repository_must_be_a_plain_owner_name():
    """`owner/..` is a path traversal dressed as a repository name."""
    for label, repo in (
            ("a/b/../../c", "a/b/../../c"),
            ("a newline and a header", "owner/name\nX-Injected: 1"),
            ("a carriage return", "owner/name\rX-Injected: 1"),
            ("a query", "owner/name?per_page=1"),
            ("a fragment", "owner/name#x"),
            ("two slashes", "a/b/c"),
            ("no owner", "/name"),
            ("no name", "owner/"),
            ("a dot-dot name", "owner/.."),
            ("a dot name", "owner/."),
            ("a percent escape", "owner/%2e%2e"),
            ("empty", ""),
            ("only spaces", "   "),
            ("a null byte", "owner/na\x00me")):
        _refused(f"repo {label}: github_list",
                 lambda repo=repo: GH.plan_list({"scope": "pulls", "repo": repo}))
        _refused(f"repo {label}: github_pr_detail",
                 lambda repo=repo: GH.plan_pr_detail({"repo": repo, "number": "1"}))


def t_a_file_path_stays_inside_the_repository():
    for label, path in (
            ("a parent step", "../x"),
            ("a parent step inside", "docs/../../etc/passwd"),
            ("a query", "a?ref=main"),
            ("a fragment", "a#x"),
            ("a backslash escape", "a\\..\\b"),
            ("empty", ""),
            ("only spaces", "   ")):
        _refused(f"path {label}",
                 lambda path=path: GH.plan_read_file({"repo": REPO, "path": path}))
    # An absolute-looking path is RE-ROOTED inside the repository rather than
    # refused (the old behaviour, kept on purpose): `/etc/passwd` becomes the
    # repository's own `etc/passwd`, which cannot reach this PC's file system.
    # What matters is asserted: it is never the address of a local file.
    with _Token():
        r = GH.plan_read_file({"repo": REPO, "path": "/etc/passwd"})
    check("an absolute-looking path is re-rooted inside the repository",
          r.steps[0].url() == (GH.GITHUB_API + f"/repos/{REPO}/contents/etc/passwd"),
          r.steps[0].url())
    # ... and a plain path with a space in it is still read.
    with _Token():
        r = GH.plan_read_file({"repo": REPO, "path": "docs/a b.md"})
    check("a plain path with a space is still read",
          r.steps[0].url().endswith("/contents/docs/a%20b.md"), r.steps[0].url())


def t_a_title_and_a_body_are_bounded_and_cannot_carry_bidi():
    """A card must never show a line that DRAWS as another line.

    The module already strips hidden characters out of FETCHED text. Text the
    model supplies is shown WHOLE on the approval card, so a direction override
    there would make the card draw as something other than what will be posted.
    It is refused rather than silently changed: what the person approves has to
    be what is posted.
    """
    _refused("a 5,000-character issue title",
             lambda: GH.plan_open_issue({"repo": REPO, "title": "x" * 5000}))
    _refused("a 5,000-character comment",
             lambda: GH.plan_comment({"repo": REPO, "number": "1",
                                      "body": "x" * 5000}))
    _refused("a 5,000-character description",
             lambda: GH.plan_create_repo({"name": "r", "description": "x" * 5000}))
    for label, text in (("an override", HOSTILE_TEXT),
                        ("an isolate", "\u2066title\u2069"),
                        ("a byte-order mark", "\ufefftitle"),
                        ("a bidi mark", "title\u200f"),
                        ("a zero-width space", "ti\u200btle")):
        _refused(f"{label} in an issue title",
                 lambda text=text: GH.plan_open_issue({"repo": REPO, "title": text}))
        _refused(f"{label} in a comment",
                 lambda text=text: GH.plan_comment(
                     {"repo": REPO, "number": "1", "body": text}))
        _refused(f"{label} in a review",
                 lambda text=text: GH.plan_pr_review(
                     {"repo": REPO, "number": "1", "event": "COMMENT", "body": text}))
        _refused(f"{label} in an issue reason",
                 lambda text=text: GH.plan_issue_state(
                     {"repo": REPO, "number": "1", "action": "close", "title": "T",
                      "reason": text}))
    for label, value in (("an empty title", ""), ("a whitespace title", "   \n\t")):
        _refused(label + " (issue)", lambda value=value: GH.plan_open_issue(
            {"repo": REPO, "title": value}))
    _refused("an empty comment", lambda: GH.plan_comment(
        {"repo": REPO, "number": "1", "body": ""}))
    # And the refusal must NOT be a refusal of real right-to-left text: a Hebrew
    # sentence and an emoji built with a zero-width joiner are ordinary text, and
    # refusing them would break the owner's own words.
    with _Token():
        r, card = _card(GH.plan_open_issue,
                        {"repo": REPO, "title": "\u05e9\u05dc\u05d5\u05dd",
                         "body": "family \U0001f468\u200d\U0001f469"})
    check("a genuine right-to-left title is accepted, not refused",
          r.body["title"] == "\u05e9\u05dc\u05d5\u05dd", r.body)
    check("... and an emoji built with a zero-width joiner survives whole",
          "\U0001f468\u200d\U0001f469" in r.body["body"], r.body)
    check("... and the card is the text that will be posted",
          "\u05e9\u05dc\u05d5\u05dd" in card, card)


def t_a_number_is_a_real_github_number():
    """GitHub numbers its issues, pull requests and runs from 1; 0 is not one."""
    for label, number in (("0 as a number", 0), ("0 as a string", "0"),
                          ("-1", "-1"), ("abc", "abc"), ("empty", ""),
                          ("a float", 1.5), ("a list", [1]), ("a bool", True),
                          ("# alone", "#"), ("a newline", "1\n2")):
        _refused(f"number {label}",
                 lambda number=number: GH.plan_comment(
                     {"repo": REPO, "number": number, "body": "hi"}))
        _refused(f"run_id {label}",
                 lambda number=number: GH.plan_rerun(
                     {"repo": REPO, "run_id": number}))
    with _Token():
        r = GH.plan_comment({"repo": REPO, "number": "#12", "body": "hi"})
    check('a number written "#12" is accepted as 12',
          r.steps[0].path.endswith("/issues/12/comments"), r.steps[0].path)


def t_a_commit_must_be_a_full_40_hex_id():
    for label, sha in (("39 hex", "a" * 39), ("41 hex", "a" * 41),
                       ("40 non-hex", "z" * 40), ("a branch name", "main"),
                       ("HEAD", "HEAD"), ("refs/heads/main", "refs/heads/main"),
                       ("empty", ""),
                       ("an over-long mixed value", "a" * 40 + "b")):
        _refused(f"head sha {label}",
                 lambda sha=sha: GH.plan_merge_pr(
                     {"repo": REPO, "number": "1", "head_sha": sha,
                      "title": "Fix it", "base_ref": "main"}))
    # A sha whose only sin is a copy-paste newline is the SAME sha, and the pin
    # is the 40 hex characters: it is stripped and used, never sent with the
    # newline in it (which would make the request the card did not show).
    with _Token():
        r = GH.plan_merge_pr({"repo": REPO, "number": "1",
                              "head_sha": SHA + "\n", "title": "Fix it",
                              "base_ref": "main"})
    check("a sha with a trailing newline is pinned as the sha, not as text",
          r.body["sha"] == SHA and r.expected_sha == SHA, r.body)
    with _Token():
        r = GH.plan_merge_pr({"repo": REPO, "number": "1", "head_sha": "A" * 40,
                              "title": "Fix it", "base_ref": "main"})
    check("an upper-case sha is accepted only by folding it to lower case",
          r.expected_sha == "a" * 40 and r.body["sha"] == "a" * 40, r.body)


def t_a_branch_must_be_a_branch_name():
    """`refs/heads/main` and `HEAD` are not the branch a card can name.

    Neither is a plain branch name, so a card printing one would name something
    that is not what the pull request merges into; and a runs filter of
    `refs/heads/main` matches nothing, which reads as "no CI run" when there are
    plenty. `main..evil` and the rest are refused for the same reason.
    """
    HOSTILE_REFS = (("a parent step", "main..evil"),
                    ("a full ref", "refs/heads/main"),
                    ("the word HEAD", "HEAD"),
                    ("a trailing slash", "main/"),
                    ("a trailing dot", "main."),
                    ("a hidden component", "feature/.secret"),
                    ("a lock file", "main.lock"),
                    ("a leading dash", "-main"),
                    ("a space", "feature branch"),
                    ("a question mark", "main?x=1"),
                    ("a fragment", "main#x"),
                    ("a tilde", "main~1"),
                    ("a caret", "main^"),
                    ("a colon", "main:evil"),
                    ("a newline", "main\nX-Injected: 1"))
    for label, ref in HOSTILE_REFS:
        _refused(f"base_ref {label}",
                 lambda ref=ref: GH.plan_merge_pr(
                     {"repo": REPO, "number": "1", "head_sha": SHA,
                      "title": "Fix it", "base_ref": ref}))
        _refused(f"file ref {label}",
                 lambda ref=ref: GH.plan_read_file(
                     {"repo": REPO, "path": "README.md", "ref": ref}))
        _refused(f"ci branch {label}",
                 lambda ref=ref: GH.plan_ci({"repo": REPO, "branch": ref}))
    _refused("base_ref empty", lambda: GH.plan_merge_pr(
        {"repo": REPO, "number": "1", "head_sha": SHA, "title": "Fix it",
         "base_ref": ""}))
    _refused("an empty new branch", lambda: GH.plan_open_pr(
        {"repo": REPO, "base": "main", "branch": ""}))
    _refused("an empty base branch", lambda: GH.plan_open_pr(
        {"repo": REPO, "base": "", "branch": "jarvis/x"}))
    for label, kwargs in (
            ("a new branch written as a full ref",
             {"repo": REPO, "base": "main", "branch": "refs/heads/x"}),
            ("a base branch written as HEAD",
             {"repo": REPO, "base": "HEAD", "branch": "jarvis/x"})):
        _refused(f"open_pr {label}", lambda kwargs=kwargs: GH.plan_open_pr(kwargs))
    # The names that must still work: a plain branch, a nested branch, a tag, and
    # a commit id used as the ref to read a file at.
    for good in ("main", "feature/tray-icon", "v1.0", SHA, "release/1.0"):
        with _Token():
            r = GH.plan_merge_pr({"repo": REPO, "number": "1", "head_sha": SHA,
                                  "title": "Fix it", "base_ref": good})
        check(f'a real branch name is accepted as the base: "{good}"',
              r.base_ref == good, r.base_ref)
        _card(GH.plan_read_file, {"repo": REPO, "path": "a.md", "ref": good})


def t_the_labels_and_the_verdict_are_closed_sets():
    for label, values in (("the APPROVE verdict", {"event": "APPROVE"}),
                          ("an unknown verdict", {"event": "LGTM"}),
                          ("a bidi label", {"add": ["tri" + BIDI + "age"]}),
                          ("a zero-width label", {"add": ["tri\u200bge"]}),
                          ("an empty label", {"add": [""]}),
                          ("eleven labels", {"add": [f"l{i}" for i in range(11)]})):
        args = {"repo": REPO, "number": "1", "body": "text"}
        args.update(values)
        if "event" in values:
            _refused(label, lambda args=args: GH.plan_pr_review(args))
        else:
            _refused(label, lambda args=args: GH.plan_issue_labels(args))


# --------------------------------------------------------------------------
#   2. No uncontrolled address
# --------------------------------------------------------------------------


def t_every_plan_starts_at_the_one_fixed_address():
    addresses = []
    for label, plan, args in VALID:
        r, _card_text = _card(plan, args)
        urls = r.urls()
        check(f"{label}: plans at least one request", bool(urls), urls)
        addresses.extend((label, url) for url in urls)
    planned = {plan.__name__ for _l, plan, _a in VALID}
    every = {name for name in dir(GH)
             if name.startswith("plan_") and callable(getattr(GH, name))}
    check("every planner in the module is covered by the address table",
          every - set(NEEDS_A_FOLDER) == planned,
          sorted(every - set(NEEDS_A_FOLDER) - planned))
    bad = [(label, url) for label, url in addresses
           if not url.startswith(GH.GITHUB_API + "/")]
    check("every planned URL starts with the module's own https://api.github.com/",
          not bad, bad[:3])
    parsed = [(label, urllib.parse.urlsplit(url)) for label, url in addresses]
    check("every planned URL names api.github.com and no other host",
          all(p.hostname == "api.github.com" and p.port is None
              and p.username is None and p.scheme == "https"
              for _l, p in parsed),
          [(label, p.netloc) for label, p in parsed
           if p.hostname != "api.github.com"][:3])
    check("no planned URL carries a fragment",
          not [(l, p.fragment) for l, p in parsed if p.fragment], "fragment")
    keys = {key for _l, p in parsed for key in
            urllib.parse.parse_qs(p.query, keep_blank_values=True)}
    check("the query carries only the module's own keys",
          keys <= QUERY_KEYS, sorted(keys - QUERY_KEYS))
    doubled = [url for _l, url in addresses
               if "//" in url[len(GH.GITHUB_API):] or "/./" in url
               or "/../" in url]
    check("no planned URL has an empty, doubled or parent path segment",
          not doubled, doubled[:3])


def t_a_request_the_module_did_not_write_is_refused_before_any_fetch():
    """The transport boundary checks the address itself, not just the planner."""
    for label, path in (("@evil.example/steal", "@evil.example/steal"),
                        ("a protocol-relative host", "//evil.example/x"),
                        ("an absolute address", "https://evil.example/x"),
                        ("a fragment", "/repos/o/r#/../../x"),
                        ("no leading slash", "repos/o/r"),
                        ("an empty path", "")):
        check(f"a hand-built step ({label}) is not a fixed address",
              GH._address(path) == "", GH._address(path))
        made = GH.Request(GH.ACTION_INSPECT, "x", (GH.Step("GET", path),))
        try:
            shown = made.steps[0].url()
        except GH.GitHubError as exc:
            check(f"... its own url() refuses it in plain words ({label})",
                  _plain_words(str(exc)), str(exc))
        else:
            check(f"... its own url() refuses it in plain words ({label})", False,
                  shown)
        sent = Fake()
        out = _run_request(made, sent)
        check(f"... and run() refuses it with no fetch at all ({label})",
              out.get("ok") is False and not sent.calls, out)
        check(f"... in one plain sentence ({label})",
              _plain_words(out.get("error")), out.get("error"))


def t_a_redirect_is_refused_and_named():
    """A redirect is how the token would reach somebody else, so say so."""
    r = GH.plan_list({"scope": "pulls", "repo": REPO})
    for status in (301, 302, 303, 307, 308):
        out = _run_request(r, Fake(status, "",
                                   {"location": "https://evil.example/"}))
        text = str(out.get("error", ""))
        check(f"a {status} answer is named as a redirect, not followed",
              out.get("ok") is False and "redirect" in text.lower(), out)
        check(f"a {status} answer says why it matters (the token)",
              "token" in text.lower() and _plain_words(text), text)
    check("the urllib layer still refuses the redirect before it is followed",
          issubclass(GH._RefuseRedirect, GH.urllib.request.HTTPRedirectHandler))


# --------------------------------------------------------------------------
#   3. Bounded answers
# --------------------------------------------------------------------------


def _fake_5mb_opener():
    """A transport whose answer is 5 MB, handed out one `read(size)` at a time."""
    class _Body:
        status = 200
        headers = {}

        def __init__(self):
            self.left = 5 * 1024 * 1024

        def read(self, size=-1):
            take = self.left if size is None or size < 0 else min(size, self.left)
            self.left -= take
            return b"A" * take

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    class _Opener:
        def open(self, _req, timeout=None):
            return _Body()

    return _Opener()


def t_a_five_megabyte_answer_is_cut_with_one_line():
    real = GH.urllib.request.build_opener
    GH.urllib.request.build_opener = lambda *_a, **_k: _fake_5mb_opener()
    try:
        status, text, _headers = GH._default_fetch_full(
            "GET", GH.GITHUB_API + "/repos/o/r/pulls", headers={})
    finally:
        GH.urllib.request.build_opener = real
    check("the read layer answers a 5 MB body with the cap and a marker",
          status == 200 and len(text) <= GH.MAX_BYTES + len(GH.CUT_MARKER) + 8
          and text.endswith(GH.CUT_MARKER), (status, len(text)))
    r = GH.plan_list({"scope": "pulls", "repo": REPO})
    out = _run_request(r, Fake(200, text))
    check("a 5 MB answer is one plain line naming what was left out",
          out.get("ok") is True
          and "longer than Jarvis reads" in str(out.get("text", ""))
          and "no open pull requests" not in str(out.get("text", "")), out)


def _pr_doc(**over):
    doc = {"number": 1116, "title": "Fix the tray icon", "draft": False,
           "state": "open", "mergeable": True, "mergeable_state": "clean",
           "changed_files": 481,
           "head": {"sha": SHA, "ref": "feature/tray-icon"},
           "base": {"ref": "main"}}
    doc.update(over)
    return json.dumps(doc)


def _files_list(count=481):
    return json.dumps([{"filename": f"src/f{i}.rs", "status": "modified",
                        "additions": 1, "deletions": 1} for i in range(count)])


def _detail_routes(files="[]", commits="[]", comments="[]", reviews="[]",
                   pr=None):
    """The five fixed GETs `github_pr_detail` makes, answerable one at a time."""
    return Routed([("/files", (200, files)), ("/commits", (200, commits)),
                   ("/comments", (200, comments)), ("/reviews", (200, reviews)),
                   ("/pulls/1116", (200, pr if pr is not None else _pr_doc()))])


def _detail_out(**answers):
    r = GH.plan_pr_detail({"repo": REPO, "number": "1116"})
    return _run_request(r, _detail_routes(**answers))


def t_a_cut_files_list_is_not_reported_as_zero_files():
    """The 481-file pull request: a cut list must never read as "no files"."""
    cut = _files_list(481)[:GH.MAX_BYTES] + GH.CUT_MARKER
    out = _detail_out(files=cut)
    text = str(out.get("text", ""))
    check("a cut files list still answers the pull request itself",
          out.get("ok") is True and "Fix the tray icon" in text, out)
    check("a cut files list is NEVER shown as zero files",
          "Changed files (0)" not in text and "files: (none)" not in text, text)
    check("a cut files list says what was left out and how many there are",
          "481" in text and "not shown" in text, text)
    check("a cut files list is one line, not a blob of JSON",
          "filename" not in text and "{" not in text, text)


def t_a_malformed_detail_list_is_never_an_empty_section():
    """The other four fixed lists: unreadable must not read as "(none)"."""
    for needle, keyword in (("files", "files"), ("commits", "Commits"),
                            ("comments", "Comments"), ("reviews", "Reviews")):
        out = _detail_out(**{needle: "<html>not JSON</html>"})
        text = str(out.get("text", ""))
        check(f"an unreadable {needle} answer is not shown as none",
              f"{keyword}: (none)" not in text
              and f"{keyword} (0)" not in text, text)
        check(f"an unreadable {needle} answer says it could not be read",
              f"{keyword}" in text and ("could not be read" in text
                                        or "not shown" in text), text)
    out = _detail_out(files="[]", commits="[]", comments="[]", reviews="[]")
    check("a genuinely empty list is still a plain (none)",
          "Changed files (0)" in str(out.get("text", "")), out.get("text"))


def t_a_cut_pull_request_answer_is_an_explicit_error():
    for label, answers in (
            ("a cut pull request body", {"pr": _pr_doc()[:200] + GH.CUT_MARKER}),
            ("a truncated diff (JSON cut mid-string)",
             {"pr": '{"number": 1116, "title": "Fix' + GH.CUT_MARKER})):
        out = _detail_out(**answers)
        text = str(out.get("error", ""))
        check(f"{label} is an explicit error", out.get("ok") is False, out)
        check(f"... naming the read cap, not a wrong cause",
              "longer than Jarvis reads" in text, text)
        check(f"... and never claims GitHub sent no pull request",
              "answered without the pull request" not in text, text)


def t_a_pull_request_ci_answer_cannot_say_passed_while_a_check_is_red():
    """PROVEN against real GitHub 2026-11-15 (PR #1263).

    `github_ci_status` asked about a pull request read `/actions/runs?head_sha=`
    and believed `workflow_runs[0]`. Two workflows run on one commit, so it
    answered "The newest CI run (...) passed" on a commit where `audit` and
    `backend-shard (3/4)` were red. A false "passed" is the worst answer this
    tool can give, so the pull request form now reads the head commit's CHECKS.
    """
    def routes(checks, runs):
        return Routed([
            ("/check-runs", (200, json.dumps({"total_count": len(checks),
                                             "check_runs": checks}))),
            ("/actions/runs", (200, json.dumps({"total_count": len(runs),
                                               "workflow_runs": runs}))),
            ("/pulls/1263", (200, json.dumps({
                "number": 1263, "title": "Widen three GitHub reads",
                "state": "open", "head": {"sha": SHA, "ref": "feature/x"},
                "base": {"ref": "main"}}))),
        ])

    def check_run(name, conclusion="success", status="completed"):
        return {"name": name, "status": status, "conclusion": conclusion,
                "details_url": f"https://github.com/{REPO}/actions/runs/1/job/2"}

    green = [check_run(n) for n in GH.REQUIRED_CHECKS]
    red = [check_run("audit", "failure"),
           check_run("backend-shard (3/4)", "failure")] + green
    passing_first = [{"name": "Jarvis client", "status": "completed",
                      "conclusion": "success", "head_branch": "feature/x"},
                     {"name": "CI", "status": "completed",
                      "conclusion": "failure", "head_branch": "feature/x"}]
    r = GH.plan_ci({"repo": REPO, "pr": "1263"})
    check("the pull request CI read asks for the head commit's checks too",
          any("/check-runs" in url for url in r.urls()), r.urls())
    out = _run_request(r, routes(red, passing_first))
    text = str(out.get("text", ""))
    check("a pull request with a red check is NEVER called passed",
          out.get("ok") is True and "passed" not in text.lower(), out)
    check("... the red checks are NAMED",
          "audit" in text and "backend-shard (3/4)" in text, text)
    check("... the pull request itself is named, not an empty '#'",
          f"pull request #1263 in {REPO}" in text, text)
    check("... and it says plainly that not every check is green",
          "NOT all green" in text, text)
    out = _run_request(r, routes(green, passing_first))
    text = str(out.get("text", ""))
    check("an all-green pull request is reported as every check succeeding",
          out.get("ok") is True and "finished successfully" in text
          and "NOT all green" not in text, out)
    # The other half of the same false answer: a run that failed while the
    # checks say green must still stop the word "green" being used.
    check_run_only = [{"name": "CI", "status": "completed",
                       "conclusion": "failure", "head_branch": "feature/x"}]
    out = _run_request(r, routes(green, check_run_only))
    check("a red RUN beside green checks still blocks a green answer",
          "will not call that green" in str(out.get("text", "")), out)
    # A repository that reports NO check runs at all: every visible run counts,
    # never just the first one.
    out = _run_request(r, routes([], passing_first))
    text = str(out.get("text", ""))
    check("with no check runs, the second, failing run is still found",
          "passed" not in text.lower() and "CI (failure)" in text, out)


def t_the_runs_list_answers_even_when_the_answer_is_cut():
    """PROVEN against real GitHub 2026-11-15: the runs scope could never answer.

    Twenty runs were 273,833 characters against a 200,000 cap, so every call
    returned only the cut sentence. It asks for five now, and a cut answer still
    gives the complete runs at its front with "N of M shown".
    """
    r = GH.plan_list({"scope": "runs", "repo": REPO})
    check("the runs list asks for five runs, not twenty",
          all("per_page=5" in url for url in r.urls()), r.urls())
    check("... and the other list scopes keep their page size",
          all("per_page=20" in url
              for url in GH.plan_list({"scope": "pulls", "repo": REPO}).urls()))
    runs = [{"name": f"workflow {i}", "status": "completed",
             "conclusion": "success" if i % 2 else "failure",
             "head_branch": "main",
             "head_commit": {"message": "x" * 60_000}}
            for i in range(40)]
    whole = json.dumps({"total_count": 40, "workflow_runs": runs})
    cut = whole[:GH.MAX_BYTES] + GH.CUT_MARKER
    out = _run_request(r, Fake(200, cut))
    text = str(out.get("text", ""))
    check("a cut runs list is not just the cut sentence",
          "longer than Jarvis reads" in text
          and "workflow 0" in text, out)
    check("... it shows the runs it could parse, and says how many of how many",
          "Showing" in text and "of 40" in text, text)
    check("... and it never claims there is no run",
          "no recent workflow run" not in text.lower(), text)
    out = _run_request(r, Fake(200, json.dumps({"total_count": 3,
                                                "workflow_runs": runs[:3]})))
    check("a whole runs list is a plain list of runs",
          out.get("ok") is True and "workflow 1" in str(out.get("text", ""))
          and "Showing" not in str(out.get("text", "")), out)


def t_a_directory_listing_is_a_directory_even_when_cut():
    """PROVEN against real GitHub 2026-11-15: reading `docs/` gave the cut line.

    `_said` tested the cut marker before the shape, so a 320,215-character
    listing answered "the answer was longer than Jarvis reads" - true, and
    useless: the model needed to know it had asked for a directory.
    """
    listing = json.dumps([{"name": f"file{i}.md", "path": f"docs/file{i}.md",
                           "type": "file"} for i in range(20_000)])
    cut = listing[:GH.MAX_BYTES] + GH.CUT_MARKER
    r = GH.plan_read_file({"repo": REPO, "path": "docs"})
    out = _run_request(r, Fake(200, cut))
    text = str(out.get("text", ""))
    check("a cut directory listing still says it is a directory",
          "directory" in text and "not a file" in text, text)
    check("... and not the cut sentence that hid it",
          "longer than Jarvis reads" not in text, text)
    # A cut FILE answer is still the cut sentence: there is no shape to report.
    out = _run_request(r, Fake(200, '{"encoding": "base64", "content": "a' +
                               GH.CUT_MARKER))
    check("a cut file answer is still an explicit cut",
          "longer than Jarvis reads" in str(out.get("text", "")), out)


def t_a_binary_file_is_not_shown_as_text():
    import base64
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(256)) * 6
    envelope = json.dumps({"type": "file", "encoding": "base64",
                           "content": base64.b64encode(png).decode("ascii"),
                           "size": len(png)})
    r = GH.plan_read_file({"repo": REPO, "path": "logo.png"})
    out = _run_request(r, Fake(200, envelope))
    text = str(out.get("text", ""))
    check("a binary blob is never shown as if it were the file's text",
          "\ufffd" not in text and "\x00" not in text and "PNG" not in text,
          repr(text)[:200])
    check("a binary blob is one plain sentence naming what it is",
          "not text" in text or "binary" in text, text[:200])
    # A real text file with an accent and an emoji still reads as text.
    good = json.dumps({"type": "file", "encoding": "base64",
                       "content": base64.b64encode(
                           "Caf\u00e9 \U0001f600".encode("utf-8")).decode("ascii")})
    out = _run_request(GH.plan_read_file({"repo": REPO, "path": "a.md"}),
                       Fake(200, good))
    check("a UTF-8 text file with an accent and an emoji is still shown",
          "Caf\u00e9" in str(out.get("text", "")), out.get("text"))


def t_a_non_json_or_empty_answer_is_never_an_empty_list():
    """A captive-portal page is not "there are no pull requests"."""
    for label, r in (
            ("github_list pulls",
             GH.plan_list({"scope": "pulls", "repo": REPO})),
            ("github_list repos", GH.plan_list({"scope": "repos"})),
            ("github_list issues",
             GH.plan_list({"scope": "issues", "repo": REPO})),
            ("github_pr_scan", GH.plan_scan_prs({"repo": REPO}))):
        for shape, body in (("a non-JSON body", "<html>sign in to the wifi</html>"),
                            ("an empty body", ""),
                            ("a JSON null", "null"),
                            ("a JSON object where a list belongs",
                             '{"message": "Not Found"}')):
            out = _run_request(r, Fake(200, body))
            # A read may refuse (the cockpit answers an explicit error) or answer
            # in words; either way it is one plain sentence and never a claim
            # that GitHub has nothing.
            text = str(out.get("text") or out.get("error") or "")
            none_words = ("no open pull requests" in text
                          or "no open issues" in text
                          or "cannot see any repositories" in text)
            check(f"{label} with {shape} is never a silent empty list",
                  not none_words, out)
            check(f"{label} with {shape} says plainly it could not be read",
                  _plain_words(text), text)


# --------------------------------------------------------------------------
#   4. Failure shapes, and 5. the token never appears
# --------------------------------------------------------------------------


def t_each_failure_shape_is_one_plain_sentence():
    r = GH.plan_list({"scope": "pulls", "repo": REPO})
    shapes = (
        ("401 the token was refused", 401, '{"message": "Bad credentials"}', None),
        ("403 a rate limit", 403,
         '{"message": "API rate limit exceeded for 1.2.3.4."}', None),
        ("404 nothing there", 404, '{"message": "Not Found"}', None),
        ("422 GitHub would not accept it", 422,
         '{"message": "Validation Failed"}', None),
        ("500 GitHub's own problem", 500, '{"message": "boom"}', None),
        ("429 too many requests", 429, '{"message": "slow down"}', None),
        ("a non-JSON body", 200, "<html>captive portal</html>", None),
        ("an empty body", 200, "", None),
        ("a redirect", 302, "", {"location": "https://evil.example/"}),
    )
    for label, status, body, headers in shapes:
        out = _run_request(r, Fake(status, body, headers))
        text = str(out.get("text") or out.get("error") or "")
        check(f"{label}: is an answer the owner can act on", bool(text), out)
        check(f"{label}: is one plain sentence", _plain_words(text), text)
        check(f"{label}: never leaks the token", TOKEN not in text, text)


def t_a_rate_limit_says_how_long_to_wait():
    """GitHub says how long; the owner is told it, instead of "try later"."""
    r = GH.plan_list({"scope": "pulls", "repo": REPO})
    out = _run_request(r, Fake(
        403, '{"message": "You have exceeded a secondary rate limit."}',
        {"retry-after": "90", "x-ratelimit-remaining": "0"}))
    text = str(out.get("error", ""))
    check("a 403 rate limit with Retry-After names the wait",
          "90 seconds" in text or "about a minute" in text, text)
    check("... in one plain sentence, with no HTTP code", _plain_words(text), text)
    out = _run_request(r, Fake(403, '{"message": "nope"}',
                               {"retry-after": "tomorrow-ish"}))
    check("a Retry-After that is not a number still gives a plain sentence",
          _plain_words(str(out.get("error", ""))), out)
    out = _run_request(r, Fake(403, '{"message": "nope"}'))
    check("a 403 with no header keeps its own plain sentence",
          _plain_words(str(out.get("error", ""))), out)
    out = _run_request(r, Fake(403, '{"message": "slow down"}',
                               {"retry-after": "0"}))
    check("a Retry-After of 0 does not become a nonsense wait",
          _plain_words(str(out.get("error", ""))), out)


def t_the_token_never_appears_in_any_words():
    """Every produced string, over a wide matrix, with the token injected."""
    produced = []
    for label, plan, args in VALID:
        with _Token():
            r = plan(dict(args))
            produced.append((label + " card", GH.describe(r)))
            produced.append((label + " what", r.what))
    reads = GH.plan_list({"scope": "pulls", "repo": REPO})
    writes = GH.plan_comment({"repo": REPO, "number": "1", "body": "hi"})
    bodies = ("[]", '{"message": "Bad credentials"}', TOKEN,
              '{"full_name": "' + TOKEN + '"}', "",
              "<html>" + TOKEN + "</html>")
    for status in (200, 401, 403, 404, 422, 500):
        for body in bodies:
            for r in (reads, writes):
                out = _run_request(r, Fake(status, body))
                produced.append((f"{r.action}/{status}", json.dumps(out)))
    leaked = [(where, str(text)[:300]) for where, text in produced
              if TOKEN in str(text)]
    check("the token appears in ZERO cards, answers or errors", not leaked,
          leaked[:2])
    # The token is really being used - otherwise the checks above would pass
    # because nothing was ever sent.
    sent = Fake(200, "[]")
    _run_request(reads, sent)
    header = sent.calls[0]["headers"].get("Authorization", "")
    check("the Authorization header really carries the token (so the checks "
          "above are not vacuous)", header == f"Bearer {TOKEN}", header)
    check("no card, answer or error ever carries a Bearer value",
          not [where for where, text in produced if "Bearer" in str(text)],
          "Bearer")
    check("_headers is the one place that header is built",
          GH._headers(TOKEN)["Authorization"] == f"Bearer {TOKEN}"
          and GH._headers(TOKEN)["User-Agent"] == GH.USER_AGENT)
    check("_scrub takes an echoed token out of fetched text",
          TOKEN not in GH._scrub("echoed " + TOKEN, TOKEN),
          GH._scrub(TOKEN, TOKEN))


def t_run_never_raises_and_never_runs_unapproved():
    r = GH.plan_comment({"repo": REPO, "number": "1", "body": "hi"})
    sent = Fake()
    out = _run_request(r, sent, approved=False)
    check("an unapproved run sends nothing at all",
          out.get("ok") is False and not sent.calls, out)
    check("an unapproved run says so in one plain sentence",
          "not approved" in str(out.get("error", ""))
          and TOKEN not in str(out.get("error", "")), out)
    for status, body in ((0, ""), (200, "{"), (200, "\xff"), (999, ""),
                         (-1, ""), (200, "[" * 50), (204, "")):
        try:
            out = _run_request(r, Fake(status, body))
        except Exception as exc:             # noqa: BLE001 - that IS the failure
            check(f"run() never raises ({status})", False,
                  f"{type(exc).__name__}: {exc}")
            continue
        check(f"run() answers a dictionary and never raises ({status})",
              isinstance(out, dict) and out.get("ok") in (True, False), out)


# --------------------------------------------------------------------------
#   6. The merge pin
# --------------------------------------------------------------------------


def t_a_merge_is_exactly_the_pinned_body():
    with _Token():
        r = GH.plan_merge_pr({"repo": REPO, "number": "1116", "head_sha": SHA,
                              "title": "Fix it", "base_ref": "main"})
    check("the merge body is exactly merge_method and the one sha",
          r.body == {"merge_method": "merge", "sha": SHA}, r.body)
    check("... and it carries nothing else at all",
          sorted(r.body) == ["merge_method", "sha"], sorted(r.body))
    check("merge_method is the module's own constant and is 'merge'",
          r.body["merge_method"] == GH.MERGE_METHOD == "merge", GH.MERGE_METHOD)
    check("the card's pinned commit is the body's sha and the run's pin",
          r.body["sha"] == r.expected_sha == SHA, (r.body, r.expected_sha))
    check("a merge is ONE PUT and nothing else",
          [(s.method, s.path) for s in r.steps] ==
          [("PUT", f"/repos/{REPO}/pulls/1116/merge")],
          [(s.method, s.path) for s in r.steps])
    # A model that tries to put its own merge fields in cannot: the body is built
    # field by field from the planner's own two values.
    with _Token():
        r = GH.plan_merge_pr({"repo": REPO, "number": "1116", "head_sha": SHA,
                              "title": "Fix it", "base_ref": "main",
                              "body": {"merge_method": "squash"},
                              "merge_method": "rebase", "commit_title": "x",
                              "commit_message": "y", "sha": "b" * 40,
                              "auto_merge": True})
    check("a model's own merge body, method and sha are ignored entirely",
          r.body == {"merge_method": "merge", "sha": SHA}, r.body)
    # The sha is refused BEFORE a request exists, so nothing can be sent with a
    # short, long or made-up commit id.
    for bad in ("a" * 39, "a" * 41, "", "main", "HEAD", "refs/heads/main",
                "z" * 40, SHA[:-1]):
        try:
            GH.plan_merge_pr({"repo": REPO, "number": "1116", "head_sha": bad,
                              "title": "Fix it", "base_ref": "main"})
        except GH.GitHubError as exc:
            check(f"a merge at {bad[:12]!r} is refused before any request",
                  _plain_words(str(exc)), str(exc))
            continue
        check(f"a merge at {bad[:12]!r} is refused before any request", False,
              "accepted")
    # And run() refuses a hand-built merge request whose pin is not a sha.
    bad_request = GH.Request(GH.ACTION_MERGE, "merge", (), expected_sha="abc",
                             repo=REPO, number="1116")
    sent = Fake()
    out = _run_request(bad_request, sent)
    check("a hand-built merge request with a bad pin is refused, not sent",
          out.get("ok") is False and not sent.calls, out)


if __name__ == "__main__":
    print(f"  file  {HERE / 'jarvis_github.py'}")
    print(f"  logs  {os.environ['JARVIS_LOG_DIR']}")
    with NoSocket():
        for fn in (t_a_repository_must_be_a_plain_owner_name,
                   t_a_file_path_stays_inside_the_repository,
                   t_a_title_and_a_body_are_bounded_and_cannot_carry_bidi,
                   t_a_number_is_a_real_github_number,
                   t_a_commit_must_be_a_full_40_hex_id,
                   t_a_branch_must_be_a_branch_name,
                   t_the_labels_and_the_verdict_are_closed_sets,
                   t_every_plan_starts_at_the_one_fixed_address,
                   t_a_request_the_module_did_not_write_is_refused_before_any_fetch,
                   t_a_redirect_is_refused_and_named,
                   t_a_five_megabyte_answer_is_cut_with_one_line,
                   t_a_cut_files_list_is_not_reported_as_zero_files,
                   t_a_malformed_detail_list_is_never_an_empty_section,
                   t_a_cut_pull_request_answer_is_an_explicit_error,
                   t_a_pull_request_ci_answer_cannot_say_passed_while_a_check_is_red,
                   t_the_runs_list_answers_even_when_the_answer_is_cut,
                   t_a_directory_listing_is_a_directory_even_when_cut,
                   t_a_binary_file_is_not_shown_as_text,
                   t_a_non_json_or_empty_answer_is_never_an_empty_list,
                   t_each_failure_shape_is_one_plain_sentence,
                   t_a_rate_limit_says_how_long_to_wait,
                   t_the_token_never_appears_in_any_words,
                   t_run_never_raises_and_never_runs_unapproved,
                   t_a_merge_is_exactly_the_pinned_body):
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
