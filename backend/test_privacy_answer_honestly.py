"""The data removal QUESTION must still answer honestly on a PC without the
module (2026-11-26).

THE MEASURED DEFECT. On the owner's live backend - the deploy of commit
`e719ccbf4`, which is the published base plus the patch stack - the sentence
"what is the data removal tool" reached NO LANE AT ALL: `jarvis_quick.match`
answered `None` (`intent: null`), so the local model was asked instead, and it
invented an answer. The cause was one line: `_privacy_prompt` returned `None`
as soon as `import jarvis_privacy_removal` failed, which is EVERY installed
copy, because that module is repository-only - named in
`test_shipped_modules.REPO_ONLY_IMPORTS`, absent from `_where.SHIPPED`, and
absent from `jarvis-backend/`. So `_run_privacy_explain`'s "not set up on this
PC" sentence was written and UNREACHABLE.

WHAT IS PROVEN HERE:

 1. The published base really does not carry the module, and the two
    `jarvis_quick.py` copies are byte-identical - so the simulated absence
    below is the installed copy's real shape, not a guess about it.
 2. The OLD behaviour is reproduced exactly: with the module blocked and the
    new fallback stubbed out, `Q.match` answers `None` for the measured
    sentence. That is `intent: null`, the state measured on the live PC, so
    the check below would have caught the defect.
 3. With the module blocked, the question reaches `privacy_explain` through the
    REAL `Q.match`, and `Q.run` answers with the pinned honest sentence: the
    tool is not set up on this PC yet, the part of Atlas that answers for it is
    not available here, and no ability and no procedure is claimed.
 4. The neighbours keep their own lanes with the module blocked, so the
    fallback cannot swallow a longer request, another feature's sentence, or a
    sentence that would need the missing engine (a mode change, a send).
 5. The module-PRESENT path is unchanged: every sentence the module claims
    still comes back from `PR.prompt` with the same fields, the answer is still
    `PR.privacy_explain(topic)` byte for byte, and the fallback is never called
    at all.

WHY `sys.modules[name] = None` IS THE HONEST SIMULATION. It makes
`import jarvis_privacy_removal` raise ImportError from inside `_privacy_prompt`,
which is the same exception an installed copy raises for a module that is not
there (a genuinely absent module raises its subclass ModuleNotFoundError, and
`_privacy_prompt` catches Exception). Nothing else about this PC changes, so
the checks below run the same code path the owner's PC runs.

A SKIP IS NEVER A PASS. This suite has no skips: the absence is simulated and
the presence is the repository's own copy, so every check runs here.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-privacy-honest-"))
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

import _where  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []

#: The exact sentence the live PC must answer with once the module is missing.
#: Pinned as a string, not read out of the source: it is the ANSWER that was
#: measured as invented, so the answer is what this suite holds still.
HONEST = ("The data removal tool is not set up on this PC yet: the part of "
          "Atlas that answers for it is not available here, so I cannot say "
          "what it does or how to use it. Nothing was guessed, and nothing "
          "was changed.")

#: The measured sentence, verbatim from the defect report.
MEASURED = "what is the data removal tool"

#: Every question that NAMES the tool has to be claimed when the module is
#: missing. These are the owner's own trigger words that do not need the
#: engine - the four explainer topics, said plainly.
QUESTIONS_NAMING_THE_TOOL = (
    "what is the data removal tool",
    "what's the data removal tool",
    "how does your personal info removal work",
    "what does the data removal tool do",
    "what can't the data removal tool do",
    "what cannot the data removal tool do",
    "how private is data removal",
    "what are the limits of the data removal tool",
    "tell me about the data removal tool",
    "explain the personal data removal tool",
    "can you remove my personal info from the internet",
)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class no_privacy_module:
    """`import jarvis_privacy_removal` fails, exactly as on an installed copy.

    Every attribute is put back as it was, so the module-present checks later in
    this file still see the repository's real module.
    """

    _name = "jarvis_privacy_removal"

    def __enter__(self):
        self._had = sys.modules.get(self._name, _MISSING)
        sys.modules[self._name] = None
        return self

    def __exit__(self, *_exc):
        if self._had is _MISSING:
            sys.modules.pop(self._name, None)
        else:
            sys.modules[self._name] = self._had
        return False


class _Missing:
    pass


_MISSING = _Missing()


#: A fixed modern instant. Deliberately not 1000.0 (1970): a neighbour sentence
#: below reaches the reminder lane, whose date maths overflows on 1970, and a
#: suite that crashes the lane it is checking proves nothing about it.
NOW = 1795651200.0


def match(sentence):
    """The REAL router, the way a request reaches it."""
    return Q.match(sentence, NOW)


def answer(sentence):
    """The reply the owner would read for `sentence`, or None (the model)."""
    got = match(sentence)
    if got is None:
        return None
    result = Q.run(got, None, NOW)
    return result.reply if result is not None else None


# ---------------------------------------------------------------------------
#   1. The installed copy's shape, measured here rather than assumed
# ---------------------------------------------------------------------------


def t_the_published_base_really_does_not_carry_the_module():
    base = ROOT / "jarvis-backend"
    check("the published base does not carry jarvis_privacy_removal.py",
          not (base / "jarvis_privacy_removal.py").exists(),
          str(base / "jarvis_privacy_removal.py"))
    check("... and the owner's ruling still holds: it is not in _where.SHIPPED",
          "jarvis_privacy_removal.py" not in _where.SHIPPED,
          str([n for n in _where.SHIPPED if "privacy" in n]))
    repo_copy = HERE / "jarvis_quick.py"
    base_copy = base / "jarvis_quick.py"
    check("... and the two jarvis_quick.py copies are byte-identical, so the "
          "base runs the fix this suite proves",
          repo_copy.read_bytes() == base_copy.read_bytes(),
          f"{repo_copy} vs {base_copy}")


# ---------------------------------------------------------------------------
#   2. The defect, reproduced: without the fallback the sentence reaches ----
#      nobody, which is the `intent: null` measured on the live PC
# ---------------------------------------------------------------------------


def t_the_measured_sentence_reached_no_lane_before_this_fix():
    real = Q._privacy_prompt_without_tool
    Q._privacy_prompt_without_tool = lambda *_a, **_k: None
    try:
        with no_privacy_module():
            got = match(MEASURED)
    finally:
        Q._privacy_prompt_without_tool = real
    check("with the module blocked and the fallback removed, the measured "
          "sentence reaches no lane at all (the measured intent: null)",
          got is None, str(got))
    check("... so this suite would have been RED on the live deployment, which "
          "is what makes the fix below a real check",
          got is None, str(got))


# ---------------------------------------------------------------------------
#   3. The fix: the question reaches the explainer, and it answers honestly
# ---------------------------------------------------------------------------


def t_the_question_still_reaches_the_explainer_without_the_module():
    with no_privacy_module():
        check("with the module blocked, `import jarvis_privacy_removal` really "
              "fails (so the simulation is not vacuous)",
              _import_fails(), "")
        for sentence in QUESTIONS_NAMING_THE_TOOL:
            got = match(sentence)
            check(f"{sentence!r} still reaches privacy_explain without the module",
                  got is not None and got.name == "privacy_explain",
                  str(getattr(got, "name", None)))


def _import_fails() -> bool:
    try:
        import jarvis_privacy_removal  # noqa: F401
    except Exception:                                       # noqa: BLE001
        return True
    return False


def t_the_answer_is_the_pinned_honest_sentence():
    with no_privacy_module():
        said = answer(MEASURED)
    check("the measured sentence is answered here, with no model", said is not None,
          str(said))
    check("... and the answer is exactly the pinned honest sentence",
          said == HONEST, repr(said))
    check("... it says plainly that the tool is not set up on this PC yet",
          "is not set up on this PC yet" in str(said), str(said))
    check("... it says the part of Atlas that answers for it is not available "
          "here", "part of Atlas that answers for it is not available here"
          in str(said), str(said))
    check("... and it says nothing was guessed",
          "Nothing was guessed" in str(said), str(said))


def t_the_answer_claims_no_ability_and_no_procedure():
    with no_privacy_module():
        said = str(answer(MEASURED) or "")
    low = said.lower()
    # The module's own overview words: if any of these appear, the answer is
    # describing a procedure this PC cannot perform.
    for word in ("data broker", "gmail", "app password", "optery", "consent card",
                 "verify pass", "90 days", "official portal", "hybrid", "mode"):
        check(f"the answer does not describe the procedure word {word!r}",
              word not in low, said)
    for word in ("you can", "to do this", "first,", "step 1", "then open"):
        check(f"the answer gives no instruction ({word!r})", word not in low, said)
    check("... and it makes no claim that a removal happened",
          "removed" not in low and "deleted" not in low, said)


def t_the_reply_really_comes_from_the_explainer():
    seen = []
    real = Q._run_privacy_explain

    def spy(fields):
        seen.append(dict(fields))
        return real(fields)

    Q._run_privacy_explain = spy
    try:
        with no_privacy_module():
            result = Q.run(match(MEASURED), None, NOW)
    finally:
        Q._run_privacy_explain = real
    check("the dispatch reaches _run_privacy_explain, the path that was "
          "unreachable before this fix", seen != [], str(seen))
    check("... and the result is that handler's own reply",
          result is not None and result.reply == HONEST
          and result.intent == "privacy_explain",
          f"{getattr(result, 'intent', None)} | {getattr(result, 'reply', None)}")
    check("... and privacy_explain is a read-only intent, so this answer needs "
          "no card and writes nothing",
          "privacy_explain" in Q.READ_ONLY_INTENTS, "")
    check("... and a private chat may still answer it",
          "privacy_explain" in Q._PRIVATE_DETERMINISTIC_READS, "")


# ---------------------------------------------------------------------------
#   4. The fallback cannot swallow anything else
# ---------------------------------------------------------------------------


def t_the_neighbours_keep_their_own_lanes_without_the_module():
    for sentence in ("what is the weather", "how private are my notes",
                     "set my cap to $5", "what can you do",
                     "remind me to look at data removal tomorrow",
                     "send an email to Bob about my removal emails",
                     "show me my notes about data removal"):
        got = match(sentence)
        check(f"{sentence!r} is still not this feature's without the module",
              got is None or got.name != "privacy_explain",
              str(getattr(got, "name", None)))


def t_a_sentence_that_needs_the_engine_is_not_claimed():
    """The fallback may not pretend to RUN what the module would run.

    A mode change, a send, a status read and a hand-list all need code that is
    not on this PC. Claiming them would answer "not set up" in place of their
    own lanes, so the fallback claims none of them - it only explains.
    """
    for sentence in ("switch data removal to local", "use hybrid data removal",
                     "send my removal emails", "send my removal requests",
                     "show my removal status", "what do I need to do by hand",
                     "sync the broker list", "check for replies"):
        got = match(sentence)
        check(f"{sentence!r} is not answered as an explanation",
              got is None or got.name != "privacy_explain",
              str(getattr(got, "name", None)))


# ---------------------------------------------------------------------------
#   5. The module-present path, unchanged
# ---------------------------------------------------------------------------


def t_the_module_present_path_is_unchanged():
    import jarvis_privacy_removal as PR

    calls = []
    real_fallback = Q._privacy_prompt_without_tool

    def spy(*args, **kwargs):
        calls.append(args)
        return real_fallback(*args, **kwargs)

    Q._privacy_prompt_without_tool = spy
    try:
        for sentence in QUESTIONS_NAMING_THE_TOOL + (
                "pros and cons of local vs optery", "should I use local or optery",
                "what are the official portals for data removal"):
            normalized = Q.normalize_spoken_command(sentence)
            want = PR.prompt(normalized, sentence)
            got = Q._privacy_prompt(normalized, sentence)
            same_fields = (got is not None and want is not None
                           and got.name == want.get("intent")
                           and got.f == {k: v for k, v in want.items()
                                         if k != "intent"})
            check(f"{sentence!r} still comes from PR.prompt with the same fields",
                  same_fields, f"want={want} got={got}")
    finally:
        Q._privacy_prompt_without_tool = real_fallback
    check("... and the fallback is NEVER called when the module imports",
          calls == [], str(calls))

    got = match(MEASURED)
    reply = Q.run(got, None, NOW).reply
    check("... the answer is still PR.privacy_explain's own words, byte for byte",
          reply == PR.privacy_explain("overview"), reply[:120])
    check("... and it is not the not-set-up sentence",
          reply != HONEST, reply[:120])


def t_the_unclaimed_neighbours_stay_unclaimed_with_the_module_present():
    for sentence in ("what is the weather", "how private are my notes",
                     "set my cap to $5", "what can you do"):
        got = Q._privacy_prompt(Q.normalize_spoken_command(sentence), sentence)
        check(f"{sentence!r} is still not the privacy lane with the module present",
              got is None, str(got))


# ---------------------------------------------------------------------------
#   The runner
# ---------------------------------------------------------------------------


def main():
    for fn in (t_the_published_base_really_does_not_carry_the_module,
               t_the_measured_sentence_reached_no_lane_before_this_fix,
               t_the_question_still_reaches_the_explainer_without_the_module,
               t_the_answer_is_the_pinned_honest_sentence,
               t_the_answer_claims_no_ability_and_no_procedure,
               t_the_reply_really_comes_from_the_explainer,
               t_the_neighbours_keep_their_own_lanes_without_the_module,
               t_a_sentence_that_needs_the_engine_is_not_claimed,
               t_the_module_present_path_is_unchanged,
               t_the_unclaimed_neighbours_stay_unclaimed_with_the_module_present):
        try:
            fn()
        except Exception:                                   # noqa: BLE001
            failed = f"{fn.__name__} raised"
            FAILED.append(failed)
            print(f"FAIL  {failed}")
            traceback.print_exc()
    summary = f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed"
    print(summary)
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED or not PASSED else 0


if __name__ == "__main__":
    sys.exit(main())
