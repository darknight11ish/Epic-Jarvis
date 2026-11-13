"""test_github_record.py - the repository record check (wave 16E, 2026-11-10).

    python3 test_github_record.py

WHAT THIS SUITE IS FOR

`backend/jarvis_review.py`'s second surface answers "are this change's records
in order before I push?" - the bookkeeping this repository's CI demands, checked
at the desk instead of after a red run: ONE `changelog.d/` fragment and no
`CHANGELOG.md` edit, the `docs/README.md` count when a document was added, every
changed `backend/<file>` carried to `jarvis-backend/<file>`, ONE decision record,
well-shaped claims and defect rows, and this repository's own read-only
checkers.

The promise this suite proves:

  1. READY is reachable, and only on a change that carries every record. The
     well-formed fixture below is a real temporary git repository, so the
     change set, the pre-change record and the docs count are measured, not
     mocked.
  2. Every obligation is MISSING or FAIL on the fixture built to break it:
     no fragment, a hand-edited CHANGELOG.md, two fragments, a badly shaped
     fragment, a one-sided twin, no decision, a decisions fragment whose date
     disagrees with its name, a rewritten DECISIONS.md, a docs count that was
     not bumped, a malformed claims row and a malformed defect row.
  3. A checker that cannot run is NOT-RUN, never PASS: a program that will not
     start, one that runs out of time, one that exits non-zero, one whose own
     output says SKIPPED, and one whose script is not in the tree at all. The
     verdict in each case is INCOMPLETE or CHECKER-FAILED, never READY.
  4. The checkers are the twelve fixed commands from the plan and there is no
     way for a caller's words to become one: every argv is built from a constant
     plus the path of an allow-listed script, and the caller's arguments are not
     in scope where a checker is run.
  5. It writes nothing. A real run over a temporary repository leaves every
     file's size and mtime unchanged and creates no file (the run's logs are
     NOT written anywhere - the excerpt is in the answer), and the module's own
     `ast` is walked for a network import and for a write call.

The git commands are REAL (a temporary repository); only the twelve checker
programs are faked, because this repository's checkers are the authority on
THEMSELVES and this suite is about how their answers are classified, not about
what they check. Standard library only.
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

# A temp config dir BEFORE anything backend-ish is imported: no suite may read
# or write the owner's own config.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-record-suite-"))
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
            raise AssertionError("the record check must never open a socket")

        socket.socket = refuse
        socket.socketpair = refuse
        return self

    def __exit__(self, *_exc):
        import socket
        socket.socket = self._socket
        socket.socketpair = self._pair


GIT = shutil.which("git")

#: The twelve checker scripts, exactly the plan's allow-list. A fixture has to
#: carry them as FILES for the selection to pick them (the check itself never
#: runs in this suite unless it says so).
CHECKER_SCRIPTS = (
    "tools/roll_changelog.py", "tools/check_docs_map.py",
    "tools/roll_decisions.py", "tools/check_claims.py",
    "tools/check_defect_register.py", "tools/check_stale_twins.py",
    "backend/test_base_matches_repo.py", "backend/test_base_regeneration.py",
    "tools/check_no_source_pins.py", "tools/check_parity.py",
    "tools/check_plugins.py", "tools/check_no_scratch_in_the_tree.py",
)


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _write(box: Path, rel: str, text: str) -> None:
    target = box / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="")


def _commit(box: Path, message="a change") -> None:
    _git(box, "add", "-A")
    _git(box, "commit", "-q", "-m", message)


#: The record files a change has to fill in, and the two record files CI reads.
BASE_TREE = {
    "backend/jarvis_thing.py": "VALUE = 1\n",
    "jarvis-backend/jarvis_thing.py": "VALUE = 1\n",
    "backend/test_thing.py": "def test_nothing():\n    assert True\n",
    "docs/README.md": ("# The documents\n\nThere are **4 markdown documents** here, "
                       "about **1 MB**.\n"),
    "docs/JARVIS-API.md": "# The API\n",
    "docs/CLAIMS.tsv": ("C001\tThe thing exists\tfile:backend/jarvis_thing.py\tbuilt\t"
                        "docs/JARVIS-API.md\n"),
    "docs/defect-register.tsv": ("DEF-001\tunclaimed\t2026-11-10\topen\t"
                                 "backend/jarvis_thing.py\tevidence\tcheckout\n"),
    "docs/DEFECT-REGISTER.md": "# The defect register\n\n- DEF-001 (open)\n",
    "docs/DECISIONS.md": ("# Decisions\n\n## 2026-11-09\n\n- An older decision.\n\n"
                          "## Decisions written as `decisions.d/` fragments, folded in "
                          "here in date order\n"),
    "changelog.d/README.md": "# fragments\n",
    "decisions.d/README.md": "# fragments\n",
}
for _script in CHECKER_SCRIPTS:
    BASE_TREE[_script] = "# a checker in the fixture; never run by this suite\n"


def _repo() -> Path:
    box = Path(tempfile.mkdtemp(prefix="jarvis-record-repo-"))
    if _git(box, "init", "-q", "-b", "main").returncode != 0:
        _git(box, "init", "-q")
    _git(box, "config", "user.email", "suite@example.invalid")
    _git(box, "config", "user.name", "suite")
    _git(box, "config", "core.autocrlf", "false")
    _git(box, "config", "commit.gpgsign", "false")
    for rel, text in BASE_TREE.items():
        _write(box, rel, text)
    _commit(box, "the base")
    _git(box, "checkout", "-q", "-b", "feat/records")
    return box


def _well_formed(box: Path) -> None:
    """Every record obligation satisfied, on the feat/records branch."""
    _write(box, "backend/jarvis_thing.py", "VALUE = 1\nVALUE = 2\n")
    _write(box, "jarvis-backend/jarvis_thing.py", "VALUE = 1\nVALUE = 2\n")
    _write(box, "docs/NEW-DOC.md", "# a new document\n")
    # docs/ holds README.md, JARVIS-API.md, DEFECT-REGISTER.md, DECISIONS.md
    # and the new document, so the page states 5 and the size is left alone.
    _write(box, "docs/README.md", ("# The documents\n\nThere are **5 markdown "
                                   "documents** here, about **1 MB**.\n"))
    _write(box, "changelog.d/2026-11-10-a-change.md",
           "- **A change:** one sentence about what changed.\n")
    _write(box, "decisions.d/2026-11-10-a-decision.md",
           "- **2026-11-10 \u2014 A decision:** one sentence about why.\n")
    _commit(box, "a well-formed change")


class FakeCheckers:
    """The process seam: real git, faked checkers.

    `routes` maps a substring of the script's name to a `Ran`; anything else
    passes. The git commands are NOT faked - the change set, the docs count and
    the pre-change record are all measured from the real temporary repository,
    because that is the half this suite is testing.
    """

    def __init__(self, routes=None, default=None):
        self.routes = dict(routes or {})
        self.default = default
        self.calls = []

    def __call__(self, argv, cwd, timeout):
        argv = tuple(str(a) for a in argv)
        self.calls.append(argv)
        if argv and Path(argv[0]).name.lower().startswith("git"):
            return R._default_run(argv, cwd, timeout)
        for needle, result in self.routes.items():
            if needle in " ".join(argv):
                return result(argv, cwd) if callable(result) else result
        if self.default is not None:
            return self.default(argv, cwd) if callable(self.default) else self.default
        return R.Ran(argv, started=True, code=0, out="ok\n")


def _pass(argv, cwd):
    return R.Ran(argv, started=True, code=0, out="ok\n")


def _fail(argv, cwd):
    return R.Ran(argv, started=True, code=1,
                 out="FAILED: the thing is not right\n  at line 12\n")


def _cannot_start(argv, cwd):
    return R.Ran(argv, started=False, detail="it could not be started (FileNotFoundError)")


def _times_out(argv, cwd):
    return R.Ran(argv, started=True, timed_out=True,
                 detail="it did not finish within 120 seconds")


def _skipped(argv, cwd):
    return R.Ran(argv, started=True, code=0,
                 out="SKIPPED  this checker needs the owner's PC\n")


def _run(box: Path, checker=None, **args):
    return R.record_check({"path": str(box), "base": "main", **args},
                          run=checker or FakeCheckers())


def _obligation(result: dict, oid: str) -> dict:
    """The obligation with this id, read out of the rendered answer's own words."""
    text = str(result.get("text") or "")
    for line in text.splitlines():
        flat = " ".join(line.split())
        for status in ("MISSING", "FAIL", "PRESENT", "INFO"):
            if flat.startswith(f"{status} {oid}:"):
                return {"status": status, "line": flat}
    return {}


# --------------------------------------------------------------------------
#   1. READY is reachable, and measured
# --------------------------------------------------------------------------


def t_ready_on_a_well_formed_change():
    if GIT is None:
        return skip("the record check needs git on PATH")
    box = _repo()
    _well_formed(box)
    checker = FakeCheckers()
    out = _run(box, checker)
    text = str(out.get("text") or "")
    head = _git(box, "rev-parse", "HEAD").stdout.strip()
    check("the record check is built", bool(out.get("ok")), out.get("error"))
    check("a well-formed change is READY", out.get("verdict") == "READY",
          (out.get("verdict"), [o for o in text.splitlines() if "MISSING" in o
                                or "FAIL" in o][:5]))
    check("... and the answer says READY, and says it is local, not CI",
          "VERDICT: READY" in text and "not CI" in text, text[-400:])
    check("no obligation is missing or wrong",
          (out.get("measured") or {}).get("obligations", {}).get("MISSING") == 0
          and (out.get("measured") or {}).get("obligations", {}).get("FAIL") == 0,
          (out.get("measured") or {}).get("obligations"))
    check("it names the tree and the head commit it measured",
          str(box).replace("\\", "/") in text.replace("\\", "/") and head[:9] in text,
          text[:300])
    check("the checkers it did not need are named, and are not failures",
          "not needed for this change" in text and "claims" in text, text)
    check("every checker it selected passed",
          (out.get("measured") or {}).get("checkers", {}).get("PASS", 0) >= 5,
          (out.get("measured") or {}).get("checkers"))
    check("a checker is chosen because the change selects it, not at random",
          any("roll_changelog" in " ".join(c) for c in checker.calls)
          and any("check_stale_twins" in " ".join(c) for c in checker.calls),
          [c[2] for c in checker.calls if len(c) > 2])
    check("a checker that was not selected was never run",
          not any("check_claims.py" in " ".join(c) for c in checker.calls),
          [c[2] for c in checker.calls if len(c) > 2])


def t_a_well_formed_change_also_needs_the_fragment_shapes():
    if GIT is None:
        return skip("the record check needs git on PATH")
    box = _repo()
    _well_formed(box)
    # The changelog fragment loses its bold title; the decision keeps its own.
    _write(box, "changelog.d/2026-11-10-a-change.md", "- A change, no title.\n")
    _commit(box, "the fragment loses its title")
    out = _run(box)
    got = _obligation(out, "changelog")
    check("a changelog bullet without a bold title is FAIL",
          got.get("status") == "FAIL" and "bold title" in got.get("line", ""), got)
    check("... and the verdict is NEEDS-RECORDS",
          out.get("verdict") == "NEEDS-RECORDS", out.get("verdict"))


# --------------------------------------------------------------------------
#   2. every obligation is MISSING/FAIL on its own fixture
# --------------------------------------------------------------------------


def _record_case(mutate, oid: str, want_status: str, *, needle: str = "") -> None:
    """Build a well-formed change, break ONE thing, and judge the obligation."""
    box = _repo()
    _well_formed(box)
    mutate(box)
    out = _run(box)
    got = _obligation(out, oid)
    check(f"{oid}: {want_status} on its fixture",
          got.get("status") == want_status,
          (got, [line for line in str(out.get("text")).splitlines()
                 if oid in line][:3]))
    if needle:
        check(f"{oid}: ... and the sentence names the thing to fix",
              needle in got.get("line", ""), got)
    check(f"{oid}: ... and the verdict is NEEDS-RECORDS",
          out.get("verdict") == "NEEDS-RECORDS",
          (out.get("verdict"), out.get("measured", {}).get("checkers")))


def t_each_obligation_is_missing_on_its_own_fixture():
    if GIT is None:
        return skip("the record check needs git on PATH")

    def no_fragment(box):
        (box / "changelog.d" / "2026-11-10-a-change.md").unlink()
        _commit(box, "the fragment is gone")

    _record_case(no_fragment, "changelog", "MISSING",
                 needle="ONE fragment per pull request")

    def edited_changelog(box):
        _write(box, "CHANGELOG.md", "# Changelog\n\n- **A change:** done.\n")
        _commit(box, "the changelog is edited")

    _record_case(edited_changelog, "changelog", "FAIL", needle="never edits")

    def two_fragments(box):
        _write(box, "changelog.d/2026-11-10-another-change.md",
               "- **Another change:** a second one.\n")
        _commit(box, "two fragments")

    _record_case(two_fragments, "changelog", "FAIL", needle="ONE per pull request")

    def stale_twin(box):
        _write(box, "backend/jarvis_thing.py", "VALUE = 1\nVALUE = 3\n")
        _commit(box, "only one half of the twin")

    _record_case(stale_twin, "backend-twin", "MISSING",
                 needle="jarvis-backend/jarvis_thing.py")

    def no_decision(box):
        (box / "decisions.d" / "2026-11-10-a-decision.md").unlink()
        _commit(box, "the decision is gone")

    _record_case(no_decision, "decision", "MISSING",
                 needle="ONE decisions.d/")

    def wrong_date(box):
        _write(box, "decisions.d/2026-11-10-a-decision.md",
               "- **2026-11-09 \u2014 A decision:** the date disagrees.\n")
        _commit(box, "the date disagrees with the name")

    _record_case(wrong_date, "decision", "FAIL", needle="they have to agree")

    def no_bold(box):
        _write(box, "decisions.d/2026-11-10-a-decision.md",
               "- 2026-11-10 A decision with no bold title.\n")
        _commit(box, "the decision has no shape")

    _record_case(no_bold, "decision", "FAIL", needle="the bullet must be")

    def records_rewrite(box):
        # A decision written as a date fragment AND the record rewritten: the
        # append rule is still checked, and a rewrite is FAIL.
        _write(box, "docs/DECISIONS.md",
               "# Decisions\n\n## 2026-11-01\n\n- Rewritten history.\n")
        _commit(box, "the record is rewritten")

    _record_case(records_rewrite, "decision", "FAIL", needle="pure append")

    def count_not_bumped(box):
        # Put the page back exactly as it was, so it is NOT in the change set,
        # then add a document: the count was never bumped for it.
        _write(box, "docs/README.md", BASE_TREE["docs/README.md"])
        _write(box, "docs/NEW-OTHER.md", "# another document\n")
        _commit(box, "a new document with the page untouched")

    _record_case(count_not_bumped, "docs-count", "MISSING",
                 needle="was not changed")

    def bad_claim(box):
        _write(box, "docs/CLAIMS.tsv",
               "C001\tThe thing exists\tfile:backend/jarvis_thing.py\tbuilt\t"
               "docs/JARVIS-API.md\n"
               "C002\tA new claim\tbecause I said so\tbuilt\tdocs/JARVIS-API.md\n")
        _commit(box, "a claims row with no check kind")

    _record_case(bad_claim, "claims", "FAIL", needle="must begin with one of")

    def bad_claim_state(box):
        _write(box, "docs/CLAIMS.tsv",
               "C001\tThe thing exists\tfile:backend/jarvis_thing.py\tbuilt\t"
               "docs/JARVIS-API.md\n"
               "C002\tA new claim\tfile:x.py\tprobably\tdocs/JARVIS-API.md\n")
        _commit(box, "a claims row with an invented state")

    _record_case(bad_claim_state, "claims", "FAIL", needle="is not one of")

    def bad_defect(box):
        _write(box, "docs/defect-register.tsv",
               "DEF-001\tunclaimed\t2026-11-10\topen\tbackend/jarvis_thing.py\t"
               "evidence\tcheckout\n"
               "DEF-002\tunclaimed\t2026-11-10\tmaybe\tbackend/a.py\tevidence\t"
               "checkout\n")
        _commit(box, "a defect row with an invented status")

    _record_case(bad_defect, "defect-register", "FAIL",
                 needle="is not open or closed")


def t_a_tail_append_to_the_record_is_a_present_decision():
    if GIT is None:
        return skip("the record check needs git on PATH")
    box = _repo()
    _well_formed(box)
    # The decision is recorded BOTH ways in the well-formed fixture; take the
    # fragment away and record it as a pure append at the end of the record.
    (box / "decisions.d" / "2026-11-10-a-decision.md").unlink()
    with (box / "docs" / "DECISIONS.md").open("a", encoding="utf-8", newline="") as f:
        f.write("\n- **2026-11-10 \u2014 A tail append:** recorded at the end.\n")
    _commit(box, "the decision is a tail append")
    out = _run(box)
    got = _obligation(out, "decision")
    check("the decision is recorded as a tail append",
          got.get("status") == "PRESENT", got)
    check("... and the obligation says which form it found",
          "tail append" in got.get("line", ""), got)
    check("... and the change is READY", out.get("verdict") == "READY",
          (out.get("verdict"), got))


# --------------------------------------------------------------------------
#   3. a checker that cannot run is NOT-RUN, never PASS
# --------------------------------------------------------------------------


def t_a_checker_that_cannot_run_is_not_run_never_pass():
    if GIT is None:
        return skip("the record check needs git on PATH")
    box = _repo()
    _well_formed(box)

    out = _run(box, FakeCheckers({"roll_changelog": _cannot_start}))
    text = str(out.get("text") or "")
    check("a checker that cannot start is NOT-RUN",
          "NOT-RUN changelog" in text and "could not be started" in text, text[-1200:])
    check("... and the verdict is INCOMPLETE, never READY",
          out.get("verdict") == "INCOMPLETE", out.get("verdict"))
    check("... and the answer never says READY", "VERDICT: READY" not in text, text[-400:])

    out = _run(box, FakeCheckers({"roll_changelog": _times_out}))
    check("a checker that runs out of time is TIMEOUT",
          "TIMEOUT changelog" in str(out.get("text")), out.get("text")[-1200:])
    check("... and the verdict is CHECKER-FAILED",
          out.get("verdict") == "CHECKER-FAILED", out.get("verdict"))

    out = _run(box, FakeCheckers({"roll_changelog": _fail}))
    text = str(out.get("text") or "")
    check("a checker that exits non-zero is FAIL", "FAIL    changelog" in text, text[-1500:])
    check("... and its output is shown, bounded",
          "the thing is not right" in text, text[-1500:])
    check("... and the verdict is CHECKER-FAILED",
          out.get("verdict") == "CHECKER-FAILED", out.get("verdict"))

    out = _run(box, FakeCheckers({"roll_changelog": _skipped}))
    text = str(out.get("text") or "")
    check("a checker whose own output says SKIPPED is NOT-RUN",
          "NOT-RUN changelog" in text and "skipped" in text, text[-1500:])
    check("... and the verdict is INCOMPLETE, never READY",
          out.get("verdict") == "INCOMPLETE", out.get("verdict"))


def t_a_checker_whose_script_is_not_in_the_tree_is_not_run():
    if GIT is None:
        return skip("the record check needs git on PATH")
    box = _repo()
    _well_formed(box)
    (box / "tools" / "roll_changelog.py").unlink()
    _commit(box, "the checker script is gone")
    out = _run(box)
    text = str(out.get("text") or "")
    check("a missing checker script is reported NOT-RUN, with the reason",
          "NOT-RUN changelog" in text and "is not in this tree" in text,
          text[-1500:])
    check("... and the change is not READY",
          out.get("verdict") != "READY", out.get("verdict"))


def t_the_checkers_are_the_twelve_fixed_commands():
    ids = [c["id"] for c in R.CHECKERS]
    check("there are twelve checkers, and they are the plan's own list",
          len(R.CHECKERS) == 12, ids)
    check("every checker's script is one of the twelve allow-listed paths",
          sorted(c["script"] for c in R.CHECKERS) == sorted(CHECKER_SCRIPTS),
          sorted(c["script"] for c in R.CHECKERS))
    check("every checker's fixed arguments are only --check or nothing",
          all(tuple(c["args"]) in ((), ("--check",)) for c in R.CHECKERS),
          [(c["id"], c["args"]) for c in R.CHECKERS])
    check("every checker is bounded by a timeout",
          all(20.0 <= float(c["timeout"]) <= 600.0 for c in R.CHECKERS),
          [(c["id"], c["timeout"]) for c in R.CHECKERS])
    check("every checker is in this repository's own tools/ or backend/",
          all(c["script"].startswith(("tools/", "backend/")) for c in R.CHECKERS),
          [c["script"] for c in R.CHECKERS])
    check("the slowest one is the claims checker, and it says why",
          max(R.CHECKERS, key=lambda c: c["timeout"])["id"] == "claims"
          and "re-runs" in max(R.CHECKERS, key=lambda c: c["timeout"])["why"],
          [c["id"] for c in R.CHECKERS])


def t_a_callers_words_cannot_become_a_checker_command():
    tree = ast.parse((HERE / "jarvis_review.py").read_text(encoding="utf-8"))
    # The function that builds and runs a checker's argv must not receive the
    # caller's argument dict: `args` is not in scope where a command is built.
    runner = next((node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "_run_checkers"), None)
    check("the checker runner exists", runner is not None)
    if runner is not None:
        names = {a.arg for a in runner.args.args + runner.args.kwonlyargs}
        check("the checker runner never receives the caller's arguments",
              "args" not in names, sorted(names))
        checks = [n for n in ast.walk(runner)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id.startswith("_")]
        check("... and it only calls this module's own helpers",
              all(n.func.id in {"_checker_ran"} for n in checks),
              [n.func.id for n in checks])
    # No checker command may be built from a string format of anything.
    literals = [n for c in R.CHECKERS for n in (c["args"], c["script"], c["id"])]
    check("every checker's command parts are plain strings",
          all(isinstance(part, str) for group in literals
              for part in (group if isinstance(group, tuple) else (group,))),
          literals)


# --------------------------------------------------------------------------
#   4. read-only: no write, no network
# --------------------------------------------------------------------------


def t_the_module_can_reach_no_network():
    tree = ast.parse((HERE / "jarvis_review.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    network = imported & {"socket", "urllib", "http", "requests", "ssl", "ftplib",
                          "smtplib", "aiohttp", "websocket", "asyncio", "telnetlib"}
    check("the record check imports no network library", not network, sorted(network))


def t_a_real_run_writes_nothing():
    if GIT is None:
        return skip("the no-write proof needs git on PATH")
    box = _repo()
    _well_formed(box)
    # An honest real run: the fixture's checker files are stubs, so every one of
    # them either passes trivially or is impossible here. What matters is that
    # NOTHING on disk changes and no log is written.
    for rel in CHECKER_SCRIPTS:
        (box / rel).unlink()
    _commit(box, "no checker scripts at all")
    before = {str(p.relative_to(box)): (p.stat().st_size, p.stat().st_mtime_ns)
              for p in box.rglob("*") if p.is_file()}
    with NoSocket():
        out = R.record_check({"path": str(box), "base": "main"})
    after = {str(p.relative_to(box)): (p.stat().st_size, p.stat().st_mtime_ns)
             for p in box.rglob("*") if p.is_file()}
    check("the real run answered", bool(out.get("ok")), out.get("error"))
    check("no file was created", set(after) == set(before),
          sorted(set(after) ^ set(before)))
    check("no file's size or mtime changed", after == before,
          [(k, before.get(k), after.get(k)) for k in after
           if before.get(k) != after.get(k)])
    check("... and it did not claim a checker ran when none could",
          out.get("verdict") != "READY", out.get("verdict"))
    check("... and it says the checkers could not run, by name",
          "is not in this tree" in str(out.get("text")),
          str(out.get("text"))[-1200:])


# --------------------------------------------------------------------------
#   5. the shipped words, the bounds, and the two rows' rules
# --------------------------------------------------------------------------


def t_the_answer_is_bounded():
    if GIT is None:
        return skip("the bound check needs git on PATH")
    box = _repo()
    _well_formed(box)
    out = _run(box)
    check("the default answer is at most 7000 characters",
          len(str(out.get("text") or "")) <= R.RECORD_MAX_TEXT,
          len(str(out.get("text") or "")))
    short = _run(box, max_chars=400)
    text = str(short.get("text") or "")
    check("a short answer is at most the asked size", len(text) <= 400, len(text))
    check("... and it says it was cut", "cut here" in text, text[-160:])


def t_the_claims_and_defect_rows_are_judged_by_shape():
    ok_claim = ["C001", "A claim", "test:backend/test_x.py", "built", "docs/x.md"]
    check("a well-shaped claims row has no problem", not R._claim_row_problems(ok_claim, 3))
    check("a claims row with four columns is refused",
          any("5" in p for p in R._claim_row_problems(ok_claim[:4], 3)),
          R._claim_row_problems(ok_claim[:4], 3))
    check("a claims row with an invented state is refused",
          any("state" in p for p in
              R._claim_row_problems(ok_claim[:3] + ["done"] + ok_claim[4:], 3)))
    check("a built row whose check is a bare sentence is refused",
          any("must begin" in p for p in R._claim_row_problems(
              ok_claim[:2] + ["because"] + ok_claim[3:], 3)))
    check("an unverifiable row must give a reason, not a check",
          any("reason" in p for p in R._claim_row_problems(
              ok_claim[:2] + ["file:x.py"] + ["unverifiable"] + ok_claim[4:], 3)))
    check("an unverifiable row with a reason is fine",
          not R._claim_row_problems(
              ok_claim[:2] + ["the owner has not measured it"] + ["unverifiable"]
              + ok_claim[4:], 3))

    ok_defect = ["DEF-001", "owner", "2026-11-10", "open", "backend/a.py",
                 "evidence", "checkout"]
    check("a well-shaped defect row has no problem",
          not R._defect_row_problems(ok_defect, 3))
    check("a defect row with six columns is refused",
          any("7" in p for p in R._defect_row_problems(ok_defect[:6], 3)))
    check("a defect row with an invented status is refused",
          any("open or closed" in p for p in R._defect_row_problems(
              ok_defect[:3] + ["later"] + ok_defect[4:], 3)))


def t_each_verdict_has_one_plain_sentence():
    obligations = [
        {"id": "changelog", "status": "MISSING", "detail": "", "next": ""},
        {"id": "decision", "status": "PRESENT", "detail": "", "next": ""},
    ]
    passed = [{"id": "changelog", "status": "PASS"}]
    not_run = [{"id": "claims", "status": "NOT-RUN"}]
    words = R._verdict_words("READY", obligations, passed)
    check("READY says it is local, not CI", "local check" in words and "CI" in words,
          words)
    words = R._verdict_words("NEEDS-RECORDS", obligations, passed)
    check("NEEDS-RECORDS names what is missing", "changelog" in words, words)
    words = R._verdict_words(
        "CHECKER-FAILED", obligations[:1], [{"id": "claims", "status": "FAIL"}])
    check("CHECKER-FAILED names the checker", "claims:FAIL" in words, words)
    check("... and says a NOT-RUN is never a pass", "never a pass" in words, words)
    words = R._verdict_words("INCOMPLETE", obligations[1:], not_run)
    check("INCOMPLETE names what did not run", "claims" in words, words)
    check("... and says a NOT-RUN is never a pass", "never a pass" in words, words)


def t_the_record_words_are_true_of_the_code():
    words = R.record_words()
    for needle in ("changelog.d", "jarvis-backend", "decision", "claims",
                   "defect", "READY", "NEEDS-RECORDS", "CHECKER-FAILED",
                   "INCOMPLETE"):
        check(f"the tool's own words name {needle}", needle in words, words)


def t_a_bad_folder_is_one_plain_sentence():
    out = R.record_check({"path": str(_TMP / "no-such-folder")})
    check("a folder that is not there is said plainly",
          out.get("ok") is False and "not on this PC" in str(out.get("error")),
          out.get("error"))
    out = R.record_check({})
    check("no folder at all says how to give one",
          out.get("ok") is False and R.ENV_REPO in str(out.get("error")),
          out.get("error"))


if __name__ == "__main__":
    print(f"  suite {Path(__file__).name}")
    print(f"  file  {HERE / 'jarvis_review.py'}")
    if GIT is None:
        print("  note  git is not on PATH; the tree-backed checks will skip")
    with NoSocket():
        for fn in (t_ready_on_a_well_formed_change,
                   t_a_well_formed_change_also_needs_the_fragment_shapes,
                   t_each_obligation_is_missing_on_its_own_fixture,
                   t_a_tail_append_to_the_record_is_a_present_decision,
                   t_a_checker_that_cannot_run_is_not_run_never_pass,
                   t_a_checker_whose_script_is_not_in_the_tree_is_not_run,
                   t_the_checkers_are_the_twelve_fixed_commands,
                   t_a_callers_words_cannot_become_a_checker_command,
                   t_the_module_can_reach_no_network,
                   t_a_real_run_writes_nothing,
                   t_the_answer_is_bounded,
                   t_the_claims_and_defect_rows_are_judged_by_shape,
                   t_each_verdict_has_one_plain_sentence,
                   t_the_record_words_are_true_of_the_code,
                   t_a_bad_folder_is_one_plain_sentence):
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
