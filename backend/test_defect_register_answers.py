"""test_defect_register_answers.py - the defect register is answered from its file.

    python -B backend/test_defect_register_answers.py

WHY THIS SUITE EXISTS (the live battery of 2026-11-18). Asked **"How many open
defects are in the register?"**, the live Jarvis answered:

    "I don't know about your defect register without seeing it. Do you have a
     file or database I can search? If so, tell me its name and where it's
     stored."

Every word of that is a false denial. The register is `docs/defect-register.tsv`
in this repository, `tools/check_defect_register.py` is its checker, and the
machine the question was asked on holds both. The measured cause was not a
matcher gap: NO chat lane read the register at all, so the question fell through
the whole fast path to the model, and the model has no tool that can count a
file on this PC. The same battery produced a second false denial ("I don't have
direct access to your GitHub repositories"), which is another lane's half; this
suite is the local-facts half.

WHAT THE FIX IS. `jarvis_quick` gained one deterministic lane (`defect_register`,
the block beside `_recent_changes`) that answers three families from
`docs/defect-register.tsv` on this PC, naming the file and the date it was read:

  * the COUNT - "how many open defects are in the register", "... are there";
  * the OPEN LIST - "what is open", "what defects are still open";
  * ONE ROW by id - "what is DEF-089", "is DEF-002 closed".

The number is the CHECKER's number: the lane imports
`tools/check_defect_register.py` BY PATH and calls its own `parse_tsv()`, so
chat cannot disagree with `py -3 tools/check_defect_register.py`. No checker,
no number.

WHAT THIS SUITE CHECKS, and every check uses a CONTROLLED FIXTURE - never the
owner's live register, except the one test that reads this repository's own
register and compares the answer with an independently parsed count (it never
hard-codes the number, because the register changes):

  1. each count sentence answers from the fixture, with the fixture's numbers,
     the file's path and the read date in the reply;
  2. a different fixture gives a different number (so the number is read, not
     remembered or hard-coded);
  3. "what is open" lists exactly the fixture's open ids, and when there are
     more than the read-out limit the COUNT is said and the tail is admitted,
     never silently dropped;
  4. one id answers with that row's own status, owner, files and evidence;
     an id the register does not have is refused in words, never invented;
  5. a MISSING register is a plain refusal - no number, and never the measured
     "I don't know about your defect register";
  6. a MALFORMED register (missing header, wrong column count, an invented
     status, a duplicate id) is refused in the checker's own words;
  7. a register with NO CHECKER beside it is refused rather than counted by a
     second parser written in the app;
  8. the answers are READ-ONLY: the intent is in READ_ONLY_INTENTS, the answer
     makes nothing, raises no card, and the fixture tree is unchanged;
  9. the decoy questions ("how many models are installed", "what windows are
     open", "how many defects are there in my code") keep their own paths;
 10. `jarvis_quick.py` and its published `jarvis-backend/` twin are identical;
 11. **THE MEASURED FIELD FAILURE OF 2026-11-19** - the HUD's own call,
     `jarvis_quick.answer_turn`, answers the owner's bare sentence (a request
     with NO `provenance` tag, the shape a script posts) from the register,
     with the fixture's count and the file's name; the tagged owner's words
     still answer the same; and the control shows the widening is READ-ONLY
     and does not swallow everything - an unrelated question, an ACTION and an
     app-sent (system-message) or pasted body all still return None and reach
     the model.

No model runs, no network, no owner file is touched: every fixture is under the
suite's own temporary folder and the register path is handed in through
`JARVIS_DEFECT_REGISTER`, exactly as the installed backend would be pointed at
a checkout it cannot otherwise see.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The live install's copy is older than this branch until the deploy pass, and
# `_where` puts BACKEND on sys.path FIRST - so with JARVIS_BACKEND set this
# suite would drive the installed copy instead of the copy it tests. This suite
# is about the repository's own code, so the ambient install is ignored exactly
# as `backend/test_chat_wrong_answers.py` ignores it. CI never sets it.
os.environ.pop("JARVIS_BACKEND", None)
# The two ways the lane can be pointed at a checkout. Neither may leak in from
# the machine this runs on: every check below says which one it means.
os.environ.pop("JARVIS_DEFECT_REGISTER", None)
os.environ.pop("JARVIS_REVIEW_REPO", None)

from _where import REPO  # noqa: E402

_TMP = Path(tempfile.gettempdir()) / ("jarvis-defect-register-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
for _name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME"):
    os.environ[_name] = str(_TMP / _name.lower())

import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []

#: The date every answer must name, and the instant it is read from. Fixed so
#: the read-date half is checked exactly; `run()`/`answer()` already take `now`
#: for the same reason every other timed lane does.
NOW = datetime(2026, 11, 18, 12, 0).timestamp()
DATE = "2026-11-18"

#: The measured false denial, in the only normalised form it can come back as.
FALSE_DENIAL = "i don't know about your defect register"

#: A count said as a number: "2 open and 1 closed". A REFUSAL must never match
#: it. Deliberately narrow: the checker's own problem text can quote a register
#: row, which contains the word "open" after a date ("... 2026-11-10 open ...").
COUNT_CLAIM = re.compile(r"\b\d+\s+open\s+and\s+\d+\s+closed\b")


def check(label: str, ok: bool, detail="") -> None:
    if ok:
        PASSED.append(label)
        print("  ok    " + label)
    else:
        FAILED.append(label)
        print("  FAIL  " + label)
        if detail:
            print("          " + str(detail)[:400])


class Sched:
    """A made-up scheduler: an answer that raises a card fails the suite."""

    def __init__(self):
        self.commands = []

    def listed(self):
        return []

    def mark_command(self, text):
        self.commands.append(text)

    def act(self, *args, **kwargs):
        raise AssertionError("a card was raised by a read-only answer")


def _answer(sentence: str):
    """The real fast path: match, then the shipped answer. (Result, Intent)."""
    intent = Q.match(sentence, now=NOW)
    if intent is None:
        return None, None
    return Q.answer(sentence, sched=Sched(), now=NOW), intent


def _reply(sentence: str) -> str:
    res, intent = _answer(sentence)
    assert intent is not None, f"{sentence!r} fell through to the model"
    assert res is not None, f"{sentence!r} matched but produced no answer"
    return str(res.reply)


# --------------------------------------------------------------------------
#   Controlled fixture registers - never the owner's live file
# --------------------------------------------------------------------------

HEADER = "id\towner\tclaimed_at\tstatus\tfiles\tevidence\tcheckout\n"


def _row(rid, status, *, owner="tester", claimed="2026-11-10",
         files="backend/a.py", evidence="evidence", checkout="wt"):
    return "\t".join((rid, owner, claimed, status, files, evidence, checkout)) + "\n"


def _checkout(register_text, *, with_tool=True, with_marker=True, with_docs=True):
    """A fake checkout: docs/defect-register.tsv (+ its checker, + the marker)."""
    root = Path(tempfile.mkdtemp(prefix="jarvis-register-tree-", dir=str(_TMP)))
    if with_marker:
        (root / "scripts").mkdir()
        (root / "scripts" / "apply-patches.ps1").write_text("", encoding="utf-8")
    if with_docs:
        (root / "docs").mkdir()
    if with_tool:
        (root / "tools").mkdir()
        shutil.copyfile(REPO / "tools" / "check_defect_register.py",
                        root / "tools" / "check_defect_register.py")
    register = root / "docs" / "defect-register.tsv"
    if register_text is not None:
        register.write_text(register_text, encoding="utf-8")
    return root, register


@contextmanager
def _point_at(path):
    """Set JARVIS_DEFECT_REGISTER for one check, then put the machine back."""
    old = os.environ.get("JARVIS_DEFECT_REGISTER")
    os.environ["JARVIS_DEFECT_REGISTER"] = str(path)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("JARVIS_DEFECT_REGISTER", None)
        else:
            os.environ["JARVIS_DEFECT_REGISTER"] = old


#: Three rows, two of them open - the fixture the behaviour checks use.
GOOD = (HEADER
        + _row("DEF-001", "open", evidence="alpha evidence")
        + _row("DEF-002", "open", owner="unclaimed", claimed="",
               files="backend/b.py", evidence="beta evidence")
        + _row("DEF-003", "closed", owner="other", claimed="2026-11-11",
               files="backend/c.py;backend/d.py", evidence="gamma evidence"))

COUNT_SENTENCES = (
    "How many open defects are in the register?",
    "how many open defects are in the register",
    "how many defects are there?",
    "how many open defects are there",
    "how many defects are in the defect register?",
    "how many open defects does the register have?",
    "how many defects are open right now?",
    "what's the number of open defects?",
    "how many defects are recorded?",
    "what is in the defect register?",
)

OPEN_SENTENCES = (
    "what is open?",
    "what's open?",
    "what is still open?",
    "what is open in the defect register?",
    "what defects are open?",
    "which defects are still open?",
    "what are the open defects?",
    "show me the open defects",
    "list the open defects",
    "what open defects are there?",
)


def _counts(reply: str):
    """(open, closed) from "N open and M closed", or None."""
    found = re.search(r"(\d+)\s+open\s+and\s+(\d+)\s+closed", reply)
    return (int(found.group(1)), int(found.group(2))) if found else None


# --------------------------------------------------------------------------
#   1. the count comes from the fixture, with the path and the read date
# --------------------------------------------------------------------------
def t_the_count_comes_from_the_fixture():
    root, register = _checkout(GOOD)
    with _point_at(register):
        for sentence in COUNT_SENTENCES:
            res, intent = _answer(sentence)
            check(f"{sentence[:52]!r} is the defect register lane",
                  intent is not None and intent.name == "defect_register"
                  and intent.f.get("ask") == "count", repr(intent))
            if res is None:
                continue
            said = str(res.reply)
            check(f"... it says the fixture's 2 open and 1 closed: {sentence[:36]!r}",
                  _counts(said) == (2, 1), said[:200])
            check(f"... it names the file it read: {sentence[:36]!r}",
                  "docs/defect-register.tsv" in said, said[:200])
            check(f"... it names the date it read it: {sentence[:36]!r}",
                  DATE in said, said[:200])
            check(f"... and never the measured denial: {sentence[:36]!r}",
                  FALSE_DENIAL not in said.lower(), said[:200])
    assert root.is_dir()


# --------------------------------------------------------------------------
#   2. a different register gives a different number - it is read, not known
# --------------------------------------------------------------------------
def t_a_different_register_gives_a_different_number():
    # Nothing open: the count sentence says so plainly.
    closed_only = HEADER + _row("DEF-007", "closed") + _row("DEF-008", "closed")
    root, register = _checkout(closed_only)
    with _point_at(register):
        said = _reply("How many open defects are in the register?")
    check("a register with nothing open says so, not an invented number",
          "Nothing is open" in said and "2 rows" in said, said[:220])
    check("... and names the file and date it read",
          "docs/defect-register.tsv" in said and DATE in said, said[:220])

    # Three open of four: the numbers move with the FILE, not with the code.
    three_open = (HEADER + _row("DEF-001", "open") + _row("DEF-002", "open",
                                                          evidence="two")
                  + _row("DEF-003", "open", evidence="three") + _row("DEF-004", "closed"))
    root, register = _checkout(three_open)
    with _point_at(register):
        said = _reply("How many open defects are in the register?")
    check("the same sentence counts a different file differently",
          _counts(said) == (3, 1), said[:220])

    # A header with no rows at all is a real (empty) register, not malformed.
    root, register = _checkout(HEADER)
    with _point_at(register):
        said = _reply("how many defects are there?")
    check("an empty register answers zero rather than refusing",
          "no rows" in said and FALSE_DENIAL not in said.lower(), said[:220])


# --------------------------------------------------------------------------
#   3. "what is open" lists exactly the fixture's open ids
# --------------------------------------------------------------------------
def t_the_open_list_comes_from_the_fixture():
    root, register = _checkout(GOOD)
    with _point_at(register):
        for sentence in OPEN_SENTENCES:
            res, intent = _answer(sentence)
            check(f"{sentence[:52]!r} is the open-list lane",
                  intent is not None and intent.name == "defect_register"
                  and intent.f.get("ask") == "open", repr(intent))
            if res is None:
                continue
            said = str(res.reply)
            check(f"... it lists the fixture's open ids: {sentence[:36]!r}",
                  "DEF-001" in said and "DEF-002" in said and "DEF-003" not in said,
                  said[:260])
            check(f"... with the file, the date and the count: {sentence[:36]!r}",
                  "docs/defect-register.tsv" in said and DATE in said
                  and said.startswith("2 defects are open"), said[:260])

    # More open ids than the read-out limit: the COUNT is still exact, and the
    # shortened list says what it left out - it is never silently truncated.
    many = HEADER + "".join(_row(f"DEF-{n:03d}", "open", evidence="e") for n in range(1, 46))
    root, register = _checkout(many)
    with _point_at(register):
        said = _reply("what is open?")
    check("a long open list says the exact count first",
          said.startswith("45 defects are open"), said[:160])
    check("... and admits the tail it did not read out",
          "and 5 more" in said, said[-200:])
    roots, register = _checkout(HEADER + _row("DEF-001", "closed"))
    with _point_at(register):
        said = _reply("what is open?")
    check("an all-closed register says nothing is open",
          "Nothing is open" in said and "no row on it has status open" in said, said[:220])


# --------------------------------------------------------------------------
#   4. one row by id: its own status, owner, files and evidence - or a refusal
# --------------------------------------------------------------------------
def t_one_defect_by_id_answers_from_its_row():
    root, register = _checkout(GOOD)
    with _point_at(register):
        said = _reply("what is DEF-002?")
        check("an open row says open, unclaimed, its file and its evidence",
              "DEF-002 is open" in said and "It is unclaimed." in said
              and "backend/b.py" in said and "beta evidence" in said, said[:300])
        check("... and names the file and date it read",
              "docs/defect-register.tsv" in said and DATE in said, said[:300])

        said = _reply("what is DEF-003?")
        check("a closed row says closed, its owner and both its files",
              "DEF-003 is closed" in said and "Its owner is other" in said
              and "backend/c.py" in said and "backend/d.py" in said, said[:320])

        said = _reply("is DEF-001 closed?")
        check("the row's OWN status is said, not the status the question guessed",
              "DEF-001 is open" in said, said[:220])

        for sentence in ("what is def-001", "what is DEF 001", "tell me about DEF-001",
                         "what is DEF-001 about?", "what's DEF-001's status?",
                         "show me DEF-001"):
            res, intent = _answer(sentence)
            check(f"{sentence!r} finds the same row",
                  intent is not None and intent.name == "defect_register"
                  and intent.f.get("number") == 1, repr(intent))
            if res is not None:
                check(f"... and answers DEF-001: {sentence!r}",
                      "DEF-001 is open" in str(res.reply), str(res.reply)[:200])

        said = _reply("what is DEF-099?")
        check("an id the register does not have is refused in words",
              "There is no DEF-099" in said and "will not guess" in said, said[:260])
        check("... and no row's evidence is invented for it",
              "Evidence" not in said and "DEF-099 is" not in said, said[:260])


# --------------------------------------------------------------------------
#   5. a MISSING register is a plain refusal - no number, never the old denial
# --------------------------------------------------------------------------
def t_a_missing_register_is_a_plain_refusal():
    root, register = _checkout(GOOD)
    with _point_at(root / "docs" / "not-there.tsv"):
        for sentence in ("How many open defects are in the register?",
                         "how many defects are there?", "what is open?",
                         "what is DEF-001?"):
            said = _reply(sentence)
            check(f"a missing register refuses: {sentence[:44]!r}",
                  "I cannot count the defect register" in said, said[:260])
            check(f"... with no number and no guessed id: {sentence[:30]!r}",
                  not COUNT_CLAIM.search(said) and "DEF-" not in said, said[:260])
            check(f"... and never the measured denial: {sentence[:30]!r}",
                  FALSE_DENIAL not in said.lower()
                  and "do you have a file or database" not in said.lower(), said[:260])

    # The installed-copy shape: this module is not running from a checkout, so
    # there is nowhere named to look. The location function says so, and the
    # sentence for it is a refusal too.
    install = Path(tempfile.mkdtemp(prefix="jarvis-install-", dir=str(_TMP))) / "backend"
    install.mkdir()
    path, named, why = Q._defect_register_location(backend_dir=str(install))
    check("an installed copy with no checkout beside it finds no register",
          path is None and named == "" and why == "no-checkout", (path, named, why))
    words = Q._MISSING_WORDS["no-checkout"]
    check("... and its sentence is a plain refusal",
          "I cannot count the defect register" in words
          and not COUNT_CLAIM.search(words) and FALSE_DENIAL not in words.lower(), words)

    # A checkout that exists but has no register: named, and refused.
    root2, _ = _checkout(None, with_docs=False)
    path, named, why = Q._defect_register_location(
        backend_dir=str(root2 / "backend"))
    check("a checkout with no register is said to have none",
          path is None and why == "checkout-no-register", (path, named, why))

    # And the checkout the register IS beside resolves, named repo-relative.
    root3, register3 = _checkout(GOOD)
    (root3 / "backend").mkdir()
    path, named, why = Q._defect_register_location(backend_dir=str(root3 / "backend"))
    check("a register beside its checkout resolves and is named by its repo path",
          path == register3 and named == "docs/defect-register.tsv" and why == "",
          (path, named, why))


# --------------------------------------------------------------------------
#   6. a MALFORMED register is refused in the checker's own words
# --------------------------------------------------------------------------
MALFORMED = (
    ("a missing header",
     _row("DEF-001", "open"),
     "header must be exactly"),
    ("a row with the wrong column count",
     HEADER + "DEF-001\ttester\topen\tbackend/a.py\n",
     "malformed row"),
    ("an invented status",
     HEADER + _row("DEF-001", "later"),
     "is not one of open or closed"),
    ("a duplicate id",
     HEADER + _row("DEF-001", "open") + _row("DEF-001", "closed"),
     "duplicate id"),
    ("a blank line",
     HEADER + _row("DEF-001", "open") + "\n",
     "blank line"),
)


def t_a_malformed_register_is_refused():
    for label, text, evidence in MALFORMED:
        root, register = _checkout(text)
        with _point_at(register):
            said = _reply("how many open defects are in the register?")
        check(f"a register with {label} is refused",
              "not well formed" in said, said[:320])
        check(f"... in the checker's own words ({evidence!r})",
              evidence in said, said[:320])
        check(f"... with no count claimed, for {label}",
              not COUNT_CLAIM.search(said) and "will not guess" in said, said[:320])
        check(f"... and never the measured denial, for {label}",
              FALSE_DENIAL not in said.lower(), said[:320])


# --------------------------------------------------------------------------
#   7. a register with no checker beside it is refused, not counted here
# --------------------------------------------------------------------------
def t_a_register_without_its_checker_is_refused():
    root, register = _checkout(GOOD, with_tool=False)
    with _point_at(register):
        for sentence in ("how many open defects are there?", "what is open?",
                         "what is DEF-001?"):
            said = _reply(sentence)
            check(f"no checker means no number: {sentence[:44]!r}",
                  "check_defect_register.py" in said and "beside it" in said
                  and "cannot count it" in said, said[:300])
            check(f"... and nothing is counted for it: {sentence[:30]!r}",
                  not COUNT_CLAIM.search(said) and "DEF-" not in said, said[:300])


# --------------------------------------------------------------------------
#   8. the answers are READ-ONLY: nothing made, no card, no file changed
# --------------------------------------------------------------------------
def t_the_answers_are_read_only():
    root, register = _checkout(GOOD)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with _point_at(register):
        for sentence in ("How many open defects are in the register?",
                         "what is open?", "what is DEF-001?",
                         "what is DEF-097?"):
            sched = Sched()
            res = Q.answer(sentence, sched=sched, now=NOW)
            check(f"read-only answer for {sentence[:40]!r}",
                  res is not None and res.made == [] and res.ids == []
                  and res.open_settings is None and res.open_brain is None,
                  repr(res))
            check(f"... and its intent is marked read-only: {sentence[:40]!r}",
                  res is not None and res.intent in Q.READ_ONLY_INTENTS, repr(res.intent))
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    check("the register tree is byte-for-byte unchanged (opened for reading only)",
          before == after, sorted(set(before) ^ set(after)) or "a file changed")
    check("no answer reached a model (the fast path returned an answer at all)",
          Q.match("what is open?") is not None)


# --------------------------------------------------------------------------
#   9. decoy questions keep their own paths; the positive control still answers
# --------------------------------------------------------------------------
def t_other_questions_keep_their_own_path():
    root, register = _checkout(GOOD)
    with _point_at(register):
        check("the positive control: bare 'what is open?' IS this lane",
              Q.match("what is open?") is not None
              and Q.match("what is open?").name == "defect_register")
        # "how many models are installed" already has its own owner.
        got = Q.match("how many models are installed", now=NOW)
        check("an existing count question keeps its own lane",
              got is not None and got.name == "models_list", repr(got))
        for sentence in ("what windows are open",
                         "what is open on my pc",
                         "what apps are open",
                         "how many defects are there in my code",
                         "how many defects can you fix",
                         "what is open source",
                         "what is the register of deeds"):
            got = Q.match(sentence, now=NOW)
            check(f"{sentence!r} is not claimed by this lane",
                  got is None or got.name != "defect_register", repr(got))


# --------------------------------------------------------------------------
#   10. the real register is read, and the answer agrees with the file
# --------------------------------------------------------------------------
def t_the_real_register_agrees_with_its_own_file():
    real = REPO / "docs" / "defect-register.tsv"
    if not real.is_file():
        check("the repository carries docs/defect-register.tsv", False, str(real))
        return
    with _point_at(real):
        said = _reply("How many open defects are in the register?")
    # An INDEPENDENT parse, in the test: the header's own columns, the status
    # column, one row per line. The register changes over time, so no number is
    # hard-coded - only the agreement between the answer and this file.
    lines = real.read_text(encoding="utf-8-sig").splitlines()
    header = [cell.strip() for cell in lines[0].split("\t")]
    rows = [[cell.strip() for cell in line.split("\t")] for line in lines[1:]
            if line.strip() and len(line.split("\t")) == len(header)]
    status_at = header.index("status")
    open_ids = {row[0] for row in rows if row[status_at] == "open"}
    check("the real register parses independently",
          header == ["id", "owner", "claimed_at", "status", "files", "evidence",
                     "checkout"] and bool(rows), (header, len(rows)))
    claimed = _counts(said)
    check("the answer's count is the file's own count, read independently",
          claimed is not None and claimed[0] == len(open_ids)
          and claimed[0] + claimed[1] == len(rows),
          f"answer {claimed} vs file {len(open_ids)} open of {len(rows)}: {said[:200]}")
    check("... and it names the file and the date it read",
          "docs/defect-register.tsv" in said and DATE in said, said[:220])
    check("... and never the measured denial",
          FALSE_DENIAL not in said.lower(), said[:220])


# --------------------------------------------------------------------------
#   11. the two-file rule
# --------------------------------------------------------------------------
def t_the_published_twin_is_byte_identical():
    a = REPO / "backend" / "jarvis_quick.py"
    b = REPO / "jarvis-backend" / "jarvis_quick.py"
    check("jarvis_quick.py has a byte-identical published twin",
          a.is_file() and b.is_file()
          and a.read_bytes().replace(b"\r\n", b"\n")
          == b.read_bytes().replace(b"\r\n", b"\n"),
          f"{a} vs {b}")


# --------------------------------------------------------------------------
#   12. THE HUD'S OWN CHAT PATH (the measured 2026-11-19 failure)
# --------------------------------------------------------------------------
# A client posted the owner's sentence the way a script does:
#
#     {"messages": [{"role": "user", "content": "How many open defects are in
#                    the register?"}]}
#
# - NO `provenance` tag. `jarvis_quick.answer_turn` (the exact function
# `jarvis_hud.py`'s /api/chat handler calls before `jarvis_agent` runs) found
# no owner's-own words, returned None, and the question reached the model. The
# model cannot read `docs/defect-register.tsv` and offered the `check_records`
# tool instead ("I can run a read-only check on your repository's records").
# The lane itself was healthy all along: `Q.match` and `_run_defect_register`
# both answered from the file in one short sentence.
#
# THIS SECTION DRIVES THE HUD'S OWN CALL, not `Q.match` alone - and each
# assertion is a way the fix could silently stop working:
#   * the bare sentence (no tag) IS answered by the register, with the
#     fixture's own count and the file's name and read date;
#   * the owner's own TAGGED words still answer, with the same words;
#   * the control: an unrelated question, an ACTION, a pasted body and a body
#     carrying an app's own `system` message all still return None (the model
#     or a tool gets them), so the widening cannot have swallowed everything.
_MISSING = object()


def _answer_turn(sentence: str, *, provenance=_MISSING, extra=None):
    """One HUD-shaped /api/chat turn, through the function the HUD calls."""
    msg = {"role": "user", "content": sentence}
    if provenance is not _MISSING:
        msg["provenance"] = provenance
    body = {"messages": [msg]}
    if extra:
        body.update(extra)
    return Q.answer_turn(body, sched=Sched(), now=NOW)


def t_the_hud_chat_path_answers_the_bare_sentence():
    root, register = _checkout(GOOD)
    with _point_at(register):
        res = _answer_turn("How many open defects are in the register?")
        check("answer_turn (the HUD's own call) answers the bare sentence",
              res is not None, repr(res))
        said = str(getattr(res, "reply", "") or "")
        check("... through the defect_register lane",
              getattr(res, "intent", None) == "defect_register", repr(getattr(res, "intent", None)))
        check("... with the fixture's own count: 2 open and 1 closed",
              _counts(said) == (2, 1), said[:240])
        check("... naming the file it read",
              "docs/defect-register.tsv" in said, said[:240])
        check("... and the date it read it",
              DATE in said, said[:240])
        check("... and never the measured denial",
              FALSE_DENIAL not in said.lower(), said[:240])
        # The owner's own tagged words are unchanged - the same answer.
        tagged = _answer_turn("How many open defects are in the register?",
                              provenance="typed")
        check("the owner's own tagged words answer the same words",
              tagged is not None and str(tagged.reply) == said, repr(tagged))
        # And the two other sentences the field test measured, same path.
        for sentence in ("How many defects are open?", "what is DEF-001"):
            got = _answer_turn(sentence)
            check(f"the measured sentence {sentence!r} answers from the register",
                  got is not None and got.intent == "defect_register", repr(got))
            check(f"... and names the file for {sentence!r}",
                  "docs/defect-register.tsv" in str(getattr(got, "reply", "")),
                  str(getattr(got, "reply", ""))[:200])


def t_the_untagged_widening_is_read_only_and_does_not_swallow_everything():
    root, register = _checkout(GOOD)
    sentence = "How many open defects are in the register?"
    with _point_at(register):
        # CONTROL 1: an unrelated question is still the model's.
        check("an unrelated untagged question still goes to the model",
              _answer_turn("tell me a joke about cats") is None)
        # CONTROL 2: an ACTION is still the model's - the owner's own words
        # are what unlock an action, and no tag means no answer here.
        check("an untagged ACTION still goes to the model (no card, no timer)",
              _answer_turn("set a timer for 10 minutes") is None)
        # CONTROL 3: the app's own text refuses the whole fast path, as before.
        check("an app-sent system message still refuses the whole fast path",
              Q.answer_turn({"messages": [
                  {"role": "system", "content": "x"},
                  {"role": "user", "content": sentence}]},
                  sched=Sched(), now=NOW) is None)
        # CONTROL 4: a TAG of any kind keeps its existing rule - only a
        # MISSING tag is read as an untagged question.
        check("a pasted body still goes to the model",
              _answer_turn(sentence, provenance="pasted") is None)
        check("a share/clipboard turn riding with the words still goes to the model",
              Q.answer_turn({"messages": [
                  {"role": "user", "content": "x", "provenance": "clipboard"},
                  {"role": "user", "content": sentence}]},
                  sched=Sched(), now=NOW) is None)
        check("a private chat keeps its own stricter rule",
              _answer_turn(sentence, extra={"private": True}) is None)
        # CONTROL 5: the gate is the EXPLICIT record-read list, not
        # READ_ONLY_INTENTS. `chat_tag` is in READ_ONLY_INTENTS (it has nothing
        # for "cancel that" to take back) and its handler FILES the chat - so an
        # untagged "label this chat Work" must not be answered here, and this
        # was a real regression the first draft of the fix caused
        # (backend/test_chat_tags.py caught it).
        check("the gate is a subset of READ_ONLY_INTENTS",
              Q.UNTAGGED_RECORD_READS <= Q.READ_ONLY_INTENTS,
              sorted(Q.UNTAGGED_RECORD_READS - Q.READ_ONLY_INTENTS))
        check("... but it does NOT include the chat-filing answer",
              "chat_tag" in Q.READ_ONLY_INTENTS
              and "chat_tag" not in Q.UNTAGGED_RECORD_READS)
        check("an untagged 'label this chat Work' is not answered here (it files)",
              _answer_turn("label this chat Work") is None)
        check("an untagged client command ('open a chat') is not answered here",
              _answer_turn("open a chat") is None)
        # The gate is a FAMILY of record reads, not a special case for one
        # sentence: a second member answers the same untagged shape...
        got = _answer_turn("what changed in your last update?")
        check("a second record read answers untagged too (the gate is a family)",
              got is not None and got.intent == "recent_changes", repr(got))
        # ...while a deterministic read that is deliberately NOT on the list
        # (it reads machine state rather than this project's record) keeps the
        # old rule: an untagged request goes to the model.
        check("a deterministic read OUTSIDE the gate keeps the old rule",
              _answer_turn("how many models are installed") is None)
        # And the OLD reader itself is untouched: an untagged message is still
        # NOT the owner's own words (test_github_tools_by_chat.py pins this too).
        check("newest_own_words is unchanged: untagged is still not the owner's",
              Q.newest_own_words({"messages": [{"role": "user", "content": sentence}]})
              is None)
        check("... and a tagged one still is",
              Q.newest_own_words({"messages": [
                  {"role": "user", "content": sentence, "provenance": "typed"}]})
              == sentence)


def main():
    print("=" * 74)
    print("jarvis_quick - the defect register answers from its own file")
    print("=" * 74)
    tests = [
        ("count from the fixture", t_the_count_comes_from_the_fixture),
        ("a different register gives a different number",
         t_a_different_register_gives_a_different_number),
        ("the open list from the fixture", t_the_open_list_comes_from_the_fixture),
        ("one id answers from its row", t_one_defect_by_id_answers_from_its_row),
        ("a missing register is a plain refusal",
         t_a_missing_register_is_a_plain_refusal),
        ("a malformed register is refused", t_a_malformed_register_is_refused),
        ("a register without its checker is refused",
         t_a_register_without_its_checker_is_refused),
        ("the answers are read-only", t_the_answers_are_read_only),
        ("other questions keep their own path", t_other_questions_keep_their_own_path),
        ("the real register agrees with its file",
         t_the_real_register_agrees_with_its_own_file),
        ("the HUD's chat path answers the bare sentence",
         t_the_hud_chat_path_answers_the_bare_sentence),
        ("the untagged widening is read-only and narrow",
         t_the_untagged_widening_is_read_only_and_does_not_swallow_everything),
        ("the published twin", t_the_published_twin_is_byte_identical),
    ]
    for name, fn in tests:
        print()
        print("--", name, "-" * max(0, 66 - len(name)))
        try:
            fn()
        except Exception as exc:                        # noqa: BLE001
            FAILED.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 74)
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
