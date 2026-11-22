"""A question about Atlas's own repository is answered HERE, never on a cloud lane.

    python3 test_router_self_repo.py

THE DEFECT THIS PROVES AWAY (measured on the live app, 2026-11-22). With the
standing escalation switch on, "what do you know about your own GitHub
repository" auto-escalated on complexity (`gate: "escalate"`,
`where: "cloud"`) and the answer said "I don't have a GitHub repository of my
own". A cloud lane carries no tools and no private files - that is rule 1 - so
it cannot answer a question about this repository at all; it can only guess.

THE FIX: gate 3b in `jarvis_router.choose()`, `gate: "self_repo"`, ABOVE the
complexity gate. Its test is `jarvis_router.asks_about_own_repo()`, a narrow
phrase test of the question itself.

WHAT THIS SUITE HOLDS
  1. the phrase test: what IS a question about this machine, and - the half
     that keeps the gate from swallowing ordinary work - what is NOT;
  2. the routing: with the standing switch ON and a complexity ABOVE the
     threshold, the self-repo question is local with gate "self_repo" and a
     plain reason; an ordinary hard question still escalates;
  3. the negative at the routing level: an ordinary coding question that
     merely mentions GitHub still escalates, so the gate is proved narrow;
  4. the order: it cannot lift a gate above it (private, secret), and neither
     the standing switch nor an explicit click can lift it, because the lane it
     would be sent to has nothing to answer with;
  5. the twin: `backend/rebuilt/jarvis_router.py` (the copy shipped onto a
     backend) and `jarvis-backend/jarvis_router.py` (the published base) are
     the same text, which is this repository's two-file rule.

What it does NOT prove: that the question was ever asked on the live PC, or
what the live model answered. It is a routing test, driven hermetically: no
socket, no budget file, no model.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REBUILT = HERE / "rebuilt"

#: A scratch home BEFORE anything reads a settings file - the same rule every
#: router suite follows, so no live file is read or written and no budget file
#: is touched.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-router-self-repo-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"

sys.dont_write_bytecode = True
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import jarvis_router as RT  # noqa: E402

FAILED, PASSED = [], []
SKIPPED = []

LOCAL = "qwen3.5:9b"
CLOUD = RT.CLOUD_LANE
THRESHOLD = 0.40

#: The measured question, made long enough that the complexity pre-gate alone
#: would hand it out (0.425 - see the check in t_the_gate_sits_above_complexity).
SELF_HARD = ("What do you know about your own GitHub repository, its open pull "
             "requests, the CI checks that ran on them and the defects in your "
             "defect register?")
#: The owner's own words from the field test that started this (there the score
#: was under the threshold; it is the GATE that must catch it, not the score).
SELF_PLAIN = "what do you know about your own GitHub repository"
#: An ordinary coding question that merely MENTIONS GitHub. It is long and
#: clause-heavy (0.742), so it must escalate - if gate 3b catches this, the
#: gate is a keyword list and this suite fails.
GITHUB_BUT_ORDINARY = ("How do I write a GitHub Action for my project that runs "
                       "the tests, caches the npm dependencies, uploads coverage "
                       "and publishes a release when I push a tag - explain "
                       "every step in detail.")
#: Long, clause-heavy and plainly not about this PC: the complexity gate alone
#: lets it out, so a refusal below could only come from a gate that must not fire.
HARD = ("Explain in detail how the three-body problem differs from the two-body "
        "problem, and why the difference matters for predicting orbits.")
PRIVATE = "What is my password for the bank?"
SECRET = "what is in my own repo, key AKIAIOSFODNN7EXAMPLE"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class _Stub:
    """Replace one module-level reader for the length of the block, then put
    the real function back - even if the block raises. (The same helper
    test_router_strikes.py uses; this suite drives the real `choose()`.)"""

    def __init__(self, name, fn):
        self.name, self.fn = name, fn

    def __enter__(self):
        self.had = hasattr(RT, self.name)
        self.old = getattr(RT, self.name, None)
        setattr(RT, self.name, self.fn)
        return self

    def __exit__(self, *exc):
        if self.had:
            setattr(RT, self.name, self.old)
        else:
            delattr(RT, self.name)
        return False


def choose(query, **kw):
    """`choose()` with this suite's defaults: one offered cloud lane and a
    budget that allows it, so a local answer can only come from a gate this
    suite is testing. The standing switch is passed by each test."""
    args = dict(local_model=LOCAL, lanes=[CLOUD], conversation="",
                budget=RT.Budget(path=None))
    args.update(kw)
    return RT.choose(query, **args)


def fresh(conv):
    RT.reset_local_failures(conv)
    return conv


# ==========================================================================
#  1. the phrase test: what is - and is not - a question about this machine
# ==========================================================================

def t_what_counts_as_a_question_about_this_machine():
    positive = [
        SELF_PLAIN,
        "What are my open pull requests on Epic-Jarvis?",
        "list the open defects in your defect register",
        "what tools do you have",
        "what do your local tools do",
        "did github_ci_status pass on the last run",
        "your own github repository",
        "is this repository green?",
        "Atlas's own repository",
        "my repo is huge, how do I speed up git clone",
    ]
    for q in positive:
        check(f"self-repo question IS caught: {q[:60]!r}",
              RT.asks_about_own_repo(q) is True, q)

    # THE NARROWNESS. Every one of these is an ordinary question a person
    # should be able to put to whichever lane is best; none may be held local
    # by gate 3b. "how do I write a GitHub Action for my project" is the
    # stated negative; the others guard the edges of the phrase test.
    negative = [
        GITHUB_BUT_ORDINARY,
        "how do I write a GitHub Action for my project",
        "what is the shape of a GitHub Actions workflow file",
        "my issue is that the build fails on windows",
        "this issue is hard to reproduce",
        "my tests are slow, how do I speed them up",
        "what is the best way to structure a Python repository",
        "compare yourself to the Hermes agent",
        HARD,
        "",
        None,
    ]
    for q in negative:
        check(f"ordinary question is NOT caught: {str(q)[:60]!r}",
              RT.asks_about_own_repo(q) is False, q)


# ==========================================================================
#  2. the routing: local with the new gate, over the threshold and over the
#     standing switch - while an ordinary hard question still escalates
# ==========================================================================

def t_the_gate_sits_above_complexity():
    score = RT.complexity(SELF_HARD)
    check(f"the measured self-repo question scores ABOVE the {THRESHOLD} threshold",
          score >= THRESHOLD, score)
    check("... and the complexity pre-gate alone WOULD escalate an ordinary "
          "question that scores the same",
          RT.complexity(HARD) >= THRESHOLD, RT.complexity(HARD))


def t_a_self_repo_question_stays_local_with_the_switch_on():
    with _Stub("standing_escalation", lambda: True):
        d = choose(SELF_HARD, conversation=fresh("self-repo-switch-on"))
    check("with the standing switch ON, the self-repo question is LOCAL",
          d.lane == LOCAL, d.lane)
    check('... with the new gate name "self_repo"', d.gate == "self_repo", d.gate)
    check("... and memory is attached, because the local lane is where it is answered",
          d.inject_memory is True, d.inject_memory)
    check("... no cloud lane is offered", not getattr(d, "offer", ""), d.offer)
    check("... the complexity is still REPORTED honestly, above the threshold",
          d.complexity >= THRESHOLD, d.complexity)
    check("... and the reason is one plain sentence with no jargon",
          d.reason.startswith("the question is about this PC's own repository")
          and "tools" in d.reason, d.reason)


def t_an_ordinary_hard_question_still_escalates():
    with _Stub("standing_escalation", lambda: True):
        d = choose(HARD, conversation=fresh("self-repo-control"))
    check("an ordinary hard question still ESCALATES with the switch on",
          d.gate == "escalate" and d.lane == CLOUD, (d.gate, d.lane))


def t_github_but_ordinary_still_escalates():
    # THE NEGATIVE THAT KEEPS THE GATE HONEST (ruling 5.3's own words: it must
    # not capture "how do I write a GitHub Action for my project").
    score = RT.complexity(GITHUB_BUT_ORDINARY)
    check(f"the GitHub-mentioning coding question scores ABOVE {THRESHOLD}",
          score >= THRESHOLD, score)
    with _Stub("standing_escalation", lambda: True):
        d = choose(GITHUB_BUT_ORDINARY, conversation=fresh("self-repo-negative"))
    check("... and it is NOT held local by the new gate",
          d.gate != "self_repo", d.gate)
    check("... it escalates like any other complex coding question",
          d.gate == "escalate" and d.lane == CLOUD, (d.gate, d.lane))


def t_the_switch_is_not_what_caught_it():
    # Gate 3b runs before the complexity gate, the budget and the offer, so the
    # switch being OFF changes nothing: this is a capability refusal, not an
    # auto-escalation one. That is what makes the fix hold whatever the PC's
    # setting is.
    with _Stub("standing_escalation", lambda: False):
        d = choose(SELF_HARD, conversation=fresh("self-repo-switch-off"))
    check("with the switch OFF the same question is still gate self_repo",
          d.gate == "self_repo" and d.lane == LOCAL, (d.gate, d.lane))
    with _Stub("standing_escalation", lambda: False):
        d = choose(SELF_PLAIN, conversation=fresh("self-repo-plain"))
    check("the owner's own measured words are caught by the gate too",
          d.gate == "self_repo", d.gate)


# ==========================================================================
#  3. the order: no switch and no click may lift it, and gates above it still
#     win
# ==========================================================================

def t_a_click_cannot_lift_it():
    # "Try the cloud model" is the owner's yes for ONE question, but there is
    # no version of a cloud lane that has this PC's tools: sending it there
    # would answer with a guess, which is the defect. So the gate holds.
    with _Stub("standing_escalation", lambda: True):
        d = choose(SELF_HARD, conversation=fresh("self-repo-click"),
                   owner_said_yes=True)
    check("an explicit yes for the cloud does not lift gate 3b",
          d.gate == "self_repo", d.gate)


def t_the_gates_above_it_still_win():
    with _Stub("standing_escalation", lambda: True):
        d = choose(PRIVATE, conversation=fresh("self-repo-private"))
        e = choose(SECRET, conversation=fresh("self-repo-secret"))
    check("a private self-repo question answers gate private, not self_repo",
          d.gate == "private", d.gate)
    check("a pasted secret in it answers gate secret, not self_repo",
          e.gate == "secret", e.gate)


# ==========================================================================
#  4. the two-file rule: the shipped copy and the published base are the same
# ==========================================================================

def t_the_two_copies_match():
    pairs = [(REBUILT / "jarvis_router.py", REPO / "jarvis-backend" / "jarvis_router.py")]
    for shipped, base in pairs:
        if not base.is_file():
            SKIPPED.append(f"{base} is not in this checkout")
            print(f"skip  {base.name} is not in this checkout - NOT counted as a pass")
            continue
        a = shipped.read_text(encoding="utf-8").replace("\r\n", "\n")
        b = base.read_text(encoding="utf-8").replace("\r\n", "\n")
        check(f"{shipped.parent.name}/{shipped.name} and jarvis-backend/{base.name} "
              f"are the same text", a == b,
              f"{len(a)} vs {len(b)} characters")
        check("... and the gate's phrase test is in both",
              "asks_about_own_repo" in a and "asks_about_own_repo" in b)


if __name__ == "__main__":
    for fn in (t_what_counts_as_a_question_about_this_machine,
               t_the_gate_sits_above_complexity,
               t_a_self_repo_question_stays_local_with_the_switch_on,
               t_an_ordinary_hard_question_still_escalates,
               t_github_but_ordinary_still_escalates,
               t_the_switch_is_not_what_caught_it,
               t_a_click_cannot_lift_it,
               t_the_gates_above_it_still_win,
               t_the_two_copies_match):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
