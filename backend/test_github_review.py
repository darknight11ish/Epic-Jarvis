"""test_github_review.py - the review packet (wave 16E, 2026-11-10).

    python3 test_github_review.py

WHAT THIS SUITE IS FOR

`backend/jarvis_review.py` answers the owner's ask for the DeepSeek-style review
gate inside Jarvis: "review my branch" or a PR or the local change set, and get
back the base and head commits, the line counts, every changed file grouped by
area, and a short list of risk flags with the concrete evidence - before the
push, instead of after a red CI run.

The product promise is narrow and this suite is the proof of it:

  1. The packet's numbers are the tree's numbers. It is driven against REAL
     temporary git repositories, so "base X -> common ancestor Y -> head Z" and
     "+N / -M" are measured, not mocked: a commit that adds two lines and
     deletes one is reported as exactly that.
  2. Every risk flag fires on a fixture built to make it fire, and NONE of them
     fires on a clean change. The flags are the two-file rule, a backend change
     with no test, a new document without the docs/README.md count bump, a tool
     or route changed without docs/JARVIS-API.md, tracked scratch, a dirty
     working tree, a changed patch, a hand-edited CHANGELOG.md and the size of
     the change.
  3. A branch is reviewed against its COMMON ANCESTOR, so a review of another
     branch cannot pick up this checkout's uncommitted files; a pull request is
     found among the LOCAL branches (Jarvis never fetches) or the answer says
     how to check it out.
  4. The answer is bounded, says which folder and head it measured, and ends
     with the owner's three-part audit checklist and the review rules.
  5. It can reach no network and it cannot write: the module's own `ast` is
     walked for a network import and for a write call, and a real run over a
     temporary repository leaves every file's size and mtime unchanged and
     creates nothing.

No socket is opened anywhere in this run: `NoSocket` refuses one for the whole
suite, including the real git runs, which are local processes. Standard library
only, and no test needs the owner's PC or the live backend.
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# A temp config dir BEFORE anything backend-ish is imported, the same rule every
# GitHub suite follows: no suite may read or write the owner's own config.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-review-suite-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ.pop("JARVIS_BACKEND", None)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

import jarvis_review as R  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """Something this machine cannot run: printed separately, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class NoSocket:
    """Refuses every real socket, for the whole run."""

    def __enter__(self):
        import socket
        self._socket = socket.socket
        self._pair = socket.socketpair

        def refuse(*_a, **_k):
            raise AssertionError("the review packet must never open a socket")

        socket.socket = refuse
        socket.socketpair = refuse
        return self

    def __exit__(self, *_exc):
        import socket
        socket.socket = self._socket
        socket.socketpair = self._pair


GIT = shutil.which("git")


# --------------------------------------------------------------------------
#   A real temporary repository, because the numbers must be the tree's
# --------------------------------------------------------------------------


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _repo(files=None, *, commit=True):
    """One temp git repo on `main`, with the given files committed."""
    box = Path(tempfile.mkdtemp(prefix="jarvis-review-repo-"))
    if _git(box, "init", "-q", "-b", "main").returncode != 0:
        _git(box, "init", "-q")
    _git(box, "config", "user.email", "suite@example.invalid")
    _git(box, "config", "user.name", "suite")
    _git(box, "config", "core.autocrlf", "false")
    _git(box, "config", "commit.gpgsign", "false")
    for rel, text in (files or {}).items():
        target = box / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")
    if commit:
        _git(box, "add", "-A")
        _git(box, "commit", "-q", "-m", "the base")
    return box


def _write(box: Path, rel: str, text: str) -> None:
    target = box / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="")


def _commit(box: Path, message="a change") -> None:
    _git(box, "add", "-A")
    _git(box, "commit", "-q", "-m", message)


#: A base tree that already looks like this repository in the small: a backend
#: module with its published-base twin, a docs page stating its own count, and
#: the two record folders.
BASE_TREE = {
    "backend/jarvis_thing.py": "VALUE = 1\n",
    "jarvis-backend/jarvis_thing.py": "VALUE = 1\n",
    "backend/test_thing.py": "def test_nothing():\n    assert True\n",
    "docs/README.md": ("# The documents\n\nThere are **1 markdown documents** here, "
                       "about **1 MB**.\n"),
    "docs/JARVIS-API.md": "# The API\n",
    "changelog.d/README.md": "# fragments\n",
    "decisions.d/README.md": "# fragments\n",
    "tools/check_thing.py": "# a checker\n",
}


def _snapshot(box: Path) -> dict:
    """Every file under `box`, with its size and mtime - the no-write proof."""
    return {str(p.relative_to(box)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in box.rglob("*") if p.is_file()}


# --------------------------------------------------------------------------
#   1. the numbers are the tree's
# --------------------------------------------------------------------------


def t_the_packet_names_the_tree_base_head_and_the_line_counts():
    if GIT is None:
        return skip("the review packet needs git on PATH")
    box = _repo(BASE_TREE)
    _git(box, "checkout", "-q", "-b", "feat/review")
    _write(box, "backend/jarvis_thing.py", "VALUE = 2\nVALUE = 3\n")
    _write(box, "docs/NEW-DOC.md", "# a new document\n")
    _commit(box, "two lines added, one replaced")
    out = R.review({"path": str(box), "base": "main"})
    text = str(out.get("text") or "")
    measured = out.get("measured") or {}
    check("the packet is built", bool(out.get("ok")), out.get("error"))
    head = _git(box, "rev-parse", "HEAD").stdout.strip()
    check("it names the folder it measured",
          str(box).replace("\\", "/") in text.replace("\\", "/"), text[:300])
    check("it names the head commit it measured", head[:9] in text, text[:300])
    check("it names the base branch", "main" in text and "common ancestor" in text,
          text[:300])
    check("measured: head sha is the real HEAD", measured.get("head_sha") == head,
          measured.get("head_sha"))
    check("measured: the base is main", measured.get("base") == "main",
          measured.get("base"))
    # The exact numbers git itself reports, so the packet cannot drift.
    stat = _git(box, "diff", "--numstat", "main").stdout.splitlines()
    added = sum(int(line.split("\t")[0]) for line in stat if line.strip())
    deleted = sum(int(line.split("\t")[1]) for line in stat if line.strip())
    check("the line counts are the real diff, as git reports it",
          f"+{added} / -{deleted}" in text,
          [line for line in text.splitlines() if "changed:" in line])
    check("the changed file is listed with its status",
          "backend/jarvis_thing.py" in text and "docs/NEW-DOC.md" in text, text)
    check("the new document is grouped under docs",
          "docs (1)" in text, [line for line in text.splitlines() if "docs (" in line])
    check("the packet ends with the owner's three-part checklist",
          "audit checklist" in text and "Both apps" in text and "Fit" in text, text[-800:])
    check("the packet ends with the review rules",
          "Quote the evidence" in text and "never counted as passes" in text,
          text[-600:])


def t_a_branch_is_reviewed_against_its_common_ancestor():
    if GIT is None:
        return skip("a branch review needs git on PATH")
    box = _repo(BASE_TREE)
    _git(box, "checkout", "-q", "-b", "feat/branch")
    _write(box, "backend/jarvis_thing.py", "VALUE = 1\n")
    _write(box, "docs/ON-THE-BRANCH.md", "# on the branch\n")
    _commit(box, "the branch's own change")
    _git(box, "checkout", "-q", "main")
    # This checkout is dirty with a file that is NOT on the branch.
    _write(box, "tools/NOT-ON-THE-BRANCH.py", "# uncommitted\n")
    out = R.review({"path": str(box), "base": "main", "branch": "feat/branch"})
    text = str(out.get("text") or "")
    check("the branch review is built", bool(out.get("ok")), out.get("error"))
    check("it says it reviewed the branch",
          "branch feat/branch" in text, text[:300])
    check("the branch's own file is in the packet",
          "docs/ON-THE-BRANCH.md" in text, text)
    check("this checkout's uncommitted file is NOT in a branch review",
          "NOT-ON-THE-BRANCH" not in text, text)
    check("a branch review's head is the branch's head, not this checkout's",
          (out.get("measured") or {}).get("head_sha")
          == _git(box, "rev-parse", "feat/branch").stdout.strip(),
          (out.get("measured") or {}).get("head_sha"))


def t_a_pull_request_is_found_locally_or_says_how_to_check_it_out():
    if GIT is None:
        return skip("a pull request review needs git on PATH")
    box = _repo(BASE_TREE)
    _git(box, "checkout", "-q", "-b", "fix/pr-77")
    _write(box, "docs/FROM-THE-PR.md", "# from the pull request\n")
    _commit(box, "the pull request's change")
    _git(box, "checkout", "-q", "main")
    found = R.review({"path": str(box), "base": "main", "pr": "77"})
    text = str(found.get("text") or "")
    check("a pull request number finds its local branch", bool(found.get("ok")),
          found.get("error"))
    check("... and the packet says nothing was fetched",
          "nothing was fetched" in text, text[:400])
    check("... and it reviewed that branch's file", "FROM-THE-PR.md" in text, text)
    missing = R.review({"path": str(box), "base": "main", "pr": "78"})
    check("an un-checked-out pull request is one plain sentence",
          missing.get("ok") is False and "not checked out" in str(missing.get("error"))
          and "fetch" in str(missing.get("error")), missing.get("error"))


def t_a_bad_folder_or_base_is_one_plain_sentence():
    if GIT is None:
        return skip("this check needs git on PATH")
    missing = R.review({"path": str(_TMP / "not-here-at-all")})
    check("a folder that is not there is said plainly",
          missing.get("ok") is False and "not on this PC" in str(missing.get("error")),
          missing.get("error"))
    plain = Path(tempfile.mkdtemp(prefix="jarvis-review-norepo-"))
    (plain / "a.txt").write_text("x\n", encoding="utf-8")
    not_repo = R.review({"path": str(plain)})
    check("a folder outside git is said plainly",
          not_repo.get("ok") is False
          and "not inside a git repository" in str(not_repo.get("error")),
          not_repo.get("error"))
    box = _repo(BASE_TREE)
    bad_base = R.review({"path": str(box), "base": "no-such-branch"})
    check("a base that is not there is said plainly, and fetching is not done",
          bad_base.get("ok") is False and "does not fetch" in str(bad_base.get("error")),
          bad_base.get("error"))
    bad_ref = R.review({"path": str(box), "base": "main; rm -rf /"})
    check("a ref with a semicolon in it is refused before any command",
          bad_ref.get("ok") is False and "not a ref" in str(bad_ref.get("error")),
          bad_ref.get("error"))
    no_path = R.review({})
    check("no folder at all says how to give one",
          no_path.get("ok") is False and R.ENV_REPO in str(no_path.get("error")),
          no_path.get("error"))


def t_the_folder_guard_refuses_a_key_store():
    home = Path.home()
    for name in (".ssh", ".gnupg", ".aws"):
        where = home / name
        why = R._refused_path(str(where))
        check(f"{name} is refused by name", bool(why), why)
    why = R._refused_path(str(Path(tempfile.mkdtemp(prefix="jarvis-review-ok-"))))
    check("an ordinary folder is not refused", why == "", why)


# --------------------------------------------------------------------------
#   2. every risk flag fires on its fixture, and none on a clean change
# --------------------------------------------------------------------------


def _flags_of(text: str) -> list:
    """The flag lines of one packet (indented under `risk flags:`)."""
    lines = str(text or "").splitlines()
    out, inside = [], False
    for line in lines:
        if line.strip() == "risk flags:":
            inside = True
            continue
        if inside:
            stripped = line.strip()
            if line.startswith("  ") and stripped.startswith(("FLAG", "INFO", "NOTE")):
                out.append(stripped)
            elif stripped:
                break
    return out


def _clean_change(box: Path) -> None:
    """A change that satisfies every recorded rule, so NO flag may fire."""
    _write(box, "backend/jarvis_thing.py", "VALUE = 1\nVALUE = 2\n")
    _write(box, "jarvis-backend/jarvis_thing.py", "VALUE = 1\nVALUE = 2\n")
    _write(box, "backend/test_thing.py",
           "def test_nothing():\n    assert True\n\n\ndef test_two():\n    assert True\n")
    _write(box, "docs/JARVIS-API.md", "# The API\n\nOne more sentence.\n")
    _write(box, "docs/NEW-DOC.md", "# a new document\n")
    _write(box, "docs/README.md",
           "# The documents\n\nThere are **2 markdown documents** here, about "
           "**1 MB**.\n")
    _write(box, "changelog.d/2026-11-10-a-change.md",
           "- **A change:** one sentence about what changed.\n")
    _write(box, "decisions.d/2026-11-10-a-decision.md",
           "- **2026-11-10 \u2014 A decision:** one sentence about why.\n")
    _commit(box, "a well-formed change")


def t_each_risk_flag_fires_on_its_own_fixture():
    if GIT is None:
        return skip("the risk flags need git on PATH")

    def packet(mutate) -> str:
        box = _repo(BASE_TREE)
        _git(box, "checkout", "-q", "-b", "feat/flag")
        mutate(box)
        out = R.review({"path": str(box), "base": "main"})
        return str(out.get("text") or "")

    def twin_missing(box):
        _write(box, "backend/jarvis_thing.py", "VALUE = 9\n")
        _commit(box)

    text = packet(twin_missing)
    flags = _flags_of(text)
    check("the twin flag fires: backend changed, jarvis-backend did not",
          any("twin edit" in f and "jarvis-backend/jarvis_thing.py" in f
              for f in flags), flags)
    check("... and it says what the next step is",
          any("twin edit" in f and "next:" in f for f in flags), flags)

    def no_test(box):
        _write(box, "backend/jarvis_thing.py", "VALUE = 4\n")
        _commit(box)

    flags = _flags_of(packet(no_test))
    check("the no-test flag fires",
          any("no test changed" in f for f in flags), flags)

    def new_doc(box):
        _write(box, "docs/ANOTHER-DOC.md", "# another\n")
        _commit(box)

    flags = _flags_of(packet(new_doc))
    check("the new-document flag fires without the docs count bump",
          any("without the docs/README.md count bump" in f for f in flags), flags)
    check("... and it says not to regenerate the size",
          any("do NOT regenerate the size" in f for f in flags), flags)

    def api_doc(box):
        _write(box, "backend/jarvis_agent.py", "# the tools\n")
        _write(box, "jarvis-backend/jarvis_agent.py", "# the tools\n")
        _commit(box)

    flags = _flags_of(packet(api_doc))
    check("the API-doc flag fires for a changed tool carrier",
          any("without docs/JARVIS-API.md" in f for f in flags), flags)

    def scratch(box):
        _write(box, ".dsh-scratch/notes.md", "# scratch\n")
        _commit(box)

    flags = _flags_of(packet(scratch))
    check("the tracked-scratch flag fires",
          any("tracked scratch" in f for f in flags), flags)

    def dirty(box):
        _write(box, "backend/jarvis_thing.py", "VALUE = 5\n")

    flags = _flags_of(packet(dirty))
    check("the dirty-tree note fires for an uncommitted change",
          any("dirty working tree" in f for f in flags), flags)

    def changelog(box):
        _write(box, "CHANGELOG.md", "# Changelog\n\n- **A change:** done.\n")
        _commit(box)

    flags = _flags_of(packet(changelog))
    check("the CHANGELOG.md flag fires",
          any("CHANGELOG.md edited" in f for f in flags), flags)

    def patch(box):
        _write(box, "backend/tasks.patch", "diff --git a/x b/x\n")
        _commit(box)

    flags = _flags_of(packet(patch))
    check("the patch-history flag fires",
          any("patch changed" in f and "build_patch_history" in f for f in flags),
          flags)

    def many(box):
        for i in range(41):
            _write(box, f"tools/gen_thing_{i}.py", "# many\n")
        _commit(box)

    flags = _flags_of(packet(many))
    check("the size note fires past 40 files",
          any("large change" in f for f in flags), flags[:3])


def t_both_copies_changing_but_disagreeing_is_flagged():
    if GIT is None:
        return skip("the twin rules need git on PATH")
    box = _repo(BASE_TREE)
    _git(box, "checkout", "-q", "-b", "feat/mismatch")
    _write(box, "backend/jarvis_thing.py", "VALUE = 1\nVALUE = 2\n")
    _write(box, "jarvis-backend/jarvis_thing.py", "VALUE = 1\nVALUE = 3\n")
    _commit(box, "both halves changed, differently")
    flags = _flags_of(str(R.review({"path": str(box), "base": "main"}).get("text")))
    check("a mismatched pair is flagged even when both copies changed",
          any("no longer match" in f for f in flags), flags)
    # The rebuilt modules land FLATTENED in the base, so the twin of
    # backend/rebuilt/<file> is jarvis-backend/<file> - not a rebuilt/ subfolder.
    check("a rebuilt module's twin is the flattened base name",
          R._twin_of("backend/rebuilt/jarvis_memory.py") ==
          "jarvis-backend/jarvis_memory.py",
          R._twin_of("backend/rebuilt/jarvis_memory.py"))
    check("a test file owes no twin, because the base never carries one",
          R._twin_of("backend/test_thing.py") == "",
          R._twin_of("backend/test_thing.py"))


def t_a_clean_change_fires_none_of_them():
    if GIT is None:
        return skip("the clean-change check needs git on PATH")
    box = _repo(BASE_TREE)
    _git(box, "checkout", "-q", "-b", "feat/clean")
    _clean_change(box)
    out = R.review({"path": str(box), "base": "main"})
    text = str(out.get("text") or "")
    flags = _flags_of(text)
    check("a well-formed change is measured", bool(out.get("ok")), out.get("error"))
    check("no risk flag fires on a clean change", not flags, flags)
    check("... and the packet says so instead of leaving the section blank",
          "(none of the recorded flags fired)" in text, text)
    check("a clean change still lists its areas",
          "backend (modules and tests)" in text and "docs" in text, text)


def t_the_answer_is_bounded():
    if GIT is None:
        return skip("the bound check needs git on PATH")
    box = _repo(BASE_TREE)
    _git(box, "checkout", "-q", "-b", "feat/many")
    for i in range(60):
        _write(box, f"backend/gen_part_{i}.py", "VALUE = %d\n" % i)
    _commit(box, "many parts")
    long = R.review({"path": str(box), "base": "main"})
    check("the default packet is at most 7000 characters",
          len(str(long.get("text") or "")) <= R.REVIEW_MAX_TEXT,
          len(str(long.get("text") or "")))
    short = R.review({"path": str(box), "base": "main", "max_chars": 400})
    text = str(short.get("text") or "")
    check("a short packet is at most the asked size", len(text) <= 400, len(text))
    check("... and it says it was cut", "cut here" in text, text[-200:])
    check("the bound holds a flag and the counts on the way out",
          "changed:" in text, text)


# --------------------------------------------------------------------------
#   3. read-only, no network, no write path
# --------------------------------------------------------------------------


def _module_tree():
    return ast.parse((HERE / "jarvis_review.py").read_text(encoding="utf-8"))


def t_the_module_can_reach_no_network():
    tree = _module_tree()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    network = imported & {"socket", "urllib", "http", "httplib", "requests", "ssl",
                          "ftplib", "smtplib", "aiohttp", "websocket", "telnetlib",
                          "xmlrpc", "asyncio"}
    check("the module imports no network library at all", not network, sorted(network))
    check("... and its imports are the small stdlib set it needs",
          imported <= {"os", "re", "subprocess", "sys", "time", "dataclasses",
                       "datetime", "pathlib", "typing", "__future__"},
          sorted(imported))


def t_the_module_has_no_write_path():
    tree = _module_tree()
    # `str.replace` is not a write, so the names here are the unambiguous
    # filesystem ones; the `open(...)` scan below covers the rest.
    writes = {"write_text", "write_bytes", "touch", "unlink", "mkdir", "rmdir",
              "rename", "remove", "rmtree", "copy2", "copyfile", "copytree",
              "move", "chmod", "truncate", "makedirs", "symlink_to", "link_to"}
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name in writes:
            found.append(name)
        if name == "open":
            mode = ""
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    mode = str(keyword.value.value)
            if any(ch in mode for ch in "wax+") or not mode:
                found.append(f"open({mode or 'r?'})")
    check("the module calls no write function", not found, sorted(set(found)))
    # The one process seam is subprocess.run with a LIST and no shell.
    shells = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in ("run", "Popen", "check_output", "call")
              and any(k.arg == "shell" and isinstance(k.value, ast.Constant)
                      and k.value.value for k in n.keywords)]
    check("no child process is ever started through a shell", not shells, shells)


def t_a_real_run_writes_nothing_and_opens_no_socket():
    if GIT is None:
        return skip("the no-write proof needs git on PATH")
    box = _repo(BASE_TREE)
    _write(box, "backend/jarvis_thing.py", "VALUE = 6\n")
    _write(box, "docs/NEW-DOC.md", "# new\n")
    before = _snapshot(box)
    with NoSocket():
        out = R.review({"path": str(box), "base": "main"})
    after = _snapshot(box)
    check("the run answered", bool(out.get("ok")), out.get("error"))
    check("no file was created", set(after) == set(before),
          sorted(set(after) ^ set(before)))
    check("no file's size or mtime changed", after == before,
          [(k, before.get(k), after.get(k)) for k in after if before.get(k) != after.get(k)])


def t_the_module_says_it_writes_nothing_and_needs_no_token():
    words = R.review_words()
    check("the tool's own words say read-only", "Read-only" in words, words)
    facts = " ".join(R.REVIEW_FACTS)
    check("the facts say nothing is written", "writes nothing" in facts, facts)
    check("the facts say there is no network", "no network" in facts, facts)
    check("the facts say no GitHub token is read", "no GitHub token" in facts, facts)
    check("the facts say a check that did not run is never a pass",
          "never reported as a pass" in facts, facts)


def t_it_names_what_it_measured_and_what_it_could_not():
    if GIT is None:
        return skip("this check needs git on PATH")
    box = _repo(BASE_TREE)
    _git(box, "checkout", "-q", "-b", "feat/x")
    _write(box, "backend/jarvis_thing.py", "VALUE = 7\n")
    _commit(box)
    out = R.review({"path": str(box), "base": "main"})
    check("the packet says it writes nothing",
          "this review writes nothing" in str(out.get("text")), out.get("text"))
    check("measured: it names the merge base it used",
          bool((out.get("measured") or {}).get("merge_base")),
          out.get("measured"))


def t_an_empty_tree_is_answered_not_crashed():
    if GIT is None:
        return skip("this check needs git on PATH")
    box = _repo(BASE_TREE)
    out = R.review({"path": str(box), "base": "main"})
    check("a clean tree is answered", bool(out.get("ok")), out.get("error"))
    check("... and it says there is nothing to review",
          "nothing to review" in str(out.get("text")).lower(), out.get("text"))


if __name__ == "__main__":
    print(f"  suite {Path(__file__).name}")
    print(f"  file  {HERE / 'jarvis_review.py'}")
    if GIT is None:
        print("  note  git is not on PATH; the tree-backed checks will skip")
    with NoSocket():
        for fn in (t_the_packet_names_the_tree_base_head_and_the_line_counts,
                   t_a_branch_is_reviewed_against_its_common_ancestor,
                   t_a_pull_request_is_found_locally_or_says_how_to_check_it_out,
                   t_a_bad_folder_or_base_is_one_plain_sentence,
                   t_the_folder_guard_refuses_a_key_store,
                   t_each_risk_flag_fires_on_its_own_fixture,
                   t_both_copies_changing_but_disagreeing_is_flagged,
                   t_a_clean_change_fires_none_of_them,
                   t_the_answer_is_bounded,
                   t_the_module_can_reach_no_network,
                   t_the_module_has_no_write_path,
                   t_a_real_run_writes_nothing_and_opens_no_socket,
                   t_the_module_says_it_writes_nothing_and_needs_no_token,
                   t_it_names_what_it_measured_and_what_it_could_not,
                   t_an_empty_tree_is_answered_not_crashed):
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
