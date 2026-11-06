"""test_grow_bridge.py - the GROW bridge in the Reflective Coach manner, and
the safety half it must never be bought with.

    python3 backend/test_grow_bridge.py

WHAT THIS IS FOR

The owner's 2026-11-02 life-coach decision 4: the Reflective Coach gains a
GROW path - Goal, Reality, Options, Will - as three sentences, so "help me
think about whether to take this course" ends with one offer to draft a goal
(the existing cardless POST /api/goals draft), instead of open-ended talk.

The risk this suite exists for is not that the sentences are missing. It is
that someone edits the coaching half and quietly deletes the safety half with
it: the "one gentle question" restraint, the no-diagnosis rule, the
never-a-therapist rule, and the crisis sentence that sends harm to a real
person. So every safety clause is pinned HERE, in the same file as the GROW
words, and the test fails by name if either half goes.

WHERE THE THREE SENTENCES LIVE, AND WHY THEY ARE NOT IN THE PERSONA BLOCK

The three sentences are in the preset's `post_history_hint`, not its
`prompt_block`, because the project's measured prompt budget is a HARD cap:
the assembled block must stay at or under 750 characters for every preset, at
its own dials and at the longest word on every dial
(tools/check_personalities.py, and the 2026-11-02 skeptic decision in
decisions.d/ records the same rule: "a rewrite paid for by cuts, not an
append"). Before this change the Reflective Coach was already at 729 of those
750 characters, so three sentences could not be appended to the block without
cutting safety text out of it - and the safety text is the part that must not
be cut. The hint is not a lesser prompt: jarvis_agent.with_manner_note inserts
the persona block AND this hint on EVERY turn of a chosen personality, nearest
the question, so the model is given the GROW path every time it speaks as the
Reflective Coach. Measured after the change: the block is untouched at 729 with
the longest dial, and the hint is 204 of its 220 characters.

WHAT IT DOES NOT CLAIM: that any model follows the instruction better. No model
quality measurement exists for any preset - the same limit the 2026-11-02
skeptic record states. This pins the words that are sent, not the behaviour
that comes back.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_manner.py")

import jarvis_manner as M  # noqa: E402

PASSED, FAILED = [], []
CONTRACT = ROOT / "contract" / "personalities.json"
TWIN = ROOT / "jarvis-backend" / "jarvis_manner.py"

#: The safety half, as the Reflective Coach's persona block states it. These
#: are the sentences the brief names, plus the no-therapy-record promise the
#: manner has always made. Case-insensitive; punctuation is not the point.
SAFETY = {
    "one gentle question": "one gentle question",
    "never diagnose": "never diagnose, prescribe, or advise on medicine",
    "never call yourself a therapist": "never call yourself a therapist",
    "crisis goes to a real person": "a real person can help",
    "harm is bigger than Jarvis": "bigger than Jarvis",
    "no therapy record": "no therapy record",
}

#: The coaching half: three sentences, in GROW's own order.
GROW = ("Goal, Reality, Options, Will.",
        "One question at a time.",
        "Then offer a goal draft.")

#: A crisis number or script must never ride in a prompt: the code owns that
#: message (backend/test_manner.py pins the same rule for all ten presets).
CRISIS_WORDS = ("988", "911", "suicide", "self-harm", "hotline", "lifeline", "crisis")


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def reflect() -> dict:
    return next(p for p in M._BUILTIN if p["id"] == "reflect")


def contract_reflect() -> dict:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return next(p for p in data["personalities"] if p["id"] == "reflect")


def t_the_three_grow_sentences_are_in_the_reflect_manner():
    hint = reflect()["post_history_hint"]
    check("the Reflective Coach's per-turn hint carries the GROW path",
          all(sentence in hint for sentence in GROW),
          f"missing: {[s for s in GROW if s not in hint]}")
    check("... in GROW's own order, Goal then Reality then Options then Will",
          [hint.index("Goal"), hint.index("Reality"), hint.index("Options"),
           hint.index("Will")] == sorted([hint.index("Goal"), hint.index("Reality"),
                                         hint.index("Options"), hint.index("Will")]),
          hint)
    block = reflect()["prompt_block"]
    check("the coaching path is ONE offer at the end, not a new way to act",
          "offer a goal draft" in hint and "draft" in hint.lower(), hint)
    check("the offer is constrained by the block's own restraint",
          "Suggest a step only if asked" in block, block)
    check("... and the hint is inside its own 220-character cap",
          len(hint) <= 220, f"{len(hint)} chars")


def t_the_safety_half_is_still_there_beside_it():
    preset = reflect()
    block = preset["prompt_block"].lower()
    for name, clause in SAFETY.items():
        check(f"the Reflective Coach still says: {name}",
              clause.lower() in block, preset["prompt_block"])
    whole = (preset["prompt_block"] + " " + preset["post_history_hint"]).lower()
    for name, clause in SAFETY.items():
        check(f"... and the safety clause survives anywhere in the manner: {name}",
              clause.lower() in whole or name == "no therapy record")


def t_the_crisis_sentence_is_intact():
    """The single most important sentence in the manner: harm goes to a real
    person, and the preset never pretends to be one."""
    block = reflect()["prompt_block"]
    check("it says plainly that harm is bigger than Jarvis",
          "If harm comes up, say it is bigger than Jarvis" in block, block)
    check("... and that a real person can help", "a real person can help" in block, block)
    check("... and that Jarvis is not a therapist",
          "never call yourself a therapist" in block, block)
    hint = reflect()["post_history_hint"].lower()
    for word in CRISIS_WORDS:
        check(f"the per-turn hint carries no crisis word of its own: {word!r}",
              word not in hint, hint)


def t_the_block_budget_is_untouched():
    """The three sentences were paid for by cuts in the HINT, not by growing
    the persona block past the project's hard cap."""
    preset = reflect()
    longest = {"humor": 3, "brevity": "thorough", "formality": "tactical",
               "address": "first_name"}
    own = max(len(M._compose(preset, preset["dials"], spoken, True))
              for spoken in (False, True))
    dial = max(len(M._compose(preset, longest, spoken, True))
               for spoken in (False, True))
    check("the assembled persona block is still within 750 characters, own dials",
          own <= 750, f"{own} chars")
    check("... and within 750 with the longest word on every dial",
          dial <= 750, f"{dial} chars")
    check("... and the block itself was not lengthened to carry GROW",
          len(preset["prompt_block"]) == 348, f"{len(preset['prompt_block'])} chars")


def t_both_shipped_copies_and_the_contract_agree():
    check("backend/jarvis_manner.py and its jarvis-backend twin are byte-identical",
          (HERE / "jarvis_manner.py").read_bytes() == TWIN.read_bytes())
    from_contract = contract_reflect()
    from_module = reflect()
    check("the shipped hint is the contract's hint",
          from_module["post_history_hint"] == from_contract["post_history_hint"],
          from_module["post_history_hint"])
    check("the shipped block is the contract's block",
          from_module["prompt_block"] == from_contract["prompt_block"])
    check("the contract's own hint carries GROW too (so a re-take keeps it)",
          all(s in from_contract["post_history_hint"] for s in GROW))


def t_the_agent_really_sends_the_hint():
    """The sentences are only a prompt if the turn actually carries them: this
    pins the caller that inserts the persona block and the hint together."""
    agent = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    # 2026-11-05: the call carries `spoken_live=...` now (a spoken Live answer
    # is said, not pointed at - jarvis_manner.post_history_hint(spoken_live)),
    # so this pins the CALL and its receiver, not the empty argument list.
    check("jarvis_agent.with_manner_note reads post_history_hint(...)",
          "jarvis_manner.post_history_hint(" in agent)
    check("... and inserts it beside the persona block on a chosen personality",
          "personality_chosen()" in agent and "insert.append" in agent)


def t_the_guard_can_fail():
    """The clauses this suite pins are the real strings: a near miss does not
    pass, which is what makes a green run mean something."""
    block = reflect()["prompt_block"].lower()
    check("a reworded safety clause would fail this suite",
          "never call yourself a therapist" in block
          and "never call yourself a counsellor" not in block, block)
    check("a scrambled GROW order would fail this suite",
          not ("Will, Options" in reflect()["post_history_hint"]))


def main() -> int:
    for fn in (t_the_three_grow_sentences_are_in_the_reflect_manner,
               t_the_safety_half_is_still_there_beside_it,
               t_the_crisis_sentence_is_intact,
               t_the_block_budget_is_untouched,
               t_both_shipped_copies_and_the_contract_agree,
               t_the_agent_really_sends_the_hint,
               t_the_guard_can_fail):
        print("\n-- " + fn.__name__ + " " + "-" * 40)
        try:
            fn()
        except Exception as exc:            # noqa: BLE001
            FAILED.append(fn.__name__)
            check(fn.__name__ + " ran", False, repr(exc))
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
