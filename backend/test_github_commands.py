#!/usr/bin/env python3
"""test_github_commands.py - a command to GitHub is not a question ABOUT GitHub.

    python3 backend/test_github_commands.py

WHY THIS EXISTS. On the live app, with the local coding lane selected, three
real messages were each answered in 0.1 seconds with the same canned paragraph
("Yes - with ONE approval card per merge, and merge commit only ..."):

  1. "Merge pull request 1472 in darknight11ish/Epic-Jarvis with a merge
     commit. All seven required checks are green. Use github_merge_pr."
  2. "Merge pull request 1472 in darknight11ish/Epic-Jarvis now, with a merge
     commit. All seven required checks are green."
  3. "Merge #1472 in darknight11ish/Epic-Jarvis with a merge commit."

The route header said `"lane": "no AI model"`, `"quick": "github_self"`: no
model ran, no tool was offered and no approval card was raised, so the merge
the owner asked for could not happen. In the same battery "Post this comment on
pull request 1471: <text>" DID reach the model, called `github_comment` and
raised the card he approved - the difference was a command the capability
family should never have claimed. Same class as the reminder-closed bug fixed
in #1468.

THE RULE (the external review's ruling of 2026-11-22, 15:45 PT), ONE gate for
the whole family rather than a patch inside one shape: a capability-explanation
intent may answer only a message that is a QUESTION and names no concrete
target.

  * QUESTION means the RAW message opens as one ("can/could/would/will/do/
    does/did/have/has/are/is/am/was/were/should", or "what/which/how/why/
    when/where/who/whose") after the address/politeness lead is removed. It is
    read from the raw text because `normalise()` strips "can you" and "please":
    the question "can you merge a pull request?" and the command "merge a pull
    request" become the same matched string, and only the raw message can tell
    them apart.
  * NO CONCRETE TARGET means no pull request/issue number ("#1472", "PR 1471",
    "pull request 1472", "issue 5"), no "owner/repo" slug, and no branch (the
    word, or main/master named after a to/into/onto).
  * In the review's own terms: a message that names one of those targets, or
    begins with an imperative action verb ("merge", "comment", "post",
    "re-run"/"rerun", "open", "create", "fix", "push"), must never match
    `github_self` or `feature_capabilities`.

THE TWO FAMILIES are `github_self` (every "what can you do on GitHub" answer,
including merge/action/never/tools) and `feature_capabilities` (the feature-list
answer behind "what can you do with GitHub?"). The gate is `_capability_answer_
forbidden`, applied once in `match()` - the public door every caller uses - so a
new shape or a new door inherits it.

THREE SHAPES ARE EXEMPT, and the suite pins why: `create_repo` raises the
owner's switch card IN PLACE (an action path, not an explanation, and the bare
"create a repository" form only exists because `normalise()` strips "can you"),
and `approve`, `destroy`, `bulk_close`, `close_pr` answer a permanently
impossible action with a "No" - no tool behind them for the model to reach, and
`test_chat_wrong_answers.py` pins each one from the 2026-11-16 measurements.

WHAT THIS SUITE PROVES, all read-only, with no network and no model:

  1. the three measured messages are not claimed at all - `Q.match` is None AND
     `Q.answer_turn` (the /api/chat door) is None, the fast path's own "the
     model has this turn";
  2. every imperative command in the review's class is the model's turn too,
     including the ones that name no target ("merge my pull request", "open an
     issue about the login bug", "push this to main") and the measured re-run
     and comment messages; where the family matcher itself WOULD produce an
     intent, this suite proves the GATE is what drops it;
  3. the family-wide scope is real: the helper forbids the same command for a
     `feature_capabilities` intent as for `github_self`, and leaves every other
     intent alone;
  4. the interrogative capability questions this family exists for still
     answer, from the module's own words (merge, comment, tools, never-list,
     needs, repository, CI, asks-first) and the feature-list answers too;
  5. the raw message, not the normalised one, is what separates the question
     from the command ("can you merge a pull request?" vs "merge a pull
     request" are the same normalised string);
  6. the permanent refusals and the create-repo switch card keep their shapes,
     including the target-naming forms ("approve PR 12", "close pull request
     1299").

This suite is about THIS repository's grammar, so it never reads an installed
backend: `JARVIS_BACKEND` is cleared before anything is imported, and every
module comes from this folder (as CI runs it). Nothing here opens a socket,
raises a card, types a secret or calls a model.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-github-commands-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ.pop("JARVIS_BACKEND", None)
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))

import jarvis_quick as Q  # noqa: E402

#: A fixed clock, so nothing here depends on the day the suite runs.
NOW = time.mktime(time.strptime("2026-11-22 15:30:00", "%Y-%m-%d %H:%M:%S"))

PASSED, FAILED = [], []

#: The three messages the owner actually typed on the live app (2026-11-22),
#: copied exactly - including the repository, the pull request number and the
#: tool name in the first one.
THE_THREE_MEASURED_MESSAGES = (
    "Merge pull request 1472 in darknight11ish/Epic-Jarvis with a merge commit. "
    "All seven required checks are green. Use github_merge_pr.",
    "Merge pull request 1472 in darknight11ish/Epic-Jarvis now, with a merge "
    "commit. All seven required checks are green.",
    "Merge #1472 in darknight11ish/Epic-Jarvis with a merge commit.",
)

#: Commands in the review's class: a target, a listed imperative verb, or both.
#: "re-run the workflow on pull request 1471" and "comment on pull request
#: 1471" are the measured re-run/comment negatives; the rest prove that the
#: verb alone is enough ("merge my pull request" has no number, slug or branch)
#: and that a command with neither a target nor a family word ("push this to
#: main", "fix the failing test") is not pulled back in.
COMMANDS = (
    "comment on pull request 1471",
    "re-run the workflow on pull request 1471",
    "rerun the failing workflow",
    "post this comment on pull request 1471: looks good",
    "merge my pull request",
    "merge the pull request",
    "comment on the pull request",
    "open an issue about the login bug",
    "close issue 5",
    "merge pull request 1472 in darknight11ish/Epic-Jarvis",
    "merge into main",
    "push this to main",
    "fix the failing test",
)

#: The capability questions this family exists for: (sentence, shape, a phrase
#: the real answer must carry). Every one opens as a question.
CAPABILITY_QUESTIONS = (
    # The review's own example, and the pinned capability wording: normalise()
    # strips "can you" and "for me", leaving "merge a pull request".
    ("can you merge a pull request for me?", "merge", "one approval card"),
    ("can you merge a pull request?", "merge", "merge commit"),
    # A question about a merge that already happened, naming "that PR" but no
    # number, repository or branch.
    ("did you merge that PR?", "merge", "one approval card"),
    ("can you comment on an issue?", "action", "approval card"),
    ("what GitHub tools do you have?", "tools", "github_merge_pr"),
    ("what can't you do on GitHub?", "never", "force-push"),
    ("what do you need before you can read my repos?", "needs",
     "personal access token"),
    ("what is your GitHub repository?", "repo", "darknight11ish/Epic-Jarvis"),
    ("what's your CI status?", "ci", "GitHub Actions"),
    ("what asks before GitHub acts?", "asks", "ask you first every time"),
)

#: The feature-list family's own capability answers (the second family the
#: family-wide gate covers). Both forms are interrogative.
FEATURE_CAPABILITY_QUESTIONS = (
    "what can you do with GitHub?",
    "what can you do with my GitHub?",
    "what can you edit in my notes?",
    "can you add something to my calendar?",
)

#: The permanent refusals. Each answers a permanently impossible action with a
#: "No"; the target-naming forms are the ones a family-wide target rule would
#: have handed to a model that has no such tool.
REFUSALS = (
    ("approve that pull request", "approve"),
    ("approve PR 12", "approve"),
    ("delete the repo", "destroy"),
    ("delete pr 12", "destroy"),
    ("close all the pull requests", "bulk_close"),
    ("close pull request 1299", "close_pr"),
)

#: `create_repo` raises the owner's switch card in place: an action path, not an
#: explanation. Both the question and the bare form it normalises to keep it.
CREATE_REPO = (
    "create a repository",
    "can you create a repository?",
    "set up a new github repository",
    "are you able to create a repository?",
)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _turn(sentence):
    """What /api/chat would get from the fast path: None means the model's turn.

    `provenance: "typed"` is what the desktop sends and what the fast path
    requires before it may act on the owner's own words (`newest_own_words`);
    without it every turn is the model's, which would make this assertion say
    nothing.
    """
    body = {"messages": [{"role": "user", "content": sentence,
                          "provenance": "typed"}]}
    return Q.answer_turn(body, now=NOW, peer="127.0.0.1", local=True)


def _shape(intent):
    return None if intent is None else intent.f.get("shape")


def _gate():
    """The family-wide helper, or None on a tree that does not carry it yet.

    Returning None instead of raising is deliberate: on the tree BEFORE the fix
    this suite must report the checks that fail, not die at the first reference
    to a helper that did not exist. `None` never satisfies an `is True` or
    `is False` check, so the missing gate reads as a failure.
    """
    return getattr(Q, "_capability_answer_forbidden", None)


def _forbidden(sentence, intent):
    helper = _gate()
    return None if helper is None else helper(sentence, intent)


# --------------------------------------------------------------------------
#   1. the three measured messages are the model's turn again
# --------------------------------------------------------------------------
def t_the_three_measured_messages_reach_the_model():
    for sentence in THE_THREE_MEASURED_MESSAGES:
        intent = Q.match(sentence)
        check(f"measured message is not claimed: {sentence[:58]!r}...",
              intent is None,
              None if intent is None else f"{intent.name} {intent.f}")
        turn = _turn(sentence)
        check(f"... and /api/chat gets no fast-path answer for it",
              turn is None, None if turn is None else str(turn.reply)[:200])


# --------------------------------------------------------------------------
#   2. every imperative command in the review's class is the model's turn
# --------------------------------------------------------------------------
def t_imperative_commands_reach_the_model():
    for sentence in COMMANDS:
        intent = Q.match(sentence)
        check(f"command is not claimed: {sentence!r}",
              intent is None,
              None if intent is None else f"{intent.name} {intent.f}")
        turn = _turn(sentence)
        check(f"... and /api/chat gets no fast-path answer for it",
              turn is None, None if turn is None else str(turn.reply)[:200])
        # Where the family matcher itself WOULD answer, prove the gate is what
        # drops it - not a matcher that happens to miss the sentence.
        inner = Q._self_github(Q.normalize_spoken_command(sentence))
        if inner is not None:
            check(f"... the family matcher would answer {sentence!r}, "
                  f"and the family-wide gate drops it",
                  _forbidden(sentence, inner) is True, inner)


# --------------------------------------------------------------------------
#   3. the interrogative capability questions still answer
# --------------------------------------------------------------------------
def t_the_capability_questions_still_answer():
    for sentence, shape, needle in CAPABILITY_QUESTIONS:
        intent = Q.match(sentence)
        got = None if intent is None else intent.name
        check(f"{sentence!r} is still the GitHub answer",
              got == "github_self", got)
        check(f"{sentence!r} is still the {shape} shape",
              _shape(intent) == shape, None if intent is None else intent.f)
        reply = "" if intent is None else str(Q.run(intent, None, 0.0).reply)
        check(f"{sentence!r} still answers with the real facts",
              needle.lower() in reply.lower(), reply[:300])


# --------------------------------------------------------------------------
#   4. the feature-list family still answers what GitHub can do
# --------------------------------------------------------------------------
def t_the_feature_list_still_answers():
    for sentence in FEATURE_CAPABILITY_QUESTIONS:
        intent = Q.match(sentence)
        check(f"{sentence!r} is still the feature-list answer",
              intent is not None and intent.name == "feature_capabilities",
              None if intent is None else intent.name)
        reply = "" if intent is None else str(Q.run(intent, None, 0.0).reply)
        check(f"{sentence!r} still answers, and not with the merge paragraph",
              bool(reply.strip())
              and "one approval card per merge" not in reply.lower(),
              reply[:300])


# --------------------------------------------------------------------------
#  5. the gate is family-wide: both intents, and ONLY those two
# --------------------------------------------------------------------------
def t_the_gate_covers_both_families_and_no_other():
    families = getattr(Q, "_CAPABILITY_EXPLANATION_INTENTS", None)
    check("the gate names exactly the two capability-explanation families",
          families == {"github_self", "feature_capabilities"}, families)
    github_merge = Q.Intent("github_self", {"shape": "merge"})
    feature = Q.Intent("feature_capabilities", {"words": "notes"})
    note = Q.Intent("note_create", {"name": "Shopping"})
    check("a command is forbidden for github_self",
          _forbidden("merge #1472", github_merge) is True)
    check("the same command is forbidden for feature_capabilities",
          _forbidden("merge #1472", feature) is True)
    check("a command the feature list could otherwise claim is forbidden for it",
          _forbidden("create a note called Shopping", feature) is True)
    check("a question is allowed for github_self",
          _forbidden("can you merge a pull request?", github_merge) is False)
    check("a question is allowed for feature_capabilities",
          _forbidden("what can you do with notes?", feature) is False)
    check("a different family is never gated",
          _forbidden("create a note called Shopping", note) is False)


# --------------------------------------------------------------------------
#  6. the RAW message separates the question from the command
# --------------------------------------------------------------------------
def t_the_gate_reads_the_raw_message():
    """The reason a "no imperatives" test on the matched string cannot work.

    `normalise()` strips "can you" and "for me", so the owner's question and
    the bare command become EXACTLY the same string; only the raw message still
    says which one he sent.
    """
    question = "can you merge a pull request for me?"
    check("the question and the command normalise to the same string",
          Q.normalise(question) == Q.normalise("merge a pull request")
          == "merge a pull request",
          (Q.normalise(question), Q.normalise("merge a pull request")))
    check("the QUESTION still gets the merge answer",
          _shape(Q.match(question)) == "merge", Q.match(question))
    check("the COMMAND is the model's turn",
          Q.match("merge a pull request") is None, Q.match("merge a pull request"))
    for sentence in ("please merge a pull request", "jarvis, merge a pull request",
                     "hey jarvis merge a pull request"):
        check(f"an addressed/polite command is still a command: {sentence!r}",
              Q.match(sentence) is None, Q.match(sentence))


# --------------------------------------------------------------------------
#  7. the exemptions are measured behaviour, not loopholes
# --------------------------------------------------------------------------
def t_the_permanent_refusals_are_untouched():
    for sentence, shape in REFUSALS:
        intent = Q.match(sentence)
        check(f"refusal keeps its shape: {sentence!r}",
              intent is not None and intent.name == "github_self"
              and _shape(intent) == shape,
              None if intent is None else f"{intent.name} {intent.f}")
        turn = _turn(sentence)
        check(f"... and it still answers 'No' rather than reaching the model",
              turn is not None and str(turn.reply).lower().startswith("no"),
              None if turn is None else str(turn.reply)[:160])


def t_the_create_repo_switch_card_is_untouched():
    """The one ACTION shape inside the gated family: it raises a real card.

    `test_github_off_switch_card.py` proves the card itself; this proves the
    gate never takes the sentence away from it, in the question form the owner
    used or the bare form `normalise()` turns it into.
    """
    for sentence in CREATE_REPO:
        intent = Q.match(sentence)
        check(f"create-repo keeps its switch-card shape: {sentence!r}",
              intent is not None and intent.name == "github_self"
              and _shape(intent) == "create_repo",
              None if intent is None else f"{intent.name} {intent.f}")


# --------------------------------------------------------------------------

def main() -> int:
    try:
        t_the_three_measured_messages_reach_the_model()
        t_imperative_commands_reach_the_model()
        t_the_capability_questions_still_answer()
        t_the_feature_list_still_answers()
        t_the_gate_covers_both_families_and_no_other()
        t_the_gate_reads_the_raw_message()
        t_the_permanent_refusals_are_untouched()
        t_the_create_repo_switch_card_is_untouched()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
