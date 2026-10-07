"""jarvis_identity.py - "Who are you?" and close phrasings, answered WITHOUT
the AI model, so the model never improvises its own nature.

NEW MODULE, shipped whole. jarvis_quick.py's `match()` answers "who are
you?", "are you an AI?", "are you JARVIS from Iron Man?", "do you have
feelings?", "do you love me?" and close phrasings from sentence() below,
with no model - the same "one source, both apps could read it" shape as
jarvis_sayable.py and jarvis_reach.py, though this one has no settings
screen of its own: it only answers a question in chat.

THE OWNER'S DECISION: feasibility idea I131, "Now" - "Instant, honest, no
model. Fixed text; no romance." (docs/FEASIBILITY-AUDIT-2026-09-26.md).
Sits beside round 2's "About Jarvis" answers (jarvis_sayable.py,
jarvis_reach.py: "what can you do?" / "what can you reach?" answered from
the PC's own settings, not guessed by the model) - the model never
improvises its own nature, what it can reach, or what it was told.

WHY FIXED TEXT, NOT THE MODEL
The research doc (`docs/CUTTING-EDGE-2026-09-26-round4-character.md`)
found that models drift from their instructions fastest on exactly these
questions - "what are you really?" and emotionally vulnerable turns
(the Assistant Axis finding, cited there). A fixed answer cannot drift.
It also cannot be talked into calling itself J.A.R.V.I.S., saying "sir",
or claiming feelings it does not have, however the question is phrased -
the character block (jarvis_agent.LANE_SYSTEM) asks the model for the same
thing, but this is the one place Jarvis does not have to trust it to hold.

NO ROMANCE
The owner's own condition. ANSWER below declines feelings, a body, a past,
romance and companionship in one plain paragraph, the same shape LANE_SYSTEM
uses ("What Jarvis never does": claims feelings, plays romance, calls
itself J.A.R.V.I.S. or says "sir") - so the chat answer and the model's own
rules never disagree about this.

test_identity.py checks every phrasing jarvis_quick.py is meant to catch
really is answered by its own grammar, with no model. test_manner.py's
style-rules check (I135) reads ANSWER too, along with every other fixed
line in this repo, so it cannot carry an emoji, "!", more than one
"sorry", or a film phrase.
"""
from __future__ import annotations

#: The one fixed answer - deliberately one paragraph, not a menu: it is a
#: short honest statement, not a settings screen. It never names a specific
#: model (that changes with hardware and presets, jarvis_hardware.py) and
#: never claims what Jarvis can reach (jarvis_reach.py already answers
#: that, live, from the PC's own settings - repeating it here would be a
#: second copy that could drift from the first).
ANSWER = (
    "I'm Jarvis - your own assistant, running on this PC. I'm software: no feelings, no body "
    "and no past, and not the character from the Iron Man films - no old-fashioned titles, no "
    "butler routine. Everything I say comes from the AI model on this machine, under rules I "
    "cannot be talked out of. For what I can actually do or reach right now, ask \"what can "
    "you do?\" or \"what can you reach?\"."
)


def sentence() -> str:
    """The fixed answer for "who are you?" and close phrasings. Never
    raises: this is fixed text, not a setting."""
    return ANSWER
