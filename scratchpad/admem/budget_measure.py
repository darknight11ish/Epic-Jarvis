"""Scratch measurement for docs/ADAPTIVE-MEMORY-DESIGN.md - NOT a deliverable.

It is kept in the repository because the design document quotes its output as
evidence (section 8), and a quoted number should be reproducible. It changes
nothing: it imports `jarvis_agent`, calls the project's own
`estimate_tokens` and `fit_messages`, and prints. No file is written and no
model is asked anything.

It answers one question, with the project's own estimator and its own budget
formula (the nested `budget()` inside `run_local_turn`, `jarvis_agent.py`):
on a 4,096-token context and on a 16,384-token context, how many of the ten
exchanges the two apps are allowed to send actually reach the model today?

Run from the repository root:

    py -3 scratchpad/admem/budget_measure.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

import jarvis_agent as AG  # noqa: E402

#: A made-up conversation with the shape a real one has: a short question and
#: an answer of a realistic length (the project's own allowance is 1,024
#: tokens, so ~400 tokens of answer is an ordinary one, not a long one).
QUESTION = "How do I get the boiler to stop making that noise at night?"
ANSWER = ("That noise is almost always the pump running at a speed the pipework "
          "resonates with. Three things usually settle it, cheapest first. ") * 4


def ten_exchanges() -> list:
    """What the apps are allowed to send: MAX_EXCHANGES = 10 pairs."""
    msgs = []
    for i in range(10):
        msgs.append({"role": "user", "content": f"{QUESTION} (question {i + 1})",
                     "provenance": "typed"})
        msgs.append({"role": "assistant", "content": ANSWER})
    return msgs


def budget(n_ctx: int, schemas: int) -> int:
    """`budget()` from jarvis_agent.run_local_turn, copied exactly."""
    return max(512, n_ctx - AG.DEFAULT_MAX_TOKENS - AG._TEMPLATE_TOKENS - schemas)


def shown_schemas(short: bool) -> int:
    """What the tool schemas cost, built by the project's own two functions."""
    names = AG.offered_tools(None)          # None means "every tool here"
    was = AG.short_list_on
    AG.short_list_on = lambda: short
    try:
        offer = AG._new_offer(names, set())
        AG._fill_offer(offer, names)
        return AG.estimate_tokens(offer["schemas"])
    finally:
        AG.short_list_on = was


def main() -> None:
    msgs = ten_exchanges()
    conversation_tokens = AG.estimate_tokens(msgs)

    print(f"jarvis_agent: {AG.__file__}")
    print(f"offered_tools(None) = {len(AG.offered_tools(None))} tools")
    print(f"DEFAULT_MAX_TOKENS = {AG.DEFAULT_MAX_TOKENS}")
    print(f"DEFAULT_CONTEXT    = {AG.DEFAULT_CONTEXT}")
    print(f"_TEMPLATE_TOKENS   = {AG._TEMPLATE_TOKENS}")
    print(f"the ten exchanges  = {conversation_tokens} tokens")
    print()

    for label, short in (("every tool (the shipped default)", False),
                         ("the short list (ships off)", True)):
        schemas = shown_schemas(short)
        print(f"{label}: schemas = {schemas} tokens")
        print("  budget() = max(512, n_ctx - max_tokens - _TEMPLATE_TOKENS - schemas):")
        for n_ctx in (4096, 16384, 32768):
            b = budget(n_ctx, schemas)
            kept = sum(1 for m in AG.fit_messages(msgs, b) if m.get("role") == "user")
            print(f"    n_ctx={n_ctx:6d} -> budget={b:6d} -> "
                  f"{kept} of 10 turns kept")
        print()


if __name__ == "__main__":
    main()
