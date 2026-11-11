"""jarvis_review.py - look a change over before it is pushed, and check its records.

WHAT IT IS FOR

Two questions the owner asks before a branch goes anywhere, answered on this PC
with no model, no GitHub token and no network:

  * `review()` - the REVIEW PACKET. What changed, grouped by the part of the
    program it belongs to, with the base and head commits, the line counts, and
    a short list of RISK FLAGS - each one the concrete evidence for a thing that
    usually goes wrong here, never a verdict. The owner's own three-part audit
    checklist and the review rules ride at the end, because they are what a
    person is supposed to do with the packet.

  * `record_check()` - the REPOSITORY RECORD CHECK. The bookkeeping this
    repository's CI demands of every pull request, checked before the push
    instead of after a red run: exactly one `changelog.d/` fragment and no
    `CHANGELOG.md` edit, the `docs/README.md` count bumped when a document was
    added, every changed `backend/<file>` carried to `jarvis-backend/<file>`,
    ONE decision record, well-shaped claims and defect rows - plus the
    repository's own read-only checkers, run from a fixed allow-list.

Both are READ-ONLY, and that is the whole design: no file is written, moved or
deleted, no socket is opened, no token is read, and no command is ever built out
of anything but a constant plus a value this module validated itself. This is a
GATE, not a fixer - it says what is wrong and what the next step is, and the
person (or an agent) does it.

THE SHAPE

    review(args, run=...)       -> {"ok": True, "text": ..., "measured": {...}}
    record_check(args, run=...) -> {"ok": True, "text": ..., "measured": {...}}

`args` is a small dict: `path` (the repository folder - `JARVIS_REVIEW_REPO` is
used when it is absent), `base` (the ref to compare against; `origin/main`, then
`main`, then `master` are tried), `branch` (review that branch instead of the
current checkout), `pr` (a pull request NUMBER, resolved to the local branch
that carries it - nothing is fetched), `limit_files`.

`run(argv, cwd, timeout)` is the ONE process seam: `(argv, cwd, timeout) ->
Ran`. No test starts git or a checker, and the default is `_default_run`. A
failure to start is `Ran(started=False)`, never an exception the caller might
swallow.

WHAT LEAVES THIS PC

Nothing. The module imports no network library at all - not `socket`, not
`urllib`, not `http` - and `backend/test_github_review.py` pins that with an
`ast` walk over this file rather than a promise in a docstring. The commands it
runs are `git` (read-only plumbing only: `rev-parse`, `merge-base`, `diff`,
`status`, `for-each-ref`, `show`) and this repository's own `tools/check_*.py`
and `backend/test_base_*.py` checkers through the Python that runs the backend.
Each child gets an environment with anything that looks like a credential
removed (`_child_env`), `PYTHONDONTWRITEBYTECODE=1` so no `__pycache__` appears
in the tree it just measured, and `GIT_OPTIONAL_LOCKS=0` so not even a `git
status` may refresh the index.

WHY A DENYLIST FOR THE FOLDER, AND WHY IT IS NOT A SECURITY BOUNDARY

`path` is a folder the owner or the model names. A review shows file NAMES and
line COUNTS, never a file's words, so its disclosure is small - but a folder
that holds keys or browser data is still refused by name (`_path_refused`), and
the Windows folder and Program Files are refused too. That is a guard rail, not
a sandbox: the real control is that this module only ever reads names, counts
and two file bodies (`docs/README.md` and a changed record row) which are the
owner's own repository's.

WHY IT DOES NOT USE ITS OWN CHECKS FOR EVERYTHING

The record rules have ONE home each: `tools/roll_changelog.py`,
`tools/roll_decisions.py`, `tools/check_claims.py` and the rest are the
authority, and this module runs them rather than re-implementing them. What it
checks itself is only the handful of obligations CI derives from the CHANGE SET
(which files moved together), where the repository's own tools look at the whole
tree and cannot know what this branch touched. `_validate_*` below mirrors the
tools' published shapes closely enough to say "this row is wrong" in words; the
tool is still the judge, and its verdict is in the table.

NOTHING HERE IS A PASS IF IT DID NOT RUN

A checker that could not start, ran out of time, or was not in this tree is
NOT-RUN or TIMEOUT, with the reason, and it is never counted as a pass. The
verdict can only be READY when no obligation is MISSING/FAIL and every checker
that was supposed to run really passed (`_verdict`).

WHERE THE REPOSITORY IS

The backend runs from its installed folder, which is not the git checkout. So
the folder comes from `JARVIS_REVIEW_REPO`, or from the `path` argument, and
when neither is there the answer is one sentence saying exactly that - never a
guess at a path. `jarvis_agent.py` puts the same sentence in the tool's result.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   The limits, in one place, so no renderer can outgrow the chat window
# --------------------------------------------------------------------------

#: The hard cap on one rendered answer. DeepSeek's own review packet is 7,000
#: characters and this mirrors it: a report a person cannot get to the end of is
#: not a report. `fit_text` is the last line of defence, and every renderer
#: below also bounds its own lists.
REVIEW_MAX_TEXT = 7_000
RECORD_MAX_TEXT = 7_000

#: What a spoken (Live) answer is cut to. A 7,000-character report read aloud is
#: not usable, so the deterministic chat path asks for a short form and gets the
#: verdict, the counts and the reason.
SHORT_MAX_TEXT = 900

#: How many changed files are looked at, listed, and counted. Past this the
#: packet says it is summarising, which is itself a risk flag.
MAX_CHANGED_FILES = 200
MAX_FILES_PER_AREA = 8

#: One git command's ceiling. Every command here is local plumbing, so this is
#: generous for a slow disk and still short enough that a broken output pipe
#: cannot hang a chat answer.
GIT_TIMEOUT = 30.0

#: One checker's ceiling, and the claims checker's own (it re-runs the suites its
#: rows name - measured here, that is the slowest thing in the run by far, which
#: is why its own ceiling matches DeepSeek's 900-second one). The total budget is
#: what keeps a chat answer from sitting forever: when it is spent, every
#: remaining checker is reported NOT-RUN with that reason.
CHECK_TIMEOUT = 120.0
CLAIMS_TIMEOUT = 600.0
TOTAL_CHECK_BUDGET = 900.0

#: How much of a checker's output is kept, and how much of a failure is shown.
#: Bounded output is the rule: one noisy checker must not push the verdict off
#: the end of the answer.
MAX_CHECK_OUTPUT = 12_000
MAX_EXCERPT_LINES = 8
MAX_EXCERPT_CHARS = 300

#: How many untracked files' lines are counted (a bounded read of each, under
#: 1 MiB and only if it looks like text). Past this the packet says so.
MAX_UNTRACKED_COUNTED = 100
MAX_UNTRACKED_BYTES = 1_048_576

#: Where the repository is when the owner has not named one. Documented in
#: `docs/JARVIS-API.md`; the tools' own words say it too.
ENV_REPO = "JARVIS_REVIEW_REPO"

#: The refs a review compares against, in the order it tries them. Never
#: fetched: a stale `origin/main` is reported as stale, not quietly updated.
DEFAULT_BASES = ("origin/main", "main", "master")

#: A git ref this module is willing to put in a command. The same shape
#: DeepSeek's gate uses (`SAFE_REF`), and it is the ONLY caller-supplied value
#: that reaches a command line; `path` reaches only `cwd`.
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@^~+-]{0,199}$")

#: A full or abbreviated commit sha, as git prints one.
_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")

#: A fragment's name, the same shape `tools/roll_changelog.py` and
#: `tools/roll_decisions.py` publish (`FRAGMENT_RE` in both).
_FRAGMENT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9][a-z0-9-]*)\.md$")

#: ONE dated decision bullet: `- **YYYY-MM-DD - Title:** prose`. The separator
#: is the em dash, exactly as `tools/roll_decisions.py`'s own `BULLET_RE` has it.
_DECISION_BULLET = re.compile(r"^- \*\*(\d{4}-\d{2}-\d{2}) \u2014 .+?:\*\*\s+\S", re.S)

#: The six kinds a claims row's `check` column may begin with
#: (`tools/check_claims.py`'s own list).
CLAIM_CHECK_KINDS = ("file:", "no-file:", "grep:", "absent:", "test:", "number:")

#: The states a claims row may carry.
CLAIM_STATES = ("built", "open", "unverifiable")

#: The states a defect row may carry.
DEFECT_STATES = ("open", "closed")

#: What counts as a test file here: the families this repository uses (the same
#: list DeepSeek's review uses, because it is the same repository).
_TEST_PATTERNS = (
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"(^|/)eval_[^/]+\.py$"),
    re.compile(r"[^/]+\.test\.mjs$"),
    re.compile(r"[^/]+Tests?\.kt$"),
    re.compile(r"[^/]+_test\.rs$"),
    re.compile(r"(^|/)fixtures/"),
)

#: The parts of the repository a change is grouped into, in the order the packet
#: shows them, with the plain words for each. The task's own grouping: backend
#: modules AND tests, the published base, desktop/HUD, the Android client, docs,
#: tools, and the contract and records. Anything else is "other".
AREAS = (
    ("backend", "backend (modules and tests)"),
    ("jarvis-backend", "jarvis-backend (the published base)"),
    ("desktop", "desktop and HUD"),
    ("android", "Android client"),
    ("docs", "docs"),
    ("tools", "tools and scripts"),
    ("records", "contract and records"),
    ("other", "other"),
)

#: Parts of a path that say "a key store, a password store or another program's
#: private data". A review of a folder under one of these is refused by name.
#: NOT a sandbox - `_path_refused`'s docstring says what this is and is not.
_DENY_PARTS = frozenset({
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", "keychains",
    "credential manager", "credentials", "secrets", "windows", "program files",
    "program files (x86)", "programdata", "$recycle.bin", "system volume information",
})

#: The scratch folders this repository's own rule says must not be tracked
#: (`tools/check_no_scratch_in_the_tree.py` owns the real list; these are the
#: names it reports, and the review flags them early).
_SCRATCH_PARTS = (".dsh-scratch/", "brag-output/", "__pycache__/", ".pytest_cache/")

#: The twins that are NOT the same name on both sides: the published base gets a
#: copy under its own name. `tools/gen_base_from_backend.py`'s `BESIDE` table is
#: the authority; this is the part of it a change set can be judged against.
BESIDE_TO_BASE = {
    "backend/rebuilt/jarvis-framework.toml": "jarvis-backend/jarvis-framework.toml",
    "backend/requirements.lock": "jarvis-backend/requirements.lock",
    "backend/quiz_grader_cases.json": "jarvis-backend/quiz_grader_cases.json",
    "backend/quotes_corpus.json": "jarvis-backend/quotes_corpus.json",
    "backend/jarvis-self-code.json": "jarvis-backend/jarvis-self-code.json",
    "jarvis-desktop/src/jarvis_hud.html": "jarvis-backend/jarvis_hud.html",
    "jarvis-desktop/src-tauri/Cargo.lock": "jarvis-backend/rust-crates.lock",
}

#: The reverse of `BESIDE_TO_BASE`, built once.
BASE_TO_BESIDE = {base: source for source, base in BESIDE_TO_BASE.items()}


# --------------------------------------------------------------------------
#   One command, run read-only
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ran:
    """What one command did - started or not, finished or not, and its words.

    `started` exists because "the program is not on this PC" and "the program
    said no" are different answers, and the second one is not a failure of the
    change under review. A command that could not start is NEVER a pass:
    `Ran(started=False)` reaches the checker table as NOT-RUN.
    """

    argv: tuple
    started: bool = False
    code: int = 0
    out: str = ""
    err: str = ""
    timed_out: bool = False
    detail: str = ""              # why it could not start, in plain words

    @property
    def ok(self) -> bool:
        return bool(self.started and not self.timed_out and self.code == 0)


#: Names whose value must never be handed to a child process. The checkers here
#: need PATH, SYSTEMROOT and a temp folder; nothing needs a token. `jarvis_child_env`
#: does this with an allowlist for the shell tool; this is the same idea, local
#: and simpler, because the only children are git and this repository's checkers.
_SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|APIKEY|"
                          r"CREDENTIAL|PRIVATE_KEY|AUTH", re.I)

#: The environment every child gets. `PYTHONDONTWRITEBYTECODE` is the one that
#: matters most: without it, running `backend/test_base_matches_repo.py` would
#: leave `__pycache__` folders in the very tree the review just measured.
_CHILD_SET = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8",
    "GIT_TERMINAL_PROMPT": "0",       # never ask for a password; fail instead
    "GIT_OPTIONAL_LOCKS": "0",        # never refresh the index while reading
    "GIT_PAGER": "cat",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _child_env() -> dict:
    """The environment a child process gets: no credential-looking variable."""
    env = {k: v for k, v in os.environ.items() if not _SECRET_NAME.search(k)}
    env.update(_CHILD_SET)
    return env


def _default_run(argv, cwd: str, timeout: float) -> Ran:
    """Run one command with no shell, bounded, and never raise.

    `argv` is a LIST, so no argument is ever re-split by a shell and a value
    that arrived from a model cannot become a second command. `cwd` is the
    repository root, which is where every relative path in an argv is resolved.
    """
    argv = tuple(str(a) for a in argv)
    kwargs = {}
    if os.name == "nt":
        # The backend runs windowed; without this a console window flashes for
        # every git call.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(list(argv), cwd=cwd or None, env=_child_env(),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        return Ran(argv, started=True, timed_out=True,
                   detail=f"it did not finish within {int(timeout)} seconds")
    except OSError as exc:
        return Ran(argv, started=False,
                   detail=f"it could not be started ({type(exc).__name__})")
    return Ran(argv, started=True, code=int(done.returncode),
               out=str(done.stdout or ""), err=str(done.stderr or ""))


# --------------------------------------------------------------------------
#   The change set: one read, shared by both surfaces
# --------------------------------------------------------------------------


@dataclass
class ChangeSet:
    """Everything both surfaces measured, so they can never disagree.

    `rows` is one dict per changed path: `{"status": "A"|"M"|"D"|"R"|"??", "path"}`.
    A rename contributes both paths, exactly as `git diff --name-status` does.
    `dirty` is the working tree's own porcelain rows, and it is only non-empty
    when the target IS this checkout (a review of another branch does not
    include uncommitted work that is not on that branch).
    """

    root: str
    repo_name: str
    base_ref: str = ""
    base_sha: str = ""
    merge_base: str = ""
    head_sha: str = ""
    head_label: str = ""
    head_branch: str = ""
    rows: list = field(default_factory=list)
    dirty: list = field(default_factory=list)
    added: int = 0
    deleted: int = 0
    numstat: dict = field(default_factory=dict)
    untracked: list = field(default_factory=list)
    untracked_lines: int = 0
    truncated: bool = False
    notes: list = field(default_factory=list)
    measured_at: str = ""

    def status_of(self, path: str) -> str:
        for row in self.rows:
            if row["path"] == path:
                return str(row["status"])
        return ""

    @property
    def paths(self) -> set:
        return {str(row["path"]) for row in self.rows}

    @property
    def statuses(self) -> dict:
        return {str(row["path"]): str(row["status"]) for row in self.rows}

    def touches(self, prefix: str) -> bool:
        return any(p.startswith(prefix) for p in self.paths)

    def added_under(self, prefix: str) -> list:
        return sorted(p for p, s in self.statuses.items()
                      if p.startswith(prefix) and s in ("A", "??"))

    @property
    def is_empty(self) -> bool:
        return not self.rows and not self.dirty


def _refused_path(path: str) -> str:
    """One sentence if `path` is a folder this will not look at, else "".

    What this is: a guard rail against pointing a review at a key store, a
    browser profile or the Windows folder, where a list of file names is still
    something the owner would not want in a chat answer. What it is NOT: a
    sandbox. The module reads names and counts, and the folder it is given is
    the owner's own machine either way.
    """
    try:
        resolved = Path(str(path)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return "That folder name could not be read."
    parts = [p for p in resolved.parts if p not in ("\\", "/")]
    lowered = [p.lower() for p in parts]
    for part in lowered:
        if part in _DENY_PARTS:
            return ("Jarvis does not look at that folder: it is in a place that "
                    f"holds keys, passwords or another program's private data "
                    f"(\"{part}\").")
    if not resolved.is_dir():
        return f"That folder is not on this PC: {resolved}"
    return ""


def _short(sha: str, n: int = 9) -> str:
    """A commit sha as a person reads it: the first few characters."""
    text = str(sha or "").strip()
    return text[:n] if text else "?"


def _fit_text(text: str, max_chars: int) -> str:
    """Hard-stop a rendered answer at `max_chars`, saying that it was cut."""
    limit = max(400, int(max_chars))
    text = str(text or "")
    if len(text) <= limit:
        return text
    suffix = f"\n... cut here at {limit} of {len(text)} characters"
    return text[:limit - len(suffix)] + suffix


def _git(cs_root: str, argv, run: Callable, timeout: float = GIT_TIMEOUT) -> Ran:
    """One git command, always with `--no-optional-locks`.

    That flag is the reason a review cannot change anything at all: without it
    `git status` may rewrite the index to record refreshed stat information,
    which is a write. It is a global git option, so it goes before the verb.
    """
    return run(["git", "--no-optional-locks", *argv], cs_root, timeout)


def _ref_exists(root: str, ref: str, run: Callable) -> bool:
    if not _REF.match(str(ref or "")):
        return False
    got = _git(root, ["rev-parse", "--verify", "--quiet", ref], run)
    return bool(got.ok and got.out.strip())


def _sha_of(root: str, ref: str, run: Callable) -> str:
    got = _git(root, ["rev-parse", "--verify", "--quiet", ref], run)
    return got.out.strip() if got.ok else ""


def _merge_base(root: str, base: str, head: str, run: Callable) -> str:
    got = _git(root, ["merge-base", base, head], run)
    line = got.out.strip().splitlines()
    return line[-1].strip() if got.ok and line else ""


def _current_branch(root: str, run: Callable) -> str:
    got = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"], run)
    name = got.out.strip() if got.ok else ""
    return "" if name in ("", "HEAD") else name


def _local_branches(root: str, run: Callable) -> list:
    """Every local branch name, read with ONE fixed command (no caller value).

    The PR number is matched against this list in Python, never spliced into a
    git command - which is why "the branch for PR 1222" cannot become a way to
    run something else.
    """
    got = _git(root, ["for-each-ref", "--format=%(refname:short)", "refs/heads"], run)
    if not got.ok:
        return []
    return [line.strip() for line in got.out.splitlines() if line.strip()]


def _branch_for_pr(root: str, number: str, run: Callable) -> tuple:
    """(branch, note) for a locally checked-out pull request, or ("", why not).

    NO NETWORK: a PR is a number on GitHub, and this only looks at the branch
    names already on this PC (`fix/pr-1222` is the shape this project's own fix
    lanes use). If none carries the number the answer says to check it out -
    never a guess, and never a fetch.
    """
    wanted = str(number).strip()
    found = [b for b in _local_branches(root, run)
             if re.search(r"(?:^|[/_-])pr[-_]?%s$" % re.escape(wanted), b, re.I)]
    if len(found) == 1:
        return found[0], ""
    if len(found) > 1:
        return "", (f"Pull request {wanted} has more than one local branch "
                    f"({', '.join(sorted(found))}). Name the branch with \"branch\" "
                    f"instead.")
    return "", (f"Pull request {wanted} is not checked out on this PC, so there is "
                f"nothing local to review - Jarvis does not fetch. Check it out "
                f"first (its branch is normally fix/pr-{wanted}) and ask again.")


def _parse_name_status(text: str) -> list:
    """`git diff --name-status -z` -> [{"status", "path"}], renames both paths."""
    tokens = [t for t in str(text or "").split("\0")]
    rows = []
    i = 0
    while i < len(tokens):
        status = tokens[i].strip()
        if not status:
            i += 1
            continue
        if status[0] in ("R", "C"):
            if i + 2 < len(tokens):
                rows.append({"status": status[0], "path": tokens[i + 1]})
                rows.append({"status": status[0], "path": tokens[i + 2]})
            i += 3
            continue
        if i + 1 < len(tokens) and tokens[i + 1]:
            rows.append({"status": status[0], "path": tokens[i + 1]})
        i += 2
    return [r for r in rows if r["path"] and not r["path"].endswith("/")]


def _parse_numstat(text: str) -> dict:
    """`git diff --numstat -z` -> {path: (added, deleted)}.

    A binary file reports "-" for both, which is kept as 0 so the totals stay
    numbers; the renderer says nothing about binary files beyond their presence.
    """
    tokens = [t for t in str(text or "").split("\0")]
    out = {}
    i = 0
    while i < len(tokens):
        head = tokens[i]
        if not head.strip():
            i += 1
            continue
        parts = head.split("\t")
        if len(parts) < 3:
            i += 1
            continue
        added, deleted, path = parts[0], parts[1], parts[2]
        if path:
            out[path] = (_as_int(added), _as_int(deleted))
            i += 1
            continue
        # A rename: the two paths follow as their own NUL-separated tokens.
        if i + 2 < len(tokens):
            out[tokens[i + 2]] = (_as_int(added), _as_int(deleted))
        i += 3
    return out


def _as_int(value) -> int:
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _parse_porcelain(text: str) -> list:
    """`git status --porcelain -z` -> [{"status", "path"}] (renames both paths)."""
    tokens = [t for t in str(text or "").split("\0")]
    rows = []
    for token in tokens:
        if len(token) < 4:
            continue
        status, path = token[:2], token[3:]
        if not path:
            continue
        if path.endswith("/"):
            # A wholly-untracked folder is one line; it is not a file, and a
            # line count for it would be a guess.
            continue
        rows.append({"status": ("??" if status.strip() == "??" else status.strip()),
                     "path": path})
    return rows


def _count_untracked_lines(path: Path) -> int:
    """Lines in one untracked file, bounded, or 0 when it is not countable text.

    An untracked file is part of what would be pushed, so its lines belong in
    the header's "+N" total - but only if it is small and readable as text. A
    binary, huge or unreadable file contributes 0 and is still LISTED, so the
    count can understate and never silently invent.
    """
    try:
        if path.stat().st_size > MAX_UNTRACKED_BYTES:
            return 0
        raw = path.read_bytes()
    except OSError:
        return 0
    if b"\0" in raw[:4096]:
        return 0
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return 0
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _area_of(path: str) -> str:
    """Which part of the program one repo-relative path belongs to."""
    p = str(path or "").replace("\\", "/")
    if p.startswith("backend/"):
        return "backend"
    if p.startswith("jarvis-backend/"):
        return "jarvis-backend"
    if p.startswith("jarvis-desktop/"):
        return "desktop"
    if p.startswith("jarvis-client/") or p.startswith("jarvis-android/"):
        return "android"
    if p.startswith("docs/"):
        return "docs"
    if p.startswith("tools/") or p.startswith("scripts/"):
        return "tools"
    if (p.startswith("contract/") or p.startswith("changelog.d/")
            or p.startswith("decisions.d/") or p.startswith("plugins/")
            or p.startswith("features/") or p.startswith("skills/")
            or p in ("CHANGELOG.md", "CLAUDE.md", "VERSION", "README.md",
                     "THIRD-PARTY-NOTICES.txt")):
        return "records"
    return "other"


def _group_by_area(paths) -> list:
    """[(plain words, [paths])] in `AREAS` order, empties left out."""
    buckets = {key: [] for key, _ in AREAS}
    for path in paths:
        buckets[_area_of(path)].append(path)
    out = []
    for key, words in AREAS:
        if buckets[key]:
            out.append((words, sorted(buckets[key])))
    return out


def is_test_path(path: str) -> bool:
    """Whether one path is a test file by this repository's own conventions."""
    return any(pattern.search(str(path or "").replace("\\", "/"))
               for pattern in _TEST_PATTERNS)


def _is_scratch(path: str) -> bool:
    p = str(path or "").replace("\\", "/")
    return any(part in p for part in _SCRATCH_PARTS)


#: Files the published base never carries, so a change to one owes no twin:
#: `tools/gen_base_from_backend.py`'s own exclusions (the tests are this
#: repository's, and two named non-shipped files). A review that demanded a
#: `jarvis-backend/test_*.py` would be telling the owner to break that rule.
_NOT_IN_THE_BASE = re.compile(r"(^|/)(test_[^/]+\.py|patch_openjarvis\.py|"
                              r"spike_sandbox\.py)$")


def _same_text(left: str, right: str) -> bool:
    """The repository's own equality rule for two copies: line endings ignored."""
    return str(left or "").replace("\r\n", "\n") == str(right or "").replace("\r\n", "\n")


def _twin_problems(cs: ChangeSet, root: str) -> list:
    """[(path, twin, why)] for every two-file-rule problem THIS change carries.

    Three ways the rule breaks, and the answer says which one it is:
      * the twin did not change at all (the ordinary one-sided edit);
      * the twin does not exist in the base yet (a new module, added on one side);
      * both changed, but the two copies no longer match (the case a
        membership-only check misses, and the one `tools/check_stale_twins.py`
        exists to catch).
    `backend/_where.py` is the documented exception: the base's copy is this
    file PLUS a trailer, so only its membership is judged here and the sentence
    says the trailer rule out loud.
    """
    out, seen = [], set()
    for path in sorted(cs.paths):
        twin = _twin_of(path, root)
        if not twin or twin == path:
            continue
        pair = tuple(sorted((path, twin)))
        if pair in seen:
            continue
        seen.add(pair)
        twin_changed = twin in cs.paths
        if path == "backend/_where.py" or twin == "backend/_where.py":
            if not twin_changed:
                out.append((path, twin, "the base's copy is this file PLUS a "
                                        "trailer, so it has to be re-taken, not "
                                        "copied"))
            continue
        twin_exists = (Path(root) / twin).is_file()
        if not twin_changed:
            out.append((path, twin,
                        "they are kept equal (the two-file rule)" if twin_exists
                        else "there is no such file in the base yet, so it has "
                             "to be added there too"))
            continue
        statuses = cs.statuses
        if (statuses.get(path) == "D") != (statuses.get(twin) == "D"):
            out.append((path, twin, "one side was deleted and the other was not"))
            continue
        if not twin_exists:
            out.append((path, twin, "the base's copy was deleted from the tree"))
            continue
        if not _same_text(_read_tree_text(root, path), _read_tree_text(root, twin)):
            out.append((path, twin, "both copies changed but they no longer match"))
    return out


def _twin_of(path: str, root: str = "") -> str:
    """The path that must move with this one (the two-file rule), or "".

    Four shapes, and the repository has one authority for each:
      * `backend/<file>` <-> `jarvis-backend/<file>` (the SHIPPED modules);
      * `backend/rebuilt/<file>` -> `jarvis-backend/<file>` (the ten rebuilt
        modules land FLATTENED beside the server);
      * `backend/static/<asset>` -> `jarvis-backend/<asset>` (the page's files,
        flattened the same way);
      * the `BESIDE` files whose base name differs (`BESIDE_TO_BASE`).
    A test file, `patch_openjarvis.py` and `spike_sandbox.py` are never in the
    base, so a change to one owes no twin. `backend/_where.py` is deliberately
    NOT a copy - the base's copy is derived from it plus a trailer - so the flag
    says that in words rather than claiming the two texts have to be equal.
    `tools/check_stale_twins.py` is the checker.
    """
    p = str(path or "").replace("\\", "/")
    if _NOT_IN_THE_BASE.search(p):
        return ""
    if p in BESIDE_TO_BASE:
        return BESIDE_TO_BASE[p]
    if p in BASE_TO_BESIDE:
        return BASE_TO_BESIDE[p]
    if p.startswith("backend/rebuilt/"):
        leaf = p.split("/")[-1]
        return f"jarvis-backend/{leaf}" if leaf else ""
    if p.startswith("backend/static/"):
        leaf = p.split("/")[-1]
        return f"jarvis-backend/{leaf}" if leaf else ""
    if p.startswith("backend/"):
        return "jarvis-backend/" + p[len("backend/"):]
    if p.startswith("jarvis-backend/"):
        rest = p[len("jarvis-backend/"):]
        if rest and "/" not in rest and root:
            for candidate in (f"backend/rebuilt/{rest}", f"backend/static/{rest}"):
                if (Path(root) / candidate).is_file():
                    return candidate
        return "backend/" + rest
    return ""


def _resolve_root(args: dict, run: Callable) -> tuple:
    """(repository root, error sentence) from the argument or the env var.

    `git rev-parse --show-toplevel` is asked rather than trusting the folder
    named: a subfolder of the checkout is a reasonable thing to say, and the
    diff has to run at the top anyway.
    """
    named = str(args.get("path") or "").strip()
    where = named or str(os.environ.get(ENV_REPO) or "").strip()
    if not where:
        return "", (f"Jarvis needs the repository folder for that. Say \"review the "
                    f"branch in C:\\...\", or set {ENV_REPO} to the checkout's "
                    f"folder on this PC so asking needs no path.")
    why = _refused_path(where)
    if why:
        return "", why
    got = _git(str(Path(where).resolve()),
               ["rev-parse", "--show-toplevel"], run)
    if not got.started:
        return "", ("Jarvis could not run git on this PC, so it cannot look at that "
                    "folder. Is git installed and on PATH?")
    top = str(got.out or "").strip().splitlines()
    root = top[-1].strip() if got.ok and top else ""
    if not root:
        return "", (f"That folder is not inside a git repository, so there is no "
                    f"branch to review: {Path(where).resolve()}")
    return root, ""


def _change_set(args: dict, run: Callable) -> tuple:
    """(ChangeSet, error sentence). ONE read of the tree, shared by both surfaces."""
    args = args or {}
    root, why = _resolve_root(args, run)
    if why:
        return None, why
    cs = ChangeSet(root=root, repo_name=Path(root).name,
                   measured_at=datetime.now().strftime("%Y-%m-%d %H:%M"))

    # --- what is being reviewed: a branch, a PR (found locally), or this tree
    pr = str(args.get("pr") or "").strip()
    branch = str(args.get("branch") or "").strip()
    local = True
    if pr:
        if not pr.isdigit():
            return None, "A pull request number is digits only, for example 1222."
        branch, why = _branch_for_pr(root, pr, run)
        if why:
            return None, why
        cs.notes.append(f"pull request {pr} was found as the local branch {branch}; "
                        f"nothing was fetched from GitHub")
    if branch:
        if not _REF.match(branch) or ".." in branch:
            return None, ("That is not a branch name Jarvis will read. Give a plain "
                          "branch name such as feat/my-change.")
        if not _ref_exists(root, branch, run):
            return None, (f"There is no branch called {branch} in "
                          f"{Path(root).name}. Jarvis does not fetch; check the "
                          f"name, or check the branch out first.")
        local = False
        cs.head_branch = branch
        cs.head_label = f"branch {branch}"
    else:
        cs.head_branch = _current_branch(root, run)
        cs.head_label = ("the local working tree" if cs.head_branch
                         else "the current checkout (detached HEAD)")

    # --- the base: named, or the first default that exists here
    base = str(args.get("base") or "").strip()
    if base:
        if not _REF.match(base) or ".." in base:
            return None, ("That is not a ref Jarvis will compare with. Give a plain "
                          "ref such as origin/main.")
        if not _ref_exists(root, base, run):
            return None, (f"There is no ref called {base} in {Path(root).name}. "
                          f"Jarvis does not fetch; try origin/main or name one.")
        cs.base_ref = base
    else:
        for candidate in DEFAULT_BASES:
            if _ref_exists(root, candidate, run):
                cs.base_ref = candidate
                break
        if not cs.base_ref:
            return None, ("Jarvis could not find a base branch to compare with "
                          "(it tried origin/main, main and master and Jarvis does "
                          "not fetch). Name one with \"base\".")
    cs.base_sha = _sha_of(root, cs.base_ref, run)

    head_ref = cs.head_branch if not local else "HEAD"
    cs.head_sha = _sha_of(root, head_ref or "HEAD", run)
    if not cs.head_sha:
        return None, "Jarvis could not read the head commit of that change set."

    # --- the common ancestor, so a branch is compared with where it left main
    cs.merge_base = _merge_base(root, cs.base_ref, head_ref or "HEAD", run)
    if not cs.merge_base:
        cs.merge_base = cs.base_sha
        cs.notes.append(f"the common ancestor of {cs.base_ref} and the head could "
                        f"not be worked out, so the comparison is against "
                        f"{cs.base_ref} itself")

    revs = [cs.merge_base] if local else [cs.merge_base, head_ref]
    names = _git(root, ["diff", "--name-status", "-z", *revs], run)
    stats = _git(root, ["diff", "--numstat", "-z", *revs], run)
    if not names.started:
        return None, ("Jarvis could not run git on that folder, so nothing was "
                      "measured.")
    if not names.ok:
        detail = (names.err or names.out or "").strip().splitlines()
        return None, ("git could not compare that change set"
                      + (f": {detail[0]}" if detail else ".")
                      + " Nothing was changed by this check.")
    cs.rows = _parse_name_status(names.out)
    cs.numstat = _parse_numstat(stats.out) if stats.ok else {}

    if local:
        status = _git(root, ["status", "--porcelain", "-z",
                             "--untracked-files=normal"], run)
        cs.dirty = _parse_porcelain(status.out) if status.ok else []
        seen = {row["path"] for row in cs.rows}
        for row in cs.dirty:
            if row["path"] not in seen:
                cs.rows.append(row)
                seen.add(row["path"])

    # --- the totals, from the numstat rows (never estimated)
    cs.added = sum(pair[0] for pair in cs.numstat.values())
    cs.deleted = sum(pair[1] for pair in cs.numstat.values())
    untracked = [r["path"] for r in cs.rows if r["status"] == "??"]
    cs.untracked = sorted(untracked)
    for rel in cs.untracked[:MAX_UNTRACKED_COUNTED]:
        cs.untracked_lines += _count_untracked_lines(Path(root) / rel)
    if len(cs.untracked) > MAX_UNTRACKED_COUNTED:
        cs.notes.append(f"only the first {MAX_UNTRACKED_COUNTED} untracked files' "
                        f"lines were counted")
    cs.added += cs.untracked_lines

    if len(cs.rows) > MAX_CHANGED_FILES:
        cs.truncated = True
        cs.rows = cs.rows[:MAX_CHANGED_FILES]
    return cs, ""


# --------------------------------------------------------------------------
#   The review packet: what changed, by area, and the risk flags
# --------------------------------------------------------------------------


def _flag(kind: str, words: str) -> str:
    """One flag line, in the shape the packet uses (FLAG/INFO/NOTE + words)."""
    return f"{kind} {words}"


def _review_flags(cs: ChangeSet, root: str) -> list:
    """The risk flags, each with its concrete evidence and the next step.

    The rule this list follows, from the owner's standing instruction: show the
    flag and WHY, and prefer that to a verdict where the judgement is
    subjective. A flag here is not "this is wrong" - it is "this is the thing
    that usually goes wrong, and here is the measurement".
    """
    paths = cs.paths
    statuses = cs.statuses
    flags = []

    # 1. The two-file rule: backend/<file> and jarvis-backend/<file>.
    twins = _twin_problems(cs, root)
    if twins:
        words = [f"{path} -> {twin}: {why}" for path, twin, why in twins[:4]]
        more = f"; and {len(twins) - 4} more" if len(twins) > 4 else ""
        flags.append(_flag(
            "FLAG one-sided or mismatched twin edit (the two-file rule):",
            "; ".join(words) + more + ". next: change both, or record why not. "
            "tools/check_stale_twins.py proves it."))

    # 2. A backend module changed with no test changed.
    backend_code = [p for p in sorted(paths)
                    if p.startswith("backend/") and p.endswith(".py")
                    and not p.startswith("backend/test_")]
    if backend_code and not any(is_test_path(p) for p in paths):
        flags.append(_flag(
            "INFO no test changed:",
            f"{len(backend_code)} backend module(s) changed "
            f"({', '.join(backend_code[:3])}"
            f"{', ...' if len(backend_code) > 3 else ''}) and no test file is in "
            f"this change set. next: say which test proves it, or why none is "
            f"needed."))

    # 3. A new document without the docs/README.md count bump.
    new_docs = [p for p in sorted(paths)
                if p.startswith("docs/") and p.endswith(".md")
                and statuses.get(p) in ("A", "??")]
    if new_docs and "docs/README.md" not in paths:
        flags.append(_flag(
            "FLAG new document without the docs/README.md count bump:",
            f"{', '.join(new_docs[:4])}"
            f"{f' and {len(new_docs) - 4} more' if len(new_docs) > 4 else ''}. "
            f"next: bump the count by hand; do NOT regenerate the size figure "
            f"(CLAUDE.md: never regenerate the size on docs/README.md)."))

    # 4. A tool or a route changed without docs/JARVIS-API.md.
    api_surface = []
    if "backend/jarvis_agent.py" in paths:
        api_surface.append("backend/jarvis_agent.py (the model's tools)")
    if "jarvis-backend/jarvis_hud.py" in paths or "backend/jarvis_hud.py" in paths:
        api_surface.append("jarvis_hud.py (the server's routes)")
    added_modules = [p for p in sorted(paths)
                     if p.startswith("backend/") and p.endswith(".py")
                     and statuses.get(p) in ("A", "??")]
    if added_modules:
        api_surface.append("a new backend module (" + ", ".join(added_modules[:3]) + ")")
    net = [p for p in sorted(paths)
           if (p.startswith("jarvis-client/") and "/net/" in p)
           or p.startswith("jarvis-desktop/src-tauri/src/")]
    if net:
        api_surface.append(", ".join(net[:3]) + " (a client's calls)")
    if api_surface and "docs/JARVIS-API.md" not in paths:
        flags.append(_flag(
            "FLAG tool or route changed without docs/JARVIS-API.md:",
            "; ".join(api_surface[:3])
            + ". next: check the API doc still tells the truth about it, and add "
              "the section this change needs."))

    # 5. Tracked scratch.
    scratch = [p for p in sorted(paths) if _is_scratch(p)]
    if scratch:
        flags.append(_flag(
            "FLAG tracked scratch:",
            f"{', '.join(scratch[:3])}"
            f"{f' and {len(scratch) - 3} more' if len(scratch) > 3 else ''} - "
            f"scratch must not be in the tree. next: tools/check_no_scratch_in_the_tree.py "
            f"says the full list."))

    # 6. A hand edit to CHANGELOG.md (the rule is one changelog.d fragment).
    if "CHANGELOG.md" in paths:
        flags.append(_flag(
            "FLAG CHANGELOG.md edited:",
            "a pull request writes ONE file under changelog.d/ and never edits "
            "CHANGELOG.md - the roll does that on a quiet main. next: move the "
            "line into changelog.d/YYYY-MM-DD-<slug>.md and put the file back."))

    # 7. A changed .patch: its old version has to be recorded.
    patches = [p for p in sorted(paths) if p.startswith("backend/") and p.endswith(".patch")]
    if patches:
        flags.append(_flag(
            "FLAG backend patch changed:",
            f"{', '.join(patches[:3])}. next: run "
            f"`py -3 tools/build_patch_history.py` and commit "
            f"backend/patch-history in the same change (CLAUDE.md)."))

    # 8. The size of the change.
    total_lines = cs.added + cs.deleted
    if len(paths) > 40:
        flags.append(_flag(
            "NOTE large change:",
            f"{len(paths)} files changed - too many to review in one pass. next: "
            f"split it, or review it by area (the groups above)."))
    if total_lines > 3000:
        flags.append(_flag(
            "NOTE large diff:",
            f"{total_lines} changed lines (+{cs.added}/-{cs.deleted}) - review by "
            f"area, not end to end."))

    # 9. The working tree's own dirt: the packet includes it, so say so.
    if cs.dirty:
        flags.append(_flag(
            "NOTE dirty working tree:",
            f"{len(cs.dirty)} uncommitted or untracked path(s) are included in "
            f"this packet, so it is not exactly HEAD. next: commit them, or "
            f"review the branch with \"branch\" to leave them out."))

    # 10. The record: a decision is a record, not a code change.
    if "docs/DECISIONS.md" in paths:
        flags.append(_flag(
            "INFO docs/DECISIONS.md changed:",
            "a new decision is ONE decisions.d/YYYY-MM-DD-<slug>.md fragment; the "
            "record itself is appended by the roll. next: check the change is a "
            "pure tail append, and that \"check the records\" is clean."))
    return flags


def _review_lines(cs: ChangeSet, root: str, limit_files: int) -> list:
    """The packet's lines, without the final clamp (the caller applies it)."""
    paths = sorted(cs.paths)
    lines = [f"Review packet for {cs.repo_name} - measured {cs.measured_at}"]
    lines.append(f"tree: {root} (this PC's own checkout; this review writes nothing)")
    base_bit = f"base {cs.base_ref} {_short(cs.base_sha)}"
    common = f" -> common ancestor {_short(cs.merge_base)}" if cs.merge_base else ""
    lines.append(f"{base_bit}{common} -> head {_short(cs.head_sha)} ({cs.head_label})")

    total = cs.added + cs.deleted
    counted = f"+{cs.added} / -{cs.deleted} lines"
    if cs.untracked:
        counted += (f" (including {len(cs.untracked)} untracked file(s), "
                    f"{cs.untracked_lines} line(s) counted)")
    lines.append(f"changed: {len(paths)} file(s), {counted}")
    for note in cs.notes:
        lines.append(f"note: {note}")
    if cs.is_empty:
        lines.append("")
        lines.append("Nothing changed against that base, and the working tree is "
                     "clean - there is nothing to review.")
        return lines

    lines.append("")
    lines.append("changed files by area:")
    shown = 0
    for words, group in _group_by_area(paths):
        if shown >= limit_files:
            break
        room = max(0, min(MAX_FILES_PER_AREA, limit_files - shown))
        slice_ = group[:room]
        shown += len(slice_)
        lines.append(f"  {words} ({len(group)}):")
        for path in slice_:
            status = cs.status_of(path) or "M"
            lines.append(f"    {status:>2} {path}")
        if len(group) > len(slice_):
            lines.append(f"    ...and {len(group) - len(slice_)} more in this area")
    if len(paths) > shown:
        lines.append(f"  ...and {len(paths) - shown} more file(s) not shown "
                     f"(raise limit_files)")

    lines.append("")
    lines.append("risk flags:")
    flags = _review_flags(cs, root)
    if not flags:
        lines.append("  (none of the recorded flags fired)")
    else:
        for flag in flags:
            lines.append(f"  {flag}")

    lines.append("")
    lines.append("the owner's standing audit checklist (three parts, from CLAUDE.md):")
    lines.append("  1. Bugs - audit the new code, and verify every finding against "
                 "the source before reporting it.")
    lines.append("  2. Both apps - did it land on desktop AND Android where it makes "
                 "sense? If one side is deliberately out, record the reason in "
                 "docs/ARCHITECTURE.md section 8 and keep tools/check_parity.py "
                 "clean.")
    lines.append("  3. Fit - the same permission model and approval cards, the same "
                 "settings patterns and wording, no clash or duplicate, and "
                 "docs/JARVIS-API.md and the other docs updated.")
    lines.append("review rules:")
    for rule in REVIEW_RULES:
        lines.append(f"  - {rule}")
    return lines


#: The owner's standing review rules, quoted in every packet (CLAUDE.md): the
#: three sentences that stopped the project believing its own instruments.
REVIEW_RULES = (
    "Quote the evidence: a path:line you read, not a guess.",
    "Say which tree you asked - this checkout or origin/main; a worktree is a "
    "second copy.",
    "BLOCKED and NOT-TESTABLE are never counted as passes.",
)


def review(args: Optional[dict] = None, *, run: Optional[Callable] = None) -> dict:
    """The REVIEW PACKET: what changed, by area, with the risk flags.

    Read-only by construction. Returns `{"ok": True, "text", "measured"}` or
    `{"ok": False, "error"}`; it never raises and never writes. `max_chars` is
    internal (`SHORT_MAX_TEXT` is what the spoken path asks for), and
    `limit_files` is bounded to `MAX_CHANGED_FILES`.
    """
    args = args or {}
    run = run or _default_run
    limit_files = _bounded_int(args.get("limit_files"), 1, MAX_CHANGED_FILES, 40)
    max_chars = _bounded_int(args.get("max_chars"), 400, REVIEW_MAX_TEXT, REVIEW_MAX_TEXT)
    try:
        cs, why = _change_set(args, run)
    except Exception as exc:                 # noqa: BLE001 - the NAME only
        return {"ok": False, "error": f"the review could not be worked out "
                                      f"({type(exc).__name__}). Nothing was changed."}
    if why:
        return {"ok": False, "error": why}
    try:
        lines = _review_lines(cs, cs.root, limit_files)
    except Exception as exc:                 # noqa: BLE001 - the NAME only
        return {"ok": False, "error": f"the packet could not be put together "
                                      f"({type(exc).__name__}). Nothing was changed."}
    text = _fit_text("\n".join(lines), max_chars)
    return {"ok": True, "text": text, "measured": {
        "repo": cs.root, "base": cs.base_ref, "base_sha": cs.base_sha,
        "merge_base": cs.merge_base, "head_sha": cs.head_sha,
        "branch": cs.head_branch, "files": len(cs.rows), "added": cs.added,
        "deleted": cs.deleted, "flags": len(_review_flags(cs, cs.root)),
        "measured_at": cs.measured_at}}


def _bounded_int(value, low: int, high: int, fallback: int) -> int:
    """An integer inside `low..high`, or `fallback` - never a raise, never huge."""
    if value is None or value == "":
        return fallback
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


# --------------------------------------------------------------------------
#   The record check: the obligations CI derives from a change set
# --------------------------------------------------------------------------


def _obligation(oid: str, status: str, detail: str, next_step: str = "") -> dict:
    """One record obligation. `status` is PRESENT / MISSING / FAIL / INFO."""
    return {"id": oid, "status": status, "detail": detail, "next": next_step}


def _fragment_problems(name: str, text: str, *, decision: bool) -> list:
    """What is wrong with ONE fragment, mirroring the roll tool's own rules.

    `tools/roll_changelog.py` and `tools/roll_decisions.py` are the authority on
    shape; this reads the same way so the answer can say what to fix before the
    checker has to. A decision fragment adds the date-in-the-bullet rule and the
    em dash; a changelog fragment adds the bold title.
    """
    problems = []
    named = _FRAGMENT_NAME.match(str(name or ""))
    if not named:
        return [f"{name}: a fragment's name is YYYY-MM-DD-<slug>.md (lowercase "
                f"letters, digits and dashes)"]
    body = str(text or "").strip()
    if not body:
        return [f"{name}: empty - a fragment is one bullet"]
    if not body.startswith("- "):
        return [f"{name}: it must start with '- ' (one markdown bullet)"]
    if "\n\n" in body:
        problems.append(f"{name}: one bullet only - remove the blank line")
    if decision:
        bullet = _DECISION_BULLET.match(body)
        if not bullet:
            problems.append(f"{name}: the bullet must be \"- **YYYY-MM-DD \u2014 "
                            f"Title:** prose\", with the em dash")
        elif bullet.group(1) != named.group(1):
            problems.append(f"{name}: the bullet says {bullet.group(1)} but the "
                            f"file's name says {named.group(1)} - they have to agree")
    else:
        first = body.splitlines()[0]
        if not re.search(r"\*\*.+?\*\*", first):
            problems.append(f"{name}: give the entry a bold title, like every "
                            f"other changelog bullet")
    return problems


def _read_tree_text(root: str, rel: str) -> str:
    """One repo-relative file's text, or "" when it is not there.

    Only ever called with a path this module built (a record path or a path out
    of git's own output), never with a value from a model.
    """
    try:
        return (Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _base_text(root: str, merge_base: str, rel: str, run: Callable) -> tuple:
    """(text at the common ancestor, whether it could be read).

    `git show <sha>:<path>` is the only way to see what a changed record file
    looked like before, and it is read-only. A file that did not exist at the
    base is ("", True) with an empty text - which is what a pure tail append
    looks like when the whole file is new.
    """
    if not merge_base:
        return "", False
    got = _git(root, ["show", f"{merge_base}:{rel}"], run)
    if not got.started:
        return "", False
    if not got.ok:
        # "does not exist in <sha>" is the ordinary case for a file this change
        # adds; anything else is a failure to read and is reported as one.
        err = (got.err or "").lower()
        if "does not exist" in err or "exists on disk, but not in" in err:
            return "", True
        return "", False
    return got.out, True


def _count_docs(root: str) -> int:
    """How many markdown documents are under docs/ - what the page states."""
    docs = Path(root) / "docs"
    if not docs.is_dir():
        return 0
    try:
        return sum(1 for p in docs.rglob("*")
                   if p.is_file() and p.suffix.lower() == ".md")
    except OSError:
        return 0


def _stated_docs_count(root: str) -> Optional[int]:
    """The document count `docs/README.md` states, or None if it states none.

    The same two places `tools/check_docs_map.py` reads: the prose sentence and
    the `(Get-ChildItem ...).Count   # 419 documents` line.
    """
    text = _read_tree_text(root, "docs/README.md")
    if not text:
        return None
    for pattern in (r"\*\*([\d,]+)\s+markdown documents\*\*",
                    r"\.Count\s*#\s*([\d,]+)\s+documents"):
        match = re.search(pattern, text)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                return None
    return None


def _claim_row_problems(cells: list, line: int) -> list:
    """What is wrong with ONE claims row (`docs/CLAIMS.tsv`), in plain words."""
    if len(cells) < 5:
        return [f"line {line}: {len(cells)} column(s); a claims row has 5, separated "
                f"by TABs (id, claim, check, state, source)"]
    _cid, claim, check, state, _source = cells[0], cells[1], cells[2], cells[3], cells[4]
    problems = []
    if not str(_cid).strip():
        problems.append(f"line {line}: the id column is empty")
    if not str(claim).strip():
        problems.append(f"line {line}: the claim column is empty")
    state = str(state).strip()
    if state not in CLAIM_STATES:
        problems.append(f"line {line}: state {state!r} is not one of "
                        f"{', '.join(CLAIM_STATES)}")
    check = str(check).strip()
    if state == "unverifiable":
        if check.startswith(CLAIM_CHECK_KINDS):
            problems.append(f"line {line}: an unverifiable row gives a reason, not "
                            f"a check")
    elif not check.startswith(CLAIM_CHECK_KINDS):
        problems.append(f"line {line}: the check column must begin with one of "
                        f"{', '.join(CLAIM_CHECK_KINDS)}")
    return problems


def _defect_row_problems(cells: list, line: int) -> list:
    """What is wrong with ONE defect register row, in plain words."""
    if len(cells) < 7:
        return [f"line {line}: {len(cells)} column(s); a defect row has 7, "
                f"separated by TABs"]
    state = str(cells[3]).strip()
    problems = []
    if state not in DEFECT_STATES:
        problems.append(f"line {line}: status {state!r} is not open or closed")
    if not str(cells[0]).strip():
        problems.append(f"line {line}: the id column is empty")
    return problems


def _tsv_rows(text: str) -> list:
    """(line number, cells) for every non-empty, non-comment row of a TSV."""
    rows = []
    for number, line in enumerate(str(text or "").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        rows.append((number, line.split("\t")))
    return rows


def _obligations(cs: ChangeSet, root: str, run: Callable) -> list:
    """Every record rule CI derives from this change set, with its evidence."""
    statuses = cs.statuses
    paths = cs.paths
    obligations = []

    # --- 1. changelog: exactly ONE fragment, and no CHANGELOG.md edit ---------
    fragments = sorted(p for p in paths
                       if p.startswith("changelog.d/") and p.endswith(".md")
                       and p != "changelog.d/README.md"
                       and statuses.get(p) in ("A", "M", "??"))
    if "CHANGELOG.md" in paths:
        obligations.append(_obligation(
            "changelog", "FAIL",
            "CHANGELOG.md was edited. A pull request writes ONE file under "
            "changelog.d/ and never edits CHANGELOG.md - the roll does that on a "
            "quiet main.",
            "put CHANGELOG.md back, and move that line into "
            "changelog.d/YYYY-MM-DD-<slug>.md"))
    elif len(fragments) == 1:
        problems = _fragment_problems(
            Path(fragments[0]).name,
            _read_tree_text(root, fragments[0]), decision=False)
        if problems:
            obligations.append(_obligation(
                "changelog", "FAIL", "; ".join(problems[:3]),
                "the fragment is ONE markdown bullet starting \"- **Title:** ...\""))
        else:
            obligations.append(_obligation(
                "changelog", "PRESENT",
                f"{fragments[0]} is one well-formed bullet"))
    elif not fragments:
        obligations.append(_obligation(
            "changelog", "MISSING",
            "no changelog.d/ fragment is in this change set. This repository's rule "
            "is ONE fragment per pull request, named YYYY-MM-DD-<slug>.md.",
            "add changelog.d/YYYY-MM-DD-<slug>.md holding one bullet: "
            "\"- **What changed:** in the owner's words\""))
    else:
        obligations.append(_obligation(
            "changelog", "FAIL",
            f"{len(fragments)} changelog fragments are in this change set "
            f"({', '.join(Path(p).name for p in fragments[:4])}). The rule is ONE "
            f"per pull request.",
            "keep one fragment and fold the other entry into it"))

    # --- 2. the docs count, bumped by hand when a document is added ----------
    new_docs = [p for p in sorted(paths)
                if p.startswith("docs/") and p.lower().endswith(".md")
                and statuses.get(p) in ("A", "??")]
    if new_docs:
        measured = _count_docs(root)
        stated = _stated_docs_count(root)
        if "docs/README.md" not in paths:
            obligations.append(_obligation(
                "docs-count", "MISSING",
                f"{len(new_docs)} document(s) added ({', '.join(new_docs[:3])}) but "
                f"docs/README.md was not changed. The tree holds {measured} "
                f"markdown document(s)"
                + (f", and the page says {stated}" if stated is not None else ""),
                f"bump the count on docs/README.md by hand to {measured} (or to the "
                f"number the tree holds after the commit) and do NOT touch the size "
                f"figure"))
        elif stated is not None and stated != measured:
            obligations.append(_obligation(
                "docs-count", "FAIL",
                f"docs/README.md says {stated} documents and the tree holds "
                f"{measured}",
                f"bump the count to {measured} by hand, and leave the size alone"))
        else:
            obligations.append(_obligation(
                "docs-count", "PRESENT",
                f"docs/README.md was changed with the {len(new_docs)} new "
                f"document(s); the tree holds {measured}"))
    else:
        stated = _stated_docs_count(root)
        measured = _count_docs(root)
        if stated is not None and stated != measured:
            obligations.append(_obligation(
                "docs-count", "INFO",
                f"no document was added, but docs/README.md says {stated} and the "
                f"tree holds {measured}. An untracked document does not reach CI.",
                "leave it: the count is checked exactly, and only a document this "
                "change adds has to move it"))
        else:
            obligations.append(_obligation(
                "docs-count", "INFO",
                f"no document was added; docs/README.md still agrees with the "
                f"tree ({measured} document(s))"))

    # --- 3. every changed backend file's twin -------------------------------
    twins = _twin_problems(cs, root)
    if twins:
        listed = "; ".join(f"{a} -> {b} ({why})" for a, b, why in twins[:4])
        more = f"; and {len(twins) - 4} more" if len(twins) > 4 else ""
        obligations.append(_obligation(
            "backend-twin", "MISSING",
            f"{len(twins)} two-file problem(s): {listed}{more}",
            "change both, or record why not. tools/check_stale_twins.py is the "
            "checker; jarvis-backend/ is the published base"))
    else:
        obligations.append(_obligation(
            "backend-twin", "PRESENT",
            "every changed backend file's jarvis-backend twin moved with it, and "
            "the two copies still match"
            if any(_twin_of(p, root) for p in paths)
            else "no backend or jarvis-backend file changed, so no twin is owed"))

    # --- 4. ONE decision record: a fragment or a tail append ----------------
    decision_fragments = sorted(p for p in paths
                                if p.startswith("decisions.d/") and p.endswith(".md")
                                and p != "decisions.d/README.md"
                                and statuses.get(p) in ("A", "M", "??"))
    record_changed = "docs/DECISIONS.md" in paths
    form = ""
    if decision_fragments and record_changed:
        form = "both"
    elif decision_fragments:
        form = "fragment"
    elif record_changed:
        form = "append"

    if form == "append" or form == "both":
        base_text, read_ok = _base_text(root, cs.merge_base, "docs/DECISIONS.md", run)
        current = _read_tree_text(root, "docs/DECISIONS.md")
        if not read_ok:
            obligations.append(_obligation(
                "decision", "INFO",
                "docs/DECISIONS.md changed and the pre-change copy could not be read "
                "from git, so the append could not be checked here "
                "(tools/roll_decisions.py --check still runs)",
                "a new decision belongs in ONE decisions.d/ fragment, not in the "
                "record"))
        elif not current.startswith(base_text):
            obligations.append(_obligation(
                "decision", "FAIL",
                "docs/DECISIONS.md was rewritten or reordered - the change is not a "
                "pure append at the end of the file.",
                "restore the record and put the new decision in ONE "
                "decisions.d/YYYY-MM-DD-<slug>.md fragment"))
        else:
            obligations.append(_obligation(
                "decision", "PRESENT",
                "the decision is recorded as a tail append to docs/DECISIONS.md"
                + (" and a decisions.d/ fragment" if decision_fragments else "")))
        if form == "both" and len(decision_fragments) > 1:
            obligations.append(_obligation(
                "decision", "FAIL",
                f"{len(decision_fragments)} decisions.d fragments are in this change "
                f"set; the rule is ONE per pull request",
                "keep one fragment"))
    elif form == "fragment":
        if len(decision_fragments) > 1:
            obligations.append(_obligation(
                "decision", "FAIL",
                f"{len(decision_fragments)} decisions.d fragments are in this change "
                f"set ({', '.join(Path(p).name for p in decision_fragments[:4])}); the "
                f"rule is ONE per pull request",
                "keep one fragment and fold the other entry into it"))
        else:
            problems = _fragment_problems(
                Path(decision_fragments[0]).name,
                _read_tree_text(root, decision_fragments[0]), decision=True)
            if problems:
                obligations.append(_obligation(
                    "decision", "FAIL", "; ".join(problems[:3]),
                    "the fragment is ONE dated bullet: \"- **YYYY-MM-DD \u2014 "
                    "Title:** prose\", and the date in the name must match"))
            else:
                obligations.append(_obligation(
                    "decision", "PRESENT",
                    f"{decision_fragments[0]} is one well-shaped dated bullet"))
    else:
        obligations.append(_obligation(
            "decision", "MISSING",
            "no decision record is in this change set. A new decision is ONE "
            "decisions.d/YYYY-MM-DD-<slug>.md fragment.",
            "add ONE decisions.d/YYYY-MM-DD-<slug>.md fragment holding one bullet: "
            "\"- **YYYY-MM-DD \u2014 Title:** what was decided, and why\""))

    # --- 5. claims rows, well shaped ----------------------------------------
    if "docs/CLAIMS.tsv" in paths:
        current = _tsv_rows(_read_tree_text(root, "docs/CLAIMS.tsv"))
        base_text, read_ok = _base_text(root, cs.merge_base, "docs/CLAIMS.tsv", run)
        base_rows = {cells[0]: "\t".join(cells) for _n, cells in _tsv_rows(base_text)} \
            if read_ok else {}
        changed = [(n, cells) for n, cells in current
                   if "\t".join(cells) != base_rows.get(cells[0])]
        problems = []
        for number, cells in changed:
            problems.extend(_claim_row_problems(cells, number))
        if problems:
            obligations.append(_obligation(
                "claims", "FAIL", "; ".join(problems[:4]),
                "a claims row is 5 TAB columns: id, claim, check, state, source; "
                "state is built/open/unverifiable and check starts with "
                "file:/no-file:/grep:/absent:/test:/number:"))
        else:
            obligations.append(_obligation(
                "claims", "PRESENT",
                f"{len(changed)} changed or new claims row(s) are well shaped"))
    else:
        obligations.append(_obligation(
            "claims", "INFO", "docs/CLAIMS.tsv did not change, so no row is owed"))

    # --- 6. the defect register's rows, well shaped -------------------------
    register_changed = ("docs/defect-register.tsv" in paths
                        or "docs/DEFECT-REGISTER.md" in paths)
    if register_changed:
        current = _tsv_rows(_read_tree_text(root, "docs/defect-register.tsv"))
        base_text, read_ok = _base_text(root, cs.merge_base,
                                        "docs/defect-register.tsv", run)
        base_rows = {cells[0]: "\t".join(cells) for _n, cells in _tsv_rows(base_text)} \
            if read_ok else {}
        changed = [(n, cells) for n, cells in current
                   if "\t".join(cells) != base_rows.get(cells[0])]
        problems = []
        for number, cells in changed:
            problems.extend(_defect_row_problems(cells, number))
        if problems:
            obligations.append(_obligation(
                "defect-register", "FAIL", "; ".join(problems[:4]),
                "a defect row is 7 TAB columns ending with status open/closed, and "
                "docs/DEFECT-REGISTER.md must agree about which are open"))
        else:
            obligations.append(_obligation(
                "defect-register", "PRESENT",
                f"{len(changed)} changed or new defect row(s) are well shaped; "
                f"docs/DEFECT-REGISTER.md must still agree about which are open"))
    else:
        obligations.append(_obligation(
            "defect-register", "INFO",
            "the defect register did not change, so no row is owed"))
    return obligations


# --------------------------------------------------------------------------
#   The repository's own checkers: a fixed allow-list, run bounded
# --------------------------------------------------------------------------

#: The twelve read-only checkers the record check may run, with the reason each
#: one exists and what selects it. Every command is a fixed argv list plus, at
#: most, `--check`; the Python is the one running this backend, so a checker runs
#: in the same interpreter the product uses. NOTHING here takes an argument from
#: a caller, and `tools/check_claims.py` is the only one given a longer ceiling
#: (it re-runs the suites its own rows name).
CHECKERS = (
    {"id": "changelog", "script": "tools/roll_changelog.py", "args": ("--check",),
     "timeout": CHECK_TIMEOUT, "always": True,
     "why": "every changelog.d fragment's name and shape, and that CHANGELOG.md "
            "still carries the roll heading",
     "select": lambda cs: True},
    {"id": "docs-map", "script": "tools/check_docs_map.py", "args": (),
     "timeout": CHECK_TIMEOUT, "always": False,
     "why": "docs/README.md states the document count exactly",
     "select": lambda cs: True},
    {"id": "decisions", "script": "tools/roll_decisions.py", "args": ("--check",),
     "timeout": CHECK_TIMEOUT, "always": False,
     "why": "every decisions.d fragment's name, bullet shape and date, and the "
            "record's anchor heading",
     "select": lambda cs: any(p.startswith("decisions.d/") for p in cs.paths)},
    {"id": "claims", "script": "tools/check_claims.py", "args": (),
     "timeout": CLAIMS_TIMEOUT, "always": False,
     "why": "every claim still holds - the slowest checker, because it re-runs "
            "the suites its rows name",
     "select": lambda cs: "docs/CLAIMS.tsv" in cs.paths},
    {"id": "defect-register", "script": "tools/check_defect_register.py", "args": (),
     "timeout": CHECK_TIMEOUT, "always": False,
     "why": "the defect register is well formed and its two files agree",
     "select": lambda cs: ("docs/defect-register.tsv" in cs.paths
                           or "docs/DEFECT-REGISTER.md" in cs.paths)},
    {"id": "stale-twins", "script": "tools/check_stale_twins.py", "args": (),
     "timeout": CHECK_TIMEOUT, "always": False,
     "why": "backend/<f> and jarvis-backend/<f> are kept equal, including the "
            "BESIDE files",
     "select": lambda cs: any(p.startswith("backend/") or p.startswith("jarvis-backend/")
                              or p in BESIDE_TO_BASE or p in BASE_TO_BESIDE
                              for p in cs.paths)},
    {"id": "base-matches-repo", "script": "backend/test_base_matches_repo.py",
     "args": (), "timeout": 180.0, "always": False,
     "why": "the published base is the base these patches describe",
     "select": lambda cs: any(p.startswith("backend/") or p.startswith("jarvis-backend/")
                              or p == "scripts/apply-patches.ps1" for p in cs.paths)},
    {"id": "base-regeneration", "script": "backend/test_base_regeneration.py",
     "args": (), "timeout": CHECK_TIMEOUT, "always": False,
     "why": "the published base follows the repository's own re-take rule",
     "select": lambda cs: any(p.startswith("backend/") or p.startswith("jarvis-backend/")
                              or p == "tools/gen_base_from_backend.py"
                              for p in cs.paths)},
    {"id": "no-source-pins", "script": "tools/check_no_source_pins.py", "args": (),
     "timeout": CHECK_TIMEOUT, "always": False,
     "why": "no test pins the source text of a production module",
     "select": lambda cs: any(p.endswith(".py") for p in cs.paths)},
    {"id": "parity", "script": "tools/check_parity.py", "args": (),
     "timeout": CHECK_TIMEOUT, "always": False,
     "why": "a feature landed on both apps, or the one-sided reason is recorded",
     "select": lambda cs: any(p.startswith("backend/") or p.startswith("jarvis-desktop/")
                              or p.startswith("jarvis-client/") for p in cs.paths)},
    {"id": "plugins", "script": "tools/check_plugins.py", "args": (),
     "timeout": CHECK_TIMEOUT, "always": False,
     "why": "the plugin catalogue matches the patches this repository applies",
     "select": lambda cs: any(p.startswith("plugins/") or p == "scripts/apply-patches.ps1"
                              or p == "plugins/registry.json" for p in cs.paths)},
    {"id": "no-scratch", "script": "tools/check_no_scratch_in_the_tree.py", "args": (),
     "timeout": CHECK_TIMEOUT, "always": True,
     "why": "no scratch file is tracked",
     "select": lambda cs: True},
)

#: The verdict when a checker's own output says a check was skipped. A skipped
#: check is never a pass (the project's standing rule).
_SKIPPED_LINE = re.compile(r"^[ \t]*(?:SKIPPED|SKIP)\b", re.M)


def _select_checkers(cs: ChangeSet, root: str) -> tuple:
    """(to run, selected but impossible here, not needed) - three honest lists.

    A checker is NOT NEEDED when nothing it checks changed; that is not a
    failure and must not make the verdict incomplete (most changes touch
    neither the claims register nor the plugin catalogue). A checker that WAS
    selected and cannot run - its script is not in this tree - is a real
    NOT-RUN, and it is never a pass.
    """
    to_run, impossible, not_needed = [], [], []
    for checker in CHECKERS:
        try:
            wanted = checker["always"] or bool(checker["select"](cs))
        except Exception:                    # noqa: BLE001 - a selector is a lambda
            wanted = True                    # an unreadable selection runs it
        if not wanted:
            not_needed.append({"id": checker["id"],
                               "reason": "nothing it checks changed in this "
                                         "change set"})
            continue
        script = Path(root) / checker["script"]
        if not script.is_file():
            impossible.append({"id": checker["id"],
                               "why": checker["why"],
                               "reason": f"{checker['script']} is not in this tree"})
            continue
        to_run.append(checker)
    return to_run, impossible, not_needed


def _checker_ran(checker: dict, ran: Optional[Ran], seconds: float) -> dict:
    """One checker record: PASS/FAIL/TIMEOUT/ERROR/NOT-RUN, never a false pass."""
    record = {"id": checker["id"], "command": "", "why": checker["why"],
              "status": "NOT-RUN", "seconds": round(seconds, 1), "exit": None,
              "excerpt": [], "reason": ""}
    if ran is None:
        record["status"] = "NOT-RUN"
        record["reason"] = "it was not run (the run's time budget was used up)"
        return record
    record["command"] = " ".join(ran.argv)
    record["exit"] = ran.code
    if not ran.started:
        record["status"] = "NOT-RUN"
        record["reason"] = ran.detail or "it could not be started"
        return record
    if ran.timed_out:
        record["status"] = "TIMEOUT"
        record["reason"] = ran.detail or "it did not finish in time"
        return record
    output = "\n".join(part for part in (ran.out, ran.err) if part)
    if ran.code == 0:
        skipped = _SKIPPED_LINE.search(output or "")
        if skipped:
            record["status"] = "NOT-RUN"
            record["reason"] = ("its own output says a check was skipped: "
                                + skipped.group(0).strip()[:160])
        else:
            record["status"] = "PASS"
        return record
    record["status"] = "FAIL"
    record["excerpt"] = _excerpt(output)
    return record


def _excerpt(text: str) -> list:
    """The bounded failure excerpt: the last few lines, each clipped."""
    lines = [line.rstrip() for line in str(text or "").splitlines() if line.strip()]
    picked = lines[-MAX_EXCERPT_LINES:]
    return [line[:MAX_EXCERPT_CHARS] for line in picked]


def _run_checkers(selected, cs: ChangeSet, run: Callable) -> list:
    """One record per selected checker - bounded in time, output and count."""
    records = []
    started = time.monotonic()
    for checker in selected:
        spent = time.monotonic() - started
        if spent > TOTAL_CHECK_BUDGET:
            records.append(_checker_ran(checker, None, 0.0))
            continue
        budget = min(float(checker["timeout"]), TOTAL_CHECK_BUDGET - spent)
        argv = [sys.executable, "-B", str(Path(cs.root) / checker["script"]),
                *checker["args"]]
        begin = time.monotonic()
        ran = run(argv, cs.root, budget)
        if not isinstance(ran, Ran):         # a seam that returned None or a dict
            ran = Ran(tuple(argv), started=False,
                      detail="the command could not be started")
        if len(ran.out) > MAX_CHECK_OUTPUT:
            ran = Ran(ran.argv, started=ran.started, code=ran.code,
                      out=ran.out[-MAX_CHECK_OUTPUT:], err=ran.err,
                      timed_out=ran.timed_out, detail=ran.detail)
        records.append(_checker_ran(checker, ran, time.monotonic() - begin))
    return records


def _verdict(obligations: list, records: list) -> str:
    """READY / NEEDS-RECORDS / CHECKER-FAILED / INCOMPLETE - the four answers.

    READY needs BOTH halves: no obligation MISSING or FAIL, and every checker
    that was selected really passed. A NOT-RUN, TIMEOUT or ERROR is never READY.
    """
    failed = [r for r in records
              if r["status"] in ("FAIL", "TIMEOUT", "ERROR")]
    needs = [o for o in obligations if o["status"] in ("MISSING", "FAIL")]
    if failed:
        return "CHECKER-FAILED"
    if needs:
        return "NEEDS-RECORDS"
    if not records or any(r["status"] == "NOT-RUN" for r in records):
        return "INCOMPLETE"
    return "READY"


def _verdict_words(verdict: str, obligations: list, records: list) -> str:
    """The verdict, in one plain sentence a beginner owner can act on."""
    counts = {k: sum(1 for o in obligations if o["status"] == k)
              for k in ("PRESENT", "MISSING", "FAIL", "INFO")}
    if verdict == "READY":
        return (f"VERDICT: READY - nothing is missing and all {len(records)} "
                f"checker(s) passed. This is a local check, not CI: it does not "
                f"replace the seven required checks.")
    if verdict == "CHECKER-FAILED":
        bad = ", ".join(f"{r['id']}:{r['status']}" for r in records
                        if r["status"] in ("FAIL", "TIMEOUT", "ERROR"))
        extra = (f"; and {counts['MISSING'] + counts['FAIL']} record obligation(s) "
                 f"need attention" if counts["MISSING"] + counts["FAIL"] else "")
        return (f"VERDICT: CHECKER-FAILED - {bad}{extra}. Fix the checker output "
                f"before pushing; a NOT-RUN is never a pass.")
    if verdict == "NEEDS-RECORDS":
        missing = ", ".join(o["id"] for o in obligations
                            if o["status"] in ("MISSING", "FAIL"))
        ran = [r for r in records if r["status"] in ("PASS", "FAIL", "TIMEOUT", "ERROR")]
        not_run = [r["id"] for r in records if r["status"] == "NOT-RUN"]
        if ran and not any(r["status"] != "PASS" for r in ran):
            passed = "every checker that ran passed."
        elif ran:
            passed = "a checker also failed, above."
        else:
            passed = "no checker could run here, so nothing about the code is proved."
        tail = (f" {len(not_run)} checker(s) did not run, so this cannot become "
                f"READY until they do ({', '.join(not_run)})." if not_run else "")
        return (f"VERDICT: NEEDS-RECORDS - {counts['MISSING']} missing and "
                f"{counts['FAIL']} wrong ({missing}); {passed}{tail} Add the "
                f"records above, then ask again.")
    not_run = ", ".join(r["id"] for r in records if r["status"] == "NOT-RUN") \
        or "no checker"
    return (f"VERDICT: INCOMPLETE - every checker that ran passed, but {not_run} "
            f"did not run. NOT-RUN is never a pass.")


def record_check(args: Optional[dict] = None, *,
                 run: Optional[Callable] = None) -> dict:
    """The REPOSITORY RECORD CHECK: is this change's bookkeeping in order?

    Read-only: it writes nothing (there is no log folder - the excerpt rides in
    the answer and the full output is dropped), opens no socket, and runs only
    the twelve fixed checker commands in `CHECKERS`. Returns
    `{"ok": True, "verdict", "text", "measured"}` or `{"ok": False, "error"}`.
    """
    args = args or {}
    run = run or _default_run
    max_chars = _bounded_int(args.get("max_chars"), 400, RECORD_MAX_TEXT,
                             RECORD_MAX_TEXT)
    try:
        cs, why = _change_set(args, run)
    except Exception as exc:                 # noqa: BLE001 - the NAME only
        return {"ok": False, "error": f"the record check could not be worked out "
                                      f"({type(exc).__name__}). Nothing was changed."}
    if why:
        return {"ok": False, "error": why}
    obligations = _obligations(cs, cs.root, run)
    to_run, impossible, not_needed = _select_checkers(cs, cs.root)
    records = _run_checkers(to_run, cs, run)
    for entry in impossible:
        records.append({"id": entry["id"], "command": "", "why": entry["why"],
                        "status": "NOT-RUN", "seconds": 0.0, "exit": None,
                        "excerpt": [], "reason": entry["reason"]})
    verdict = _verdict(obligations, records)
    text = _fit_text("\n".join(
        _record_lines(cs, obligations, records, not_needed, verdict)), max_chars)
    return {"ok": True, "verdict": verdict, "text": text, "measured": {
        "repo": cs.root, "base": cs.base_ref, "merge_base": cs.merge_base,
        "head_sha": cs.head_sha, "files": len(cs.rows),
        "obligations": {k: sum(1 for o in obligations if o["status"] == k)
                        for k in ("PRESENT", "MISSING", "FAIL", "INFO")},
        "checkers": {k: sum(1 for r in records if r["status"] == k)
                     for k in ("PASS", "FAIL", "TIMEOUT", "ERROR", "NOT-RUN")},
        "not_run": [r["id"] for r in records if r["status"] == "NOT-RUN"],
        "not_needed": [r["id"] for r in not_needed],
        "verdict": verdict, "measured_at": cs.measured_at}}


def _record_lines(cs: ChangeSet, obligations: list, records: list,
                  not_needed: list, verdict: str) -> list:
    """The record check's rendered answer, obligations first, verdict last."""
    paths = sorted(cs.paths)
    counts = {k: sum(1 for o in obligations if o["status"] == k)
              for k in ("PRESENT", "MISSING", "FAIL", "INFO")}
    lines = [f"Record check for {cs.repo_name} - {verdict} - measured "
             f"{cs.measured_at}"]
    lines.append(f"tree: {cs.root} (this PC's own checkout; nothing here is written)")
    lines.append(f"base {cs.base_ref} {_short(cs.base_sha)} -> common ancestor "
                 f"{_short(cs.merge_base)} -> head {_short(cs.head_sha)} "
                 f"({cs.head_label})")
    lines.append(f"changed: {len(paths)} file(s)")
    for path in paths[:8]:
        lines.append(f"  {cs.status_of(path) or 'M':>2} {path}")
    if len(paths) > 8:
        lines.append(f"  ...and {len(paths) - 8} more")

    lines.append("")
    lines.append(f"obligations: {counts['PRESENT']} present, {counts['MISSING']} "
                 f"missing, {counts['FAIL']} fail, {counts['INFO']} info")
    order = {"MISSING": 0, "FAIL": 1, "PRESENT": 2, "INFO": 3}
    for obligation in sorted(obligations, key=lambda o: order.get(o["status"], 9)):
        lines.append(f"  {obligation['status']:<7} {obligation['id']}: "
                     f"{obligation['detail']}")
        if obligation["next"]:
            lines.append(f"          next: {obligation['next']}")

    lines.append("")
    summary = ", ".join(f"{n} {status}" for status, n in
                        ((s, sum(1 for r in records if r["status"] == s))
                         for s in ("FAIL", "TIMEOUT", "ERROR", "NOT-RUN", "PASS"))
                        if n) or "no checker ran"
    lines.append(f"checkers: {summary}")
    for record in records:
        extra = f" - {record['reason']}" if record.get("reason") else ""
        exit_bit = f" exit {record['exit']}" if record["exit"] is not None else ""
        lines.append(f"  {record['status']:<7} {record['id']} "
                     f"{record['seconds']}s{exit_bit}{extra}")
    for record in records:
        if record["status"] in ("FAIL", "TIMEOUT", "ERROR") and record["excerpt"]:
            lines.append(f"  [{record['id']}]")
            for line in record["excerpt"]:
                lines.append(f"    {line}")
    if not_needed:
        lines.append("  not needed for this change (nothing they check moved, so "
                     "these are not failures - and not passes either): "
                     + ", ".join(r["id"] for r in not_needed))

    lines.append("")
    lines.append("uncertainty: a checker that did not run is never a pass; this is "
                 "a local check, not CI.")
    lines.append(_verdict_words(verdict, obligations, records))
    return lines


# --------------------------------------------------------------------------
#   The two switches' own words: what the model reads and the owner hears
# --------------------------------------------------------------------------

#: Both surfaces in one breath, for the tool descriptions and the spoken answer.
#: Every fact here is also true of the code above; `backend/test_github_review.py`
#: and `backend/test_github_record.py` drive the behaviour it describes.
REVIEW_FACTS = (
    "It reads the repository folder on this PC and writes nothing: no file, no "
    "folder, no log, no network, and no GitHub token.",
    "Every command it runs is a fixed read-only git command or one of this "
    "repository's own checkers, from a closed list; nothing a caller says becomes "
    "a command.",
    "It says which folder, which branch and which commit it measured, and what it "
    "could not check - a check that did not run is never reported as a pass.",
)


def review_words() -> str:
    """The review packet's own sentence, for a tool description or a card."""
    return ("The review packet: the base and head commits, the line counts, every "
            "changed file grouped by area, and the risk flags with the evidence - "
            "a one-sided twin, a change with no test, a new document without the "
            "docs count, a tool or route without docs/JARVIS-API.md, tracked "
            "scratch, a dirty tree and the size of the change - then the owner's "
            "three-part audit checklist. Read-only.")


def record_words() -> str:
    """The record check's own sentence."""
    return ("The record check before a push: one changelog.d fragment and no "
            "CHANGELOG.md edit, the docs/README.md count, every changed backend "
            "file's jarvis-backend twin, one decision record, well-shaped claims "
            "and defect rows, and this repository's own read-only checkers - "
            "ending in READY, NEEDS-RECORDS, CHECKER-FAILED or INCOMPLETE.")
