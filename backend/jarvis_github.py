"""jarvis_github.py - read the owner's GitHub, and take three small actions on it.

WHAT IT IS FOR

The owner's decision of 2026-11-03: Jarvis may READ his GitHub (his repos, open
pull requests, issues, CI status, and a file in a repo) and may take a few
ACTIONS (comment on an issue or pull request, open an issue, re-run a workflow),
each action behind its own approval card - and it may never merge, push, commit,
delete or close anything.

`jarvis_connect_account.py` already gets the token: "connect GitHub" raises one
card for a personal access token, checks it with `GET /user`, and stores it in
Windows Credential Manager as `jarvis_research.TOKEN_TARGET`. This module spends
that same secret and invents no second way to store one.

THE SHAPE, WHICH IS THE POINT

    plan_*(args)  -> Request    works out exactly what would be sent, and sends
                                nothing. No socket is opened.
    describe(r)   -> str        the words on the approval card.
    run(r, ...)                 only ever called after a person said yes.

`run()` has no default that means "go ahead": `approved` must be passed, so a
module that can reach the network is never one function call away from doing it
by accident. This is the same split `jarvis_research.py` already uses, for the
same reason.

WHAT LEAVES THIS PC, EXACTLY

  * The GitHub token, in an `Authorization` header, to `api.github.com` and to
    nothing else. There is no arbitrary-URL code path here at all: every request
    is built from `GITHUB_API` plus a path this module wrote, so a model cannot
    point it at another host. A redirect is REFUSED rather than followed
    (`_RefuseRedirect`), because following one would hand the token to whoever
    answered.
  * For a read: the scope name, the repository name, a path inside that
    repository, a branch name, or a pull request / run number - all of which the
    owner or the model named, and all of which are printed on the card first.
  * For an action: the comment text, or the issue's title and body, word for
    word, as it will be posted. Nothing else is ever sent.

Nothing from email, files, saved memory, notes or credentials is read here or
put in a request. This module has no import of `jarvis_email`,
`jarvis_token_store` (past the one read of its own target), `jarvis_memory` or
`jarvis_files`, and nothing in it enumerates a folder.

THE TOKEN IS NEVER PRINTED

Not in a card, not in a tool result, not in a log line, not in an exception
message. `describe()` says only THAT a token is saved, never with what. A text
GitHub sends back is scrubbed before it is shown, in case a server ever echoes
something it was handed (`_scrub`).

FAILURES ARE SAID IN PLAIN WORDS

The owner reads the answer, so it never says "HTTP 403". It says what happened
and what to do about it: the key was refused (save a new one), GitHub said no
for now (too many looks in an hour), there is no such repository (or it is
private and the saved key cannot see it).

WHAT THIS MODULE WILL NEVER DO

Merge, push, commit, delete, close, edit a file, or write code of any kind.
There is no planner, no endpoint and no tool for any of them; `NEVER` names
them and `never_words()` is the plain sentence a person gets instead. The
absence is the control, and `backend/test_github_tools.py` pins the absence.

Standard library only.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

#: The one host this module may talk to. Every URL it builds starts with this.
GITHUB_API = "https://api.github.com"

#: Long enough for a slow answer from GitHub, short enough that a dead network
#: does not hold a turn until the owner gives up waiting.
TIMEOUT = 20.0

#: A hard cap on how much of any answer is read. GitHub can return a lot more
#: than a person needs, and a read that streams forever is a hang with a nicer
#: name. The marker says plainly when it was cut.
MAX_BYTES = 200_000
CUT_MARKER = "\n(GitHub's answer was longer than Jarvis reads, so it was cut here.)"

#: A file read is the one answer whose whole point is its text, so it keeps a
#: separate, smaller cap: a 40,000-character file is already too long to read
#: out, and the model gets the top of it plus a plain note.
MAX_FILE_CHARS = 40_000

#: The longest comment or issue body this module will put on a card. The gate
#: keeps 4,000 characters for a whole card (`jarvis_agent._GATE_DETAIL_LIMIT`),
#: and a card that would be cut is refused rather than shown in part - so the
#: limit is well inside that, and a longer text is refused here with words the
#: owner can act on instead of a card that cannot be shown.
MAX_TEXT = 2_000

#: How many repos / pull requests / issues / runs one read asks for.
PER_PAGE = 20

#: The GitHub REST API version this module speaks. Sent on every request so a
#: future change to GitHub's defaults cannot silently change what is read.
API_VERSION = "2022-11-28"

USER_AGENT = "jarvis-github"

#: The four things this module is allowed to do, as the gate action each one is
#: decided under. These names are also the `[autonomy.tiers]` keys and the
#: `_RISK` rows in `jarvis_gate.py` (github-tools.patch), so the card a person
#: sees and the tier that governs it are always the same thing.
ACTION_INSPECT = "github_inspect"
ACTION_COMMENT = "github_comment"
ACTION_OPEN_ISSUE = "github_open_issue"
ACTION_RERUN = "github_rerun_workflow"

#: Read scopes `github_list` accepts. A closed set, never an arbitrary URL: the
#: model picks a NAME here, and this module decides what that name means.
SCOPES = ("repos", "pulls", "issues", "runs")

#: What each scope reads, in the owner's words.
SCOPE_WORDS = {
    "repos": "your repositories, most recently updated first",
    "pulls": "the open pull requests on this repository",
    "issues": "the open issues on this repository",
    "runs": "the most recent workflow runs on this repository",
}

#: The one sentence a person gets when they ask for something this module does
#: not do. Kept here, in one place, so every path says the same thing.
NEVER = frozenset({"merge", "push", "commit", "delete", "close", "edit_file",
                   "write_file", "create_branch", "force_push", "approve_pr"})
NEVER_WORDS = ("Jarvis cannot merge, push, commit, delete or close anything on "
               "GitHub - it can read your GitHub, comment, open an issue and "
               "re-run a workflow, and nothing else. That is deliberate: a "
               "mistake in any of those cannot be undone.")

#: Said when no token is saved yet. NOT a card: there is nothing to approve,
#: and a card nobody can act on is noise. `backend/jarvis_connect_account.py`
#: is the one writer that fixes it.
NOT_CONNECTED = ('Jarvis has no GitHub token saved yet, so it cannot read your '
                 'GitHub. Say "connect GitHub" and one card appears for a '
                 'personal access token.')

#: The parts of a repository / path / ref that this module will accept. Strict
#: on purpose: these values are put INTO a URL, so a `/`, a `?`, a `#` or a
#: `..` that slipped through would let a model choose a different request than
#: the one the card showed. Only the characters GitHub itself allows survive.
_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,199}$")
_PATH = re.compile(r"^[A-Za-z0-9_.\-/ ]{1,400}$")
_NUMBER = re.compile(r"^[0-9]{1,12}$")


class GitHubError(Exception):
    """A refusal or a failure, already in words a person can read."""


class NotConnected(GitHubError):
    """No token is saved yet. Raised from a planner, so no card is raised."""


# --------------------------------------------------------------------------
#   The token: one name, read the way every other named secret is read
# --------------------------------------------------------------------------


def _research():
    """`jarvis_research` when it can be imported, else None.

    It owns the token's NAME (`TOKEN_ENV`, `TOKEN_TARGET`) and the sentence
    "a token is configured" (`authenticated`). Reading those through it - rather
    than writing a second copy of the strings here - is what stops the
    connect-a-card writer and this reader from drifting apart and leaving the
    owner with a token saved where nothing looks for it.
    """
    try:
        import jarvis_research
        return jarvis_research
    except Exception:                        # noqa: BLE001 - absent is a state
        return None


def token_env() -> str:
    r = _research()
    return str(getattr(r, "TOKEN_ENV", "JARVIS_GITHUB_TOKEN"))


def token_target() -> str:
    r = _research()
    return str(getattr(r, "TOKEN_TARGET", "Jarvis Backend/GitHub token"))


def _token() -> str:
    """The saved token, or "". Never logged, never returned to a caller."""
    import jarvis_token_store
    return jarvis_token_store.resolve_secret(token_env(), token_target())


def connected() -> bool:
    """Whether a token is saved. Never reveals the token itself."""
    try:
        return bool(_token())
    except Exception:                        # noqa: BLE001 - no store is "no"
        return False


def _need_token() -> str:
    """The token, or a plain refusal with NO card raised."""
    try:
        value = _token()
    except Exception:                        # noqa: BLE001 - the NAME only
        value = ""
    if not value:
        raise NotConnected(NOT_CONNECTED)
    return value


def _scrub(text: str, token: str) -> str:
    """`text` with the token taken out of it if it was ever echoed back."""
    text = str(text or "")
    if token and token in text:
        text = text.replace(token, "(the token, which Jarvis does not show)")
    return text


# --------------------------------------------------------------------------
#   One request, worked out before anything is sent
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One HTTP request: method plus a path under GITHUB_API.

    `path` may hold `{commit}`, filled in by `run()` from the answer to the step
    before it - which is how "the CI status of this pull request's newest
    commit" is two requests without either of them being an arbitrary URL.
    """

    method: str
    path: str

    def url(self) -> str:
        return GITHUB_API + self.path

    def shown_url(self) -> str:
        """The address as the CARD shows it: a placeholder stays a word."""
        return self.url().replace("{commit}", "<the commit GitHub names>")


@dataclass(frozen=True)
class Request:
    """What a person is being asked about, worked out with no socket open."""

    action: str                   # which gate action decides it
    what: str                     # one plain sentence: what it will do
    steps: tuple = ()             # Step objects, in the order they are sent
    body: Optional[dict] = None   # JSON body, for an action only
    shows: str = ""               # the exact text that will be posted, if any
    touches: str = ""             # one plain sentence: what changes on GitHub

    def urls(self) -> tuple:
        return tuple(s.url() for s in self.steps)


def describe(r: Request) -> str:
    """The approval card's words: what, where, and what changes.

    Every address is printed LITERALLY, and the text of a comment or an issue is
    printed in full - the honest version of "may I post this" is to show the
    thing that will be posted, not a summary of it.
    """
    if r is None:
        return "Jarvis wants to do something on GitHub."
    lines = [r.what.rstrip()]
    if r.shows:
        lines.append("")
        lines.append(r.shows.rstrip())
    lines.append("")
    for step in r.steps:
        lines.append(f"  {step.method} {step.shown_url()}")
    if r.touches:
        lines.append("")
        lines.append(r.touches.rstrip())
    lines.append("")
    lines.append("The GitHub token saved on this PC is sent to api.github.com and "
                 "nowhere else; it is never shown.")
    if r.action != ACTION_INSPECT:
        lines.append("Nothing is merged, pushed, committed, deleted or closed - "
                     "Jarvis cannot do any of those.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   The planners - each one validates its own arguments and sends nothing
# --------------------------------------------------------------------------


def _check_repo(repo: str) -> str:
    repo = str(repo or "").strip()
    if not _REPO.match(repo):
        raise GitHubError('Jarvis needs a repository named like "owner/name" '
                          '(letters, numbers, dot, dash and underscore only).')
    return repo


def _check_ref(ref: str) -> str:
    ref = str(ref or "").strip()
    if not _REF.match(ref) or ".." in ref:
        raise GitHubError("That branch name does not look like a branch name, so "
                          "Jarvis did not ask GitHub about it.")
    return ref


def _check_path(path: str) -> str:
    path = str(path or "").strip().lstrip("/")
    if not path:
        raise GitHubError("Jarvis needs a file path inside the repository.")
    if not _PATH.match(path) or ".." in path.split("/"):
        raise GitHubError("That file path does not look like a path inside a "
                          "repository, so Jarvis did not ask GitHub for it.")
    return path


def _check_number(value, what: str) -> str:
    text = str(value or "").strip().lstrip("#")
    if not _NUMBER.match(text):
        raise GitHubError(f"Jarvis needs a {what} number, and that was not one.")
    return text


def _check_text(text: str, what: str) -> str:
    """The text that will be posted, bounded so its card can always be shown."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise GitHubError(f"Jarvis needs the {what} itself - there was no text to post.")
    if len(text) > MAX_TEXT:
        raise GitHubError(f"That {what} is longer than Jarvis will post in one go "
                          f"({MAX_TEXT} characters). Shorten it, or split it into "
                          f"a few comments.")
    return text


def _repo_path(repo: str) -> str:
    return "/repos/" + urllib.parse.quote(repo, safe="/")


def plan_list(args: Optional[dict] = None) -> Request:
    """Read a fixed list: your repos, or one repo's PRs, issues or runs."""
    args = args or {}
    scope = str(args.get("scope") or "repos").strip().lower()
    if scope not in SCOPES:
        raise GitHubError('Jarvis can list one of these on GitHub: your '
                          'repositories, the open pull requests, the open issues, '
                          'or the recent workflow runs.')
    if scope == "repos":
        step = Step("GET", f"/user/repos?per_page={PER_PAGE}&sort=updated")
        return Request(
            ACTION_INSPECT,
            f"Jarvis will read {SCOPE_WORDS[scope]}.",
            (step,),
            touches="Nothing on GitHub changes; this only reads.",
        )
    repo = _check_repo(args.get("repo"))
    if scope == "pulls":
        path = f"{_repo_path(repo)}/pulls?state=open&per_page={PER_PAGE}"
    elif scope == "issues":
        path = f"{_repo_path(repo)}/issues?state=open&per_page={PER_PAGE}"
    else:
        path = f"{_repo_path(repo)}/actions/runs?per_page={PER_PAGE}"
    return Request(
        ACTION_INSPECT,
        f"Jarvis will read {SCOPE_WORDS[scope]} ({repo}).",
        (Step("GET", path),),
        touches="Nothing on GitHub changes; this only reads.",
    )


def plan_read_file(args: Optional[dict] = None) -> Request:
    """Read ONE file's text, at an optional branch or commit."""
    args = args or {}
    repo = _check_repo(args.get("repo"))
    path = _check_path(args.get("path"))
    ref = _check_ref(args["ref"]) if str(args.get("ref") or "").strip() else ""
    query = f"?ref={urllib.parse.quote(ref, safe='')}" if ref else ""
    step = Step("GET", f"{_repo_path(repo)}/contents/"
                        f"{urllib.parse.quote(path, safe='/')}{query}")
    where = f" on {ref}" if ref else ""
    return Request(
        ACTION_INSPECT,
        f"Jarvis will read the file {path} in {repo}{where}.",
        (step,),
        touches="Nothing on GitHub changes; this only reads one file.",
    )


def plan_ci(args: Optional[dict] = None) -> Request:
    """The latest CI run for a repository and branch, or for a pull request."""
    args = args or {}
    repo = _check_repo(args.get("repo"))
    pr = str(args.get("pr") or "").strip()
    branch = str(args.get("branch") or "").strip()
    if pr and branch:
        raise GitHubError("Ask about a branch OR a pull request, not both.")
    if pr:
        number = _check_number(pr, "pull request")
        return Request(
            ACTION_INSPECT,
            f"Jarvis will look at pull request {number} in {repo}, then at the CI "
            f"runs for the commit at its head.",
            (Step("GET", f"{_repo_path(repo)}/pulls/{number}"),
             Step("GET", f"{_repo_path(repo)}/actions/runs?head_sha={{commit}}"
                         f"&per_page={PER_PAGE}")),
            touches="Nothing on GitHub changes; this only reads which run is newest and how it ended.",
        )
    if branch:
        ref = _check_ref(branch)
        return Request(
            ACTION_INSPECT,
            f"Jarvis will read the most recent workflow runs for {ref} in {repo}.",
            (Step("GET", f"{_repo_path(repo)}/actions/runs"
                         f"?branch={urllib.parse.quote(ref, safe='')}"
                         f"&per_page={PER_PAGE}"),),
            touches="Nothing on GitHub changes; this only reads how the newest run ended.",
        )
    return Request(
        ACTION_INSPECT,
        f"Jarvis will read the most recent workflow runs for {repo}.",
        (Step("GET", f"{_repo_path(repo)}/actions/runs?per_page={PER_PAGE}"),),
        touches="Nothing on GitHub changes; this only reads how the newest run ended.",
    )


def plan_comment(args: Optional[dict] = None) -> Request:
    """Post ONE comment on an issue or pull request, as the owner."""
    args = args or {}
    repo = _check_repo(args.get("repo"))
    number = _check_number(args.get("number"), "issue or pull request")
    text = _check_text(args.get("body"), "comment")
    return Request(
        ACTION_COMMENT,
        f"Jarvis will post this comment on {repo}, issue or pull request {number}, "
        f"as you:",
        (Step("POST", f"{_repo_path(repo)}/issues/{number}/comments"),),
        body={"body": text},
        shows=text,
        touches=(f"Your GitHub account posts one public-if-the-thread-is-public "
                 f"comment. It cannot be edited or taken back by Jarvis, and "
                 f"nothing else on GitHub changes."),
    )


def plan_open_issue(args: Optional[dict] = None) -> Request:
    """Open ONE issue: a title, and optionally a body."""
    args = args or {}
    repo = _check_repo(args.get("repo"))
    title = str(args.get("title") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    title = " ".join(title.split())
    if not title:
        raise GitHubError("Jarvis needs the issue's title - there was none to post.")
    if len(title) > 200:
        raise GitHubError("That issue title is longer than GitHub will take (200 "
                          "characters). Shorten it.")
    body = str(args.get("body") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if body:
        body = _check_text(body, "issue text")
    shows = title if not body else f"{title}\n\n{body}"
    payload = {"title": title}
    if body:
        payload["body"] = body
    return Request(
        ACTION_OPEN_ISSUE,
        f"Jarvis will open a new issue on {repo}, as you:",
        (Step("POST", f"{_repo_path(repo)}/issues"),),
        body=payload,
        shows=shows,
        touches=("Your GitHub account opens one new issue. Jarvis cannot close, "
                 "edit or delete it afterwards, and nothing else changes."),
    )


def plan_rerun(args: Optional[dict] = None) -> Request:
    """Re-run ONE workflow run that already exists, exactly as it ran before."""
    args = args or {}
    repo = _check_repo(args.get("repo"))
    run_id = _check_number(args.get("run_id"), "workflow run")
    return Request(
        ACTION_RERUN,
        f"Jarvis will ask GitHub to run workflow run {run_id} in {repo} again, "
        f"with the same code and settings it ran with before.",
        (Step("POST", f"{_repo_path(repo)}/actions/runs/{run_id}/rerun"),),
        touches=("This starts one CI run that has already run before. It changes "
                 "no code and no repository setting; it only spends the work of "
                 "running the checks again."),
    )


#: The three actions this module can take, by name - the closed set. A name
#: outside it is a bug, not a feature: `run()` refuses it.
ACTIONS = (ACTION_COMMENT, ACTION_OPEN_ISSUE, ACTION_RERUN)


def never_words(name: str = "") -> str:
    """The plain sentence for anything this module will never do."""
    return NEVER_WORDS


# --------------------------------------------------------------------------
#   Running one - only after a person said yes
# --------------------------------------------------------------------------


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses a redirect instead of following it.

    A redirect is how a request to one host becomes a request to ANOTHER host,
    and this request carries the owner's GitHub token in a header. urllib would
    hand the header to whatever it was redirected to. GitHub's own API does not
    redirect a normal call; anything that does is not GitHub, and the answer is
    no. `jarvis_research.py` already refuses redirects for the same reason.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code,
            "refused to follow a redirect: the GitHub token would have been sent there",
            headers, fp)


def _default_fetch(method: str, url: str, *, headers: dict,
                   body: Optional[bytes] = None,
                   timeout: float = TIMEOUT) -> tuple:
    """(status, text). The only place in this module that opens a socket.

    `fetch` is injectable everywhere else so every test can drive this module
    with a fake and no network, which is how it is tested here.
    """
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(_RefuseRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            raw = r.read(MAX_BYTES)
            return int(getattr(r, "status", 200) or 200), raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(MAX_BYTES)
        except Exception:                    # noqa: BLE001 - no body is fine
            raw = b""
        return int(exc.code or 0), raw.decode("utf-8", "replace")


def _headers(token: str) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": API_VERSION,
        "Authorization": f"Bearer {token}",
    }


def _plain_failure(status: int, *, token: Optional[str] = None) -> str:
    """A failure sentence with NO HTTP code in it, and what to do about it.

    The owner reads this, so "HTTP 403" tells them nothing they can act on. Each
    line names the cause in their own terms and says what fixes it.
    """
    if status == 0:
        return ("api.github.com could not be reached from this PC. Check the "
                "internet connection, then ask again.")
    if status == 401:
        return ('GitHub refused the token saved on this PC - it may have expired '
                'or been cancelled. Say "connect GitHub" to save a new one.')
    if status == 403:
        return ("GitHub said no for now. Either the token is not allowed to do "
                "this, or too many requests were made from this address in the "
                "last hour; it works again when GitHub's own limit resets.")
    if status == 404:
        return ("GitHub says there is nothing there - or it is private and the "
                "token saved on this PC cannot see it.")
    if status == 409:
        return "GitHub says that is empty, so there was nothing to do."
    if status == 422:
        return ("GitHub would not accept that, because something in it is not "
                "valid to GitHub (an empty body, or a name it does not allow).")
    if status == 429:
        return ("Too many requests were made from this address in the last hour. "
                "It works again when GitHub's own limit resets.")
    if 500 <= status <= 599:
        return "GitHub had a problem on its own side. Ask again in a little while."
    return "GitHub did not answer the way it should have, so nothing was changed."


def run(r: Request, *, fetch: Optional[Callable] = None,
        approved: bool = False) -> dict:
    """Do the one request `r` describes. `approved` is not a courtesy argument.

    It has no default of True on purpose: the caller has to have gone and got an
    answer from a person. Every failure comes back as `{"ok": False, "error":
    <plain sentence>}` - never a raised exception the caller might swallow, and
    never an HTTP code in the text the owner reads.
    """
    if not approved:
        return {"ok": False, "error": "not approved; nothing was sent"}
    if r is None:
        return {"ok": False, "error": "there was nothing to ask GitHub about"}
    if r.action not in (ACTION_INSPECT,) + ACTIONS:
        return {"ok": False, "error": "Jarvis has no way to do that on GitHub."}
    try:
        token = _need_token()
    except GitHubError as exc:
        return {"ok": False, "error": str(exc)}
    fetch = fetch or _default_fetch
    headers = _headers(token)
    payload = None
    if r.body is not None:
        payload = json.dumps(r.body, ensure_ascii=False).encode("utf-8")
        headers = dict(headers, **{"Content-Type": "application/json"})

    answers = []
    commit = ""
    for step in r.steps:
        path = step.path
        if "{commit}" in path:
            if not commit:
                return {"ok": False,
                        "error": "GitHub did not name the commit to look at, so "
                                 "Jarvis could not read its CI."}
            path = path.replace("{commit}", urllib.parse.quote(commit, safe=""))
        url = GITHUB_API + path
        try:
            status, text = fetch(step.method, url, headers=headers, body=payload,
                                 timeout=TIMEOUT)
        except Exception as exc:             # noqa: BLE001 - the NAME only
            return {"ok": False,
                    "error": f"api.github.com did not answer ({type(exc).__name__}), "
                             f"so nothing was changed."}
        if status < 200 or status >= 300:
            return {"ok": False, "error": _plain_failure(status, token=token)}
        answers.append((status, _scrub(text, token)))
        if "{commit}" not in "".join(s.path for s in r.steps):
            continue
        try:
            body = json.loads(answers[0][1] or "{}")
            commit = str((body or {}).get("head", {}).get("sha") or "")
        except Exception:                    # noqa: BLE001 - no sha, said below
            commit = ""

    return {"ok": True, "text": _said(r, answers)}


def _payload(text: str):
    """The JSON an answer holds, or None - GitHub answers 204 with no body."""
    if not text or not str(text).strip():
        return None
    try:
        return json.loads(text)
    except Exception:                        # noqa: BLE001 - not JSON is fine
        return None


def _cut(text: str, limit: int = MAX_BYTES) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + CUT_MARKER


def _said(r: Request, answers: list) -> str:
    """The answer, in plain words, from the last body the requests returned."""
    text = answers[-1][1] if answers else ""
    doc = _payload(text)
    if r.action == ACTION_COMMENT:
        return "The comment was posted."
    if r.action == ACTION_OPEN_ISSUE:
        number = ""
        if isinstance(doc, dict):
            number = str(doc.get("number") or "")
        return ("The issue was opened" + (f" as number {number}" if number else "") + ".")
    if r.action == ACTION_RERUN:
        return ("GitHub accepted the re-run. It starts in a moment, and the newest "
                "run's result is what github_ci_status will show.")
    if r.action != ACTION_INSPECT:
        return "Done."
    # A read: shape it by which planner built it, so the words match the question.
    steps = tuple(r.steps)
    if len(steps) == 2:
        return _ci_words(_payload(answers[-1][1]) if answers else None)
    first = steps[0].path if steps else ""
    if first.startswith("/user/repos"):
        return _repos_words(doc)
    if "/pulls?" in first:
        return _pulls_words(doc)
    if "/issues?" in first:
        return _issues_words(doc)
    if "/actions/runs" in first:
        return _ci_words(doc)
    if "/contents/" in first:
        return _file_words(text)
    return _cut(text).strip() or "GitHub answered, and there was nothing to show."


def _list(doc):
    return doc if isinstance(doc, list) else []


def _repos_words(doc) -> str:
    items = _list(doc)
    if not items:
        return "That GitHub token cannot see any repositories."
    out = [f"Your {len(items)} most recently updated repositories:"]
    for repo in items:
        if not isinstance(repo, dict):
            continue
        name = str(repo.get("full_name") or "")
        private = " (private)" if repo.get("private") else ""
        out.append(f"  {name}{private}")
    return "\n".join(out)


def _pulls_words(doc) -> str:
    items = _list(doc)
    if not items:
        return "There are no open pull requests on that repository."
    out = [f"{len(items)} open pull request(s):"]
    for pr in items:
        if not isinstance(pr, dict):
            continue
        out.append(f'  #{pr.get("number")} {str(pr.get("title") or "").strip()}'
                   f' (by {str((pr.get("user") or {}).get("login") or "someone")})')
    return "\n".join(out)


def _issues_words(doc) -> str:
    items = [i for i in _list(doc)
             if isinstance(i, dict) and "pull_request" not in i]
    if not items:
        return "There are no open issues on that repository."
    out = [f"{len(items)} open issue(s):"]
    for issue in items:
        out.append(f'  #{issue.get("number")} {str(issue.get("title") or "").strip()}')
    return "\n".join(out)


def _ci_words(doc) -> str:
    if not isinstance(doc, dict):
        return "GitHub answered without saying anything about CI."
    runs = doc.get("workflow_runs")
    if runs is None:
        runs = [doc] if doc.get("conclusion") or doc.get("status") else []
    runs = [r for r in runs if isinstance(r, dict)]
    if not runs:
        return "There is no recent CI run there to report."
    newest = runs[0]
    status = str(newest.get("status") or "")
    conclusion = str(newest.get("conclusion") or "")
    name = str(newest.get("name") or "a workflow").strip()
    branch = str((newest.get("head_branch") or "")).strip()
    where = f" on {branch}" if branch else ""
    if status and status != "completed":
        return f"The newest CI run ({name}{where}) is still going: {status}."
    if conclusion == "success":
        return f"The newest CI run ({name}{where}) passed."
    if conclusion in ("failure", "timed_out", "startup_failure"):
        return (f"The newest CI run ({name}{where}) failed. GitHub keeps the log; "
                f"Jarvis does not read it.")
    if conclusion == "cancelled":
        return f"The newest CI run ({name}{where}) was cancelled."
    if conclusion:
        return f"The newest CI run ({name}{where}) finished as {conclusion}."
    return f"The newest CI run ({name}{where}) has not finished yet."


def _file_words(text: str) -> str:
    if not str(text or "").strip():
        return "That file is empty."
    return _cut(text, MAX_FILE_CHARS).strip()
