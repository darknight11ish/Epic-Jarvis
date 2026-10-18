"""test_self_improve.py - phases 3 and 4: read-only diagnosis, and drafting only.

    python3 backend/test_self_improve.py

WHAT IT PROVES, AND WHY EACH CHECK CAN FAIL

Phase 3 (design section 4.5) and phase 4 (section 7's Phase-4 row) have
acceptance criteria that can all be driven with NO Ollama, because the half that
carries the value is deterministic:

  * retrieval finds the line that answers a question, and returns NOTHING for a
    question the source does not answer - so "I could not find it" is a real,
    tested path and not a hope;
  * every answer either carries a file:line citation whose quote is re-read from
    disk, or says plainly that it could not establish it - there is no third
    shape, so a model cannot talk its way to an uncited "fact";
  * a missing scrubber means NOTHING is read out (fail closed);
  * a private question latches the taint gate, and a plain source question does
    not;
  * the model seam is replaceable, exactly as `test_model_lanes.py:290` replaces
    `_run`, and no check here needs a socket;
  * phase 4 drafts a diff with its test and APPLIES NOTHING, and the refusal
    checker bites on the gate, a tier table and a test file.

EVERY GUARD IS BITE-PROVED. A check that cannot fail is worse than none, so the
guards below are each shown FAILING with the guard itself disabled - the boundary
table, the test-file pattern, the citation rule, the scrubber, the loopback pin,
the blob filter - and then restored. The bite checks say so in their own names.

The real tree is used by ONE check (`t_the_real_tree_answers_with_a_real_line`),
because everything else is faster and more honest against a fixture where the
answer and the non-answer are both known exactly.
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_self_improve as M  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   Fixtures - small, known, and fast
# --------------------------------------------------------------------------

#: Two files with the same NAME and the same TEXT, in two folders: that is
#: `backend/` and `jarvis-backend/` in miniature, and it is what the duplicate
#: rule is for.
_ALPHA = """\
# a small fixture
def retry_backup(times=3):
    # the backup retry loop stops after three tries
    return times
"""

_MEMORY = """\
# jarvis_memory.py, in miniature: a module that HOLDS private material
def remember(fact):
    return {"fact": fact}
"""

_DOC = """\
# Notes about the program
The backup is written to one folder. Nothing else.
"""

_SPARE = """\
# an unrelated file, so a question about spares has something to find
SPARE_PARTS = 4
"""

#: One identifier with the question's word AFTER the underscore, and nowhere else
#: in the fixture. This is the measured bug the check below pins: with an
#: underscore treated as a letter, `taint` did not match `latch_taint`, and the
#: line that answered the question was never retrieved.
_HISTORY = """\
def save_history():
    return 1
"""


def fixture_tree() -> Path:
    """A throwaway backend: the answer, the non-answer, and a twin pair."""
    root = Path(tempfile.mkdtemp(prefix="jarvis-self-improve-"))
    (root / "alpha.py").write_text(_ALPHA, encoding="utf-8", newline="\n")
    (root / "spare.py").write_text(_SPARE, encoding="utf-8", newline="\n")
    (root / "notes.md").write_text(_DOC, encoding="utf-8", newline="\n")
    (root / "jarvis_memory.py").write_text(_MEMORY, encoding="utf-8", newline="\n")
    (root / "save_history_only.py").write_text(_HISTORY, encoding="utf-8", newline="\n")
    twin = root / "twin"
    twin.mkdir()
    (twin / "alpha.py").write_text(_ALPHA, encoding="utf-8", newline="\n")
    return root


def _git_status_free_snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _good_diffs():
    """(code diff, test diff) that the boundary ALLOWS."""
    code = ("--- a/alpha.py\n+++ b/alpha.py\n@@ -1,4 +1,5 @@\n"
            " # a small fixture\n+import time\n def retry_backup(times=3):\n"
            "     # the backup retry loop stops after three tries\n     return times\n")
    test = ("--- /dev/null\n+++ b/test_alpha_retry.py\n@@ -0,0 +1,3 @@\n"
            "+def test_retry():\n+    assert True\n")
    return code, test


def _stub(answer: str):
    """A model seam that records the prompt it was given and answers once."""
    seen = []

    def ask(prompt: str) -> str:
        seen.append(prompt)
        return answer

    return ask, seen


def _no_scrubber():
    """Replace `_scrubber` with one that finds nothing, and give the old one back."""
    real = M._scrubber
    M._scrubber = lambda: None
    return real


# --------------------------------------------------------------------------
#   The suite's own registration - the trap the design names (section 6, Claim 5)
# --------------------------------------------------------------------------

def _unregistered(names, run) -> list:
    """`t_*` names the run tuple does not carry - a test that would never run."""
    return sorted(set(names) - set(run))


def t_every_test_in_this_file_is_registered():
    """A `def t_...` that is not in the RUN tuple at the bottom NEVER RUNS.

    The design names this as the failure mode to look for (section 6, Claim 5),
    and `test_voice_contract.py:632-636` is the live example of the shape. This
    check reads this file's own source and compares every top-level `t_` function
    with the tuple that is really run, so a forgotten one is a red check rather
    than silence."""
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined = sorted(node.name for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name.startswith("t_"))
    running = sorted(fn.__name__ for fn in RUN)
    check("this file defines at least ten checks", len(defined) >= 10, defined)
    check("every t_ function this file defines is in the RUN tuple",
          not _unregistered(defined, running), _unregistered(defined, running))
    check("... and every entry in RUN is a real function here",
          not _unregistered(running, defined), _unregistered(running, defined))


def t_the_registration_check_bites():
    """BITE: a name left out of the tuple is really caught, and so is a stale one.

    Without this, `t_every_test_in_this_file_is_registered` could be comparing two
    lists that are both wrong in the same way and passing."""
    defined = ["t_a", "t_b", "t_c"]
    check("a missing name is reported", _unregistered(defined, ["t_a", "t_b"]) == ["t_c"],
          _unregistered(defined, ["t_a", "t_b"]))
    check("a name only in RUN is reported", _unregistered(["t_a", "t_gone"], ["t_a"]) == ["t_gone"],
          _unregistered(["t_a", "t_gone"], ["t_a"]))
    check("a complete tuple reports nothing", _unregistered(defined, defined) == [])


# --------------------------------------------------------------------------
#   Phase 3 - retrieval, the deterministic half
# --------------------------------------------------------------------------

def t_retrieval_finds_the_line_that_answers_the_question():
    """The acceptance criterion's first half: a question whose answer EXISTS.

    No model, no socket: `retrieve()` is the deterministic step, and it must put
    the retry loop's own line in front of the model."""
    root = fixture_tree()
    try:
        found = M.retrieve("where is the backup retry loop", roots=[root])
        check("retrieval returns something for a question the source answers", bool(found), found)
        check("... and the line it returns is the retry loop's own comment",
              any("retry loop" in e.text for e in found),
              [f"{e.where}: {e.text}" for e in found])
        check("... with a file:line that is really where it is",
              any(e.path == "alpha.py" and e.line == 3 for e in found),
              [(e.path, e.line) for e in found])
        check("... and the evidence carries the line itself, not a summary",
              any(e.text.strip() == "return times" or "retry" in e.text for e in found))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_retrieval_returns_nothing_when_the_answer_is_not_there():
    """The acceptance criterion's second half: a question whose answer does NOT.

    This is the check that makes "could not find" a real path rather than a hope.
    A fixture word that exists nowhere in the tree must produce an EMPTY evidence
    set - and the same on the real repository, with the control word's absence
    verified first so the negative cannot be luck."""
    root = fixture_tree()
    try:
        found = M.retrieve("wobblegong flurb", roots=[root])
        check("a question about nothing in the tree returns no evidence", found == (), found)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # The control word is ASSEMBLED, not written out: this test file is itself
    # inside the tree the real-tree search reads, so a literal control word here
    # would be found there and the negative would fail for the wrong reason.
    control = "zq" + "xv" + "jjww"
    check("the assembled control word is not in this file verbatim",
          control not in Path(__file__).read_text(encoding="utf-8"))
    real = M.retrieve(control, roots=M.default_roots())
    check(f"the real tree has no line containing {control!r} (the control is real)",
          real == (), [f"{e.where}: {e.text}" for e in real][:3])


def t_retrieval_is_deterministic_and_drops_the_twin():
    """Two runs, one answer; and `backend/x.py` + `jarvis-backend/x.py` is ONE hit.

    Determinism is what lets the suite assert anything about ranking at all, and
    the twin rule is what stops the published copy of the program eating half the
    evidence budget."""
    root = fixture_tree()
    try:
        first = M.retrieve("backup retry", roots=[root], limit=6)
        second = M.retrieve("backup retry", roots=[root], limit=6)
        check("the same question returns the same lines in the same order", first == second,
              (first, second))
        names = [(Path(e.path).name, e.line) for e in first]
        check("the twin pair appears once, not twice", len(names) == len(set(names)), names)
        check("... and it is cited from the first tree, not the copy",
              not any(e.path.startswith("twin/") for e in first),
              [e.path for e in first])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_blob_is_not_evidence_and_the_blob_rule_bites():
    """BITE: without the blob filter, an invented word matches encoded data.

    Measured on the real repository: `zzq` matched inside `jarvis_stopword.py`'s
    base64 table, so a nonsense question came back with confident hits. The
    filter is what makes "no answer exists" reliable."""
    root = fixture_tree()
    try:
        blob = "zqxwobble" * 12            # 108 characters, no spaces
        # On its OWN line, the shape the real word lists use: a line with a
        # space in it is a line of source, however long.
        (root / "encoded.py").write_text(f'"{blob}",\n', encoding="utf-8", newline="\n")
        found = M.retrieve("zqxwobble", roots=[root])
        check("a word inside an encoded blob is not evidence", found == (), found)

        real_is_blob, real_min = M._is_blob, M.BLOB_MIN_CHARS
        M._is_blob = lambda line: False     # the guard, disabled
        try:
            unfiltered = M.retrieve("zqxwobble", roots=[root])
        finally:
            M._is_blob = real_is_blob
        check("BITE: with the blob filter off, that same word DOES come back",
              bool(unfiltered), "the filter is not what is doing the work")
        check("... and the filter is back on", M._is_blob is real_is_blob and M.BLOB_MIN_CHARS == real_min)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_word_inside_a_snake_case_name_counts_the_same():
    """`save_history` must be found by the word AFTER the underscore.

    Measured on the real tree: with an underscore treated as a letter, `taint`
    did not match `def latch_taint(...)` - the one line that answers the
    question - and the evidence came back as prose ABOUT the latch instead. BITE
    included: the old pattern is put back and shown to miss it."""
    root = fixture_tree()
    try:
        found = M.retrieve("history", roots=[root])
        check("a word after an underscore is matched",
              any(e.path == "save_history_only.py" and e.line == 1 for e in found),
              [f"{e.where}: {e.text}" for e in found])
        check("... and the line it returns is the definition",
              any(e.text.strip().startswith("def save_history(") for e in found),
              [e.text for e in found])

        real_patterns = M._patterns
        M._patterns = lambda tokens: {t: re.compile(r"(?<![a-z0-9_])" + re.escape(t))
                                      for t in tokens}      # the old, broken rule
        try:
            missed = M.retrieve("history", roots=[root])
        finally:
            M._patterns = real_patterns
        check("BITE: with an underscore treated as a letter, that line is NOT found",
              not any(e.path == "save_history_only.py" for e in missed),
              [e.path for e in missed])
        check("... and the real pattern is back", M._patterns is real_patterns)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_no_evidence_means_the_model_is_never_asked():
    """A question with nothing to read must not reach a model at all.

    Asking anyway is how a plausible guess gets made, which section 4.5 forbids
    in as many words."""
    root = fixture_tree()
    try:
        ask, seen = _stub("ANSWER: something\nCITE: 1\n")
        d = M.diagnose("wobblegong flurb", roots=[root], ask=ask)
        check("the model was not asked", seen == [], seen)
        check("... and the diagnosis says why, in plain words", not d.found and bool(d.why), d)
        check("... and the rendered text has NO file:line in it",
              "alpha.py:" not in M.text(d) and ".py:" not in M.text(d), M.text(d))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   Phase 3 - the answer shape
# --------------------------------------------------------------------------

def t_an_answer_cites_a_real_line_and_the_quote_is_re_read():
    """The citation is re-read from the file, never copied out of the prompt.

    Two things are proven: the citation points at the line the model was shown,
    and its TEXT is read from disk at the moment of the answer - proven by
    changing the file between retrieval and citation."""
    root = fixture_tree()
    try:
        evidence = M.retrieve("backup retry loop", roots=[root], limit=4)
        check("there is evidence to cite", bool(evidence), evidence)
        prompt = M.build_prompt("backup retry loop", evidence)
        check("the prompt numbers the evidence from 1", "1) " in prompt and "alpha.py:" in prompt, prompt[:200])
        answer = M._canonical(prompt).split("\n")
        numbered = [l for l in answer if re.match(r"^\d+\) ", l)]
        check("every numbered line in the prompt is one evidence item",
              len(numbered) == len(evidence), (len(numbered), len(evidence)))

        ask, seen = _stub("ANSWER: the retry loop stops after three tries.\nCITE: 1\n")
        index = next((i for i, e in enumerate(evidence, start=1) if e.path == "alpha.py"), 0)
        check("the fixture's own line is in the evidence", index > 0,
              [f"{e.where}: {e.text}" for e in evidence])
        if not index:
            return
        ask, _seen = _stub(f"ANSWER: the retry loop stops after three tries.\nCITE: {index}\n")
        d = M.diagnose("backup retry loop", roots=[root], ask=ask)
        first = evidence[index - 1]
        check("the diagnosis is found", d.found, d.why)
        check("... it carries exactly the citation the model named", len(d.citations) == 1, d.citations)
        check("... and that citation is the line it was shown",
              d.citations[0].where == f"{first.path}:{first.line}",
              (d.citations[0].where, first.where))
        check("... and the quote is the file's own text",
              d.citations[0].text == first.text.strip(), d.citations[0].text)
        check("... and the rendered text shows file:line and the line",
              d.citations[0].where in M.text(d) and d.citations[0].quoted()[:20] in M.text(d),
              M.text(d))

        # THE RE-READ: change the line on disk, then cite it again.
        target = root / first.path
        lines = target.read_text(encoding="utf-8").split("\n")
        lines[first.line - 1] = "# THE LINE CHANGED AFTER RETRIEVAL"
        target.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        again = M._cite(evidence, (index,), (root,))
        check("the quote is re-read from disk, not replayed from the prompt",
              again[0].text == "# THE LINE CHANGED AFTER RETRIEVAL", again[0].text)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_model_cannot_produce_an_answer_with_no_citation():
    """No valid CITE and no CANNOT is "could not establish" - never an answer.

    This is the property that makes a paraphrase-as-fact impossible: there is no
    code path that returns `found=True` without a citation."""
    root = fixture_tree()
    try:
        for label, reply in (
            ("a plain answer with no citation at all", "ANSWER: the backup is broken somewhere.\n"),
            ("a citation of a line that was never shown", "ANSWER: it is in the backup.\nCITE: 99\n"),
            ("a citation that is not a number", "ANSWER: it is in the backup.\nCITE: alpha\n"),
            ("an empty reply", ""),
        ):
            ask, _seen = _stub(reply)
            d = M.diagnose("backup retry loop", roots=[root], ask=ask)
            check(f"{label}: not reported as found", not d.found, (d.found, d.why))
            check(f"{label}: says why it could not establish it", bool(d.why), d)
            check(f"{label}: the rendered text has no file:line citation",
                  "alpha.py:" not in M.text(d), M.text(d))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_citation_rule_bites():
    """BITE: with the citation requirement removed, the same reply becomes an answer.

    The guard is `_cite` returning nothing and `diagnose` refusing; this shows
    what the refusal is really holding back by running the same reply through a
    citation function that answers with evidence it was never given."""
    root = fixture_tree()
    try:
        evidence = M.retrieve("backup retry loop", roots=[root], limit=4)
        ask, _seen = _stub("ANSWER: the backup is broken somewhere.\n")
        d = M.diagnose("backup retry loop", roots=[root], ask=ask)
        check("with the rule on, no citation means not found", not d.found and d.citations == (), d.why)

        real_cite = M._cite
        M._cite = lambda ev, numbers, roots: (
            (M.Citation(path=ev[0].path, line=ev[0].line, text=ev[0].text),) if ev else ())
        try:
            unbitten = M.diagnose("backup retry loop", roots=[root], ask=ask)
        finally:
            M._cite = real_cite
        check("BITE: with the rule off, the SAME uncited reply is reported as found",
              unbitten.found and bool(unbitten.citations),
              "the citation rule is not what makes the refusal happen")
        check("... and the rule is back", M._cite is real_cite)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_model_that_says_it_cannot_is_reported_as_could_not_find():
    root = fixture_tree()
    try:
        ask, _seen = _stub("CANNOT: no line in the evidence shows the retry count")
        d = M.diagnose("backup retry loop", roots=[root], ask=ask)
        check("a CANNOT reply is not found", not d.found, d)
        check("... and the model's own reason is carried, not replaced",
              "no line in the evidence" in d.why, d.why)
        check("... and the text says so plainly",
              M.text(d).startswith("Could not establish this:"), M.text(d))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_run_seam_is_the_one_the_suite_replaces():
    """The seam is `M._run`, the shape `test_model_lanes.py:290` uses.

    Proven by replacing the module attribute and calling `diagnose` WITHOUT
    `ask=`: if the seam were bypassed, the real `_run` would be reached and the
    fake would never see the prompt."""
    root = fixture_tree()
    seen = []

    def fake_run(prompt, **kwargs):
        seen.append((prompt, kwargs))
        return "ANSWER: the retry loop stops after three tries.\nCITE: 1\n"

    real_run, M._run = M._run, fake_run
    try:
        d = M.diagnose("backup retry loop", roots=[root], model="a-test-model")
    finally:
        M._run = real_run
    check("the suite's replacement of _run is what production calls", len(seen) == 1, seen)
    check("... and what it was handed is the real prompt", seen and "CITE:" in seen[0][0], seen[:1])
    check("... and the model name is passed through", seen and seen[0][1].get("model") == "a-test-model", seen[:1])
    check("... and the answer it returned is the answer reported", d.found, d.why)
    check("... and _run is back", M._run is real_run)


def t_one_hunk_of_untrusted_text_cannot_break_the_protocol():
    """A model's reply is untrusted text. Weird whitespace, CRLF and a lower-case
    anchor are tolerated; a citation is still only ever a number."""
    for label, reply, want in (
        ("CRLF", "ANSWER: fine\r\nCITE: 2\r\n", 2),
        ("lower case anchor", "answer: fine\ncite: 2\n", 2),
        ("indented anchor", "   ANSWER: fine\n   CITE:   2   \n", 2),
        ("a number written with a hash and a full stop", "ANSWER: fine\nCITE: #2.\n", 2),
        ("a word where a number belongs", "ANSWER: fine\nCITE: second\n", None),
        ("a negative number", "ANSWER: fine\nCITE: -1\n", None),
    ):
        answer, cites, cannot = M.parse_reply(reply)
        check(f"{label}: parsed as {want!r}", cites == (() if want is None else (want,)),
              (answer, cites, cannot))


# --------------------------------------------------------------------------
#   Phase 3 - the scrubber, the latch, and the loopback pin
# --------------------------------------------------------------------------

def t_no_scrubber_means_nothing_is_read_out():
    """FAIL CLOSED. `jarvis_voiceprint.py:632` is the same rule for the same
    reason: a scrubber that is missing must not mean "carry on unscrubbed".

    BITE included: with the scrubber present again, the same question is answered
    - so the refusal is the missing scrubber and not something else."""
    root = fixture_tree()
    try:
        ask, _seen = _stub("ANSWER: the retry loop stops after three tries.\nCITE: 1\n")
        real = _no_scrubber()
        try:
            d = M.diagnose("backup retry loop", roots=[root], ask=ask)
            t = M.text(d)
        finally:
            M._scrubber = real
        check("with no scrubber, nothing is found", not d.found, d)
        check("... and the reason names the scrubber", "scrubber" in d.why, d.why)
        check("... and NO quoted line is printed", "alpha.py:" not in t, t)
        check("BITE: with the scrubber back, the same question IS answered",
              M.diagnose("backup retry loop", roots=[root], ask=ask).found)
        check("... and the scrubber is the real one again", M._scrubber is real)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_private_question_latches_and_a_plain_one_does_not():
    """Section 4.5: the taint latch applies.

    Two directions, so the check cannot pass by latching everything or nothing:
    a question about the owner's memory MUST latch, and a question about the
    program's own plumbing MUST NOT. The gate is a recorded stub - no database,
    no state file, nothing written."""
    root = fixture_tree()
    calls = []

    class FakeGate:
        @staticmethod
        def latch_taint(minutes=None, why=""):
            calls.append(why)
            return True

    real_gate = M._gate
    M._gate = lambda: FakeGate
    try:
        ask, _seen = _stub("ANSWER: the retry loop stops after three tries.\nCITE: 1\n")
        plain = M.diagnose("where is the backup retry loop", roots=[root], ask=ask)
        check("a plain source question does not latch", calls == [], calls)
        check("... and it is not marked private", plain.tainted is False and plain.latched is False, plain)

        calls.clear()
        private = M.diagnose("what is in my memory about me", roots=[root], ask=ask)
        check("a question about the owner's memory latches", calls == ["self_improve_diagnosis"], calls)
        check("... and the diagnosis says so", private.tainted is True and private.latched is True, private)
        check("... and the rendered text says so in plain words",
              "local-only" in M.text(private), M.text(private))

        calls.clear()
        read = M.diagnose("what does remember() do", roots=[root], ask=ask)
        check("a question that READS a module holding private material also latches",
              calls == ["self_improve_diagnosis"], (calls, read.evidence))
    finally:
        M._gate = real_gate
        shutil.rmtree(root, ignore_errors=True)


def t_a_missing_gate_is_not_an_error():
    """The gate is optional like every shipped module here: no gate, no latch,
    no exception, and the diagnosis still works."""
    root = fixture_tree()
    real_gate = M._gate
    M._gate = lambda: None
    try:
        ask, _seen = _stub("ANSWER: the retry loop stops after three tries.\nCITE: 1\n")
        d = M.diagnose("what is in my memory about me", roots=[root], ask=ask)
        check("with no gate, nothing raises and the answer still comes back", d.found, d.why)
        check("... and it is still marked private, with no latch claimed",
              d.tainted is True and d.latched is False, d)
    finally:
        M._gate = real_gate
        shutil.rmtree(root, ignore_errors=True)


def t_only_loopback_is_ever_used_and_the_pin_bites():
    """Nothing here may be pointed at another machine.

    The pin is checked by behaviour AND by reading the module's own source: one
    `urlopen`, inside `_run` alone, and the URL it opens comes from
    `_loopback_url`."""
    check("an explicit remote url is not used", M._loopback_url("http://192.168.1.5:11434")
          == M.DEFAULT_URL, M._loopback_url("http://192.168.1.5:11434"))
    had = os.environ.get("OLLAMA_HOST")
    os.environ["OLLAMA_HOST"] = "http://example.com:11434"
    try:
        from_env = M._loopback_url()
    finally:
        if had is None:
            os.environ.pop("OLLAMA_HOST", None)
        else:
            os.environ["OLLAMA_HOST"] = had
    check("... nor one from the environment", from_env == M.DEFAULT_URL, from_env)
    check("... and loopback is kept", M._loopback_url("http://127.0.0.1:11435")
          == "http://127.0.0.1:11435", M._loopback_url("http://127.0.0.1:11435"))
    check("... including the IPv6 loopback and the name",
          M._loopback_url("http://localhost:11434") == "http://localhost:11434"
          and M._loopback_url("http://[::1]:11434") == "http://[::1]:11434")

    text = (HERE / "jarvis_self_improve.py").read_text(encoding="utf-8")
    check("the module opens exactly one URL, and it is in _run",
          text.count("urlopen(") == 1, text.count("urlopen("))
    check("... and _run builds it from _loopback_url",
          re.search(r"def _run\([\s\S]*?where = _loopback_url\(url\)[\s\S]*?urlopen\(", text)
          is not None)
    check("... and no other network client is imported",
          not any(word in text for word in ("import socket", "import requests",
                                            "http.client", "import asyncio")))


# --------------------------------------------------------------------------
#   Phase 4 - drafting, and the boundary
# --------------------------------------------------------------------------

def t_a_draft_carries_a_diff_a_test_and_an_explanation_and_applies_nothing():
    """Section 7's Phase-4 row: the diff is shown, the test is required, and
    nothing is applied.

    "Applies nothing" is checked twice: behaviourally (the fixture tree is
    byte-identical afterwards) and structurally (the module has no subprocess,
    no shell, no writer and no git)."""
    root = fixture_tree()
    try:
        code, test = _good_diffs()
        reply = (f"EXPLAIN: it would import time before the retry loop.\n"
                 f"CODE_DIFF:\n{code}END_CODE_DIFF\nTEST_DIFF:\n{test}END_TEST_DIFF\nCITE: 1\n")
        before = _git_status_free_snapshot(root)
        ask, seen = _stub(reply)
        p = M.draft("the backup retry loop", roots=[root], ask=ask)
        after = _git_status_free_snapshot(root)

        check("the draft is offered", p.ok, p.refusal)
        check("... with the explanation", "import time" in p.explanation, p.explanation)
        check("... with the code diff, lines and all", diff_targets_ok(p.code_diff, "alpha.py"),
              p.code_diff)
        check("... with the test diff", diff_targets_ok(p.test_diff, "test_alpha_retry.py"),
              p.test_diff)
        check("... and NOTHING on disk changed", before == after,
              set(before.items()) ^ set(after.items()))
        check("... and the module says so in the text the owner reads",
              "Nothing was changed" in M.proposal_text(p), M.proposal_text(p)[-120:])
        check("... and it was asked with the drafting protocol",
              seen and "CODE_DIFF:" in seen[0] and "TEST_DIFF:" in seen[0])

        source = (HERE / "jarvis_self_improve.py").read_text(encoding="utf-8")
        for label, needle in (("no subprocess", "subprocess"),
                              ("no os.system", "os.system"),
                              ("no file being written", None),
                              ("no write_text", "write_text"),
                              ("no unlink/remove/rmtree", "unlink"),
                              ("no git", '"git"')):
            if needle is None:
                source = (HERE / "jarvis_self_improve.py").read_text(encoding="utf-8")
                found_open = re.search(r"(?<![A-Za-z_.])open\(", source)
                check(f"the module has {label}", found_open is None, found_open)
                continue
            check(f"the module has {label}", needle not in source, needle)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def diff_targets_ok(diff_text: str, name: str) -> bool:
    """Helper: does this diff touch `name` and look like a real diff?"""
    return M.is_diff(diff_text) and name in M.diff_targets(diff_text)


def t_no_test_means_no_proposal():
    """Section 5.2 step 3: "No test, no proposal"."""
    root = fixture_tree()
    try:
        code, _test = _good_diffs()
        reply = ("EXPLAIN: it would import time.\nCODE_DIFF:\n" + code +
                 "END_CODE_DIFF\nCITE: 1\n")
        p = M.draft("the backup retry loop", roots=[root], ask=_stub(reply)[0])
        check("a draft with a code diff and NO test is refused", not p.ok, p)
        check("... and the refusal says a test is what is missing",
              "test" in p.refusal and "not offered" in p.refusal, p.refusal)
        check("... and the refusal is in the text the owner reads",
              M.proposal_text(p).startswith("Not drafted:"), M.proposal_text(p))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_boundary_refuses_the_gate_a_tier_table_and_a_test_file():
    """Section 5.1, and the Phase-4 row: a diff touching the gate, a tier table
    or a test file is refused."""
    _code, test = _good_diffs()

    def code_for(path: str) -> str:
        return (f"--- a/{path}\n+++ b/{path}\n@@ -1,3 +1,4 @@\n"
                f" line one\n+an added line\n line two\n line three\n")

    for label, path, needle in (
        ("the gate", "backend/jarvis_gate.py", "jarvis_gate.py"),
        ("a tier table", "backend/jarvis_preview.py", "tier or risk table"),
        ("a tier table in the settings", "backend/rebuilt/jarvis-framework.toml", "tier or risk table"),
        ("a test file", "backend/test_alpha.py", "test file"),
        ("the shipped lists", "scripts/apply-patches.ps1", "shipped lists"),
        ("the other end of the lists", "backend/_where.py", "shipped lists"),
    ):
        reason = M.refusal_reason(code_for(path), test)
        check(f"a draft touching {label} is refused", bool(reason), reason or "ALLOWED")
        check(f"... and the refusal names it", needle in reason, reason)


def t_the_boundary_bites():
    """BITE for all three mandated refusals, one guard at a time.

    Each guard is disabled and the SAME diff is shown being allowed - which is
    what proves the guard, and not something else, is doing the work. The gate is
    refused by two lists at once (`PROTECTED` and `TIER_TABLE_NAMES`), so its
    bite disables both; a bite that removed one of them would still be refused
    and would prove nothing."""
    _code, test = _good_diffs()
    gate = ("--- a/backend/jarvis_gate.py\n+++ b/backend/jarvis_gate.py\n@@ -1,3 +1,4 @@\n"
            " line one\n+an added line\n line two\n line three\n")
    tier = ("--- a/backend/jarvis_preview.py\n+++ b/backend/jarvis_preview.py\n@@ -1,3 +1,4 @@\n"
            " line one\n+an added line\n line two\n line three\n")
    a_test = ("--- a/backend/test_alpha.py\n+++ b/backend/test_alpha.py\n@@ -1,3 +1,4 @@\n"
              " line one\n+an added line\n line two\n line three\n")
    check("all three are refused with every guard on",
          bool(M.refusal_reason(gate, test)) and bool(M.refusal_reason(tier, test))
          and bool(M.refusal_reason(a_test, test)))

    real_protected, real_tiers, real_re = M.PROTECTED, M.TIER_TABLE_NAMES, M.TEST_FILE_RE

    M.PROTECTED = tuple(n for n in real_protected if n != "jarvis_gate.py")
    M.TIER_TABLE_NAMES = tuple(n for n in real_tiers if n != "jarvis_gate.py")
    try:
        allowed = M.refusal_reason(gate, test)
    finally:
        M.PROTECTED, M.TIER_TABLE_NAMES = real_protected, real_tiers
    check("BITE: with the gate off both lists, that same diff is ALLOWED", allowed == "", allowed)

    M.TIER_TABLE_NAMES = tuple(n for n in real_tiers if n != "jarvis_preview.py")
    try:
        allowed_tier = M.refusal_reason(tier, test)
    finally:
        M.TIER_TABLE_NAMES = real_tiers
    check("BITE: with the tier table off the list, that same diff is ALLOWED",
          allowed_tier == "", allowed_tier)

    # The prohibition and the requirement share one pattern, so the bite must not
    # simply kill it - that would refuse the test diff as "not a test" and the
    # case would still be refused by the other half. This replacement matches the
    # NEW test file only, so the requirement still holds and the only rule turned
    # off is the one that forbids editing an EXISTING test.
    M.TEST_FILE_RE = re.compile(r"test_alpha_retry\.py$")
    try:
        allowed_test = M.refusal_reason(a_test, test)
    finally:
        M.TEST_FILE_RE = real_re
    check("BITE: with the prohibition off (the new-file rule still on), that diff is ALLOWED",
          allowed_test == "", allowed_test)

    check("... and all three guards are back",
          M.PROTECTED is real_protected and M.TIER_TABLE_NAMES is real_tiers
          and M.TEST_FILE_RE is real_re)
    check("... and they refuse again", bool(M.refusal_reason(gate, test))
          and bool(M.refusal_reason(tier, test)) and bool(M.refusal_reason(a_test, test)))


def t_the_test_diff_must_create_a_new_test():
    """A test that EDITS an existing test file is refused: that is how a wrong
    change makes itself pass."""
    _code, _test = _good_diffs()
    edits = ("--- a/backend/test_alpha.py\n+++ b/backend/test_alpha.py\n@@ -1,3 +1,3 @@\n"
             "-def test_old():\n-    assert False\n+def test_old():\n+    assert True\n")
    reason = M.refusal_reason(_code, edits)
    check("editing an existing test is refused", bool(reason), reason or "ALLOWED")
    check("... and the reason is the NEW-file rule", "NEW file" in reason, reason)

    not_a_test = ("--- /dev/null\n+++ b/backend/jarvis_new.py\n@@ -0,0 +1,2 @@\n"
                  "+VALUE = 1\n")
    reason2 = M.refusal_reason(_code, not_a_test)
    check("a test diff that is not a test file is refused", bool(reason2), reason2 or "ALLOWED")
    check("... and the reason says so", "not a test" in reason2, reason2)


def t_a_diff_that_is_not_a_diff_is_refused():
    """`is_diff` is what stops a paragraph of prose being offered as a change."""
    _code, test = _good_diffs()
    for label, junk in (("prose", "I would change the retry loop to use time.sleep."),
                        ("a diff with no hunk", "--- a/alpha.py\n+++ b/alpha.py\n")):
        check(f"{label} is not a diff", not M.is_diff(junk), junk)
        check(f"... and a draft whose code diff is {label} is refused",
              bool(M.refusal_reason(junk, test)), M.refusal_reason(junk, test))
    check("a real diff is a diff", M.is_diff(_code))


def t_the_model_saying_cannot_is_a_refusal_and_so_is_silence():
    root = fixture_tree()
    try:
        for label, reply, want in (
            ("CANNOT", "CANNOT: this needs a schema change I cannot make", "could not draft"),
            ("an empty reply", "", "did not answer"),
            ("an explanation with no diffs", "EXPLAIN: something should change\nCITE: 1\n",
             "no code diff"),
        ):
            p = M.draft("the backup retry loop", roots=[root], ask=_stub(reply)[0])
            check(f"{label}: the draft is refused", not p.ok, p)
            check(f"{label}: the refusal says why", want in p.refusal, p.refusal)
            check(f"{label}: nothing is offered", p.code_diff == "" and p.test_diff == "", p)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_prohibited_names_really_are_those_files():
    """The boundary is only as good as its list, so the list is checked against
    the tree: every tier-table name that EXISTS here must really carry a tier or
    risk table, and `jarvis_gate.py` must hold the tier map the design names."""
    root = HERE.parent  # the repository root when this suite runs from a checkout
    gate = root / "jarvis-backend" / "jarvis_gate.py"
    if not gate.is_file():
        gate = HERE / "jarvis_gate.py"
    if not gate.is_file():
        print("skip  jarvis_gate.py is not in this tree, so the names cannot be checked here")
        return
    source = gate.read_text(encoding="utf-8", errors="replace")
    check("jarvis_gate.py holds the tier ranks", "_RANK = {" in source, "no _RANK")
    check("... and the valid-tier set", "_VALID_TIERS" in source)
    check("... and the modify_own_code tier line the design cites",
          '"modify_own_code"' in source and "revertible from a backup" in source,
          "the modify_own_code tuple moved - section 5.2 cites it, and Claim 3 turns on it")

    marks = {
        "jarvis_content_risk.py": "_RANK = {",
        "jarvis_preview.py": "_RANK = {",
        "jarvis_injection.py": "_RANK = {",
        "jarvis_browser_control.py": "_INJECTION_RANK = {",
        "jarvis_arbiter.py": "_PRI_RANK = {",
        "jarvis-framework.toml": "[autonomy.tiers]",
    }
    for name, mark in marks.items():
        path = root / "jarvis-backend" / name
        if not path.is_file():
            path = HERE / name
        if not path.is_file():
            check(f"{name} is present to be checked", False, f"not found under {root}")
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        check(f"{name} really holds a tier/risk table ({mark!r})", mark in body, mark)
    missing = []
    for name in M.PROTECTED:
        places = (root / "jarvis-backend" / name, HERE / name,
                  root / "scripts" / name, root / "backend" / name)
        if not any(p.is_file() for p in places):
            missing.append(name)
    check("every name in PROTECTED is a real file in this tree", not missing, missing)


def t_no_confidence_is_asked_for_or_reported():
    """Section 4.4: "Confidence is not asked for and not reported."

    Checked on the dataclasses and on both prompts, so the field cannot come back
    quietly in a later edit."""
    for klass in (M.Diagnosis, M.Proposal):
        fields = set(getattr(klass, "__dataclass_fields__", {}))
        check(f"{klass.__name__} carries no confidence field",
              not (fields & {"confidence", "certainty", "probability", "score", "sure"}), fields)
    evidence = (M.Evidence(path="a.py", line=1, text="x = 1"),)
    for label, prompt in (("diagnosis", M.build_prompt("q", evidence)),
                          ("drafting", M.build_draft_prompt("q", evidence))):
        low = prompt.lower()
        check(f"the {label} prompt does not ask for confidence",
              "confidence" not in low and "how sure" not in low, low[:200])
        check(f"the {label} prompt demands a citation from the numbered lines",
              "CITE:" in prompt and "numbered lines" in low, prompt[:200])


# --------------------------------------------------------------------------
#   The real tree, and the shipped wiring
# --------------------------------------------------------------------------

def t_the_real_tree_answers_with_a_real_line():
    """The acceptance criterion on the REAL program: a question whose answer
    exists, answered with a file:line whose quote is the line that is really
    there.

    The model is a stub - CI has no Ollama - but retrieval is not: it runs over
    this checkout, and the citation is read back out of the file."""
    roots = M.default_roots()
    check("the tree this module runs in is readable", all(r.exists() for r in roots), roots)
    question = "where is the taint latch written"
    found = M.retrieve(question, roots=roots, limit=M.MAX_EVIDENCE)
    index = next((i for i, e in enumerate(found, start=1)
                  if e.text.strip().startswith("def latch_taint(")), 0)
    check("retrieval finds the definition of the taint latch", index > 0,
          [f"{e.where}: {e.text[:60]}" for e in found])
    if not index:
        return
    ask, _seen = _stub(f"ANSWER: the latch is set here.\nCITE: {index}\n")
    d = M.diagnose(question, roots=roots, ask=ask, limit=M.MAX_EVIDENCE)
    check("the diagnosis is found", d.found, d.why)
    check("... and it cites the real file the definition is in",
          d.citations and d.citations[0].path.endswith("jarvis_gate.py"),
          [c.where for c in d.citations])
    check("... and the quote is that file's line, re-read",
          d.citations[0].text.startswith("def latch_taint("), d.citations[0].text)
    check("... and the line number is the real one", d.citations[0].line > 0, d.citations[0].line)
    check("... and the rendered text shows it", "jarvis_gate.py:" in M.text(d), M.text(d))


def t_the_repository_ships_this_module_in_all_three_lists():
    """A module that is not in `$SHIPPED` is dead on arrival on the owner's PC
    (`tools/check_unmanaged_files.py` exists for exactly that).

    `test_shipped_modules.py` owns the full comparison of the three lists; this
    check is the narrow one that says whether THIS module is in them, so a PR
    that forgets one place fails here in a second rather than in CI."""
    root = HERE.parent
    where = HERE / "_where.py"
    script = root / "scripts" / "apply-patches.ps1"
    if not where.is_file() or not script.is_file():
        print("skip  this is not a checkout of the repository, so the lists are not here")
        return
    own = where.read_text(encoding="utf-8", errors="replace")
    ps1 = script.read_text(encoding="utf-8", errors="replace")
    check("the module is in backend/_where.py's SHIPPED", '"jarvis_self_improve.py"' in own,
          "not in SHIPPED - it would never reach the owner's PC")
    check("... and in scripts/apply-patches.ps1's $SHIPPED", "'jarvis_self_improve.py'" in ps1,
          "not in the script's list - the installer would never copy it")
    twin = root / "jarvis-backend" / "_where.py"
    check("... and its twin", twin.is_file() and '"jarvis_self_improve.py"' in
          twin.read_text(encoding="utf-8", errors="replace"), str(twin))
    check("... and the twin of the module itself exists",
          (root / "jarvis-backend" / "jarvis_self_improve.py").is_file(),
          "backend/<file> has no jarvis-backend/ twin")


def t_the_only_route_is_two_read_only_gets_and_no_way_to_draft():
    """Section 5.4 and the design's refusal list, kept by what the route CANNOT do.

    Phase 3 was originally wired with "no route", so that nothing could apply
    anything. The wiring queue (the read-only diagnostic route, wired
    2026-10-17) exposed the READ-ONLY half only: two GETs, for the owner, so a
    question about the program's own source can be asked without opening the
    source by hand. Phase 5 - applying a change - is still not here.

    This check proves the wall BEHAVIOURALLY rather than by reading the source:
    after install(), the class gains a GET wrapper and NO POST wrapper, every
    other path still reaches the core, there is no route for draft(), and the
    diagnosis route refuses a request that carries no question. The route's own
    answers and refusals are in `test_self_improve_diagnostic.py`."""
    core, sent = [], []

    class Handler:
        def __init__(self, path="/"):
            self.path = path

        def do_GET(self):
            core.append(("GET", self.path))

        def do_POST(self):
            core.append(("POST", self.path))

        def _send(self, code, payload):
            sent.append((code, payload))
            return payload

    post0, get0 = Handler.do_POST, Handler.do_GET
    line = M.install(Handler, origin_ok=lambda r: True, token_ok=lambda r: True,
                     read_body=lambda r: b"{}")
    check("install() exists and returns a banner line for the start-up banner",
          isinstance(line, str) and "self-improve" in line, line)
    check("... and the class gained NO POST handler: a read cannot become a write",
          Handler.do_POST is post0)
    check("... and it did wrap do_GET, so the two read-only GETs are served",
          Handler.do_GET is not get0)
    Handler("/api/other").do_GET()
    check("... and every other path still reaches the core",
          core == [("GET", "/api/other")], core)
    Handler("/api/self-improve/draft").do_GET()
    check("... and there is no draft route: the draft path reaches the core too",
          core[-1] == ("GET", "/api/self-improve/draft"), core)
    Handler("/api/self-improve/diagnose").do_GET()
    check("... and the diagnosis route refuses a request with no question",
          sent and sent[-1][0] == 400 and "empty" in str(sent[-1][1]), sent)
    check("... and nothing was written: the core saw no POST",
          all(method == "GET" for method, _ in core), core)


if __name__ == "__main__":
    RUN = (
        t_every_test_in_this_file_is_registered,
        t_the_registration_check_bites,
        t_retrieval_finds_the_line_that_answers_the_question,
        t_retrieval_returns_nothing_when_the_answer_is_not_there,
        t_retrieval_is_deterministic_and_drops_the_twin,
        t_a_blob_is_not_evidence_and_the_blob_rule_bites,
        t_a_word_inside_a_snake_case_name_counts_the_same,
        t_no_evidence_means_the_model_is_never_asked,
        t_an_answer_cites_a_real_line_and_the_quote_is_re_read,
        t_a_model_cannot_produce_an_answer_with_no_citation,
        t_the_citation_rule_bites,
        t_a_model_that_says_it_cannot_is_reported_as_could_not_find,
        t_the_run_seam_is_the_one_the_suite_replaces,
        t_one_hunk_of_untrusted_text_cannot_break_the_protocol,
        t_no_scrubber_means_nothing_is_read_out,
        t_a_private_question_latches_and_a_plain_one_does_not,
        t_a_missing_gate_is_not_an_error,
        t_only_loopback_is_ever_used_and_the_pin_bites,
        t_a_draft_carries_a_diff_a_test_and_an_explanation_and_applies_nothing,
        t_no_test_means_no_proposal,
        t_the_boundary_refuses_the_gate_a_tier_table_and_a_test_file,
        t_the_boundary_bites,
        t_the_test_diff_must_create_a_new_test,
        t_a_diff_that_is_not_a_diff_is_refused,
        t_the_model_saying_cannot_is_a_refusal_and_so_is_silence,
        t_the_prohibited_names_really_are_those_files,
        t_no_confidence_is_asked_for_or_reported,
        t_the_real_tree_answers_with_a_real_line,
        t_the_repository_ships_this_module_in_all_three_lists,
        t_the_only_route_is_two_read_only_gets_and_no_way_to_draft,
    )
    for fn in RUN:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
