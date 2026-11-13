"""test_github_authoring.py - wave 16B: Jarvis writes the fix inside the copy.

    python3 backend/test_github_authoring.py

WHAT THIS SUITE IS FOR

The 2026-11-10 GitHub record deferred one thing in its own words: *"The
scratch-scoped code-authoring tool that would let fix-and-push write its own fix
is deliberately deferred to wave 16B."* This is wave 16B, and this suite proves
the capability it added:

  * `github_fix_and_push` stage "write" changes ONE file inside the isolated
    copy the "prepare" stage made, and makes ONE commit there, on its OWN card
    (`github_fix_write`) showing the file, the exact unified diff and the commit
    message - and it sends NOTHING, uses no token, and never leaves this PC;
  * stage "read" shows one file from that copy and raises NO card, because it
    sends nothing and changes nothing - like every other local read;
  * every way out is refused in a plain sentence and changes nothing: `..`, an
    absolute path, a drive letter, a UNC address, a symlink or Windows junction,
    another pull request's copy, the owner's own checkout, a folder that was
    never prepared, a credential file, `.git`, a delete/rename/move/chmod
    argument, a change too big for one card, and a file that changed since the
    card was shown;
  * the existing carded push still prints the REAL commits, files and command,
    and it does not happen without its own approval.

HERMETIC, AND WHY IT USES REAL GIT

Every folder is a temporary directory; the scratch root is redirected through
`JARVIS_GITHUB_SCRATCH_ROOT`, so nothing here can touch the owner's own
`%LOCALAPPDATA%\\Jarvis\\github-fix`. The write stage's whole job is a file plus a
git commit, so this suite initialises a REAL temporary git repository and drives
the module's REAL git executor: a fake could agree with a broken implementation.
No socket is opened (the write and the read never open one, and `NoSocket` makes
that a failure rather than a claim), no GitHub token is read, and no network is
touched. The push RUN is only ever called with `approved=False`, so even the one
network-capable stage cannot reach out from here.

Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for path in (HERE, HERE / "rebuilt"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

#: The scratch root this suite owns. Set BEFORE `jarvis_github` is imported, and
#: read again on every call by the module (`scratch_root()` is deliberately not
#: cached), so one fresh root per run is enough.
_TMP = tempfile.mkdtemp(prefix="jarvis-github-authoring-")
os.environ["JARVIS_GITHUB_SCRATCH_ROOT"] = os.path.join(_TMP, "scratch")
#: A config folder of this suite's own, so an import cannot read the owner's.
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", os.path.join(_TMP, "config"))
os.environ.setdefault("JARVIS_CONFIG_DIR", os.path.join(_TMP, "config"))
os.environ.pop("JARVIS_FRAMEWORK_TOML", None)

import jarvis_github as GH  # noqa: E402
import jarvis_agent as AG  # noqa: E402

ROOT = GH.scratch_root()
REPO_NAME = "owner/repo"
NUMBER = "12"
BRANCH = "fix/tray-icon"
HEAD_SHA = "a" * 40
TOKEN = "ghp_" + "x" * 30

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """An honest SKIP: the thing this check needs is not on this PC.

    Never a silent pass - a check that passes without looking is worse than no
    check at all.
    """
    SKIPPED.append(name)
    print(f"SKIP {name}\n        {why}")


class NoSocket:
    """Any socket opened while this is active fails the run (the same guard
    `test_github_parity.py` uses). The write and the read must never open one."""

    def __enter__(self):
        import socket

        self.saved = (socket.socket, socket.create_connection,
                      socket.getaddrinfo)
        self.opened = []

        def bad(*a, **k):
            self.opened.append(a)
            raise AssertionError("a socket was opened by a local-only stage")

        socket.socket = bad
        socket.create_connection = bad
        socket.getaddrinfo = bad
        return self

    def __exit__(self, *exc):
        import socket
        socket.socket, socket.create_connection, socket.getaddrinfo = self.saved
        return False


def _git(args, cwd=None, env=None):
    """The REAL git, used by the fixtures and by the module's own executor."""
    run_env = dict(os.environ)
    run_env.update({str(k): str(v) for k, v in (env or {}).items()})
    done = subprocess.run(["git"] + [str(a) for a in args], cwd=cwd,
                          capture_output=True, text=True, env=run_env,
                          stdin=subprocess.DEVNULL)
    return int(done.returncode), done.stdout or "", done.stderr or ""


class Copy:
    """A prepared copy for one pull request, as `prepare` would have left it.

    The `.git` note is the same file `_write_marker` makes (no token, the repo,
    the number, the branch and the head sha), so the write stage's marker check
    is exercised for real rather than bypassed.
    """

    #: One unique folder per fixture, so two copies in one run cannot collide.
    _made = 0

    def __init__(self, number=NUMBER, repo=REPO_NAME, branch=BRANCH, sha=None,
                 files=None, folder=None):
        self.repo = repo
        self.number = str(number)
        self.branch = branch
        Copy._made += 1
        name = folder or (GH.scratch_folder_name(repo, self.number)
                          + f"__t{Copy._made}")
        self.path = os.path.join(ROOT, name)
        os.makedirs(self.path)
        code, _out, err = _git(["init", "-q"], cwd=self.path)
        assert code == 0, err
        self.write("README.md", "# fixture\n")
        for rel, text in (files or {"backend/app.py":
                                    "def main():\n    return 1\n"}).items():
            self.write(rel, text)
        code, _out, err = _git(["add", "--", "."], cwd=self.path)
        assert code == 0, err
        code, _out, err = _git(
            ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
             "commit", "-qm", "the pull request's head"], cwd=self.path)
        assert code == 0, err
        # The prepare stage renames the local branch to the pull request's own
        # branch, so a push card can only ever name that branch.
        code, _out, err = _git(["checkout", "-qb", branch], cwd=self.path)
        assert code == 0, err
        # The note `prepare` leaves names the pull request's REAL head commit -
        # a fabricated sha would make the push stage's `git log <sha>..HEAD`
        # fail, which is a fixture bug, not the product's.
        code, out, err = _git(["rev-parse", "HEAD"], cwd=self.path)
        assert code == 0, err
        self.sha = sha or out.strip()
        os.makedirs(os.path.join(self.path, ".git"), exist_ok=True)
        with open(GH._marker_path(self.path), "w", encoding="utf-8") as fh:
            json.dump({"repo": repo, "number": self.number, "head_ref": branch,
                       "head_sha": self.sha, "failing_checks": []}, fh)

    def file(self, rel):
        return os.path.join(self.path, *rel.split("/"))

    def read(self, rel):
        with open(self.file(rel), "r", encoding="utf-8", newline="") as fh:
            return fh.read()

    def write(self, rel, text):
        target = self.file(rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def commits(self):
        code, out, _ = _git(["log", "--format=%s"], cwd=self.path)
        return [line for line in out.splitlines() if line.strip()]

    def dirty(self):
        code, out, _ = _git(["status", "--porcelain"], cwd=self.path)
        return out.strip()


def _write_args(copy, **over):
    args = {"repo": copy.repo, "number": copy.number, "stage": "write",
            "worktree": copy.path, "path": "backend/app.py",
            "content": "def main():\n    return 0\n",
            "message": "Fix the return value"}
    args.update(over)
    return args


def _plan(copy, **over):
    return GH.plan_fix_and_push(_write_args(copy, **over), git=_git)


# --------------------------------------------------------------------------
#   1. The happy path: one file, one commit, one card showing the exact change
# --------------------------------------------------------------------------


def t_the_write_changes_one_file_and_makes_one_commit():
    copy = Copy()
    before = copy.read("backend/app.py")
    outside = os.path.join(_TMP, "outside.txt")
    Path(outside).write_text("untouched", encoding="utf-8")
    commits_before = copy.commits()
    r = _plan(copy)
    text = GH.describe(r)
    check("the card is its OWN action, never the push's",
          r.action == GH.ACTION_FIX_WRITE and r.action in GH.ACTIONS, r.action)
    check("... and the card names the pull request and the file",
          f"#{NUMBER}" in text and "backend/app.py" in text, text[:300])
    check("the card shows the exact change as a real unified diff",
          "--- a/backend/app.py" in text and "+++ b/backend/app.py" in text
          and "-    return 1" in text and "+    return 0" in text, text)
    check("... and the one-line commit message",
          "Fix the return value" in text, text[-400:])
    check("the card says no token is used and nothing is sent",
          "sends nothing anywhere" in text and "no github token" in text.lower(),
          text[-400:])
    check("the card does not claim the GitHub token is sent",
          "sent to api.github.com" not in text)
    check("nothing was written while PLANNING", copy.read("backend/app.py") == before)
    out = GH.run(r, approved=True, git=_git)
    check("the write succeeds", out.get("ok") is True, out)
    check("the file has exactly the new text", copy.read("backend/app.py")
          == "def main():\n    return 0\n", repr(copy.read("backend/app.py")))
    after_commits = copy.commits()
    check("exactly ONE commit was made",
          len(after_commits) == len(commits_before) + 1, after_commits)
    check("... with the message the card showed",
          after_commits[0] == "Fix the return value", after_commits[:2])
    check("... and only that one file is in it",
          _git(["show", "--name-only", "--format=", "HEAD"], cwd=copy.path)[1]
          .strip() == "backend/app.py",
          _git(["show", "--name-only", "--format=", "HEAD"], cwd=copy.path)[1])
    check("the copy is left CLEAN, so the push stage can read it",
          copy.dirty() == "", copy.dirty())
    check("nothing outside the copy changed",
          Path(outside).read_text(encoding="utf-8") == "untouched")
    check("the answer says nothing was pushed",
          "Nothing is pushed" in str(out.get("text")) or
          "nothing is pushed" in str(out.get("text")).lower(), out)
    check("... and that no token was used",
          "no github token" in str(out.get("text")).lower(), out)
    return copy


def t_a_new_file_can_be_added_and_shows_every_line_as_an_addition():
    copy = Copy(files={"backend/app.py": "x = 1\n"})
    r = _plan(copy, path="backend/new_module.py", content="y = 2\n",
              message="Add the missing module")
    text = GH.describe(r)
    check("a new file is named as one on the card", "a NEW file" in text, text[:300])
    check("... and its diff is against /dev/null",
          "--- /dev/null" in text and "+y = 2" in text, text[-300:])
    out = GH.run(r, approved=True, git=_git)
    check("the new file is written", out.get("ok") is True, out)
    check("... with its text", copy.read("backend/new_module.py") == "y = 2\n")
    check("... and committed", copy.commits()[0] == "Add the missing module",
          copy.commits()[:2])


# --------------------------------------------------------------------------
#   2. The read: no card, local only, the file's own text
# --------------------------------------------------------------------------


def t_the_read_raises_no_card_and_returns_the_files_text():
    copy = Copy()
    words = GH.read_copy_file({"repo": copy.repo, "number": copy.number,
                               "worktree": copy.path, "path": "backend/app.py"})
    check("the read names the pull request and the file",
          f"#{NUMBER}" in words and "backend/app.py" in words, words[:200])
    check("... says it is a local read", "nothing was sent" in words.lower(), words[:300])
    check("... and returns the file's real text",
          "def main():" in words and "return 1" in words, words[-300:])
    check("it is wrapped as data, not instructions",
          GH.GITHUB_TEXT_BEGINS in words and GH.GITHUB_TEXT_ENDS in words,
          words[:200])
    state, text = AG.TOOLS["github_fix_and_push"].prepare(
        {"repo": copy.repo, "number": copy.number, "stage": "read",
         "worktree": copy.path, "path": "backend/app.py"})
    check("the agent's prepare answers the read directly, with NO card",
          isinstance(state, AG._GitHubAnswered) and text == "", (state, text))
    check("... and no token is needed for it", bool(state.words))


# --------------------------------------------------------------------------
#   3. Every way out is refused, in words, and nothing is written
# --------------------------------------------------------------------------


def _refused(label, args, needle, copy=None):
    try:
        if str(args.get("stage") or "").strip().lower() == "read":
            GH.read_copy_file(args)
        else:
            GH.plan_fix_and_push(args, git=_git)
    except GH.GitHubError as exc:
        said = str(exc)
        check(f"{label}: refused", True)
        check(f"{label}: in a plain sentence naming why", needle.lower() in
              said.lower(), said)
        return said
    check(f"{label}: refused", False, "it was NOT refused")
    return ""


def t_every_escape_is_refused_with_nothing_written():
    copy = Copy()
    other = Copy(number="13", branch="fix/other")
    before = copy.read("backend/app.py")
    live = os.path.join(_TMP, "live-checkout")
    os.makedirs(live, exist_ok=True)
    Path(os.path.join(live, "app.py")).write_text("live", encoding="utf-8")

    _refused("a '..' path", _write_args(copy, path="../../outside.txt"),
             "contains \"..\"")
    _refused("an absolute path outside the copy",
             _write_args(copy, path=os.path.join(_TMP, "outside.txt")),
             "full file address")
    _refused("a drive-letter path", _write_args(copy, path="C:\\Windows\\evil.txt"),
             "full file address")
    _refused("a UNC path", _write_args(copy, path="\\\\server\\share\\evil.txt"),
             "full file address")
    _refused("a credential file from the push stage's denylist",
             _write_args(copy, path=".env"), "key, a password or a token")
    _refused("a private key", _write_args(copy, path="deploy/id_rsa"),
             "key, a password or a token")
    _refused("a path inside .git", _write_args(copy, path=".git/config"),
             "key, a password or a token")
    _refused("another pull request's copy",
             _write_args(copy, worktree=other.path), "different pull request")
    _refused("the owner's live checkout",
             _write_args(copy, worktree=live), "not inside Jarvis's own scratch")
    _refused("a folder that was never prepared",
             _write_args(copy, worktree=os.path.join(ROOT, "not-prepared")),
             "no prepared scratch folder")
    _refused("a delete argument", _write_args(copy, delete=True),
             "cannot delete, rename, move")
    _refused("a rename argument", _write_args(copy, rename_to="elsewhere.py"),
             "cannot delete, rename, move")
    _refused("a chmod argument", _write_args(copy, mode="0755"),
             "cannot delete, rename, move")
    _refused("no content at all",
             {"repo": copy.repo, "number": copy.number, "stage": "write",
              "worktree": copy.path, "path": "backend/app.py", "message": "m"},
             "new text")
    _refused("no commit message",
             {"repo": copy.repo, "number": copy.number, "stage": "write",
              "worktree": copy.path, "path": "backend/app.py", "content": "x\n"},
             "one-line message")
    _refused("text that has not changed", _write_args(copy, content=before),
             "already contains exactly that text")
    _refused("a change too big for one card",
             _write_args(copy, content="".join(
                 f"line {i}: the quick brown fox jumps over the lazy dog\n"
                 for i in range(200))),
             "bigger than one card")
    _refused("a binary file (a NUL in the text)",
             _write_args(copy, content="a\x00b"), "NUL")
    check("every one of those left the file exactly as it was",
          copy.read("backend/app.py") == before, copy.read("backend/app.py")[:80])
    check("... and left the live checkout exactly as it was",
          Path(os.path.join(live, "app.py")).read_text(encoding="utf-8") == "live")
    check("... and made no commit", copy.commits()[0] == "the pull request's head",
          copy.commits()[:2])


def t_a_link_out_of_the_copy_is_refused():
    copy = Copy()
    outside = os.path.join(_TMP, "link-target")
    os.makedirs(outside, exist_ok=True)
    Path(os.path.join(outside, "secret.txt")).write_text("secret", encoding="utf-8")
    link = copy.file("linked")
    made = ""
    try:
        os.symlink(outside, link, target_is_directory=True)
        made = "symlink"
    except (OSError, NotImplementedError):
        done = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, outside],
            capture_output=True, text=True)
        if done.returncode == 0:
            made = "junction"
    if not made:
        skip("a link out of the copy is refused",
             "this PC refused both a symlink and a junction, so the link case "
             "could not be driven here. It did NOT pass.")
        return
    try:
        _refused(f"a {made} that points outside the copy",
                 _write_args(copy, path="linked/secret.txt"),
                 "outside the prepared scratch copy")
        _refused(f"reading through a {made} that points outside the copy",
                 {"repo": copy.repo, "number": copy.number, "stage": "read",
                  "worktree": copy.path, "path": "linked/secret.txt"},
                 "outside the prepared scratch copy")
        check("the file behind the link was not touched",
              Path(os.path.join(outside, "secret.txt")).read_text(
                  encoding="utf-8") == "secret")
    finally:
        try:
            os.unlink(link) if made == "symlink" else os.rmdir(link)
        except OSError:
            pass


def t_the_run_rechecks_the_file_the_card_showed():
    copy = Copy()
    r = _plan(copy)
    # The file changes between the card and the yes - exactly what a TOCTOU pin
    # exists to catch.
    copy.write("backend/app.py", "def main():\n    return 9\n")
    out = GH.run(r, approved=True, git=_git)
    check("a file that changed since the card is refused",
          out.get("ok") is False, out)
    check("... in plain words", "changed since the card" in str(out.get("error")),
          out)
    check("... and nothing was written over it",
          copy.read("backend/app.py") == "def main():\n    return 9\n")
    check("... and no commit was made",
          copy.commits()[0] == "the pull request's head", copy.commits()[:2])


def t_the_write_is_refused_without_approval_and_with_no_token():
    copy = Copy()
    r = _plan(copy)
    out = GH.run(r, approved=False, git=_git)
    check("an unapproved write is refused",
          out.get("ok") is False and "not approved" in str(out.get("error")), out)
    check("... and nothing was written",
          copy.read("backend/app.py") == "def main():\n    return 1\n")
    # The write is local, so it must work with NO token at all: `_need_token` is
    # replaced with something that fails the run if it is ever called.
    saved = GH._need_token

    def never_called():
        raise AssertionError("the LOCAL write read the GitHub token")

    GH._need_token = never_called
    try:
        with NoSocket():
            out = GH.run(r, approved=True, git=_git)
    finally:
        GH._need_token = saved
    check("the write runs with no token and opens no socket",
          out.get("ok") is True, out)


# --------------------------------------------------------------------------
#   4. The existing carded push still carries the real commits and command
# --------------------------------------------------------------------------


def t_the_push_card_still_shows_the_real_commits_files_and_command():
    copy = Copy()
    out = GH.run(_plan(copy), approved=True, git=_git)
    check("the fix was written and committed", out.get("ok") is True, out)
    push = GH.plan_fix_and_push({"repo": copy.repo, "number": copy.number,
                                 "stage": "push", "worktree": copy.path}, git=_git)
    text = GH.describe(push)
    check("the push card names the REAL new commit",
          "Fix the return value" in text, text[-500:])
    check("... and the changed file", "backend/app.py" in text, text[-500:])
    check("... and the EXACT command",
          "git push origin HEAD:refs/heads/fix/tray-icon" in text, text[-300:])
    check("... and it is the push's own action",
          push.action == GH.ACTION_FIX_PUSH, push.action)
    check("... with the branch and folder the card showed",
          push.head_ref == BRANCH and push.fix_stage == "push", push)
    # The push does NOT happen without its own card: unapproved, it is refused
    # before the token is read, before any read of GitHub, and before any git
    # push. `git` here records every argument it is given.
    calls = []

    def spy(args, cwd=None, env=None):
        calls.append(list(args))
        return _git(args, cwd=cwd, env=env)

    out = GH.run(push, approved=False, git=spy)
    check("the push is refused without its own approval",
          out.get("ok") is False and "not approved" in str(out.get("error")), out)
    check("... and not one git command ran", calls == [], calls)


# --------------------------------------------------------------------------
#   5. The wiring: one tool, four stages, two carded actions
# --------------------------------------------------------------------------


def t_the_tool_wires_the_write_to_its_own_card_action():
    tool = AG.TOOLS["github_fix_and_push"]
    check("the tool advertises all four stages",
          set(tool.parameters["properties"]["stage"]["enum"])
          == {"prepare", "read", "write", "push"},
          tool.parameters["properties"]["stage"]["enum"])
    check("its write stage is decided under its OWN action",
          tool.gate_lookup_name({"stage": "write"}) == GH.ACTION_FIX_WRITE)
    check("anything else stays under the fix-and-push action",
          tool.gate_lookup_name({"stage": "push"}) == GH.ACTION_FIX_PUSH
          and tool.gate_lookup_name({}) == GH.ACTION_FIX_PUSH)
    check("the write action is carded and a person is always asked",
          GH.ACTION_FIX_WRITE in GH.ACTIONS
          and "github_fix_and_push" in AG.NEEDS_A_PERSON)
    check("the tool's own words say it writes only inside that one copy",
          "writes only inside that one copy" in tool.description,
          tool.description[:200])
    # The capability inventory says the same, and its extra gate is the write.
    row = GH.capabilities_for("github_fix_and_push")
    check("the inventory carries the write as a second carded action",
          row["extra_gates"] == (GH.ACTION_FIX_WRITE,), row["extra_gates"])
    check("... and its two-stage kind names prepare, write and push",
          row["two_stage_kind"] == "prepare_write_then_push", row["two_stage_kind"])


def t_no_parameter_can_point_outside_the_prepared_copy():
    """Every path-shaped argument, driven with an escape, must be refused.

    The write stage has exactly two arguments that name a place - `worktree` (a
    folder) and `path` (a file inside it) - and the read uses the same two. This
    drives each one at a place outside the copy and proves the module refuses it
    rather than trusting the argument.
    """
    copy = Copy()
    live = os.path.join(_TMP, "live-checkout-2")
    os.makedirs(live, exist_ok=True)
    Path(os.path.join(live, "app.py")).write_text("live", encoding="utf-8")
    bad_worktrees = [
        live,
        os.path.join(ROOT, "..", "outside"),
        "C:\\Windows",
        os.path.join(_TMP, "scratch", "..", "scratch-evil"),
    ]
    refused = 0
    for worktree in bad_worktrees:
        try:
            GH.plan_fix_and_push(_write_args(copy, worktree=worktree), git=_git)
        except GH.GitHubError:
            refused += 1
    check("every out-of-root worktree is refused", refused == len(bad_worktrees),
          f"{refused}/{len(bad_worktrees)}")
    bad_paths = ["../x", "..\\x", "/etc/passwd", "C:\\x", "\\\\host\\share\\x",
                 "backend/../../x", ".git/HEAD", ".env", "id_ed25519"]
    for path in bad_paths:
        try:
            GH.read_copy_file({"repo": copy.repo, "number": copy.number,
                               "worktree": copy.path, "path": path})
        except GH.GitHubError:
            continue
        check(f"the read refuses the path {path!r}", False, "it was NOT refused")
        return
    check("every out-of-copy path is refused by the read", True)
    check("the live checkout was never touched",
          Path(os.path.join(live, "app.py")).read_text(encoding="utf-8") == "live")


# --------------------------------------------------------------------------
#   The run
# --------------------------------------------------------------------------


if __name__ == "__main__":
    print(f"  file  {HERE / 'jarvis_github.py'}")
    print(f"  tmp   {_TMP}")
    with NoSocket():
        for fn in (t_the_write_changes_one_file_and_makes_one_commit,
                   t_a_new_file_can_be_added_and_shows_every_line_as_an_addition,
                   t_the_read_raises_no_card_and_returns_the_files_text,
                   t_every_escape_is_refused_with_nothing_written,
                   t_a_link_out_of_the_copy_is_refused,
                   t_the_run_rechecks_the_file_the_card_showed,
                   t_the_write_is_refused_without_approval_and_with_no_token,
                   t_the_push_card_still_shows_the_real_commits_files_and_command,
                   t_the_tool_wires_the_write_to_its_own_card_action,
                   t_no_parameter_can_point_outside_the_prepared_copy):
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    import shutil
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
