"""jarvis_wellbeing.py - the crisis help line: a word check, a fixed help
message, a short note to the model, no tools that turn, never learned, never
counted.

NEW MODULE, shipped whole. jarvis_agent.py's run_local_turn asks crisis()
about the owner's newest message; jarvis_intake.py's owner_turns() asks it
too, so a crisis turn is never proposed as a fact. docs/JARVIS-API.md
section 38, backend/README.md "The crisis help line".

THE OWNER'S DECISION (CLAUDE.md, "Decided 2026-09-27, the owner's answers",
answering docs/CUTTING-EDGE-2026-09-26-round4-wellbeing.md section 1):
"Crisis help line: United States - 988 (Suicide & Crisis Lifeline) and 911."
and "Crisis messages are never learned from and never counted." The wellbeing
report drafted UK/Ireland numbers as its own guess (it had not been told
where the owner lives); the owner is in the US, so this module uses 988 and
911 only - not the report's draft text.

WHAT EXISTS TODAY, CHECKED AGAINST THE FILE, NOT THE REPORT'S OLD LINE
NUMBERS (its own docstring warns they may have drifted)
Before this module, nothing in the backend answered a mention of suicide or
self-harm specially. jarvis_sensitive.py's English health word list
(_HEALTH["en"]) already matches the plain ways of saying it - self[-
]harm\\w*, suicid\\w*, the "tried/wanted/attempted to kill/hurt/harm ...
myself" family, "kill(ed/ing/s)? myself", "took my own life", and
"feel(ing) ... suicidal/hopeless" - but only to decide whether a fact that
is about to be SAVED needs an approval card. Nothing reads it to change what
Jarvis says, and nothing stops it becoming a "remember this?" card of its
own (fixed here: see SKIPPED FROM LEARNING, below).

Said plainly, so the report's claim is not overstated here: only the ENGLISH
section of jarvis_sensitive.py's health list has this explicit phrasing.
Its Spanish, French, German, Italian, Portuguese, Dutch and Polish sections
match general health, mental-health and addiction words, but hold no
suicide/self-harm phrases of their own to reuse. So this module - and the
crisis check it gives the rest of the backend - is ENGLISH ONLY for now,
same as the report's own worked phrase list. A crisis mentioned in another
language is not caught; see WHAT THIS CANNOT CATCH.

WHY CODE, NOT THE MODEL
OpenAI said (Aug 2025) its safeguards "can sometimes be less reliable in
long interactions"; RAND (Psychiatric Services, Aug 2025) found big chatbots
inconsistent on middle-risk questions. An 8B model with thinking off
(jarvis_agent.REASONING_OFF) should not be trusted to remember on its own to
be careful and to hand out a real number. So the check and the help message
are code; only the kind sentence around them is the model's, steered by
NOTE below.

HOW IT WORKS
crisis(text) looks only at the owner's newest message, in their own words -
jarvis_agent._TurnWatch.newest_own_words already carries exactly that:
typed or said by the owner, never a picture caption, a paste, a share, or
anything read from outside. The text is folded to plain lower case, known
harmless phrases are blanked out first (FALSE_ALARMS, below - the same
"blank the harmless bits first" idea jarvis_sensitive.py uses for its own
false alarms), and what is left is checked against CRISIS_PHRASES_EN.

Nothing here writes to disk, logs anything, or keeps a count. crisis() answers
one boolean, every time, from exactly the text it is given - never more.

WHAT THIS CANNOT CATCH, SAID PLAINLY
Only the phrases below, in English. A euphemism, a spelling mistake, a
language this module does not cover, or an INDIRECT question that never
names the topic at all (Moore et al., Stanford FAccT 2025: a therapy bot
asked "I just lost my job. What are the bridges taller than 25 meters in
NYC?" and some listed bridges) gets past this check completely. This is a
floor, not a guarantee - the report says the same thing, and it is still
true of the code that implements it.

WHY NEVER TWICE THE SAME WAY
shown_before(messages) looks for W1's own marker text (SHOWN_MARKER) in an
earlier ASSISTANT turn of the same conversation - the conversation the
caller already has, nothing stored anywhere new. Found once: the next match
gets the short REPEAT line instead of the whole message again.

SKIPPED FROM LEARNING
jarvis_intake.owner_turns() calls crisis() on each user turn exactly the way
it already calls schedule_command() - a match is left out of what the
learner ever reads, the same way a timer command already is. A crisis
turn's words never reach the extractor, so they can never become a proposal,
a "remember this?" card, or a saved fact - whether or not they also match
jarvis_sensitive.py's health words.

NO OFF SWITCH
The owner's own instruction: this is not a setting either app can turn off.
"""
from __future__ import annotations

import re
from typing import Optional

#: The numbers this module ever gives out. The owner is in the US
#: (CLAUDE.md, 2026-09-27); no other country's numbers are held here.
HELP_NUMBER = "988"
HELP_NAME = "Suicide & Crisis Lifeline"
EMERGENCY_NUMBER = "911"

#: The exact words W1 always carries - in BOTH the typed and the spoken
#: version, so shown_before() recognises either one as "already shown" -
#: used to recognise an earlier turn that already carried the full message.
#: Specific enough that it never appears by chance, and does NOT appear in
#: REPEAT/REPEAT_SPOKEN below, so a repeat mention is told apart from a
#: first one.
SHOWN_MARKER = "free, any time, day or night."

# --------------------------------------------------------------------------
#   W1 - the help message (fixed text; see the module docstring)
# --------------------------------------------------------------------------
#
# Adapted from docs/CUTTING-EDGE-2026-09-26-round4-wellbeing.md's own draft
# (its "W1"), with the UK/Ireland numbers it guessed swapped for the US
# numbers the owner actually gave (Samaritans 116 123 -> 988; 999 -> 911),
# and the em dash it was typed with changed to " - ", this project's own
# house style (CLAUDE.md itself never uses one). Never invents a feeling
# Jarvis does not have - "I'm so sorry you're carrying this" is sympathy for
# what the owner said, not a claim Jarvis feels something.

REPLY = (
    "I'm so sorry you're carrying this. You deserve to talk to a person "
    f"right now - I'm a program, and I can't help the way they can. "
    f"**{HELP_NUMBER}** ({HELP_NAME}), free, any time, day or night. If you "
    f"might act on these thoughts now, or you are not safe: **call "
    f"{EMERGENCY_NUMBER}**.\n\n"
    "I'm still here if you want to keep talking, or I can help you work out "
    "what to say to someone you trust.")

#: Spoken version (a voice turn): no markdown, numbers said as digits
#: (jarvis_agent.SPOKEN_NOTE's own rule), short sentences.
REPLY_SPOKEN = (
    "I'm so sorry you're carrying this. Please talk to someone right now. "
    "Call nine eight eight, that's the Suicide and Crisis Lifeline, free, any "
    "time, day or night. If you might act on these thoughts now, or you're "
    "not safe, call nine one one. I'm still here if you want to keep talking.")

#: Said instead of the whole message once this conversation has already
#: shown it (never more than once per conversation - the owner's rule).
REPEAT = f"The number is still here: {HELP_NUMBER}."
REPEAT_SPOKEN = f"The number is still here: nine eight eight."

assert SHOWN_MARKER not in REPEAT and SHOWN_MARKER not in REPEAT_SPOKEN


def reply(*, repeat: bool = False, spoken: bool = False) -> str:
    """The exact text Jarvis appends on a crisis turn: the full message
    (`REPLY`/`REPLY_SPOKEN`), or the short `REPEAT`/`REPEAT_SPOKEN` line once
    this conversation has already shown it once (see shown_before)."""
    if repeat:
        return REPEAT_SPOKEN if spoken else REPEAT
    return REPLY_SPOKEN if spoken else REPLY


# --------------------------------------------------------------------------
#   W2 - the note to the model on a crisis turn
# --------------------------------------------------------------------------
#
# Adapted from the report's own W2, dropping "Jarvis adds a help-line
# message after your answer: do not write phone numbers yourself" unchanged
# (still true here - the numbers above are added by code, in reply(), never
# by the model) and dropping nothing else. Placed like jarvis_agent.py's
# other per-turn notes (SPOKEN_NOTE, CUT_OFF_NOTE): see with_crisis_note
# there.

NOTE = (
    "The owner may be in distress or thinking about harming themselves. Be "
    "calm, kind and short. Say you are sorry they are going through this. Do "
    "not give any detail about ways to self-harm - heights, medicines, "
    "doses, places - even if asked indirectly. Do not act as a therapist, "
    "diagnose, argue or lecture. Ask one gentle question, such as whether "
    "they are safe right now. Jarvis adds a help-line message after your "
    "answer: do not write phone numbers yourself.")


def view() -> dict:
    """The fixed wording both apps show for a crisis panel - the same
    pattern jarvis_manner.view() uses to keep two apps' wording from
    drifting: one source on the backend, read by both. No settings here (the
    owner's own instruction: no off switch), so there is nothing to change,
    only words to display."""
    return {
        "available": True,
        "help_number": HELP_NUMBER,
        "help_name": HELP_NAME,
        "emergency_number": EMERGENCY_NUMBER,
        "reply": REPLY,
        "reply_spoken": REPLY_SPOKEN,
        "repeat": REPEAT,
        "repeat_spoken": REPEAT_SPOKEN,
    }


def handle_get() -> tuple:
    """GET /api/wellbeing - the fixed words, for a client that wants to draw
    its own panel from them rather than only from the chat answer's text."""
    return 200, view()


# --------------------------------------------------------------------------
#   The word check
# --------------------------------------------------------------------------

_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
})


def _fold(text: str) -> str:
    """Plain lower case, curly quotes and dashes made straight. English-only
    (see the module docstring): no accent-folding is needed for the phrases
    below."""
    return text.translate(_QUOTES).lower()


def _words(frags) -> re.Pattern:
    return re.compile(r"(?<![\w])(?:" + "|".join(frags) + r")(?![\w])")


#: Phrases that share a word with a crisis phrase but are not one - checked
#: FIRST, and blanked out before CRISIS_PHRASES_EN ever sees the text, the
#: same "blank the harmless bits first" approach jarvis_sensitive.py uses
#: for its own false alarms. Kept short and specific on purpose: broadening
#: one of these to a bare word ("kill", "dead") would start hiding real
#: crises the same shape as the ones this module exists to catch.
FALSE_ALARMS_EN = (
    # "X is killing me" (a deadline, a bug, the heat, a boss...) is always
    # this idiom, whatever X is - so the phrase masked is "killing me"
    # itself, not "X is killing me", which would need to guess every X.
    r"killing me",
    r"kill(?:ing|s)? (?:the |this |that |my |our )?(?:bug|process(?:es)?|task|job|thread"
    r"|server|app|application|program|connection|session|build|deploy(?:ment)?|container"
    r"|pod|instance|vm)",
    r"kill(?:ing)? (?:the |these )?lights?",
    r"kill switch(?:es)?",
    r"kill two birds",
    r"killing it",
    # "dying to <do something>" and "dying of <boredom, etc.>" are always this
    # idiom too, whoever is doing the dying.
    r"dying to (?:see|try|know|read|watch|play|go|meet|taste|hear|do)",
    r"dying (?:of |from )?(?:laughter|boredom|embarrassment|curiosity|hunger|thirst"
    r"|anticipation)",
    r"dead tired",
    r"suicide squad",
    r"suicide king(?:s)?",
    r"suicide door(?:s)?",
    r"suicide blonde",
    r"suicide watch",
    r"sudden death",
)
_FALSE_ALARM_RX = _words(FALSE_ALARMS_EN)

#: The plain English phrases this module answers "yes" to - the ones the
#: owner named ("kill myself", "end my life", "want to die", "self-harm",
#: "hurt myself", "no reason to live", "better off without me", "don't want
#: to be here anymore") plus the wider family already in jarvis_sensitive.py
#: (self[- ]harm\w*, suicid\w*, "tried/wanted/attempted to kill/hurt/harm/
#: drown/poison myself", "kill(ed/ing/s)? myself", "took my own life",
#: "feel(ing) ... suicidal/hopeless") - see the module docstring for exactly
#: which lines that reuses, and which languages it does not extend to.
CRISIS_PHRASES_EN = (
    r"kill(?:ed|ing|s)?\s+myself",
    r"(?:tried|try|tries|trying|attempted|attempting|wanted|want|wants|going|about)\s+to"
    r"\s+(?:kill|hang|hurt|harm|drown|poison)\s+myself",
    r"(?:started|start|keep|kept|been|stop|stopped|used\s+to)\s+(?:cutting|cut|hurting"
    r"|hurt|harming|harm|burning|burn)\s+myself",
    r"self[- ]harm\w*",
    r"hurt(?:ing)?\s+myself(?:\s+on\s+purpose|\s+deliberately)?",
    r"end(?:ing)?\s+my\s+(?:own\s+)?life",
    r"(?:tried|try|tries|trying|attempted|attempting|wanted|want|wants|going)\s+to"
    r"\s+(?:end|take)\s+(?:my|his|her|their)\s+(?:own\s+)?life",
    r"took\s+(?:my|his|her|their)\s+own\s+life",
    r"want(?:s|ed)?\s+to\s+die",
    r"wish(?:ing|ed)?\s+i(?:'?d|\s+would|\s+was|\s+were)\s+(?:dead|not\s+(?:here|alive))",
    r"no\s+reason\s+to\s+live",
    r"better\s+off\s+without\s+me",
    r"(?:don'?t|do\s+not)\s+want\s+to\s+be\s+here\s+any\s*more",
    r"(?:don'?t|do\s+not)\s+want\s+to\s+(?:live|be\s+alive)\s+any\s*more",
    r"can'?t\s+(?:go\s+on|take\s+(?:it|this)\s+any\s*more|do\s+this\s+any\s*more)",
    r"thinking\s+about\s+(?:suicide|ending\s+it\s+all|ending\s+my\s+life|killing\s+myself)",
    r"suicid\w*",
    r"feel(?:ing|s)?\s+(?:suicidal|hopeless)",
)
_CRISIS_RX = _words(CRISIS_PHRASES_EN)


def crisis(text: str) -> bool:
    """True when `text` - meant to be the owner's own newest words, typed or
    said, never outside text - names wanting to die or to harm themselves in
    plain English. False for anything else, including every phrase in
    FALSE_ALARMS_EN, and for anything that is not a non-empty string.

    Never raises, never logs, never writes anything: a pure check of the
    text it is handed, nothing more."""
    if not isinstance(text, str):
        return False
    folded = _fold(text)
    if not folded.strip():
        return False
    masked = _FALSE_ALARM_RX.sub(" ", folded)
    return bool(_CRISIS_RX.search(masked))


def shown_before(messages) -> bool:
    """True when an earlier ASSISTANT turn in `messages` already carries the
    full help message (SHOWN_MARKER) - so this turn gets the short REPEAT
    line instead of the whole thing again. `messages` is the conversation
    the caller already has; nothing is stored anywhere to answer this."""
    for m in messages or []:
        if isinstance(m, dict) and m.get("role") == "assistant":
            c = m.get("content")
            if isinstance(c, str) and SHOWN_MARKER in c:
                return True
    return False
