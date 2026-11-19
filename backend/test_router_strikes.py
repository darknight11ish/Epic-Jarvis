"""test_router_strikes.py - the 2-strike local-failure fallback for coding turns.

    python3 backend/test_router_strikes.py

THE RULING THIS PROVES (external review, 2026-11-19, 6.1). Keep the
deterministic `complexity >= 0.40` pre-gate as Stage 1, and pair it with a
2-strike / local-failure fallback for coding tasks - do NOT replace it with raw
log-probs.

IN THIS CODEBASE that means: when a CODING turn has failed locally TWICE in the
same conversation (the local model returned no usable answer, or the tool path
failed), the third attempt may escalate even though its complexity score is
under 0.40 - and it must still pass EVERY safety gate, still in the same order,
and still need the owner's yes / this PC's standing switch.

WHAT THIS SUITE RUNS. The real `jarvis_router.choose()` from
`backend/rebuilt/`, with a scratch settings folder made before anything imports
(so no live file is read or written, no budget file is touched). `choose()` is
pure Python: it opens no socket, sends no message and loads no model. The only
things stood in are Lockdown and the standing switch - two module-level
readers a suite has always been allowed to fake - and they are restored after
each test.

THE GATE ORDER THIS PROVES IS STILL THE POLICY (quoted from `choose()`'s own
docstring): cloud_model, unavailable, lockdown, taint, image, file, screen,
private, secret, complexity (Stage 1), budget, the owner's yes. The fallback
sits inside the complexity stage only; every other gate is checked with and
without two recorded failures and must answer the same.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REBUILT = HERE / "rebuilt"

#: A scratch home BEFORE anything reads a settings file.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-router-strikes-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")

sys.dont_write_bytecode = True
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import jarvis_router as RT  # noqa: E402

FAILED, PASSED = [], []
LOCAL = "qwen3.5:9b"
CLOUD = RT.CLOUD_LANE
#: A coding request that is SHORT on prose: its router score is far under the
#: 0.40 threshold, which is the whole point of the fallback.
CODING = "fix this bug in my app"
#: Long, clause-heavy and plainly non-private: the complexity gate alone lets it
#: out, so a refusal below can only come from the gate named in that check.
HARD = ("Explain in detail how the three-body problem differs from the two-body "
        "problem, and why the difference matters for predicting orbits.")
#: An ordinary short question: under 0.40, not coding, so it must stay local
#: however many times something else failed.
ORDINARY = "What is a semicolon?"
PRIVATE = "What is my password for the bank?"
SECRET = "fix this bug in my app, key AKIAIOSFODNN7EXAMPLE"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh(conv):
    RT.reset_local_failures(conv)
    return conv


def choose(query, *, conversation="", coding=None, **kw):
    """`choose()` with this suite's safe defaults: one offered cloud lane and
    the owner's yes for the question (gate 6 is satisfied, so a refusal below
    can only come from a gate this suite is testing)."""
    args = dict(local_model=LOCAL, lanes=[CLOUD], owner_said_yes=True,
                conversation=conversation, coding=coding)
    args.update(kw)
    return RT.choose(query, **args)


class _Stub:
    """Replace one module-level reader for the length of the block, then put
    the real function back - even if the block raises."""

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


# ==========================================================================
#  1. the strikes: none, one, two - and the third attempt is the one that
#     may escalate, with Stage 1 still doing its own job
# ==========================================================================

def t_two_local_failures_let_the_third_attempt_escalate():
    conv = fresh("strike-basic")
    check("with no failures a coding turn under the threshold stays local",
          choose(CODING, conversation=conv).gate == "complexity",
          choose(CODING, conversation=conv).gate)
    RT.note_local_failure(conv)
    d1 = choose(CODING, conversation=conv)
    check("ONE failure does NOT escalate: it can be a load or a cancelled request",
          d1.gate == "complexity" and d1.lane == LOCAL, (d1.gate, d1.lane))
    RT.note_local_failure(conv)
    d2 = choose(CODING, conversation=conv, coding=True)
    check("TWO failures let the third attempt reach the cloud even under 0.40",
          d2.gate == "escalate" and d2.lane == CLOUD, (d2.gate, d2.lane))
    check("... and the route reason says why, in plain words",
          "failed on this PC 2 times" in d2.reason and "under the threshold" in d2.reason,
          d2.reason)
    check("... its complexity is still reported honestly, under the threshold",
          d2.complexity < 0.40, d2.complexity)


def t_stage_one_is_still_the_pre_gate():
    conv = fresh("strike-stage1")
    d = choose(HARD, conversation=conv)
    check("a HARD question escalates on complexity alone, as before",
          d.gate == "escalate" and d.lane == CLOUD, (d.gate, d.lane))
    check("... with no strike recorded for the conversation",
          RT.local_failure_strikes(conv) == 0, RT.local_failure_strikes(conv))
    under = choose(ORDINARY, conversation=fresh("strike-control"))
    check("the control: an ordinary short question under 0.40 stays local",
          under.gate == "complexity" and under.lane == LOCAL,
          (under.gate, under.lane))
    # Two strikes do not REMOVE Stage 1's own behaviour either: a hard question
    # still escalates on complexity, and the fallback is not needed to say so.
    RT.note_local_failure(conv)
    RT.note_local_failure(conv)
    d2 = choose(HARD, conversation=conv, coding=True)
    check("two strikes leave a HARD question's Stage-1 escalation unchanged",
          d2.gate == "escalate" and d2.lane == CLOUD
          and "under the threshold" not in d2.reason,
          (d2.gate, d2.reason))


def t_a_non_coding_turn_does_not_get_the_fallback():
    conv = fresh("strike-noncoding")
    RT.note_local_failure(conv)
    RT.note_local_failure(conv)
    d = choose(ORDINARY, conversation=conv, coding=False)
    check("two failures on a NON-coding turn do not escalate it",
          d.gate == "complexity" and d.lane == LOCAL, (d.gate, d.lane))


def t_a_private_turn_stays_local_after_two_failures():
    conv = fresh("strike-private")
    RT.note_local_failure(conv)
    RT.note_local_failure(conv)
    d = choose(PRIVATE, conversation=conv, coding=True)
    check("a private turn with two failures STILL stays on this PC",
          d.gate == "private" and d.lane == LOCAL, (d.gate, d.lane))


def t_the_fallback_still_needs_the_owners_yes():
    conv = fresh("strike-yes")
    RT.note_local_failure(conv)
    RT.note_local_failure(conv)
    with _Stub("standing_escalation", lambda: False):
        d = RT.choose(CODING, local_model=LOCAL, lanes=[CLOUD],
                      conversation=conv, coding=True)
    check("two failures are not a standing permission: without a yes the turn "
          "is answered locally, with the cloud lane OFFERED",
          d.gate == "offer" and d.lane == LOCAL and d.offer == CLOUD,
          (d.gate, d.lane, d.offer))
    # The owner typing the request for the cloud is still a yes for that turn.
    d2 = choose(CODING + " - send this to the cloud", conversation=conv, coding=True)
    check("... and asking for the cloud in the message is still a yes",
          d2.gate == "escalate" and d2.lane == CLOUD, (d2.gate, d2.lane))


# ==========================================================================
#  2. every safety gate still runs, twice-failed coding turn or not
# ==========================================================================

def t_every_safety_gate_still_runs_after_two_failures():
    conv = fresh("strike-gates")
    RT.note_local_failure(conv)
    RT.note_local_failure(conv)

    def gate(**kw):
        args = dict(conversation=conv, coding=True)
        args.update(kw)
        return RT.choose(CODING, local_model=LOCAL, lanes=[CLOUD],
                         owner_said_yes=True, **args).gate

    checks = (
        ("taint", gate(conversation_tainted=True), "taint"),
        ("image", gate(has_image=True), "image"),
        ("file", gate(has_file=True), "file"),
        ("screen", gate(has_screen=True), "screen"),
        ("private", choose(PRIVATE, conversation=conv, coding=True).gate, "private"),
        ("secret", choose(SECRET, conversation=conv, coding=True).gate, "secret"),
        ("budget", gate(budget=RT.Budget(path=None, per_day=1,
                                         day_hits=[time.time()])), "budget"),
        ("cloud model as the local lane",
         RT.choose(CODING, local_model="gpt-oss:120b-cloud", lanes=[CLOUD],
                   owner_said_yes=True, conversation=conv, coding=True).gate,
         "cloud_model"),
        ("no cloud lane offered",
         RT.choose(CODING, local_model=LOCAL, lanes=[], owner_said_yes=True,
                   conversation=conv, coding=True).gate,
         "unavailable"),
    )
    tried = 0
    for label, got, want in checks:
        tried += 1
        check(f"two failures do not lift the {label} gate", got == want, (got, want))
    with _Stub("lockdown_on", lambda: True):
        got = RT.choose(CODING, local_model=LOCAL, lanes=[CLOUD],
                        owner_said_yes=True, conversation=conv, coding=True).gate
    tried += 1
    check("two failures do not lift Lockdown", got == "lockdown", got)
    check("... so every safety gate was really checked", tried == 10, tried)


# ==========================================================================
#  3. keying, reset and bounds
# ==========================================================================

def t_the_count_is_keyed_per_conversation_and_resets():
    a = fresh("conv-a")
    b = fresh("conv-b")
    RT.note_local_failure(a)
    RT.note_local_failure(a)
    check("the count is kept per conversation", RT.local_failure_strikes(a) == 2,
          RT.local_failure_strikes(a))
    check("a NEW conversation starts at zero - the required reset",
          RT.local_failure_strikes(b) == 0
          and choose(CODING, conversation=b, coding=True).gate == "complexity",
          (RT.local_failure_strikes(b), choose(CODING, conversation=b, coding=True).gate))
    RT.reset_local_failures(a)
    check("reset forgets one conversation explicitly",
          RT.local_failure_strikes(a) == 0, RT.local_failure_strikes(a))


def t_the_counter_is_bounded_and_holds_only_counts():
    conv = fresh("strike-bounded")
    seen = []
    for _ in range(RT.STRIKES_FOR_FALLBACK):
        seen.append(RT.note_local_failure(conv))
    check("each failure returns the count it became",
          seen == [1, 2], seen)
    for i in range(300):
        RT.note_local_failure(f"conversation-{i}")
    check(f"the store is bounded to {RT._STRIKES_MAX_CONVERSATIONS} conversations",
          len(RT._LOCAL_FAILURES) <= RT._STRIKES_MAX_CONVERSATIONS,
          len(RT._LOCAL_FAILURES))
    check("... every value is a count, never a word of the conversation",
          all(isinstance(v, int) for v in RT._LOCAL_FAILURES.values()),
          list(RT._LOCAL_FAILURES.values())[:3])
    check("... and every key is short and printable",
          all(isinstance(k, str) and len(k) <= 120 and k.isprintable()
              for k in RT._LOCAL_FAILURES))
    RT._LOCAL_FAILURES.clear()


# ==========================================================================
#  4. the coding definition is the existing one, not a new classifier
# ==========================================================================

def t_coding_is_read_from_the_existing_signals():
    check("a coding request is recognised by the Coding preset's own words",
          RT.is_coding_turn("write a python script to sort a list") is True,
          RT.is_coding_turn("write a python script to sort a list"))
    check("an ordinary question is not coding",
          RT.is_coding_turn(ORDINARY) is False, RT.is_coding_turn(ORDINARY))
    check("a coder model loaded as the local lane is coding",
          RT.is_coding_turn(ORDINARY, local_model="qwen3-coder-30b-a3b") is True,
          RT.is_coding_turn(ORDINARY, local_model="qwen3-coder-30b-a3b"))
    check("a caller that KNOWS (the tool in play) wins over the word match",
          RT.is_coding_turn("anything at all", coding=False) is False
          and RT.is_coding_turn(ORDINARY, coding=True) is True)


# ==========================================================================
#  5. the shipped module and its published-base twin are one file
# ==========================================================================

def t_the_twins_match():
    here = (REBUILT / "jarvis_router.py").read_bytes()
    base = (REPO / "jarvis-backend" / "jarvis_router.py").read_bytes()
    check("backend/rebuilt/jarvis_router.py and jarvis-backend/ are byte identical",
          here == base, (len(here), len(base)))


# ==========================================================================

TESTS = [
    t_two_local_failures_let_the_third_attempt_escalate,
    t_stage_one_is_still_the_pre_gate,
    t_a_non_coding_turn_does_not_get_the_fallback,
    t_a_private_turn_stays_local_after_two_failures,
    t_the_fallback_still_needs_the_owners_yes,
    t_every_safety_gate_still_runs_after_two_failures,
    t_the_count_is_keyed_per_conversation_and_resets,
    t_the_counter_is_bounded_and_holds_only_counts,
    t_coding_is_read_from_the_existing_signals,
    t_the_twins_match,
]


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(f"{fn.__name__} raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
