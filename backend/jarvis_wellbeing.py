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

THE SERIOUS MOMENT (the owner's decision, 2026-09-28)
"At serious moments the animals drop the cute gestures": while a crisis
answer is being given, the animal faces show a neutral pose and Jarvis
speaks in its plain built-in voice - not an animal's voice, no pitch rise.
serious_begin()/serious_end()/serious_calm() below keep one in-memory
window (timestamps only - never a word of the turn); jarvis_speech.say()
asks speak_plainly(text) per sentence, and both apps hear of the window as a
`wellbeing` event, {"serious": true | false} - see "The serious moment"
further down, and docs/JARVIS-API.md section 38.1.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

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
    only words to display - and `serious`, whether the serious moment is on
    now (see "The serious moment" below)."""
    return {
        "available": True,
        "help_number": HELP_NUMBER,
        "help_name": HELP_NAME,
        "emergency_number": EMERGENCY_NUMBER,
        "reply": REPLY,
        "reply_spoken": REPLY_SPOKEN,
        "repeat": REPEAT,
        "repeat_spoken": REPEAT_SPOKEN,
        # The serious moment (below; 2026-09-28): a crisis answer is being
        # given or spoken right now - the one live field, for an app that
        # (re)connected and missed the `wellbeing` event.
        "serious": serious_now(),
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


# --------------------------------------------------------------------------
#   The serious moment (the owner's decision, 2026-09-28)
# --------------------------------------------------------------------------
#
# "At serious moments the animals drop the cute gestures": for a crisis
# answer the animal faces show a neutral pose, and Jarvis speaks in its
# PLAIN built-in voice - the owner's own built-in choice, no animal voice, no
# pitch rise (jarvis_voices.plain_voice). A voice the owner recorded still
# speaks as it always does; only "Voice follows the face" is set aside.
#
# WHY A WINDOW, NOT A FLAG ON THE SAY REQUEST
# Both apps speak an answer one sentence at a time, each through
# `POST /api/voice/say {"text": ...}` - and that route hands say() the text
# and nothing else. Telling it "this sentence is from a crisis answer" per
# request would need both apps changed first. Instead the PC keeps ONE
# window here: opened when a crisis turn starts (run_local_turn, before the
# first word), and when the turn ends, kept open long enough to SPEAK the
# whole answer at the slowest speaking speed (serious_end). Every sentence
# say() makes while it is open is plain. It closes early when the owner's
# next ordinary question starts (serious_calm) - both apps drop whatever of
# the last answer was still queued to be said at that moment, so nothing of
# the crisis answer is left to speak.
#
# AND THE HELP WORDS THEMSELVES, WHATEVER THE WINDOW SAYS
# help_words(text) recognises the fixed help message (REPLY, REPLY_SPOKEN,
# REPEAT, REPEAT_SPOKEN) in a sentence - so "Call nine eight eight" is said
# plainly even if it is spoken long after the window closed (a paused
# answer, a "read it again").
#
# WHAT IS KEPT: two timestamps and a counter, in memory. Never a word of the
# turn, never on disk, never logged; gone when the backend restarts. The
# answer's LENGTH is used once, to work out how long the window stays open,
# and not kept. The event carries one boolean.
#
# ERRING ON THE SAFE SIDE: a sentence said inside the window that was NOT
# part of the crisis answer (an alarm's words a minute later) is also said
# plainly, and the faces stay neutral for up to SERIOUS_GRACE_MAX_SECONDS
# after the answer ended. The opposite mistake - an animal's voice reading
# out the help line - is the one this is here to prevent.

#: The event both apps hear: {"serious": true} as a crisis answer starts,
#: {"serious": false} when the window closes. One boolean, nothing else.
SERIOUS_EVENT = "wellbeing"
#: A crisis turn that never reported its end (a crash mid-turn) stops
#: counting as serious after this long.
SERIOUS_OPEN_MAX_SECONDS = 600.0
#: After the turn ends: at least this long, at most SERIOUS_GRACE_MAX.
SERIOUS_GRACE_MIN_SECONDS = 30.0
SERIOUS_GRACE_MAX_SECONDS = 300.0
#: The slowest built-in speaking pace ("Slower", 0.5x of Kokoro's ~2.5
#: words a second), a little under, so the window outlasts the speech.
SLOWEST_WORDS_PER_SECOND = 1.2

_SERIOUS_LOCK = threading.Lock()
_SERIOUS = {"gen": 0, "open": False, "since": 0.0, "until": 0.0}

#: Stand-ins for tests: the clock, a timer and the event bus.
_now: Callable[[], float] = time.monotonic


def _later(seconds: float, fn: Callable[[], None]) -> None:
    t = threading.Timer(max(0.0, float(seconds)), fn)
    t.daemon = True
    t.start()


def _publish(serious: bool) -> None:
    """The `wellbeing` event, best-effort: a missing bus changes nothing."""
    try:
        import jarvis_events
        jarvis_events.BUS.publish(SERIOUS_EVENT, {"serious": bool(serious)})
    except Exception:
        pass


def _serious_locked(now: float) -> bool:
    s = _SERIOUS
    if s["open"]:
        return now - s["since"] < SERIOUS_OPEN_MAX_SECONDS
    return now < s["until"]


def serious_now() -> bool:
    """True while a crisis answer is being given, or may still be being
    spoken (see above). Never raises."""
    try:
        with _SERIOUS_LOCK:
            return _serious_locked(_now())
    except Exception:
        return False


def grace_seconds(words: int) -> float:
    """How long the window stays open after a crisis turn of `words` words
    ends: long enough to speak it all at the slowest pace, within limits."""
    try:
        n = max(0, int(words))
    except (TypeError, ValueError):
        n = 0
    return float(min(SERIOUS_GRACE_MAX_SECONDS,
                     SERIOUS_GRACE_MIN_SECONDS + n / SLOWEST_WORDS_PER_SECOND))


def serious_begin() -> None:
    """A crisis turn starts (jarvis_agent.run_local_turn, before its first
    word): the window opens and both apps are told. Never raises."""
    try:
        with _SERIOUS_LOCK:
            _SERIOUS.update(gen=_SERIOUS["gen"] + 1, open=True, since=_now(), until=0.0)
    except Exception:
        return
    _publish(True)


def serious_end(words: int = 0) -> None:
    """The crisis turn ended, `words` long: the window stays open until the
    answer can have been spoken (grace_seconds), then closes by itself and
    both apps are told. Never raises."""
    try:
        grace = grace_seconds(words)
        with _SERIOUS_LOCK:
            if not _SERIOUS["open"]:
                return
            gen = _SERIOUS["gen"]
            _SERIOUS.update(open=False, until=_now() + grace)
        _later(grace, lambda: _expire(gen))
    except Exception:
        pass


def _expire(gen: int) -> None:
    """The timer serious_end started: closes the window it was set for -
    not a newer one a later crisis turn opened."""
    try:
        with _SERIOUS_LOCK:
            if _SERIOUS["gen"] != gen or _SERIOUS["open"] or not _SERIOUS["until"]:
                return
            _SERIOUS.update(until=0.0)
    except Exception:
        return
    _publish(False)


def serious_calm() -> None:
    """The owner's next ordinary question starts: an ENDED crisis answer's
    window closes now (both apps drop what was left of that answer to say).
    A crisis turn still being answered - another device's - is left alone.
    Tells both apps only when something was open. Never raises."""
    try:
        with _SERIOUS_LOCK:
            # `until` still set means the closing `false` has not been sent
            # yet (_expire clears it when it sends one) - even if the time
            # just ran out and the timer is a moment late - so it is sent
            # here, once; the late timer then finds a newer `gen` and stays
            # quiet.
            if _SERIOUS["open"] or not _SERIOUS["until"]:
                return
            _SERIOUS.update(gen=_SERIOUS["gen"] + 1, until=0.0)
    except Exception:
        return
    _publish(False)


def _reset_serious_for_tests() -> None:
    with _SERIOUS_LOCK:
        _SERIOUS.update(gen=0, open=False, since=0.0, until=0.0)


def _plain_words(text: str) -> str:
    """Lower case letters and digits only, one space between: how a
    sentence is compared with the fixed help texts, whatever markdown,
    punctuation or curly quotes either side had."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _fold(text)).split())


_HELP_TEXTS = tuple(_plain_words(t) for t in (REPLY, REPLY_SPOKEN, REPEAT, REPEAT_SPOKEN))
#: A piece of the help message this long or longer, found in a sentence (or
#: a sentence found inside the help message), is the help message. Shorter
#: pieces ("I'm still here.") are ordinary words too.
_HELP_MIN = 24
_HELP_PIECES = tuple(sorted({
    p for t in (REPLY, REPLY_SPOKEN, REPEAT, REPEAT_SPOKEN)
    for p in (_plain_words(x) for x in re.split(r"[.!?\n]+", t))
    if len(p) >= _HELP_MIN}))
#: The words that are only ever the help line, however a sentence is cut
#: (both apps start speaking at the first comma).
_HELP_RX = re.compile(r"(?<![0-9a-z])(?:988|nine eight eight|crisis lifeline"
                      r"|call 911|call nine one one)(?![0-9a-z])")


def help_words(text: str) -> bool:
    """True when `text` - one sentence or phrase about to be spoken - is
    part of the fixed help message, or names the help line. Never raises."""
    if not isinstance(text, str):
        return False
    try:
        t = _plain_words(text)
    except Exception:
        return False
    if not t:
        return False
    if _HELP_RX.search(t):
        return True
    if len(t) >= _HELP_MIN and any(t in h for h in _HELP_TEXTS):
        return True
    return any(p in t for p in _HELP_PIECES)


def speak_plainly(text: str = "") -> bool:
    """jarvis_speech.say()'s one question: say this in the plain built-in
    voice, not an animal's? True inside the serious window, or for the help
    message's own words. Never raises."""
    return serious_now() or help_words(text)
